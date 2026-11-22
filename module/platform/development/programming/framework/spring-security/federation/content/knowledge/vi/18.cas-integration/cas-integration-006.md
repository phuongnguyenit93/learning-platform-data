# AuthenticationUserDetailsService và chuyển thuộc tính CAS thành quyền trong Spring Security

**Vấn đề:** Khi ứng dụng sử dụng Central Authentication Service (CAS) để đăng nhập một lần, CAS Server xác thực người dùng và có thể trả về **principal attributes** như mã nhân viên, phòng ban, nhóm hoặc affiliation trong phản hồi kiểm chứng Service Ticket. Tuy nhiên, ứng dụng Spring Security vẫn cần quyết định **người dùng nội bộ nào** đang đăng nhập và được cấp **GrantedAuthority** gì. **AuthenticationUserDetailsService** là một điểm tích hợp thích hợp để đưa kết quả xác thực CAS vào mô hình tài khoản và quyền của ứng dụng.

**Nguyên tắc cốt lõi:** Chỉ chuyển thuộc tính từ **CAS assertion đã được TicketValidator xác minh**, sau đó áp dụng **policy do ứng dụng quản lý** theo CAS context/service, tài khoản nội bộ và tenant. Không truyền thẳng mọi giá trị nhóm CAS thành ROLE_ADMIN hay quyền nghiệp vụ. **Đăng nhập thành công ở CAS không đồng nghĩa có quyền xem hoặc sửa mọi tài nguyên trong ứng dụng.**

Bài thuộc **Spring Security – federation → Tích hợp CAS**, trình bày sự khác biệt giữa UserDetailsService và AuthenticationUserDetailsService, dữ liệu Assertion, cách Spring Security CAS gọi service, lớp hỗ trợ dựng authorities, cách ánh xạ an toàn, ví dụ Java 17 chạy độc lập, integration code, xử lý lỗi, kiểm thử và vận hành.

## 1. Authentication và Authorization trong một ứng dụng dùng CAS

CAS giúp giải quyết authentication: người đang đăng nhập đã được CAS Server xác thực theo chính sách của CAS. Sau khi CAS Service Ticket (ST) được xác minh, Spring Security xây đối tượng Authentication; ứng dụng vẫn phải quyết định account status, roles, tenant membership và quyền truy cập tài nguyên.

~~~text
Browser -> SP Portal -> CAS /login
                         |
                    CAS xác thực
                         |
                   CAS cấp ST cho Portal
                         |
Browser -> Portal /login/cas?ticket=ST-...
                         |
                 CasAuthenticationFilter
                         |
                CasAuthenticationProvider
                         |
               TicketValidator gọi CAS
              /serviceValidate với service
                         |
                   CAS Assertion
                 principal + attributes
                         |
       AuthenticationUserDetailsService
         local account lookup + policy
                         |
           UserDetails + GrantedAuthority
                         |
          CasAuthenticationToken / SecurityContext
                         |
       AuthorizationFilter / @PreAuthorize
               + domain/tenant policy
~~~

Điểm ranh giới:

- **CAS Server:** xác minh credentials hoặc SSO session; phát ST đã gắn với một service.
- **TicketValidator:** xác minh ST với CAS Server qua HTTPS, đúng service và protocol.
- **CAS Assertion:** chứa principal đã được xác thực, có thể kèm attributes được release.
- **AuthenticationUserDetailsService:** tra cứu hồ sơ người dùng hoặc xây UserDetails dựa trên một Authentication token mang assertion.
- **Authorization:** quyết định sử dụng authorities cho endpoint/method/object; domain policy có thể cần thêm dữ liệu ở backend.

Không thực hiện mapping authorities bằng cách đọc query parameter ticket rồi đoán người dùng. ST là bearer credential ngắn hạn, one-time; phải được validate.

## 2. Các thành phần trong Spring Security CAS

| Thành phần | Vai trò |
| --- | --- |
| **CasAuthenticationEntryPoint** | Chuyển browser tới trang đăng nhập CAS và truyền service URL |
| **ServiceProperties** | Định nghĩa service callback của ứng dụng, ví dụ https://portal.example.test/login/cas |
| **CasAuthenticationFilter** | Nhận ST ở callback và chuyển cho AuthenticationManager |
| **CasAuthenticationProvider** | Gọi TicketValidator, xác minh ticket và dựng Authentication thành công |
| **TicketValidator** | Gọi CAS server validation endpoint; xác minh ST đúng service |
| **CasAssertionAuthenticationToken** | Token trung gian chứa Assertion đã được CAS provider xử lý, chuyển tới user details loader |
| **AuthenticationUserDetailsService<T>** | Tra cứu hoặc tạo UserDetails dựa trên Authentication token T |
| **UserDetailsService** | Tra cứu UserDetails theo một username string |
| **UserDetailsByNameServiceWrapper** | Adapter dùng username để gọi UserDetailsService |
| **GrantedAuthorityFromAssertionAttributesUserDetailsService** | Lớp có sẵn để biến giá trị của một số CAS attributes thành authorities |
| **GrantedAuthoritiesMapper** | Có thể chỉnh tập authorities trước khi lưu Authentication |
| **UserDetailsChecker** | Kiểm tra trạng thái UserDetails theo provider configuration |
| **SimpleGrantedAuthority** | Implementation thường dùng cho authority có tên dạng chuỗi |

Spring Security CAS dùng **module spring-security-cas** và Apereo CAS Client. Đây không phải phần tự động của saml2Login hoặc oauth2Login. CAS, SAML2 và OIDC đều có thể dùng chung khái niệm GrantedAuthority nhưng **cách xác minh thông điệp và đọc identity attributes hoàn toàn khác**.

## 3. AuthenticationUserDetailsService khác UserDetailsService thế nào?

**UserDetailsService** có hợp đồng:

~~~java
UserDetails loadUserByUsername(String username);
~~~

Nó phù hợp khi chỉ cần username để tra cứu local account/roles. **UserDetailsByNameServiceWrapper** có thể bọc UserDetailsService thành AuthenticationUserDetailsService để CAS provider gọi.

**AuthenticationUserDetailsService<T extends Authentication>** có hợp đồng:

~~~java
UserDetails loadUserDetails(T token);
~~~

Trong tích hợp CAS, kiểu token thường là **CasAssertionAuthenticationToken**; nó cho phép lấy **CAS Assertion** và attributes, không chỉ tên người dùng.

| Nhu cầu | Cách phù hợp |
| --- | --- |
| CAS chỉ phát username, local DB giữ quyền đầy đủ | UserDetailsService + UserDetailsByNameServiceWrapper |
| Cần đọc nhóm/phòng ban từ CAS assertion | AuthenticationUserDetailsService<CasAssertionAuthenticationToken> |
| Cần kiểm tra tenant, account status, mapping allowlist | Custom AuthenticationUserDetailsService hoặc policy service do ứng dụng kiểm soát |
| CAS đã phát chuỗi role đúng chuẩn và được quản trị tin cậy | Có thể cân nhắc GrantedAuthorityFromAssertionAttributesUserDetailsService sau khi thẩm định rủi ro |
| Cần mapping authorities toàn cục hậu xử lý | GrantedAuthoritiesMapper, nhưng không thay kiểm tra scope/nguồn thuộc tính |
| Cần entitlement mới nhất ở từng request | Domain authorization/database policy, không chỉ snapshot UserDetails lúc login |

**Không coi UserDetailsService là chỗ xác thực lại mật khẩu CAS.** CAS provider sử dụng TicketValidator để xác nhận ST. UserDetails trả về mô tả tài khoản và quyền; mật khẩu local không được dùng để xác minh ST.

## 4. CasAssertionAuthenticationToken và dữ liệu CAS Assertion

Sau khi CAS Server xác nhận Service Ticket, CAS client nhận một **org.apereo.cas.client.validation.Assertion**. Spring Security sử dụng **CasAssertionAuthenticationToken** làm object trung gian khi cần tải UserDetails.

Ví dụ cách đọc API **bên trong custom loader**:

~~~java
@Override
public UserDetails loadUserDetails(
        CasAssertionAuthenticationToken token) {
    org.apereo.cas.client.validation.Assertion assertion =
            token.getAssertion();

    String casSubject = assertion.getPrincipal().getName();
    Map<String, Object> attributes =
            assertion.getPrincipal().getAttributes();

    // Dùng casSubject + attributes trong policy service của SP.
    // Return UserDetails do ứng dụng xây từ local account.
}
~~~

Đây là **mảnh code**, chưa phải method có thể biên dịch độc lập; cần class implements interface, imports và return UserDetails. Không tự tạo **CasAssertionAuthenticationToken** từ HTTP query trong controller rồi giả nó đã được xác thực.

Phân biệt ba giá trị:

1. **Ticket ST:** chuỗi bearer mà browser chuyển về application callback.
2. **Assertion principal name:** ID mà CAS xác nhận, lấy bằng getPrincipal().getName().
3. **Assertion principal attributes:** Map<String,Object> do CAS cung cấp sau attribute release policy.

**Map<String,Object> không bảo đảm mọi giá trị đều là String.** Một attribute nhóm có thể là String, Collection<?> hoặc cấu trúc tùy CAS client/server và validation protocol. Phải có parser dữ liệu theo hợp đồng cụ thể.

## 5. Luồng cấp quyền sau xác minh Service Ticket

Giả sử CAS đã xác minh người dùng có subject **user-104** và release nhóm **portal-readers** và **finance-reviewers**.

~~~text
CAS Server
  ST được phát cho service Portal
        |
        v
CAS /p3/serviceValidate (hoặc endpoint phù hợp)
  authenticationSuccess:
    user = user-104
    attributes:
      memberOf = [portal-readers, finance-reviewers]
        |
        v
TicketValidator -> verified Assertion
        |
        v
AuthenticationUserDetailsService
  1. Xác định CAS trust context đã cấu hình
  2. Map CAS subject tới local account
  3. Từ chối account disabled/suspended
  4. Kiểm tra tenant membership
  5. Parse memberOf theo hợp đồng CAS
  6. Map allowlist nhóm -> role nội bộ
  7. Kết hợp entitlement nội bộ theo policy
        |
        v
UserDetails:
  username = local-account-57
  authorities = [
    ROLE_AUTHENTICATED,
    ROLE_VIEWER,
    ROLE_APPROVER
  ]
        |
        v
Spring Security authorization + object checks
~~~

**Quan trọng:** CASE trên chỉ hợp lệ khi CAS server/service policy được phép release các attributes đó, ST đã được kiểm chứng đúng service và người dùng được liên kết với local account đúng tenant. Nếu CAS chỉ trả username mà không có nhóm, custom loader phải có policy rõ: quyền cơ bản hoặc từ chối nơi yêu cầu đặc quyền.

Không dùng email hoặc tên hiển thị làm căn cứ account linking duy nhất khi có nhiều CAS servers, broker hoặc tenant.

## 6. CAS Attribute Resolution và Attribute Release là hai việc khác nhau

Apereo CAS có hai bước riêng:

- **Attribute Resolution:** CAS lấy thuộc tính principal từ LDAP, database, directory hoặc nguồn khác và gắn với principal.
- **Attribute Release:** CAS quyết định thuộc tính nào được phép trả cho **service cụ thể** trong validation response.

Một CAS Server có thể biết nhóm người dùng nhưng **Portal không nhìn thấy nhóm đó** nếu service registry chưa cho release. Đó có thể là cấu hình đúng vì tối thiểu hóa dữ liệu.

| Giai đoạn | Câu hỏi cần kiểm tra |
| --- | --- |
| CAS authentication | User đã được xác thực theo policy nào? |
| Principal resolution | CAS đã tìm thấy các attributes gì? |
| Service registry | Portal có được phép nhận attribute memberOf không? |
| Attribute release policy | Các giá trị nào được lọc/release cho Portal? |
| Service validation endpoint | Client đang dùng endpoint CAS protocol hỗ trợ attributes chưa? |
| CAS assertion | getPrincipal().getAttributes() có đúng kiểu/value không? |
| Application mapping | Nhóm từ CAS có được phép tạo authority nào? |

Một cấu hình CAS 3.x có thể trả attributes qua **/p3/serviceValidate** và một số validation implementations hỗ trợ attributes theo format riêng. Nếu client dùng validator/version chỉ đọc username, mapper có thể thấy attributes rỗng. **Không tự tạo nhóm mặc định có quyền cao để chữa lỗi thiếu attribute.**

**Phân biệt CAS principal attributes với authentication attributes:** authentication metadata mô tả sự kiện xác thực, handler, thời gian hoặc assurance; principal attributes thường là group, department, email. Không đưa một authentication attribute có tên trùng group vào permission mapping nếu hợp đồng chỉ cho principal attributes.

## 7. XML validation response chứa attributes trông như thế nào?

Ví dụ cấu trúc được mở rộng theo CAS 3.x, để minh họa đa giá trị:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>user-104</cas:user>
    <cas:attributes>
      <cas:memberOf>portal-readers</cas:memberOf>
      <cas:memberOf>finance-reviewers</cas:memberOf>
      <cas:department>finance</cas:department>
    </cas:attributes>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

Đây là **mẫu minh họa**, không phải phản hồi thật từ CAS và không nhất thiết là format serialization của mọi version. Các tên **memberOf** và **department** do ví dụ định nghĩa; hợp đồng thực tế phải xác định tên attribute, kiểu, case, multi-value representation và chính sách release.

**Không parse XML bằng regex/XPath tự viết** trong ứng dụng Spring khi đã có CAS client validator; dùng Assertion được thư viện cung cấp sau validation. Nếu custom XML parsing là bắt buộc, phải giữ các bảo vệ parser/XML schema, TLS, service matching và one-time ticket semantics.

Với dữ liệu có nhiều values, không lấy tùy tiện giá trị đầu tiên rồi bỏ các nhóm còn lại. Ngược lại, cũng không lấy mọi thuộc tính trong map rồi tự hiểu là role.

## 8. Cấp quyền trực tiếp từ CAS attribute có thể nguy hiểm thế nào?

Giả sử CAS trả:

~~~text
memberOf = [
  "portal-readers",
  "ROLE_ADMIN",
  "finance-reviewers"
]
~~~

Một implement sai:

~~~java
// KHÔNG NÊN DÙNG:
List<GrantedAuthority> authorities = rawGroups.stream()
    .map(group -> new SimpleGrantedAuthority(group.toString()))
    .toList();
~~~

Nếu một giá trị từ directory/LDAP do user hoặc đối tác có thể tác động mang tên **ROLE_ADMIN**, nó có thể biến thành authority thực của ứng dụng. Những lỗi khác:

- IdP/CAS A và CAS B đều có nhóm **admins**, nhưng chỉ A được phép cấp một role quản trị.
- Người dùng thuộc **finance-reviewers** trong tenant X nhưng không có quyền trong tenant Y.
- CAS group dùng tên hiển thị có thể đổi; mapping dựa vào substring "admin" sẽ cấp sai.
- Attribute group chưa được release đầy đủ hoặc value bị ép kiểu sai; ứng dụng cấp fallback role quá cao.
- Một user có email trùng với user khác qua CAS context khác và bị gán local account sai.

**Giải pháp:** application-owned allowlist, ràng buộc nguồn, account status, tenant membership và object-level authorization.

## 9. Lớp hỗ trợ sẵn: GrantedAuthorityFromAssertionAttributesUserDetailsService

Spring Security có class **org.springframework.security.cas.userdetails.GrantedAuthorityFromAssertionAttributesUserDetailsService**:

~~~java
// Mảnh cấu hình API, không phải bean Spring đầy đủ:
GrantedAuthorityFromAssertionAttributesUserDetailsService loader =
    new GrantedAuthorityFromAssertionAttributesUserDetailsService(
        new String[] { "memberOf" });

loader.setConvertToUpperCase(false);
casProvider.setAuthenticationUserDetailsService(loader);
~~~

Lớp này implements **AuthenticationUserDetailsService<CasAssertionAuthenticationToken>**. Theo Javadoc, nó đọc các attribute được chỉ định, rồi **mỗi giá trị** của attribute trở thành một GrantedAuthority. Có tùy chọn đổi giá trị sang uppercase.

### Khi nào có thể dùng?

Chỉ cân nhắc khi tất cả điều kiện đã được bảo đảm:

1. CAS Server được tin, đã validate ST đúng service.
2. Attribute được chỉ định được phát hành cho **đúng ứng dụng** và có semantics role thật sự, không phải generic group.
3. CAS **đã giới hạn/chuyển đổi chính xác** các giá trị sang namespace quyền của SP.
4. Không có tenant/source collision hoặc app-specific conditions mà mapper trực tiếp không thể biểu diễn.
5. Không có trường hợp user tự ghi giá trị attribute hoặc nhóm đến từ nơi không được phê duyệt.
6. Đã kiểm thử các case role injection, giá trị lạ và thủ tục thu hồi quyền.

**setConvertToUpperCase không phải bảo mật.** Nó chỉ thay đổi chữ hoa/chữ thường, không biến nhóm thành allowlist, không giải quyết IdP/tenant scope và không xác nhận đây là quyền hợp lệ.

### Khi nào không nên dùng trực tiếp?

Nếu CAS trả các nhóm phổ quát của LDAP, tên hiển thị, tenant groups hoặc thông tin từ nhiều upstream providers, **một-một sang GrantedAuthority** có thể cấp quá nhiều quyền. Nên dùng custom AuthenticationUserDetailsService và policy do ứng dụng kiểm soát.

Đặc biệt **không cấu hình class trên với attribute names không chắc chắn**, ví dụ cho tất cả department/email hoặc attribute do user sửa được.

## 10. Thiết kế chính sách mapping an toàn

Một mapping nên gắn tối thiểu:

| Thành phần | Ví dụ | Ai quản lý? |
| --- | --- | --- |
| CAS trust context | **corp-cas** | SP/operations, không lấy từ query |
| Service identity | **https://portal.example.test/login/cas** | CAS service registry và SP config |
| CAS principal ID | **user-104** | CAS sau ticket validation |
| Local account | **acct-57** | SP database, mapping đáng tin |
| Tenant scope | **north** | SP kiểm tra membership |
| CAS attribute | **memberOf** | Contract với CAS admin |
| Giá trị group | **finance-reviewers** | CAS directory group ID |
| Authority nội bộ | **ROLE_APPROVER** | SP policy owner |
| Additional requirements | account active, MFA/assurance nếu cần, resource ownership | SP + CAS policy |

Ví dụ:

| CAS context / tenant | Giá trị memberOf | Authority được phép |
| --- | --- | --- |
| corp-cas / north | portal-readers | ROLE_VIEWER |
| corp-cas / north | finance-reviewers | ROLE_APPROVER |
| partner-cas / north | partner-readers | ROLE_VIEWER |
| corp-cas / south | finance-reviewers | Không có mapping, không cấp |
| partner-cas / north | finance-reviewers | Không có mapping, không cấp |
| Bất kỳ | ROLE_ADMIN | Không cấp chỉ từ raw group name |

**Tại sao dùng exact mapping?** Một nhóm có tên finance-reviewers không tự tương đương role của tenant khác. Mỗi quyền phải được đặt tên và xét điều kiện bởi domain owner. Nếu tổ chức cần quyền quản trị, nên yêu cầu policy riêng với approver, MFA và account entitlement trong database.

## 11. Thuộc tính CAS có nhiều kiểu: cần parse cẩn thận

**Map<String,Object>** có thể chứa:

- Một String: **portal-readers**.
- Một List hoặc Collection: **[portal-readers, finance-reviewers]**.
- Mảng values hoặc định dạng serializer khác theo client.
- Null hoặc attribute không được release.
- Giá trị không thuộc kiểu dự kiến, ví dụ số, XML object, Map hay nested collection.
- Chuỗi lớn bất thường hoặc số lượng groups vượt mức chấp nhận.

Một policy phòng ngừa nên:

1. Chỉ đọc **tên attribute đã thỏa thuận** (ví dụ memberOf).
2. Định nghĩa **những kiểu value được chấp nhận** theo CAS validator/version, không tự gọi toString() trên mọi object.
3. Với nhiều values, kiểm tra từng value là String hợp lệ; loại trùng.
4. Áp giới hạn kích thước và số lượng; từ chối trường hợp quá lớn để bảo vệ performance.
5. Map exact group ID, không match regex quá rộng/substring.
6. Chỉ cho phép các authorities nằm trong allowlist của **đúng CAS context/tenant**.
7. Không cấp quyền nhạy cảm nếu attribute thiếu hoặc sai kiểu; nếu attribute bắt buộc cho cả login thì từ chối có kiểm soát.
8. Không vô tình coi giá trị trống, khoảng trắng, chữ hoa/thường khác nhau là cùng group khi policy không quy định.
9. Không tự cố phân tích một chuỗi **a,b,c** thành ba groups trừ khi hợp đồng CAS nói rõ đó là định dạng serialized list.
10. Với nhóm LDAP DN, nên map theo mã ID/DN canonical đã được phê duyệt, không tách lấy CN rồi tin mọi nhóm CN trùng nhau.

**Fail closed** nghĩa là quyền nhạy cảm bị từ chối khi không có bằng chứng đủ, không nhất thiết phải chặn mọi người dùng khỏi trang thông tin công khai.

## 12. Java 17 độc lập: chuyển group sang role qua allowlist

Ví dụ dưới đây **chạy được bằng JDK 17+**, chỉ sử dụng thư viện chuẩn. Nó mô phỏng policy sau khi CAS ticket đã được xác minh, không xử lý CAS protocol. Context và tenant giả định được xác định ở server.

Tạo file **CasAuthorityPolicyDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class CasAuthorityPolicyDemo {

    record Scope(String casContext, String tenant) {}

    private static final Map<Scope, Map<String, String>> ALLOWED =
            Map.of(
                new Scope("corp-cas", "north"),
                    Map.of("portal-readers", "ROLE_VIEWER",
                           "finance-reviewers", "ROLE_APPROVER"),
                new Scope("partner-cas", "north"),
                    Map.of("partner-readers", "ROLE_VIEWER")
            );

    static Set<String> authorities(
            String casContext, String tenant, Object rawGroups) {

        Map<String, String> mapping =
                ALLOWED.get(new Scope(casContext, tenant));

        if (mapping == null || rawGroups == null) {
            return Set.of();
        }

        Collection<?> values;
        if (rawGroups instanceof String string) {
            values = List.of(string);
        } else if (rawGroups instanceof Collection<?> collection) {
            values = new ArrayList<>(collection);
        } else {
            throw new IllegalArgumentException("Unsupported groups type");
        }

        TreeSet<String> result = new TreeSet<>();
        for (Object value : values) {
            if (!(value instanceof String group)) {
                throw new IllegalArgumentException("Unsupported group value");
            }
            String role = mapping.get(group);
            if (role != null) {
                result.add(role);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("corp/north: " + authorities(
            "corp-cas", "north",
            List.of("portal-readers", "finance-reviewers",
                    "ROLE_ADMIN", "portal-readers")));

        System.out.println("partner/north: " + authorities(
            "partner-cas", "north",
            List.of("finance-reviewers")));

        System.out.println("corp/south: " + authorities(
            "corp-cas", "south",
            List.of("finance-reviewers")));

        System.out.println("single value: " + authorities(
            "partner-cas", "north", "partner-readers"));

        try {
            authorities("corp-cas", "north",
                List.of("portal-readers", 7));
        } catch (IllegalArgumentException error) {
            System.out.println("bad type: REJECT");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CasAuthorityPolicyDemo.java
java CasAuthorityPolicyDemo
~~~

**Stdout chính xác:**

~~~text
corp/north: [ROLE_APPROVER, ROLE_VIEWER]
partner/north: []
corp/south: []
single value: [ROLE_VIEWER]
bad type: REJECT
~~~

### Giải thích từng trường hợp

- corp/north có hai groups được phê duyệt nên nhận ROLE_APPROVER và ROLE_VIEWER. ROLE_ADMIN không được map và group trùng bị khử trùng lặp.
- partner/north không được dùng finance-reviewers của corp-cas, nên không cấp quyền corp.
- corp/south không có policy, nên không thể lấy quyền north.
- Một String riêng lẻ cũng được xử lý theo contract.
- Một giá trị số trong danh sách khiến mapper từ chối thay vì gọi toString() rồi giả như group hợp lệ.

**Hạn chế rõ ràng:** chương trình chỉ kiểm thử hàm ánh xạ nhóm; không kết nối CAS, không xác minh ST, không xác thực principal, không kiểm tra tenant membership trong database và không tạo Spring GrantedAuthority. Trong production, **casContext và tenant phải lấy từ configuration/account đã được server xác nhận**, không lấy trực tiếp từ HTTP query/header. Không sử dụng hàm này như một CAS TicketValidator.

## 13. Custom AuthenticationUserDetailsService trong dự án Spring

Mẫu sau dành cho **Spring Security 6.x/7.x với module CAS và Java 17+**, dùng API đã công bố: **CasAssertionAuthenticationToken.getAssertion()**, **Assertion.getPrincipal().getAttributes()**, và **AuthenticationUserDetailsService.loadUserDetails()**.

Tệp **src/main/java/com/example/security/ScopedCasUserDetailsService.java**:

~~~java
package com.example.security;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.cas.authentication.CasAssertionAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.AuthenticationUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

public final class ScopedCasUserDetailsService
        implements AuthenticationUserDetailsService<CasAssertionAuthenticationToken> {

    public interface AccountDirectory {
        LocalAccount findByCasIdentity(String context, String subject);
    }

    public record LocalAccount(
            String localId, String tenant, boolean active) {}

    private final AccountDirectory accounts;

    // Đây là CAS context chỉ định bởi SERVER cho provider này,
    // không lấy từ query/attribute của browser.
    private static final String CAS_CONTEXT = "corp-cas";

    private static final Map<String, Map<String, String>> RULES =
            Map.of("north",
                Map.of("portal-readers", "ROLE_VIEWER",
                       "finance-reviewers", "ROLE_APPROVER"));

    public ScopedCasUserDetailsService(AccountDirectory accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserDetails(CasAssertionAuthenticationToken token) {
        if (token == null || token.getAssertion() == null
                || token.getAssertion().getPrincipal() == null) {
            throw new BadCredentialsException("Missing verified CAS assertion");
        }

        String subject = token.getAssertion().getPrincipal().getName();
        if (subject == null || subject.isBlank()) {
            throw new BadCredentialsException("Missing CAS subject");
        }

        LocalAccount local = accounts.findByCasIdentity(CAS_CONTEXT, subject);
        if (local == null) {
            throw new UsernameNotFoundException(
                    "No linked local account for CAS subject");
        }
        if (!local.active()) {
            throw new DisabledException("Local account is disabled");
        }

        Map<String, Object> attributes =
                token.getAssertion().getPrincipal().getAttributes();

        // Authority nền tảng cố định, KHÔNG phải quyền quản trị.
        Set<String> roles = new TreeSet<>();
        roles.add("ROLE_AUTHENTICATED");

        Map<String, String> allowed = RULES.get(local.tenant());
        if (allowed != null && attributes != null) {
            Object raw = attributes.get("memberOf");
            Collection<?> groups;
            if (raw == null) {
                groups = List.of();
            } else if (raw instanceof String one) {
                groups = List.of(one);
            } else if (raw instanceof Collection<?> many) {
                groups = new ArrayList<>(many);
            } else {
                throw new BadCredentialsException("Invalid CAS groups type");
            }

            if (groups.size() > 100) {
                throw new BadCredentialsException("Too many CAS groups");
            }
            for (Object value : groups) {
                if (!(value instanceof String group) || group.length() > 256) {
                    throw new BadCredentialsException("Invalid CAS group value");
                }
                String role = allowed.get(group);
                if (role != null) {
                    roles.add(role);
                }
            }
        }

        List<GrantedAuthority> authorities = roles.stream()
                .map(SimpleGrantedAuthority::new)
                .map(x -> (GrantedAuthority) x)
                .toList();

        // "!" là password marker không sử dụng trong login CAS.
        // Không cấu hình DaoAuthenticationProvider cho account này.
        return new User(local.localId(), "!", true, true, true, true,
                authorities);
    }
}
~~~

**Điểm an toàn được thực thi:**

1. Lấy principal/attributes từ assertion do CAS provider nhận sau validation, không từ form hoặc raw HTTP ticket.
2. Resolve account bằng **CAS_CONTEXT + subject**, không dùng subject string xuyên mọi CAS environments.
3. Từ chối account không có identity link hoặc bị disable.
4. Dùng tenant của **local account đã tra cứu**, không lấy tenant do browser tự yêu cầu.
5. Chỉ đọc memberOf và chỉ nhận String/Collection có values là String.
6. Áp giới hạn số lượng/độ dài, tránh tự ép kiểu.
7. Tạo ROLE_AUTHENTICATED là **quyền cơ sở do SP định nghĩa**, không đồng nghĩa ROLE_APPROVER/ADMIN.
8. Chỉ cấp quyền mạnh qua RULES của đúng tenant; group lạ không được chuyển thành authority.
9. Trả UserDetails để provider xây Authentication; Spring vẫn phải kiểm tra các domain permissions sau login.

**Đây là class có thể đưa vào dự án Spring**, không thể chạy bằng javac thuần JDK và không có stdout cố định. Cần implement **AccountDirectory** bằng repository/database nội bộ và tạo bean cho class. Mẫu chỉ minh họa một CAS provider; với nhiều CAS servers phải tạo loader/policy có CAS context riêng, không dùng chung một hằng số context cho mọi provider.

**Bảo vệ password marker:** UserDetails contract đòi cung cấp trường password cho class User, nhưng authentication ở đây dựa trên CAS ST. Marker "!" không dùng như password hợp lệ và **không nên đồng thời đưa cùng UserDetails này vào một password-based login flow**. Nếu hệ thống có nhiều authentication mechanisms, dùng custom principal/credential management tách biệt và PasswordEncoder phù hợp.

## 14. Nối loader với CasAuthenticationProvider

Trong một Spring Configuration đã có **ServiceProperties** và **TicketValidator** được cấu hình đúng, tích hợp custom loader:

~~~java
@Bean
ScopedCasUserDetailsService casUserDetails(
        ScopedCasUserDetailsService.AccountDirectory directory) {
    return new ScopedCasUserDetailsService(directory);
}

@Bean
CasAuthenticationProvider casAuthenticationProvider(
        ServiceProperties serviceProperties,
        TicketValidator ticketValidator,
        ScopedCasUserDetailsService casUserDetails) {

    CasAuthenticationProvider provider = new CasAuthenticationProvider();
    provider.setServiceProperties(serviceProperties);
    provider.setTicketValidator(ticketValidator);
    provider.setAuthenticationUserDetailsService(casUserDetails);
    provider.setKey("portal-cas-provider-identity-v1");
    return provider;
}
~~~

**Đây là đoạn bean setup nằm trong @Configuration, không phải lớp standalone**. Cần imports:

- **org.springframework.security.cas.authentication.CasAuthenticationProvider**
- **org.springframework.security.cas.ServiceProperties**
- **org.apereo.cas.client.validation.TicketValidator**

Còn cần **CasAuthenticationFilter**, **CasAuthenticationEntryPoint**, AuthenticationManager/ProviderManager, SecurityFilterChain và đúng CAS service URL theo tài liệu Spring Security. Đừng chỉ tạo provider bean rồi mặc định cho rằng filter và entry point sẽ tự được dây nối trong mọi project.

### Chọn TicketValidator phù hợp để nhận attributes

Apereo CAS Client có các validators theo protocol, gồm **Cas20ServiceTicketValidator** và **Cas30ServiceTicketValidator**. Hãy dùng validator tương thích với endpoint CAS Server và kiểu attributes cần thiết. Với một hệ thống CAS 3.x release multi-value attributes, thường cần **/p3/serviceValidate** hoặc validation profile tương ứng.

**Nếu assertion không có attributes**, trước tiên kiểm tra CAS service registry release policy, validation endpoint/validator version và attribute mapping. Không cho fallback cấp ROLE_ADMIN hoặc bỏ qua validation.

## 15. UserDetailsByNameServiceWrapper: trường hợp quyền do DB nội bộ quyết định hoàn toàn

Nếu muốn CAS chỉ chứng minh username và toàn bộ roles nằm trong database ứng dụng, có thể dùng một UserDetailsService:

~~~java
UserDetailsService localUserDetails = username -> {
    // Repository của ứng dụng tự lookup user:
    // chỉ dùng khi CAS trust context của provider đã rõ,
    // tránh collision giữa nhiều CAS servers.
    return localAccountService.loadUserByCasSubject("corp-cas", username);
};

UserDetailsByNameServiceWrapper<CasAssertionAuthenticationToken> adapter =
        new UserDetailsByNameServiceWrapper<>(localUserDetails);

casProvider.setAuthenticationUserDetailsService(adapter);
~~~

**Snippet trên có localAccountService được ứng dụng cung cấp** và phải đặt trong cấu hình Spring phù hợp; không thể copy chạy độc lập. Nó minh họa điểm mạnh/yếu: wrapper đơn giản, nhưng nếu CAS gửi group attributes thì wrapper **không dùng những attributes đó** trừ khi local service truy cập qua cơ chế khác. Đừng làm localUserDetails tra cứu chỉ theo email nếu nhà cung cấp CAS có nhiều subject namespaces.

Cách này hữu ích khi:

- CAS attributes chỉ dùng cho hiển thị.
- Quyền được quản lý độc lập trong ứng dụng/authorization service.
- Thời gian thu hồi quyền cần ngắn hơn phiên SSO.
- Application owner không muốn IdP quyết định trực tiếp app roles.
- Có policy audit và account status ở database.

## 16. Dùng GrantedAuthoritiesMapper có thay custom service được không?

**CasAuthenticationProvider#setAuthoritiesMapper** cho phép can thiệp tập GrantedAuthority được sinh ra. Đây có thể là chỗ áp dụng **prefix**, đổi tên role hoặc loại bỏ authorities không phù hợp.

Ví dụ:

~~~java
GrantedAuthoritiesMapper mapper = originals -> originals.stream()
    .filter(a -> Set.of("ROLE_AUTHENTICATED", "ROLE_VIEWER",
            "ROLE_APPROVER").contains(a.getAuthority()))
    .map(a -> new SimpleGrantedAuthority(a.getAuthority()))
    .collect(java.util.stream.Collectors.toSet());

casProvider.setAuthoritiesMapper(mapper);
~~~

**Đây chỉ là mảnh code trong cấu hình Spring**, không độc lập. Việc lọc danh sách authority theo tên giúp tránh một số giá trị không mong muốn nhưng **không đủ cho multi-tenant/cross-CAS mapping** nếu đã mất thông tin nguồn/tenant. Do đó nên quyết định group→role trong custom AuthenticationUserDetailsService nơi có assertion và account context.

**Lưu ý:** khi dùng cả custom loader và authorities mapper, cần định nghĩa thứ tự và semantics rõ ràng để mapper không vô tình thêm quyền mới không được policy cho phép.

## 17. ROLE_ prefix, hasRole và hasAuthority

Spring Security dùng GrantedAuthority để diễn tả quyền. Với role prefix mặc định:

- **hasAuthority('ROLE_APPROVER')** kiểm chuỗi chính xác.
- **hasRole('APPROVER')** tìm authority tương ứng với prefix **ROLE_** theo cấu hình chuẩn.
- **hasAuthority('payment:approve')** có thể dùng permission dạng hành động cụ thể.
- **ROLE_AUTHENTICATED** trong ví dụ chỉ là role cơ sở do ứng dụng định nghĩa, không có ý nghĩa bảo mật chuẩn chung.

Ví dụ trong một service đã bật Method Security:

~~~java
@PreAuthorize("hasRole('APPROVER')")
public void approveInvoice(long invoiceId) {
    // Ngoài role, cần kiểm object tenant và trạng thái hóa đơn.
}
~~~

Trong ứng dụng thực, bảo vệ domain object thêm:

~~~java
@PreAuthorize("hasAuthority('ROLE_APPROVER')"
    + " and @invoiceAccess.canApprove(authentication, #invoiceId)")
public void approveInvoice(long invoiceId) {
    // Sau khi service policy đồng ý mới cập nhật hóa đơn.
}
~~~

**Hai method trên là ví dụ thay thế, không đặt cùng signature trong một class**. Phải bật **@EnableMethodSecurity** và định nghĩa bean invoiceAccess theo đúng tên/logic domain. Không dùng một role toàn cục để cấp quyền duyệt hóa đơn của mọi tenant.

## 18. Bảo đảm CAS trust context và account linking

Một hệ thống có thể nhận ticket từ nhiều CAS servers hoặc một broker đứng trước nhiều nguồn identity. Username **alice** ở CAS corp không tự trùng với username **alice** ở CAS partner. Cũng không thể coi cùng email là một local account.

Dữ liệu liên kết an toàn:

~~~text
federated_identity:
  cas_context      = corp-cas
  cas_subject      = alice
  local_account_id = acct-57
  tenant_id        = north
  UNIQUE(cas_context, cas_subject)

federated_identity:
  cas_context      = partner-cas
  cas_subject      = alice
  local_account_id = acct-91
  tenant_id        = partner-tenant
~~~

**cas_context** trong ví dụ là định danh trust configuration **do SP gán** cho CAS server và service; CAS protocol không có claim **iss** bắt buộc như OIDC. Đừng tự gán username thành namespace toàn cục hoặc dùng URL login mà browser nhập để xác định trust context.

Nếu hệ thống có nhiều CAS clients/filters, cần bảo đảm ticket validator và authentication provider của đúng CAS context đang chạy. Không tùy tiện fallback sang validator của CAS khác vì một ST không validate được.

### Tenant authorization

Dù account được liên kết đúng, mapping nhóm chỉ nên tạo các quyền trong tenant được phép. Khi truy cập object, cần kiểm:

1. Local account còn active.
2. Account là member của tenant hiện tại.
3. Nhóm CAS có được policy cho phép cấp quyền trong tenant này?
4. Quyền trên object cụ thể/ownership/approval workflow có hợp lệ?
5. Với thao tác nhạy cảm, mức xác thực/step-up và session freshness có đủ không?

Không lấy tham số **?tenant=north** từ browser làm một nguồn sự thật trước khi cấp ROLE_APPROVER.

## 19. Attribute release tối thiểu và quyền bảo mật ở CAS Server

Application không nên yêu cầu mọi thuộc tính CAS có sẵn. Với một Portal chỉ cần nhóm và department, CAS admin nên cấu hình **release policy theo service**:

| Attribute | Có cần release? | Lý do |
| --- | --- | --- |
| Stable principal ID | Có | Liên kết account nội bộ |
| memberOf (nhóm dành cho Portal) | Nếu policy dựa vào groups | Dữ kiện để map authorities |
| department | Chỉ nếu domain policy cần | Thông tin ngữ cảnh |
| email | Có thể cho UX/notification | Không dùng làm unique identity key |
| password/credential | **Không** | Bí mật xác thực, không được release |
| TGT/TGC/PGT value | **Không** trừ protocol-specific proxy policy cực kỳ chặt | Credential nhạy cảm |
| Mọi LDAP attributes | Thường không | Vi phạm least privilege và tăng rủi ro PII |

Apereo CAS hỗ trợ **Return Allowed**, **Mapped** và nhiều loại policies; dịch vụ cần owner duyệt thuộc tính nào được phát hành. Một group dùng cho quyền nên có **identifier ổn định và semantics được định nghĩa**, thay vì tên hiển thị thay đổi.

**Ranh giới hai phía:** CAS giới hạn điều được release; SP vẫn phải **giới hạn quyền được cấp**. CAS release thành công không tự làm một giá trị trở thành ROLE_ADMIN.

## 20. Quyền có bị cập nhật ngay khi group CAS thay đổi không?

Không mặc định. Tại thời điểm login, AuthenticationUserDetailsService tạo **UserDetails/authorities snapshot**. Spring Security lưu Authentication trong SecurityContext và local session. Khi CAS/LDAP thay group sau đó:

- TGT CAS có thể còn hiệu lực.
- Local session SP có thể còn hiệu lực.
- UserDetails/GrantedAuthority trong session SP có thể giữ các role cũ.
- CAS không tự gọi AuthenticationUserDetailsService lại trên mọi request.
- CAS Single Logout có thể chấm dứt local session nếu tích hợp đúng, nhưng không thay thế quyền kiểm tra realtime.

Biện pháp tùy mức độ nhạy cảm:

1. Giới hạn SP session timeout và idle timeout.
2. Với quyền cao, tra entitlements hiện hành tại authorization service mỗi request quan trọng.
3. Áp version/epoch revocation của account hoặc tenant roles trong backend.
4. Bắt reauthentication/renew khi thực hiện bước nhạy cảm, nếu CAS assurance policy yêu cầu.
5. Kết nối sự kiện thay đổi quyền/khóa tài khoản để invalidate sessions.
6. Đánh giá cache trong UserDetailsService, CasAuthenticationProvider và ứng dụng để tránh giữ roles quá lâu.
7. Kiểm tra access sau khi user bị disable hoặc bị gỡ group, không chỉ sau login mới.

**Không dựa vào TGC/TGT hết hạn để kết luận local session và mọi API tokens đã hết hiệu lực.** Ứng dụng có trách nhiệm với phiên/tokens do mình phát.

## 21. Tách quyền đăng nhập, quyền chức năng và quyền dữ liệu

Một mapping bảo mật tốt thường có ba lớp:

| Cấp | Ví dụ | Khi nào kiểm |
| --- | --- | --- |
| Authentication baseline | ROLE_AUTHENTICATED | Sau CAS ST validation và active local account |
| Chức năng ứng dụng | ROLE_VIEWER, ROLE_APPROVER | Trong AuthorizationFilter/@PreAuthorize |
| Đối tượng/tenant | Có quyền duyệt invoice 123 của tenant north | Trong domain service/authorization component |

**Người dùng có ROLE_APPROVER không tự được quyền duyệt mọi hóa đơn.** Nếu cùng local account là Approver của north nhưng chỉ Viewer của south, phải gắn role với tenant hoặc kiểm domain policy theo tenant mỗi lần thao tác. Role toàn cục không đủ làm ranh giới tenant.

Một chính sách tổng quát:

~~~text
ALLOW approve(invoiceId)
  IF verified CAS login
  AND local account active
  AND current tenant membership active
  AND permitted app authority
  AND invoice belongs to current tenant
  AND invoice state permits approval
  AND approval separation-of-duties check succeeds
ELSE DENY
~~~

Không đặt logic quyền nhạy cảm trong JSP/template hay chỉ ẩn nút trên frontend. Server-side enforcement là bắt buộc.

## 22. Vấn đề đặc thù: groups thiếu, sai kiểu hoặc thay tên

| Input đã xác minh từ CAS | Hành vi an toàn |
| --- | --- |
| memberOf vắng mặt | Không cấp thêm role nhạy cảm; có thể giữ quyền cơ sở tùy policy |
| memberOf = empty Collection | Không cấp thêm role |
| memberOf = portal-readers | Map chính xác thành ROLE_VIEWER trong scope được phê duyệt |
| memberOf = ROLE_ADMIN lạ | Không chuyển nguyên xi thành ROLE_ADMIN |
| memberOf có nhiều values trùng | Khử trùng lặp |
| memberOf chứa Integer hoặc Map | Reject/bỏ qua theo contract; không gọi toString để cấp quyền |
| memberOf quá dài/nhiều | Enforce limits, từ chối có kiểm soát |
| Group đổi tên từ finance-reviewers sang finance-approvers | Chưa cấp quyền mới đến khi policy được duyệt |
| Attribute đổi từ memberOf sang groups | Không tự đoán; phối hợp CAS admin sửa release contract |
| Tenant không được liên kết với account | Không cấp quyền tenant-specific |
| CAS trả attributes nhưng DB local bị lỗi | Fail closed cho quyền nhạy cảm, không fallback admin |
| Local account bị disabled | Từ chối login hoặc invalidate session theo policy |
| CAS principal alice có hai trust contexts | Tách identity links, không gộp theo username |
| Group lạ ngoài allowlist | Không cấp authority mới, audit mức phù hợp |

**Thông báo cho người dùng:** Khi CAS authentication đã thành công nhưng SP không cấp đủ quyền, có thể nhận **403 Forbidden** thay vì quay lại CAS login. Đây thường là lỗi role/tenant configuration, không phải chứng cứ CAS ST validation sai.

## 23. Testing: Unit test mapper và integration test CAS

### Unit test theo các case

| Case | Dữ liệu | Kết quả kỳ vọng |
| --- | --- | --- |
| 01 | corp-cas/north + portal-readers | ROLE_VIEWER |
| 02 | corp-cas/north + finance-reviewers | ROLE_APPROVER |
| 03 | corp-cas/north + cả hai groups | Viewer và Approver |
| 04 | corp-cas/north + ROLE_ADMIN | Không tự cấp Admin |
| 05 | partner-cas/north + finance-reviewers | Không cấp quyền corp |
| 06 | corp-cas/south + finance-reviewers | Không có quyền north |
| 07 | Group trùng | Chỉ một authority tương ứng |
| 08 | Group value kiểu số | Reject hoặc fail closed theo mapper |
| 09 | memberOf null/empty | Chỉ quyền cơ sở |
| 10 | Attribute name đổi | Không tự tìm trường khác để cấp quyền |
| 11 | local account không linked | Không tạo Authentication quyền cao |
| 12 | local account disabled | Từ chối theo account status |
| 13 | User CAS A và CAS B cùng username | Định danh nội bộ độc lập |
| 14 | Tenant X membership bị thu hồi | Không cho truy cập tài nguyên X |
| 15 | Policy service timeout | Fail closed quyền nhạy cảm |
| 16 | Group thay đổi trong khi local session còn | Kiểm chứng revocation/session policy |
| 17 | Quyền ROLE_APPROVER nhưng invoice tenant khác | Deny tại object-level authorization |
| 18 | CAS attribute nhiều values | Duyệt đầy đủ, map đúng |
| 19 | Prefix ROLE_ tùy chỉnh | hasRole/hasAuthority thực thi đúng |
| 20 | Case-sensitive group ID | Không normalize ngầm |
| 21 | Local database concurrent lookup/provision | Không tạo duplicate accounts |
| 22 | CAS assertion null hoặc principal thiếu | Không chấp nhận |
| 23 | Mất ticket validation network | Không gọi loader với dữ liệu chưa xác minh |
| 24 | Service URL mismatch | CAS không trả authenticationSuccess |
| 25 | CAS /serviceValidate không release groups | App không tự cấp role vì không có dữ liệu |

### Integration tests có CAS thật hoặc test CAS Server

1. Browser được redirect tới CAS login cho service đã đăng ký.
2. CAS cấp một ST đúng service; Spring CasAuthenticationProvider gọi TicketValidator.
3. Validation response có principal+memberOf thực; custom loader nhận đúng assertions.
4. UserDetails trả local account ID và authorities đúng allowlist.
5. Với ST của service khác, CAS validation fail **trước** user loader.
6. Đăng nhập lại với group khác sau policy update; quyền mới được áp theo thời điểm/lifecycle kỳ vọng.
7. CAS logout/SLO và SP session invalidation được thử riêng.
8. HTTPS, reverse proxy URL, cookies, one-time ticket, XML parsing và client version được kiểm chứng.

**Không coi unit test fake Assertion là bằng chứng production SSO.** Nó chỉ kiểm tra mapper; protocol trust phải được test qua CAS Server và configured TicketValidator.

## 24. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| CAS login thành công nhưng Spring trả 403 | Không có local roles hoặc domain policy từ chối | Kiểm tra UserDetails authorities và tenant membership |
| CAS assertion chỉ có username | Service chưa được release attributes | Kiểm tra CAS Service Registry và attribute release policy |
| Attributes vẫn trống dù CAS có LDAP groups | Validator dùng protocol/endpoint không trả attributes | So /p3/serviceValidate, CAS client version và assertion parsing |
| CasAuthenticationProvider không gọi custom loader | Chưa cấu hình setAuthenticationUserDetailsService đúng instance | Xác minh provider bean/filter/manager wiring |
| Ứng dụng chỉ load roles từ DB dù CAS có groups | Đang dùng UserDetailsByNameServiceWrapper | Chuyển custom loader khi cần group CAS |
| Một group lạ thành ROLE_ADMIN | Mapping raw attribute không qua allowlist | Dùng exact group→role policy, không auto-name |
| User corp được quyền partner | Không scope CAS context/tenant | Tách trust namespaces và membership |
| Đăng nhập lỗi do username không tìm thấy | External identity chưa được liên kết | Onboarding/JIT có phê duyệt, không ghép theo email |
| Disabled account vẫn vào ứng dụng | Custom loader không kiểm trạng thái hoặc session cũ còn | Check active status và revoke sessions |
| ROLE_VIEWER có nhưng hasRole('VIEWER') không nhận | Prefix/case mismatch | Kiểm tra ROLE_ prefix và authority names |
| ROLE_APPROVER đúng nhưng invoice tenant khác vẫn thao tác được | Chưa có object-level authorization | Kiểm resource tenant và nghiệp vụ |
| ST invalid/expired | CAS one-time ticket, service mismatch, timeout | Kiểm client CAS validation, không retry ST bừa |
| Spring 5 code không compile ở Spring 6/7 | Package org.jasig ↔ org.apereo và API khác | Cập nhật dependency/import theo version BOM |
| Reload local DB làm roles thay đổi chậm | Authorities nằm trong SecurityContext/session | Thiết kế re-login/refresh/revocation |
| Một node thấy group, node khác không | CAS attribute cache/client version config lệch | Đồng bộ CAS/Spring cluster configuration |
| Attribute value là Collection nhưng code ép String | ClassCastException/role missing | Parser strict hỗ trợ multi-value |
| Client dùng acceptAnyProxy để tránh lỗi | Mở trust quá rộng cho proxy tickets | Khóa proxy policy, không bật khi không cần |

**Log an toàn:** correlation ID, service identity, CAS trust context, local account ID đã ẩn danh khi cần, policy version, số groups hợp lệ, số authority được cấp và mã lỗi. **Không log** ST, TGT, TGC, raw CAS assertion chứa PII, password hoặc private/proxy credentials.

## 25. Bảo mật và vận hành nâng cao

### Service-specific authority policy

CAS Service Registry có thể release một tập attribute khác nhau tới từng service. Cùng nhóm directory **finance-reviewers** có thể mang nghĩa khác ở Portal và HRM. Đừng sử dụng chung một bảng mapping toàn tập đoàn nếu role semantics không tương ứng.

**Đúng:** mỗi ứng dụng có policy owner, group IDs, role names, tenant scope và test riêng. **Sai:** mọi service đều tự áp rule "bất kỳ group có chữ admin → ROLE_ADMIN".

### Cơ chế đổi phiên/thu hồi quyền

Nếu group bị rút tại CAS/LDAP, local session có thể còn authorities cũ. Với quyền cao, kiểm entitlement ở server hoặc invalidates sessions khi policy thay đổi. Đặt TTL theo sensitivity, không dựa duy nhất vào thời hạn TGT.

### Consent và PII

Chỉ request/release attributes thiết yếu. Nếu cần email/department cho hiển thị, không dùng chúng như chứng cứ đủ để liên kết account và quyền. CAS service release policy nên chặn password và proxy-granting credentials ngoài những use cases có kiểm soát nghiêm ngặt.

### Rate limit và chống DoS

Không chấp nhận hàng chục nghìn group values, nested objects, chuỗi cực lớn hoặc regular expressions nguy hiểm cho role mapping. Đặt giới hạn và đưa lỗi về authentication failure/authorization deny có kiểm soát.

### Phối hợp đổi tên group

CAS admin và app owner cần quy trình change: chuẩn hóa group ID, đánh giá semantic difference, cập nhật mapping bảng allowlist, test canary, triển khai rồi mới bỏ tên cũ khi phù hợp. Không tự alias mọi tên nhóm chỉ bằng lowercase/trim.

### Đa CAS server

Một ứng dụng có thể kết nối nhiều CAS servers qua kiến trúc riêng; mỗi server cần trust config/validator, service IDs và identity namespace rõ. Không dùng principal username duy nhất để nối hai CAS contexts khi chưa có account-link proof.

## 26. Runbook triển khai từ đầu

1. **Thỏa thuận CAS contract:** xác định CAS Server URL, service callback, TLS trust, validation endpoint và CAS client version.
2. **Đăng ký service:** CAS Service Registry cho phép Portal, cấu hình strict service URL và attribute release policy.
3. **Xác minh dữ liệu:** dùng test user có một và nhiều groups, đọc assertion principal/attributes sau ticket validation; không ghi nguyên ST/PII vào log.
4. **Thiết kế account linking:** map (CAS context, CAS subject) → local account ID, có uniqueness và kiểm account status.
5. **Thiết kế mapping:** allowlist per-service/per-tenant; quyền nhạy cảm phải được app owner phê duyệt.
6. **Chọn loader:** UserDetailsService wrapper khi không cần CAS attributes; custom AuthenticationUserDetailsService khi cần assertion/tenant.
7. **Nối provider:** setAuthenticationUserDetailsService vào đúng CasAuthenticationProvider; đúng TicketValidator, ServiceProperties, filter và entry point.
8. **Thử roles:** CAS login thành công, authorities đúng, hasRole/hasAuthority đúng.
9. **Thử fail closed:** ticket invalid, attribute thiếu, group lạ, account disabled, tenant sai, DB outage.
10. **Thử session lifecycle:** logout, SLO, group change, cache/session expiry và revocation.
11. **Triển khai nhiều node:** đồng nhất config, ticket validation TLS, access logs redaction, metrics và policy version.
12. **Audit:** lưu change owner, test results, CAS release policy và phương án rollback.

Không chỉ thử “đăng nhập được” mà bỏ qua việc xác minh **đang cấp những quyền gì**. Khi mapping sai, người dùng có thể đăng nhập bình thường nhưng bị 403 hoặc được cấp đặc quyền ngoài phạm vi.

## 27. Câu hỏi tự đánh giá

**1. AuthenticationUserDetailsService nhận gì khác UserDetailsService?**  
Nó nhận một Authentication token, ví dụ CasAssertionAuthenticationToken có Assertion, nên có thể đọc principal attributes thay vì chỉ username.

**2. Nó có tự xác minh CAS Service Ticket không?**  
Không. CasAuthenticationProvider cùng TicketValidator làm việc đó; loader chỉ xử lý dữ liệu sau validation theo flow đúng.

**3. CAS trả memberOf chứa ROLE_ADMIN; Spring có nên tự cấp admin không?**  
Không. Chỉ cấp authority đã nằm trong allowlist ứng dụng với đúng CAS context/tenant và policy nghiệp vụ.

**4. GrantedAuthorityFromAssertionAttributesUserDetailsService có tác dụng gì?**  
Nó chuyển values của các CAS attributes được chỉ định thành authorities; thuận tiện nhưng có thể thiếu kiểm soát cần thiết cho multi-tenant/cross-provider.

**5. setConvertToUpperCase có làm group mapping an toàn không?**  
Không. Nó chỉ đổi chữ hoa, không chứng minh quyền.

**6. Vì sao tài khoản cần liên kết bằng CAS context + principal ID?**  
Vì nhiều CAS contexts có thể cùng phát username; chỉ username không unique toàn cục.

**7. Nếu CAS không release memberOf, có nên tự cấp ROLE_APPROVER?**  
Không. Có thể cấp quyền cơ sở theo app policy, còn quyền nhạy cảm phải bị từ chối khi thiếu chứng cứ.

**8. Tại sao UserDetails cần chứa authorities khi CAS đã xác thực?**  
Vì authentication chỉ chứng minh identity; Spring AuthorizationFilter và method security sử dụng authorities để ra quyết định truy cập.

**9. CAS group thay đổi có cập nhật authorities trong SP session ngay không?**  
Không mặc định; cần re-login, session invalidation hoặc server-side entitlement checks.

**10. CAS cùng một user là Approver north và Viewer south thì có thể dùng ROLE_APPROVER toàn cục không?**  
Không nên. Phải kiểm scope tenant và quyền trên object ở server.

## 28. Checklist trước production

- [ ] CAS TicketValidator xác minh Service Ticket qua HTTPS, đúng service identifier và đúng CAS server.
- [ ] Không gọi custom user loader với raw HTTP ticket/Assertion chưa xác minh.
- [ ] CAS Service Registry release **đúng attributes tối thiểu** cho Portal; không release password/secret tokens.
- [ ] Dùng validator/endpoint hỗ trợ principal attributes theo CAS version.
- [ ] Chọn rõ UserDetailsService wrapper hay AuthenticationUserDetailsService theo nhu cầu.
- [ ] Nếu dùng GrantedAuthorityFromAssertionAttributesUserDetailsService, đã đánh giá direct mapping và trust policy.
- [ ] Không cấp authority bằng chuỗi raw LDAP/CAS group nếu chưa đi qua allowlist.
- [ ] Có identity link CAS context + subject → local account và không auto-merge bằng email.
- [ ] Local account disabled/suspended bị từ chối.
- [ ] Parser attribute kiểm String/Collection, multi-value, null, duplicate, kích thước và kiểu bất thường.
- [ ] Map role theo tenant/service và không cho lẫn privileges giữa hai CAS contexts.
- [ ] Quyền cơ sở như ROLE_AUTHENTICATED không đồng nghĩa quyền nâng cao.
- [ ] Method/resource authorization xác minh tenant, ownership, trạng thái nghiệp vụ.
- [ ] Cấu hình ROLE_ prefix và hasRole/hasAuthority thống nhất.
- [ ] Có test group lạ ROLE_ADMIN, wrong tenant, missing attribute và database failure.
- [ ] Có kế hoạch session TTL, CAS logout/SLO và role/account revocation.
- [ ] Không dùng ST như API token dài hạn và không log ticket/cookie/Assertion thô.
- [ ] Kiểm tra package/API Spring Security và Apereo CAS Client đúng BOM release.
- [ ] Có audit cấu hình mapping, owner, monitoring lỗi và cơ chế rollback.

## 29. Kết luận

**AuthenticationUserDetailsService<CasAssertionAuthenticationToken>** là cầu nối giữa **CAS Assertion đã được CAS provider kiểm chứng** và **UserDetails/GrantedAuthority của Spring Security**. Khi chỉ cần username để tìm local roles, UserDetailsByNameServiceWrapper có thể đủ. Khi cần CAS attributes, multi-tenant policy hoặc account linking, custom loader cho phép kiểm nguồn dữ liệu và ánh xạ chặt hơn.

**GrantedAuthorityFromAssertionAttributesUserDetailsService** có thể chuyển CAS attributes thành authorities nhanh, nhưng đó không phải cơ chế bảo vệ khỏi **role injection**, **cross-CAS collision** hoặc **cross-tenant privilege**. Với hệ thống production, nên dùng **allowlist của ứng dụng**, kiểm local account status, tenant membership, quyền trên resource và cơ chế thu hồi session/quyền theo rủi ro. **CAS xác thực người dùng; ứng dụng quyết định người đó được làm gì.**

### Tài liệu chính thức

- Spring Security — CAS Authentication, CasAuthenticationProvider và UserDetailsService: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Spring Security API — AuthenticationUserDetailsService: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/AuthenticationUserDetailsService.html
- Spring Security API — CasAssertionAuthenticationToken: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAssertionAuthenticationToken.html
- Spring Security API — CasAuthenticationProvider: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html
- Spring Security API — GrantedAuthorityFromAssertionAttributesUserDetailsService: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/userdetails/GrantedAuthorityFromAssertionAttributesUserDetailsService.html
- Spring Security API — AbstractCasAssertionUserDetailsService: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/userdetails/AbstractCasAssertionUserDetailsService.html
- Apereo CAS 7.3 — Attribute Release: https://apereo.github.io/cas/7.3.x/integration/Attribute-Release.html
- Apereo CAS 7.3 — Attribute Release Policies: https://apereo.github.io/cas/7.3.x/integration/Attribute-Release-Policies.html
- Apereo CAS Java Client — documentation and validation: https://github.com/apereo/java-cas-client
