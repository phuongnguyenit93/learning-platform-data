# Lookup entry bằng DN với LdapTemplate

Trong LDAP, một **entry** được xác định bằng **Distinguished Name (DN)**, ví dụ `uid=lan,ou=people,dc=example,dc=org`. Khi ứng dụng đã biết DN của entry cần đọc, `LdapTemplate.lookup(...)` là cách trực tiếp để lấy dữ liệu của **entry đó**. Bạn không cần xây LDAP search filter để tìm một bản ghi đã biết tên chính xác.

Bài học thuộc chương **LdapTemplate** của module Spring LDAP. Trọng tâm là cách đọc entry theo DN, xây tên an toàn, ánh xạ thuộc tính và xử lý trường hợp không tìm thấy hoặc không đủ quyền. Kiến thức này bổ trợ cho việc cấu hình `ContextSource`, xác thực/TLS và thao tác entry qua `LdapTemplate`, `LdapClient` hoặc ODM trong các bài khác.

Sau bài học, bạn có thể:

- Phân biệt **DN**, **RDN**, **base DN của ContextSource** và DN tương đối truyền cho `lookup`.
- Dùng `lookup(String, ...)` hoặc `lookup(Name, ...)` với `ContextMapper` và `AttributesMapper`.
- Đọc attribute đơn trị, nhiều giá trị và thuộc tính tùy chọn mà không làm mất dữ liệu.
- Tạo DN động bằng `LdapNameBuilder` để tránh lỗi escape và thay đổi cấu trúc tên ngoài ý muốn.
- Phân biệt lookup theo DN với search theo thuộc tính, nhận diện lỗi và kiểm thử bằng dữ liệu LDAP mẫu.

## 1. Lookup khác gì với search?

Xét một cây LDAP:

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

DN đầy đủ của Lan là:

```text
uid=lan,ou=people,dc=example,dc=org
```

Nếu đã biết DN này, ta có thể tra cứu đúng entry Lan. Nếu **chỉ biết giá trị `uid=lan`** mà không biết người dùng nằm trong OU nào, ta thường phải **search** trong phạm vi phù hợp bằng filter `(uid=lan)` rồi xác định DN của entry khớp.

| Cách truy cập | Thông tin cần biết | Ví dụ | Kết quả mong đợi |
| --- | --- | --- | --- |
| **Lookup** | DN của entry cần đọc | `lookup("uid=lan,ou=people", mapper)` | Dữ liệu của một entry có DN đó, hoặc lỗi nếu không thể tra cứu |
| **Search** | Search base, scope và filter | Tìm `(uid=lan)` dưới `ou=people` | Danh sách các entry thỏa điều kiện |
| **Base-object search** | DN base và filter áp dụng lên chính base | `-s base -b "uid=lan,ou=people,..."` | 0 hoặc 1 entry, tùy filter có khớp |

**Lookup không có search scope hay filter:** nó dùng tên chính xác để tra cứu. **Base-object search** cũng chỉ xét một entry, nhưng vẫn có filter. Nếu chỉ cần đọc entry theo DN với Spring LDAP, `lookup` thường là lựa chọn rõ ràng.

Không được suy ra lookup luôn nhanh hơn search ở mọi directory server: hiệu năng còn phụ thuộc network, provider, server, ACL, dữ liệu trả về và cache. Lợi ích trực tiếp của lookup là **diễn đạt chính xác thao tác theo DN**.

## 2. DN, RDN và base context

Một DN gồm các **Relative Distinguished Name (RDN)** được viết từ entry cụ thể tới các entry cha. Với `uid=lan,ou=people,dc=example,dc=org`:

| Phần tên | Vai trò |
| --- | --- |
| `uid=lan` | RDN của entry Lan |
| `ou=people` | RDN của OU chứa Lan |
| `dc=example,dc=org` | Hậu tố tổ chức trong ví dụ |
| `uid=lan,ou=people,dc=example,dc=org` | DN đầy đủ của entry Lan |

Spring LDAP thường cấu hình **base context** trong `ContextSource`, ví dụ:

```text
ContextSource base = dc=example,dc=org
```

Khi đó, các DN truyền vào `LdapTemplate` cho các thao tác trên entry được hiểu là **tương đối với base context**:

```text
DN tương đối đưa vào lookup: uid=lan,ou=people
Base context đã cấu hình:     dc=example,dc=org
DN entry trên LDAP server:    uid=lan,ou=people,dc=example,dc=org
```

Đây là mô hình ghép tên để giải thích vị trí trong cây; khi có dữ liệu động, **không tự nối chuỗi DN**.

| Base của `ContextSource` | DN truyền cho `lookup` để đọc cùng entry Lan |
| --- | --- |
| `dc=example,dc=org` | `uid=lan,ou=people` |
| `ou=people,dc=example,dc=org` | `uid=lan` |
| Base rỗng | `uid=lan,ou=people,dc=example,dc=org` |

Nếu base đã là `dc=example,dc=org` mà truyền thêm cả hậu tố đó vào `lookup`, ứng dụng có thể tra cứu tên tương ứng với **hậu tố bị lặp** và nhận lỗi không tìm thấy.

> **RDN khác DN tương đối:** `uid=lan` là một RDN. Tùy base context, DN tương đối của entry có thể là `uid=lan` hoặc `uid=lan,ou=people`, gồm nhiều RDN.

## 3. Cấu hình ContextSource và LdapTemplate

Trong ứng dụng Spring Boot có Spring LDAP và auto-configuration phù hợp, một cấu hình ví dụ:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Các giá trị `example.org` và tên biến môi trường chỉ dùng minh họa. Trong ứng dụng thật, cần cung cấp URL, DN bind và secret phù hợp; cấu hình CA/truststore để **xác minh chứng chỉ TLS**. Không ghi mật khẩu thật vào mã nguồn, file commit hoặc log.

- `spring.ldap.urls` xác định endpoint kết nối, ví dụ LDAPS.
- `spring.ldap.base` đặt base context, quyết định cách diễn giải các DN tương đối truyền cho template.
- `spring.ldap.username` là DN dùng **bind/xác thực tài khoản dịch vụ**, thường được cấu hình đầy đủ. Nó **không phải** DN của entry mà các thao tác `lookup` muốn đọc.
- `spring.ldap.password` được cấp qua biến môi trường hoặc hệ thống quản lý secret.

Một bean `LdapTemplate` được sử dụng thông qua constructor injection, không cần tự tạo `InitialDirContext` trong service. `LdapTemplate` sử dụng `ContextSource` để lấy JNDI context, thực hiện thao tác và giải phóng tài nguyên theo vòng đời của Spring LDAP.

Ví dụ dưới đây giả định `ContextSource.base = "dc=example,dc=org"` trong toàn bộ các đoạn mã.

## 4. Lookup đơn giản và đọc attribute bằng ContextMapper

Cho entry mẫu:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
displayName: Lan N.
mail: lan@example.org
mail: lan.work@example.org
```

`ContextMapper<T>` cho phép biến JNDI context được `LdapTemplate` cung cấp thành đối tượng Java. Khi mapping entry thư mục, một cách thông dụng là chuyển `context` thành `DirContextOperations` để đọc attribute:

```java
import java.util.Arrays;
import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

record PersonView(
    String uid,
    String commonName,
    String displayName,
    List<String> emails
) {}

public final class PersonDirectory {
    private final LdapTemplate ldapTemplate;

    public PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public PersonView lookupLan() {
        return ldapTemplate.lookup(
            "uid=lan,ou=people",
            (ContextMapper<PersonView>) context -> {
                DirContextOperations entry = (DirContextOperations) context;

                String[] values = entry.getStringAttributes("mail");
                List<String> emails = values == null
                    ? List.of()
                    : Arrays.asList(values);

                return new PersonView(
                    entry.getStringAttribute("uid"),
                    entry.getStringAttribute("cn"),
                    entry.getStringAttribute("displayName"),
                    emails
                );
            }
        );
    }
}
```

Cách đọc đoạn code:

1. `"uid=lan,ou=people"` là **DN tương đối** của entry cần tra cứu.
2. `lookup` chỉ đọc entry tại DN này, không chạy filter `(uid=lan)` trên cả subtree.
3. `ContextMapper<PersonView>` nhận context và ánh xạ dữ liệu vào record.
4. `getStringAttribute("cn")` phù hợp khi ứng dụng chỉ cần một giá trị chuỗi. Nếu attribute thực tế có **nhiều giá trị**, phương thức lấy một chuỗi không phải cách đọc đầy đủ và cũng không xác định “giá trị ưu tiên”.
5. `getStringAttributes("mail")` lấy các giá trị email. Nếu `mail` không có, ví dụ trả một danh sách rỗng; không giả định thuộc tính tùy chọn luôn tồn tại.

Thứ tự các giá trị trong LDAP multi-valued attribute **không được bảo đảm**. Nếu ứng dụng cần “email chính”, hãy dùng quy tắc nghiệp vụ/attribute thích hợp, thay vì mặc nhiên lấy phần tử đầu tiên. Với dữ liệu nhị phân như `jpegPhoto`, không ép về `String`; dùng API/mapper xử lý kiểu `byte[]` tương ứng.

Ví dụ dùng Java 17+ cho `record` và `List.of()`; các ứng dụng Java cũ có thể dùng class DTO và `Collections.emptyList()`.

## 5. Dùng AttributesMapper khi chỉ cần các thuộc tính

`AttributesMapper<T>` là lựa chọn ngắn gọn nếu code chỉ quan tâm đến đối tượng `javax.naming.directory.Attributes`, không cần truy cập thông tin context:

```java
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public final class CommonNameReader {
    private final LdapTemplate ldapTemplate;

    public CommonNameReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String readCommonName() {
        return ldapTemplate.lookup(
            "uid=lan,ou=people",
            (AttributesMapper<String>) attributes -> {
                Attribute cn = attributes.get("cn");
                return cn == null ? null : (String) cn.get();
            }
        );
    }
}
```

So sánh hai kiểu mapper:

| Mapper | Đầu vào callback | Phù hợp khi |
| --- | --- | --- |
| `ContextMapper<T>` | Context của entry, thường được chuyển thành `DirContextOperations` | Cần phương thức tiện ích đọc attribute, thao tác với thông tin context |
| `AttributesMapper<T>` | `Attributes` của JNDI | Chỉ cần đọc một vài attribute và tự ánh xạ |

Hai cách trên đều tra cứu **một entry theo DN**. Không được nhầm `lookup(..., mapper)` với `search(..., mapper)`: lookup nhận một DN, còn search cần phạm vi và filter.

### Thuộc tính vắng mặt và giới hạn schema

Trong các entry thực tế, một số attribute có thể không tồn tại hoặc bị che bởi ACL; hãy kiểm tra null trước khi lấy giá trị. Attribute object class và schema quyết định các thuộc tính được phép chứa, giá trị bao nhiêu và có syntax nào.

Ví dụ, `displayName` là thuộc tính riêng, không phải alias của `cn`. Một ứng dụng có thể chọn `displayName` rồi fallback sang `cn`, nhưng đó là **quy tắc trình bày của ứng dụng**, không phải bước tự động trong `LdapTemplate.lookup`.

## 6. Tạo DN động bằng LdapNameBuilder thay vì ghép chuỗi

Trong code thật, DN thường được tạo từ `uid` do ứng dụng nhận vào. Không nên viết:

```java
String dn = "uid=" + uid + ",ou=people"; // Dễ sai escaping và cấu trúc DN.
```

Giá trị RDN có thể chứa ký tự đặc biệt như dấu phẩy, dấu cộng, dấu gạch chéo ngược hoặc dấu cách ở vị trí cần escape. Ghép chuỗi thô có thể tạo DN sai hoặc khiến một phần dữ liệu đầu vào bị hiểu nhầm là RDN mới.

Spring LDAP cung cấp `LdapNameBuilder` để tạo `Name` có cấu trúc:

```java
import javax.naming.Name;

import org.springframework.ldap.support.LdapNameBuilder;

public static Name relativePersonDn(String uid) {
    return LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("uid", uid)
        .build();
}
```

Với `uid = "lan"`, tên được biểu diễn là `uid=lan,ou=people`. Với `uid = "lan,qa"`, builder xử lý dấu phẩy nằm **trong giá trị** để không bị hiểu thành dấu phân cách hai RDN.

Kết hợp `Name` với `lookup`:

```java
import javax.naming.Name;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

public String readUid(String uid) {
    Name dn = relativePersonDn(uid);
    return ldapTemplate.lookup(
        dn,
        (ContextMapper<String>) context ->
            ((DirContextOperations) context).getStringAttribute("uid")
    );
}
```

Đây là đoạn method minh họa nằm trong một class đã có field `ldapTemplate` và method `relativePersonDn`. Cấu trúc builder thêm từ RDN của nhánh cha `ou=people` rồi thêm RDN con `uid=...`.

**DN escaping và filter escaping là hai quy tắc khác nhau.** Khi dựng DN, dùng `LdapNameBuilder` / `LdapName`. Khi tìm kiếm bằng filter có giá trị đầu vào, dùng `LdapQueryBuilder` hoặc các filter builder như `EqualsFilter`. Không lấy chuỗi đã escape cho filter rồi coi như DN hợp lệ.

## 7. Có DN rồi, lookup có cần filter và search scope không?

Không. Hãy phân biệt hai tình huống:

**Tình huống A – đã biết DN chính xác:** hệ thống đã lưu DN `uid=lan,ou=people,dc=example,dc=org` từ bước trước hoặc đã xác định chính xác DN theo quy ước đặt tên. Sử dụng:

```java
ldapTemplate.lookup("uid=lan,ou=people",
    (ContextMapper<String>) context ->
        ((DirContextOperations) context).getStringAttribute("cn"));
```

**Tình huống B – chỉ biết `uid`:** hệ thống cần tìm người dùng trong một hay nhiều OU, chưa biết DN đầy đủ. Sử dụng `search` với filter:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

List<String> matches = ldapTemplate.search(
    query().base("ou=people").where("uid").is(uid),
    (AttributesMapper<String>) attributes ->
        (String) attributes.get("cn").get()
);
```

Query builder ở B giúp escape giá trị `uid`. Kết quả search có thể có **0, 1 hoặc nhiều entry**; vì `uid` không nhất thiết duy nhất trên mọi nhánh, không tự chọn kết quả đầu tiên khi nghiệp vụ đòi hỏi một người duy nhất.

Nếu tài khoản được chuyển từ `ou=people` sang `ou=staff`, **DN đã thay đổi**. Lookup theo DN cũ sẽ không tìm thấy dù entry vẫn tồn tại ở nơi khác. Với ứng dụng lưu DN như tham chiếu dài hạn, cần thiết kế cách cập nhật khi rename/move entry hoặc xác định lại DN theo khóa nghiệp vụ thích hợp.

### So sánh với lệnh ldapsearch

Một câu lệnh để kiểm tra entry có DN đã biết (hostname, DN và tài khoản chỉ là ví dụ):

```bash
ldapsearch -x -LLL -H ldaps://ldap.example.org:636 \
  -D "cn=app-reader,ou=service,dc=example,dc=org" -W \
  -b "uid=lan,ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" dn uid cn displayName mail
```

`-s base` chỉ tìm tại chính entry được đặt ở `-b`. Bộ lọc `(objectClass=*)` là điều kiện hiện diện; với một entry thông thường có `objectClass`, kết quả có thể tương ứng với entry mà lookup đọc. **Lưu ý:** đây là base-object search có filter, không phải phương thức `lookup`; chúng khác nhau về thao tác/cách dùng API.

Khác biệt cấu hình đáng chú ý: `ldapsearch -b` ở đây nhận **DN đầy đủ**, còn `LdapTemplate.lookup` dùng **DN tương đối** nếu `ContextSource` đã có base. So sánh DN và quyền bind khi đối chiếu kết quả giữa công cụ và Spring LDAP.

## 8. Xử lý không tìm thấy, lỗi quyền và lỗi kết nối

Lookup bằng DN cần được thiết kế cho những trạng thái khác nhau:

| Tình huống | Ý nghĩa | Cách ứng dụng nên xử lý |
| --- | --- | --- |
| DN tồn tại và được đọc thành công | Đọc đúng entry | Map sang DTO, trả dữ liệu |
| DN không tồn tại | Không thể tìm entry tại tên được cung cấp | Tách thành “không tìm thấy”, kiểm tra DN/base khi cần |
| DN sai hoặc hậu tố base bị lặp | Đang tra tên không đúng | Sửa cách tính DN tương đối, không sửa filter |
| Tài khoản bind thiếu quyền | Server không cho thao tác hoặc che entry/attribute | Kiểm tra ACL và chính sách quyền |
| Kết nối, TLS hoặc bind thất bại | Chưa thực hiện lookup như kỳ vọng | Báo lỗi hạ tầng, retry có kiểm soát nếu phù hợp |
| Attribute bắt buộc trong ứng dụng bị thiếu | Mapping không thỏa hợp đồng dữ liệu | Xử lý/null validation hoặc lỗi dữ liệu theo schema |

Trong Spring LDAP, lỗi JNDI được chuyển sang nhóm exception truy cập dữ liệu LDAP của Spring. Một lookup vào tên không tồn tại thường dẫn tới `NameNotFoundException` tương ứng; code adapter có thể bắt **đúng trường hợp không tìm thấy** và chuyển thành `Optional.empty()` theo hợp đồng nghiệp vụ. Tên/lớp exception cụ thể cần đối chiếu theo phiên bản Spring LDAP trong dự án.

**Không biến mọi lỗi thành “không tìm thấy”.** Nếu dùng:

```java
// Cách xử lý sai về mặt nghiệp vụ:
try {
    return readUserByDn();
} catch (Exception ex) {
    return null;
}
```

thì mất kết nối LDAP, lỗi TLS và thiếu quyền sẽ bị che thành dữ liệu vắng mặt. Thay vào đó, adapter chỉ chuyển đổi các loại lỗi có ý nghĩa nghiệp vụ rõ ràng; những lỗi hạ tầng khác phải được báo cáo/giám sát và xử lý phù hợp.

Một điểm tinh tế: trong một số server, ACL có thể khiến entry không quan sát được như khi không tồn tại. Do đó, **kết luận “entry không tồn tại thật” chỉ dựa trên một lookup thất bại với tài khoản bị giới hạn quyền là không chắc chắn**. Khi chẩn đoán, sử dụng công cụ truy vấn với tài khoản được phép, nhưng không mở quyền vô tội vạ cho ứng dụng production.

## 9. Kiểm thử lookup theo DN

Một kiểm thử tích hợp với LDAP thử nghiệm (embedded LDAP hoặc server riêng có schema phù hợp) nên tạo dữ liệu giả:

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
mail: lan@example.org
mail: lan.work@example.org
```

Các trường hợp cần xác minh:

1. **Đúng DN:** `lookup("uid=lan,ou=people", mapper)` đọc được `uid=lan` khi `ContextSource.base = "dc=example,dc=org"`.
2. **Sai DN:** `lookup("uid=unknown,ou=people", mapper)` không trả người dùng khác; adapter nhận biết tình huống không tìm thấy.
3. **Sai base context:** không lặp hậu tố `dc=example,dc=org` khi ứng dụng đã cấu hình base.
4. **Escaping:** `uid` có dấu phẩy, dấu cộng hoặc ký tự đặc biệt được build thành DN đúng và không làm thay đổi các RDN dự kiến.
5. **Multi-valued:** hai giá trị `mail` đều được đọc và ánh xạ, không giả định thứ tự.
6. **Thuộc tính tùy chọn:** vắng `displayName`/`mail` không gây lỗi null ngoài ý muốn.
7. **Phân quyền:** tài khoản bind thiếu quyền sẽ được báo hoặc có kết quả theo ACL server, không bị xử lý như một truy vấn thành công giả.
8. **Kết nối/TLS:** lỗi server unavailable hoặc chứng chỉ không hợp lệ được báo như lỗi hạ tầng.

Khi test dữ liệu LDAP, phải bảo đảm entry cha tồn tại và schema cho phép object class/attribute. Unit test mapper bằng mock có thể kiểm tra quy tắc Java, nhưng **chỉ kiểm thử tích hợp** mới xác nhận tương tác với directory server, base DN, TLS và ACL thật.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `lookup` cần filter `(uid=lan)` | Lookup tra cứu bằng **DN đã biết**, không dùng search filter |
| Cứ có `uid` là suy ra DN đầy đủ của người dùng | Còn phải biết nhánh OU, base và quy ước đặt tên hiện tại |
| `uid=lan` luôn là DN tương đối đúng | Chỉ đúng nếu base context đã chỉ tới chính OU chứa người dùng |
| Dùng DN đầy đủ với `LdapTemplate` dù đã có base | Có thể lặp hậu tố và tìm sai tên |
| `lookup("uid=lan,ou=people")` cũng tìm người ở OU contractors bên dưới | Lookup chỉ tại DN đó; không tự duyệt các nhánh khác |
| Nối `"uid=" + uid + ",ou=people"` là đủ an toàn | Giá trị động cần escaping; dùng `LdapNameBuilder` |
| `getStringAttribute("mail")` luôn lấy email chính | LDAP không đảm bảo thứ tự của multi-valued attribute |
| Mọi lookup thất bại đều có nghĩa người dùng không tồn tại | Cần phân biệt DN sai, ACL, TLS, bind và lỗi kết nối |
| Đã gọi `lookup` thì không cần cấu hình TLS | Tra cứu LDAP vẫn có thể mang dữ liệu/tài khoản nhạy cảm |
| Một `LdapTemplate` singleton phải dùng chung một `DirContext` | Template quản lý context theo thao tác/wrapper, không phải một session global đơn lẻ |

## 11. Bài tập tự kiểm tra

Giả sử LDAP server chứa:

```text
dc=example,dc=org
└── ou=people
    ├── uid=lan
    ├── uid=minh
    └── ou=contractors
        └── uid=an
```

Ứng dụng cấu hình `ContextSource.base = "dc=example,dc=org"` và có quyền đọc các entry.

**Câu hỏi:**

1. Cần truyền DN nào cho `lookup` để đọc entry Lan?
2. `lookup("uid=an,ou=people", ...)` có tìm được An không? Vì sao?
3. Nếu chuyển base context thành `ou=people,dc=example,dc=org`, DN tương đối của Lan thay đổi ra sao?
4. Vì sao `LdapNameBuilder` an toàn hơn nối chuỗi khi `uid` có giá trị `lan,qa`?
5. Khi `mail` có hai giá trị, phương thức nào phù hợp hơn để đọc đầy đủ?
6. Tính năng chỉ nhận `uid=lan` và không biết OU; nên dùng lookup hay search trước?
7. Lỗi mất kết nối LDAP có được đổi thành `Optional.empty()` không?

**Đáp án giải thích:**

1. `uid=lan,ou=people`. Phần `dc=example,dc=org` đã nằm trong base context.
2. Không, vì An có DN `uid=an,ou=contractors,ou=people,dc=example,dc=org`. Lookup không tự tìm xuyên qua OU con.
3. Còn `uid=lan`, vì base mới đã bao gồm `ou=people`.
4. Builder xem dấu phẩy là dữ liệu của giá trị thuộc tính và escape đúng theo quy tắc DN, không biến nó thành RDN khác.
5. `getStringAttributes("mail")` để đọc mọi value; đừng dựa vào giá trị đầu tiên như email chính.
6. Dùng search với filter `(uid=lan)` trong phạm vi phù hợp để xác định entry/DN; lookup chỉ dùng khi biết tên entry chính xác.
7. Không. Lỗi kết nối không chứng minh entry không tồn tại; phải báo sự cố hạ tầng và áp dụng chính sách xử lý phù hợp.

## 12. Tổng kết và tài liệu tham khảo

`LdapTemplate.lookup(...)` dùng khi ứng dụng **biết DN của entry** và cần đọc entry đó. Nếu `ContextSource` đã có base DN, hãy truyền **DN tương đối** phù hợp. Sử dụng `ContextMapper` hoặc `AttributesMapper` để ánh xạ giá trị, xây DN động bằng `LdapNameBuilder` và bảo toàn dữ liệu multi-valued.

Lookup khác search: lookup không dùng filter hoặc scope, còn search tìm entry theo base/scope/filter khi chưa biết DN chính xác. Trong hệ thống thật, cần nhận diện không tìm thấy, DN sai, ACL và lỗi kết nối/TLS; đồng thời giữ tài khoản bind có quyền tối thiểu và kiểm thử trên directory đại diện.

Tài liệu tham khảo:

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): sử dụng `ContextSource`, `LdapTemplate`, lookup, mapping và query API.
- [Spring LDAP LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): các overload của `lookup` và thao tác directory.
- [Spring LDAP LdapNameBuilder API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapNameBuilder.html): xây DN/RDN có cấu trúc.
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cách biểu diễn và escape DN.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): định danh entry, tìm kiếm và lỗi LDAP.
