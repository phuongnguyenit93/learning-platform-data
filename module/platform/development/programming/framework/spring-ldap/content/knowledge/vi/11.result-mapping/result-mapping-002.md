# AttributesMapper và ánh xạ Attributes trong Spring LDAP

Khi gọi `LdapTemplate.search(...)`, LDAP server trả về các entry với nhiều thuộc tính như `uid`, `cn`, `mail` hoặc `displayName`. Tầng nghiệp vụ Java thường không muốn xử lý trực tiếp các kiểu JNDI như `Attributes`, `Attribute` hay `NamingEnumeration`; nó cần một đối tượng rõ nghĩa, ví dụ `DirectoryPerson`. **`AttributesMapper<T>`** của Spring LDAP là một cách đơn giản để chuyển các thuộc tính của **mỗi entry** thành đối tượng Java.

Bài thuộc chương **Mapping kết quả** trong module **Spring LDAP**. Trọng tâm là ánh xạ `javax.naming.directory.Attributes` một cách đúng đắn: phân biệt thuộc tính đơn trị và nhiều giá trị, dữ liệu tùy chọn, kiểu chuỗi/nhị phân, tên thuộc tính theo schema và lỗi khi thuộc tính không được trả về. Ta cũng so sánh `AttributesMapper` với `ContextMapper` để biết lúc nào cần cả DN của entry.

Sau bài học, bạn có thể:

- Hiểu `Attributes`, `Attribute`, giá trị thuộc tính và vòng đời callback mapper.
- Dùng `AttributesMapper<T>` với `LdapTemplate.search(...)` và `LdapTemplate.lookup(...)`.
- Chuyển các attribute LDAP thành record/DTO trong Java với kiểm tra dữ liệu bắt buộc.
- Đọc **tất cả** giá trị của một attribute nhiều giá trị mà không phụ thuộc thứ tự.
- Phân biệt attribute vắng mặt, rỗng, không được yêu cầu và không đủ quyền đọc.
- Không nhầm chuỗi dữ liệu với byte array hoặc coi `AttributesMapper` là API cung cấp DN.
- Viết unit test cho mapper không cần server và integration test với directory thử nghiệm.

## 1. Ví dụ dữ liệu LDAP cần ánh xạ

Giả sử directory có base DN `dc=example,dc=org` và hai entry dưới `ou=people`:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
cn: Nguyen Lan
sn: Nguyen
displayName: Lan N.
mail: lan@example.org
mail: lan.work@example.org

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Minh Tran
sn: Tran
```

Entry Lan có hai giá trị `cn` và hai giá trị `mail`. Entry Minh không có `displayName` và `mail` trong dữ liệu mẫu. Để phục vụ ứng dụng, ta muốn có record:

```java
import java.util.List;

public record DirectoryPerson(
    String uid,
    List<String> commonNames,
    String displayName,
    List<String> emails
) {}
```

Trong ví dụ, ứng dụng đặt quy tắc **`uid` bắt buộc có đúng một giá trị**, `cn` và `mail` được ánh xạ thành danh sách và `displayName` có thể là `null`. Đây là **hợp đồng dữ liệu do ứng dụng chọn**, không phải tuyên bố rằng mọi LDAP schema trên mọi server đều áp cùng số lượng giá trị như vậy.

| Thuộc tính LDAP | Dữ liệu của Lan | Dữ liệu của Minh | Trường Java |
| --- | --- | --- | --- |
| `uid` | `lan` | `minh` | `String uid`, bắt buộc theo ứng dụng |
| `cn` | `Lan Nguyen`, `Nguyen Lan` | `Minh Tran` | `List<String> commonNames` |
| `displayName` | `Lan N.` | Không có | `String displayName`, nullable |
| `mail` | Hai email | Không có | `List<String> emails`, có thể rỗng |

DN của entry là `uid=lan,ou=people,dc=example,dc=org`, nhưng **DN không phải một thuộc tính bình thường tự động nằm trong `Attributes`**. Nếu đối tượng đầu ra cần DN, ta sẽ chuyển sang `ContextMapper` ở phần sau.

## 2. JNDI Attributes và Attribute có cấu trúc như thế nào?

Spring LDAP sử dụng các API directory của JNDI, trong đó:

- **`javax.naming.directory.Attributes`** là một tập hợp các `Attribute` được tra theo tên thuộc tính. Ví dụ `attributes.get("mail")` trả một `Attribute`, hoặc `null` khi không có trong tập kết quả.
- **`javax.naming.directory.Attribute`** biểu diễn một loại thuộc tính cùng các **giá trị** đang có trong tập kết quả, ví dụ attribute `mail` có hai địa chỉ.
- **`Attribute.get()`** lấy một giá trị (không diễn đạt “giá trị chính” cho thuộc tính nhiều giá trị).
- **`Attribute.size()`**, **`Attribute.get(int)`** hoặc **`Attribute.getAll()`** giúp duyệt các giá trị; phải xử lý `NamingException` khi các API có thể ném lỗi.
- **`Attributes.getAll()`** cho phép duyệt các attribute đã được trả về, không phải duyệt mọi thuộc tính được phép trong schema.

Sơ đồ:

```text
Một LDAP entry (uid=lan,ou=people,...)
             │
             ▼
   Attributes trong callback
       ├── uid          → Attribute ["lan"]
       ├── cn           → Attribute ["Lan Nguyen", "Nguyen Lan"]
       ├── displayName  → Attribute ["Lan N."]
       └── mail         → Attribute ["lan@example.org",
                                    "lan.work@example.org"]
             │
             ▼
   AttributesMapper<DirectoryPerson>
             │
             ▼
    DirectoryPerson Java record
```

Trong LDAP, attribute type có tên và định danh schema. Một entry có thể chứa attribute nhiều giá trị nếu schema cho phép. **LDAP không cam kết thứ tự của các giá trị trong một attribute không có thứ tự**. Vì thế, `get(0)` hay `get()` không thể được coi là “email chính” hay “họ tên ưu tiên” nếu ứng dụng chưa có quy tắc rõ ràng.

### Thuộc tính trong kết quả không bằng toàn bộ schema

Nếu query chỉ yêu cầu `uid` và `cn`, `Attributes` chuyển vào mapper có thể chỉ chứa hai attribute này. Tập kết quả cũng có thể bị ảnh hưởng bởi ACL hoặc cách server cung cấp operational attribute. Một `null` từ `attributes.get("mail")` **không chứng minh** rằng bản ghi hoàn toàn không có email trong directory: có thể query không yêu cầu, server không trả hoặc tài khoản thiếu quyền.

## 3. Hợp đồng của AttributesMapper<T>

Interface quan trọng là `org.springframework.ldap.core.AttributesMapper<T>`. Ở dạng ý tưởng, nó giống:

```java
public interface AttributesMapper<T> {
    T mapFromAttributes(
        javax.naming.directory.Attributes attributes
    ) throws javax.naming.NamingException;
}
```

Đây là **chữ ký minh họa** để giải thích callback, không phải mã cần tự định nghĩa lại interface. Một implementation ánh xạ **một đối tượng `Attributes` thành một `T`**.

Khi dùng `LdapTemplate.search(...)`:

1. Template lấy context từ `ContextSource`, thực hiện search theo base/scope/filter.
2. Với mỗi entry khớp được server trả, callback `mapFromAttributes(...)` nhận các thuộc tính của entry đó.
3. Callback tạo record/DTO Java.
4. Template gom các kết quả mapping vào `List<T>` để trả cho ứng dụng; đồng thời quản lý việc lấy/đóng tài nguyên JNDI.

Khi dùng `lookup(dn, mapper)`, callback nhận thuộc tính của **một entry có DN đã biết**, còn kết quả Java là `T` thay vì danh sách các match.

**`AttributesMapper` không cung cấp trực tiếp DN hoặc `SearchResult` trong callback.** Nếu cần DN, object class cấp context hoặc thao tác giàu ngữ cảnh hơn, hãy xem `ContextMapper` và `DirContextOperations`.

## 4. Ví dụ đầu tiên: ánh xạ một thuộc tính thành String

Giả sử chỉ cần `cn` của entry Lan theo DN đã biết, có thể dùng `lookup` với một `AttributesMapper<String>`:

```java
import javax.naming.directory.Attribute;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public final class CommonNameReader {
    private final LdapTemplate ldapTemplate;

    public CommonNameReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String readOneCommonName() {
        return ldapTemplate.lookup(
            "uid=lan,ou=people",
            (AttributesMapper<String>) attrs -> {
                Attribute cn = attrs.get("cn");
                if (cn == null || cn.size() == 0) {
                    return null;
                }
                return (String) cn.get();
            }
        );
    }
}
```

Ví dụ giả định `ContextSource.base = "dc=example,dc=org"`, nên DN tương đối `uid=lan,ou=people` trỏ đúng tới entry Lan. Nếu `ContextSource` có base khác, DN truyền cho `lookup` cũng cần thay đổi tương ứng.

Ở đây `cn.get()` chỉ trả **một** giá trị được provider cung cấp. Với Lan có hai giá trị `cn`, đoạn code trên **không phải** giải pháp đọc mọi tên. Cách mapping sang `List<String>` ở phần tiếp theo phù hợp hơn khi muốn bảo toàn dữ liệu.

Lưu ý trường hợp thiếu `cn`: trả `null` giúp minh họa một mapper nhẹ, nhưng nếu hợp đồng nghiệp vụ bắt buộc phải có tên, nên trả lỗi dữ liệu thay vì âm thầm coi hồ sơ đã đầy đủ.

## 5. Viết mapper hoàn chỉnh: required, optional và multi-valued

Ví dụ Java 17+ dưới đây cài đặt `AttributesMapper<DirectoryPerson>` có thể tái sử dụng trong nhiều truy vấn. Nó xử lý riêng ba dạng dữ liệu:

- **Required one value:** `uid` phải tồn tại và có đúng một chuỗi theo hợp đồng của ứng dụng.
- **Optional one value:** `displayName` có thể thiếu; nếu có thì ứng dụng kỳ vọng một chuỗi.
- **Zero or many values:** `cn` và `mail` trở thành danh sách, không bỏ sót giá trị.

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;

public final class PersonAttributesMapper
        implements AttributesMapper<DirectoryPerson> {

    @Override
    public DirectoryPerson mapFromAttributes(Attributes attrs)
            throws NamingException {
        String uid = requiredOne(attrs, "uid");
        List<String> commonNames = strings(attrs, "cn");
        String displayName = optionalOne(attrs, "displayName");
        List<String> emails = strings(attrs, "mail");

        return new DirectoryPerson(uid, commonNames, displayName, emails);
    }

    private static String requiredOne(Attributes attrs, String name)
            throws NamingException {
        String value = optionalOne(attrs, name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Required LDAP attribute missing or blank: " + name);
        }
        return value;
    }

    private static String optionalOne(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            return null;
        }
        if (attribute.size() != 1) {
            throw new IllegalStateException(
                "Expected one value for LDAP attribute: " + name);
        }
        return requireString(attribute.get(0), name);
    }

    private static List<String> strings(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            return List.of();
        }

        List<String> values = new ArrayList<>(attribute.size());
        for (int i = 0; i < attribute.size(); i++) {
            values.add(requireString(attribute.get(i), name));
        }
        return List.copyOf(values);
    }

    private static String requireString(Object value, String name) {
        if (!(value instanceof String text)) {
            throw new IllegalStateException(
                "Unexpected non-string LDAP value for: " + name);
        }
        return text;
    }
}
```

**Giải thích kỹ thuật:**

1. `attrs.get(name)` có thể trả `null`. Mapper không gọi `get()` trên `null`.
2. `attribute.size()` kiểm tra số giá trị **thực sự có trong kết quả**. Ứng dụng có thể đặt chính sách nghiêm ngặt cho `uid`/`displayName`.
3. Vòng lặp `get(i)` lấy mọi giá trị của `cn` và `mail`; không gán ý nghĩa thứ tự cho danh sách.
4. `requireString(...)` từ chối value không phải `String`, thay vì ép kiểu sai một `byte[]` thành chuỗi hoặc dùng `toString()` không kiểm soát.
5. `List.copyOf(...)` tạo danh sách bất biến cho record Java. Nếu ứng dụng muốn mutable list, hãy quyết định rõ ở tầng DTO.
6. Exception ném khi dữ liệu không đáp ứng hợp đồng cho biết có vấn đề mapping/cấu hình/ACL. **Không** nên biến mọi lỗi thành “không tìm thấy người dùng”.

**Quan trọng:** kiểu LDAP attribute trong schema quyết định giá trị nhận về. Cách kiểm tra `instanceof String` phù hợp với những attribute chuỗi của ví dụ. Mapper nhị phân, thời gian, generalized time, DN, số hoặc các attribute đặc thù sẽ cần logic riêng, không nhất thiết dùng `String`.

## 6. Kết hợp mapper với LdapTemplate.search

Giả sử ứng dụng Spring Boot có cấu hình:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Trên hệ thống thật, mật khẩu cần lấy từ secret store, CA/truststore phải tin cậy đúng máy chủ và kết nối LDAPS/StartTLS phải xác minh chứng chỉ. Tài khoản bind nên có quyền tối thiểu, phù hợp với dữ liệu ứng dụng cần đọc.

Tạo một repository/adapter chuyên làm việc với LDAP:

```java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class DirectoryPersonRepository {
    private final LdapTemplate ldapTemplate;
    private final PersonAttributesMapper mapper = new PersonAttributesMapper();

    public DirectoryPersonRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryPerson> findByUid(String requestedUid) {
        if (requestedUid == null || requestedUid.isBlank()) {
            throw new IllegalArgumentException("uid must not be blank");
        }

        LdapQuery ldapQuery = query()
            .base("ou=people")
            .attributes("uid", "cn", "displayName", "mail")
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(requestedUid);

        return ldapTemplate.search(ldapQuery, mapper);
    }
}
```

Với `requestedUid = "lan"` và dữ liệu mẫu, ứng dụng nhận về một danh sách chứa `DirectoryPerson` với hai giá trị `cn` và hai địa chỉ email. Trong directory thật, nếu cùng `uid` có thể xuất hiện ở nhiều OU, search có thể trả **nhiều entry**; thuộc tính `uid` không tự bảo đảm tính duy nhất trên toàn subtree. Không âm thầm lấy phần tử đầu tiên nếu nghiệp vụ cần đúng một người.

Các quyết định cần chú ý:

| Thành phần | Ý nghĩa | Lỗi cần tránh |
| --- | --- | --- |
| `base("ou=people")` | Nhánh tìm kiếm tương đối với base context | Truyền DN đầy đủ và lặp hậu tố |
| `where("objectClass").is(...)` | Giới hạn loại entry | Dùng tên object class không tồn tại trong schema |
| `and("uid").is(requestedUid)` | Equality filter được builder escape giá trị | Nối thẳng input vào filter |
| `attributes("uid","cn","displayName","mail")` | Projection: yêu cầu đúng thuộc tính mapper sử dụng | Quên `uid` rồi mapper báo thiếu dữ liệu |
| `ldapTemplate.search(query, mapper)` | Mỗi entry khớp được map thành một object | Mong một `Attributes` chứa dữ liệu của tất cả entry |

**Điểm tinh tế:** filter được phép dùng `objectClass` dù projection không yêu cầu trả attribute đó về. Server dùng filter để quyết định entry có khớp hay không; projection quyết định những attribute client yêu cầu cho mapping. Không nhầm hai công đoạn.

Một số thuộc tính operational không được trả mặc định, tùy server phải yêu cầu tường minh. Nếu chưa thấy một attribute, hãy kiểm tra projection, quyền ACL và schema trước khi kết luận dữ liệu không tồn tại.

## 7. Dùng cùng mapper trong lookup theo DN

Khi đã **biết DN của entry**, dùng `lookup` thay vì search theo filter:

```java
public DirectoryPerson readLanByDn() {
    return ldapTemplate.lookup(
        "uid=lan,ou=people",
        new PersonAttributesMapper()
    );
}
```

Ví dụ là method trong class đã có field `ldapTemplate` và `ContextSource.base = "dc=example,dc=org"`. `lookup` đọc entry có DN tương đối `uid=lan,ou=people`; không tự duyệt các OU khác.

**Không nhầm hai trường hợp:**

- Search theo `uid`: cần base, scope và filter; kết quả có thể là 0, 1 hoặc nhiều entry.
- Lookup theo DN đã biết: nhắm tới đúng entry đó; lỗi khi không thể tra tên hoặc đọc entry.

Nếu DN được tạo từ giá trị người dùng, dùng `LdapNameBuilder` hoặc `LdapName` để escape đúng ký tự trong RDN. Không ghép `"uid=" + userInput + ",ou=people"` hoặc dùng escaping của filter như escaping của DN: hai quy tắc này khác nhau.

## 8. Multi-valued attribute và vấn đề thứ tự dữ liệu

LDAP cho phép một số attribute có nhiều giá trị. Ví dụ `mail` có hai địa chỉ, `cn` có thể chứa nhiều tên. Không dùng:

```java
// Không phải cách lấy đầy đủ mọi email.
String oneMail = (String) attrs.get("mail").get();
```

Lệnh trên vừa có nguy cơ `NullPointerException` khi `mail` vắng, vừa chỉ lấy một giá trị khi có nhiều email. Thay vào đó, dùng phương thức `strings(attrs, "mail")` ở phần 5 hoặc duyệt `Attribute.getAll()`.

Nếu chọn `getAll()`, hãy chú ý hợp đồng đóng tài nguyên `NamingEnumeration`:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;

static List<String> readAllStrings(Attribute attribute)
        throws NamingException {
    if (attribute == null) {
        return List.of();
    }

    List<String> result = new ArrayList<>();
    NamingEnumeration<?> values = attribute.getAll();
    try {
        while (values.hasMore()) {
            Object value = values.next();
            if (!(value instanceof String text)) {
                throw new IllegalStateException("Non-string value");
            }
            result.add(text);
        }
    } finally {
        values.close();
    }
    return List.copyOf(result);
}
```

Trong mapper chính, vòng lặp `get(i)` được sử dụng để tránh giữ thêm enumeration. Cả hai cách đều lấy nhiều giá trị nếu provider hỗ trợ; **không mặc định thứ tự giá trị là có ý nghĩa**. Với dữ liệu cần một giá trị chính thức, nên lưu quy tắc ở schema/nghiệp vụ hoặc dùng thuộc tính riêng (ví dụ `displayName`) thay vì đoán dựa trên thứ tự trả về.

### Attribute name và schema

Các tên như `cn`, `sn`, `uid`, `mail` và `displayName` là descriptor của attribute type, có quy tắc schema tương ứng. LDAP attribute type có OID, có thể có alias được khai báo trong schema. Không tự đặt “alias” chỉ bằng cách thay key trong mapper Java.

LDAP descriptor không phân biệt chữ hoa/chữ thường ở mức schema; tuy nhiên cách biểu diễn key trong tập JNDI `Attributes` có thể phụ thuộc provider và cách khởi tạo `Attributes` khi tự mock. Trong unit test dùng `new BasicAttributes(true)` để mô phỏng phép tra cứu key không phân biệt hoa/thường khi cần.

## 9. Binary attribute và chuyển đổi kiểu dữ liệu

Không phải mọi giá trị từ LDAP đều là `String`. Một attribute như `jpegPhoto` có thể được provider trả về dưới dạng `byte[]`. Nếu mapper cố ép kiểu `String` hoặc log toàn bộ byte array, kết quả có thể lỗi hoặc rò rỉ dữ liệu nhạy cảm.

Ví dụ đọc dữ liệu ảnh khi schema/server hỗ trợ:

```java
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

static byte[] optionalPhoto(Attributes attrs) throws NamingException {
    Attribute photo = attrs.get("jpegPhoto");
    if (photo == null || photo.size() == 0) {
        return null;
    }

    Object value = photo.get(0);
    if (!(value instanceof byte[] bytes)) {
        throw new IllegalStateException("jpegPhoto is not binary");
    }
    return bytes.clone(); // Không phát tán reference mutable từ JNDI.
}
```

Lưu ý:

1. Các attribute nhị phân có thể rất lớn. Chỉ thêm `jpegPhoto` vào projection khi tính năng thực sự cần và được quyền đọc.
2. Chương trình cần giới hạn kích thước payload, kiểm tra định dạng dữ liệu và xử lý quyền truy cập phù hợp. Mapper không tự kiểm chứng tính hợp lệ của ảnh.
3. Nếu attribute có nhiều giá trị, code trên chọn **một giá trị**, không phải toàn bộ ảnh; quy tắc lựa chọn phải là một quyết định rõ ràng.
4. Với record chứa `byte[]`, cần cân nhắc defensive copy cả khi lưu lẫn khi trả về để tránh thay đổi dữ liệu ngoài ý muốn.

Không áp dụng máy móc `new String(bytes)` cho dữ liệu LDAP nhị phân; nội dung có thể không phải văn bản. Với attribute có syntax thời gian hoặc DN, hãy xác định cách parser và quy tắc chuẩn hóa phù hợp với schema/directory thật.

## 10. Khi nào chuyển sang ContextMapper?

`AttributesMapper` phù hợp khi chỉ cần **giá trị attribute**. Nếu kết quả nghiệp vụ cần cả DN của entry hoặc tiện ích của `DirContextOperations`, dùng `ContextMapper<T>`:

```java
import javax.naming.Name;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

record PersonIdentity(Name entryDn, String uid) {}

ContextMapper<PersonIdentity> mapper = context -> {
    DirContextOperations entry = (DirContextOperations) context;
    return new PersonIdentity(
        entry.getDn(),
        entry.getStringAttribute("uid")
    );
};
```

Trong ví dụ, `entry.getDn()` lấy DN mà Spring LDAP context biểu diễn. **Hãy kiểm tra quan hệ của tên này với `ContextSource.base` trước khi lưu hoặc đưa vào API ngoài**; không tự giả định mọi kết quả đều là DN tuyệt đối của server. Một số bài toán còn cần tên đầy đủ trong namespace với cách lấy cụ thể theo provider.

So sánh:

| Nhu cầu | Mapper nên cân nhắc | Lý do |
| --- | --- | --- |
| Hiển thị `uid`, `cn`, `mail` | `AttributesMapper` | Nhẹ, tập trung vào các attribute |
| Cần một `String` từ lookup | `AttributesMapper<String>` | Callback ngắn gọn |
| Cần DN để rename/move hoặc liên kết entry | `ContextMapper` | Context có thông tin về tên entry |
| Muốn dùng `DirContextOperations.getStringAttributes(...)` | `ContextMapper` | API tiện ích trên context |
| Mapping nhiều object phức tạp theo annotation | Spring LDAP ODM, nếu phù hợp | Quy tắc ánh xạ khai báo tập trung |

**Không coi `AttributesMapper` là ORM tự động.** Nó là callback Java do bạn triển khai: bạn chịu trách nhiệm tên thuộc tính, kiểu dữ liệu, null/multi-value và validation. ODM có mục đích khác và cần các annotation/schema phù hợp.

## 11. Xử lý thiếu dữ liệu, lỗi server và quyền truy cập

Một truy vấn có thể không trả được dữ liệu mong đợi vì nhiều lý do. Mapper cần phân biệt tình huống một entry được trả nhưng thiếu attribute, với trường hợp **không có entry nào khớp** và với trường hợp **truy vấn thất bại**.

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `search(...)` trả `List.of()` | Không entry nào khớp trong base/scope/filter hoặc không nhìn thấy entry do ACL | Xác nhận kết quả tìm kiếm thành công và chính sách quyền |
| Callback không được gọi | Không có entry trả về | Không phải lỗi mapper |
| `attrs.get("mail") == null` | Entry thiếu mail, projection không yêu cầu, hoặc ACL che attribute | Đối chiếu projection, schema và quyền |
| `uid` thiếu dù filter dùng `(uid=lan)` | Projection không trả `uid`, ACL hoặc dữ liệu/schema bất thường | Bảo đảm query yêu cầu trường mapper cần |
| `(String) attribute.get()` gây `ClassCastException` | Attribute có kiểu không phải chuỗi | Kiểm tra syntax và kiểu dữ liệu JNDI trước khi ép |
| Có nhiều `cn` nhưng giao diện chỉ hiện một | Mapper dùng `get()` hoặc `get(0)` | Map tất cả hoặc định nghĩa quy tắc chọn riêng |
| DN sai, lookup thất bại | Base context và DN tương đối không khớp hoặc entry đã move | Kiểm tra DN thực tế và cấu hình |
| Lỗi bind, TLS, ACL, timeout | Truy vấn không hoàn thành như dự kiến | Báo lỗi hạ tầng, không đổi thành danh sách rỗng |

Một mapper có thể cố ý ném `IllegalStateException` khi thiếu attribute bắt buộc theo hợp đồng. Spring LDAP chuyển đổi nhiều `NamingException` do JNDI phát sinh trong quá trình thao tác, nhưng exception do **code ứng dụng chủ động ném** không nhất thiết bị biến thành một lỗi directory cụ thể. Tầng nghiệp vụ nên biết mapper có chính sách **strict** hay **lenient**.

**Strict mapping** phù hợp khi thiếu `uid` có thể tạo danh tính sai. **Lenient mapping** phù hợp khi `displayName` hoặc `mail` là tùy chọn và đã có fallback. Dù chọn cách nào, tránh:

```java
// Không nên: mất kết nối LDAP bị ngụy trang thành "không tìm thấy".
try {
    return repository.findByUid(userUid);
} catch (Exception ignored) {
    return List.of();
}
```

Cấu hình kết nối LDAPS/StartTLS với chứng chỉ đáng tin cậy, bảo vệ secret của bind account, và để LDAP server thực thi ACL. Mapping đúng không thay thế bảo mật hoặc kiểm soát quyền truy cập thư mục.

## 12. Unit test mapper với BasicAttributes, không cần LDAP server

`AttributesMapper` là một callback thuần Java: có thể unit test ngay bằng `BasicAttributes` và `BasicAttribute` của JNDI. Không cần khởi động `LdapTemplate` hay LDAP server để xác minh logic required/optional/multi-valued.

Ví dụ JUnit 5 (giả định `DirectoryPerson` và `PersonAttributesMapper` là các class của phần trước):

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Set;
import javax.naming.directory.Attributes;
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.junit.jupiter.api.Test;

class PersonAttributesMapperTest {
    private final PersonAttributesMapper mapper =
        new PersonAttributesMapper();

    @Test
    void mapsMultiValuedMailWithoutAssumingOrder() throws Exception {
        Attributes attrs = new BasicAttributes(true);
        attrs.put("uid", "lan");
        attrs.put("displayName", "Lan N.");

        Attribute cn = new BasicAttribute("cn");
        cn.add("Lan Nguyen");
        cn.add("Nguyen Lan");
        attrs.put(cn);

        Attribute mail = new BasicAttribute("mail");
        mail.add("lan@example.org");
        mail.add("lan.work@example.org");
        attrs.put(mail);

        DirectoryPerson result = mapper.mapFromAttributes(attrs);

        assertEquals("lan", result.uid());
        assertEquals("Lan N.", result.displayName());
        assertEquals(
            Set.of("Lan Nguyen", "Nguyen Lan"),
            Set.copyOf(result.commonNames())
        );
        assertEquals(
            Set.of("lan@example.org", "lan.work@example.org"),
            Set.copyOf(result.emails())
        );
    }

    @Test
    void missingOptionalAttributesAreHandled() throws Exception {
        Attributes attrs = new BasicAttributes(true);
        attrs.put("uid", "minh");
        attrs.put("cn", "Minh Tran");

        DirectoryPerson result = mapper.mapFromAttributes(attrs);

        assertNull(result.displayName());
        assertEquals(List.of(), result.emails());
        assertEquals(List.of("Minh Tran"), result.commonNames());
    }

    @Test
    void missingRequiredUidIsRejected() {
        Attributes attrs = new BasicAttributes(true);
        attrs.put("cn", "Unknown Person");

        assertThrows(
            IllegalStateException.class,
            () -> mapper.mapFromAttributes(attrs)
        );
    }

    @Test
    void nonStringValueForMailIsRejected() {
        Attributes attrs = new BasicAttributes(true);
        attrs.put("uid", "lan");
        attrs.put("mail", new byte[] {1, 2, 3});

        assertThrows(
            IllegalStateException.class,
            () -> mapper.mapFromAttributes(attrs)
        );
    }
}
```

Trong unit test, `BasicAttributes(true)` chỉ định **tra cứu ID attribute không phân biệt hoa/thường**. Hai attribute nhiều giá trị được so sánh bằng tập `Set` để tránh đặt giả định về thứ tự. Với dữ liệu có **giá trị trùng lặp hoặc thứ tự có ý nghĩa theo schema**, cần xây bài test tương ứng thay vì chuyển sang Set một cách máy móc.

Unit test như trên xác minh logic mapper, **không chứng minh** LDAP server thật sẽ trả cùng loại object hoặc cho phép đọc cùng thuộc tính. Phải có integration test cho phần kết nối và schema.

## 13. Integration test và kiểm tra hoạt động thật

Khi đã có một directory thử nghiệm với entry mẫu, nên kiểm tra tối thiểu:

1. **Cấu hình:** `ContextSource.base` cộng search base tương đối tạo đúng DN trên server; URL, bind DN và TLS hợp lệ.
2. **Projection:** tìm theo `objectClass`/`uid` nhưng chỉ nhận `uid`, `cn`, `displayName` và `mail` như đã yêu cầu.
3. **Single value policy:** `uid` trả một giá trị đúng theo dữ liệu ứng dụng kỳ vọng.
4. **Multi-valued:** mọi `cn` và `mail` đều được ánh xạ, không dựa vào thứ tự.
5. **Optional:** entry thiếu `displayName` hoặc `mail` không gây lỗi ngoài ý muốn.
6. **Binary:** nếu có `jpegPhoto`, kiểm tra kiểu trả về và giới hạn payload.
7. **Quyền:** tài khoản chỉ đọc thấy đúng các attribute được phép; khi thiếu quyền, lỗi/dữ liệu thiếu được xử lý theo chính sách rõ ràng.
8. **Search vs lookup:** search theo filter có thể có nhiều entry; lookup theo DN đã biết nhắm đúng một entry.
9. **Giới hạn:** size/time limit hoặc phân trang chưa hoàn tất không được diễn giải thành danh sách đầy đủ.

Nếu kết quả lớn, `LdapTemplate.search(..., AttributesMapper<T>)` trả danh sách DTO và có thể tiêu tốn nhiều bộ nhớ. Trong hệ thống production, hãy giới hạn search base, scope, filter, attribute projection; dùng paging hoặc callback/cách duyệt phù hợp với phiên bản và directory server khi phải đọc số lượng lớn. **Projection giảm dữ liệu trả về, không tự giới hạn số entry.**

Không log nguyên giá trị email, mã định danh hoặc ảnh nếu không cần; quan sát truy vấn bằng metric không chứa dữ liệu cá nhân. Khi so sánh với `ldapsearch`, nhớ rằng công cụ dòng lệnh thường dùng **DN đầy đủ** cho `-b`, còn `LdapTemplate` dùng DN tương đối nếu `ContextSource` đã có base.

## 14. Bài thực hành tự kiểm tra

Cho entry:

```ldif
dn: uid=mai,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: mai
cn: Mai Pham
sn: Pham
mail: mai@example.org
mail: mai.team@example.org
```

Giả sử `ContextSource.base = "dc=example,dc=org"` và server cho phép đọc những attribute được yêu cầu.

**Câu 1.** Nếu mapper gọi `attrs.get("displayName")` mà nhận `null`, có thể kết luận entry hoàn toàn không lưu attribute đó không?

**Câu 2.** Với query chỉ yêu cầu `uid` và `cn`, mapper đọc `mail` có nhận đủ hai địa chỉ không?

**Câu 3.** Muốn bảo toàn cả hai địa chỉ `mail`, nên dùng `get()` hay duyệt `get(i)`/`getAll()`?

**Câu 4.** Vì sao `attrs.get("mail").get()` có thể gây lỗi?

**Câu 5.** Nếu muốn trả thêm DN của Mai để ứng dụng lưu tham chiếu, chọn `AttributesMapper` hay `ContextMapper`?

**Câu 6.** Nếu dùng `lookup` với `ContextSource.base = "dc=example,dc=org"`, DN tương đối để đọc Mai là gì?

**Câu 7.** Nếu `jpegPhoto` được trả về là `byte[]`, vì sao ép `(String)` là sai? Có cần yêu cầu nó trong mọi search không?

**Câu 8.** Khi LDAP server mất kết nối, có được trả `List.of()` từ repository để giả làm kết quả “không có người dùng” không?

**Đáp án và giải thích:**

1. Không chắc. Attribute có thể không được yêu cầu trong projection, không được phép đọc hoặc thực sự không có. Cần kiểm tra cả ba tình huống.
2. Không; projection chỉ yêu cầu `uid`/`cn` thì `mail` không nhất thiết được trả về. Phải thêm `mail` nếu mapper cần đọc.
3. Duyệt `get(i)` hoặc `getAll()`; `get()` chỉ lấy một giá trị và không đảm bảo thứ tự.
4. Vì `attrs.get("mail")` có thể là `null` nếu thuộc tính không được trả về. Cần kiểm tra trước khi lấy giá trị.
5. Chọn `ContextMapper` nếu cần thông tin DN từ `DirContextOperations`, sau đó kiểm tra tên tương đối/đầy đủ theo bối cảnh.
6. `uid=mai,ou=people`. Base `dc=example,dc=org` đã nằm trong `ContextSource`.
7. `byte[]` không phải `String` và có thể chứa dữ liệu ảnh lớn; chỉ yêu cầu khi tính năng cần và người dùng được phép.
8. Không. Mất kết nối là lỗi hạ tầng, không chứng minh search đã thành công với tập kết quả rỗng.

## 15. Tổng kết và tài liệu tham khảo

**`AttributesMapper<T>`** chuyển tập thuộc tính của **mỗi entry LDAP** thành một đối tượng Java. Kết hợp với `LdapTemplate.search(...)`, mapper tạo danh sách DTO; với `lookup(dn, mapper)`, nó chuyển dữ liệu của một entry có DN đã biết. Điểm quan trọng nhất là hiểu `Attributes` có thể **thiếu attribute**, `Attribute` có thể **nhiều giá trị**, và giá trị có thể là **chuỗi hoặc nhị phân** tùy schema/provider.

Khi thiết kế mapper, hãy phân biệt required và optional, không suy ra thứ tự của multi-valued attribute, không ép `byte[]` thành chuỗi, yêu cầu đúng projection và dùng `ContextMapper` khi cần DN. Spring LDAP giúp quản lý JNDI/context và thực thi truy vấn, nhưng **kiểm tra schema, ACL, TLS, giá trị dữ liệu và ngữ nghĩa nghiệp vụ vẫn là trách nhiệm của ứng dụng**.

Tài liệu tham khảo:

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): mapping results, `LdapTemplate`, `ContextSource` và tìm kiếm LDAP.
- [Spring LDAP — AttributesMapper API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/AttributesMapper.html): callback `mapFromAttributes`.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): overload `search`/`lookup` với mapper.
- [Spring LDAP — ContextMapper API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/ContextMapper.html): mapping qua context.
- [Java JNDI — Attributes API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/Attributes.html): đọc thuộc tính của entry.
- [Java JNDI — Attribute API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/Attribute.html): các giá trị, `get(int)`, `getAll()`, `size()`.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, attribute type và schema.
- [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp filter và escaping.
