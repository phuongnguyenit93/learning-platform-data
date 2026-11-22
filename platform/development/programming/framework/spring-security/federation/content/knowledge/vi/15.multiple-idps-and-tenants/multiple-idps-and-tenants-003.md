# RelyingPartyRegistrationResolver và lựa chọn đăng ký theo yêu cầu trong Spring Security SAML 2.0

> **Chủ đề:** Spring Security – federation. **Nhóm:** Nhiều IdP và tenant. Bài này giải thích cách Spring Security xác định **RelyingPartyRegistration** nào sẽ được sử dụng cho một HTTP request trong ứng dụng SAML 2.0 Service Provider, cách viết **RelyingPartyRegistrationResolver** để chọn cấu hình có kiểm soát, và cách giữ đúng ranh giới tin cậy ở luồng phát AuthnRequest, nhận SAMLResponse, công bố metadata và Single Logout.

## 1. Vấn đề thực tế: cùng một ứng dụng, nhiều IdP hoặc tenant

Một ứng dụng Java Spring Security có thể phục vụ:

- Tenant **alpha** trên `https://alpha.portal.example.org`, liên kết với IdP alpha.
- Tenant **beta** trên `https://beta.portal.example.org`, liên kết với IdP beta.
- Một tenant có thể có **nhiều lựa chọn IdP** (ví dụ IdP nhân sự và IdP đối tác).
- Hai tenant có thể dùng **cùng sản phẩm IdP** nhưng khác entityID/tenant, signing keys hoặc cấu hình chính sách.
- Nhiều ứng dụng SP logic có thể chạy trong một service Java, cùng mã nguồn nhưng **khác Entity ID, ACS, signing/decryption credentials**.

Khi user vào một hostname, path hoặc trang login, hệ thống cần biết **sẽ dùng cấu hình SAML nào** để tạo AuthnRequest. Khi IdP gửi SAMLResponse về ACS, hệ thống lại phải chọn **đúng trust configuration** để kiểm chữ ký, Issuer, Audience, Recipient, InResponseTo và attributes.

Nếu chọn sai registration:

- Browser có thể bị đưa sang IdP của tenant khác.
- AuthnRequest dùng sai SP Entity ID hoặc ACS URL.
- SAMLResponse không xác minh được vì trusted IdP certificate không đúng.
- Nguy hiểm hơn: một custom converter thiếu kiểm soát có thể chấp nhận assertion từ **IdP ngoài tenant được phép**, dẫn tới account/role mix-up.

**Ý nghĩa cốt lõi:** `RelyingPartyRegistrationResolver` không phải “cho mọi HTTP request tùy chọn IdP bất kỳ”. Nó là một **điểm quyết định ngữ cảnh** cần dựa vào mapping tin cậy và phải phối hợp với các validator SAML sau đó.

## 2. Các thành phần và tên gọi dễ nhầm

| Khái niệm | Vai trò | API/vị trí |
|---|---|---|
| `RelyingPartyRegistration` | Một cấu hình liên kết SP ↔ IdP: SP Entity ID/ACS/credentials và IdP issuer/SSO/verification cert | `org.springframework.security.saml2.provider.service.registration` |
| `registrationId` | Khóa nội bộ Spring dùng để tìm registration, ví dụ `alpha`, `beta` | `RelyingPartyRegistration.getRegistrationId()` |
| `RelyingPartyRegistrationRepository` | Kho dữ liệu truy vấn registration theo ID; có thể cố định hoặc lấy từ DB/caching | `findByRegistrationId(String)` |
| `IterableRelyingPartyRegistrationRepository` | Có thể liệt kê registrations để hiển thị lựa chọn/công bố metadata | Spring Security registration repository |
| `RelyingPartyRegistrationResolver` | Quyết định registration thích hợp từ HTTP request và optional ID hint | `resolve(HttpServletRequest, String)` |
| `DefaultRelyingPartyRegistrationResolver` | Implementation có sẵn: lấy ID, tra repository và giải placeholders | `org.springframework.security.saml2.provider.service.web` |
| `Saml2AuthenticationTokenConverter` | Chuyển request ACS thành token đầu vào AuthenticationManager, cần biết registration | Nhận `RelyingPartyRegistrationResolver` ở constructor |
| `Saml2AuthenticationRequestResolver` | Xác định/tạo **AuthnRequest gửi đi** từ HTTP request | Điểm mở rộng **khác** |
| `Saml2MetadataResponseResolver` | Xác định metadata SP nào được công bố cho request | Điểm mở rộng **khác** |
| `Saml2AuthenticationRequestRepository` | Lưu AuthnRequest đã phát để đối chiếu callback, thường gắn session | Giúp chống cross-session/tenant mix-up |

**Đặc biệt:** `registrationId` không phải `SP Entity ID`, không phải `IdP Entity ID`, không phải tenant ID công khai và cũng không phải `NameID`. Bạn có thể đặt `registrationId=alpha` nhưng IdP issuer là một URL hoàn toàn khác.

### Một registration mô tả cả hai bên

~~~text
RelyingPartyRegistration "alpha"
  SP / relying party:
      entityID = https://alpha.portal.example.org/saml/sp
      ACS = https://alpha.portal.example.org/login/saml2/sso/alpha
      signingCredentials / decryptionCredentials = SP keys
  IdP / asserting party:
      entityID = https://login.alpha-idp.example.org/issuer
      SSO = https://login.alpha-idp.example.org/sso
      verificationCredentials = trusted IdP signing cert

RelyingPartyRegistration "beta"
  SP / relying party:
      entityID = https://beta.portal.example.org/saml/sp
      ACS = https://beta.portal.example.org/login/saml2/sso/beta
      signingCredentials / decryptionCredentials = SP keys
  IdP / asserting party:
      entityID = https://login.beta-idp.example.org/issuer
      SSO = https://login.beta-idp.example.org/sso
      verificationCredentials = trusted IdP signing cert
~~~

**Quy tắc:** một login cho alpha phải sử dụng đúng cặp SP/IdP đã đăng ký. Một certificate IdP beta **không mặc nhiên được chấp nhận** để xác minh người dùng của alpha, dù người dùng có cùng email.

## 3. Ba thao tác “chọn registration” khác nhau theo thời điểm

### 3.1. SP-initiated: trước khi gửi AuthnRequest

~~~text
User -> GET /private on alpha.portal.example.org
            |
            v
   Login entrypoint / identity picker
            |
            v
   Choose registration "alpha"
            |
            v
 GET /saml2/authenticate/alpha
            |
            v
 Saml2AuthenticationRequestResolver
            |
            v
 AuthnRequest -> IdP alpha
~~~

Tại đây, hệ thống cần **chọn IdP/registration để bắt đầu**. Với URL mặc định `/saml2/authenticate/{registrationId}`, Spring có đủ hint từ path. Nếu app dùng domain hoặc URL tùy biến không có ID, bạn có thể cấu hình `Saml2AuthenticationRequestResolver` hoặc một entrypoint/controller redirect có mapping rõ ràng; **chỉ thay converter xử lý ACS không làm thay đổi tự động bên phát AuthnRequest**.

### 3.2. ACS callback: sau khi nhận SAMLResponse

~~~text
IdP alpha -> Browser -> POST /login/saml2/sso/alpha
                        |
                        v
            Saml2WebSsoAuthenticationFilter
                        |
                        v
           Saml2AuthenticationTokenConverter
                        |
                        v
           RelyingPartyRegistrationResolver
                        |
                        v
              Registration alpha
                        |
                        v
          OpenSAML/Spring Security verifies
          issuer, signature, Audience, Recipient,
          Destination, InResponseTo, conditions
                        |
                        v
                    Authentication
~~~

Khi nhận Response, thứ tự ưu tiên mặc định có thể dùng **AuthnRequest đã lưu**, ID từ URL, hoặc **Issuer** từ Response nếu cần. Issuer trước khi chữ ký được kiểm là **dữ liệu chưa được tin**; có thể dùng làm **gợi ý tra một tập trust cố định**, nhưng chỉ được tin nội dung sau khi provider xác minh bằng signing keys/conditions của đúng registration.

### 3.3. Công bố SP metadata

~~~text
IdP admin -> GET /saml2/metadata/alpha
                    |
                    v
      Saml2MetadataResponseResolver
                    |
                    v
      SP metadata for registration alpha
      (Entity ID, ACS, public certificates)
~~~

Metadata là luồng **khác**. Việc custom resolver cho ACS **không tự động** khiến `/saml2/metadata` xuất XML của đúng tenant. Nếu một hostname cần một metadata duy nhất hoặc URL không có `registrationId`, cần thiết kế `Saml2MetadataResponseResolver`/repository phù hợp. Metadata sai dẫn tới IdP lưu sai SP Entity ID, ACS hoặc signing cert.

### Ma trận các điểm mở rộng

| Mục đích | Dữ liệu đầu vào đáng chú ý | Điểm mở rộng tương ứng |
|---|---|---|
| Chọn một IdP từ giao diện login | Tenant context đã xác định, danh sách IdP được phép | Login entrypoint/picker; `Saml2AuthenticationRequestResolver` |
| Sinh AuthnRequest | Request path/registration hint, SP/IdP configuration | `Saml2AuthenticationRequestResolver` |
| Nhận và xác thực SAMLResponse | Pending request, ACS URL, Response issuer/ID | `Saml2AuthenticationTokenConverter` với `RelyingPartyRegistrationResolver` |
| Công bố metadata | URL metadata, hostname, registration | `Saml2MetadataResponseResolver` |
| Nhận SAML LogoutRequest | IdP issuer, current user/registration | SLO request validator/resolver tương ứng |
| LogoutResponse callback | Pending LogoutRequest và issuer | SLO response validation/repository |

**Không dùng một resolver để tự động “làm hộ” tất cả luồng.** Một triển khai đa tenant phải kiểm rõ từng endpoint có mapping nhất quán.

## 4. API RelyingPartyRegistrationResolver chính xác

Theo JavaDoc Spring Security 6.5/7.1, interface:

~~~java
package org.springframework.security.saml2.provider.service.web;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;

public interface RelyingPartyRegistrationResolver {
    RelyingPartyRegistration resolve(
            HttpServletRequest request,
            String relyingPartyRegistrationId);
}
~~~

Đây là **phiên bản mô tả chữ ký chính**, trong JavaDoc thực tế có nullability annotations tùy version; không copy lại interface vào dự án vì Spring đã cung cấp.

- `request`: HTTP request hiện tại, ví dụ host, path, server context, các headers đã được gateway chuẩn hóa.
- `relyingPartyRegistrationId`: **gợi ý** nếu một thành phần khác đã biết ID; có thể `null`.
- Return: đối tượng registration tương ứng; các implementation có thể trả `null` khi không xác định được hoặc ID không được phép.
- **Không** có API `resolve(request)` trên interface này. Phương thức một tham số `convert(request)` thuộc `DefaultRelyingPartyRegistrationResolver` khi dùng như một `Converter`.

### 4.1. Implementation có sẵn

~~~java
RelyingPartyRegistrationResolver resolver =
        new DefaultRelyingPartyRegistrationResolver(registrations);

RelyingPartyRegistration selected =
        resolver.resolve(request, "alpha");
~~~

Đoạn là **fragment** cần `registrations` và `request` được cung cấp từ ứng dụng. `DefaultRelyingPartyRegistrationResolver` tra `RelyingPartyRegistrationRepository`, giải các URI template values như `{baseUrl}` và `{registrationId}` theo ngữ cảnh request.

**Không nhầm:** Resolver này **không xác minh XML Signature**, không tự kiểm Issuer/Audience và không cấp Authentication. Việc đó thuộc Spring Security/OpenSAML provider sau khi registration đã được chọn.

### 4.2. Khác nhau giữa Repository và Resolver

| Repository | Resolver |
|---|---|
| Nhận **registration ID** và trả bản ghi | Nhận **HttpServletRequest + optional registration ID** |
| Lưu cấu hình IdP/SP/credentials | Áp quy tắc chọn cấu hình cho request cụ thể |
| Có thể load từ cấu hình, DB, cache, metadata | Có thể quyết định theo host/path/tenant context |
| Trả không tìm thấy nếu không có ID | Có thể bác host/ID không tương thích |
| Không biết ngữ cảnh HTTP nếu chỉ lookup theo ID | Biết ngữ cảnh HTTP nhưng **không được tin mọi header** |
| Ví dụ `findByRegistrationId("alpha")` | Ví dụ `resolve(request, "alpha")` |

Nếu tenant selection đơn giản từ `registrationId` trong path và mỗi ID đã có một registration cố định, **không cần tự viết resolver**. Dùng mặc định giúp giảm code bảo mật phải duy trì.

## 5. Chọn registration từ đâu thì an toàn?

Một ứng dụng multi-tenant có thể có nhiều tín hiệu: hostname, path prefix, query parameter, session tenant, lời mời đăng nhập hoặc Response issuer. **Độ tin cậy của các tín hiệu không giống nhau.**

| Tín hiệu | Ví dụ | Có thể dùng để làm gì? | Rủi ro |
|---|---|---|---|
| URL path ID đã được định tuyến rõ | `/saml2/authenticate/alpha` | Chọn registration khi khởi tạo login | User có thể nhập ID khác; cần allowlist theo tenant |
| Public hostname do gateway quản lý | `alpha.portal.example.org` | Map đến tenant alpha | Host header spoofing nếu không có trusted routing |
| Path prefix ứng dụng | `/t/alpha/login` | Map tenant trong route nội bộ | Cần xác minh tenant tồn tại và quyền truy cập |
| Query parameter | `?tenant=alpha` | Gợi ý UI/entrypoint được allowlist | **Không** phải bằng chứng authorization hoặc trust |
| HTTP header tùy ý | `X-Tenant: alpha` | Chỉ dùng khi **proxy đáng tin** chèn sau khi strip inbound | Attacker tự đặt header nếu proxy không bảo vệ |
| Email domain | `user@alpha.example.org` | Có thể hỗ trợ discovery ban đầu | Không chứng minh IdP/tenant, dễ nhầm domain |
| Cookie phiên đã xác thực | Registration/tenant trong server session | Liên hệ ngữ cảnh sau đăng nhập | Phải chống session fixation/tampering |
| Saved AuthnRequest state | ID/registration của request gốc | **Cơ sở tốt cho SP-initiated callback** | Mất cookie/session, repository mismatch |
| `SAMLResponse.Issuer` | URL của IdP từ XML | Gợi ý chọn **trusted registration candidate** | Payload chưa xác minh, nhiều tenant có issuer giống nhau |
| `Assertion.Audience` | SP Entity ID | Kiểm assertion dành đúng SP | Không chọn trust chỉ bằng assertion chưa ký |

**Quy tắc quyết định:** Dùng một mapping **server-controlled và allowlisted** để chọn registration candidate, rồi dùng SAML provider để **xác minh** candidate đó khớp issuer/keys/audience/recipient/request state. Không bao giờ cấp role chỉ dựa vào ID/hint mà browser khai.

### 5.1. Khi nào Host header đáng tin?

`request.getServerName()` có thể lấy host từ HTTP request/Host header hoặc forwarded headers đã được xử lý. Nếu app cho phép client kết nối trực tiếp và tự gửi Host bất kỳ, map theo host không đủ đảm bảo tenant isolation.

Để an toàn:

1. Chỉ expose các hostname tenant qua **gateway/ingress đã kiểm TLS/SNI và virtual host**.
2. Chặn truy cập trực tiếp tới backend nếu không đi qua trusted proxy.
3. Proxy xóa `Forwarded`, `X-Forwarded-Host` và `X-Tenant` do client tự gửi trước khi chèn giá trị nội bộ chuẩn.
4. Cấu hình Spring Boot forwarded-header handling phù hợp hạ tầng.
5. Allowlist exact hostnames, normalize case theo DNS semantics, không sử dụng substring hoặc suffix sơ sài.
6. Nếu Host và `registrationId` không thống nhất, **từ chối**, không fallback sang default tenant.
7. Không tạo Metadata/ACS dựa trên Host header chưa được kiểm vì có nguy cơ host header injection.

### 5.2. Khi nào path registration ID tốt hơn?

Dùng URL rõ ràng như:

~~~text
GET  /saml2/authenticate/alpha
POST /login/saml2/sso/alpha
GET  /saml2/metadata/alpha
~~~

Ưu điểm: đơn giản, dễ đối chiếu, Spring Security mặc định hỗ trợ và logs rõ ràng. Nhược điểm: khi một SP có nhiều tenant trên một hostname, người dùng có thể tự sửa `alpha` thành `beta`. Điều này **chỉ được** nếu user/tenant context được phép chọn IdP beta và application authorization sau login không trộn tenant.

Nếu mỗi hostname chỉ được gắn một tenant, áp quy tắc **host-to-registration** ở entrypoint/response/metadata, không chỉ dựa vào path do user nhập.

## 6. Ví dụ cấu hình hai registrations bằng Spring Boot YAML

Cấu hình minh họa cho Spring Security Servlet SP, theo cấu trúc Spring Boot 3.x/nhánh tương ứng; URL IdP là **giá trị ví dụ**, không phải metadata thật:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          alpha:
            entity-id: "https://alpha.portal.example.org/saml/sp"
            acs:
              location: "https://alpha.portal.example.org/login/saml2/sso/alpha"
            assertingparty:
              metadata-uri: "https://login.alpha-idp.example.org/metadata"
          beta:
            entity-id: "https://beta.portal.example.org/saml/sp"
            acs:
              location: "https://beta.portal.example.org/login/saml2/sso/beta"
            assertingparty:
              metadata-uri: "https://login.beta-idp.example.org/metadata"
~~~

Spring Boot sẽ tạo `RelyingPartyRegistrationRepository` từ cấu hình phù hợp, mỗi tên `alpha`/`beta` là một `registrationId`.

**Khi triển khai thật:**
- IdP alpha phải đăng ký SP Entity ID và ACS alpha chính xác; beta tương tự.
- `metadata-uri` phải là nguồn metadata đáng tin, đúng issuer và signing cert tenant.
- Ứng dụng không tự tin metadata chỉ vì kết nối HTTPS hợp lệ; phải xác minh trust/source và key rollover.
- Nếu IdP bắt ký AuthnRequest, bổ sung SP signing credential và cấu hình IdP tin public cert.
- Nếu Assertion được mã hóa, bổ sung SP decryption credential tương ứng.
- Với Spring Boot 4/Spring Security 7, đối chiếu exact property names theo version đang chạy.

### 6.1. Không chỉ copy chung Entity ID và ACS cho mọi tenant

Có trường hợp một SP dùng chung SP Entity ID/ACS cho nhiều IdP. SAML profile không cấm mọi biến thể đó, nhưng khi IdP issuers trùng/khác tenants và signatures/credentials khác nhau, lookup càng dễ mơ hồ. Tách một SP Entity ID và ACS rõ theo tenant thường đơn giản hơn về vận hành/trust, **không phải lúc nào cũng bắt buộc**.

Phải ghi bảng contract:

| Tenant | registrationId | SP Entity ID | ACS URL | IdP issuer | IdP signing fingerprint |
|---|---|---|---|---|---|
| Alpha | `alpha` | `https://alpha.portal.example.org/saml/sp` | `https://alpha.portal.example.org/login/saml2/sso/alpha` | Issuer alpha đã xác minh | Fingerprint của cert alpha |
| Beta | `beta` | `https://beta.portal.example.org/saml/sp` | `https://beta.portal.example.org/login/saml2/sso/beta` | Issuer beta đã xác minh | Fingerprint của cert beta |

Không gửi các private keys qua spreadsheet, metadata công khai hoặc log. Fingerprint công bố được nhưng chỉ có ý nghĩa trust khi nguồn đã xác minh.

## 7. Java 17+ custom resolver chọn theo hostname và chống hint xung đột

Đây là ví dụ trọng tâm của bài. Nó **bắt buộc** registration từ hostname đã được gateway kiểm và kiểm `relyingPartyRegistrationId` nếu một component upstream truyền ID. Khi host không nằm trong allowlist hoặc ID không khớp, trả `null` để authentication fail. Nó **không** fallback tới tenant đầu tiên.

Tệp `src/main/java/com/example/saml/HostBoundRegistrationResolver.java`:

~~~java
package com.example.saml;

import java.util.Locale;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;

public final class HostBoundRegistrationResolver
        implements RelyingPartyRegistrationResolver {

    private final RelyingPartyRegistrationResolver delegate;

    private final Map<String, String> allowedHosts = Map.of(
            "alpha.portal.example.org", "alpha",
            "beta.portal.example.org", "beta");

    public HostBoundRegistrationResolver(
            RelyingPartyRegistrationRepository repository) {
        this.delegate = new DefaultRelyingPartyRegistrationResolver(repository);
    }

    @Override
    public RelyingPartyRegistration resolve(
            HttpServletRequest request, String relyingPartyRegistrationId) {
        String host = request.getServerName();
        if (host == null) {
            return null;
        }

        String expectedId = allowedHosts.get(host.toLowerCase(Locale.ROOT));
        if (expectedId == null) {
            return null;
        }

        if (relyingPartyRegistrationId != null
                && !expectedId.equals(relyingPartyRegistrationId)) {
            return null;
        }

        return this.delegate.resolve(request, expectedId);
    }
}
~~~

**Giải thích từng bước:**

1. `allowedHosts` là **allowlist do server cấu hình**, không lấy từ JSON body hoặc query.
2. `getServerName()` được coi là nguồn đã được **trusted ingress kiểm soát**; nếu không có bảo vệ ở ingress thì **chưa đủ an toàn**.
3. `toLowerCase(Locale.ROOT)` phù hợp hostname DNS đơn giản; ở thực tế nên xử lý IDNA/Punycode, port, trailing dot và canonical host theo quy tắc gateway.
4. Host không nằm trong allowlist → `null`; không mặc định đăng nhập bằng alpha.
5. Nếu path/callback mang hint beta nhưng request đang ở host alpha → `null`; không chọn một phía tùy tiện.
6. Delegate là `DefaultRelyingPartyRegistrationResolver`, giúp tra repository và giải URI templates.
7. Resolver **chỉ chọn candidate**, không tự kiểm chữ ký SAML; provider vẫn phải kiểm issuer, signing key, audience, recipient và các conditions.

**Giới hạn quan trọng:** Đoạn này **không ngăn đường phát AuthnRequest tự động bằng resolver mặc định** nếu ứng dụng vẫn dùng GET `/saml2/authenticate/beta` trên host alpha; phải bảo vệ outgoing initiation riêng (mục 9). Đồng thời nó không tự thay metadata resolver. Đây là điểm phân biệt giữa “chọn registration khi nhận Response” và “chọn IdP khi bắt đầu flow”.

### 7.1. Tích hợp resolver với SAML Response AuthenticationConverter

Tệp `src/main/java/com/example/saml/SamlSecurityConfiguration.java`, Java 17+ trong project Spring Boot Servlet có spring-security-saml2-service-provider:

~~~java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.Saml2AuthenticationTokenConverter;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    RelyingPartyRegistrationResolver relyingPartyRegistrationResolver(
            RelyingPartyRegistrationRepository repository) {
        return new HostBoundRegistrationResolver(repository);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RelyingPartyRegistrationResolver registrationResolver)
            throws Exception {

        Saml2AuthenticationTokenConverter converter =
                new Saml2AuthenticationTokenConverter(registrationResolver);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml2 -> saml2
                .authenticationConverter(converter))
            .build();
    }
}
~~~

**Cơ chế:** `Saml2AuthenticationTokenConverter` có constructor nhận `RelyingPartyRegistrationResolver`; DSL `saml2Login(saml2 -> saml2.authenticationConverter(converter))` gắn converter cho **bước ACS authentication request**. Spring Security/OpenSAML tiếp tục kiểm signature/conditions.

**Không đánh đồng:** Config này không tự bảo vệ việc GET `/saml2/authenticate/{registrationId}` trên hostname sai. Có thể đưa người dùng qua custom entrypoint/selector có allowlist và chặn direct outgoing URI mismatch hoặc cấu hình một `Saml2AuthenticationRequestResolver` phù hợp. Mã Spring cần dependencies/classpath và IdP thật, **không phải chương trình dùng javac độc lập**.

### 7.2. Nếu muốn đổi URL nhận Response

Ví dụ chọn URL callback cố định `/saml/acs` trên nhiều host:

~~~java
http.saml2Login(saml2 -> saml2
    .loginProcessingUrl("/saml/acs")
    .authenticationConverter(converter));
~~~

Đây là **fragment trong SecurityFilterChain**. Với callback không có `registrationId` trong path, converter cần phân giải từ trusted host và/request state; HostBoundRegistrationResolver ở trên có thể trả registration theo host, nhưng vẫn phải kiểm issuer/signature/Audience/Recipient.

Phải cập nhật **ACS trong mỗi RelyingPartyRegistration**, metadata SP xuất ra và IdP stored Reply URL. Nếu chỉ đổi `loginProcessingUrl` mà không đổi ACS/location, IdP có thể POST sai endpoint hoặc Spring từ chối Recipient/Destination.

## 8. Java 17 standalone: thử tư duy “hint phải khớp tenant”

Chương trình này **độc lập**, không cần Spring, minh họa chính sách host→registration rồi từ chối khi path hint xung đột. Nó không đọc SAML XML, không xác minh signature và không quyết định quyền user; kết quả chỉ là **selection policy trước SAML provider**.

Tệp `TenantSelectionDemo.java`:

~~~java
import java.util.Locale;
import java.util.Map;

public class TenantSelectionDemo {

    static final Map<String, String> HOST_TO_REGISTRATION = Map.of(
            "alpha.portal.example.org", "alpha",
            "beta.portal.example.org", "beta");

    static String select(String hostname, String hintedId) {
        if (hostname == null) {
            return "REJECT";
        }

        String expected = HOST_TO_REGISTRATION.get(
                hostname.toLowerCase(Locale.ROOT));

        if (expected == null) {
            return "REJECT";
        }

        if (hintedId != null && !expected.equals(hintedId)) {
            return "REJECT";
        }

        return expected;
    }

    public static void main(String[] args) {
        System.out.println(select("alpha.portal.example.org", "alpha"));
        System.out.println(select("beta.portal.example.org", null));
        System.out.println(select("alpha.portal.example.org", "beta"));
        System.out.println(select("unknown.example.org", "alpha"));
        System.out.println(select(null, "alpha"));
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac TenantSelectionDemo.java
java TenantSelectionDemo
~~~

**Stdout chính xác:**

~~~text
alpha
beta
REJECT
REJECT
REJECT
~~~

**Ý nghĩa của các case:**

1. Host alpha cùng hint alpha → chọn alpha.
2. Host beta không có hint → chọn beta qua allowlist.
3. Host alpha nhưng hint beta → từ chối, không âm thầm ưu tiên hint hoặc host.
4. Host không được đăng ký → từ chối.
5. Host null → từ chối.

**Giới hạn:** Nếu Host do attacker có thể spoof, hàm vẫn trả `alpha` theo chuỗi attacker đưa. Vì vậy trong production cần **trusted edge routing** và full SAML signature/issuer/audience validation. Demo chỉ là logic quyết định deterministic, không chứng minh trust của host hay payload.

## 9. Phải bảo vệ cả luồng phát AuthnRequest

Một sai lầm thường gặp là: “Tôi đã viết custom `RelyingPartyRegistrationResolver` cho SAMLResponse nên tất cả login đều được định tuyến đúng tenant”. Điều đó **không chính xác**.

### 9.1. Route outgoing mặc định

Spring Security tạo AuthnRequest tại:

~~~text
GET /saml2/authenticate/{registrationId}
~~~

Khi người dùng truy cập `/saml2/authenticate/beta` trên host alpha, request filter có thể chọn **beta** nếu chỉ dựa vào path. Dù callback sau này bị HostBoundRegistrationResolver từ chối, user đã bị redirect tới IdP beta, có thể gây trải nghiệm sai hoặc lộ context/redirect không mong muốn.

**Giải pháp theo mức ưu tiên:**

1. Nếu dùng một hostname duy nhất và user được phép chọn IdP, hiển thị **picker** chỉ gồm những registrations tenant được phép, rồi redirect đến `/saml2/authenticate/{id}`.
2. Nếu mỗi hostname buộc dùng một IdP, tạo entrypoint/endpoint tại host đó và chỉ cho phép ID đã map, **chặn outgoing URL không tương ứng**.
3. Khi cần custom query/URI format, dùng `Saml2AuthenticationRequestResolver` hoặc `saml2Login.authenticationRequestUriQuery(...)` theo API phiên bản.
4. Nếu tùy biến request repository, đảm bảo AuthnRequest được lưu với registration/tenant và correlation state đúng browser.
5. Nếu app có nhiều entrypoints, kiểm mọi alias/path có thể tạo AuthnRequest, không chỉ nút trên login page.

### 9.2. API khác biệt cần nhớ

| API | Phương thức/điểm dùng | Kết quả |
|---|---|---|
| `RelyingPartyRegistrationResolver` | `resolve(HttpServletRequest, String)` | `RelyingPartyRegistration` |
| `Saml2AuthenticationRequestResolver` | `resolve(HttpServletRequest)` | Một `AbstractSaml2AuthenticationRequest` (Redirect/Post request theo provider) |
| `Saml2LoginConfigurer.authenticationRequestResolver(...)` | Gắn strategy tạo AuthnRequest | Xử lý outgoing login request |
| `Saml2LoginConfigurer.authenticationConverter(...)` | Gắn converter nhận SAMLResponse | Xử lý ACS incoming Response |
| `Saml2LoginConfigurer.loginProcessingUrl(...)` | Chuyển callback URL | Phải đổi metadata/ACS cùng lúc |
| `Saml2MetadataConfigurer.metadataResponseResolver(...)` | Gắn strategy metadata | Xử lý GET metadata |

**Spring Security 7.x:** JavaDoc có `authenticationRequestUriQuery(...)` và ghi `authenticationRequestUri(...)` là deprecated. Không đem tên API từ legacy Spring SAML Extension sang ứng dụng SAML2 Service Provider hiện đại.

### 9.3. Ví dụ entrypoint định tuyến riêng, không thay resolver mặc định

Một controller hỗ trợ domain-based entrypoint có thể quyết định ID dựa trusted host rồi redirect:

~~~java
@GetMapping("/start-sso")
String startSso(HttpServletRequest request) {
    String host = request.getServerName();
    if ("alpha.portal.example.org".equalsIgnoreCase(host)) {
        return "redirect:/saml2/authenticate/alpha";
    }
    if ("beta.portal.example.org".equalsIgnoreCase(host)) {
        return "redirect:/saml2/authenticate/beta";
    }
    throw new ResponseStatusException(
        HttpStatus.BAD_REQUEST, "Unknown tenant host");
}
~~~

Đây là **method fragment** trong Spring MVC controller có imports tương ứng. Nút bấm chỉ đi qua `/start-sso` không đảm bảo direct GET `/saml2/authenticate/other` đã bị chặn. Nếu có yêu cầu không cho phép cross-host initiation, hãy bảo vệ route AuthnRequest thực tế ở security filter/router hoặc custom resolver, và có regression test cho đường truy cập trực tiếp.

**Lưu ý UX:** Một app có nhiều IdP trong cùng tenant không thể luôn ép một ID duy nhất bằng host. Khi đó host chỉ xác định tenant, còn user chọn một ID trong **allowlist IdP của tenant**. Mapping từ user email domain chỉ phù hợp làm **gợi ý ban đầu**, không làm bằng chứng quyền hoặc issuer.

## 10. Nhận SAMLResponse: request state, URL và Issuer

Theo Spring Security SAML2 Login Overview và Authenticating Responses, converter mặc định có thể xác định registration từ:
- AuthnRequest đã phát và lưu tương ứng.
- Registration ID trong URL callback.
- Khi thiếu các gợi ý trên, IdP Issuer được parse từ Response.

**Mức tin cậy phải phân biệt:**

### 10.1. Có AuthnRequest tương ứng (SP-initiated)

~~~text
Browser của tenant alpha
  -> SP phát AuthnRequest ID=_req123 bằng registration alpha
  -> lưu ID + registration alpha + browser session context
  -> IdP alpha trả SAMLResponse InResponseTo=_req123
  -> Spring tra pending request
  -> chọn registration alpha
  -> verify issuer/signing cert/audience/recipient/time
  -> tạo Authentication đúng tenant
~~~

Đây là luồng nên ưu tiên vì có **request correlation** với browser session. Nếu pending request mất do cookie SameSite, cluster session storage hoặc proxy, **không được silently chuyển sang IdP-initiated** để bỏ InResponseTo validation.

### 10.2. Không có AuthnRequest (IdP-initiated)

Trong IdP-initiated login, IdP có thể gửi unsolicited Response không mang InResponseTo. Một app có hai IdPs/tenants phải xác định đúng registration qua ACS URL/host và issuer đã đăng ký. Nếu **Issuer giống nhau** ở nhiều tenant registrations và không có state phân biệt, lựa chọn có thể mơ hồ.

**Giải pháp:** Dùng dedicated ACS/host/path rõ ràng, require known registrationId và allowlist host/issuer phù hợp; hoặc **từ chối unsolicited SSO** theo security policy. Không thử ngẫu nhiên mọi IdP trusted certificates rồi chọn cái nào verify được, nếu kết quả có thể làm lệch tenant/authorization.

### 10.3. Vì sao Issuer là gợi ý, không phải trust?

Response XML có thể tự khai:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_response_01"
    Version="2.0"
    Destination="https://alpha.portal.example.org/login/saml2/sso/alpha">
  <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    https://login.alpha-idp.example.org/issuer
  </saml:Issuer>
  <!-- Chữ ký và Assertion được lược bỏ -->
</samlp:Response>
~~~

Mẫu trên **không phải Response hợp lệ**, chỉ minh họa một field. Attacker có thể viết Issuer tùy ý trong payload chưa ký. Có thể parse Issuer như **lookup hint** vào repository allowlisted, nhưng chỉ chấp nhận sau khi SAML provider dùng **đúng IdP verification credential** kiểm XML Signature và semantic conditions. Dùng Issuer làm key cache khác với tin Issuer là bằng chứng IdP.

### 10.4. Điều kiện bắt buộc sau khi resolver trả registration

| Kiểm tra | Mục tiêu |
|---|---|
| Response/Assertion signature | Chữ ký hợp lệ với public key của **IdP trong chosen registration** |
| Response/Assertion Issuer | Trùng IdP entityID đã cấu hình |
| Assertion AudienceRestriction | Có SP Entity ID của **chosen registration** |
| Response Destination | Đúng ACS URL mà browser gửi tới |
| SubjectConfirmation Recipient | Trùng ACS phù hợp |
| InResponseTo | Nếu SP-initiated, trùng pending AuthnRequest của browser/session |
| Time conditions | NotBefore/NotOnOrAfter hợp lệ, clock skew giới hạn |
| Replay | Assertion/Response ID không được dùng lại trái profile |
| NameID mapping | Kết hợp issuer/tenant/subject, không liên kết account chỉ bằng email |
| GrantedAuthority | Mapping nhóm/quyền theo tenant và IdP trust policy |

**Tối quan trọng:** Resolver trả `alpha` **không đồng nghĩa** đã xác thực một người dùng alpha. Chỉ provider/correlation/authorization hoàn chỉnh mới tạo được phiên và quyền.

## 11. Trường hợp nhiều IdP nhưng chỉ một tenant

“Multi-IdP” và “multi-tenant” không đồng nhất.

- **Một tenant, nhiều IdP:** Tenant corporate cho nhân viên dùng IdP A và đối tác dùng IdP B. Một account local có thể liên kết nhiều identities theo policy.
- **Nhiều tenant, mỗi tenant một IdP:** Alpha và Beta tách data/roles. SAML selection phải phản ánh tenant isolation.
- **Nhiều tenant cùng một IdP:** Có thể chia cùng IdP signing key/issuer nhưng SP Entity ID/ACS/attributes khác. Phải giữ scope tenant rõ.
- **Một IdP có nhiều tenant/realm:** Khác issuer, endpoints, certificates hoặc metadata, không thể chỉ dựa vào tên sản phẩm IdP.

### 11.1. Picker nên làm gì?

Một trang chọn IdP cần:

1. Xác định tenant context bằng routing đã tin.
2. Liệt kê **chỉ các IdP/registrations được tenant cho phép**.
3. Dùng registrationId opaque ổn định và allowlisted.
4. Chuyển sang AuthnRequest endpoint của registration đã chọn.
5. Không gắn vai trò/admin vào query parameter hoặc hidden field.
6. Sau callback, đối chiếu registration với tenant context gốc và SAML validation.
7. Có chính sách khi user cố đổi IdP hoặc đăng nhập tenant khác trong cùng browser.

**Không** chỉ lấy domain từ email nhập vào rồi auto tin IdP đó; email là dữ liệu browser khai. Nó có thể hỗ trợ discovery/UX nhưng phải tiếp tục xác thực bình thường.

### 11.2. Tách tenant khỏi application authorization

Ngay cả khi một user hợp lệ ở IdP beta, ứng dụng không được mở dữ liệu alpha chỉ vì user có `ROLE_USER`. Authorization cần tenant scope rõ: resource tenant ID, authenticated issuer/subject, allowed roles. Khi role mapping, ưu tiên một cặp `(issuer, group-id)` được duyệt thay vì một chuỗi group name trùng nhau giữa IdPs.

## 12. Công bố metadata nhất quán với resolver

Khi IdP administrator hỏi “SP metadata của alpha ở đâu?”, câu trả lời có thể là:

~~~text
GET https://alpha.portal.example.org/saml2/metadata/alpha

EntityID: https://alpha.portal.example.org/saml/sp
ACS:      https://alpha.portal.example.org/login/saml2/sso/alpha
Certs:    SP public signing/encryption certs theo policy
~~~

**Không lấy** metadata beta ở alpha hostname rồi import vào IdP alpha. Nếu metadata API của Spring có thể trả về nhiều EntityDescriptors khi repository hỗ trợ Iterable, hãy bảo đảm IdP admin dùng đúng registration-specific metadata endpoint hoặc custom metadata response resolver.

### 12.1. Metadata có resolver riêng

Ví dụ DSL bật xuất metadata:

~~~java
http
    .saml2Login(Customizer.withDefaults())
    .saml2Metadata(Customizer.withDefaults());
~~~

Đây là fragment trong `SecurityFilterChain`. Với Spring Security hiện đại, endpoint thường gồm `/saml2/metadata` và `/saml2/metadata/{registrationId}`.

Nếu muốn tùy biến lookup metadata từ hostname/path, dùng `Saml2MetadataResponseResolver` được gắn qua `saml2Metadata(saml2 -> saml2.metadataResponseResolver(...))`. Không nhầm với `RelyingPartyRegistrationResolver` của `Saml2AuthenticationTokenConverter`.

**Cảnh báo:** Metadata URL public, SP Entity ID, ACS trong metadata và cấu hình IdP phải khớp ở từng tenant. Nếu app ở sau reverse proxy, `{baseUrl}` có thể phát sai HTTP localhost URL nếu forwarded headers không đáng tin hoặc chưa được cấu hình đúng. Khi đó điều chỉnh routing/explicit URLs chứ không bỏ Destination/Recipient validation.

## 13. Lựa chọn động từ cơ sở dữ liệu

Ứng dụng SaaS có thể thêm tenant/IdP mới mà không restart server. Lúc này `RelyingPartyRegistrationRepository` có thể:

- Lấy một registration từ DB theo `registrationId` (có tenant ownership và status).
- Tải/parse IdP metadata đã được quản trị phê duyệt.
- Cache registrations theo key ổn định và TTL/vòng đời metadata phù hợp.
- Hỗ trợ rotation signing certificates đồng thời cũ/mới trong giai đoạn overlap.
- Hủy cấu hình khi tenant bị disabled hoặc IdP integration revoked.

Resolver **vẫn** phải map request vào một **ID đã được phê duyệt**, không cho request tự gửi metadata URL rồi lấy cert của bất kỳ IdP nào. Nếu tenant config từ DB có signing credentials, private keys phải ở secret manager/HSM, không nằm plaintext trong bảng metadata ứng dụng.

### 13.1. DB schema tối thiểu về mặt ý nghĩa

| Trường | Ý nghĩa | Nguyên tắc |
|---|---|---|
| `registration_id` | Khóa stable/unique của config | Không tái dùng ID cho tenant/issuer khác tùy tiện |
| `tenant_id` | Owner của registration | Chỉ tenant này được sử dụng |
| `public_host` | Host đã allowlist | Áp trusted gateway mapping |
| `sp_entity_id` | SP logical identity | Trùng IdP stored Audience/Identifier |
| `acs_url` | Public SAML callback URL | Trùng IdP Reply URL |
| `idp_entity_id` | Issuer đáng tin | Trùng IdP metadata issuer |
| `idp_metadata_uri` | Nguồn metadata đã xác minh | Không nhận trực tiếp từ người dùng |
| `signing_cert_fingerprint` | IdP signing material version | Ghi nhận rotation và audit |
| `enabled` | Cho phép đăng nhập hay không | Disabled → resolver/repository fail closed |
| `config_version` | Revision để cache invalidation | Mọi node nhận bản mới atomically |

Bảng chỉ là **hợp đồng dữ liệu**, không yêu cầu sửa schema ở nhiệm vụ này. Khi xác minh SAML, phải dùng configuration snapshot nhất quán cho AuthnRequest→Response, đặc biệt khi rotate certificates.

### 13.2. Cache và metadata refresh

Spring Security cung cấp `CachingRelyingPartyRegistrationRepository` và các giải pháp metadata repository có khả năng refresh. Với cấu hình thay đổi ở runtime:

1. Cố định trust anchor và nguồn metadata được duyệt.
2. Không để attacker cung cấp URL metadata để server fetch tùy ý (SSRF).
3. Có TTL/cache invalidation rõ khi certificate thay đổi hoặc tenant bị disable.
4. Đảm bảo nhiều nodes dùng tập trusted credentials tương thích trong window rotation.
5. Không xóa public signing key cũ khi các Response hợp lệ đang trong flight; chỉ retire sau overlap.
6. Khi thiếu registration/cert hoặc metadata fetch lỗi, fail closed và báo vận hành; không fallback tenant khác.
7. Có audit trail ai thay đổi IdP metadata, issuer, ACS hoặc signing keys.

**Phân biệt:** Dynamic repository là thay đổi **tập registrations**. Resolver là thay đổi **quy tắc chọn** từ request. Cần cả hai nếu onboarding tenant mới tự động và URL không chứa ID.

## 14. Không tin HTTP headers và tránh tenant mix-up

### 14.1. Một anti-pattern

~~~java
// KHÔNG AN TOÀN: X-Tenant có thể do client tự gửi.
String registrationId = request.getHeader("X-Tenant");
return repository.findByRegistrationId(registrationId);
~~~

Nếu backend nhận trực tiếp header này, user ở alpha có thể đặt `X-Tenant: beta` và khiến app chọn IdP/trust beta. Dù SAML validation có thể vẫn chặn một số trường hợp, **không nên tạo selection vulnerability** và vô tình liên kết authority/data sai tenant.

**Đúng hơn:** Ingress xác thực tenant từ hostname/routing/server config, xóa inbound X-Tenant trước khi thêm header nội bộ, chặn direct backend access, còn Spring resolver dùng allowlist host→registration và kiểm request ID hint.

### 14.2. Một anti-pattern khác

~~~java
// KHÔNG AN TOÀN: user có thể chọn IdP metadata từ URL.
String metadataUrl = request.getParameter("metadataUrl");
// Không dùng metadataUrl để tự tải một IdP mới và tin signing cert.
~~~

Đây là rủi ro **SSRF, trust substitution và tenant confusion**. Metadata chỉ được lấy từ nguồn cấu hình được quản trị duyệt, có HTTPS và/hoặc metadata-signature verification/explicit trust phù hợp.

### 14.3. Không cố thử mọi khóa của mọi IdP

Một số custom code có ý tưởng:
- Parse Response.
- Thử verify signature bằng mọi certificate của mọi IdP đã đăng ký.
- Key nào verify được thì coi như user thuộc tenant tương ứng.

Cách này bỏ qua **request/tenant context** và dễ gây account mix-up khi IdP cấp nhiều accounts/group claims. **Đúng:** candidate registration phải được giới hạn từ trusted route hoặc pending request, verify signer của IdP đó và Audience/Recipient/Issuer tương ứng. Nếu nhiều registrations hợp lệ không phân biệt được, **từ chối** thay vì chọn theo thứ tự mảng.

### 14.4. Tenant context phải đi vào authorization

Sau login, lưu server-side identity binding như:
- application tenant ID;
- chosen registrationId và trusted IdP issuer;
- NameID/subject ID có format/qualifiers phù hợp;
- mapped authorities theo allowlist của tenant.

Không dùng riêng email để ghép local users giữa hai IdPs. Không để tenant ID trong request path sau login ghi đè tenant từ authenticated principal mà không có authorization check.

## 15. Kiểm thử resolver và toàn bộ luồng SSO

### 15.1. Unit tests của resolver

Với class `HostBoundRegistrationResolver`:

| Request | Hint ID | Kỳ vọng |
|---|---|---|
| Host alpha | `alpha` | Trả registration alpha |
| Host beta | `beta` | Trả registration beta |
| Host alpha | `null` | Trả alpha |
| Host beta | `null` | Trả beta |
| Host alpha | `beta` | **null/reject** |
| Host beta | `alpha` | **null/reject** |
| Host unknown | `alpha` | **null/reject** |
| Host null/empty | `alpha` | **null/reject** |
| Backend direct host spoof | `alpha` | Edge chặn; resolver đơn thuần chưa chứng minh an toàn |
| Repo không có ID | `alpha` | Fail closed/không có registration |

Có thể unit test Spring implementation bằng `MockHttpServletRequest` từ spring-test cùng một test `InMemoryRelyingPartyRegistrationRepository` với fake-but-structurally-valid registrations. **Không cần fake SAMLResponse** cho test map host→ID, nhưng phải có integration test ở cấp protocol riêng.

### 15.2. Integration tests cho SP-initiated

1. User vào alpha hostname, nhận đúng login/picker/IdP alpha.
2. `AuthnRequest.Issuer` là SP alpha Entity ID.
3. Destination SSO URL thuộc IdP alpha, không beta.
4. ACS URL trong request và IdP registration là public alpha URL.
5. Pending request lưu registration alpha và liên kết browser session.
6. IdP alpha trả Response có `InResponseTo` trỏ đúng AuthnRequest.
7. Spring converter chọn alpha; OpenSAML verify IdP alpha signing key, issuer, Audience, Recipient, time.
8. Principal/roles tạo đúng tenant, không dùng dữ liệu beta.
9. Request ở beta host phải cho kết quả đối xứng.
10. Direct GET tới URI initiate beta trên alpha host bị chặn theo policy.

### 15.3. Integration tests cho ACS/IdP-initiated

| Case | Kỳ vọng |
|---|---|
| Response IdP alpha tới ACS alpha, signature đúng | Có thể chấp nhận sau validation/tenant policy |
| Response IdP beta tới ACS alpha | **Từ chối** dù signer beta là IdP đã đăng ký khác |
| Response sai Audience nhưng signature đúng | **Từ chối** |
| Response sai Recipient/Destination | **Từ chối** |
| Response signed bằng key không tin cậy | **Từ chối** |
| Response có InResponseTo không khớp browser/session | **Từ chối**, không fallback unsolicited |
| IdP-initiated không có pending request | Chỉ cho phép nếu policy cho unsolicited và routing không mơ hồ |
| Hai tenants có cùng IdP issuer, không có trusted distinguishing context | **Từ chối sự mơ hồ** |
| Assertion hết hạn hoặc NotBefore chưa tới | **Từ chối** |
| Replay Assertion/Response ID | **Từ chối** theo profile |
| Có role/group chung tên giữa tenants | Chỉ map theo tenant/issuer allowlist |
| Metadata beta được GET qua alpha host khi policy không cho | Không lộ sai config; route metadata theo policy |
| Session cookie mất qua cross-site POST | Fail correlation đúng; sửa SameSite/store, không bỏ validation |

### 15.4. Test ở môi trường đa node

- Request AuthnRequest tạo ở node A, callback về node B.
- Session repository hoặc custom `Saml2AuthenticationRequestRepository` giữ đúng state.
- Certificate rotation đồng bộ trên các nodes.
- Tenant config disabled được áp dụng nhất quán.
- Không reuse request state của một browser cho browser khác.
- Reverse proxy sanitizes forwarded headers; hostname mapping không bị user overwrite.
- Metadata public trên mọi node phải có cùng Entity ID/ACS/trust configuration version.

**Lưu ý:** Test chỉ bằng `SecurityMockMvcRequestPostProcessors.user(...)` hoặc tự tạo Authentication không kiểm được SAML Signature/Audience/Recipient. Cần dùng test IdP thực hoặc SAML fixtures ký hợp lệ và các negative messages được thiết kế có chủ đích.

## 16. Troubleshooting theo tầng

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm |
|---|---|---|
| “No relying party registration found” | ID không tồn tại, host không allowlist, repository chưa load | Log host canonical, ID hint, repository version; không log raw SAML |
| Browser bị chuyển sang IdP sai | Outgoing AuthnRequest selection chưa ràng buộc tenant | Kiểm picker, `/saml2/authenticate/{id}`, resolver outgoing |
| ACS báo invalid signature | Chọn registration khác IdP đã ký hoặc cert đã rotate | Kiểm issuer, chosen registration, trusted signing keys |
| ACS báo invalid Audience | SP Entity ID khác IdP expected Audience | So metadata SP và config IdP đúng tenant |
| ACS báo invalid Recipient | ACS path/hostname khác public Reply URL | So proxy, IdP stored ACS, request URL |
| SSO chạy ở localhost nhưng fail trên ingress | `{baseUrl}` bị tính từ HTTP internal host | Trusted Forwarded headers hoặc explicit public URLs |
| Multi-tenant login thỉnh thoảng sai khi load-balanced | Các nodes dùng config/cache khác hoặc request repo mất state | Đồng bộ cache/keys, Spring Session |
| Một IdP issuer trùng giữa tenants, converter chọn nhầm | Lookup by Issuer không đủ phân biệt | Dùng request state/dedicated ACS/host hoặc reject unsolicited |
| SAMLResponse không có InResponseTo được nhận ngoài ý muốn | IdP-initiated policy quá rộng | Bật deny unsolicited hoặc thêm policy riêng, test login CSRF |
| Metadata trả tất cả registrations | Iterable repository ở endpoint chung | Dùng per-registration metadata hoặc custom response resolver |
| Tenant vừa bị disabled vẫn login được | Cache stale hoặc repository không kiểm enabled | Invalidate cache/refresh, fail closed |
| IdP cert đổi nhưng TLS vẫn bình thường | SAML signing key rotation riêng TLS | Cập nhật trusted IdP verification credentials |
| User alpha có thể truy cập dữ liệu beta | Authorization bỏ tenant scope | Sửa resource-level tenant checks, issuer+subject mapping |
| ACS 404 sau custom path | `loginProcessingUrl` đổi nhưng metadata/IdP chưa cập nhật | Đồng bộ Spring filter, ACS metadata và IdP Reply URL |
| AuthenticationConverter tùy biến khiến chữ ký không được kiểm | Provider/manager bị thay sai | Giữ OpenSAML validation mặc định, test negative signature |
| Host spoofing làm chọn registration khác | Backend nhận Host/Forwarded không tin cậy | Chặn direct backend, sanitize proxy headers, allowlist |

**Thứ tự debug:** tenant routing → host/path ID hint → repository/registration → AuthnRequest state → issuer/certificate/Audience/ACS → authentication provider → principal/authorities → business tenant authorization. Tránh bỏ signature hoặc audience validation để làm login “thành công”.

## 17. Checklist thiết kế trước khi đưa vào production

- [ ] Quy định rõ **multi-IdP** khác **multi-tenant** và tenant được chọn trước authentication bằng yếu tố nào.
- [ ] Mọi registration ID duy nhất, ổn định và thuộc đúng tenant.
- [ ] SP Entity ID, ACS, IdP issuer, SSO URL và signing certificates được đối chiếu theo từng registration.
- [ ] Dùng repository mặc định nếu chỉ cần lookup bằng ID; chỉ custom resolver khi có nhu cầu request-based rõ.
- [ ] `RelyingPartyRegistrationResolver.resolve(HttpServletRequest,String)` được implement fail closed.
- [ ] Không tin Host/X-Forwarded-Host/X-Tenant do client có thể spoof; có trusted ingress routing.
- [ ] Không để query parameter/metadata URL từ user trở thành trusted IdP issuer/key.
- [ ] Khi host/path/hint xung đột, reject; không fallback tenant đầu tiên.
- [ ] Outgoing AuthnRequest selection có policy phù hợp, không chỉ custom ACS converter.
- [ ] SAMLResponse selection giữ pending AuthnRequest/browser state nếu SP-initiated.
- [ ] IdP-initiated/unsolicited Response chỉ chấp nhận theo policy và không gây ambiguous issuer lookup.
- [ ] Response/Assertion được xác minh chữ ký bằng đúng IdP verification credentials trong chosen registration.
- [ ] Issuer, Audience, Recipient, Destination, timing, InResponseTo và replay đều được kiểm.
- [ ] Metadata endpoint thuộc đúng tenant, không công bố sai Entity ID/ACS/cert.
- [ ] SLO request/response selection nếu bật logout federation được cấu hình/kiểm riêng.
- [ ] Không ghép local accounts chỉ bằng email, không map roles không có tenant scope.
- [ ] Dynamic DB/caching có lifecycle/rotation, audit và disable tenant rõ ràng.
- [ ] Unit tests host/path hints và integration tests cross-tenant/multi-node/negative signatures đã chạy.
- [ ] Không log nguyên SAMLResponse, NameID, private keys, group claims nhạy cảm hoặc cookies.
- [ ] Spring Security 6.x/7.x API đã được khóa, migration/test tương ứng; không dùng ví dụ của Spring SAML Extension cũ.

## 18. Câu hỏi tự kiểm tra

1. **`RelyingPartyRegistrationResolver` có trả Authentication không?** Không. Nó trả `RelyingPartyRegistration` để các thành phần khác tiếp tục xử lý.
2. **Method quan trọng của interface là gì?** `resolve(HttpServletRequest request, String relyingPartyRegistrationId)`.
3. **Repository và Resolver khác nhau thế nào?** Repository lookup theo ID; Resolver quyết định ID/config dựa request và optional hint.
4. **DefaultRelyingPartyRegistrationResolver làm gì?** Lấy registration ID theo context, tra repository và resolve URI placeholders.
5. **Nếu có nhiều IdP nhưng path callback đã chứa registrationId thì có bắt buộc custom resolver?** Không. Đường mặc định có thể đủ khi trust/isolation đã đúng.
6. **Custom converter nhận SAMLResponse có làm outbound AuthnRequest tự chọn đúng tenant không?** Không. Outgoing dùng `Saml2AuthenticationRequestResolver`/entrypoint riêng.
7. **Chọn IdP dựa Host có an toàn tuyệt đối không?** Không nếu Host/Forwarded headers chưa được gateway chuẩn hóa.
8. **Nếu host alpha và hint beta?** Fail closed; không chọn beta từ user input.
9. **Issuer trong SAMLResponse có đáng tin trước verify chữ ký không?** Không. Nó chỉ có thể là hint tra candidate registration.
10. **SAMLResponse ký hợp lệ bởi beta có được login vào alpha không?** Không, khi tenant policy chỉ cho alpha; phải khớp registration, issuer, Audience và ACS.
11. **Tại sao pending AuthnRequest có ích?** Liên kết registration, request ID và browser/session để chống nhầm lẫn và login CSRF.
12. **Khi shared ACS không có registrationId nên làm gì?** Dùng trusted host/state/issuer mapping có kiểm soát, custom converter và reject ambiguous cases.
13. **Metadata có được xử lý bởi cùng converter ACS không?** Không. Có `Saml2MetadataResponseResolver` riêng.
14. **Như thế nào là SSRF metadata?** Cho người dùng quyết định URL IdP metadata để server tự fetch/trust nguồn tùy ý.
15. **Một tenant có hai IdPs thì chọn thế nào?** User chọn trong allowlist của tenant, không nhầm tenant with IdP.
16. **Một issuer chung cho hai tenant có làm lookup bằng Issuer đủ không?** Không, cần request state hoặc context đáng tin khác.
17. **Đổi loginProcessingUrl có đủ để callback hoạt động không?** Không. Phải cập nhật ACS metadata và IdP Reply URL.
18. **Resolver có quyền bỏ signature validation không?** Không; provider phải xác minh signature và conditions sau selection.
19. **Dynamic registrations cần chú ý điều gì?** Caching, atomic config, signing cert rotation, disabled tenant, trust anchor và audit.
20. **Cross-tenant authorization phải dựa gì?** Tenant ID từ authentication được xác minh, issuer/subject và rules cho resource cụ thể.

## 19. Tài liệu chính thức

- Spring Security – SAML 2.0 Login Overview; registration repository, URI patterns, selection và multi-IdP: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML Responses; custom `AuthenticationConverter`: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – Producing AuthnRequests; request resolver và AuthnRequest repository: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security – SAML Metadata và custom `Saml2MetadataResponseResolver`: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- JavaDoc – `RelyingPartyRegistrationResolver`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/RelyingPartyRegistrationResolver.html
- JavaDoc – `DefaultRelyingPartyRegistrationResolver`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/DefaultRelyingPartyRegistrationResolver.html
- JavaDoc – `Saml2AuthenticationTokenConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationTokenConverter.html
- JavaDoc – `Saml2LoginConfigurer`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/saml2/Saml2LoginConfigurer.html
- JavaDoc – `Saml2AuthenticationRequestResolver`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/Saml2AuthenticationRequestResolver.html
- OASIS SAML 2.0 Profiles – Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OWASP – SAML Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet

**Kết luận:** `RelyingPartyRegistrationResolver` giúp Spring Security **chọn cấu hình SP↔IdP từ HTTP request** thay vì chỉ suy ra registration ID đơn giản. Nhưng chọn cấu hình **không đồng nghĩa xác thực**. Một hệ thống nhiều tenant/IdP phải bảo đảm **đúng mapping tin cậy ở entrypoint, AuthnRequest, ACS và metadata**, không cho client tùy ý chọn trust, và luôn xác minh issuer, chữ ký, audience, recipient, request correlation cùng tenant-scoped authorization trước khi cấp quyền.
