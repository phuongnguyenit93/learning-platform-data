# Chuyển thuộc tính hoặc nhóm SAML thành GrantedAuthority có kiểm soát

Khi ứng dụng Spring Security sử dụng SAML 2.0 federation, **Identity Provider (IdP/Asserting Party)** thường cung cấp các thuộc tính của người dùng trong `AttributeStatement`: mã nhân viên, email, phòng ban, nhóm, chức danh hoặc thông tin tenant. Ứng dụng **Service Provider (SP/Relying Party)** có thể dùng một số thuộc tính đó làm **đầu vào** cho việc tính quyền truy cập. Tuy nhiên, ứng dụng **không được chuyển nguyên xi mọi giá trị nhóm nhận được thành `GrantedAuthority`**, nhất là các quyền mạnh như `ROLE_ADMIN` hay quyền truy cập dữ liệu của tenant khác.

**Nguyên tắc chính:** Chỉ ánh xạ các thuộc tính được xác minh từ **đúng IdP và đúng registration**, qua một **chính sách allowlist do SP kiểm soát**, kết hợp người dùng/tenant/tài nguyên và nguyên tắc **least privilege**. Nếu nhóm lạ, thuộc tính thiếu, IDP không được phép cấp quyền đó hoặc thông tin mâu thuẫn, mặc định **không cấp thêm quyền**. Đăng nhập thành công không có nghĩa được phép thực hiện mọi chức năng.

Đây là bài Knowledge thuộc **Spring Security – federation → Danh tính và quyền**. Nội dung gồm mô hình tin cậy, thiết kế mapping, API Spring Security, ví dụ Java 17 chạy độc lập, gợi ý tích hợp vào SAML response converter, session/thu hồi quyền, kiểm thử và xử lý lỗi.

## 1. Authentication và authorization khác nhau ở đâu?

**Authentication** trả lời: *Ai là người vừa đăng nhập, IdP nào đã xác thực họ và bằng chứng có hợp lệ không?* **Authorization** trả lời: *Người đó được thực hiện hành động nào đối với tài nguyên nào, ở tenant nào và theo điều kiện nào?*

~~~text
Người dùng ----> IdP xác thực ----> SAMLResponse
                                          |
                                     Spring Security
                               xác minh XML signature,
                                Issuer/Audience/Time,
                               Recipient/InResponseTo
                                          |
                                          v
                              Saml2Authentication
                              + principal / attributes
                                          |
                              Policy mapping của SP
                     IdP + registration + tenant + allowlist
                                          |
                                          v
                          Collection<GrantedAuthority>
                                          |
                          AuthorizationFilter / @PreAuthorize
                                          |
                                kiểm tra tài nguyên
~~~

| Khái niệm | Nguồn | Ý nghĩa |
| --- | --- | --- |
| `SAML Assertion` hợp lệ | IdP đáng tin, SP kiểm tra | Bằng chứng xác thực/thuộc tính theo ngữ cảnh |
| `Saml2AuthenticatedPrincipal` | Spring Security sau xác thực | Principal, NameID, danh sách thuộc tính đã đọc |
| `GrantedAuthority` | SP xây từ chính sách hoặc hệ thống quyền | Một quyền mà Spring Security có thể kiểm tra |
| `ROLE_REVIEWER`, `ROLE_ADMIN` | Namespace quyền của ứng dụng | Tên role nội bộ, không mặc định là giá trị nhóm IdP |
| `hasAuthority` / `hasRole` | Expression authorization | Cách yêu cầu quyền để bảo vệ endpoint/method |
| ACL, ABAC, ownership và tenant policy | Nghiệp vụ của SP | Ràng buộc quyền với đối tượng cụ thể |

Ví dụ: IdP xác thực người dùng An và gửi nhóm `portal-reviewers`. SP chỉ ánh xạ nhóm này thành `ROLE_APPROVER` **nếu policy cho IdP/tenant đó được cấp quyền duyệt**, và khi duyệt hóa đơn vẫn kiểm tra **hóa đơn thuộc tenant nào, trạng thái nào và An có được phân công không**.

**Sai:** tin rằng chữ ký IdP hợp lệ thì mọi nhóm do IdP công bố đều có thể biến thành quyền quản trị ứng dụng. **Đúng:** tin danh tính đã xác minh trong phạm vi IdP rồi áp dụng quy tắc phân quyền thuộc sở hữu SP.

## 2. Thuộc tính SAML đến từ đâu và hình dạng ra sao?

Một assertion có thể chứa nhiều `AttributeStatement`, mỗi statement chứa một hoặc nhiều `Attribute`; một thuộc tính có thể có nhiều `AttributeValue`.

~~~xml
<saml:AttributeStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Attribute Name="urn:example:claims:groups"
                  NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
                  FriendlyName="groups">
    <saml:AttributeValue>portal-readers</saml:AttributeValue>
    <saml:AttributeValue>portal-reviewers</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="urn:example:claims:department">
    <saml:AttributeValue>finance</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
~~~

Đây là **mảnh XML minh họa** để giải thích cấu trúc, không phải một SAML Assertion/Response có chữ ký và điều kiện hợp lệ. URI `urn:example:claims:groups` là **tên thuộc tính theo ví dụ**, không phải tên bắt buộc của chuẩn SAML.

Các điểm cần kiểm tra khi thống nhất tích hợp với IdP:

1. **`Attribute.Name`** là định danh của thuộc tính; một số IdP dùng URI/OID, một số dùng chuỗi như `groups` hoặc `memberOf`.
2. **`NameFormat`** có thể chỉ ra kiểu đặt tên. Không tự coi hai Attribute có cùng FriendlyName nhưng Name/NameFormat khác nhau là đồng nhất.
3. **`FriendlyName`** chủ yếu phục vụ đọc hiểu; đừng chọn nó làm khóa bảo mật nếu hợp đồng tích hợp yêu cầu Name/OID.
4. **`AttributeValue`** có thể xuất hiện nhiều lần, không phải luôn một chuỗi; một số nhà cung cấp trả các giá trị có kiểu phức tạp.
5. **Giá trị nhóm** có thể là tên hiển thị, mã nội bộ, OID, GUID hoặc LDAP DN như `CN=PortalReaders,OU=Groups,DC=example,DC=test`.
6. Một số IdP có giới hạn kích thước assertion hoặc số group được trả; nhóm bị lược bỏ sẽ gây sai khác quyền nếu ứng dụng giả định always-complete.
7. `AttributeStatement` thuộc assertion; nó chỉ đáng tin sau khi Spring Security/OpenSAML đã xác minh thông điệp SAML và đúng registration.

**Khuyến nghị:** dùng **định danh group ổn định** do IdP cung cấp, có hợp đồng ý nghĩa rõ ràng, thay vì chuỗi mô tả hiển thị dễ đổi tên hoặc trùng nhau.

## 3. Đọc thuộc tính trong Spring Security

Với Spring Security SAML2 Login, sau khi SAMLResponse được xác minh, Spring có thể tạo `Saml2Authentication`. Ở các nhánh dùng `Saml2AuthenticatedPrincipal`, principal chứa tên và attribute map.

Ví dụ đọc thuộc tính trong controller (mảnh code trong **dự án Spring**, không phải Java standalone):

~~~java
import java.util.List;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/profile/groups")
    public List<Object> groups(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        List<Object> groups =
                principal.getAttribute("urn:example:claims:groups");
        return groups != null ? groups : List.of();
    }
}
~~~

**Đây chỉ là ví dụ cách truy cập API**, không khuyến khích công khai endpoint trả group claims trong production. API `getAttribute(name)` trả **danh sách** giá trị; `getFirstAttribute(name)` lấy giá trị đầu tiên khi biết thuộc tính chỉ có một giá trị. Khi chính sách cần tất cả nhóm, **không chỉ lấy giá trị đầu tiên**.

Lưu ý tương thích phiên bản: Spring Security 6.x thường dùng `Saml2AuthenticatedPrincipal`; các nhánh 7.x bổ sung cách truy cập assertion qua `Saml2ResponseAssertionAccessor` và thay đổi mô hình authentication mặc định. Kiểm tra Javadoc/source code **đúng version** để lấy attributes ở vị trí phù hợp; đừng buộc mọi triển khai phải ép kiểu principal thành `Saml2AuthenticatedPrincipal` khi đã nâng lên API mới.

**Không ánh xạ quyền ngay trong controller ví dụ trên.** Việc tính `GrantedAuthority` nên đặt tập trung ở bước tạo Authentication hoặc ở authorization service, không để mỗi controller diễn giải group một cách khác nhau.

## 4. GrantedAuthority, hasAuthority và hasRole

Trong Spring Security:

- **`GrantedAuthority`** là interface mô tả một thẩm quyền; `getAuthority()` thường trả chuỗi.
- **`SimpleGrantedAuthority`** là implementation phổ biến cho quyền dạng string.
- **`hasAuthority("document:approve")`** đối chiếu authority chính xác.
- **`hasRole("ADMIN")`** theo mặc định tìm authority **`ROLE_ADMIN`** do tiền tố `ROLE_` được áp dụng. Cơ chế role prefix có thể được tùy chỉnh trong dự án, nên phải kiểm tra cấu hình thực tế.
- **`@PreAuthorize`** hoặc AuthorizationManager cho phép bảo vệ method/endpoint với quyền và điều kiện nghiệp vụ.

Ví dụ dùng cùng một quyền theo hai cách:

~~~java
@PreAuthorize("hasAuthority('ROLE_APPROVER')")
public void approveUsingAuthority(long paymentId) { /* service logic */ }

@PreAuthorize("hasRole('APPROVER')")
public void approveUsingRole(long paymentId) { /* service logic */ }
~~~

Mẫu trên là **hai method minh họa trong service có method security bật**, không phải source độc lập. Với prefix mặc định, hai biểu thức tương đương về điều kiện role. Cả hai **chưa kiểm tra ownership/tenant** của `paymentId`; production cần kết hợp authorization service hoặc domain policy.

**Tuyệt đối không làm:** `new SimpleGrantedAuthority(groupValue)` cho mọi `groupValue` do IdP phát, đặc biệt khi IdP có thể trả `ROLE_ADMIN`, `*:* ` hoặc tên quyền nội bộ do người dùng tự chọn.

## 5. Threat model: những con đường leo thang quyền

| Rủi ro | Ví dụ | Biện pháp kiểm soát |
| --- | --- | --- |
| **Group-name collision** | Hai IdP đều phát nhóm `admins` nhưng chỉ A được phép cấp quyền quản trị | Map theo IdP/registration và tenant, không theo string toàn cục |
| **Role injection** | Một group bất ngờ có tên `ROLE_ADMIN` | Exact allowlist, không cho nhóm tự quyết định tên authority |
| **Tenant confusion** | IdP A phát nhóm `finance` nhưng session đang ở tenant B | Kiểm tra tenant membership nội bộ và ràng buộc registration |
| **Ambiguous mapping** | `Finance`, `finance`, `CN=finance,...` được hiểu như nhau dù là nhóm khác | Dùng định danh đã thỏa thuận, chuẩn hóa có kiểm soát |
| **Attribute type confusion** | `AttributeValue` là XML object nhưng code ép sang String | Chỉ nhận kiểu dữ liệu đã định nghĩa, từ chối các giá trị lạ |
| **Overprivileged group** | IdP có nhóm `all-employees` bị map thành `ROLE_ADMIN` | Nguyên tắc least privilege, review mapping |
| **Stale group** | Người dùng bị xóa khỏi nhóm nhưng SP session vẫn giữ quyền cũ | Giới hạn phiên, reauth, refresh hoặc tra cứu quyền mỗi request nhạy cảm |
| **Account linking error** | Ghép người dùng chỉ theo email dễ thay đổi | Dùng subject ổn định + issuer + tenant mapping được xác minh |
| **Dynamic tenant URL** | `?tenant=finance` từ browser quyết định map role | Tenant phải được kiểm tra ở server, không chỉ từ query |
| **Upstream IdP transitivity** | A ký attribute được đưa từ IdP phụ không nằm trong hợp đồng | Thẩm định nguồn thuộc tính/assurance và chính sách federation |
| **Mapping drift** | Group bị IdP đổi tên nhưng app vẫn map vào quyền khác | Quản lý policy có phiên bản, test và audit |

Điểm then chốt: SAML signature chứng minh IdP được tin đã phát một thông điệp, **không chứng minh mọi giá trị nhóm luôn phù hợp để cấp đặc quyền trong ứng dụng**.

## 6. Thiết kế mapping bằng allowlist

Mỗi bản ghi chính sách nên có ít nhất các phần:

| Thành phần | Ví dụ | Kiểm soát |
| --- | --- | --- |
| Registration/IdP | `corp` | Đúng RelyingPartyRegistration đã được xác minh |
| Tenant | `north` | Membership/tenant selection được SP kiểm chứng |
| Attribute name | `urn:example:claims:groups` | Đúng hợp đồng thuộc tính |
| Attribute value | `portal-reviewers` | Exact match với mã group đã phê duyệt |
| Authority đích | `ROLE_APPROVER` | Do ứng dụng định nghĩa |
| Conditions | Tài khoản đang hoạt động, điều kiện MFA/freshness nếu cần | Kiểm tra bảo mật bổ sung |
| Owner của mapping | Nhóm quản trị quyền ứng dụng | Có review, audit và rollback |

Ví dụ bảng quyết định:

| IdP / tenant | Group đầu vào | Authority được cấp |
| --- | --- | --- |
| `corp / north` | `portal-readers` | `ROLE_VIEWER` |
| `corp / north` | `portal-reviewers` | `ROLE_APPROVER` |
| `partner / north` | `partner-viewers` | `ROLE_VIEWER` |
| `corp / south` | `portal-reviewers` | **Không cấp**, chưa có policy |
| `partner / north` | `portal-reviewers` | **Không cấp**, khác IdP |
| Bất kỳ | `ROLE_ADMIN` | **Không cấp**, không có mapping cho giá trị đó |

Một nhóm không nên tự mang theo tên `ROLE_...` mà được phép chèn nguyên xi vào authorities. Mọi quyền phải xuất phát từ **mapping table do SP quản lý**.

### Xử lý dữ liệu đầu vào

- Nếu attribute không tồn tại: thường trả **tập quyền bổ sung rỗng**, hoặc **từ chối đăng nhập** khi hợp đồng yêu cầu phải có nhóm mới được sử dụng SP.
- Nếu attribute chứa nhiều giá trị: duyệt **tất cả**, loại bỏ trùng lặp, chỉ cấp những quyền có exact policy.
- Nếu có một giá trị null, kiểu không phải string hoặc chuỗi dài bất thường: bỏ qua hoặc fail theo policy; không tự `toString()` trên XML object lạ để match quyền.
- Nếu có nhóm vừa `allow` vừa `deny`: định nghĩa cơ chế ưu tiên rõ ràng; quyền nhạy cảm nên ưu tiên **deny** khi thông tin mâu thuẫn.
- Nếu tenant không được định danh chắc chắn: không cấp quyền tenant-specific.
- Nếu policy lookup/database lỗi: **fail closed** cho quyền nhạy cảm, không mặc định thành admin hay đọc mọi dữ liệu.
- Nếu một IdP phát group chung dùng trong nhiều ứng dụng: bảo đảm group được cấp nghĩa dành riêng cho SP này, không tự liên hệ group phổ thông với quyền đặc biệt.

## 7. Java 17 độc lập: ánh xạ theo IdP + tenant + allowlist

Để tách **logic nghiệp vụ** khỏi version OpenSAML/Spring Security, ví dụ sau dùng **Java 17+ thuần JDK**. Nó nhận registration và tenant **đã được hệ thống phía server xác minh**, cùng danh sách group **được lấy từ assertion đã được xác thực**, rồi trả tập authority được phép.

Tạo tệp **SafeSamlAuthorityMappingDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class SafeSamlAuthorityMappingDemo {

    record Scope(String registrationId, String tenantId) {}

    private static final Map<Scope, Map<String, String>> POLICY = Map.of(
        new Scope("corp", "north"), Map.of(
            "portal-readers", "ROLE_VIEWER",
            "portal-reviewers", "ROLE_APPROVER"
        ),
        new Scope("partner", "north"), Map.of(
            "partner-viewers", "ROLE_VIEWER"
        )
    );

    static Set<String> mapAuthorities(String registrationId,
                                      String trustedTenant,
                                      List<String> groups) {
        Map<String, String> allowed =
                POLICY.get(new Scope(registrationId, trustedTenant));

        if (allowed == null || groups == null) {
            return Set.of();
        }

        Set<String> result = new TreeSet<>();

        for (String group : groups) {
            if (group == null) {
                continue;
            }
            String authority = allowed.get(group);
            if (authority != null) {
                result.add(authority);
            }
        }

        return result;
    }

    public static void main(String[] args) {
        System.out.println(mapAuthorities(
            "corp", "north",
            List.of("portal-readers", "portal-reviewers", "ROLE_ADMIN")
        ));
        System.out.println(mapAuthorities(
            "partner", "north", List.of("portal-reviewers")
        ));
        System.out.println(mapAuthorities(
            "corp", "south", List.of("portal-readers")
        ));
        System.out.println(mapAuthorities(
            "partner", "north", List.of("partner-viewers")
        ));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SafeSamlAuthorityMappingDemo.java
java SafeSamlAuthorityMappingDemo
~~~

**Stdout chính xác:**

~~~text
[ROLE_APPROVER, ROLE_VIEWER]
[]
[]
[ROLE_VIEWER]
~~~

**Giải thích:**

1. Với `corp/north`, hai nhóm đã có trong allowlist tạo `ROLE_APPROVER` và `ROLE_VIEWER`. Giá trị lạ `ROLE_ADMIN` **không tự cấp quyền quản trị**.
2. `partner/north` không có quyền diễn giải `portal-reviewers` của `corp`, nên không cấp gì.
3. `corp/south` không có chính sách nên không được dùng nhầm quyền của `corp/north`.
4. Nhóm `partner-viewers` thuộc `partner/north` được map thành `ROLE_VIEWER`.

`TreeSet` tạo thứ tự chuỗi ổn định để output dễ kiểm tra; thứ tự không phải ưu tiên quyền. `Map.of` và `record` đều hỗ trợ Java 17. Policy trong ví dụ là **cấu hình mẫu**, không bao gồm xác minh SAML, kiểm tra tenant membership, phân quyền đối tượng, thu hồi quyền hoặc bảo đảm MFA. Trong production phải triển khai các bước đó tách biệt.

**Không bao giờ lấy `trustedTenant` trực tiếp từ query string không kiểm tra** rồi truyền vào hàm. Tenant phải được xác định qua session/subject mapping/quyền membership đáng tin ở server.

## 8. Đưa policy thành SimpleGrantedAuthority trong Spring Security

Sau khi một SAML Response đã qua xác minh, ứng dụng có thể chuyển tập authority nội bộ thành `SimpleGrantedAuthority`:

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Đoạn này nằm trong service/converter sau khi xác thực SAML thành công.
// policy là kết quả lookup do SP quản lý, không phải Map nhận từ client.
Set<String> permittedRoles = Set.of("ROLE_VIEWER", "ROLE_APPROVER");

List<GrantedAuthority> authorities = permittedRoles.stream()
    .map(SimpleGrantedAuthority::new)
    .collect(Collectors.toList());
~~~

Đây là **mảnh code sử dụng biến `permittedRoles` đã được policy kiểm tra**, không phải class độc lập. Đặt `new SimpleGrantedAuthority(value)` trong code map không có nghĩa tự cho phép mọi chuỗi đầu vào; điều quan trọng là `value` **phải thuộc tập role do ứng dụng quyết định**, không phải chuỗi group thô.

### Tổ chức thành service có thể unit test

Thiết kế một `SamlAuthorityMappingService` chuyên trách:

~~~text
Input:
  verified registrationId
  verified SAML AttributeStatement / principal
  trusted application account + tenant membership
  current policy version / allowlist

Mapping service:
  validate attribute key and data types
  normalize only by explicit contract
  match exact issuer+registration+tenant+group
  deduplicate
  apply deny constraints and least privilege

Output:
  Collection<GrantedAuthority>
  + source and policy version for audit
~~~

**Cơ sở dữ liệu và ứng dụng là nguồn quyết định cuối** khi quyền mang ý nghĩa nghiệp vụ: IdP có thể nói “người này thuộc group X”, còn SP quyết định “group X được duyệt hóa đơn nào trong tenant nào”. Với quyền cấp cao, có thể yêu cầu phê duyệt nội bộ hoặc quyền cấp từ database thay vì chỉ dựa vào group SAML.

## 9. Cắm mapping vào luồng SAML Response authentication

Spring Security cho phép tùy chỉnh **response-to-authentication conversion** trong provider OpenSAML. Vị trí được khuyến nghị là **sau khi thư viện đã xác minh Response/Assertion**, tận dụng default converter để đọc principal/attributes, rồi thay/bổ sung authorities theo policy.

~~~text
Saml2WebSsoAuthenticationFilter
                |
                v
         Saml2AuthenticationToken
                |
                v
    OpenSAML AuthenticationProvider
       signature + issuer + destination
       assertions + time + audience
                |
          Default converter
                |
      Principal + SAML attributes
                |
       Mapping service của SP
                |
   Saml2Authentication / Authentication
      with controlled authorities
                |
        SecurityContextHolder
~~~

### Spring Security 6.x: converter của OpenSAML provider

Ở những phiên bản Spring Security 6.x dùng `OpenSaml4AuthenticationProvider`, mẫu tích hợp thường là:

~~~java
OpenSaml4AuthenticationProvider provider =
        new OpenSaml4AuthenticationProvider();

Converter<OpenSaml4AuthenticationProvider.ResponseToken,
          Saml2Authentication> defaults =
        OpenSaml4AuthenticationProvider
            .createDefaultResponseAuthenticationConverter();

provider.setResponseAuthenticationConverter(responseToken -> {
    Saml2Authentication verified = defaults.convert(responseToken);

    Saml2AuthenticatedPrincipal principal =
            (Saml2AuthenticatedPrincipal) verified.getPrincipal();

    // Ở đây gọi service của ứng dụng với principal, registrationId,
    // account/tenant đã được server xác minh.
    Collection<GrantedAuthority> mapped =
            mappingService.mapVerifiedSamlPrincipal(principal);

    return new Saml2Authentication(
            principal, verified.getSaml2Response(), mapped);
});
~~~

**Đây là code minh họa điểm tích hợp**, không phải class Java độc lập; biến `mappingService` là service thực do ứng dụng xây. Cần import các lớp Spring Security thích hợp, đặt bean provider trong cấu hình SAML và nối với authentication manager của `saml2Login`, kiểm tra **đúng phiên bản Spring Security/OpenSAML** trước khi dùng. Trong một số bản 6.x có provider OpenSAML 5, tên class và converter khác.

**Điểm an toàn bắt buộc:** gọi converter mặc định và giữ validator mặc định để tránh tự làm mất xác minh chữ ký, issuer, audience, time và subject confirmation. Nếu mapping service không chạy được, không thay `mapped` bằng `ROLE_ADMIN` hoặc authorities tùy ý. Bản thân lời gọi mapping từ đoạn code phải được thiết kế để chỉ thấy **thông tin đã xác thực**, không phải raw XML từ HTTP request.

### Spring Security 7.x: khác biệt API

Spring Security 7.x định hướng `OpenSaml5AuthenticationProvider` và `ResponseAuthenticationConverter`, đồng thời tách một phần thông tin assertion khỏi principal với **`Saml2ResponseAssertionAccessor`**; những chi tiết liên quan tới `Saml2AuthenticatedPrincipal` được điều chỉnh trong migration.

Cách tiếp cận an toàn:

1. Dùng **provider OpenSAML 5** cùng version và response converter tương ứng.
2. Bắt đầu từ **converter mặc định**; không thay validator bằng một parser tự viết.
3. Từ dữ liệu assertions/attributes đã xác minh, gọi **mapping policy service**.
4. Tạo Authentication có authorities đã thẩm định theo API đúng version (ví dụ dạng `Saml2AssertionAuthentication` hoặc class được khuyến nghị ở nhánh đó).
5. Gắn provider vào `saml2Login(authenticationManager(...))` hoặc cấu hình tương đương của release đã chọn.
6. Compile/test bằng đúng Spring Boot/Security BOM đang dùng.

**Không dùng mảnh code OpenSaml4 của mục trước như mã copy-paste cho Spring Security 7.** API và cách lưu trữ assertion có thay đổi; kiểm tra tài liệu migration chính thức trước khi nâng cấp.

## 10. Có nên giữ các authorities mặc định?

Tùy nhánh và provider, Spring Security có thể cấp authority cơ sở như `ROLE_USER`, và các bản mới có thể thể hiện yếu tố xác thực qua authority riêng. Khi thay thế tập authorities bằng mapping tùy chỉnh, cần **quyết định rõ** có giữ hay loại các authorities cơ sở.

Hai chiến lược:

- **Replace:** chỉ giữ các quyền có trong allowlist SP. Ưu điểm: ít quyền ngoài ý muốn; nhược điểm: ứng dụng có thể cần authority cơ sở để bảo vệ trang thông thường.
- **Controlled merge:** giữ một tập authority nền tảng **được phê duyệt** sau SAML login, rồi cộng thêm các authority từ mapping. Không sao chép vô điều kiện mọi authority đã có nếu policy đang cố hạn chế quyền.

**Không coi `ROLE_USER` là `ROLE_APPROVER`.** Quyền đăng nhập vào Portal chỉ chứng minh người dùng là một subject hợp lệ; các thao tác đặc quyền phải được cấp riêng và kiểm tra theo đối tượng.

Một nguyên tắc thực tế: **default-deny quyền nhạy cảm**. Nếu không thể xác định nhóm/tenant/policy, có thể vẫn cho xem landing page với quyền tối thiểu theo chính sách tổ chức, nhưng không được approve, export dữ liệu hoặc quản trị.

## 11. Không nhầm SAML groups với OAuth2 scopes/JWT authorities

SAML Federation và OAuth2 Resource Server có thể cùng tồn tại trong một hệ thống, nhưng cơ chế ánh xạ là khác nhau:

| Nguồn | Dữ liệu đầu vào | Công cụ điển hình |
| --- | --- | --- |
| SAML2 Login | `AttributeStatement` từ SAML Assertion | Response authentication converter / policy mapping |
| OAuth2/JWT Resource Server | JWT claims như `scope`, `scp`, `roles` | `JwtAuthenticationConverter` |
| OIDC Login | ID token/UserInfo claims | OIDC/OAuth2 user authority mapper theo version |
| LDAP login | LDAP group membership | LDAP authorities mapper |
| Database nội bộ | Tenant roles/entitlements | `UserDetailsService`, PermissionEvaluator hoặc domain authorization service |

**Không sử dụng `JwtGrantedAuthoritiesConverter` để xử lý SAML XML.** Nó dành cho JWT, không phải SAML Assertion. Nếu một backend vừa có web SAML login vừa có API JWT, nên có chính sách quyền nghiệp vụ chung nhưng **adapter/validation khác nhau cho từng loại token**.

Một nhóm `finance` của IdP A không tự tương đương scope OAuth `finance.read` hoặc `ROLE_FINANCE_ADMIN`. Mọi phép chuyển đổi phải có owner và hợp đồng quyền rõ.

## 12. Tenant, account linking và identity lifecycle

SAML principal thường có **NameID** và thuộc tính email. Chúng phục vụ nhận diện, nhưng không mặc nhiên là khóa duy nhất bất biến cho mọi đối tác.

Với multi-tenant:

1. Xác thực **registration/IdP issuer** trước.
2. Xác định account nội bộ dựa trên **issuer + subject identifier ổn định** đã thống nhất; email có thể đổi, tái sử dụng hoặc không được IdP xác minh theo policy.
3. Lấy danh sách tenant mà account được phép tham gia từ kho nội bộ hoặc một nguồn được phê duyệt.
4. Nếu browser chọn tenant hiện tại, so nó với membership; không nhận tenant chỉ qua query/header.
5. Map group sang authorities **trong scope của tenant đó**.
6. Khi truy cập đối tượng, xác minh object thuộc tenant hiện tại và có quyền phù hợp.

**Tình huống:** cùng một tài khoản có vai trò `ROLE_VIEWER` ở tenant X và `ROLE_APPROVER` ở tenant Y. Nếu lưu tập authorities chung trong session mà không gắn tenant, `hasRole('APPROVER')` đơn thuần có thể vô tình cấp quyền ở X. Khắc phục bằng **tenant-scoped authority** (ví dụ permission chứa tenant) hoặc **domain-level authorization check** mỗi thao tác có tenant/object ID.

Có thể lưu role như `tenant:Y:payment:approve`, nhưng tên/format quyền phải được kiến trúc ứng dụng quy định; không nối trực tiếp một chuỗi tenant do client cung cấp vào `SimpleGrantedAuthority` rồi mặc định tin.

## 13. Khi IdP đổi group, session của SP có đổi quyền ngay không?

Thông thường, authorities được tạo lúc SAML login thành công và nằm trong `Authentication`/SecurityContext của **SP session**. Nếu quản trị viên IdP xóa người dùng khỏi group giữa phiên, authorities trong SP **không tự được thu hồi tức thì** chỉ vì group ở IdP đổi.

Cần xác định **thời gian sống của quyền**:

- **Session timeout:** giới hạn thời gian session SP được tái sử dụng.
- **Reauthentication/step-up:** bắt buộc xác thực mới trước thao tác nhạy cảm, kiểm tra lại AuthnInstant và AuthnContext.
- **Server-side entitlements:** kiểm tra quyền hiện hành trong database/authorization service mỗi yêu cầu quan trọng.
- **Revocation events:** đồng bộ thu hồi quyền qua SCIM, event bus, back-channel hoặc cơ chế riêng đã được thiết kế; SAML login đơn thuần không cung cấp tính năng quyền realtime.
- **Periodic refresh:** cập nhật quyền theo policy và TTL nếu phù hợp, không tin vào thông tin SAML cũ vô thời hạn.

Ví dụ: nhân viên nghỉ việc lúc 11:00, nhưng session được tạo từ 09:00 còn hạn tới 17:00. Nếu ứng dụng chỉ kiểm tra authority snapshot từ SAML mà không có revocation strategy, nhân viên có thể tiếp tục thao tác. Với quyền nhạy cảm, cần xử lý lifecycle thu hồi, không chỉ cập nhật nhóm tại IdP.

**Lưu ý:** SAML Single Logout là giao thức phiên, không tự thay thế việc cập nhật mọi role/permission trong tất cả ứng dụng. Nếu SLO thất bại hoặc không được triển khai, session SP có thể tồn tại theo policy riêng.

## 14. Nhóm thiếu, nhóm lạ hoặc dữ liệu bất thường: xử lý ra sao?

| Input sau xác minh | Hành vi gợi ý |
| --- | --- |
| `groups` không có | Không cấp thêm role, trừ khi policy bắt buộc attribute thì từ chối đăng nhập |
| `groups=[]` | Không cấp thêm role |
| `groups=[portal-readers]` với đúng corp/north | Cấp `ROLE_VIEWER` |
| `groups=[ROLE_ADMIN]` không nằm trong allowlist | Bỏ qua, audit mức phù hợp |
| `groups=[portal-readers,portal-readers]` | Khử trùng lặp, chỉ cấp một authority |
| `groups` có Object không mong đợi | Không ép kiểu mù; từ chối/bỏ qua theo policy |
| Group dài bất thường hoặc số lượng quá lớn | Áp giới hạn và quy tắc bảo vệ DoS, xử lý có kiểm soát |
| Attribute name/OID không trùng hợp đồng | Không giả định đồng nghĩa với trường khác |
| User thuộc tenant khác | Không cấp role tenant hiện tại |
| Policy database timeout | Không cấp quyền nhạy cảm; trả lỗi có kiểm soát hoặc quyền tối thiểu theo policy |
| Group có khác biệt chữ hoa/thường | Exact match trừ khi hai bên đã thống nhất cách chuẩn hóa |
| IdP gửi một nhóm mới sau khi đổi tên | Chưa cấp quyền cho tới khi mapping được phê duyệt và triển khai |

Một nhóm không được ánh xạ không nhất thiết là lỗi xác thực SAML; nó có thể khiến user **đăng nhập được nhưng nhận 403** khi truy cập vùng cần role. Điều này đúng với nguyên tắc phân tách authentication và authorization.

**Đừng chọn “người dùng thiếu nhóm → cấp ROLE_USER và ROLE_ADMIN tạm thời để không bị 403”.** Nếu hệ thống cần quyền cơ sở để sử dụng trang chung, định nghĩa rõ quyền đó theo policy và giữ quyền nhạy cảm deny.

## 15. Unit test và integration test cần có

### Unit test của mapping service

| Case | Dữ liệu | Kết quả kỳ vọng |
| --- | --- | --- |
| Đúng group và đúng scope | corp/north, portal-reviewers | `ROLE_APPROVER` |
| Hai group hợp lệ | corp/north, readers + reviewers | Viewer + Approver |
| Role injection | corp/north, ROLE_ADMIN | Không cấp Admin |
| IdP khác | partner/north, portal-reviewers | Không cấp quyền corp |
| Tenant khác | corp/south, portal-reviewers | Không cấp quyền north |
| Dữ liệu rỗng | groups null/empty | Không thêm quyền |
| Giá trị trùng | readers lặp hai lần | Chỉ một Viewer |
| Thuộc tính sai tên | `groupsX` thay `urn:example:claims:groups` | Không tự diễn giải |
| Unsupported type | XML object thay String | Không cấp quyền từ kiểu lạ |
| Database fail | Không lấy được tenant membership | Fail closed cho quyền mạnh |
| Change policy | Group bị xóa khỏi allowlist | Role tương ứng không còn được cấp trong lần tính mới |

### Integration test với Spring Security và IdP thử nghiệm

1. Tạo SAML Response có chữ ký hợp lệ của đúng IdP; sau xác thực, kiểm tra `Authentication.getAuthorities()`.
2. Thử Response ký từ IdP B nhưng nhằm dùng policy của A; phải bị từ chối ở bước protocol trust hoặc không được map role A.
3. Thử thuộc tính có nhiều AttributeValue và tên URI/OID thực tế; kiểm tra mapper xử lý tất cả đúng cách.
4. Kiểm tra `hasRole`/ `hasAuthority`, method security và quyền đối với domain object.
5. Thử session còn hạn sau khi nhóm bị thu hồi; xác minh cơ chế revocation hoặc domain authorization đang được dùng.
6. Thử IdP metadata/key rotation; không được mất ranh giới issuer/registration.
7. Thử multi-tenant với cùng user có quyền khác nhau giữa hai tenant.
8. Thử dữ liệu thiếu/hỏng, mapping database timeout và thuộc tính quá lớn; không cấp đặc quyền khi lỗi.
9. Thử nâng Spring Security 6.x → 7.x; xác minh converter, principal accessor và authorities sau migration.
10. Kiểm tra log không lộ danh sách nhóm nhạy cảm hoặc toàn bộ assertion.

**Chỉ mock policy mapper là chưa đủ:** cần một số integration tests với SAML Response/IdP thật để chứng minh thuộc tính được giải mã, xác minh và ánh xạ đúng.

## 16. Chẩn đoán lỗi ROLE_ và lỗi 403

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| SAML login thành công nhưng mọi API trả 403 | Không có authority được map, hoặc thiếu quyền nghiệp vụ | Kiểm tra chính sách allowlist, log dạng đã làm sạch |
| `hasRole('ADMIN')` không nhận `ADMIN` | Mặc định cần `ROLE_ADMIN` | Dùng tên quyền/prefix nhất quán |
| IdP gửi nhiều nhóm nhưng chỉ có một quyền | Code dùng `getFirstAttribute` thay danh sách | Duyệt tất cả AttributeValue hợp lệ |
| Thay IdP mà quyền vẫn giữ nguyên | Mapping không scope theo registration | Tách policy theo issuer/registration |
| User nhóm readers được cấp reviewer | Mapping sai hoặc chuẩn hóa chuỗi quá rộng | Đối chiếu exact group IDs và policy owner |
| User tenant Y duyệt tài liệu của tenant X | Chỉ dùng role toàn cục, không kiểm tra resource tenant | Áp dụng authorization ở service và tenant membership |
| Nhóm bị xóa tại IdP nhưng phiên vẫn còn quyền | Snapshot Authentication chưa được làm mới | Dùng session policy/revocation và quyền tại server |
| `Saml2AuthenticatedPrincipal` cast lỗi khi nâng version | Principal/authentication type thay đổi | Sử dụng accessor/converter đúng Spring Security version |
| Mất `ROLE_USER` sau tùy chỉnh | Converter thay toàn bộ authorities không giữ base role | Quy định chính sách merge/replace rõ ràng |
| Một giá trị nhóm bị diễn giải sai | IdP đổi Name/NameFormat hoặc value type | Kiểm tra hợp đồng thuộc tính, không dựa FriendlyName một mình |
| Role trở nên có quyền admin sau khi IdP phát chuỗi ROLE_ADMIN | Truyền raw string vào SimpleGrantedAuthority | Chỉ map sang role nội bộ qua allowlist |

**Ghi log tối thiểu:** registrationId đã xác minh, policy version, tên attribute, số giá trị hợp lệ/không hợp lệ, authorities được cấp và correlation ID; với dữ liệu nhạy cảm cân nhắc hash/ẩn group names. Không log SAMLResponse, NameID/email và danh sách entitlement nhạy cảm một cách bừa bãi.

## 17. Câu hỏi tự đánh giá

**Câu 1:** Vì sao không thể dùng `groups.stream().map(SimpleGrantedAuthority::new)` trên mọi nhóm SAML?  
Vì group labels do IdP cung cấp không tự tương đương quyền ứng dụng. Tên `ROLE_ADMIN` hoặc nhóm trùng giữa các IdP có thể gây cấp quyền ngoài ý muốn. Phải có allowlist theo scope.

**Câu 2:** IdP A và IdP B đều phát `admins`. Có ánh xạ toàn cục thành `ROLE_ADMIN` không?  
Không. Chỉ IdP/tenant được phê duyệt mới có quyền cấp authority tương ứng; phải xét registration và chính sách nội bộ.

**Câu 3:** Nếu có ba AttributeValue, gọi `getFirstAttribute` có đủ để xác định tất cả role không?  
Không. Phải xử lý toàn bộ danh sách giá trị đã được phép.

**Câu 4:** Group `portal-reviewers` đã được map `ROLE_APPROVER`; có thể bỏ kiểm tra đối tượng thanh toán không?  
Không. Role là điều kiện cấp cao; vẫn cần kiểm tra tenant, ownership, trạng thái nghiệp vụ và quyền trên đối tượng.

**Câu 5:** Người dùng mất nhóm trên IdP lúc 11 giờ thì authority trong session SP có biến mất ngay không?  
Không mặc nhiên. Cần timeout, refresh/relogin, revocation hoặc server-side authorization để cập nhật đúng hạn.

**Câu 6:** `hasRole('APPROVER')` và `hasAuthority('ROLE_APPROVER')` có thường tương đương không?  
Có khi dùng prefix mặc định `ROLE_`, nhưng cần xác nhận cấu hình của dự án.

**Câu 7:** Có thể dùng JWT converter để ánh xạ SAML groups không?  
Không trực tiếp. JWT và SAML có converter/validation riêng, mặc dù có thể dùng chung policy service.

**Câu 8:** Nếu thiếu group bắt buộc để cấp quyền nhạy cảm, hành vi an toàn là gì?  
Không cấp quyền đó; nếu yêu cầu đăng nhập phải có thuộc tính này thì từ chối có kiểm soát theo policy.

## 18. Checklist và kết luận

- [ ] Chỉ lấy thuộc tính từ **SAML Assertion đã được Spring Security/OpenSAML xác minh**.
- [ ] Ràng buộc đúng `registrationId`, IdP issuer, tenant và account mapping đáng tin.
- [ ] Xác định rõ Attribute.Name/NameFormat, kiểu giá trị và group IDs ổn định.
- [ ] Chỉ ánh xạ **nhóm có trong allowlist SP** thành **authority do SP định nghĩa**.
- [ ] Không biến chuỗi raw `ROLE_ADMIN` hoặc tên nhóm lạ thành đặc quyền.
- [ ] Xử lý nhiều AttributeValue, null, duplicate, type lạ và nhóm quá lớn.
- [ ] Fail closed khi policy/tenant membership thiếu hoặc lookup lỗi đối với quyền nhạy cảm.
- [ ] Quy định việc giữ `ROLE_USER` hoặc authority nền tảng khi thay response converter.
- [ ] Kiểm tra `hasAuthority`, `hasRole`, method security và object-level authorization.
- [ ] Thiết kế session TTL, key rotation, account lifecycle, revocation và refresh quyền.
- [ ] Với Spring Security 6.x/7.x, chọn đúng provider, converter và principal/assertion accessor.
- [ ] Có test role injection, cross-IdP, cross-tenant, attribute thiếu và stale group.
- [ ] Có owner phê duyệt policy mapping, versioning, audit và khả năng rollback.

**Kết luận:** Group/attribute SAML là **dữ kiện đầu vào đã được IdP khẳng định**, còn `GrantedAuthority` là **quyền mà ứng dụng lựa chọn cấp theo chính sách**. Khoảng cách giữa hai khái niệm phải được bảo vệ bằng đúng nguồn tin cậy, allowlist theo IdP/tenant, phân quyền tối thiểu và kiểm tra đối tượng. Đối với quyền nhạy cảm, không phụ thuộc hoàn toàn vào snapshot group trong SSO session; luôn cân nhắc revocation và authorization tại server.

### Tài liệu chính thức

- Spring Security — SAML 2.0 Login Overview (authentication, principal, attributes): https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Authenticating SAML Responses (response converter, authorities, extension points): https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — SAML 2.0 migration notes (thay đổi 6.x/7.x): https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- OASIS — SAML 2.0 Core, AttributeStatement: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS — SAML 2.0 Profiles, Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
