# setAttributeValue và setAttributeValues trong DirContextAdapter

Khi ứng dụng Spring LDAP cần tạo hoặc cập nhật một entry, việc sửa thuộc tính trực tiếp bằng JNDI `Attributes`/`ModificationItem` có thể dài dòng: phải xây đúng kiểu giá trị, tính toán thuộc tính nào đổi và gửi các thay đổi lên LDAP server. **`DirContextAdapter`** cung cấp các phương thức tiện ích để thao tác attribute, trong đó **`setAttributeValue(String, Object)`** đặt một giá trị và **`setAttributeValues(String, Object[])`** đặt toàn bộ tập giá trị của một attribute.

Hai phương thức dễ bị dùng nhầm. Ví dụ, muốn **thêm** email thứ hai vào `mail` mà gọi `setAttributeValue("mail", ...)` sẽ đặt lại attribute với một giá trị, thay vì giữ nguyên những giá trị cũ. Ngược lại, khi tạo entry có nhiều `objectClass`, chỉ gọi setter đơn trị sẽ không biểu diễn đủ cấu trúc schema.

Bài này thuộc chương **DirContextAdapter** của module **Spring LDAP**. Trọng tâm là ngữ nghĩa đặt giá trị đơn/nhiều, quá trình tạo và cập nhật entry bằng `LdapTemplate`, cơ chế theo dõi thay đổi, ràng buộc schema và cách kiểm thử thao tác an toàn.

Sau bài học, bạn có thể:

- Phân biệt `setAttributeValue`, `setAttributeValues`, `addAttributeValue` và `removeAttributeValue`.
- Chọn setter phù hợp với attribute đơn trị hoặc nhiều giá trị theo LDAP schema.
- Tạo entry mới bằng `DirContextAdapter` và `LdapTemplate.bind(...)`.
- Đọc entry hiện có bằng `lookupContext(...)`, thay thuộc tính rồi gọi `modifyAttributes(...)`.
- Giải thích `getModificationItems()`, update mode và quy tắc bỏ qua thay đổi thứ tự trên multi-valued attribute.
- Xử lý việc xóa attribute, giá trị null, DN typed value, thuộc tính nhị phân, ACL/TLS và lỗi schema.
- Viết unit test và integration test kiểm tra entry sau khi ghi.

## 1. Dữ liệu mẫu: một entry có thuộc tính đơn và nhiều giá trị

Giả sử LDAP server chứa entry:

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
description: Engineer
mail: lan@example.org
mail: lan.work@example.org
```

Ví dụ này giả định `ContextSource.base = "dc=example,dc=org"`. Khi gọi Spring LDAP, DN của entry tương đối với base context là `uid=lan,ou=people`.

| Attribute | Giá trị trong ví dụ | Cách thao tác phù hợp |
| --- | --- | --- |
| `uid` | `lan` | Thông thường đặt một giá trị theo quy ước ứng dụng |
| `sn` | `Nguyen` | Cần giữ hợp lệ vì `person` yêu cầu `sn` |
| `displayName` | `Lan N.` | Có thể thay toàn bộ bằng một giá trị |
| `description` | `Engineer` | Có thể chứa nhiều giá trị theo schema, dù ví dụ chỉ dùng một |
| `mail` | Hai email | Dùng setter nhiều giá trị nếu muốn thay **toàn bộ tập** |
| `objectClass` | Bốn tên object class | Dùng setter nhiều giá trị khi **tạo** entry |

**Số giá trị hợp lệ do schema quyết định**, không do tên của setter. Một số attribute LDAP cho phép nhiều giá trị; một số được đánh dấu `SINGLE-VALUE`. `setAttributeValue` không thể ép schema đa trị thành đơn trị, cũng như `setAttributeValues` không cho phép đặt nhiều giá trị cho attribute được schema giới hạn một giá trị.

## 2. DirContextAdapter nằm ở đâu trong Spring LDAP?

`DirContextAdapter` thuộc gói `org.springframework.ldap.core` và triển khai `DirContextOperations`. Nó lưu các attribute cùng thông tin DN, có API đọc và sửa attribute, đồng thời có thể tạo danh sách thay đổi phù hợp với JNDI.

```text
Ứng dụng / Repository
         │
         ├─ Tạo mới ── new DirContextAdapter(dn)
         │                       │ setAttributeValue(s)
         │                       ▼
         │                LdapTemplate.bind(ctx)
         │
         └─ Cập nhật ── LdapTemplate.lookupContext(dn)
                                 │
                                 ▼
                         DirContextOperations
                         setAttributeValue(s)
                                 │
                                 ▼
                       getModificationItems()
                                 │
                                 ▼
                    LdapTemplate.modifyAttributes(ctx)
                                 │
                                 ▼
                            LDAP server
```

Trong cấu hình thường dùng, `DefaultDirObjectFactory` của Spring LDAP tạo `DirContextAdapter` khi lookup/search một entry. API trả về `DirContextOperations` để code thao tác ở mức interface.

Phân biệt **thay đổi trong adapter** và **ghi lên server**:

1. Gọi `setAttributeValue(...)` hoặc `setAttributeValues(...)` thay dữ liệu trên object adapter.
2. Khi adapter ở **update mode**, nó ghi nhận sự khác biệt so với thuộc tính ban đầu để cung cấp `ModificationItem[]`.
3. Chỉ khi gọi `ldapTemplate.modifyAttributes(ctx)` (hoặc API modify phù hợp) mới yêu cầu LDAP server cập nhật.
4. Với entry mới, `ldapTemplate.bind(ctx)` tạo entry bằng tập attribute đã điền, không phải cập nhật entry tồn tại.

**Không gọi setter rồi nghĩ LDAP server đã thay đổi ngay.** `DirContextAdapter` là lớp thích nghi/lưu trạng thái thuộc tính; không phải lời gọi ghi từ xa cho từng setter.

## 3. Hai phương thức chính và ý nghĩa khác nhau

### 3.1. setAttributeValue(String name, Object value)

Dùng khi muốn đặt **một giá trị** cho attribute:

```java
context.setAttributeValue("displayName", "Lan Nguyen");
context.setAttributeValue("sn", "Nguyen");
```

Ý nghĩa là đặt attribute có tên tương ứng thành giá trị mới. Nếu attribute trước đó có nhiều giá trị, **không coi đây là hành động thêm một value**. Với attribute cần giữ toàn bộ những giá trị hiện có, phải xác định rõ là đang thay toàn bộ hay thêm một giá trị riêng.

Đối số `value` có kiểu `Object`, vì LDAP/JNDI có attribute giá trị chuỗi, byte array hoặc giá trị kiểu DN. Kiểu dữ liệu thực tế phải tương thích với syntax của attribute trên directory server.

### 3.2. setAttributeValues(String name, Object[] values)

Dùng khi muốn đặt **toàn bộ tập giá trị**:

```java
context.setAttributeValues(
    "mail",
    new String[] {"lan@example.org", "lan.work@example.org"}
);
```

Nếu `mail` đang có `old@example.org`, nhưng mảng mới **không chứa** địa chỉ cũ, adapter sẽ tính toán thay đổi để trạng thái mong muốn là tập giá trị mới. Phương thức này **không phải phép hợp (union) tự động** giữa mảng mới và dữ liệu cũ.

Đặt các giá trị `objectClass` khi tạo entry:

```java
context.setAttributeValues(
    "objectClass",
    new String[] {
        "top",
        "person",
        "organizationalPerson",
        "inetOrgPerson"
    }
);
```

Các object class xác định ràng buộc schema. Với `inetOrgPerson`, bộ dữ liệu mẫu có `cn` và `sn` như yêu cầu từ lớp `person`; `uid`, `mail`, `displayName` là những attribute phù hợp với ví dụ. Tùy server, schema có thể bổ sung ràng buộc khác.

### Bảng so sánh nhanh

| API | Điều muốn diễn đạt | Ví dụ |
| --- | --- | --- |
| `setAttributeValue(name, value)` | Đặt một giá trị mới cho attribute | Đổi `displayName` |
| `setAttributeValues(name, values)` | Đặt **tập giá trị đầy đủ** của attribute | Thay hai email bằng ba email mới |
| `addAttributeValue(name, value)` | **Thêm** một giá trị vào attribute đang có | Thêm một email/phần tử nhóm |
| `removeAttributeValue(name, value)` | **Bỏ** một giá trị cụ thể | Loại một email, giữ email khác |
| `setAttributeValues(name, emptyArray)` | Loại bỏ attribute khỏi tập thuộc tính | Xóa attribute tùy chọn `mail` |

> Tên Java `setAttributeValues` ở số nhiều **không có nghĩa** mọi attribute đều được lưu dưới dạng có thứ tự hoặc cho phép nhiều giá trị. Tính hợp lệ của số lượng, syntax, object class và matching rule vẫn do LDAP schema/server quyết định.

## 4. Phân biệt thay thế toàn bộ với thêm/bớt một value

Ban đầu một entry có:

```ldif
mail: lan@example.org
mail: lan.work@example.org
```

Nếu muốn **thay toàn bộ danh sách** bằng một địa chỉ:

```java
context.setAttributeValues("mail", new String[] {
    "lan.new@example.org"
});
```

Trạng thái mong muốn sau khi ghi là `mail` chỉ có `lan.new@example.org`.

Nếu muốn **giữ hai địa chỉ cũ và thêm một địa chỉ**:

```java
context.addAttributeValue("mail", "lan.other@example.org");
```

Nếu muốn **chỉ bỏ** địa chỉ `lan.work@example.org`:

```java
context.removeAttributeValue("mail", "lan.work@example.org");
```

Nếu gọi:

```java
// KHÔNG phù hợp với yêu cầu "thêm email":
context.setAttributeValue("mail", "lan.other@example.org");
```

thì đó là yêu cầu **đặt attribute thành một value**, không phải giữ nguyên các value hiện có rồi thêm. Đây là lỗi nghiệp vụ dễ xảy ra khi một màn hình chỉ gửi phần dữ liệu thay đổi, còn adapter bị dùng như thao tác “append”.

**Chọn hành vi theo hợp đồng API**:

- Dạng **PUT/replace**: client gửi toàn bộ danh sách email mong muốn → dùng `setAttributeValues`.
- Dạng **add one**: client gửi một email cần thêm → dùng `addAttributeValue`.
- Dạng **remove one**: client gửi một email cần bỏ → dùng `removeAttributeValue`.

Không suy ra danh sách thiếu phần tử là “muốn xóa” nếu client vốn chỉ gửi các giá trị một phần. Ranh giới giữa **không cập nhật**, **thay toàn bộ** và **xóa attribute** phải được mô tả rõ ở tầng nghiệp vụ.

## 5. Xóa một attribute: mảng rỗng và null

Theo hợp đồng của `DirContextAdapter.setAttributeValues`, nếu đối số mảng là `null` hoặc có **độ dài bằng 0**, attribute tương ứng sẽ bị xóa khỏi trạng thái adapter:

```java
// Cách tường minh để bỏ tất cả giá trị mail:
context.setAttributeValues("mail", new String[0]);

// Cũng là yêu cầu xóa attribute theo hợp đồng của setAttributeValues:
context.setAttributeValues("mail", (Object[]) null);
```

Khi adapter là entry đã lookup và ở update mode, thay đổi này được đưa vào danh sách modification để gửi tới server sau `modifyAttributes`. **Xóa một attribute tùy chọn khác với đặt nó thành chuỗi rỗng**:

```java
// Không phải cách biểu diễn "không còn attribute":
context.setAttributeValue("displayName", "");
```

Chuỗi rỗng có thể không hợp lệ theo LDAP syntax, bị server từ chối hoặc mang ngữ nghĩa khác với việc attribute không tồn tại. Không dùng nó thay cho yêu cầu xóa.

Với `setAttributeValue(name, null)`, đừng dựa vào giả định tự phát rằng mọi phiên bản/provider xử lý giống nhau. Nếu nghiệp vụ cần xóa attribute, dùng **`setAttributeValues(name, new Object[0])`** là cách rõ ràng, được mô tả trong API và dễ kiểm thử.

**Không xóa các attribute bắt buộc** như `cn`/`sn` của `person` chỉ vì form gửi giá trị rỗng. Server có thể trả lỗi schema/object class và entry sẽ không được cập nhật như mong muốn.

## 6. Tạo entry mới với setAttributeValue(s) và bind

Ví dụ tạo user mới trong `ou=people,dc=example,dc=org`. Giả sử `ContextSource.base = "dc=example,dc=org"` và entry cha `ou=people` đã tồn tại.

```java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PeopleWriter {
    private final LdapTemplate ldapTemplate;

    public PeopleWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void createPerson(
            String uid, String commonName, String surname,
            String[] emails) {

        if (uid == null || uid.isBlank()
                || commonName == null || commonName.isBlank()
                || surname == null || surname.isBlank()) {
            throw new IllegalArgumentException(
                "uid, commonName and surname are required");
        }
        if (emails == null) {
            throw new IllegalArgumentException("emails must not be null");
        }

        Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", uid)
            .build();

        DirContextAdapter context = new DirContextAdapter(dn);
        context.setAttributeValues("objectClass", new String[] {
            "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        context.setAttributeValue("uid", uid);
        context.setAttributeValue("cn", commonName);
        context.setAttributeValue("sn", surname);
        if (emails.length > 0) {
            context.setAttributeValues("mail", emails);
        }

        ldapTemplate.bind(context);
    }
}
```

Điểm cần hiểu:

1. `LdapNameBuilder` tạo DN đúng cấu trúc và escape giá trị RDN (ví dụ `uid` có dấu phẩy). Tránh ghép chuỗi không kiểm soát thành DN.
2. `new DirContextAdapter(dn)` tạo adapter cho **entry mới**. Tại đây, setter chuẩn bị tập thuộc tính cho `bind`.
3. `setAttributeValues("objectClass", ...)` đặt các object class liên quan. Đây là attribute nhiều giá trị.
4. `setAttributeValue` đặt một giá trị cho `uid`, `cn` và `sn` của entry mẫu.
5. `setAttributeValues("mail", emails)` đặt toàn bộ email nếu mảng không rỗng. Vì `mail` là optional trong ví dụ, mảng rỗng nghĩa là **không thêm attribute mail** lúc tạo.
6. **`ldapTemplate.bind(context)`** mới thực hiện yêu cầu tạo entry. Nếu DN đã tồn tại hoặc schema/ACL không cho phép, server sẽ trả lỗi phù hợp.

**Ví dụ chỉ là một thao tác tạo entry**. Ứng dụng production cần kiểm tra dữ liệu đầu vào (định dạng/giới hạn độ dài, trùng lặp, kích thước), dùng account có quyền tạo trong đúng OU, TLS và cơ chế xử lý lỗi/giám sát.

### Đừng hiểu “đã gọi set” là “đã gửi bind”

Bạn có thể tạo một `DirContextAdapter`, điền hàng chục attribute rồi chưa gọi `bind`: LDAP server lúc đó **chưa có entry mới**. Tương tự, nếu `bind` thất bại, đừng báo thành công chỉ vì các setter trước đó chạy không ném exception.

## 7. Cập nhật entry đã tồn tại bằng lookupContext và modifyAttributes

Với entry đã có trên server, quy trình là:

```text
1. Xác định DN đúng
         ↓
2. ldapTemplate.lookupContext(dn)
         ↓
3. setAttributeValue(s) trên context đang ở update mode
         ↓
4. Context ghi nhận ModificationItem[]
         ↓
5. ldapTemplate.modifyAttributes(context)
         ↓
6. Đọc lại entry để xác minh khi cần
```

Ví dụ Java cập nhật tên hiển thị và **thay toàn bộ** email:

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonUpdateRepository {
    private final LdapTemplate ldapTemplate;

    public PersonUpdateRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void replaceProfile(
            String uid, String newDisplayName, String[] desiredEmails) {

        if (newDisplayName == null || newDisplayName.isBlank()) {
            throw new IllegalArgumentException("displayName is required");
        }
        if (desiredEmails == null) {
            throw new IllegalArgumentException(
                "desiredEmails must be supplied, even when empty");
        }

        Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", uid)
            .build();

        // Đọc entry hiện có và baseline cho modification tracking.
        DirContextOperations context = ldapTemplate.lookupContext(dn);

        context.setAttributeValue("displayName", newDisplayName);
        context.setAttributeValues("mail", desiredEmails);

        // Gửi các thay đổi được adapter tính toán tới server.
        ldapTemplate.modifyAttributes(context);
    }
}
```

Trong phương thức trên, hợp đồng nghiệp vụ là **replace toàn bộ hồ sơ email**:

- `desiredEmails = {"new@example.org"}` → chỉ còn địa chỉ mới (nếu server chấp nhận).
- `desiredEmails = {}` → bỏ attribute `mail`.
- `desiredEmails = null` → **bị từ chối ở tầng ứng dụng**; không vô tình xóa mail khi caller quên gửi trường.

Nếu nghiệp vụ chỉ muốn **bổ sung một email**, dùng `context.addAttributeValue("mail", email)` thay cho `setAttributeValues(...)`.

**Quan trọng:** `lookupContext(dn)` lấy entry ở dạng có thể theo dõi thay đổi; trong cấu hình Spring LDAP mặc định, adapter của entry được lookup ở update mode. Nếu tự khởi tạo adapter từ dữ liệu có sẵn để gửi qua `modifyAttributes`, bạn phải kiểm tra DN và bật `setUpdateMode(true)` đúng cách; không đơn giản lấy `new DirContextAdapter(dn)` rồi xem đó là entry đã đọc từ server.

## 8. Cơ chế theo dõi thay đổi và ModificationItem[]

Một điểm mạnh của `DirContextAdapter` là thực hiện việc tính **chênh lệch thuộc tính**. Với entry ở update mode, adapter có thể ghi nhận các thao tác sửa và tạo một mảng `javax.naming.directory.ModificationItem[]`:

```java
DirContextOperations context = ldapTemplate.lookupContext(dn);
context.setAttributeValue("displayName", "Lan Nguyen");
context.setAttributeValues("mail", new String[] {
    "lan@example.org", "lan.new@example.org"
});

ModificationItem[] changes = context.getModificationItems();
// Mảng changes mô tả phần thay đổi đang chờ gửi lên server.

ldapTemplate.modifyAttributes(context);
```

Đoạn minh họa ở trong class/method đã có `ldapTemplate`, `dn`, đồng thời cần import `javax.naming.directory.ModificationItem`. Hãy xem `changes` như **phần mô tả thay đổi**, không tự khẳng định mảng luôn có một mục `REPLACE_ATTRIBUTE` cho mỗi setter.

Tùy dữ liệu cũ và mới, adapter có thể sinh:

| Kiểu JNDI ModificationItem | Ý nghĩa |
| --- | --- |
| `DirContext.ADD_ATTRIBUTE` | Thêm giá trị/thuộc tính |
| `DirContext.REMOVE_ATTRIBUTE` | Loại giá trị/thuộc tính |
| `DirContext.REPLACE_ATTRIBUTE` | Thay tập giá trị của thuộc tính |

Nếu giá trị mới không khác giá trị hiện tại, adapter có thể **không phát sinh modification** cho attribute đó. Với nhiều giá trị, nó có thể tính **thêm hoặc loại những value thay đổi**, thay vì thay toàn bộ attribute. Cách tính chi tiết phụ thuộc kiểu attribute, equality và cấu hình adapter.

Vì vậy, unit test nên xác minh **trạng thái mong muốn** và chỉ khẳng định loại/count modification khi API đã cam kết rõ. Đừng viết business logic phụ thuộc việc mỗi setter luôn tạo đúng một `ModificationItem`.

### Update mode khác new-entry mode

| Trạng thái | Đặc điểm |
| --- | --- |
| **New entry / bind** | Dựng tập attribute ban đầu bằng setters rồi dùng `bind` |
| **Existing entry / modify** | Đọc baseline, bật update mode, setters được so với giá trị trước để tính chênh lệch |

`setUpdateMode(true)` trên một object **không tự tải dữ liệu cũ** từ server. Muốn cập nhật một entry hiện hữu theo kiểu diff, điểm xuất phát tốt nhất thường là `lookupContext(dn)`.

Một phương thức tên `update()` trên adapter dùng để đồng bộ lại trạng thái nội bộ và quên các modification đã tính; **không được nhầm** nó với lời gọi cập nhật LDAP server. Việc ghi từ xa phải đi qua `modifyAttributes(...)` hoặc API modify tương ứng.

## 9. Thứ tự của multi-valued attribute và orderMatters

LDAP attribute nhiều giá trị **thông thường không bảo đảm thứ tự**. Chẳng hạn:

```ldif
mail: lan@example.org
mail: lan.work@example.org
```

Nếu ứng dụng chỉ đảo thứ tự hai phần tử:

```java
context.setAttributeValues("mail", new String[] {
    "lan.work@example.org", "lan@example.org"
});
```

Theo hợp đồng mặc định của `setAttributeValues(name, values)`, **việc chỉ đổi thứ tự không làm phát sinh thay đổi** khi adapter so sánh trong update mode. Điều đó phù hợp với ngữ nghĩa tập giá trị không có thứ tự.

Spring LDAP còn có overload:

```java
context.setAttributeValues(
    "mail",
    new String[] {"lan.work@example.org", "lan@example.org"},
    true // orderMatters
);
```

Khi đặt `orderMatters = true`, adapter tính thay đổi kể cả khi chỉ đổi thứ tự. **Điều này không bảo đảm LDAP server sẽ lưu/trả giá trị theo thứ tự mới**, và không biến attribute LDAP thông thường thành một danh sách có thứ tự được schema cam kết.

Với `mail` hoặc `cn`, mặc định `orderMatters = false` thường phù hợp hơn. Nếu nghiệp vụ cần một email chính, hãy mô hình hóa rõ thuộc tính/trạng thái ưu tiên; đừng lấy “phần tử đầu tiên” sau khi đọc từ directory.

## 10. Attribute chứa DN và khả năng so sánh bằng Name

Một số thuộc tính, như `member` trong nhiều schema group, chứa **DN của entry khác**. Chuỗi DN có thể khác nhau về chữ hoa/chữ thường hoặc cách escape nhưng vẫn biểu diễn cùng tên theo quy tắc DN.

`DirContextAdapter` hỗ trợ giá trị kiểu `javax.naming.Name` trong các setter/add/remove, và dùng **ngữ nghĩa so sánh DN** khi tính thay đổi. Ví dụ minh họa:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapUtils;

Name memberDn = LdapUtils.newLdapName(
    "uid=lan,ou=people,dc=example,dc=org");

groupContext.addAttributeValue("member", memberDn);
```

Trong đó `groupContext` là một `DirContextOperations` đã lấy từ entry nhóm. API có thể nhận biết một DN khác cách viết nhưng tương đương về tên; nhờ vậy giảm nguy cơ thêm giá trị lặp do khác biệt biểu diễn.

Tuy nhiên:

- Tên attribute `member` và object class của group phải hợp lệ theo schema của LDAP server.
- Truyền `Name` giúp việc so sánh DN, **không bảo đảm** entry được nhắc đến tồn tại hoặc người gọi có quyền sửa group.
- Nếu dữ liệu đang lưu không phải chuỗi DN hợp lệ, một số phép so sánh typed `Name` có thể gây `IllegalArgumentException`.
- DN ở `member` là **giá trị attribute**, khác với DN của chính entry group.

Không dùng so sánh chuỗi Java để áp quy tắc equality của DN trong các trường hợp cần độ chính xác về tên.

## 11. Binary attribute và kiểu Object

Hai setter nhận `Object`/`Object[]`, vì thế chúng không chỉ dành cho chuỗi. Chẳng hạn attribute ảnh `jpegPhoto` có thể chứa dữ liệu nhị phân:

```java
byte[] photoBytes = loadValidatedPhotoBytes();
context.setAttributeValue("jpegPhoto", photoBytes.clone());
```

Đây là đoạn minh họa trong code có phương thức `loadValidatedPhotoBytes()` do ứng dụng tự triển khai; không phải API có sẵn của Spring LDAP.

**Một `byte[]` là một giá trị nhị phân**, không phải mỗi byte là một giá trị của attribute. Cần kiểm soát:

1. Schema có cho phép attribute `jpegPhoto` và đúng object class không?
2. JNDI provider có trả/nhận kiểu `byte[]` như mong đợi không?
3. Dữ liệu ảnh đã được kiểm tra định dạng, kích thước và quyền truy cập chưa?
4. Có cần defensive copy khi truyền hoặc lưu mảng mutable không?
5. Có đang ghi log byte array hoặc dữ liệu cá nhân mà không cần thiết không?

Không chuyển tùy tiện ảnh sang `String` hoặc để dữ liệu nhị phân lớn đi vào mọi truy vấn đọc hồ sơ. Tương tự, các attribute số, thời gian hoặc DN cần tuân theo LDAP syntax/matching rule tương ứng.

## 12. Schema, DN, ACL và những giới hạn khi cập nhật

**Setter trên adapter không vượt qua ràng buộc LDAP server.** Ví dụ:

- `objectClass` cần tương thích với nhau và với các attribute MUST/MAY của entry.
- `SINGLE-VALUE` không cho phép lưu nhiều giá trị như một danh sách.
- Xóa attribute bắt buộc có thể gây lỗi schema.
- Giá trị RDN cần được xử lý đặc biệt khi đổi tên entry.
- ACL có thể cho phép đọc nhưng **không cho phép modify/bind**.
- Attribute operational hoặc server-managed có thể bị từ chối khi client cố ghi.

### Không dùng setter để rename entry

Nếu DN là `uid=lan,ou=people,dc=example,dc=org`, thay:

```java
context.setAttributeValue("uid", "lan2");
```

**không tự chuyển tên entry** thành `uid=lan2,ou=people,...`. Đổi DN/RDN phải dùng thao tác rename/modrdn phù hợp, ví dụ API `LdapTemplate.rename(...)`, đồng thời tuân theo ràng buộc giữ giá trị RDN của server. Không dùng setters như cơ chế đổi vị trí entry.

### Cẩn thận với dữ liệu đọc thiếu

Nếu adapter được tạo từ lookup/search chỉ trả **một số attribute**, dữ liệu không được load có thể bị hiểu là vắng mặt trong baseline. Việc xóa hoặc tính diff cho attribute operational/server-managed có thể không tạo thay đổi như mong đợi, hoặc gây lỗi khi ghi.

Trước khi sửa một attribute:

1. Bảo đảm entry được lookup với đủ attribute liên quan đến thao tác.
2. Xác nhận quyền đọc và ghi của bind account.
3. Không suy ra “không tồn tại attribute” chỉ vì projection/ACL không trả nó.
4. Với operational attribute cần xử lý đặc biệt, cân nhắc overload lookup yêu cầu attribute cụ thể hoặc tạo `ModificationItem[]` rõ ràng theo hợp đồng API.

### Kết nối và đặc tính vận hành

Dùng **LDAPS hoặc StartTLS** đã xác minh chứng chỉ, bảo vệ mật khẩu bind và giới hạn quyền ghi theo OU/attribute. Không ghi mật khẩu, DN nhạy cảm, ảnh hoặc dữ liệu hồ sơ vào log nếu không có lý do nghiệp vụ.

Một lần `modifyAttributes(context)` gửi các thay đổi của entry theo ngữ nghĩa LDAP Modify. Tuy nhiên, **nhiều lần modify trên nhiều entry không tạo thành giao dịch phân tán tự động**. Nếu phải phối hợp cập nhật nhiều entry hoặc hệ thống khác, thiết kế xử lý lỗi/retry phù hợp; không xem thay đổi local trong adapter là bằng chứng server đã commit.

## 13. Unit test setter và cơ chế diff

Các phương thức của `DirContextAdapter` có thể được kiểm thử **không cần LDAP server** bằng JNDI `BasicAttributes` và JUnit 5. Dưới đây là một số test tập trung vào API, không mock network:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.support.LdapNameBuilder;

class DirContextAdapterSetterTest {

    private Name dn() {
        return LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", "lan")
            .build();
    }

    @Test
    void setSingleValueChangesLocalAttribute() {
        DirContextAdapter ctx = new DirContextAdapter(dn());

        ctx.setAttributeValue("displayName", "Lan Nguyen");

        assertEquals("Lan Nguyen",
            ctx.getStringAttribute("displayName"));
    }

    @Test
    void setMultipleValuesKeepsAllValues() {
        DirContextAdapter ctx = new DirContextAdapter(dn());

        ctx.setAttributeValues("mail", new String[] {
            "lan@example.org", "lan.work@example.org"
        });

        assertEquals(
            2, ctx.getStringAttributes("mail").length);
    }

    @Test
    void changingAttributeInUpdateModeCreatesModifications() {
        Attributes attrs = new BasicAttributes(true);
        attrs.put("displayName", "Old Name");

        DirContextAdapter ctx = new DirContextAdapter(attrs, dn());
        ctx.setUpdateMode(true);

        ctx.setAttributeValue("displayName", "New Name");

        assertEquals("New Name",
            ctx.getStringAttribute("displayName"));
        assertTrue(ctx.getModificationItems().length > 0);
    }

    @Test
    void reorderingUnorderedValuesIsNotAChange() {
        Attributes attrs = new BasicAttributes(true);
        Attribute mail = new BasicAttribute("mail");
        mail.add("lan@example.org");
        mail.add("lan.work@example.org");
        attrs.put(mail);

        DirContextAdapter ctx = new DirContextAdapter(attrs, dn());
        ctx.setUpdateMode(true);
        ctx.setAttributeValues("mail", new String[] {
            "lan.work@example.org", "lan@example.org"
        });

        assertEquals(0, ctx.getModificationItems().length);
    }

    @Test
    void emptyArrayRemovesOptionalAttributeLocally() {
        DirContextAdapter ctx = new DirContextAdapter(dn());
        ctx.setAttributeValue("description", "Engineer");

        ctx.setAttributeValues("description", new String[0]);

        assertFalse(ctx.attributeExists("description"));
    }
}
```

Ý nghĩa:

- Test đầu xác nhận setter thay đổi **object trong bộ nhớ**, không xác nhận LDAP đã nhận dữ liệu.
- Test hai xác nhận `setAttributeValues` lưu được tập giá trị nhiều phần tử.
- Test ba tạo adapter có dữ liệu ban đầu và bật update mode, rồi kiểm tra có modification khi giá trị đổi.
- Test bốn xác nhận mặc định không coi **đảo thứ tự** multi-value là thay đổi.
- Test năm kiểm tra loại bỏ attribute tùy chọn bằng mảng rỗng.

Nếu phiên bản Spring LDAP hoặc Java khác, cần chạy test trên dependencies thật của dự án. Các unit test này **không thay thế** kiểm thử schema, ACL, kết nối và dữ liệu trên LDAP server.

## 14. Integration test với directory thử nghiệm

Chuẩn bị một LDAP server thử nghiệm hoặc embedded LDAP có schema phù hợp, entry cha `ou=people,dc=example,dc=org` và tài khoản bind được phép thao tác trên nhánh test. Một bộ kiểm thử tích hợp nên gồm:

1. **Create:** gọi `ldapTemplate.bind(ctx)` với `objectClass` nhiều giá trị, `cn`, `sn`, `uid`; lookup lại và xác minh entry tồn tại.
2. **Replace single:** thay `displayName` bằng `setAttributeValue` rồi `modifyAttributes`, đọc lại giá trị mới.
3. **Replace multi:** thay hai email bằng một email; xác minh email cũ không còn.
4. **Add one:** dùng `addAttributeValue("mail", ...)` và xác minh email cũ vẫn được giữ.
5. **Remove one:** dùng `removeAttributeValue`; xác minh chỉ giá trị được chọn bị loại.
6. **Remove entire optional attribute:** dùng `setAttributeValues("mail", new String[0])` rồi modify, xác minh `mail` vắng mặt.
7. **Schema:** thử đặt nhiều giá trị vào một attribute `SINGLE-VALUE` hoặc xóa `sn`; server phải áp dụng ràng buộc và báo lỗi thích hợp.
8. **DN:** đổi giá trị `uid` bằng setter không được kỳ vọng tự đổi DN; thử rename bằng API đúng trong một test riêng.
9. **ACL/TLS:** user chỉ đọc không sửa được entry; chứng chỉ TLS/bind sai phải gây lỗi, không được báo ghi thành công.
10. **Order:** thay vị trí các giá trị email không được dùng làm kiểm thử thứ tự trả về; so sánh như **tập giá trị**.

Khi kiểm thử các trường hợp lỗi, chỉ dùng OU và dữ liệu **không phục vụ production**. Không cố viết vào directory dùng chung hoặc thực hiện thử nghiệm phá schema trên dữ liệu thật.

## 15. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Muốn thêm email nhưng email cũ biến mất | Dùng `setAttributeValue` hoặc `setAttributeValues` với tập không đầy đủ | Dùng `addAttributeValue` hoặc gửi đủ tập giá trị |
| Gọi setter xong lookup vẫn thấy dữ liệu cũ | Chưa gọi `modifyAttributes` hoặc `bind` thất bại | Phân biệt thay đổi local và ghi lên server |
| `getModificationItems()` rỗng | Giá trị không đổi, đảo thứ tự multi-value hoặc adapter chưa ở update mode | Kiểm tra baseline, mode và giá trị trước/sau |
| Không đổi được `sn`/`cn` | Schema/RDN/ACL không cho phép thay theo cách đó | Kiểm tra MUST, RDN và quyền |
| Đặt `""` để xóa thuộc tính nhưng server từ chối | Chuỗi rỗng khác attribute không tồn tại | Dùng `setAttributeValues(name, new Object[0])` cho attribute optional |
| Xóa attribute bằng mảng rỗng không tác động như dự kiến | Attribute không được load trong baseline hoặc server-managed | Kiểm tra projection/ACL, cân nhắc `ModificationItem` |
| Việc đảo thứ tự mail không được ghi | `setAttributeValues` mặc định bỏ qua thứ tự | Đây thường là hành vi đúng; không giả định LDAP lưu thứ tự |
| Thêm member cùng DN nhưng khác cách viết | Giá trị DN nên so sánh theo tên | Dùng `Name` typed value khi thích hợp |
| `setAttributeValue("uid", ...)` không đổi DN | Setter không phải thao tác rename | Dùng API rename/modrdn |
| Update lỗi dù account đọc được entry | Quyền đọc không có nghĩa quyền sửa | Kiểm tra ACL cho attribute/OU |
| Bind thất bại dù thuộc tính trông đúng | Entry cha thiếu, DN trùng, schema thiếu object class/MUST | Kiểm tra DIT, schema và mã lỗi LDAP |
| Thay `objectClass` làm mất các attribute bắt buộc | Đặt lại danh sách objectClass không hợp lệ | Không cập nhật mù quáng; hiểu schema trước |

Một lỗi cần đặc biệt chú ý khi tích hợp form: **phân biệt trường không xuất hiện và trường được gửi rỗng**. Với yêu cầu patch một profile, không nên gọi `setAttributeValues("mail", new String[0])` chỉ vì request không có key `mail`. Hành động đó sẽ **xóa hết email** khi ứng dụng thực sự muốn giữ nguyên.

## 16. Bài thực hành tự kiểm tra

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
displayName: Mai P.
mail: mai@example.org
mail: mai.team@example.org
```

Giả sử `ContextSource.base = "dc=example,dc=org"` và bạn đã lấy `DirContextOperations ctx = ldapTemplate.lookupContext(dn)`, với `dn = uid=mai,ou=people`.

**Câu 1.** Muốn đổi `displayName` thành `Mai Pham`, nên dùng phương thức nào?

**Câu 2.** Muốn giữ email cũ và thêm `mai.new@example.org`, nên dùng phương thức nào?

**Câu 3.** Muốn thay cả hai email cũ bằng đúng `mai.primary@example.org`, dùng phương thức nào?

**Câu 4.** Muốn xóa hoàn toàn attribute `mail`, lời gọi nào rõ ràng nhất?

**Câu 5.** Sau khi gọi setter trên `ctx`, còn thiếu bước gì để thay đổi được gửi tới LDAP server?

**Câu 6.** Vì sao không nên gọi `setAttributeValue("uid", "mai2")` để đổi DN?

**Câu 7.** Khi đặt lại `objectClass`, vì sao phải giữ các class và attribute phù hợp schema?

**Câu 8.** Nếu đảo vị trí hai email bằng `setAttributeValues` mặc định, có cần phát sinh modification không?

**Câu 9.** Khi thuộc tính `mail` không được trả về lúc lookup, có thể kết luận entry không có email để xóa không?

**Câu 10.** Unit test dùng `DirContextAdapter` tại bộ nhớ có chứng minh LDAP server sẽ chấp nhận sửa attribute không?

### Đáp án và giải thích

1. `ctx.setAttributeValue("displayName", "Mai Pham")`: đặt một giá trị mới.
2. `ctx.addAttributeValue("mail", "mai.new@example.org")`: thêm một value, không thay cả tập.
3. `ctx.setAttributeValues("mail", new String[] {"mai.primary@example.org"})`: đặt tập giá trị đầy đủ mới.
4. `ctx.setAttributeValues("mail", new String[0])`: yêu cầu xóa attribute tùy chọn.
5. Gọi `ldapTemplate.modifyAttributes(ctx)`; setter chỉ chuẩn bị thay đổi trong adapter.
6. Thay giá trị attribute không tự đổi RDN/DN; thao tác rename/modrdn cần API riêng và tuân schema.
7. Schema quyết định objectClass/MUST/MAY, xóa nhầm có thể khiến entry không hợp lệ và bị server từ chối.
8. Không; overload mặc định bỏ qua khác biệt chỉ do thứ tự. LDAP multi-valued attribute thường không có thứ tự được bảo đảm.
9. Không. Attribute có thể bị loại khỏi projection hoặc bị ACL che; cần xác nhận dữ liệu và quyền trước khi xóa.
10. Không. Unit test chỉ kiểm tra hành vi của Java adapter; phải integration test trên server đại diện để xác minh schema, ACL và TLS.

## 17. Tổng kết và tài liệu tham khảo

**`setAttributeValue`** dùng để đặt một giá trị mới cho attribute; **`setAttributeValues`** dùng để đặt **toàn bộ tập giá trị**. Khi muốn thêm hoặc bỏ một giá trị riêng lẻ, hãy dùng `addAttributeValue` hoặc `removeAttributeValue` thay vì vô tình thay toàn bộ tập. Mảng rỗng với `setAttributeValues` là cách rõ ràng để xóa một attribute tùy chọn, trong khi giá trị null từ form phải được xử lý theo hợp đồng nghiệp vụ.

Trong Spring LDAP, `DirContextAdapter` giữ thuộc tính và hỗ trợ tính `ModificationItem[]` khi ở update mode. Tạo entry mới cần `bind`, còn cập nhật entry đã đọc cần `lookupContext` → setters → `modifyAttributes`. Việc ghi dữ liệu vẫn chịu ràng buộc schema, ACL, DN/RDN, kiểu attribute, TLS và hành vi của LDAP server.

Tài liệu tham khảo chính thức:

- [Spring LDAP — Simplifying Attribute Access and Manipulation with DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html): tạo entry, cập nhật và cơ chế tính modification.
- [Spring LDAP — DirContextAdapter API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextAdapter.html): `setAttributeValue`, `setAttributeValues`, update mode và `getModificationItems`.
- [Spring LDAP — DirContextOperations API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextOperations.html): phương thức thay đổi và truy xuất attribute trên context.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `bind`, `lookupContext` và `modifyAttributes`.
- [Spring LDAP — Pooling and Connection Security](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, kết nối bảo mật và quản lý tài nguyên.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): schema, objectClass, attribute type và syntax.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): Bind, Add, Modify, ModifyDN và lỗi server.
