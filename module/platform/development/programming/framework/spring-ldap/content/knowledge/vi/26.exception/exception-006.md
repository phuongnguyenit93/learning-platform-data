# AttributeInUseException và vi phạm schema

Khi ứng dụng **Spring LDAP** thêm giá trị cho thuộc tính của một entry, server có thể từ chối vì **giá trị đã tồn tại**, thuộc tính không cho phép thêm giá trị thứ hai, hoặc dữ liệu vi phạm **LDAP schema**. Những tình huống này trông giống nhau ở tầng giao diện (“không lưu được”), nhưng nguyên nhân và hướng xử lý rất khác nhau. Bắt sai exception hoặc thay lệnh thêm giá trị bằng lệnh thay thế toàn bộ có thể làm mất dữ liệu đang được người khác sử dụng.

Bài thuộc chương **Exception** của module **SPRING_LDAP**. Trọng tâm là `AttributeInUseException`, mã LDAP `attributeOrValueExists (20)`, các lỗi schema liên quan, và cách cập nhật entry bằng `LdapTemplate.modifyAttributes`. Những nguyên tắc này cũng cần thiết khi sử dụng `LdapClient` hoặc Object–Directory Mapping (ODM), trong bối cảnh có `ContextSource`, DN, filter, xác thực, TLS, pooling và kiểm thử LDAP an toàn.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt `javax.naming.directory.AttributeInUseException` với `org.springframework.ldap.AttributeInUseException`.
2. Giải thích khi nào một thao tác LDAP **Modify Add** nhận mã `20`, và khác gì lỗi `19`, `21` hoặc `65`.
3. Chọn đúng `DirContext.ADD_ATTRIBUTE`, `REPLACE_ATTRIBUTE` và `REMOVE_ATTRIBUTE` khi dùng `ModificationItem`.
4. Xử lý “đã có giá trị” theo hợp đồng nghiệp vụ, không che lỗi quyền, thiếu entry hoặc schema.
5. Tránh race condition của thao tác đọc–kiểm tra–ghi, tránh retry làm hỏng dữ liệu sau mất phản hồi mạng.
6. Thiết kế bộ kiểm thử cho giá trị trùng, thuộc tính đơn trị/đa trị, schema, ACL và cập nhật đồng thời.

## 2. LDAP entry, attribute và schema

Một entry LDAP có **distinguished name (DN)** để xác định vị trí trong cây thư mục và một tập thuộc tính. Mỗi thuộc tính có tên/`attributeType` và một hoặc nhiều giá trị, tùy schema.

Ví dụ entry nhóm:

```ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: uid=an,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
```

Trong nhiều schema LDAP, `groupOfNames` yêu cầu `cn` và ít nhất một `member`. `member` là thuộc tính **đa trị** chứa DN của các thành viên. Với thuộc tính đa trị, thêm **một giá trị mới** khác với **thay toàn bộ tập giá trị**; nhầm hai thao tác có thể loại bỏ thành viên khác khỏi nhóm.

Các quy tắc schema quan trọng:

| Khái niệm | Ý nghĩa | Lỗi có thể gặp |
| --- | --- | --- |
| `objectClass` | Xác định loại entry và bộ thuộc tính được phép/yêu cầu | `SchemaViolationException`, thường mã `65` |
| `MUST` / `MAY` | Attribute bắt buộc / được phép trong các objectClass | Thiếu MUST hoặc thêm attribute không được cho phép có thể trả `65` |
| `SINGLE-VALUE` | Attribute chỉ được có tối đa một giá trị | Thêm giá trị thứ hai có thể vi phạm constraint (`19`); mã thực tế tùy server |
| Multi-valued attribute | Cho phép nhiều giá trị khác nhau | Thêm giá trị đã có có thể trả `20` |
| Syntax / matching rule | Quy tắc kiểu, so sánh và chuẩn hóa giá trị | `21`, `19`, `20` hoặc lỗi liên quan tùy tình huống |
| ACL | Quyền đọc hoặc sửa entry/attribute | `NoPermissionException`, thường mã `50` |

**Không phải mọi lỗi schema đều là `AttributeInUseException`.** Đây là một loại rất cụ thể, thường liên quan việc cố **thêm attribute hoặc giá trị đã hiện diện**. Server còn có thể kiểm tra ràng buộc riêng, plugin/overlay hoặc quy tắc của directory vendor.

## 3. `AttributeInUseException` là exception nào?

### 3.1. Hai package Java dễ nhầm

| API | Class | Đặc điểm |
| --- | --- | --- |
| JNDI | `javax.naming.directory.AttributeInUseException` | **Checked exception**, kế thừa `javax.naming.NamingException` |
| Spring LDAP | `org.springframework.ldap.AttributeInUseException` | **Runtime exception**, kế thừa `org.springframework.ldap.NamingException` |
| Spring DAO | `org.springframework.dao.DataIntegrityViolationException` | Hệ DAO khác; không mặc định được `LdapTemplate` dùng thay cho exception LDAP |

Khi dùng JNDI `DirContext.modifyAttributes` trực tiếp, lỗi có thể là exception checked thuộc `javax.naming.directory`. `LdapTemplate` tự xử lý vòng đời context và chuyển các JNDI `NamingException` thành exception của Spring LDAP. Cơ chế chung có thể xem ở `LdapUtils.convertLdapException(javax.naming.NamingException)`.

```text
LDAP server
  │ Modify/Add member đã có: resultCode 20
  ▼
JNDI provider
  │ javax.naming.directory.AttributeInUseException
  ▼
Spring LDAP (LdapTemplate)
  │ org.springframework.ldap.AttributeInUseException
  ▼
Service
    ├── "Thành viên đã có": xử lý như kết quả nghiệp vụ nếu hợp đồng cho phép
    └── Ngữ cảnh bất thường: tiếp tục báo lỗi / kiểm tra lại trạng thái
```

**Kiểm tra đúng import** khi viết `catch`:

```java
import org.springframework.ldap.AttributeInUseException;
// Dành cho mã gọi LdapTemplate.

// javax.naming.directory.AttributeInUseException là kiểu JNDI khác.
```

Lưu ý tên gọi **attribute in use** không đồng nghĩa “thuộc tính hiện đang được ứng dụng khác khóa”. LDAP `attributeOrValueExists` báo **giá trị/thuộc tính đã tồn tại** theo quy tắc server; nó không phải cơ chế khóa bản ghi hay optimistic locking.

### 3.2. LDAP resultCode `20 — attributeOrValueExists`

Theo LDAP protocol, `attributeOrValueExists (20)` thường xuất hiện khi yêu cầu thêm một giá trị mà entry đã có giá trị tương đương theo **equality matching rule** của thuộc tính.

Ví dụ nhóm đã có:

```text
member: uid=an,ou=people,dc=example,dc=org
```

Yêu cầu:

```text
Modify:
  operation: ADD
  attribute: member
  value:     uid=an,ou=people,dc=example,dc=org
```

Server có thể trả `20` vì giá trị `member` này đã có. Nhưng nếu thêm một giá trị **khác** vào thuộc tính **đơn trị**, server có thể trả `constraintViolation (19)` hoặc mã chuyên biệt khác thay vì `20`. Mã thực tế phụ thuộc schema, matching rules, implementation và thao tác.

Điều quan trọng là **tên thuộc tính hiện diện chưa đủ để kết luận lỗi**: với thuộc tính đa trị, thêm một giá trị *mới* vào thuộc tính đã tồn tại là thao tác bình thường.

## 4. Phân biệt các mã lỗi schema và attribute

Các mã sau thường được gặp khi dùng `modifyAttributes` hoặc tạo entry:

| LDAP result code | Tên chuẩn | Spring LDAP exception thường gặp | Ví dụ và hướng kiểm tra |
| --- | --- | --- | --- |
| `16` | `noSuchAttribute` | `NoSuchAttributeException` | REMOVE giá trị/thuộc tính không tồn tại; xem request và trạng thái hiện tại |
| `17` | `undefinedAttributeType` | `InvalidAttributeIdentifierException` | Tên attribute không được định nghĩa trong schema |
| `18` | `inappropriateMatching` | Phụ thuộc provider, có thể thuộc nhóm search/filter/attribute | Phép so khớp không hợp lệ đối với attribute |
| `19` | `constraintViolation` | `InvalidAttributeValueException` hoặc loại chuyên biệt theo provider | Định dạng/quy tắc số lượng giá trị hoặc ràng buộc khác |
| `20` | `attributeOrValueExists` | `AttributeInUseException` | ADD một giá trị mà server nhận là đã hiện diện |
| `21` | `invalidAttributeSyntax` | `InvalidAttributeValueException` | Giá trị không đúng cú pháp attribute, ví dụ định dạng DN/thời gian không hợp lệ |
| `32` | `noSuchObject` | `NameNotFoundException` | DN của entry cần sửa không tồn tại |
| `34` | `invalidDNSyntax` | `InvalidNameException` | DN mục tiêu sai cú pháp |
| `50` | `insufficientAccessRights` | `NoPermissionException` | Bind identity không có quyền sửa |
| `65` | `objectClassViolation` | `SchemaViolationException` | Thiếu attribute MUST; objectClass không hợp lệ; thuộc tính không được phép |
| `67` | `notAllowedOnRDN` | `SchemaViolationException` hoặc loại liên quan tùy provider | Cố sửa/xóa giá trị cần thiết cho RDN |
| `69` | `objectClassModsProhibited` | `SchemaViolationException` hoặc loại liên quan tùy provider | Server cấm cách sửa objectClass được yêu cầu |

Bảng nêu **ánh xạ điển hình**, không phải cam kết 1–1 cho mọi JNDI provider và LDAP server. Khi chẩn đoán, xem **loại exception + thao tác Modify + nguyên nhân gốc** trước; diagnostic message chỉ là dữ kiện bổ sung và không nên bị parse bằng chuỗi cố định.

### 4.1. `AttributeInUseException` khác `SchemaViolationException`

Giả sử `groupOfNames` đã có hai giá trị `member`. Thêm đúng một DN thành viên đã có thường là xung đột giá trị (`20`). Nhưng nếu xóa **toàn bộ** `member` trong khi objectClass vẫn yêu cầu ít nhất một thành viên, server có thể trả `objectClassViolation (65)`. Đó là lỗi vi phạm schema, khác nguyên nhân với “giá trị đã tồn tại”.

Tương tự, khi tạo `inetOrgPerson`, thiếu `cn` hoặc `sn` bắt buộc có thể gây `SchemaViolationException`. Thêm một giá trị đã tồn tại vào attribute đa trị của entry vốn hợp lệ lại có thể gây `AttributeInUseException`.

### 4.2. `AttributeInUseException` khác `NameAlreadyBoundException`

| Tình huống | Đối tượng bị trùng | Exception điển hình |
| --- | --- | --- |
| LDAP Add tạo entry tại DN đã có | **DN của entry** | `NameAlreadyBoundException` (LDAP `68`) |
| LDAP Modify ADD giá trị đã có | **Giá trị attribute trong entry** | `AttributeInUseException` (LDAP `20`) |

`LdapTemplate.bind(...)` là thao tác tạo entry, **không phải** cách thêm một giá trị vào thuộc tính của entry đã có. Muốn thêm giá trị `member`, hãy dùng `modifyAttributes` với `DirContext.ADD_ATTRIBUTE`.

## 5. Chọn đúng thao tác Modify

JNDI cung cấp `ModificationItem` với ba loại thao tác chính:

| Operation | Mục đích | Ví dụ | Rủi ro nếu dùng sai |
| --- | --- | --- | --- |
| `DirContext.ADD_ATTRIBUTE` | Thêm giá trị vào thuộc tính (hoặc tạo thuộc tính nếu chưa có và schema cho phép) | Thêm thành viên vào nhóm | Thêm giá trị trùng → `20`; thêm giá trị thứ hai vào single-valued → constraint |
| `DirContext.REPLACE_ATTRIBUTE` | Thay thế các giá trị hiện tại bằng các giá trị được cung cấp | Đổi `telephoneNumber` hoặc `description` | Có thể **ghi đè toàn bộ** giá trị đang có, làm mất cập nhật đồng thời |
| `DirContext.REMOVE_ATTRIBUTE` | Xóa giá trị chỉ định; tùy request có thể xóa toàn bộ thuộc tính | Gỡ một thành viên khỏi nhóm | Xóa giá trị không có → `16`; xóa thuộc tính MUST → lỗi schema |

Ví dụ lược đồ:

```text
Trước:
member = {A, B}

ADD member:C          → {A, B, C}
ADD member:B          → có thể LDAP 20 (đã tồn tại)
REPLACE member:{C}    → {C}       (A và B bị loại bỏ)
REMOVE member:B       → {A}       (khi trước đó {A, B})
```

LDAP Modify trên **một entry** xử lý các thay đổi trong cùng yêu cầu theo quy tắc nguyên tử của giao thức: khi một phép sửa thất bại, server không được để lại một phần thay đổi của yêu cầu đó. Điều này **không tạo transaction ACID chung** giữa nhiều entry, nhiều request hoặc giữa LDAP và cơ sở dữ liệu ngoài.

## 6. Ví dụ: thêm thành viên vào nhóm bằng `LdapTemplate`

Giả định:

- `ContextSource` có base `dc=example,dc=org`, được cấu hình kết nối/tài khoản bind có quyền sửa nhóm.
- `cn=engineering,ou=groups,dc=example,dc=org` đã có entry `groupOfNames` hợp lệ.
- Thành viên cần thêm là `uid=an,ou=people,dc=example,dc=org`.
- Hợp đồng nghiệp vụ: **thêm thành viên nếu chưa có; nếu đã có thì trả kết quả “đã là thành viên”**.

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.AttributeInUseException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class DirectoryGroupMembership {
    private final LdapTemplate ldapTemplate;

    public DirectoryGroupMembership(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public enum AddResult { ADDED, ALREADY_MEMBER }

    public AddResult addMember(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        // DN của entry cần sửa: tương đối với base ContextSource.
        Name groupDn = LdapNameBuilder.newInstance("ou=groups")
                .add("cn", "engineering")
                .build();

        // Giá trị của attribute 'member': DN đầy đủ của thành viên.
        Name fullMemberDn = LdapNameBuilder
                .newInstance("dc=example,dc=org")
                .add("ou", "people")
                .add("uid", uid)
                .build();

        ModificationItem add = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", fullMemberDn.toString())
        );

        try {
            ldapTemplate.modifyAttributes(
                    groupDn, new ModificationItem[] { add });
            return AddResult.ADDED;
        } catch (AttributeInUseException ex) {
            // Hợp đồng của phương thức: thêm một member cụ thể.
            // Server báo giá trị đã tồn tại => thành viên đã được thêm.
            return AddResult.ALREADY_MEMBER;
        }
    }
}
```

**Vì sao ví dụ này an toàn hơn “lookup rồi replace toàn bộ member”?**

1. `ADD_ATTRIBUTE` chỉ yêu cầu thêm **một giá trị**, không đụng đến các thành viên khác.
2. Không cần tải danh sách thành viên về để tự so sánh trước; LDAP server kiểm tra giá trị tại lúc Modify.
3. Hai request cùng thêm một giá trị có thể được server phân xử: một request thêm, request kia nhận `20`.
4. Những lỗi khác như `NameNotFoundException`, `NoPermissionException`, `SchemaViolationException` và `CommunicationException` **không bị nuốt** vào `ALREADY_MEMBER`.

Lưu ý: ví dụ chỉ phù hợp khi `AttributeInUseException` xuất hiện trong **ngữ cảnh ADD đúng một giá trị `member`**. Nếu adapter tổng hợp nhiều thao tác vào một request, không nên mặc định mọi `AttributeInUseException` là “đã là thành viên” mà không xác định phép sửa gây lỗi. Với yêu cầu nhạy cảm về quyền, có thể đọc lại trạng thái bằng một truy vấn đáng tin cậy để xác nhận membership, nhất là sau timeout hoặc có referral/replica.

**Không kiểm tra sự tồn tại của thành viên bằng cách ghép filter thủ công.** `LdapNameBuilder` escape DN; `LdapQueryBuilder` phục vụ escape filter. Đây là hai cú pháp khác nhau.

### 6.1. Nếu DN của thành viên không tồn tại thì sao?

Một số LDAP server/schema lưu giá trị `member` theo cú pháp DN nhưng **không nhất thiết kiểm tra entry được tham chiếu có thật**. Hành vi referential integrity phụ thuộc server và cấu hình. Vì vậy, Modify ADD thành công **không chứng minh** account ở DN thành viên đã tồn tại hoặc tài khoản đó có quyền sử dụng ứng dụng.

Nếu nghiệp vụ đòi thành viên là một tài khoản hợp lệ, hãy xác minh bằng truy vấn phù hợp và quyền đọc cần thiết. Lưu ý kiểm tra–sử dụng vẫn có race condition: entry có thể bị xóa/đổi DN sau khi kiểm tra.

### 6.2. Có thể dùng `LdapClient` không?

Ở phiên bản Spring LDAP hỗ trợ Fluent API, `LdapClient` cũng có thao tác cập nhật attribute và có thể truyền `ModificationItem`:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapClient;

public final class LdapClientMembershipWriter {
    private final LdapClient ldapClient;

    public LdapClientMembershipWriter(LdapClient ldapClient) {
        this.ldapClient = ldapClient;
    }

    public void addMember(Name relativeGroupDn, String fullMemberDn) {
        ModificationItem change = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", fullMemberDn)
        );
        ldapClient.modify()
                .name(relativeGroupDn)
                .attributes(change)
                .execute();
    }
}
```

Kiểm tra phiên bản Spring LDAP đang sử dụng, vì API và overload cụ thể có thể khác theo phiên bản. Nguyên tắc chọn `ADD_ATTRIBUTE` và phân loại `AttributeInUseException` không thay đổi. Với ODM, hãy xem nó tạo `ModificationItem` nào từ thay đổi của đối tượng; một bước đồng bộ toàn bộ collection có thể thay thế nhiều giá trị và ảnh hưởng cập nhật đồng thời.

## 7. Ví dụ: đổi thuộc tính đơn trị bằng REPLACE

Đối với thuộc tính thường lưu một giá trị như `description` theo quy tắc nghiệp vụ, dùng `REPLACE_ATTRIBUTE` để đổi giá trị sẽ đúng hơn việc liên tục gọi `ADD_ATTRIBUTE`:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class DirectoryPersonProfile {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonProfile(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void replaceDescription(String uid, String description) {
        if (description == null) {
            throw new IllegalArgumentException("description không được null");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        ModificationItem change = new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("description", description)
        );
        ldapTemplate.modifyAttributes(dn, new ModificationItem[] { change });
    }
}
```

Trong ví dụ này, `description` được xem là một thuộc tính chỉ có **một giá trị theo hợp đồng ứng dụng**; không cần khẳng định schema của mọi LDAP server bắt buộc nó là `SINGLE-VALUE`. Lệnh `REPLACE_ATTRIBUTE` vẫn thay các giá trị hiện có của attribute trong entry. Nếu dữ liệu cho phép nhiều giá trị và có caller khác đang thêm vào, thao tác này có thể ghi đè cập nhật của họ.

Khi sử dụng `DirContextAdapter` với `lookupContext(...)` rồi `setAttributeValue(...)`/`setAttributeValues(...)` và `modifyAttributes(ctx)`, hãy hiểu rằng adapter có thể tạo **REPLACE** hoặc các `ModificationItem` dựa trên trạng thái ban đầu và thay đổi phát hiện được. Đừng giả định đó là phép “thêm một giá trị” an toàn trong mọi phiên bản/kiểu dữ liệu.

### 7.1. Khi nào dùng REMOVE?

Để gỡ **một thành viên cụ thể** khỏi nhóm, có thể dùng:

```java
ModificationItem remove = new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("member", fullMemberDn)
);
ldapTemplate.modifyAttributes(groupDn, new ModificationItem[] { remove });
```

Nếu giá trị chưa có, server có thể báo `noSuchAttribute (16)`. Nếu thao tác xóa khiến `groupOfNames` **không còn giá trị `member` bắt buộc**, server có thể trả lỗi schema (`65`). Vì vậy, việc gỡ thành viên cuối cùng cần chính sách riêng (ví dụ không cho phép, chuyển group sang loại khác khi được hỗ trợ, hoặc xóa group theo quy trình được cấp quyền). Không xóa toàn bộ `member` chỉ để gỡ một DN.

## 8. Race condition, tính nguyên tử và idempotency

### 8.1. Kiểm tra trước rồi thêm vẫn có race

Một mẫu code dễ sai:

```text
Request A: lookup(group) → chưa có member X
Request B: lookup(group) → chưa có member X
Request A: ADD member X → success
Request B: ADD member X → attributeOrValueExists (20)
```

Kết quả lookup ở thời điểm trước **không khóa** entry cho mọi writer. Dù cả hai đều thấy X chưa có, request B vẫn phải xử lý `AttributeInUseException`. Nếu hợp đồng là “đảm bảo X thuộc nhóm”, `ALREADY_MEMBER` có thể là kết quả hợp lệ; nếu hợp đồng là “thêm mới phải tạo thay đổi”, có thể báo conflict.

Ngược lại, thao tác **REPLACE** dựa trên danh sách member đọc trước dễ gây *lost update*:

```text
T1 đọc: {A, B}
T2 đọc: {A, B}
T1 replace: {A, B, C}
T2 replace: {A, B, D}
Kết quả: {A, B, D}  → mất C
```

Với tập giá trị dùng chung, nên dùng `ADD_ATTRIBUTE`/`REMOVE_ATTRIBUTE` theo giá trị cụ thể và server kiểm tra ràng buộc. Nếu nghiệp vụ cần thay toàn bộ collection, cân nhắc version/compare-and-swap hoặc cơ chế concurrency control mà LDAP server hỗ trợ; không thể bảo đảm an toàn chỉ bằng `synchronized` trong một instance Java.

### 8.2. Lỗi mạng sau Modify không chứng minh request thất bại

```text
Ứng dụng                           LDAP server
   │                                    │
   ├──── ADD member:X ─────────────────>│
   │                                    ├─ Thêm X thành công
   X<──── Phản hồi thất lạc ────────────┤
   │
   ├─ CommunicationException
   │
   └──── Gửi lại ADD member:X ─────────>│
                                        └─ Có thể trả 20
```

Khi mất phản hồi, server có thể đã áp dụng phép sửa. Nếu retry dẫn đến `20`, điều đó chứng minh giá trị **đang tồn tại theo phản hồi server**, nhưng chưa chứng minh request đầu tiên của chính caller đã thêm nó (writer khác có thể làm trước). Chính sách idempotency phải định nghĩa rõ liệu trạng thái “X đã là thành viên” có đủ để coi yêu cầu thành công không.

Retry có giới hạn phù hợp hơn khi lỗi được xác nhận là tạm thời và thao tác có chính sách kiểm soát trùng. Không retry mù quáng với `20`, `19`, `21`, `50` hoặc `65`; sửa nguyên nhân và dữ liệu trước.

### 8.3. So sánh giá trị phải tôn trọng matching rule

LDAP có quy tắc so sánh riêng theo attribute syntax và matching rule. Ví dụ, DN trong attribute kiểu Distinguished Name có thể có các cách biểu diễn văn bản tương đương. Một phép so sánh `String.equals` phía Java **không thay thế** được đánh giá của LDAP server.

Nếu cần kiểm tra trước để hiển thị UI, có thể đọc group và xem các giá trị member, nhưng kết quả chỉ là quan sát tại thời điểm đó. Quyết định cuối cùng khi ghi phải dựa trên phản hồi của LDAP server và chính sách đồng thời.

## 9. Xử lý lỗi trong service/API

Một API thêm thành viên có thể trả các kết quả sau:

| Tình huống | Ý nghĩa nghiệp vụ | Phản hồi gợi ý |
| --- | --- | --- |
| ADD member thành công | Có thay đổi mới | `200 OK`/`204 No Content` hoặc `201` nếu API định nghĩa tạo resource membership |
| ADD member trả `20` | Thành viên đã có; yêu cầu “ensure membership” | Có thể trả `200`/`204` khi hợp đồng idempotent cho phép |
| ADD member trả `20` | Endpoint yêu cầu thêm mới và không chấp nhận trùng | Có thể trả `409 Conflict` |
| `NameNotFoundException` (`32`) | Group cần sửa không tồn tại | `404` nếu resource group được xác định và caller được phép biết |
| `NoPermissionException` (`50`) | Tài khoản LDAP không đủ quyền Modify | Lỗi hạ tầng/cấu hình hoặc lỗi phân quyền tùy luồng; không mặc định `403` cho HTTP caller |
| `SchemaViolationException` (`65`) | Payload/điều kiện schema không phù hợp | Lỗi validation hoặc lỗi server tùy ai gây ra |
| `CommunicationException` / `ServiceUnavailableException` | Không xác định/không thực hiện được thao tác | Có thể trả `503` và quy trình đối soát tùy API |

**Không đưa diagnostic message gốc của LDAP ra HTTP**: nó có thể lộ DN, tên OU, thuộc tính hoặc chính sách nội bộ. Chỉ hiển thị thông điệp đủ cho mục đích người dùng, còn log có cấu trúc lưu operation, nhóm lỗi, correlation ID, thời lượng và nguyên nhân được làm sạch.

Đặc biệt, **không log credential, password, access token hoặc giá trị attribute nhạy cảm**. Thêm/xóa nhóm có thể thay đổi quyền truy cập tài nguyên, vì vậy hãy xác thực và **ủy quyền caller** ở tầng ứng dụng trước khi thao tác; quyền LDAP của service account không đủ để chứng minh caller được phép thay đổi thành viên.

## 10. Chẩn đoán lỗi `20` và lỗi schema theo quy trình

Khi nhận `org.springframework.ldap.AttributeInUseException`:

1. **Xác định thao tác**: là `ADD_ATTRIBUTE` trên thuộc tính nào, thêm giá trị nào? Có phải request chứa nhiều `ModificationItem` không?
2. **Kiểm tra entry và DN**: đúng nhóm, đúng relative/full DN, đúng LDAP endpoint và base của `ContextSource` chưa?
3. **Kiểm tra schema**: attribute là single-valued hay multi-valued, được phép trên objectClass đó không; có equality matching rule nào?
4. **Kiểm tra ý nghĩa của giá trị đã có**: có thể coi là idempotent success theo hợp đồng, hay là conflict cần thông báo?
5. **Đối chiếu các lỗi cạnh tranh**: `19`/`21` cho constraint/syntax, `65` cho objectClass, `32` cho DN không tồn tại, `50` cho ACL.
6. **Kiểm tra concurrency**: có nhiều request cùng ADD/REMOVE, ODM replace toàn bộ tập giá trị, hoặc retry sau timeout không?
7. **Đưa ra quyết định**: phản hồi theo hợp đồng và theo quyền của caller; không tự động sửa schema, ghi đè hay xóa dữ liệu khác.

Khi nhận `SchemaViolationException`, cần kiểm tra thêm objectClass, thuộc tính MUST/MAY và ràng buộc giá trị RDN. Ví dụ:

- Tạo `inetOrgPerson` thiếu `sn` hoặc `cn` trong schema yêu cầu.
- Xóa giá trị `member` cuối cùng của `groupOfNames`.
- Sửa `objectClass` theo cách server không cho phép.
- Cố xóa/đổi thuộc tính tham gia cấu tạo RDN mà không dùng thao tác đổi tên phù hợp.

Trong các trường hợp này, **retry nguyên request không khắc phục lỗi**. Hãy thay payload hoặc quy trình quản trị dữ liệu theo schema và chính sách server.

### 10.1. Phân biệt lỗi với sự cố TLS, authentication và pooling

`AttributeInUseException` xuất hiện khi server đã có đủ ngữ cảnh để đánh giá thao tác cập nhật. Nếu **kết nối TLS/LDAPS** thất bại ngay lúc mở context, Spring LDAP thường báo `CommunicationException` có thể bọc nguyên nhân SSL/TLS. Nếu service account bind không thành công, thường là `AuthenticationException`. Nếu context được tái sử dụng sai hoặc cấu hình pooling không phù hợp, identity và quyền của thao tác có thể khác mong đợi.

Không xử lý các vấn đề hạ tầng bằng cách bắt `AttributeInUseException` rồi trả “đã có giá trị”. Cũng không tắt xác minh chứng chỉ để giải quyết lỗi kết nối LDAP; kết nối mang credential và dữ liệu thư mục cần được bảo vệ.

## 11. Kiểm thử các tình huống quan trọng

Unit test kiểm tra việc service phân loại exception đúng. Integration test trên LDAP test server hoặc môi trường cô lập giúp xác nhận schema, equality matching rule, ACL và concurrency thật.

| Ca thử | Kỳ vọng |
| --- | --- |
| ADD giá trị `member` chưa có | Thao tác thành công; danh sách thành viên có thêm đúng một DN |
| ADD lại đúng `member` đã có | Có thể nhận `AttributeInUseException`, service trả `ALREADY_MEMBER` theo hợp đồng |
| ADD giá trị khác vào thuộc tính đa trị | Giữ nguyên các giá trị cũ và thêm giá trị mới |
| ADD giá trị thứ hai vào thuộc tính `SINGLE-VALUE` | Nhận lỗi constraint/schema phù hợp; không mặc định `AttributeInUseException` |
| REPLACE một thuộc tính đơn trị | Giá trị mới thay thế giá trị cũ |
| REPLACE toàn bộ `member` dựa trên dữ liệu stale | Phát hiện nguy cơ lost update và điều chỉnh thiết kế |
| REMOVE `member` đã có | Xóa đúng giá trị được chỉ định |
| REMOVE `member` không có | Lỗi `noSuchAttribute` hoặc hành vi cụ thể của server/API được phân loại |
| REMOVE `member` cuối của `groupOfNames` | Lỗi schema khi schema yêu cầu tối thiểu một giá trị |
| Thiếu group DN | `NameNotFoundException`, không đổi thành `ALREADY_MEMBER` |
| Service account thiếu quyền Modify | `NoPermissionException`, không đổi thành lỗi dữ liệu trùng |
| Sửa thuộc tính không tồn tại trong schema | `InvalidAttributeIdentifierException` hoặc lỗi provider tương ứng |
| Timeout sau khi server đã ADD | Đối soát trạng thái trước khi retry để giữ idempotency |
| Hai request ADD cùng DN thành viên | Server phân xử; không mất giá trị của thành viên khác |

### 11.1. Unit test minh họa cách bắt exception

Ví dụ Mockito kiểm tra service chuyển **chỉ lỗi `AttributeInUseException`** thành kết quả “đã là thành viên”. Constructor của exception Spring LDAP nhận nguyên nhân JNDI:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;

import javax.naming.Name;
import javax.naming.directory.ModificationItem;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.AttributeInUseException;
import org.springframework.ldap.core.LdapTemplate;

class DirectoryGroupMembershipTest {
    @Test
    void duplicateMemberReturnsAlreadyMember() {
        LdapTemplate template = mock(LdapTemplate.class);
        doThrow(new AttributeInUseException(
                new javax.naming.directory.AttributeInUseException(
                        "Attribute value already exists")))
                .when(template)
                .modifyAttributes(
                        any(Name.class), any(ModificationItem[].class));

        DirectoryGroupMembership service =
                new DirectoryGroupMembership(template);

        assertEquals(
                DirectoryGroupMembership.AddResult.ALREADY_MEMBER,
                service.addMember("an")
        );
    }
}
```

Đây là **ví dụ kiểm tra logic**, không chứng minh server thực hiện đúng schema. Cần integration test riêng để kiểm chứng LDAP code và trạng thái thật của entry. Unit test hữu ích vì nếu ai đó đổi `ADD_ATTRIBUTE` thành `REPLACE_ATTRIBUTE` hoặc bắt mọi `NamingException`, chiến lược kiểm thử hành vi phải phát hiện thay đổi không mong muốn.

## 12. Những lỗi thiết kế thường gặp

1. **Nhầm `AttributeInUseException` với `NameAlreadyBoundException`:** một lỗi trùng giá trị attribute, lỗi kia trùng DN khi Add entry.
2. **Cho rằng attribute đã có thì không thể thêm giá trị:** thuộc tính đa trị được phép có nhiều giá trị **khác nhau**.
3. **Giả định mọi vi phạm schema đều trả `20`:** có nhiều mã khác như `19`, `21`, `65`, `67`, `69`.
4. **Đổi `ADD_ATTRIBUTE` thành `REPLACE_ATTRIBUTE` để tránh lỗi trùng:** có thể mất thành viên khác hoặc ghi đè cập nhật đồng thời.
5. **Lookup rồi ADD mà không xử lý race:** một writer khác có thể thêm cùng giá trị giữa hai bước.
6. **Retry vô hạn sau `20`:** nếu giá trị đã có, lặp lại cùng ADD không thay đổi nguyên nhân.
7. **Dùng `String.equals` thay matching rule của LDAP:** biểu diễn khác nhau có thể được server coi là cùng giá trị.
8. **Nuốt mọi `NamingException` và trả “đã tồn tại”:** làm mất tín hiệu từ ACL, schema, TLS, server unavailable hoặc DN sai.
9. **Bắt `javax.naming.directory.AttributeInUseException` trực tiếp quanh `LdapTemplate`:** Spring LDAP thường đã chuyển sang runtime exception thuộc `org.springframework.ldap`.
10. **Log dữ liệu và DN nhạy cảm:** thông tin về group membership có thể liên quan phân quyền; cần giảm thiểu dữ liệu trong log.

## 13. Câu hỏi tự đánh giá

**Câu 1.** Một nhóm `groupOfNames` đã có `member=X`. Gọi `ADD_ATTRIBUTE` với `member=X` lần nữa thường gặp mã nào?

**Đáp án:** `attributeOrValueExists (20)` và thường được Spring LDAP biểu diễn bằng `AttributeInUseException`.

**Câu 2.** `ADD_ATTRIBUTE` và `REPLACE_ATTRIBUTE` khác nhau thế nào khi `member={A,B}`?

**Đáp án:** ADD C tạo `{A,B,C}`; REPLACE C tạo `{C}` và có thể xóa A/B khỏi nhóm.

**Câu 3.** Vì sao xóa `member` cuối cùng của `groupOfNames` có thể là lỗi schema?

**Đáp án:** Schema `groupOfNames` thường yêu cầu ít nhất một `member`. Lệnh xóa khiến entry vi phạm thuộc tính MUST, khác với lỗi trùng giá trị (`20`).

**Câu 4.** Thêm giá trị thứ hai vào thuộc tính single-valued có bắt buộc trả `20` không?

**Đáp án:** Không. Có thể trả `constraintViolation (19)` hoặc lỗi schema/attribute khác theo server; phải kiểm tra schema và phản hồi thực tế.

**Câu 5.** Có cần gọi `lookup` trước mỗi `ADD_ATTRIBUTE` để tránh duplicate không?

**Đáp án:** Không bắt buộc. Server có thể phân xử Add trực tiếp; lookup trước vẫn không loại bỏ race condition.

**Câu 6.** Gặp `CommunicationException` sau khi gửi Add member, có biết phép sửa thất bại hoàn toàn không?

**Đáp án:** Không. Server có thể đã thực hiện và phản hồi bị mất. Cần xác minh trạng thái hoặc áp dụng hợp đồng idempotent có kiểm soát.

**Câu 7.** `AttributeInUseException` của Spring LDAP có phải subclass của `DataIntegrityViolationException` không?

**Đáp án:** Không. Spring LDAP có hệ `NamingException` riêng; chỉ adapter đặc thù mới có thể chuyển chủ động sang hệ DAO.

## 14. Tài liệu tham khảo

- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): resultCode `attributeOrValueExists`, `constraintViolation` và tính nguyên tử của Modify.
- [Java SE — `javax.naming.directory.AttributeInUseException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/AttributeInUseException.html): exception JNDI khi thao tác cố thêm attribute đã tồn tại.
- [Spring LDAP — `org.springframework.ldap.AttributeInUseException`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/AttributeInUseException.html): runtime exception tương ứng.
- [Spring LDAP — `LdapTemplate`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): `modifyAttributes(Name, ModificationItem[])` và xử lý exception.
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): cập nhật entry bằng `modifyAttributes` / `LdapClient` và khác biệt với `rebind`.
- [Spring LDAP — FAQ](https://docs.spring.io/spring-ldap/reference/faq.html): cách xử lý operational attributes và sử dụng `ModificationItem`.
- [Spring LDAP — `LdapNameBuilder`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapNameBuilder.html): tạo DN và escape RDN an toàn.

**Ghi nhớ:** `AttributeInUseException` thường có nghĩa **giá trị cần ADD đã tồn tại trong attribute của entry**, không phải “entry đã tồn tại” hoặc “schema luôn sai”. Hãy dùng đúng phép Modify, để server phân xử xung đột giá trị, giữ các giá trị khác khỏi bị ghi đè, và phân loại rõ lỗi schema, ACL, DN, xác thực và kết nối trước khi quyết định retry hoặc trả kết quả nghiệp vụ.
