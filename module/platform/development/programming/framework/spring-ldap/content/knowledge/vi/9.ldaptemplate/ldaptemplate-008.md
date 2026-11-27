# Authenticate và compare attribute

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **xác thực bằng LDAP bind** với **so sánh một thuộc tính của entry** theo matching rule của LDAP server.
- Giải thích luồng `LdapTemplate.authenticate(...)`: tìm entry người dùng theo filter, xác định DN và thử bind bằng mật khẩu được cung cấp.
- Sử dụng đúng hai nhóm overload `authenticate`: phiên bản cũ trả `boolean` và API nhận `LdapQuery` có quy ước ngoại lệ khác.
- Hiểu LDAP **Compare operation** (RFC 4511), kết quả `compareTrue`/`compareFalse` và mối quan hệ với `EQUALITY` matching rule.
- Biết rằng `compare(...)` được cung cấp bởi `SpringSecurityLdapTemplate` trong Spring Security LDAP, **không phải** một phương thức `compare` phổ quát của `LdapTemplate` core.
- Thiết kế luồng đăng nhập, kiểm tra membership và xử lý lỗi an toàn: TLS, tài khoản bind, escape filter, search scope, mật khẩu rỗng, ACL và kiểm thử tích hợp.

Bài thuộc chương **LdapTemplate** của module **SPRING_LDAP**. Đây là phần kết nối giữa việc truy cập directory qua `ContextSource`, tìm kiếm theo DN/filter, xác thực bằng bind và so sánh thuộc tính; từ đó xác định lúc nào cần `LdapTemplate`, `LdapClient`, Spring Data LDAP hay Spring Security LDAP.

## 1. Hai câu hỏi nghiệp vụ khác nhau

Giả sử thư mục LDAP có các entry:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Lan
sn: Nguyen
mail: lan@example.org

dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
~~~

Ứng dụng có hai yêu cầu:

1. **Người đăng nhập đưa username `lan` và mật khẩu.** Ứng dụng cần kiểm tra server có chấp nhận credentials của entry người dùng hay không.
2. **Người dùng `lan` đã được xác thực, ứng dụng muốn biết DN của họ có trong nhóm `developers` không.** Ứng dụng cần kiểm tra một giá trị thuộc tính `member` của group.

Hai câu hỏi này không thể giải bằng cùng một phép so sánh chuỗi trong Java:

| Mục đích | Đối tượng kiểm tra | Cách phù hợp |
| --- | --- | --- |
| Kiểm tra mật khẩu của người dùng | Credentials của DN người dùng | LDAP **bind** authentication |
| Kiểm tra thuộc tính `member` chứa DN | Giá trị attribute trong entry nhóm | LDAP **Compare** hoặc equality test do server thực thi, tùy API |
| Tìm DN người dùng theo username | `uid`, base, scope và filter | LDAP search, ví dụ qua `LdapTemplate` |
| Lấy toàn bộ nhóm/roles của user | Các entry nhóm, membership và ánh xạ authority | Group search/authority mapper phù hợp |
| Quyết định user có thể gọi API admin không | Principal, authorities và chính sách ứng dụng | Authorization của Spring Security |

**Xác thực (authentication) trả lời “đây là ai?”. So sánh thuộc tính trả lời “giá trị này có khớp giá trị trong entry không?”. Phân quyền (authorization) trả lời “người này được làm gì?”.**

## 2. Kiến trúc: ContextSource, tìm DN, bind và compare

Spring LDAP thường sử dụng `ContextSource` để quản lý cấu hình truy cập directory. Một `LdapTemplate` dùng context này cho các thao tác search/lookup và xác thực thuận tiện.

~~~mermaid
flowchart TB
    App["Ứng dụng nhận username + password"]
    Search["LdapTemplate tìm user theo uid<br/>Search base + filter + scope"]
    Found{"Tìm đúng một DN?"}
    Bind["ContextSource.getContext(userDn, password)<br/>Tạo context bằng danh tính người dùng"]
    Valid{"Server chấp nhận bind?"}
    Good["Xác thực thành công"]
    Deny["Không xác thực / báo lỗi an toàn"]
    App --> Search --> Found
    Found -->|"Có"| Bind --> Valid
    Found -->|"Không / nhiều entry"| Deny
    Valid -->|"Có"| Good
    Valid -->|"Không"| Deny
    Compare["Kiểm tra membership/attribute sau xác thực<br/>bằng rule của server"]
    Good --> Compare
~~~

Một số điểm cần nhớ:

- Việc **tìm DN** có thể dùng tài khoản dịch vụ có quyền search, trong khi bước **bind** dùng DN và mật khẩu của người đăng nhập.
- **LDAP server** quyết định credentials có hợp lệ theo cơ chế bind và chính sách account hay không.
- `LdapTemplate.authenticate` không biến một LDAP entry thành HTTP session hoặc tự sinh đầy đủ `Authentication`/authorities của Spring Security.
- `compare`/equality chỉ kiểm tra một assertion về thuộc tính; thành công không thay thế việc bind xác thực.
- Không bao giờ cần đọc `userPassword` của người dùng rồi tự dùng `String.equals(...)` để triển khai xác thực.

## 3. Cấu hình ContextSource an toàn

Ví dụ một Spring Boot application có LDAP client:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=directory-reader,ou=services,dc=example,dc=org
    # Lấy spring.ldap.password từ environment/secret manager.
~~~

Ở ví dụ trên:

- Server URL là endpoint kết nối LDAP qua TLS.
- `base` là `dc=example,dc=org`.
- `username` là **bind DN của tài khoản dịch vụ**, không phải username của người đang đăng nhập vào ứng dụng.
- Trong nhiều phương thức Spring LDAP, search base `ou=people` là **DN tương đối** với `dc=example,dc=org`.
- Tài khoản dịch vụ chỉ cần quyền tìm kiếm các entry phục vụ đăng nhập và quyền đọc tối thiểu theo thiết kế ACL.

Một ứng dụng có thể dùng dependency `org.springframework.ldap:spring-ldap-core` để sử dụng `LdapTemplate`. Với Spring Boot có Spring Data LDAP starter, thư viện LDAP liên quan có thể được quản lý qua starter. Nếu cần các API của **Spring Security LDAP** như `SpringSecurityLdapTemplate` hoặc thiết lập authentication providers, cần dependency `spring-security-ldap` cùng các thư viện Spring Security thích hợp.

**Bảo vệ kết nối:** simple bind truyền credentials qua LDAP; dùng LDAPS hoặc StartTLS đã xác thực certificate chain/hostname theo chính sách. Không dùng LDAP plaintext để gửi password trong production và không tắt kiểm tra chứng chỉ chỉ để làm ví dụ chạy được.

## 4. LdapTemplate.authenticate thực hiện những gì?

Trong Spring LDAP core, `LdapTemplate.authenticate(...)` hỗ trợ xác thực bằng cách:

1. **Search** một entry người dùng theo base, scope và filter.
2. Xác định DN của entry được tìm thấy.
3. Thử tạo context dùng DN đó và password đầu vào, thường thông qua `ContextSource.getContext(String principal, String credentials)`.
4. Đánh giá thành công/thất bại hoặc phát sinh ngoại lệ theo **overload** được chọn.

Ở bước 1, filter dùng username để **định vị** entry. Việc filter khớp **không** có nghĩa mật khẩu hợp lệ; bước 3 mới kiểm tra điều đó.

### 4.1. Overload cũ trả boolean

Một dạng API được dùng trong nhiều mã nguồn Spring LDAP:

~~~java
boolean ok = ldapTemplate.authenticate(
    "ou=people",
    new EqualsFilter("uid", username).encode(),
    password
);
~~~

Đây là overload `authenticate(String base, String filter, String password)`; trả `true` nếu xác thực thành công, `false` nếu thất bại theo hợp đồng của overload đó.

**Lưu ý phiên bản:** trong API Spring LDAP hiện hành, các overload cũ nhận base/filter/password đã được **đánh dấu deprecated**, và tài liệu hướng dẫn chuyển sang các overload dùng `LdapQuery`. Chúng vẫn hữu ích để hiểu hoặc bảo trì code cũ, nhưng không nên chọn làm API mặc định cho dự án mới khi phiên bản đã hỗ trợ API mới. Ngoài kết quả boolean, lỗi hạ tầng hoặc kết quả tìm kiếm không duy nhất vẫn có thể phát sinh ngoại lệ tùy tình huống.

### 4.2. API hiện đại dùng LdapQuery

Ví dụ minh họa với `LdapQueryBuilder`:

~~~java
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryCredentialVerifier {

    private final LdapTemplate ldapTemplate;

    public DirectoryCredentialVerifier(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void verify(String username, String password) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("Username không hợp lệ");
        }
        if (password == null || password.isEmpty()) {
            throw new IllegalArgumentException("Mật khẩu không được rỗng");
        }

        LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")
            .searchScope(SearchControls.SUBTREE_SCOPE)
            .where("uid").is(username);

        // Thành công: trả về bình thường.
        // Không tìm được, nhiều entry, credentials sai hoặc lỗi LDAP:
        // xử lý theo loại ngoại lệ thực tế của phiên bản Spring LDAP.
        ldapTemplate.authenticate(query, password);
    }
}
~~~

Ở đây:

- `LdapQueryBuilder.where("uid").is(username)` xây equality filter với cơ chế encode giá trị, tránh ghép chuỗi filter từ input.
- `SUBTREE_SCOPE` giúp tìm người dùng dưới nhiều OU con của `ou=people`; nếu directory phẳng và chỉ muốn con trực tiếp, có thể dùng `ONELEVEL_SCOPE` phù hợp.
- `authenticate(LdapQuery, String)` có kiểu trả **`void`**, **không** phải boolean. API mới dùng **ngoại lệ để thể hiện thất bại**; code gọi cần phân loại rồi chuyển thành phản hồi authentication phù hợp.
- Một user search filter dùng cho xác thực phải xác định **đúng một entry**, không chỉ trả một tập hợp kết quả gần đúng.

Ví dụ là một service kiểm tra credentials ở mức LDAP, **không phải** toàn bộ hệ thống login Spring Security. Trong một ứng dụng web được Spring Security bảo vệ, nên giao việc chuyển kết quả xác thực thành `Authentication` và quản lý authorization cho cơ chế LDAP authentication của Spring Security.

### 4.3. Không nhầm cách xử lý ngoại lệ giữa hai overload

| API | Kiểu trả | Hành vi cần thiết kế |
| --- | --- | --- |
| `authenticate(String base, String filter, String password)` | `boolean` | Xem `true`/`false` theo hợp đồng API cũ; vẫn xử lý lỗi không hợp lệ/hạ tầng |
| `authenticate(Name base, String filter, String password)` | `boolean` | Tương tự; tên base là kiểu `Name` |
| `authenticate(LdapQuery query, String password)` | `void` | Kết thúc bình thường biểu thị thành công; thất bại dùng ngoại lệ |
| `authenticate(LdapQuery query, String password, mapper)` | `T` | Trả object từ mapper chạy theo context đã xác thực, hoặc phát sinh ngoại lệ |

Theo Javadoc, các overload dùng `LdapQuery` chủ động ném ngoại lệ thay vì sử dụng callback lỗi của API cũ. Trong code production hãy đọc contract chính xác của **phiên bản Spring LDAP** đã triển khai; không viết:

~~~java
boolean ok = ldapTemplate.authenticate(query, password);
// SAI: overload nhận LdapQuery, String có kiểu trả void.
~~~

### 4.4. Vì sao phải xử lý mật khẩu rỗng trước khi bind?

Trong một số cấu hình LDAP, simple bind với username/principal nhưng password rỗng có thể được xử lý theo cơ chế bind không xác thực/anonymous, tùy server và provider. Vì thế **không để mật khẩu rỗng đi vào phép kiểm tra credentials** nếu nghiệp vụ yêu cầu đăng nhập bằng mật khẩu.

Điều kiện `password == null || password.isEmpty()` trong ví dụ là lớp bảo vệ tối thiểu. Nếu hệ thống có chính sách về độ dài, khóa account, MFA, rate limiting hoặc password reset, những chính sách đó phải được thực thi ở tầng thích hợp; không thay thế bằng phép `trim()` hoặc tự sửa password trước khi gửi server.

**Không tự gọi `password.trim()` hoặc lowercase mật khẩu.** Mật khẩu có thể hợp lệ với khoảng trắng và case riêng; thay đổi chuỗi trước khi bind làm thay đổi credentials người dùng cung cấp.

## 5. Chọn đúng search base, filter và danh tính

Ví dụ directory có hai entry:

~~~text
uid=lan,ou=people,dc=example,dc=org
uid=minh,ou=engineering,ou=people,dc=example,dc=org
~~~

Search dưới `ou=people` với scope `ONELEVEL` không thấy `uid=minh`. Nếu dùng `SUBTREE`, server có thể tìm entry trong OU lồng nhau. Kết quả phụ thuộc cả ACL đọc và filter.

### 5.1. Filter phải xác định duy nhất một user

Một filter như:

~~~ldap
(cn=*Lan*)
~~~

không thích hợp để định vị danh tính đăng nhập. Nhiều người có thể cùng `cn` hoặc có tên gần giống. Nên dùng một thuộc tính login được tổ chức quản lý sao cho xác định đúng một entry, ví dụ `uid` nếu directory có quy tắc uniqueness tương ứng.

**Cảnh báo:** tên thuộc tính `uid` **không tự bảo đảm uniqueness toàn directory** trên mọi server. Hãy đặt chính sách schema/index/uniqueness hoặc xác minh kết quả duy nhất, nhất là khi có nhiều OU hoặc tenant.

### 5.2. Đừng dùng DN từ input một cách tùy tiện

Nếu username đến từ HTTP request, không ghép trực tiếp:

~~~java
String filter = "(uid=" + username + ")";
~~~

Ký tự `*`, `(`, `)` hoặc backslash có thể làm thay đổi cấu trúc và ý nghĩa filter. Dùng `EqualsFilter` hoặc `LdapQueryBuilder`. Khi xây DN từ các thành phần, dùng `LdapNameBuilder` hoặc `Rdn` theo quy tắc escape DN, **không** thay filter escaping bằng DN escaping.

Nếu ứng dụng đã biết full DN của user từ nguồn đáng tin cậy, có thể thiết kế bind phù hợp qua `ContextSource`/Spring Security; không cần search lại theo một display name không ổn định. Nhưng phải phân biệt full DN với DN tương đối của `ContextSource.base`.

### 5.3. Trường hợp không tìm được hoặc tìm quá một entry

Không nên tự động “lấy entry đầu tiên” khi user search trả nhiều entry. Với authentication, **tính duy nhất là điều kiện quan trọng**; chọn tùy tiện có thể khiến credential của người khác hoặc một entry ngoài ý định được dùng.

Tương tự, không nên tự động nói mật khẩu sai khi tìm kiếm không được do ACL hoặc server timeout. Phản hồi cho người dùng cuối có thể được thiết kế chung chung để tránh dò tài khoản, nhưng log vận hành và metrics phải phân biệt được loại lỗi.

## 6. LDAP Compare operation là gì?

RFC 4511 định nghĩa **Compare operation** riêng với Search và Bind. Compare Request về mặt khái niệm chứa:

- **Entry DN** cần so sánh.
- **Attribute Value Assertion (AVA)** gồm tên thuộc tính và giá trị yêu cầu so.
- LDAP server kiểm tra assertion đối với thuộc tính của entry đó, áp dụng **EQUALITY matching rule** được định nghĩa trong schema.

Ví dụ nghiệp vụ:

~~~text
Entry DN:
  cn=developers,ou=groups,dc=example,dc=org

Attribute:
  member

Assertion value:
  uid=lan,ou=people,dc=example,dc=org
~~~

Ứng dụng muốn biết `member` của group có giá trị DN này theo matching rule của server hay không. Nó **không** yêu cầu lấy toàn bộ giá trị `member` về rồi so chuỗi trong Java.

### 6.1. Kết quả Compare không chỉ là true/false trong mọi tình huống

Theo RFC 4511, Compare Response có các mã:

| Kết quả | Ý nghĩa |
| --- | --- |
| `compareTrue` | Giá trị assertion khớp một giá trị của attribute (hoặc subtype liên quan) theo EQUALITY rule |
| `compareFalse` | Assertion không khớp các giá trị liên quan |
| Mã lỗi phù hợp | Không thể so hợp lệ, server gặp lỗi hoặc có vấn đề về DN, schema, ACL, rule... |

Điều này nghĩa là không thể coi mọi lỗi là `compareFalse`. Ví dụ quyền so sánh bị từ chối, DN không tồn tại hoặc server không có matching rule áp dụng được phải được nhận diện khác với việc một assertion hợp lệ nhưng không khớp.

### 6.2. Matching rule của attribute quyết định cách so

Với attribute type thông dụng:

| Thuộc tính / loại giá trị | Matching rule liên quan | Hệ quả |
| --- | --- | --- |
| `cn` kiểu Directory String | Có thể dùng `caseIgnoreMatch` theo schema thông dụng | `Lan` và `lan` có thể khớp |
| Attribute tùy chỉnh case-sensitive | Có thể dùng `caseExactMatch` | Case của giá trị có thể làm kết quả khác |
| `member` chứa DN | Thường dùng `distinguishedNameMatch` | So theo cấu trúc DN/RDN và rule của thành phần |
| Attribute nhị phân | Có rule so byte phù hợp nếu schema định nghĩa | Không ép về `String` rồi so |
| Attribute không có EQUALITY phù hợp | Tùy rule/schema/server | Có thể không đánh giá được theo cách ứng dụng mong muốn |

**Tên attribute** không phân biệt hoa/thường theo định nghĩa LDAP descriptor, nhưng **giá trị** có case-sensitive hay không phụ thuộc schema. Đừng tự lower-case DN hoặc username trước khi compare để “bắt chước server”.

### 6.3. Compare và Search khác nhau trên giao thức

~~~mermaid
flowchart LR
    A["Có DN + attribute + value"] --> B{"Muốn làm gì?"}
    B -->|"So assertion tại một entry"| C["LDAP CompareRequest<br/>trả compareTrue / compareFalse / error"]
    B -->|"Tìm entry thỏa filter"| D["LDAP SearchRequest<br/>base + scope + filter"]
    B -->|"Xác thực credentials"| E["LDAP BindRequest<br/>principal + password"]
~~~

Có thể tìm kiếm một entry bằng base-object scope với filter equality để hỏi một câu giống compare, nhưng **SearchRequest không phải CompareRequest**. Cách ACL được áp dụng, dữ liệu được trả và chi phí truy vấn có thể khác nhau. Nếu yêu cầu chính xác opcode LDAP Compare, phải dùng client/provider hỗ trợ Compare và kiểm chứng đường đi trên phiên bản đang chạy.

## 7. So sánh attribute trong hệ sinh thái Spring

### 7.1. LdapTemplate core không có API compare chung như một số LDAP client khác

Trong tài liệu API Spring LDAP core, các operation của `LdapTemplate` tập trung vào `search`, `lookup`, `bind`, `modifyAttributes`, `authenticate`... **Đừng viết ví dụ gọi `ldapTemplate.compare(dn, attr, value)` như một phương thức core được bảo đảm tồn tại.**

Spring Security LDAP có lớp `org.springframework.security.ldap.SpringSecurityLdapTemplate` và công khai:

~~~java
boolean compare(
    String dn,
    String attributeName,
    Object value
);
~~~

Javadoc mô tả phương thức đó dùng để so một giá trị attribute của một directory entry. Đây là một API **Spring Security LDAP**, không phải bằng chứng rằng `LdapTemplate` core có phương thức `compare` cùng chữ ký hoặc mọi provider gửi trực tiếp CompareRequest trên wire.

### 7.2. Ví dụ kiểm tra thành viên nhóm bằng SpringSecurityLdapTemplate

Giả sử `ContextSource.base = dc=example,dc=org` và nhóm ở `ou=groups`:

~~~java
import org.springframework.ldap.core.ContextSource;
import org.springframework.security.ldap.SpringSecurityLdapTemplate;

public class DirectoryGroupChecker {
    private final SpringSecurityLdapTemplate securityLdapTemplate;

    public DirectoryGroupChecker(ContextSource contextSource) {
        this.securityLdapTemplate =
            new SpringSecurityLdapTemplate(contextSource);
    }

    public boolean isDirectMemberOfDevelopers() {
        String groupDn = "cn=developers,ou=groups";
        String userFullDn =
            "uid=lan,ou=people,dc=example,dc=org";

        return securityLdapTemplate.compare(
            groupDn,
            "member",
            userFullDn
        );
    }
}
~~~

Giả định ví dụ:

- `groupDn` được API giải theo base mà `ContextSource` thiết lập; kiểm tra hợp đồng DN của phiên bản thư viện trước khi triển khai.
- Giá trị `member` được lưu theo DN schema của group, còn `userFullDn` là full DN của thành viên cần kiểm tra.
- Tài khoản kết nối được phép kiểm tra membership của group, và server hỗ trợ rule thích hợp.
- Kết quả `true` ở đây chỉ xác nhận **membership trực tiếp** theo cấu trúc group ví dụ, **không** xử lý tự động nested groups, dynamic group hoặc vai trò/authority của ứng dụng.
- Nếu cần bảo đảm operation trên wire thực sự là LDAP CompareRequest, cần xác minh implementation và provider; tên phương thức `compare` không phải chứng cứ đủ.

Không nhận `groupDn` hoặc tên thuộc tính tùy ý từ input ngoài rồi dùng trực tiếp để hỏi những thuộc tính nhạy cảm. Chỉ so các entry/attribute được thiết kế và ủy quyền cho nghiệp vụ.

### 7.3. Nếu chỉ có LdapTemplate: base-object equality search

Khi dùng **Spring LDAP core** mà không có `SpringSecurityLdapTemplate`, có thể đặt SearchRequest với scope **OBJECT** và equality filter để kiểm tra assertion trên một entry:

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;

public boolean hasDirectMember(
        LdapTemplate ldapTemplate,
        String userFullDn) {

    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.OBJECT_SCOPE);
    controls.setReturningAttributes(new String[0]);

    String filter = new EqualsFilter(
        "member", userFullDn
    ).encode();

    List<Boolean> matches = ldapTemplate.search(
        "cn=developers,ou=groups",
        filter,
        controls,
        (AttributesMapper<Boolean>) attrs -> true
    );

    return !matches.isEmpty();
}
~~~

Phép kiểm tra này:

- Đánh giá equality filter **tại entry nhóm**, vì scope OBJECT không xét entry con.
- Không yêu cầu trả giá trị `member` cho client, chỉ dùng một kết quả match.
- Dùng `EqualsFilter` để escape dữ liệu assertion theo cú pháp filter.
- Thường cho đáp án hữu ích trong directory có ACL/search và matching rule phù hợp.

**Giới hạn quan trọng:** đây là **LDAP Search**, không phải LDAP Compare. Một kết quả rỗng còn có thể do ACL che entry, filter bị đánh giá Undefined hoặc base/entry không phù hợp; lỗi server và khác biệt quyền search/compare cần được xem xét riêng. Đừng dùng mẹo này để khẳng định mọi directory sẽ có cùng hành vi với CompareRequest.

### 7.4. Vì sao không tự lấy thuộc tính rồi String.equals?

Ví dụ dễ sai:

~~~java
// Không dùng làm phép kiểm tra membership/identity tổng quát:
String member = (String) attrs.get("member").get();
boolean equal = member.equalsIgnoreCase(userDnString);
~~~

Có ít nhất ba vấn đề:

1. `member` thường là **đa giá trị**; `get()` chỉ trả một giá trị.
2. DN phải được so theo cấu trúc RDN/AVA và matching rule; lower-case toàn bộ string không thay thế `distinguishedNameMatch`.
3. Quyền **read** attribute có thể khác quyền **compare**, và việc kéo toàn bộ thành viên nhóm về client có thể không cần thiết hoặc không được phép.

Để so assertion một thuộc tính, ưu tiên server đánh giá; để xây chính sách phân quyền phức tạp, sử dụng Spring Security LDAP authority mapping theo thiết kế.

## 8. Bind authentication khác so `userPassword` như thế nào?

Một cách làm không an toàn là tìm user rồi đọc:

~~~text
userPassword: {SSHA}...
~~~

sau đó cố so password đầu vào với chuỗi đã lưu. Đây không phải cách xác thực đáng tin cậy vì:

- Mật khẩu có thể được hash, salt, mã hóa hoặc lưu theo cơ chế đặc thù.
- ACL thường không cho đọc `userPassword`.
- Một giá trị hash có salt ngẫu nhiên không thể so nguyên văn với plaintext password.
- Tự triển khai xử lý mật khẩu làm tăng rủi ro rò rỉ dữ liệu và sai chính sách khóa tài khoản.
- Một directory có thể ủy quyền xác thực cho backend khác mà client không nhìn thấy.

**Đối với đăng nhập thông thường, hãy dùng LDAP bind** hoặc provider authentication được hỗ trợ của Spring Security LDAP. LDAP Compare trên `userPassword` có thể được một số directory/cơ chế cho phép trong những điều kiện cụ thể, nhưng không phải chiến lược xác thực mặc định, không hoạt động giống bind ở mọi hệ thống và có thể không phù hợp với password hash có salt ngẫu nhiên.

| Tình huống | Bind | Compare attribute |
| --- | --- | --- |
| Kiểm tra password của user | Phù hợp với cơ chế LDAP authentication | Không nên mặc định thay thế bind |
| Kiểm tra `member` của group | Không phải mục đích của bind | Có thể phù hợp nếu schema/ACL cho phép |
| So `cn` với tên hiển thị | Không phù hợp | Chỉ là phép so dữ liệu, không xác thực |
| Thiết lập danh tính kết nối | Có | Không |
| Tạo HTTP SecurityContext và authorities | Cần tầng Spring Security | Không tự động |

## 9. Spring Security LDAP: authentication và authorization

Một ứng dụng web Spring Security có thể tích hợp LDAP theo nhiều cách, trong đó thường gặp:

- **Bind authentication:** tìm DN của user, bind với mật khẩu người dùng và tạo `Authentication` khi thành công.
- **User DN patterns:** khi cấu trúc DN được biết và đáng tin cậy, có thể xây danh sách pattern thích hợp thay vì search theo display name.
- **Group search/authority mapping:** xác định group membership và ánh xạ thành `GrantedAuthority` hoặc quy tắc bảo vệ endpoint.

**Không gọi `LdapTemplate.authenticate(...)` rồi mặc định HTTP request đã được Spring Security đánh dấu đăng nhập.** Một phương thức Java trả `true` hoặc không ném ngoại lệ mới chỉ là kết quả của thao tác LDAP; session, SecurityContext, MFA, policy và audit vẫn phải được tích hợp đúng tầng.

### Ví dụ thiết kế hợp lý

~~~text
POST /login
  -> Spring Security AuthenticationManager
     -> LDAP bind authentication provider
        -> Tìm DN user trong ou=people
        -> Bind bằng credentials user
        -> Mapping groups/authorities
  -> Authorization bảo vệ /admin/**

GET /profile
  -> Service nghiệp vụ
     -> LdapTemplate.search(...) / lookup(...)
     -> Map uid/cn/mail thành DTO

Kiểm tra member
  -> LDAP group lookup/compare theo schema và ACL
  -> Ánh xạ vào chính sách quyền của ứng dụng
~~~

Đừng trộn user bind context và service bind context trong connection pool một cách tùy tiện. Khi dùng pooling và StartTLS, cần kiểm tra context lifecycle và cách danh tính được tái sử dụng theo provider đang chạy.

## 10. Xử lý lỗi không làm rò rỉ danh tính

Một luồng authentication nên phân biệt **lỗi nghiệp vụ** với **lỗi vận hành** ở tầng nội bộ.

| Trường hợp | Ý nghĩa | Gợi ý xử lý |
| --- | --- | --- |
| Không có entry khớp `uid` | User search không tìm thấy danh tính | Trả lỗi đăng nhập chung, log/metrics phù hợp |
| Nhiều entry khớp filter | Danh tính không xác định duy nhất | Không chọn entry đầu tiên; điều tra cấu trúc/uniqueness |
| Bind bị từ chối | Credentials không được server chấp nhận | Không tiết lộ chính xác trạng thái account cho bên ngoài |
| TLS handshake thất bại | Không thiết lập được kết nối an toàn | Coi là sự cố hạ tầng/chứng chỉ; không tắt kiểm tra TLS |
| Timeout/mất kết nối | Không xác định được kết quả | Không coi đó là password sai theo nghĩa chắc chắn |
| ACL ngăn search/compare | Tài khoản không có quyền cần thiết | Kiểm tra danh tính context, policy và server logs |
| Compare false | Assertion không khớp giá trị của entry | Không tự suy ra người dùng chưa xác thực |
| Attribute thiếu hoặc equality rule không phù hợp | Không so được theo mong đợi | Xem schema, attribute options và dữ liệu |
| Thao tác có thể bị giới hạn tải | Server từ chối hoặc làm chậm request | Rate limiting, monitoring, backoff hợp lý |

Ở API public, có thể dùng một thông báo tổng quát “Thông tin đăng nhập không hợp lệ” để giảm dò tài khoản. Nhưng ở tầng vận hành cần phân biệt được **invalid credentials** với **server unavailable** để không che giấu sự cố hoặc tạo hành vi retry không kiểm soát.

**Không log password, bind credentials hoặc toàn bộ JNDI environment.** Khi log DN, user identifiers hoặc group membership, thực hiện theo chính sách dữ liệu cá nhân của hệ thống.

## 11. Các lỗi lập trình thường gặp

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Gán `authenticate(query, password)` vào `boolean` | API nhận `LdapQuery` trả `void` | Dựa trên hoàn thành/ngoại lệ, hoặc dùng overload phù hợp |
| Coi mọi overload `authenticate` đều trả bool | Contract khác giữa phiên bản/overload | Kiểm tra Javadoc đúng phương thức |
| Gọi `ldapTemplate.compare(...)` | Không phải phương thức chung của core `LdapTemplate` | Dùng Spring Security LDAP compare hoặc search thích hợp |
| Chỉ search `uid` rồi kết luận đã login | Search không kiểm tra password | Thử bind qua authentication provider |
| Chấp nhận password rỗng | Có thể gặp unauthenticated bind ở một số môi trường | Chặn input rỗng, kiểm thử server |
| Dùng filter `(cn=*name*)` để tìm user login | Có thể có nhiều entry không duy nhất | Dùng login attribute và kiểm tra uniqueness |
| Tự ghép input vào `(uid=...)` | LDAP filter injection | `EqualsFilter` hoặc `LdapQueryBuilder` |
| Lowercase mọi password | Thay đổi credentials | Truyền nguyên giá trị, không log |
| So DN bằng `String.equalsIgnoreCase` | Không hiểu escaping/schema | Server matching/LDAP DN semantics |
| Dùng `Attribute.get()` cho `member` đa giá trị | Bỏ sót thành viên khác | So trên server hoặc duyệt toàn bộ giá trị nếu thực sự cần |
| Compare membership rồi cấp quyền admin ngay | Direct member không tự bằng authorization policy | Mapping authorities và chính sách app |
| Tự đọc `userPassword` rồi so | Sai cơ chế hash/ACL, rủi ro bảo mật | LDAP bind |
| Che timeout thành “user không tồn tại” | Làm mất tín hiệu sự cố | Phân loại lỗi ở server và app |
| Bỏ TLS vì môi trường test không tin cert | Rủi ro lộ password | Thiết lập CA/truststore phù hợp |
| Tăng pooling vô hạn khi login chậm | Có thể tăng tải trên LDAP | Đo filter/index/connection và giới hạn concurrency |

## 12. Kiểm thử tích hợp: xác thực và so attribute

Các bài kiểm thử cần một LDAP test server (ví dụ embedded LDAP hoặc directory staging cô lập) với schema và ACL tương tự hệ thống mục tiêu. **Không dùng password hoặc tài khoản production** cho dữ liệu thử nghiệm.

### 12.1. Ma trận kiểm thử authentication

| Case | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| A1 | Username hợp lệ, password đúng | Bind thành công |
| A2 | Username hợp lệ, password sai | Không xác thực |
| A3 | Username rỗng | Bị từ chối trước khi gửi LDAP |
| A4 | Password rỗng | Bị từ chối trước khi bind |
| A5 | Username có `*` hoặc `(` | Filter builder escape literal; không mở rộng tìm kiếm |
| A6 | User nằm dưới OU con | SUBTREE tìm được nếu ACL cho phép |
| A7 | Hai entry cùng match login filter | Không xác thực dựa trên entry tùy ý |
| A8 | Service account không được search OU | Báo lỗi quyền/lookup phù hợp |
| A9 | TLS certificate không được tin cậy | Fail kết nối an toàn; không fallback sang plaintext |
| A10 | LDAP server mất kết nối | Thất bại có kiểm soát, không báo password sai như kết luận chắc chắn |

Kiểm thử **tính duy nhất** đặc biệt quan trọng khi có nhiều tenant hoặc OU. Dữ liệu đăng nhập có thể được phân vùng theo base DN hoặc domain; quy tắc xác định user cần rõ ràng.

### 12.2. Ma trận kiểm thử compare

| Case | Entry/attribute | Điều cần xác minh |
| --- | --- | --- |
| C1 | Group có `member: uid=lan,...` | Assertion với DN của Lan khớp |
| C2 | Group không chứa DN đó | Trả không khớp |
| C3 | Group có nhiều giá trị `member` | Khớp nếu một giá trị tương ứng bằng nhau |
| C4 | Case/escaping khác trong DN | Kết quả theo `distinguishedNameMatch` của server |
| C5 | Group entry không tồn tại | Phân biệt lỗi/không tìm thấy với compare false |
| C6 | Tài khoản không được so/đọc `member` | Hành vi phù hợp ACL; không giả định false |
| C7 | Group lồng nhau | Direct membership chưa đủ để kết luận nested membership |
| C8 | Thuộc tính không có EQUALITY rule phù hợp | Không suy kết quả từ Java string |
| C9 | Dùng base-object equality search thay compare | Xác nhận không nhầm opcode, giới hạn ACL và output |
| C10 | Network/server lỗi trong compare | Báo lỗi hạ tầng, không biến thành “không thuộc nhóm” |

### 12.3. Unit test và integration test giải quyết những gì?

- **Unit test**: kiểm tra validation username/password, việc chọn base/scope, filter encoding và ánh xạ ngoại lệ của service.
- **Integration test với directory**: xác minh bind thật, matching rule, ACL, DN, kết quả compare, khả năng xử lý password policy và TLS.
- **Kiểm thử tải**: đo latency, số lần bind/search, timeout, pooling và limit server dưới concurrency đại diện.

Một unit test chỉ kiểm tra `filter.encode()` không chứng minh bind thành công hoặc compare được máy chủ chấp nhận. Ngược lại, một test dùng tài khoản admin đọc được mọi thuộc tính cũng không chứng minh ACL của service account đã được thiết kế đúng.

## 13. Tình huống thiết kế

**Yêu cầu:** hệ thống nội bộ đăng nhập bằng `uid` trên `ou=people` (có OU con), sau đó chỉ cho phép vào trang quản lý release nếu người dùng là thành viên nhóm `cn=release-managers,ou=groups`.

**Thiết kế đề xuất:**

1. Tìm user bằng login attribute `uid`, search scope SUBTREE, và filter đã escape; không dùng `cn` hiển thị để xác định danh tính.
2. Thử **LDAP bind** để kiểm tra password, không lấy `userPassword` về Java.
3. Khi xác thực thành công, lấy/giữ DN đáng tin cậy của user theo context và base đúng.
4. Tra membership theo `member` bằng API group search/compare thích hợp. Phải biết server dùng `member`, `uniqueMember`, `memberOf` hay schema khác và có nested groups không.
5. Map membership thành authorities và để **Spring Security** quyết định người dùng có quyền gọi endpoint release.
6. Giới hạn tài khoản bind, bảo vệ TLS, không log credentials và thiết kế phản hồi lỗi phù hợp.
7. Kiểm thử người dùng không có quyền, thành viên trực tiếp, thành viên qua nhóm lồng nhau (nếu được hỗ trợ), group không tồn tại, ACL hạn chế và server mất kết nối.

### Câu hỏi tự kiểm tra

1. Vì sao tìm được entry `uid=lan` chưa đồng nghĩa mật khẩu chính xác?
2. `authenticate(LdapQuery, String)` trả `boolean` hay `void`? Nên xử lý thất bại thế nào?
3. Tại sao `authenticate(String, String, String)` có thể xuất hiện trong dự án cũ nhưng không nên là API mặc định cho code mới?
4. LDAP CompareRequest cần những thành phần nào và dùng loại matching rule nào?
5. Vì sao `(member=userDn)` ở scope OBJECT là một LDAP **Search** chứ không phải LDAP CompareRequest?
6. API `compare(String dn, String attributeName, Object value)` thuộc lớp Spring nào?
7. Compare `member` trả true có đủ để xác nhận HTTP user đã đăng nhập và có quyền admin không?
8. Tại sao không tự so `userPassword` đã hash/salt với password plaintext?
9. Vì sao password rỗng cần bị chặn **trước** khi gọi LDAP bind?
10. Trường hợp compare không khớp và trường hợp bị ACL từ chối khác nhau như thế nào?
11. Nếu LDAP server không thể kết nối, có nên đổi lỗi thành “user không tồn tại” không?
12. Những vấn đề nào cần đo khi số lượng yêu cầu login tăng rất nhanh?

**Gợi ý trả lời:** (1) Search chỉ định vị DN, bind mới xác thực; (2) `void`, dùng ngoại lệ; (3) overload base/filter/password bị deprecated ở API hiện hành; (4) entry DN + AVA, EQUALITY rule; (5) vì đó là SearchRequest dùng filter; (6) `SpringSecurityLdapTemplate`; (7) không, còn xác thực/authorization policy; (8) sai hash/ACL và rủi ro; (9) tránh unauthenticated/anonymous bind ngoài ý định; (10) false là không khớp còn lỗi quyền là không được thực hiện; (11) không; (12) lookup/search, bind, TLS, index, pool, connection limits và tỷ lệ lỗi.

## 14. Checklist khi triển khai

- [ ] Xác định login attribute và tính duy nhất của kết quả search.
- [ ] Chọn search base/scope phản ánh đúng OU của user.
- [ ] Dùng `EqualsFilter` hoặc `LdapQueryBuilder`, không ghép filter trực tiếp.
- [ ] Chặn username/password rỗng; không tự trim/lowercase mật khẩu.
- [ ] Hiểu đúng contract overload `authenticate` của phiên bản Spring LDAP.
- [ ] Giao bước kiểm tra password cho LDAP bind, không lấy `userPassword` ra so bằng Java.
- [ ] Dùng API compare/search phù hợp; phân biệt LDAP CompareRequest với SearchRequest.
- [ ] Kiểm tra schema/matching rule của thuộc tính muốn so sánh.
- [ ] Không coi group membership trực tiếp là toàn bộ authorization policy.
- [ ] Sử dụng LDAPS hoặc StartTLS đã xác minh chứng chỉ.
- [ ] Quản lý DN, base và tài khoản bind; không lẫn danh tính trong pooling.
- [ ] Phân loại lỗi bind, không tìm thấy, kết quả trùng, ACL, TLS và timeout.
- [ ] Unit test filter/validation và integration test bind + compare trên directory đại diện.
- [ ] Không đưa password, full môi trường JNDI hoặc dữ liệu nhạy cảm vào logs.

## 15. Tóm tắt

**`LdapTemplate.authenticate` tìm đúng entry người dùng và thử bind với password; đây là kiểm tra credentials, không phải so khớp một Java string.** Các overload cũ có thể trả `boolean`, trong khi API `authenticate(LdapQuery, String)` hiện đại trả `void` và dùng ngoại lệ để báo thất bại.

**LDAP Compare** là operation kiểm tra một assertion thuộc tính tại một DN theo **EQUALITY matching rule** của server. Trong hệ sinh thái Spring, `SpringSecurityLdapTemplate` có API `compare`; nếu chỉ dùng `LdapTemplate` core, có thể thực hiện equality search ở OBJECT scope cho một số nhu cầu nhưng phải ghi nhận nó **không tương đương protocol-level CompareRequest** ở mọi tình huống.

Cuối cùng, xác thực, kiểm tra membership và phân quyền phải được **tách ranh giới**. Kết hợp DN/filter an toàn, schema, ACL, TLS và Spring Security phù hợp để tránh nhầm “tìm thấy entry”, “so attribute thành công” với “đăng nhập và có quyền”.

### Tài liệu tham khảo chính thức

- [Spring LDAP API — LdapTemplate (authenticate overloads)](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP API — LdapOperations](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html)
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Spring Security LDAP API — SpringSecurityLdapTemplate.compare](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/SpringSecurityLdapTemplate.html)
- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
- [RFC 4511 — LDAP: The Protocol (Bind, Search, Compare)](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517)
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 4518 — LDAP: Internationalized String Preparation](https://www.rfc-editor.org/rfc/rfc4518)
