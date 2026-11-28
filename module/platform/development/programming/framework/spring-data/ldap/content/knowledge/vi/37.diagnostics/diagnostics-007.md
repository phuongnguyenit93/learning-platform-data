# Đổi DN làm mất liên kết nhóm hoặc tham chiếu trong LDAP

## 1. Vì sao đổi DN có thể làm hỏng những liên kết đang tồn tại?

Trong **Spring Data LDAP**, mỗi entry trong directory được định danh bằng một **Distinguished Name (DN)**. DN biểu diễn vị trí của entry trong cây thư mục, ví dụ:

~~~text
uid=alice,ou=people,dc=example,dc=org
~~~

Các entry khác có thể lưu DN này như giá trị thuộc tính để tạo quan hệ. Ví dụ nhóm `reviewers` có thể chứa:

~~~ldif
dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: reviewers
uniqueMember: uid=alice,ou=people,dc=example,dc=org
~~~

Nếu Alice chuyển từ `ou=people` sang `ou=contractors`, DN mới trở thành:

~~~text
uid=alice,ou=contractors,dc=example,dc=org
~~~

Entry Alice vẫn có thể tồn tại, nhưng giá trị `uniqueMember` của nhóm có thể vẫn trỏ tới DN cũ. Ứng dụng tìm Alice theo DN mới thành công, trong khi truy vấn membership hoặc tham chiếu từ hệ thống khác lại thất bại.

Đây là vấn đề quan trọng khi dùng LDAP làm nguồn dữ liệu cho danh bạ, tài khoản, nhóm và phân quyền. **Đổi DN là thay đổi tên/vị trí entry; nó không mặc định là một thao tác cập nhật mọi tham chiếu trên toàn hệ thống.**

Bài học tập trung vào:

1. Hiểu thao tác LDAP **ModifyDN** và ảnh hưởng của nó tới DN.
2. Nhận diện các thuộc tính có thể chứa DN như `member`, `uniqueMember`, `manager`, `owner` và `seeAlso`.
3. Phân biệt hành vi referential integrity giữa OpenLDAP, Active Directory và các directory khác.
4. Dùng Spring LDAP để rename/move entry và cập nhật tham chiếu có kiểm soát.
5. Giữ định danh ổn định, xử lý cache và bản sao dữ liệu, kiểm thử các tình huống rename thất bại giữa chừng.

> **Nguyên tắc:** DN là tên phân cấp có thể thay đổi. Nếu ứng dụng cần nhận diện một đối tượng qua rename, hãy dùng định danh ổn định do directory cung cấp khi có thể, đồng thời có chiến lược duy trì mọi tham chiếu DN.

## 2. DN, RDN và các tham chiếu trong directory

### 2.1. Phân biệt DN và RDN

Một DN được ghép từ một hoặc nhiều thành phần **Relative Distinguished Name (RDN)**:

~~~text
uid=alice,ou=people,dc=example,dc=org
|---------| |---------| |-------------|
   RDN 1       RDN 2        RDN 3
~~~

- `uid=alice` là RDN của entry Alice trong OU `people`.
- `ou=people` xác định nhánh cha.
- `dc=example,dc=org` xác định naming context.
- DN đầy đủ xác định một entry trong directory; DN tương đối trong ứng dụng phụ thuộc base DN của `ContextSource`.

Khi `ContextSource.base=dc=example,dc=org`, Spring LDAP thường nhận DN tương đối:

~~~text
uid=alice,ou=people
~~~

Trong khi thuộc tính tham chiếu như `member` thường lưu **DN đầy đủ**:

~~~text
uid=alice,ou=people,dc=example,dc=org
~~~

Đừng trộn hai dạng này khi tìm hoặc cập nhật tham chiếu.

### 2.2. Một DN có thể xuất hiện ở nhiều nơi

Ví dụ cây directory:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice
│   └── uid=bob
├── ou=groups
│   ├── cn=reviewers
│   │   └── uniqueMember: uid=alice,ou=people,...
│   └── cn=developers
│       └── uniqueMember: uid=alice,ou=people,...
└── ou=applications
    └── cn=approval-workflow
        └── manager: uid=alice,ou=people,...
~~~

DN Alice có thể được tham chiếu bởi:

| Thuộc tính | Ý nghĩa thường gặp | Ghi chú |
| --- | --- | --- |
| `member` | Thành viên nhóm | Thường dùng với `groupOfNames`; giá trị có cú pháp DN |
| `uniqueMember` | Thành viên nhóm có định danh duy nhất | Theo schema chuẩn có cú pháp `NameAndOptionalUID`, không luôn chỉ là DN thuần |
| `manager` | Người quản lý của entry | Thường là thuộc tính DN-valued |
| `owner` | Chủ sở hữu entry/đối tượng | Phụ thuộc schema ứng dụng |
| `seeAlso` | Entry liên quan | Có thể chứa một hoặc nhiều DN |
| `secretary` | Thư ký hoặc liên hệ được chỉ định | Phụ thuộc schema |
| `memberOf` | Nhóm chứa người dùng | Thường là backlink/operational attribute do server hoặc vendor quản lý, không phải luôn là thuộc tính người dùng tự ghi |

Ngoài các thuộc tính chuẩn, ứng dụng có thể định nghĩa custom attribute chứa DN. Vì vậy, **không thể chỉ tìm `member` rồi cho rằng đã tìm hết tham chiếu**. Cần kiểm kê schema, `objectClass` và quy ước của các ứng dụng tiêu thụ directory.

### 2.3. DN-valued attribute không phải khóa ngoại SQL

LDAP không tự áp dụng đầy đủ các quy tắc khóa ngoại như cơ sở dữ liệu quan hệ. Việc một thuộc tính có cú pháp DN chỉ cho biết giá trị được biểu diễn như tên entry; điều đó **không đồng nghĩa server luôn kiểm tra entry đích còn tồn tại** hoặc tự sửa mọi tham chiếu khi rename.

Một số server có extension/plugin referential integrity; một số loại thuộc tính được quản lý như linked attributes; các thuộc tính tùy biến có thể không được bảo vệ. Hành vi thực tế phải được xác minh trên đúng directory và schema đang triển khai.

## 3. LDAP ModifyDN thay đổi điều gì?

LDAPv3 định nghĩa thao tác **ModifyDN** để đổi RDN và/hoặc chuyển entry sang parent khác. Về khái niệm, request có các thông tin:

- DN hiện tại của entry (`entry`).
- RDN mới (`newrdn`).
- Cờ `deleteoldrdn`: có xóa giá trị RDN cũ khỏi attribute tương ứng hay không.
- `newSuperior` tùy chọn: DN của parent mới khi di chuyển entry.

Ví dụ:

~~~text
DN cũ:
uid=alice,ou=people,dc=example,dc=org

DN mới:
uid=alice,ou=contractors,dc=example,dc=org
~~~

Đây là thao tác chuyển entry từ parent `ou=people` sang `ou=contractors`, giữ RDN `uid=alice`.

### 3.1. Đổi RDN có thể thay đổi cả thuộc tính naming

Ví dụ đổi UID:

~~~text
Trước:
uid=alice,ou=people,dc=example,dc=org
uid: alice

Sau:
uid=alice.nguyen,ou=people,dc=example,dc=org
uid: alice.nguyen
~~~

Với `deleteOldRDN=true`, server xóa giá trị RDN cũ khỏi thuộc tính tương ứng nếu giá trị đó không còn được dùng trong RDN mới. Với `deleteOldRDN=false`, giá trị cũ được giữ lại.

Điều này ảnh hưởng tới các ứng dụng đang tìm theo `uid`, các quy tắc uniqueness và những thuộc tính khác phụ thuộc vào giá trị naming. Nếu cần giữ UID cũ như alias, phải thiết kế thuộc tính/alias riêng theo schema và hành vi server; không dựa vào việc giữ old RDN một cách ngẫu nhiên.

### 3.2. Di chuyển entry sang parent mới

Một thao tác ModifyDN có thể bao gồm `newSuperior` để chỉ parent mới. Ví dụ:

~~~text
uid=alice,ou=people,dc=example,dc=org
             |
             | ModifyDN / newSuperior
             v
uid=alice,ou=contractors,dc=example,dc=org
~~~

Các giới hạn cần kiểm tra:

- Parent đích phải tồn tại và cho phép Add/ModifyDN.
- DN đích không được xung đột với entry khác.
- Server có thể giới hạn việc di chuyển qua naming context hoặc partition.
- Quyền ModifyDN/rename có thể khác quyền Modify attribute thông thường.
- Di chuyển một entry cha có thể làm thay đổi DN của toàn bộ subtree con; phải kiểm tra hỗ trợ và chính sách của server.
- Referral, replication và ACL trên cả nhánh nguồn lẫn đích có thể ảnh hưởng kết quả.

Không giả định mọi LDAP server cho phép chuyển entry qua mọi OU hoặc qua mọi naming context. Một số môi trường yêu cầu quy trình tạo bản sao rồi xóa nguồn khi chuyển giữa partition/server; đây là workflow khác với một ModifyDN đơn lẻ.

## 4. Vì sao tham chiếu nhóm có thể bị mất?

### 4.1. Server không tự động cập nhật mọi DN-valued attribute

Giả sử nhóm có:

~~~ldif
dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: reviewers
uniqueMember: uid=alice,ou=people,dc=example,dc=org
~~~

Sau khi Alice được rename/move, có thể xảy ra:

~~~text
Entry Alice:
  DN mới = uid=alice,ou=contractors,dc=example,dc=org

Group reviewers:
  uniqueMember = uid=alice,ou=people,dc=example,dc=org
~~~

Khi ứng dụng tìm DN mới trong `uniqueMember`, không tìm thấy Alice. Giá trị cũ có thể trở thành **dangling reference** (tham chiếu treo).

Đây không nhất thiết là lỗi của Spring Data LDAP. Spring Data LDAP không thể suy ra mọi attribute trong mọi schema và mọi ứng dụng bên ngoài cần cập nhật như thế nào. ModifyDN được thực thi ở directory server; việc duy trì tham chiếu tùy khả năng server và cấu hình.

### 4.2. OpenLDAP: Referential Integrity overlay

OpenLDAP có overlay **`slapo-refint`** (Referential Integrity overlay) có thể cấu hình để duy trì các thuộc tính DN-valued được chỉ định khi entry bị rename hoặc xóa.

Các điểm cần biết:

- Overlay phải được **cấu hình và bật**; không nên giả định OpenLDAP nào cũng đã bật.
- Danh sách attribute cần theo dõi phải được cấu hình theo schema và yêu cầu hệ thống, ví dụ `member`, `manager`, `owner`.
- Theo tài liệu OpenLDAP, các attribute trong `refint_attributes` phải có syntax `distinguishedName`. `uniqueMember` theo schema chuẩn có syntax `NameAndOptionalUID`, vì vậy không mặc định rằng `slapo-refint` sẽ duy trì attribute này như `member`; cần kiểm tra khả năng hỗ trợ và kiểm thử đúng phiên bản.
- Nếu overlay phải loại giá trị cuối cùng khỏi một attribute bắt buộc, cấu hình `refint_nothing` có thể được dùng để cung cấp giá trị thay thế phù hợp schema. Đây là quyết định quản trị directory, không nên tự chèn một DN giả từ ứng dụng.
- Quyền và phạm vi database/backend có thể ảnh hưởng overlay.
- Cần kiểm tra hành vi với rename, move và delete trên phiên bản OpenLDAP thực tế.
- Custom DN-valued attribute không tự động được xử lý nếu không nằm trong cấu hình overlay phù hợp.

Nếu `slapo-refint` đã tự cập nhật `member`, ứng dụng không nên chạy thêm một vòng thay thế mù quáng. Sau rename, hãy **đọc lại tham chiếu** để xác nhận server đã làm đúng.

### 4.3. Active Directory: linked attributes và backlink

Active Directory có mô hình **linked attributes** cho một số quan hệ. Ví dụ, `member` là forward link của nhóm và `memberOf` là backlink được directory duy trì theo quan hệ đó.

Với thuộc tính có link semantics hoặc syntax `Object(DS-DN)` phù hợp, Active Directory quản lý giá trị như tham chiếu tới đối tượng và cập nhật giá trị DN khi đối tượng được rename hoặc move. Điều này giúp các liên kết nhóm như `member` tiếp tục trỏ tới đối tượng, thay vì chỉ giữ một chuỗi DN do ứng dụng tự duy trì.

Tuy nhiên:

- Không phải mọi attribute có cú pháp DN đều là linked attribute.
- `manager` hoặc custom attribute phải được kiểm tra theo schema/link metadata và hành vi AD cụ thể.
- Một attribute chỉ có syntax chứa chuỗi DN không nhất thiết là linked attribute. Kiểm tra `linkID`/schema metadata hoặc tài liệu thuộc tính trước khi dựa vào cơ chế tự cập nhật.
- Backlink như `memberOf` có cách đọc và quyền khác với forward link.
- Hành vi replication, Global Catalog và phạm vi domain có thể ảnh hưởng kết quả quan sát.
- Không chuyển giả định về AD sang OpenLDAP hoặc directory khác.

**Kết luận:** cần kiểm tra attribute cụ thể trên server. Đừng suy ra “AD tự sửa tất cả DN references” chỉ vì `memberOf` hoạt động sau một lần rename.

### 4.4. Nhóm lồng nhau và tham chiếu nhiều cấp

Nếu một nhóm chứa DN của nhóm khác, rename nhóm con có thể ảnh hưởng liên kết từ nhóm cha. Ví dụ:

~~~text
cn=engineering,ou=groups,...
    member -> cn=developers,ou=groups,...

cn=developers,ou=groups,...
    member -> uid=alice,ou=people,...
~~~

Có thể có nhiều cấp tham chiếu. Chỉ cập nhật nhóm trực tiếp chứa Alice là chưa đủ nếu Alice chính là **entry nhóm** được tham chiếu ở nơi khác. Hãy kiểm tra toàn bộ attribute có khả năng tham chiếu DN, gồm quan hệ nhóm lồng nhau và custom references.

## 5. DN có phải định danh ổn định không?

**Không.** DN xác định vị trí hiện tại của entry, nên có thể thay đổi khi:

- Đổi RDN, ví dụ `uid=alice` thành `uid=alice.nguyen`.
- Chuyển OU, ví dụ `ou=people` sang `ou=contractors`.
- Đổi tên hoặc di chuyển một parent entry, khiến DN của toàn bộ descendant thay đổi.
- Di chuyển entry sang một nhánh khác trong cùng naming context.

Nếu ứng dụng dùng DN làm primary key cục bộ, rename có thể tạo ra hai bản ghi logic cho cùng một người hoặc làm hỏng foreign references trong database riêng.

### 5.1. Ưu tiên stable identifier khi server hỗ trợ

Một số directory cung cấp ID ổn định qua rename:

| Directory/attribute | Mô tả | Lưu ý |
| --- | --- | --- |
| `entryUUID` | Operational attribute được định nghĩa trong RFC 4530 ở các server hỗ trợ | Không có ở mọi server; phải yêu cầu/đọc theo quyền |
| `objectGUID` | Định danh nhị phân phổ biến trong Active Directory | Cần xử lý đúng binary representation |
| Mã nhân viên do tổ chức cấp | Định danh nghiệp vụ | Chỉ ổn định nếu quy trình tổ chức bảo đảm duy nhất và không tái sử dụng |
| DN | Vị trí entry hiện tại | Có thể thay đổi, không nên coi là immutable ID |

Mô hình bản sao nội bộ có thể lưu:

~~~text
directory_id: corp-directory
stable_id:    <entryUUID hoặc objectGUID>
current_dn:   uid=alice,ou=contractors,dc=example,dc=org
uid:          alice
last_seen_at: 2026-11-26T10:00:00Z
~~~

Khi rename, cập nhật `current_dn` theo stable ID. Không tạo user mới chỉ vì DN khác. Nếu directory không cung cấp stable ID, cần chọn một khóa nghiệp vụ có hợp đồng uniqueness rõ ràng hoặc thiết kế bước đối soát/ghép nối thủ công.

### 5.2. ODM và Repository giữ DN trong `@Id`

Một entity Spring LDAP thường dùng:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name value) { dn = value; }

    public String getUid() { return uid; }
    public void setUid(String value) { uid = value; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String value) { commonName = value; }

    public String getSurname() { return surname; }
    public void setSurname(String value) { surname = value; }
}
~~~

Khi entry đã được rename:

- `findById(oldDn)` có thể không còn tìm thấy entry.
- Entity Java đã nạp trước rename có thể vẫn giữ DN cũ trong field `@Id`.
- `save(entity)` với DN cũ có thể tác động sai entry hoặc thất bại.
- Ứng dụng cần đọc lại bằng DN mới và cập nhật bản sao/cache theo stable ID.

Không kỳ vọng Spring Data LDAP tự động sửa tất cả entity đang nằm trong memory, repository cache, database hoặc token chứa DN cũ.

### 5.3. Không nhầm cập nhật ODM với LDAP ModifyDN

Đổi field `@Id` hoặc các field `@DnAttribute` rồi gọi `save`/`update` không nên được xem là tương đương với một LDAP ModifyDN. Tài liệu API Spring LDAP mô tả rằng trong một số đường `ObjectDirectoryMapper` update, khi DN được tính lại khác DN hiện tại, implementation có thể thực hiện **unbind entry cũ rồi bind entry mới**. Đây là hành vi khác với server-side ModifyDN.

Sự khác biệt quan trọng: một thao tác unbind + bind không nhất thiết kích hoạt cùng cơ chế referential integrity mà server chạy khi nhận ModifyDN (`modrdn`). Nó cũng có thể ảnh hưởng operational attributes, audit và replication theo cách khác. Vì vậy:

- Dùng `LdapTemplate.rename(oldDn, newDn)` khi yêu cầu nghiệp vụ là một thao tác ModifyDN được server xử lý.
- Chỉ dùng đường ODM update để đổi DN sau khi đã kiểm tra hành vi của đúng phiên bản Spring LDAP và chấp nhận các hệ quả của nó.
- Sau thao tác, xác minh entry bằng stable ID và đọc lại các DN-valued references; không suy ra referential integrity chỉ từ việc method trả về thành công.

Tham khảo API `LdapOperations.update` và `LdapTemplate.rename` trong tài liệu Spring LDAP ở cuối bài.

## 6. Thực hiện rename/move bằng Spring LDAP

### 6.1. Dựng DN bằng `LdapNameBuilder`

Giả sử `ContextSource.base=dc=example,dc=org`. Spring LDAP có thể nhận DN tương đối:

~~~java
import javax.naming.Name;

import org.springframework.ldap.support.LdapNameBuilder;

Name oldDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "alice")
    .build();

Name newDn = LdapNameBuilder.newInstance("ou=contractors")
    .add("uid", "alice")
    .build();
~~~

Dùng `LdapNameBuilder` để xử lý thành phần DN chứa ký tự đặc biệt. Không tự ghép chuỗi bằng phép cộng hoặc `split(",")`; escape của DN theo RFC 4514 khác với escape của LDAP filter theo RFC 4515.

### 6.2. Rename bằng `LdapTemplate`

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;

public final class PersonDnService {

    private final LdapTemplate ldapTemplate;

    public PersonDnService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void moveAlice(Name oldDn, Name newDn) {
        // Cả hai DN được hiểu tương đối với ContextSource base.
        // Parent đích phải tồn tại và server phải cho phép ModifyDN.
        ldapTemplate.rename(oldDn, newDn);
    }
}
~~~

`LdapTemplate.rename(...)` thực hiện thao tác đổi tên entry thông qua Spring LDAP/JNDI. Với trường hợp chuyển parent, hãy xác minh phiên bản Spring LDAP, JNDI provider và LDAP server hỗ trợ thao tác ModifyDN có `newSuperior` tương ứng. Ví dụ này giả định hai DN nằm trong cùng naming context mà `ContextSource` đang truy cập.

**Trước khi gọi rename**, nên kiểm tra:

1. DN cũ tồn tại và thuộc phạm vi nghiệp vụ được phép.
2. Parent mới tồn tại, đúng naming context và có quyền ModifyDN.
3. DN mới chưa bị entry khác chiếm.
4. Các attribute cấu thành RDN mới phù hợp schema.
5. Các tham chiếu DN có thể bị ảnh hưởng đã được kiểm kê.
6. Job/consumer đang cập nhật cùng entry được điều phối để tránh race.

### 6.3. Đổi RDN và `deleteOldRDN`

API rename mức cao có thể không bộc lộ mọi chi tiết của ModifyDN request. Nếu nghiệp vụ cần quyết định chính xác việc giữ giá trị RDN cũ, cần dùng API Spring LDAP/JNDI phù hợp với phiên bản đang dùng và kiểm tra tham số `deleteOldRDN`.

Ví dụ đổi UID:

~~~text
Old DN: uid=alice,ou=people,dc=example,dc=org
New DN: uid=alice.nguyen,ou=people,dc=example,dc=org
~~~

Nếu xóa old RDN, giá trị `uid=alice` có thể bị bỏ khỏi attribute `uid`; nếu giữ old RDN, attribute có thể còn cả hai giá trị nếu schema cho phép. Không nên dùng nhiều giá trị UID như alias nếu schema/ứng dụng không được thiết kế cho điều đó.

### 6.4. Khi move cả subtree

Nếu di chuyển một OU chứa nhiều entry con, DN của các descendant cũng thay đổi theo đường dẫn mới. Trước khi thực hiện:

- Xác định số lượng entry con và mọi DN reference trỏ tới chúng.
- Kiểm tra server hỗ trợ rename/move non-leaf entry.
- Kiểm tra ACL trên subtree nguồn và parent đích.
- Đánh giá giới hạn thời gian, replication và ảnh hưởng đến các ứng dụng.
- Có kế hoạch cập nhật mapping DN cho toàn bộ descendant, không chỉ OU gốc.

Không thử nghiệm subtree move trực tiếp trên production khi chưa xác minh hành vi server và tác động của các tham chiếu.

## 7. Kiểm kê tham chiếu trước khi đổi DN

### 7.1. Lập reference inventory

| Nơi tham chiếu | Cách tìm | Câu hỏi cần trả lời |
| --- | --- | --- |
| Group `member` | Search nhóm theo DN cũ | Có bao nhiêu nhóm trực tiếp chứa entry? |
| Group `uniqueMember` | Search theo NameAndOptionalUID phù hợp | Có optional UID component cần giữ không? |
| `manager`, `owner`, `seeAlso` | Search các objectClass/attribute liên quan | Thuộc tính đơn trị hay đa trị? |
| Nested groups | Search nhóm có chứa DN của nhóm được đổi | Có quan hệ nhiều cấp không? |
| Custom schema | Đọc schema và tài liệu ứng dụng | Attribute nào lưu DN hoặc chuỗi DN? |
| Database nội bộ | Tìm cột `current_dn`/reference | Có khóa ngoại hoặc index dựa vào DN không? |
| Cache/session/token | Kiểm tra cache key, claim và payload | Có DN cũ cần invalidate/expire không? |
| Hệ thống tích hợp | Kiểm tra mapping/export/event | Consumer nào lưu DN cũ? |

Không phải mọi chuỗi trông giống DN đều là DN syntax; có ứng dụng lưu DN trong một attribute text tùy biến. Cũng có attribute DN-valued nhưng server tự duy trì bằng referential integrity. Cần hiểu từng trường hợp trước khi cập nhật.

### 7.2. Đọc tham chiếu bằng LDAP Search

Ví dụ kiểm tra các nhóm có `member` bằng DN cũ. Dùng `LdapQueryBuilder` để mã hóa assertion value:

~~~java
import java.util.List;

import javax.naming.Name;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public List<Name> findGroupsReferencingMember(
        LdapTemplate ldapTemplate,
        String oldFullDn) {

    LdapQuery q = query()
        .base("ou=groups")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("groupOfNames")
        .and("member").is(oldFullDn);

    return ldapTemplate.search(
        q,
        (ContextMapper<Name>) context ->
            ((DirContextOperations) context).getDn()
    );
}
~~~

Ví dụ giả định `ContextSource.base=dc=example,dc=org`, group entry nằm trong `ou=groups`, và server dùng `groupOfNames/member`. `getDn()` trả DN của group trong ngữ cảnh mapper để dùng tiếp với các thao tác Spring LDAP tương ứng.

Với `groupOfUniqueNames`, cần truy vấn `uniqueMember` và xử lý đúng syntax **NameAndOptionalUID**. Không dùng nguyên ví dụ `member` cho mọi loại nhóm.

**Không nối** `oldFullDn` vào filter string. DN có ký tự như `*`, `(`, `)` hoặc dấu gạch chéo ngược cần được encode theo filter rules. Cách escape DN và cách escape filter assertion value là hai tầng khác nhau.

### 7.3. Tham chiếu có thể nằm ngoài nhánh đang tìm

Nếu chỉ Search `ou=groups`, kết quả không bao gồm tham chiếu trong `ou=applications`, `ou=services`, naming context khác hoặc directory server khác. Hãy lập phạm vi theo:

- Các naming context mà ứng dụng quản lý.
- Schema và custom attributes.
- Referral/partition/topology.
- Quyền đọc của service account.
- Các hệ thống bên ngoài LDAP.

Search không trả kết quả có thể do ACL hoặc scope, không nhất thiết chứng minh không có tham chiếu.

## 8. Cập nhật tham chiếu khi server không tự duy trì

### 8.1. Xác định trước ai chịu trách nhiệm

Có hai chiến lược:

**Chiến lược A — Directory server duy trì tham chiếu.** Nếu server có referential integrity overlay hoặc linked attribute được xác nhận sẽ tự sửa, hãy để server xử lý. Sau rename, đọc lại các tham chiếu quan trọng để xác minh. Không cập nhật thủ công lần hai nếu server đã thay đổi chúng.

**Chiến lược B — Ứng dụng duy trì tham chiếu.** Nếu server không tự cập nhật một attribute, ứng dụng cần tìm các entry chứa DN cũ và thay bằng DN mới theo một workflow có kiểm soát.

Không trộn hai chiến lược một cách tùy tiện. Nếu server tự đổi `member` nhưng ứng dụng cũng cố xóa giá trị cũ/thêm giá trị mới, có thể gặp lỗi “không tồn tại giá trị cũ” hoặc thêm trùng.

### 8.2. Ví dụ thay một giá trị `member` trong entry nhóm

Ví dụ dưới đây chỉ áp dụng cho attribute `member` có cú pháp DN thuần. Sau khi đã xác minh server không tự duy trì liên kết, ứng dụng có thể thay giá trị trong từng group entry:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;

public void replaceMemberReference(
        LdapTemplate ldapTemplate,
        Name groupDn,
        String oldFullDn,
        String newFullDn) {

    ModificationItem[] changes = {
        new ModificationItem(
            DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("member", oldFullDn)
        ),
        new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("member", newFullDn)
        )
    };

    // Hai thay đổi được gửi trong một LDAP Modify cho cùng entry nhóm.
    ldapTemplate.modifyAttributes(groupDn, changes);
}
~~~

Các điểm quan trọng:

- `groupDn` là DN của **entry nhóm**, không phải DN của Alice; truyền đúng dạng tương đối/đầy đủ theo `ContextSource`.
- `oldFullDn` và `newFullDn` là giá trị **DN đầy đủ** lưu trong attribute `member`.
- Hai ModificationItem được gửi trong một Modify request cho **một entry**; đây không phải transaction nguyên tử bao trùm tất cả group entries.
- Nếu giá trị cũ đã bị server tự cập nhật hoặc bị thay đổi đồng thời, thao tác remove có thể thất bại. Cần đọc lại và đối soát.
- Nếu nhóm dùng `groupOfNames`, schema yêu cầu `member`; xóa thành viên cuối có thể vi phạm schema.
- Cần quyền Modify trên group entry và attribute.
- Không dùng code này cho `uniqueMember` có NameAndOptionalUID nếu chưa bảo toàn optional UID component.

### 8.3. Cập nhật nhiều nhóm là workflow nhiều bước

Một người có thể là thành viên của nhiều nhóm. Mỗi group entry là một LDAP entry riêng, do đó việc thay tham chiếu ở nhiều nhóm tạo thành nhiều Modify operation:

~~~text
1. Rename Alice
2. Update cn=reviewers: member old DN -> new DN
3. Update cn=developers: member old DN -> new DN
4. Update cn=on-call: member old DN -> new DN
5. Verify all references
~~~

Nếu bước 4 thất bại, các bước trước có thể đã thành công. LDAP không mặc định cung cấp transaction ACID xuyên nhiều entry, và `@Transactional` của Spring không tự biến chuỗi thao tác đó thành một transaction LDAP.

Cần một workflow có thể tiếp tục hoặc bù trừ:

- Lưu operation ID và old/new DN.
- Lưu danh sách tham chiếu đã phát hiện.
- Ghi trạng thái từng bước: pending, applied, verified, failed.
- Retry có điều kiện từng tham chiếu sau khi đọc trạng thái hiện tại.
- Chạy reconciliation để tìm giá trị cũ còn sót.
- Chỉ đóng workflow khi mọi reference cần thiết đã được xác minh.

### 8.4. Race condition khi có cập nhật đồng thời

Trong lúc rename diễn ra, một ứng dụng khác có thể thêm Alice vào nhóm mới bằng DN cũ. Nếu inventory được chụp trước rename, tham chiếu mới này có thể bị bỏ sót.

Cách giảm rủi ro:

1. Dùng maintenance window hoặc khóa nghiệp vụ cho đối tượng đang đổi DN.
2. Tạm dừng/serialize các luồng cập nhật group membership nếu có thể.
3. Thu thập tham chiếu trước khi rename.
4. Thực hiện rename và cập nhật tham chiếu theo chiến lược server/application đã chọn.
5. Search lại DN cũ trên toàn bộ attribute đã kiểm kê.
6. Lặp reconciliation cho đến khi không còn tham chiếu cũ trong phạm vi được quản lý.
7. Gỡ khóa và cho phép luồng cập nhật hoạt động trở lại.

Không có cách nào bảo đảm nhất quán tuyệt đối giữa nhiều entry và nhiều hệ thống chỉ bằng một lần gọi `LdapTemplate.rename`.

## 9. Quy trình rename an toàn từ đầu đến cuối

~~~mermaid
flowchart TD
    A["Nhận yêu cầu đổi DN"] --> B["Xác minh stable ID, old DN, new DN"]
    B --> C["Kiểm tra parent, schema, quyền và xung đột"]
    C --> D["Kiểm kê references và server referential integrity"]
    D --> E["Điều phối / khóa các thay đổi liên quan"]
    E --> F["Thực hiện ModifyDN"]
    F --> G{"Server tự cập nhật reference?"}
    G -->|Có| H["Đọc lại và xác minh liên kết"]
    G -->|Không| I["Thay DN cũ bằng DN mới ở từng reference"]
    I --> H
    H --> J["Cập nhật DB, cache và hệ thống tích hợp"]
    J --> K{"Còn reference cũ hoặc lỗi bước?"}
    K -->|Có| L["Retry có điều kiện / reconciliation"]
    L --> H
    K -->|Không| M["Ghi audit và hoàn tất"]
~~~

### 9.1. Preflight

Trước khi gửi ModifyDN:

- Đọc entry theo DN cũ bằng tài khoản vận hành.
- Đọc stable identifier như `entryUUID` hoặc `objectGUID` nếu server hỗ trợ.
- Xác minh DN mới chưa tồn tại.
- Xác minh parent mới và naming context.
- Kiểm tra `objectClass`, MUST attributes và giá trị RDN mới.
- Xác định server có `slapo-refint`, linked attributes hoặc cơ chế tương đương không.
- Tìm các tham chiếu DN ở group, manager, owner và custom attributes.
- Xác định hệ thống ngoài LDAP nào đang lưu DN.

### 9.2. Thực hiện và xác minh

Sau rename:

1. Lookup DN mới và xác minh stable ID vẫn là đối tượng ban đầu.
2. Lookup DN cũ để xác nhận không còn entry tại vị trí cũ, trừ khi có alias hoặc một entry khác hợp lệ.
3. Đọc lại các nhóm và attribute tham chiếu đã phát hiện.
4. Search lại old DN trong tất cả naming context/attribute được quản lý.
5. Kiểm tra các descendant nếu di chuyển subtree.
6. Cập nhật bản sao nội bộ, cache và mapping DN.
7. Ghi audit gồm operation ID, stable ID, DN cũ/mới, người yêu cầu, kết quả từng bước.

### 9.3. Nếu một phần workflow thất bại

Không tự động rename ngược ngay khi một group update lỗi. Rename ngược cũng là một ModifyDN mới, có thể gặp xung đột hoặc tạo thêm tham chiếu treo.

Thay vào đó:

- Giữ operation ở trạng thái **partial**.
- Đọc lại trạng thái directory hiện tại.
- Xác định server đã tự cập nhật những reference nào.
- Chỉ tiếp tục thay đổi các reference còn trỏ DN cũ.
- Nếu phải rollback, tạo kế hoạch bù trừ dựa trên trạng thái quan sát được, không dựa vào giả định “lần trước chưa thành công”.
- Cảnh báo vận hành nếu chưa thể đưa quan hệ về trạng thái nhất quán.

## 10. Ảnh hưởng tới Spring Data LDAP Repository và cache ứng dụng

### 10.1. Repository ID cũ không tự đổi

Với entity:

~~~java
@Id
private Name dn;
~~~

DN là ID mà repository dùng để định vị entry. Sau khi rename, đối tượng Java đã nạp trước đó không tự biết DN mới. Vì vậy:

~~~java
repository.findById(oldDn); // Có thể không còn tìm thấy
repository.findById(newDn); // Tìm entry sau rename
~~~

Nếu application service giữ object cũ trong memory, cần cập nhật lại ID hoặc đọc lại entity theo DN mới. Tránh gọi `save(oldEntity)` sau rename khi chưa xác minh hành vi và DN của object.

### 10.2. Cache và dữ liệu ngoài LDAP

Các nơi sau có thể lưu DN cũ:

- Cache key hoặc cache value.
- Bản ghi SQL có cột `ldap_dn`.
- Search index.
- Message queue/outbox đang chờ xử lý.
- JWT claim hoặc session attribute.
- Cấu hình tích hợp và audit reference.
- Các ứng dụng tiêu thụ LDAP khác.

Một cache key dựa vào DN có thể làm một người xuất hiện như hai đối tượng sau rename. Nếu dùng stable ID làm cache key, chỉ cần cập nhật thuộc tính DN hiện tại; nếu không có stable ID, cần một quy trình alias/mapping hoặc invalidation rõ ràng.

Không nên nhúng DN thay đổi vào token dài hạn nếu ứng dụng cần phân giải lại identity sau rename. Dùng định danh ổn định trong claim khi chính sách bảo mật và IAM cho phép, rồi resolve DN hiện tại theo nguồn tin cậy.

### 10.3. Tham chiếu trong database nội bộ

Nếu bảng ứng dụng dùng DN làm foreign key logic, cần migration/transaction nội bộ để cập nhật các hàng liên quan. Tuy nhiên, cập nhật DB và LDAP là hai hệ thống khác nhau; không mặc định một transaction SQL bao trùm LDAP.

Một mô hình outbox/workflow có thể ghi nhận yêu cầu rename, cập nhật LDAP, sau đó đồng bộ các bản ghi nội bộ và đánh dấu hoàn tất. Khi lỗi giữa chừng, job reconciliation tiếp tục theo operation ID và trạng thái thực tế.

## 11. Chẩn đoán khi nhóm không còn nhận ra người dùng sau rename

### 11.1. Các triệu chứng thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Alice tìm được theo DN mới nhưng không thuộc `reviewers` | `member`/`uniqueMember` còn DN cũ | Đọc entry nhóm và so giá trị reference |
| `memberOf` biến mất sau move | Backlink/server behavior hoặc replication | Kiểm tra forward link, schema và server cụ thể |
| Search theo DN cũ vẫn trả entry | Rename chưa thực hiện, alias hoặc replica chưa đồng bộ | Kiểm tra cùng endpoint và stable ID |
| Group A được cập nhật, Group B không | Workflow nhiều entry dở dang hoặc ACL khác nhau | Đọc từng group, kiểm tra operation state |
| Repository tìm thấy hai bản ghi | Local cache/database dùng DN làm key | So stable ID và current DN |
| Rename thành công nhưng group query rỗng | Server không có referential integrity cho attribute đó | Kiểm tra overlay/linked attribute và giá trị raw |
| Chỉ một ứng dụng bị lỗi | Ứng dụng lưu DN trong cache/token/DB riêng | Kiểm tra mapping và thời gian cache |
| Nested group không còn cấp quyền | Tham chiếu tới DN của group hoặc user chưa được cập nhật | Duyệt các cấp group và kiểm tra policy |
| Xóa thành viên cuối bị từ chối | Schema yêu cầu `member`/`uniqueMember` | Kiểm tra MUST attribute và lỗi schema |
| Một số replica thấy DN mới, số khác thấy cũ | Replication lag | Đối chiếu node, thời điểm và stable ID |

### 11.2. Quy trình debug

1. Dùng cùng endpoint, bind identity và naming context để lookup DN mới.
2. Kiểm tra stable ID nhằm xác định đó là cùng một entry.
3. Đọc raw group entry với attribute `member` hoặc `uniqueMember`.
4. Kiểm tra các DN-valued attributes như `manager`, `owner`, `seeAlso`.
5. Kiểm tra server có referential integrity overlay hoặc linked attribute phù hợp không.
6. Tìm kiếm DN cũ trong các nhánh được phép và mọi naming context liên quan.
7. Kiểm tra cache, DB, token và hệ thống tích hợp.
8. Đối chiếu replication và ACL trước khi kết luận reference đã mất.

Ví dụ kiểm tra thủ công một nhóm:

~~~bash
ldapsearch -LLL -x \\
  -H ldaps://ldap.example.org:636 \\
  -D "uid=app-reader,ou=service-accounts,dc=example,dc=org" -W \\
  -b "cn=reviewers,ou=groups,dc=example,dc=org" -s base \\
  "(objectClass=*)" dn cn member uniqueMember
~~~

Không đưa password trực tiếp vào command line. Output chứa DN/quan hệ người dùng có thể nhạy cảm; chỉ lưu ở môi trường vận hành được phép. Nếu attribute không xuất hiện, kiểm tra quyền và yêu cầu trả attribute trước khi kết luận nó không tồn tại.

## 12. Kiểm thử rename và tham chiếu trong LDAP test directory

Mock `LdapTemplate.rename(...)` chỉ chứng minh service gọi method; nó không kiểm tra server có cập nhật DN, schema và referential integrity như mong muốn. Cần integration test với đúng loại directory hoặc container có cấu hình gần production.

### 12.1. Fixture LDIF

Một fixture đơn giản:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=contractors,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: contractors

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen

dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: reviewers
uniqueMember: uid=alice,ou=people,dc=example,dc=org
~~~

Fixture giả định root `dc=example,dc=org` đã tồn tại hoặc được tạo trước. `groupOfUniqueNames` yêu cầu `uniqueMember`; nếu dùng schema khác, điều chỉnh entry theo đúng server.

### 12.2. Integration test cho rename

~~~java
import javax.naming.Name;
import javax.naming.ldap.LdapName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class PersonRenameIntegrationTest {

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void renameMovesEntryToNewDn() throws Exception {
        Name oldDn = new LdapName("uid=alice,ou=people");
        Name newDn = new LdapName("uid=alice,ou=contractors");

        ldapTemplate.rename(oldDn, newDn);

        var alice = ldapTemplate.lookup(
            newDn,
            new String[] {"uid", "cn"},
            attrs -> new String[] {
                String.valueOf(attrs.get("uid").get()),
                String.valueOf(attrs.get("cn").get())
            }
        );

        assertThat(alice[0]).isEqualTo("alice");
        assertThat(alice[1]).isEqualTo("Alice Nguyen");
    }
}
~~~

Test này chỉ chứng minh **entry đã được chuyển**. Nó chưa chứng minh `uniqueMember` được cập nhật. Cần thêm assertion đọc group entry sau rename. Với DN cũ, viết assertion theo exception cụ thể của phiên bản Spring LDAP đang dùng (ví dụ lỗi không tìm thấy entry), không nên giữ `Exception.class` chung trong suite cuối cùng.

### 12.3. Test referential integrity của server

Với fixture có nhóm `reviewers`, thực hiện:

1. Đọc `uniqueMember` trước rename.
2. Rename Alice.
3. Đọc lại group entry.
4. Kiểm tra server đã cập nhật `uniqueMember` sang DN mới hay chưa.
5. Nếu server không tự cập nhật, kiểm tra workflow ứng dụng thay thế reference.
6. Xác minh không còn DN cũ trong các group entry được quản lý.
7. Kiểm tra nhóm vẫn thỏa schema, đặc biệt khi có quy tắc bắt buộc tối thiểu một member.

Tách test theo hai cấu hình:

- **Server có referential integrity:** xác nhận overlay/linked attribute thực sự tự cập nhật.
- **Server không có referential integrity:** xác nhận application workflow phát hiện và thay thế tham chiếu.

Không dùng embedded LDAP khác vendor để kết luận hành vi production của Active Directory hoặc OpenLDAP overlay.

### 12.4. Test partial failure và retry

~~~text
1. Rename Alice: SUCCESS
2. Update reviewers: SUCCESS
3. Update developers: FAILURE
4. Restart workflow
5. Read current DN + stable ID
6. Detect developers still references old DN
7. Replace only the stale reference
8. Verify all managed references
~~~

Kỳ vọng:

- Không tạo Alice thứ hai.
- Không rename lại một entry đã ở DN mới.
- Không thêm trùng thành viên.
- Workflow có thể tiếp tục từ trạng thái thực tế.
- Không đánh dấu hoàn tất khi còn tham chiếu cũ.
- Lỗi ACL/network được phân loại, không chuyển thành “không có reference”.

## 13. Bảo mật và vận hành

- Chỉ cho service account quyền ModifyDN ở đúng OU được phép; quyền này nhạy cảm hơn read/search.
- Chỉ cấp quyền Modify trên các group attributes cần duy trì reference; không cấp write toàn directory.
- Dùng LDAPS/StartTLS, xác minh CA và hostname; không hạ TLS để thử rename.
- Filter chứa DN cũ phải dùng encoder/builder; escape DN và filter assertion value theo hai quy tắc riêng.
- Kiểm soát ai được yêu cầu đổi DN; không cho caller gửi arbitrary old/new DN rồi thực thi.
- Audit operation ID, stable ID, DN cũ/mới và trạng thái từng bước; tránh log dữ liệu nhạy cảm không cần thiết.
- Có cảnh báo cho partial rename, dangling references và workflow quá hạn.
- Nếu group membership dùng cho authorization, không giữ quyền cũ chỉ vì LDAP đang lỗi; áp dụng cache TTL và fail-safe policy đã xác định.
- Khi có replication, xác minh kết quả trên node phù hợp và tính đến độ trễ trước khi tuyên bố rename đã nhất quán toàn hệ thống.

## 14. Câu hỏi tự kiểm tra

1. DN và RDN khác nhau như thế nào? Vì sao DN có thể đổi khi entry vẫn là cùng một đối tượng?
2. LDAP ModifyDN gồm những thông tin chính nào? Vai trò của `newSuperior` và `deleteOldRDN` là gì?
3. Vì sao một nhóm có thể vẫn lưu DN cũ sau khi user được chuyển OU?
4. `member` khác `uniqueMember` như thế nào? Vì sao `uniqueMember` cần chú ý NameAndOptionalUID?
5. `memberOf` có phải thuộc tính chuẩn luôn được mọi LDAP server cung cấp không?
6. OpenLDAP `slapo-refint` giải quyết vấn đề gì và vì sao phải xác minh overlay đã bật?
7. Active Directory linked attributes có nghĩa mọi thuộc tính chứa DN đều tự cập nhật không?
8. Vì sao không nên dùng DN làm stable primary key cho bản sao nội bộ nếu có thể rename?
9. Khi repository entity đã nạp trước rename, điều gì xảy ra với field `@Id Name dn`?
10. Khi nào nên để directory tự duy trì reference, khi nào ứng dụng cần cập nhật thủ công?
11. Vì sao không thể cập nhật tất cả group references trong một transaction LDAP mặc định?
12. Nếu rename thành công nhưng một group update thất bại, workflow nên tiếp tục như thế nào?
13. Vì sao cần tìm references trong cả nested groups và custom DN-valued attributes?
14. Tại sao phải dùng `LdapNameBuilder` để tạo DN và `LdapQueryBuilder` để tìm DN trong filter?
15. Một full scan không tìm thấy DN cũ có đủ chứng minh không còn reference không? Cần xét ACL/scope nào?
16. Hãy thiết kế integration test phân biệt server tự cập nhật `member` với ứng dụng phải cập nhật thủ công.
17. Nếu di chuyển một OU cha, DN của các entry con và references đến chúng thay đổi ra sao?
18. Khi dùng `objectGUID` hoặc `entryUUID`, ứng dụng cần cập nhật những trường nào sau rename?
19. Vì sao không nên rollback bằng rename ngược ngay khi một bước cập nhật reference lỗi?
20. Nếu authorization cache vẫn chứa group membership cũ sau rename, cần chính sách invalidation nào?

## 15. Tổng kết

**Đổi DN là thay đổi tên/vị trí entry, không phải thao tác tự động cập nhật mọi liên kết trong directory và ứng dụng.** LDAP ModifyDN xử lý entry được đổi tên/di chuyển; các tham chiếu như `member`, `uniqueMember`, `manager`, `owner` hoặc custom attributes chỉ được duy trì nếu server có cơ chế phù hợp và đã được cấu hình. OpenLDAP referential integrity overlay, Active Directory linked attributes và các directory khác có hành vi riêng, không thể suy rộng lẫn nhau.

Trong Spring Data LDAP, `@Id Name` và `findById` gắn với DN hiện tại. Sau rename, cần đọc lại theo DN mới, cập nhật bản sao/cache và xác minh các reference. Dùng `LdapTemplate.rename` cho thao tác ModifyDN, `LdapQueryBuilder` để tìm tham chiếu, và `modifyAttributes` để thay DN-valued value khi ứng dụng chịu trách nhiệm duy trì quan hệ.

Một workflow an toàn phải có **stable identifier, reference inventory, server capability check, điều phối cập nhật, idempotency, reconciliation và audit**. Khi thao tác nhiều entry hoặc nhiều hệ thống thất bại giữa chừng, phải tiếp tục/đối soát theo trạng thái thực tế thay vì giả định có transaction toàn cục.

### Tài liệu tham khảo

- [RFC 4511 — LDAPv3 Protocol: ModifyDN Operation](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512).
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514).
- [RFC 4515 — LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515).
- [RFC 4519 — LDAP Schema for User Applications: groupOfNames and groupOfUniqueNames](https://www.rfc-editor.org/rfc/rfc4519).
- [RFC 4530 — entryUUID LDAP Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530).
- [OpenLDAP Administrator's Guide — Referential Integrity Overlay](https://www.openldap.org/doc/admin26/guide.html).
- [Microsoft Learn — Linked Attributes](https://learn.microsoft.com/en-us/windows/win32/ad/linked-attributes).
- [Microsoft Learn — Choosing an Active Directory Attribute Syntax](https://learn.microsoft.com/en-us/windows/win32/ad/choosing-a-syntax).
- [Spring LDAP Reference — Basic Usage and LdapTemplate](https://docs.spring.io/spring-ldap/reference/basic-usage.html).
- [Spring LDAP API — LdapOperations (rename and update)](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html).
- [Spring LDAP Reference — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html).
