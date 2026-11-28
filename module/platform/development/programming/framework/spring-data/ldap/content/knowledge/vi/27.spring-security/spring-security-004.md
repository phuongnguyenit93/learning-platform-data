# Vai trò tài khoản dịch vụ trong tìm kiếm người dùng

Khi người dùng đăng nhập vào một ứng dụng Spring Boot bằng tài khoản LDAP, ứng dụng thường chỉ nhận được **tên đăng nhập** như `lan` và **mật khẩu** do người dùng cung cấp. Trong khi đó, thao tác LDAP bind thường cần một **Distinguished Name (DN)** đầy đủ, chẳng hạn `uid=lan,ou=people,dc=example,dc=org`. Ai sẽ tìm ra DN của Lan khi ứng dụng chưa xác thực được Lan? Đây là một vai trò phổ biến của **tài khoản dịch vụ (service account, còn gọi là manager/bind account)**.

Trong chương **Spring Security** của module **SPRING_DATA_LDAP**, cần phân biệt hai luồng: **Spring Security LDAP** tìm danh tính, kiểm tra credential và nạp quyền cho request; **Spring Data LDAP** dùng repository/`LdapTemplate` để đọc, tìm kiếm và CRUD entry theo DN, `objectClass` và schema. Hai luồng có thể dùng cùng directory, nhưng không được nhầm **tài khoản kết nối dịch vụ** với **người dùng đang đăng nhập**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích tại sao một ứng dụng có thể cần service account để **tìm entry/DN trước khi xác thực** người dùng.
2. Phân biệt **bind tìm kiếm bằng service account**, **bind kiểm tra mật khẩu bằng user DN**, **tìm nhóm quyền** và **truy cập entry bằng repository**.
3. Xác định trường hợp không cần tài khoản tìm kiếm (ví dụ biết chính xác DN pattern), đồng thời hiểu hạn chế của cách này.
4. Cấu hình Spring Boot/Spring Security LDAP để tìm người dùng theo `uid` mà không đọc hay tự so sánh thuộc tính mật khẩu.
5. Thiết kế quyền LDAP tối thiểu, TLS, quản lý secret, giới hạn search base/filter và chính sách phân quyền API.
6. Kiểm thử riêng bind tài khoản dịch vụ, user search, user bind, group search và authorization; phân loại lỗi chính xác.

## 2. Mô hình cây và các danh tính liên quan

Giả sử một directory thử nghiệm có cấu trúc:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=groups
│   └── cn=DIRECTORY_READER
└── ou=services
    └── cn=app-auth-search
~~~

Những danh tính/giá trị sau có thể cùng xuất hiện trong một request đăng nhập:

| Danh tính hoặc giá trị | Ví dụ | Dùng để làm gì? |
| --- | --- | --- |
| **Tên đăng nhập từ client** | `lan` | Thông tin người dùng khai báo; chưa được xác thực. |
| **DN service account** | `cn=app-auth-search,ou=services,dc=example,dc=org` | Bind vào directory để tìm entry người dùng và, khi cần, tìm nhóm. |
| **DN thực của người dùng** | `uid=lan,ou=people,dc=example,dc=org` | Đích của phép **user bind authentication** sau khi tìm thấy entry. |
| **Credential người dùng** | Mật khẩu được gửi qua kênh đăng nhập an toàn. | Được sử dụng để thử bind dưới DN người dùng; không phải mật khẩu service account. |
| **Authority trong Spring Security** | `ROLE_DIRECTORY_READER` | Quyền mà ứng dụng dùng để cho phép hoặc từ chối endpoint. |
| **DN tài khoản truy cập dữ liệu** | Có thể là `cn=app-data-reader,...` | Bind của `LdapTemplate`/repository để đọc entry nghiệp vụ, nếu được cấu hình riêng. |

**Service account không phải tài khoản đại diện cho mọi người dùng ở tầng nghiệp vụ.** Nó là một danh tính kỹ thuật được directory cấp quyền cụ thể. Một thao tác search được thực hiện thành công bởi `app-auth-search` không chứng tỏ người gọi HTTP là `lan`.

### Entry minh họa

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
~~~

Nhánh nhóm có thể chứa:

~~~ldif
dn: cn=DIRECTORY_READER,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: DIRECTORY_READER
uniqueMember: uid=lan,ou=people,dc=example,dc=org
~~~

Các LDIF trên mô tả schema minh họa, không phải cấu hình chung cho mọi directory. Với Active Directory, user có thể có RDN `cn`, tên đăng nhập nằm ở `sAMAccountName`, nhóm sử dụng `member` hoặc đặc điểm khác. Cần kiểm tra schema và ACL thật trước khi thiết kế user search.

## 3. Tại sao chưa đăng nhập vẫn cần tìm người dùng?

Một request có thể chỉ mang username `lan`, nhưng DN có thể:

- Nằm trong `ou=people` hoặc các OU con theo bộ phận.
- Dùng `cn` làm RDN thay vì `uid`, ví dụ `cn=Lan Nguyen,ou=employees,dc=example,dc=org`.
- Thay đổi do rename hoặc move entry, mặc dù username vẫn giống nhau.
- Được xác định thông qua thuộc tính như `uid`, `userPrincipalName` hoặc `sAMAccountName` tùy directory.

Vì vậy, không phải ứng dụng nào cũng biết cách xây DN từ username bằng một mẫu cố định. Trong **search-based bind authentication**, Spring Security cần một context có khả năng **đọc/tìm entry trước khi user bind được xác thực**.

~~~mermaid
flowchart TD
    A["HTTP login: username + password"] --> B["Spring Security LDAP authentication"]
    B --> C["Service bind: app-auth-search"]
    C --> D["Search uid=lan trong ou=people"]
    D --> E{"Tìm được đúng một DN phù hợp?"}
    E -- "Không" --> F["Xác thực thất bại / lỗi tìm kiếm phù hợp"]
    E -- "Có" --> G["Bind với DN của user + mật khẩu vừa nhập"]
    G --> H{"Directory chấp nhận user bind?"}
    H -- "Không" --> I["Xác thực thất bại"]
    H -- "Có" --> J["Tìm nhóm/authority theo cấu hình"]
    J --> K["Spring Security Authentication"]
    K --> L{"User có quyền gọi API?"}
    L -- "Không" --> M["Từ chối: HTTP 403 khi đã xác thực"]
    L -- "Có" --> N["Controller / Service"]
    N --> O["Spring Data LDAP Repository / LdapTemplate"]
    O --> P["Directory kiểm tra ACL của bind dùng cho data access"]
~~~

**Điểm then chốt:** service account giúp *xác định DN*; **phép bind dưới danh tính người dùng với mật khẩu được cung cấp** mới là bước xác thực trong cấu hình bind authentication. Việc tìm được entry không đủ để đăng nhập.

### Ai thực hiện từng thao tác?

| Bước | Ai đang bind với LDAP? | Kết quả cần kiểm tra |
| --- | --- | --- |
| Tìm DN theo `uid=lan` | Service account dùng trong `ContextSource` tìm kiếm. | Tìm được entry trong search base, có thể đọc DN. |
| Xác thực mật khẩu | Kết nối/context được tạo để bind dưới **DN của Lan**. | Directory chấp nhận hoặc từ chối credential của Lan. |
| Tra cứu nhóm | Thường là service account/manager context theo cấu hình authorities populator. | Membership được ánh xạ thành `GrantedAuthority`. |
| `PersonRepository.findByUid("lan")` | Bind account của context dùng cho **data access**. | Entry dữ liệu được trả về nếu filter, base và ACL cho phép. |

Chi tiết context được tạo/reuse phụ thuộc phiên bản Spring Security LDAP và các thành phần đã cấu hình. Đừng suy rằng mọi thao tác LDAP đều tự động “mang theo” credential của người gọi HTTP.

## 4. Những quyền tối thiểu service account thực sự cần

Đối với **search-based bind authentication**, tài khoản kỹ thuật thường cần:

1. Có quyền **bind** theo chính sách directory.
2. Có quyền **search** ở nhánh người dùng mà ứng dụng hỗ trợ, ví dụ `ou=people`.
3. Có quyền đọc những thuộc tính cần cho việc định vị và ánh xạ danh tính (tùy server/cách tìm kiếm), chẳng hạn `uid` và DN của entry được trả về.
4. Nếu dùng cùng context để tra cứu nhóm, có quyền search/read trên nhánh `ou=groups` và những attribute membership cần thiết như `uniqueMember`.

Nó **không cần**:

- Đọc `userPassword` chỉ để dùng cơ chế **bind authentication**.
- Quyền sửa mật khẩu, vô hiệu hóa tài khoản, thêm người dùng vào nhóm quản trị.
- Quyền đọc toàn bộ directory, entry dịch vụ khác hoặc dữ liệu nhạy cảm không liên quan.
- Quyền tạo/xóa entry nếu nhiệm vụ chỉ là search.

Các quyền cụ thể do LDAP server thực thi qua ACL. Một tài khoản có thể bind thành công nhưng search trả kết quả rỗng hoặc lỗi `insufficientAccessRights` vì không được xem entry/thuộc tính tương ứng.

### Khác biệt quan trọng: search DN và đọc password

Nếu service account đọc `uid=lan` và DN của Lan, đây là **truy vấn định danh**. Trong **bind authentication**, Spring Security thử xác thực trực tiếp với server bằng DN + mật khẩu Lan cung cấp; ứng dụng không cần đọc hash mật khẩu từ entry, cũng không tự so sánh `userPassword` bằng chuỗi.

Spring Security có thể hỗ trợ mô hình **password comparison** trong những cấu hình riêng, nhưng đó là cơ chế khác với user bind. Không dùng password comparison như một cách “sửa nhanh” khi search account thiếu quyền hoặc bind authentication đang cấu hình sai; phải hiểu schema, hashing, policy và an toàn credential trước khi chọn.

## 5. Cấu hình Spring Boot và Spring Security LDAP

Ví dụ dùng **Spring Boot 3.x / Spring Security 6.x** về mặt cách tổ chức API. Đối chiếu phiên bản chính xác trong dự án trước khi triển khai. Directory mẫu sử dụng `uid` trong `ou=people` và `groupOfUniqueNames` trong `ou=groups`.

### 5.1. Dependency

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.security:spring-security-ldap")
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Ở đây, **Spring Security LDAP** đảm nhận authentication/authority; **Spring Data LDAP** cung cấp repository/`LdapTemplate` phục vụ truy cập dữ liệu. Spring Boot quản lý phiên bản dependency tương thích nếu dùng đúng BOM/starter.

### 5.2. Cấu hình địa chỉ và danh tính tìm kiếm

`application.yml`:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_SEARCH_BIND_DN}
    password: ${LDAP_SEARCH_BIND_PASSWORD}
~~~

Ví dụ giá trị môi trường:

~~~dotenv
LDAP_URL=ldaps://ldap.example.org:636
LDAP_BASE_DN=dc=example,dc=org
LDAP_SEARCH_BIND_DN=cn=app-auth-search,ou=services,dc=example,dc=org
LDAP_SEARCH_BIND_PASSWORD=<secret-do-he-thong-cap>
~~~

Ý nghĩa:

| Thuộc tính | Giá trị mẫu | Vai trò |
| --- | --- | --- |
| `spring.ldap.urls` | `ldaps://ldap.example.org:636` | Địa chỉ dịch vụ directory. |
| `spring.ldap.base` | `dc=example,dc=org` | Root tương đối cho tìm kiếm và DN thao tác. |
| `spring.ldap.username` | `cn=app-auth-search,ou=services,dc=example,dc=org` | Service account được dùng khi context cần bind với danh tính quản lý. |
| `spring.ldap.password` | Lấy từ biến môi trường/secret manager. | Mật khẩu **của service account**, không phải mật khẩu của Lan. |

Ví dụ dùng một `ContextSource` được Spring Boot cấu hình để tập trung vào luồng authentication. Vì Spring Data LDAP cũng có thể sử dụng context này theo mặc định, quyền service account phải được giới hạn phù hợp; nếu yêu cầu đọc/ghi dữ liệu khác quyền tìm danh tính, nên thiết kế **các context/tài khoản riêng** như mục 8.

**Kết nối an toàn:** `ldaps://` mã hóa từ đầu nếu TLS và chứng chỉ được cấu hình đúng. `ldap://` thường là kết nối không mã hóa trừ khi **StartTLS** được nâng cấp một cách tường minh. Không chuyển sang LDAP không mã hóa chỉ vì user bind lỗi hoặc chứng chỉ không được JVM tin cậy.

### 5.3. Tìm DN theo username và bind người dùng

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LdapSecurityConfiguration {

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {

        var factory = new LdapBindAuthenticationManagerFactory(contextSource);

        // DN người dùng chưa biết: tìm bằng uid dưới nhánh people.
        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter("(uid={0})");

        // Sau khi user bind thành công, tìm các nhóm đã gán cho DN.
        var groups = new DefaultLdapAuthoritiesPopulator(
                contextSource, "ou=groups");
        groups.setGroupSearchFilter("(uniqueMember={0})");
        groups.setGroupRoleAttribute("cn");
        groups.setRolePrefix("ROLE_");
        groups.setConvertToUpperCase(true);
        factory.setLdapAuthoritiesPopulator(groups);

        return factory.createAuthenticationManager();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager ldapAuthenticationManager)
            throws Exception {

        http.authenticationManager(ldapAuthenticationManager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/directory/people/**")
                    .hasRole("DIRECTORY_READER")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Đọc cấu hình theo trình tự:**

1. Spring Boot tạo `ContextSource` từ URL, base DN và service account (nếu auto-configuration được kích hoạt và không có bean custom thay thế).
2. `setUserSearchBase("ou=people")` giới hạn nhánh tìm user tương đối với `spring.ldap.base`.
3. `setUserSearchFilter("(uid={0})")` định nghĩa điều kiện lấy DN của người dùng. `{0}` là tham số username được Spring Security LDAP xử lý theo cơ chế thay thế/escape filter; **không** tự nối chuỗi username vào filter.
4. `LdapBindAuthenticationManagerFactory` dùng bind authenticator: sau khi tìm DN phù hợp, thử bind với DN và password người dùng cung cấp. Bind user thành công là cơ sở xác thực danh tính.
5. `DefaultLdapAuthoritiesPopulator` tra cứu nhóm có `uniqueMember` chứa DN đầy đủ của user (tham số `{0}` trong group search) và chuyển `cn` thành authority có tiền tố `ROLE_`.
6. `hasRole("DIRECTORY_READER")` đòi `ROLE_DIRECTORY_READER` trong `Authentication`. Người dùng bind thành công nhưng thiếu role vẫn không được phép gọi endpoint.
7. `httpBasic(...)` được dùng để minh họa dễ kiểm thử. Trong ứng dụng thực, mọi request chứa credential phải qua HTTPS và có chiến lược authentication/session phù hợp.

Nếu directory dùng `member` thay cho `uniqueMember`, hoặc dùng `sAMAccountName` thay `uid`, phải cập nhật cấu hình theo schema. Nhóm lồng nhau, group search base và cách ánh xạ authority trong Active Directory có thể cần xử lý riêng. Không mặc định role là danh tính hoặc tên OU.

### 5.4. Vì sao user search filter cần giới hạn?

Không nên cấu hình search base quá rộng như toàn bộ `dc=example,dc=org` khi user chỉ ở `ou=people`. Search rộng có thể vô tình phát hiện account kỹ thuật, account ở OU không dành cho ứng dụng hoặc nhiều entry có cùng `uid`.

Cần bảo đảm filter chọn **đúng một người dùng** theo schema/khóa đăng nhập đã được quản trị. Nếu có nhiều entry phù hợp, phải xử lý như lỗi định danh/môi trường chứ không chọn ngẫu nhiên entry đầu tiên. Dùng `uid` vì directory ví dụ bảo đảm tính duy nhất trong nhánh của ứng dụng; LDAP nói chung không tự áp một quy tắc duy nhất cho mọi `uid` ở toàn cây.

## 6. Service account và tìm nhóm quyền

Sau khi xác thực Lan qua bind, Spring Security có thể cần biết Lan có quyền gì. Giả sử entry nhóm:

~~~ldif
dn: cn=DIRECTORY_READER,ou=groups,dc=example,dc=org
objectClass: groupOfUniqueNames
cn: DIRECTORY_READER
uniqueMember: uid=lan,ou=people,dc=example,dc=org
~~~

`DefaultLdapAuthoritiesPopulator` có thể tìm nhóm bằng một context có quyền đọc nhánh `ou=groups`. Điều này thường đòi service account có quyền **search/read group membership**, dù việc user bind xác thực đã thành công.

| Tình huống | User bind | Group search | Kết quả ứng dụng |
| --- | --- | --- | --- |
| Lan đúng password, thuộc `DIRECTORY_READER`. | Thành công. | Trả nhóm. | Có `ROLE_DIRECTORY_READER`; có thể qua kiểm tra endpoint. |
| Minh đúng password nhưng không thuộc nhóm. | Thành công. | Không có nhóm phù hợp. | Vẫn là danh tính đã xác thực; bị từ chối endpoint yêu cầu role. |
| Lan đúng password, service account không đọc được `ou=groups`. | Có thể thành công. | Bị từ chối hoặc kết quả không đủ. | Không nên suy rằng đã có quyền; phải xử lý như thiếu authority/lỗi cấu hình theo chính sách. |
| Sai mật khẩu user. | Thất bại. | Không tiếp tục nạp quyền cho một authentication thành công. | Đăng nhập bị từ chối. |

**Vai trò của service account trong group search khác với quyền của người dùng HTTP.** Service account chỉ làm nguồn dữ liệu cho phép ánh xạ group. Quy tắc ai được gọi API thuộc Spring Security/authorization và quy định nghiệp vụ, không tự phát sinh từ việc user có mặt trong directory.

### Vấn đề nhóm lồng nhau và dữ liệu quyền cũ

Một số directory cho phép nhóm chứa nhóm, hoặc lưu membership qua `memberOf`/thuộc tính đặc thù. Filter `(uniqueMember={0})` trong ví dụ chỉ minh họa **nhóm trực tiếp** dùng schema `groupOfUniqueNames`; không mặc định hỗ trợ nested groups. Khi nhóm thay đổi, authority đã lưu trong session/JWT/cache có thể chưa được cập nhật ngay. Ứng dụng nhạy cảm cần chính sách làm mới quyền, thu hồi phiên và kiểm tra lại khi phù hợp.

## 7. Khi nào không cần service account để tìm DN?

Trong một số directory, DN được xây theo mẫu cố định:

~~~text
uid={username},ou=people,dc=example,dc=org
~~~

Nếu hệ thống **cam kết** mọi người dùng có RDN `uid` dưới `ou=people`, ứng dụng có thể thử **direct bind** theo DN pattern mà không cần search trước để tìm DN.

Một ví dụ về lựa chọn cấu hình trong Spring Security LDAP là `setUserDnPatterns(...)` thay cho user search, tùy cách triển khai factory/provider. Tuy nhiên, điều kiện là ứng dụng **thực sự biết cách tạo DN của mọi user hợp lệ** và xử lý đúng escape cho RDN qua API thư viện.

| Cách xác định DN | Ưu điểm | Hạn chế |
| --- | --- | --- |
| **Search DN bằng service account** | Hỗ trợ user ở nhiều OU, DN không dự đoán được, RDN khác username. | Cần quyền search, secret, cấu hình ACL và xử lý lỗi/dữ liệu trùng. |
| **DN pattern/direct bind** | Ít phụ thuộc vào manager search cho bước xác định DN. | Hỏng nếu DN đổi, user nằm ngoài pattern hoặc username không phải RDN; vẫn có thể cần context để tìm nhóm. |
| **Identity provider bên ngoài (OIDC/SAML)** | Ứng dụng không cần trực tiếp nhận mật khẩu LDAP nếu ủy quyền đăng nhập cho IdP. | Cần thiết kế tích hợp token/claim/quyền, không phải mọi use case LDAP data access đều biến mất. |

Không nên chọn DN pattern chỉ để tránh quản lý service account nếu directory thật có cấu trúc phức tạp. Ngược lại, không tạo thêm service account có quyền rộng nếu ứng dụng dùng direct bind và không cần tìm entry/nhóm.

## 8. Tài khoản tìm danh tính và tài khoản truy cập dữ liệu có cần tách?

**Có thể**, và thường nên tách khi trách nhiệm/quyền khác nhau.

~~~mermaid
flowchart LR
    A["HTTP login"] --> B["Spring Security LDAP"]
    B --> C["Auth search ContextSource<br/>cn=app-auth-search"]
    C --> D["LDAP: user DN + group"]
    A --> E["API nghiệp vụ sau authorization"]
    E --> F["Spring Data LDAP<br/>Repository / LdapTemplate"]
    F --> G["Data ContextSource<br/>cn=app-data-reader"]
    G --> H["LDAP: các thuộc tính được phép đọc"]
~~~

Ví dụ phân chia:

| Tài khoản | Phạm vi | Quyền tối thiểu mong muốn |
| --- | --- | --- |
| `app-auth-search` | `ou=people` và `ou=groups` | Search DN, các thuộc tính định danh và membership cần thiết. |
| `app-data-reader` | Nhánh danh bạ được API sử dụng. | Chỉ đọc `uid`, `cn`, `mail` hoặc thuộc tính được duyệt. |
| `app-directory-writer` (nếu có) | Nhánh quản trị cụ thể. | Ghi đúng attribute và entry được cấp phép, không phải quản trị toàn bộ directory. |

Trong ví dụ ở mục 5, tất cả có thể dùng **một** `ContextSource` để đơn giản hóa bài học. Muốn tách trong ứng dụng thật, cần cấu hình nhiều `LdapContextSource`, gắn đúng context cho authentication provider/authorities populator và `LdapTemplate`/repository bằng bean/qualifier tương ứng. Đừng chỉ đặt hai biến mật khẩu trong YAML rồi mặc định Spring Boot tự định tuyến mỗi luồng sang tài khoản riêng.

### Cẩn thận với thao tác CRUD

Spring Data LDAP repository có `save`, `delete`, còn `LdapTemplate` có `bind`/`modifyAttributes`/`unbind`. Việc service account tìm DN thành công **không** có nghĩa ứng dụng được phép thêm, sửa, xóa entry. Quyền CRUD phải được thiết kế riêng tại API/service và ACL của directory.

Đừng dùng tài khoản service tìm danh tính để tự động sửa `userPassword`, đổi nhóm quản trị hay cập nhật account state. Đó là nghiệp vụ có đặc quyền cao cần quy trình, audit và phân quyền chuyên biệt.

## 9. Tìm entry qua Spring Data LDAP không phải phép xác thực

Giả sử ứng dụng có entity LDAP:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    public String getUid() { return uid; }
    public String getCommonName() { return commonName; }
}
~~~

Repository:

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    Optional<PersonEntry> findByUid(String uid);
}
~~~

`findByUid("lan")` trả về thông tin người dùng **nếu entry tồn tại, đúng filter/base, và bind account có quyền đọc**. Nó không biết ai đang gửi request và không nhận mật khẩu để xác thực Lan.

Trong một service của API đã được bảo vệ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

public record PersonView(String uid, String displayName) {}

@Service
public class DirectoryPeopleService {
    private final PersonRepository repository;

    public DirectoryPeopleService(PersonRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasRole('DIRECTORY_READER')")
    public PersonView getByUid(String uid) {
        PersonEntry person = repository.findByUid(uid)
            .orElseThrow(() -> new IllegalArgumentException(
                "Khong tim thay entry"));
        return new PersonView(person.getUid(), person.getCommonName());
    }
}
~~~

Để `@PreAuthorize` có hiệu lực, cần bật `@EnableMethodSecurity` và gọi service qua Spring-managed proxy; lời gọi nội bộ tự gọi phương thức trong cùng object có thể bỏ qua proxy. Mã ví dụ tập trung vào ranh giới trách nhiệm, chưa minh họa ánh xạ exception sang HTTP 404, kiểm tra ownership hoặc cấu hình security hoàn chỉnh cho các endpoint khác.

**Hai quyền khác nhau:**

- Spring Security kiểm tra **principal HTTP** có `ROLE_DIRECTORY_READER`.
- Directory server kiểm tra **bind account của repository** có thể đọc entry/attribute.

Nếu service account có quyền xem tất cả nhưng người dùng HTTP không được phân quyền, API vẫn phải từ chối. Nếu người dùng HTTP được phép nhưng bind account bị hạn chế ACL, LDAP vẫn có thể không trả dữ liệu.

## 10. Những sai lầm bảo mật cần tránh

| Sai lầm | Hậu quả | Thiết kế đúng |
| --- | --- | --- |
| Dùng tài khoản quản trị directory làm search account. | Nếu credential lộ, phạm vi ảnh hưởng rất lớn. | Tài khoản kỹ thuật riêng, ACL đọc tối thiểu. |
| Cho search account quyền đọc `userPassword` dù chỉ dùng bind authentication. | Mở rộng quyền truy cập dữ liệu nhạy cảm không cần thiết. | Xác thực qua user bind; không đọc hash mật khẩu. |
| Chuyển credential của user sang repository mặc định. | Lẫn danh tính xác thực với context dữ liệu; khó quản lý pool và audit. | Cấu hình rõ context cho authentication và data access. |
| Nhập mật khẩu service account vào `application.yml` rồi commit. | Lộ secret trong Git, bản build hoặc log. | Secret manager, biến môi trường, luân chuyển credential. |
| Dùng `ldap://` không TLS để kiểm tra password. | Credential có thể bị nghe lén. | LDAPS/StartTLS đúng cách, xác minh CA/hostname. |
| Tìm user từ directory root không giới hạn filter. | Tìm nhầm service account, trùng username, tải lớn. | Base hẹp, filter cụ thể, giới hạn search và dữ liệu. |
| Tự ghép username thành filter. | LDAP filter injection hoặc sai ý nghĩa truy vấn. | Dùng `{0}` theo API Spring Security và query builder/escaping đúng ngữ cảnh. |
| Báo “không tồn tại tài khoản” khác hẳn “sai mật khẩu”. | Tạo điều kiện dò tên người dùng hợp lệ. | Thông điệp đăng nhập chung cho caller, log nội bộ có kiểm soát. |
| Cho rằng bind thành công đồng nghĩa có mọi quyền. | Người không thuộc nhóm vẫn truy cập API. | Kiểm tra authority và chính sách theo đối tượng. |
| Không giới hạn retry khi LDAP từ chối bind. | Có thể gây khóa tài khoản hoặc quá tải directory. | Rate limit, chống brute force, backoff phù hợp, giám sát. |

### Filter escaping và phân quyền scope

`(uid={0})` là template filter cho username, không phải quyền chọn tùy ý attribute/base. Nếu API có tham số chọn nhánh hoặc tên trường, phải dùng allowlist do server định nghĩa. Không cho người dùng điều khiển trực tiếp `userSearchBase` hoặc `userSearchFilter` từ request. DN và LDAP filter có quy tắc escaping khác nhau; dùng API phù hợp cho từng loại.

### Tài khoản kỹ thuật cũng có vòng đời

Service account cần người sở hữu, phạm vi sử dụng rõ ràng, quy trình cấp/thu hồi/đổi mật khẩu, audit bind và cảnh báo khi credential hết hạn. Khi luân chuyển secret, phải kiểm thử cả user search và group search trên từng endpoint LDAP dự phòng, tránh ứng dụng vẫn bind được ở một server nhưng lỗi ở server khác do replication hoặc ACL khác nhau.

## 11. Kiểm chứng từng tầng bằng công cụ LDAP

Trước khi đổ lỗi cho Spring Security, hãy xác minh directory thử nghiệm độc lập với code Java. Các lệnh sau yêu cầu có OpenLDAP command-line tools và tài khoản được cấp quyền.

### 11.1. Tài khoản dịch vụ có tìm được user không?

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-auth-search,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=lan))" dn uid cn
~~~

`-W` hỏi password qua prompt, không ghi password trên command line. Thành công với entry Lan chứng minh **search account có khả năng đọc DN và các trường yêu cầu** theo base/filter đang dùng. Chưa chứng minh mật khẩu Lan hợp lệ.

### 11.2. Bind bằng DN và password của người dùng

~~~bash
ldapwhoami -x \
  -H "ldaps://ldap.example.org:636" \
  -D "uid=lan,ou=people,dc=example,dc=org" -W
~~~

Ở bước này nhập **mật khẩu của Lan** vào prompt, không phải mật khẩu của `app-auth-search`. Nếu bind thành công, directory chấp nhận thông tin xác thực của Lan theo chính sách hiện tại. Không dùng tài khoản người khác hoặc directory production ngoài phạm vi được cấp phép.

Nếu user có DN `cn=Lan Nguyen,ou=staff,...` thay vì `uid=lan,...`, dùng **DN thực tìm từ bước trước**; tự suy DN từ username có thể cho kết quả sai.

### 11.3. Kiểm tra group search của service account

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-auth-search,ou=services,dc=example,dc=org" -W \
  -b "ou=groups,dc=example,dc=org" -s sub \
  "(uniqueMember=uid=lan,ou=people,dc=example,dc=org)" dn cn
~~~

Lệnh kiểm tra group thuộc schema minh họa. Nếu không thấy `DIRECTORY_READER`, kiểm tra `uniqueMember`, vị trí group, ACL, nested groups và cách Spring Security ánh xạ group thành authority. Việc group search trả rỗng không làm user bind biến thành sai mật khẩu; nó ảnh hưởng quyền được nạp sau xác thực.

### 11.4. Thử qua HTTP

Với ứng dụng thử nghiệm đã bật HTTPS:

~~~bash
curl -i --user lan \
  https://localhost:8443/api/directory/people/lan
~~~

`curl --user lan` sẽ yêu cầu mật khẩu qua prompt trong môi trường CLI thông thường. Kiểm thử Lan đúng mật khẩu/có nhóm; Minh đúng mật khẩu/không nhóm; sai mật khẩu; user không tồn tại và service account bị thu hồi quyền search.

Với cấu hình HTTP Basic điển hình, sai hoặc thiếu thông tin xác thực nhận **HTTP 401**, còn tài khoản đã xác thực nhưng không có role nhận **HTTP 403**. Lỗi backend LDAP do mạng, TLS hoặc service account không bind được có thể được ứng dụng ánh xạ thành lỗi dịch vụ; không kết luận tất cả lỗi LDAP đều là sai mật khẩu của người dùng.

## 12. Phân tích sự cố theo từng bước

| Dấu hiệu | Nghi ngờ trước tiên | Kiểm tra |
| --- | --- | --- |
| Service bind bằng `ldapsearch` thất bại với code **49**. | DN/secret tài khoản dịch vụ hoặc trạng thái account. | Xác minh credential qua secret manager, account policy và server. |
| Bind service được, search user trả rỗng. | User search base/filter, schema, tên attribute, ACL hoặc thực sự không có entry. | Dùng cùng base/filter và tài khoản trên server. |
| Search thấy nhiều entry có cùng username. | Định danh đăng nhập chưa duy nhất trong phạm vi search. | Thu hẹp base, sửa dữ liệu/quy ước identity; không chọn entry tùy ý. |
| Search user thành công, user bind trả code **49**. | Password người dùng sai, tài khoản bị khóa/hết hạn hoặc policy từ directory. | Kiểm tra trạng thái user theo quy trình được phép. |
| User bind thành công nhưng không có role. | Group search base/filter, `uniqueMember`, role prefix, nested groups, ACL. | Truy vấn group độc lập bằng service account. |
| Login đúng nhưng endpoint trả **403**. | `hasRole` không khớp `GrantedAuthority` hoặc policy khác. | Kiểm tra authority ánh xạ trong test/debug có bảo vệ PII. |
| LDAP code **50** khi tìm entry/nhóm. | ACL của tài khoản đang bind không đủ quyền. | Kiểm tra chính sách đọc/search của nhánh và attribute. |
| LDAP code **32**. | DN/base không tồn tại, nhánh đã đổi hoặc chính sách ẩn entry. | Xác nhận cây DN, base tương đối và search scope. |
| `SSLHandshakeException`/timeout. | TLS, DNS, tường lửa, truststore hoặc endpoint. | Kiểm tra chứng chỉ/hostname/mạng và cấu hình JVM. |
| Repository trả rỗng dù user login thành công. | Data context khác auth context; base/ACL/filter của repository khác. | Tách và đối chiếu hai đường tìm kiếm. |

**Mã 49/50/32 là LDAP result code**, còn 401/403 là HTTP status; chúng thuộc các tầng khác nhau. Một kết quả search rỗng không có nghĩa chắc chắn tài khoản không tồn tại, vì ACL và search base cũng có thể khiến entry không xuất hiện.

## 13. Thiết kế kiểm thử tích hợp

Chuẩn bị directory thử nghiệm với tối thiểu:

- User **Lan** có mật khẩu hợp lệ và là thành viên `DIRECTORY_READER`.
- User **Minh** có mật khẩu hợp lệ nhưng không thuộc nhóm.
- User nằm ở OU khác mà filter không được phép tìm.
- Một service account đọc được user nhưng **không được đọc** group, để test hành vi thiếu quyền.
- Một tài khoản chỉ đọc dùng cho truy vấn Spring Data LDAP và, nếu cần, một tài khoản ghi riêng.

### Ma trận kiểm thử

| Trường hợp | User search bằng service account | User bind | Group search | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Lan đúng password, đúng nhóm. | Tìm đúng một DN. | Thành công. | Có `DIRECTORY_READER`. | Có quyền gọi GET được bảo vệ. |
| Lan sai password. | Có thể tìm đúng DN. | Thất bại. | Không nạp authority cho login thành công. | Từ chối đăng nhập. |
| Minh đúng password, không nhóm. | Tìm DN. | Thành công. | Không có role bắt buộc. | HTTP 403 ở endpoint cần role. |
| User không nằm trong search base. | Không tìm thấy. | Không có DN phù hợp để bind theo luồng search. | Không nạp quyền. | Từ chối xác thực theo cấu hình; kiểm tra log nội bộ. |
| Service account mất quyền search user. | Lỗi hoặc trả rỗng tùy server/ACL. | Có thể chưa tới bước bind. | Không xác định. | Không tự cấp quyền; báo lỗi vận hành. |
| Service account mất quyền tìm group. | Vẫn có thể tìm DN. | Có thể thành công. | Thiếu/lỗi group. | Không cấp role bị thiếu; ghi nhận lỗi cấu hình. |
| Nhóm bị đổi tên hoặc đổi attribute. | Vẫn tìm user. | Thành công. | Mapping không khớp. | Kiểm tra lại cấu hình `cn`/`member`/`uniqueMember`. |
| Repository dùng bind account chỉ đọc. | Auth search độc lập. | Auth có thể thành công. | Mapping độc lập. | Chỉ đọc các thuộc tính do data account được cấp. |

Test cần quan sát cả **trạng thái HTTP** và những **LDAP bind/search thực sự xảy ra** (qua log server/proxy được phép) để không nhầm xác thực với đọc dữ liệu. Khi đo log, không in mật khẩu, token, hash hoặc toàn bộ thuộc tính cá nhân.

### Unit test chính sách độc lập với directory

Nên có test bảo đảm `hasRole("DIRECTORY_READER")` cho phép Lan nhưng từ chối Minh, kể cả khi một repository giả lập có thể trả entry của cả hai. Điều này chứng minh **data access không thay thế authorization**.

Integration test mới kiểm tra được ACL directory thật, thao tác user bind, schema nhóm và việc Spring Security ánh xạ DN/authority. Không kết luận toàn bộ luồng đăng nhập đã an toàn chỉ vì mock `LdapRepository.findByUid` trả kết quả đúng.

## 14. Bài tập tình huống

Một ứng dụng nội bộ có LDAP:

~~~text
dc=company,dc=internal
├── ou=employees
│   └── cn=Mai Le           uid=mai
├── ou=roles
│   └── cn=HR_VIEWER
└── ou=technical
    └── cn=app-searcher
~~~

`cn=app-searcher,ou=technical,dc=company,dc=internal` có quyền tìm entry trong `ou=employees` và đọc membership của `ou=roles`. Nhân viên Mai đăng nhập bằng `uid=mai` nhưng DN đầy đủ là `cn=Mai Le,ou=employees,dc=company,dc=internal`.

**Yêu cầu:**

1. Vì sao không thể luôn xây DN đăng nhập bằng mẫu `uid={0},ou=employees,...`? Trình bày cách dùng search base/filter để tìm DN thật.
2. Trong search-based bind authentication, những bước nào chạy bằng service account và bước nào dùng DN + mật khẩu của Mai?
3. Nếu service account có thể tìm user nhưng không được đọc group, login bằng mật khẩu đúng có tự động nhận `ROLE_HR_VIEWER` không?
4. Nếu ứng dụng dùng `LdapRepository.findByUid("mai")` và thấy entry, có được coi request là Mai đã xác thực không?
5. Nếu Mai đăng nhập thành công nhưng không có `HR_VIEWER`, hệ thống có được trả danh bạ HR chỉ vì tài khoản repository có ACL đọc không?
6. Tạo ma trận kiểm thử cho các trường hợp: sai mật khẩu Mai, service account sai secret, sai user search base, group filter sai, quyền ACL thiếu và chứng chỉ LDAPS không tin cậy.
7. Khi tổ chức quyết định chuyển từ một tài khoản kỹ thuật chung sang hai tài khoản `app-auth-search` và `app-data-reader`, phải thay đổi gì trong thiết kế context, quyền và kiểm thử?

**Gợi ý đáp án:**

- DN thật dùng `cn=Mai Le`, không phải `uid=mai`; tìm trong `ou=employees` bằng filter `(uid={0})`, rồi bind với DN trả về.
- Service account dùng để user search và có thể group search; user bind kiểm tra mật khẩu của Mai.
- Không có kết quả group hợp lệ thì không tự tạo `ROLE_HR_VIEWER`.
- Repository chỉ đọc dữ liệu; nó không xác thực caller HTTP.
- Spring Security vẫn phải kiểm tra role/policy độc lập với ACL của data account.
- Mỗi lỗi cần được kiểm tra ở đúng tầng: service bind, user search, user bind, group search, authorization và TLS.
- Tách hai `ContextSource`/bind DN và gắn đúng vào auth/data component, cấp ACL tối thiểu và test cả hai luồng với directory thật.

## 15. Ghi nhớ

Trong LDAP bind authentication, **service account dùng để tìm người dùng** khi ứng dụng chỉ biết username và cần xác định DN thực. Sau đó **directory xác thực credential qua user bind**; Spring Security có thể tra cứu group rồi ánh xạ thành role/authority để quyết định quyền sử dụng API.

**Service account tìm DN không phải người dùng đang đăng nhập; repository tìm thấy entry cũng không phải phép xác thực.** Hãy giới hạn search base, filter và ACL, dùng TLS, giữ secret an toàn, tách auth/data context khi quyền khác nhau, và kiểm thử lần lượt service bind → user search → user bind → group search → authorization → repository. Đó là cách áp dụng Spring Security cùng Spring Data LDAP an toàn và dễ chẩn đoán.

### Tài liệu tham khảo

- [Spring Security Reference — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security Reference — LDAP Authorities](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
- [Spring LDAP Reference — Basic Usage](https://docs.spring.io/spring-ldap/reference/basic.html)
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/)
- [RFC 4511 — LDAPv3 Bind and Search](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513)
