# Saml2AuthenticatedPrincipal, Saml2Authentication và truy cập thuộc tính SAML 2.0

> **Chủ đề:** Spring Security – federation. **Nhóm:** Danh tính và quyền. Bài này giải thích cách Spring Security chuyển SAML 2.0 Response/Assertion đã được xác thực thành đối tượng người dùng trong ứng dụng Java, cách đọc NameID và SAML attributes, cách dùng `Saml2Authentication` và `GrantedAuthority`, cùng điểm khác biệt rất quan trọng giữa **Spring Security 6.x** và **7.x**.

## 1. Mục tiêu của bài học

Sau bài này, bạn có thể:

1. Phân biệt **SAML Assertion**, **Principal**, **Authentication**, **Credentials** và **Authorities**.
2. Dùng `Saml2AuthenticatedPrincipal` trong hệ thống Spring Security 6.x để lấy `getName()`, `getAttributes()`, `getAttribute(name)` và `getFirstAttribute(name)`.
3. Lấy thông tin phiên và registration: `getRelyingPartyRegistrationId()`, `getSessionIndexes()` theo API của từng phiên bản.
4. Phân biệt `Saml2Authentication` (kết quả đã xác thực) với `Saml2AuthenticationToken` (yêu cầu xác thực đang được xử lý).
5. Không nhầm **SAML attributes** với **Spring Security GrantedAuthority** hoặc **business permissions**.
6. Xử lý thuộc tính thiếu, nhiều giá trị, sai kiểu, sai tên/namespace và thay đổi cấu hình IdP một cách an toàn.
7. Viết controller/service Spring Boot đọc danh tính đúng loại, không lộ raw `SAMLResponse`, và mapping role theo allowlist.
8. Hiểu thay đổi Spring Security 7: `Saml2AuthenticatedPrincipal` đã được đánh dấu **deprecated**, dữ liệu assertion được chuyển sang `Saml2ResponseAssertionAccessor`/`Saml2AssertionAuthentication`. Không viết mã giả định một cast luôn hoạt động ở cả hai phiên bản.

**Trả lời nhanh:** Trong ứng dụng Spring Security 6.x mặc định, `Authentication.getPrincipal()` thường là `Saml2AuthenticatedPrincipal`, còn đối tượng Authentication là `Saml2Authentication`. Trong Spring Security 7.x, mặc định có thể nhận `Saml2AssertionAuthentication` (một subclass của `Saml2Authentication`), và các thuộc tính SAML nằm ở **assertion accessor trong credentials**, thay vì mặc định nằm ở principal. Cần kiểm version trước khi chọn cách truy cập.

## 2. Từ SAML Response tới Spring Security Authentication

Spring Security Servlet SAML2 Login cho phép ứng dụng làm **Service Provider (SP/Relying Party)**. Khi người dùng hoàn thành đăng nhập tại Identity Provider (IdP/Asserting Party):

~~~text
Browser gửi SAMLResponse (HTTP POST)
           |
           v
Saml2WebSsoAuthenticationFilter
           |
           v
Saml2AuthenticationTokenConverter
           |  resolve RelyingPartyRegistration
           v
Saml2AuthenticationToken        [CHƯA xác thực]
           |
           v
AuthenticationManager -> OpenSaml5AuthenticationProvider
           |  - kiểm IdP issuer và trust
           |  - xác minh chữ ký Response/Assertion
           |  - giải mã Assertion/attributes nếu cần
           |  - kiểm Audience, Recipient, Conditions, time, request state...
           v
Saml2Authentication / Saml2AssertionAuthentication
           |  [ĐÃ xác thực nếu thành công]
           |  principal + authorities + dữ liệu SAML tương ứng
           v
SecurityContextHolder -> Controller/Service/Authorization
~~~

Tùy phiên bản Spring Security, provider có thể dùng các class OpenSAML khác nhau hoặc thứ tự validator khác nhau. Điều quan trọng: **chỉ sau khi phản hồi và assertion được xác thực** mới nên đọc NameID/thuộc tính để quyết định tài khoản hoặc quyền. Không tự Base64-decode `SAMLResponse` từ HTTP request rồi tin giá trị `NameID`/`role`.

### Năm khái niệm cần tách

| Đối tượng / khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **SAML Response** | Thông điệp IdP gửi về ACS, gồm trạng thái và một/nhiều Assertion | XML `samlp:Response` |
| **SAML Assertion** | Dữ liệu về chủ thể được IdP khẳng định và giới hạn điều kiện sử dụng | `NameID`, `AttributeStatement`, `AuthnStatement` |
| **Principal** | Danh tính người dùng trong Spring sau xác thực | Tên principal hoặc object chứa thông tin người dùng |
| **Authentication** | Kết quả xác thực Spring dùng trong `SecurityContext` | `Saml2Authentication` / `Saml2AssertionAuthentication` |
| **GrantedAuthority** | Quyền/role mà Spring dùng để quyết định truy cập | `ROLE_USER`, `ROLE_REPORT_VIEW`, `FACTOR_SAML_RESPONSE` |

**Ví dụ:** IdP gửi một `groups=finance-readers` trong Assertion. Đây trước hết chỉ là **SAML Attribute**. Chỉ khi chính sách ánh xạ đã xác minh phát ra `GrantedAuthority("ROLE_REPORT_VIEW")` thì `hasAuthority("ROLE_REPORT_VIEW")` mới chấp nhận. Không tự coi mọi chuỗi trong AttributeStatement là authority.

## 3. Assertion chứa những phần nào liên quan danh tính?

Ví dụ XML dưới đây là **fragment minh họa**; các trường bắt buộc khác như issuer, conditions, chữ ký và SAML Response bao ngoài đã lược bỏ nên **không dùng làm Assertion hợp lệ để đăng nhập**:

~~~xml
<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                ID="_sample_assertion">
  <saml:Subject>
    <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
      8f91a1c9-identity-key
    </saml:NameID>
  </saml:Subject>
  <saml:AuthnStatement SessionIndex="_session_01"
                       AuthnInstant="2026-11-07T02:30:00Z">
    <!-- AuthnContext được lược bỏ -->
  </saml:AuthnStatement>
  <saml:AttributeStatement>
    <saml:Attribute Name="email">
      <saml:AttributeValue>reader@example.org</saml:AttributeValue>
    </saml:Attribute>
    <saml:Attribute Name="department">
      <saml:AttributeValue>Finance</saml:AttributeValue>
    </saml:Attribute>
    <saml:Attribute Name="groups">
      <saml:AttributeValue>report-readers</saml:AttributeValue>
      <saml:AttributeValue>finance-users</saml:AttributeValue>
    </saml:Attribute>
  </saml:AttributeStatement>
</saml:Assertion>
~~~

Nếu IdP phát Assertion tương ứng và Spring Security xác minh thành công, về ý nghĩa:

- **NameID:** định danh của subject; có thể là persistent ID, emailAddress, transient, unspecified... theo cấu hình IdP và hợp đồng federation.
- **Attributes:** tập thuộc tính dạng **tên → danh sách giá trị**. Một tên `groups` có thể có **hai giá trị**. Giá trị có thể là đối tượng chứ không phải luôn `String`.
- **AuthnStatement.SessionIndex:** thông tin phiên SAML do IdP cung cấp, có thể được dùng trong SAML Single Logout; **không phải HttpSession ID của Spring**, cũng không phải giá trị quyền.
- **Conditions/Audience/SubjectConfirmation:** quyết định Assertion có được dùng tại SP, trong khoảng thời gian, đúng audience/recipient hay không.
- **Signature:** bảo vệ nội dung được ký; phải được kiểm cùng IdP trust trước khi tạo principal.

### Ba kiểu dữ liệu dễ bị hiểu sai

1. **NameID khác Attribute `email`.** IdP có thể đặt `NameID` là opaque persistent ID trong khi `email` là tên hòm thư có thể đổi.
2. **Attribute `groups` khác `GrantedAuthority`.** Mapper phải quyết định claim nào tin và quyền nào được cấp.
3. **SessionIndex khác Session ID của ứng dụng.** IdP SSO logout có thể dựa SessionIndex; app session nội bộ vẫn được quản lý theo security context/session riêng.

## 4. Spring Security 6.x: Saml2AuthenticatedPrincipal

Trong Spring Security 6.x, `org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal` là interface kế thừa `AuthenticatedPrincipal`. Implementation phổ biến là `DefaultSaml2AuthenticatedPrincipal`.

Các phương thức thường dùng:

| Phương thức | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| `getName()` | `String` | Tên của principal, mặc định thường từ NameID trong Assertion được dùng |
| `getAttributes()` | `Map<String, List<Object>>` | Toàn bộ SAML attributes đã được ánh xạ từ AttributeStatement |
| `getAttribute("groups")` | `List<A>` hoặc null | Danh sách giá trị của một attribute theo tên đã truyền |
| `getFirstAttribute("email")` | `A` hoặc null | Phần tử đầu tiên của attribute; có thể thiếu |
| `getRelyingPartyRegistrationId()` | `String` | Registration ID của RP/SP ↔ IdP được chọn |
| `getSessionIndexes()` | `List<String>` | Các SessionIndex SAML trong Assertion/Authentication |

`getFirstAttribute` tiện cho trường single-value theo hợp đồng, nhưng **không hợp thức hóa** một trường vốn có nhiều giá trị. Với group/entitlement, dùng **danh sách đầy đủ**, không lấy giá trị đầu rồi bỏ phần còn lại. `getAttribute("unknown")` và `getFirstAttribute("unknown")` có thể trả `null`: code phải xử lý.

**Cảnh báo generic:** `<A> A getFirstAttribute(String name)` là generic dựa trên kết quả mong đợi của caller, **không có cơ chế schema runtime tự xác minh IdP trả đúng `String`**. Nếu IdP gửi kiểu khác, gán thẳng vào `String` có thể dẫn đến `ClassCastException`. Với dữ liệu ngoài, ưu tiên nhận `Object` và kiểm `instanceof String` hoặc converter được định nghĩa rõ.

### 4.1. Cách truy cập trong controller Spring Security 6.x

Ví dụ trong ứng dụng Spring Boot MVC đã bật SAML2 login. Tệp `src/main/java/com/example/portal/LegacySamlProfileController.java`:

~~~java
package com.example.portal;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class LegacySamlProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        if (principal == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        Object department = principal.getFirstAttribute("department");
        List<?> groups = principal.getAttribute("groups");

        return Map.of(
                "name", principal.getName(),
                "registrationId", principal.getRelyingPartyRegistrationId(),
                "department", department == null ? "(missing)" : department.toString(),
                "groupCount", groups == null ? 0 : groups.size());
    }
}
~~~

**Tính chất ví dụ:** Class Java có đủ imports và cú pháp dùng cho Spring Security 6.x phù hợp, nhưng **không phải chương trình `javac` độc lập**. Cần project Spring Boot Servlet/Security/SAML2 module và IdP đã đăng ký, plus route `/me` được bảo vệ. Có xử lý null; `Map.of` không nhận null, nên code chuyển department thiếu thành chuỗi placeholder nội bộ. API mẫu **chỉ trả số lượng nhóm**, không trả toàn bộ raw assertion hoặc claims nhạy cảm. Trong production nên kiểm chính sách về dữ liệu nhận dạng có thể hiển thị.

Không tự điền vào endpoint tất cả attributes từ `principal.getAttributes()`: email, phòng ban, nhóm, số nhân viên hoặc PII có thể nhạy cảm. Chỉ trả các trường được authorization/privacy policy cho phép.

### 4.2. Truy cập qua Authentication trong 6.x

Ngoài `@AuthenticationPrincipal`, controller/service có thể nhận `Authentication` trực tiếp:

~~~java
@GetMapping("/session-type")
public String sessionType(Authentication authentication) {
    if (authentication instanceof Saml2Authentication saml) {
        Object principal = saml.getPrincipal();
        if (principal instanceof Saml2AuthenticatedPrincipal samlPrincipal) {
            return samlPrincipal.getRelyingPartyRegistrationId();
        }
    }
    return "not-legacy-saml-principal";
}
~~~

Đây là **method fragment** đặt trong controller có imports phù hợp, không phải class biên dịch độc lập. Kiểm `instanceof` thay vì cast thẳng; nếu ứng dụng có nhiều cơ chế authentication hoặc custom converter, kiểu principal có thể khác. Trong Spring Security 7.x, kiểu này còn quan trọng hơn vì `Saml2AuthenticatedPrincipal` có thể không còn là principal mặc định.

## 5. Saml2Authentication: đại diện kết quả xác thực

`org.springframework.security.saml2.provider.service.authentication.Saml2Authentication` là một implementation của Spring Security `Authentication`, kế thừa `AbstractAuthenticationToken`. Nó chứa:

- **`getPrincipal()`:** người dùng được xác thực. Kiểu tĩnh là `Object` ở API hiện đại; đừng luôn assume `Saml2AuthenticatedPrincipal`.
- **`getName()`:** tên authentication; trong flow mặc định thường phản ánh NameID của Assertion được dùng.
- **`getAuthorities()`:** tập `GrantedAuthority` mà Spring dùng kiểm truy cập.
- **`isAuthenticated()`:** thông tin trạng thái xác thực được quản lý bởi provider.
- **`getCredentials()`:** trường credentials theo Authentication interface; **nội dung cụ thể phụ thuộc subclass/version**.
- **`getSaml2Response()`:** XML SAML Response ở dạng chuỗi đã giải mã; **có thể chứa PII/định danh, assertion hoặc các phần tử vẫn được mã hóa**.
- **`getDetails()`:** thông tin chi tiết của authentication do framework/config bổ sung, **không phải map SAML attributes** theo mặc định.

**Không bao giờ log hoặc trả về trực tiếp `getSaml2Response()` trong API web.** Raw XML có thể chứa NameID, groups, email, attributes và thông tin đăng nhập nhạy cảm. Việc đã ký hoặc mã hóa một số thành phần không thay đổi yêu cầu kiểm soát quyền truy cập vào response gốc.

### 5.1. Saml2AuthenticationToken khác Saml2Authentication

| Loại | Ở giai đoạn nào | Có thể dùng làm bằng chứng danh tính? |
|---|---|---|
| `Saml2AuthenticationToken` | Filter nhận HTTP SAMLResponse, đưa vào AuthenticationManager/provider để **xác thực** | **Không**; là yêu cầu chưa được xác thực |
| `Saml2Authentication` | Provider xác thực thành công và tạo Authentication | **Có thể** dùng trong SecurityContext cùng authorization policy |
| `Saml2AssertionAuthentication` (7.x) | Kết quả xác thực dạng subclass chứa accessor assertion | **Có**, sau khi provider hoàn tất validation |
| `Saml2AuthenticatedPrincipal` (6.x) | Principal giàu dữ liệu từ Assertion | **Có**, nhưng phải lấy từ Authentication đã xác thực, không tự khởi tạo từ raw XML |

Một lỗi nghiêm trọng là đọc `Saml2AuthenticationToken.getSaml2Response()` ở filter chưa xác minh rồi gán user roles, hoặc tạo thủ công một token authenticated bằng dữ liệu từ browser. Hãy để Spring Security/OpenSAML xác minh IdP signature/trust và SAML conditions trước.

### 5.2. Authorities và kiểm truy cập

Các quyền cấp trong kết quả authentication **không tự động bằng mọi giá trị group ở IdP**. Theo SAML2 Login Overview của Spring Security ở nhánh đang mô tả, provider mặc định cấp `ROLE_USER` và `FACTOR_SAML_RESPONSE`; tập quyền có thể thay đổi khi dùng custom converter hoặc ở version cụ thể.

Ví dụ quy tắc trong `HttpSecurity`:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/reports/**").hasAuthority("ROLE_REPORT_VIEW")
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    )
    .saml2Login(Customizer.withDefaults());
~~~

Đây là **fragment cấu hình** để đưa vào `SecurityFilterChain` Servlet. `hasRole("ADMIN")` kiểm `ROLE_ADMIN` theo prefix role mặc định, còn `hasAuthority("ROLE_REPORT_VIEW")` so đúng chuỗi authority. Chỉ bật `saml2Login` **chưa tạo** custom authority `ROLE_REPORT_VIEW`; cần mapping SAML group/claims đúng trust sang authority theo policy trước khi đường dẫn reports được phép.

## 6. Spring Security 7.x: API thay đổi rất đáng lưu ý

**Spring Security 7.x tách thông tin SAML Assertion ra khỏi principal.** Tài liệu migration giải thích thay đổi này giúp Spring Security lấy các chi tiết assertion cần thiết cho SAML Single Logout ngay cả khi ứng dụng tự tạo principal tùy biến.

- `Saml2AuthenticatedPrincipal` và `DefaultSaml2AuthenticatedPrincipal` đã được đánh dấu **@Deprecated** trong JavaDoc của Spring Security 7.1.
- `Saml2AssertionAuthentication` (since 7.0) là subclass của `Saml2Authentication`.
- `Saml2AssertionAuthentication.getCredentials()` trả `Saml2ResponseAssertionAccessor` thay vì chỉ một đối tượng chung không kiểu.
- `Saml2ResponseAssertionAccessor` cung cấp `getNameId()`, `getAttributes()`, `getAttribute(name)`, `getFirstAttribute(name)`, `getSessionIndexes()` và `getResponseValue()`.
- `Saml2AssertionAuthentication.getRelyingPartyRegistrationId()` trả registration ID; thông tin này không cần lấy từ `Saml2AuthenticatedPrincipal`.
- Với cấu hình mặc định Spring Security 7, bạn **không nên cast bừa** `Authentication.getPrincipal()` sang `Saml2AuthenticatedPrincipal` rồi giả định cast luôn đúng.

Điều này có nghĩa **khác biệt giữa Principal và Assertion data** trở nên rõ ràng: principal có thể là danh tính nội bộ do ứng dụng chọn, còn assertion accessor cho biết dữ liệu SAML IdP phát hành đã được provider xác thực.

### 6.1. Bảng so sánh API 6.x và 7.x

| Nhu cầu | Spring Security 6.x phổ biến | Spring Security 7.x mặc định |
|---|---|---|
| Authentication type | `Saml2Authentication` | `Saml2AssertionAuthentication`, subclass của `Saml2Authentication` |
| Principal mặc định | `Saml2AuthenticatedPrincipal` | Có thể là một principal khác; không giả định interface legacy |
| Tên người dùng | `authentication.getName()` / `principal.getName()` | `authentication.getName()` / `accessor.getNameId()` khi cần NameID gốc |
| Một SAML attribute | `principal.getFirstAttribute(name)` | `accessor.getFirstAttribute(name)` |
| Mọi giá trị attribute | `principal.getAttribute(name)` | `accessor.getAttribute(name)` |
| Toàn bộ attributes | `principal.getAttributes()` | `accessor.getAttributes()` |
| Registration ID | `principal.getRelyingPartyRegistrationId()` | `saml2AssertionAuthentication.getRelyingPartyRegistrationId()` |
| SAML SessionIndex | `principal.getSessionIndexes()` | `accessor.getSessionIndexes()` |
| Raw SAMLResponse | `authentication.getSaml2Response()` | `authentication.getSaml2Response()` hoặc `accessor.getResponseValue()` tùy API; **tránh log** |
| Lập trình ứng dụng mới | Tiếp tục dùng theo version đang khóa | Ưu tiên API 7.x và kiểm migration guide |

**Không hiểu nhầm:** `Saml2Authentication` **không bị xóa** trên 7.x; subclass `Saml2AssertionAuthentication` chính là một `Saml2Authentication`. Thay đổi chủ yếu ở chỗ **Assertion details không còn phải chứa trong principal**. Một custom `ResponseAuthenticationConverter` vẫn có thể trả legacy `Saml2Authentication` khi cần compatibility, nhưng điều này không biến API deprecated thành giải pháp lâu dài.

### 6.2. Controller Java Spring Security 7.x

Ví dụ trong project Spring Boot dùng Spring Security **7.x**; tất cả imports đầy đủ. Tệp `src/main/java/com/example/portal/Saml7ProfileController.java`:

~~~java
package com.example.portal;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2AssertionAuthentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2ResponseAssertionAccessor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class Saml7ProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        if (!(authentication instanceof Saml2AssertionAuthentication saml)) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "SAML authentication required");
        }

        Saml2ResponseAssertionAccessor assertion = saml.getCredentials();
        Object department = assertion.getFirstAttribute("department");
        List<?> groups = assertion.getAttribute("groups");

        Map<String, Object> profile = new LinkedHashMap<>();
        profile.put("principalName", saml.getName());
        profile.put("nameId", assertion.getNameId());
        profile.put("registrationId", saml.getRelyingPartyRegistrationId());
        profile.put("department",
                department == null ? "(missing)" : department.toString());
        profile.put("groupCount", groups == null ? 0 : groups.size());
        return profile;
    }
}
~~~

**Giải thích code:**

1. `Authentication authentication` do Spring MVC lấy từ SecurityContext đã xác thực.
2. `instanceof Saml2AssertionAuthentication` xử lý tường minh API 7; nếu app cho phép nhiều authentication mechanisms, hoặc provider tùy biến trả subclass khác, không cast sai.
3. `getCredentials()` ở subclass này có kiểu `Saml2ResponseAssertionAccessor`. Đây là **dữ liệu assertion**, không phải password được trả về.
4. `getFirstAttribute("department")` là giá trị **có thể null** và kiểu không bảo đảm luôn là String.
5. `getAttribute("groups")` lấy danh sách. Controller ở ví dụ chỉ trả **số lượng**, không tiết lộ tất cả claim.
6. `getName()` và `getNameId()` có thể biểu diễn hai mục đích khác nhau nếu principal được ứng dụng tùy biến; đừng giả định luôn bằng nhau trong mọi hệ thống.
7. `registrationId` là mã cấu hình của Spring, **không phải issuer/entityID của IdP**.

Đoạn code nằm trong một ứng dụng có security filter chain bảo vệ `/me`. **Không chạy standalone bằng `javac`**; cần dependency Spring Boot/Web MVC/SAML2 SP đúng version, Java tương thích với Spring Boot và IdP đăng ký hợp lệ. Nếu có một `Saml2Authentication` legacy từ custom converter trên 7.x, ví dụ trên chủ động trả lỗi thay vì giả định credentials có assertion accessor; đây là kết quả rõ ràng để kiểm trong migration.

### 6.3. Vì sao không nên viết một controller với cast cứng?

Đoạn sau là **anti-pattern khi nâng lên 7.x**:

~~~java
// Nguy cơ ClassCastException: principal có thể không còn là
// Saml2AuthenticatedPrincipal trong Spring Security 7.x mặc định.
Saml2AuthenticatedPrincipal principal =
        (Saml2AuthenticatedPrincipal) authentication.getPrincipal();
String email = principal.getFirstAttribute("email");
~~~

Lý do: Trong nhánh 7.x, assertion attributes không còn bắt buộc thuộc principal; ứng dụng có thể có custom principal và framework cần accessor riêng để xử lý SLO. Code `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` có thể hợp lệ ở 6.x, nhưng **không phải bảo đảm tương thích mặc định với 7.x**.

**Lộ trình migration:** trước khi nâng Spring Security, kiểm các chỗ dùng `Saml2AuthenticatedPrincipal`, `DefaultSaml2AuthenticatedPrincipal`, `getRelyingPartyRegistrationId()` và `getSessionIndexes()`; viết test login từ IdP thật; chuyển assertion reads sang `Saml2ResponseAssertionAccessor` và registration ID sang `Saml2AssertionAuthentication` theo nhánh 7. Nếu cần tạm giữ dạng authentication cũ, tham khảo migration guide về `ResponseAuthenticationConverter`, đồng thời lập kế hoạch bỏ code deprecated.

## 7. Đọc attributes đúng cách: tên, kiểu, nhiều giá trị và null

SAML `AttributeStatement` ánh xạ một trường theo **tên cấu hình của IdP** tới danh sách giá trị. Điều này khác DTO JSON có thuộc tính cố định.

### 7.1. Tên attribute không được đoán

| Thông tin nghiệp vụ | Tên IdP có thể cung cấp | Vấn đề |
|---|---|---|
| Email | `email`, `mail`, URI claim | Không phải mọi IdP dùng `email` |
| Họ tên | `displayName`, `givenName`, `sn` | Có thể thiếu hoặc không đồng nhất |
| Nhóm | `groups`, `memberOf`, URI group claim | Danh sách, group ID thay vì tên |
| Bộ phận | `department`, custom URI | Có thể chứa locale hoặc giá trị mã nội bộ |
| Mã người dùng | `employeeNumber`, `uid`, NameID | Có thể khác NameID; không tự tin email là khóa bền vững |
| Vai trò | `roles`, `Role`, URI claim | Một giá trị "admin" không tự tạo GrantedAuthority |

Phải kiểm **IdP attribute mapping contract** và tên thực tế trong assertion đã được xác thực. SAML `NameFormat` và attribute `Name` cũng có ý nghĩa; các thư viện và IdP có thể biểu diễn tên khác nhau. Đừng chỉ sửa code để dò 20 tên khác nhau và chọn "tên nào có thì lấy" khi dùng cho identity binding hoặc quyền.

### 7.2. Map chứa danh sách, không phải một String duy nhất

Dữ liệu giả định (sau khi provider đã xác minh):

~~~text
{
  "email": ["reader@example.org"],
  "department": ["Finance"],
  "groups": ["report-readers", "finance-users"],
  "employeeNumber": ["E-12345"]
}
~~~

`getAttributes()` trả về kiểu `Map<String, List<Object>>`. Vì thế:

- `getFirstAttribute("email")` có thể phù hợp khi đã thỏa thuận email có đúng một giá trị.
- `getAttribute("groups")` lấy danh sách **đầy đủ**; gọi `getFirstAttribute("groups")` làm mất các group còn lại.
- `getAttribute("missing")` có thể `null`; luôn có fallback/validation.
- Không ép `List<Object>` thành `List<String>` mà không kiểm từng phần tử.
- Nếu yêu cầu email đã verified và chỉ một giá trị, **kiểm điều kiện đó** chứ không lấy giá trị đầu trong hai email và xem như hợp lệ.
- Các giá trị có thể chứa whitespace/case/encoding khác nhau; chuẩn hóa theo **hợp đồng có kiểm soát**, không áp dụng trim/lowercase tùy ý lên ID/role mà không đối chiếu IdP.

### 7.3. Một utility Java an toàn về kiểu

Ví dụ Java **độc lập**, chỉ xử lý map attributes giả định **đã đến từ bộ xác thực SAML đáng tin**, không tự kiểm SAML Response. Tệp `SamlAttributeReaderDemo.java`:

~~~java
import java.util.List;
import java.util.Map;

public class SamlAttributeReaderDemo {

    static String firstString(Map<String, List<Object>> attrs, String key) {
        List<Object> values = attrs.get(key);
        if (values == null || values.size() != 1) {
            return "(missing-or-ambiguous)";
        }
        Object value = values.get(0);
        if (!(value instanceof String str) || str.isBlank()) {
            return "(missing-or-ambiguous)";
        }
        return str;
    }

    static int stringGroupCount(Map<String, List<Object>> attrs) {
        List<Object> values = attrs.get("groups");
        if (values == null) {
            return 0;
        }
        int count = 0;
        for (Object value : values) {
            if (value instanceof String group && !group.isBlank()) {
                count++;
            }
        }
        return count;
    }

    public static void main(String[] args) {
        Map<String, List<Object>> attributes = Map.of(
                "email", List.<Object>of("reader@example.org"),
                "groups", List.<Object>of("report-readers", "finance-users"),
                "department", List.<Object>of("Finance"));

        System.out.println("email=" + firstString(attributes, "email"));
        System.out.println("unknown=" + firstString(attributes, "unknown"));
        System.out.println("groups=" + stringGroupCount(attributes));
    }
}
~~~

Biên dịch và chạy **không cần Spring** bằng Java 17+:

~~~bash
javac SamlAttributeReaderDemo.java
java SamlAttributeReaderDemo
~~~

Stdout chính xác:

~~~text
email=reader@example.org
unknown=(missing-or-ambiguous)
groups=2
~~~

**Bài học từ utility:** Tên attribute có thể thiếu, số phần tử có thể không đúng mong đợi, giá trị có thể không phải String. Với định danh/authorization, **fail closed** khi không đạt hợp đồng, thay vì cast ép hoặc tin dữ liệu tùy ý.

**Giới hạn rõ ràng:** Utility nhận một map do ta tự tạo. Nó **không** xác minh chữ ký XML, IdP issuer, Audience, Recipient, time, SessionIndex hay replay. Trên production, chỉ cung cấp attributes **sau** khi Spring Security/OpenSAML đã xác thực SAML.

## 8. Danh tính người dùng: getName, NameID, email và khóa local

### 8.1. getName() được hình thành thế nào?

Theo pipeline SAML2 Login trong tài liệu Spring Security truyền thống, `Authentication#getName()` mặc định đến từ **NameID của Assertion được chọn**. Với custom `ResponseAuthenticationConverter` hoặc custom principal, `getName()` có thể được đổi sang local user ID.

Một số khả năng thường gặp:

| Giá trị | Ý nghĩa | Có thể làm khóa local? |
|---|---|---|
| SAML persistent NameID | ID ổn định theo IdP/SP nếu IdP thực thi đúng policy | Thường phù hợp, nhưng phải kết hợp IdP issuer/tenant |
| SAML transient NameID | Định danh theo phiên/ngắn hạn | Không phù hợp làm khóa dài hạn |
| Email NameID | Hòm thư người dùng | Có thể đổi/tái sử dụng, phải đánh giá |
| Attribute `email` | Thông tin liên hệ/claim | Không mặc định là unique/verified trong mọi tenant |
| Attribute `employeeNumber` | Mã nhân sự | Chỉ dùng sau khi hợp đồng xác nhận uniqueness/lifecycle |
| Local account ID | Định danh người dùng nội bộ ứng dụng | Phù hợp khi mapping IdP issuer + subject đã được quản trị |

**Khuyến nghị:** Khi liên kết federated identities với local account, coi danh tính ít nhất là **cặp (IdP issuer hoặc registration ổn định, subject ID đã xác minh)**, kèm chính sách thay đổi tenant/IdP và JIT provisioning. Đừng hợp nhất hai user chỉ vì cùng email nếu các IdP khác nhau có thể phát cùng chuỗi email.

### 8.2. Authentication.getName khác Attribute

Ví dụ:
- `authentication.getName() = "8f91a1c9-identity-key"`;
- `email = "reader@example.org"`;
- `department = "Finance"`.

Ba giá trị dùng cho những mục đích khác nhau. Nếu ứng dụng muốn hiển thị email nhưng lưu quan hệ user bằng NameID persistent, hãy giữ rõ **public display attribute** và **stable identity binding key**.

## 9. Quyền: ánh xạ SAML group sang GrantedAuthority

### 9.1. Đừng cấp role từ một chuỗi bất kỳ

Những giá trị như:

~~~text
groups=["finance-users","report-readers"]
department=["Finance"]
title=["Director"]
~~~

không tự mang cùng độ tin cậy và độ đặc quyền. Ánh xạ quyền thường cần:

1. Xác minh chữ ký Response/Assertion **bằng đúng trusted IdP key**.
2. Xác nhận issuer, audience, recipient, time, subject và registration đúng.
3. Xác định **IdP/tenant** nào có quyền phát claim group dùng cho ứng dụng.
4. Chỉ ánh xạ một **allowlist** các group IDs cụ thể sang authority nội bộ.
5. Từ chối hoặc bỏ qua giá trị không có trong allowlist; không auto tạo `ROLE_` từ bất kỳ chuỗi nào.
6. Giữ ứng dụng quyết định access bằng `@PreAuthorize`, `hasAuthority` và business permission policy.
7. Có quy trình thu hồi: khi user rời nhóm hoặc bị disable ở IdP, phiên SP đã tồn tại phải tuân theo session expiry/re-authentication/disable policy.

### 9.2. Ví dụ hàm ánh xạ độc lập, có chặn tenant

Tệp `SamlAuthorityMapperDemo.java` – mã Java 17 độc lập, mô phỏng mapping từ **list đã được provider xác thực**:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class SamlAuthorityMapperDemo {

    static Set<String> map(String registrationId, List<?> groups) {
        if (!"corporate".equals(registrationId) || groups == null) {
            return Set.of();
        }

        Map<String, String> allowed = Map.of(
                "report-readers", "ROLE_REPORT_VIEW",
                "report-editors", "ROLE_REPORT_EDIT");

        Set<String> result = new LinkedHashSet<>();
        for (Object group : groups) {
            if (group instanceof String name) {
                String authority = allowed.get(name);
                if (authority != null) {
                    result.add(authority);
                }
            }
        }
        return Set.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> groups = List.of("report-readers", "unknown-group");
        System.out.println("corporate=" + map("corporate", groups).contains("ROLE_REPORT_VIEW"));
        System.out.println("other=" + map("other-tenant", groups).contains("ROLE_REPORT_VIEW"));
        System.out.println("admin=" + map("corporate", groups).contains("ROLE_ADMIN"));
    }
}
~~~

Chạy:

~~~bash
javac SamlAuthorityMapperDemo.java
java SamlAuthorityMapperDemo
~~~

Stdout chính xác:

~~~text
corporate=true
other=false
admin=false
~~~

Mẫu giới hạn **registrationId** và nhóm allowlist, không tự tạo quyền admin. Với hệ thống nhiều tenant, ưu tiên khóa trust theo **issuer và federation contract đã xác minh**, không dựa duy nhất vào tên `corporate` từ tham số request. `registrationId` chỉ có ý nghĩa sau khi Spring Security đã xác minh ánh xạ tới đúng IdP.

**Giới hạn ví dụ:** Hàm này trả `Set<String>`, không phải `Collection<GrantedAuthority>`, nên **chưa tự cắm vào SecurityContext**. Trong Spring Security, integration đúng cần converter/provider cho authorities sau xác thực, thường tạo `SimpleGrantedAuthority` từ danh sách đã qua allowlist và trả `Authentication` có authorities tương ứng. Không viết `new Saml2Authentication(...)` từ input chưa kiểm chữ ký để "bật role".

### 9.3. Authorization trong HTTP Security và method security

Ví dụ fragment Servlet:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/reports/**").hasAuthority("ROLE_REPORT_VIEW")
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
    .saml2Login(Customizer.withDefaults());
~~~

Ở đây:
- User chỉ có `ROLE_USER` mặc định không được xem reports hoặc admin.
- User có `ROLE_REPORT_VIEW` sau mapping đúng policy được xem reports.
- `hasRole("ADMIN")` yêu cầu `ROLE_ADMIN` với prefix mặc định.
- Ngoài URL rules, service method vẫn có thể cần business authorization theo resource owner/department/transaction, không chỉ dựa role chung.

**Không nên kiểm group text trực tiếp ở mọi controller.** Một tầng mapping đã kiểm schema, issuer và policy giúp tránh mỗi endpoint hiểu `groups` khác nhau.

## 10. Spring Security 7.x và Single Logout: vì sao tách accessor?

SAML2 Single Logout (SLO) có thể cần các giá trị của assertion như **NameID, SessionIndex và Relying Party registration**. Trước Spring Security 7, principal chứa nhiều dữ liệu đó. Nếu ứng dụng muốn custom principal (ví dụ domain user object), SLO có thể gặp khó khi cần đọc chi tiết assertion từ principal không còn interface legacy.

Trong Spring Security 7:

- Assertion được thể hiện qua `Saml2ResponseAssertionAccessor`, truy cập bằng `Saml2AssertionAuthentication.getCredentials()`.
- `getNameId()` cung cấp NameID gốc.
- `getSessionIndexes()` cung cấp các SessionIndex liên quan.
- `getRelyingPartyRegistrationId()` nằm trên authentication subclass.
- Principal có thể là một object riêng, không nhất thiết chứa attribute map hoặc SessionIndex.

### Cách không nên làm

- Lưu `SessionIndex` làm HttpSession ID: hai loại dữ liệu khác nhau.
- Gọi `getSessionIndexes().get(0)` không kiểm danh sách trống; một số assertion có thể không có SessionIndex.
- In raw `getSaml2Response()` hoặc `getResponseValue()` để debug SLO trên production.
- Tự chèn NameID/SessionIndex từ HTTP request vào SLO mà không gắn với authentication đã được xác thực.
- Giả định `Saml2AuthenticatedPrincipal` đã bị xóa ở 7.x: **nó deprecated, chưa đồng nghĩa bị xóa ngay**, nhưng cần kế hoạch nâng cấp.

**Ví dụ:** Nếu IdP dùng SessionIndex `_session_01` để quản lý SAML SSO, SP vẫn có phiên HTTP riêng do container/Spring quản lý. Khi local logout xảy ra, session HTTP có thể bị xóa nhưng IdP SSO session còn; khi SLO được triển khai đúng, framework cần danh tính và SessionIndex của authentication để trao đổi LogoutRequest/LogoutResponse với IdP theo profile.

## 11. Truy cập Authentication trong controller, service và background code

### 11.1. Controller nhận Authentication trực tiếp

Trong Spring MVC:

~~~java
@GetMapping("/whoami")
public String whoami(Authentication authentication) {
    return authentication.getName();
}
~~~

Đây là fragment, **không phải class độc lập**. Khi endpoint yêu cầu authenticated, Spring MVC có thể resolve Authentication hiện tại. Nếu có nhiều loại authentication (SAML, form login, bearer JWT), không xem mọi `Authentication` là SAML; kiểm type trước khi đọc SAML-specific properties.

### 11.2. SecurityContextHolder trong service synchronous

Với code Servlet đồng bộ:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
if (authentication == null || !authentication.isAuthenticated()) {
    // Không dùng làm danh tính ứng dụng.
}
~~~

Đây cũng là fragment. `isAuthenticated()` có thể đúng đối với một số token đặc biệt không phải người dùng thực (ví dụ anonymous tokens tùy config), nên trong business flow phải dựa vào **security rules và principal type/policy**. Đừng dùng câu `isAuthenticated()==true` làm điều kiện duy nhất cấp quyền admin.

### 11.3. Async/background jobs

`SecurityContextHolder` thường gắn với thread/ngữ cảnh xử lý request theo chiến lược của Spring Security. Nếu đẩy việc sang một executor, queue hoặc scheduled job, không nên giả định SecurityContext tự đi theo mọi thread. Khi cần thực thi công việc dưới danh tính đã xác minh, dùng context propagation/DelegatingSecurityContext phù hợp hoặc truyền một immutable **business identity key** đã được kiểm soát. Không serialize raw Saml2Authentication/SAMLResponse vào queue để tiện gọi lại.

### 11.4. WebFlux khác Servlet

Spring Security SAML2 Service Provider login được tài liệu chính thức tập trung cho **Servlet**. `@AuthenticationPrincipal` và `Authentication` nói trên thuộc ví dụ Spring MVC; không copy `HttpSecurity.saml2Login` sang `ServerHttpSecurity` WebFlux rồi mong chạy được. Nếu ứng dụng WebFlux tiêu thụ OIDC từ identity broker, principal/attributes là OAuth2/OIDC API, **không phải Saml2AuthenticatedPrincipal**.

## 12. Cấu hình Spring Boot Servlet và scope demo

Để chạy ví dụ controller trong dự án, cần Spring Boot Servlet, Security và SAML2 SP module tương thích. Trong `pom.xml` đã có Spring Boot BOM hoặc parent, phụ thuộc dạng:

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

OpenSAML dependencies/repositories cần được thêm theo đúng Spring Security version và chính sách build của dự án. Đừng ghép API của Spring Security 6 và 7 trong một artifact nếu không có compatibility plan.

Ví dụ config IdP metadata (URL minh họa, **không phải một IdP thực sẵn chạy**):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: "https://idp.example.org/metadata"
~~~

IdP phải thực sự đăng ký **SP entityID/ACS** và cung cấp public signing cert đáng tin. Thêm `SecurityFilterChain` cho Servlet (fragment):

~~~java
@Bean
SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/error").permitAll()
            .requestMatchers("/reports/**").hasAuthority("ROLE_REPORT_VIEW")
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .build();
}
~~~

Để chạy một Spring Boot project có Maven wrapper và IdP đã cấu hình đúng:

~~~bash
./mvnw spring-boot:run
~~~

Không có stdout/login result cố định vì nó phụ thuộc IdP, user và policy. Các fragment trên phải được đặt trong class có annotations/import phù hợp; controller 6.x và controller 7.x ở trên **là hai lựa chọn cho hai version**, không đưa cùng một `/me` mapping vào cùng project.

## 13. Kiểm thử đúng lớp: unit mapping, Spring MVC và SAML integration

### 13.1. Kiểm đọc thuộc tính

Các case cần có:

| Test | Input giả định từ validated SAML assertion | Kỳ vọng |
|---|---|---|
| Email single-value | `email=["a@example.org"]` | Đọc đúng giá trị |
| Email missing | không có `email` | Null/fallback hoặc reject theo policy |
| Email multi-value | `email=["a@x","b@x"]` | Reject nếu contract yêu cầu duy nhất |
| Group multi-value | `groups=["readers","finance"]` | Giữ đủ hai giá trị |
| Group type mismatch | `groups=[123]` | Không cast bừa sang String |
| NameID khác email | NameID opaque và email khác | Không ghi đè stable identity bằng email |
| Attribute names khác | IdP gửi `mail` thay `email` | Cảnh báo/mapping contract, không silently thiếu |
| Đăng nhập tenant khác | issuer khác, email giống | Không account-linking hoặc nâng quyền tự động |

### 13.2. Kiểm đúng Spring Security version

- **6.x:** test principal type `Saml2AuthenticatedPrincipal` và các phương thức getter dùng trong controller.
- **7.x:** test authentication type mặc định `Saml2AssertionAuthentication`, `getCredentials()` là `Saml2ResponseAssertionAccessor`, registration ID và SessionIndexes đúng.
- **Nâng cấp:** test rằng `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` không còn bị assume mặc định trên 7.x.
- **Mixed login:** nếu app có thêm form/Basic/OIDC, controller đọc SAML attributes phải xử lý authentication không thuộc SAML.
- **Custom converter:** test principal tùy biến vẫn cho app truy cập business identity và SLO có assertion details theo API version.

### 13.3. Kiểm integration với IdP

Một test chỉ tạo `DefaultSaml2AuthenticatedPrincipal` thủ công rồi gọi service **không kiểm chứng SAML**. Cần test với **test IdP/fixture có chữ ký hợp lệ** để xác nhận:

- SP xác minh trusted signature của Response/Assertion.
- Issuer, AudienceRestriction, Recipient/Destination, timing và InResponseTo được kiểm.
- NameID và các attributes được đọc từ Assertion **đã được xác minh**.
- Multiple Assertions/EncryptedAttributes được xử lý đúng pipeline.
- User/group mapping đúng policy và không nâng quyền bằng claim không hợp lệ.
- Logout có SessionIndexes khi cần và đúng protocol.
- Dữ liệu nhạy cảm không bị log/raw-expose.

Có thể dùng `MockMvc` và Spring Security test support để kiểm controller/authorization, nhưng test mocks **không thay thế integration test thật** với IdP signature, metadata/certificate và SAML conditions.

## 14. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân phổ biến | Hướng xử lý |
|---|---|---|
| `ClassCastException` khi cast principal | Ứng dụng 7.x hoặc custom principal không phải `Saml2AuthenticatedPrincipal` | Kiểm `instanceof`; dùng `Saml2AssertionAuthentication.getCredentials()` khi đúng version |
| `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` nhận null | Principal kiểu khác hoặc không phải SAML login | Kiểm Authentication thực tế/version; dùng Authentication + type checks |
| `getFirstAttribute("email")` trả null | IdP gửi tên khác, không có email hoặc chưa mapping | Thống nhất attribute contract; xử lý missing |
| Role từ IdP nhưng Spring trả 403 | SAML group **chưa ánh xạ** thành GrantedAuthority cần thiết | Thêm mapping allowlist trong pipeline sau validation |
| Có nhiều groups nhưng app chỉ thấy một | Dùng `getFirstAttribute("groups")` | Dùng `getAttribute("groups")` / map List<Object> |
| `ClassCastException` từ List<String> | IdP phát các giá trị kiểu khác String | Duyệt từng Object, kiểm type và reject theo policy |
| Tên principal thay đổi khi đổi NameID format | Ứng dụng dùng NameID/email không ổn định làm user key | Thiết kế subject binding lâu dài với issuer và ID ổn định |
| Chỉ thấy `ROLE_USER` | Provider mặc định không tự map mọi group claim | Custom converter/authority mapping sau khi kiểm IdP trust |
| `getSessionIndexes()` rỗng | Assertion không có SessionIndex hoặc IdP không phát | Không gọi `get(0)` không kiểm; đánh giá SLO support |
| Logout không hoạt động sau custom principal | SAML assertion details không còn ở chỗ framework cần | Dùng API accessor/credential của Spring Security 7 hoặc migration path được hỗ trợ |
| Đường `/me` trả raw group/email cho user không được phép | Controller expose quá nhiều attributes | Giới hạn fields, kiểm authz và privacy |
| Đọc `getSaml2Response()` để parse trực tiếp | Bỏ qua validator và lặp xử lý XML | Dùng typed, validated attribute API và OpenSAML pipeline |
| `getDetails()` không có email | Details khác SAML AttributeStatement | Dùng principal/accessor đúng version |
| `hasRole("ADMIN")` fail dù groups có "admin" | Chưa cấp `ROLE_ADMIN` trong authorities | Không auto cấp; mapping policy cụ thể và test |
| Session/SLO mismatch | Dùng SessionIndex làm HTTP session ID | Tách IdP SessionIndex, SP session, logout protocol |

## 15. Checklist code review và vận hành

- [ ] Đã khóa chính xác Java, Spring Boot, Spring Security và OpenSAML version.
- [ ] Đã xác nhận 6.x hay 7.x để chọn API đọc thuộc tính SAML.
- [ ] `Saml2AuthenticationToken` chỉ được dùng như **unauthenticated request**.
- [ ] Controller/service chỉ đọc dữ liệu sau khi framework tạo authenticated Authentication.
- [ ] Với 6.x, `Saml2AuthenticatedPrincipal` được lấy từ SecurityContext hoặc `@AuthenticationPrincipal` và kiểm null/type.
- [ ] Với 7.x, code nhận `Saml2AssertionAuthentication`, đọc `Saml2ResponseAssertionAccessor` và registration ID đúng API.
- [ ] `getAttribute` và `getFirstAttribute` có xử lý null, multi-values, type và attribute name.
- [ ] NameID, email, user ID, issuer và registration ID không bị nhầm.
- [ ] Group/role được map qua allowlist theo issuer/tenant và business policy, không tự tạo authority từ claim tùy ý.
- [ ] `hasRole`/`hasAuthority` và Method Security thực sự dùng những GrantedAuthority đã cấp.
- [ ] Không expose `getSaml2Response()`, `getResponseValue()`, private keys, NameID/groups nhạy cảm trong logs/public API.
- [ ] Có kiểm test với IdP thật và negative cases: invalid signature, wrong issuer/audience, expired assertion, replay, untrusted group.
- [ ] SessionIndex và SLO được xử lý theo protocol, không dùng như HTTP session ID.
- [ ] Custom converter không bypass signature/conditions validation; compatibility test cho Spring Security upgrade.
- [ ] SecurityContext/Authentication không bị truyền ra background job một cách tùy tiện.

## 16. Câu hỏi tự kiểm tra

1. **`Saml2AuthenticatedPrincipal` là gì?** Trong 6.x, là interface principal giàu thông tin đã xác thực từ SAML Assertion, có các getter NameID-like name, attributes, registration và SessionIndex. Trên 7.x đã deprecated.
2. **`Saml2Authentication` khác `Saml2AuthenticationToken` thế nào?** Token đầu là kết quả đã qua provider; token thứ hai là yêu cầu SAMLResponse chưa qua xác thực.
3. **Tại sao `getAttributes()` trả Map của List?** SAML Attribute có thể có **nhiều AttributeValue** dưới cùng một Name.
4. **Nên gọi `getFirstAttribute("groups")`?** Không nếu groups là multi-value; sử dụng `getAttribute("groups")` và xử lý đầy đủ.
5. **Nếu `getFirstAttribute` trả null?** Có thể thiếu attribute/tên không đúng; xử lý theo business contract, không cast/dùng mặc định tăng quyền.
6. **Các group từ IdP có tự thành GrantedAuthority?** Không. Cần converter/mapping theo trust và allowlist.
7. **Spring Security 7.x lấy attributes qua đâu?** Trong default SAML7 flow, từ `Saml2AssertionAuthentication.getCredentials()` trả `Saml2ResponseAssertionAccessor`.
8. **Dùng `authentication.getPrincipal()` cast thẳng sang Saml2AuthenticatedPrincipal ở 7.x được không?** Không đảm bảo; kiểm type và migration.
9. **Vì sao mã principal khác NameID?** Custom principal có thể chứa local user ID; SAML accessor vẫn giữ NameID gốc.
10. **`getSessionIndexes()` có phải HttpSession ID?** Không. Nó liên quan IdP SAML session/SLO.
11. **Có nên log `getSaml2Response()`?** Không, vì XML có thể chứa PII/claims/session info.
12. **Để cho user có quyền REPORT_VIEW cần làm gì?** Xác minh IdP/Assertion, ánh xạ group hợp lệ theo allowlist sang `ROLE_REPORT_VIEW` rồi áp dụng authorization rules.

## 17. Tài liệu chính thức cần đối chiếu theo version

- Spring Security SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security Authenticating SAML2 Responses và tùy biến Converter: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security 7 SAML2 Migration (deprecated principal và accessor): https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
- JavaDoc Saml2AuthenticatedPrincipal: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html
- JavaDoc Saml2Authentication: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2Authentication.html
- JavaDoc Saml2AssertionAuthentication: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AssertionAuthentication.html
- JavaDoc Saml2ResponseAssertionAccessor: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2ResponseAssertionAccessor.html
- Spring Security Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- OASIS SAML 2.0 Core (Assertion/AttributeStatement): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf

**Tổng kết:** `Saml2Authentication` đại diện Authentication đã được Spring Security xác minh; `Saml2AuthenticatedPrincipal` là cách đọc principal và attributes quen thuộc ở Spring Security 6.x, nhưng ở 7.x hãy chuyển sang `Saml2AssertionAuthentication` + `Saml2ResponseAssertionAccessor`. Dù API nào, **NameID ≠ email**, **SAML Attribute ≠ GrantedAuthority**, **SessionIndex ≠ HttpSession**, và chỉ dữ liệu đã qua validation cùng policy mapping mới được dùng để nhận diện hoặc cấp quyền.
