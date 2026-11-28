# Đồng bộ thêm, xóa thành viên mà không làm mất thay đổi đồng thời

## 1. Bài toán: vì sao một lần cập nhật danh sách thành viên có thể xóa nhầm dữ liệu?

Giả sử nhóm LDAP `cn=developers,ou=groups,dc=example,dc=org` có ba thành viên:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=example,dc=org
member: uid=an,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
```

Hai request đến gần như đồng thời:

- Service A thêm Hoa vào nhóm.
- Service B xóa An khỏi nhóm.

Nếu cả hai service đều đọc danh sách hiện tại, chỉnh một bản sao trong Java rồi ghi đè **toàn bộ** attribute `member`, một cập nhật có thể xóa thay đổi của cập nhật còn lại.

```text
Trạng thái ban đầu: {Linh, An, Minh}

Service A đọc:      {Linh, An, Minh}
Service B đọc:      {Linh, An, Minh}

A tính tập mới:     {Linh, An, Minh, Hoa}
B tính tập mới:     {Linh, Minh}

A REPLACE member:   {Linh, An, Minh, Hoa}
B REPLACE member:   {Linh, Minh}

Kết quả cuối:       {Linh, Minh}
                    Hoa bị mất dù A đã ghi thành công.
```

Vấn đề không nằm ở việc LDAP không hỗ trợ cập nhật đồng thời. Vấn đề là **cách client gửi yêu cầu**: thay toàn bộ tập giá trị từ một snapshot có thể đã cũ.

Trong module **SPRING_DATA_LDAP**, Spring Data LDAP repository/ODM và Spring LDAP `LdapTemplate` giúp ánh xạ entry, DN, `objectClass` và thao tác group membership. Với attribute đa trị như `member`, cần biểu diễn ý định theo từng giá trị:

- Thêm một thành viên: LDAP `ADD_ATTRIBUTE` với đúng DN thành viên.
- Xóa một thành viên: LDAP `REMOVE_ATTRIBUTE` với đúng DN thành viên.
- Thay toàn bộ danh sách: `REPLACE_ATTRIBUTE` chỉ khi nghiệp vụ thực sự yêu cầu thay toàn bộ và có chiến lược đồng thời phù hợp.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích lost update khi đọc danh sách group rồi ghi đè toàn bộ.
2. Phân biệt LDAP Modify `ADD`, `DELETE` và `REPLACE` trên một attribute đa trị.
3. Gửi một hoặc nhiều `ModificationItem` qua `LdapTemplate.modifyAttributes`.
4. Dùng `DirContextOperations.addAttributeValue` và `removeAttributeValue` để biểu diễn delta.
5. Hiểu tính nguyên tử của một LDAP ModifyRequest và giới hạn của nó.
6. Xử lý giá trị trùng, giá trị không tồn tại, retry sau timeout và thao tác đồng thời.
7. Thiết kế idempotent sync, checkpoint, audit và reconciliation cho group membership.
8. Kiểm thử nhiều writer cùng sửa một group trên directory test.

## 2. LDAP group membership là attribute đa trị

Một nhóm LDAP thường biểu diễn thành viên bằng một attribute chứa nhiều giá trị:

- `groupOfNames` thường dùng attribute `member` chứa DN đầy đủ của từng thành viên.
- `groupOfUniqueNames` dùng `uniqueMember`; giá trị có cú pháp riêng theo schema.
- Active Directory thường dùng `member` là linked attribute cho group; còn có quy tắc riêng như primary group và range retrieval.
- Directory hoặc ứng dụng có thể dùng schema nhóm khác; không giả định mọi group đều có cùng objectClass/attribute.

Ví dụ `groupOfNames`:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=example,dc=org
member: uid=an,ou=people,dc=example,dc=org
```

Ở đây `member` là **một attribute với hai giá trị**, không phải hai attribute cùng tên trong một map thông thường. Mỗi giá trị là một DN đầy đủ, có thể phải escape theo RFC 4514 khi xây dựng.

### 2.1. Group schema có ràng buộc riêng

| Object class | Attribute thành viên | Ghi chú |
| --- | --- | --- |
| `groupOfNames` | `member` | Theo schema phổ biến, `member` là MUST và phải có ít nhất một giá trị. |
| `groupOfUniqueNames` | `uniqueMember` | Dùng unique member DN syntax; cần tuân thủ schema tương ứng. |
| `posixGroup` | `memberUid` | Thường chứa UID dạng chuỗi, không phải DN đầy đủ. |
| Active Directory group | `member` | Linked attribute; có các quy tắc riêng theo scope/type và primary group. |

Ví dụ trong bài dùng `groupOfNames` và DN đầy đủ. Nếu xóa thành viên cuối cùng, server có thể từ chối vì vi phạm `MUST`/schema. Muốn nhóm rỗng, cần chọn object class hoặc mô hình dữ liệu phù hợp đã được quản trị directory phê duyệt; không tắt schema check chỉ để thao tác thành công.

## 3. Ba phép sửa LDAP khác nhau

RFC 4511 định nghĩa ModifyRequest với danh sách các thay đổi, mỗi thay đổi có operation và một attribute:

| JNDI constant | LDAP operation | Ý nghĩa với attribute đa trị |
| --- | --- | --- |
| `DirContext.ADD_ATTRIBUTE` | `add` | Thêm các giá trị chỉ định; tạo attribute nếu chưa có. |
| `DirContext.REMOVE_ATTRIBUTE` | `delete` | Xóa các giá trị chỉ định; nếu không nêu giá trị thì xóa toàn attribute. |
| `DirContext.REPLACE_ATTRIBUTE` | `replace` | Thay toàn bộ tập giá trị hiện có bằng tập mới. |

Ví dụ trước có `member={Linh, An, Minh}`:

```text
ADD member=Hoa
  => {Linh, An, Minh, Hoa}

REMOVE member=An
  => {Linh, Minh}

REPLACE member={Linh, Minh}
  => {Linh, Minh}
```

Kết quả của ADD/REMOVE chỉ tác động tới **giá trị được chỉ định**; các giá trị khác tiếp tục được giữ. Đây là điều làm chúng phù hợp cho thao tác thêm/xóa một thành viên giữa nhiều writer.

### 3.1. ADD không phải REPLACE

```java
// Chỉ thêm một thành viên; giữ mọi member khác.
ModificationItem addHoa = new ModificationItem(
    DirContext.ADD_ATTRIBUTE,
    new BasicAttribute("member", hoaDn.toString())
);

ldapTemplate.modifyAttributes(groupDn, new ModificationItem[] {addHoa});
```

Không viết:

```java
// RỦI RO: thay toàn bộ membership bằng snapshot trong Java.
ModificationItem replaceMembers = new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE,
    new BasicAttribute("member", allMembersFromEarlierSearch)
);
```

Nếu một actor khác thêm một DN sau khi snapshot được đọc, `REPLACE_ATTRIBUTE` có thể xóa DN đó khỏi tập.

### 3.2. REMOVE một giá trị không phải xóa cả attribute

```java
ModificationItem removeAn = new ModificationItem(
    DirContext.REMOVE_ATTRIBUTE,
    new BasicAttribute("member", anDn.toString())
);
```

Khi `BasicAttribute` có đúng một giá trị, ý định là xóa **giá trị đó** khỏi `member`. Nếu tạo `BasicAttribute("member")` không có value, LDAP delete operation có thể xóa **toàn bộ attribute**; đây không phải cách an toàn để xóa một thành viên cụ thể.

## 4. Tại sao ADD/REMOVE theo giá trị giảm lost update?

Quay lại hai request đồng thời:

```text
Trạng thái ban đầu: {Linh, An, Minh}

A: ADD member=Hoa
B: REMOVE member=An

Server áp dụng A rồi B:
  {Linh, An, Minh}
  -> {Linh, An, Minh, Hoa}
  -> {Linh, Minh, Hoa}

Server áp dụng B rồi A:
  {Linh, An, Minh}
  -> {Linh, Minh}
  -> {Linh, Minh, Hoa}

Kết quả cuối trong cả hai thứ tự:
  {Linh, Minh, Hoa}
```

Vì hai request tác động lên **hai giá trị khác nhau** của cùng attribute, ADD Hoa không thay thế tập member và REMOVE An không đụng đến Hoa. Server xử lý mỗi ModifyRequest như một thao tác nguyên tử trên entry.

Đây là ưu điểm chính của **delta update**:

- Không cần đọc toàn bộ tập thành viên trước khi thêm/xóa một DN.
- Không gửi lại các giá trị mà request không sở hữu.
- Giảm khả năng một writer ghi đè thay đổi khác.
- Ít dữ liệu hơn khi group có nhiều member.

**Giới hạn:** nếu hai writer cùng ADD hoặc một writer ADD trong khi writer kia REMOVE **cùng một DN**, kết quả cuối phụ thuộc thứ tự xử lý. Delta update không tự quyết định nghiệp vụ nào thắng.

## 5. Tính nguyên tử của một LDAP ModifyRequest

RFC 4511 quy định danh sách modifications trong **một ModifyRequest** được server thực hiện theo thứ tự liệt kê và như **một thao tác nguyên tử**. Nếu server trả response thành công, các thay đổi trong request đã hoàn tất; nếu nhận response lỗi, client có thể kỳ vọng không có phần nào của request được áp dụng.

Ví dụ cần thay thành viên cũ bằng thành viên mới trong **cùng một group entry**:

```java
ModificationItem[] replaceOneMember = {
    new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("member", oldMemberDn.toString())
    ),
    new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("member", newMemberDn.toString())
    )
};

ldapTemplate.modifyAttributes(groupDn, replaceOneMember);
```

Hai thay đổi nằm trong một ModifyRequest tới cùng DN group. Server áp dụng theo thứ tự: gỡ DN cũ rồi thêm DN mới; kết quả phải thỏa schema của group.

### 5.1. Atomicity có phạm vi một entry và một request

Không suy rộng atomicity thành:

- Một request HTTP chứa nhiều LDAP group.
- Một vòng lặp gọi `modifyAttributes` nhiều lần.
- Cập nhật LDAP group và SQL database.
- Cập nhật LDAP và publish Kafka.
- Nhiều directory server/naming context.

Nếu service cập nhật 20 group, request thứ 13 có thể thất bại sau khi 12 group đầu đã được sửa. Cần thiết kế workflow có checkpoint, retry, idempotency và reconciliation.

### 5.2. Không nhận response sau khi gửi request: trạng thái chưa xác định

Nếu TCP bị ngắt hoặc timeout sau khi client gửi ModifyRequest nhưng trước khi nhận ModifyResponse, client **không thể biết** server đã áp dụng hay chưa. RFC 4511 nêu rõ trạng thái không thể xác định khi ModifyResponse không nhận được.

Không retry một cách mù quáng:

- ADD có thể trả `attributeOrValueExists` nếu request trước đã thành công.
- REMOVE có thể trả `noSuchAttribute` nếu giá trị đã bị xóa.
- Một thao tác khác cùng DN có thể đã xảy ra sau request đầu tiên.

Hãy đọc lại trạng thái hiện tại và so với **ý định cuối** trước khi quyết định gửi lại delta.

## 6. Cách 1: dùng ModificationItem trực tiếp

Đây là cách thể hiện ý định rõ nhất khi chỉ thêm/xóa một member.

### 6.1. Helper dựng DN an toàn

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

static Name personDn(String uid) {
    return LdapNameBuilder.newInstance("ou=people")
        .add("uid", uid)
        .build();
}

static Name groupDn(String cn) {
    return LdapNameBuilder.newInstance("ou=groups")
        .add("cn", cn)
        .build();
}
```

`ContextSource.base` được giả định là `dc=example,dc=org`, nên các `Name` trên là DN tương đối. Không nối chuỗi DN bằng input thô vì UID/CN có thể chứa dấu phẩy, dấu cộng hoặc ký tự cần escape theo RFC 4514.

### 6.2. Thêm một member

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

void addMember(LdapTemplate ldap, Name groupDn, Name memberDn) {
    ModificationItem add = new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("member", memberDn.toString())
    );

    ldap.modifyAttributes(groupDn, new ModificationItem[] {add});
}
```

Phép sửa này không cần `lookup` membership trước. LDAP server tự xử lý việc thêm giá trị vào tập hiện tại của entry group.

### 6.3. Xóa một member

```java
void removeMember(LdapTemplate ldap, Name groupDn, Name memberDn) {
    ModificationItem remove = new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("member", memberDn.toString())
    );

    ldap.modifyAttributes(groupDn, new ModificationItem[] {remove});
}
```

Nếu group schema yêu cầu ít nhất một member, xóa thành viên cuối cùng có thể bị từ chối. Service cần xác định policy trước khi gọi thao tác, hoặc dùng group model cho phép tập rỗng.

### 6.4. Gộp nhiều thay đổi trên cùng group

```java
ModificationItem[] changes = {
    new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("member", hoaDn.toString())
    ),
    new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("member", anDn.toString())
    )
};

ldapTemplate.modifyAttributes(groupDn, changes);
```

Đây là một request sửa **một entry group**. Hai thay đổi được xử lý theo thứ tự đã khai báo. Nếu request thất bại vì schema/ACL, server không áp dụng một nửa request rồi giữ nửa còn lại.

## 7. Cách 2: dùng DirContextOperations để theo dõi delta

Spring LDAP cung cấp `DirContextOperations` và `DirContextAdapter` với các API:

- `addAttributeValue(attributeName, value)`.
- `removeAttributeValue(attributeName, value)`.
- `setAttributeValues(attributeName, values)`.
- `getModificationItems()`.
- `LdapTemplate.modifyAttributes(context)`.

Đối với attribute đa trị, `addAttributeValue`/`removeAttributeValue` thể hiện thay đổi theo giá trị. Trái lại, `setAttributeValues` thể hiện ý định đặt lại **toàn bộ tập**.

### 7.1. Thêm thành viên bằng context đã lookup

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

void addMemberWithContext(
        LdapTemplate ldap, Name groupDn, Name memberDn) {

    DirContextOperations group = ldap.lookupContext(groupDn);
    group.addAttributeValue("member", memberDn.toString());

    // Xem delta trước khi ghi; không log giá trị DN nhạy cảm.
    var modifications = group.getModificationItems();
    if (modifications.length > 0) {
        ldap.modifyAttributes(group);
    }
}
```

`lookupContext` trả context đã được khởi tạo từ entry hiện có trong update mode theo cấu hình mặc định Spring LDAP. `modifyAttributes(group)` lấy DN và các `ModificationItem` từ context.

### 7.2. Xóa thành viên bằng context

```java
void removeMemberWithContext(
        LdapTemplate ldap, Name groupDn, Name memberDn) {

    DirContextOperations group = ldap.lookupContext(groupDn);
    group.removeAttributeValue("member", memberDn.toString());

    var modifications = group.getModificationItems();
    if (modifications.length > 0) {
        ldap.modifyAttributes(group);
    }
}
```

Không gọi `group.update()` để “commit”. `DirContextAdapter.update()` cập nhật snapshot nội bộ và có thể xóa pending modifications; nó không gửi LDAP ModifyRequest. Phải gọi `ldap.modifyAttributes(group)` để ghi.

### 7.3. Khi nào context delta vẫn có thể gặp lost update?

Dirty tracking chỉ tốt nếu adapter gửi delta theo từng giá trị. Nếu service:

1. Lookup toàn bộ `member`.
2. Chỉnh danh sách trong Java.
3. Gọi `setAttributeValues("member", fullList)`.

thì vẫn là REPLACE toàn tập và vẫn có lost update.

Ngay cả khi dùng `addAttributeValue`/`removeAttributeValue`, context snapshot có thể cũ và kết quả tính delta có thể gặp cạnh tranh trên **cùng một giá trị**. Nếu yêu cầu là “chỉ sửa khi trạng thái entry vẫn đúng version tôi đã đọc”, cần cơ chế conditional update/assertion nếu server hỗ trợ; dirty tracking tự nó không phải optimistic locking.

### 7.4. Khi attribute không được lookup trả về

Nếu ACL/projection không trả `member`, adapter không biết tập giá trị gốc. Khi đó `removeAttributeValue` có thể không tạo delta vì giá trị không hiện diện trong snapshot. Nếu chỉ cần gỡ đúng một DN và account có quyền Modify, gửi `ModificationItem(REMOVE_ATTRIBUTE, ...)` trực tiếp có thể phù hợp hơn.

Đừng suy ra attribute không tồn tại trên server chỉ vì `getStringAttributes("member")` trả null; có thể bind account không có quyền đọc hoặc query không yêu cầu attribute đó.

## 8. Lỗi trùng và thiếu giá trị

LDAP server kiểm tra giá trị theo equality matching rule của attribute.

| Thao tác | Trạng thái hiện tại | Kết quả thường gặp |
| --- | --- | --- |
| ADD `member=DN-A` | DN-A đã có | `attributeOrValueExists` (LDAP result code 20). |
| ADD `member=DN-A` | DN-A chưa có | Thêm thành công nếu schema/ACL cho phép. |
| REMOVE `member=DN-A` | DN-A không có | `noSuchAttribute` (LDAP result code 16). |
| REMOVE `member=DN-A` | DN-A có và không vi phạm schema | Gỡ giá trị. |
| REMOVE attribute không chỉ định value | Attribute tồn tại | Xóa toàn attribute; rất nguy hiểm nếu ý định chỉ gỡ một member. |

### 8.1. Equality matching rule quan trọng

LDAP không so sánh mọi giá trị như Java `String.equals`. Matching rule do schema quyết định:

- Có attribute so sánh không phân biệt hoa/thường.
- DN-valued attribute được so sánh theo quy tắc DN matching.
- Một số attribute dùng binary/octet-string hoặc matching rule riêng.

Không tự lowercase DN hoặc UID rồi kết luận chúng tương đương. Hãy dựng DN qua `LdapNameBuilder` và để server thực thi matching rule.

### 8.2. Đặt nghĩa cho “đảm bảo có mặt” và “đảm bảo vắng mặt”

Hai API business có thể là:

- `ensureMember(group, user)`: sau khi hoàn tất, giá trị DN user phải có trong attribute.
- `ensureNotMember(group, user)`: sau khi hoàn tất, giá trị DN user phải không còn.

Chúng khác với lệnh thấp tầng:

- `addMember`: yêu cầu ADD; nếu đã tồn tại, server có thể trả code 20.
- `removeMember`: yêu cầu REMOVE; nếu không tồn tại, server có thể trả code 16.

Một service có thể coi hai result code đó là **trạng thái mong muốn đã đạt**, nhưng chỉ khi đã kiểm tra chính xác operation, DN, attribute, giá trị và policy. Không catch chung mọi lỗi rồi coi là idempotent success.

## 9. Retry và idempotency khi kết nối bị ngắt

### 9.1. Tình huống response bị mất

```text
Client                         LDAP server
  |                                 |
  | Modify: ADD member=Hoa          |
  |------------------------------->|
  |                         Apply ADD
  |                         Commit entry
  |<--- ModifyResponse success ----X  Network lost
  |
  | Client timeout: không biết đã ghi?
```

Nếu retry ADD ngay:

- Nếu request trước chưa tới server: retry có thể thêm Hoa.
- Nếu request trước đã thành công: retry có thể trả `attributeOrValueExists`.
- Nếu một actor đã gỡ Hoa giữa hai lần: retry có thể thêm Hoa trở lại, trái với ý định mới nhất.

### 9.2. Quy trình reconcile trước khi retry

```text
1. Nhận timeout / CommunicationException.
2. Không advance sync checkpoint.
3. Đọc lại group membership bằng một connection mới.
4. So sánh trạng thái hiện tại với desired state và source version.
5. Nếu đã đúng: đánh dấu event đã áp dụng.
6. Nếu chưa đúng và event vẫn còn hợp lệ: gửi delta tương ứng.
7. Nếu có event mới hơn: áp dụng thứ tự nghiệp vụ hoặc đưa vào reconciliation.
```

Ví dụ, một event cũ yêu cầu ADD Hoa nhưng sau đó có event mới hơn yêu cầu REMOVE Hoa. Consumer không được retry event cũ sau khi đã xử lý event mới hơn.

### 9.3. Idempotency key cho event

Event sync có thể mang:

```json
{
  "eventId": "group-event-2026-000042",
  "groupStableId": "group-7f2a",
  "memberStableId": "user-8c13",
  "operation": "ADD",
  "sourceVersion": "opaque-version"
}
```

Đây là **schema event do ứng dụng định nghĩa**, không phải format LDAP. Consumer nên lưu event đã xử lý hoặc source version để không áp dụng lặp theo thứ tự sai. Không dùng DN làm idempotency key duy nhất nếu DN có thể thay đổi khi user rename/move.

## 10. Hai writer cùng sửa một member: nghiệp vụ quyết định kết quả

ADD/REMOVE theo value giảm lost update giữa các member khác nhau. Nhưng khi cùng một giá trị bị sửa đồng thời:

### 10.1. Hai request ADD cùng DN

```text
Initial: {Linh, An}

A: ADD Hoa
B: ADD Hoa

Một request được xử lý trước -> thành công.
Request sau -> thường attributeOrValueExists.

Final: {Linh, An, Hoa}
```

Nếu mục tiêu là ensure-present, service có thể coi duplicate là đã đạt desired state sau khi xác minh. Nếu event biểu diễn “mỗi lần thêm” có audit riêng, vẫn phải lưu nhận biết event dù membership không đổi.

### 10.2. Một request ADD và một request REMOVE cùng DN

```text
Initial: {Linh, An}

Thứ tự 1: ADD Hoa -> REMOVE Hoa
Final: {Linh, An}

Thứ tự 2: REMOVE Hoa -> ADD Hoa
Final: {Linh, An, Hoa}
```

Kết quả phụ thuộc thứ tự server xử lý. LDAP không biết business rule như “lệnh của quản trị viên ưu tiên”, “event có timestamp mới hơn thắng” hoặc “deny membership luôn thắng”.

Nếu nghiệp vụ cần xác định ai thắng:

- Serialize các lệnh theo `groupStableId` ở một tầng điều phối có tính nhất quán.
- Dùng source sequence/version và loại bỏ event cũ.
- Lưu membership desired state ở một nguồn authoritative và reconcile.
- Hoặc dùng conditional update/assertion control nếu server hỗ trợ.

Không thể giải quyết xung đột nghiệp vụ chỉ bằng cách chọn ADD thay cho REPLACE.

## 11. Conditional update bằng LDAP Assertion Control

RFC 4528 định nghĩa **Assertion Control**: client gửi một LDAP filter condition cùng update operation. Server chỉ thực hiện operation nếu điều kiện trên entry đích đúng; điều kiện và update được đánh giá như một thao tác nguyên tử.

Ví dụ khái niệm:

```text
Modify group entry
  Assertion: (modifyTimestamp=20261126120000Z)
  Changes:
    ADD member=uid=hoa,ou=people,...

Nếu modifyTimestamp không còn bằng giá trị đã đọc:
  server trả assertionFailed (122)
  không áp dụng thay đổi.
```

Điều này có thể hỗ trợ optimistic concurrency cho entry nếu server triển khai control và có thuộc tính/version phù hợp. Tuy nhiên:

- Không phải mọi LDAP server hỗ trợ RFC 4528.
- Không phải mọi client API Spring LDAP mức cao đều cung cấp tiện ích cho control này; có thể cần JNDI request controls hoặc extension phù hợp.
- `modifyTimestamp` có thể có độ phân giải/semantics phụ thuộc server; không tự coi là version counter không trùng.
- Assertion filter phải kiểm tra đúng điều kiện; nếu dùng một attribute nghiệp vụ, cần kiểm soát ai được thay đổi nó.

Không đưa code assertion control giả định vào production nếu chưa kiểm tra OID, encoding, criticality, server support và JNDI provider. Hãy dùng test tích hợp để xác minh server từ chối stale update bằng code `assertionFailed`.

### 11.1. Assertion không thay thế delta

Nếu chỉ thêm Hoa, vẫn nên gửi `ADD_ATTRIBUTE`. Assertion Control thêm **điều kiện** cho phép update, không biến một REPLACE toàn tập thành thiết kế tốt. Với thao tác một giá trị không xung đột, delta vẫn đơn giản và ít rủi ro hơn.

## 12. Một số khác biệt theo directory

### 12.1. OpenLDAP với groupOfNames

- `member` thường chứa DN đầy đủ.
- Schema `groupOfNames` yêu cầu ít nhất một `member`.
- ACL có thể giới hạn ai được thêm/gỡ member và ai được đọc membership.
- Overlay `memberof` (nếu được cấu hình) có thể duy trì reverse membership attribute; đó là cấu hình server, không phải tác dụng tự động của client.

### 12.2. Active Directory

- `member` là linked attribute của group; có quy tắc liên kết và replication riêng.
- Với group lớn, server có thể yêu cầu **range retrieval** khi đọc member; một search thông thường không nhất thiết trả toàn bộ danh sách.
- `primaryGroupID` là cơ chế riêng cho primary group; không thể chỉ đọc `member` rồi suy ra mọi membership.
- Một số thuộc tính liên kết có hành vi backlink/forward-link được server quản lý.
- Phải xét group scope/type, domain boundary và ACL khi thay đổi membership.

Không áp dụng nguyên xi ví dụ `groupOfNames`/`member` của OpenLDAP cho AD mà không xác minh schema và behavior. API Modify vẫn có thể gửi delta, nhưng semantics membership tổng thể của directory phụ thuộc vendor.

### 12.3. Referral và nhiều replica

Nếu group nằm trong naming context khác hoặc server trả referral:

- Xác định operation được gửi tới server nào.
- Kiểm tra credential và TLS trên referral endpoint.
- Không giả định hai replica có read-after-write tức thì.
- Reconcile trên đúng authoritative source hoặc chấp nhận replication lag theo policy.

Nếu client đọc từ replica chậm sau khi ghi thành công ở server khác, nó có thể thấy trạng thái cũ. Đừng gửi ADD/REMOVE lặp chỉ vì một replica chưa cập nhật.

## 13. Đồng bộ hai chiều: tách desired state khỏi delta

Một job đồng bộ có thể nhận sự kiện từ HR, IAM hoặc hệ thống ứng dụng:

```text
Source of truth
    |
    | event: ADD user Hoa to developers
    v
Sync consumer
    |
    | validate groupStableId/memberStableId
    | deduplicate eventId / sourceVersion
    v
LDAP ModifyRequest
    ADD member=HoaDN
    |
    v
LDAP group entry
    |
    +--> record result / checkpoint
```

Khi có nhiều nguồn cùng sửa:

- Xác định **authoritative owner** của membership: LDAP, HR, IAM hay một hệ thống trung tâm.
- Nếu LDAP là source of truth, consumer không nên ghi đè các thay đổi quản trị viên bằng snapshot từ hệ thống khác mà không có quy tắc.
- Nếu hệ thống ngoài là source of truth, LDAP là projection; cần reconcile từng member theo delta thay vì REPLACE toàn group mỗi lần poll.
- Ghi nhận nguồn tạo thay đổi, actor, thời điểm và version để điều tra xung đột.

### 13.1. Đồng bộ snapshot theo tập mong muốn

Đôi khi nghiệp vụ thật sự yêu cầu đồng bộ toàn bộ membership từ source of truth. Có thể tính:

```text
toAdd    = desiredMembers - currentMembers
toRemove = currentMembers - desiredMembers
```

Sau đó gửi các ADD/REMOVE theo giá trị. Nhưng **snapshot currentMembers có thể đã cũ** trước khi apply delta. Nếu có writer ngoài source of truth, cần:

1. Quy định ai có quyền thay đổi group.
2. Serialize hoặc conditional update nếu cần.
3. Dùng delta trên từng member.
4. Chạy reconciliation định kỳ để sửa drift.
5. Không xóa thành viên chỉ vì snapshot nguồn thiếu dữ liệu do paging/ACL/timeout.

### 13.2. Đọc đủ membership trước khi reconcile

Với group lớn:

- Phải xử lý paging/range retrieval theo server.
- Kiểm tra SearchResultDone và referral.
- Phân biệt attribute bị ẩn với attribute rỗng.
- Không coi page thiếu hoặc partial result là snapshot đầy đủ.
- Chỉ advance checkpoint khi toàn bộ batch được xử lý bền vững.

Một snapshot không đầy đủ kết hợp REPLACE toàn tập là một trong những cách nguy hiểm nhất để làm mất membership.

## 14. Ví dụ service Java: add/remove với lỗi nghiệp vụ rõ ràng

Service dưới đây giới hạn tên attribute và xây DN từ UID/Group ID đã được validate. Đây là ví dụ cho schema dùng `member` chứa DN đầy đủ.

```java
package com.example.directory;

import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class GroupMembershipService {

    private final LdapTemplate ldap;

    public GroupMembershipService(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public void addMember(String groupCn, String memberUid) {
        Name groupDn = groupDn(groupCn);
        Name memberDn = personDn(memberUid);

        ModificationItem add = new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("member", memberDn.toString())
        );
        ldap.modifyAttributes(groupDn, new ModificationItem[] {add});
    }

    public void removeMember(String groupCn, String memberUid) {
        Name groupDn = groupDn(groupCn);
        Name memberDn = personDn(memberUid);

        ModificationItem remove = new ModificationItem(
            DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("member", memberDn.toString())
        );
        ldap.modifyAttributes(groupDn, new ModificationItem[] {remove});
    }

    private Name groupDn(String cn) {
        validateRdnValue(cn);
        return LdapNameBuilder.newInstance("ou=groups")
            .add("cn", cn)
            .build();
    }

    private Name personDn(String uid) {
        validateRdnValue(uid);
        return LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();
    }

    private void validateRdnValue(String value) {
        if (value == null || value.isBlank() || value.length() > 128) {
            throw new IllegalArgumentException("Invalid directory identifier");
        }
    }
}
```

Các giới hạn cần nhớ:

- Ví dụ giả định user nằm trực tiếp trong `ou=people`; nếu DN thực tế nhiều OU, hãy resolve DN từ repository/search bằng stable ID hoặc directory mapping phù hợp.
- Validate độ dài/blank chỉ là kiểm tra đầu vào cơ bản, không thay authorization và uniqueness check.
- `LdapNameBuilder` xử lý biểu diễn RDN; không cho phép caller chọn OU tùy ý.
- Method để nguyên exception của Spring LDAP cho tầng service/controller phân loại. Production cần map duplicate/missing membership và lỗi ACL/schema thành kết quả nghiệp vụ rõ ràng.

### 14.1. Không tạo filter từ group/member input

Để tìm user/group, dùng `LdapQueryBuilder` hoặc escape filter theo RFC 4515. Đừng viết:

```java
// KHÔNG an toàn nếu groupCn đến từ request.
String filter = "(cn=" + groupCn + ")";
```

DN escaping và filter escaping là hai cú pháp khác nhau. Dùng `LdapNameBuilder` để xây DN; dùng query builder để xây filter.

## 15. Chẩn đoán lỗi và cách phản ứng

| Lỗi/result code | Nguyên nhân thường gặp | Hành động |
| --- | --- | --- |
| `attributeOrValueExists` (20) | ADD một member đã tồn tại theo matching rule. | Với ensure-present, xác minh state rồi coi là đạt; không nuốt mọi lỗi. |
| `noSuchAttribute` (16) | REMOVE giá trị không có hoặc attribute không tồn tại. | Đọc lại state, phân biệt đã bị gỡ với DN/attribute sai. |
| `noSuchObject` (32) | DN group hoặc parent/base sai, entry không tồn tại. | Xác minh group DN, base DN và replica. |
| `insufficientAccessRights` (50) | Bind account không được phép sửa membership. | Kiểm tra ACL ở group; không dùng admin làm workaround. |
| `objectClassViolation` (65) | Vi phạm schema, ví dụ xóa member cuối của groupOfNames. | Kiểm tra MUST/MAY và mô hình group. |
| `constraintViolation` (19) | Policy/server constraint, uniqueness hoặc size limit theo vendor. | Đọc diagnostic nội bộ, đối chiếu policy/schema. |
| `CommunicationException` | Network/TLS/timeout; có thể response bị mất sau khi server ghi. | Re-read/reconcile trước retry. |
| `PartialResultException` | Referral/partial search hoặc kết quả không đầy đủ. | Không coi snapshot là đầy đủ; xử lý referral/scope. |
| Đọc lại thấy state cũ sau success | Replica lag hoặc đọc nhầm server. | Kiểm tra topology, authoritative source và replication. |

### 15.1. Phân biệt “member không tồn tại” với “không có quyền đọc”

Nếu `getStringAttributes("member")` trả null, có thể:

- Group không có attribute đó.
- Query chỉ yêu cầu các attribute khác.
- ACL ẩn `member` với principal hiện tại.
- Server/replica trả kết quả không đầy đủ.

Đừng tự động dùng REPLACE rỗng hoặc xóa attribute. Một bind account có quyền Modify nhưng không có quyền Read vẫn có thể thực hiện delta cụ thể theo ACL; phải xác nhận bằng policy và test, không suy đoán.

### 15.2. Không log toàn bộ membership

Danh sách group member có thể tiết lộ danh tính, vai trò và quyền truy cập. Log:

- Group stable ID hoặc mã nội bộ đã kiểm soát.
- Operation ADD/REMOVE.
- Event ID/source version và kết quả.
- LDAP result code/loại lỗi.
- Số lượng giá trị thay đổi.

Tránh log toàn bộ DN, email, tên người dùng hoặc payload membership nếu không có lý do và quyền truy cập audit phù hợp.

## 16. Integration test: hai writer không ghi đè nhau

Test cần chạy trên LDAP **test directory** có group và OU fixture, service account được phép Modify. Để chứng minh hành vi, ta thực hiện hai delta độc lập và đọc lại tập membership từ server.

### 16.1. Fixture và helper

```java
package com.example.directory;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class ConcurrentMembershipDeltaIT {

    @Autowired
    private LdapTemplate ldap;

    @Test
    void independentAddAndRemovePreserveBothIntents() throws Exception {
        String suffix = UUID.randomUUID().toString().replace("-", "")
            .substring(0, 10);
        String groupCn = "lab-" + suffix;
        Name groupDn = groupDn(groupCn);
        String linhDn = personDn("linh").toString();
        String anDn = personDn("an").toString();
        String hoaDn = personDn("hoa-" + suffix).toString();

        Attributes attrs = new BasicAttributes(true);
        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("groupOfNames");
        attrs.put(classes);
        attrs.put("cn", groupCn);
        Attribute initialMembers = new BasicAttribute("member");
        initialMembers.add(linhDn);
        initialMembers.add(anDn);
        attrs.put(initialMembers);

        boolean created = false;
        try {
            ldap.bind(groupDn, null, attrs);
            created = true;

            // Hai writer chờ cùng một latch rồi gửi delta song song.
            ModificationItem addHoa = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", hoaDn)
            );
            ModificationItem removeAn = new ModificationItem(
                DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("member", anDn)
            );

            ExecutorService writers = Executors.newFixedThreadPool(2);
            CountDownLatch ready = new CountDownLatch(2);
            CountDownLatch start = new CountDownLatch(1);
            try {
                Future<?> addTask = writers.submit(() -> {
                    ready.countDown();
                    start.await();
                    ldap.modifyAttributes(
                        groupDn, new ModificationItem[] {addHoa});
                    return null;
                });
                Future<?> removeTask = writers.submit(() -> {
                    ready.countDown();
                    start.await();
                    ldap.modifyAttributes(
                        groupDn, new ModificationItem[] {removeAn});
                    return null;
                });

                assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
                start.countDown();
                addTask.get(10, TimeUnit.SECONDS);
                removeTask.get(10, TimeUnit.SECONDS);
            } finally {
                start.countDown();
                writers.shutdownNow();
                writers.awaitTermination(5, TimeUnit.SECONDS);
            }

            String[] members = ldap.lookup(
                groupDn,
                new String[] {"member"},
                (org.springframework.ldap.core.AttributesMapper<String[]>)
                    ConcurrentMembershipDeltaIT::readMembers
            );

            assertThat(members)
                .contains(linhDn, hoaDn)
                .doesNotContain(anDn);
        } finally {
            if (created) {
                ldap.unbind(groupDn);
            }
        }
    }

    private static String[] readMembers(Attributes attributes)
            throws javax.naming.NamingException {
        Attribute member = attributes.get("member");
        if (member == null) return new String[0];
        java.util.List<String> values = new java.util.ArrayList<>();
        javax.naming.NamingEnumeration<?> all = member.getAll();
        try {
            while (all.hasMore()) {
                values.add(String.valueOf(all.next()));
            }
        } finally {
            all.close();
        }
        return values.toArray(String[]::new);
    }

    private static Name groupDn(String cn) {
        return LdapNameBuilder.newInstance("ou=groups")
            .add("cn", cn).build();
    }

    private static Name personDn(String uid) {
        return LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid).build();
    }
}
```

Mapper của test được ép kiểu `AttributesMapper<String[]>` để chọn đúng overload `lookup` đọc `Attributes`. Fixture `linh`/`an` phải tồn tại nếu server có referential integrity kiểm tra DN member. Test chưa được build/chạy trong bước biên soạn này.

### 16.2. Bản mapper rõ ràng hơn cho project

Nếu muốn tách mapper khỏi lời gọi lookup, có thể khai báo rõ:

```java
AttributesMapper<String[]> memberMapper =
    ConcurrentMembershipDeltaIT::readMembers;

String[] members = ldap.lookup(
    groupDn,
    new String[] {"member"},
    memberMapper
);
```

`readMembers` phải xử lý `NamingException` và đóng `NamingEnumeration`; không dùng `toString()` trên cả object `Attribute` vì kết quả đó không phải danh sách DN ổn định để so sánh.

### 16.3. Test thật sự song song

Để kiểm thử concurrency, chạy hai task đồng thời bằng `ExecutorService`/`CountDownLatch`:

1. Cả hai task cùng đợi latch.
2. Task A gửi `ADD member=Hoa`.
3. Task B gửi `REMOVE member=An`.
4. Mở latch để hai task cùng bắt đầu.
5. Đợi cả hai response.
6. Đọc lại membership bằng connection mới.
7. Xác nhận Linh và Hoa còn, An không còn.

Kết quả kỳ vọng không phụ thuộc thứ tự vì hai thao tác tác động lên hai DN member khác nhau. Đây là test phù hợp để phát hiện code vô tình dùng REPLACE toàn tập.

**Lưu ý:** test này kiểm tra tính bảo toàn hai delta độc lập; nó không chứng minh mọi race trên cùng một member có kết quả cố định.

## 17. Các trường hợp test bổ sung

| Trường hợp | Thao tác | Kỳ vọng |
| --- | --- | --- |
| ADD một DN chưa có | ADD_ATTRIBUTE | Thành công, các member cũ vẫn còn. |
| ADD DN đã có | ADD_ATTRIBUTE | Duplicate result; state vẫn có một giá trị theo equality rule. |
| REMOVE DN đang có | REMOVE_ATTRIBUTE | Chỉ DN đó bị gỡ. |
| REMOVE DN không có | REMOVE_ATTRIBUTE | noSuchAttribute hoặc kết quả theo server; reconcile desired state. |
| Hai ADD khác DN đồng thời | Hai ModifyRequest | Cả hai DN được giữ. |
| Hai REMOVE khác DN đồng thời | Hai ModifyRequest | Cả hai DN bị gỡ, trừ ràng buộc schema. |
| ADD và REMOVE cùng DN | Hai ModifyRequest | Kết quả theo thứ tự server; business rule quyết định. |
| Hai delta trong một ModifyRequest | ADD + REMOVE | Server áp dụng theo thứ tự, nguyên tử trên entry group. |
| REPLACE từ stale snapshot | Một writer thêm, writer khác replace | Test chứng minh member mới có thể bị mất. |
| Xóa member cuối groupOfNames | REMOVE_ATTRIBUTE | Bị schema từ chối nếu vi phạm MUST. |
| ACL không cho Modify | ADD/REMOVE | insufficientAccessRights. |
| Timeout sau Modify | Cắt response | Re-read trước retry. |
| Read ACL không có nhưng Modify được phép | REMOVE trực tiếp | Kiểm tra behavior theo server policy; không suy luận từ snapshot null. |
| Active Directory group lớn | Range retrieval | Đọc đầy đủ membership theo cơ chế AD. |

## 18. Checklist trước khi đồng bộ membership

- [ ] Đã xác định group objectClass và attribute thành viên thực tế.
- [ ] Đã biết DN member có đầy đủ, đúng base và được escape an toàn.
- [ ] Chỉ thêm một thành viên bằng `ADD_ATTRIBUTE`.
- [ ] Chỉ xóa một thành viên bằng `REMOVE_ATTRIBUTE` có value cụ thể.
- [ ] Không dùng `REPLACE_ATTRIBUTE` từ snapshot có thể cũ khi chỉ muốn thay đổi delta.
- [ ] Hiểu một ModifyRequest nguyên tử trên một entry, không phải transaction nhiều group/hệ thống.
- [ ] Đã định nghĩa cách xử lý duplicate ADD và missing REMOVE.
- [ ] Sau timeout, đọc lại/reconcile trước khi retry.
- [ ] Có source version/event ID để chống event cũ và lặp.
- [ ] Có quy tắc phân xử khi ADD/REMOVE cùng một member đồng thời.
- [ ] Đã xem xét Assertion Control nếu cần conditional update và server hỗ trợ.
- [ ] Đã kiểm tra schema groupOfNames/groupOfUniqueNames/AD group và ràng buộc member cuối.
- [ ] Không coi snapshot Search là đầy đủ nếu ACL, paging, referral hoặc range retrieval chưa hoàn tất.
- [ ] Có integration test trên directory riêng với hai writer.
- [ ] Có audit và metrics không làm lộ toàn bộ membership.

## 19. Bài tập vận dụng

1. Cho `member={Linh, An, Minh}`. Hãy viết ba ModificationItem để thêm Hoa, xóa An và thay toàn bộ tập thành `{Linh, Minh}`. Giải thích operation nào giữ được thay đổi ngoài snapshot.
2. Mô tả interleaving của hai writer: A thêm Hoa, B xóa An. Vì sao hai delta theo value bảo toàn cả hai ý định?
3. Thay hai thao tác trên bằng hai lần `REPLACE_ATTRIBUTE` dựa trên cùng snapshot. Viết timeline chứng minh lost update.
4. Vì sao `DirContext.REMOVE_ATTRIBUTE` với BasicAttribute không có value có thể xóa cả attribute `member`?
5. LDAP trả `attributeOrValueExists` khi ADD. Trường hợp nào có thể coi là idempotent success, và cần kiểm tra gì trước?
6. Một request REMOVE bị timeout sau khi gửi. Làm sao xác định server đã xóa member chưa mà không gây lỗi nghiệp vụ khi retry?
7. Hai writer cùng ADD/REMOVE một DN. Vì sao LDAP không thể biết “lệnh mới hơn” nếu ứng dụng không cung cấp version/ordering?
8. Thiết kế một event sync có `eventId`, `groupStableId`, `memberStableId`, operation và sourceVersion.
9. Giải thích atomicity của một ModifyRequest và vì sao không mở rộng sang 20 group hoặc LDAP+SQL.
10. Thiết kế một test `ExecutorService`/`CountDownLatch` để hai delta khác member chạy đồng thời.
11. Với `groupOfNames`, vì sao xóa thành viên cuối cùng có thể bị schema từ chối? Đề xuất group model phù hợp nếu cần nhóm rỗng.
12. Với Active Directory group lớn, tại sao Search một lần có thể không trả toàn bộ `member`? Nêu cách xử lý range retrieval và primary group.
13. Một adapter `DirContextOperations` không thấy `member` do ACL. Vì sao removeAttributeValue có thể không tạo delta?
14. Khi nào cần LDAP Assertion Control? Những điều kiện nào cần xác minh về server/client?

## 20. Tài liệu tham khảo

- [RFC 4511 — LDAP Protocol, Section 4.6 Modify Operation](https://www.rfc-editor.org/rfc/rfc4511): ADD/DELETE/REPLACE semantics, thứ tự và atomicity của một ModifyRequest.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528): conditional update, test-and-set/test-and-clear và assertionFailed.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): `modifyAttributes(Name, ModificationItem[])` và `modifyAttributes(DirContextOperations)`.
- [Spring LDAP API — DirContextOperations](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/DirContextOperations.html): `addAttributeValue`, `removeAttributeValue`, update mode và modification tracking.
- [Spring LDAP — Simplifying Attribute Access and Manipulation with DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html): đọc/sửa attribute và tạo modification delta.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và ODM mapping cho entry/group.
- [Oracle Java SE 17 — DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html): `ADD_ATTRIBUTE`, `REMOVE_ATTRIBUTE`, `REPLACE_ATTRIBUTE` và JNDI Modify.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): attribute syntax, equality matching rules, objectClass và schema.
- [RFC 4514 — LDAP Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): biểu diễn/escape DN thành viên.
- [Microsoft Learn — Active Directory Attribute Range Retrieval](https://learn.microsoft.com/en-us/windows/win32/adsi/attribute-range-retrieval): đọc membership attribute có nhiều giá trị.
- [Microsoft Learn — Group Objects](https://learn.microsoft.com/en-us/windows/win32/ad/group-objects): các thuộc tính và semantics group trong Active Directory.
- [OpenLDAP Administrator's Guide — Overlays](https://www.openldap.org/doc/admin26/overlays.html): overlay và behavior phụ trợ có thể ảnh hưởng membership/reference.
