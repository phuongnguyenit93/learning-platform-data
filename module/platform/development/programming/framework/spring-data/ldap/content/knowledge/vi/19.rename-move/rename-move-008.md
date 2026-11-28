# Thiết kế quy trình di chuyển có kiểm tra và phương án phục hồi

## 1. Di chuyển entry LDAP là một quy trình, không chỉ là một lệnh rename

Trong **Spring Data LDAP**, mỗi entry trong directory được định danh bằng **Distinguished Name (DN)**. DN mô tả vị trí của entry trong cây thư mục, ví dụ:

~~~text
uid=alice,ou=people,dc=example,dc=org
~~~

Khi Alice chuyển sang đơn vị nhà thầu, entry có thể được di chuyển tới nhánh khác:

~~~text
DN cũ: uid=alice,ou=people,dc=example,dc=org
DN mới: uid=alice,ou=contractors,dc=example,dc=org
~~~

Ở tầng LDAP, thao tác này thường được biểu diễn bằng **ModifyDN**. Spring LDAP cung cấp `LdapTemplate.rename(...)` để gửi thao tác tương ứng tới directory server.

Tuy nhiên, một yêu cầu di chuyển trong hệ thống thực tế còn có thể ảnh hưởng tới:

- Các nhóm lưu DN người dùng trong `member` hoặc `uniqueMember`.
- Các thuộc tính như `manager`, `owner`, `seeAlso` và custom attributes.
- Các entry con nếu di chuyển một OU hoặc subtree.
- Repository entity đang giữ DN cũ trong `@Id`.
- Database, cache, search index, session, token và hệ thống tích hợp.
- Các luồng ghi đồng thời có thể tiếp tục sử dụng DN cũ.
- Các replica có thể quan sát thay đổi ở thời điểm khác nhau.

Vì vậy, một lệnh `rename` thành công chỉ chứng minh server đã chấp nhận thao tác ModifyDN. Nó **không chứng minh toàn bộ quan hệ và bản sao dữ liệu đã nhất quán**.

Bài học hướng dẫn thiết kế một workflow di chuyển có kiểm tra, lưu tiến độ, có thể tiếp tục sau lỗi và có phương án phục hồi. Trọng tâm là **kiểm tra trước, thực hiện có điều phối, xác minh sau và chỉ hoàn tất khi các hậu điều kiện được đáp ứng**.

Sau bài này, người học có thể:

1. Phân biệt đổi RDN, chuyển parent và di chuyển subtree.
2. Xây dựng preflight để xác minh DN, stable ID, schema, quyền và tham chiếu.
3. Sử dụng `LdapTemplate.rename(...)` đúng phạm vi.
4. Thiết kế trạng thái workflow bền vững và xử lý lặp an toàn.
5. Phục hồi khi lỗi xảy ra trước, trong hoặc sau ModifyDN.
6. Phân biệt phục hồi tiến (roll forward) với thao tác bù trừ (compensation).
7. Kiểm thử quy trình trên directory tương ứng với môi trường triển khai.

> **Nguyên tắc:** Không quyết định thành công hay thất bại chỉ dựa vào việc client nhận được response. Sau lỗi giao tiếp, phải đọc lại trạng thái directory bằng định danh ổn định trước khi chạy lại thao tác.

## 2. Phân loại yêu cầu di chuyển

Trước khi thiết kế workflow, cần xác định chính xác yêu cầu đang thay đổi thành phần nào của DN.

### 2.1. Đổi RDN

Đổi thành phần định danh ở entry:

~~~text
Trước:
uid=alice,ou=people,dc=example,dc=org

Sau:
uid=alice.nguyen,ou=people,dc=example,dc=org
~~~

Thay đổi này có thể tác động tới attribute dùng làm RDN, chẳng hạn `uid`. Cờ `deleteOldRDN` trong LDAP ModifyDN quyết định giá trị RDN cũ có được xóa khỏi attribute tương ứng hay không.

Nếu giữ giá trị cũ, cần xác minh schema cho phép attribute đa trị và ứng dụng có thực sự dùng nó như alias hay không. Không tự coi việc giữ old RDN là một cơ chế alias phổ quát.

### 2.2. Chuyển entry sang parent khác

Giữ nguyên RDN nhưng đổi parent:

~~~text
Trước:
uid=alice,ou=people,dc=example,dc=org

Sau:
uid=alice,ou=contractors,dc=example,dc=org
~~~

LDAP ModifyDN có thể dùng `newSuperior` để chỉ parent mới. Cả parent nguồn và đích, naming context, quyền ModifyDN và chính sách của server đều cần được xác minh.

### 2.3. Di chuyển một subtree

Ví dụ di chuyển cả OU:

~~~text
Trước:
ou=engineering,ou=departments,dc=example,dc=org
├── uid=alice
├── uid=bob
└── ou=projects
    └── cn=atlas

Sau:
ou=engineering,ou=contractors,dc=example,dc=org
├── uid=alice
├── uid=bob
└── ou=projects
    └── cn=atlas
~~~

DN của các entry con cũng thay đổi vì DN được hình thành từ toàn bộ đường dẫn tới root. Trước khi move subtree, phải tính đến số lượng entry con, các tham chiếu tới từng entry và khả năng hỗ trợ non-leaf ModifyDN của directory server.

### 2.4. Di chuyển sang naming context hoặc directory khác

Di chuyển giữa các naming context, partition hoặc LDAP server có thể bị giới hạn bởi topology và implementation. Không giả định một `LdapTemplate.rename(...)` có thể di chuyển entry xuyên mọi server.

Nếu nguồn và đích thuộc các directory độc lập, thường phải thiết kế **migration workflow** gồm export/đọc dữ liệu, tạo entry ở đích, kiểm tra, chuyển tham chiếu/tích hợp và cuối cùng xử lý entry nguồn theo chính sách. Đây không phải một ModifyDN nguyên tử.

| Loại yêu cầu | Thay đổi chính | Rủi ro nổi bật |
| --- | --- | --- |
| Đổi RDN | Thành phần naming attribute | Old RDN, uniqueness và tham chiếu |
| Chuyển parent | `newSuperior` | Quyền, parent đích và DN references |
| Chuyển subtree | DN của entry cha và descendants | Phạm vi lớn, tham chiếu nhiều cấp |
| Chuyển naming context/server | Nguồn và đích ở các vùng directory khác nhau | Không có thao tác nguyên tử chung, replication và đồng bộ dữ liệu |

**Hợp đồng workflow phải ghi rõ loại di chuyển.** Không nhận một chuỗi `newDn` tùy ý từ request rồi mặc định nó là một move hợp lệ.

## 3. Mô hình directory và dữ liệu tham chiếu

Giả sử tổ chức có cấu trúc:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice
│   └── uid=bob
├── ou=contractors
├── ou=groups
│   ├── cn=reviewers
│   └── cn=developers
└── ou=applications
    └── cn=approval-workflow
~~~

Alice hiện nằm trong `ou=people`, được hai nhóm tham chiếu và là manager của một workflow:

~~~ldif
dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: reviewers
member: uid=alice,ou=people,dc=example,dc=org
member: uid=bob,ou=people,dc=example,dc=org

dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: developers
uniqueMember: uid=alice,ou=people,dc=example,dc=org

dn: cn=approval-workflow,ou=applications,dc=example,dc=org
objectClass: top
objectClass: applicationProcess
cn: approval-workflow
manager: uid=alice,ou=people,dc=example,dc=org
~~~

Khi Alice chuyển OU, các giá trị tham chiếu có thể vẫn chứa DN cũ nếu server không duy trì chúng tự động.

### 3.1. Lập danh sách loại tham chiếu

| Attribute | Ví dụ ý nghĩa | Điều cần kiểm tra |
| --- | --- | --- |
| `member` | Thành viên nhóm | DN-valued; nhóm có thể yêu cầu tối thiểu một member |
| `uniqueMember` | Thành viên nhóm có định danh duy nhất | Schema dùng `NameAndOptionalUID`; phải bảo toàn optional UID component |
| `manager` | Người quản lý | Có thể là attribute đơn trị |
| `owner` | Chủ sở hữu | Phụ thuộc schema và ứng dụng |
| `seeAlso` | Entry liên quan | Có thể đa trị |
| Custom DN attribute | Quan hệ do ứng dụng định nghĩa | Kiểm tra syntax và quy ước tiêu thụ |
| `memberOf` | Nhóm chứa user | Có thể là backlink/attribute do server quản lý, không nên mặc định tự ghi |

Không thể tìm mọi tham chiếu chỉ bằng cách Search `member`. Cần kiểm kê schema, objectClass, cấu hình referential integrity và các hệ thống tích hợp.

### 3.2. Server-managed hay application-managed reference?

Trước khi move, xác định ai chịu trách nhiệm duy trì từng liên kết:

- **Server-managed:** một cơ chế như OpenLDAP `slapo-refint` hoặc Active Directory linked attributes đã được cấu hình và xác minh cho đúng attribute.
- **Application-managed:** ứng dụng phải tìm entry chứa DN cũ và cập nhật giá trị.
- **External-managed:** database, cache hoặc hệ thống khác có quy trình riêng để cập nhật mapping.

OpenLDAP `slapo-refint` có giới hạn theo syntax được hỗ trợ; không mặc định mọi DN-like attribute, đặc biệt `uniqueMember` với `NameAndOptionalUID`, đều được overlay duy trì. Trong Active Directory, chỉ những attribute có linked-attribute semantics theo schema mới được server quản lý như link. Một attribute chỉ chứa chuỗi trông giống DN không tự động có referential integrity.

**Không để server và ứng dụng cùng cập nhật một reference mà không có quy ước rõ ràng.** Sau ModifyDN, đọc lại các liên kết quan trọng để xác nhận ai đã cập nhật.

## 4. Những bất biến cần xác định trước khi triển khai

Một workflow đáng tin cậy bắt đầu bằng việc định nghĩa **preconditions** và **postconditions**. Nếu không biết thế nào là trạng thái đúng, hệ thống không thể tự quyết định tiếp tục hay phục hồi.

### 4.1. Preconditions

Trước khi thực hiện, cần bảo đảm:

- Đối tượng nguồn được xác định bằng stable ID đáng tin cậy.
- DN nguồn hiện tại trỏ tới đúng stable ID.
- DN đích được tính từ quy tắc nghiệp vụ được phép.
- Parent đích tồn tại và thuộc naming context được hỗ trợ.
- DN đích chưa bị entry khác chiếm.
- RDN mới phù hợp schema và attribute naming.
- Service account có quyền cần thiết trên nguồn, đích và các references.
- Danh sách references và cơ chế server-managed đã được xác định.
- Các writer khác đã được điều phối hoặc có kế hoạch xử lý race.
- Workflow có operation ID và có thể lưu trạng thái trước khi thay đổi directory.

### 4.2. Postconditions

Sau khi workflow báo hoàn tất, cần xác minh:

1. DN đích tồn tại.
2. Stable ID ở DN đích giống stable ID đã xác nhận ở nguồn.
3. DN nguồn không còn chứa đối tượng đó, trừ trường hợp có alias/entry khác được cho phép.
4. RDN và các naming attributes có giá trị đúng.
5. References được server hoặc workflow cập nhật theo chính sách.
6. Không còn reference cũ trong phạm vi được quản lý.
7. Descendants có DN đúng nếu di chuyển subtree.
8. Database, cache, index và hệ thống tích hợp đã được cập nhật hoặc có trạng thái đồng bộ được xác định.
9. Audit ghi lại người yêu cầu, operation ID, DN cũ/mới và kết quả xác minh.
10. Các replica liên quan đã đạt mức hội tụ theo SLA của hệ thống.

Một lần Lookup thành công tại DN mới **chưa đủ** để đáp ứng toàn bộ postconditions.

## 5. Thiết kế preflight: kiểm tra trước khi thay đổi

### 5.1. Xác định đối tượng bằng stable ID

DN có thể thay đổi. Nếu directory cung cấp `entryUUID` hoặc `objectGUID`, hãy dùng giá trị đó để xác nhận đối tượng trước và sau move.

| Giá trị | Vai trò | Lưu ý |
| --- | --- | --- |
| DN | Vị trí entry hiện tại | Thay đổi được |
| `uid` | Attribute định danh nghiệp vụ phổ biến | Có thể không duy nhất toàn directory và có thể đổi |
| `entryUUID` | Operational identifier trong các LDAP server hỗ trợ | Không phổ quát; kiểm tra quyền và schema |
| `objectGUID` | Identifier nhị phân trong Active Directory | Cần xử lý đúng binary representation |
| Employee ID | Định danh nghiệp vụ | Chỉ ổn định nếu tổ chức đảm bảo uniqueness và không tái sử dụng |

Ví dụ đọc stable ID bằng `LdapTemplate`:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.LdapTemplate;

public String readEntryUuid(
        LdapTemplate ldapTemplate,
        Name relativeDn) {

    return ldapTemplate.lookup(
        relativeDn,
        new String[] {"entryUUID"},
        attrs -> {
            Attribute value = attrs.get("entryUUID");
            return value == null ? null : String.valueOf(value.get());
        }
    );
}
~~~

Đoạn code minh họa cho server có `entryUUID`. Với Active Directory, cần adapter đọc `objectGUID` dưới dạng binary và chuyển đổi đúng quy ước. Không dùng chung converter chuỗi cho mọi directory.

Nếu không có stable ID, phải xác định một khóa nghiệp vụ có uniqueness rõ ràng hoặc yêu cầu bước xác minh thủ công. Không tự coi DN là định danh bất biến.

### 5.2. Tính DN nguồn và DN đích an toàn

Giả sử `ContextSource.base=dc=example,dc=org`, Spring LDAP thường dùng DN tương đối:

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

Dùng `LdapNameBuilder` để xử lý thành phần DN có ký tự đặc biệt. Không tự ghép chuỗi hoặc `split(",")`. Escape DN theo RFC 4514 khác với escape giá trị trong LDAP filter theo RFC 4515.

DN đầy đủ mà entry nhóm lưu trong `member` có thể là:

~~~text
uid=alice,ou=people,dc=example,dc=org
~~~

Trong khi API `LdapTemplate` hoạt động với DN tương đối theo base có thể nhận:

~~~text
uid=alice,ou=people
~~~

Cần quy ước rõ loại DN trong command, log và database; tránh nối suffix hai lần.

### 5.3. Xác minh nguồn và đích

Preflight cần thực hiện các bước đọc:

- Lookup DN nguồn và đọc stable ID.
- Xác nhận stable ID bằng đúng đối tượng được yêu cầu di chuyển.
- Lookup DN đích để kiểm tra collision.
- Lookup parent đích để xác nhận tồn tại và đúng naming context.
- Đọc các attribute liên quan tới RDN.
- Xác định objectClass và các MUST attributes theo schema.
- Kiểm tra references và phạm vi tìm kiếm được phép.

Kiểm tra DN đích chưa tồn tại chỉ là **preflight**, không phải khóa chống race. Một client khác có thể tạo entry tại DN đó sau khi kiểm tra. Server vẫn là nơi quyết định kết quả cuối cùng của ModifyDN; phải xử lý lỗi entry đã tồn tại.

### 5.4. Kiểm tra quyền và phạm vi

Tài khoản thực hiện move cần những quyền tương ứng, có thể gồm:

- Quyền ModifyDN trên entry nguồn.
- Quyền tạo child hoặc quyền phù hợp trên parent đích.
- Quyền đọc stable ID và references cần kiểm tra.
- Quyền Modify trên các group entries nếu ứng dụng tự cập nhật reference.
- Quyền đọc/ghi phù hợp trên các hệ thống ngoài LDAP.

Không cấp quyền admin toàn directory chỉ để workflow chạy được. Nếu một phần references không đọc được do ACL, workflow không thể kết luận đã kiểm kê đầy đủ.

## 6. Điều phối thay đổi đồng thời

Một preflight đúng có thể trở nên lỗi thời nếu một hệ thống khác thay đổi entry hoặc group membership trong lúc di chuyển.

Ví dụ:

~~~text
10:00:00  Workflow tìm references của Alice
10:00:05  Một ứng dụng khác thêm Alice vào nhóm on-call bằng DN cũ
10:00:10  Workflow rename Alice
10:00:15  Workflow cập nhật những references đã tìm ở 10:00:00
~~~

Nhóm `on-call` có thể vẫn giữ DN cũ vì nó chưa nằm trong inventory ban đầu.

### 6.1. Khóa theo stable ID

Nếu mọi thay đổi đi qua cùng application service, có thể dùng lock theo stable ID:

~~~text
lock key = directoryId + stableEntryId
~~~

Lock phải có lease/timeout và được lưu ở hệ thống phù hợp nếu ứng dụng chạy nhiều instance. Khóa này chỉ điều phối **những writer tuân theo cơ chế khóa**; nó không ngăn LDAP administrator hoặc ứng dụng khác sửa directory trực tiếp.

### 6.2. Maintenance window hoặc write freeze

Với một đối tượng quan trọng hoặc subtree lớn, có thể cần:

- Tạm dừng các job đồng bộ và writer liên quan.
- Chặn thay đổi membership trong khoảng di chuyển.
- Thông báo hệ thống tích hợp về maintenance window.
- Chỉ mở lại ghi sau khi references và cache được xác minh.

Không nên giữ một transaction SQL mở trong toàn bộ thời gian LDAP move. Dùng workflow bền vững với trạng thái và lease, thay vì giữ tài nguyên transaction lâu.

### 6.3. Chụp inventory và kiểm tra lại sau move

Ngay cả khi đã khóa các writer nội bộ, external writer có thể không tuân theo. Vì vậy sau rename phải Search lại DN cũ trên các attributes và naming contexts đã kiểm kê. Reconciliation sau move là một phần của workflow, không phải một thao tác tùy chọn để dọn dẹp khi rảnh.

## 7. Workflow có trạng thái bền vững

Không nên viết một hàm dài gồm nhiều lệnh LDAP rồi chỉ lưu `success=true` ở cuối. Nếu tiến trình dừng giữa chừng, hệ thống cần biết đã thực hiện tới đâu.

### 7.1. Mô hình trạng thái

Một workflow có thể dùng các trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `REQUESTED` | Đã nhận yêu cầu và có operation ID |
| `VALIDATED` | Preconditions đã được xác minh |
| `QUIESCED` | Các writer liên quan đã được điều phối |
| `RENAMED` | Entry đã được xác minh ở DN mới |
| `REFERENCES_RECONCILED` | Các DN references được quản lý đã được cập nhật/đối soát |
| `EXTERNALS_UPDATED` | Database, cache và hệ thống tích hợp đã được cập nhật |
| `VERIFIED` | Tất cả postconditions đã đạt |
| `COMPLETED` | Workflow hoàn tất và ghi audit |
| `RETRYABLE_FAILURE` | Lỗi có thể tiếp tục sau khi điều kiện phục hồi |
| `NEEDS_MANUAL_REPAIR` | Trạng thái không thể phân giải tự động một cách an toàn |
| `CANCELLED` | Đã hủy trước khi có thay đổi không thể đảo ngược |

Không nhất thiết dùng đúng các tên này, nhưng mỗi trạng thái phải có **điều kiện vào, hành động và điều kiện chuyển tiếp** rõ ràng.

### 7.2. Sơ đồ workflow

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> VALIDATED: Preflight PASS
    VALIDATED --> QUIESCED: Điều phối writer
    QUIESCED --> RENAMED: ModifyDN và xác minh
    RENAMED --> REFERENCES_RECONCILED: Sửa/kiểm tra references
    REFERENCES_RECONCILED --> EXTERNALS_UPDATED: Cập nhật bản sao
    EXTERNALS_UPDATED --> VERIFIED: Kiểm tra postconditions
    VERIFIED --> COMPLETED: Audit + release lock
    REQUESTED --> CANCELLED: Hủy trước khi thay đổi
    VALIDATED --> RETRYABLE_FAILURE: Lỗi tạm thời
    QUIESCED --> RETRYABLE_FAILURE: Lỗi trước ModifyDN
    RENAMED --> RETRYABLE_FAILURE: Lỗi cập nhật references
    REFERENCES_RECONCILED --> NEEDS_MANUAL_REPAIR: Conflict không rõ
    RETRYABLE_FAILURE --> VALIDATED: Retry từ trạng thái đã đọc lại
    NEEDS_MANUAL_REPAIR --> REFERENCES_RECONCILED: Đã sửa thủ công và xác minh
~~~

Các trạng thái phải được lưu bền vững. Khi ứng dụng restart, worker có thể đọc operation đang dở và **đối chiếu với trạng thái directory hiện tại** trước khi chạy tiếp.

### 7.3. Ghi operation record

Một bản ghi điều phối có thể gồm:

| Trường | Mục đích |
| --- | --- |
| `operationId` | Định danh duy nhất cho yêu cầu di chuyển |
| `directoryId` | Directory/partition nguồn |
| `stableId` | Định danh đối tượng |
| `oldDn` | DN trước di chuyển |
| `newDn` | DN đích |
| `moveType` | RENAME, MOVE hoặc SUBTREE_MOVE |
| `status` | Trạng thái workflow |
| `referencePlan` | Danh sách loại reference và chiến lược duy trì |
| `completedSteps` | Các bước đã được xác minh |
| `attemptCount` | Số lần thử theo từng bước |
| `lastErrorCode` | Mã lỗi đã chuẩn hóa, không chứa secret |
| `createdAt`, `updatedAt` | Metadata vận hành |
| `requestedBy` | Danh tính người yêu cầu theo audit policy |

Không lưu mật khẩu LDAP, bind credential hay toàn bộ entry nhạy cảm trong operation record. Có thể lưu danh sách reference tối thiểu hoặc truy vấn lại khi resume, tùy yêu cầu audit và chính sách bảo vệ dữ liệu.

### 7.4. Java model cho yêu cầu di chuyển

~~~java
import java.time.Instant;
import java.util.UUID;

public record MoveCommand(
    UUID operationId,
    String directoryId,
    String stableId,
    String oldDn,
    String newDn,
    MoveType moveType,
    Instant requestedAt
) {}

public enum MoveType {
    RENAME,
    MOVE,
    SUBTREE_MOVE
}

public enum MoveStatus {
    REQUESTED,
    VALIDATED,
    QUIESCED,
    RENAMED,
    REFERENCES_RECONCILED,
    EXTERNALS_UPDATED,
    VERIFIED,
    COMPLETED,
    RETRYABLE_FAILURE,
    NEEDS_MANUAL_REPAIR,
    CANCELLED
}
~~~

Đây là model minh họa. Trong hệ thống thực, `oldDn` và `newDn` nên được parse thành `LdapName` khi sử dụng, kiểm tra theo quy tắc directory và lưu representation có thể khôi phục. Không dùng một `UUID` do ứng dụng sinh ra thay cho stable ID của entry; `operationId` và `stableId` có hai mục đích khác nhau.

## 8. Thực hiện ModifyDN bằng Spring LDAP

### 8.1. API rename

`LdapTemplate` có thể thực hiện rename bằng:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;

public final class EntryMover {

    private final LdapTemplate ldapTemplate;

    public EntryMover(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void move(Name oldDn, Name newDn) {
        ldapTemplate.rename(oldDn, newDn);
    }
}
~~~

Các DN được truyền theo quy ước của `ContextSource` (thường là relative DN nếu base đã được cấu hình). Server thực hiện thao tác ModifyDN và kiểm tra:

- Entry nguồn có tồn tại không.
- Parent mới có tồn tại và được phép không.
- DN đích có collision không.
- Schema và naming rules có được đáp ứng không.
- Quyền ModifyDN và các hạn chế naming context/subtree.

`LdapTemplate.rename` không tự tìm và cập nhật mọi group reference trong ứng dụng. Nó cũng không cập nhật database, cache hoặc token.

### 8.2. Tách việc tính DN khỏi việc thực thi

Không để controller tự nhận raw `oldDn` và `newDn` tùy ý. Application service nên:

1. Nhận stable ID và thông tin đích theo nghiệp vụ (ví dụ `targetOu`).
2. Resolve DN hiện tại từ directory.
3. Tính DN mới bằng `LdapNameBuilder`.
4. Kiểm tra old/new DN thuộc phạm vi được phép.
5. Tạo operation record.
6. Chỉ gọi `rename` sau khi preflight và điều phối hoàn tất.

Cách này giảm nguy cơ caller di chuyển một entry bất kỳ hoặc đưa DN chứa naming context không được quản lý.

### 8.3. Kiểm tra sau khi rename

Sau ModifyDN, đọc lại DN mới và stable ID:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.LdapTemplate;

public String readStableId(
        LdapTemplate ldapTemplate,
        Name dn,
        String idAttribute) {

    return ldapTemplate.lookup(
        dn,
        new String[] {idAttribute},
        attrs -> {
            Attribute id = attrs.get(idAttribute);
            return id == null ? null : String.valueOf(id.get());
        }
    );
}
~~~

So sánh stable ID ở DN mới với giá trị đã ghi trong operation record. Không chỉ so `uid` nếu UID có thể thay đổi hoặc tái sử dụng.

Đọc DN cũ để xác nhận entry không còn ở vị trí cũ. Nếu DN cũ lại có một entry khác, không xóa entry đó vì giả định nó là bản sao; phải xác minh stable ID và xử lý conflict.

## 9. Cập nhật DN references theo kế hoạch

### 9.1. Nếu directory tự duy trì liên kết

Nếu server có referential integrity đã được cấu hình và kiểm thử cho attribute cụ thể:

1. Thực hiện ModifyDN.
2. Đọc lại group/reference entries.
3. Xác minh các giá trị đã trỏ sang DN mới.
4. Không gửi một vòng remove/add thủ công lần nữa nếu server đã cập nhật.
5. Nếu một attribute không được cơ chế server quản lý, đưa nó vào application-managed reference plan riêng.

Ví dụ, OpenLDAP `slapo-refint` cần cấu hình attribute và có giới hạn theo syntax. Active Directory linked attributes chỉ áp dụng với những attribute có link metadata. Không suy rộng cơ chế từ một attribute sang custom attribute khác.

### 9.2. Nếu ứng dụng phải thay giá trị `member`

Với `groupOfNames` và attribute `member` có cú pháp DN, có thể thay một giá trị bằng một LDAP Modify gồm REMOVE và ADD trên cùng entry nhóm:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;

public void replaceMemberDn(
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

    ldapTemplate.modifyAttributes(groupDn, changes);
}
~~~

Đoạn này chỉ minh họa attribute `member` chứa DN đầy đủ. Nó không áp dụng trực tiếp cho `uniqueMember` nếu giá trị có optional UID component. Với `uniqueMember`, phải parse và bảo toàn cả phần đó theo schema.

Hai ModificationItem trên được gửi trong **một Modify request cho một group entry**; nó không làm cho nhiều group entries trở thành một transaction. Nếu giá trị cũ đã biến mất, đọc lại trạng thái trước khi quyết định bước tiếp theo. Nếu nhóm có yêu cầu tối thiểu một member, bảo đảm trạng thái cuối vẫn hợp lệ theo schema.

### 9.3. Cập nhật thuộc tính đơn trị như `manager`

Với thuộc tính đơn trị, có thể dùng `REPLACE_ATTRIBUTE` sau khi xác minh syntax và chính sách:

~~~java
ModificationItem[] changes = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("manager", newFullManagerDn)
    )
};

ldapTemplate.modifyAttributes(entryDn, changes);
~~~

Không thay thế mọi chuỗi xuất hiện của DN cũ trong mọi attribute. Một attribute có thể là text thuần, DN-valued, NameAndOptionalUID hoặc một cấu trúc vendor-specific. Chỉ cập nhật các attribute đã được xác minh.

### 9.4. Nhiều references là nhiều bước

Ví dụ Alice thuộc 30 nhóm và được tham chiếu bởi 4 entry quản lý. Mỗi group/entry là một LDAP entry riêng; workflow cần lưu kết quả từng lần Modify.

~~~text
reference 1: reviewers      -> VERIFIED
reference 2: developers     -> VERIFIED
reference 3: on-call        -> PENDING
reference 4: approval-flow  -> PENDING
...
~~~

Nếu request cập nhật reference thứ 3 thất bại, không rollback tất cả bằng một lệnh tổng quát. Đọc lại từng entry, xác định giá trị hiện tại và chỉ thực hiện phần còn thiếu.

## 10. Cập nhật database, cache và hệ thống tích hợp

LDAP và database ứng dụng là hai hệ thống lưu trữ độc lập. `@Transactional` của Spring cho database không tự bao trùm ModifyDN trên LDAP.

Một workflow điển hình:

~~~mermaid
sequenceDiagram
    participant API as Move service
    participant DB as Workflow DB / Outbox
    participant LDAP as LDAP directory
    participant Cache as Cache / Search index
    API->>DB: Lưu operation REQUESTED
    API->>LDAP: Preflight + đọc stable ID
    API->>DB: Lưu VALIDATED
    API->>LDAP: ModifyDN
    LDAP-->>API: Kết quả ModifyDN
    API->>LDAP: Xác minh DN mới và references
    API->>DB: Cập nhật currentDn + workflow state
    API->>Cache: Invalidate/update stable ID
    API->>DB: Đánh dấu COMPLETED
~~~

### 10.1. Outbox hoặc workflow record

Trước khi gọi LDAP, lưu operation intent vào database nội bộ. Khi LDAP move thành công, cập nhật trạng thái operation và tạo outbox event để các consumer khác cập nhật cache/index.

Nếu process dừng sau khi LDAP đã move nhưng trước khi database commit, lần chạy sau phải:

1. Đọc operation còn dở.
2. Resolve stable ID tại DN cũ và DN mới.
3. Xác định directory đã move hay chưa.
4. Tiếp tục cập nhật database/outbox nếu DN mới đã chứa đúng đối tượng.
5. Không chạy ModifyDN lần nữa chỉ vì trạng thái DB chưa được cập nhật.

Đây là một dạng **saga/workflow có khả năng phục hồi**, không phải distributed transaction.

### 10.2. Cache và token

Nếu cache key là DN, cần invalidation key cũ và tạo mapping DN mới. Tốt hơn, nếu có stable ID, dùng stable ID làm cache key và lưu DN hiện tại như một giá trị có thể cập nhật.

Các token/session đã chứa DN cũ cần có chính sách rõ:

- Token ngắn hạn tự hết hạn?
- Có introspection hoặc resolve stable ID sang DN hiện tại?
- Có cần revoke session khi move?
- Ứng dụng có dùng DN như authorization claim không?

Không để một DN cũ trong JWT hoặc cache dài hạn trở thành nguồn cấp quyền sau khi directory đã thay đổi.

## 11. Phương án phục hồi: tiếp tục tiến hay bù trừ?

### 11.1. Ưu tiên roll forward khi trạng thái đã đổi

Nếu ModifyDN đã thành công nhưng một bước cập nhật reference thất bại, phương án thường dễ kiểm soát hơn là **tiếp tục hoàn tất move**:

- Xác minh entry ở DN mới bằng stable ID.
- Tìm các reference còn giữ DN cũ.
- Tiếp tục cập nhật các reference thiếu.
- Cập nhật DB/cache và xác minh hậu điều kiện.
- Ghi audit sau khi toàn bộ workflow hoàn tất.

Roll forward tránh phải đổi DN qua lại, nhưng chỉ phù hợp khi DN mới vẫn là trạng thái nghiệp vụ được chấp nhận và có thể sửa các phần còn thiếu.

### 11.2. Khi nào cần compensation/rollback?

Compensation có thể cần khi:

- DN đích không còn phù hợp với yêu cầu nghiệp vụ.
- Một chính sách kiểm tra sau move phát hiện điều kiện không thể khắc phục tại DN mới.
- Một hệ thống downstream không thể tiếp tục với trạng thái đã thay đổi.
- Có yêu cầu vận hành rõ ràng buộc phải trở về vị trí cũ.

Trước khi rollback, phải xác minh:

1. Entry ở DN mới vẫn là stable ID ban đầu.
2. DN cũ chưa bị entry khác chiếm.
3. Không có thay đổi nghiệp vụ mới phát sinh tại DN mới mà rollback sẽ làm mất.
4. Các references đã cập nhật có thể được chuyển lại an toàn.
5. Server-managed referential integrity có hỗ trợ thao tác ngược như mong đợi.
6. Các consumer/cache/database có thể xử lý compensation.
7. Writer liên quan có thể được điều phối trong suốt quá trình.

Không rollback chỉ vì một lần gọi LDAP trả exception. Exception có thể xảy ra sau khi server đã hoàn tất thao tác.

### 11.3. Compensation không phải transaction rollback

Một compensation là **một thao tác mới** nhằm đưa hệ thống gần về trạng thái trước đó. Nó có thể thất bại và cần được theo dõi như workflow riêng.

~~~text
Move đã thực hiện:
  old DN -> new DN
  references old -> new

Compensation được yêu cầu:
  new DN -> old DN
  references new -> old
  cache/database -> old mapping
~~~

Không có một thứ tự duy nhất phù hợp cho mọi directory khi phải đảo ngược rename và nhiều reference. Trong lúc chuyển đổi, có thể tồn tại khoảng thời gian một số entry trỏ tới DN cũ và entry khác trỏ tới DN mới. Phải điều phối writer, xác định thứ tự giảm rủi ro, lưu trạng thái từng bước và xác minh sau mỗi bước.

Nếu server tự quản lý references, kiểm tra hành vi khi rename ngược trước khi ứng dụng tự sửa chúng. Không chạy compensation thủ công trên những attribute mà server đã cập nhật tự động.

## 12. Xử lý lỗi theo thời điểm xảy ra

| Thời điểm lỗi | Trạng thái có thể xảy ra | Hành động an toàn |
| --- | --- | --- |
| Preflight | Chưa có thay đổi LDAP | Sửa điều kiện hoặc hủy workflow |
| Sau khi lưu intent, trước ModifyDN | Operation tồn tại, directory chưa đổi | Có thể tiếp tục sau khi kiểm tra lại preconditions |
| ModifyDN trả collision | DN đích đã có entry khác | Dừng, xác minh stable ID; không ghi đè |
| Mất kết nối khi ModifyDN | Kết quả commit không xác định | Đọc old/new DN bằng stable ID trên node có thẩm quyền |
| Rename thành công, reference update lỗi | Entry đã ở DN mới, quan hệ chưa hoàn tất | Ưu tiên roll forward hoặc repair theo trạng thái |
| DB update lỗi sau LDAP | LDAP đã đổi, bản sao nội bộ có thể cũ | Resume workflow, cập nhật DB/outbox theo stable ID |
| Cache invalidation lỗi | Directory và DB có thể đúng, cache cũ | Retry invalidation và giới hạn TTL/fail-safe |
| Replica chưa hội tụ | Node khác có thể trả DN cũ | Theo dõi replication, chưa công bố hoàn tất toàn topology |
| Compensation lỗi | Hệ thống ở trạng thái một phần | Giữ trạng thái manual repair, không đánh dấu rollback thành công |

### 12.1. CommunicationException trong ModifyDN

Một trường hợp đặc biệt:

~~~text
Client gửi ModifyDN
        |
        v
LDAP server thực hiện rename thành công
        |
        v
Response bị mất trên mạng
        |
        v
Client nhận CommunicationException
~~~

Client không biết request chưa tới server hay response bị mất sau khi server xử lý. Không gửi lại ModifyDN mù quáng.

Cách phân giải:

1. Dùng một kết nối khỏe tới directory node có thẩm quyền hoặc endpoint được chỉ định.
2. Lookup DN cũ và DN mới.
3. Đọc stable ID ở nơi tìm thấy entry.
4. Quyết định theo ma trận:

| DN cũ | DN mới | Stable ID | Kết luận và hành động |
| --- | --- | --- | --- |
| Có | Không | Ở DN cũ đúng ID | Rename chưa được quan sát; kiểm tra lỗi và có thể thử lại có điều kiện |
| Không | Có | Ở DN mới đúng ID | Rename đã xảy ra; tiếp tục workflow |
| Có | Có | Một hoặc hai ID khác nhau | Collision/conflict; dừng tự động và điều tra |
| Không | Không | Không tìm thấy | Có thể sai endpoint, ACL, replica hoặc entry đã bị xóa; cần manual repair |
| Không rõ | Không rõ | Không đọc được | Giữ trạng thái chưa xác định; không retry mù |

Nếu đọc từ replica trễ, DN cũ có thể vẫn xuất hiện sau khi writer đã xử lý rename. Phải xác định node/consistency model và chờ replication theo chính sách, không kết luận chỉ từ một lần read.

## 13. Xử lý subtree và di chuyển giữa các directory

### 13.1. Subtree move

Khi move một OU cha, DN của các descendants thay đổi theo đường dẫn mới. Workflow cần:

- Đếm và nhận diện các entry con theo stable ID nếu có.
- Xác minh server hỗ trợ ModifyDN cho non-leaf entry.
- Xác định references trỏ tới mọi descendant.
- Kiểm tra giới hạn thời gian và tải.
- Xác minh kết quả ở cả parent mới và các DN con.
- Cập nhật bản sao và cache của toàn subtree.

Không chỉ xác minh DN OU gốc rồi kết luận tất cả entry con đã được chuyển chính xác. Với directory có giới hạn hoặc semantics riêng, phải test trên phiên bản/server thực tế.

### 13.2. Chuyển giữa naming context hoặc server

Nếu nguồn và đích không thuộc cùng vùng directory có thể thực hiện ModifyDN, hãy thiết kế migration như hai phía:

1. Đọc entry nguồn và descendants theo schema.
2. Chuyển đổi DN và DN-valued references sang naming context đích.
3. Tạo parent và entry ở đích theo đúng thứ tự.
4. Xác minh stable ID/mapping nghiệp vụ, attributes, binary values và group membership.
5. Chuyển traffic hoặc consumer sang đích theo kế hoạch.
6. Đối soát dữ liệu trong cửa sổ chuyển đổi.
7. Chỉ xử lý entry nguồn sau khi đích đã được xác nhận và có phê duyệt.

Một lần export/import có thể không bảo toàn các operational attributes như `entryUUID`, `createTimestamp`, `modifyTimestamp`, password policy hoặc vendor-specific metadata. Phải xác định rõ giá trị nào được giữ, giá trị nào do server đích sinh mới và cách liên kết stable ID giữa hai directory.

## 14. Kiểm thử workflow trên directory thật

Mock `LdapTemplate.rename` chỉ kiểm tra lời gọi method. Nó không chứng minh server thực sự xử lý ModifyDN, cập nhật references hoặc áp dụng schema như production. Cần integration test với đúng loại directory và cấu hình referential integrity tương ứng.

### 14.1. Bộ dữ liệu kiểm thử

Fixture tối thiểu cần có:

- Root naming context.
- OU nguồn và OU đích.
- Một user có stable identifier.
- Một hoặc nhiều nhóm tham chiếu user.
- Một entry khác có `manager` trỏ tới user.
- Các references đa trị và đơn trị.
- Một DN đích đã tồn tại để kiểm tra collision.
- Một test case cho nested group hoặc subtree nếu nghiệp vụ hỗ trợ.

Không nạp trùng root entry nếu container đã bootstrap naming context. Mỗi test ghi/xóa nên dùng DN riêng và cleanup an toàn.

### 14.2. Ma trận kiểm thử

| Kịch bản | Thao tác | Kết quả cần xác minh |
| --- | --- | --- |
| Move thành công | Chuyển Alice sang OU đích | DN mới có cùng stable ID |
| Target collision | Tạo entry tại DN đích trước | Workflow dừng, không ghi đè |
| Parent không tồn tại | Chỉ định OU đích sai | Preflight thất bại trước ModifyDN |
| Thiếu quyền ModifyDN | Bind account read-only | Directory từ chối, workflow không báo hoàn tất |
| Reference server-managed | Rename với overlay/link phù hợp | Reference được cập nhật theo cơ chế server |
| Reference app-managed | Rename trên server không auto-update | Workflow cập nhật và xác minh references |
| `uniqueMember` | Có optional UID component | Giá trị được bảo toàn hoặc xử lý theo schema |
| Group cuối cùng | Xóa/thay member cuối | Không vi phạm MUST attribute |
| Partial failure | Lỗi ở group thứ ba | Resume chỉ các bước chưa hoàn tất |
| Mất response ModifyDN | Ngắt mạng đúng thời điểm | Phân giải trạng thái bằng stable ID |
| Concurrent writer | Thêm membership trong lúc move | Lock/freeze hoặc reconciliation phát hiện |
| Subtree move | Chuyển OU có descendants | DN các entry con được xác minh |
| Cross-context | Chuyển partition/server | Dùng migration workflow, không giả định ModifyDN nguyên tử |
| Replica lag | Đọc ngay sau write từ replica | Chờ hội tụ theo policy, không rollback nhầm |
| Cache/DB failure | LDAP thành công, DB lỗi | Workflow resume và cập nhật bản sao |
| Compensation | Thử đưa entry về DN cũ | Chỉ thực hiện khi preconditions được xác minh |

### 14.3. Test trạng thái trước và sau thao tác

Một test tích hợp nên xác minh tối thiểu:

1. Stable ID tại DN cũ trước move.
2. DN đích chưa có entry.
3. References trước move có DN cũ.
4. Gọi `LdapTemplate.rename`.
5. Stable ID tại DN mới vẫn giống giá trị ban đầu.
6. DN cũ không còn chứa cùng đối tượng.
7. References được server hoặc workflow cập nhật theo policy.
8. Repository tìm thấy entry theo DN mới.
9. Bản sao DB/cache được cập nhật theo stable ID.
10. Operation record chuyển `COMPLETED` chỉ khi mọi postconditions đạt.

### 14.4. Fault injection

Để kiểm tra phục hồi, có thể dùng proxy mạng trong test hoặc một adapter giả lập lỗi ở từng điểm:

~~~text
Test A:
  Preflight -> PASS
  ModifyDN -> lỗi trước khi gửi request
  Resume -> xác minh old DN, thử lại

Test B:
  Preflight -> PASS
  ModifyDN -> server commit, response bị mất
  Resume -> đọc new DN + stable ID, tiếp tục references

Test C:
  ModifyDN -> PASS
  Reference 1 -> PASS
  Reference 2 -> lỗi
  Resume -> chỉ repair reference 2 và các reference còn thiếu

Test D:
  LDAP -> PASS
  Database commit -> lỗi
  Resume -> cập nhật DB/outbox theo stable ID
~~~

Test không được chạy trên directory production. Fault injection phải kiểm soát được endpoint và dữ liệu để tránh tác động đến hệ thống dùng chung.

## 15. Bảo mật, audit và vận hành

- Chỉ cấp quyền ModifyDN trên các OU/entry được phép.
- Chỉ cấp quyền Modify trên những attributes dùng để duy trì references.
- Dùng LDAPS hoặc StartTLS với CA và hostname được xác minh.
- Không nhận arbitrary DN hoặc LDAP filter từ caller mà không kiểm tra phạm vi.
- Dùng `LdapNameBuilder` để dựng DN và filter builder để encode assertion values.
- Ghi audit operation ID, stable ID, DN cũ/mới, actor, thời điểm và trạng thái từng bước.
- Không ghi password, token, toàn bộ entry hoặc dữ liệu cá nhân không cần thiết vào log.
- Có metric cho số workflow đang chạy, thời gian ở từng trạng thái, số lần retry, partial failure, dangling reference và reconciliation.
- Cảnh báo workflow ở `NEEDS_MANUAL_REPAIR` hoặc quá hạn.
- Không giải phóng write freeze trước khi đã xác minh references và consumer cần thiết.
- Với authorization, áp dụng cache TTL và chính sách fail-safe trong thời gian directory/replica chưa hội tụ.

Một workflow hoàn tất kỹ thuật nhưng chưa được kiểm tra trên topology production vẫn cần theo dõi sau triển khai. Kết quả từ embedded LDAP không chứng minh hành vi linked attributes hoặc referential integrity của mọi vendor.

## 16. Checklist vận hành cho một yêu cầu di chuyển

Trước khi chạy:

- [ ] Xác nhận người yêu cầu và mục đích nghiệp vụ.
- [ ] Resolve stable ID và DN hiện tại.
- [ ] Xác định loại move: RDN, parent, subtree hay cross-directory.
- [ ] Kiểm tra DN đích, parent, schema và quyền.
- [ ] Kiểm kê references và xác định server-managed/application-managed.
- [ ] Lưu operation ID và intent bền vững.
- [ ] Điều phối writer và maintenance window nếu cần.

Trong khi chạy:

- [ ] Ghi trạng thái sau từng bước đã xác minh.
- [ ] Thực hiện ModifyDN một lần theo operation state.
- [ ] Sau lỗi giao tiếp, đọc lại old/new DN bằng stable ID.
- [ ] Cập nhật references theo đúng strategy.
- [ ] Cập nhật DB/cache/index bằng outbox hoặc workflow.
- [ ] Giới hạn retry và giữ trạng thái partial khi chưa chắc chắn.

Sau khi chạy:

- [ ] Xác minh DN mới chứa đúng stable ID.
- [ ] Xác minh DN cũ không còn chứa cùng entry.
- [ ] Xác minh group/manager/custom references.
- [ ] Xác minh descendants nếu là subtree move.
- [ ] Xác minh database, cache và consumer.
- [ ] Đối chiếu replication theo topology.
- [ ] Ghi audit và chỉ đánh dấu `COMPLETED` khi postconditions đạt.
- [ ] Giải phóng lock/write freeze.

## 17. Câu hỏi tự kiểm tra

1. Đổi RDN khác chuyển parent như thế nào?
2. Vì sao ModifyDN không đồng nghĩa với cập nhật mọi group references?
3. Những điều kiện nào phải được kiểm tra trước khi move một entry?
4. Vì sao DN không phải stable identifier? Khi nào dùng `entryUUID` hoặc `objectGUID`?
5. `ContextSource.base` ảnh hưởng thế nào tới DN truyền vào `LdapTemplate.rename`?
6. Tại sao kiểm tra DN đích chưa tồn tại không loại bỏ được race condition?
7. Khi nào directory server tự duy trì references? Vì sao phải kiểm tra từng attribute?
8. Vì sao `uniqueMember` cần được xử lý khác `member`?
9. Tại sao một workflow cần lưu trạng thái sau mỗi bước thay vì một cờ `success` cuối cùng?
10. Nếu ModifyDN mất response do `CommunicationException`, làm sao biết server đã commit?
11. Vì sao nên ưu tiên roll forward trong nhiều trường hợp rename đã thành công nhưng reference update còn thiếu?
12. Những điều kiện nào phải đúng trước khi thực hiện compensation?
13. Vì sao rollback là một thao tác mới chứ không phải transaction rollback?
14. Làm sao tránh một ứng dụng khác thêm DN cũ vào group trong lúc move?
15. Tại sao `@Transactional` không bảo đảm transaction xuyên LDAP và database?
16. Nếu một workflow move subtree, cần xác minh những descendant nào?
17. Khi nào phải dùng export/import migration thay vì một ModifyDN?
18. Vì sao không nên đánh dấu `COMPLETED` ngay sau khi `LdapTemplate.rename` trả về?
19. Hãy thiết kế test mô phỏng server commit nhưng response ModifyDN bị mất.
20. Khi nào cần chuyển workflow sang `NEEDS_MANUAL_REPAIR` thay vì tiếp tục retry?

## 18. Tổng kết

Một quy trình di chuyển LDAP an toàn phải được thiết kế như **workflow có trạng thái**, không chỉ là một lời gọi `rename`. Bắt đầu bằng việc xác định loại di chuyển, stable ID, DN nguồn/đích, schema, quyền, references và các writer đồng thời. Thực hiện ModifyDN bằng Spring LDAP khi server hỗ trợ, sau đó xác minh entry và duy trì các liên kết theo đúng cơ chế referential integrity của directory.

Nếu thao tác thất bại giữa chừng, hãy đọc lại trạng thái directory và tiếp tục theo operation record. Khi ModifyDN mất response, kết quả có thể chưa xác định; khi một số group references đã được cập nhật, workflow cần biết chính xác bước nào còn thiếu. **Roll forward** thường dễ kiểm soát hơn khi DN mới đã hợp lệ; compensation chỉ nên dùng sau khi xác minh có thể đảo ngược an toàn.

Cuối cùng, LDAP và database/cache không nằm trong một transaction toàn cục mặc định. Dùng operation ID, outbox, idempotency, reconciliation, audit và integration test theo đúng vendor để bảo đảm workflow có thể tiếp tục sau restart, lỗi mạng và cập nhật đồng thời.

### Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol: ModifyDN Operation](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512).
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514).
- [RFC 4515 — LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515).
- [RFC 4519 — LDAP Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519).
- [RFC 4530 — entryUUID LDAP Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530).
- [Spring LDAP Reference — Basic Usage and LdapTemplate](https://docs.spring.io/spring-ldap/reference/basic-usage.html).
- [Spring LDAP Reference — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html).
- [Spring LDAP API — LdapOperations](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html).
- [OpenLDAP Administrator's Guide — Referential Integrity Overlay](https://www.openldap.org/doc/admin26/guide.html).
- [Microsoft Learn — Linked Attributes](https://learn.microsoft.com/en-us/windows/win32/ad/linked-attributes).
