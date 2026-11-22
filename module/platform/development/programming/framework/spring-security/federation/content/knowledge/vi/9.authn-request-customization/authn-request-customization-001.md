# Saml2AuthenticationRequestResolver và các điểm mở rộng theo phiên bản Spring Security

Trong Spring Security SAML 2.0 Login, **`Saml2AuthenticationRequestResolver`** là giao diện định nghĩa cách biến một **`HttpServletRequest`** của Service Provider (SP, còn gọi là Relying Party) thành yêu cầu xác thực SAML 2.0 gửi tới Identity Provider (IdP, còn gọi là Asserting Party). Đây là một điểm mở rộng quan trọng khi cần tùy chỉnh `AuthnRequest`: yêu cầu người dùng đăng nhập lại với **`ForceAuthn`**, đề xuất `RequestedAuthnContext`, đổi đường dẫn bắt đầu SSO, xử lý nhiều IdP hoặc điều chỉnh cách tạo yêu cầu theo chính sách doanh nghiệp.

Cần hiểu ba lớp riêng biệt:

1. **`Saml2AuthenticationRequestResolver`** quyết định và tạo thông tin AuthnRequest đi ra; nó không xác thực người dùng.
2. **`RelyingPartyRegistrationRepository` / `RelyingPartyRegistrationResolver`** cung cấp cấu hình IdP, SP entity ID, endpoint và certificate cho cặp tin cậy đang dùng.
3. **`Saml2AuthenticationRequestRepository`** lưu **yêu cầu đã phát** để đối chiếu khi SAML Response trở về; đây là đối tượng khác với *resolver*, dù tên gần giống nhau.

**Điểm cần lưu ý theo phiên bản:** interface `Saml2AuthenticationRequestResolver` xuất hiện từ Spring Security **5.7**. Tài liệu Spring Security 6.x dùng `OpenSaml4AuthenticationRequestResolver` trong những phiên bản/cấu hình dựa trên OpenSAML 4, trong khi Spring Security 7.x có ví dụ chính thức với `OpenSaml5AuthenticationRequestResolver`. Không sao chép class và import từ một nhánh tài liệu sang nhánh dependency khác mà không kiểm tra API của phiên bản đã khóa trong dự án.

## 1. AuthnRequest là gì và vì sao cần resolver?

Trong mô hình **SP-initiated SAML Web Browser SSO**, người dùng truy cập ứng dụng; SP phát `AuthnRequest` gửi IdP để yêu cầu xác thực. IdP có thể yêu cầu mật khẩu, MFA hoặc tái sử dụng phiên SSO hiện có theo chính sách. Sau đó IdP trả **SAML Response** cho Assertion Consumer Service (ACS) của SP.

~~~text
Trình duyệt          Spring Security SP/RP                    IdP
    |                           |                              |
    | GET /private              |                              |
    +-------------------------->|                              |
    |                           | Chọn registrationId           |
    |                           | -> RelyingPartyRegistration   |
    |                           | -> Saml2AuthenticationRequestResolver
    |                           | -> AuthnRequest               |
    |                           | -> lưu request tương quan     |
    | <---- Redirect / Form POST|                              |
    |---------------- SAMLRequest ----------------------------->|
    |                           |                         Xác thực
    |<----------------------- SAMLResponse ---------------------|
    |---- POST ACS ----------->|                              |
    |                     Kiểm tra chữ ký, InResponseTo,        |
    |                     audience, recipient, thời gian       |
    |                     -> Authentication -> session         |
~~~

Theo cấu hình mặc định, **`Saml2WebSsoAuthenticationRequestFilter`** kích hoạt luồng khởi tạo SSO tại các endpoint như:

- `/saml2/authenticate/{registrationId}`, ví dụ `/saml2/authenticate/corp`;
- `/saml2/authenticate?registrationId={registrationId}` trong những phiên bản Spring Security hỗ trợ.

Filter cần một resolver để xây yêu cầu dưới dạng Spring Security `AbstractSaml2AuthenticationRequest`. Tùy binding, kết quả cụ thể là `Saml2RedirectAuthenticationRequest` hoặc `Saml2PostAuthenticationRequest`.

**Đừng nhầm:** AuthnRequest chỉ là *yêu cầu xác thực*, không phải bằng chứng rằng IdP đã xác thực thành công. Quyền của người dùng chỉ được xét sau khi SP xác minh SAML Response/Assertion trở về.

## 2. Interface Saml2AuthenticationRequestResolver

Package của interface:

~~~java
org.springframework.security.saml2.provider.service.web.authentication
~~~

Mô hình chữ ký quan trọng:

~~~java
public interface Saml2AuthenticationRequestResolver {
    <T extends AbstractSaml2AuthenticationRequest> T resolve(
            HttpServletRequest request);
}
~~~

Đây là **chữ ký lược giản để học khái niệm**, không phải toàn bộ mã định nghĩa interface; các annotation nullability và hằng số của API có thể khác theo phiên bản. Trong Spring Security 6+/7+, `HttpServletRequest` thuộc package `jakarta.servlet.http` (các nhánh cũ hơn có thể dùng `javax.servlet`).

Diễn giải:

- **Input:** HTTP request đến SP, thường mang đường dẫn hoặc tham số xác định `registrationId`.
- **Output:** một `AbstractSaml2AuthenticationRequest` phù hợp với binding được cấu hình, hoặc **null** khi request không khớp trường hợp resolver xử lý.
- **Hợp đồng trách nhiệm:** tìm registration, xây dữ liệu XML SAML AuthnRequest và đóng gói yêu cầu để filter gửi đúng IdP/binding.
- **Không đảm nhiệm:** xác minh SAML Response, ánh xạ principal, phân quyền API hoặc lưu lâu dài session.

Phân biệt một số loại liên quan:

| Loại | Chức năng |
| --- | --- |
| `Saml2AuthenticationRequestResolver` | Sinh AuthnRequest cho request hiện tại |
| `RelyingPartyRegistrationResolver` | Tìm và giải quyết template của registration theo HTTP request |
| `DefaultRelyingPartyRegistrationResolver` | Triển khai phổ biến của bộ giải quyết registration |
| `RelyingPartyRegistrationRepository` | Tra cứu registration theo registrationId |
| `Saml2AuthenticationRequestRepository` | Lưu/đọc/loại bỏ request SAML đã phát để xử lý tương quan với Response |
| `Saml2AuthenticationTokenConverter` | Chuyển incoming SAMLResponse thành token authentication chưa xác minh |
| `OpenSamlXAuthenticationProvider` | Xác minh Response/Assertion và tạo Authentication theo phiên bản OpenSAML |

Giao diện resolver cho phép phần filter/DSL không cần phụ thuộc trực tiếp vào chi tiết cách OpenSAML tạo XML.

## 3. Các thành phần chính trong XML AuthnRequest

Ví dụ **mảnh XML** có một số trường thường tùy chỉnh:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_request-unique-id"
    Version="2.0"
    IssueInstant="2026-11-07T10:00:00Z"
    Destination="https://idp.example.test/sso"
    AssertionConsumerServiceURL="https://portal.example.test/login/saml2/sso/corp"
    ForceAuthn="true">
    <saml:Issuer>https://portal.example.test/saml/sp</saml:Issuer>
    <samlp:NameIDPolicy
        Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
        AllowCreate="true"/>
    <samlp:RequestedAuthnContext Comparison="exact">
        <saml:AuthnContextClassRef>
            urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
        </saml:AuthnContextClassRef>
    </samlp:RequestedAuthnContext>
</samlp:AuthnRequest>
~~~

Đây là **XML minh họa**, không phải một AuthnRequest hoàn chỉnh có chữ ký. Trong thực tế, Spring Security tạo ID ngẫu nhiên, timestamp, encoding, binding và chữ ký theo registration và chính sách. Không dùng chính chuỗi tĩnh này làm AuthnRequest thật.

Các trường cần hiểu:

| Thuộc tính/phần tử | Ý nghĩa | Rủi ro khi tự sửa sai |
| --- | --- | --- |
| `ID` | Định danh duy nhất của AuthnRequest | Trùng ID làm hỏng correlation và chống replay |
| `IssueInstant` | Thời điểm SP phát yêu cầu | Thời gian sai gây lỗi xác minh |
| `Destination` | Endpoint của IdP dự định nhận yêu cầu | Nhầm IdP/binding hoặc open redirect |
| `Issuer` | SP entity ID | Không khớp SP đăng ký tại IdP |
| `AssertionConsumerServiceURL` | Nơi IdP gửi Response trở lại | Sai ACS/recipient hoặc phản hồi tới nơi không tin cậy |
| `ProtocolBinding` | Binding mong muốn để IdP trả Response, nếu được chỉ định | Trộn lẫn binding gửi request và binding trả response |
| `ForceAuthn` | Yêu cầu IdP trực tiếp xác thực lại theo quy tắc SAML | Không phải bảo đảm MFA |
| `IsPassive` | Đề nghị IdP không tương tác trực tiếp với người dùng | Có thể thất bại nếu không có phiên SSO phù hợp |
| `NameIDPolicy` | Chính sách về cách thể hiện định danh subject | IdP không hỗ trợ format hoặc yêu cầu sai |
| `RequestedAuthnContext` | Đề nghị lớp/ngữ cảnh xác thực mong muốn | IdP có thể không hỗ trợ, cần kiểm tra kết quả thực tế |

Đường dẫn bắt đầu đăng nhập **tại SP**, ví dụ `/saml2/authenticate/corp`, không phải `Destination` trong XML. `Destination` là endpoint **tại IdP**. Tương tự, callback ACS nhận **SAMLResponse**, không phải nơi browser yêu cầu SP bắt đầu SSO.

## 4. RelyingPartyRegistrationResolver: chọn đúng SP–IdP trước khi tạo AuthnRequest

Một resolver AuthnRequest thường dựa vào `RelyingPartyRegistrationResolver` để biết cặp SP–IdP nào đang được dùng. Phần cấu hình có thể trông như sau:

~~~text
RelyingPartyRegistrationRepository
    "corp"    -> SP Portal / IdP công ty
    "partner" -> SP Portal / IdP đối tác
             |
             v
DefaultRelyingPartyRegistrationResolver
             |
             v
OpenSaml4/5AuthenticationRequestResolver
             |
             v
AbstractSaml2AuthenticationRequest
             |
             v
Saml2WebSsoAuthenticationRequestFilter
~~~

Một số điểm dễ nhầm:

- `registrationId` là khóa nội bộ của Spring Security, **không bắt buộc bằng** SAML SP entityId hoặc IdP entityId.
- `DefaultRelyingPartyRegistrationResolver` dùng repository và ngữ cảnh HTTP request để chọn và giải quyết các URI template, ví dụ `{baseUrl}`.
- Nếu một SP kết nối nhiều IdP, phải chọn registration bằng cơ chế có quy tắc; không dùng tham số `idpUrl` do người dùng nhập tùy ý để phát AuthnRequest đến Internet.
- Cấu hình `RelyingPartyRegistration` phải đúng issuer, IdP SSO endpoint, signing credential và ACS; customizer không thể khắc phục mọi lỗi registration.
- Khi ứng dụng đặt sau reverse proxy, `{baseUrl}`/SP metadata cần dựa vào external URL đã xác minh, không tin bừa `X-Forwarded-Host` từ client.

## 5. Điểm mở rộng phổ biến: sửa OpenSAML AuthnRequest bằng customizer

Đây là trường hợp người phát triển thường cần nhất: tạo một `AuthnRequest` theo cấu hình chuẩn rồi điều chỉnh một vài trường **trước bước encode/ký/gửi**. Thay vì tự dựng XML, nên dùng extension chính thức của resolver dựa trên OpenSAML.

### Ví dụ Spring Security 7.x + OpenSAML 5

Ví dụ sau dùng Java 17+ và Servlet Spring Security 7.x, với điều kiện dự án có module **`spring-security-saml2-service-provider`** và đã có bean `RelyingPartyRegistrationRepository` hợp lệ.

Tệp `src/main/java/com/example/security/SamlAuthnRequestConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml5AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlAuthnRequestConfig {

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository registrations) {

        RelyingPartyRegistrationResolver registrationResolver =
                new DefaultRelyingPartyRegistrationResolver(registrations);

        OpenSaml5AuthenticationRequestResolver resolver =
                new OpenSaml5AuthenticationRequestResolver(
                        registrationResolver);

        resolver.setAuthnRequestCustomizer(context ->
                context.getAuthnRequest().setForceAuthn(true));

        return resolver;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            Saml2AuthenticationRequestResolver resolver) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/healthz").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .authenticationRequestResolver(resolver))
            .build();
    }
}
~~~

**Giải thích:**

1. `DefaultRelyingPartyRegistrationResolver` tra cấu hình từ repository theo thông tin login request.
2. `OpenSaml5AuthenticationRequestResolver` tạo AuthnRequest bằng OpenSAML 5.
3. `setAuthnRequestCustomizer(...)` nhận một context cho phép sửa **OpenSAML AuthnRequest object**; gọi `setForceAuthn(true)` yêu cầu xác thực lại.
4. `saml2Login(...authenticationRequestResolver(resolver))` truyền trực tiếp custom resolver cho Security DSL. Cách này làm rõ điểm nối giữa bean và filter chain.
5. `securityFilterChain` chỉ phục vụ Servlet web; để SSO hoạt động thực tế còn cần SP/IdP registration, trust certificates, endpoints, user flow và một IdP đang chạy.

**Cảnh báo:** ví dụ đặt `ForceAuthn=true` **cho mọi request** tạo qua resolver này. Điều đó có thể loại bỏ lợi ích tái sử dụng SSO và khiến người dùng phải xác thực lại thường xuyên. Hãy áp dụng có chủ đích cho thao tác cần recent authentication hoặc tách flow rõ ràng. **ForceAuthn không bảo đảm MFA**; nếu cần MFA/assurance phải có chính sách IdP, RequestedAuthnContext phù hợp và kiểm chứng kết quả.

Đây là **class cấu hình của dự án Spring**, không phải Java standalone dùng một lệnh `javac` rồi `java`; không có stdout cố định. Tên import và API dựa vào tài liệu Spring Security 7.x với OpenSAML 5, **không áp nguyên mẫu vào Spring Security 5.x hoặc 6.x chưa hỗ trợ lớp này**.

### Ví dụ ở nhánh dùng OpenSAML 4

Trong một số nhánh Spring Security **5.7/6.x** dùng OpenSAML 4, ý tưởng tương tự nhưng thay resolver:

~~~java
RelyingPartyRegistrationResolver registrationResolver =
        new DefaultRelyingPartyRegistrationResolver(registrations);

OpenSaml4AuthenticationRequestResolver resolver =
        new OpenSaml4AuthenticationRequestResolver(registrationResolver);

resolver.setAuthnRequestCustomizer(context ->
        context.getAuthnRequest().setForceAuthn(true));
~~~

Đây là **mảnh code thay thế bên trong bean**, với biến `registrations` đã có và các import `OpenSaml4AuthenticationRequestResolver` thuộc package `org.springframework.security.saml2.provider.service.web.authentication`. Không thêm song song hai resolver mà không có cơ chế chọn rõ ràng. Một số class/cấu hình bị thay đổi hoặc loại bỏ khi nâng version; hãy kiểm tra class thực sự có trên classpath.

## 6. Bản đồ điểm mở rộng theo phiên bản

| Nhánh / API | Hướng tiếp cận | Lưu ý tương thích |
| --- | --- | --- |
| **Spring Security 5.2–5.6** | Có SAML2 Login nhưng khả năng tùy chỉnh AuthnRequest khác các bản mới | Không giả định interface `Saml2AuthenticationRequestResolver` đã hiện diện trước 5.7; phải đọc docs đúng release |
| **Từ 5.7** | Có `Saml2AuthenticationRequestResolver`, method `authenticationRequestResolver(...)` trong DSL; resolver dựa OpenSAML theo phiên bản | Servlet API có thể là `javax.servlet` ở thế hệ cũ |
| **Spring Security 6.x** | Dùng `jakarta.servlet`; tài liệu của nhiều nhánh 6.x cho ví dụ `OpenSaml4AuthenticationRequestResolver`, và khả năng OpenSAML 5 phụ thuộc release/dependencies | Khóa exact dependency, kiểm tra Javadoc/classpath và các cảnh báo deprecated |
| **Spring Security 7.x** | Tài liệu chính thức hướng dẫn `OpenSaml5AuthenticationRequestResolver` và `setAuthnRequestCustomizer` | Không dùng import class OpenSAML 4 đã không còn trong nhánh |
| **Từ Spring Security 6.0** | `authenticationRequestUriQuery(...)` có thể thay đổi endpoint khởi tạo AuthnRequest kèm query parameters | `authenticationRequestUri(...)` bị deprecated; không chuyển đổi URL callback ACS bằng method này |
| **Nhiều nhánh 6/7** | Có `Saml2AuthenticationRequestRepository` cho request correlation; mặc định thường là HttpSession repository | Nếu dùng distributed cache, cần kiểm soát liên kết request–browser để tránh login CSRF/fixation |

Không lấy một con số version trong bài làm chứng chỉ rằng mọi patch release đều hỗ trợ cùng chữ ký. Trước khi triển khai: kiểm tra BOM Spring Boot/Security, module SAML service provider, version OpenSAML, API import và migration notes. Đặc biệt tránh trộn dependency OpenSAML 4 và 5 bằng tay để “chữa” lỗi compile.

### Bảng chọn cách mở rộng theo nhu cầu

| Mục tiêu | Công cụ phù hợp | Không nên dùng |
| --- | --- | --- |
| Đổi URL người dùng bấm để bắt đầu SSO | `authenticationRequestUriQuery` / filter matcher đúng version | Tự sửa Destination của AuthnRequest |
| Chọn IdP theo `registrationId` | `RelyingPartyRegistrationRepository`, `RelyingPartyRegistrationResolver` | Dùng URL IdP truyền tự do từ browser |
| Thêm `ForceAuthn`, `IsPassive`, RequestedAuthnContext | OpenSAML AuthnRequest customizer của resolver phù hợp | Regex sửa XML đã ký |
| Đổi IdP SSO endpoint hoặc binding gửi request | `RelyingPartyRegistration` / asserting-party metadata | Rewrite URL sau khi ký |
| Đổi ACS xử lý SAMLResponse | `loginProcessingUrl` và `assertionConsumerServiceLocation`, metadata và IdP | Chỉ sửa đường dẫn bắt đầu SSO |
| Lưu InResponseTo/RelayState có kiểm soát | `Saml2AuthenticationRequestRepository` | Bỏ kiểm tra correlation để “fix” login |
| Tùy chỉnh validation hoặc principal của Response | `Saml2AuthenticationTokenConverter`, authentication provider/validator của version | Nhét logic xác minh assertion vào AuthnRequest resolver |

## 7. Đổi endpoint bắt đầu SSO: authenticationRequestUriQuery

Mặc định người dùng có thể bắt đầu login tại `/saml2/authenticate/corp`. Nếu cần URL riêng, chẳng hạn `/auth/sso/start?registrationId=corp`, Spring Security 6.0+ cho phép cấu hình:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .saml2Login(saml -> saml
            .authenticationRequestUriQuery(
                "/auth/sso/start?registrationId={registrationId}"))
        .build();
}
~~~

Đây là **một ví dụ cấu hình thay thế** cho `SecurityFilterChain` của mục 5; không định nghĩa đồng thời hai bean cùng tác dụng trong một ứng dụng. `{registrationId}` phải xác định registration phù hợp; hãy kiểm thử URL và redirect thực tế với nhánh Spring Security của dự án.

**Chỉ đổi endpoint khởi tạo** không đổi:

- URL `SingleSignOnService` tại IdP mà AuthnRequest sẽ gửi đến;
- ACS `/login/saml2/sso/{registrationId}` mà IdP sẽ POST Response về;
- SP entity ID và metadata IdP.

Nếu tự định nghĩa resolver và matcher khác mặc định, phải đồng bộ cách nhận URL trong custom resolver với DSL. Không giả định `authenticationRequestUriQuery` sẽ sửa matcher của custom resolver tùy chỉnh theo đúng mong muốn.

## 8. RequestedAuthnContext, ForceAuthn, IsPassive: phải hiểu ngữ nghĩa

### ForceAuthn

`ForceAuthn="true"` trong SAML AuthnRequest yêu cầu IdP trực tiếp xác thực lại subject thay vì dựa hoàn toàn vào ngữ cảnh phiên trước. Đây là cách diễn đạt yêu cầu *fresh authentication*.

Nhưng:

- Không đồng nghĩa **MFA** hoặc phishing-resistant authentication.
- Không tự đưa người dùng tới một level assurance cụ thể.
- Không tự bảo đảm IdP thực thi đúng chính sách khi hệ thống tích hợp không tương thích.
- SP phải kiểm tra `AuthnInstant` và `AuthnContext` từ **assertion đã xác minh** khi giao dịch đòi hỏi mức bảo đảm cụ thể.

### RequestedAuthnContext

`RequestedAuthnContext` có thể yêu cầu một hoặc nhiều lớp ngữ cảnh xác thực theo **`AuthnContextClassRef`**, ví dụ lớp đã thống nhất với IdP, và lựa chọn `Comparison` như `exact` theo SAML.

~~~xml
<samlp:RequestedAuthnContext
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Comparison="exact">
    <saml:AuthnContextClassRef>
        urn:oasis:names:tc:SAML:2.0:ac:classes:SmartcardPKI
    </saml:AuthnContextClassRef>
</samlp:RequestedAuthnContext>
~~~

Mảnh trên chỉ diễn tả **yêu cầu** trong AuthnRequest, không phải một `AuthnStatement` khẳng định IdP đã làm gì. Nếu IdP không hỗ trợ lớp yêu cầu, xác thực có thể thất bại với lỗi như `NoAuthnContext`. Dù IdP trả response thành công, RP vẫn phải kiểm chứng thông tin `AuthnContext` thực tế nếu nghiệp vụ cần bảo đảm.

**Không tự gán nhãn “MFA” cho một URI chỉ mang ý nghĩa mật khẩu.** Nếu tổ chức dùng URI assurance tùy chỉnh, phải xác định hợp đồng với IdP và kiểm thử hành vi thực.

### IsPassive

`IsPassive="true"` yêu cầu IdP tránh tương tác trực tiếp với người dùng. Nếu không thể xác thực bằng ngữ cảnh sẵn có, IdP có thể trả `NoPassive`. Không dùng đồng thời `IsPassive=true` và kỳ vọng có màn hình đăng nhập mới tương tác theo mọi trường hợp; mục tiêu hai lựa chọn thường mâu thuẫn.

### NameIDPolicy

`NameIDPolicy` cho phép SP yêu cầu cách thể hiện định danh subject, ví dụ persistent hoặc transient nếu IdP hỗ trợ. Chọn loại nào là quyết định federation/account linking, không nên thay đổi tùy ý sau khi người dùng đã được liên kết tài khoản.

### Tùy chỉnh OpenSAML object

Khi cần nhiều hơn `setForceAuthn`, có thể dùng context và OpenSAML XML object API của phiên bản để thay đổi các phần tử. **Không có một snippet “dùng cho mọi OpenSAML version”**: builder/factory và model class phụ thuộc version. Hãy tạo object theo API OpenSAML của nhánh đang dùng và chạy integration test với IdP cụ thể; không tự dựng XML bằng nối chuỗi.

## 9. Tùy chỉnh theo request: login thường so với step-up

Một tình huống thực tế:

- Xem dashboard: cho phép reuse SSO session theo chính sách.
- Duyệt thanh toán: phải xác thực mới trong 10 phút và thuộc lớp assurance được phê duyệt.

Sai lầm thường gặp là đặt `ForceAuthn=true` cho **toàn bộ** SSO flow. Điều đó khiến mỗi lần login lại yêu cầu xác thực và chưa chứng minh đủ điều kiện MFA.

Một thiết kế có kiểm soát:

~~~text
Ứng dụng nhận yêu cầu nghiệp vụ
            |
       Kiểm tra quyền
            |
      Cần fresh auth?
       |          |
      Không       Có
       |          |
    Login thường  Tạo step-up intent phía server
       |          |
       |         AuthnRequest:
       |         ForceAuthn=true
       |         RequestedAuthnContext theo policy
       |          |
       +-----> IdP trả Response đã được xác minh
                  |
             Kiểm tra AuthnInstant + AuthnContext
                  |
             Kiểm tra quyền nghiệp vụ lần nữa
                  |
             Cho phép hoặc từ chối hành động
~~~

**Không dùng duy nhất query parameter `?force=true` do client tự đưa để kết luận người dùng cần step-up hoặc đã qua step-up.** Động cơ step-up có thể đến từ yêu cầu nghiệp vụ của server, lưu trạng thái có TTL, gắn session/browser và liên kết với AuthnRequest ID. Sau callback, kết quả AuthnInstant/AuthnContext phải được kiểm chứng độc lập với request parameter.

Một custom resolver có thể phân loại route hoặc lấy intent từ một nguồn state đáng tin rồi gán các thuộc tính tương ứng trước khi encode/ký. Khi đặt policy động, thiết kế một lớp quyết định độc lập để unit test và một adapter OpenSAML riêng theo version. Nếu không thể đảm bảo liên kết state giữa request và response, hãy từ chối thay vì cho qua.

## 10. RelayState và AuthenticationRequestRepository không phải resolver

Hai khái niệm có tên dễ gây nhầm lẫn:

| Component | Thời điểm | Vai trò |
| --- | --- | --- |
| `Saml2AuthenticationRequestResolver` | Trước khi gửi đến IdP | Tạo AuthnRequest và thông tin binding |
| `Saml2AuthenticationRequestRepository` | Khi gửi và khi nhận Response | Lưu, tải và loại bỏ request đã phát, phục vụ correlation và chống login CSRF/replay |

Spring Security mặc định thường dùng **`HttpSessionSaml2AuthenticationRequestRepository`**. Vì HttpSession gắn với trình duyệt, kẻ tấn công không thể đơn giản lấy request ID của chính mình rồi buộc trình duyệt nạn nhân chấp nhận response cùng một session khác.

**`CacheSaml2AuthenticationRequestRepository`** có thể được sử dụng ở các phiên bản hỗ trợ để lưu request vào distributed cache, ví dụ trong kiến trúc nhiều instance hoặc ứng dụng cần thiết kế session khác mặc định. Tuy nhiên, lưu theo `RelayState` hoặc `InResponseTo` **mà không gắn an toàn với phiên/browsing context** có thể tạo rủi ro login injection/fixation. Cần nonce ngẫu nhiên, TTL ngắn, one-time retrieval, correlation và các lớp bảo vệ phiên được thiết kế có ý thức.

`RelayState` là cơ chế mang state được trả về qua SAML binding; không mặc nhiên đáng tin chỉ vì nó được IdP trả lại. Không cho phép `RelayState` chứa URL bất kỳ rồi redirect theo đó sau login; cần chống open redirect, giới hạn kích thước và lưu mapping về URL nội bộ đã thẩm định.

Thay request repository **không** đồng nghĩa thay AuthnRequest resolver. Hai thành phần có thể được cấu hình riêng, nhưng phải thống nhất cách phát ID, RelayState, lưu request và kiểm tra Response.

## 11. Chọn binding, ký request và nguồn cấu hình đúng

Việc gửi AuthnRequest bằng **HTTP-Redirect** hay **HTTP-POST** và việc ký thường liên quan đến **`RelyingPartyRegistration` / IdP metadata**, không nhất thiết cần một customizer sửa XML.

| Tình huống | Cách cấu hình chính |
| --- | --- |
| IdP nhận AuthnRequest tại SSO URL khác | Cập nhật asserting-party metadata của registration sau khi xác minh nguồn |
| IdP yêu cầu HTTP-POST | Cấu hình `singleSignOnServiceBinding(Saml2MessageBinding.POST)` phù hợp |
| IdP yêu cầu signed AuthnRequest | Cung cấp SP signing private key/certificate, ký theo IdP policy |
| IdP không yêu cầu signed AuthnRequest | Điều chỉnh chính sách `wantAuthnRequestsSigned` nếu thực sự phù hợp |
| IdP cần thuật toán ký cụ thể | Dùng metadata hoặc `signingAlgorithms` theo API và danh sách thuật toán được phép |
| SP muốn sửa `ForceAuthn` | OpenSAML authentication-request resolver customizer |
| SP cần đổi callback ACS | `assertionConsumerServiceLocation` + `loginProcessingUrl` + IdP registration |

**Không thay đổi SAMLRequest sau khi đã được ký**, và không chuyển một Redirect-bound request sang POST chỉ bằng việc đổi HTTP method. Mỗi binding có quy tắc encoding/signature tương ứng; để thư viện xử lý.

### Encoding và dữ liệu đã tạo

`AbstractSaml2AuthenticationRequest` chứa thông tin được chuẩn bị cho SAML binding. Với Redirect binding, payload thường qua DEFLATE và Base64; với POST binding, dùng Base64 theo profile. URL encoding/form escaping phải được thực hiện đúng ở lớp gửi; không tự Base64 thêm một lần trên `getSamlRequest()`.

Nếu chỉ cần xem các trường AuthnRequest khi debug, dùng test harness hoặc log đã **ẩn dữ liệu nhạy cảm** ở môi trường thử nghiệm, không ghi toàn bộ SAMLRequest/XML vào production logs. Không tự “decode/sửa/re-encode” như cách tùy biến chính thức.

## 12. Điểm mở rộng không nên dùng nhầm

Một số yêu cầu **không thuộc trách nhiệm** AuthnRequest resolver:

- **Tùy chỉnh ACS / xử lý Response:** dùng `Saml2WebSsoAuthenticationFilter`, `loginProcessingUrl`, `Saml2AuthenticationTokenConverter` và authentication provider phù hợp.
- **Bổ sung kiểm tra chữ ký/clock skew/assertion:** dùng `OpenSamlXAuthenticationProvider` hoặc extension validator trong nhánh đang dùng.
- **Đổi tên principal hoặc ánh xạ role:** thực hiện ở tầng conversion/authorization sau khi xác minh assertion.
- **Làm mới IdP metadata/certificate:** dùng registration/metadata repository hoặc cơ chế refresh an toàn.
- **OAuth 2.0 access token cho API:** dùng OAuth2 Client/Resource Server; `AuthnRequest` SAML không tự cấp token OAuth.
- **Single Logout:** dùng các thành phần logout SAML riêng, không dùng AuthnRequest resolver để tạo LogoutRequest.

Nếu nhu cầu chỉ là **đổi login URL**, không cần viết nguyên một custom XML factory. Nếu nhu cầu thay đổi **mức bảo đảm xác thực**, chỉ sửa AuthnRequest là chưa đủ; phải xác minh Response thực tế theo chính sách.

## 13. Ví dụ Java 17 độc lập: quyết định khi nào yêu cầu ForceAuthn

Để tách **chính sách ứng dụng** khỏi **code OpenSAML phụ thuộc version**, có thể quyết định từ server-side action và thời điểm xác thực đã được xác minh trước đó. Ví dụ Java 17 sau chạy độc lập; nó **không tự xác minh SAML**, không tạo token, không được dùng với dữ liệu `AuthnInstant` từ nguồn chưa tin cậy.

Tạo tệp `AuthnRequestPolicyDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;

public class AuthnRequestPolicyDemo {

    static boolean needsFreshLogin(String action, Instant lastAuthn,
                                   Instant now) {
        if (!"APPROVE_PAYMENT".equals(action)) {
            return false;
        }
        if (lastAuthn == null || lastAuthn.isAfter(now)) {
            return true;
        }
        Duration age = Duration.between(lastAuthn, now);
        return age.compareTo(Duration.ofMinutes(10)) > 0;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T10:00:00Z");
        Instant recent = Instant.parse("2026-11-07T09:55:00Z");
        Instant old = Instant.parse("2026-11-07T09:20:00Z");

        System.out.println(needsFreshLogin("VIEW_DASHBOARD", old, now));
        System.out.println(needsFreshLogin("APPROVE_PAYMENT", recent, now));
        System.out.println(needsFreshLogin("APPROVE_PAYMENT", old, now));
        System.out.println(needsFreshLogin("APPROVE_PAYMENT", null, now));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac AuthnRequestPolicyDemo.java
java AuthnRequestPolicyDemo
~~~

Stdout **chính xác**:

~~~text
false
false
true
true
~~~

Giải thích:

1. Xem dashboard không yêu cầu reauthentication theo chính sách demo.
2. Duyệt thanh toán khi lần xác thực gần nhất cách 5 phút không cần login mới.
3. Duyệt thanh toán khi lần xác thực cách 40 phút cần login mới.
4. Thiếu thông tin AuthnInstant đã được xác minh thì yêu cầu login mới.

**Chú ý bảo mật:** hàm trên chỉ đưa ra quyết định **trước khi tạo AuthnRequest**; nó không chứng minh người dùng đã đáp ứng MFA và không thay thế validation assertion/authorization. Đầu vào `action` phải đến từ tác vụ server được xác minh, không tùy tiện từ query string. Với production cần chính sách clock skew, session/intent TTL, cơ chế kiểm tra context và quy tắc step-up sau callback.

## 14. Kiểm thử resolver theo tầng

### Unit test (không cần IdP)

- Trên đường dẫn không phải SSO initiation, resolver trả null hoặc không được filter chọn.
- Đúng `registrationId` thì resolve ra request gắn registration phù hợp.
- `ForceAuthn` và các trường customizer áp dụng đúng policy.
- Route/intent không được phép không sinh yêu cầu tới IdP tùy ý.
- Không viết state/RelayState hay URL đích từ dữ liệu không được thẩm định.
- Với nhiều IdP, cùng một `registrationId` luôn map đúng metadata và chứng thư đã cấu hình.

### Integration test với IdP thử nghiệm

- Request khởi tạo tại `/saml2/authenticate/corp` thật sự chuyển trình duyệt đến đúng SSO URL.
- Giải mã SAMLRequest theo binding và xác minh trường `ForceAuthn`, `Issuer`, `Destination`, `NameIDPolicy`, RequestedAuthnContext theo cấu hình.
- Đúng chữ ký AuthnRequest nếu IdP yêu cầu, với certificate SP đã đăng ký.
- SAMLResponse trở lại đúng ACS; tương quan `InResponseTo` và `RelayState` theo quy tắc.
- IdP báo lỗi khi không thể đáp ứng RequestedAuthnContext hoặc IsPassive; ứng dụng từ chối có kiểm soát.
- Khi request step-up, Response được xác minh có `AuthnInstant` đủ mới và `AuthnContext` đúng chính sách trước thao tác nhạy cảm.
- Kiểm tra ở reverse proxy: `{baseUrl}`, Issuer, ACS sử dụng HTTPS host công khai đúng.

### Regression test khi nâng Spring Security

1. Kiểm tra **exact dependency version** và đổi `OpenSaml4...` ↔ `OpenSaml5...` khi được thư viện hỗ trợ.
2. Chạy compile/build, integration tests và không bỏ qua warning deprecation.
3. So sánh AuthnRequest XML/binding trong cùng kịch bản trước và sau nâng version.
4. Kiểm tra matcher của endpoint SSO, response ACS, lưu request session/cache và key signing.
5. Thử logout/login nhiều IdP, SSO session reuse và step-up theo policy.

## 15. Lỗi thường gặp và hướng chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Không import được `OpenSaml4AuthenticationRequestResolver` sau upgrade | Class không có trong nhánh đã dùng OpenSAML 5 | Xem Javadoc đúng version, chuyển sang OpenSaml5 API thay vì trộn JAR |
| Không import được `OpenSaml5AuthenticationRequestResolver` | Project đang ở nhánh chưa có resolver đó hoặc thiếu SAML provider | Đồng bộ Spring Security BOM/module, chọn class đúng version |
| `Saml2AuthenticationRequestResolver` không nhận HTTP request | Matcher/URL SSO initiation không khớp | Kiểm tra `authenticationRequestUriQuery`, request matcher của resolver |
| Gửi AuthnRequest nhưng IdP báo SP unknown | SP entityId hoặc registration IdP không tương thích | Đối chiếu metadata SP/IdP và entity IDs |
| IdP báo Request signature invalid | SP signing credential, binding, algorithm hoặc XML bị sửa sai | Cấu hình signing đúng, không sửa payload sau ký |
| IdP trả `NoAuthnContext` | RequestedAuthnContext không được IdP hỗ trợ | Thỏa thuận assurance classes, kiểm thử mapping và policy |
| Bật ForceAuthn khiến liên tục bị yêu cầu đăng nhập | Customizer áp dụng toàn cục cho mọi login | Chỉ áp dụng theo step-up policy có kiểm soát |
| Response báo `InResponseTo` không khớp | Request không được lưu, HttpSession/SameSite, cache correlation lỗi | Kiểm tra `Saml2AuthenticationRequestRepository` và session binding |
| Response được gửi tới sai URL | ACS hoặc reverse proxy public URL cấu hình sai | Đồng bộ `assertionConsumerServiceLocation`, IdP, loginProcessingUrl |
| Nhiều IdP nhưng chuyển nhầm tenant | registrationId/issuer resolution sai | Ràng buộc registration với request state đáng tin |
| IdP không hỗ trợ `IsPassive` với user chưa có session | Không thể xác thực im lặng | Xử lý `NoPassive`, không tự cho qua |
| Login thành công nhưng action step-up chưa đủ assurance | Chỉ dựa vào ForceAuthn mà không kiểm tra response | Kiểm chứng AuthnInstant/AuthnContext và quyền nghiệp vụ |
| Thay request repository bằng cache, phát sinh login injection | Lấy request bằng RelayState không ràng buộc browser/session | Thiết kế one-time nonce, TTL, session binding, correlation an toàn |

**Không sửa lỗi bằng cách** tắt xác minh chữ ký SAML, bỏ qua `InResponseTo`/replay, chấp nhận mọi IdP hoặc cho phép người dùng tự chọn bất kỳ callback URL nào.

## 16. Checklist triển khai

- [ ] Biết version Spring Security, OpenSAML và package Servlet đang dùng; không trộn class ví dụ giữa các nhánh.
- [ ] `RelyingPartyRegistrationRepository` có đủ registration với IdP metadata/chứng thư/ACS/entityId hợp lệ.
- [ ] Chọn `Saml2AuthenticationRequestResolver` theo nhu cầu và version: OpenSaml4 hoặc OpenSaml5.
- [ ] Tùy chỉnh XML bằng `setAuthnRequestCustomizer` trước khi thư viện ký/encode; không tự ghép XML đã ký.
- [ ] Kiểm tra trường `ForceAuthn`, `IsPassive`, RequestedAuthnContext và `NameIDPolicy` chỉ khi IdP hỗ trợ.
- [ ] Dùng `authenticationRequestUriQuery` đúng mục đích để đổi đường dẫn bắt đầu login, không nhầm với ACS.
- [ ] Định tuyến `registrationId` tin cậy; tránh URL IdP hoặc RelayState do client tùy ý kiểm soát.
- [ ] Giữ request correlation bằng `Saml2AuthenticationRequestRepository`, xác minh `InResponseTo`/RelayState và replay.
- [ ] Cấu hình Redirect/POST binding, SP signing credential và signing algorithm phù hợp metadata IdP.
- [ ] Với step-up, xác minh Response đã ký, AuthnInstant/Context và authorization trước thao tác nhạy cảm.
- [ ] Kiểm tra login sau reverse proxy, nhiều IdP, SSO session và tình huống failure.
- [ ] Khi nâng Spring Security, chạy compile và end-to-end tests cho mọi điểm mở rộng.

## 17. Kết luận

**`Saml2AuthenticationRequestResolver` là điểm mở rộng để tạo SAML2 AuthnRequest từ HTTP request trong Spring Security.** Nó liên kết HTTP initiation với một `RelyingPartyRegistration` đáng tin rồi chuẩn bị AuthnRequest để filter gửi qua binding SAML đã cấu hình. **`Saml2AuthenticationRequestRepository` là thành phần khác**, dùng để lưu yêu cầu đã phát phục vụ correlation khi SAML Response trở về.

Khi cần đổi `ForceAuthn`, RequestedAuthnContext hoặc các thuộc tính SAML, ưu tiên customizer của **`OpenSaml4AuthenticationRequestResolver` hoặc `OpenSaml5AuthenticationRequestResolver` đúng phiên bản**. Khi chỉ đổi URL hoặc binding, dùng DSL và registration tương ứng. Khi cần yêu cầu xác thực mạnh/mới, **đừng dừng ở việc gửi AuthnRequest**: phải xác minh phản hồi và chính sách ứng dụng. Tách biệt giao thức, state, metadata và authorization giúp hệ thống federation an toàn, bảo trì được khi Spring Security đổi phiên bản.

### Tài liệu chính thức

- Spring Security 7.0 — Producing AuthnRequests: https://docs.spring.io/spring-security/reference/7.0/servlet/saml2/login/authentication-requests.html
- Spring Security 6.5 — Producing AuthnRequests: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication-requests.html
- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Javadoc — Saml2AuthenticationRequestResolver: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/Saml2AuthenticationRequestResolver.html
- Javadoc — Saml2LoginConfigurer: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/saml2/Saml2LoginConfigurer.html
- Javadoc (Spring Security 6.0) — OpenSaml4AuthenticationRequestResolver: https://docs.spring.io/spring-security/site/docs/6.0.x/api/org/springframework/security/saml2/provider/service/web/authentication/OpenSaml4AuthenticationRequestResolver.html
- OASIS SAML 2.0 Core (AuthnRequest): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
