# List child context và đọc tên entry với LdapTemplate

Một LDAP directory là cây các **entry**, mỗi entry có **Distinguished Name (DN)**. Khi đã biết một nhánh và muốn liệt kê **những entry nằm ngay bên dưới nhánh đó**, Spring LDAP cung cấp các phương thức `LdapTemplate.list(...)` và `LdapTemplate.listBindings(...)`. Các phương thức này bắt nguồn từ cơ chế **naming context** trong JNDI và hoạt động theo kiểu **không đệ quy** (non-recursive).

Bài học thuộc chương **LdapTemplate** của module Spring LDAP. Trọng tâm là đọc tên các entry con, hiểu `NameClassPair`/`Binding` và phân biệt việc liệt kê tên với việc tìm kiếm thuộc tính bằng filter. Kiến thức này hữu ích khi duyệt cấu trúc OU, chọn nhánh người dùng, xây công cụ quản trị thư mục hoặc kiểm tra dữ liệu trước khi thao tác entry.

Sau bài học, bạn có thể:

- Giải thích “child context” và thế nào là **con trực tiếp** trong cây LDAP.
- Sử dụng `LdapTemplate.list(String)` và overload `list(Name)` để lấy tên các entry con.
- Ánh xạ `NameClassPair` bằng `NameClassPairMapper`, phân biệt `getName()`, `getClassName()` và `getNameInNamespace()`.
- Phân biệt `list` với `listBindings`, `lookup` và `search` có `ONELEVEL_SCOPE`.
- Xây DN con an toàn từ tên tương đối, không nối chuỗi hoặc tách DN thủ công.
- Xử lý ACL, base DN, thiếu entry, hiệu năng và kiểm thử bằng cây LDAP mẫu.

## 1. Child context là gì trong LDAP?

Giả sử directory chứa cây sau:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   ├── uid=minh
│   └── ou=contractors
│       └── uid=an
└── ou=groups
    └── cn=developers
```

Với **base** để liệt kê là `ou=people,dc=example,dc=org`:

| Entry | DN đầy đủ | Quan hệ với base |
| --- | --- | --- |
| People | `ou=people,dc=example,dc=org` | Chính entry base |
| Lan | `uid=lan,ou=people,dc=example,dc=org` | Con trực tiếp |
| Minh | `uid=minh,ou=people,dc=example,dc=org` | Con trực tiếp |
| Contractors | `ou=contractors,ou=people,dc=example,dc=org` | Con trực tiếp |
| An | `uid=an,ou=contractors,ou=people,dc=example,dc=org` | Cháu, sâu hai cấp |
| Developers | `cn=developers,ou=groups,dc=example,dc=org` | Thuộc nhánh khác |

Lệnh **list children** tại `ou=people` chỉ liệt kê Lan, Minh và OU contractors. Nó **không** bao gồm chính entry people, không tự đi sâu xuống An và không mở rộng sang groups.

Trong ngôn ngữ JNDI, một *context* là vùng tên chứa các tên được bind bên dưới nó; `Context.list(...)` liệt kê các binding con. Trong LDAP, các entry thể hiện cây DN. Dù tên gọi là “list child context”, **không nên hiểu rằng chỉ có entry thuộc object class `organizationalUnit` mới được liệt kê**: `uid=lan` và `uid=minh` cũng là con trực tiếp. Muốn chỉ lấy OU, phải dùng cách tìm kiếm có filter phù hợp.

**RDN không phải DN đầy đủ.** Tên con như `uid=lan` là một **Relative Distinguished Name (RDN)** so với OU people. DN đầy đủ của Lan có thêm đường dẫn cha `ou=people,dc=example,dc=org`.

## 2. `LdapTemplate.list(...)`: liệt kê tên ngay dưới base

Spring LDAP cung cấp overload thông dụng:

| Phương thức | Kết quả | Khi sử dụng |
| --- | --- | --- |
| `list(String base)` | `List<String>` gồm tên con | Chỉ cần tên |
| `list(Name base)` | `List<String>` gồm tên con | Đã có một đối tượng `javax.naming.Name` |
| `list(String base, NameClassPairMapper<T>)` | `List<T>` do mapper tạo | Muốn đọc tên kèm metadata của `NameClassPair` |
| `list(Name base, NameClassPairMapper<T>)` | `List<T>` do mapper tạo | Vừa có base dạng `Name` vừa cần ánh xạ |
| `list(String/Name, NameClassPairCallbackHandler)` | Callback trên từng kết quả | Muốn xử lý tên con trong callback thay vì lấy `List<T>` |

Theo hợp đồng API, `list` là thao tác **non-recursive**: danh sách gồm các tên được bind trực tiếp dưới base, không phải tất cả entry bên trong subtree.

### Ví dụ Java: lấy List<String> tên con

Giả sử `ContextSource` của ứng dụng cấu hình base `dc=example,dc=org`:

```java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;

public final class DirectoryChildren {
    private final LdapTemplate ldapTemplate;

    public DirectoryChildren(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> listPeopleChildren() {
        return ldapTemplate.list("ou=people");
    }
}
```

Với directory ví dụ và LDAP provider trả tên con tương đối, danh sách có các phần tử như:

```text
uid=lan
uid=minh
ou=contractors
```

Đây là **tập kết quả minh họa**; không giả định server giữ nguyên thứ tự trả về. Chương trình cần sắp xếp nếu muốn giao diện hiển thị theo thứ tự cố định. Danh sách tên này **không tự chứa** `cn`, `mail`, `displayName` hay toàn bộ DN của từng entry.

Không nên thực hiện:

```java
// Sai về ý nghĩa nếu mong muốn xem mọi người dùng bên dưới people.
List<String> everyone = ldapTemplate.list("ou=people");
```

Nếu entry An nằm sâu trong OU contractors, An không có trong kết quả trên. Khi cần mọi cấp con, phải xác định yêu cầu rồi dùng `search` với scope subtree và filter thích hợp.

## 3. Base context của ContextSource và base của lệnh list

LDAP server nhận DN để định vị nhánh. Nhưng `LdapTemplate` làm việc thông qua `ContextSource`, vốn thường có **base context**:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Các giá trị `example.org` chỉ dùng cho ví dụ. Mật khẩu bind cần được cấp từ secret store/biến môi trường và kết nối phải xác minh chứng chỉ TLS đúng cách.

Với cấu hình trên:

```text
ContextSource base: dc=example,dc=org
list() base:        ou=people
Vị trí thật:        ou=people,dc=example,dc=org
```

Vì vậy, khi `ContextSource.base = "dc=example,dc=org"`, đối số `"ou=people"` của `list` là **DN tương đối** của nhánh cần liệt kê. Nếu truyền cả `"ou=people,dc=example,dc=org"`, bạn có thể vô tình lặp hậu tố base và trỏ sang một DN không tồn tại.

| ContextSource base | Base truyền cho `list` | Nhánh thực tế được yêu cầu |
| --- | --- | --- |
| `dc=example,dc=org` | `ou=people` | `ou=people,dc=example,dc=org` |
| `ou=people,dc=example,dc=org` | `""` | Chính nhánh `ou=people,...` |
| Base rỗng | `ou=people,dc=example,dc=org` | `ou=people,dc=example,dc=org` |

Lưu ý phân biệt:

- **ContextSource base**: gốc mà các thao tác của ứng dụng lấy làm tương đối.
- **List base**: entry cha có các con trực tiếp cần liệt kê.
- **Entry DN**: tên xác định entry cụ thể, ví dụ `uid=lan,ou=people,dc=example,dc=org`.
- **Bind DN**: danh tính dùng để đăng nhập vào LDAP server; không phải base của truy vấn.

Thay đổi base không thay đổi LDAP schema hay nội dung entry trên server. Base chỉ thay đổi **cách client định vị** các entry.

## 4. `NameClassPair`: đọc tên entry và tên lớp đối tượng JNDI

JNDI định nghĩa `NameClassPair` cho kết quả liệt kê tên. Hai thành phần chính là:

| Thành phần | Ý nghĩa |
| --- | --- |
| `getName()` | Tên của binding được liệt kê |
| `getClassName()` | Tên lớp Java của đối tượng được bind, theo cách provider mô tả |
| `isRelative()` | Cho biết tên trong `getName()` có tương đối với context được liệt kê không |
| `getNameInNamespace()` | Tên đầy đủ trong namespace, **nếu provider hỗ trợ** |

Trong trường hợp LDAP provider trả tên tương đối, `getName()` thường là một RDN như `uid=lan` hoặc `ou=contractors`. Giá trị `getClassName()` là **tên lớp Java/JNDI**, không phải giá trị attribute LDAP `objectClass` và cũng không phải tên của người dùng.

### Ví dụ: mapper biến mỗi NameClassPair thành DTO

```java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.NameClassPairMapper;

record ChildBindingName(
    String childName,
    String javaClassName,
    boolean relative
) {}

public final class DirectoryNameReader {
    private final LdapTemplate ldapTemplate;

    public DirectoryNameReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<ChildBindingName> listChildrenWithMetadata() {
        return ldapTemplate.list(
            "ou=people",
            (NameClassPairMapper<ChildBindingName>) pair ->
                new ChildBindingName(
                    pair.getName(),
                    pair.getClassName(),
                    pair.isRelative()
                )
        );
    }
}
```

Với dữ liệu mẫu, những trường `childName` có thể là `uid=lan`, `uid=minh` và `ou=contractors`. Việc đọc `javaClassName` chỉ để hiểu thông tin JNDI trả về; **không nên lọc người dùng hay OU dựa trên tên lớp Java này**. LDAP object class phải đọc từ attribute `objectClass` qua lookup/search nếu cần phân loại entry.

### Cẩn thận khi đọc “tên đầy đủ”

Trong JNDI, `NameClassPair.getNameInNamespace()` có thể trả về tên đầy đủ trong namespace. Nhưng không phải provider hoặc kiểu binding nào cũng hỗ trợ; lời gọi có thể ném `UnsupportedOperationException`.

Vì vậy, đừng viết code bắt buộc lấy DN đầy đủ từ mọi `NameClassPair` mà không kiểm chứng provider. Nếu `pair.isRelative()` là `true`, có thể ghép **tên con** với DN của base bằng API parse DN thích hợp. Nếu `isRelative()` là `false`, theo hợp đồng JNDI, tên có thể là URL và **không được xử lý như một RDN LDAP bình thường**.

## 5. Xây DN con an toàn từ kết quả list

Trong cây ví dụ:

```text
Tên con (RDN):     uid=lan
Base list:         ou=people
ContextSource:     dc=example,dc=org
DN tương đối:      uid=lan,ou=people
DN đầy đủ:         uid=lan,ou=people,dc=example,dc=org
```

Khi cần dùng tên con cho `lookup`, bạn cần **DN tương đối với ContextSource base**, không chỉ chuỗi tên con. Không ghép chuỗi bằng `child + "," + base` nếu `child` là dữ liệu chưa xác định hình dạng hoặc chưa được parse; tên LDAP có escaping riêng, RDN có thể chứa dấu phẩy hoặc dấu cộng được escape.

Ví dụ với `javax.naming.ldap.LdapName`:

```java
import java.util.List;
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.NameClassPairMapper;

public final class ChildDnReader {
    private final LdapTemplate ldapTemplate;

    public ChildDnReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<Name> directChildDns() {
        return ldapTemplate.list(
            "ou=people",
            (NameClassPairMapper<Name>) pair -> {
                if (!pair.isRelative()) {
                    throw new NamingException(
                        "Child name is not relative to the listing base");
                }

                // Mỗi tên con trực tiếp phải là đúng một RDN.
                LdapName childRdn = new LdapName(pair.getName());
                if (childRdn.size() != 1) {
                    throw new NamingException(
                        "Expected a single-RDN child name");
                }

                LdapName relativeDn = new LdapName("ou=people");
                relativeDn.addAll(childRdn);
                return relativeDn;
            }
        );
    }
}
```

Với tên con `uid=lan`, kết quả tương ứng `uid=lan,ou=people`, là DN tương đối mà `LdapTemplate.lookup` dùng được khi `ContextSource.base = "dc=example,dc=org"`.

Một cách dùng tiếp:

```java
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;

for (Name dn : directChildDns()) {
    String cn = ldapTemplate.lookup(
        dn,
        (AttributesMapper<String>) attrs ->
            attrs.get("cn") == null
                ? null
                : (String) attrs.get("cn").get()
    );
    // Xử lý cn theo nhu cầu ứng dụng; không giả định mọi child đều là user.
}
```

Đoạn `for` là ví dụ rút gọn bên trong một class có field `ldapTemplate` và method `directChildDns()`. Chú ý: OU `ou=contractors` có thể **không có attribute `cn`**, vì thế ví dụ trả `null` cho entry này.

### Tránh bẫy N+1 lookup

Nếu liệt kê được 5.000 tên con rồi gọi `lookup` cho **mỗi tên**, ứng dụng có thể thực hiện hàng nghìn thao tác LDAP bổ sung. Nếu cần tên **và** attribute của nhiều entry, hãy dùng một **one-level search** với filter và projection phù hợp, thay vì luôn list xong mới lookup từng entry.

Nếu chỉ cần các tên, `list` thường rõ ràng hơn và tránh tải attribute không cần thiết. Cách tối ưu cụ thể cần đo trên directory server thực tế và phụ thuộc index, ACL, độ lớn OU, giới hạn truy vấn và network.

## 6. `listBindings(...)` khác `list(...)` ở đâu?

Trong JNDI:

- `Context.list(...)` trả `NamingEnumeration<NameClassPair>`: **tên và thông tin tên lớp** của binding.
- `Context.listBindings(...)` trả `NamingEnumeration<Binding>`: thông tin binding **kèm đối tượng được bind**.

Spring LDAP cung cấp `LdapTemplate.listBindings(...)` với overload tương ứng. Nó cũng **chỉ liệt kê con trực tiếp** của base; không tự chuyển thành subtree search.

| Tác vụ | Phương thức phù hợp | Nhận xét |
| --- | --- | --- |
| Lấy tên các entry con | `list("ou=people")` | Ngắn gọn nhất nếu chỉ cần tên |
| Đọc `NameClassPair.getName()` và thông tin lớp | `list(base, NameClassPairMapper)` | Không nhất thiết lấy đối tượng bound |
| Cần truy cập `Binding`/bound object | `listBindings(base, mapper)` | Phụ thuộc JNDI provider và loại object trả về |
| Cần `cn`, `uid`, `mail` của entry | `search` hoặc `lookup` với mapper | Kiểm soát attribute được trả về |

Ví dụ đọc tên từ kết quả `listBindings`:

```java
import java.util.List;
import javax.naming.Binding;
import org.springframework.ldap.core.NameClassPairMapper;

List<String> childNames = ldapTemplate.listBindings(
    "ou=people",
    (NameClassPairMapper<String>) pair -> {
        Binding binding = (Binding) pair;
        return binding.getName();
    }
);
```

Code này dựa vào hợp đồng của `listBindings` là cung cấp `Binding`. Nếu chỉ muốn tên, cách trên **không có lợi thế** so với `ldapTemplate.list("ou=people")`. Bound object có thể yêu cầu nhiều công việc hơn; không tự tin rằng `Binding.getObject()` luôn là `DirContextOperations` hoặc chứa sẵn mọi attribute LDAP bạn muốn.

Spring LDAP cũng có overload `listBindings(base, ContextMapper<T>)` ở những phiên bản hỗ trợ, dùng để ánh xạ đối tượng được trả về trong binding. Chỉ nên chọn đường này nếu thật sự cần context/object và đã kiểm thử trên provider. Không ép kiểu tùy ý một bound object thành DTO nghiệp vụ.

## 7. Khi nào nên dùng one-level search thay vì list?

`list` hữu ích để **khám phá tên entry** dưới một nhánh. Nhưng nó không có tham số filter để giới hạn theo object class, phòng ban hoặc thuộc tính bất kỳ.

Ví dụ yêu cầu “Liệt kê **chỉ các tài khoản inetOrgPerson** là con trực tiếp của OU people, kèm UID và tên hiển thị.” Nếu dùng `list("ou=people")`, kết quả có thể gồm cả OU contractors. Dùng `search` với `SearchControls.ONELEVEL_SCOPE` phù hợp hơn:

```java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

record DirectPerson(String uid, String cn) {}

public final class DirectPeopleSearch {
    private final LdapTemplate ldapTemplate;

    public DirectPeopleSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectPerson> findDirectPeople() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
        controls.setReturningAttributes(new String[] {"uid", "cn"});
        controls.setCountLimit(200);

        return ldapTemplate.search(
            "ou=people",
            "(&(objectClass=inetOrgPerson)(uid=*))",
            controls,
            (AttributesMapper<DirectPerson>) attrs -> {
                Attribute uid = attrs.get("uid");
                Attribute cn = attrs.get("cn");
                return new DirectPerson(
                    uid == null ? null : (String) uid.get(),
                    cn == null ? null : (String) cn.get()
                );
            }
        );
    }
}
```

Giải thích:

1. `"ou=people"` là search base tương đối với `ContextSource.base`.
2. `SearchControls.ONELEVEL_SCOPE` chỉ xét con trực tiếp — tương tự độ sâu mà `list` liệt kê.
3. Filter `(&(objectClass=inetOrgPerson)(uid=*))` loại các entry không thuộc lớp người dùng tương ứng.
4. `setReturningAttributes(...)` chỉ yêu cầu `uid` và `cn` thay vì mọi attribute.
5. `setCountLimit(200)` là giới hạn kết quả, **không phải** cơ chế phân trang hay bảo đảm OU chỉ có tối đa 200 entry.

Khác biệt cần nhớ:

| API | Có filter? | Độ sâu | Nhận được gì? |
| --- | --- | --- | --- |
| `list(base)` | Không | Một cấp con | Tên con |
| `listBindings(base)` | Không | Một cấp con | Tên/binding object, tùy overload |
| `lookup(dn, mapper)` | Không | Đúng một DN đã biết | Dữ liệu của entry đó |
| `search(base, filter, ONELEVEL_SCOPE, mapper)` | Có | Một cấp con | Các entry khớp filter và attribute yêu cầu |
| `search(base, filter, SUBTREE_SCOPE, mapper)` | Có | Mọi cấp con và base | Các entry khớp filter ở toàn subtree |

Không nên thay `ONELEVEL_SCOPE` bằng `SUBTREE_SCOPE` chỉ vì muốn “lấy đủ” nếu nghiệp vụ chỉ cần các con trực tiếp; chọn scope rộng hơn sẽ làm thay đổi **ý nghĩa và khối lượng** truy vấn.

## 8. Đọc tên entry và DN: các lỗi diễn giải thường gặp

### 8.1. Tên trong kết quả không luôn là DN đầy đủ

Giả sử `list("ou=people")` trả `uid=lan`. Nếu đem ngay `"uid=lan"` truyền cho `lookup` với `ContextSource.base = "dc=example,dc=org"`, client sẽ thử đọc `uid=lan,dc=example,dc=org`, **không phải** `uid=lan,ou=people,dc=example,dc=org`. Bạn cần bổ sung nhánh `ou=people` khi tạo DN tương đối.

### 8.2. Không tách DN bằng dấu phẩy thô

Giả sử một RDN có giá trị chứa dấu phẩy:

```text
cn=Nguyen\, Lan
```

Đó vẫn có thể là **một RDN**, vì dấu phẩy được escape. Dùng `LdapName`/`LdapNameBuilder` thay vì `split(",")` để parse hoặc xây DN. RDN nhiều thành phần như `cn=Lan+uid=lan` cũng cần được xử lý như một đơn vị RDN, không dùng tách `+` thô.

### 8.3. “Tên entry” không bằng `cn` hoặc `displayName`

Tên trả về từ `list` là **tên binding/RDN**. Với `uid=lan`, đó là tên định vị entry trong OU. Attribute `cn: Lan Nguyen` và `displayName: Lan N.` là **dữ liệu LDAP**, có thể khác hẳn RDN. Nếu giao diện cần tên thân thiện, hãy dùng lookup/search để lấy attribute này, thay vì hiển thị nguyên `uid=lan` như một “họ tên”.

### 8.4. Không giả định thứ tự hoặc tính đầy đủ của mọi lần liệt kê

JNDI không hứa thứ tự ổn định của `NamingEnumeration`; không nên dùng “phần tử đầu tiên” làm mặc định. Kết quả có thể chịu giới hạn/ACL của server. Với OU lớn, một lần list có thể tốn tài nguyên và bị server từ chối vì giới hạn; API list cơ bản không thay thế thiết kế phân trang/giới hạn tải cho một tác vụ export dữ liệu lớn.

## 9. Quản lý tài nguyên và xử lý lỗi

Với JNDI trực tiếp, caller có trách nhiệm duyệt và đóng `NamingEnumeration` cùng context theo hợp đồng API. Khi sử dụng các overload của `LdapTemplate.list(...)`, Spring LDAP đảm nhiệm các phần việc lặp lại: lấy context đọc, duyệt kết quả, chuyển đổi exception và giải phóng tài nguyên. Điều đó giúp tầng ứng dụng tập trung vào tên/DTO, không tự quản lý `DirContext` trong mỗi lần gọi.

Tuy nhiên, caller vẫn phải xử lý lỗi hợp lý:

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Danh sách rỗng | Base không có con thấy được, ACL che kết quả, hoặc tình huống lỗi tên được API xử lý | Kiểm tra base, quyền và hành vi API thực tế |
| Base bị lặp hậu tố | Đã truyền DN đầy đủ trong khi `ContextSource` có base | Sửa DN tương đối truyền vào `list` |
| Chỉ thấy `ou=contractors` nhưng không thấy `uid=an` | An là cháu, không phải con trực tiếp | Chọn base `ou=contractors,ou=people` hoặc subtree search |
| `getClassName()` không bằng `inetOrgPerson` | Đây là tên lớp của đối tượng JNDI | Dùng LDAP attribute `objectClass` qua search |
| Muốn `mail` nhưng list chỉ trả tên | API list không phải truy vấn attribute với filter | Dùng `search` hoặc `lookup` |
| Timeout/size limit | OU quá nhiều con, thiếu quota, provider/server giới hạn | Thu hẹp base, dùng search có kiểm soát/paging |
| Lỗi bind/TLS/ACL | Kết nối hoặc quyền của tài khoản không đủ | Kiểm tra endpoint, truststore, bind và ACL |

**Đặc biệt chú ý lỗi tên không tồn tại:** tài liệu API Spring LDAP ghi nhận ở một số overload liệt kê, `NameNotFoundException` có thể được diễn giải thành **không tìm thấy entry nào** và trả danh sách rỗng. Vì vậy, **danh sách rỗng không phải bằng chứng chắc chắn base tồn tại**. Nếu nghiệp vụ bắt buộc biết base có tồn tại, thực hiện kiểm tra riêng (ví dụ lookup base bằng quyền thích hợp) và phân biệt rõ lỗi hạ tầng với không có child.

Về bảo mật, dùng LDAPS hoặc StartTLS với chứng chỉ máy chủ được xác minh; bảo vệ bind credentials bằng secret store. Quyền truy cập được LDAP server quyết định, không phải việc ứng dụng gọi `list` hay `search`. Tránh hiển thị DN nhạy cảm hoặc ghi toàn bộ cây LDAP vào log của request công khai.

## 10. Quy trình thử nghiệm trên một directory mẫu

Để kiểm tra cách liệt kê, có thể dùng các entry giả định sau:

```ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Minh Tran
sn: Tran

dn: ou=contractors,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: contractors

dn: uid=an,ou=contractors,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Le
sn: Le
```

Chạy theo thứ tự:

1. Cấu hình `ContextSource.base = dc=example,dc=org` và xác minh bind/TLS thành công.
2. Gọi `list("ou=people")`; kỳ vọng tập tên con gồm `uid=lan`, `uid=minh`, `ou=contractors`.
3. Gọi `list("ou=contractors,ou=people")`; kỳ vọng `uid=an`.
4. Dùng mapper `NameClassPairMapper` để đọc tên; xác nhận `getName()` và `isRelative()` theo provider.
5. Xây DN tương đối của Lan từ `uid=lan` và `ou=people`, sau đó `lookup` `cn` thành công.
6. Chạy one-level search tại `ou=people` với filter `(objectClass=inetOrgPerson)`; kỳ vọng chỉ Lan và Minh.
7. Thử base không tồn tại và user bind có quyền hạn chế để quan sát sự khác biệt, không suy diễn từ danh sách rỗng.

Lệnh dòng lệnh gần tương đương **về phạm vi** với danh sách con:

```bash
ldapsearch -x -LLL -H ldaps://ldap.example.org:636 \
  -D "cn=reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(objectClass=*)" dn
```

Đây là **one-level search**, không phải thao tác JNDI `Context.list` đúng nghĩa; nó có filter và trả DN theo kết quả search. Mục tiêu là đối chiếu tập con trực tiếp khi filter không loại bớt entry thông thường. Để hiển thị tên con như `uid=lan`, cần đọc/parse DN trong kết quả; không mặc nhiên coi chuỗi `dn: ...` giống phần tử trong `LdapTemplate.list(...)`.

## 11. Bài tập tự kiểm tra

Giả sử cây:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=hoa
│   ├── ou=interns
│   │   └── uid=bao
│   └── uid=long
└── ou=groups
    └── cn=editors
```

Ứng dụng cấu hình `ContextSource.base = "dc=example,dc=org"` và có quyền đọc tất cả entry.

**Câu hỏi:**

1. Gọi `ldapTemplate.list("ou=people")` có thể nhận những tên con nào?
2. Tại sao `uid=bao` không có trong kết quả câu 1?
3. Để liệt kê đúng các con của `ou=interns`, base truyền cho `list` nên là gì?
4. Nếu kết quả `getName()` là `uid=hoa` với `isRelative() == true`, DN tương đối cần truyền cho `lookup` là gì?
5. Khi giao diện cần `cn` và `mail` của các người dùng con trực tiếp, `list` hay `search` phù hợp hơn?
6. `NameClassPair.getClassName()` có phải là LDAP attribute `objectClass` không?
7. Vì sao việc dùng `split(",")` để lấy RDN từ DN bất kỳ không đáng tin?
8. Nếu `list("ou=unknown")` trả danh sách rỗng, có thể kết luận OU đó chắc chắn tồn tại nhưng không có con không?

**Đáp án:**

1. Tập tên gồm `uid=hoa`, `ou=interns` và `uid=long`; thứ tự không được đảm bảo.
2. Bảo là **cháu** của people, nằm dưới OU interns. `list` không duyệt đệ quy.
3. `ou=interns,ou=people`, tương đối với base context `dc=example,dc=org`.
4. `uid=hoa,ou=people`; cần gắn RDN tên con vào đúng nhánh cha trước khi lookup.
5. One-level `search` với filter chọn người dùng và projection `cn`/`mail` phù hợp hơn, tránh liệt kê rồi lookup từng entry.
6. Không. `getClassName()` là thông tin kiểu object JNDI; LDAP `objectClass` là attribute trong entry.
7. Một RDN có thể chứa dấu phẩy đã escape hoặc nhiều cặp thuộc tính–giá trị; dùng `LdapName` để parse đúng.
8. Không. Theo API, một số lỗi `NameNotFoundException` khi list có thể được diễn giải là không có kết quả; cần kiểm chứng base riêng nếu sự tồn tại là bắt buộc.

## 12. Ghi nhớ và tài liệu tham khảo

`LdapTemplate.list(base)` liệt kê **tên các entry con trực tiếp** của base, không chứa chính base và không đi sâu vào cháu/chắt. `NameClassPair` cho phép đọc tên và thông tin lớp JNDI; `listBindings` có thể cung cấp đối tượng bound, nhưng **không nên dùng thay one-level search** khi mục tiêu là lọc theo attribute hoặc lấy nhiều thuộc tính LDAP.

Để dùng tên con đúng, hãy phân biệt RDN trả về với DN tương đối cho template và DN đầy đủ trên server; kiểm tra `isRelative()`, ưu tiên `LdapName`/`LdapNameBuilder`, và không giả định provider nào cũng hỗ trợ `getNameInNamespace()`. Với nhiều entry, chọn filter/scope/projection thích hợp để tránh N+1 lookup, đồng thời kiểm soát TLS, ACL và các giới hạn vận hành.

Tài liệu tham khảo:

- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): các overload `list`, `listBindings`, `search` và resource handling.
- [Spring LDAP — NameClassPairMapper API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/NameClassPairMapper.html): hợp đồng ánh xạ `NameClassPair`.
- [JNDI — Context API (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/Context.html): `list` và `listBindings`.
- [JNDI — NameClassPair API (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/NameClassPair.html): `getName`, `isRelative`, `getNameInNamespace`.
- [RFC 4514 — LDAP Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): định dạng DN và escape RDN.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): entry, search và phạm vi tìm kiếm.
