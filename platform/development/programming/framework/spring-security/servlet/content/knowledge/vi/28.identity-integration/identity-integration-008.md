# SAML2 Login: RelyingPartyRegistration, metadata và ánh xạ thuộc tính

> **Phạm vi:** Spring Security 6.x trên **Servlet stack** (Spring MVC, Spring Boot 3.x, Java 17+, Jakarta Servlet). Bài này giải thích ứng dụng Spring đóng vai **SAML 2.0 Service Provider / Relying Party (SP/RP)**, cách tạo và tra `RelyingPartyRegistration`, trao đổi metadata với Identity Provider (IdP), tiếp nhận `SAMLResponse`, đọc và ánh xạ SAML attributes thành danh tính/quyền của ứng dụng. Các ví dụ Spring cần dependency của dự án; không phải chương trình Java SE chạy độc lập bằng `javac`.

## 1. SAML2 Login giải quyết vấn đề gì?

Trong môi trường doanh nghiệp, người dùng có thể đã được quản lý tại một IdP (ví dụ hệ thống SSO nội bộ). Ứng dụng web không cần tự quản lý mật khẩu nếu tin cậy IdP và cấu hình SAML 2.0 đúng cách. Ở mô hình này:

- **Identity Provider (IdP), còn được gọi là Asserting Party:** hệ thống xác thực người dùng và phát hành SAML assertion/response theo thỏa thuận tin cậy.
- **Service Provider (SP), còn được gọi là Relying Party:** ứng dụng Spring tiếp nhận response, xác minh các điều kiện bảo mật của SAML, tạo `Authentication` và phiên đăng nhập ứng dụng.
- **SAML Assertion:** khẳng định của IdP về subject (người dùng), thời điểm/điều kiện hiệu lực, phương thức xác thực và những attributes được cung cấp.
- **SAML Response:** thông điệp đưa assertion từ IdP đến SP. Có thể được ký, có assertion ký, hoặc các tổ hợp tùy cấu hình/tính hợp lệ; chữ ký phải được kiểm tra theo chính sách tin cậy của SP.
- **Binding:** cách mang SAML message qua HTTP. SP-initiated SSO thường dùng HTTP-Redirect cho `AuthnRequest`, HTTP-POST cho `SAMLResponse`.
- **Metadata:** XML mô tả entity ID, endpoints, bindings và chứng thư X.509 của một entity. Metadata là **cấu hình/trust material**, không phải thông điệp đăng nhập.

Đây là **SAML2 Login** trên server-side Servlet, khác với OAuth2 Client/OIDC. SAML uses XML assertions và trust giữa SP/IdP; OAuth2/OIDC thường dùng authorization code, access token/ID token. Đừng chuyển cấu hình SAML vào OAuth2 `ClientRegistrationRepository`.

### Kết quả mong đợi sau bài

Bạn có thể trả lời: một `registrationId` trỏ đến IdP nào, SP entity ID/ACS URL nằm ở đâu, metadata IdP/SP chứa gì, SAML Response được kiểm tra trước khi tin ở bước nào, vì sao NameID không mặc nhiên là email, và làm thế nào ánh xạ groups/roles của IdP một cách có kiểm soát.

## 2. Luồng SP-initiated SAML2 Login trên Servlet

Sơ đồ tổng quát:

~~~text
[Browser]                         [Spring Security SP]                   [IdP]
   |                                      |                                |
   | GET /saml2/authenticate/corp         |                                |
   |------------------------------------->|                                |
   |                                      | lookup RelyingPartyRegistration |
   |                                      | tạo AuthnRequest + RelayState   |
   | 302 Redirect tới IdP SSO endpoint    |                                |
   |<-------------------------------------|                                |
   | GET IdP URL với SAMLRequest/RelayState ------------------------------>|
   |                                      |                                |
   |                           (IdP xác thực user / kiểm tra policy)       |
   |                                      |                                |
   | POST /login/saml2/sso/corp           |<--- SAMLResponse + RelayState  |
   |------------------------------------->|                                |
   |                                      | decode + verify SAML response  |
   |                                      | validate issuer/audience/ACS   |
   |                                      | validate time/subject/signature|
   |                                      | create Saml2Authentication     |
   |                                      | SecurityContext + session      |
   | login success / redirect             |                                |
   |<-------------------------------------|                                |
~~~

Các bước cần hiểu:

1. Browser truy cập **đường khởi tạo đăng nhập của SP** `/saml2/authenticate/{registrationId}` (thường là đường mặc định). Spring tra `RelyingPartyRegistrationRepository` để biết IdP tương ứng.
2. Spring tạo `AuthnRequest` (có ID, issuer, ACS đích và các thông số khác); lưu thông tin correlation nếu flow yêu cầu. Tùy cấu hình và yêu cầu IdP, AuthnRequest có thể cần được **ký bằng private key của SP**.
3. Browser được chuyển sang **IdP SingleSignOnService URL**; IdP xác thực user, áp dụng chính sách doanh nghiệp, rồi phát hành SAML Response.
4. Browser POST `SAMLResponse` (thường Base64-encoded XML) tới **Assertion Consumer Service (ACS)** của SP, mặc định thường là `/login/saml2/sso/{registrationId}`.
5. Bộ xử lý SAML của Spring Security phải xác minh **chữ ký phù hợp trust**, issuer, destination/recipient, audience, thời gian hiệu lực và subject confirmation; với SP-initiated flow còn đối chiếu response với yêu cầu ban đầu (ví dụ `InResponseTo`). Chỉ sau khi hợp lệ mới đưa danh tính và attributes vào `Saml2Authentication`.
6. Sau login, Spring Security dùng `SecurityContext`/cơ chế session của Servlet để lưu trạng thái xác thực theo cấu hình. Authorization trong app vẫn phải dựa trên `GrantedAuthority`, resource ownership và policy cụ thể.

**RelayState không phải password hay bằng chứng xác thực.** Nó dùng liên kết luồng và trạng thái điều hướng theo cấu hình. Không được tin URL tùy ý trong RelayState để redirect ra ngoài mà không kiểm tra. SAML POST về ACS có thể đến từ một origin khác, nhưng điều đó **không có nghĩa** ứng dụng nên tắt CSRF trên mọi endpoint. Giữ sự phân biệt giữa ACS được filter SAML xử lý và các POST nghiệp vụ của ứng dụng.

### SP-initiated và IdP-initiated khác nhau

Với **SP-initiated**, ứng dụng bắt đầu AuthnRequest nên có cơ sở đối chiếu callback/`InResponseTo`. Với **IdP-initiated (unsolicited)**, IdP đẩy SAML Response tới ACS khi SP chưa khởi tạo request tương ứng, vì vậy thường **không có correlation** cùng mức như SP-initiated. Chỉ hỗ trợ IdP-initiated khi chính sách IdP/SP, validation, chống replay/login CSRF và risk acceptance đã được thiết kế và kiểm chứng; ưu tiên SP-initiated khi phù hợp.

## 3. RelyingPartyRegistration là gì?

`org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration` là **cấu hình quan hệ tin cậy giữa SP và một IdP**. Đối tượng này hướng dẫn Spring Security cách tạo AuthnRequest, nhận SAMLResponse, xác minh chữ ký và công bố SP metadata. Nó không lưu session đăng nhập của user và không chứa SAMLResponse hiện tại.

| Khái niệm | Ý nghĩa thực tế |
| --- | --- |
| **registrationId** | Khóa nội bộ Spring, ví dụ `corp`, dùng lựa chọn registration và trong URL login/ACS mặc định. |
| **SP entityId** | Mã định danh **Service Provider** trong giao thức SAML; IdP dùng để nhận diện audience/issuer SP. |
| **ACS location / binding** | URL tại SP nhận SAML Response, thường qua HTTP-POST. IdP phải được cấu hình đúng địa chỉ công khai này. |
| **Asserting Party entity ID** | Issuer/entity ID của IdP mà SP chấp nhận. |
| **SingleSignOnService location / binding** | Endpoint và binding mà SP dùng gửi AuthnRequest tới IdP. |
| **Verification X.509 credentials** | Public certificate(s) đáng tin để kiểm tra chữ ký của IdP. |
| **SP signing credentials** | Private key và certificate dùng khi SP phải ký AuthnRequest hoặc các thông điệp SP thích hợp. |
| **SP decryption credentials** | Private key/certificate cần khi IdP mã hóa assertion/name ID/attribute mà SP phải giải mã. |
| **Metadata** | Thông tin entity ID, endpoints, bindings và các cert để trao đổi giữa SP/IdP. |

Đừng nhầm những ID sau:

~~~text
registrationId ở Spring: "corp"                         (khóa nội bộ)
SP entityId:           "https://app.example.org/saml2/service-provider-metadata/corp"
IdP entityId:          "https://idp.example.org/metadata" (chỉ ví dụ)
IdP SSO endpoint:      "https://idp.example.org/sso"      (endpoint, không phải entity ID)
SP ACS:                "https://app.example.org/login/saml2/sso/corp"
~~~

**Entity ID là identifier**, không bắt buộc phải là URL có thể GET thành công. ID thực tế phải khớp hoàn toàn thỏa thuận tại IdP/SP. Metadata URL lại là nơi *lấy XML metadata*. Trong nhiều hệ thống ba giá trị entity ID, metadata URL và SSO endpoint khác nhau.

### Tại sao một registration chỉ đại diện một trust configuration?

Ứng dụng có thể tin nhiều IdP (ví dụ `corp` và `partners`), mỗi IdP có issuer, certificate và SSO location khác. `registrationId` dùng chọn đúng configuration. Không được nhận tùy tiện một IdP URL từ query parameter rồi tin mọi SAMLResponse từ URL đó. Với multi-tenant cần ánh xạ tenant → registration tin cậy và cô lập credentials/policy.

## 4. RelyingPartyRegistrationRepository: tra đúng cấu hình

`org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository` là interface cho phép Spring tìm RP registration theo khóa:

~~~java
RelyingPartyRegistration findByRegistrationId(String registrationId);
~~~

- Spring SAML filters dùng repository để chọn issuer, ACS URL và trust certificate tương ứng.
- Với `InMemoryRelyingPartyRegistrationRepository`, repository chứa một hoặc nhiều registrations được nạp khi khởi động.
- Nếu lookup không có kết quả, luồng không thể xây dựng/công nhận RP phù hợp; ứng dụng nên từ chối theo cơ chế framework, không chọn bừa provider khác.
- Repository **không phải** cơ sở dữ liệu password hay token; SAML Response sau khi xác minh tạo `Saml2Authentication` riêng.

Tương tự những repository cấu hình khác trong Spring Security, lựa chọn in-memory thường phù hợp khi tập IdP tương đối ổn định. Dynamic repository cần xử lý đổi cert, metadata refresh, concurrent login và nhất quán giữa AuthnRequest/ACS callback.

## 5. SAML metadata: IdP metadata và SP metadata khác nhau

Một trong các bước tích hợp quan trọng nhất là **trao đổi metadata đúng hai chiều**.

| Metadata | Ai xuất bản? | SP/IdP dùng làm gì? |
| --- | --- | --- |
| **IdP / Asserting Party metadata** | IdP | SP đọc entity ID IdP, SSO/SLO endpoints, supported bindings, verification certificates và thông số IdP. |
| **SP / Relying Party metadata** | Ứng dụng Spring (SP) | IdP nhận diện SP entity ID, ACS URL/binding, và certificate SP nếu yêu cầu signed requests/encrypted assertions. |

Ví dụ trích yếu **IdP metadata** (XML rút gọn mang tính khái niệm, không phải document đầy đủ để import):

~~~xml
<EntityDescriptor entityID="https://idp.example.org/entity">
    <IDPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <KeyDescriptor use="signing">...</KeyDescriptor>
        <SingleSignOnService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
            Location="https://idp.example.org/sso"/>
    </IDPSSODescriptor>
</EntityDescriptor>
~~~

Trong XML thật cần các namespaces chuẩn SAML metadata, nội dung `KeyInfo/X509Certificate` thực tế và đôi khi chữ ký metadata. Dấu `...` trong snippet **chỉ ký hiệu cấu trúc lược bỏ** và không được đem làm giá trị import. Đọc IdP metadata đầy đủ từ kênh được tin cậy, không viết lại thủ công nội dung certificate.

Ví dụ một đoạn **SP metadata** (cũng là sơ đồ XML rút gọn):

~~~xml
<EntityDescriptor entityID="https://app.example.org/saml2/service-provider-metadata/corp">
    <SPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <AssertionConsumerService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            Location="https://app.example.org/login/saml2/sso/corp"
            index="0"/>
    </SPSSODescriptor>
</EntityDescriptor>
~~~

Điều mà người triển khai phải đối chiếu **trên metadata thật** là: SP entity ID, ACS URL, binding, chứng thư ký/giải mã (nếu cấu hình), IdP issuer, SSO URL và chứng thư xác minh chữ ký. **Không đoán issuer bằng cách lấy metadata URL**, và không tự coi HTTPS metadata URL là đảm bảo mọi certificate đáng tin trong tương lai.

### Chứng thư metadata không phải khóa HTTPS

- **TLS certificate** bảo vệ kết nối HTTPS khi tải metadata hoặc gửi request.
- **SAML signing certificate** dùng kiểm tra chữ ký XML của SAML message/assertion, có thể khác chứng thư TLS và có vòng đời khác.
- **SP private signing key** không bao giờ xuất trong metadata; SP metadata chỉ công bố public certificate cần thiết.
- **Decryption private key** cũng phải ở server/secret store, không gửi IdP dưới dạng private material.
- Khi IdP rotate signing key, metadata có thể có nhiều cert hợp lệ trong giai đoạn chuyển tiếp. Cần có quy trình cập nhật registration/trust, không xóa cert cũ hoặc thêm cert lạ theo phản xạ.

Tải metadata từ URI đáng tin hoặc bản XML cục bộ đã được xác minh nguồn. Metadata nhận từ người dùng không tin cậy có thể gây **SSRF**, redirect tới endpoint độc hại hoặc thay đổi bộ khóa xác minh mà SP tin cậy.

## 6. Cấu hình Boot bằng IdP metadata URI

Đây là cách thường gọn nhất khi IdP cung cấp metadata đầy đủ. Dự án Servlet dùng Java 17+, Spring Boot 3.x, `spring-boot-starter-web`, `spring-boot-starter-security` và module `spring-security-saml2-service-provider`; để Spring Boot BOM quản lý dependency versions tương thích.

Ví dụ các dependencies Maven bên trong `pom.xml` (đây là **mảnh cấu hình**, không phải POM hoàn chỉnh):

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

Ví dụ `application.yml` dùng IdP giả định cung cấp SAML metadata:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
~~~

**Phân tích:**

- `corp` chính là **registrationId**. Nó xuất hiện trong URL bắt đầu login `/saml2/authenticate/corp` và ACS theo cấu hình mặc định.
- `metadata-uri` trỏ tới **IdP metadata**, từ đó Spring dựng cấu hình Asserting Party; đây không phải link tới SP metadata.
- Để chạy thật, thay bằng metadata URL của IdP thực tế có thể truy cập, được xác minh provenance, chứa issuer/endpoints/verification certificates hợp lệ. Trong nhiều cách nạp, metadata được đọc lúc dựng registration/startup; **đừng mặc định thư viện sẽ tự refresh certificate** khi IdP rotate key.
- Boot có thể tạo `RelyingPartyRegistrationRepository` từ YAML nếu không có bean do app tự định nghĩa. Nếu đã tạo repository bằng Java, các registration YAML **không nhất thiết tự hợp nhất**; chọn một cách quản lý nhất quán.
- Khi IdP yêu cầu signed AuthnRequest hoặc encrypted assertions, cần thêm **signing** hoặc **decryption credentials** cho SP; không tự suy ra chúng từ IdP metadata. Các private keys phải được bảo vệ riêng.

### Lưu ý về signing/decryption

Trong cấu hình Boot, SP signing credential thường gồm **private-key-location** và **certificate-location**; IdP verification credentials là public certificates từ IdP metadata. Ví dụ cấu trúc tùy chọn:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            signing:
              credentials:
                - private-key-location: classpath:saml/sp-signing.key
                  certificate-location: classpath:saml/sp-signing.crt
~~~

Đây là **mảnh bổ sung** cho `registration.corp`, không phải cấu hình YAML hoàn chỉnh và không chỉ ra private key thật. Trong production không commit private key vào repository nếu không có cơ chế bảo vệ phù hợp; dùng secret store, filesystem permissions và rotation process. Nếu IdP không yêu cầu SP ký request thì không nên thêm signing credentials chỉ để “có đủ trường”.

## 7. Cấu hình SecurityFilterChain và endpoint mặc định

Ví dụ class `SamlSecurityConfig.java` trong package được Boot component-scan. Nó sử dụng repository từ YAML ở trên; ví dụ dành cho **Spring Security 6.1+** để dùng DSL `saml2Metadata`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                        "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Các vai trò:

- `.saml2Login(...)` bật filter/handlers cho SAML2 SSO trên Servlet stack. Cần `RelyingPartyRegistrationRepository` hợp lệ.
- `.saml2Metadata(...)` bật việc công bố metadata SP trên endpoint do Spring Security hỗ trợ, thường dùng `/saml2/service-provider-metadata/{registrationId}`. Kiểm tra chính URL thực tế ở phiên bản/framework đang triển khai.
- `anyRequest().authenticated()` yêu cầu xác thực trước khi vào tài nguyên còn lại. Để triển khai quyền admin/nhân viên, phải **ánh xạ SAML attributes thành `GrantedAuthority`** và cấu hình authorize tương ứng.
- `permitAll` ở SP metadata không có nghĩa các path nghiệp vụ cũng công khai. Metadata thường cần được IdP/admin truy cập để đăng ký SP; nếu có chính sách bảo mật riêng hãy quyết định phạm vi cho đúng.
- Cấu hình này **không** ép bỏ CSRF protection, không thay đổi session policy, không tự bật single logout hay mapping groups. Các tính năng đó phải kiểm thử/cấu hình phù hợp.
- Với reverse proxy, cần tạo SP entity ID/ACS bằng **public HTTPS base URL** được tin cậy; tránh request-generated metadata mang `http://localhost:8080` hoặc host nội bộ khi IdP chỉ biết hostname public. Chỉ chấp nhận forwarded headers từ proxy do mình kiểm soát.

### Những URL cần đối chiếu

| Đường / thông số | Ý nghĩa |
| --- | --- |
| `/saml2/authenticate/corp` | URL SP thường dùng khởi tạo SAML AuthnRequest tới IdP. |
| `/login/saml2/sso/corp` | ACS endpoint mặc định thường xử lý SAML Response POST. |
| `/saml2/service-provider-metadata/corp` | URL metadata SP điển hình khi `saml2Metadata` được bật. |
| **SP entity ID** | ID bên trong SAML XML và SP metadata; phải đăng ký đúng với IdP. |
| **IdP SSO URL** | Endpoint bên IdP nhận AuthnRequest; đọc từ metadata IdP. |
| **IdP issuer/entity ID** | Giá trị mà Spring đối chiếu với issuer SAML response/assertion theo trust configuration. |

Các đường trên có thể được customize và còn chịu Servlet context path. **Đừng lấy endpoint mặc định làm bằng chứng** URL công khai đã đúng khi ứng dụng chạy phía sau proxy hoặc trong đường dẫn con.

## 8. Tạo RelyingPartyRegistration bằng Java nếu không dùng Boot YAML

Bạn có thể dùng factory `RelyingPartyRegistrations.fromMetadataLocation(...)` và repository in-memory. Ví dụ `SamlRegistrationConfig.java` là **phương án thay thế** YAML `spring.security.saml2.relyingparty.registration.corp`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

@Configuration
public class SamlRegistrationConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
        RelyingPartyRegistration corp = RelyingPartyRegistrations
                .fromMetadataLocation("https://idp.example.org/saml/metadata")
                .registrationId("corp")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }
}
~~~

- `fromMetadataLocation(...)` xây registration từ **IdP metadata**. URL chỉ minh họa; code sẽ cần metadata thật/trusted để khởi tạo thành công.
- `registrationId("corp")` là khóa nội bộ dùng lookup/URLs, không phải IdP entity ID.
- `build()` tạo cấu hình; nó chưa đăng nhập người dùng.
- Repository nhận một hoặc nhiều registrations, để Spring Security dùng trong filter chain.
- Nếu IdP cần SP-specific entity ID, ACS URL hoặc signing credentials, phải bổ sung vào builder/cấu hình trước `build()` theo hợp đồng với IdP; không phụ thuộc mù vào mặc định.
- **Không cấu hình song song hai bean repository cùng kiểu** rồi mong Boot tự hợp nhất. Một nguồn registration rõ ràng giúp tránh callback sai issuer/certificate.

Đây là class Spring có dependency và IdP metadata thật; không chạy độc lập với `javac/java` trần. Test unit có thể cấu trúc repository bằng metadata fixture cục bộ/trustworthy và xác minh lookup, nhưng test end-to-end cần một IdP thực hoặc sandbox.

## 9. Truy cập thông tin user từ Saml2Authentication

Khi SAML Response được xác minh thành công, Spring Security có thể tạo `Saml2Authentication` với principal thực hiện `Saml2AuthenticatedPrincipal`. Thông tin quan trọng gồm **NameID** (`getName()`) và các SAML attributes (`getAttributes()`, `getFirstAttribute(...)`).

### 9.1 NameID không mặc nhiên là email

Trong SAML, subject có thể chứa NameID với format khác nhau: persistent, transient, email-address hoặc identifier riêng IdP. Ví dụ:

~~~text
SAML Subject/NameID = "A7D0C1E4F..."
Attribute Name="email" = "lan@example.org"
Attribute Name="displayName" = "Lan Nguyễn"
Attribute Name="groups" = ["employees", "app-report-readers"]
~~~

Cấu trúc trên chỉ là dữ liệu ví dụ. `NameID` có thể là ID không đọc được và cần được xem là **khóa định danh ổn định** chỉ khi IdP thực sự cam kết tính ổn định, uniqueness và ranh giới tenant. Không tự dùng email làm primary key nếu email có thể đổi/tái cấp. Nếu IdP chuyển NameID từ persistent sang transient, chiến lược liên kết account cần được đánh giá lại.

### 9.2 Đọc attributes trong Spring MVC Controller

Ví dụ file `SamlProfileController.java` với endpoint yêu cầu login thành công:

~~~java
package com.example.web;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SamlProfileController {

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        String nameId = principal.getName();
        String email = principal.getFirstAttribute("email");
        String displayName = principal.getFirstAttribute("displayName");

        Map<String, String> result = new LinkedHashMap<>();
        result.put("subject", nameId);
        result.put("email", email == null ? "" : email);
        result.put("displayName",
                displayName == null ? "" : displayName);
        return result;
    }
}
~~~

Code này yêu cầu SAML2 login đã thành công, `/me` được bảo vệ bởi `authenticated()` và IdP thực sự phát các attribute names `email`/`displayName` (nếu không chúng trả `null`). Nó **không tạo thông tin giả** nếu IdP không cung cấp. Không trả dữ liệu SAML nhạy cảm ra public endpoint, nhất là `getAttributes()` toàn bộ, SAML Response XML hoặc session index.

Một response minh họa với dữ liệu giả định ở trên:

~~~json
{
  "subject": "A7D0C1E4F...",
  "email": "lan@example.org",
  "displayName": "Lan Nguyễn"
}
~~~

Đây là JSON **giả định** nếu IdP phát đúng attributes; Spring Security không bảo đảm các keys hay giá trị trên trong mọi môi trường.

### 9.3 Attribute Name, FriendlyName và URI/OID

SAML assertion có thể gửi tên thuộc tính theo nhiều cách: `Name="email"`, `Name="urn:oid:0.9.2342.19200300.100.1.3"`, `FriendlyName="mail"` hoặc các URI theo schema của IdP. API `getFirstAttribute("email")` chỉ đúng khi **tên attribute thực tế** mà Spring đã nạp là `email`.

Các việc cần làm khi tích hợp:

1. Xin IdP cung cấp danh sách **Attribute Name** và mẫu response test hợp lệ (ẩn PII/keys).
2. Xác định NameID format, thuộc tính unique user ID, email, display name, groups và các danh sách giá trị.
3. Chọn một schema ổn định (tên/tên URI) cho app; không đoán từ FriendlyName hoặc tên hiện trên giao diện quản trị IdP.
4. Phân biệt attribute **single-valued** và **multi-valued**; `getFirstAttribute` chỉ lấy giá trị đầu nếu có nhiều giá trị.
5. Giữ nguyên semantic và encoding Unicode; kiểm tra trường hợp thiếu attribute, list rỗng, giá trị đổi type và thay schema.
6. Khi map account, luôn ràng buộc user với issuer/tenant tin cậy cùng ID ổn định; tránh account takeover khi email trùng giữa hai IdP.

## 10. Ánh xạ thuộc tính SAML sang vai trò Spring Security

Spring Security không thể tự suy luận `ROLE_ADMIN` từ mọi SAML attribute có chữ “admin”. SAML attributes là **dữ liệu đã được xác minh nguồn gốc** sau khi response hợp lệ, nhưng ý nghĩa của từng nhóm/role vẫn phải được ứng dụng cấu hình một cách rõ ràng.

Ví dụ IdP phát:

~~~text
Attribute Name="groups":
  - employees
  - finance-readers
  - app-admins

Policy của ứng dụng:
  employees       -> ROLE_USER
  finance-readers -> REPORT_READ
  app-admins      -> ROLE_ADMIN
~~~

**Quy tắc tốt:** dùng allowlist tên nhóm do IdP đáng tin phát, ánh xạ sang các authorities hẹp có nghĩa ở ứng dụng. Không biến mọi string nhận từ assertion thành `ROLE_*` với quyền tùy ý. Đặc biệt quyền admin phải dựa trên đúng issuer, đúng attribute name và chính sách được phê duyệt.

### 10.1 Ví dụ Java: hàm ánh xạ thuần, dễ unit test

Class `SamlGroupAuthorityPolicy.java` dưới đây chỉ minh họa **logic ánh xạ**. Nó không tự động đăng ký thành filter hoặc sửa `SecurityContext`; cần tích hợp vào giai đoạn chuyển SAML authentication thành principal/authorities theo API phù hợp **phiên bản Spring Security** đang dùng.

~~~java
package com.example.security;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;

public final class SamlGroupAuthorityPolicy {

    private SamlGroupAuthorityPolicy() {
    }

    public static Set<GrantedAuthority> map(
            Saml2AuthenticatedPrincipal principal) {

        List<String> groups = principal.getAttribute("groups");
        Set<GrantedAuthority> authorities = new HashSet<>();

        if (groups == null) {
            return Set.of();
        }
        if (groups.contains("employees")) {
            authorities.add(new SimpleGrantedAuthority("ROLE_USER"));
        }
        if (groups.contains("finance-readers")) {
            authorities.add(new SimpleGrantedAuthority("REPORT_READ"));
        }
        if (groups.contains("app-admins")) {
            authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
        }
        return Set.copyOf(authorities);
    }
}
~~~

Giải thích:

- Danh sách `groups` do IdP phát **phải được chấp nhận chỉ sau khi toàn bộ SAML assertion được xác minh thành công**. Hàm không tự verify SAML signature.
- Thiếu `groups` trả về tập quyền rỗng, nên không cấp ngầm `ROLE_ADMIN`.
- `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN` theo prefix mặc định; `hasAuthority("REPORT_READ")` kiểm tra authority chính xác là `REPORT_READ`.
- Không tự thêm quyền `ROLE_USER` cho mọi người nếu app đòi thuộc nhóm `employees`; trong ví dụ chỉ cấp quyền nếu có group tương ứng.
- Nếu IdP dùng attribute URI/OID thay `groups`, phải đổi **đúng tên** và đảm bảo danh sách kiểu dữ liệu đúng.
- Chức năng gắn authorities vào `Saml2Authentication` phụ thuộc điểm mở rộng authentication/provider của phiên bản Spring; hàm trên là **policy để tái sử dụng/test**, không phải cấu hình bảo đảm `@PreAuthorize` nhận role mới.

### 10.2 Tích hợp authority mapping ở đâu?

Các hướng triển khai thường gặp:

- Trong giai đoạn **authentication conversion** do SAML authentication provider hỗ trợ: sau khi validate response và dựng principal, lấy trusted attributes → áp dụng mapping → tạo Authentication với granted authorities phù hợp.
- Dùng **dịch vụ cấp quyền nội bộ** sau khi liên kết NameID/issuer với account doanh nghiệp; đây là lựa chọn tốt khi role mang tính nghiệp vụ, không do IdP quản lý.
- Thiết kế mapping theo **issuer + registrationId + attribute schema** khi nhiều IdP; cùng string `app-admins` từ hai IdP không mặc định cấp cùng quyền.

Đừng chỉ viết `@PreAuthorize("hasRole('ADMIN')")` rồi hy vọng IdP attribute tự trở thành authority. Phải xác minh `Authentication.getAuthorities()` trong một integration test **sau bước mapping**. Các class/OpenSAML APIs liên quan provider thay đổi qua Spring Security 6.x; khi dùng điểm mở rộng cụ thể cần kiểm tra đúng API/version thay vì sao chép snippet phiên bản khác.

### 10.3 Test policy ánh xạ không cần IdP

Trong unit test, có thể tạo principal giả bằng `DefaultSaml2AuthenticatedPrincipal` để kiểm tra mapping. Ví dụ JUnit 5 file `SamlGroupAuthorityPolicyTest.java`:

~~~java
package com.example.security;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.saml2.provider.service.authentication.DefaultSaml2AuthenticatedPrincipal;

class SamlGroupAuthorityPolicyTest {

    @Test
    void mapsOnlyAllowlistedGroups() {
        var principal = new DefaultSaml2AuthenticatedPrincipal(
                "subject-123",
                Map.of("groups", List.of("employees", "finance-readers")));

        var authorities = SamlGroupAuthorityPolicy.map(principal)
                .stream()
                .map(a -> a.getAuthority())
                .toList();

        assertTrue(authorities.contains("ROLE_USER"));
        assertTrue(authorities.contains("REPORT_READ"));
        assertFalse(authorities.contains("ROLE_ADMIN"));
    }
}
~~~

Test này chỉ xác nhận **quy tắc map groups** của class Java, không chứng minh SAML signature, issuer, ACS callback hoặc filter chain hoạt động. Test tích hợp phải dùng IdP test/sandbox và response ký hợp lệ để xác nhận trust chain cùng authentication/authorization thực tế.

## 11. Điều kiện bảo mật không được bỏ qua khi kiểm tra SAML Response

Không nên tự parse `SAMLResponse` bằng XML parser rồi gọi `SecurityContextHolder.getContext().setAuthentication(...)` chỉ dựa vào trường NameID hoặc email. Cần để SAML authentication provider xác minh message và các điều kiện bắt buộc.

Các nhóm kiểm tra quan trọng:

- **Signature & trust:** chữ ký assertion/response hợp lệ theo chính sách SP, chứng thư được phép từ IdP tương ứng; không tin bất kỳ cert nào tự xuất hiện trong response.
- **Issuer:** assertion/response xuất phát từ IdP entity ID dự kiến cho registration, không phải issuer tùy ý.
- **Audience restriction:** assertion được phát cho đúng SP entity ID. Assertion của ứng dụng A không được dùng để đăng nhập ứng dụng B.
- **Destination/Recipient/ACS:** response được gửi đúng endpoint của SP theo binding và subject confirmation phù hợp; không nhận response gửi cho SP khác.
- **Time conditions:** `NotBefore`, `NotOnOrAfter` và subject confirmation phải hợp lệ với clock skew hợp lý; không tắt kiểm tra thời gian để né lệch giờ.
- **Correlation:** với SP-initiated flow kiểm tra request ID và `InResponseTo`, RelayState/session correlation khi áp dụng.
- **Replay:** không chấp nhận assertion/response đã được dùng lại vượt chính sách; cách chống replay có thể đòi state store ở nhiều node.
- **XML safety:** sử dụng stack SAML/OpenSAML được hỗ trợ; không tự mở XML external entities hoặc triển khai signature validation từ đầu.
- **Attribute mapping:** chỉ tin attribute *sau* validation, map dựa vào issuer/name/schema được tin, không cấp quyền admin từ text người dùng gửi.
- **Transport:** dùng HTTPS, cookie Secure/HttpOnly và trusted reverse proxy; chữ ký SAML không thay thế việc bảo vệ cookie/session.

**SAML assertions có thể chứa PII**. Không log raw Base64 `SAMLResponse`, decrypted assertion, NameID nhạy cảm, attributes đầy đủ, private key hay session cookie. Nếu cần debug, dùng dấu vết có kiểm soát và lọc dữ liệu.

## 12. SAML POST callback, CSRF và SameSite cookie

Một điểm thực tế dễ bị bỏ sót: IdP thường trả **HTTP-POST từ domain IdP đến ACS trên domain SP**. Đó là bối cảnh **cross-site** trong browser. Nếu flow dùng HttpSession để giữ AuthnRequest trước khi redirect, mà session cookie không được gửi lại trong POST callback do `SameSite=Lax`/`Strict`, SP có thể **không đối chiếu được AuthnRequest** hoặc mất trạng thái phiên.

Điều cần kiểm tra:

1. Browser thực tế có gửi session cookie với ACS POST không? Xem DevTools “Cookies blocked reason” và cấu hình SameSite/Secure theo domain.
2. Nếu cần cookie cho cross-site POST, `SameSite=None; Secure` có thể phù hợp ở browser cho phép; phải dùng HTTPS và xét chính sách chặn third-party cookies. Không áp dụng bừa trên tất cả cookie.
3. Nếu dùng state lưu bên ngoài session hoặc cấu hình đặc thù, cần đảm bảo correlation và session fixation handling vẫn chính xác.
4. **Không tắt CSRF toàn ứng dụng.** ACS là endpoint giao thức SAML được filter authentication xử lý; cần kiểm tra request matcher/CSRF handling đúng cho callback trong cấu hình Spring Security. POST nghiệp vụ dùng session vẫn cần CSRF protection.
5. Nếu có proxy/ingress, kiểm tra public ACS URL, cookie `Domain/Path`, path rewriting và forwarded scheme. Một callback tới URL khác với URL phát trong AuthnRequest có thể bị IdP hoặc SP từ chối.

Không có một giá trị SameSite phù hợp cho tất cả hệ thống SAML. Hãy kiểm chứng với **IdP, binding và trình duyệt thực tế**.

## 13. Môi trường multi-node, khóa ký và metadata rotation

Trong triển khai nhiều instance SP:

- **State correlation / sessions:** AuthnRequest có thể bắt đầu ở node A, callback rơi vào node B. Cần sticky session hoặc session/state store phù hợp; không “sửa” bằng cách bỏ `InResponseTo` verification.
- **Clock skew:** đồng bộ NTP và cấu hình khoảng lệch giờ theo chính sách; lệch giờ gây lỗi `NotBefore`/`NotOnOrAfter`.
- **IdP certificate rotation:** theo dõi thời hạn, cập nhật trusted IdP verification credentials từ nguồn metadata đáng tin, hỗ trợ giai đoạn overlap key đúng cách.
- **SP signing/decryption keys:** bảo vệ private keys, có chiến lược rotation, xuất đúng public certificates trong SP metadata cho IdP; không dùng private key thử nghiệm trong production.
- **Metadata cache:** nếu registration được dựng từ IdP metadata tại startup, không giả định cert mới được load tự động giữa runtime. Có quy trình re-fetch/redeploy/update repository và rollback được kiểm chứng.
- **Multiple IdPs/tenants:** chọn registration dựa vào ngữ cảnh tenant đã được xác thực/kiểm soát, không để request tự chỉ định issuer bất kỳ. Mỗi registration có entity IDs và keys đúng.
- **Logout:** local Spring logout và SAML Single Logout (SLO) là những cơ chế khác nhau; muốn SLO cần metadata, endpoints và support phù hợp của cả SP/IdP. Không hứa “logout khỏi IdP” chỉ bằng xóa Spring session.

## 14. Kiểm tra từng lớp khi tích hợp

### 14.1 Checklist theo trình tự

1. **Xác nhận config:** repository chứa đúng `registrationId=corp`; SP entity ID và ACS khớp cấu hình IdP; IdP issuer, SSO location và signing cert khớp metadata trusted.
2. **Kiểm tra metadata SP:** mở metadata endpoint do app công bố; kiểm tra EntityDescriptor, entity ID, ACS binding/location, public certificates nếu có. Đừng chỉ xem URL có 200 OK.
3. **Khởi tạo login:** GET `/saml2/authenticate/corp` có redirect tới đúng IdP; nhận AuthnRequest có issuer, ACS, request ID đúng theo cấu hình.
4. **Login tại IdP:** dùng tài khoản test, kiểm tra SAML Response được gửi tới ACS HTTPS public URL đã đăng ký; không đưa raw response vào ticket công khai.
5. **Xác minh SP:** chỉ khi response hợp lệ mới có `Saml2Authentication`; nếu có lỗi issuer/audience/signature/timing, request phải bị từ chối.
6. **Attributes:** kiểm tra NameID format, chính xác các tên attribute (URI/OID), single/multi values; kiểm tra missing/empty attributes.
7. **Role mapping:** chỉ những group trong allowlist mới được authority mong muốn; một IdP/tenant không được tự map thành admin của tenant khác.
8. **Session/ACS:** quan sát cookie SameSite, path, Secure và callback HTTP POST; kiểm tra state correlation trong môi trường nhiều node.
9. **Logout và role revocation:** xác nhận hành vi local session, IdP SLO nếu cần, quyền thay đổi khi group bị thu hồi.

### 14.2 Phân biệt unit test và integration test

- **Unit test:** có thể xây policy mapping và dùng `DefaultSaml2AuthenticatedPrincipal` giả để kiểm tra các trường hợp groups. Không chạy SAML XML validation.
- **MockMvc test:** có thể mô phỏng authentication để test controller authorization, nhưng điều đó không thay thế việc kiểm tra SAML signature, IdP trust và ACS callback.
- **Integration test:** cần IdP test hoặc fixtures SAML ký hợp lệ cùng cơ chế xác minh cấu hình; kiểm tra issuer, audience, thời gian, request correlation, cookie, metadata và lỗi ngược. Không cần gọi IdP production để test quyền map groups.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `/saml2/authenticate/corp` không bắt đầu flow | Thiếu `saml2Login`, sai registration ID, thiếu dependency hoặc filter chain không match. | Kiểm tra bean RP repository, URL, security chain và dependencies. |
| Ứng dụng khởi động lỗi khi lấy metadata | Metadata URI không truy cập được, XML không hợp lệ, issuer/endpoint thiếu hoặc TLS trust lỗi. | Kiểm tra nguồn metadata trusted, log cấu hình đã được redacted và kết nối. |
| IdP từ chối SP “unknown entity/audience” | SP entity ID hoặc metadata đăng ký tại IdP sai. | Đối chiếu entity ID trong metadata SP và cấu hình IdP. |
| IdP báo ACS/Recipient sai | ACS URL sai hostname/port/context-path, proxy forwarded headers sai hoặc path rewrite. | Kiểm tra public HTTPS URL phát trong AuthnRequest và IdP configuration. |
| `SAMLResponse` bị từ chối chữ ký | IdP signing cert rotate, verify credential sai, assertion/response không được ký đúng policy. | Kiểm tra cert chain/trust config và signature requirement; không disable verify. |
| `InResponseTo` không khớp | Mất session/request state, callback đến node khác, flow IdP-initiated hoặc cookie SameSite bị loại. | Kiểm tra state repository, load balancer, browser cookies và SP-initiated request ID. |
| SAML assertion hết hạn hoặc “not yet valid” | Clock drift, `NotBefore/NotOnOrAfter` không phù hợp. | Đồng bộ giờ, kiểm tra IdP issuance và skew theo chính sách. |
| Login thành công nhưng không có email | IdP không phát `Name="email"` hoặc dùng OID/URI khác. | Đối chiếu raw attribute name ở dữ liệu test đã lọc PII, không đoán FriendlyName. |
| Login thành công nhưng thiếu ROLE_ADMIN | IdP group khác tên, mapper chưa tích hợp, khác tenant/issuer hoặc policy không cho admin. | Kiểm tra attributes và authorities sau authentication; không gán admin tự động. |
| User của IdP khác đăng nhập thành user hiện tại | Map account bằng email không unique hoặc bỏ qua issuer/tenant. | Sửa account-linking dựa trên issuer + stable subject ID và validation. |
| Sau đổi cert IdP login đồng loạt thất bại | Registry vẫn giữ cert cũ, metadata chưa được refresh/redeploy. | Thực hiện rotation có overlap và kiểm tra nguồn metadata đáng tin. |
| Logout SP rồi quay lại vẫn đăng nhập | IdP SSO session vẫn còn; local logout không phải SLO. | Thiết kế logout phù hợp nhu cầu, xác nhận cả SP và IdP. |

## 16. Cách lựa chọn triển khai trong thực tế

**Một IdP doanh nghiệp ổn định:** cấu hình Boot với `assertingparty.metadata-uri`, bật `saml2Login` và `saml2Metadata` (khi cần), trao SP metadata cho IdP. Chỉ thêm SP signing/decryption credentials khi thỏa thuận yêu cầu.

**Nhiều IdP cho một ứng dụng:** tạo nhiều `RelyingPartyRegistration` có `registrationId` riêng; khóa luồng vào đúng tenant/provider, tránh IdP confusion và account takeover. Cẩn trọng generated login page và việc công khai các registration IDs.

**Ứng dụng dùng group trong IdP để cấp quyền:** đọc `Saml2AuthenticatedPrincipal` sau khi SAML response đã được xác minh, xây allowlist mapping, gắn authorities tại authentication conversion step và kiểm thử `hasRole`/`hasAuthority` thực tế. Giữ quyền nghiệp vụ ở ứng dụng nếu IdP không phải nguồn đáng tin cho quyền đó.

**Hệ thống yêu cầu high availability:** chuẩn bị state/session store, metadata refresh, IdP signing cert rotation, SP keys, NTP, proxy/cookie và quy trình sự cố trước khi mở login cho production.

**Ghi nhớ:** `RelyingPartyRegistration` định nghĩa **SP tin IdP nào, endpoint/cert nào và nhận assertion ở đâu**; metadata là **hợp đồng tin cậy và khả năng tương tác**; `Saml2Authentication` chỉ xuất hiện sau khi kiểm tra SAML Response; attributes sau xác minh mới có thể map sang danh tính và `GrantedAuthority` của ứng dụng. Một SAML login an toàn cần đúng trust, metadata, callback, account linking và authorization, không chỉ một màn hình redirect thành công.

## Tài liệu tham khảo

- Spring Security — SAML2 Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security Javadoc — RelyingPartyRegistration: https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html
- OASIS SAML 2.0 Technical Overview và SAML Metadata specifications: https://www.oasis-open.org/committees/security/
