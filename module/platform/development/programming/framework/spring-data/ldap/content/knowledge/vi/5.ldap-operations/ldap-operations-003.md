# Add, Modify, Delete và Modify DN trong LDAP

Trong **Spring Data LDAP**, ứng dụng Java quản lý các entry của dịch vụ thư mục thông qua repository và các API Spring LDAP như `LdapTemplate`. Khác với cơ sở dữ liệu quan hệ, LDAP tổ chức dữ liệu theo **Directory Information Tree (DIT)**, trong đó mỗi entry có **Distinguished Name (DN)** và bộ thuộc tính được schema xác định. Bốn thao tác quan trọng để thay đổi nội dung hoặc cấu trúc cây là **Add**, **Modify**, **Delete** và **Modify DN**.

Bài học giải thích ý nghĩa của từng thao tác ở mức giao thức LDAP, điều kiện thành công, cách gọi bằng Spring LDAP và các lỗi dễ gặp. Mục tiêu là thao tác an toàn với entry đã ánh xạ sang Java, đồng thời hiểu rõ khi nào cần đổi thuộc tính và khi nào phải đổi DN.

Sau bài học, bạn có thể:

- Chỉ ra sự khác nhau giữa tạo entry mới, cập nhật thuộc tính, xóa entry và đổi tên/di chuyển entry.
- Viết các lời gọi `LdapTemplate.bind`, `modifyAttributes`, `unbind` và `rename`.
- Chọn đúng `ADD_ATTRIBUTE`, `REPLACE_ATTRIBUTE` và `REMOVE_ATTRIBUTE` trong JNDI.
- Giải thích các điều kiện về DN cha, `objectClass`, schema, RDN, quyền truy cập và tính nguyên tử.
- Liên hệ thao tác mức thấp với `LdapRepository`, ODM và xây dựng kiểm thử trên directory thử nghiệm.

## 1. Đặt bốn thao tác vào mô hình DIT

Xét một nhánh thư mục:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=staff
└── ou=groups
    └── cn=backend
```

Các nhãn phía trên là **RDN (Relative Distinguished Name)**. Chẳng hạn, DN đầy đủ của Lan là `uid=lan,ou=people,dc=example,dc=org`. Tài khoản hoặc API có thể tìm Lan bằng filter `(uid=lan)`, nhưng filter là **điều kiện truy vấn**, còn DN là **tên xác định một entry**. Các thao tác ghi thường nhắm tới DN, không chỉ tới `uid`.

| Thao tác LDAP | Mục đích | Trước → Sau | Có đổi DN? |
| --- | --- | --- | --- |
| **Add** | Tạo một entry chưa tồn tại | Thêm `uid=mai` dưới `ou=people` | Có DN mới |
| **Modify** | Thay giá trị thuộc tính của entry hiện có | `mail: lan@old.example` → `mail: lan@example.org` | Thường **không** |
| **Delete** | Xóa entry | Xóa entry lá `uid=mai` | DN đó không còn |
| **Modify DN** | Đổi RDN hoặc chuyển entry/subtree sang parent khác | `uid=lan,ou=people,...` → `uid=lan,ou=staff,...` | **Có** |

Một entry có thể có nhiều thuộc tính, chẳng hạn `uid`, `cn`, `sn`, `mail`, `objectClass`; schema quy định thuộc tính nào phải có (MUST), thuộc tính nào được phép (MAY) và kiểu giá trị. Việc API gọi đúng phương thức Java **không** có nghĩa server phải chấp nhận thay đổi: directory còn kiểm tra tên, schema, ràng buộc dữ liệu, ACL và trạng thái cây.

## 2. Đọc nhanh quy tắc chung trước khi ghi dữ liệu

Trong ví dụ, `LdapContextSource` được giả định có base DN:

```text
dc=example,dc=org
```

Do đó `LdapTemplate` thường nhận **DN tương đối** như `uid=lan,ou=people`. Nếu context của ứng dụng có base khác hoặc rỗng, cách tạo DN truyền vào API cũng phải đổi tương ứng.

**Các điều kiện xuyên suốt:**

1. **Đúng DN:** mỗi thao tác làm việc với entry được xác định theo DN. Dựng DN bằng `LdapNameBuilder`, `LdapName` hoặc `Rdn`, thay vì nối chuỗi trực tiếp từ input.
2. **Đúng schema:** entry phải có `objectClass` thích hợp và đáp ứng các yêu cầu MUST/MAY; thuộc tính RDN phải hợp lệ.
3. **Đúng nhánh:** entry cha/naming context phải tồn tại, server phục vụ nhánh đó và cho phép các thao tác liên quan.
4. **Đúng quyền:** tài khoản bind cần quyền tạo con, sửa thuộc tính, xóa entry hoặc đổi DN theo chính sách server; quyền đọc không đồng nghĩa quyền ghi.
5. **Đúng kết nối:** ứng dụng phải bảo vệ thông tin đăng nhập và dữ liệu nhạy cảm qua TLS/LDAPS hợp lệ; không ghi secret vào log.

## 3. Add: tạo entry mới

### 3.1. Ý nghĩa theo LDAP

**Add** yêu cầu server tạo một entry mới với **DN** và tập **attributes** ban đầu. Ví dụ, thêm Mai vào `ou=people`:

```ldif
dn: uid=mai,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: mai
cn: Le Thi Mai
sn: Le
mail: mai@example.org
```

Với schema chuẩn `inetOrgPerson` kế thừa từ `person`, `cn` và `sn` là những thuộc tính bắt buộc. `uid` được dùng làm RDN trong ví dụ và cần phù hợp với naming rule/server. Entry `ou=people,dc=example,dc=org` phải tồn tại trước.

Server thường từ chối Add nếu:

- DN đã tồn tại, chẳng hạn `uid=mai,ou=people,...` đã có entry;
- Parent không tồn tại hoặc nằm ngoài naming context mà server phục vụ;
- Thiếu `objectClass`, `cn`, `sn` hoặc vi phạm schema/naming rule;
- Principal không có quyền tạo entry dưới parent hoặc thêm các thuộc tính yêu cầu;
- Giá trị chứa định dạng, số lượng hoặc ký tự không được schema chấp nhận.

LDAP Add **không giống** thao tác UPSERT mặc định: nếu entry đã tồn tại, thao tác tạo mới phải bị báo lỗi; ứng dụng cần quyết định rõ đó là cập nhật hay xung đột.

### 3.2. Tạo bằng `LdapTemplate.bind`

Trong Spring LDAP, `bind` tương ứng với hành vi tạo entry. Ví dụ Java:

```java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonWriter {
    private final LdapTemplate ldapTemplate;

    public PersonWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void addMai() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "mai")
                .build();

        Attributes attrs = new BasicAttributes(true);
        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attrs.put(classes);
        attrs.put("uid", "mai");
        attrs.put("cn", "Le Thi Mai");
        attrs.put("sn", "Le");
        attrs.put("mail", "mai@example.org");

        ldapTemplate.bind(dn, null, attrs);
    }
}
```

`BasicAttributes(true)` dùng cách tra cứu **không phân biệt hoa/thường với tên thuộc tính** trong đối tượng `Attributes` của JNDI. Nó không thay thế matching rule của LDAP server đối với **giá trị**. Ví dụ định nghĩa `objectClass` đa trị qua `BasicAttribute` giúp server thấy đầy đủ schema class trong thao tác Add.

Đường dẫn `ou=people` được tính tương đối theo base DN cấu hình. `LdapNameBuilder` xử lý escape giá trị trong DN; tránh viết mã kiểu `"uid=" + userInput + ",ou=people"` vì RDN có ký tự đặc biệt phải tuân theo RFC 4514.

### 3.3. Add với `DirContextAdapter` hoặc ODM

Spring LDAP còn có `DirContextAdapter` để xây dựng tập thuộc tính dễ đọc hơn:

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextAdapter;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "mai").build();

DirContextAdapter entry = new DirContextAdapter(dn);
entry.setAttributeValues("objectClass",
        new String[] {"top", "person", "organizationalPerson", "inetOrgPerson"});
entry.setAttributeValue("uid", "mai");
entry.setAttributeValue("cn", "Le Thi Mai");
entry.setAttributeValue("sn", "Le");
entry.setAttributeValue("mail", "mai@example.org");

ldapTemplate.bind(dn, entry, null);
```

Trong mô hình **Spring Data LDAP ODM**, nếu class Java được đánh dấu `@Entry`, field DN có `@Id` và các field thuộc tính được ánh xạ phù hợp, có thể gọi `ldapTemplate.create(person)` hoặc thao tác tạo thông qua repository. Cách tính DN phụ thuộc cấu hình `@Entry(base=...)`, field `@Id` và nếu sử dụng, các `@DnAttribute(index=...)`. Hãy kiểm tra DN cuối cùng trước khi ghi lên directory.

## 4. Modify: thay đổi thuộc tính của entry hiện có

### 4.1. Phân biệt ba kiểu sửa thuộc tính

**Modify** làm việc với **một entry đã tồn tại**, được chọn bằng DN. Một `ModifyRequest` mang **danh sách các thay đổi theo thứ tự**; mỗi thay đổi chỉ rõ tên thuộc tính, loại thao tác và những giá trị liên quan.

| Loại thay đổi LDAP | Hằng số JNDI | Ý nghĩa | Ví dụ |
| --- | --- | --- | --- |
| **Add values** | `DirContext.ADD_ATTRIBUTE` | Thêm giá trị vào attribute hoặc tạo attribute nếu chưa tồn tại | Thêm một giá trị `mail` |
| **Delete values/attribute** | `DirContext.REMOVE_ATTRIBUTE` | Bỏ các giá trị được chỉ định, hoặc toàn attribute nếu không có giá trị | Bỏ địa chỉ email cũ |
| **Replace values** | `DirContext.REPLACE_ATTRIBUTE` | Thay toàn bộ tập giá trị; tập rỗng sẽ xóa attribute theo ngữ nghĩa LDAP | Đặt `mail` mới |

Ở đây cần phân biệt **Add entry** và **ADD_ATTRIBUTE**. Hai thao tác khác cấp độ:

```text
Add entry:     Tạo uid=mai,ou=people,...   (entry mới)
ADD_ATTRIBUTE: Thêm mail=mai@work.example  (entry có sẵn)
```

Với thuộc tính nhiều giá trị như `mail`, **Replace** thường ghi đè **toàn bộ tập giá trị**, chứ không chỉ thay một phần tử. Nếu muốn giữ email còn lại, cần xác định đầy đủ tập giá trị mới hoặc dùng Add/Remove phù hợp. Một số server không cho phép sửa những thuộc tính vận hành do server quản lý như `createTimestamp`, `modifyTimestamp`.

### 4.2. Modify bằng `ModificationItem[]`

Ví dụ thay email và thêm mô tả cho Lan trong **một LDAP Modify operation**:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

ModificationItem[] changes = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "lan@example.org")
    ),
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("description", "Backend engineer")
    )
};

ldapTemplate.modifyAttributes(dn, changes);
```

Nếu attribute `description` được schema cho phép nhưng chưa tồn tại, thao tác Replace có thể tạo nó. Nếu attribute không được phép theo `objectClass`, server báo lỗi schema. Phép Replace một giá trị yêu cầu kiểm tra thuộc tính có phải đa trị hay không, để tránh làm mất dữ liệu khác.

### 4.3. Thêm và xóa *một giá trị* trong thuộc tính nhiều giá trị

Giả sử `mail` đã có hai giá trị, ta muốn thêm một email phụ:

```java
ModificationItem addSecondaryMail = new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("mail", "lan.secondary@example.org"));

ldapTemplate.modifyAttributes(dn,
        new ModificationItem[] {addSecondaryMail});
```

Xóa riêng một email:

```java
ModificationItem removeSecondaryMail = new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("mail", "lan.secondary@example.org"));

ldapTemplate.modifyAttributes(dn,
        new ModificationItem[] {removeSecondaryMail});
```

Xóa **toàn bộ** attribute tùy chọn `description`:

```java
ModificationItem removeDescription = new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("description"));

ldapTemplate.modifyAttributes(dn,
        new ModificationItem[] {removeDescription});
```

Không được xóa `cn` hoặc `sn` nếu đây là giá trị bắt buộc duy nhất của `inetOrgPerson`, và không thể tùy ý xóa giá trị thuộc tính đang tạo nên RDN của entry. Phải tôn trọng quy tắc tên và schema của LDAP server.

### 4.4. Modify qua `DirContextOperations`

Nếu cần sửa vài field của một entry có sẵn mà không muốn tự tính từng `ModificationItem`, Spring LDAP có `DirContextOperations`:

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan").build();

DirContextOperations entry = ldapTemplate.lookupContext(dn);
entry.setAttributeValue("mail", "lan@example.org");
entry.setAttributeValue("description", "Backend engineer");

ldapTemplate.modifyAttributes(entry);
```

`lookupContext` đọc entry hiện tại và tạo adapter theo dõi thay đổi của thuộc tính. `modifyAttributes(entry)` gửi danh sách thay đổi đã tính được. Nếu hai client cùng đọc rồi cùng cập nhật, **lost update** vẫn có thể xảy ra: LDAP ODM không tự cung cấp transaction hoặc optimistic locking như cơ chế `@Version` trong một số ORM. Khi nghiệp vụ cần chống ghi đè đồng thời, kiểm tra khả năng hỗ trợ assertion control/versioning của directory và thiết kế quy tắc xử lý xung đột.

### 4.5. Tính nguyên tử của một Modify

**RFC 4511 yêu cầu toàn bộ danh sách thay đổi của cùng một ModifyRequest được xử lý theo thứ tự và nguyên tử**: nếu server trả lỗi, client có thể kỳ vọng không thay đổi nào trong danh sách được áp dụng; nếu thành công, tất cả đã được áp dụng. Đây là lợi thế của việc gửi hai hoặc ba `ModificationItem` trong **một** lời gọi `modifyAttributes`.

Điều đó **không** có nghĩa:

- Hai lần gọi `modifyAttributes` độc lập tự động gộp thành một transaction.
- Thao tác sửa entry A rồi entry B có rollback chung.
- Nếu kết nối đứt trước khi nhận phản hồi, client biết chắc server đã hay chưa hoàn tất Modify.

Với lỗi mạng làm mất phản hồi, hãy **đọc lại entry** để xác định trạng thái trước khi quyết định retry.

## 5. Delete: xóa một entry

### 5.1. LDAP Delete chỉ xóa entry lá

**Delete** nhắm tới **DN của một entry đã tồn tại**. Theo RFC 4511, thao tác LDAP Delete thông thường chỉ được phép trên **leaf entry**, tức entry **không có con**.

```text
dc=example,dc=org
└── ou=people                  <- Có con: Delete thường bị từ chối
    ├── uid=lan                <- Lá: có thể Delete nếu đủ quyền
    └── uid=minh               <- Lá: có thể Delete nếu đủ quyền
```

Xóa `ou=people` khi còn `uid=lan` và `uid=minh` thường trả về kết quả `notAllowedOnNonLeaf`. Muốn xóa toàn bộ cây con cần cơ chế xóa đệ quy ở phía ứng dụng hoặc extension chuyên biệt do server hỗ trợ; đây là thao tác có hậu quả lớn, phải tách khỏi đường xóa một entry thông thường.

### 5.2. Xóa bằng `LdapTemplate.unbind`

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "mai")
        .build();

ldapTemplate.unbind(dn);
```

`unbind` là tên API JNDI/Spring LDAP tương ứng với việc xóa entry. Nó **không phải** “đăng xuất” hay “LDAP bind lại” của tài khoản. Nếu DN không tồn tại, server sẽ trả lỗi phù hợp; nếu không có quyền xóa, server có thể trả `insufficientAccessRights` hoặc kết quả khác tùy ACL và chính sách tiết lộ thông tin của directory.

Spring LDAP có API xóa đệ quy cho trường hợp đặc biệt (ví dụ overload `unbind(dn, true)` ở những phiên bản hỗ trợ). Không dùng làm mặc định trong tác vụ xóa người dùng vì dễ xóa cả entry con ngoài dự kiến. Một lần xóa lá cũng có thể làm tham chiếu trong các nhóm trở nên không hợp lệ nếu server không tự duy trì tham chiếu.

### 5.3. Các điều cần làm trước và sau Delete

Trước khi xóa entry, xác minh:

- Đúng DN tuyệt đối hoặc DN tương đối theo `ContextSource`; tránh chọn nhầm entry có `uid` giống nhau ở OU khác.
- Entity không còn con, hoặc có quy trình rõ ràng xử lý các entry con.
- Quyền xóa phù hợp, cùng mọi chính sách khóa hoặc bảo vệ tài khoản.
- Quan hệ tham chiếu từ nhóm (`member`/`uniqueMember`), thuộc tính `manager`, ACL và hệ thống ngoài có cần cập nhật.
- Đã xác định đây là **xóa vĩnh viễn** hay chỉ cần vô hiệu hóa/ẩn tài khoản theo nghiệp vụ.

Sau khi Delete thành công, kiểm tra `lookup`/`findById` với DN cũ không còn trả về entry. Nếu ứng dụng có cache riêng hoặc dịch vụ khác giữ bản sao, cần chính sách đồng bộ hoặc invalidation phù hợp.

## 6. Modify DN: đổi RDN hoặc di chuyển entry

### 6.1. Modify DN khác Modify thường

**Modify DN** thay đổi **tên phân biệt** của entry trong cây. Nó có thể:

1. Đổi **RDN** tại cùng parent.
2. Chuyển entry sang **parent mới**, giữ nguyên RDN.
3. Kết hợp đổi RDN và chuyển parent.

Ví dụ đổi RDN:

```text
Trước: uid=lan,ou=people,dc=example,dc=org
Sau:   uid=lan.nguyen,ou=people,dc=example,dc=org
```

Ví dụ chuyển OU:

```text
Trước: uid=lan,ou=people,dc=example,dc=org
Sau:   uid=lan,ou=staff,dc=example,dc=org
```

Thay giá trị của attribute `ou` trên entry người dùng **không** tự chuyển entry sang một parent khác. Vị trí trong DIT được biểu diễn bằng **DN**, do đó cần Modify DN để đổi nhánh.

### 6.2. Các trường của `ModifyDNRequest` theo RFC 4511

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `entry` | DN hiện tại của entry | `uid=lan,ou=people,dc=example,dc=org` |
| `newrdn` | RDN mới, kể cả khi chỉ chuyển parent và RDN không đổi | `uid=lan.nguyen` |
| `deleteoldrdn` | Có xóa các giá trị thuộc tính của RDN cũ khỏi entry hay không | `TRUE` hoặc `FALSE` |
| `newSuperior` (tùy chọn) | DN của parent mới nếu chuyển nhánh | `ou=staff,dc=example,dc=org` |

Với `deleteoldrdn=TRUE`, các giá trị của RDN cũ không còn cần cho RDN mới sẽ bị xóa khỏi attribute của entry (nếu schema cho phép). Với `FALSE`, chúng được giữ lại dưới dạng **giá trị thuộc tính thường**; điều này có thể gây bất ngờ khi đọc lại `uid` có nhiều giá trị. Khi dùng Spring LDAP `rename`, cần kiểm tra cấu hình và hành vi của JNDI provider/server đối với việc giữ hoặc xóa giá trị RDN cũ; API `LdapTemplate.rename(oldDn, newDn)` không phơi bày mọi trường của giao thức như tham số Java riêng biệt.

### 6.3. Đổi DN bằng `LdapTemplate.rename`

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name oldDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

Name newDn = LdapNameBuilder.newInstance("ou=staff")
        .add("uid", "lan")
        .build();

ldapTemplate.rename(oldDn, newDn);
```

Ở ví dụ này, `ou=staff,dc=example,dc=org` phải tồn tại; tài khoản gọi API phải có quyền thích hợp với cả nơi đi và nơi đến. Nếu DN đích đã tồn tại, hoặc server không cho phép di chuyển giữa hai naming context, thao tác sẽ thất bại.

**Không kỳ vọng di chuyển tự do giữa các LDAP server.** RFC 4511 không yêu cầu hỗ trợ mọi chuyển động entry/subtree giữa các DSA hay naming context. Nếu một entry có con, Modify DN có thể làm DN của cả subtree thay đổi theo, nhưng hỗ trợ cho phép di chuyển và các ràng buộc phụ thuộc server.

### 6.4. Các tham chiếu bằng DN sau khi đổi tên

Giả sử nhóm backend có:

```ldif
dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: groupOfNames
cn: backend
member: uid=lan,ou=people,dc=example,dc=org
```

Nếu Lan được chuyển sang `ou=staff`, giá trị `member` trong entry nhóm có thể **vẫn trỏ tới DN cũ**. Một số directory có overlay/plugin tự cập nhật tham chiếu; nhiều directory không có hoặc phải bật chức năng này. Ứng dụng cần xác minh trạng thái thực tế rồi cập nhật các tham chiếu bằng Modify khi cần.

Các trường hợp liên quan khác gồm `manager`, thuộc tính nhóm `uniqueMember`, ứng dụng có cấu hình DN cố định, quyền truy cập dựa trên DN và cache danh tính ngoài LDAP. Tránh giả định rằng Modify DN tự cập nhật mọi quan hệ nghiệp vụ.

## 7. Phân biệt `bind`, `rebind`, `modifyAttributes` và `rename`

Tên API Java có thể gây nhầm, nhất là `bind` khi tài liệu LDAP cũng dùng từ này cho **đăng nhập/xác thực**:

| Spring LDAP API | Ý nghĩa khi quản lý dữ liệu | Nên dùng khi |
| --- | --- | --- |
| `LdapTemplate.bind(dn, ..., attrs)` | Tạo một entry | Add mới với DN chưa tồn tại |
| `LdapTemplate.modifyAttributes(dn, items)` | Modify một entry bằng thay đổi thuộc tính | Update chính xác attribute/value |
| `LdapTemplate.unbind(dn)` | Delete một entry | Xóa entry lá |
| `LdapTemplate.rename(oldDn, newDn)` | Modify DN | Đổi RDN hoặc parent |
| `LdapTemplate.rebind(dn, ..., attrs)` | Thay thế entry hiện có bằng thao tác kiểu unbind/bind | Chỉ dùng nếu thực sự muốn thay nguyên entry và đã hiểu tác động |
| `LdapTemplate.create/update/delete(entity)` | Thao tác ODM với entity `@Entry` | Khi mô hình Java đã ánh xạ đầy đủ, kiểm soát DN và schema |

**Phân biệt hai khái niệm “bind”:** LDAP protocol **Bind operation** dùng xác thực/thiết lập authentication state của phiên, còn phương thức JNDI/Spring `bind(dn, ..., attrs)` là API để **thêm entry**. Đọc chữ `bind` trong tên API phải dựa vào context, không thể kết luận nó luôn là đăng nhập.

### 7.1. Vì sao `rebind` không phải Modify thông thường?

`rebind` là cách thay entry khá thô: có thể loại bỏ các giá trị không được đưa vào object mới và không giữ được hành vi một `ModifyRequest` có danh sách thay đổi nguyên tử. Đặc biệt với entry có operational attributes, nhiều object class hoặc tham chiếu, thay toàn bộ entry có thể làm mất dữ liệu hoặc vi phạm schema. **Ưu tiên `modifyAttributes`** nếu mục tiêu là thay vài attribute.

### 7.2. Thận trọng khi ODM tự tính lại DN

Spring LDAP ODM có các phương thức `create(Object)`, `update(Object)`, `delete(Object)`. Tài liệu API của `LdapTemplate.update(Object)` nêu rằng nếu DN được tính từ `@DnAttribute` khác DN đang lưu, cơ chế này có thể **unbind entry cũ rồi bind entry mới**. Đó không phải luôn là **một Modify DN operation nguyên tử** theo giao thức.

Vì vậy, khi nghiệp vụ yêu cầu **đổi tên hoặc di chuyển entry**, hãy cân nhắc dùng `LdapTemplate.rename` một cách tường minh để server xử lý Modify DN, rồi đọc lại entry và cập nhật các tham chiếu liên quan. Không nên coi sửa `uid` trong object rồi gọi `save` là đủ để chứng minh một phép rename an toàn trong mọi phiên bản/framework.

## 8. Ánh xạ với Spring Data LDAP repository

Ở mức cao hơn, entity ODM có thể như sau:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class Person {
    @Id
    private Name dn;

    @DnAttribute(value = "uid", index = 0)
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String mail;

    public Person() {}
    // Getter/setter tùy phong cách entity của ứng dụng.
}
```

Repository:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {
    List<Person> findByUid(String uid);
}
```

Các thao tác `save(entity)`, `findById(dn)` hoặc `deleteById(dn)` giúp lập trình viên làm việc ở mức object. Nhưng khi cần **phân biệt chính xác thao tác giao thức** và kiểm soát hậu quả của rename, Delete hay Modify giá trị đa trị, `LdapTemplate` vẫn là API trực tiếp, rõ ý nghĩa.

Khi gọi repository, phải hiểu:

- `@Id Name dn` đại diện **DN**, không chỉ chuỗi `uid`.
- `@Entry(base=...)` xác định nhánh gốc của loại entity, không tự bảo đảm parent tồn tại.
- `@Attribute` ánh xạ thuộc tính; server vẫn kiểm tra schema và ACL.
- `@DnAttribute` có thể tham gia tính DN; thay nó có hậu quả lên định danh, không giống sửa `mail`.
- Repository không tự tạo một transaction LDAP bao trùm nhiều entry khi ứng dụng gọi nhiều `save`.

## 9. Tính nguyên tử, idempotency và xử lý lỗi

### 9.1. Một thao tác khác chuỗi nhiều thao tác

LDAP server trả một kết quả cho mỗi yêu cầu Add/Modify/Delete/Modify DN. Trong một **ModifyRequest**, mọi phần tử trong danh sách được thực hiện nguyên tử theo RFC 4511. Nhưng workflow:

```text
Add người dùng → Modify nhóm backend → Modify thuộc tính manager
```

gồm **ba yêu cầu độc lập**. Nếu yêu cầu thứ ba thất bại, hai yêu cầu đầu có thể đã thành công. Không được giả định một `@Transactional` thông thường của cơ sở dữ liệu sẽ rollback cả ba thao tác LDAP. Một số directory hỗ trợ extension giao dịch riêng, nhưng cần xác nhận cả server lẫn client thực sự hỗ trợ, cấu hình và sử dụng.

### 9.2. Retry sau lỗi mạng có thể tạo trạng thái khó đoán

| Thao tác | Khi thử lại mù quáng | Cách tiếp cận an toàn hơn |
| --- | --- | --- |
| Add | Nếu lần đầu đã thành công, lần sau có thể báo `entryAlreadyExists` | Đọc DN đích, đối chiếu nội dung rồi quyết định |
| Modify (ADD value) | Có thể thêm trùng giá trị và nhận `attributeOrValueExists` | Kiểm tra trạng thái hiện tại trước khi retry |
| Modify (REPLACE) | Có thể ghi đè thay đổi hợp lệ mới hơn của client khác | Dùng kiểm soát đồng thời khi cần; đọc/đối chiếu |
| Delete | Nếu lần đầu thành công, lần sau có thể báo `noSuchObject` | Xác minh DN đã vắng mặt và nghiệp vụ cho phép |
| Modify DN | Nếu lần đầu thành công, DN cũ không còn và DN mới tồn tại | Kiểm tra cả DN cũ và DN mới, các tham chiếu liên quan |

Nếu client mất kết nối **sau khi gửi yêu cầu nhưng trước khi nhận response**, client không thể chắc chắn server đã áp dụng thao tác hay chưa. Vì thế, retry phải dựa trên trạng thái directory và ý nghĩa nghiệp vụ, không chỉ dựa vào exception.

### 9.3. Các mã lỗi thường gặp

| Mã lỗi LDAP / tên thường gặp | Ngữ cảnh | Hướng chẩn đoán |
| --- | --- | --- |
| `entryAlreadyExists (68)` | Add/Modify DN đến DN đã có | Kiểm tra DN đích và quy tắc duy nhất theo parent |
| `noSuchObject (32)` | DN hoặc parent không tồn tại | Kiểm tra base DN, suffix và từng entry cha |
| `objectClassViolation (65)` | Thiếu thuộc tính bắt buộc, class không phù hợp | Xem schema, `objectClass`, `cn`/`sn` |
| `namingViolation (64)` | RDN hoặc vị trí entry không hợp lệ | Kiểm tra naming rule, parent và thuộc tính RDN |
| `notAllowedOnNonLeaf (66)` | Delete một entry còn con | Liệt kê hậu duệ và chọn quy trình xóa phù hợp |
| `insufficientAccessRights (50)` | Principal thiếu quyền ghi/đổi DN | Kiểm tra ACL và quyền trên source/destination |
| `attributeOrValueExists (20)` | Thêm giá trị đã tồn tại | Đọc giá trị hiện tại trước khi thêm |
| `noSuchAttribute (16)` | Gỡ giá trị/attribute không tồn tại | Kiểm tra entry đang có những attribute nào |
| `constraintViolation (19)` | Vi phạm ràng buộc giá trị/schema/server | Kiểm tra tính đơn trị, syntax, policy |
| `unwillingToPerform (53)` | Server từ chối do policy/trạng thái | Kiểm tra log, quyền, server capability |

Spring LDAP thường chuyển lỗi JNDI/LDAP thành những ngoại lệ trong hierarchy `org.springframework.ldap`. Khi chẩn đoán, hãy ghi loại ngoại lệ, thao tác, DN mục tiêu và mã LDAP (nếu có), nhưng **không log mật khẩu hoặc giá trị nhạy cảm**.

## 10. Thực hành end-to-end trên directory thử nghiệm

Chuẩn bị một directory test, ví dụ OpenLDAP hoặc một máy chủ LDAP nhúng phù hợp với phiên bản dự án. Cấu hình `LdapContextSource` trỏ vào `dc=example,dc=org` qua LDAPS/TLS nếu cần, tạo trước hai entry cha `ou=people` và `ou=staff`. Dùng một **tài khoản thử nghiệm** có quyền giới hạn trong hai nhánh này. Không chạy ví dụ xóa hoặc di chuyển trên directory sản xuất.

### Bước 1: Add

Tạo `uid=mai,ou=people` với đầy đủ `objectClass`, `uid`, `cn`, `sn`. Sau `bind`, thực hiện `lookup`/`findById` hoặc search tại base tương ứng để xác nhận:

```text
uid=mai,ou=people,dc=example,dc=org
```

### Bước 2: Modify

Dùng `REPLACE_ATTRIBUTE` thay `mail` thành `mai.new@example.org`, rồi kiểm tra đúng giá trị và không mất các attribute bắt buộc. Thêm hai `mail` nếu schema cho phép đa trị, sau đó xóa riêng một giá trị bằng `REMOVE_ATTRIBUTE`.

### Bước 3: Modify DN

Di chuyển Mai từ `ou=people` sang `ou=staff`:

```text
oldDn = uid=mai,ou=people
newDn = uid=mai,ou=staff
```

Gọi `rename`, rồi xác minh **DN cũ không tìm được**, **DN mới tìm được** và các thuộc tính vẫn hợp lệ. Nếu entry có nhóm tham chiếu, kiểm tra cả DN trong `member`.

### Bước 4: Delete

Xóa `uid=mai,ou=staff` sau khi kiểm tra entry không có con. Xác minh DN mới không còn; `ou=staff` và `ou=people` vẫn tồn tại.

### Bước 5: Thử các trường hợp lỗi có chủ đích

- Add cùng DN lần nữa để quan sát `entryAlreadyExists`.
- Add vào parent không tồn tại để quan sát `noSuchObject`.
- Bỏ `sn` khỏi entry `inetOrgPerson` mới để quan sát schema violation.
- Delete một OU còn con để xác nhận server chặn thao tác xóa non-leaf.
- Modify DN đến DN đã tồn tại hoặc parent không có quyền để kiểm tra báo lỗi.
- Ngắt kết nối thử nghiệm đúng lúc gửi request, rồi đọc lại directory thay vì retry mù quáng.

Giới hạn thử nghiệm trong cây dữ liệu giả và phục hồi trạng thái sau mỗi case để những case sau không phụ thuộc vào kết quả case trước.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Lan đã tồn tại với `uid=lan,ou=people,...`. Muốn thay email thì chọn Add, Modify hay Modify DN?

*Đáp án gợi ý:* **Modify**, vì DN giữ nguyên và chỉ đổi thuộc tính `mail`; dùng `REPLACE_ATTRIBUTE` nếu muốn thay tập giá trị hiện tại.

**Câu 2.** Thêm email phụ cho Lan bằng `ADD_ATTRIBUTE` có giống Add một entry mới không?

*Đáp án gợi ý:* Không. `ADD_ATTRIBUTE` thêm giá trị vào một **entry đã tồn tại**; Add tạo **entry mới** tại một DN chưa có.

**Câu 3.** Xóa `ou=people` khi nó còn `uid=lan` và `uid=minh` sẽ xảy ra điều gì theo LDAP Delete thông thường?

*Đáp án gợi ý:* Bị từ chối vì parent là non-leaf; LDAP Delete theo RFC 4511 chỉ xóa entry lá.

**Câu 4.** Lan chuyển từ `ou=people` sang `ou=staff`. Có thể chỉ sửa attribute `ou` của Lan không?

*Đáp án gợi ý:* Không. Phải dùng **Modify DN** vì parent là thành phần của DN; phải bảo đảm parent đích tồn tại và quyền hợp lệ.

**Câu 5.** Một `ModifyRequest` có hai thay đổi: sửa `mail` và sửa `description`. Nếu phần thứ hai vi phạm schema, phần đầu có được ghi không?

*Đáp án gợi ý:* Theo yêu cầu tính nguyên tử của RFC 4511, **không** thay đổi nào trong cùng request được áp dụng khi server trả lỗi.

**Câu 6.** Gọi `ldapTemplate.update(entity)` sau khi thay `@DnAttribute` có luôn tương đương một LDAP Modify DN nguyên tử không?

*Đáp án gợi ý:* Không. Đường cập nhật ODM có thể đi qua `unbind` rồi `bind` khi DN thay đổi. Với đổi tên hoặc chuyển nhánh, cần hiểu rõ API và cân nhắc gọi `rename` tường minh.

## 12. Ghi nhớ

- **Add** tạo entry mới tại DN chưa tồn tại; cần parent, `objectClass`, attribute bắt buộc và quyền phù hợp.
- **Modify** thay **giá trị thuộc tính** của entry hiện có; `ADD_ATTRIBUTE`/`REMOVE_ATTRIBUTE`/`REPLACE_ATTRIBUTE` khác nhau và toàn bộ danh sách thay đổi của **một** ModifyRequest là nguyên tử.
- **Delete** xóa entry, thông thường chỉ cho phép **entry lá**; thao tác xóa cả subtree là trường hợp khác và cần kiểm soát riêng.
- **Modify DN** thay tên hoặc vị trí entry trong DIT; có thể ảnh hưởng DN hậu duệ và tham chiếu từ nhóm/ứng dụng.
- Spring LDAP cung cấp `bind`, `modifyAttributes`, `unbind`, `rename`; ODM/repository giúp làm việc với Java object nhưng **không thay thế** hiểu biết về giao thức.
- Mọi thao tác ghi cần kiểm soát DN, schema, ACL, TLS, tính đồng thời và retry khi mất phản hồi.

**Tài liệu tham khảo:**

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511) (Add, Modify, Delete, Modify DN, result code).
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512) (entry, schema, DIT và naming).
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514) (DN, RDN và escape).
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html) (`bind`, `modifyAttributes`, `unbind`, `rename`, `create/update/delete`).
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html).
- [Spring LDAP — Simplifying Attribute Access with DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html).
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/).
