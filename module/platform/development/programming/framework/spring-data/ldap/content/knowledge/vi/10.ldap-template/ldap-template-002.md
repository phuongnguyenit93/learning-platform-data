# Lookup một entry theo DN

Trong **Spring Data LDAP**, ứng dụng Java làm việc với dữ liệu người dùng, nhóm và cấu hình dưới dạng đối tượng, nhưng dữ liệu thật nằm trong **directory** gồm các LDAP entry tổ chức theo cây. Khi đã biết chính xác **Distinguished Name (DN)** của một entry, cách truy cập trực tiếp qua **`LdapTemplate.lookup(...)`** thường phù hợp hơn một truy vấn tìm kiếm theo thuộc tính: ta chỉ định đúng entry cần đọc và ánh xạ kết quả về kiểu Java mong muốn.

Bài thuộc chương **LdapTemplate** này hướng dẫn cách đọc một LDAP entry theo DN: hiểu DN tương đối với base, xây DN an toàn, dùng `AttributesMapper` hoặc `ContextMapper`, đối chiếu với ánh xạ ODM và repository của Spring Data LDAP, xử lý trường hợp không tìm thấy, kiểm tra schema/`objectClass`, bảo vệ kết nối và viết kiểm thử với directory.

## 1. Lookup theo DN là gì?

LDAP lưu dữ liệu theo **Directory Information Tree (DIT)**. Mỗi entry có một DN xác định tên và vị trí của nó trong cây ở thời điểm truy cập. Ví dụ:

```text
dc=example,dc=org
└── ou=people
    └── uid=u1001
        ├── objectClass: inetOrgPerson
        ├── cn: An Nguyen
        ├── sn: Nguyen
        ├── uid: u1001
        └── mail: an.nguyen@example.org
```

DN đầy đủ của entry người dùng là:

```text
uid=u1001,ou=people,dc=example,dc=org
```

Trong chuỗi đó:

- **`uid=u1001`** là **Relative Distinguished Name (RDN)** của entry người dùng trong nhánh cha.
- **`ou=people`** là RDN của entry tổ chức người dùng; **`dc=example,dc=org`** là các thành phần phía trên.
- **DN** định danh entry thông qua đường dẫn phân cấp, không giống khóa chính độc lập với vị trí trong cơ sở dữ liệu quan hệ.
- **`objectClass`** quyết định thuộc tính bắt buộc và được phép theo schema; `inetOrgPerson` kế thừa các lớp khác trong hệ phân cấp object class.

Một entry tương ứng có thể được chuẩn bị trong directory thử nghiệm bằng LDIF:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
mail: an.nguyen@example.org
```

Lời gọi **lookup theo DN** mang ý nghĩa: “Đọc entry đang có DN này và trả các thuộc tính của nó”. Nó **khác với tìm kiếm** “Tìm mọi entry có `uid=u1001`”, vì một thuộc tính không nhất thiết là duy nhất trên tất cả các nhánh LDAP. Nếu có hai entry ở hai OU khác nhau cùng `uid`, hai DN vẫn khác nhau và có thể được lookup riêng.

> LDAP protocol không có thao tác mang tên `LOOKUP` riêng như một loại request chuẩn. `lookup` là API của JNDI/Spring LDAP; LDAP provider có thể thực hiện nó bằng thao tác đọc/tìm kiếm entry tại base DN. Không suy luận “một lời gọi lookup Java chắc chắn là đúng một gói tin LDAP” khi đo hiệu năng.

## 2. Phân biệt DN đầy đủ và DN tương đối với LDAP base

Trong Spring Boot, cấu hình kết nối Spring LDAP thường có dạng sau (giá trị chỉ để minh họa, không dùng trực tiếp cho môi trường thật):

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=readonly,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

`spring.ldap.base` xác định **base DN** của `LdapContextSource`. Các thao tác qua `LdapTemplate` thường nhận **DN tương đối với base này**. Với ví dụ trên:

| Khái niệm | Giá trị |
|---|---|
| Base DN của context | `dc=example,dc=org` |
| DN đầy đủ trên directory | `uid=u1001,ou=people,dc=example,dc=org` |
| DN truyền vào `LdapTemplate.lookup` | `uid=u1001,ou=people` |
| Nếu base DN đã là `ou=people,dc=example,dc=org` | DN tương đối chỉ còn `uid=u1001` |

**Lỗi thường gặp:** gọi `lookup` bằng DN đã chứa `dc=example,dc=org` trong khi context cũng có base này. Tùy cách xây context, đường dẫn có thể bị ghép hậu tố hai lần và trả lỗi không tìm thấy. Trước khi sửa filter hoặc điều chỉnh repository, hãy kiểm tra rõ DN thực sự truyền tới `LdapTemplate` và base đang cấu hình.

Đối với entry **`ou=people`** nằm ngay dưới base, DN tương đối của nó chỉ là `ou=people`. Một entry là con của nhánh đó có thêm thành phần `uid=u1001` phía trước. Nếu đổi OU hoặc đổi RDN, DN mới cũng đổi; DN không nên bị xem là định danh nghiệp vụ bất biến của một người.

## 3. Xây dựng DN với `LdapNameBuilder`

DN có cú pháp và quy tắc escape riêng (ví dụ dấu phẩy, dấu cộng, dấu bằng hoặc khoảng trắng ở vị trí đặc biệt). **Không ghép chuỗi DN từ đầu vào** như:

```java
// Không dùng khi uid đến từ dữ liệu bên ngoài.
String dn = "uid=" + uid + ",ou=people";
```

Thay vào đó, tạo DN bằng công cụ của Spring LDAP:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String uid = "u1001";

Name relativeDn = LdapNameBuilder
    .newInstance("ou=people")
    .add("uid", uid)
    .build();

// relativeDn biểu diễn uid=u1001,ou=people
```

`LdapNameBuilder` nhận thành phần RDN và tạo đối tượng `javax.naming.Name`, tránh diễn giải ký tự đặc biệt trong giá trị thành cấu trúc DN. **Escape đúng cú pháp không thay thế kiểm tra dữ liệu nghiệp vụ:** nếu chính sách ứng dụng chỉ cho phép UID theo mẫu nhất định, hãy kiểm tra UID trước khi tạo DN. Việc xây DN cũng khác với cách escape chuỗi dùng trong **LDAP search filter**.

Nếu hệ thống nhận **DN đầy đủ** từ nơi khác, phải thống nhất liệu nó đã bao gồm base của context hay chưa; chỉ tách base sau khi xác minh DN thuộc cây được phép truy cập. Không tùy tiện dùng một DN do người dùng gửi lên để đọc mọi entry khác bên ngoài phạm vi được ủy quyền.

## 4. Lookup bằng `LdapTemplate` và `AttributesMapper`

`LdapTemplate` là abstraction của **Spring LDAP** giúp ứng dụng dùng JNDI mà không phải tự quản lý từng `DirContext`. Với một DN đã biết, ta có thể gọi `lookup(Name, AttributesMapper<T>)`: hàm mapper nhận các thuộc tính LDAP (`javax.naming.directory.Attributes`) và tạo đối tượng Java.

Ví dụ sau minh họa một service tra cứu theo `uid` đã biết là RDN của người dùng dưới `ou=people`. Để dễ theo dõi dữ liệu, phần kết quả dùng một Java record (yêu cầu Java 16+).

```java
import java.util.Optional;
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

record PersonView(String uid, String commonName, String surname, String email) {}

@Service
public class PersonLookupService {
    private final LdapTemplate ldapTemplate;

    public PersonLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Optional<PersonView> findByUidAtKnownOu(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid must not be blank");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        AttributesMapper<PersonView> mapper = attrs -> new PersonView(
                readText(attrs, "uid"),
                readText(attrs, "cn"),
                readText(attrs, "sn"),
                readText(attrs, "mail"));

        try {
            return Optional.ofNullable(ldapTemplate.lookup(dn, mapper));
        } catch (NameNotFoundException ex) {
            return Optional.empty();
        }
    }

    private static String readText(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null ? null : (String) attribute.get();
    }
}
```

Điểm cần hiểu từ ví dụ:

1. **`Name dn`** là DN tương đối với LDAP base đã cấu hình, không phải chỉ giá trị `uid`.
2. **`lookup(dn, mapper)`** truy cập entry cụ thể và sử dụng mapper để tạo `PersonView`.
3. **`AttributesMapper<T>`** chỉ nhận tập thuộc tính, thuận tiện cho dữ liệu đơn giản. Nếu cần biết DN thực của entry hoặc đọc các giá trị theo đặc tính của `DirContext`, cân nhắc `ContextMapper`.
4. Hàm `readText` chỉ thích hợp với **thuộc tính text đơn trị** trong ví dụ. Một thuộc tính vắng mặt trả `null`; việc thiếu `cn`/`sn` ở entry `person` đúng schema là bất thường, nhưng `mail` có thể không tồn tại. Với dữ liệu binary hoặc đa trị, phải đọc và chuyển đổi kiểu theo schema.
5. **`NameNotFoundException`** là tình huống không tìm thấy tên/entry trong context của thao tác. `Optional.empty()` là chính sách của service này; lỗi xác thực, thiếu quyền, kết nối hoặc schema không được biến thành “không có người dùng”.

Để chạy thật, ứng dụng cần dependency Spring LDAP/Spring Data LDAP thích hợp, cấu hình `LdapContextSource` và `LdapTemplate` (có thể được Spring Boot cấu hình tự động khi điều kiện phù hợp), directory có dữ liệu, tài khoản bind hợp lệ và kết nối được bảo vệ.

## 5. Lookup với `ContextMapper`: khi cần nhiều ngữ cảnh hơn

`ContextMapper<T>` nhận đối tượng context đại diện entry. Trong Spring LDAP, cách phổ biến là dùng `DirContextOperations` hoặc `DirContextAdapter` để lấy thuộc tính và DN.

```java
import javax.naming.Name;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

ContextMapper<PersonView> mapper = context -> {
    DirContextOperations entry = (DirContextOperations) context;
    String uid = entry.getStringAttribute("uid");
    String cn = entry.getStringAttribute("cn");
    String sn = entry.getStringAttribute("sn");
    String mail = entry.getStringAttribute("mail");
    return new PersonView(uid, cn, sn, mail);
};

PersonView person = ldapTemplate.lookup(relativeDn, mapper);
```

Ở đây, `relativeDn` là `Name` đã tạo ở phần trước. `DirContextOperations` còn có phương thức như `getDn()` để truy cập tên entry mà adapter quản lý. Context mapper hữu ích khi cần thao tác thuận tiện với thuộc tính đa trị, DN, hoặc dữ liệu LDAP phức tạp; `AttributesMapper` thường đủ nếu chỉ cần một vài giá trị đơn.

| Cách đọc | Đầu vào ánh xạ | Thích hợp khi | Lưu ý |
|---|---|---|---|
| `lookup(dn, AttributesMapper<T>)` | `Attributes` | Chuyển một số thuộc tính thành DTO đơn giản | Mapper không được truyền DN trực tiếp |
| `lookup(dn, ContextMapper<T>)` | Context/adapter của entry | Cần DN và các tiện ích `DirContextOperations` | Cần hiểu kiểu context do Spring LDAP đưa vào |
| ODM `findByDn(dn, Entity.class)` | Metadata annotation của entity | Muốn tái sử dụng `@Entry`, `@Attribute`, `@Id` | Entity, DN và schema phải khớp |
| Spring Data LDAP repository `findById(dn)` | Repository và ODM | Muốn thao tác theo mô hình repository | `Id` vẫn là DN, không phải khóa chính SQL |

**Lưu ý về overload:** Java có thể không phân giải được một lambda trần khi nhiều overload đều nhận interface hàm. Hãy gán lambda vào biến có kiểu cụ thể `AttributesMapper<PersonView>` hoặc `ContextMapper<PersonView>` như hai ví dụ trên, để compiler chọn đúng phương thức.

## 6. Lookup theo DN so với truy vấn LDAP filter

Một cách hiểu sai thường gặp là dùng `lookup("u1001", ...)` để “tìm theo UID”. Nhưng **lookup nhận DN**, không phải giá trị thuộc tính. Chỉ khi DN có RDN là `uid=u1001` và bạn biết chính xác nhánh `ou=people`, mới có thể xây ra DN để lookup.

Nếu chỉ biết email, mã nhân viên hoặc UID nhưng **không biết OU/RDN chính xác**, cần tìm kiếm qua LDAP filter và một search base phù hợp:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery ldapQuery = query()
        .base("ou=people")
        .where("uid").is(userInput);

AttributesMapper<String> uidMapper =
        attrs -> (String) attrs.get("uid").get();

List<String> ids = ldapTemplate.search(ldapQuery, uidMapper);
```

`LdapQueryBuilder` tạo và escape giá trị LDAP filter an toàn hơn việc nối chuỗi như `"(uid=" + userInput + ")"`. **Escape filter** dùng quy tắc khác với **escape RDN**; chọn đúng API cho đúng mục đích. Ngoài ra, search có thể trả **0, 1 hoặc nhiều entry**; nếu nghiệp vụ đòi duy nhất, phải kiểm tra số kết quả và xử lý trường hợp trùng, thay vì tự lấy phần tử đầu tiên.

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Biết đầy đủ DN của một entry | `lookup(dn, mapper)` | Truy cập đúng entry theo địa chỉ |
| Biết UID và OU/RDN đã được quy ước cố định | Tạo DN bằng `LdapNameBuilder` rồi lookup | Không cần tìm trên nhiều nhánh |
| Chỉ biết email hoặc UID, OU chưa rõ | `search(query, mapper)` | Cần tìm entry theo thuộc tính |
| Muốn tìm nhiều người cùng phòng ban | `search` với base/scope và filter | Trả danh sách entry |
| Muốn đọc entity ODM theo DN | `findByDn` hoặc repository `findById` | Tái sử dụng metadata ánh xạ Java |

Không nên thực hiện chuỗi **search để lấy DN rồi lookup lại** nếu search đã trả đầy đủ các thuộc tính ứng dụng cần; lần lookup thứ hai có thể tăng độ trễ mà không thêm thông tin. Chỉ làm vậy khi có lý do rõ như cần thuộc tính khác hoặc cần xác minh entry tại một thời điểm sau đó.

## 7. Kết hợp với Spring Data LDAP ODM và repository

`LdapTemplate.lookup` cho phép tự định nghĩa mapper tại chỗ. Nếu ứng dụng có nhiều thao tác CRUD trên cùng loại entry, có thể mô hình hóa entry bằng **Object–Directory Mapping (ODM)**:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String mail;

    public DirectoryPerson() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) { this.commonName = commonName; }
    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }
    public String getMail() { return mail; }
    public void setMail(String mail) { this.mail = mail; }
}
```

Khi có mapper ODM, API của `LdapTemplate` có thể ánh xạ trực tiếp entity theo DN:

```java
// dn là javax.naming.Name, tương đối với context base.
DirectoryPerson person = ldapTemplate.findByDn(dn, DirectoryPerson.class);
```

Với **Spring Data LDAP repository**, có thể khai báo:

```java
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
```

Rồi truy cập bằng `repository.findById(dn)` theo API repository (thường trả `Optional<DirectoryPerson>`), với điều kiện repository đã được cấu hình, DN đúng và entry phù hợp với mapping.

Quan trọng là:

- `@Id` của ODM dùng **DN kiểu `javax.naming.Name`**, không phải ID số của JPA.
- `@Entry` cùng các `objectClasses` và `@Attribute` cung cấp thông tin ánh xạ, nhưng **schema và ACL của LDAP server** vẫn quyết định dữ liệu nào có thể đọc/ghi.
- Lời gọi đọc entity qua ODM/repository thuận tiện cho mô hình đối tượng; `lookup` với mapper thủ công phù hợp khi chỉ cần một DTO nhỏ hoặc xử lý thuộc tính đặc biệt.
- Đổi RDN/OU làm DN thay đổi; không mặc định rằng một lần `save` sẽ tự rename/move entry giống `UPDATE` trên bảng quan hệ.

## 8. Xử lý lỗi và dữ liệu không đầy đủ

Một lần lookup có thể thất bại vì nhiều lý do; **đừng gộp tất cả thành “không tìm thấy”**:

| Tình huống | Dấu hiệu/cơ chế | Hướng xử lý ở tầng ứng dụng |
|---|---|---|
| Entry không tồn tại ở DN được chỉ định | `NameNotFoundException` sau khi Spring LDAP dịch ngoại lệ JNDI | Trả `Optional.empty()`/404 nếu đúng chính sách nghiệp vụ |
| Base DN sai hoặc DN không khớp OU hiện tại | Thường biểu hiện không tìm thấy | Kiểm tra base và cách ghép DN, không tự mở rộng quyền search |
| DN sai cú pháp | Lỗi tên/DN không hợp lệ | Validate đầu vào; tạo bằng `LdapNameBuilder` |
| Tài khoản bind không được phép đọc | Lỗi quyền hoặc đôi khi thông tin bị che bởi chính sách server | Kiểm tra ACL/bind account; không xem lỗi quyền là entry chắc chắn không tồn tại |
| Sai mật khẩu hoặc hết quyền xác thực | Lỗi authentication/bind | Xử lý lỗi hệ thống; bảo vệ credential, không retry vô hạn |
| Máy chủ không kết nối được, timeout, lỗi TLS | Communication/timeout/SSL exception phù hợp | Báo lỗi phụ thuộc hệ thống, timeout và retry có giới hạn |
| Thiếu thuộc tính bắt buộc trong DTO | Giá trị `null`, hoặc lỗi mapper nếu tự gọi `get()` trên thuộc tính vắng | Phân biệt dữ liệu tùy chọn với vi phạm giả định mapping |
| Thuộc tính có nhiều giá trị | Một `Attribute` có thể chứa nhiều giá trị | Xử lý kiểu collection hoặc đọc toàn bộ giá trị; không mặc định chỉ một |

Ví dụ, `mail` có thể là thuộc tính tùy chọn. Thay vì yêu cầu luôn có mail, bạn có thể biểu diễn nó dưới dạng nullable/`Optional` trong model dịch vụ tùy cách thiết kế. Với các thuộc tính đa trị như `member` của entry nhóm, một lần `attrs.get("member").get()` chỉ lấy **một** giá trị; cần đọc danh sách qua `Attribute.getAll()` hoặc các tiện ích tương ứng, kiểm tra kiểu dữ liệu và đóng enumeration theo quy định JNDI.

Ngoài ra, **DN trỏ tới entry nhưng objectClass không đúng kỳ vọng** không đồng nghĩa với việc không có entry. Với mapper thủ công, bạn có thể cần đọc `objectClass` và kiểm tra loại entry trước khi xử lý. Với ODM, hãy kiểm tra metadata `@Entry` và schema của directory. Trường hợp một nhánh vừa chứa `person` vừa chứa `device`, lookup trực tiếp bằng DN chưa tự bảo đảm rằng entry là “người dùng hợp lệ”.

## 9. Bảo mật và hiệu năng khi lookup

**Lookup theo DN cũng cần kiểm soát bảo mật** dù không dùng LDAP filter:

1. **Kết nối:** ưu tiên LDAPS hoặc StartTLS theo cấu hình hạ tầng, xác thực chứng chỉ máy chủ và đặt timeout phù hợp. Không tắt kiểm tra TLS để “cho lookup chạy được”.
2. **Quyền bind:** tài khoản chỉ tra cứu nên có ACL chỉ đọc đối với nhánh và thuộc tính được phép. Không dùng tài khoản quản trị directory cho mọi request.
3. **Đầu vào:** chuẩn hóa và kiểm tra UID/RDN theo quy tắc nghiệp vụ; dùng `LdapNameBuilder` để escape DN. Không để client quyết định DN bất kỳ nhằm đọc những OU không được phép.
4. **Thông tin nhạy cảm:** không trả các thuộc tính nhạy cảm, secret hoặc hash mật khẩu từ API; tránh log nguyên DN/email nếu không cần. Không ghi password bind vào log hoặc source code.
5. **Bảo vệ API:** phân quyền ở tầng ứng dụng trước khi đọc và trước khi trả thông tin. Quyền có thể đọc ở LDAP không đồng nghĩa mọi người dùng cuối đều được xem các thuộc tính đó.

**Về hiệu năng:** lookup theo DN tiết kiệm việc tìm một entry trong tập rộng khi đã biết đúng vị trí. Tuy nhiên thời gian vẫn chịu ảnh hưởng của RTT, số kết nối, bind/TLS, ACL, size của entry và số thuộc tính trả về. Với overload API hỗ trợ lựa chọn tên thuộc tính cần đọc, có thể giảm payload nếu chỉ cần `cn`/`mail`. Đo thời gian thực tế trước khi tối ưu; tránh suy ra mỗi lookup tương đương đúng một network round-trip trong mọi provider.

Nếu ứng dụng xử lý một danh sách rất lớn các DN và lookup tuần tự từng entry, tổng số thao tác có thể tăng theo số entry. Cần đánh giá lại cách lấy dữ liệu, kích thước batch và đặc tính directory; không mặc định LDAP có khả năng `JOIN` hoặc lazy loading của JPA. Đừng cache thông tin danh tính/phân quyền vô hạn: phải xác định thời gian hết hạn và cách làm mới theo yêu cầu bảo mật.

## 10. Kiểm thử với directory thật hoặc directory dùng cho test

Mock mapper có thể kiểm tra chuyển đổi `Attributes` → Java, nhưng **không kiểm tra được base DN, kết nối, ACL hoặc schema thực tế**. Vì vậy nên có kiểm thử tích hợp với LDAP directory test (ví dụ container/embedded directory có schema phù hợp), sử dụng dữ liệu LDIF cô lập.

| Ca kiểm thử | Dữ liệu chuẩn bị | Kết quả kỳ vọng |
|---|---|---|
| Lookup đúng DN | Entry `uid=u1001,ou=people,...` có `cn`, `sn`, `mail` | Trả đúng `PersonView` |
| DN không có | `uid=missing,ou=people` | Service trả `Optional.empty()` cho lỗi không tìm thấy |
| Sai base DN | Context base và DN cố tình bị ghép sai | Lỗi không tìm thấy/định vị sai được phát hiện |
| Có ký tự đặc biệt ở RDN | Một entry thử nghiệm với giá trị UID phù hợp schema nhưng chứa ký tự cần escape | `LdapNameBuilder` tạo DN đọc đúng entry |
| Entry thiếu `mail` | `inetOrgPerson` hợp lệ không có mail | Mapper xử lý `null` hoặc chính sách mặc định |
| Entry có objectClass khác | DN trỏ tới nhóm hoặc thiết bị | Ứng dụng không gán nhầm thành người dùng |
| Tài khoản thiếu quyền đọc | Bind với ACL giới hạn | Không lộ dữ liệu, lỗi được phân loại đúng |
| LDAP timeout/mất kết nối | Server tạm không sẵn sàng trong môi trường test | Báo lỗi hệ thống, không trả nhầm 404 |
| Entry đổi RDN/OU | Rename/move entry giữa hai lần đọc | DN cũ không còn trỏ entry mới; cơ chế định danh được kiểm chứng |

Khi đo hiệu năng, đặt timer ở tầng service để thấy thời gian `lookup` từ ứng dụng, đồng thời đối chiếu log/counter LDAP server nếu cần biết số thao tác giao thức thực. Số lần gọi `LdapTemplate.lookup` **không phải** số lượng search/bind/LDAP operation chính xác trong mọi tình huống.

### Một bài tập thực hành

Directory thử nghiệm có base `dc=example,dc=org`, hai entry:

```text
uid=u1001,ou=people,dc=example,dc=org
uid=u1001,ou=contractors,dc=example,dc=org
```

Hãy xác định:

1. DN tương đối cần truyền vào `lookup` cho từng entry.
2. Vì sao chỉ truyền chuỗi `"u1001"` không đủ để lookup chính xác?
3. Cần dùng lookup hay search nếu ứng dụng chỉ biết `uid=u1001` nhưng chưa biết người dùng ở OU nào?
4. Khi `mail` không tồn tại, `AttributesMapper` có nên ném lỗi không? Tùy thuộc điều kiện nghiệp vụ nào?
5. Nếu DN cũ ngừng truy cập được sau khi nhân viên chuyển OU, cần làm gì để tránh kết luận nhầm rằng tài khoản đã bị xóa?

**Gợi ý:** DN tương đối lần lượt là `uid=u1001,ou=people` và `uid=u1001,ou=contractors`. Chỉ biết UID thì chưa biết đường dẫn; cần search với base/scope/filter an toàn và xử lý khả năng có nhiều kết quả. Thuộc tính tùy chọn có thể vắng mặt. Khi entry chuyển OU, DN sẽ đổi; hãy tra cứu bằng khóa nghiệp vụ ổn định hoặc cập nhật liên kết DN thay vì dựa vào vị trí cũ.

## 11. Tổng kết

- **`LdapTemplate.lookup(dn, mapper)`** đọc một entry đã biết DN, khác với `search` dùng LDAP filter để tìm theo thuộc tính.
- DN truyền vào thường **tương đối với base của `LdapContextSource`**. Dùng `LdapNameBuilder` để xây RDN an toàn và không ghép DN từ chuỗi đầu vào.
- `AttributesMapper` phù hợp ánh xạ thuộc tính thành DTO; `ContextMapper` hữu ích khi cần DN hoặc tiện ích của `DirContextOperations`. ODM/`LdapRepository` giúp quản lý entity trên mô hình repository.
- Không nhầm **không tìm thấy entry** với lỗi quyền truy cập, mạng hoặc TLS. Luôn kiểm tra schema, `objectClass`, thuộc tính đa trị và quyền bind.
- Một lần lookup đúng phải được xác minh với directory test, cả trường hợp thành công, thiếu thuộc tính, sai DN, đổi OU và lỗi kết nối.

Nắm vững lookup theo DN giúp bạn chọn đúng điểm sử dụng `LdapTemplate` trong **Spring Data LDAP**: đọc chính xác một entry khi biết địa chỉ, ánh xạ nó sang Java object và giữ quyền truy cập an toàn, dự đoán được và có thể kiểm thử.
