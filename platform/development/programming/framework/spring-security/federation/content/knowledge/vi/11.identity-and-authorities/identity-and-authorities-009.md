# Tùy chỉnh kết quả xác thực bằng bộ chuyển đổi của AuthenticationProvider

Trong Spring Security SAML 2.0, IdP (*Identity Provider*) xác thực người dùng rồi gửi SAML Response tới ACS (*Assertion Consumer Service*) của ứng dụng SP (*Service Provider*). Spring Security xác minh Response/Assertion bằng OpenSAML trước khi quyết định tạo đối tượng `Authentication` cho ứng dụng. **Bộ chuyển đổi kết quả xác thực của `AuthenticationProvider`** (*response authentication converter*) là điểm mở rộng giúp doanh nghiệp biến principal SAML đã xác minh thành **danh tính nội bộ**, ánh xạ **`GrantedAuthority`**, kiểm tra tài khoản bị khóa và bảo toàn dữ liệu SAML cần dùng sau khi đăng nhập.

Ở Spring Security 7.x / OpenSAML 5, API quan trọng là **`OpenSaml5AuthenticationProvider#setResponseAuthenticationConverter(...)`**, nhận một `Converter<ResponseToken, Saml2Authentication>`. Chức năng của nó là **chuyển kết quả xác thực**, chứ không thay việc kiểm XML signature, issuer, audience, recipient, timestamp hoặc replay. Bài học thuộc nhóm **Danh tính và quyền**; các ví dụ được tách rõ giữa code Spring cần dependency và chương trình Java 17 tự chạy.

## 1. Mục tiêu và vấn đề thực tiễn

Sau bài học, bạn có thể:

- Xác định chính xác converter của **provider** khác gì converter HTTP ở SAML authentication filter.
- Hiểu `Saml2Authentication`, `Saml2AssertionAuthentication`, principal, credentials và authorities.
- Ánh xạ subject do IdP xác minh tới tài khoản nội bộ qua khóa có namespace IdP/registration.
- Tích hợp `UserDetailsService` hoặc kho liên kết danh tính, và tránh tự tạo quyền admin từ external groups.
- Cấu hình `OpenSaml5AuthenticationProvider` thực sự được `saml2Login` sử dụng.
- Giữ `Saml2ResponseAssertionAccessor` và `registrationId` khi cần SAML Single Logout.
- Phân biệt API theo Spring Security 5, 6 và 7; kiểm thử positive/negative, offboarding và tenant isolation.

Ví dụ: IdP đối tác B phát `NameID=employee-123` cùng attribute `groups=ExternalAdmins`. Ứng dụng A chỉ cho user tương ứng `localUserId=u-702` thuộc tenant B xem báo cáo. Nếu chỉ tin external group, app có thể cấp `ROLE_ADMIN` ngoài ý muốn. Nếu bỏ metadata issuer khi liên kết tài khoản, IdP C có thể có user trùng `employee-123` bị gộp vào user B. **Converter đúng phải fail closed và tuân theo quyền do ứng dụng A kiểm soát.**

## 2. Hai loại converter trong pipeline SAML

~~~mermaid
sequenceDiagram
    participant Browser as Browser
    participant Filter as Saml2WebSsoAuthenticationFilter
    participant Input as HTTP AuthenticationConverter
    participant Manager as AuthenticationManager
    participant Provider as OpenSaml5AuthenticationProvider
    participant Output as Response Authentication Converter
    participant App as SecurityContext / Ứng dụng
    Browser->>Filter: POST ACS với SAMLResponse
    Filter->>Input: convert(HttpServletRequest)
    Input-->>Filter: Saml2AuthenticationToken
    Filter->>Manager: authenticate(token)
    Manager->>Provider: authenticate(token)
    Provider->>Provider: Chọn registration và xác minh SAML
    Provider->>Output: convert(ResponseToken)
    Output-->>Provider: Saml2Authentication đã map
    Provider-->>Manager: Authentication thành công
    Manager-->>Filter: Authentication
    Filter->>App: Lưu SecurityContext
    App->>App: Authorization theo role, tenant, object
~~~

| Thành phần | Đầu vào | Đầu ra | Trách nhiệm |
| --- | --- | --- | --- |
| `Saml2AuthenticationTokenConverter` (hoặc token converter theo OpenSAML version) | HTTP request tại ACS | `Saml2AuthenticationToken` chưa xác thực | Lấy Response, chọn `RelyingPartyRegistration`, lấy AuthnRequest state |
| `AuthenticationManager` / `ProviderManager` | Authentication request | Authentication result | Gọi provider phù hợp |
| `OpenSaml5AuthenticationProvider` | SAML token + trusted registration | Authentication kết quả | Giải mã và xác thực giao thức, điều phối validation và converter |
| **`setResponseAuthenticationConverter`** | `ResponseToken` của provider | `Saml2Authentication` | Tạo principal/authorities nội bộ sau kiểm SAML |
| `UserDetailsService` / identity-link service | ID đã xác minh và namespace IdP | Local user, roles, account status | Ánh xạ và kiểm chính sách tài khoản |
| `SecurityContext` / AuthorizationManager | Authentication kết quả | Quyết định truy cập | Bảo vệ endpoint, tenant, object |

**Điểm mấu chốt:** `Saml2LoginConfigurer.authenticationConverter(...)` nếu được sử dụng liên quan bước **HTTP request → authentication token**. `OpenSaml5AuthenticationProvider#setResponseAuthenticationConverter(...)` liên quan bước **SAML assertion → Authentication đã xác thực**. Chọn sai điểm mở rộng có thể khiến code không bao giờ chạy hoặc bỏ mất kiểm chứng cần thiết.

## 3. SAML đã được kiểm gì trước khi tin vào principal?

Một response đến ACS phải qua các bước xác minh tương ứng với phiên bản/provider và profile:

1. Đúng `RelyingPartyRegistration` và issuer/entityID của IdP đã tin cậy.
2. Chữ ký XML của Response hoặc Assertion được kiểm đúng phần tử và verification certificate.
3. `AudienceRestriction` giới hạn Assertion dành cho SP Entity ID của ứng dụng.
4. `Destination` và bearer `Recipient` trùng ACS hợp lệ.
5. `InResponseTo`, `RelayState` và AuthnRequest state ràng buộc đúng phiên khi SP-initiated.
6. `NotBefore`, `NotOnOrAfter`, subject confirmation, clock skew và replay tuân theo policy.
7. SAML attributes, NameID và encrypted elements được xử lý theo trust policy.

Converter **không thể biến dữ liệu chưa xác minh thành đã xác minh**. Nếu tự gọi converter trên một Response XML do client đưa vào, mọi role mapping phía sau sẽ đứng trên dữ liệu không tin cậy. Giữ validator mặc định của Spring/OpenSAML và dùng converter **chỉ cho nhiệm vụ lập danh tính/authorities**.

Trong một số version, thứ tự kiểm Response/Assertion thay đổi; đừng xây converter dựa trên giả định tự viết rằng token đã kiểm tất cả các điều kiện mà không đọc Javadoc/migration của version đang dùng. Khi tùy chỉnh validators, ưu tiên nối với defaults thay vì thay toàn bộ.

## 4. Kết quả Authentication chứa những gì?

Đối tượng `Authentication` của Spring Security cung cấp:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `getPrincipal()` | Danh tính ứng dụng dùng; có thể là `Saml2AuthenticatedPrincipal` hoặc local `UserDetails` |
| `getName()` | Tên định danh do principal/Authentication cung cấp |
| `getAuthorities()` | `Collection<? extends GrantedAuthority>` kiểm authorization |
| `isAuthenticated()` | Provider đã xác thực thành công |
| `getDetails()` | Chi tiết bổ sung tùy filter/framework |
| `getCredentials()` | Bằng chứng/đối tượng liên quan; kiểu tùy class và version |
| `getSaml2Response()` | XML SAML Response được giữ theo contract; có thể chứa dữ liệu nhạy cảm |

Dữ liệu **external assertion** không nhất thiết là **principal nội bộ**. Ví dụ:

~~~text
IdP B xác thực:
  registrationId = partner-b
  issuer         = https://idp.partner-b.example/saml2
  NameID         = employee-123
  groups         = [PortalReaders, ExternalAdmins]

Ứng dụng A liên kết:
  externalKey    = (partner-b, employee-123)
  localUserId    = u-702
  status         = ACTIVE
  tenant         = tenant-b
  authorities    = [ROLE_REPORT_VIEWER]

Authentication sau converter:
  principal      = local user u-702
  authorities    = [ROLE_REPORT_VIEWER]
  samlContext    = giữ assertion accessor/registration
~~~

Role `ROLE_REPORT_VIEWER` **không** tự cho phép xem tài nguyên tenant C; còn cần kiểm object ownership và tenant membership.

## 5. Ranh giới tin cậy giữa IdP, SP và kho quyền nội bộ

**Identity Provider** chịu trách nhiệm xác thực user và phát assertions đã ký. **Relying Party** có thể tin các claims theo hợp đồng đã phê duyệt, nhưng không bị bắt buộc phải cấp đúng mọi quyền mà IdP nêu. **Ứng dụng nội bộ** vẫn sở hữu chính sách authorization và dữ liệu nghiệp vụ.

Một bảng liên kết danh tính tốt nên bao gồm:

| Trường | Ví dụ | Vì sao cần |
| --- | --- | --- |
| `registrationId` | `partner-b` | Chỉ cặp SP–IdP được phê duyệt |
| `assertingPartyEntityId` | `https://idp.partner-b.example/saml2` | Tách các nguồn phát hành |
| `externalSubject` | `employee-123` | Khóa user do IdP cam kết ổn định |
| `NameIDFormat/NameQualifier` nếu cần | persistent format | Tránh nhầm namespace |
| `tenantId` | `tenant-b` | Ranh giới dữ liệu |
| `localUserId` | `u-702` | Định danh người dùng phía SP |
| `enabled/locked` | ACTIVE | Chính sách offboarding |
| `authorities` | `ROLE_REPORT_VIEWER` | Quyền đã duyệt trong SP |

Khóa khái niệm:

~~~text
ExternalIdentityKey(
  registrationId,
  trustedIssuer,
  stableSubject,
  qualifiersIfApplicable
)
  -> linkedLocalUser
  -> tenantMembership
  -> accountStatus
  -> permittedAuthorities
~~~

**Không tự liên kết dựa duy nhất trên email**: email có thể đổi, được tái sử dụng hoặc cùng xuất hiện ở nhiều IdP. `NameID` dạng transient có thể thay qua mỗi phiên, vì vậy nếu cần liên kết dài hạn nên dùng immutable ID đã thỏa thuận hoặc cơ chế account-linking được kiểm duyệt. Không tự lowercase/trim user ID nếu IdP không cam kết cách chuẩn hóa.

## 6. Tại sao ROLE_USER mặc định thường chưa đủ?

Theo tài liệu Spring Security, provider mặc định thường ánh xạ `AttributeStatement` thành principal và cấp một authority cơ bản `ROLE_USER`. Nó không tự xây cả đồ thị phân quyền doanh nghiệp.

Một số hệ thống cần:

- `ROLE_REPORT_VIEWER` để đọc báo cáo.
- `ROLE_REPORT_EDITOR` cho thao tác chỉnh sửa được phê duyệt.
- `ROLE_BILLING_APPROVER` chỉ khi tài khoản có approval nội bộ.
- Quyền truy cập `tenant-b` nhưng **không** có quyền tenant C.
- Từ chối user disabled dù IdP vừa xác thực thành công.

Vì vậy converter có thể gọi `UserDetailsService` hoặc service chuyên biệt để lấy roles. **Không** biến mọi giá trị external group thành `new SimpleGrantedAuthority("ROLE_" + group)` mà thiếu allowlist.

## 7. API chính của Spring Security 7.x

Ở Spring Security 7.1 / OpenSAML 5, provider có thể nhận converter kiểu:

~~~java
OpenSaml5AuthenticationProvider provider =
        new OpenSaml5AuthenticationProvider();

Converter<OpenSaml5AuthenticationProvider.ResponseToken, Saml2Authentication>
        converter = /* converter ứng dụng xây theo yêu cầu */;

provider.setResponseAuthenticationConverter(converter);
~~~

**Đây chỉ là fragment API:** cần project Spring, import đúng type và biến converter thật. Việc đặt một bean converter vào IoC **không đủ** nếu provider được `saml2Login` sử dụng không được gắn bean đó.

Sử dụng provider:

~~~java
http.saml2Login(saml ->
        saml.authenticationManager(new ProviderManager(provider)));
~~~

Tài liệu Spring Security có `OpenSaml5AuthenticationProvider.ResponseAuthenticationConverter` để thực hiện ánh xạ mặc định. Có thể tạo delegate rồi dùng `Converter.andThen(...)` thay principal/role. Cách này giữ hành vi trích attributes mặc định và giảm số bước phải tự viết.

**Đừng nhầm `ResponseToken` với `Saml2AuthenticationToken`.** ResponseToken do provider dùng khi chuyển kết quả đã xác minh; token ở HTTP filter chưa phải Authentication thành công.

## 8. Spring Security 7: Saml2AssertionAuthentication và SAML Single Logout

Spring Security 7 giới thiệu `Saml2AssertionAuthentication` và `Saml2ResponseAssertionAccessor`. Migration guide khuyên không gắn toàn bộ dữ liệu assertion vào `Saml2AuthenticatedPrincipal` như nhiều cách cũ.

`Saml2AssertionAuthentication` mở rộng `Saml2Authentication` nhưng có thêm những thông tin hữu ích:

- `getCredentials()` trả `Saml2ResponseAssertionAccessor`.
- `getRelyingPartyRegistrationId()` trả registration cụ thể.
- `getPrincipal()` chứa principal được ứng dụng dùng.
- `getAuthorities()` chứa authorities cuối cùng.
- `getSaml2Response()` được kế thừa.

**Vì sao cần giữ?** SAML Single Logout cần thông tin về assertion/NameID/SessionIndex và registration để giao tiếp với đúng IdP. Nếu converter thay Authentication bằng một token username/password, hoặc bằng `Saml2Authentication` thuần chỉ có response string, SLO có thể mất thông tin mà framework mong đợi.

Javadoc Spring Security 7 có constructor:

~~~java
new Saml2AssertionAuthentication(
    localPrincipal,
    existingAssertionAccessor,
    mappedAuthorities,
    relyingPartyRegistrationId
);
~~~

Các biến là **fragment minh họa**, không phải đoạn chương trình đầy đủ. Hãy dùng accessor được converter/provider chuẩn trả về, không tự tạo một object “assertion đã xác minh” từ XML chưa kiểm chữ ký.

## 9. Ví dụ Spring Security 7.1: thay principal và quyền theo UserDetailsService

Giả sử:

1. Ứng dụng đã có `RelyingPartyRegistrationRepository` cho `corp` và `partner-b`.
2. Có `UserDetailsService` tra khóa `registrationId + "|" + stableExternalSubject`, ví dụ `partner-b|employee-123`.
3. User store có `UserDetails.isEnabled()`, account locked/expired và `getAuthorities()` do app quản lý.
4. `verified.getName()` là subject **bền vững trong namespace registration** theo hợp đồng IdP. Nếu không, phải thiết kế subject resolver/identity link riêng.
5. Ứng dụng dùng đúng Spring Security 7.x / OpenSAML 5; class `Saml2AssertionAuthentication` tồn tại từ 7.0.

File `SamlUserMappingSecurityConfig.java`:

~~~java
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider.ResponseAuthenticationConverter;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider.ResponseToken;
import org.springframework.security.saml2.provider.service.authentication.Saml2AssertionAuthentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlUserMappingSecurityConfig {

    private static final Set<String> ALLOWED_IDPS =
            Set.of("corp", "partner-b");

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService localUsers) throws Exception {

        OpenSaml5AuthenticationProvider provider =
                new OpenSaml5AuthenticationProvider();

        ResponseAuthenticationConverter defaults =
                new ResponseAuthenticationConverter();

        Converter<ResponseToken, Saml2Authentication> mapped =
                defaults.andThen(authentication -> {
                    if (!(authentication instanceof
                            Saml2AssertionAuthentication verified)) {
                        throw new BadCredentialsException(
                                "Missing SAML assertion context");
                    }
                    String registrationId =
                            verified.getRelyingPartyRegistrationId();
                    if (!ALLOWED_IDPS.contains(registrationId)) {
                        throw new BadCredentialsException(
                                "Unknown SAML registration");
                    }
                    String externalSubject = verified.getName();
                    if (externalSubject == null
                            || externalSubject.isBlank()) {
                        throw new BadCredentialsException(
                                "Missing stable external identity");
                    }

                    // Demo: UserDetailsService dùng namespace "id|subject".
                    // Production: dùng composite identity-link repository.
                    String lookupKey =
                            registrationId + "|" + externalSubject;
                    UserDetails user =
                            localUsers.loadUserByUsername(lookupKey);

                    if (!user.isEnabled() || !user.isAccountNonLocked()
                            || !user.isAccountNonExpired()) {
                        throw new DisabledException(
                                "Local account is inactive");
                    }

                    Saml2AssertionAuthentication result =
                            new Saml2AssertionAuthentication(
                                    user,
                                    verified.getCredentials(),
                                    user.getAuthorities(),
                                    registrationId);
                    result.setDetails(verified.getDetails());
                    return result;
                });

        provider.setResponseAuthenticationConverter(mapped);

        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/health").permitAll()
                    .requestMatchers("/admin/**").hasRole("ADMIN")
                    .anyRequest().authenticated())
            .saml2Login(saml -> saml
                    .authenticationManager(new ProviderManager(provider)));

        return http.build();
    }
}
~~~

**Giải thích từng khâu:**

- `ResponseAuthenticationConverter defaults` xử lý mapping mặc định, giữ dữ liệu SAML do provider xác thực.
- `defaults.andThen(...)` thêm bước quy đổi user/role **sau** mapping mặc định, không tự xử lý XML chưa kiểm.
- `Saml2AssertionAuthentication` giữ assertion accessor và `registrationId` của phiên bản 7.
- `ALLOWED_IDPS` là allowlist minh họa; trong sản phẩm nên quản trị theo cấu hình IdP hợp đồng.
- `UserDetailsService` cung cấp local user và local authorities. Không lấy `groups=ExternalAdmins` để tự cấp `ROLE_ADMIN`.
- `DisabledException` từ chối account inactive ngay cả khi IdP xác thực user.
- `new ProviderManager(provider)` là nơi quan trọng để đảm bảo filter sử dụng provider đã được gắn converter.
- `hasRole("ADMIN")` yêu cầu authority `ROLE_ADMIN` theo cấu hình prefix mặc định; không tự cho qua.
- `setDetails` giữ thêm chi tiết nếu framework/app có dùng, nhưng không đồng nghĩa thay `SecurityContext` hay session policy.

**Điều kiện runtime:** class này yêu cầu project Spring Boot/Spring Security có module `spring-security-saml2-service-provider`, IdP metadata/credentials đúng và một `UserDetailsService` bean hợp lệ. Nó **không phải chương trình Java thuần** chạy được bằng `javac`. Không khai báo Identity Provider tùy ý từ HTTP query. Khi chỉ có Spring Security 6.x, cần thay API vì `Saml2AssertionAuthentication` chưa tồn tại.

**Lưu ý bảo mật với lookupKey:** nối `registrationId + "|" + externalSubject` chỉ dùng để minh họa. Nếu định danh có ký tự phân cách hoặc qualifier phức tạp, có nguy cơ nhập nhằng. Trong production, dùng DB unique composite key chứa registration/issuer/subject/qualifiers, và định danh SAML được chọn phải bền vững.

## 10. Nếu muốn đổi tên principal từ một SAML attribute

Tình huống: IdP gửi `NameID` loại transient, còn SP cần immutable `employeeId` từ `AttributeStatement`. Spring Security 7 cung cấp:

~~~java
ResponseAuthenticationConverter converter =
        new ResponseAuthenticationConverter();

converter.setPrincipalNameConverter(assertion -> {
    // Trích employeeId theo contract của IdP.
    // Phải kiểm đúng Name/NameFormat và tính đơn trị/không rỗng.
    return extractContractedEmployeeId(assertion);
});
~~~

Đây là **fragment thiết kế**: `extractContractedEmployeeId` là hàm ứng dụng phải cài đặt theo OpenSAML Assertion API và hợp đồng IdP. Không chép fragment như một chương trình hoàn chỉnh. Nếu NameID đã là khóa bền vững được IdP bảo đảm, không cần tùy chỉnh chỉ để đổi tên cho đẹp.

Khi lấy attribute làm principal key:

- Chỉ lấy từ assertion đã qua validation và đúng IdP đã chọn.
- Phải biết attribute `Name`, `NameFormat` và kiểu giá trị XML.
- Nếu thuộc tính thiếu, null, có nhiều giá trị mâu thuẫn: **fail closed**.
- Không tự lowercase email, trim/cắt chuỗi nếu không có quy ước định danh.
- Không tự quyết định hai IdP có cùng employeeId là một người.
- Gắn issuer + subject/qualifier vào identity-link policy và audit.
- Kiểm logic khi IdP đổi format/rotate issuer/đổi employeeId theo quy trình.

`setPrincipalNameConverter` tùy chỉnh **tên danh tính**, trong khi `setResponseAuthenticationConverter` cho phép tùy chỉnh **toàn bộ Authentication** gồm principal, credentials context và authorities.

## 11. Quy tắc an toàn khi ánh xạ nhóm SAML thành GrantedAuthority

Giả sử IdP B phát `groups = [PortalReaders, ExternalAdmins]` trong một AttributeStatement đã được kiểm chữ ký. SP A có chính sách:

| Issuer / registration | External group | Authority nội bộ |
| --- | --- | --- |
| `corp` | `REPORTS_VIEW` | `ROLE_REPORT_VIEWER` |
| `corp` | `REPORTS_EDIT` | `ROLE_REPORT_EDITOR` |
| `partner-b` | `PortalReaders` | `ROLE_REPORT_VIEWER` |
| `partner-b` | `ExternalAdmins` | Không map |
| `partner-c` | `PortalReaders` | Chỉ map nếu contract C cho phép |

**Nguyên tắc:**

1. **Dựa đúng nguồn:** chỉ sử dụng attributes sau khi SAML Response/Assertion được xác minh với certificate IdP tin cậy.
2. **Scope theo issuer:** hai IdP có group giống tên không mặc nhiên có role giống nhau.
3. **Allowlist:** external group không được map rõ thì **không cấp authority**.
4. **Least privilege:** quyền admin, tạo/duyệt giao dịch, xuất dữ liệu thường cần local approval.
5. **Trạng thái tài khoản:** user local bị khóa/disabled không được login dù group IdP hợp lệ.
6. **Đa tenant:** role xác thực chỉ là một đầu vào; phải kiểm membership và quyền dữ liệu cụ thể.
7. **Kiểu dữ liệu:** nhận diện empty/multiple values, đúng namespace attribute, không đoán bằng substring.
8. **Quan sát:** audit rule và local user ID nhưng không log toàn bộ Assertion.

Ví dụ không nên viết:

~~~java
// Không tự cấp role từ group không có policy.
new SimpleGrantedAuthority("ROLE_" + groupFromIdP);
~~~

Một group tên `ADMIN` do đối tác quản trị vì nhu cầu của họ **không phải** quyền `ROLE_ADMIN` trong ứng dụng SP. Nếu muốn hỗ trợ ánh xạ groups, hãy thiết kế policy `(issuer, attributeName, exactGroup) -> allowedLocalAuthority` và chỉ áp dụng sau issuer/signature check.

## 12. Kết hợp UserDetailsService với identity-link service

`UserDetailsService#loadUserByUsername(String)` là API tiện lợi khi local username đã xác định; nó không nhận issuer/tenant theo tham số riêng. Một domain service rõ hơn có thể là:

~~~java
public interface FederatedIdentityLinkService {
    LocalUser lookup(
            String verifiedRegistrationId,
            String verifiedIssuer,
            String verifiedStableSubject);
}
~~~

**Đây là interface minh họa**, không phải API Spring, và `LocalUser` phải do ứng dụng khai báo. Có thể dùng schema:

~~~text
federated_identity_link(
  registration_id,
  asserting_party_entity_id,
  external_subject,
  qualifier,
  local_user_id,
  tenant_id,
  status,
  PRIMARY/UNIQUE KEY(...)
)

local_user(
  user_id,
  enabled,
  locked,
  roles,
  membership
)
~~~

Nếu không tìm thấy user:

- **Fail closed**: từ chối với thông báo trung tính, phù hợp hệ thống B2B cần onboarding.
- **JIT provisioning**: chỉ tạo account khi IdP/tenant được cho phép và có policy chống lạm dụng, uniqueness, role tối thiểu, audit và approval khi cần.

Không tự liên kết chỉ bằng email, không import group bên ngoài thành admin, không gọi password verifier để “xác thực lại SAML” trong converter. Việc xác minh identity thuộc provider; local service chịu trách nhiệm account và authorities.

## 13. Spring Security 5/6/7 có khác nhau ở bước này không?

| Version | Provider/API thường dùng | Lưu ý khi viết code |
| --- | --- | --- |
| Spring Security 5.x đời đầu SAML2 | `OpenSamlAuthenticationProvider` và API OpenSAML nhánh cũ | Chữ ký converter/default khác; không copy code 7.x |
| Spring Security 6.0–6.4 | `OpenSaml4AuthenticationProvider` tùy phiên bản | Có `setResponseAuthenticationConverter` nhưng kiểu token/constructor phải kiểm |
| Spring Security 6.5 | Có hỗ trợ `OpenSaml5AuthenticationProvider` theo cấu hình OpenSAML | `createDefaultResponseAuthenticationConverter()` deprecated, ưu tiên nested `ResponseAuthenticationConverter` |
| Spring Security 7.x | `OpenSaml5AuthenticationProvider` và `ResponseAuthenticationConverter` | `Saml2AssertionAuthentication` và assertion accessor được ưu tiên |
| Các bản preview/snapshot | Có thể khác | Xem Javadoc của **exact version**, không đoán từ tên tutorial |

Trong Spring Security 7, `Saml2AuthenticatedPrincipal` bị deprecate ở ngữ cảnh nhiều API; `Saml2ResponseAssertionAccessor` và `Saml2AssertionAuthentication` được dùng để giữ dữ liệu cần thiết cho SAML lifecycle. Vì thế mẫu cũ:

~~~java
return new Saml2Authentication(
    myPrincipal,
    authentication.getSaml2Response(),
    myAuthorities
);
~~~

có thể không còn là lựa chọn tốt khi ứng dụng dùng SLO vì làm mất kiểu authentication/accessor chuyên biệt. Nếu buộc giữ dạng cũ vì tính tương thích, cần test phiên bản, SLO và security context rõ ràng.

Kiểm phiên bản thật thay vì suy đoán:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-saml2-service-provider
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-config
~~~

Hoặc Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

Spring Security 5.x sử dụng `javax.servlet`, trong khi 6.x/7.x sử dụng `jakarta.servlet`. Kiểm cả Spring Boot BOM, Spring Framework và OpenSAML transitive dependencies để tránh class/method linkage errors.

## 14. Java 17 chạy độc lập: kiểm ánh xạ issuer/subject và local roles

Đoạn Java thuần sau **không đọc SAML XML hoặc xác minh chữ ký**. Nó giả định các trường trong `VerifiedIdentity` đã được provider đáng tin kiểm. Bài tập chỉ chứng minh **chính sách liên kết tài khoản/role** hoạt động đúng và không gộp subject giữa hai IdP.

Tạo file `FederatedRoleMappingDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public class FederatedRoleMappingDemo {
    record ExternalKey(String registrationId, String subject) {}
    record LocalAccount(String userId, boolean active, Set<String> roles) {}
    record VerifiedIdentity(
            String registrationId, String subject, Set<String> groups) {}

    static String map(
            VerifiedIdentity verified,
            Map<ExternalKey, LocalAccount> links) {

        LocalAccount local = links.get(new ExternalKey(
                verified.registrationId(), verified.subject()));

        if (local == null) {
            return "DENY: unlinked";
        }
        if (!local.active()) {
            return "DENY: inactive";
        }

        String roles = local.roles().stream()
                .sorted()
                .collect(Collectors.joining(", ", "[", "]"));
        return "ALLOW " + local.userId() + " " + roles;
    }

    public static void main(String[] args) {
        Map<ExternalKey, LocalAccount> links = Map.of(
                new ExternalKey("corp", "employee-123"),
                new LocalAccount("u-001", true,
                        Set.of("ROLE_USER", "ROLE_EDITOR")),
                new ExternalKey("partner-b", "employee-123"),
                new LocalAccount("u-702", true,
                        Set.of("ROLE_REPORT_VIEWER")),
                new ExternalKey("partner-b", "disabled-7"),
                new LocalAccount("u-703", false,
                        Set.of("ROLE_USER")));

        System.out.println("Corp: " + map(
                new VerifiedIdentity("corp", "employee-123", Set.of()),
                links));

        System.out.println("Partner B: " + map(
                new VerifiedIdentity("partner-b", "employee-123", Set.of()),
                links));

        System.out.println("Unknown issuer: " + map(
                new VerifiedIdentity("partner-c", "employee-123", Set.of()),
                links));

        System.out.println("Disabled: " + map(
                new VerifiedIdentity("partner-b", "disabled-7", Set.of()),
                links));

        System.out.println("External admin ignored: " + map(
                new VerifiedIdentity("partner-b", "employee-123",
                        Set.of("ExternalAdmins")),
                links));
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac FederatedRoleMappingDemo.java
java FederatedRoleMappingDemo
~~~

**Stdout chính xác:**

~~~text
Corp: ALLOW u-001 [ROLE_EDITOR, ROLE_USER]
Partner B: ALLOW u-702 [ROLE_REPORT_VIEWER]
Unknown issuer: DENY: unlinked
Disabled: DENY: inactive
External admin ignored: ALLOW u-702 [ROLE_REPORT_VIEWER]
~~~

**Giải thích:**

- `employee-123` thuộc `corp` và `partner-b` được ánh xạ sang **hai tài khoản khác nhau**.
- `partner-c` không có liên kết nên **DENY**.
- User `disabled-7` bị từ chối dù có external identity tồn tại.
- Group `ExternalAdmins` không được phép tự bổ sung `ROLE_ADMIN`; kết quả lấy từ local account.
- `Set` được sort giúp thứ tự stdout ổn định trên mọi JDK phù hợp.

**Giới hạn:** chương trình không bao gồm việc kiểm issuer certificate, chữ ký SAML, audience, recipient, NotBefore/NotOnOrAfter, InResponseTo, request state, replay và session. Trong app thật, `VerifiedIdentity` chỉ được tạo từ output **đã xác minh** của provider; không dùng record này làm bằng chứng từ HTTP client.

## 15. Lỗi bảo mật thường gặp

### Lỗi A — Mở rộng quyền từ external group

Một IdP đối tác phát `groups=ADMIN`. Nếu converter gán `ROLE_ADMIN` theo chuỗi group, user có thể có quyền chưa được SP chấp thuận. Giải pháp: allowlist theo registration/issuer, local approval, least privilege, kiểm quyền tài nguyên.

### Lỗi B — Dùng email làm khóa toàn cục

Cùng email có thể xuất hiện trong IdP B và C hoặc bị tái sử dụng. Giải pháp: composite key gồm nguồn phát hành đáng tin, immutable subject và qualifiers phù hợp; account linking có review.

### Lỗi C — Converter không được AuthenticationManager thực sự dùng

App đăng ký bean converter nhưng không gắn vào provider trong chain; output vẫn là `ROLE_USER`. Giải pháp: kiểm `setResponseAuthenticationConverter`, `ProviderManager`, `saml2Login.authenticationManager` và các `SecurityFilterChain` theo request matcher.

### Lỗi D — Thay validation bằng mapping

Developer tắt `ResponseValidator` hoặc `AssertionValidator` để login “pass” sau khi đổi IdP. Giải pháp: sửa metadata, issuer, ACS, certificate hoặc clock skew; không xóa security checks.

### Lỗi E — Mất thông tin SAML Single Logout

Custom converter thay `Saml2AssertionAuthentication` bằng `UsernamePasswordAuthenticationToken` hoặc `Saml2Authentication` thuần. Giải pháp: giữ assertion accessor và registration ID ở dòng 7; test SLO/NameID/SessionIndex.

### Lỗi F — Không kiểm user disabled

IdP vẫn xác thực người đã bị tổ chức SP thu hồi quyền. Giải pháp: kiểm trạng thái nội bộ tại mapping và có session revocation/TTL sau khi user đã login.

### Lỗi G — Role stale trong session

Roles được cache tại `SecurityContext` lúc login nhưng sau đó user bị thu hồi quyền. Giải pháp: TTL/refresh và kiểm quyền tại service cho thao tác quan trọng.

### Lỗi H — Ghi log assertion nhạy cảm

`getSaml2Response()` có thể chứa XML với NameID, thông tin nhân sự và session. Giải pháp: chỉ log registration ID, local user ID, correlation ID và mã lỗi rút gọn; không log raw Response, credentials hoặc private keys.

## 16. Kiểm thử converter đúng nghĩa

Kiểm thử nên chia ba lớp:

**Lớp 1 — Unit mapping:** kiểm hàm liên kết định danh và quyền sau khi đã có input giả định tin cậy. Đây là lớp `FederatedRoleMappingDemo` minh họa.

**Lớp 2 — Provider integration:** dùng IdP lab hoặc signed SAML fixtures thực để kiểm XML signature/issuer/audience/recipient/timestamp, sau đó kiểm converter có tạo đúng principal và authorities.

**Lớp 3 — End-to-end authorization:** browser đăng nhập qua IdP, session được tạo, request tới URL và tài nguyên tenant được cấp/đoạt quyền đúng policy; kiểm logout, cache và key rotation khi cần.

| Bài test | Input | Kỳ vọng |
| --- | --- | --- |
| Local identity hợp lệ | partner-b + employee-123 | Đúng localUserId và `ROLE_REPORT_VIEWER` |
| Trùng subject, khác IdP | corp + employee-123 | Không trộn với partner-b |
| Unknown registration | partner-c chưa khai báo | Fail closed |
| Missing immutable subject | NameID/attribute bắt buộc thiếu | Fail closed |
| Disabled/locked | User linked nhưng inactive | Không tạo login thành công |
| External admin group | `ExternalAdmins` | Không cấp `ROLE_ADMIN` |
| Approved group mapping | `PortalReaders` từ B theo allowlist | Đúng role đã phê duyệt |
| Invalid signature | Assertion bị sửa | Provider từ chối |
| Wrong issuer | Response từ IdP C tại registration B | Từ chối |
| Wrong audience | Assertion dành SP khác | Từ chối |
| Wrong recipient | Response hướng ACS khác | Từ chối |
| Expired assertion | Quá `NotOnOrAfter` | Từ chối |
| Incorrect `InResponseTo` | AuthnRequest không khớp | Từ chối theo SP-initiated policy |
| Replay | Gửi lại Response đã sử dụng | Không tạo session trái phép |
| Authorization tenant | User B xem dữ liệu C | HTTP 403 |
| Single Logout | Logout sau custom mapping | Giữ đúng assertion accessor và issuer |
| Role revoked | Local authority bị thu hồi | Session/refresh policy có hiệu lực |

**Một unit test tạo `Saml2Authentication` thủ công không chứng minh login SAML an toàn.** Nó chỉ kiểm phần ứng dụng sau xác thực. Muốn kết luận tính đúng đắn của federation phải có phép thử signed SAML end-to-end với IdP đã đăng ký.

## 17. Tùy chỉnh user theo IdP và tenant

Trong federation đa tổ chức, cùng `NameID` có thể xuất hiện ở nhiều issuer. Converter phải biết user thuộc registration nào để tra đúng local account; role sau đó còn bị giới hạn theo tenant.

Một policy hợp lý:

~~~text
Trusted IdP:
  partner-b -> issuer B -> tenant-b
  partner-c -> issuer C -> tenant-c

Verified Identity:
  registration = partner-b
  subject = employee-123

Local link:
  (partner-b, employee-123) -> user u-702
  u-702 is ACTIVE
  u-702 tenantMembership = tenant-b

Authorities:
  [ROLE_REPORT_VIEWER]

Request:
  GET /tenants/tenant-c/orders/991

Decision:
  authenticated = true
  role valid = true
  tenant/resource ownership = false
  -> 403 Forbidden
~~~

Tách rõ **authentication success** và **authorization success**. Converter không nên tự cho phép mọi resource theo group attribute IdP. Với Spring Security, kết hợp `authorizeHttpRequests`, `@PreAuthorize`, service-level checks và data access filters.

Nếu các IdP thay đổi NameID format/issuer hoặc dùng JIT provisioning, cần quy trình migration identity links và tests chống trùng user; không chỉ thay principal converter rồi coi dữ liệu cũ tự khớp.

## 18. Mô hình lỗi và vận hành

Khi user không login sau khi tích hợp converter, cần xác định lớp lỗi:

1. **Trước converter:** signature sai, IdP issuer sai, registration không tồn tại, ACS/recipient sai, audience không khớp, assertion expired, request state thiếu. Sửa cấu hình federation, không sửa local roles.
2. **Trong converter:** local user không tìm thấy, account disabled, nhóm không được map, khóa định danh không ổn định, identity-link repository lỗi. Sửa policy/data mapping.
3. **Sau converter:** authenticated user có role nhưng tài nguyên bị 403, session cookie không giữ, role stale, SLO lỗi. Sửa authorization/session management.

Cần telemetry vừa đủ: registrationId đã xác minh, mã lỗi, localUserId, ruleId, correlation ID, thời điểm UTC và kết quả. Không xuất raw SAMLResponse/certificate private key vào log sản xuất.

Đặc biệt với `UserDetailsService`, lỗi `UsernameNotFoundException` cần được xử lý theo thông điệp trung tính, không tiết lộ tài khoản cụ thể tồn tại hay không. Khi local user store mất kết nối, đừng mặc định cho login thành công mà không role hoặc tự tạo user admin. Dùng fail closed và giám sát.

## 19. Checklist triển khai production

- [ ] Đã xác định Spring Boot/Security/OpenSAML exact version.
- [ ] Hiểu request converter khác response authentication converter.
- [ ] `OpenSaml5AuthenticationProvider` thực tế được `saml2Login` dùng đã gắn converter.
- [ ] Converter mặc định được delegate khi không cần tự xử lý lại dữ liệu SAML.
- [ ] Chữ ký, issuer, audience, recipient, time, correlation và replay validation còn nguyên.
- [ ] External identity key chứa namespace IdP/registration và immutable subject phù hợp.
- [ ] Tài khoản local được liên kết, active, không locked và thuộc tenant hợp lệ.
- [ ] Authorities được lấy từ nguồn/allowlist được phê duyệt, không copy nhóm admin từ IdP.
- [ ] `Saml2AssertionAuthentication`/assertion accessor được bảo toàn trên Security 7 nếu dùng SLO.
- [ ] Không ghi SAMLResponse, assertion hoặc credentials vào log.
- [ ] Unit test mapping đúng cho user trùng subject khác IdP.
- [ ] Integration test signature/issuer/audience/recipient/expiration/replay.
- [ ] Authorization test 403 khi role hoặc tenant không phù hợp.
- [ ] Offboarding/session revocation/refresh role có hiệu lực đúng policy.
- [ ] Có audit, metrics và rollback khi thay converter hoặc nâng major.

## 20. Tài liệu chính thức

1. [Spring Security 7.1 — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): mục **Converting an Assertion into an Authentication**, `setResponseAuthenticationConverter`, local user và authority mapping.
2. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): chuỗi filter → token converter → provider → Authentication.
3. [Spring Security 7 — SAML Migration Guide](https://docs.spring.io/spring-security/reference/7.0/migration/servlet/saml2.html): ưu tiên `Saml2AssertionAuthentication` và `Saml2ResponseAssertionAccessor`.
4. [Javadoc — Saml2AssertionAuthentication](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/saml2/provider/service/authentication/Saml2AssertionAuthentication.html): constructor principal, accessor, authorities và registrationId.
5. [Spring Security 6.5 Deprecated API](https://javadoc.io/static/org.springframework.security/spring-security-saml2-service-provider/6.5.0/deprecated-list.html): `createDefaultResponseAuthenticationConverter` deprecated, ưu tiên `ResponseAuthenticationConverter`.
6. [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): ý nghĩa `GrantedAuthority`, prefix `ROLE_` và policy.
7. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): kiểm quyền ở service/method sau SAML login.

**Ghi nhớ:** bộ chuyển đổi kết quả của `AuthenticationProvider` là cầu nối giữa **danh tính SAML đã xác minh** và **principal/authorities của ứng dụng**. Dùng nó để cấp đúng quyền theo local policy, không thay bằng cách bỏ validation. Trên Spring Security 7, giữ `Saml2AssertionAuthentication` cùng assertion accessor để bảo toàn thông tin SAML; mọi lúc phải tách vai trò IdP xác thực và trách nhiệm SP quyết định quyền trên tài nguyên.