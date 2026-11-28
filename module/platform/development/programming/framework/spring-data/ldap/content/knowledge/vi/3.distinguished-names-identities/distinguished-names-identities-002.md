# DN tuyệt đối và DN tương đối với base được cấu hình

Trong **SPRING_DATA_LDAP**, ứng dụng truy cập directory LDAP bằng Spring Data LDAP repository hoặc `LdapTemplate`. Mỗi entry nằm trong cây phân cấp, có **Distinguished Name (DN)** xác định vị trí; việc ánh xạ sang đối tượng Java, tìm kiếm, đọc và cập nhật đều cần dùng DN nhất quán. Một lỗi rất thường gặp là truyền **DN đầy đủ** vào API đang chờ **DN tương đối với base đã cấu hình**: đường dẫn bị ghép lặp, truy vấn không tìm thấy entry, hoặc thao tác nhầm nhánh.

Bài học giải thích cách đọc DN, phân biệt Relative Distinguished Name (RDN) với DN tương đối, hiểu base DN của `LdapContextSource`, viết code dựng DN và truy vấn an toàn, cũng như kiểm thử để phát hiện lỗi ghép DN trước khi ứng dụng kết nối tới directory thực tế.

## 1. DN biểu diễn vị trí của entry trong cây LDAP

Giả sử directory có các entry:

```text
dc=org
└── dc=example
    ├── ou=people
    │   ├── uid=lan
    │   └── uid=binh
    └── ou=groups
        └── cn=developers
```

Đường dẫn DN đầy đủ của Lan là:

```text
uid=lan,ou=people,dc=example,dc=org
```

Đọc DN từ **trái sang phải**: RDN cụ thể nhất đứng trước, theo sau là các RDN của entry cha và các cấp cao hơn. Trong ví dụ:

- `uid=lan` là **RDN** (*Relative Distinguished Name*) của entry so với entry cha `ou=people,...`.
- `ou=people` là RDN của container chứa người dùng.
- `dc=example,dc=org` là hậu tố tên của directory, thường được ứng dụng dùng làm **base DN**.
- Chuỗi `uid=lan,ou=people,dc=example,dc=org` là **DN đầy đủ** để xác định entry trong cây tên ví dụ.

Một RDN có thể chứa nhiều cặp thuộc tính/giá trị (multi-valued RDN), chẳng hạn `cn=Lan+uid=lan`; vì vậy không nên nghĩ mọi RDN luôn chỉ chứa một dấu `=`. Một DN là **chuỗi các RDN**, không phải đường dẫn file với dấu `/` ở đầu.

Ví dụ LDAP entry ở dạng LDIF:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
```

Các lớp `objectClass`/schema quy định thuộc tính hợp lệ của entry; **DN xác định vị trí và tên của entry**, còn những thuộc tính như `cn`, `mail` là dữ liệu. Trường `uid` xuất hiện cả ở RDN và trong thuộc tính entry vì được dùng để đặt tên; không phải mọi thuộc tính của entry đều nằm trong DN.

## 2. “Tuyệt đối” và “tương đối” luôn cần một mốc so sánh

Trong ứng dụng, cách nói **DN tuyệt đối** thường có nghĩa là **DN đầy đủ trong cây namespace đang xét**, ví dụ `uid=lan,ou=people,dc=example,dc=org`. **DN tương đối** là phần DN còn lại sau khi bỏ base của context mà ứng dụng đã chọn.

Ví dụ với cùng một entry:

| Base DN mà kết nối chọn | DN cần truyền tương đối với base | DN đầy đủ của entry |
|---|---|---|
| `dc=example,dc=org` | `uid=lan,ou=people` | `uid=lan,ou=people,dc=example,dc=org` |
| `ou=people,dc=example,dc=org` | `uid=lan` | `uid=lan,ou=people,dc=example,dc=org` |
| `uid=lan,ou=people,dc=example,dc=org` | DN rỗng `""` | `uid=lan,ou=people,dc=example,dc=org` |

Có thể hình dung công thức:

```text
DN đầy đủ = DN tương đối + base DN

Ví dụ:
uid=lan,ou=people + dc=example,dc=org
  = uid=lan,ou=people,dc=example,dc=org
```

Đây là phép **ghép các thành phần RDN** theo thứ tự, không nên thực hiện bằng nối chuỗi tùy ý trong chương trình.

Điểm cần phân biệt:

1. **RDN** là một thành phần tên tương đối với entry cha, như `uid=lan`.
2. **DN tương đối với base** có thể chứa **nhiều RDN**, như `uid=lan,ou=people`.
3. **DN đầy đủ** không tự gắn nhãn “absolute” trong cú pháp. Cùng một chuỗi DN có thể là tên đầy đủ để kết nối tới một naming context, nhưng là tên tương đối khi xét từ một context cao hơn. Khi làm việc với Spring LDAP, phải nêu rõ **base được cấu hình**.

LDAP root DSE có DN rỗng `""` ở cấp giao thức. Tuy nhiên, nếu `LdapContextSource` đã cấu hình base `dc=example,dc=org`, thì nhiều lời gọi `LdapTemplate` với DN tương đối rỗng lại chỉ tới **entry tại base đã cấu hình**, chứ không tự nhiên là root DSE của server. Đừng đánh đồng hai ngữ cảnh này.

## 3. Base DN của Spring LDAP được áp dụng ở đâu?

`LdapContextSource` là thành phần tạo JNDI context cho `LdapTemplate` và các thành phần Spring Data LDAP sử dụng cùng context. Khi ứng dụng cấu hình:

```java
LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://ldap.example.org:636");
source.setBase("dc=example,dc=org");
// userDn và password được cung cấp từ hệ thống cấu hình/bí mật;
// Spring quản lý khởi tạo bean ContextSource trong ứng dụng thực tế.
```

thì `dc=example,dc=org` trở thành **mốc DN** cho các thao tác LDAP sử dụng context này.

Ví dụ cấu hình quen thuộc trong Spring Boot:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=reader,ou=service,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

Ở đây:

- `spring.ldap.base` là base để Spring LDAP giải quyết **DN tương đối trong các thao tác**.
- `spring.ldap.username` là định danh bind dùng cho xác thực. Nếu directory chấp nhận DN dạng này, giá trị là **DN đầy đủ của tài khoản bind**; không được tự bỏ hậu tố base chỉ vì application base đã cấu hình.
- `ldap.example.org` là host giả định; ứng dụng thực tế dùng endpoint, TLS và account do hệ thống directory cung cấp.

Giả sử base là `dc=example,dc=org`, mối quan hệ giữa tham số API và entry thực tế:

| Thao tác với `LdapTemplate` | DN/base truyền vào | Đích thực tế |
|---|---|---|
| `lookup(...)` | `uid=lan,ou=people` | `uid=lan,ou=people,dc=example,dc=org` |
| `lookup(...)` | `ou=people` | `ou=people,dc=example,dc=org` |
| `lookup(...)` | `""` | `dc=example,dc=org` |
| `search(...)` với `base("ou=people")` | `ou=people` làm gốc tìm kiếm | Tìm trong nhánh `ou=people,dc=example,dc=org` |

**Cạm bẫy:** nếu truyền `uid=lan,ou=people,dc=example,dc=org` như một **DN tương đối** trong context đã có base `dc=example,dc=org`, tên có thể bị giải quyết thành đường dẫn với hậu tố base lặp:

```text
uid=lan,ou=people,dc=example,dc=org,dc=example,dc=org
```

Khi đó directory có thể báo không tìm thấy đối tượng hoặc lỗi tên, dù entry thực sự tồn tại. Phải thống nhất trước tại **ranh giới API**: hàm nhận DN đầy đủ hay DN tương đối với base của context? Không tự ý trộn hai loại.

## 4. Dựng DN bằng LdapNameBuilder thay vì nối chuỗi

Khi xây dựng DN trong Java, nên sử dụng các kiểu và tiện ích hiểu cấu trúc tên LDAP:

- `javax.naming.Name` là giao diện JNDI biểu diễn tên.
- `javax.naming.ldap.LdapName` là cách biểu diễn DN theo cú pháp LDAP.
- `org.springframework.ldap.support.LdapNameBuilder` giúp tạo `Name` từ RDN, tự escape giá trị đặc biệt theo quy tắc DN.

Giả sử base của context là `dc=example,dc=org`; ta chỉ dựng **phần tương đối** cho người dùng:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String uid = "lan";

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", uid)
        .build();

System.out.println(relativeDn);
// uid=lan,ou=people
```

Nếu cần biểu diễn **DN đầy đủ** cho log đã làm sạch, tài liệu hoặc thao tác bên ngoài context:

```java
Name fullDn = LdapNameBuilder.newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("uid", uid)
        .build();

System.out.println(fullDn);
// uid=lan,ou=people,dc=example,dc=org
```

Với giá trị nhận từ người dùng, **không** tạo DN bằng:

```java
// Không an toàn: đầu vào có thể thêm các thành phần RDN ngoài ý muốn.
String unsafeDn = "uid=" + userInput + ",ou=people";
```

Ví dụ, một `uid` có dấu phẩy như `"lan,team"` phải được escape như **giá trị của cùng một RDN**, không được khiến dấu phẩy bị hiểu thành ranh giới RDN mới. `LdapNameBuilder.add("uid", userInput)` mã hóa giá trị cho mục đích này.

**DN escaping khác LDAP filter escaping**. Dùng `LdapNameBuilder` khi tạo tên entry; dùng `LdapQueryBuilder` hoặc `LdapEncoder` phù hợp khi tạo giá trị trong LDAP filter. Không lấy chuỗi DN đã escape để nhét tùy tiện vào filter, và không nối filter từ dữ liệu người dùng.

## 5. Đọc một entry theo DN tương đối

Tại tầng ứng dụng, ví dụ service sau nhận `uid` từ logic nghiệp vụ, dựng DN tương đối rồi dùng `LdapTemplate.lookup(...)`. Với base `dc=example,dc=org`, phương thức đọc `uid=lan,ou=people,dc=example,dc=org`:

**`PersonDirectory.java`**

```java
package com.example.ldap;

import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.InvalidAttributeValueException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Repository;

@Repository
public class PersonDirectory {
    private final LdapTemplate ldapTemplate;

    public PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String findFullName(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        return ldapTemplate.lookup(relativeDn, attrs -> {
            Attribute cn = attrs.get("cn");
            if (cn == null || cn.size() == 0) {
                throw new InvalidAttributeValueException("Thiếu thuộc tính cn");
            }
            return (String) cn.get();
        });
    }
}
```

`lookup` truy cập **một DN cụ thể**, khác với `search` là tìm nhiều entry theo base/scope/filter. Nếu entry không tồn tại, ứng dụng phải xử lý ngoại lệ phù hợp (thường thuộc nhóm `NameNotFoundException` đã được Spring LDAP chuyển đổi), không mặc định nhận `null`.

Trong ví dụ này, DN đưa vào `lookup` **không chứa** `dc=example,dc=org` vì `LdapContextSource` đã cung cấp phần đó. Khi đổi base kết nối thành `ou=people,dc=example,dc=org`, chỉ nên truyền `uid=lan` ở lời gọi tương đương, thay vì giữ nguyên `uid=lan,ou=people`.

## 6. Search base tương đối và phạm vi tìm kiếm

Một truy vấn không nhất thiết biết DN của entry; khi đó ứng dụng chọn **search base** nằm bên dưới base kết nối, rồi đặt `scope` và `filter`:

```java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

// ldapTemplate đã được Spring cấu hình với base dc=example,dc=org.
LdapQuery ldapQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .attributes("uid", "cn")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("lan");

List<String> names = ldapTemplate.search(ldapQuery, attrs -> {
    return (String) attrs.get("cn").get();
});
```

`base("ou=people")` trong ví dụ là **tương đối** với `dc=example,dc=org`. Ba mức phạm vi thường gặp:

| Scope | Được tìm dưới search base? | Ví dụ với base `ou=people,dc=example,dc=org` |
|---|---|---|
| `OBJECT` | Chỉ entry tại base | Chỉ entry `ou=people` |
| `ONELEVEL` | Các entry con trực tiếp, không gồm base | `uid=lan`, `uid=binh` trong `ou=people` |
| `SUBTREE` | Entry base và mọi cấp con | Cả `ou=people` và các entry bên dưới ở mọi độ sâu |

`where("uid").is("lan")` giúp tạo LDAP filter và escape giá trị; nó **không thay thế** cho cách dựng DN an toàn khi code cần gọi `lookup`. Lưu ý nếu người dùng được quyền thay đổi search base thì phải kiểm tra nhánh được phép, không cho họ tùy ý mở rộng tìm kiếm đến mọi vùng directory.

Trong ứng dụng dùng repository, các lớp ánh xạ ODM như `@Entry`, `@Id`, `@Attribute` giúp mô tả entry Java. `@Entry(base = "ou=people")` mô tả vùng phù hợp **bên dưới base của context**. Đường dẫn DN trong đối tượng và cách repository đặt base vẫn phải theo quy ước của Spring LDAP; không tự cộng `@Entry.base`, `ContextSource.base` và hậu tố DN thêm lần nữa. Khi viết custom repository hoặc chuyển entity giữa các context, cần kiểm tra rõ DN tại từng ranh giới.

## 7. Nhận DN từ kết quả tìm kiếm: tránh mất mốc base

Một entry có thể được tham chiếu ở nhiều tầng:

```text
DN đầy đủ trên directory:
uid=lan,ou=people,dc=example,dc=org

DN tương đối với ContextSource.base = dc=example,dc=org:
uid=lan,ou=people

DN tương đối với search base = ou=people:
uid=lan
```

Tùy API, thông tin DN có thể được trả lại theo các mốc khác nhau:

- Ở **giao thức LDAP**, `SearchResultEntry.objectName` mang tên DN của entry.
- Với **JNDI**, `SearchResult.getName()` có thể là tên tương đối so với context của truy vấn; cần chú ý cả `isRelative()` và `getNameInNamespace()` khi provider hỗ trợ.
- Trong **Spring LDAP**, `ContextMapper`/`DirContextOperations` giúp truy cập DN gắn với context đã ánh xạ. Phải kiểm tra hợp đồng DN của tầng đang dùng trước khi ghi lại vào repository khác hoặc tạo URL cho hệ thống bên ngoài.
- `AttributesMapper` chỉ nhận `Attributes`, **không nhận trực tiếp DN** của entry. Nếu DTO cần DN, dùng loại mapper/API hỗ trợ ngữ cảnh DN.

**Không lấy `uid` rồi suy ra đầy đủ DN** trừ khi bạn biết chắc entry luôn ở đúng `ou=people` và không có tên ghép hoặc thay đổi vị trí. Cùng `uid=lan` có thể xuất hiện tại `ou=people` và `ou=contractors`; chỉ `uid` không phải khóa toàn cục.

Để trao đổi một DN qua các dịch vụ khác nhau, hãy ghi rõ:

1. Đây là **DN đầy đủ** hay **DN tương đối**?
2. Nếu tương đối, **base DN** nào được dùng?
3. Dữ liệu thuộc directory/naming context nào?

Nếu giao diện API chỉ có một trường `dn` nhưng không quy định ba điểm trên, việc chuyển cấu hình sang một base khác rất dễ gây lỗi.

## 8. Đổi tên hoặc chuyển entry làm thay đổi DN

DN dùng vị trí trong cây làm một phần định danh; nó có thể **thay đổi khi rename/move**. Ví dụ:

```text
Trước: uid=lan,ou=people,dc=example,dc=org
Sau:   uid=lan2,ou=people,dc=example,dc=org
```

Với base `dc=example,dc=org`, `LdapTemplate.rename(...)` nhận **hai tên tương đối**:

```java
Name oldDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

Name newDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan2")
        .build();

ldapTemplate.rename(oldDn, newDn);
```

Đây là ví dụ về đổi RDN dưới cùng một parent. Khi di chuyển sang nhánh khác, cần quyền ghi và khả năng hỗ trợ thao tác đổi DN của server; không phải topology LDAP nào cũng cho phép chuyển entry giữa naming context/server. Sau khi đổi DN, các liên kết hoặc cache lưu DN cũ cũng cần được xử lý theo nghiệp vụ.

**DN không nhất thiết là định danh bất biến** của người dùng. Nếu hệ thống cần ID giữ nguyên qua rename/move, hãy xem xét thuộc tính định danh ổn định do directory cung cấp (ví dụ `entryUUID` hoặc `objectGUID`, tùy server/schema), có quy tắc rõ cho từng backend. Không mặc định các thuộc tính đó hiện diện hoặc tương đương giữa tất cả LDAP directory.

## 9. Các lỗi phổ biến và cách xác định nguyên nhân

| Biểu hiện | Nguyên nhân có thể xảy ra | Cách xử lý |
|---|---|---|
| `lookup` báo không tìm thấy dù entry có tồn tại | Đã truyền DN đầy đủ vào API đòi DN tương đối nên bị ghép lặp base | Ghi lại base kết nối và DN tham số; dựng DN tương đối chuẩn |
| Tìm được dữ liệu ở nhánh `people` nhưng không thấy ở `groups` | Search base bị giới hạn ở `ou=people` hoặc scope quá hẹp | Xem lại search base và `OBJECT`/`ONELEVEL`/`SUBTREE` |
| Một DN hoạt động ở máy A nhưng lỗi ở máy B | Hai `ContextSource` sử dụng base khác nhau, hoặc topology khác | Chuẩn hóa quy ước API DN và cấu hình context của từng nguồn |
| Chuỗi `uid` có dấu phẩy khiến kết quả sai | Nối chuỗi DN từ đầu vào chưa escape | Dùng `LdapNameBuilder.add(attribute, value)` |
| Search theo `uid` có kết quả nhưng lookup theo DN thất bại | Entry không ở nhánh giả định, hoặc DN tham chiếu đã đổi | Lấy vị trí entry thực tế từ ngữ cảnh tìm kiếm |
| Đổi DN làm lookup cũ hỏng | DN thay đổi theo rename/move | Cập nhật tham chiếu và cân nhắc ID bất biến |
| `attrs.get("dn")` trả `null` | DN không tự động là một LDAP attribute của entry | Dùng API trả DN hoặc `ContextMapper` phù hợp |

Lỗi trong thao tác LDAP còn có thể đến từ quyền đọc, schema, naming context, referral và kết nối TLS. Vì vậy **đúng DN** là điều kiện cần, chưa đủ để khẳng định một thao tác thành công.

## 10. Kiểm thử việc dựng DN

Bạn có thể kiểm thử quy tắc DN độc lập với LDAP server. Ví dụ với JUnit 5:

**`DistinguishedNameTest.java`**

```java
package com.example.ldap;

import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DistinguishedNameTest {

    @Test
    void buildsRelativeAndFullDnFromTheSameEntry() {
        Name relative = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "lan")
                .build();

        Name full = LdapNameBuilder.newInstance("dc=example,dc=org")
                .add("ou", "people")
                .add("uid", "lan")
                .build();

        assertEquals("uid=lan,ou=people", relative.toString());
        assertEquals("uid=lan,ou=people,dc=example,dc=org",
                full.toString());
    }

    @Test
    void commaInsideUidIsNotAnExtraRdn() throws Exception {
        Name relative = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "lan,team")
                .build();

        LdapName parsed = new LdapName(relative.toString());
        assertEquals(2, parsed.size());
        assertEquals("uid", parsed.getRdn(parsed.size() - 1).getType());
        assertEquals("lan,team",
                parsed.getRdn(parsed.size() - 1).getValue());
    }
}
```

Kiểm thử trên chứng minh cách dựng tên và escape dấu phẩy; nó **không** chứng minh server có entry tương ứng.

Với kiểm thử tích hợp trên LDAP test directory, nên xác minh:

1. Bind một entry mẫu tại `uid=lan,ou=people,dc=example,dc=org`.
2. Dùng `ContextSource.base = dc=example,dc=org` rồi gọi `lookup` với `uid=lan,ou=people`: nhận đúng entry.
3. Dùng `search(base("ou=people"), scope ONELEVEL)`: chỉ nhận các entry con trực tiếp dự kiến.
4. Thử cấu hình base là `ou=people,dc=example,dc=org` và lookup bằng `uid=lan`: kết quả phải tương đương.
5. Cố tình truyền DN đầy đủ vào lời gọi yêu cầu DN tương đối trong môi trường thử nghiệm và đối chiếu lỗi để nhận diện vấn đề ghép base.
6. Thử rename trong môi trường test có đủ quyền và xác minh tên cũ không còn truy cập như trước.

Khi dùng nhiều backend LDAP, lặp các kiểm thử trên cho từng naming context thực tế; DN có thể đúng cú pháp nhưng không nằm trong vùng mà server hiện tại quản lý.

## 11. Câu hỏi tự kiểm tra

1. Với base `dc=example,dc=org`, bạn phải truyền DN nào vào `lookup` để đọc `uid=lan,ou=people,dc=example,dc=org`?
2. Khi đổi base thành `ou=people,dc=example,dc=org`, giá trị tương đối thay đổi như thế nào?
3. RDN `uid=lan` khác gì DN tương đối `uid=lan,ou=people`?
4. Tại sao `query().base("")` trong ứng dụng đã cấu hình base không mặc nhiên là truy vấn root DSE?
5. Vì sao cần `LdapNameBuilder` khi giá trị `uid` có dấu phẩy hoặc ký tự đặc biệt?
6. Sau khi rename một entry, lý do nào khiến DN không nên là định danh bất biến cho API công khai?

**Ghi nhớ:** DN đầy đủ xác định vị trí entry trong namespace; DN tương đối chỉ có nghĩa khi đã biết **base**. Trong Spring Data LDAP/Spring LDAP, `ContextSource.base` là mốc quan trọng cho `lookup`, `search` và các thao tác tên. Hãy dựng DN từ các RDN bằng công cụ chuyên dụng, quy định rõ loại DN tại ranh giới API và kiểm thử cùng cấu hình base thực tế.

### Tài liệu tham khảo

- IETF [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): khái niệm DIT, entry, DN, RDN và naming context.
- IETF [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cách biểu diễn và escape DN.
- Oracle Java SE: [`LdapName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html), [`Rdn`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/Rdn.html).
- Spring LDAP API: [`LdapNameBuilder`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapNameBuilder.html), [`LdapContextSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/LdapContextSource.html), [`LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html).
