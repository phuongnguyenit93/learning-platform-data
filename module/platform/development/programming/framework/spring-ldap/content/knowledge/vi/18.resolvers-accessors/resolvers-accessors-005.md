# Custom ContextMapper cho domain model trong Spring LDAP

Ứng dụng thường làm việc với đối tượng nghiệp vụ như `DirectoryPerson`, `Group` hoặc `Employee`, trong khi dịch vụ thư mục LDAP lưu dữ liệu thành **entry** gồm DN và nhiều thuộc tính (`uid`, `cn`, `mail`, `telephoneNumber`...). Nếu các tầng service liên tục thao tác với `Attributes`, ép kiểu và xử lý `null`, mã nghiệp vụ sẽ khó đọc, khó kiểm thử và bị phụ thuộc vào chi tiết LDAP.

Trong **Spring LDAP**, `ContextMapper<T>` là điểm chuyển một LDAP context thành đối tượng Java tùy ý. Chủ đề này thuộc chương **Resolver và accessor**: bạn sẽ xây một mapper riêng cho domain model, dùng nó trong `LdapTemplate.search` và `lookup`, ánh xạ DN cùng thuộc tính đơn trị/đa trị, xác định quy tắc dữ liệu thiếu và kiểm thử độc lập không cần server.

## 1. Từ LDAP entry tới domain model

Giả sử directory lưu người dùng như sau:

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
telephoneNumber: +84-28-1234-5678
telephoneNumber: +84-90-123-4567
```

Ở tầng ứng dụng, ta muốn nhận một đối tượng có ý nghĩa rõ ràng:

```text
DirectoryPerson
  relativeDn   = "uid=lan,ou=people"
  uid          = "lan"
  displayName  = "Lan Nguyen"
  email        = "lan@example.org"
  phoneNumbers = ["+84-28-1234-5678", "+84-90-123-4567"]
```

Trong ví dụ, `ContextSource` đã cấu hình base DN `dc=example,dc=org`, nên `relativeDn` là DN tương đối với base. Nếu cần DN đầy đủ, phải ghép với base đúng cú pháp LDAP hoặc dùng API lấy tên trong namespace khi context cung cấp thông tin đó.

Luồng xử lý:

```text
LDAP server
    │ entry (DN + attributes)
    ▼
LdapTemplate.search(...) / lookup(...)
    │ tạo context cho từng entry
    ▼
ContextMapper<DirectoryPerson>
    │ đọc DirContextOperations
    │ chuyển đổi và kiểm tra dữ liệu
    ▼
DirectoryPerson (Java domain model)
    │
    ▼
Service / API / UI
```

Một mapper được tái sử dụng ở nhiều phương thức giúp thống nhất cách gọi tên field, chính sách `null` và cách xử lý thuộc tính đa trị.

## 2. ContextMapper, AttributesMapper và ODM khác nhau thế nào?

`ContextMapper<T>` định nghĩa phương thức:

```java
T mapFromContext(Object ctx) throws javax.naming.NamingException;
```

Với `DefaultDirObjectFactory` thường được dùng mặc định, đối tượng `ctx` là `DirContextAdapter`, triển khai `DirContextOperations`. Từ đó có thể đọc cả thuộc tính lẫn DN của entry.

| Cơ chế | Dữ liệu mapper nhận | Dùng khi nào |
| --- | --- | --- |
| `AttributesMapper<T>` | `javax.naming.directory.Attributes` | Chỉ cần một số thuộc tính, không cần DN/context. |
| `ContextMapper<T>` | Object được cung cấp bởi `DirObjectFactory`, thường là `DirContextAdapter` | Cần **DN** và nhiều phép truy cập thuộc tính tiện dụng. |
| `AbstractContextMapper<T>` | Hàm `doMapFromContext(DirContextOperations)` sau khi tự cast context | Muốn tạo lớp mapper riêng, rõ kiểu và tái sử dụng được. |
| **ODM** của Spring LDAP | Entity có annotation `@Entry`, `@Id`, `@Attribute`... | Muốn ánh xạ khai báo bằng annotation và dùng cơ chế quản lý object-directory tương ứng. |

`ContextMapper` cho phép kiểm soát cách map dữ liệu một cách tường minh, phù hợp với domain model không muốn gắn annotation LDAP. `AbstractContextMapper` rất tiện khi dùng object factory mặc định; nếu dự án cấu hình **DirObjectFactory tùy biến** trả về kiểu khác, việc ép sang `DirContextOperations` có thể dẫn đến `ClassCastException`. Khi đó cần mapper phù hợp với kiểu context thực tế.

> **Quy tắc thiết kế:** Mapper làm nhiệm vụ **chuyển dữ liệu một entry thành một domain object**. Các thao tác tìm kiếm, xác thực, phân quyền, ghi LDAP và orchestration nên thuộc service hoặc repository.

## 3. Xây dựng domain model độc lập với LDAP

Trước tiên tạo một class Java chỉ biểu diễn dữ liệu mà ứng dụng cần. Ví dụ dưới đây tương thích với Java 8 trở lên:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public final class DirectoryPerson {
    private final String relativeDn;
    private final String uid;
    private final String displayName;
    private final String email;
    private final List<String> phoneNumbers;

    public DirectoryPerson(
            String relativeDn,
            String uid,
            String displayName,
            String email,
            List<String> phoneNumbers) {
        this.relativeDn = Objects.requireNonNull(relativeDn);
        this.uid = Objects.requireNonNull(uid);
        this.displayName = displayName;
        this.email = email;
        this.phoneNumbers = Collections.unmodifiableList(
                new ArrayList<>(Objects.requireNonNull(phoneNumbers)));
    }

    public String getRelativeDn() {
        return relativeDn;
    }

    public String getUid() {
        return uid;
    }

    public String getDisplayName() {
        return displayName;
    }

    public String getEmail() {
        return email;
    }

    public List<String> getPhoneNumbers() {
        return phoneNumbers;
    }
}
```

Đặc điểm của model:

- Không import lớp Spring LDAP hoặc JNDI; tầng nghiệp vụ chỉ làm việc với kiểu Java thông thường.
- Dùng trường `relativeDn` để diễn đạt rõ đây là DN theo base cấu hình, tránh nhầm với DN đầy đủ.
- `uid` là thuộc tính bắt buộc theo quy tắc của ví dụ; `displayName` và `email` được cho phép `null` để phân biệt thiếu dữ liệu.
- `phoneNumbers` là danh sách bất biến từ góc nhìn caller; không giữ tham chiếu đến mảng hoặc list tạm do mapper tạo.

Với hệ thống thực tế, quy tắc bắt buộc của các trường phải căn cứ schema LDAP **và** nghiệp vụ ứng dụng. Ví dụ `mail` không phải lúc nào cũng bắt buộc trong `inetOrgPerson`, và không nên tự đánh dấu nó là luôn có.

## 4. Viết lớp PersonContextMapper

`AbstractContextMapper<T>` cung cấp phương thức `mapFromContext(Object)` và chuyển sẵn về `DirContextOperations`; lớp tùy biến chỉ cần override `doMapFromContext`.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.support.AbstractContextMapper;

public final class PersonContextMapper
        extends AbstractContextMapper<DirectoryPerson> {

    @Override
    protected DirectoryPerson doMapFromContext(DirContextOperations ctx) {
        String uid = ctx.getStringAttribute("uid");
        if (uid == null || uid.trim().isEmpty()) {
            throw new IllegalStateException(
                    "LDAP entry thiếu uid: " + ctx.getDn());
        }

        String[] phones = ctx.getStringAttributes("telephoneNumber");
        List<String> numbers = phones == null
                ? Collections.emptyList()
                : Arrays.asList(phones);

        return new DirectoryPerson(
                ctx.getDn().toString(),
                uid,
                ctx.getStringAttribute("cn"),
                ctx.getStringAttribute("mail"),
                numbers);
    }
}
```

Với LDIF phía trên, mapper tạo một `DirectoryPerson` có `uid = "lan"`, `displayName = "Lan Nguyen"` và hai số điện thoại.

### 4.1. Vai trò của từng accessor

| Accessor | Kết quả trong ví dụ | Lưu ý |
| --- | --- | --- |
| `ctx.getDn()` | `uid=lan,ou=people` | `Name` tương đối với base đã cấu hình; không tự giả định là DN đầy đủ. |
| `ctx.getStringAttribute("uid")` | `"lan"` | Một giá trị; trả `null` nếu thuộc tính không hiện diện. |
| `ctx.getStringAttribute("cn")` | `"Lan Nguyen"` | Đọc một giá trị; nếu thuộc tính đa trị, không lấy đủ các giá trị bằng cách này. |
| `ctx.getStringAttributes("telephoneNumber")` | Mảng hai chuỗi | Trả `null` nếu thuộc tính không tồn tại; có thể có mảng rỗng ở mức API. |
| `ctx.getObjectAttributes("jpegPhoto")` | Mảng đối tượng, thường chứa `byte[]` | Dùng cho dữ liệu không phải chuỗi; không ép ảnh thành text. |
| `ctx.attributeExists("mail")` | `true` hoặc `false` | Cho biết thuộc tính có trong **context được trả về**, không khẳng định chắc chắn tình trạng trên server nếu thuộc tính chưa được yêu cầu. |

Việc chuyển mảng `telephoneNumber` thành `List` chỉ thực hiện khi dữ liệu không `null`. LDAP đa trị thông thường **không bảo đảm thứ tự mang ý nghĩa nghiệp vụ**, nên không nên xem phần tử `[0]` là số điện thoại chính nếu schema không quy định điều đó.

### 4.2. Vì sao kiểm tra dữ liệu bắt buộc?

Một entry có thể thiếu giá trị vì dữ liệu chưa đồng bộ, schema của máy chủ khác dự kiến, thuộc tính không được yêu cầu trả về hoặc ACL hạn chế quyền đọc. Ví dụ chọn chính sách **fail-fast** nếu thiếu `uid` để không âm thầm tạo domain object không định danh được.

Tùy nghiệp vụ, có thể chọn cách khác:

- Với `mail` không bắt buộc: cho phép `null` hoặc biểu diễn bằng `Optional` ở tầng model.
- Với số điện thoại đa trị không có giá trị: trả danh sách rỗng theo hợp đồng API.
- Với trường định danh bắt buộc `uid` bị thiếu: báo lỗi dữ liệu; tầng service quyết định có dừng cả tác vụ đồng bộ, bỏ qua entry và ghi nhận lỗi, hay cần retry sau khi kiểm tra quyền.

Không tự điền giá trị giả như `"unknown"` cho mã định danh quan trọng; nó có thể làm trùng khóa hoặc dẫn tới liên kết nhầm người dùng.

## 5. Tái sử dụng mapper trong LdapTemplate.search

Một điểm mạnh của `ContextMapper` là dùng cùng một quy tắc map cho mọi entry trả về từ `LdapTemplate.search`.

```java
import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public final class PersonDirectoryRepository {
    private final LdapTemplate ldapTemplate;
    private final ContextMapper<DirectoryPerson> personMapper =
            new PersonContextMapper();

    public PersonDirectoryRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryPerson> findPeople() {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail", "telephoneNumber")
                .countLimit(100)
                .timeLimit(3_000)
                .where("objectClass").is("inetOrgPerson");

        return ldapTemplate.search(query, personMapper);
    }
}
```

Giả sử `ContextSource` đã có base DN `dc=example,dc=org`:

1. `base("ou=people")` chọn nhánh con **tương đối** với base cấu hình.
2. `searchScope(SearchScope.SUBTREE)` tìm các entry trong toàn cây con.
3. `attributes(...)` yêu cầu trả về đúng các thuộc tính mà mapper sử dụng. Nếu không yêu cầu `uid`, phép kiểm tra bắt buộc trong mapper có thể báo lỗi dù entry có `uid` trên server.
4. `countLimit(100)` và `timeLimit(3_000)` kiểm soát chi phí truy vấn, nhưng không chứng minh kết quả là đầy đủ nếu số người nhiều hơn giới hạn hoặc server có quota riêng.
5. `where("objectClass").is("inetOrgPerson")` tạo filter thông qua query builder; cách viết này phù hợp hơn so với nối filter từ dữ liệu người dùng.

Phương thức `search(query, personMapper)` gọi mapper **một lần cho mỗi entry tìm được**, sau đó trả về `List<DirectoryPerson>`. Với cùng một đối tượng mapper không lưu trạng thái nội bộ, việc tái sử dụng giữa các lời gọi được khuyến khích.

**Lưu ý:** Nếu một entry làm mapper ném exception, hoạt động search có thể dừng và không trả danh sách hoàn chỉnh. Với công việc đồng bộ yêu cầu chịu lỗi từng entry, phải thiết kế chính sách kiểm tra, thu thập lỗi và xử lý lại ở tầng phù hợp; không bắt tất cả exception rồi trả object rỗng.

## 6. Tra cứu một entry theo DN với cùng ContextMapper

Khi đã biết `uid`, ứng dụng có thể dựng DN của một entry cụ thể bằng `LdapNameBuilder` và dùng `lookup`:

```java
import javax.naming.Name;

import org.springframework.ldap.support.LdapNameBuilder;

// Thêm vào PersonDirectoryRepository:
public DirectoryPerson findByUid(String uid) {
    if (uid == null || uid.trim().isEmpty()) {
        throw new IllegalArgumentException("uid không được rỗng");
    }

    Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", uid)
            .build();

    return ldapTemplate.lookup(
            dn,
            new String[] {"uid", "cn", "mail", "telephoneNumber"},
            personMapper);
}
```

Ví dụ: `findByUid("lan")` tra cứu entry `uid=lan,ou=people,dc=example,dc=org` nếu `ContextSource` có base `dc=example,dc=org`. `LdapNameBuilder` xử lý các ký tự đặc biệt trong giá trị RDN; không ghép chuỗi `"uid=" + uid + ",ou=people"` từ input trực tiếp.

Vì dùng **cùng `personMapper`**, đối tượng trả về từ `lookup` có cùng cấu trúc và quy tắc xử lý dữ liệu thiếu như từ `search`.

### Lookup khác search ở trường hợp không tìm thấy

| Trường hợp | `ldapTemplate.search(...)` | `ldapTemplate.lookup(dn, ...)` |
| --- | --- | --- |
| Không có entry phù hợp | Thông thường trả danh sách rỗng. | Thường ném `org.springframework.ldap.NameNotFoundException` nếu DN không tồn tại. |
| Có một entry | Trả danh sách một domain object. | Trả một domain object. |
| Có nhiều entry phù hợp | Trả danh sách (trong giới hạn query). | Lookup theo **một DN xác định**, không có nhiều match. |
| Thuộc tính bắt buộc bị thiếu trong entry tìm được | Mapper có thể báo lỗi dữ liệu. | Mapper cũng báo lỗi theo cùng quy tắc. |

Nếu muốn tìm **chính xác một kết quả theo filter** (không biết DN), Spring LDAP còn có `searchForObject(query, mapper)`; nó yêu cầu tập kết quả có đúng một phần tử và sẽ báo `IncorrectResultSizeDataAccessException` khi không phải một kết quả duy nhất.

## 7. Lambda ContextMapper hay lớp mapper riêng?

`ContextMapper<T>` là một functional interface, nên khi mapping rất đơn giản, bạn có thể dùng lambda:

```java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<String> uidMapper = context -> {
    DirContextOperations ctx = (DirContextOperations) context;
    return ctx.getStringAttribute("uid");
};
```

Tuy nhiên, với domain model gồm nhiều field, quy tắc ràng buộc và chuyển đổi dữ liệu, một lớp `PersonContextMapper` thường có lợi hơn:

- **Tái sử dụng:** ánh xạ đồng nhất cho tìm kiếm, lookup và các workflow đọc khác.
- **Độc lập:** logic map không nằm lẫn với xây filter, retry hoặc business logic.
- **Kiểm thử:** có thể truyền một `DirContextAdapter` giả lập để test không cần mạng.
- **Mở rộng:** thêm quy tắc parse số, chuẩn hóa mã hoặc chuyển đổi dữ liệu chuyên biệt mà không sửa mọi câu truy vấn.

Mapper nên **stateless**: không lưu `DirContextOperations` đang xử lý trong một field dùng chung, không giữ `NamingEnumeration` hoặc phụ thuộc vào dữ liệu từ entry trước. Cách này phù hợp khi nhiều thread sử dụng chung repository.

## 8. Kiểm thử mapping không cần LDAP server

Một trong những ưu điểm rõ nhất của custom `ContextMapper` là có thể kiểm tra phép ánh xạ bằng dữ liệu JNDI trong bộ nhớ. Ví dụ JUnit 5 dưới đây có thể đặt vào dự án đã có Spring LDAP và JUnit:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Arrays;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.ldap.LdapName;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;

class PersonContextMapperTest {
    private final PersonContextMapper mapper = new PersonContextMapper();

    @Test
    void mapsDnAndMultiplePhoneNumbers() throws Exception {
        BasicAttributes attrs = new BasicAttributes(true);
        attrs.put("uid", "lan");
        attrs.put("cn", "Lan Nguyen");
        attrs.put("mail", "lan@example.org");

        BasicAttribute phones = new BasicAttribute("telephoneNumber");
        phones.add("+84-28-1234-5678");
        phones.add("+84-90-123-4567");
        attrs.put(phones);

        DirContextAdapter context = new DirContextAdapter(
                attrs, new LdapName("uid=lan,ou=people"));

        DirectoryPerson result = mapper.mapFromContext(context);

        assertEquals("uid=lan,ou=people", result.getRelativeDn());
        assertEquals("lan", result.getUid());
        assertEquals("Lan Nguyen", result.getDisplayName());
        assertEquals("lan@example.org", result.getEmail());
        assertEquals(2, result.getPhoneNumbers().size());
        assertTrue(result.getPhoneNumbers().containsAll(
                Arrays.asList("+84-28-1234-5678", "+84-90-123-4567")));
    }

    @Test
    void missingOptionalAttributesBecomeNullOrEmptyList() throws Exception {
        BasicAttributes attrs = new BasicAttributes(true);
        attrs.put("uid", "minh");

        DirContextAdapter context = new DirContextAdapter(
                attrs, new LdapName("uid=minh,ou=people"));

        DirectoryPerson result = mapper.mapFromContext(context);

        assertNull(result.getEmail());
        assertNull(result.getDisplayName());
        assertTrue(result.getPhoneNumbers().isEmpty());
    }

    @Test
    void missingRequiredUidIsRejected() throws Exception {
        BasicAttributes attrs = new BasicAttributes(true);
        attrs.put("cn", "Không có uid");

        DirContextAdapter context = new DirContextAdapter(
                attrs, new LdapName("cn=missing-uid,ou=people"));

        assertThrows(IllegalStateException.class,
                () -> mapper.mapFromContext(context));
    }
}
```

Lưu ý kiểm tra `phoneNumbers` bằng `containsAll` hoặc so sánh tập hợp khi thích hợp: LDAP không bảo đảm thứ tự có ý nghĩa của các giá trị đa trị, nên test không nên khóa cứng số nào là phần tử thứ nhất.

Đây là **unit test của mapper**, không chứng minh rằng server thật có schema, ACL, search scope hoặc kết nối như kỳ vọng. Cần kiểm thử tích hợp riêng với LDAP thử nghiệm để xác nhận các phần đó.

## 9. Những lỗi thường gặp khi thiết kế custom mapper

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `ClassCastException` khi cast context | Dự án thay `DefaultDirObjectFactory` bằng factory tùy biến trả kiểu khác. | Xác minh kiểu context và viết `ContextMapper` tương thích; không giả định mọi factory đều trả `DirContextAdapter`. |
| `uid`/`mail` bất ngờ là `null` | Thuộc tính không được server trả về, bị ACL ẩn hoặc thật sự vắng mặt. | Yêu cầu đúng thuộc tính trong query, kiểm tra schema và quyền; tách dữ liệu bắt buộc và tùy chọn. |
| Chỉ lấy một số điện thoại | Dùng `getStringAttribute` cho trường đa trị. | Dùng `getStringAttributes` và xử lý trường hợp `null`. |
| Sai DN trong domain object | Nhầm `getDn()` với DN đầy đủ. | Đặt tên field `relativeDn`; quản lý base DN bằng `ContextSource`. |
| Lỗi khi đọc `jpegPhoto` | Cố ép dữ liệu nhị phân thành chuỗi. | Sử dụng `getObjectAttributes` / kiểu `byte[]` và xử lý riêng. |
| Mapper trộn nghiệp vụ hoặc gọi LDAP thêm lần nữa | Mapping mỗi entry gây thêm truy vấn; dễ tạo N+1 và khó test. | Giữ mapper tập trung chuyển dữ liệu; phần tra cứu liên quan do service quyết định. |
| Dùng `memberOf` và coi là luôn tồn tại | Thuộc tính phụ thuộc directory, có thể là operational/constructed và ACL. | Chỉ yêu cầu/ánh xạ khi server hỗ trợ; đặt mặc định theo hợp đồng ứng dụng. |
| Kết quả mapper nhất quán nhưng danh sách không đủ | `countLimit`, time limit hoặc quota server cắt ngắn search. | Kiểm soát giới hạn và dùng phân trang khi cần lấy hết; mapper không quyết định độ đầy đủ truy vấn. |

### Cẩn trọng với DN và attribute có giá trị nhạy cảm

DN có thể chứa tên người dùng hoặc định danh nội bộ; thuộc tính LDAP có thể chứa email, số điện thoại, nhóm quyền, chứng chỉ và dữ liệu xác thực. Chỉ đưa những field ứng dụng thật sự cần vào domain model, tránh log toàn bộ context hoặc thuộc tính nhạy cảm. Việc cấu hình xác thực, LDAPS/StartTLS và phân quyền đọc LDAP nằm ở tầng kết nối và chính sách server, không thuộc trách nhiệm của mapper.

## 10. Thực hành mở rộng

Giả sử yêu cầu API trả danh sách người dùng gồm `uid`, `cn`, email tùy chọn và nhiều số điện thoại.

1. Tạo thêm entry `uid=binh` không có thuộc tính `mail` và `telephoneNumber`. Dùng `PersonContextMapper` xác nhận domain object có email `null` và danh sách điện thoại rỗng.
2. Bỏ `"uid"` khỏi danh sách `attributes(...)` của query. Quan sát mapper phát hiện thiếu trường bắt buộc; bổ sung lại attribute và so sánh.
3. Thay `LdapTemplate.search(...)` bằng `lookup(...)` khi đã biết DN, nhưng giữ nguyên một instance mapper. Kiểm tra hai cách cùng tạo một cấu trúc `DirectoryPerson`.
4. Thử một entry chứa hai giá trị `telephoneNumber` với thứ tự đảo ngược. Kiểm thử nội dung thay vì thứ tự phần tử.
5. Nếu server hỗ trợ, thêm một thuộc tính tùy chọn như `employeeNumber` vào model và mapper, rồi chỉnh returning attributes. Viết test cho cả trường hợp có và thiếu.
6. Giả lập một entry thiếu `uid`. Quyết định chính sách nghiệp vụ: fail-fast hay thu thập lỗi đồng bộ; tránh âm thầm tạo người dùng không có danh tính.

**Câu hỏi tự đánh giá:**

- Khi nào `ContextMapper<T>` phù hợp hơn `AttributesMapper<T>`?
- `ctx.getDn()` là DN đầy đủ hay tương đối với base?
- Vì sao `getStringAttributes("telephoneNumber")` cần kiểm tra `null`?
- Điều gì xảy ra nếu một query chỉ trả về `cn` nhưng mapper yêu cầu `uid`?
- Vì sao `AbstractContextMapper` có thể không dùng được với mọi `DirObjectFactory`?
- Vì sao domain object không nên giữ trực tiếp `DirContextAdapter`?
- Một unit test bằng `BasicAttributes` có kiểm tra được ACL và TLS của server thật không?

## 11. Ghi nhớ

- `ContextMapper<T>` chuyển **mỗi LDAP context thành một domain object**; nó được dùng qua `LdapTemplate.search`, `lookup` và các API truy xuất tương tự.
- Với cấu hình mặc định, `ctx` thường là `DirContextAdapter`; có thể dùng `AbstractContextMapper<T>` và `DirContextOperations` để lấy DN, giá trị đơn trị, đa trị.
- `getDn()` trả DN tương đối với base; phân biệt rõ với DN đầy đủ khi thiết kế domain model.
- Xác định chính sách cho trường **bắt buộc**, **tùy chọn** và **đa trị**; đừng suy ra dữ liệu trên server chỉ từ những attribute đã trả về.
- Đặt quy tắc mapping trong lớp stateless, tái sử dụng cho cả search và lookup, và kiểm thử độc lập bằng `DirContextAdapter` giả lập.
- Custom mapper tập trung xử lý dữ liệu đọc; xác thực, TLS, filter, ACL, paging và ghi entry thuộc các tầng khác của ứng dụng.

## Tài liệu tham khảo

- [Spring LDAP Javadoc — ContextMapper](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/ContextMapper.html)
- [Spring LDAP Javadoc — AbstractContextMapper](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextMapper.html)
- [Spring LDAP Javadoc — DirContextAdapter](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/DirContextAdapter.html)
- [Spring LDAP Javadoc — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP Javadoc — LdapOperations](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html)
- [Spring LDAP FAQ — Operational Attributes](https://docs.spring.io/spring-ldap/reference/faq.html)
