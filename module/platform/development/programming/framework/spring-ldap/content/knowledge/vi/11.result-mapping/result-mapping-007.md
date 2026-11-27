# Xử lý attribute thiếu và attribute đa trị khi mapping kết quả Spring LDAP

## 1. Vì sao đọc được entry nhưng ánh xạ vẫn có thể sai?

Giả sử một ứng dụng **Spring LDAP** tìm được tài khoản trong thư mục LDAP nhưng trả HTTP 500 khi chuyển kết quả thành đối tượng Java:

```java
String email = attributes.get("mail").get().toString();
```

Đoạn mã có hai giả định không an toàn. Thứ nhất, entry **có thuộc tính `mail`** và tài khoản bind được phép nhìn thấy nó. Thứ hai, lấy một giá trị bằng `get()` là đủ. Với các thuộc tính tùy chọn hoặc **đa trị**, hai giả định này dễ dẫn đến kết quả không đầy đủ hoặc lỗi lúc chạy.

Trong LDAP, một entry có thể có:

- Thuộc tính **bắt buộc theo schema** nhưng không được trả về cho client vì quyền đọc hoặc cách chọn returning attributes.
- Thuộc tính **tùy chọn** chưa được lưu, như `mail` của một số người dùng.
- Thuộc tính có **nhiều giá trị**, ví dụ `telephoneNumber` hoặc `description`.
- Thuộc tính vận hành do server quản lý, chẳng hạn `createTimestamp`, thường cần yêu cầu tường minh để nhìn thấy.
- Thuộc tính có giá trị **nhị phân**; không thể mặc nhiên chuyển sang chuỗi bằng `toString()`.

Bài học thuộc chương **Mapping kết quả** trong module **Spring LDAP**. Trọng tâm là đọc `Attributes`, `Attribute` và `NamingEnumeration` đúng cách trong `LdapTemplate`; chọn chính sách cho giá trị thiếu; chuyển thuộc tính đa trị thành collection; dùng `ContextMapper` khi cần DN; và kiểm thử việc truy cập thư mục qua TLS, quyền tối thiểu.

**Sau bài này, bạn có thể:** phân biệt thuộc tính thiếu với search không có entry; hiểu khi nào cần `Attribute.getAll()` thay vì `get()`; triển khai mapper chịu được dữ liệu tùy chọn mà không nuốt lỗi dữ liệu bắt buộc; và kiểm thử tập giá trị độc lập với thứ tự trả về.

## 2. Cấu trúc một kết quả LDAP Search

Với dữ liệu thử nghiệm:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
telephoneNumber: +84 28 1111 2222
telephoneNumber: +84 28 3333 4444
description: active
description: engineering
```

Một entry khác có thể chỉ có:

```ldif
dn: uid=bob,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: bob
cn: Bob Tran
sn: Tran
```

Bob **không có `mail` và `telephoneNumber`**, nhưng vẫn có thể là một entry hợp lệ theo schema `inetOrgPerson` chuẩn. `cn` và `sn` là thuộc tính bắt buộc do kế thừa `person`; điều đó không bảo đảm mọi client đều nhìn thấy chúng trong mọi truy vấn.

Đường đi của kết quả:

```text
LDAP server
   |
   +-- Entry / DN
   |      +-- objectClass: nhiều giá trị
   |      +-- cn: một hoặc nhiều giá trị tùy entry/schema
   |      +-- mail: có thể vắng
   |      +-- telephoneNumber: có thể có nhiều giá trị
   |
   v
LDAP Search result
   |
   +-- Attributes (tập các Attribute được trả về)
   |      |
   |      +-- Attribute.getID()
   |      +-- Attribute.size()
   |      +-- Attribute.get()
   |      +-- Attribute.getAll()
   |
   v
AttributesMapper / ContextMapper
   |
   v
DTO / domain model / API response
```

### 2.1. `Attributes` khác `Attribute`

| Kiểu JNDI | Đại diện cho | Phương thức thường dùng |
| --- | --- | --- |
| `javax.naming.directory.Attributes` | Tập thuộc tính của một entry được trả về | `get("mail")`, `getAll()` |
| `javax.naming.directory.Attribute` | Một loại thuộc tính có thể chứa nhiều giá trị | `getID()`, `size()`, `get()`, `getAll()` |
| `javax.naming.NamingEnumeration` | Tập các phần tử được duyệt từ JNDI | `hasMore()`, `next()`, `close()` |

Khi dùng `AttributesMapper<T>`, mapper nhận `Attributes` của từng entry. Khi dùng `ContextMapper<T>` với `DirContextOperations`, mapper có thể lấy thêm thông tin DN và thực hiện những cách truy cập thuộc tính mà đối tượng context hỗ trợ.

### 2.2. Một entry không đồng nghĩa một giá trị cho mỗi thuộc tính

Trong LDAP, một tên attribute type có thể có **0 hoặc nhiều giá trị** trong dữ liệu ứng dụng được nhìn thấy. Schema có thể ràng buộc một số attribute type là `SINGLE-VALUE`. Nhưng tên trường Java kiểu `String` không tự áp một ràng buộc đơn trị trên LDAP server.

Ngay cả khi ứng dụng mong `uid` có đúng một giá trị, đó có thể là **quy tắc nghiệp vụ bổ sung** chứ không phải điều kiện bảo đảm bởi mọi schema LDAP. Mapper phải chọn cách xử lý khi nhận 0 hoặc nhiều giá trị.

## 3. “Attribute thiếu” có nhiều nguyên nhân khác nhau

Xem mã:

```java
Attribute mail = attributes.get("mail");
if (mail == null) {
    // Không nhận được thuộc tính mail trong tập kết quả.
}
```

Nhận `null` ở đây chỉ chứng minh **trong đối tượng `Attributes` được trả về không có attribute ID `mail`**. Nó *không* cho biết chắc lý do vì sao.

| Nguyên nhân | Ví dụ | Cách điều tra |
| --- | --- | --- |
| Entry thực sự không có thuộc tính tùy chọn | Bob chưa khai báo `mail` | Tra cứu entry/nguồn dữ liệu bằng tài khoản được phép |
| Truy vấn không yêu cầu trả thuộc tính | Query chỉ chọn `uid` và `cn` | Kiểm tra `attributes(...)` và `SearchControls` |
| Tài khoản không có quyền đọc thuộc tính | ACL che `mail` | Đối chiếu bằng tài khoản test có quyền hợp lệ |
| Thuộc tính là loại vận hành | `createTimestamp` có thể không trả về mặc định | Yêu cầu tường minh nếu server hỗ trợ |
| Dữ liệu nằm ngoài base/scope | Entry ở OU con sâu, query dùng one-level | Sửa base/scope; đây là lỗi *không trả entry*, không chỉ thiếu attribute |
| Entry không thỏa filter | `uid=bob` nhưng tìm `uid=alice` | Phân biệt danh sách search rỗng với attribute thiếu |

Do đó, khi mapper nhận `mail == null`, **không tự khẳng định “người dùng không có email”** nếu truy vấn có thể chưa yêu cầu thuộc tính hoặc đang chịu ACL. Một câu trả lời API trung thực cần phản ánh *điều đã quan sát*, không suy diễn nguyên nhân chưa được xác minh.

### 3.1. Ba chính sách ứng dụng dành cho attribute thiếu

Mỗi thuộc tính cần một **hợp đồng dữ liệu**:

1. **Tùy chọn:** `mail` không bắt buộc cho use case; ánh xạ thành `null`, `Optional.empty()` ở lớp tương ứng hoặc một tập rỗng khi DTO định nghĩa là danh sách.
2. **Bắt buộc để xử lý nghiệp vụ:** nếu `uid` hoặc `cn` không được trả về, mapper có thể **báo lỗi dữ liệu/ủy quyền** và không tự đặt giá trị giả.
3. **Chỉ dùng cho hiển thị:** có thể dùng chuỗi placeholder như “Chưa cung cấp” ở **tầng giao diện**, nhưng không ghi placeholder trở lại LDAP và không coi nó là dữ liệu định danh thật.

**Không nên** trả giá trị `""` cho mọi attribute thiếu một cách máy móc. Làm vậy dễ trộn lẫn “không tồn tại”, “không được phép xem” và “bị loại khỏi returning attributes”.

## 4. Lỗi mapping phổ biến và cách sửa

### 4.1. Gọi `get()` trên `null`

**Không an toàn:**

```java
String mail = attributes.get("mail").get().toString();
```

Nếu `get("mail")` trả `null`, mã có thể ném `NullPointerException`. Ngoài ra, với một `Attribute` có 0 giá trị trong một đối tượng JNDI được dựng thủ công, gọi `get()` cũng không phải hành vi cần giả định an toàn.

**Kiểm tra trước khi đọc:**

```java
Attribute mail = attributes.get("mail");
String email = mail == null || mail.size() == 0
        ? null
        : String.valueOf(mail.get());
```

Đoạn này chỉ phù hợp nếu **ứng dụng chấp nhận lấy một giá trị**. Nếu `mail` có nhiều giá trị hợp lệ và nghiệp vụ cần tất cả, phải sử dụng `getAll()`.

### 4.2. `get()` không trả toàn bộ giá trị

**Dễ mất dữ liệu:**

```java
String phone = String.valueOf(
        attributes.get("telephoneNumber").get()
);
```

Nếu có hai số điện thoại, mã trên chỉ lấy **một số**, không trả danh sách đầy đủ. LDAP không bảo đảm thứ tự các giá trị của attribute đa trị theo ý nghĩa nghiệp vụ; không nên chọn “số đầu tiên” làm số chính nếu schema/quy ước tổ chức không định nghĩa rõ cách chọn.

### 4.3. Không mặc định mọi giá trị là `String`

JNDI có thể trả giá trị kiểu `String` hoặc dữ liệu nhị phân (ví dụ `byte[]`), tùy attribute type và provider. Với thuộc tính nhị phân, `String.valueOf(byteArray)` không cho nội dung hữu ích.

Hãy xác định kiểu dựa trên **schema** và cách provider trả dữ liệu. Mapper sau đây được thiết kế riêng cho **các thuộc tính văn bản**; nếu gặp giá trị không phải chuỗi, nó báo lỗi thay vì silently biến giá trị nhị phân thành text.

## 5. Viết hàm dùng lại để đọc toàn bộ giá trị văn bản

Một helper duy nhất giúp các mapper xử lý `null`, nhiều giá trị và vòng đời `NamingEnumeration` nhất quán.

```java
import java.util.ArrayList;
import java.util.List;

import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

public final class LdapTextValues {
    private LdapTextValues() {
    }

    public static List<String> all(Attributes attributes, String name)
            throws NamingException {

        Attribute attribute = attributes.get(name);
        if (attribute == null || attribute.size() == 0) {
            return List.of();
        }

        List<String> values = new ArrayList<>();
        NamingEnumeration<?> enumeration = attribute.getAll();

        try {
            while (enumeration.hasMore()) {
                Object value = enumeration.next();

                if (!(value instanceof String)) {
                    throw new IllegalArgumentException(
                            "Expected text LDAP attribute: " + name
                    );
                }

                values.add((String) value);
            }
        } finally {
            enumeration.close();
        }

        return List.copyOf(values);
    }

    public static String oneOrNull(Attributes attributes, String name)
            throws NamingException {
        List<String> values = all(attributes, name);

        if (values.isEmpty()) {
            return null;
        }
        if (values.size() != 1) {
            throw new IllegalStateException(
                    "Expected at most one value for: " + name
            );
        }

        return values.get(0);
    }

    public static String exactlyOne(Attributes attributes, String name)
            throws NamingException {
        List<String> values = all(attributes, name);

        if (values.size() != 1) {
            throw new IllegalStateException(
                    "Expected exactly one value for: " + name
            );
        }

        return values.get(0);
    }
}
```

**Ý nghĩa từng hàm:**

- `all(...)` trả **danh sách không null**. Attribute thiếu hoặc không có giá trị trong object đang đọc được biểu diễn là `List.of()`.
- `oneOrNull(...)` phù hợp cho thuộc tính tùy chọn khi **hợp đồng nghiệp vụ chỉ chấp nhận tối đa một giá trị**.
- `exactlyOne(...)` phù hợp cho giá trị **bắt buộc và được ứng dụng yêu cầu đơn trị**. Nếu thiếu hoặc nhiều hơn một giá trị, nó báo lỗi rõ ràng.

**Các ràng buộc đơn trị trong helper là chính sách của ứng dụng**, không phải lời khẳng định rằng những attribute type đó luôn có `SINGLE-VALUE` trong schema LDAP. Nếu schema cho phép nhiều giá trị, chỉ gọi `exactlyOne` khi nghiệp vụ thực sự yêu cầu đúng một.

### 5.1. Vì sao phải đóng NamingEnumeration?

`Attribute.getAll()` trả `NamingEnumeration<?>`. Đây là API JNDI có phương thức `close()`; dùng `try/finally` giúp giải phóng tài nguyên ngay cả khi một giá trị có kiểu sai hoặc việc duyệt phát sinh ngoại lệ.

Với `AttributesMapper`, bạn **không** tự đóng context mà `LdapTemplate` đang quản lý; nhưng enumeration bạn chủ động mở trong helper nên được đóng theo hợp đồng JNDI.

### 5.2. Danh sách đa trị có thứ tự không?

Một LDAP attribute đa trị về nguyên tắc là **tập các giá trị không mang thứ tự nghiệp vụ**. `List<String>` ở helper giữ thứ tự mà provider duyệt ra, **không có nghĩa giá trị đầu tiên là giá trị chính** hoặc thứ tự này ổn định giữa các lần truy vấn.

Nếu cần so sánh nội dung của attribute đa trị, hãy so sánh **tập giá trị**. Nếu API hiển thị cần thứ tự ổn định, ứng dụng có thể sắp xếp bản sao theo quy tắc sản phẩm, đồng thời hiểu rằng đó là **thứ tự hiển thị**, không phải thứ tự được server định nghĩa.

## 6. Mapping một entry thành DTO đầy đủ với LdapTemplate

Ví dụ DTO dùng `String` cho UID (ứng dụng yêu cầu một giá trị), các `List<String>` cho thuộc tính có thể đa trị hoặc không có. Một ví dụ phù hợp Java 17:

```java
import java.util.List;

public record DirectoryPerson(
        String uid,
        List<String> commonNames,
        List<String> emails,
        List<String> phoneNumbers) {
}
```

Repository sử dụng `LdapQueryBuilder` để chọn những trường mapper cần đọc:

```java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Repository;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Repository
public class DirectoryPersonRepository {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryPerson> findPeople() {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail", "telephoneNumber")
                .where("objectClass").is("inetOrgPerson");

        return ldapTemplate.search(
                ldapQuery,
                (AttributesMapper<DirectoryPerson>) attributes -> {
                    String uid = LdapTextValues.exactlyOne(
                            attributes, "uid");

                    List<String> names = LdapTextValues.all(
                            attributes, "cn");

                    if (names.isEmpty()) {
                        throw new IllegalStateException(
                                "No visible cn for required name");
                    }

                    List<String> emails = LdapTextValues.all(
                            attributes, "mail");

                    List<String> phones = LdapTextValues.all(
                            attributes, "telephoneNumber");

                    return new DirectoryPerson(
                            uid, names, emails, phones);
                }
        );
    }
}
```

**Giải thích những quyết định mapping:**

1. `.attributes("uid", "cn", "mail", "telephoneNumber")` yêu cầu các thuộc tính mapper thực sự dùng. Nếu bỏ `mail` khỏi danh sách này, mapper có thể nhìn thấy `null` dù entry trên server có email.
2. UID được kiểm tra đúng một giá trị theo **hợp đồng của ví dụ**. Trong LDAP thực tế, cần quyết định thế nào là danh tính ứng dụng duy nhất trước khi chọn logic này.
3. `cn` là thuộc tính bắt buộc theo schema `person`, nhưng nếu không được trả về, mapper không tự bịa một tên thay thế. Nó đưa lỗi lên tầng xử lý để kiểm tra returning attributes/ACL.
4. `mail` và `telephoneNumber` là danh sách; nếu không được trả về, danh sách rỗng giúp tránh NPE, nhưng **chưa chứng minh trên server không có giá trị**.
5. `AttributesMapper` chỉ ánh xạ mỗi entry, không quyết định số entry khớp. `LdapTemplate.search` trả một `List<DirectoryPerson>` và bản thân search cũng có thể trả 0, 1 hoặc nhiều entry.

Ví dụ minh họa thuộc tính chuẩn, chưa có validation domain về kiểu số điện thoại, độ dài tên, email hoặc việc phân quyền hiển thị dữ liệu cá nhân. Các lớp `LdapClient`/ODM cũng phải xử lý tương đương nếu model Java không khớp số lượng giá trị từ LDAP.

## 7. Tìm đúng DN và mapping với ContextMapper

Đôi khi ứng dụng cần **DN của entry** để gọi `lookup`, `modifyAttributes` hoặc phân biệt hai user cùng UID ở hai OU. DN là một tên entry, **không phải thuộc tính người dùng `cn` hay `uid`**.

Với Spring LDAP, `ContextMapper<T>` có thể truy cập `DirContextOperations`, bao gồm thông tin DN và Attributes của entry:

```java
import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

record PersonLocator(String relativeDn, List<String> names) {}

class PersonLocatorRepository {
    private final LdapTemplate template;

    PersonLocatorRepository(LdapTemplate template) {
        this.template = template;
    }

    List<PersonLocator> findLocators(String uid) {
        LdapQuery q = query()
                .base("ou=people")
                .where("uid").is(uid);

        return template.search(q,
                (ContextMapper<PersonLocator>) context -> {
                    DirContextOperations entry =
                            (DirContextOperations) context;

                    return new PersonLocator(
                            entry.getDn().toString(),
                            LdapTextValues.all(
                                    entry.getAttributes(), "cn")
                    );
                });
    }
}
```

`entry.getDn()` trả DN dưới dạng được Spring LDAP cung cấp trong ngữ cảnh. Khi dùng `LdapContextSource` với base, cần phân biệt **DN tương đối của entry trong context** với **DN đầy đủ trên server**; không tự thêm hoặc bỏ hậu tố `dc=example,dc=org` hai lần.

Trong ví dụ này, hãy bổ sung `SearchScope.SUBTREE` khi yêu cầu tìm UID xuyên nhiều OU con; không dựa vào mặc định nếu phạm vi là điều kiện nghiệp vụ quan trọng.

`AttributesMapper` phù hợp khi chỉ cần dữ liệu thuộc tính. `ContextMapper` phù hợp khi cần thêm thông tin entry/context như DN. Hai kiểu mapper không thay thế schema, ACL hoặc cách chọn returning attributes.

## 8. Thuộc tính đa trị và nguyên tắc không gán ý nghĩa cho thứ tự

Một ví dụ đặc biệt là một người dùng có:

```ldif
telephoneNumber: +84 28 1111 2222
telephoneNumber: +84 28 3333 4444
telephoneNumber: +84 28 5555 6666
```

**Câu hỏi nghiệp vụ:** đâu là “số điện thoại chính”? LDAP **không tự trả lời** chỉ vì `Attribute.get()` trả về một số nào đó. Nếu muốn số chính, hệ thống cần schema/thuộc tính riêng, một quy tắc ưu tiên được định nghĩa và đồng thuận, hoặc một nguồn dữ liệu xác định rõ thứ tự ưu tiên.

### 8.1. Trả danh sách hay tập hợp?

| Model Java | Khi nào phù hợp | Lưu ý |
| --- | --- | --- |
| `String` | Nghiệp vụ yêu cầu đúng một giá trị | Phải xử lý 0 hoặc nhiều giá trị |
| `String` nullable / `Optional<String>` | Thuộc tính tùy chọn, tối đa một giá trị theo contract | Không mất thông tin về trạng thái “không nhận được” |
| `List<String>` | API cần trả tất cả giá trị | Không suy thứ tự của list là thứ tự LDAP có ý nghĩa |
| `Set<String>` | Cần membership, loại duplicate theo quy tắc Java | Cần xác định equality/case folding của nghiệp vụ |

LDAP matching rules có thể chuẩn hóa so sánh không giống `String.equals`; vì vậy không đơn giản dùng `HashSet` để kết luận hai LDAP values luôn tương đương theo server. Việc chọn Set chỉ là quyết định biểu diễn ở Java.

### 8.2. So sánh kết quả trong test

**Không nên** kiểm tra phần tử thứ nhất/thứ hai như thể thứ tự có ý nghĩa:

```java
// Dễ sai nếu thứ tự giá trị từ LDAP thay đổi:
assertEquals("+84 28 1111 2222", phones.get(0));
```

**Nên** so sánh tập giá trị khi chỉ quan tâm danh sách các số:

```java
import java.util.Set;

assertEquals(
        Set.of("+84 28 1111 2222", "+84 28 3333 4444"),
        Set.copyOf(phones)
);
```

Trên đây là ví dụ test giả định `phones` và `assertEquals` đã có trong test. Nếu yêu cầu nghiệp vụ có định nghĩa thứ tự hiển thị, sắp xếp **bản sao** sau mapping theo quy tắc rõ ràng rồi kiểm tra thứ tự đó, thay vì dựa vào provider.

## 9. Thuộc tính nhị phân, operational attribute và tên attribute có options

### 9.1. Nhị phân cần mapper khác

Thuộc tính ảnh, chứng chỉ hoặc dữ liệu nhị phân có thể được JNDI trả về dưới dạng `byte[]`. Đừng dùng hàm `LdapTextValues.all` cho chúng hoặc chuyển `byte[]` thành `String` bằng `toString()`. Cần hiểu encoding, quy tắc kích thước, đặc tính nhạy cảm và cách provider cấu hình trả binary attributes.

Ví dụ đọc một giá trị nhị phân khi schema/provider đã thống nhất:

```java
Attribute certificate = attributes.get("userCertificate;binary");

if (certificate != null && certificate.size() > 0) {
    Object value = certificate.get();

    if (value instanceof byte[] bytes) {
        // Xử lý bytes theo định dạng chứng chỉ được ứng dụng hỗ trợ.
        // Không ghi bytes nhạy cảm vào log.
    } else {
        throw new IllegalStateException(
                "Unexpected certificate representation");
    }
}
```

Tên thuộc tính trả về có thể bao gồm **attribute options** (ví dụ `;binary`) và hành vi cụ thể phụ thuộc server/provider. Đừng giả định chỉ một ID được dùng cho mọi directory. Với `BasicAttributes(true)` của JNDI, tên thuộc tính được xử lý không phân biệt hoa thường theo cấu hình object; điều đó không có nghĩa mọi option hoặc loại encoding trở nên tương đương.

### 9.2. Operational attributes thường không được trả về mặc định

Các thuộc tính vận hành như `createTimestamp` hoặc `modifyTimestamp` có thể cần yêu cầu tường minh:

```java
LdapQuery q = query()
        .base("ou=people")
        .attributes("uid", "cn", "createTimestamp")
        .where("uid").is("alice");
```

Một số LDAP server hỗ trợ các selectors `*` (user attributes), `+` (operational attributes) trong danh sách attributes của Search, nhưng quyền hiển thị và cách triển khai có thể khác nhau. Chỉ yêu cầu đúng thông tin cần dùng; tránh đọc mọi thuộc tính có khả năng chứa dữ liệu nhạy cảm khi không cần thiết.

## 10. Bảo mật dữ liệu, escaping và giới hạn truy vấn

Việc xử lý thiếu/đa trị ở mapper là bước **sau khi** truy vấn được server thực hiện. Một mapper phòng thủ không làm cho query đầu vào tự động an toàn.

### 10.1. Cấu hình ContextSource và query tối thiểu

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class DirectoryConfig {
    @Bean
    LdapContextSource contextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String dn,
            @Value("${app.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(dn);
        source.setPassword(password);
        return source;
    }

    @Bean
    LdapTemplate template(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
```

```yaml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
```

Tài khoản bind chỉ đọc nên chỉ có quyền truy cập những thuộc tính cần thiết. Sử dụng **LDAPS với xác minh chứng chỉ và hostname**, hoặc StartTLS được triển khai đúng trước khi gửi mật khẩu. `ldap://` một mình không tự mã hóa kết nối. Không đưa password vào mã nguồn hoặc log.

### 10.2. Filter động phải dùng builder

**Không nên:**

```java
String filter = "(uid=" + clientInput + ")";
```

**Nên:**

```java
LdapQuery q = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn", "mail", "telephoneNumber")
        .where("uid").is(clientInput);
```

Builder xử lý escaping giá trị trong LDAP filter, giúp tránh wildcard và dấu ngoặc biến đầu vào thành điều kiện ngoài ý muốn. Nếu xây DN từ dữ liệu động, dùng `LdapNameBuilder`; escaping DN khác escaping filter.

Với truy vấn subtree lớn, cần chọn base đủ hẹp, filter có tính chọn lọc, danh sách returning attributes cụ thể, time/count limits và paging nếu server hỗ trợ. Một số kết quả có thể bị cắt vì giới hạn; khi đó mapper chỉ nhìn thấy **những entry đã được trả về**, không thể kết luận đã đọc toàn bộ thư mục.

### 10.3. Không ghi toàn bộ Attribute vào log

`Attributes` có thể chứa dữ liệu cá nhân, thuộc tính xác thực hoặc chứng chỉ. Không log toàn bộ entry hoặc mọi `Attribute` khi phát sinh lỗi. Nên ghi loại thao tác, tên thuộc tính được phép ghi log, mã lỗi LDAP, correlation ID và thông tin kỹ thuật đã lược bỏ dữ liệu nhạy cảm.

## 11. Phân loại lỗi: thiếu attribute không phải mọi lỗi LDAP

| Trường hợp | Biểu hiện | Cách hiểu và xử lý |
| --- | --- | --- |
| Search hợp lệ không khớp entry | `List` rỗng | Không có entry được trả về; chưa hề chạy mapper cho entry |
| Entry trả về nhưng thiếu `mail` | `attributes.get("mail") == null` | Thuộc tính không có trong tập được trả; kiểm tra returning attributes, ACL, dữ liệu |
| Attribute có nhiều giá trị | `size() > 1` | Dùng `getAll()` nếu cần toàn bộ |
| Giá trị khác kiểu dự kiến | Không phải `String` | Kiểm tra schema/provider; dùng mapper binary nếu thích hợp |
| Mapper yêu cầu đơn trị, server trả nhiều | `IllegalStateException` từ policy ứng dụng | Chọn lại model, schema hoặc ràng buộc nghiệp vụ |
| LDAP **32 / noSuchObject** | Base hoặc DN không tồn tại/không thể thấy | Kiểm tra base DN và phân quyền |
| LDAP **50 / insufficientAccessRights** | Bind identity thiếu quyền | Kiểm tra ACL; không tự tăng quyền |
| LDAP **3, 4** | Time/size limit exceeded | Truy vấn có thể chưa trả đủ dữ liệu |
| Lỗi TLS, bind hoặc kết nối | Ngoại lệ hạ tầng | Không đổi thành kết quả “không tìm thấy người dùng” |

Spring LDAP giúp chuyển đổi nhiều ngoại lệ JNDI thành hệ ngoại lệ của framework. Mapper cũng có thể ném ngoại lệ do hợp đồng dữ liệu của ứng dụng. Cần phân biệt rõ **lỗi server**, **lỗi truy vấn** và **lỗi ánh xạ** khi đưa thông tin lên service/API.

Khi thiếu một thuộc tính bắt buộc theo nghiệp vụ, tốt hơn là báo một lỗi có kiểm soát và bổ sung kiểm thử, thay vì thầm lặng tạo dữ liệu giả khiến các thao tác sau hoạt động sai.

## 12. Kiểm thử đơn vị cho attribute thiếu và đa trị

Ta có thể kiểm tra helper `LdapTextValues` mà chưa cần LDAP server bằng `BasicAttributes` và `BasicAttribute` của JNDI.

### 12.1. Thuộc tính vắng trả danh sách rỗng

```java
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class LdapTextValuesTest {

    @Test
    void missingOptionalAttributeIsEmpty() throws Exception {
        Attributes attrs = new BasicAttributes(true);

        assertTrue(LdapTextValues.all(attrs, "mail").isEmpty());
        assertNull(LdapTextValues.oneOrNull(attrs, "mail"));
    }
}
```

`BasicAttributes(true)` tạo tập thuộc tính không phân biệt hoa thường theo API JNDI trong test. Đây là kiểm thử Java cho hành vi helper, **chưa chứng minh** LDAP server có quyền đọc `mail` hay schema trả dữ liệu theo mong đợi.

### 12.2. Đọc đủ tập giá trị đa trị

```java
import java.util.Set;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LdapMultiValueTest {

    @Test
    void readsAllPhoneValuesWithoutDependingOnOrder()
            throws Exception {

        Attributes attrs = new BasicAttributes(true);
        Attribute phones = new BasicAttribute("telephoneNumber");
        phones.add("+84 28 1111 2222");
        phones.add("+84 28 3333 4444");
        attrs.put(phones);

        Set<String> actual = Set.copyOf(
                LdapTextValues.all(attrs, "telephoneNumber"));

        assertEquals(Set.of(
                "+84 28 1111 2222",
                "+84 28 3333 4444"
        ), actual);
    }
}
```

Test so sánh Set vì LDAP attribute đa trị không bảo đảm thứ tự theo nghiệp vụ. Với dữ liệu có thể trùng hoặc cần phép so sánh theo matching rule không trùng Java equality, cần điều chỉnh chiến lược so sánh cho đúng use case.

### 12.3. Kiểm tra chính sách bắt buộc đúng một giá trị

```java
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class LdapRequiredValueTest {

    @Test
    void rejectsMissingBusinessIdentifier() {
        Attributes attrs = new BasicAttributes(true);

        assertThrows(IllegalStateException.class,
                () -> LdapTextValues.exactlyOne(attrs, "uid"));
    }
}
```

Đây là policy ứng dụng: **bắt buộc có một UID**. Nếu hệ thống thật cho phép nhiều UID cho cùng entry, cần quyết định mô hình định danh trước khi áp dụng helper đó.

## 13. Kiểm thử tích hợp với LDAP server thực

Unit test của mapper không thể xác nhận schema, ACL, quyền đọc operational attributes hoặc cách JNDI provider chuyển dữ liệu. Cần bổ sung kiểm thử tích hợp trên LDAP **dành cho test**, không dùng tài khoản hay dữ liệu thật.

### 13.1. Dùng ldapsearch để xem trạng thái ban đầu

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(objectClass=inetOrgPerson)" \
  uid cn sn mail telephoneNumber
```

Các tham số `-H`, `-D`, `-W`, `-b` và `-s` lần lượt xác định URL LDAP, bind DN, nhập mật khẩu tương tác, base DN và scope. Chuỗi cuối liệt kê returning attributes.

Nếu ứng dụng dùng `ContextSource` base `dc=example,dc=org`, thì `query().base("ou=people")` tương ứng với `ldapsearch -b "ou=people,dc=example,dc=org"`.

### 13.2. Ma trận kiểm thử

| Ca | Dữ liệu/điều kiện | Kết quả mapper mong đợi |
| --- | --- | --- |
| Alice có email + hai số điện thoại | `telephoneNumber` đa trị | Trả đủ cả hai số, không phụ thuộc thứ tự |
| Bob không có mail | `mail` tùy chọn vắng | Danh sách email rỗng, không NPE |
| Query quên chọn mail | Entry có mail nhưng returning attrs bỏ mail | Mapper không thấy mail; test phát hiện hợp đồng query sai |
| Chỉ yêu cầu `uid`, `cn` | Returning attrs tối thiểu | Không vô tình dựa vào những thuộc tính khác |
| Không có quyền đọc `mail` | ACL hạn chế | Không suy “không có mail” chỉ từ kết quả mapper |
| Không có UID dù contract yêu cầu | Thuộc tính thiếu/không được trả | Mapper báo lỗi dữ liệu hoặc visibility |
| Nhiều UID với contract đơn trị | Trả nhiều giá trị | Mapper báo xung đột hợp đồng |
| Thuộc tính nhị phân | Provider trả `byte[]` | Không chuyển bằng text helper |
| UID nằm trong OU con sâu | Search scope SUBTREE | Tìm đúng entry và mapping |
| Size/time limit thấp | Query bị giới hạn | Không coi số entry đã đọc là tập hoàn chỉnh |
| TLS/credentials sai | Server từ chối kết nối/bind | Lỗi hạ tầng, không thành danh sách rỗng |

Tài khoản dùng để kiểm tra ACL cần được quản trị viên cấp quyền phù hợp; không thay ACL sản xuất để tạo ca test. Các ca test tạo/sửa entry nên có DN riêng và dọn dẹp sau khi chạy, tránh va chạm khi thực thi song song.

## 14. Bài thực hành theo bước

**Bối cảnh:** xây endpoint tra cứu danh bạ, trả `uid`, tên và toàn bộ số điện thoại. Email không bắt buộc, dữ liệu có thể nằm ở nhiều OU con.

1. Chuẩn bị ba entry thử nghiệm: Alice có mail và hai số điện thoại; Bob không có mail/số điện thoại; Carol có một số điện thoại ở OU con `ou=engineering`.
2. Cấu hình `LdapContextSource` với LDAPS đã xác minh chứng chỉ, base DN hợp lệ và reader bind DN.
3. Viết query chọn `uid`, `cn`, `mail`, `telephoneNumber` với `SearchScope.SUBTREE`.
4. Viết helper đọc toàn bộ giá trị của một Attribute và đóng `NamingEnumeration` trong `finally`.
5. Dùng `AttributesMapper<DirectoryPerson>` chuyển kết quả sang DTO có danh sách email/số điện thoại, không giả định giá trị thứ nhất là “chính”.
6. Thử bỏ `mail` khỏi returning attributes. Quan sát mapper không biết mail chưa được lưu hay chưa được yêu cầu; bổ sung test bảo vệ cấu hình query.
7. Tạo ca `uid` thiếu trong `BasicAttributes` để thử policy `exactlyOne`. Không cần cố tạo một entry LDAP sai schema ngoài môi trường test.
8. Thêm `ContextMapper` nếu API cần trả DN và đối chiếu DN tương đối/đầy đủ.
9. So sánh các số điện thoại bằng tập giá trị, không phụ thuộc thứ tự LDAP trả về.
10. Thử tài khoản có quyền đọc hạn chế, server không sẵn sàng và truy vấn vượt limit để xác minh ứng dụng tách lỗi ACL/hạ tầng khỏi dữ liệu tùy chọn vắng mặt.

### Câu hỏi tự kiểm tra

1. `attributes.get("mail") == null` có đủ để khẳng định entry trên server không có mail không?
2. Vì sao gọi `get()` một lần có thể làm mất thông tin ở thuộc tính đa trị?
3. Khi nào nên trả danh sách rỗng, khi nào trả `null` hoặc báo lỗi dữ liệu?
4. Vì sao helper đọc text không được dùng trực tiếp với `byte[]`?
5. `AttributesMapper` và `ContextMapper` khác nhau ở điểm nào?
6. Vì sao không nên dựa vào phần tử thứ nhất trong `telephoneNumber` để xác định số chính?
7. Thuộc tính vận hành như `createTimestamp` có thể cần xử lý riêng trong returning attributes vì sao?
8. Một danh sách kết quả rỗng khác với entry có `mail` rỗng/không được trả thế nào?
9. Vì sao mapper đơn vị vượt qua test không đồng nghĩa ACL của LDAP server đã được kiểm tra?
10. Cần những biện pháp nào để không lộ dữ liệu nhạy cảm trong kết quả và log?

## 15. Ghi nhớ

Trong **Spring LDAP**, ánh xạ một entry cần xử lý cả **thuộc tính không được trả về** và **thuộc tính có nhiều giá trị**. `Attributes.get(name)` có thể trả `null`; nhưng điều đó không tự chứng minh entry thiếu dữ liệu, vì query projection, ACL và loại thuộc tính cũng ảnh hưởng kết quả. `Attribute.get()` chỉ lấy một giá trị, còn `getAll()` cần được duyệt và đóng đúng cách để đọc đủ tập đa trị. Hãy chọn chính sách rõ ràng cho giá trị tùy chọn/bắt buộc, không giả định thứ tự giá trị, và phân biệt text với binary. `AttributesMapper` phù hợp cho thuộc tính; `ContextMapper` hữu ích khi cần thêm DN/context. Kết hợp query trả đúng thuộc tính, TLS đã xác minh, quyền tối thiểu và kiểm thử đơn vị lẫn tích hợp sẽ giúp việc mapping kết quả LDAP chính xác, an toàn và dễ bảo trì.
