# LDAP, directory và Active Directory trong mô hình danh tính tổ chức

## 1. Vì sao tổ chức cần một directory?

Một tổ chức có hàng nghìn nhân viên, nhiều phòng ban và nhiều ứng dụng (intranet, VPN, quản lý nhân sự, hệ thống nghiệp vụ). Nếu mỗi ứng dụng lưu tài khoản, mật khẩu và danh sách phòng ban riêng, việc tạo, chuyển bộ phận, khóa tài khoản hoặc thu hồi quyền sẽ dễ bị lệch. Một **directory** là kho dữ liệu danh tính dùng chung, giúp quản trị tập trung thông tin người dùng, máy tính, nhóm và quan hệ giữa chúng.

Trong ngữ cảnh này cần phân biệt ba khái niệm:

| Khái niệm | Bản chất | Ví dụ / vai trò |
|---|---|---|
| **Directory (dịch vụ thư mục)** | Hệ thống lưu các entry danh tính theo cấu trúc và schema, tối ưu cho tìm kiếm/tra cứu và quản lý tập trung. | Người dùng, nhóm, tổ chức, thiết bị, thuộc tính. |
| **LDAP (Lightweight Directory Access Protocol)** | Giao thức để client truy cập, tìm kiếm, xác thực qua bind và (khi được phép) sửa dữ liệu directory. | Ứng dụng gửi LDAP search/bind tới directory server. |
| **Active Directory Domain Services (AD DS)** | Dịch vụ thư mục doanh nghiệp của Microsoft; cung cấp domain, domain controller, group, policy, trust và nhiều cơ chế xác thực. | Domain `corp.example`, các máy chủ domain controller; hỗ trợ LDAP, Kerberos, v.v. |

**Directory không đồng nghĩa với LDAP; LDAP không đồng nghĩa với Active Directory.** OpenLDAP là một triển khai máy chủ LDAP; AD DS là dịch vụ thư mục rộng hơn, hỗ trợ LDAP như một giao diện. LDAP là giao thức, không phải một hệ quản trị danh tính hay cơ chế single sign-on hoàn chỉnh.

Một kiến trúc thường gặp:

```text
Người dùng ── tên đăng nhập + mật khẩu ──> Ứng dụng
                                            |
                                    Spring Security
                                            |
                              LDAP client / provider
                                            |
                               LDAPS (kênh TLS)
                                            |
                              Directory server / AD DS
                                  |           |
                              User entry   Group entry
                                            |
                           Xác thực + ánh xạ quyền ứng dụng
```

Ứng dụng vẫn chịu trách nhiệm **phân quyền nghiệp vụ**. Việc directory xác nhận mật khẩu đúng chưa đủ để cho phép đọc bảng lương, duyệt đơn hàng hay truy cập API quản trị.

## 2. Mô hình dữ liệu directory: entry, DN, attribute và schema

Directory tổ chức dữ liệu thành các **entry** trong cây thông tin thư mục (*Directory Information Tree*, DIT). Mỗi entry có một **Distinguished Name (DN)** để xác định vị trí duy nhất trong cây, một hay nhiều **objectClass**, cùng các **attribute** và giá trị của chúng.

Ví dụ minh họa một cây LDAP thông thường:

```text
dc=corp,dc=example                    ← base DN
├── ou=People
│   ├── uid=lan                        ← một user entry
│   └── uid=minh
├── ou=Groups
│   ├── cn=developers                  ← một group entry
│   └── cn=auditors
└── ou=Services
    └── cn=ldap-reader                 ← service account
```

Một số thuật ngữ phải đọc đúng:

- **DN:** đường dẫn đầy đủ, chẳng hạn `uid=lan,ou=People,dc=corp,dc=example`.
- **RDN (Relative Distinguished Name):** thành phần của DN tại một cấp; trong ví dụ user, `uid=lan`. Không coi RDN đơn lẻ là định danh duy nhất của toàn directory.
- **Base DN:** nút gốc mà client dùng làm điểm bắt đầu tìm kiếm; ví dụ `dc=corp,dc=example`.
- **Attribute:** tên thuộc tính như `uid`, `cn`, `sn`, `mail`, `member`, `userPrincipalName`. Attribute có thể có nhiều giá trị, tùy schema.
- **objectClass/schema:** quy định loại entry, thuộc tính bắt buộc/được phép và các ràng buộc. Không thể giả định mọi server đều có cùng schema.
- **OU (Organizational Unit):** nút tổ chức, dùng để sắp xếp hoặc quản trị các đối tượng. OU không tự động là một vai trò bảo mật.
- **Group:** mô tả tập hợp thành viên; khi tích hợp ứng dụng có thể dùng làm dữ liệu để ánh xạ sang authority/role.

Ví dụ dữ liệu theo định dạng LDIF cho schema dạng OpenLDAP:

```ldif
dn: uid=lan,ou=People,dc=corp,dc=example
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@corp.example

dn: cn=developers,ou=Groups,dc=corp,dc=example
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=People,dc=corp,dc=example
```

Đây là **dữ liệu minh họa**, không phải lệnh tạo sẵn cho mọi server. AD DS dùng schema và cách đặt tên khác: user thường có DN như `CN=Lan Nguyen,OU=Engineering,DC=corp,DC=example`, đăng nhập bằng `lan@corp.example` (UPN) hoặc `CORP\lan` (tên miền + sAMAccountName); DN không nhất thiết bằng tên đăng nhập. Trong AD, thuộc tính `objectGUID` thường thích hợp làm khóa định danh ổn định của đối tượng hơn DN khi đối tượng có thể đổi tên/di chuyển OU. Trong một directory khác, cần chọn khóa ổn định tương ứng theo schema và vòng đời thực tế.

**Ví dụ dễ nhầm:** chuyển Lan từ `OU=Engineering` sang `OU=Finance` có thể làm DN thay đổi, nhưng không có nghĩa Lan là một tài khoản khác. Nếu ứng dụng dùng DN làm khóa người dùng bất biến, việc di chuyển này có thể gây trùng hồ sơ hoặc mất liên kết dữ liệu.

## 3. LDAP hoạt động như thế nào?

Những thao tác thường gặp:

| Thao tác | Ý nghĩa |
|---|---|
| **Bind** | Thiết lập danh tính cho phiên kết nối với directory; simple bind có thể dùng DN/định danh và mật khẩu; còn có các phương thức SASL tùy server. |
| **Search** | Tìm các entry theo base DN, scope, filter và danh sách attribute cần lấy. |
| **Compare** | Yêu cầu server so sánh một giá trị thuộc tính theo quy tắc LDAP. |
| **Add/Modify/Delete/Modify DN** | Thay đổi directory nếu tài khoản có quyền. Ứng dụng chỉ cần xác thực thường không được cấp quyền ghi. |
| **Unbind** | Kết thúc phiên LDAP. |

Search có ba **scope** thường dùng: `base` (chỉ entry ở base DN), `one-level` (các entry con trực tiếp) và `subtree` (toàn bộ cây con). Filter có cú pháp riêng, chẳng hạn:

```ldap
(uid=lan)
(&(objectClass=inetOrgPerson)(uid=lan))
(|(uid=lan)(uid=minh))
```

Dòng thứ hai có nghĩa là tìm entry vừa có object class phù hợp vừa có `uid=lan`; dòng thứ ba là toán tử OR. Đây là **LDAP filter**, không phải cú pháp SQL. Kết quả tìm kiếm còn phụ thuộc search base, scope, ACL, schema và index; một filter hợp lệ vẫn có thể trả về 0 hoặc nhiều bản ghi.

### Luồng xác thực thông dụng: search rồi user bind

1. Người dùng nhập tên đăng nhập/mật khẩu vào ứng dụng qua HTTPS.
2. Ứng dụng dùng một tài khoản dịch vụ **chỉ có quyền đọc cần thiết** (hoặc cơ chế tìm kiếm đã được server cho phép) để tìm user DN bằng một filter an toàn.
3. Nếu tìm thấy **đúng một** user entry, LDAP authentication provider thử **bind dưới danh tính người dùng đó** với mật khẩu vừa nhập qua TLS.
4. Directory xác minh thông tin bind và trả thành công/thất bại; ứng dụng không cần lấy bản rõ hay hash mật khẩu từ directory.
5. Sau khi xác thực, ứng dụng đọc thông tin nhóm/thuộc tính cần thiết, chuyển thành authorities theo chính sách nội bộ, rồi thực thi authorization đối với endpoint và dữ liệu.

Nếu cấu trúc DN ổn định, có thể bind trực tiếp theo một DN pattern; nếu tài khoản nằm ở nhiều OU hoặc DN thay đổi, **search trước khi bind** thường linh hoạt hơn. Không nên tự suy luận một DN chỉ từ tên hiển thị hoặc địa chỉ email.

Luồng này phân biệt rõ:

- **Authentication:** “Lan có chứng minh được danh tính không?” (LDAP bind thành công).
- **Directory lookup:** “Lan thuộc đơn vị nào, có những nhóm gì?” (LDAP search và đọc attribute).
- **Authorization:** “Lan có được phê duyệt giao dịch này không?” (quy tắc của ứng dụng, có thể dùng thông tin nhóm).

Một user bind đúng vẫn có thể nhận HTTP **403 Forbidden** nếu thiếu authority. Ngược lại, không được cấp role chỉ vì client gửi tên một nhóm trong request.

## 4. Active Directory bổ sung gì cho mô hình này?

**AD DS** tổ chức danh tính quanh domain và forest:

- **Domain:** ranh giới quản lý các tài khoản, máy tính và domain controller; namespace thường gắn với tên DNS.
- **Domain controller (DC):** máy chủ thực thi AD DS và đáp ứng yêu cầu xác thực/truy vấn directory. Thay đổi được nhân bản giữa các DC theo cơ chế replication; việc đọc từ các DC khác nhau có thể có độ trễ hội tụ.
- **Forest và trust:** nhiều domain có thể tạo thành một forest; quan hệ trust quyết định khả năng nhận diện danh tính liên miền, nhưng không đồng nghĩa mọi ứng dụng tự có quyền liên miền.
- **Global Catalog (GC):** dịch vụ hỗ trợ tìm kiếm đối tượng trên phạm vi forest với một tập thuộc tính phù hợp; không mặc nhiên chứa mọi attribute trên mọi domain.
- **Group và Group Policy:** group tham gia vào quản lý quyền; Group Policy điều khiển nhiều thiết lập cho tài khoản/máy tính Windows. LDAP client chỉ nhìn thấy phần thông tin được truy vấn, không tự “áp dụng Group Policy” cho ứng dụng Java.

Các thuộc tính AD nên biết:

| Thuộc tính / khái niệm | Cách sử dụng và lưu ý |
|---|---|
| `sAMAccountName` | Tên đăng nhập kiểu cũ, thường dùng trong một domain; không mặc nhiên duy nhất giữa mọi domain. |
| `userPrincipalName` (UPN) | Định danh đăng nhập dạng `user@suffix`; suffix thực tế có thể khác tên DNS của domain. |
| `distinguishedName` | Địa chỉ hiện tại của đối tượng trong cây; có thể thay đổi khi rename/move. |
| `objectGUID` | Định danh đối tượng AD thường ổn định qua rename/move trong vòng đời đối tượng; phù hợp cho liên kết danh tính khi dùng AD DS. |
| `objectSid` | Định danh bảo mật Windows, có ý nghĩa với security principals và ACL; không thay cho mọi khóa nghiệp vụ. |
| `member` / `memberOf` | Biểu diễn quan hệ nhóm theo hướng khác nhau; không được giả định `memberOf` luôn liệt kê toàn bộ nhóm lồng nhau hay primary group. |

**LDAP bind vào AD DS không đồng nghĩa đăng nhập Kerberos/SSO.** AD DS có thể xác thực bằng LDAP và cũng cung cấp Kerberos trong môi trường domain. Ứng dụng web cần trải nghiệm SSO, token và chính sách MFA/Conditional Access thường sẽ làm việc với một identity provider qua **OpenID Connect/SAML**, tùy kiến trúc. **Microsoft Entra ID** là dịch vụ danh tính đám mây khác AD DS; có thể tích hợp/synchronization, nhưng không được coi là một endpoint LDAP AD DS thông thường.

### Nhóm trực tiếp và nhóm lồng nhau

Giả sử:

```text
Lan  ──member of──>  dev-team  ──member of──>  app-editors
Ứng dụng yêu cầu quyền APP_EDIT để sửa dữ liệu.
```

Chỉ đọc `memberOf` trực tiếp của Lan có thể thấy `dev-team` mà bỏ sót `app-editors`. Khi chính sách cho phép nhóm lồng nhau, cần giải quyết **membership theo quan hệ bắc cầu** bằng cơ chế hỗ trợ của AD, hoặc logic riêng đã kiểm soát độ sâu/hiệu năng. Một filter AD chuyên biệt cho quan hệ DN là:

```ldap
(member:1.2.840.113556.1.4.1941:=CN=Lan Nguyen,OU=Engineering,DC=corp,DC=example)
```

Đây là ví dụ tìm các group mà Lan là thành viên trực tiếp/gián tiếp khi truy vấn đúng search base/group scope. OID `1.2.840.113556.1.4.1941` là matching rule của AD; **không áp nguyên xi cho mọi LDAP server**. Với nhiều nhóm lồng nhau, search có thể tốn tài nguyên; phải kiểm soát phạm vi và thử nghiệm với dữ liệu thực tế. Sau cùng, ứng dụng ánh xạ nhóm AD được chấp thuận sang authority của ứng dụng, không mặc định cho mọi group AD quyền tương đương.

## 5. Tích hợp với Spring Security: chọn đúng trách nhiệm

Trong một ứng dụng **Spring Security 6.x (Servlet/Spring Boot 3.x)** sử dụng username/password và LDAP bind, các thành phần chính gồm:

- **ContextSource:** thông số kết nối và base DN của directory, tương tự một nguồn kết nối.
- **LdapBindAuthenticationManagerFactory / LdapAuthenticator:** tìm user DN và thực hiện bind bằng thông tin người dùng.
- **LdapAuthoritiesPopulator:** đọc group/attribute và biến thành authorities nếu có cấu hình phù hợp.
- **SecurityFilterChain:** xác định đường dẫn cần xác thực, cơ chế login và quy tắc truy cập.

Gradle (ví dụ dự án Spring Boot đã được quản lý phiên bản):

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.security:spring-security-ldap")
}
```

Ví dụ cấu hình Java sau là **đoạn tích hợp trong một ứng dụng Spring Boot có các dependency trên**, không phải chương trình `java` độc lập. URL, base DN, search base và tên attribute **phải khớp directory thực tế**; ví dụ này mô phỏng schema `uid`/`ou=People`, chưa cấu hình group-to-role.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LdapAuthenticationConfig {

    @Bean
    BaseLdapPathContextSource ldapContextSource() {
        // LDAP_URL = ldaps://ldap.corp.example:636/dc=corp,dc=example
        var source = new DefaultSpringSecurityContextSource(
                System.getenv("LDAP_URL"));
        source.setUserDn(System.getenv("LDAP_READER_DN"));
        source.setPassword(System.getenv("LDAP_READER_PASSWORD"));
        return source;
    }

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource ldapContextSource) {
        var factory = new LdapBindAuthenticationManagerFactory(ldapContextSource);
        factory.setUserSearchBase("ou=People");
        factory.setUserSearchFilter("(uid={0})");
        return factory.createAuthenticationManager();
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            AuthenticationManager ldapAuthenticationManager) throws Exception {
        http.authenticationManager(ldapAuthenticationManager);
        http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
        http.formLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

Giải thích từng điểm:

1. `LDAP_URL` chứa URL LDAPS **và base DN** như trong comment. `LDAP_READER_DN` và `LDAP_READER_PASSWORD` là tài khoản đọc để tìm DN; phải được cấu hình an toàn và xác minh ở startup. Mật khẩu thực tế lấy từ secret manager hoặc cơ chế cấu hình bí mật thích hợp, không hard-code trong source.
2. `setUserSearchBase("ou=People")` làm search dưới `ou=People,dc=corp,dc=example`. Nếu người dùng trải ở nhiều OU, điều chỉnh base cho đúng cây và scope; `(uid={0})` là pattern filter được framework xử lý tham số.
3. Sau khi tìm DN, bind authenticator dùng mật khẩu người dùng để xác thực với server. Đây là **bind authentication**; Spring Security không tự đọc hash mật khẩu để so sánh qua `UserDetailsService`.
4. Filter chain yêu cầu đăng nhập cho mọi request và cung cấp form login. Trong ứng dụng API hoặc có SSO, cần chọn cơ chế đăng nhập/session/token khác phù hợp.
5. Ví dụ **chưa gán quyền theo nhóm**: nếu endpoint cần `hasRole("ADMIN")`, phải cấu hình truy vấn group, ánh xạ group sang `GrantedAuthority` và kiểm tra chính sách; một login thành công không tự tạo ra `ROLE_ADMIN`.

Đối với AD DS, có thể dùng cách tìm theo các thuộc tính AD (thí dụ `sAMAccountName` hoặc `userPrincipalName`) hoặc provider chuyên dụng `ActiveDirectoryLdapAuthenticationProvider` khi phù hợp quy ước AD. **Không sao chép filter `(uid={0})` sang AD rồi mặc định đúng**: xác minh suffix UPN, domain, vị trí account, group schema và quyền truy vấn trên hệ thống thực.

Cấu hình này cần một directory/AD test riêng và chứng chỉ TLS đáng tin cậy để kiểm thử end-to-end. Không dùng `ldap://` không mã hóa chỉ vì dễ thử nghiệm rồi đưa nguyên vào production.

## 6. LDAP filter injection và cách truyền tham số an toàn

Filter LDAP có ký tự điều khiển như `*`, `(`, `)`, `\` và NUL. Nếu nối input trực tiếp thành filter, ví dụ `"(uid=" + username + ")"`, chuỗi độc hại có thể đổi ý nghĩa truy vấn hoặc gây lỗi. Trong code tích hợp, ưu tiên API/framework có **parameter binding và escaping cho LDAP filter**, đồng thời kiểm tra giá trị nhập, độ dài và tính duy nhất kết quả. Escaping **filter** khác escaping **DN**; không dùng thay thế cho nhau.

Ví dụ Java 17+ độc lập sau chỉ minh họa cách escape các ký tự đặc biệt của **giá trị LDAP filter**, không thực hiện xác thực LDAP và không thay thế API thư viện đã kiểm chứng:

```java
public class LdapFilterEscapeDemo {
    static String escapeFilter(String value) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '\\' -> result.append("\\5c");
                case '*'  -> result.append("\\2a");
                case '('  -> result.append("\\28");
                case ')'  -> result.append("\\29");
                case '\u0000' -> result.append("\\00");
                default -> result.append(ch);
            }
        }
        return result.toString();
    }

    public static void main(String[] args) {
        String username = "lan*)(uid=*)";
        System.out.println("(uid=" + escapeFilter(username) + ")");
    }
}
```

Lưu tệp `LdapFilterEscapeDemo.java` rồi chạy:

```bash
javac LdapFilterEscapeDemo.java
java LdapFilterEscapeDemo
```

Kết quả stdout chính xác:

```text
(uid=lan\2a\29\28uid=\2a\29)
```

Dấu `*` trong input đã thành ký tự literal `\2a`, không còn là wildcard của filter. Trong hệ thống thật, dùng bộ mã hóa LDAP của framework, giới hạn filter/search base và không đưa giá trị từ request vào vị trí cấu trúc (tên attribute, toán tử, DN gốc) một cách tùy ý.

## 7. Bảo mật và vận hành khi LDAP là nguồn danh tính tổ chức

**Kênh truyền và danh tính máy chủ**

- Dùng **LDAPS** (thông dụng cổng TCP **636**) hoặc **StartTLS** nâng cấp kết nối LDAP (thông dụng cổng **389**) trước khi trao đổi thông tin nhạy cảm; luôn xác thực certificate chain và hostname. Tránh simple bind truyền mật khẩu qua kết nối không mã hóa.
- Cổng AD Global Catalog thường là **3268** (LDAP) và **3269** (TLS). GC phục vụ mục đích và tập thuộc tính riêng; không coi nó luôn giống endpoint LDAP trên DC ở cổng 389/636.
- Đặt timeout kết nối/truy vấn, giới hạn phạm vi search, dùng paging khi truy vấn lớn, xử lý referral khi cần và lựa chọn DC/failover phù hợp. Không vô hạn số lần retry đăng nhập.
- Không vô hiệu hóa kiểm tra chứng chỉ, không log mật khẩu, bind credential hoặc token, và không gửi LDAP traffic qua Internet công khai chỉ vì endpoint truy cập được.

**Danh tính, quyền và vòng đời**

- Tài khoản dịch vụ dùng cho search chỉ cần các quyền đọc thực sự cần; tài khoản ứng dụng thông thường không được cấp quyền sửa directory.
- Thiết kế khóa nhận diện người dùng ổn định (AD `objectGUID` là một ví dụ), chính sách xử lý user đổi tên, đổi OU, nghỉ việc, khóa tài khoản và thay đổi group.
- Kiểm tra **group nested**, group scope, domain trust và quyền đọc thuộc tính trước khi ánh xạ role. Cần chính sách rõ nếu nhóm bị đổi, bị xóa hoặc dữ liệu ở DC chưa hội tụ.
- Xem LDAP là thành phần của hệ thống xác thực: rate limiting, giám sát đăng nhập, session management và MFA/SSO (nếu yêu cầu) cần triển khai bằng kiến trúc phù hợp, không tự phát sinh từ một thao tác LDAP bind.
- Không tiết lộ chi tiết “user tồn tại nhưng bị khóa” cho người ngoài qua thông báo đăng nhập. Ghi mã lỗi nội bộ có kiểm soát để đội vận hành phân biệt nguyên nhân.

**Chẩn đoán lỗi có hệ thống**

| Hiện tượng | Nơi cần kiểm tra trước |
|---|---|
| Không tìm thấy user | Search base/scope/filter, tên thuộc tính (`uid` hay `sAMAccountName`), quyền đọc, nhiều OU/domain. |
| LDAP bind thất bại | Mật khẩu, trạng thái tài khoản/chính sách máy chủ, DN/UPN, kết nối tới đúng domain; không hiển thị chi tiết cho người dùng. |
| TLS/SSL handshake lỗi | CA/truststore, hostname, thời hạn và EKU chứng chỉ, cấu hình DC, DNS/port. |
| Đăng nhập thành công nhưng HTTP 403 | Quy tắc authorization, ánh xạ LDAP group sang Spring authority, prefix `ROLE_`, nested groups và phạm vi domain. |
| Nhóm/thuộc tính khác nhau giữa các lần đọc | DC/GC đang được hỏi, replication, referral, cache, visibility/ACL và độ trễ cập nhật. |
| Chậm khi có nhiều user/group | Filter quá rộng, index, paging, recursive group search, timeout, đo latency từng bước. |

## 8. Tình huống áp dụng: ứng dụng quản lý yêu cầu nội bộ

Giả sử một tổ chức dùng AD DS. Lan có tên đăng nhập `lan@corp.example`, là thành viên nhóm `dev-team`; `dev-team` thuộc nhóm `app-editors`. Ứng dụng yêu cầu authority `APP_EDIT` để duyệt yêu cầu.

1. Lan nhập thông tin đăng nhập vào giao diện ứng dụng; Spring Security xác thực thông qua cơ chế đã chọn. Nếu dùng LDAP bind thì LDAP/DC xác nhận thông tin tài khoản.
2. Ứng dụng lấy định danh ổn định của Lan và các group theo quy tắc truy vấn đã thiết kế. Nếu chỉ đọc direct `memberOf`, ứng dụng có thể bỏ sót `app-editors`.
3. Chính sách ánh xạ “thành viên (kể cả nested membership được cho phép) của `app-editors`” thành `APP_EDIT`. Chỉ khi authority có mặt mới cho phép hành động; nếu thiếu, từ chối dù đăng nhập thành công.
4. Khi Lan chuyển phòng ban, group membership được thay đổi trong AD. Ứng dụng phải có chính sách làm mới group cache/session để việc thu hồi quyền có hiệu lực đúng hạn; tránh giữ quyền cũ vô thời hạn.

Thiết kế tốt tách rời **nguồn danh tính (directory)**, **cách chứng minh danh tính (LDAP bind/Kerberos/OIDC tùy luồng)** và **quyết định cấp quyền (quy tắc ứng dụng)**. Nhờ đó việc đổi OU, đăng nhập theo UPN hoặc bổ sung SSO không kéo theo việc gán quyền tùy tiện.

## 9. Những điều cần tự kiểm tra sau bài học

1. Có thể dùng LDAP với directory không phải Microsoft AD không? **Có.** LDAP là giao thức; AD DS và OpenLDAP là những hệ thống có thể cung cấp giao diện LDAP.
2. User bind thành công có chắc được gọi API admin không? **Không.** Authentication khác authorization; cần role/authority và chính sách ứng dụng.
3. `DN` và `sAMAccountName` có tương đương nhau không? **Không.** DN chỉ vị trí hiện tại trong cây; sAMAccountName là thuộc tính tên tài khoản trong quy ước AD.
4. Vì sao direct `memberOf` có thể thiếu quyền? **Vì nested groups và các quy tắc riêng về membership**, nên phải xác định cách giải quyết quan hệ nhóm theo chính sách.
5. Có thể bật MFA bằng cách đổi `ldap://` sang `ldaps://` không? **Không.** LDAPS mã hóa đường truyền; MFA cần giải pháp xác thực/IdP và luồng tích hợp đáp ứng MFA.

## Tài liệu tham khảo

- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html): bind authentication, ContextSource, search filter và mapping authorities.
- [Microsoft Learn — LDAP Search Filter Syntax](https://learn.microsoft.com/en-us/windows/win32/adsi/search-filter-syntax): cú pháp filter và matching rule cho AD, gồm quy tắc nested membership.
- [Microsoft Learn — Configure certificates for LDAP over SSL in AD DS](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/configure-ldap-signing-certificates): chứng chỉ và kiểm tra LDAPS.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): đặc tả các thao tác giao thức LDAP.
