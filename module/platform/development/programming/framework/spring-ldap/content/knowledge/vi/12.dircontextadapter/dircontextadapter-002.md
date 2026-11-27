# getStringAttribute và đọc giá trị đơn với DirContextAdapter

Khi tìm được một entry LDAP, ứng dụng Java thường cần chuyển thuộc tính như `uid`, `cn`, `mail` thành các trường `String` trong DTO. Spring LDAP cung cấp `DirContextAdapter` và interface `DirContextOperations` để giảm thao tác trực tiếp với JNDI `Attributes`. Một trong các phương thức tiện dụng nhất là **`getStringAttribute("attributeName")`**.

Tuy nhiên, việc đọc được một chuỗi **không có nghĩa** thuộc tính đó chắc chắn chỉ có một giá trị, cũng không có nghĩa mọi entry đều phải trả thuộc tính ấy. LDAP cho phép thuộc tính đa trị, áp dụng schema và ACL, còn từng lệnh search có thể giới hạn danh sách thuộc tính trả về. Bài này giúp sử dụng `getStringAttribute` đúng phạm vi, tránh mất dữ liệu hoặc lỗi `null` khi mapping.

Bài thuộc chương **DirContextAdapter** của SPRING_LDAP. Ta sẽ đi từ cấu trúc entry, cách đọc với `LdapTemplate.lookupContext(...)` và `ContextMapper`, tới việc xử lý thuộc tính đơn trị, đa trị, giá trị thiếu, DN và kiểm thử an toàn. Các quy tắc về schema, filter, xác thực và giới hạn truy vấn cũng áp dụng khi ứng dụng dùng `LdapClient` hoặc ODM.

## 1. Bối cảnh: entry LDAP không phải một Java bean có trường cố định

Giả sử LDAP server có cây:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   ├── uid=binh
│   └── ou=contractors
│       └── uid=chi
└── ou=groups
    └── cn=developers
~~~

Một entry nhân viên có thể được thể hiện bằng LDIF:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
displayName: Nguyễn Văn An
mail: an@example.org
telephoneNumber: +84 28 1234 5678
~~~

Các thành phần cần phân biệt:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **DN** | `uid=an,ou=people,dc=example,dc=org` | Tên định vị entry trong cây |
| **RDN** | `uid=an` | Thành phần tên phân biệt entry với các entry cùng cha |
| **Attribute name** | `cn`, `mail` | Loại thuộc tính do schema định nghĩa |
| **Attribute value** | `Nguyen Van An` | Giá trị thuộc tính, có thể đơn trị hoặc đa trị |
| **objectClass** | `inetOrgPerson`, `person` | Quy định các thuộc tính bắt buộc/được phép |

Với schema chuẩn phổ biến, `person` yêu cầu `cn` và `sn`; `inetOrgPerson` kế thừa ràng buộc này. Nhưng việc một thuộc tính là **MUST** không bảo đảm ứng dụng luôn nhìn thấy nó trong mọi kết quả tìm kiếm: ACL hoặc danh sách thuộc tính được yêu cầu có thể giới hạn response.

Một thuộc tính như `mail` có thể vắng mặt. Một số thuộc tính như `objectClass` và `member` thường có **nhiều giá trị**. Không được mặc định cấu trúc LDAP luôn giống một bản ghi SQL với mỗi cột chỉ chứa một chuỗi.

## 2. `DirContextAdapter` và `DirContextOperations` có vai trò gì?

JNDI biểu diễn tập thuộc tính của một entry qua `javax.naming.directory.Attributes` và từng thuộc tính qua `Attribute`. Ví dụ khi làm việc thuần JNDI, code có thể phải truy vấn một `DirContext`, kiểm tra `Attributes.get(...)`, rồi lấy và ép kiểu giá trị.

Spring LDAP đưa thêm lớp trừu tượng:

- **`DirContextOperations`**: interface cung cấp các thao tác thuận tiện để đọc/sửa thuộc tính và truy cập thông tin ngữ cảnh entry.
- **`DirContextAdapter`**: một triển khai thường dùng của interface này. Nó có thể được tạo mới để chuẩn bị dữ liệu entry hoặc được Spring LDAP cung cấp khi mapping kết quả đọc.
- **`LdapTemplate`**: lấy context từ `ContextSource`, gọi thao tác LDAP và chuyển dữ liệu kết quả cho adapter/mapper.
- **`ContextMapper<T>`**: chuyển ngữ cảnh entry thành DTO khi cần cả thuộc tính lẫn thông tin DN.

~~~mermaid
flowchart TD
    A["Service Java"] --> B["LdapTemplate"]
    B --> C["ContextSource / JNDI"]
    C --> D[("LDAP server")]
    D --> E["Entry + Attributes"]
    E --> F["DirContextAdapter / DirContextOperations"]
    F --> G["getStringAttribute"]
    F --> H["getStringAttributes"]
    F --> I["getDn"]
    G --> J["DTO / nghiệp vụ"]
    H --> J
    I --> J
~~~

Adapter **không thay thế LDAP schema** và không tạo ra quyền đọc thuộc tính bị server từ chối. Nó chỉ hỗ trợ thao tác với dữ liệu/entry mà JNDI và Spring LDAP đã nhận được.

## 3. `getStringAttribute(...)` đọc gì?

Cú pháp cơ bản:

~~~java
String name = entry.getStringAttribute("cn");
String email = entry.getStringAttribute("mail");
~~~

Trong đó `entry` là một `DirContextOperations` hoặc `DirContextAdapter` có dữ liệu của LDAP entry.

**Ý nghĩa:** yêu cầu adapter cung cấp **một giá trị dạng `String`** của thuộc tính có tên xác định. Phương thức này phù hợp khi contract của ứng dụng mong đợi một giá trị chuỗi và thuộc tính thực tế được biểu diễn như vậy.

| Tình huống | Cách xử lý |
| --- | --- |
| Thuộc tính có một giá trị chuỗi | Đọc bằng `getStringAttribute("cn")` |
| Thuộc tính không có trong dữ liệu trả về | Có thể nhận `null`; cần chính sách fallback hoặc báo thiếu |
| Thuộc tính có nhiều giá trị | Không coi một `String` là toàn bộ dữ liệu; dùng `getStringAttributes(...)` |
| Thuộc tính có dữ liệu nhị phân | Không ép thành text; sử dụng API đọc đúng kiểu dữ liệu |
| Thuộc tính bị thiếu trong projection/ACL | Không vội kết luận entry không có dữ liệu trên server |

Ví dụ đoạn mapping có xử lý email tùy chọn:

~~~java
String cn = entry.getStringAttribute("cn");
String mail = entry.getStringAttribute("mail");

String emailToDisplay = mail == null
        ? "(chưa có email)"
        : mail;
~~~

Việc dùng một placeholder hiển thị chỉ phù hợp ở **tầng giao diện**. Không nên ghi lại chuỗi `"(chưa có email)"` vào LDAP như email thật.

### Phương thức không tự kiểm chứng nghiệp vụ

Gọi `getStringAttribute("mail")` không tự kiểm tra đây có phải địa chỉ email hợp lệ, đã xác minh hay được phép hiển thị. Tương tự, nó không tự chuẩn hóa Unicode, không kiểm tra tính duy nhất của `uid` và không phân biệt account đang hoạt động hay bị khóa. Đó là trách nhiệm schema, LDAP server và quy tắc nghiệp vụ của ứng dụng.

## 4. Đọc một entry theo DN với `lookupContext(...)`

Giả sử `LdapContextSource` cấu hình base `dc=example,dc=org`. DN tương đối của An trong ứng dụng là `uid=an,ou=people`.

Ví dụ:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonLookupService {
    private final LdapTemplate ldapTemplate;

    public PersonLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String findDisplayName(String uid) {
        if (uid == null || uid.isBlank() || uid.length() > 64) {
            throw new IllegalArgumentException("Invalid uid");
        }

        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        DirContextOperations entry = ldapTemplate.lookupContext(relativeDn);

        String displayName = entry.getStringAttribute("displayName");
        if (displayName != null && !displayName.isBlank()) {
            return displayName;
        }

        String cn = entry.getStringAttribute("cn");
        if (cn == null || cn.isBlank()) {
            throw new IllegalStateException(
                    "Directory entry has no readable common name");
        }
        return cn;
    }
}
~~~

**Luồng thực thi:** `LdapTemplate` dùng `ContextSource` để truy cập entry tại DN tương đối, tạo/lấy ngữ cảnh kết quả rồi cung cấp `DirContextOperations`. Service không cần tự mở và đóng JNDI `DirContext` cho mỗi lần lookup.

Điểm cần lưu ý:

1. `LdapNameBuilder` dùng để dựng **DN/RDN**, tránh sai cú pháp khi giá trị UID chứa ký tự đặc biệt.
2. `lookupContext(relativeDn)` đọc entry theo DN đã biết, không phải tìm bằng filter; nếu DN không tồn tại, có thể phát sinh exception như `NameNotFoundException`.
3. `displayName` có thể vắng mặt nên sử dụng fallback sang `cn`.
4. Ví dụ giả định ứng dụng được phép đọc `cn`; nếu ACL che thuộc tính này, cần xử lý theo chính sách rõ ràng.
5. Đường truyền phải được bảo vệ bằng LDAPS hoặc StartTLS đã kiểm tra chứng chỉ và bind account có ACL cần thiết.

**Không ghép full DN vào DN tương đối:** nếu `ContextSource.base` đã là `dc=example,dc=org`, giá trị `uid=an,ou=people` mới là phần tương đối. Truyền `uid=an,ou=people,dc=example,dc=org` cho API đang dùng base tương đối có thể khiến suffix bị lặp.

## 5. Đọc thuộc tính khi `search(...)` trả nhiều entry

Khi chưa biết DN đầy đủ, ứng dụng thường tìm kiếm theo filter. Với `LdapTemplate.search(...)` và `ContextMapper<T>`, đối tượng context của từng kết quả có thể được truy cập dưới dạng `DirContextOperations`.

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

record EmployeeView(String dn, String uid, String name, String email) {}

public class EmployeeSearchService {
    private final LdapTemplate ldapTemplate;

    public EmployeeSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<EmployeeView> findByUid(String userInput) {
        if (userInput == null || userInput.isBlank()
                || userInput.length() > 128) {
            throw new IllegalArgumentException("Invalid uid");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchControls.SUBTREE_SCOPE)
                .attributes("uid", "cn", "displayName", "mail")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(userInput);

        return ldapTemplate.search(
                query,
                (ContextMapper<EmployeeView>) context -> {
                    DirContextOperations entry =
                            (DirContextOperations) context;

                    String display = entry.getStringAttribute("displayName");
                    String name = display != null && !display.isBlank()
                            ? display
                            : entry.getStringAttribute("cn");

                    return new EmployeeView(
                            entry.getDn().toString(),
                            entry.getStringAttribute("uid"),
                            name,
                            entry.getStringAttribute("mail"));
                });
    }
}
~~~

Trong ví dụ:

- `.base("ou=people")` là search base tương đối với base của `ContextSource`.
- `SUBTREE_SCOPE` cho phép tìm cả nhân viên trong các OU lồng nhau.
- `.where("objectClass").is(...)` và `.and("uid").is(userInput)` tạo filter từ cấu trúc do code kiểm soát; builder xử lý escaping cho giá trị UID.
- `.attributes(...)` yêu cầu những thuộc tính cần để mapping, giảm lượng dữ liệu chuyển về.
- `ContextMapper` thích hợp vì DTO cần **cả DN lẫn thuộc tính**. `entry.getDn()` cần được diễn giải theo base của Spring LDAP, không mặc định là full DN cho mọi API.
- `getStringAttribute(...)` được gọi riêng cho từng entry. Một kết quả tìm kiếm có thể thiếu `mail`, ngay cả khi entry khác có.

Lời gọi search có thể trả về **0, 1 hoặc nhiều entry**. Nếu yêu cầu nghiệp vụ đòi hỏi duy nhất một người dùng, phải quy định cách xử lý nhiều kết quả theo chính sách dữ liệu; đừng tự động lấy phần tử đầu tiên để bỏ qua vấn đề trùng UID trong các OU.

## 6. Chọn `AttributesMapper` hay `ContextMapper`?

Khi chỉ cần thuộc tính và không cần DN, `AttributesMapper` thường gọn hơn. Nó nhận `javax.naming.directory.Attributes` trực tiếp, nhưng **không nhận `DirContextOperations`**.

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public List<String> findCommonNames(LdapTemplate template) {
    LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")
            .where("objectClass").is("inetOrgPerson");

    return template.search(
            query,
            (AttributesMapper<String>) attrs ->
                    attrs.get("cn") == null
                            ? null
                            : (String) attrs.get("cn").get());
}
~~~

Không thể gọi `attrs.getStringAttribute("cn")` trong ví dụ này: `Attributes` là API của JNDI, không có phương thức tiện ích đó. Với `AttributesMapper`, phải dùng `attrs.get("cn")` và kiểm tra `null` trước khi lấy giá trị.

| Tiêu chí | `AttributesMapper` | `ContextMapper` |
| --- | --- | --- |
| Đầu vào | `Attributes` | Context của entry, thường là `DirContextOperations` |
| Có `getStringAttribute(...)`? | Không | Có |
| Phù hợp DTO chỉ cần thuộc tính | Có | Có |
| Dễ lấy DN qua mapper | Không trực tiếp | Có, qua `getDn()` |
| Xử lý optional attribute | Kiểm tra `attrs.get(...)` | Kiểm tra kết quả của `getStringAttribute(...)` |
| Xử lý đa trị | Duyệt `Attribute`/`getAll()` | Có thể dùng `getStringAttributes(...)` |

Một API khác, `NameClassPairMapper`, thường được dùng với `LdapTemplate.list(...)` để ánh xạ **tên binding con trực tiếp**, không phải để đọc `cn` hay `mail` trong kết quả search. `NameClassPair.getClassName()` là tên class Java/JNDI, **không phải** `objectClass` của LDAP entry.

## 7. Thuộc tính đơn trị và đa trị: chỗ dễ dùng sai nhất

Một thuộc tính có thể chứa **một hoặc nhiều giá trị** tùy schema và dữ liệu. Câu hỏi “chỉ lấy một `String` được không?” khác câu hỏi “schema có bảo đảm tối đa một giá trị không?”.

| Attribute minh họa | Tình huống thường gặp | Hướng đọc |
| --- | --- | --- |
| `displayName` | Một tên hiển thị theo hợp đồng ứng dụng | `getStringAttribute("displayName")` khi đã chấp nhận một giá trị |
| `uid` | Một UID trên entry trong hệ thống ví dụ | Có thể dùng `getStringAttribute` nhưng phải kiểm tra uniqueness/multi-value theo schema và nghiệp vụ |
| `cn` | Có thể có nhiều tên/cách gọi | Không mặc nhiên có đúng một giá trị; cần quyết định giá trị dùng để hiển thị |
| `mail` | Có thể không có hoặc có nhiều địa chỉ trong một số directory | Chọn quy tắc rõ ràng, không tùy tiện bỏ giá trị |
| `telephoneNumber` | Có thể có nhiều số | Đọc thành mảng/danh sách nếu ứng dụng cần đầy đủ |
| `objectClass` | Thường có nhiều giá trị như `top`, `person`, `inetOrgPerson` | Đọc toàn bộ tập, không chỉ một giá trị |
| `member` của nhóm | Nhiều DN thành viên | Đọc toàn bộ danh sách DN |

**`getStringAttribute` không phải bộ xác nhận single-valued schema.** Ngay cả khi nó cung cấp một chuỗi, ứng dụng vẫn phải biết liệu các giá trị còn lại có bị bỏ qua hay không. Đối với thuộc tính có khả năng đa trị, sử dụng `getStringAttributes(attributeName)` hoặc API đọc `Attribute` đa trị.

### `getStringAttributes(...)` để không bỏ sót giá trị

~~~java
DirContextOperations entry = ldapTemplate.lookupContext(relativeDn);

String[] phones = entry.getStringAttributes("telephoneNumber");
if (phones == null || phones.length == 0) {
    System.out.println("Entry không có số điện thoại được đọc");
} else {
    for (String phone : phones) {
        System.out.println(phone);
    }
}
~~~

Ví dụ chỉ minh họa cách xử lý mảng. **Thứ tự các giá trị LDAP của một thuộc tính đa trị thông thường không mang ý nghĩa sắp xếp.** Không dùng phần tử `[0]` làm “số chính” nếu directory không có quy ước rõ ràng.

### Kiểm tra đúng một giá trị khi nghiệp vụ bắt buộc

Nếu hệ thống có quy tắc “mỗi nhân viên phải có đúng một `uid` nhìn thấy được”, hãy kiểm tra số lượng thay vì lấy đại một giá trị:

~~~java
import org.springframework.ldap.core.DirContextOperations;

public static String requireOneString(
        DirContextOperations entry, String attributeName) {

    String[] values = entry.getStringAttributes(attributeName);

    if (values == null || values.length != 1) {
        throw new IllegalStateException(
                "Expected exactly one readable value for " + attributeName);
    }
    return values[0];
}
~~~

Hàm này dùng cho attribute đã được **ứng dụng lựa chọn và tin cậy**; không đưa tên attribute tùy ý của client vào thông báo lỗi hoặc logic. Với dữ liệu thật, lỗi nên được chuyển thành trạng thái nghiệp vụ thích hợp, tránh trả nguyên thông tin cấu trúc LDAP ra API công khai.

Cần phân biệt ba cấp độ bảo đảm:

1. **Schema:** attribute type có được khai báo `SINGLE-VALUE` hay không.
2. **Dữ liệu và ACL:** server thực sự có bao nhiêu giá trị và client được đọc bao nhiêu.
3. **Nghiệp vụ:** ứng dụng mong muốn bao nhiêu giá trị, và nếu có nhiều thì chọn theo quy tắc nào.

Không dùng một lời gọi `getStringAttribute` để thay cả ba cấp độ này.

## 8. Dữ liệu vắng mặt, rỗng và không được phép đọc

Một kết quả `null` từ `getStringAttribute("mail")` có thể xảy ra khi:

- Entry thật sự không chứa attribute `mail`.
- Query chỉ yêu cầu các attribute khác qua projection, chẳng hạn `.attributes("uid", "cn")`.
- LDAP ACL ngăn tài khoản bind xem giá trị.
- Cơ chế truy cập/provider hoặc cách mapping không cung cấp dữ liệu như mong đợi.

Do đó cần phân biệt:

| Trạng thái | Có thể suy ra từ một `null`? |
| --- | --- |
| Không có giá trị trong object được mapper nhìn thấy | **Có**, trong phạm vi dữ liệu hiện tại |
| Entry trên server chắc chắn không có attribute | **Không** |
| Tài khoản bind chắc chắn không có quyền đọc | **Không** |
| Phép search chắc chắn thất bại | **Không**, nếu entry vẫn được trả về |
| Có thể dùng `null` để hiển thị “chưa cung cấp” | Có, nếu hợp đồng UI chấp nhận cách diễn giải đó |

Một chuỗi rỗng `""` (nếu API trả như vậy) không phải cùng một giá trị Java với `null`. Trong LDAP, quy tắc về độ dài, cú pháp và giá trị rỗng phụ thuộc attribute type/server; không tự suy luận từ Java rằng một attribute rỗng hợp lệ. Ở tầng UI, nên thống nhất chính sách cho `null` và blank thay vì `trim()` mọi dữ liệu rồi thay đổi giá trị gốc.

### Khi cần trường bắt buộc của DTO

Nếu DTO bắt buộc có tên để hiển thị, code nên từ chối dữ liệu thiếu theo cách có kiểm soát:

~~~java
String cn = entry.getStringAttribute("cn");
if (cn == null || cn.isBlank()) {
    throw new IllegalStateException("Readable cn is required");
}
~~~

Thông báo lỗi nghiệp vụ nên ngắn gọn và không chứa password, toàn bộ entry hay các thuộc tính nhạy cảm. Khi điều tra nội bộ, ghi lại ngữ cảnh an toàn như operation, base/scope và mã lỗi LDAP nếu có.

## 9. Ký tự và kiểu dữ liệu: không phải attribute nào cũng là String

LDAP attribute có syntax riêng. Một vài giá trị thường được biểu diễn ở phía Java dưới dạng `String` (chẳng hạn `cn`, `uid`, `mail`), nhưng có những dữ liệu nhị phân như ảnh, chứng chỉ hoặc giá trị không nên tự biến thành text.

Ví dụ:

| Attribute hoặc loại dữ liệu | Cách tiếp cận |
| --- | --- |
| `cn`, `sn`, `mail` | Dùng cách đọc chuỗi khi schema/provider biểu diễn dưới dạng String |
| `member` chứa DN | Có thể đọc chuỗi, sau đó parse như DN khi cần thao tác tên |
| `objectClass` đa trị | Dùng API nhiều giá trị |
| `jpegPhoto` | Dùng API đọc giá trị binary như `byte[]`; không dùng `getStringAttribute` để giả định UTF-8 |
| `userCertificate` | Xử lý theo syntax binary/chứng chỉ và chính sách an toàn |

Nếu cần đọc dữ liệu thô, JNDI `Attributes` và `Attribute` cho phép lấy object có kiểu thật. Ví dụ trong `AttributesMapper`:

~~~java
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

public static byte[] readJpegPhoto(Attributes attributes)
        throws javax.naming.NamingException {

    Attribute attribute = attributes.get("jpegPhoto");
    if (attribute == null) {
        return null;
    }

    Object value = attribute.get();
    if (!(value instanceof byte[] bytes)) {
        throw new IllegalStateException("jpegPhoto is not binary");
    }
    return bytes;
}
~~~

Ví dụ yêu cầu Java hỗ trợ pattern matching cho `instanceof` (Java 16+), và cố ý tập trung một giá trị ảnh. Trong directory thật, cần xét đa trị/giới hạn kích thước và phân quyền trước khi gửi dữ liệu nhị phân qua HTTP.

**Không gọi `new String(bytes)` theo charset mặc định** để biến chứng chỉ/ảnh thành giá trị của trường text. Việc mapping phải đi theo syntax LDAP và loại dữ liệu ứng dụng mong muốn.

## 10. DN, filter và single-value mapping là ba trách nhiệm khác nhau

Trong Spring LDAP, một thao tác tra cứu thường trải qua:

~~~text
Tạo DN hoặc query
       ↓
ContextSource chọn server và danh tính bind
       ↓
LDAP server kiểm tra base, filter, schema, ACL
       ↓
LdapTemplate cung cấp kết quả/context
       ↓
DirContextOperations.getStringAttribute("cn")
       ↓
DTO hoặc logic nghiệp vụ
~~~

Một số nguyên tắc:

- **DN:** khi tạo tên entry động, dùng `LdapNameBuilder`. `uid=an,ou=people` là DN tương đối với base `dc=example,dc=org` trong ví dụ.
- **Filter:** khi tìm theo input, dùng `LdapQueryBuilder.where("uid").is(userInput)` để bảo toàn giá trị literal và tránh LDAP filter injection. Escaping của filter theo RFC 4515 khác escaping DN.
- **Mapping:** `getStringAttribute("cn")` chỉ đọc dữ liệu mà query/lookup đã nhận được. Nó không sửa filter, không tăng search scope và không tăng quyền.
- **Xác thực:** bind DN/password của `ContextSource` dùng để truy cập LDAP; khác với method `LdapTemplate.bind(...)` tạo entry. Mapping chuỗi không chứng minh mật khẩu người dùng đúng.
- **Bảo mật:** LDAPS hoặc StartTLS cần xác minh chứng chỉ, tài khoản dịch vụ cần ACL tối thiểu, và secret không được ghi log.

Đặc biệt, **đọc một trường đơn trị không đồng nghĩa query trả một entry duy nhất**. Số lượng *entry* và số lượng *giá trị trong một attribute* là hai trục khác nhau:

| Trục | Câu hỏi cần trả lời |
| --- | --- |
| Số entry khớp search | 0, 1 hay nhiều entry? |
| Số giá trị của `cn` ở mỗi entry | 0, 1 hay nhiều giá trị? |
| Số thuộc tính được trả về | Projection và ACL cho thấy những attribute nào? |
| Kiểu dữ liệu của mỗi attribute | String, byte array hay dạng khác? |

## 11. Thiết kế mapper an toàn và có thể kiểm thử

Một cách tốt là gom logic mapping vào một hàm nhận `DirContextOperations`, để có thể unit test mà không kết nối LDAP server.

~~~java
import org.springframework.ldap.core.DirContextOperations;

public record PersonCard(
        String uid,
        String name,
        String email,
        String relativeDn) {}

public final class PersonCardMapper {

    private PersonCardMapper() {}

    public static PersonCard map(DirContextOperations entry) {
        String uid = requireOne(entry, "uid");
        String cn = entry.getStringAttribute("cn");

        if (cn == null || cn.isBlank()) {
            throw new IllegalStateException("Readable cn is required");
        }

        String displayName = entry.getStringAttribute("displayName");
        String name = displayName != null && !displayName.isBlank()
                ? displayName
                : cn;

        return new PersonCard(
                uid,
                name,
                entry.getStringAttribute("mail"),
                entry.getDn().toString());
    }

    private static String requireOne(
            DirContextOperations entry, String attributeName) {

        String[] values = entry.getStringAttributes(attributeName);
        if (values == null || values.length != 1) {
            throw new IllegalStateException(
                    "Expected one value for " + attributeName);
        }
        return values[0];
    }
}
~~~

Ví dụ này chỉ phù hợp nếu nghiệp vụ yêu cầu đúng một UID và schema/dữ liệu trả về có `uid`. Khi muốn giữ nhiều email, DTO phải sử dụng `List<String>` hoặc `String[]` thay cho `String`.

Dùng cùng mapper với `ContextMapper`:

~~~java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<PersonCard> mapper = context ->
        PersonCardMapper.map((DirContextOperations) context);

// ldapTemplate.search(query, mapper);
~~~

Nếu cần mapping phức tạp qua nhiều entity, ODM cũng là lựa chọn đáng xem xét; tuy nhiên quy tắc xử lý null, đa trị và schema vẫn phải được thiết kế rõ.

## 12. Kiểm thử `getStringAttribute` với JUnit

Có thể tạo `DirContextAdapter` trong bộ nhớ để kiểm tra logic đọc thuộc tính, không cần kết nối LDAP:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;

class DirContextAdapterReadTest {

    @Test
    void readsSingleStringAttribute() {
        DirContextAdapter entry = new DirContextAdapter();
        entry.setAttributeValue("cn", "Nguyen Van An");

        assertEquals("Nguyen Van An", entry.getStringAttribute("cn"));
    }

    @Test
    void missingOptionalAttributeIsNull() {
        DirContextAdapter entry = new DirContextAdapter();
        entry.setAttributeValue("cn", "Nguyen Van An");

        assertNull(entry.getStringAttribute("mail"));
    }

    @Test
    void readsAllValuesOfMultivaluedAttribute() {
        DirContextAdapter entry = new DirContextAdapter();
        entry.setAttributeValues("telephoneNumber", new String[] {
                "+84 28 1111", "+84 28 2222"
        });

        String[] phones = entry.getStringAttributes("telephoneNumber");
        assertEquals(2, phones.length);
        assertTrue(Arrays.asList(phones).contains("+84 28 1111"));
        assertTrue(Arrays.asList(phones).contains("+84 28 2222"));
    }
}
~~~

Unit test kiểm tra hành vi adapter đối với dữ liệu giả lập, **không chứng minh** server LDAP thực tế có cùng schema, trả đủ attributes hay cấp ACL. Để kiểm thử end-to-end cần thư mục lab đã chuẩn bị: dữ liệu có/không có `mail`, entry có thuộc tính đa trị và người dùng bị giới hạn quyền đọc.

### Một test tích hợp nên kiểm tra những gì?

| Trường hợp | Điều cần chứng minh |
| --- | --- |
| Lookup entry đã biết | DN tương đối kết hợp với `ContextSource.base` đúng |
| Search theo UID | Query filter được escape và trả đúng entry |
| Attribute có một chuỗi | `getStringAttribute` trả đúng giá trị mong muốn |
| Attribute tùy chọn vắng mặt | Mapper không gặp lỗi null và áp dụng fallback |
| Attribute đa trị | `getStringAttributes` đọc đủ các giá trị, không phụ thuộc thứ tự |
| Chỉ yêu cầu một số attributes | Mapper phân biệt giá trị không được trả về với giá trị nghiệp vụ bắt buộc |
| Thử ACL khác nhau | Ứng dụng không suy luận quyền/không tồn tại từ null một cách thiếu căn cứ |
| Thuộc tính binary | Không ép `byte[]` thành `String` tùy ý |

Không chạy thử nghiệm với tài khoản quản trị production; giới hạn OU, thời gian, số lượng kết quả và dữ liệu được phép truy cập.

## 13. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `getStringAttribute("mail")` trả null | Mail vắng, không nằm trong projection hoặc bị ACL che | Kiểm tra dữ liệu, `.attributes(...)` và ACL |
| Mapper phát sinh `NullPointerException` | Gọi phương thức trên một giá trị null | Guard null hoặc chính sách bắt buộc rõ ràng |
| Chỉ thấy một `member` của nhóm | Dùng API đọc một chuỗi cho attribute đa trị | Dùng `getStringAttributes("member")` |
| Số điện thoại hiển thị không ổn định | Tự lấy phần tử đầu từ tập không có thứ tự | Xác định quy tắc chọn/sắp xếp của nghiệp vụ |
| Không tìm thấy entry | DN/search base/scope/filter sai, hoặc không được phép thấy | Kiểm tra toàn bộ query và danh tính bind |
| Không đọc được `cn` dù schema yêu cầu | ACL hoặc projection có thể che dữ liệu | Kiểm tra attributes được yêu cầu và quyền |
| Gặp kiểu dữ liệu lạ | LDAP syntax/provider trả loại không phải String | Dùng API dữ liệu thô hoặc binary đúng kiểu |
| DN trả về thiếu suffix | `getDn()` mang tên tương đối | Diễn giải theo `ContextSource.base` |
| Mất dữ liệu email thứ hai | Mapper chỉ lấy một String thay vì tất cả giá trị | Đổi DTO sang cấu trúc đa trị |
| Kết nối chậm/lỗi | DNS, TLS, bind, pool hoặc timeout | Kiểm tra tầng kết nối, không sửa mapper để “chữa” |

Một search rỗng không mặc nhiên là `getStringAttribute` bị lỗi. Và một lỗi `invalidCredentials (49)` thuộc giai đoạn xác thực LDAP, không phải lỗi chuyển một attribute thành String.

## 14. Bài thực hành: đọc thuộc tính đơn và đa trị

Giả sử thư mục lab có hai nhân viên:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
displayName: Nguyễn Văn An
mail: an@example.org
telephoneNumber: +84 28 1111
telephoneNumber: +84 28 2222

dn: uid=binh,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: binh
cn: Tran Van Binh
sn: Tran
~~~

Đây là dữ liệu minh họa, phải bảo đảm schema thực của server chấp nhận các object class/attributes khi nạp thử nghiệm.

### Yêu cầu

1. Dùng `LdapTemplate.lookupContext(...)` để đọc Bình theo DN tương đối khi `ContextSource.base=dc=example,dc=org`.
2. Lấy `cn` và `mail` của Bình, xử lý khi `mail` thiếu.
3. Đọc đủ hai số điện thoại của An, không dựa vào thứ tự.
4. Viết một `ContextMapper` tìm nhân viên theo UID, trả `uid`, `cn`, `mail` và DN.
5. Nếu search chỉ yêu cầu `uid` và `cn` mà `mail` trả null, có được kết luận entry chắc chắn không có email không?
6. Nếu ứng dụng chỉ cần `cn` và không cần DN, nên cân nhắc mapper nào thay cho `ContextMapper`?
7. Nếu `getStringAttribute("objectClass")` trả về `person`, có thể kết luận entry không có `inetOrgPerson` không?

### Đáp án tham khảo

| Câu | Lời giải |
| --- | --- |
| 1 | Xây `uid=binh,ou=people` bằng `LdapNameBuilder` rồi gọi `lookupContext(...)` |
| 2 | Dùng `getStringAttribute("cn")` và `getStringAttribute("mail")`; kết quả mail có thể null |
| 3 | Dùng `getStringAttributes("telephoneNumber")`, kiểm tra mảng và xử lý mọi giá trị |
| 4 | Query `.base("ou=people").where("uid").is(input)` rồi `search(query, ContextMapper)` |
| 5 | Không. `mail` không được yêu cầu hoặc bị ACL giới hạn nên có thể không xuất hiện |
| 6 | `AttributesMapper`, đọc qua `Attributes.get("cn")` |
| 7 | Không. `objectClass` là thuộc tính đa trị; cần đọc toàn bộ các giá trị |

### Câu hỏi mở rộng

**A.** Có nên dùng `getStringAttribute("member")` để trả danh sách thành viên nhóm LDAP?

*Không.* `member` thường là đa trị; cần đọc toàn bộ và phân tích từng DN theo cách phù hợp.

**B.** Có thể dùng `getStringAttribute` để xác minh mật khẩu người dùng bằng `userPassword` không?

*Không.* Xác thực LDAP nên dùng bind/API xác thực thích hợp. Thuộc tính mật khẩu thường không được đọc hoặc không chứa giá trị plaintext; tuyệt đối không ghi log password.

**C.** `getStringAttribute` có quyết định so khớp hoa/thường khi tìm `uid` không?

*Không.* Cách so khớp do matching rule của LDAP server quyết định ở bước filter. Mapper chỉ đọc kết quả đã được chọn.

## 15. Checklist và điểm cần ghi nhớ

- **`getStringAttribute("name")`** tiện cho việc lấy một giá trị chuỗi từ `DirContextOperations` hoặc `DirContextAdapter`.
- **Không đồng nhất “đọc một String” với “schema bảo đảm SINGLE-VALUE”.** Thuộc tính đa trị cần được xử lý bằng `getStringAttributes(...)` hoặc API `Attribute`.
- **Kiểm tra `null`** cho thuộc tính tùy chọn; khi thiếu trường bắt buộc, áp dụng chính sách lỗi/fallback rõ ràng.
- **Phân biệt thiếu thật với không được trả về.** Projection và ACL có thể làm thuộc tính không xuất hiện trong dữ liệu mapper nhìn thấy.
- **`ContextMapper`** cung cấp `DirContextOperations` để đọc attribute và DN. **`AttributesMapper`** nhận JNDI `Attributes`, không có `getStringAttribute`.
- **Dùng đúng kiểu dữ liệu:** không ép ảnh, chứng chỉ hoặc thuộc tính binary thành String.
- **Giữ DN, filter và mapping là ba trách nhiệm tách biệt:** `LdapNameBuilder` cho DN, `LdapQueryBuilder` cho filter, adapter cho attributes.
- **Bảo vệ truy cập LDAP:** TLS có kiểm tra chứng chỉ, service bind quyền tối thiểu, giới hạn search base/scope và dữ liệu trả về, kiểm thử trên thư mục lab.
- **Kiểm thử hai tầng:** unit test logic adapter/mapper, integration test schema, ACL và dữ liệu thực trên server.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Java Naming and Directory Interface (JNDI): `Attributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/Attributes.html)
- [Java Naming and Directory Interface (JNDI): `Attribute`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/Attribute.html)
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)
- [RFC 4517 — LDAP Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517)
