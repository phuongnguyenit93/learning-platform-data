# Search, Compare và đọc thông tin entry trong Spring Data LDAP

## 1. Ba nhu cầu đọc dữ liệu LDAP

Trong **Spring Data LDAP**, ứng dụng Java giao tiếp với dịch vụ thư mục thông qua repository và `LdapTemplate` (thuộc Spring LDAP). Dữ liệu directory được tổ chức thành các **entry** có Distinguished Name (**DN**), các thuộc tính (`uid`, `cn`, `mail`, ...) và một hoặc nhiều `objectClass` xác định quy tắc schema.

Khi xây dựng chức năng tìm nhân viên hoặc kiểm tra thành viên nhóm, ta thường gặp ba nhu cầu:

1. **Search:** chưa biết DN chính xác; tìm các entry thỏa một filter trong phạm vi một nhánh.
2. **Compare:** đã biết DN, thuộc tính và giá trị cần kiểm tra; muốn biết server đánh giá giá trị đó có khớp thuộc tính của entry hay không.
3. **Đọc entry theo DN:** đã biết chính xác DN và muốn lấy các thuộc tính cần thiết của entry đó.

Ba nhu cầu có điểm chung là đọc dữ liệu nhưng **đầu vào, đầu ra và quyền truy cập** khác nhau. Đặc biệt, trong giao thức LDAPv3 không có một thông điệp riêng mang tên `Read`; việc đọc entry cụ thể có thể được thực hiện qua **Search với scope `baseObject`**, hoặc được thư viện Java cung cấp dưới dạng API `lookup`.

### Cây directory minh họa

Giả sử `ContextSource` của ứng dụng đã cấu hình base DN `dc=example,dc=org`:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice                objectClass: inetOrgPerson
│   │   ├── cn: Alice Nguyen
│   │   ├── uid: alice
│   │   └── mail: alice@example.org
│   ├── uid=bob                  objectClass: inetOrgPerson
│   │   ├── cn: Bob Tran
│   │   └── uid: bob
│   └── ou=interns
│       └── uid=carol            objectClass: inetOrgPerson
│           └── uid: carol
└── ou=groups
    └── cn=reviewers             objectClass: groupOfUniqueNames
        ├── cn: reviewers
        └── uniqueMember: uid=alice,ou=people,dc=example,dc=org
~~~

DN đầy đủ của Alice là `uid=alice,ou=people,dc=example,dc=org`. Khi dùng `LdapTemplate` với base được cấu hình ở trên, ta thường truyền DN **tương đối với base**, ví dụ `uid=alice,ou=people`. Trong lệnh `ldapsearch`/`ldapcompare`, truyền DN đầy đủ.

## 2. Phân biệt Search, Compare và đọc theo DN

| Tiêu chí | Search | Compare | Đọc theo DN (`lookup`) |
| --- | --- | --- | --- |
| Đầu vào | Base DN, scope, filter, thuộc tính trả về | Một DN, một tên thuộc tính, một giá trị cần so sánh | Một DN đã biết, danh sách thuộc tính muốn lấy |
| Mục đích | Tìm một hoặc nhiều entry | Kiểm tra một assertion tại đúng một entry | Lấy dữ liệu của một entry |
| Kết quả | Danh sách entry/thuộc tính khớp filter | `compareTrue`, `compareFalse` hoặc lỗi LDAP | Thuộc tính của entry hoặc lỗi khi entry không tồn tại |
| Phạm vi | `OBJECT`, `ONELEVEL`, `SUBTREE` | Một DN cụ thể | Một DN cụ thể |
| Khả năng đọc giá trị | Có, nhưng bị giới hạn bởi thuộc tính được yêu cầu và ACL | Không trả về giá trị thuộc tính | Có, theo thuộc tính được yêu cầu và ACL |
| Công cụ | `LdapTemplate.search(...)`, repository | Lệnh `ldapcompare`, client triển khai Compare; tùy chọn Spring Security LDAP | `LdapTemplate.lookup(...)`, `lookupContext(...)` |

Không nên hiểu Compare là hàm `String.equals(...)` sau khi đọc thuộc tính. **LDAP Compare** do server đánh giá theo **equality matching rule của schema** cho loại thuộc tính tương ứng; ví dụ một số thuộc tính dùng phép so khớp không phân biệt chữ hoa/thường, nhưng điều này phụ thuộc schema.

## 3. Search: tìm entry bằng base DN, scope và filter

Một LDAP Search có các thành phần chính:

- **Base DN:** điểm bắt đầu tìm, ví dụ `ou=people,dc=example,dc=org`.
- **Scope:** `OBJECT` chỉ xét base; `ONELEVEL` xét con trực tiếp; `SUBTREE` xét cả base và mọi hậu duệ.
- **Filter:** điều kiện lọc, ví dụ `(objectClass=inetOrgPerson)`, `(uid=alice)` hoặc `(&(objectClass=inetOrgPerson)(uid=alice))`.
- **Attribute selection:** tên thuộc tính muốn lấy, ví dụ `uid`, `cn`, `mail`.
- **Giới hạn:** giới hạn số kết quả, thời gian và các quy tắc được server cho phép.

Filter `(uid=alice)` mang ý nghĩa **tìm entry có thuộc tính `uid` khớp `alice`** trong phạm vi đã chọn. Filter này không tự xác định DN của Alice. Nếu dùng scope `ONELEVEL` tại `ou=people`, Carol ở sâu dưới `ou=interns` sẽ không được xét, cho dù filter của Carol khớp.

### 3.1. Tìm entry qua `LdapQueryBuilder`

Đoạn mã minh họa dùng `LdapTemplate` đã được Spring Boot hoặc ứng dụng cấu hình với LDAP `ContextSource`. Giả sử ứng dụng chạy Java 17 trở lên để sử dụng `record`.

~~~java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PeopleReader {
    private final LdapTemplate ldapTemplate;

    public PeopleReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record PersonView(String uid, String cn, String mail) {}

    private static String getText(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            return null;
        }
        Object value = attribute.get();
        return value == null ? null : value.toString();
    }

    private static PersonView toPerson(Attributes attrs)
            throws NamingException {
        return new PersonView(
            getText(attrs, "uid"),
            getText(attrs, "cn"),
            getText(attrs, "mail")
        );
    }

    public List<PersonView> searchByUid(String suppliedUid) {
        LdapQuery ldapQuery = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes("uid", "cn", "mail")
            .countLimit(100)
            .timeLimit(3000)
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(suppliedUid);

        return ldapTemplate.search(ldapQuery, PeopleReader::toPerson);
    }
}
~~~

Với dữ liệu minh họa, `searchByUid("alice")` trả về danh sách chứa một `PersonView("alice", "Alice Nguyen", "alice@example.org")`, nếu tài khoản kết nối có quyền tìm và đọc các thuộc tính đó.

Cần hiểu rõ:

- `LdapQueryBuilder` xây dựng filter từ các giá trị đầu vào và **escape giá trị** cho đúng cú pháp LDAP filter. Không tự viết `"(&(uid=" + suppliedUid + ")...)"` vì dễ gây LDAP injection.
- Tên thuộc tính truyền vào `where(...)` phải do mã nguồn đáng tin cậy lựa chọn. Không cho người dùng tùy ý nhập tên thuộc tính để ghép vào query.
- `attributes("uid", "cn", "mail")` chỉ yêu cầu các thuộc tính cần thiết. Không cần tải mọi thuộc tính của entry.
- `.countLimit(100)` và `.timeLimit(3000)` là các giới hạn tìm kiếm tại client/API; server vẫn có thể áp dụng giới hạn thấp hơn, và search có thể phát sinh lỗi khi vượt hạn mức.
- Vì kết quả Search là danh sách, **không được ngầm giả định chỉ có một entry**. Nếu nghiệp vụ đòi duy nhất, phải kiểm tra rõ số kết quả và xử lý cả trường hợp `0` hoặc nhiều hơn `1`.
- Thứ tự kết quả do directory trả về không được mặc định là thứ tự mong muốn; dùng cơ chế sắp xếp được server hỗ trợ hoặc sắp xếp sau khi nhận dữ liệu nếu cần.

`AttributesMapper<T>` nhận các thuộc tính được server trả về và chuyển thành đối tượng Java. Bản thân nó **không cung cấp DN của entry** trong tham số `Attributes`; nếu cần DN trong kết quả, hãy dùng `ContextMapper<T>`/`DirContextOperations` hoặc API mapping entry phù hợp.

### 3.2. Search với `SearchControls` thay vì query builder

Khi cần cấu hình trực tiếp JNDI SearchControls, có thể đặt đoạn mã sau trong một phương thức của lớp `PeopleReader` để dùng lại mapper `toPerson`:

~~~java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
controls.setReturningAttributes(new String[] {"uid", "cn"});
controls.setCountLimit(50);
controls.setTimeLimit(3000);

List<PeopleReader.PersonView> directPeople = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    controls,
    PeopleReader::toPerson
);
~~~

Nếu dùng cây ví dụ, ONELEVEL chỉ xét Alice và Bob; Carol nằm sâu thêm một cấp dưới `ou=interns`. `PeopleReader::toPerson` vẫn có thể trả `mail == null` nếu server không gửi `mail` vì yêu cầu chỉ lấy `uid` và `cn`.

Lưu ý: trong JNDI, `SearchControls.OBJECT_SCOPE` tương ứng `baseObject`, `ONELEVEL_SCOPE` tương ứng `singleLevel`, và `SUBTREE_SCOPE` tương ứng `wholeSubtree` của LDAPv3.

## 4. Đọc đúng một entry đã biết DN

Nếu ứng dụng đã lưu DN của Alice, không cần tìm cả nhánh bằng UID. API `lookup(...)` của `LdapTemplate` cho phép truy xuất trực tiếp entry và ánh xạ các thuộc tính.

~~~java
import javax.naming.ldap.LdapName;

// Giả sử đoạn mã nằm trong PeopleReader:
public PersonView readByDn() throws Exception {
    return ldapTemplate.lookup(
        new LdapName("uid=alice,ou=people"),
        new String[] {"uid", "cn", "mail"},
        PeopleReader::toPerson
    );
}
~~~

Kết quả ví dụ: `PersonView("alice", "Alice Nguyen", "alice@example.org")`.

Để lấy đối tượng chứa cả thông tin ngữ cảnh entry, dùng:

~~~java
import org.springframework.ldap.core.DirContextOperations;

DirContextOperations alice =
    ldapTemplate.lookupContext("uid=alice,ou=people");

String displayName = alice.getStringAttribute("cn");
String[] classes = alice.getStringAttributes("objectClass");
~~~

Ở ví dụ trên, `objectClass` là thuộc tính **đa trị**, nên sử dụng `getStringAttributes(...)` khi cần đọc toàn bộ giá trị thay vì giả định chỉ có một giá trị.

**Không tìm thấy entry** cần được xử lý riêng. `lookup` theo DN không tồn tại thường dẫn đến exception (được Spring LDAP chuyển đổi từ lỗi LDAP/JNDI, ví dụ `NameNotFoundException`), trong khi `search` với filter không khớp trên nhánh hợp lệ có thể trả một danh sách rỗng. Không nên bắt toàn bộ exception rồi biến thành “entry không tồn tại”: lỗi mạng, TLS, bind và ACL cần được báo khác.

### Đọc một entry theo đúng giao thức LDAP

Ở tầng giao thức, có thể xem thao tác đọc entry cụ thể là Search với:

~~~text
base DN = uid=alice,ou=people,dc=example,dc=org
scope   = baseObject (OBJECT)
filter  = (objectClass=*)
attrs   = uid, cn, mail
~~~

Scope OBJECT **bao gồm chính entry base**, không bao gồm con của nó. Tuy nhiên, filter `(objectClass=*)` vẫn phải khớp entry; quyền truy cập và trạng thái tồn tại của entry cũng ảnh hưởng kết quả.

## 5. Compare: kiểm tra một giá trị mà không lấy thuộc tính

Trong LDAPv3, **CompareRequest** bao gồm:

- `entry`: DN của entry muốn kiểm tra.
- `ava`: cặp *attribute-value assertion*, gồm tên thuộc tính và giá trị cần so khớp.

Ví dụ: DN `cn=reviewers,ou=groups,dc=example,dc=org`, thuộc tính `uniqueMember`, giá trị `uid=alice,ou=people,dc=example,dc=org`.

~~~text
CompareRequest:
  DN:        cn=reviewers,ou=groups,dc=example,dc=org
  Attribute: uniqueMember
  Value:     uid=alice,ou=people,dc=example,dc=org

CompareResponse:
  compareTrue     nếu giá trị assertion khớp theo equality matching rule
  compareFalse    nếu assertion không khớp
  LDAP error      nếu entry không tồn tại, không đủ quyền, lỗi schema...
~~~

`compareFalse` **không có nghĩa tương đương** với “DN không tồn tại”. Với DN sai, server có thể trả `noSuchObject`. Bên cạnh đó, quyền **compare** và quyền **read/search** có thể khác nhau theo ACL; phải thử với chính tài khoản bind của ứng dụng.

### 5.1. Thử Compare trực tiếp bằng `ldapcompare`

Công cụ `ldapcompare` của OpenLDAP cho phép gửi một LDAP Compare request:

~~~bash
ldapcompare -x -H ldaps://ldap.example.org:636 \
  -D "uid=reader,ou=service,dc=example,dc=org" -W \
  "cn=reviewers,ou=groups,dc=example,dc=org" \
  "uniqueMember:uid=alice,ou=people,dc=example,dc=org"
~~~

Trong ví dụ, `-W` yêu cầu nhập mật khẩu qua prompt; URL `ldaps://` giả định máy chủ hỗ trợ TLS và chứng chỉ đã được xác minh. Với dữ liệu ban đầu, kết quả so sánh kỳ vọng là `TRUE`; nếu thay Alice bằng Bob (không thuộc nhóm) thì kỳ vọng là `FALSE` trong điều kiện ACL cho phép.

Giá trị assertion có thể chứa ký tự đặc biệt; ở chương trình Java, hãy để thư viện LDAP tạo request và encode đúng kiểu dữ liệu. Đừng tự ghép các giá trị nhạy cảm vào câu lệnh shell.

### 5.2. Java API: phân biệt Compare native với Search kiểm tra điều kiện

Trong **Spring LDAP `LdapTemplate`**, các API đọc phổ biến là `search(...)`, `lookup(...)` và `lookupContext(...)`; `LdapTemplate` không cung cấp lời gọi `compare(dn, attribute, value)` như một phương thức chuẩn của chính nó.

Nếu ứng dụng có tích hợp **Spring Security LDAP**, lớp `SpringSecurityLdapTemplate` có phương thức `compare(String dn, String attributeName, Object value)` để thực hiện LDAP Compare:

~~~java
import org.springframework.ldap.core.ContextSource;
import org.springframework.security.ldap.SpringSecurityLdapTemplate;

// Yêu cầu dependency spring-security-ldap.
SpringSecurityLdapTemplate securityLdap =
    new SpringSecurityLdapTemplate(contextSource);

boolean matches = securityLdap.compare(
    "cn=reviewers,ou=groups",
    "uniqueMember",
    "uid=alice,ou=people,dc=example,dc=org"
);
~~~

Trong ví dụ, `contextSource` là bean `ContextSource` đã cấu hình cùng base DN `dc=example,dc=org`. Mã minh họa này dùng **API của Spring Security LDAP**, không tự có trong dự án chỉ thêm Spring Data LDAP. Cần chọn phiên bản Spring Security tương thích với Spring LDAP đang sử dụng.

Nếu chỉ có `LdapTemplate`, có thể kiểm tra điều kiện **bằng một Search với scope OBJECT**, nhưng đó vẫn là **SearchRequest**, không phải CompareRequest:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public boolean containsMember(String memberFullDn) {
    LdapQuery q = query()
        .base("cn=reviewers,ou=groups")
        .searchScope(SearchScope.OBJECT)
        .attributes("1.1") // Chỉ kiểm tra khớp, không yêu cầu thuộc tính.
        .where("uniqueMember").is(memberFullDn);

    return !ldapTemplate.search(q, attrs -> Boolean.TRUE).isEmpty();
}
~~~

Selector đặc biệt `"1.1"` theo LDAPv3 nghĩa là không yêu cầu bất kỳ thuộc tính nào. Đoạn mã chỉ dựa trên việc Search trả entry khớp, không sử dụng thuộc tính của nó. Hai cách có thể cùng trả `true` trong ví dụ thuận lợi nhưng **không tương đương về giao thức, lỗi và phân quyền**:

- Compare trả `compareTrue`/`compareFalse` hoặc lỗi; Search trả danh sách entry khớp hoặc lỗi.
- ACL cho Compare và Search có thể khác nhau.
- Search vẫn dùng filter/scope và có các giới hạn tìm kiếm; Compare nhắm đúng DN.
- Nếu `search` bị từ chối do không có quyền tìm kiếm, không được suy diễn người dùng không thuộc nhóm.

**Không dùng Compare để tự kiểm tra mật khẩu người dùng** chỉ vì không phải tải giá trị mật khẩu. Hành vi LDAP Compare với thuộc tính password phụ thuộc directory, cách băm và chính sách server; với ứng dụng đăng nhập, nên dùng cơ chế **bind authentication** hoặc Spring Security LDAP được cấu hình phù hợp.

## 6. Đọc entry và ánh xạ đối tượng trong Spring Data LDAP

`LdapTemplate` thích hợp khi cần kiểm soát chi tiết các thành phần của query hoặc đọc thuộc tính động. Khi đã ánh xạ entry sang POJO, **Spring Data LDAP repository** có thể biểu diễn những trường hợp đọc quen thuộc dưới dạng truy vấn repository.

Ví dụ cấu trúc ánh xạ cơ bản:

~~~java
import javax.naming.Name;
import org.springframework.data.annotation.Id;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;

@Entry(
    base = "ou=people",
    objectClasses = {"inetOrgPerson", "top"}
)
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "mail")
    private String email;

    // Constructor không tham số, getter/setter theo cơ chế mapping đang dùng.
}
~~~

Repository có thể đọc theo DN qua API repository phù hợp và tìm entry theo thuộc tính qua phương thức truy vấn dẫn xuất, ví dụ `findByUid(String uid)`, khi entity và repository được cấu hình đúng. Việc repository thực hiện tìm kiếm vẫn chịu **schema, base DN, scope, filter và ACL** của directory; tên method không chứng minh rằng ứng dụng đã gửi một LDAP CompareRequest.

Lưu ý khi đọc nhiều thuộc tính:

- Một entry có thể có nhiều `objectClass`; objectClass là thông tin kiểu dữ liệu và các quy tắc thuộc tính bắt buộc/tùy chọn.
- Một thuộc tính như `member` hoặc `uniqueMember` có thể chứa **nhiều giá trị**. Dùng tập hợp/array để ánh xạ nếu cần đọc đầy đủ.
- Thuộc tính tùy chọn như `mail` có thể không xuất hiện. Mapper cần kiểm tra `null` và kiểu dữ liệu thay vì luôn gọi `attrs.get("mail").get()`.
- Một số thuộc tính mang dữ liệu nhị phân (`jpegPhoto`, chứng chỉ) cần ánh xạ `byte[]`, không ép sang `String`.
- Thuộc tính vận hành như `modifyTimestamp`, `createTimestamp` có thể không được trả về nếu không yêu cầu rõ ràng, hoặc ACL không cho phép.
- Nếu cần DN của entry khi tìm kiếm, sử dụng mapping có ngữ cảnh (`ContextMapper`, `DirContextOperations`) hoặc ODM phù hợp. `AttributesMapper` chỉ nhận các thuộc tính.

## 7. Thực hành đối chiếu với `ldapsearch`

Công cụ `ldapsearch` giúp đối chiếu hành vi của query Java với server thật.

**Tìm mọi người dưới `ou=people`, kể cả OU con:**

~~~bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(objectClass=inetOrgPerson)" dn uid cn mail
~~~

**Chỉ tìm người ở một cấp ngay dưới `ou=people`:**

~~~bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(objectClass=inetOrgPerson)" dn uid
~~~

**Đọc đúng entry Alice theo DN:**

~~~bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=reader,ou=service,dc=example,dc=org" -W \
  -b "uid=alice,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" dn uid cn mail
~~~

Khi lệnh trả về thiếu thuộc tính, hãy kiểm tra danh sách thuộc tính yêu cầu, quyền truy cập và schema. Nếu lệnh không trả entry, kiểm tra **base DN, scope, filter** và lỗi LDAP được server báo thay vì kết luận dữ liệu không có.

## 8. Lỗi phổ biến, quyền truy cập và hiệu năng

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Search trả danh sách rỗng | Sai filter, sai base DN, scope quá hẹp, ACL | Đối chiếu DN, filter, thử truy vấn tối thiểu với tài khoản thử nghiệm phù hợp |
| Lookup theo DN thất bại | DN không tồn tại, DN truyền sai tương đối/tuyệt đối, ACL hoặc kết nối lỗi | Kiểm tra DN đầy đủ, `ContextSource` base và lỗi cụ thể |
| Compare trả `compareFalse` | Assertion không khớp giá trị theo equality rule | Kiểm tra attribute/value và schema; không suy ra DN không tồn tại |
| Compare lỗi `noSuchObject` | DN đích không tồn tại hoặc không truy cập được | Kiểm tra DN và thông tin lỗi/ACL |
| Có entry nhưng thiếu `mail` | Không yêu cầu thuộc tính, không có giá trị, hoặc ACL hạn chế | Kiểm tra attribute selection và mapper |
| Query tìm rất chậm | SUBTREE rộng, filter không tối ưu, giới hạn server, referral | Thu hẹp base/scope, dùng index thích hợp và phân trang khi được hỗ trợ |
| Một người xuất hiện nhiều lần | Các entry trùng thuộc tính được tìm hoặc dữ liệu thư mục không duy nhất | Xác định DN và quy tắc nghiệp vụ; không mặc định UID duy nhất trên toàn cây |
| Lỗi LDAP filter | Tự nối chuỗi từ input người dùng | Sử dụng `LdapQueryBuilder`, `EqualsFilter` hoặc cơ chế encode tham số |

### Các nguyên tắc an toàn

1. Sử dụng **LDAPS hoặc StartTLS** và xác thực chứng chỉ server khi trao đổi dữ liệu LDAP trên mạng.
2. Chỉ cấp cho tài khoản bind các quyền **search, read, compare** thực sự cần thiết; quyền giữa các thao tác không nhất thiết giống nhau.
3. Giới hạn base DN, scope, các thuộc tính trả về và giới hạn kết quả để giảm tải và hạn chế lộ dữ liệu.
4. Không ghép trực tiếp input vào LDAP filter hoặc DN; filter phải escape đúng cú pháp, còn DN phải được tạo/parse theo quy tắc DN (`LdapName`, `LdapNameBuilder`).
5. Không log mật khẩu bind, dữ liệu nhạy cảm của entry hoặc filter có thông tin cá nhân ở mức không cần thiết.
6. Nếu ứng dụng cần đọc ngay sau thao tác ghi, lưu ý directory có replication có thể khiến kết quả đọc từ replica khác chưa cập nhật tức thì.

## 9. Bài tập tự kiểm tra

1. Cần lấy toàn bộ nhân viên dưới nhiều OU con của `ou=people`. Chọn scope Search nào? Nếu chỉ muốn con trực tiếp thì thay đổi gì?
2. Bạn đã biết `uid=alice,ou=people,dc=example,dc=org` và chỉ cần lấy `cn`, `mail`. Khi nào `lookup(...)` thích hợp hơn `search(...)`?
3. CompareRequest trả `compareFalse`: điều gì có thể kết luận, và điều gì **không** thể kết luận về DN?
4. Vì sao LDAP Compare một thuộc tính không giống Java `String.equals()`?
5. Trong Java chỉ có `LdapTemplate`, tại sao Search `OBJECT` với filter `(uid=alice)` không được gọi là một LDAP CompareRequest?
6. Một mapper gọi `attrs.get("mail").get()` và gây lỗi ở một người dùng. Hãy chỉ ra hai nguyên nhân hợp lý và cách sửa.
7. Tại sao `searchByUid("alice")` có thể trả nhiều entry ở các OU khác nhau, dù phần mềm chỉ mong một tài khoản?
8. Bạn muốn kiểm tra đăng nhập bằng mật khẩu. Vì sao nên xem xét bind authentication thay vì gọi Compare trên `userPassword`?

## 10. Kết luận

Hãy dùng **Search** khi cần tìm một hay nhiều entry theo base DN, scope và filter; dùng **Compare** khi cần server so khớp một assertion trên entry đã biết DN mà không lấy giá trị thuộc tính; dùng **`lookup`** khi cần đọc thuộc tính của một DN cụ thể. Trong Spring Data LDAP, repository giúp ánh xạ và tìm kiếm entity, còn `LdapTemplate` cho phép kiểm soát trực tiếp tìm kiếm và đọc dữ liệu. Việc chọn đúng thao tác, đúng thuộc tính và đúng quyền giúp code rõ ràng, hạn chế truy vấn không cần thiết và tránh xử lý sai các trường hợp không có kết quả.

### Tài liệu tham khảo

- [RFC 4511 — LDAPv3, Search Operation (4.5), Compare Operation (4.10)](https://www.rfc-editor.org/rfc/rfc4511).
- [Spring LDAP — `LdapTemplate` API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html).
- [Spring LDAP — `LdapQueryBuilder` API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html).
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html).
- [Spring Security LDAP — `SpringSecurityLdapTemplate` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/SpringSecurityLdapTemplate.html).
