# Tìm người dùng, tìm nhóm và ánh xạ quyền LDAP

Trong một ứng dụng tích hợp LDAP hoặc Active Directory (AD), đăng nhập thành công mới chỉ trả lời câu hỏi **người dùng là ai**. Ứng dụng còn phải tìm đúng đối tượng người dùng trong cây thư mục, xác định các nhóm mà đối tượng đó thuộc về, rồi chuyển những thông tin phù hợp thành **GrantedAuthority** để Spring Security thực hiện kiểm soát truy cập. Ba khâu này liên quan nhưng có cấu hình, lỗi và rủi ro khác nhau.

Bài học tập trung vào việc **tìm người dùng, tìm nhóm và ánh xạ quyền LDAP**. Nó minh họa quy trình bằng Spring Security LDAP cho ứng dụng Servlet, đồng thời chỉ rõ khác biệt cần quan tâm khi nguồn thư mục là Microsoft Active Directory.

## 1. Mô hình dữ liệu phải hiểu trước khi tìm kiếm

LDAP lưu dữ liệu trong **Directory Information Tree (DIT)**. Mỗi bản ghi (entry) có một **Distinguished Name (DN)**, một tập thuộc tính và các objectClass cho biết entry tuân theo schema nào.

Ví dụ cây thư mục của tổ chức:

~~~text
dc=example,dc=org                         (base DN)
├── ou=people
│   ├── uid=lan                            (user entry)
│   └── uid=minh                           (user entry)
├── ou=groups
│   ├── cn=app-viewers                      (group entry)
│   └── cn=app-admins                       (group entry)
└── ou=service
    └── cn=ldap-reader                     (service account)
~~~

DN đầy đủ của Lan là **uid=lan,ou=people,dc=example,dc=org**. Phần **uid=lan** là Relative Distinguished Name (RDN); **uid**, **cn**, **ou** và **dc** là những tên thuộc tính có vai trò khác nhau.

| Thành phần | Ý nghĩa thường gặp | Cần phân biệt |
| --- | --- | --- |
| DN | Định danh vị trí duy nhất của entry trong cây thư mục tại thời điểm tìm kiếm | Không đồng nghĩa username do người dùng nhập |
| uid | Tên đăng nhập trong nhiều hệ OpenLDAP | Không phải mọi AD đều dùng uid |
| cn | Common Name của người hoặc nhóm | Có thể thay đổi, không mặc định là ID ứng dụng ổn định |
| ou | Organizational Unit, thường dùng làm nhánh chứa entry | Nhánh của user và group có thể khác nhau |
| member | Danh sách DN thành viên, hay gặp ở groupOfNames và nhóm AD | Thuộc tính nhóm trỏ tới thành viên |
| uniqueMember | Danh sách DN thành viên, hay gặp ở groupOfUniqueNames | Cần filter khác với member |
| memberOf | Liên kết ngược cho biết nhóm trực tiếp của user, khi server/schema cung cấp | Không phải thuộc tính bắt buộc ở mọi LDAP server |
| sAMAccountName / userPrincipalName | Thuộc tính đăng nhập phổ biến của AD | Có thể khác nhau và khác DN |

Ví dụ dữ liệu nhóm (LDIF minh họa hai entry, giả sử các nhánh cha và user đã tồn tại):

~~~ldif
dn: cn=app-viewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: app-viewers
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org

dn: cn=app-admins,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: app-admins
member: uid=lan,ou=people,dc=example,dc=org
~~~

Nếu tìm nhóm có thuộc tính **member** bằng DN của Lan, kết quả là **app-viewers** và **app-admins**. Đó là thông tin thành viên nhóm. Ứng dụng có thể chọn ánh xạ những nhóm này thành quyền xem hoặc quyền quản trị, nhưng LDAP server tự nó không biết quyền nghiệp vụ của HTTP endpoint.

**Không nhầm DN với username:** một người dùng có thể nhập "lan", trong khi bind và group membership sử dụng DN đầy đủ. Trong AD, người đó còn có thể đăng nhập bằng dạng UPN như **lan@corp.example.org**.

## 2. Ba phép xử lý độc lập: tìm user → xác thực → lấy quyền

Luồng thông dụng của Spring Security LDAP:

~~~text
Username/password từ HTTP login
          │
          ▼
TÌM USER theo search base + filter
          │
          ├─ 0 entry / nhiều entry / không có quyền đọc → lỗi cần xử lý
          ▼
Có DN và entry của user
          │
          ▼
XÁC THỰC (thường là bind bằng DN + password)
          │
          ├─ bind thất bại → chưa xác thực
          ▼
TÌM GROUP dưới group search base
          │
          ▼
CHUYỂN GROUP thành GrantedAuthority
          │
          ▼
Authentication chứa principal + authorities
          │
          ▼
Authorization: hasRole / hasAuthority / chính sách nghiệp vụ
~~~

- **User search** tìm *entry nào* tương ứng với tên đăng nhập.
- **Bind authentication** yêu cầu LDAP server kiểm tra credential của entry đó. Tìm thấy entry **không có nghĩa** mật khẩu hợp lệ.
- **Group search** tìm quan hệ thành viên nhóm. Một user hợp lệ có thể không nằm trong nhóm ứng dụng cho phép.
- **Authority mapping** chuyển dữ liệu thư mục thành chuỗi quyền có nghĩa với ứng dụng; chính sách HTTP/method security dùng chuỗi này để ra quyết định.

Spring Security cung cấp riêng **LdapAuthenticator** cho xác thực và **LdapAuthoritiesPopulator** cho lấy quyền. Điều này cho phép thay đổi chiến lược tìm nhóm mà không đổi cơ chế xác thực. Trong phương án bind, mật khẩu không được đọc từ LDAP để tự so sánh trong ứng dụng; LDAP server là nơi kiểm tra credential.

## 3. Tìm người dùng: search base, scope và filter

Một LDAP search được xác định bởi ba yếu tố chính:

1. **Base DN**: bắt đầu tìm từ nhánh nào, ví dụ **ou=people,dc=example,dc=org**.
2. **Search scope**: chỉ entry gốc (base object), con trực tiếp (one-level), hay cả cây con (subtree).
3. **Search filter**: điều kiện chọn entry, ví dụ **(uid=lan)**.

Một số filter LDAP hợp lệ:

~~~ldap
(uid=lan)
(&(objectClass=inetOrgPerson)(uid=lan))
(|(uid=lan)(mail=lan@example.org))
(&(objectCategory=person)(objectClass=user)(sAMAccountName=lan))
~~~

Dòng đầu tìm uid; dòng thứ hai kết hợp objectClass và uid; dòng thứ ba tìm theo một trong hai thuộc tính; dòng cuối là ví dụ hướng AD. Cấu trúc **(&(...)(...))** nghĩa AND, **(|(...)(...))** nghĩa OR. Filter phải phù hợp với schema thực tế; một tên thuộc tính phổ biến không bảo đảm server đó có nó.

Từ Spring Security, có hai cách định vị DN:

| Cách | Thiết lập mẫu | Khi thích hợp |
| --- | --- | --- |
| DN pattern | **uid={0},ou=people** | User nằm tại một vị trí xác định, suy DN được từ login |
| User search | **userSearchBase=ou=people**, **userSearchFilter=(uid={0})** | User có thể ở nhiều nhánh hoặc DN không suy ra trực tiếp từ login |

Trong hai cách, **{0}** đại diện username do người dùng nhập vào cấu hình tìm user. Khi dùng user search, nên có điều kiện đủ đặc thù để tìm đúng **một** user: filter quá rộng có thể khớp người khác, nhiều entry hoặc nhầm tài khoản dịch vụ. Nếu dữ liệu có nhiều nhánh con, xác định chính xác scope của công cụ/provider đang dùng và tránh tìm từ toàn bộ root khi không cần.

Ví dụ thực tế:

~~~text
ContextSource root: dc=example,dc=org
User search base:  ou=people
User search filter: (&(objectClass=inetOrgPerson)(uid={0}))
Login:              lan
Result DN:          uid=lan,ou=people,dc=example,dc=org
~~~

Với DN pattern, cấu hình **uid={0},ou=people** cho phép dựng đường dẫn trực tiếp mà không nhất thiết tìm user toàn cây; nó không phù hợp nếu user có OU thay đổi hoặc username không phải thành phần RDN.

**Tránh LDAP injection:** không viết filter bằng phép nối chuỗi tùy ý như **"(uid=" + input + ")"**. Ký tự đặc biệt ***, **(**, **)**, dấu gạch chéo ngược và NUL có ý nghĩa trong LDAP filter. Hãy dùng tham số thay thế hoặc API filter builder/escaping của Spring LDAP, giới hạn input hợp lệ, và phân biệt **escape giá trị filter** với **escape giá trị DN**. Một filter tự xây chứa input không được escape có thể mở rộng số entry khớp hoặc làm truy vấn sai.

## 4. Tìm nhóm: quan hệ thành viên trực tiếp

Với schema **groupOfNames**, mỗi group có thể có một hay nhiều thuộc tính **member** trỏ tới DN của user hoặc group khác. Để tìm nhóm của Lan trong ví dụ, truy vấn:

~~~ldap
(&(objectClass=groupOfNames)(member=uid=lan,ou=people,dc=example,dc=org))
~~~

Vùng tìm kiếm hợp lý là **ou=groups,dc=example,dc=org**. Kết quả trả về các group có **member** khớp DN trên.

Với schema **groupOfUniqueNames**, dùng **uniqueMember** thay cho **member**:

~~~ldap
(&(objectClass=groupOfUniqueNames)(uniqueMember=uid=lan,ou=people,dc=example,dc=org))
~~~

Trong **DefaultLdapAuthoritiesPopulator** của Spring Security:

- **groupSearchBase** là đường dẫn tìm nhóm tương đối với base DN của ContextSource. Ví dụ ContextSource root **dc=example,dc=org** thì groupSearchBase **ou=groups**.
- **groupSearchFilter** là LDAP filter tìm membership. **{0}** là **DN đầy đủ của user**; **{1}** có thể dùng làm **username**. Không dùng **{1}** cho thuộc tính member chứa DN nếu dữ liệu thực tế lưu DN.
- **groupRoleAttribute** quyết định thuộc tính nào của group được đọc làm tên quyền. Mặc định là **cn**.
- **rolePrefix** mặc định **ROLE_**; **convertToUpperCase** mặc định **true**.
- **searchSubtree** mặc định **false** (chỉ một cấp dưới base). Đặt **true** nếu groups được tổ chức theo OU lồng nhau và cần tìm toàn subtree.

Lấy groupName từ **cn** chỉ là cách mặc định. Hệ thống thực tế có thể dùng thuộc tính khác hoặc bảng mapping do ứng dụng kiểm soát; việc đổi nhãn nhóm trong directory có thể ảnh hưởng quyền nếu dùng tên nhóm làm role trực tiếp.

## 5. Kết quả LDAP và kết quả Spring Security không cùng loại

Giả sử user **lan** thuộc:

~~~text
DN nhóm 1: cn=app-viewers,ou=groups,dc=example,dc=org
DN nhóm 2: cn=app-admins,ou=groups,dc=example,dc=org
Thuộc tính cn: app-viewers, app-admins
~~~

Nếu populator dùng **groupRoleAttribute=cn**, **rolePrefix=ROLE_**, **convertToUpperCase=true**, Spring Security tạo authority dự kiến:

~~~text
ROLE_APP-VIEWERS
ROLE_APP-ADMINS
~~~

Có ba điểm đáng nhớ:

1. **GrantedAuthority** là tên quyền dạng chuỗi. Nó chưa tự biết được "xem báo cáo" hay "quản trị người dùng" trừ khi policy của ứng dụng sử dụng/ánh xạ nó.
2. **hasRole("APP-ADMINS")** trong cấu hình mặc định tìm authority **ROLE_APP-ADMINS**; **hasAuthority("ROLE_APP-ADMINS")** so sánh chuỗi trực tiếp. Việc thay rolePrefix hoặc cấu hình mặc định của biểu thức bảo mật có thể đổi kết quả.
3. Nếu tổ chức đổi tên group, dùng cùng chuỗi group CN trong application policy có thể làm thay đổi hành vi. Với quyền nhạy cảm, một **allowlist ánh xạ group DN/ID đã được kiểm soát → authority nghiệp vụ** thường rõ ràng hơn việc cấp mọi group CN thành quyền được dùng trực tiếp.

Ví dụ ánh xạ theo chính sách ứng dụng:

| Group tìm được | Quyền nghiệp vụ quyết định cấp | Ý nghĩa |
| --- | --- | --- |
| app-viewers | REPORT_READ | Đọc báo cáo |
| app-admins | REPORT_ADMIN | Quản trị báo cáo |
| engineering-general | Không cấp quyền đặc biệt | Nhóm nhân sự không tự động có quyền ứng dụng |
| unknown-group | Không cấp quyền | Mặc định không mở rộng quyền cho nhóm chưa duyệt |

Nếu quy ước ứng dụng sử dụng vai trò, các authority kết quả có thể là **ROLE_REPORT_READ** và **ROLE_REPORT_ADMIN**. Không nên hiểu group **app-admins** đương nhiên là quyền admin trên mọi resource.

## 6. Ví dụ Spring Boot + Spring Security: tìm user và group

Ví dụ dưới đây dành cho **ứng dụng Spring Boot Servlet có Spring Security LDAP**. Nó là cấu hình Java có thể đưa vào một ứng dụng Spring Boot đã tạo sẵn; cần LDAP server với schema và credential phù hợp. Đây **không phải chương trình chạy độc lập chỉ bằng javac**.

Phụ thuộc Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    implementation("org.springframework.security:spring-security-ldap")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Với dự án Gradle Groovy DSL, chuyển cú pháp dependency tương ứng. Sử dụng dependency management của Spring Boot để quản lý phiên bản đồng bộ thay vì tự trộn phiên bản Spring LDAP/Security.

**application.yml**:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=ldap-reader,ou=service,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Đây là cấu hình có thể dùng khi môi trường cung cấp LDAP server thật, tài khoản đọc hợp lệ và biến môi trường **LDAP_BIND_PASSWORD**. Server cần chứng thư TLS được JVM tin cậy; không vô hiệu hóa việc xác minh chứng thư để làm cho kết nối "chạy được".

Tệp **LdapAuthenticationConfig.java** (đặt vào package được Spring Boot quét):

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;

@Configuration(proxyBeanMethods = false)
public class LdapAuthenticationConfig {

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {

        var groups = new DefaultLdapAuthoritiesPopulator(
                contextSource, "ou=groups");

        groups.setGroupSearchFilter(
                "(&(objectClass=groupOfNames)(member={0}))");
        groups.setGroupRoleAttribute("cn");
        groups.setSearchSubtree(true);
        groups.setRolePrefix("ROLE_");
        groups.setConvertToUpperCase(true);

        var factory = new LdapBindAuthenticationManagerFactory(contextSource);
        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter(
                "(&(objectClass=inetOrgPerson)(uid={0}))");
        factory.setLdapAuthoritiesPopulator(groups);

        return factory.createAuthenticationManager();
    }
}
~~~

Đoạn cấu hình trên dùng các API phổ biến của Spring Security 5.7+ và tương thích với dòng Spring Security 6.x khi dùng dependency phù hợp. Nó hoạt động theo thứ tự: tìm user dưới **ou=people** với **uid**, bind để xác thực credential, tìm group dưới **ou=groups** có **member** là DN người dùng, chuyển **cn** thành authority có tiền tố **ROLE_**. Nếu directory dùng **uniqueMember**, phải đổi filter cho phù hợp. Nếu group nằm trực tiếp trong **ou=groups** thì searchSubtree(true) không bắt buộc; bật nó chỉ khi cần bao phủ OU con.

Trong ứng dụng Servlet có thể kiểm tra role khi cấu hình HTTP:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(requests -> requests
                    .requestMatchers("/reports/admin/**")
                    .hasAuthority("ROLE_APP-ADMINS")
                    .requestMatchers("/reports/**")
                    .hasAnyAuthority("ROLE_APP-VIEWERS", "ROLE_APP-ADMINS")
                    .anyRequest().authenticated())
            .formLogin(org.springframework.security.config.Customizer.withDefaults())
            .build();
}
~~~

Đây là **mảnh phương thức @Bean**, thêm vào lớp cấu hình có các import **org.springframework.security.config.annotation.web.builders.HttpSecurity**, **org.springframework.security.web.SecurityFilterChain** và **org.springframework.context.annotation.Bean**. Bảo đảm AuthenticationManager LDAP được dùng bởi HTTP authentication mechanism thích hợp; khi ứng dụng có nhiều AuthenticationProvider/AuthenticationManager cần cấu hình rõ thứ tự và phạm vi. Một user xác thực thành công nhưng không thuộc hai nhóm được phép sẽ không truy cập được /reports/**.

Ví dụ này dành cho **Servlet**; các API **AuthenticationManager** và **SecurityFilterChain** đồng bộ không được sao chép nguyên xi vào pipeline **WebFlux**. Nếu yêu cầu xác thực trực tiếp với LDAP trong reactive stack, phải xét bản chất I/O chặn của thư viện LDAP/JNDI và thiết kế adapter/lịch chạy phù hợp, tránh gọi LDAP blocking trên event-loop.

## 7. Ánh xạ group thành quyền nghiệp vụ có kiểm soát

Đôi khi ứng dụng không muốn mang nguyên tên group LDAP vào chính sách. Ví dụ tổ chức đặt tên nhóm **app-viewers** nhưng ứng dụng muốn quyền **ROLE_REPORT_READ**. Có thể cấu hình **GrantedAuthoritiesMapper** ở factory sau khi populator lấy nhóm, hoặc triển khai **LdapAuthoritiesPopulator** riêng nếu dữ liệu cần truy vấn/ghép từ nhiều nguồn.

Một đoạn mapper có thể gắn sau khi thiết lập factory (phần thân của phương thức cấu hình ở mục 6):

~~~java
factory.setAuthoritiesMapper(loaded -> {
    java.util.Map<String, String> allowlist = java.util.Map.of(
            "ROLE_APP-VIEWERS", "ROLE_REPORT_READ",
            "ROLE_APP-ADMINS", "ROLE_REPORT_ADMIN");

    return loaded.stream()
            .map(org.springframework.security.core.GrantedAuthority::getAuthority)
            .map(allowlist::get)
            .filter(java.util.Objects::nonNull)
            .distinct()
            .map(org.springframework.security.core.authority.SimpleGrantedAuthority::new)
            .toList();
});
~~~

Đặt đoạn này **trước** lời gọi **factory.createAuthenticationManager()**. Đây là **mảnh mã có ngữ cảnh**; dự án cần các import như ở mục 6. Trong mapping trên, nếu group không nằm trong allowlist thì **không tạo authority** từ group đó. Cẩn thận: một mapping dạng "drop toàn bộ group chưa biết" có thể khiến user không còn quyền truy cập tính năng cơ bản; đó là lựa chọn policy có chủ đích, cần test.

Với quyền nhạy cảm, nên cân nhắc map từ **DN hoặc ID nhóm ổn định** thay vì CN dễ trùng/đổi tên. DefaultLdapAuthoritiesPopulator theo cn ở ví dụ là điểm khởi đầu để hiểu cơ chế. Muốn ánh xạ theo DN, cần lấy được định danh nhóm từ nguồn dữ liệu, chuẩn hóa và kiểm tra chính sách trước khi trả GrantedAuthority; không mặc định giả định CN có tính duy nhất trên toàn cây LDAP.

### Chương trình Java 17 độc lập mô phỏng mapping

Ví dụ bên dưới chỉ mô phỏng **bước ánh xạ**, không gọi LDAP hay thực hiện xác thực. Có thể lưu thành **LdapRoleMappingDemo.java** rồi chạy với Java 17+:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class LdapRoleMappingDemo {
    public static void main(String[] args) {
        Map<String, String> allowedGroups = Map.of(
                "app-viewers", "ROLE_REPORT_READ",
                "app-admins", "ROLE_REPORT_ADMIN");

        List<String> ldapGroupCns = List.of(
                "app-viewers", "engineering-general", "app-admins");

        var authorities = ldapGroupCns.stream()
                .map(allowedGroups::get)
                .filter(Objects::nonNull)
                .collect(Collectors.toCollection(TreeSet::new));

        System.out.println("Authorities: " + authorities);
        System.out.println("Can read: " +
                authorities.contains("ROLE_REPORT_READ"));
        System.out.println("Unknown group granted: " +
                authorities.contains("ROLE_ENGINEERING_GENERAL"));
    }
}
~~~

Lệnh:

~~~bash
javac LdapRoleMappingDemo.java
java LdapRoleMappingDemo
~~~

Stdout chính xác:

~~~text
Authorities: [ROLE_REPORT_ADMIN, ROLE_REPORT_READ]
Can read: true
Unknown group granted: false
~~~

Dùng TreeSet khiến thứ tự in ra xác định theo bảng chữ cái. Trong thực tế, các quyền sẽ được bọc trong các đối tượng **GrantedAuthority** và gắn lên **Authentication** sau khi xác thực; đừng dùng ví dụ mô phỏng để bỏ qua kiểm tra credential.

## 8. Active Directory: tên đăng nhập và danh sách nhóm khác OpenLDAP mẫu

AD sử dụng LDAP nhưng có những quy ước riêng. Một vài trường hợp phổ biến:

| Khía cạnh | OpenLDAP theo ví dụ bài | Active Directory thường gặp |
| --- | --- | --- |
| Tên login | uid | sAMAccountName hoặc userPrincipalName |
| DN user | uid=lan,ou=people,... | CN=Lan Tran,OU=Users,DC=corp,... |
| Group schema | groupOfNames, member hoặc groupOfUniqueNames, uniqueMember | group với member; user thường có memberOf |
| Kết nối xác thực | Bind theo DN sau user search | Thường đăng nhập bằng UPN user@domain |
| Provider tiện dụng | LdapBindAuthenticationManagerFactory | ActiveDirectoryLdapAuthenticationProvider |

Spring Security cung cấp **ActiveDirectoryLdapAuthenticationProvider** cho thiết lập AD thông dụng. Ví dụ bean cấu hình (đoạn mã chạy trong ứng dụng Spring, dùng ldaps URL thực tế):

~~~java
@Bean
ActiveDirectoryLdapAuthenticationProvider activeDirectoryProvider() {
    return new ActiveDirectoryLdapAuthenticationProvider(
            "corp.example.org", "ldaps://ad.corp.example.org:636/");
}
~~~

Cần import **org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider** và **org.springframework.context.annotation.Bean**. Provider có thể dùng UPN hoặc searchFilter tùy chỉnh và mặc định lấy authority từ thuộc tính **memberOf** của user. Điều này khác với cách truy vấn nhóm bằng **DefaultLdapAuthoritiesPopulator** trong phần OpenLDAP: không thể giả định chúng có cùng default search base/filter, cách mở rộng nhóm hoặc định dạng role.

Khi cần ánh xạ khác, xem xét **setAuthoritiesPopulator(...)**, **setAuthoritiesMapper(...)** và **setSearchFilter(...)** trên provider theo đúng phiên bản đang chạy. Kiểm tra giá trị Authentication.authorities thực tế trong test trước khi viết các policy như hasRole hoặc hasAuthority; không suy diễn từ tên AD group rồi tự cho rằng có sẵn chuỗi quyền đó.

### Hai ví dụ truy vấn AD

Tìm tài khoản theo sAMAccountName:

~~~ldap
(&(objectCategory=person)(objectClass=user)(sAMAccountName=lan))
~~~

Tìm nhóm trực tiếp chứa DN của user:

~~~ldap
(&(objectCategory=group)(member=CN=Lan Tran,OU=Users,DC=corp,DC=example,DC=org))
~~~

Phải dùng **đúng DN thực tế** do directory trả về. Trong AD, thuộc tính **memberOf** có thể hữu ích để đọc các nhóm trực tiếp; một số quan hệ như **primary group** không được phản ánh theo cách đơn giản trong memberOf. Các group có thể nằm ở nhiều OU, domain hoặc security scope khác nhau; dùng một search base quá hẹp có thể bỏ sót.

## 9. Nhóm lồng nhau: membership trực tiếp không đủ

Ví dụ:

~~~text
User lan
  └── member của "team-backend"
        └── "team-backend" là member của "app-admins"
~~~

Tìm group bằng **(member={0})** với {0}=DN của Lan sẽ nhìn thấy **team-backend**. Truy vấn này **không tự suy ra** Lan là thành viên gián tiếp của **app-admins**.

Các chiến lược cần cân nhắc:

1. **Không hỗ trợ nested group:** chỉ nhóm trực tiếp cấp quyền. Đơn giản, dễ audit; cần viết rõ cho đội quản trị directory.
2. **NestedLdapAuthoritiesPopulator:** Spring Security cung cấp lớp có thể tìm nhóm lồng nhau dạng static; cần kiểm tra group schema, groupSearchBase, giới hạn độ sâu và chi phí truy vấn.
3. **AD matching rule in chain:** với AD hỗ trợ, filter mở rộng cho member ở nhóm có thể là **(member:1.2.840.113556.1.4.1941:={0})**, trong đó {0} phải được thay bằng DN user theo cơ chế escaping của thư viện. Đây là tính năng riêng AD, không phải LDAP tiêu chuẩn hỗ trợ ở mọi server.
4. **Chính sách nhóm/role của ứng dụng:** có thể chỉ cho phép vài nhóm bảo mật được duyệt và không mở rộng tự động tất cả nested memberships.

Matching rule in chain đi qua đường liên kết DN và có thể làm truy vấn nặng trên cây lớn. Cần đo độ trễ, kiểm tra giới hạn phân trang/referral và xác minh quyền của search account. Không bật duyệt đệ quy tất cả nhóm chỉ vì dữ liệu có OU lồng nhau: **searchSubtree(true)** chỉ thay search scope (phạm vi entry), không tự động duyệt quan hệ member-of theo đồ thị nhóm.

Cũng không mặc định một nhóm AD bất kỳ là **security group** hợp lệ để cấp quyền. Chính sách có thể cần lọc theo thuộc tính nhóm, domain tin cậy hoặc danh sách nhóm được kiểm soát, thay vì biến mọi distribution group thành quyền truy cập.

## 10. Search, bind và authorization cần tài khoản/quyền truy cập khác nhau

Một tích hợp LDAP sản xuất thường có hai loại danh tính:

- **Search/bind account của ứng dụng:** tài khoản dịch vụ dùng để tra DN/thuộc tính (nếu directory không cho anonymous search). Cấp quyền đọc tối thiểu vào nhánh cần thiết; không dùng domain admin. Credentials phải nằm trong secret manager hoặc biến môi trường và thay đổi được.
- **User account đang đăng nhập:** LDAP server xác thực mật khẩu qua bind hoặc cơ chế được cấu hình. Kết quả xác thực không đồng nghĩa search account có quyền xem mọi thuộc tính nhóm.

Tài khoản service tìm được entry nhưng không đọc được **member**, **memberOf** hoặc group dưới OU nhất định sẽ dẫn tới quyền rỗng/thiếu tùy thiết kế. Phân biệt trường hợp "user sai mật khẩu" với "user đúng nhưng không có nhóm phù hợp" và "LDAP không thể truy vấn nhóm"; chúng là những lớp lỗi khác nhau.

Ở cấp mạng, ưu tiên **LDAPS hoặc StartTLS có xác minh chứng thư**, timeout kết nối/đọc hợp lý, kết nối tới directory đáng tin, không ghi mật khẩu/token trong log, giới hạn số kết quả và quyền đọc. Không triển khai LDAP filter qua phép nối input, không tin group name do client gửi, và không sử dụng giá trị request parameter để tự cấp GrantedAuthority.

## 11. Thử trực tiếp truy vấn để xác nhận cấu hình

Dùng công cụ **ldapsearch** trên máy phát triển hoặc môi trường kiểm thử có quyền truy cập LDAP. Đối với một server tương thích OpenLDAP, ví dụ tìm user:

~~~bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "cn=ldap-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  "(&(objectClass=inetOrgPerson)(uid=lan))" dn uid cn
~~~

Công cụ sẽ hỏi password do tham số **-W**, giúp tránh đưa password trực tiếp vào command history. Kết quả đúng theo dữ liệu minh họa có thể chứa:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
uid: lan
cn: Lan Tran
~~~

Để tìm nhóm:

~~~bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "cn=ldap-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=groups,dc=example,dc=org" \
  "(&(objectClass=groupOfNames)(member=uid=lan,ou=people,dc=example,dc=org))" \
  dn cn
~~~

Trong dữ liệu nhóm minh họa, bạn mong đợi hai DN nhóm **app-viewers** và **app-admins**. Đây là **kết quả kỳ vọng có điều kiện trên dữ liệu ví dụ**, không phải stdout đã quan sát từ một LDAP server thật. Nếu không có LDAP server, các lệnh trên sẽ không có kết quả đúng để đối chiếu.

Trình tự kiểm tra hữu ích:

1. Xác minh kết nối/TLS và tài khoản dịch vụ có quyền search.
2. Chạy truy vấn user; kết quả phải khớp duy nhất một entry với DN kỳ vọng.
3. Dùng DN đó truy vấn group; kiểm tra member/uniqueMember và phạm vi tìm kiếm.
4. Thử bind bằng credential của user ở môi trường kiểm thử, xác minh credential đúng/sai cho kết quả khác nhau.
5. Qua Spring Security, xác nhận danh sách authority trên Authentication và policy trên endpoint.

Ở production, tránh log toàn bộ entry người dùng vì có thể chứa email, số điện thoại hoặc thuộc tính nhạy cảm; nếu cần log chẩn đoán thì ưu tiên mã lỗi, số lượng kết quả, tên chính sách và correlation ID.

## 12. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và sửa |
| --- | --- | --- |
| User tồn tại nhưng không tìm thấy | Sai userSearchBase, dùng uid thay vì sAMAccountName, scope không bao phủ nhánh | Chạy LDAP search bằng đúng filter/base; đọc DN thực tế |
| Tìm được user nhưng bind thất bại | Sai password, account disabled/expired, chính sách AD, DN/UPN sai | Tách bước search và bind, xem mã lỗi an toàn |
| Login thành công nhưng authorities rỗng | Sai groupSearchBase, member/uniqueMember không khớp, account đọc thiếu quyền | Thử filter group bằng DN user và kiểm tra ACL |
| Chỉ thấy nhóm trực tiếp | Chưa xử lý nested membership | Dùng chiến lược nested rõ ràng; test hai cấp hoặc hơn |
| Người dùng có nhóm nhưng bị 403 | ROLE_ prefix, uppercase, mapping hoặc biểu thức hasRole/hasAuthority không khớp | So sánh chuỗi GrantedAuthority chính xác với policy |
| Quyền quá rộng | Mọi group CN được coi như role, search base quá rộng, mapping tùy tiện | Dùng allowlist hoặc DN/ID nhóm và nguyên tắc least privilege |
| Query chậm | Scope subtree quá rộng, filter không chọn lọc, nested group nhiều cấp, referral | Thu hẹp base/filter, xem index và đo latency, giới hạn mở rộng |
| Quyền không đổi ngay sau khi cập nhật group | Authentication cũ/cached authorities, token/session chưa được cấp lại | Xác định thời điểm cập nhật quyền và cơ chế re-auth/refresh |
| Có username trùng nhau | Search base quá rộng hoặc thuộc tính không duy nhất | Dùng thuộc tính định danh phù hợp và kiểm tra ambiguity |

**403 và 401 có ý nghĩa khác nhau:** tùy HTTP mechanism/chính sách của ứng dụng, 401 thường chỉ request chưa xác thực được còn 403 thường là đã xác thực nhưng không đủ quyền. Không sửa lỗi "thiếu nhóm" bằng cách mở toàn bộ endpoint cho mọi user đã đăng nhập.

## 13. Kiểm thử tích hợp tối thiểu phải bao phủ điều gì?

Một bộ kiểm thử đủ tin cậy cần kiểm tra cả danh tính lẫn quyền:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Một user hợp lệ trong group app-viewers | Đăng nhập được và có authority của nhóm xem |
| Cùng user, password sai | Không xác thực thành công |
| Username không tồn tại | Không xác thực thành công, không phát sinh authority |
| User hợp lệ nhưng không ở nhóm ứng dụng | Có thể xác thực được nhưng không truy cập endpoint cần role |
| User có nhóm app-admins | Được cấp đúng quyền của nhóm; không tự cấp thêm quyền khác |
| User chỉ thuộc nhóm cha qua một nhóm con | Kết quả phụ thuộc chiến lược nested đã định nghĩa, được test rõ |
| Hai user khác nhóm | Không dùng chung hoặc tái sử dụng nhầm authorities |
| Nhóm bị gỡ hoặc tài khoản bị khóa | Quyền/trạng thái mới xuất hiện ở thời điểm re-auth/refresh như đã thiết kế |
| User có giá trị login chứa ký tự đặc biệt | Không làm thay đổi filter ngoài giá trị được escape; hành vi từ chối/chấp nhận theo policy |
| Directory chậm/mất kết nối | Fail closed đối với endpoint yêu cầu xác thực, không cấp quyền mặc định |

Sử dụng LDAP test directory (ví dụ embedded directory hoặc môi trường kiểm thử cô lập) với LDIF dữ liệu nhỏ và xác định. Mỗi test nên quan sát **DN user được chọn**, **nhóm tìm được**, **authorities thực tế**, rồi **quyết định truy cập**; chỉ assert HTTP 200 sau một login thành công sẽ không phát hiện sai scope hoặc role mapping.

Đối với AD, dùng một test môi trường tương thích AD vì các thuộc tính **userPrincipalName**, **memberOf**, **groupType**, nested matching rule và primary-group semantics không thể được chứng minh đầy đủ chỉ bằng OpenLDAP embedded.

## 14. Nguyên tắc thực hành và kết luận

Khi triển khai tìm người dùng, tìm nhóm và ánh xạ quyền LDAP, hãy xác định trước **schema thực tế**, **base DN**, **thuộc tính username**, **thuộc tính membership** và **chuỗi GrantedAuthority mà ứng dụng mong đợi**. Tìm user là truy vấn directory, bind là kiểm tra credential, tìm group là đọc quan hệ thành viên, còn authorization là quyết định của ứng dụng.

Một quy trình chắc chắn là **login → tìm đúng một user DN → xác thực → tìm nhóm theo schema → ánh xạ allowlist thành authority → kiểm tra quyền trên resource**. Kiểm thử từng ranh giới và đừng để cấu hình mặc định biến danh sách group tùy ý thành đặc quyền cao.

### Tài liệu tham khảo chính thức

- Spring Security – LDAP Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html
- Spring Security – DefaultLdapAuthoritiesPopulator API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/userdetails/DefaultLdapAuthoritiesPopulator.html
- Spring Security – AbstractLdapAuthenticationManagerFactory API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/ldap/AbstractLdapAuthenticationManagerFactory.html
- Spring Security – ActiveDirectoryLdapAuthenticationProvider API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html
- Spring Security – NestedLdapAuthoritiesPopulator API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/userdetails/NestedLdapAuthoritiesPopulator.html
- Microsoft Learn – LDAP Search Filter Syntax and matching rules: https://learn.microsoft.com/en-us/windows/win32/adsi/search-filter-syntax
