# Chọn AttributesMapper, ContextMapper hoặc callback xử lý kết quả

Trong **Spring Data LDAP**, ứng dụng Java có thể truy cập thư mục LDAP qua `LdapRepository`, qua cơ chế Object-Directory Mapping (ODM) hoặc truy vấn trực tiếp bằng **`LdapTemplate`**. Khi gọi `LdapTemplate.search(...)`, một quyết định quan trọng là **chuyển từng kết quả LDAP thành dữ liệu Java theo cách nào**: chỉ đọc attributes, cần thêm DN hay xử lý ngay từng entry mà không phải tạo một danh sách DTO.

Ba lựa chọn phổ biến là:

1. **`AttributesMapper<T>`** — ánh xạ tập thuộc tính `Attributes` của mỗi entry thành đối tượng Java.
2. **`ContextMapper<T>`** — ánh xạ ngữ cảnh entry, thường là `DirContextAdapter` có cả **DN** và helper đọc attribute.
3. **`NameClassPairCallbackHandler`** — nhận một callback cho từng kết quả và tự quyết định làm gì với kết quả đó.

Bài học đi sâu vào ngữ nghĩa và API của ba cách, tiêu chí lựa chọn, ví dụ Java, hiệu năng, bảo mật filter, giới hạn kết quả và kiểm thử với directory. Bạn sẽ biết khi nào một mapper gọn là đủ và khi nào cần context hoặc callback.

## 1. Dữ liệu thực tế được mapper xử lý

Giả sử LDAP server có entry:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
mail: lan.work@example.org
```

Entry này nằm trong **Directory Information Tree (DIT)**. `dn` là định danh phân cấp của entry; `uid`, `cn`, `sn`, `mail` và `objectClass` là các thuộc tính LDAP. Một LDAP SearchRequest còn có:

```text
Search base : ou=people,dc=example,dc=org
Search scope: SUBTREE
Filter      : (&(objectClass=inetOrgPerson)(uid=lan))
```

Mỗi entry trả về thường được JNDI biểu diễn qua `javax.naming.directory.SearchResult`, cung cấp tên của kết quả cùng một tập `Attributes`. `LdapTemplate` có thể chuyển dữ liệu này tới mapper hoặc callback:

```text
LDAP SearchResult
   │
   ├── AttributesMapper<T>
   │      └── Attributes -> T -> List<T>
   │
   ├── ContextMapper<T>
   │      └── DirContextAdapter -> T -> List<T>
   │
   └── NameClassPairCallbackHandler
          └── SearchResult -> xử lý từng entry; không trả List<T>
```

**Base/scope/filter quyết định entry nào khớp; mapper/callback quyết định cách kết quả được xử lý.** Việc dùng `ContextMapper` không khiến LDAP server tìm được nhiều entry hơn, còn callback không tự động giới hạn số kết quả hoặc tối ưu filter.

## 2. Bảng lựa chọn nhanh

| Nhu cầu nghiệp vụ | Chọn | Vì sao |
| --- | --- | --- |
| Trả tên/email cho một trang danh bạ | **`AttributesMapper<T>`** | Chỉ cần attributes; mapping đơn giản |
| Ánh xạ DTO không cần DN | **`AttributesMapper<T>`** | Không phụ thuộc đối tượng context của factory |
| Phải biết DN để phân biệt người trùng `uid` ở hai OU | **`ContextMapper<T>`** | Lấy `getDn()` hoặc `getNameInNamespace()` |
| Cần các helper `getStringAttribute` và `getStringAttributes` | **`ContextMapper<T>`** | Dùng `DirContextOperations` |
| Chỉ đếm số kết quả search nhận được | **Callback** | Không phải tạo DTO rồi giữ danh sách |
| Tích lũy thống kê hoặc đưa từng entry sang một bộ xử lý | **Callback** | Tạo side effect khi đang duyệt từng kết quả |
| Quản lý entity với `@Entry`/`@Id`/`@Attribute` | **ODM/repository** | Tránh ánh xạ lại mô hình đối tượng đã khai báo |
| Cần LDAP controls, ví dụ phân trang | **`DirContextProcessor` phối hợp** | Điều khiển request/response, không thay thế mapper |

Mapper **trả một đối tượng Java cho mỗi entry** để Spring LDAP thu thập vào `List<T>`. Callback **thực hiện một hành động với mỗi kết quả** và overload callback của `search` trả `void`.

## 3. AttributesMapper: chỉ cần thuộc tính LDAP

### 3.1. Hợp đồng API

`AttributesMapper<T>` thuộc `org.springframework.ldap.core`, có phương thức:

```java
T mapFromAttributes(javax.naming.directory.Attributes attributes)
        throws javax.naming.NamingException;
```

Nó nhận **tập LDAP attributes của một entry**, không nhận trực tiếp DN/context theo hợp đồng interface. Không nên cố tìm một attribute tên `dn` để dựng lại tên entry, vì DN là **tên phân biệt**, không phải attribute nội dung thông thường như `cn`.

### 3.2. Ví dụ: DTO liên hệ theo `uid`

Giả sử `LdapContextSource` được cấu hình base `dc=example,dc=org`; vì vậy `ou=people` trong query là base tương đối. Ví dụ dùng Java 17+ để viết `record`; có thể thay bằng POJO.

```java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

record Contact(String uid, String fullName, String email) {}

public class ContactSearchService {
    private final LdapTemplate ldapTemplate;

    public ContactSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<Contact> findByUid(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail")
                .countLimit(100)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(query,
                (AttributesMapper<Contact>) attrs ->
                        new Contact(
                                firstValue(attrs, "uid"),
                                firstValue(attrs, "cn"),
                                firstValue(attrs, "mail")));
    }

    private static String firstValue(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null || attribute.size() == 0
                ? null
                : (String) attribute.get();
    }
}
```

Giải thích:

- `.is(uid)` xây equality filter từ giá trị đầu vào và escape theo cú pháp LDAP filter; không cần nối chuỗi.
- `.attributes("uid", "cn", "mail")` hạn chế dữ liệu trả về để giảm lưu lượng và chi phí ánh xạ.
- `.countLimit(100)` đặt giới hạn kết quả được trả về, **không bảo đảm `uid` là duy nhất** và không phải chỉ dẫn dùng index.
- Hàm `firstValue` bảo vệ trường hợp attribute không tồn tại. Nó lấy **một giá trị**, phù hợp chỉ khi DTO thật sự cần một giá trị.

### 3.3. Thuộc tính đa trị và nhị phân

Ví dụ trên có hai giá trị `mail` nhưng hàm `firstValue` chỉ đọc một. Nếu nghiệp vụ cần toàn bộ email, có thể duyệt các giá trị của `Attribute`:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

static List<String> stringValues(Attributes attrs, String name)
        throws NamingException {
    Attribute attr = attrs.get(name);
    if (attr == null) {
        return List.of();
    }
    List<String> values = new ArrayList<>();
    for (int i = 0; i < attr.size(); i++) {
        values.add((String) attr.get(i));
    }
    return values;
}
```

LDAP attribute đa trị **không mặc nhiên có thứ tự có ý nghĩa**. Khi cần ảnh `jpegPhoto` hoặc attribute nhị phân, JNDI có thể trả `byte[]`, không phải `String`. Phải đối chiếu LDAP schema/syntax và kiểu dữ liệu thực tế thay vì ép mọi `Object` sang `String`.

**Khi AttributesMapper chưa đủ:** nếu directory có cả `uid=lan,ou=people,...` và `uid=lan,ou=contractors,...`, DTO chỉ chứa `uid`/`cn` không nói rõ entry đến từ OU nào. Cần DN để sửa/xóa đúng entry thì nên chọn `ContextMapper`.

## 4. ContextMapper: dùng khi cần DN và ngữ cảnh entry

### 4.1. Hợp đồng và đối tượng thực tế

`ContextMapper<T>` có phương thức:

```java
T mapFromContext(Object context)
        throws javax.naming.NamingException;
```

Giá trị `context` được tạo qua **`DirObjectFactory`** của `ContextSource`. Với factory mặc định `DefaultDirObjectFactory`, Spring LDAP thường truyền vào một `DirContextAdapter`, triển khai `DirContextOperations`.

Một số API tiện dụng của `DirContextOperations`:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getStringAttribute("cn")` | Đọc một giá trị chuỗi của `cn` |
| `getStringAttributes("mail")` | Đọc các giá trị chuỗi của `mail` |
| `getDn()` | DN **tương đối với base của `ContextSource`** |
| `getNameInNamespace()` | Tên đầy đủ của entry trong LDAP namespace |
| `getReferralUrl()` / `isReferral()` | Thông tin referral khi cách xử lý và server có trả |

Nếu ứng dụng có **custom `DirObjectFactory`**, object có thể không phải `DirContextOperations`. Vì vậy, casting trong ví dụ chỉ hợp lệ theo giả định factory mặc định.

### 4.2. Ví dụ: lấy cả DN để định danh

```java
import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

record LocatedPerson(String fullDn, String uid, String fullName) {}

public class PersonWithDnService {
    private final LdapTemplate ldapTemplate;

    public PersonWithDnService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<LocatedPerson> findPeople(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("uid", "cn")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(query,
                (ContextMapper<LocatedPerson>) object -> {
                    DirContextOperations entry =
                            (DirContextOperations) object;
                    return new LocatedPerson(
                            entry.getNameInNamespace(),
                            entry.getStringAttribute("uid"),
                            entry.getStringAttribute("cn"));
                });
    }
}
```

Với Lan, DTO có thể chứa:

```text
fullDn   = uid=lan,ou=people,dc=example,dc=org
uid      = lan
fullName = Nguyen Thi Lan
```

**Đừng nhầm hai cách lấy DN:**

| Phương thức | Ví dụ, với ContextSource base `dc=example,dc=org` |
| --- | --- |
| `entry.getDn()` | `uid=lan,ou=people` |
| `entry.getNameInNamespace()` | `uid=lan,ou=people,dc=example,dc=org` |

Để dựng DN từ input, dùng `LdapNameBuilder`/`LdapName` nhằm xử lý các ký tự đặc biệt theo RFC 4514. **Escape DN** và **escape LDAP filter** là hai quy tắc khác nhau.

### 4.3. Tái sử dụng mapper với `AbstractContextMapper`

Khi nhiều service sử dụng cùng mapping, có thể viết một mapper riêng:

```java
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.support.AbstractContextMapper;

public final class LocatedPersonMapper
        extends AbstractContextMapper<LocatedPerson> {

    @Override
    protected LocatedPerson doMapFromContext(DirContextOperations context) {
        return new LocatedPerson(
                context.getNameInNamespace(),
                context.getStringAttribute("uid"),
                context.getStringAttribute("cn"));
    }
}
```

`AbstractContextMapper` thực hiện phần ép kiểu cho factory mặc định, còn lớp con chỉ cần xử lý `DirContextOperations`. Mapper nên **stateless**, không giữ đối tượng context sau lượt tìm kiếm và không có side effect ngoài ý muốn.

### 4.4. Lưu ý về returning object flag

Một số overload mức thấp nhận `SearchControls`. Khi dùng `ContextMapper` trong luồng tự cấu hình search/callback, **`SearchControls#setReturningObjFlag(true)`** có vai trò quan trọng để đối tượng được trả về có thể được factory chuyển thành context. Những overload `LdapTemplate.search(LdapQuery, ContextMapper<T>)` thông dụng đã phụ trách phần cấu hình cần thiết; không nên giả định giá trị mặc định của JNDI khi tự ghép `SearchControls` và handler cấp thấp.

Việc `ContextMapper` có DN không đòi hỏi tải mọi attribute: `.attributes("uid", "cn")` vẫn giới hạn tập attribute của response.

## 5. Callback: xử lý từng kết quả mà không cần List

### 5.1. Interface callback của Spring LDAP

`NameClassPairCallbackHandler` có phương thức:

```java
void handleNameClassPair(javax.naming.NameClassPair pair)
        throws javax.naming.NamingException;
```

`LdapTemplate` gọi callback một lần cho mỗi phần tử trả về. Với `search(...)` thông thường, phần tử là `javax.naming.directory.SearchResult` (một subtype của `NameClassPair`); các thao tác `list` hoặc `listBindings` có thể truyền kiểu `NameClassPair`/`Binding` khác. Không ép tất cả mọi callback của mọi API sang `SearchResult`.

Callback phù hợp để **đếm**, **tổng hợp**, **kiểm tra chất lượng dữ liệu** hoặc **chuyển từng entry tới consumer**. Khác các overload mapper, overload callback của `search` không tạo `List<T>` để trả về.

### 5.2. Ví dụ: đếm kết quả

Spring LDAP có handler đếm sẵn:

```java
import org.springframework.ldap.core.support.CountNameClassPairCallbackHandler;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson");

CountNameClassPairCallbackHandler counter =
        new CountNameClassPairCallbackHandler();
ldapTemplate.search(query, counter);
int returnedEntries = counter.getNoOfRows();
```

`getNoOfRows()` trả **số entry handler đã nhận**, không phải server-side COUNT và không mặc nhiên bằng tổng số user trong directory. ACL, base/scope, size limit và phân trang có thể làm tập kết quả nhỏ hơn tập dữ liệu thực.

### 5.3. Ví dụ: xử lý từng `SearchResult`

```java
import java.util.function.Consumer;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchResult;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.NameClassPairCallbackHandler;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public class UidProcessor {
    private final LdapTemplate ldapTemplate;

    public UidProcessor(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void forEachUid(Consumer<String> sink) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("uid")
                .where("objectClass").is("inetOrgPerson");

        NameClassPairCallbackHandler handler = pair -> {
            SearchResult result = (SearchResult) pair;
            Attributes attrs = result.getAttributes();
            Attribute uid = attrs.get("uid");
            if (uid != null && uid.size() > 0) {
                sink.accept((String) uid.get());
            }
        };
        ldapTemplate.search(query, handler);
    }
}
```

Trong ví dụ này, `sink` tiêu thụ **giá trị chuỗi độc lập**, không cần giữ `SearchResult` hoặc `DirContext` sau khi search kết thúc.

**Những giới hạn cần hiểu rõ:**

- Callback **không phải reactive stream** và không tự kích hoạt LDAP paging; nó được gọi trong quá trình duyệt kết quả đồng bộ.
- Nếu callback xử lý chậm (ví dụ mỗi entry gọi một HTTP API), context bị giữ lâu và có thể làm các request khác phải chờ pool.
- Nếu callback ném exception ở entry thứ 100, 99 entry trước có thể đã tạo side effect. **Một search không phải transaction** cho tất cả hành động callback.
- Không giữ trực tiếp đối tượng context hoặc `SearchResult` để sử dụng không đồng bộ sau khi search hoàn tất.
- Callback giảm nhu cầu tích lũy `List<T>` nhưng không miễn chi phí server tìm và truyền các entry.

### 5.4. Vòng đời `NamingEnumeration` và `DirContext`

Với các overload tìm kiếm tiêu chuẩn, `LdapTemplate` chịu trách nhiệm mượn `DirContext` từ `ContextSource`, duyệt `NamingEnumeration`, gọi mapper/callback, đóng enumeration và giải phóng context (hoặc trả về pool). Đồng thời Spring LDAP chuyển các lỗi JNDI phổ biến sang hệ phân cấp exception của thư viện.

Vì vậy, **không gọi `close()` trên context được mapper/callback cấp và không giữ context cho thread khác**. Nếu tự dùng JNDI bên ngoài `LdapTemplate`, lập trình viên phải quản lý `NamingEnumeration` và `DirContext` trong `finally`.

## 6. Liên hệ với lookup, repository và ODM

| Phương thức | Khi nào dùng? | Kết quả |
| --- | --- | --- |
| `search(LdapQuery, AttributesMapper<T>)` | Biết filter, cần attributes của nhiều entry | `List<T>` |
| `search(LdapQuery, ContextMapper<T>)` | Biết filter, cần DN và context của nhiều entry | `List<T>` |
| `search(LdapQuery, NameClassPairCallbackHandler)` | Biết filter, muốn xử lý từng kết quả | `void` |
| `lookup(Name, AttributesMapper<T>)` | Đã biết DN, chỉ cần attributes | Một object `T` |
| `lookup(Name, ContextMapper<T>)` | Đã biết DN, cần context | Một object `T` |
| `findByDn(Name, Person.class)` | Có entity ODM và DN | Một entity đã ánh xạ |
| `LdapRepository<Person>` | Thao tác entity theo phương thức repository | Entity hoặc tập entity |

Nếu đã biết **DN chính xác**, dùng `lookup` hoặc `findByDn` thường thể hiện ý định tốt hơn việc search với filter rộng. Nếu chỉ biết `uid`, `mail` hoặc một điều kiện khác, cần search phù hợp.

### 6.1. Ví dụ Spring Data LDAP entity

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(base = "ou=people",
       objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"})
public class Person {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    public Person() {}
    // Getter/setter theo quy ước entity.
}
```

ODM/repository tốt khi nghiệp vụ quản lý trọn entity và CRUD. `AttributesMapper` có thể nhẹ hơn cho API danh bạ chỉ trả `cn`/`mail`; `ContextMapper` phù hợp cho màn hình cần DN để điều hướng hoặc xác định entry cần sửa. Không có yêu cầu toàn bộ service phải dùng cùng một loại mapper, nhưng cần thống nhất **`ContextSource`, base DN, ACL và bảo mật kết nối**.

## 7. Base, scope, filter và thuộc tính trả về

Chọn mapper đúng không cứu được một truy vấn có filter quá rộng hoặc search base sai.

| Cấu hình query | Tác dụng | Lưu ý |
| --- | --- | --- |
| `base("ou=people")` | Chỉ xét nhánh `people` | Tương đối với base của `ContextSource` |
| `searchScope(SearchScope.ONELEVEL)` | Chỉ entry con trực tiếp | Bỏ sót các OU sâu hơn |
| `searchScope(SearchScope.SUBTREE)` | Base và mọi hậu duệ | Có thể trả rất nhiều entry |
| `attributes("uid", "cn")` | Hạn chế dữ liệu được trả | Mapper phải xử lý field không yêu cầu |
| `countLimit(100)` | Giới hạn số kết quả | Không phải paging hay tổng số entry |
| Filter `(uid=lan)` | Tra cứu chính xác | Có thể hưởng lợi từ index equality trên server |

Ví dụ filter an toàn:

```java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(userSuppliedUid);
```

Tránh xây filter bằng chuỗi:

```java
// KHÔNG AN TOÀN: input có thể chứa *, (, ), \ và ký tự đặc biệt.
String filter = "(uid=" + userSuppliedUid + ")";
```

`LdapQueryBuilder` hỗ trợ escape **giá trị LDAP filter** theo cú pháp phù hợp. Nếu cần DN từ input, dùng `LdapNameBuilder` để escape **DN**, không dùng chung hàm escape của filter. Đồng thời, không cho input người dùng tự chọn attribute name hoặc search base tùy ý nếu chưa có allowlist và kiểm soát quyền.

Đối với hàng nghìn kết quả, có thể cân nhắc **paged results control** nếu server hỗ trợ và dùng `DirContextProcessor` trong Spring LDAP để phối hợp xử lý control. Callback **không tự phân trang**, còn `countLimit` có thể cắt mất những kết quả mà nghiệp vụ cần.

## 8. Xử lý an toàn và hiệu năng

### 8.1. Tối thiểu hóa dữ liệu

Một API chỉ cần `cn` và `mail` không nên yêu cầu toàn bộ attributes rồi chuyển tiếp ra ngoài. LDAP ACL là một lớp bảo vệ, nhưng mapper và DTO vẫn phải tuân nguyên tắc **chỉ tải và chỉ xuất bản dữ liệu cần thiết**. Tránh log credential, token hoặc thông tin cá nhân không cần thiết.

### 8.2. Callback không luôn tốt hơn List

Đối với 20 entry, mapper trả `List<Contact>` thường rõ ràng và dễ kiểm thử. Với nhiều entry, callback có thể tránh tích lũy danh sách lớn, nhưng một callback làm thao tác I/O chậm cho từng entry có thể **tăng tổng độ trễ và thời gian chiếm context**. Thử nghiệm cần đo p50/p95/p99, CPU, bộ nhớ, kích thước kết quả và số context active/idle.

### 8.3. Lỗi và tính nhất quán

Một mapper có thể ném `NamingException` khi đọc attribute lỗi, và Spring sẽ xử lý theo luồng exception phù hợp. Callback có side effect có thể dừng giữa chừng khi gặp lỗi mạng hoặc exception từ consumer. Nếu nghiệp vụ phải đồng bộ dữ liệu sang một hệ thống khác, nên thiết kế **idempotency, checkpoint và retry có kiểm soát**; không giả định tất cả kết quả search được xử lý nguyên tử.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| DTO cần DN nhưng mapper chỉ có attributes | Chọn `AttributesMapper` cho yêu cầu định danh | Dùng `ContextMapper` |
| `getDn()` thiếu suffix `dc=example,dc=org` | DN tương đối với base của `ContextSource` | Dùng `getNameInNamespace()` cho DN đầy đủ |
| `ClassCastException` khi ép `DirContextOperations` | Custom `DirObjectFactory` trả kiểu khác | Xác minh factory hoặc dùng mapping tương thích |
| `NullPointerException` ở `attrs.get("mail").get()` | Attribute không tồn tại, không yêu cầu hoặc bị ACL ẩn | Kiểm tra `null` và cấu hình query |
| `mail` có nhiều giá trị nhưng DTO chỉ có một | Gọi `Attribute.get()` hoặc `getStringAttribute` | Duyệt tất cả values nếu cần |
| Đọc `jpegPhoto` như `String` gây lỗi | Thuộc tính binary trả `byte[]` | Dùng kiểu dữ liệu/schema phù hợp |
| Callback trả `void` nhưng code muốn `List<T>` | Chọn sai overload | Dùng mapper hoặc tự thu thập có chủ đích |
| Callback xử lý 100 entry rồi lỗi | Side effect tuần tự, không có transaction chung | Thiết kế retry/idempotency |
| `getNoOfRows()` không bằng tổng số user | Query, size limit, ACL hoặc paging | Chỉ coi đó là số kết quả đã xử lý |
| Search chậm dù không tạo `List<T>` | Server filter không tối ưu hoặc handler chậm | Giới hạn base/scope, index và chi phí callback |
| DTO thiếu `cn` sau khi thêm `attributes("uid")` | Search không yêu cầu `cn` | Điều chỉnh returned attributes |
| Người dùng nhập `*` khiến filter rộng bất ngờ | Ghép chuỗi filter trực tiếp | Dùng `LdapQueryBuilder` |

## 10. Thực hành và kiểm thử

Trên directory test, tạo ba entry giả:

```text
dc=example,dc=org
└── ou=people
    ├── uid=lan   (cn, sn, hai mail)
    ├── uid=minh  (cn, sn, một mail)
    └── uid=mai   (cn, sn, không có mail)
```

Thực hiện:

1. **AttributesMapper:** tìm Lan, tạo DTO `Contact` từ `uid`, `cn`, `mail`; kiểm tra dữ liệu đúng.
2. **Thiếu attribute:** tìm Mai và xác minh mapper không ném `NullPointerException` khi `mail` vắng mặt.
3. **Đa trị:** chuyển hai email của Lan thành danh sách bằng `stringValues(...)`.
4. **ContextMapper:** so sánh `getDn()` và `getNameInNamespace()` với base DN thật.
5. **Callback:** dùng `CountNameClassPairCallbackHandler` để đếm kết quả đã trả; thay `countLimit` để quan sát giới hạn.
6. **Lỗi callback:** giả lập exception sau vài entry và xác minh ứng dụng không xem đó là thao tác đồng bộ hoàn tất.
7. **Filter injection:** thử input có `*`, dấu ngoặc hoặc dấu gạch chéo ngược; bảo đảm builder giữ ngữ nghĩa equality.
8. **Quyền và dữ liệu:** kiểm tra với tài khoản có quyền đọc hạn chế, đảm bảo mapper xử lý attribute không được trả về.
9. **Tải lớn:** so sánh memory và latency giữa mapper trả `List<T>` với callback xử lý từng entry, đồng thời đo thời gian server search.

### Unit test đơn giản cho logic AttributesMapper

```java
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;
import org.springframework.ldap.core.AttributesMapper;

Attributes attrs = new BasicAttributes(true);
attrs.put("uid", "mai");
attrs.put("cn", "Le Thi Mai");

AttributesMapper<Contact> mapper = value ->
        new Contact((String) value.get("uid").get(),
                    (String) value.get("cn").get(),
                    value.get("mail") == null
                            ? null : (String) value.get("mail").get());

Contact contact = mapper.mapFromAttributes(attrs);
// Kỳ vọng: contact.uid() = "mai", contact.email() = null.
```

Đoạn minh họa trên giả định record `Contact` đã được định nghĩa như ở phần trước. Unit test bảo đảm ánh xạ Java đúng, còn **integration test với directory** mới xác minh được DN, search base, schema, ACL, `DirObjectFactory` và kết nối.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** API chỉ trả `cn` và `mail`, không cần DN. Nên dùng API nào?

*Gợi ý:* `AttributesMapper<T>`, giới hạn attributes và xử lý giá trị đa trị đúng yêu cầu.

**Câu 2.** Hai entry cùng có `uid=lan` dưới hai OU. API cần phân biệt hai DN. Chọn gì?

*Gợi ý:* `ContextMapper<T>`, đọc `getNameInNamespace()`.

**Câu 3.** Chỉ cần biết có bao nhiêu entry được một search trả về mà không cần giữ danh sách. Chọn gì?

*Gợi ý:* Callback `CountNameClassPairCallbackHandler`; không nhầm số đã nhận với tổng số entry toàn directory.

**Câu 4.** Callback có tự bật server-side paging không?

*Gợi ý:* Không. Paging cần LDAP controls/`DirContextProcessor` và phải có hỗ trợ từ server.

**Câu 5.** Tại sao `getDn()` đôi khi chỉ trả `uid=lan,ou=people`?

*Gợi ý:* Nó trả DN tương đối với base của `ContextSource`; dùng `getNameInNamespace()` khi cần DN đầy đủ.

**Câu 6.** Nếu `attrs.get("mail")` trả `null`, có thể khẳng định entry không có email không?

*Gợi ý:* Chưa chắc; query có thể không yêu cầu attribute đó, hoặc ACL không cho đọc.

**Câu 7.** Callback đã gửi 50 entry tới API ngoài trước khi exception xảy ra. Cả lần search có rollback không?

*Gợi ý:* Không. Cần thiết kế idempotency và xác minh trạng thái các side effect khi retry.

## 12. Ghi nhớ

- **`AttributesMapper`** dành cho **attribute → DTO**; dùng khi không cần DN và cần xử lý thuộc tính thiếu, đa trị, binary.
- **`ContextMapper`** dành cho **entry context → DTO**; dùng khi cần **DN** hoặc các helper của `DirContextOperations`.
- **`NameClassPairCallbackHandler`** thực hiện một hành động **cho mỗi kết quả**, không trả `List<T>`, không tự paging và không mang lại transaction.
- `LdapTemplate` quản lý vòng đời `DirContext`/`NamingEnumeration`; không giữ context hoặc result sống ngoài callback.
- **Base + scope + filter** quyết định kết quả; chỉ yêu cầu attributes cần thiết và dùng builder an toàn với input.
- Nếu quản lý trọn entity Spring Data LDAP, dùng repository/ODM khi phù hợp; mapper/callback hữu ích khi cần DTO hoặc cách xử lý kết quả chuyên biệt.

**Tài liệu tham khảo:**

- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): các overload `search` và quản lý tài nguyên.
- [Spring LDAP API — AttributesMapper](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/AttributesMapper.html): `mapFromAttributes(Attributes)`.
- [Spring LDAP API — ContextMapper](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/ContextMapper.html): `mapFromContext(Object)` và `DirObjectFactory`.
- [Spring LDAP API — DirContextAdapter](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextAdapter.html): `getDn()` và `getNameInNamespace()`.
- [Spring LDAP API — NameClassPairCallbackHandler](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/NameClassPairCallbackHandler.html): callback từng kết quả.
- [Spring LDAP API — CountNameClassPairCallbackHandler](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/CountNameClassPairCallbackHandler.html): `getNoOfRows()`.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và ODM.
- [RFC 4511](https://www.rfc-editor.org/rfc/rfc4511) và [RFC 4515](https://www.rfc-editor.org/rfc/rfc4515): SearchRequest và LDAP filter.
