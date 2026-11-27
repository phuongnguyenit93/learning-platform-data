# NameClassPairMapper và kết quả search trong Spring LDAP

Một ứng dụng Spring LDAP có thể cần **liệt kê tên các entry con của một OU** hoặc **tìm các entry theo filter rồi chuyển kết quả thành đối tượng Java**. Hai nhu cầu đều liên quan đến đọc thư mục, nhưng dữ liệu trả về và kiểu mapper được dùng không giống nhau. Nhầm `NameClassPairMapper` với `AttributesMapper` hoặc `ContextMapper` thường dẫn đến lỗi thiếu thuộc tính, hiểu sai DN, hoặc sử dụng tên lớp Java như thể nó là LDAP object class.

Bài học thuộc chương **Mapping kết quả** của SPRING_LDAP. Mục tiêu là hiểu `javax.naming.NameClassPair`, cách dùng `NameClassPairMapper` với `LdapTemplate.list(...)` và mối liên hệ với kết quả `search(...)`. Ta cũng thực hành phân biệt DN tương đối, chọn mapper thích hợp, xử lý thuộc tính tùy chọn/đa trị, kiểm soát filter, search scope và quyền truy cập. Nguyên tắc này vẫn hữu ích khi chuyển sang `LdapClient` hoặc ODM.

## 1. Một thư mục, ba nhu cầu truy cập

Giả sử LDAP server có cây thông tin thư mục (*DIT*):

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   ├── uid=binh
│   └── ou=contractors
│       └── uid=chi
├── ou=groups
│   └── cn=developers
└── ou=services
    └── cn=app-reader
~~~

Entry An:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
mail: an@example.org
~~~

| Câu hỏi của ứng dụng | Thao tác điển hình | Kiểu thông tin cần |
| --- | --- | --- |
| Có những entry con nào ngay dưới `ou=people`? | `list(...)` | Tên các binding trực tiếp |
| Có bao nhiêu entry `inetOrgPerson` trong toàn bộ subtree? | `search(...)` | Entry khớp filter ở nhiều độ sâu |
| Tìm người có `uid=an`, lấy `cn`, `mail` và DN? | `search(...)` | Attributes và định danh entry |

Nếu chỉ muốn hiện tên các con trực tiếp, không nhất thiết tải cả email. Ngược lại, một đối tượng mô tả tên binding không đủ để tạo DTO nhân viên có thuộc tính nghiệp vụ.

## 2. `NameClassPair` ở tầng JNDI

JNDI (*Java Naming and Directory Interface*) cung cấp `javax.naming.NameClassPair` để biểu diễn **tên** cùng **tên lớp Java của đối tượng được gắn với tên đó** trong một naming context.

| Thành viên | Giá trị trả về | Lưu ý |
| --- | --- | --- |
| `getName()` | Tên của binding/entry | Có thể là tên tương đối, không mặc định full DN |
| `getClassName()` | Tên lớp Java theo JNDI provider | **Không phải** thuộc tính LDAP `objectClass` |
| `isRelative()` | Có biểu diễn tương đối không | Cần xét trước khi diễn giải tên |
| `getNameInNamespace()` | Tên trong namespace nếu được cung cấp | Khả năng có tên đầy đủ phụ thuộc provider/ngữ cảnh |

Ví dụ tạo một `NameClassPair` thuần Java:

~~~java
import javax.naming.NameClassPair;

NameClassPair example = new NameClassPair(
        "uid=an",
        "javax.naming.directory.DirContext",
        true);

System.out.println(example.getName());       // uid=an
System.out.println(example.getClassName());  // Tên class Java minh họa
System.out.println(example.isRelative());    // true
~~~

Đây là **đối tượng giả lập**, không phải lời cam kết rằng một LDAP server hoặc JNDI provider luôn trả tên class Java như trong ví dụ.

### Cạm bẫy: hai nghĩa khác nhau của chữ “class”

| `NameClassPair.getClassName()` | LDAP attribute `objectClass` |
| --- | --- |
| Metadata thuộc mô hình JNDI naming | Dữ liệu LDAP của entry |
| Mô tả class Java của đối tượng binding | Mô tả schema object class mà entry thuộc về |
| Phụ thuộc cách provider biểu diễn object | Ví dụ `top`, `person`, `inetOrgPerson` |
| Không cho biết người dùng hay nhóm | Được server dùng khi kiểm tra MUST/MAY |
| Có ngay trên `NameClassPair` | Cần lấy attribute từ entry qua search/lookup |

**Sai:** dùng `pair.getClassName().equals("inetOrgPerson")` để nhận dạng nhân viên. **Đúng:** tìm theo LDAP filter `(objectClass=inetOrgPerson)` hoặc đọc thuộc tính `objectClass` từ entry, nếu có quyền.

## 3. `NameClassPairMapper` ánh xạ dữ liệu nào?

Spring LDAP định nghĩa interface `org.springframework.ldap.core.NameClassPairMapper<T>`. Về mặt hợp đồng, mapper nhận một `NameClassPair` và tạo ra đối tượng kiểu `T`:

~~~java
// Chữ ký minh họa trách nhiệm của interface:
import javax.naming.NameClassPair;
import javax.naming.NamingException;

public interface NameClassPairMapper<T> {
    T mapFromNameClassPair(NameClassPair pair)
            throws NamingException;
}
~~~

Đây là đoạn minh họa chữ ký, không phải yêu cầu khai báo lại interface trong dự án. Khi lập trình thực tế, **import interface do Spring LDAP cung cấp**.

Mapper không tự truy vấn LDAP, không tự tạo context và không xác định filter. Nó chỉ chuyển đổi đối tượng mà thao tác đã lấy được thành DTO. Trong cách dùng điển hình, mapper được truyền vào `LdapTemplate.list(...)`.

~~~mermaid
flowchart LR
    A["Service"] --> B["LdapTemplate.list"]
    B --> C["JNDI list trên OU"]
    C --> D["NameClassPair của từng child"]
    D --> E["NameClassPairMapper"]
    E --> F["List<DTO>"]
~~~

### Vì sao là list, không phải search?

JNDI `DirContext.list(...)` trả một enumeration các `NameClassPair` đại diện cho **những binding con trực tiếp**. Nó phù hợp khi ứng dụng muốn đi từng cấp trong cây. Ngược lại, `DirContext.search(...)` dùng filter/scope và trả các `SearchResult` có thể chứa attributes.

Không mặc định rằng một mapper nhận `NameClassPair` có thể đọc toàn bộ thông tin một entry. Đó chính là lý do Spring LDAP cung cấp các mapper khác nhau.

## 4. Ví dụ `LdapTemplate.list(...)` với `NameClassPairMapper`

Giả sử ứng dụng đã cấu hình `LdapContextSource` như sau:

~~~text
URL:                ldaps://ldap.example.org:636
ContextSource base: dc=example,dc=org
Service bind DN:    cn=app-reader,ou=services,dc=example,dc=org
~~~

Tài khoản bind được cấp quyền đọc trong `ou=people`. Ta xây DTO chỉ chứa tên binding và metadata JNDI:

~~~java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.NameClassPairMapper;
import org.springframework.stereotype.Service;

record ChildEntry(String name, String javaClass, boolean relative) {}

@Service
public class DirectoryTreeService {
    private final LdapTemplate ldapTemplate;

    public DirectoryTreeService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<ChildEntry> listPeopleChildren() {
        NameClassPairMapper<ChildEntry> mapper = pair ->
                new ChildEntry(
                        pair.getName(),
                        pair.getClassName(),
                        pair.isRelative());

        return ldapTemplate.list("ou=people", mapper);
    }
}
~~~

Ví dụ sử dụng overload `LdapTemplate.list(String, NameClassPairMapper<T>)` thường gặp trong Spring LDAP; cần đối chiếu phiên bản thư viện của dự án khi tích hợp. `record` yêu cầu Java 16+ (thông thường Java 17).

Với DIT ở mục 1, những tên con trực tiếp dự kiến là:

~~~text
uid=an
uid=binh
ou=contractors
~~~

**Không thấy `uid=chi`** bởi Chi nằm trong `ou=contractors`, tức ở hai cấp bên dưới `ou=people`. `list` ở đây không tự đệ quy. Các giá trị cụ thể của `javaClass` phụ thuộc JNDI provider, vì vậy không nên viết unit test khẳng định một class provider duy nhất.

### Search base và ContextSource base

Với `ContextSource.base=dc=example,dc=org`, lời gọi `list("ou=people", mapper)` thao tác tại:

~~~text
ou=people,dc=example,dc=org
~~~

`pair.getName()` trong ví dụ có thể là `uid=an`. Nó là tên con **tương đối với phép list**, không phải full DN `uid=an,ou=people,dc=example,dc=org`. Đừng nối suffix tùy ý nếu chưa xác định tên đang tương đối với ngữ cảnh nào.

Nếu search/list base của một API đã được hiểu tương đối với `ContextSource`, truyền cả `ou=people,dc=example,dc=org` có nguy cơ lặp suffix `dc=example,dc=org` và trỏ tới DN sai.

## 5. Giới hạn của việc liệt kê tên entry

| Thuộc tính của phép list | Ý nghĩa thực hành |
| --- | --- |
| Chỉ thấy child trực tiếp | Không tự tìm vào mọi OU lồng nhau |
| Không có filter LDAP trong thao tác list điển hình | Không chọn entry theo `uid` hay `objectClass` |
| Không lấy attributes trong `NameClassPair` | Không đọc được `mail`, `cn` qua mapper này |
| Không có full DN bảo đảm từ `getName()` | Phải hiểu tên tương đối và API/provider |
| `getClassName()` chỉ là tên Java | Không thay cho LDAP schema |
| Vẫn cần ACL | Không phải mọi danh tính đều được xem các entry |

Một ví dụ thực tế là giao diện duyệt cây LDAP: mỗi lần người dùng mở một OU, ứng dụng chỉ lấy các child của OU đó. Việc tải “theo nhu cầu” thường dễ kiểm soát hơn quét toàn subtree. Tuy nhiên, list trên OU có rất nhiều con vẫn có thể tốn tài nguyên; cần giới hạn truy cập và theo dõi tải thực tế.

Nếu muốn tìm các nhân viên có `mail` hoặc `uid` thỏa điều kiện, **search với filter** là lựa chọn đúng. Không sử dụng `list` rồi cố lấy `objectClass` từ `getClassName()`.

## 6. JNDI `SearchResult` chứa những gì?

JNDI trả các `javax.naming.directory.SearchResult` khi thực hiện tìm kiếm. `SearchResult` kế thừa trong họ `Binding`/`NameClassPair` nhưng có thêm **thuộc tính của entry** thông qua `getAttributes()`.

| Kiểu kết quả JNDI | Tên binding | Tên class Java | Attributes của LDAP entry |
| --- | --- | --- | --- |
| `NameClassPair` | Có | Có | **Không** |
| `Binding` | Có | Có | Không được cung cấp bởi giao diện cơ sở |
| `SearchResult` | Có | Có | **Có**, qua `getAttributes()` |

Phân biệt:

- `NameClassPair` là đối tượng metadata để liệt kê binding.
- `SearchResult` mô tả một kết quả search có tập attribute; nó **không chỉ** là tên binding.
- Spring LDAP cung cấp `AttributesMapper` và `ContextMapper` để giúp mapping kết quả search sang DTO.

Do đó, một dòng như `pair.getAttributes()` trên biến kiểu `NameClassPair` sẽ không biên dịch, vì interface/class đó **không có** phương thức này. Dù `SearchResult` nằm trong cùng hệ kế thừa, không mặc định rằng `NameClassPairMapper` là mapper đúng cho kết quả search có thuộc tính.

## 7. `AttributesMapper` cho kết quả search chỉ cần dữ liệu thuộc tính

Giả sử ứng dụng cần lấy `uid`, `cn`, `mail` từ toàn bộ nhánh nhân viên, gồm những OU lồng nhau. Dùng `LdapQueryBuilder` tạo query, rồi `AttributesMapper` biến tập thuộc tính thành DTO.

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

record PersonSummary(String uid, String name, String email) {}

public class PeopleService {
    private final LdapTemplate ldapTemplate;

    public PeopleService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findAllPeople() {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchControls.SUBTREE_SCOPE)
                .attributes("uid", "cn", "mail")
                .where("objectClass").is("inetOrgPerson");

        return ldapTemplate.search(
                query,
                (AttributesMapper<PersonSummary>) attrs ->
                        new PersonSummary(
                                attrs.get("uid") == null
                                        ? null
                                        : (String) attrs.get("uid").get(),
                                (String) attrs.get("cn").get(),
                                attrs.get("mail") == null
                                        ? null
                                        : (String) attrs.get("mail").get()));
    }
}
~~~

Ví dụ trả các entry mà server cho phép xem và có `objectClass=inetOrgPerson` trong subtree. Kết quả có thể bao gồm An, Bình và Chi; trong khi list chỉ thấy các entry con trực tiếp. `uid` là thuộc tính tùy chọn trong schema `inetOrgPerson` chuẩn, vì vậy mã cũng kiểm tra `uid` vắng mặt; `cn` được giả định có sẵn nhờ MUST của `person` và quyền đọc.

**`AttributesMapper` nhận `Attributes`, không nhận DN.** Nếu DTO cần định danh để thực hiện lookup, sửa hoặc xóa sau đó, dùng `ContextMapper` hoặc một API có thông tin DN phù hợp.

### Search dựa trên cả base, scope và filter

- `.base("ou=people")`: tìm từ OU nhân sự tương đối với base của `ContextSource`.
- `.searchScope(SearchControls.SUBTREE_SCOPE)`: bao gồm các cấp bên dưới OU đó.
- `.where("objectClass").is("inetOrgPerson")`: chỉ chọn entry có giá trị object class tương ứng.
- `.attributes("uid", "cn", "mail")`: hạn chế tập thuộc tính trả về theo nhu cầu.

Nếu chỉ dùng `ONELEVEL_SCOPE`, Chi sẽ nằm ngoài phạm vi search. Nếu chỉ dùng `NameClassPairMapper`, không có attribute `mail` để ánh xạ.

## 8. `ContextMapper` khi cần cả DN và thuộc tính

Một số DTO cần lưu tên entry cho các thao tác tiếp theo. `ContextMapper<T>` nhận ngữ cảnh của entry tìm được; trong Spring LDAP thường ép thành `DirContextOperations` để đọc DN và thuộc tính.

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

record PersonWithDn(String dn, String uid, String name, String email) {}

public class PeopleWithDnService {
    private final LdapTemplate ldapTemplate;

    public PeopleWithDnService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonWithDn> searchPeople() {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchControls.SUBTREE_SCOPE)
                .attributes("uid", "cn", "mail")
                .where("objectClass").is("inetOrgPerson");

        return ldapTemplate.search(
                query,
                (ContextMapper<PersonWithDn>) context -> {
                    DirContextOperations entry =
                            (DirContextOperations) context;
                    return new PersonWithDn(
                            entry.getDn().toString(),
                            entry.getStringAttribute("uid"),
                            entry.getStringAttribute("cn"),
                            entry.getStringAttribute("mail"));
                });
    }
}
~~~

`entry.getDn()` mô tả DN trong ngữ cảnh mà Spring LDAP đang dùng, thường tương đối với base của `ContextSource` trong luồng mapping. Không tự kết luận chuỗi đó luôn là full DN trên mọi API/provider. Khi chuyển DN sang service có base khác, phải xác định rõ cách diễn giải.

**Tóm lại:** dùng `NameClassPairMapper` cho dữ liệu tên từ list; dùng `AttributesMapper` cho nội dung thuộc tính; dùng `ContextMapper` khi cần cả dữ liệu và định danh entry.
## 9. Bảng chọn mapper theo dữ liệu cần lấy

| Nhu cầu nghiệp vụ | API Spring LDAP | Mapper phù hợp | Đầu vào mapper |
| --- | --- | --- | --- |
| Duyệt tên entry con trực tiếp trong một OU | `list(...)` | `NameClassPairMapper<T>` | `NameClassPair` |
| Tìm mọi người có `mail` theo filter | `search(...)` | `AttributesMapper<T>` | `Attributes` |
| Tìm người và lưu DN tương đối của entry | `search(...)` | `ContextMapper<T>` | Ngữ cảnh entry |
| Lấy một entry xác định theo DN | `lookup(...)` / `lookupContext(...)` | Mapper hoặc `DirContextOperations` theo overload | Phụ thuộc API |
| Mapping entry theo entity có annotation | ODM | Công cụ ODM | Entity/class theo mapping |
| Chỉ cần kiểm tra sự hiện diện thuộc tính | `search(...)` với filter presence | `AttributesMapper` hoặc `ContextMapper` | Thuộc tính được yêu cầu |

Phân biệt **mapper** với **truy vấn**. Mapper không quyết định search base, filter hay scope. Nó chỉ diễn giải kết quả sau khi server đã tìm kiếm và áp dụng ACL. Không thể sửa một search base sai bằng cách đổi mapper.

### Ba sai lầm khi chọn mapper

**Sai lầm 1 — Dùng tên lớp Java để lọc người dùng:** `getClassName()` phản ánh metadata của JNDI, không phải `inetOrgPerson` hay `groupOfNames`. Muốn lấy người dùng hãy dùng filter `(objectClass=inetOrgPerson)` và search.

**Sai lầm 2 — Dùng list để đếm toàn bộ subtree:** `list("ou=people", ...)` không tự tìm vào `ou=contractors`. Đếm các kết quả của list không phải số người trong cả subtree.

**Sai lầm 3 — Dùng AttributesMapper khi DTO phải chứa DN:** `Attributes` không tự cung cấp DN; lấy `uid` rồi tự ghép một DN giả định sẽ sai với các OU lồng nhau. Với nhu cầu định danh entry, dùng `ContextMapper` và giữ rõ ngữ cảnh DN.

## 10. Tên tương đối, search base và full DN

Đây là phần dễ gây lỗi nhất khi trả kết quả từ LDAP sang API khác.

~~~text
ContextSource base:
dc=example,dc=org

List base:
ou=people

NameClassPair.getName():
uid=an

DN đầy đủ của entry:
uid=an,ou=people,dc=example,dc=org
~~~

Có **hai loại “tương đối”**:

- Tên của `NameClassPair` từ JNDI list thường là **tương đối với ngữ cảnh thao tác list**; ở đây một tên như `uid=an` có thể chỉ là RDN.
- DN lấy từ `DirContextOperations.getDn()` qua Spring LDAP thường được dùng **tương đối với base của `ContextSource`**; có thể chứa `uid=an,ou=people`, không chỉ `uid=an`.

Với JNDI thuần, `SearchResult.getName()` có thể tương đối với **search base** của thao tác, và provider có thể cung cấp `getNameInNamespace()` nếu hỗ trợ. Không trộn các biểu diễn này mà không đánh dấu gốc.

| Giá trị | Ngữ cảnh phải biết |
| --- | --- |
| `uid=an` lấy từ phép list dưới `ou=people` | OU của phép list |
| `uid=an,ou=people` lấy từ mapper Spring LDAP | Base `dc=example,dc=org` |
| `uid=an,ou=people,dc=example,dc=org` | Full DN đã xác định |
| `uid=chi,ou=contractors` | Vẫn cần base nếu là DN tương đối |

Không dùng `String.split(",")` để bóc RDN: một DN có thể chứa dấu phẩy được escape trong **giá trị** RDN. Cũng không nối `"," + base` bằng tay cho mọi tên trả về mà không xét `isRelative()` hoặc nguồn phát sinh tên.

### Dựng DN đúng cách cho thao tác tiếp theo

Nếu đã có UID được kiểm tra theo chính sách ứng dụng và OU đích cố định, dùng `LdapNameBuilder`:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String uid = "an"; // Giá trị nghiệp vụ đã được xác minh.
Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", uid)
        .build();

// uid=an,ou=people: tương đối với ContextSource base.
~~~

Trong ví dụ này, không phải cứ thấy `pair.getName()` bằng `uid=an` là suy ra UID luôn có dạng đơn giản; trước khi tạo DN cho entry ở OU lồng nhau, xác định **parent thực tế**. Khi đọc tên từ list và muốn kết hợp các thành phần, ưu tiên parser/builder hỗ trợ cú pháp LDAP DN, không nối text tùy tiện.

**DN escaping khác filter escaping.** Dùng `LdapNameBuilder` cho tên DN; dùng `LdapQueryBuilder` hoặc filter builder cho assertion value của query.

## 11. Các trường hợp khó khi mapping thuộc tính từ search

### Thuộc tính `MAY` có thể vắng mặt

Trong schema `inetOrgPerson` phổ biến, `mail` không phải thuộc tính bắt buộc. Vì vậy:

~~~java
// Dễ lỗi nếu mail không được trả về:
String mail = (String) attrs.get("mail").get();

// Xử lý trường có thể vắng:
String safeMail = attrs.get("mail") == null
        ? null
        : (String) attrs.get("mail").get();
~~~

Một attribute có thể không được trả về vì entry không có giá trị, vì query không yêu cầu nó hoặc vì ACL không cho đọc. **Không nhìn thấy thuộc tính không tự chứng minh rằng nó không tồn tại trên server.**

### Thuộc tính LDAP có thể đa trị

`objectClass` và `member` thường có nhiều giá trị. Chỉ gọi `Attribute.get()` một lần sẽ không thu được cả tập.

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

public final class LdapAttributeValues {
    private LdapAttributeValues() {}

    public static List<String> readStrings(
            Attributes attrs, String attributeName) throws NamingException {

        Attribute attribute = attrs.get(attributeName);
        if (attribute == null) {
            return List.of();
        }

        List<String> values = new ArrayList<>();
        NamingEnumeration<?> entries = attribute.getAll();
        try {
            while (entries.hasMore()) {
                Object value = entries.next();
                if (value instanceof String stringValue) {
                    values.add(stringValue);
                }
            }
        } finally {
            entries.close();
        }
        return values;
    }
}
~~~

Code sử dụng pattern matching của Java 16+; dùng phiên bản Java phù hợp với dự án. Với các thuộc tính nhị phân, giá trị có thể là `byte[]` nên hàm trên **cố ý chỉ lấy String**. Không tự chuyển dữ liệu binary thành String. Đối với `member`, giá trị là một DN; muốn thao tác tên, hãy phân tích nó bằng API phù hợp sau khi đọc.

### Kết quả search có thể bị giới hạn

`AttributesMapper` không tự bảo đảm sẽ nhận mọi entry của subtree. Kết quả có thể bị giới hạn bởi ACL, server-side size limit, time limit, referral hoặc cấu hình search scope. Nếu cần tải danh sách lớn, hãy xem cơ chế paging mà server/client hỗ trợ; không mặc định một danh sách rỗng hay bị cắt là lỗi mapper.

## 12. Bảo mật và hiệu năng khi duyệt/mapping kết quả

| Quyết định | Rủi ro nếu làm sai | Thực hành phù hợp |
| --- | --- | --- |
| List toàn bộ OU rất lớn | Trả nhiều binding, làm tăng tải | Giới hạn khu vực được duyệt, dùng tree view theo cấp |
| Search từ naming context với subtree | Quét phạm vi rộng, có thể lộ nhiều metadata | Chỉ tìm dưới OU cần thiết |
| Yêu cầu mọi attributes | Chuyển dữ liệu nhạy cảm không cần thiết | Dùng projection `.attributes(...)` |
| Trả full DN ra API công khai | Tiết lộ topology hoặc định danh nội bộ | Chỉ trả theo nhu cầu và quyền |
| Cho client gửi filter LDAP thô | Nguy cơ LDAP injection | Dùng filter/query builder và allowlist |
| Dùng account quản trị để đọc | Vượt quyền tối thiểu | Service bind account chỉ đọc theo ACL |
| Đọc LDAP không TLS | Có thể lộ credential/dữ liệu trên mạng | LDAPS hoặc StartTLS xác minh chứng chỉ |

`NameClassPairMapper` không phải cơ chế bảo mật hoặc giới hạn truy vấn. Dù chỉ lấy tên entry, dữ liệu vẫn chịu chính sách LDAP ACL; đồng thời một tên OU hay RDN cũng có thể là thông tin nội bộ cần kiểm soát.

Khi gặp lỗi kết nối, xác thực hoặc truy vấn, phân biệt nhóm lỗi: `invalidCredentials (49)` cho bind, `noSuchObject (32)` thường liên quan tên/base, `insufficientAccessRights (50)` liên quan quyền, còn kết quả rỗng có thể chỉ do filter không khớp. Không thay mapper rồi coi đó là cách khắc phục một lỗi ACL hoặc search base.

## 13. Tình huống thực tế: giao diện quản trị LDAP

Một công cụ quản trị muốn có hai màn hình:

**Màn hình A — Duyệt cây.** Người vận hành bấm “People” để thấy `uid=an`, `uid=binh` và `ou=contractors`. Công cụ chỉ cần RDN và thông tin lớp Java do provider đưa ra nếu hữu ích cho chẩn đoán; **không** dựa vào lớp Java để quyết định icon người/nhóm.

**Màn hình B — Tìm nhân viên.** Người vận hành nhập UID hoặc chọn bộ lọc; ứng dụng cần trả về `cn`, `mail` và DN để mở hồ sơ. Công cụ sử dụng search với filter được xây an toàn, scope được giới hạn và `ContextMapper` để lấy DN cùng thuộc tính.

~~~mermaid
flowchart TD
    A["Người dùng chọn chức năng"] --> B{"Cần tên hay dữ liệu?"}
    B -->|Tên child trực tiếp| C["LdapTemplate.list"]
    C --> D["NameClassPairMapper"]
    D --> E["DTO tên/RDN"]
    B -->|Attributes theo filter| F["LdapTemplate.search"]
    F --> G{"Có cần DN?"}
    G -->|Không| H["AttributesMapper"]
    G -->|Có| I["ContextMapper"]
    H --> J["DTO dữ liệu"]
    I --> K["DTO dữ liệu + DN"]
~~~

Sơ đồ thể hiện một nguyên tắc thiết kế: **chọn API phù hợp với lượng thông tin cần lấy**, thay vì luôn tải toàn bộ entry rồi bỏ phần không dùng.

## 14. Bài thực hành: lựa chọn mapper và kiểm thử

Chuẩn bị LDAP lab theo DIT ở mục 1. Dùng tài khoản đã được cấp quyền đọc dưới `ou=people` và kết nối TLS được kiểm chứng. Không chạy thử trên thư mục sản xuất.

### Nhiệm vụ

1. Dùng `NameClassPairMapper` viết một phương thức trả `name` và `relative` cho mọi child trực tiếp dưới `ou=people`.
2. Giải thích vì sao kết quả của phép list không bao gồm `uid=chi`.
3. Dùng `LdapQueryBuilder` search `(objectClass=inetOrgPerson)` trong subtree `ou=people`. Hãy chọn mapper để chỉ lấy `uid`, `cn` và `mail`.
4. Nếu DTO còn cần DN để đổi email sau đó, nên chọn mapper nào?
5. Tại sao `pair.getClassName()` không giúp xác nhận entry thuộc `inetOrgPerson`?
6. Nếu nhóm `cn=developers` có ba DN thành viên trong `member`, mapper phải xử lý ra sao?
7. Nêu hai rủi ro khi lấy DN từ list rồi nối chuỗi để xóa entry.

### Đáp án

| Nhiệm vụ | Cách giải |
| --- | --- |
| 1 | Gọi `ldapTemplate.list("ou=people", pair -> new Child(pair.getName(), pair.isRelative()))` với DTO thích hợp |
| 2 | Vì `list` chỉ liệt kê con trực tiếp; Chi nằm trong `ou=contractors` |
| 3 | Dùng `search` với `SUBTREE_SCOPE` và `AttributesMapper` |
| 4 | Dùng `ContextMapper` lấy `DirContextOperations.getDn()` và các thuộc tính |
| 5 | `getClassName()` là class Java/JNDI; `objectClass` là LDAP attribute |
| 6 | Dùng `Attribute.getAll()`, mapping thành danh sách DN chứ không chỉ lấy một giá trị |
| 7 | Có thể nhầm tên tương đối với full DN, hoặc escape sai RDN gây trỏ nhầm entry; cần xác minh base và dùng builder/parser |

### Unit test logic `NameClassPairMapper`

Không cần LDAP server để kiểm thử một callback chỉ đọc các trường của `NameClassPair`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.naming.NameClassPair;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.NameClassPairMapper;

class NameClassPairMapperTest {
    record Child(String name, String className, boolean relative) {}

    @Test
    void mapsJndiNameMetadata() throws Exception {
        NameClassPairMapper<Child> mapper = pair ->
                new Child(
                        pair.getName(),
                        pair.getClassName(),
                        pair.isRelative());

        NameClassPair source = new NameClassPair(
                "uid=an", "javax.naming.directory.DirContext", true);

        Child result = mapper.mapFromNameClassPair(source);

        assertEquals("uid=an", result.name());
        assertEquals("javax.naming.directory.DirContext",
                result.className());
        assertTrue(result.relative());
    }
}
~~~

Đây chỉ là unit test về **chuyển đổi đối tượng**, không chứng minh LDAP server thực tế trả đúng tên hoặc class trong dữ liệu giả lập.

### Checklist integration test

- [ ] `ContextSource.base` và base của list/search trỏ đến đúng OU.
- [ ] List chỉ trả con trực tiếp; search subtree bao gồm những entry lồng sâu phù hợp.
- [ ] Mapper không nhầm `getClassName()` với LDAP `objectClass`.
- [ ] Search dùng filter/schema/ACL đúng để lấy các entry nhân viên.
- [ ] `AttributesMapper` xử lý attribute có thể vắng mặt và đa trị.
- [ ] `ContextMapper` trả DN theo ngữ cảnh đã biết, không nối lặp suffix.
- [ ] Không dùng DN hay filter thô do người dùng nhập để truy cập entry ngoài phạm vi cho phép.
- [ ] Kết nối LDAPS/StartTLS, tài khoản read-only, timeout và giới hạn search được kiểm tra.

## 15. Ghi nhớ

- **`NameClassPairMapper`** ánh xạ một `NameClassPair`, hữu ích khi dùng **`LdapTemplate.list(...)`** để đọc tên các entry con trực tiếp.
- **`getClassName()` không phải `objectClass` của LDAP.** Muốn nhận diện object class, sử dụng filter hoặc đọc attribute thật của entry.
- **`list` khác `search`**: list thường duyệt một cấp, search kết hợp base, scope và filter để chọn entry ở độ sâu cần thiết.
- **`AttributesMapper`** dành cho dữ liệu thuộc tính; **`ContextMapper`** phù hợp khi cần cả attributes và DN của kết quả.
- Không tự suy ra một tên tương đối là full DN. Xác định đúng base/ngữ cảnh và dùng API DN để xử lý RDN có ký tự escape.
- Với search thực tế, xử lý trường vắng mặt, thuộc tính đa trị, giới hạn kết quả và ACL; dùng filter builder cho input người dùng.
- Spring LDAP hỗ trợ quản lý JNDI context, nhưng không thay thế schema, xác thực, TLS và kiểm thử directory có quyền phù hợp.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [JNDI `NameClassPair` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/NameClassPair.html)
- [JNDI `SearchResult` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/SearchResult.html)
- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4515 — LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
