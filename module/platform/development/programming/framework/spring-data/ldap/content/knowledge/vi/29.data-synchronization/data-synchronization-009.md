# Đối soát dữ liệu và xử lý xung đột giữa nhiều nguồn ghi

> **Chương:** Đồng bộ dữ liệu  
> **Module:** SPRING_DATA_LDAP — truy cập dịch vụ thư mục LDAP qua Spring Data LDAP bằng repository và ánh xạ entry phân cấp sang đối tượng Java. Người học hiểu DN, objectClass, schema, truy vấn repository/LdapTemplate, CRUD, filter an toàn, bảo mật kết nối và kiểm thử với directory.

Một hệ thống nhân sự có thể nhận thay đổi hồ sơ từ nhiều nơi: ứng dụng quản trị ghi vào JDBC, bộ phận IT sửa trực tiếp LDAP, hệ thống HR đồng bộ dữ liệu nhân viên, và một job import nhận dữ liệu từ nhà cung cấp bên ngoài. Khi hai nguồn cùng sửa một thuộc tính, hệ thống phải quyết định giá trị nào được giữ, cách phát hiện dữ liệu đã lệch và cách đưa các bản sao về trạng thái nhất quán.

Đây là bài toán **đối soát dữ liệu và giải quyết xung đột**. Việc chạy một job đồng bộ định kỳ hoặc gọi repository.save() không tự giải quyết xung đột. Ứng dụng cần định nghĩa nguồn dữ liệu có thẩm quyền, quyền sở hữu từng trường, identity ổn định, quy tắc merge, version, cách xử lý delete và quy trình audit/retry.

LDAP có các cơ chế hỗ trợ kiểm tra điều kiện khi ghi và thông báo thay đổi, nhưng cần phân biệt chúng với chính sách nghiệp vụ. Assertion Control có thể bảo vệ một thao tác ghi khỏi việc cập nhật trên phiên bản cũ; LDAP Content Synchronization có thể giúp phát hiện entry thay đổi. Không cơ chế nào tự biết rằng dữ liệu HR phải thắng dữ liệu nhập từ hệ thống khác.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt đồng bộ một chiều, đồng bộ hai chiều, replication của directory và reconciliation ở tầng nghiệp vụ.
2. Xác định system of record và quyền sở hữu từng attribute.
3. Dùng business key ổn định thay cho việc xem DN là identity bất biến.
4. Phân loại conflict do ghi đồng thời, dữ liệu cũ, format khác nhau, delete và replication.
5. Chọn chiến lược xử lý: single writer, field ownership, source priority, merge, version hoặc manual review.
6. Giải thích vì sao last-write-wins theo timestamp có thể chọn sai dữ liệu.
7. Dùng revision và LDAP Assertion Control khi server hỗ trợ.
8. Phân biệt RFC 4528 Assertion Control với RFC 4533 Content Synchronization.
9. Thiết kế tombstone, change cursor, checkpoint và incremental reconciliation.
10. Viết luồng Spring LDAP/Spring Data LDAP có idempotency, audit và retry.
11. Kiểm thử race condition, event trùng/lệch thứ tự, DN rename và partial failure.
12. Theo dõi mức độ lệch dữ liệu mà không làm lộ thông tin nhạy cảm.

## 2. Bối cảnh: nhiều nguồn cùng ghi một nhân viên

Giả sử một nhân viên có dữ liệu ở ba hệ thống:

~~~text
             HR application
           (contract, status)
                  |
                  v
          JDBC employee table
                  |
                  | provisioning / sync
                  v
              LDAP DIT
          (uid, cn, mail, groups)
                  ^
                  |
             IT admin tool
           (mail, phone, groups)
~~~

Một ngày có các thay đổi sau:

- HR đổi phòng ban và trạng thái hợp đồng trong JDBC.
- IT cập nhật số điện thoại trực tiếp trong LDAP.
- Một import job ghi email mới từ hệ thống bên ngoài.
- Job đồng bộ cũ chạy trễ và ghi lại email của ngày hôm trước.

Nếu job chỉ copy toàn bộ object từ JDBC sang LDAP, thay đổi số điện thoại do IT vừa thực hiện có thể bị ghi đè. Nếu job copy ngược toàn bộ LDAP sang JDBC, HR có thể mất giá trị phòng ban mới nhất.

Giải pháp bắt đầu từ việc trả lời: **trường nào do hệ thống nào quản lý?**

## 3. Phân biệt bốn khái niệm

| Khái niệm | Phạm vi | Ví dụ |
|---|---|---|
| Data synchronization | Chuyển thay đổi giữa các hệ thống | Cập nhật mail từ HR sang LDAP |
| Reconciliation | So sánh trạng thái thực tế với trạng thái mong muốn và sửa lệch | LDAP thiếu employeeStatus thì tạo lại |
| Directory replication | Đồng bộ thay đổi giữa các LDAP replica/server | OpenLDAP syncrepl, AD replication |
| Conflict resolution | Quyết định kết quả khi nhiều thay đổi không tương thích | HR và IT cùng sửa mail |

Replication của LDAP server có quy tắc riêng về change sequence, metadata và conflict resolution. Nó không thay thế quy tắc nghiệp vụ giữa HR, JDBC, ứng dụng và LDAP. Tương tự, một reconciliation job không nên tự ý thay đổi cơ chế replication nội bộ của directory.

## 4. Chọn system of record và quyền sở hữu theo trường

Không nên tuyên bố một hệ thống là nguồn chân lý cho mọi attribute nếu các bộ phận khác nhau quản lý các phần dữ liệu khác nhau.

Ví dụ một ownership matrix:

| Attribute nghiệp vụ | Nguồn có thẩm quyền | Hướng đồng bộ | Ai được ghi trực tiếp? |
|---|---|---|---|
| employeeId | HR/JDBC | JDBC → LDAP | HR |
| departmentNumber | HR/JDBC | JDBC → LDAP | HR |
| employeeStatus | HR/JDBC | JDBC → LDAP | HR |
| mail | HR hoặc directory admin theo policy | Một hướng được quy định | Chủ sở hữu đã chọn |
| telephoneNumber | IT directory admin | LDAP → JDBC hoặc chỉ LDAP | IT |
| group membership | Identity governance | Theo workflow cấp quyền | Identity service |
| modifyTimestamp | LDAP server | Chỉ đọc để quan sát | Directory server |

Với mỗi field, tài liệu thiết kế phải nêu:

- Owner/source of truth.
- Hệ thống nào được phép ghi.
- Các hệ thống nhận bản sao.
- Quy tắc format/canonicalization.
- Cách phát hiện thay đổi.
- Quy tắc conflict và tie-break.
- Hành vi khi owner unavailable.
- Ai được phép sửa conflict thủ công.

**Single-writer theo attribute** thường là cách đơn giản và dễ kiểm soát nhất. Ví dụ HR là writer duy nhất của employeeStatus, còn IT là writer duy nhất của telephoneNumber. Nếu cần nhiều writer, hãy định nghĩa merge/version rõ ràng trước khi triển khai.

## 5. Identity ổn định: business key khác DN

DN xác định vị trí entry trong Directory Information Tree. DN có thể đổi khi đổi RDN hoặc chuyển entry sang OU khác.

~~~text
uid=lan,ou=people,dc=example,dc=org
                 |
                 | rename / move
                 v
uid=lan,ou=employees,dc=example,dc=org
~~~

Nếu JDBC lưu DN như khóa identity duy nhất, việc rename có thể làm bản ghi JDBC trỏ tới DN cũ. Với đồng bộ nhiều nguồn, nên có business key ổn định như employeeId:

| Trường | Vai trò |
|---|---|
| employeeId | Identity nghiệp vụ ổn định, duy nhất theo domain |
| uid | Login name; có thể đổi theo policy |
| DN | Địa chỉ hiện tại của entry trong DIT |
| entryUUID/objectGUID | Identity kỹ thuật do directory cấp, semantics phụ thuộc server |

Trong LDAP schema, có thể lưu employeeId bằng attribute tùy biến đã được schema cho phép. Không tự giả định attribute này có sẵn trong inetOrgPerson. Với Active Directory, objectGUID là identity kỹ thuật của object; với OpenLDAP, entryUUID có vai trò tương tự trong các cơ chế sync. Hãy xác định rõ nguồn cấp, format và khả năng giữ identity khi export/import.

Khi reconciliation tìm entry, ưu tiên lookup theo business key duy nhất trong search base được kiểm soát. Nếu tìm thấy nhiều entry cho cùng employeeId, đó là conflict identity cần quarantine/manual review, không chọn kết quả đầu tiên.

## 6. Chuẩn hóa dữ liệu trước khi so sánh

Hai giá trị có thể khác chuỗi nhưng tương đương theo quy tắc nghiệp vụ hoặc schema. Ngược lại, hai chuỗi nhìn gần giống nhau có thể khác ý nghĩa.

Ví dụ:

- LAN@example.org và lan@example.org có thể được ứng dụng coi tương đương theo policy email.
- DN có cách biểu diễn thành phần khác nhau nhưng có thể tương đương theo quy tắc so sánh DN.
- Số điện thoại có dấu cách, dấu gạch hoặc mã quốc gia khác nhau.
- Chuỗi rỗng và attribute không tồn tại là hai trạng thái khác nhau.
- Multi-valued attribute có thể trả các giá trị theo thứ tự khác nhau.

Tạo canonicalization riêng cho từng field:

| Field | Quy tắc so sánh gợi ý | Cần tránh |
|---|---|---|
| DN | Parse thành LdapName, so sánh theo semantics DN | So sánh raw string đơn giản |
| employeeId | Trim/format theo hợp đồng mã nhân viên | Tự đổi hoa/thường nếu mã phân biệt |
| mail | Policy domain/application đã xác nhận | Áp dụng case folding tùy tiện lên local-part |
| telephoneNumber | Chuẩn hóa theo kế hoạch đánh số và extension | Xóa mọi ký tự mà không giữ extension |
| group membership | So sánh tập DN đã parse/normalize | So sánh thứ tự List |
| timestamp | Parse về Instant/offset có timezone rõ | So sánh chuỗi format khác nhau |

Canonicalization phải được áp dụng đồng nhất ở nơi ghi, nơi đọc và nơi reconciliation. Không sửa dữ liệu nguồn chỉ để làm phép so sánh dễ hơn nếu chưa có migration.

## 7. Phân loại conflict

| Loại conflict | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Concurrent update | Hai admin cùng đổi mail | Ai có quyền ghi field này? |
| Stale write | Job cũ ghi snapshot trước đó | Revision nào đã được đọc? |
| Source conflict | HR và CRM cung cấp hai số điện thoại | Nguồn nào có thẩm quyền? |
| Format conflict | Một nguồn gửi ACTIVE, nguồn khác active | Canonical value là gì? |
| Identity conflict | Hai entry có cùng employeeId | Có duplicate hoặc DN rename chưa được xử lý? |
| Delete/update conflict | Một nguồn xóa user, nguồn khác cập nhật mail | Delete có ưu tiên hay phải giữ lại? |
| Multi-valued conflict | Hai nguồn thay đổi membership | Merge theo union, remove-wins hay policy khác? |
| Replication conflict | Hai writable replica nhận thay đổi gần đồng thời | Quy tắc server/vendor nào quyết định? |
| Schema conflict | Một nguồn gửi attribute không được phép | Sửa schema, mapping hay reject dữ liệu? |

Không dùng một thuật toán duy nhất cho mọi loại conflict. Ví dụ, union hợp lý cho một tập nhãn không nhất thiết hợp lý cho group membership, vì thêm quyền và thu hồi quyền có tác động bảo mật.

## 8. Các chiến lược giải quyết conflict

| Chiến lược | Cách làm | Phù hợp khi | Rủi ro |
|---|---|---|---|
| Single writer | Một nguồn duy nhất được ghi field | Dữ liệu có owner rõ | Cần chặn writer ngoài policy |
| Field ownership | Mỗi nguồn sở hữu một nhóm attribute | Nhiều hệ thống quản lý các phần khác nhau | Cần schema/contract rõ |
| Source priority | Nguồn ưu tiên cao thắng | Có thứ bậc nghiệp vụ cố định | Nguồn ưu tiên có thể gửi dữ liệu cũ |
| Version-based | Chỉ ghi nếu revision còn đúng | Có version đáng tin và conditional write | Cần hỗ trợ control/lock |
| Merge | Kết hợp các thay đổi theo quy tắc | Tập dữ liệu có semantics merge rõ | Xung đột remove/add cần policy |
| Last-write-wins | Chọn timestamp mới hơn | Có clock và event time tin cậy | Clock skew, precision, replay |
| Manual resolution | Đưa vào hàng đợi xử lý | Quyền nhạy cảm hoặc identity conflict | Tăng thời gian xử lý |

### Ví dụ field ownership

Nếu HR sở hữu employeeStatus, LDAP chỉ là bản chiếu. Khi IT sửa employeeStatus trực tiếp trên LDAP, reconciliation phát hiện khác biệt và ghi lại giá trị HR. Có thể audit lần sửa LDAP là external drift để điều tra, nhưng không biến thay đổi đó thành nguồn chân lý.

Nếu IT sở hữu telephoneNumber, thay đổi LDAP cần được đồng bộ về JDBC. HR không được gửi snapshot toàn bộ employee để ghi đè trường này.

## 9. Vì sao last-write-wins không đơn giản?

Last-write-wins (LWW) chọn giá trị có timestamp lớn nhất. Cách này chỉ đáng tin nếu timestamp phản ánh đúng thứ tự nghiệp vụ và các nguồn có clock/precision đủ tốt.

Ví dụ:

~~~text
09:00:00.900 HR ghi mail A
09:00:01.100 IT ghi mail B
09:00:00.500 Job cũ phát lại mail C
~~~

Nếu timestamp do client gửi, job cũ có thể mang thời gian mới hơn do clock sai hoặc retry sau. Nếu timestamp chỉ chính xác đến giây, hai thay đổi khác nhau có thể có cùng timestamp.

LWW cần định nghĩa:

- Timestamp là thời gian sự kiện xảy ra hay thời gian server nhận dữ liệu?
- Ai cấp timestamp và clock được đồng bộ ra sao?
- Độ chính xác timestamp là gì?
- Hai event cùng timestamp thì tie-break thế nào?
- Event đến trễ có được phép ghi đè không?
- Có phân biệt user edit với batch replay không?

Không dùng LDAP operational attribute modifyTimestamp như một version toàn cục giữa nhiều server. Nó hữu ích cho quan sát thay đổi, nhưng không phải một distributed logical clock hay compare-and-swap token chuẩn.

Nếu cần thứ tự đáng tin, ưu tiên revision/sequence do owner cấp và được kiểm tra nguyên tử ở nơi ghi. Với nhiều writer độc lập, có thể cần version vector hoặc conflict ledger, nhưng độ phức tạp tăng đáng kể.

## 10. Revision và optimistic concurrency

Một cách phát hiện stale write là lưu revision do ứng dụng quản lý, ví dụ attribute tùy biến appRevision:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
objectClass: appPersonAux
uid: lan
cn: Tran Thi Lan
sn: Tran
appRevision: 41
employeeStatus: active
~~~

appRevision là ví dụ custom attribute. Directory test phải khai báo attribute và auxiliary objectClass tương ứng; không mặc định schema chuẩn có field này.

Luồng optimistic concurrency:

1. Client đọc entry và nhận revision 41.
2. Client tính thay đổi.
3. Client gửi Modify có điều kiện revision vẫn bằng 41.
4. Cùng ModifyRequest cập nhật field và đặt revision thành 42.
5. Nếu revision không còn 41, server từ chối toàn bộ operation.
6. Client đọc lại, phân tích conflict và quyết định merge/retry.

Nếu client chỉ đọc revision rồi gửi Modify thông thường, một writer khác vẫn có thể thay đổi entry giữa hai bước. Đó chỉ là check-then-act với race condition, chưa phải optimistic concurrency nguyên tử.

Tất cả writer cần tuân thủ quy ước tăng revision. Nếu một admin hoặc ứng dụng khác thay đổi field nhưng không tăng appRevision, cơ chế sẽ không phát hiện được stale write đó.

## 11. LDAP Assertion Control: conditional update tại server

RFC 4528 định nghĩa LDAP Assertion Control với OID 1.3.6.1.1.12. Client gửi một LDAP filter BER-encoded làm điều kiện. Server chỉ thực hiện update nếu assertion đúng trên entry đích; nếu sai hoặc không xác định, server trả result code assertionFailed (122) và không thực hiện operation.

Ví dụ điều kiện:

~~~text
(appRevision=41)
~~~

Client muốn sửa employeeStatus và revision:

~~~text
Assertion: appRevision phải bằng 41

Modify:
  REPLACE employeeStatus = suspended
  REPLACE appRevision = 42
~~~

Assertion được đánh giá như một phần nguyên tử của update. Điều này giúp thực hiện test-and-set cho một entry mà không có cửa sổ race giữa lần đọc revision và lần ghi.

### Server support và criticality

- Kiểm tra Root DSE attribute supportedControl có OID 1.3.6.1.1.12.
- Nếu control là critical, server không hỗ trợ phải từ chối operation thay vì âm thầm bỏ qua.
- Nếu control không critical và server bỏ qua nó, update có thể chạy mà không có điều kiện. Với optimistic concurrency, đây là hành vi nguy hiểm.
- Assertion chỉ bảo vệ operation trên entry đích; nó không tạo transaction cho nhiều DN.
- Control không thay thế authorization/ACL.

### Dùng LdapTemplate để truy cập LdapContext

Spring LDAP cung cấp LdapTemplate.executeReadWrite(ContextExecutor) để chạy thao tác trên một DirContext do template quản lý. Nếu JNDI provider trả về LdapContext, có thể gắn request control vào context rồi thực hiện Modify trên cùng context:

~~~java
private static final String ASSERTION_OID = "1.3.6.1.1.12";

public void updateStatusIfRevisionMatches(
        Name personDn,
        long expectedRevision,
        EmploymentStatus nextStatus) {

    byte[] assertionFilterBer =
            assertionFilterEncoder.encodeEquals(
                    "appRevision",
                    Long.toString(expectedRevision));

    ModificationItem[] changes = {
        new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute(
                        "employeeStatus",
                        nextStatus.directoryValue())),
        new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute(
                        "appRevision",
                        Long.toString(expectedRevision + 1)))
    };

    ldapTemplate.executeReadWrite(ctx -> {
        if (!(ctx instanceof LdapContext ldapContext)) {
            throw new IllegalStateException(
                    "Provider does not expose LdapContext controls");
        }

        Control[] previousControls = ldapContext.getRequestControls();

        try {
            ldapContext.setRequestControls(new Control[] {
                new BasicControl(
                        ASSERTION_OID,
                        true,
                        assertionFilterBer)
            });

            ldapContext.modifyAttributes(personDn, changes);
            return null;
        } finally {
            ldapContext.setRequestControls(previousControls);
        }
    });
}
~~~

Đây là mẫu tích hợp; assertionFilterEncoder là adapter cần triển khai bằng một LDAP SDK/BER encoder đã được kiểm thử. Control value phải là BER encoding của LDAP Filter theo RFC 4528, **không phải UTF-8 bytes của chuỗi filter**. Không tự đặt byte array bằng filter string rồi cho rằng server hiểu.

BasicControl giữ OID, criticality và BER control value. setRequestControls áp dụng controls cho operation tiếp theo trên context. Mẫu lưu và phục hồi controls cũ trong finally để tránh ảnh hưởng thao tác khác nếu context được tái sử dụng. Nếu provider không cung cấp LdapContext hoặc không hỗ trợ assertion control, fail closed và chuyển sang chiến lược lock/serialization khác.

### Xử lý assertionFailed

Khi server trả assertionFailed (122):

1. Không retry cùng modification với revision cũ.
2. Đọc lại entry và revision.
3. So sánh các field thay đổi từ nguồn nào.
4. Áp dụng ownership/merge policy.
5. Tạo modification mới với revision mới nếu conflict có thể tự giải quyết.
6. Nếu không thể giải quyết, ghi conflict ledger và đưa vào manual review.

Không chuyển assertionFailed thành lỗi tạm thời thông thường. Đây là tín hiệu concurrency conflict có chủ đích.

## 12. Repository và LdapTemplate có vai trò khác nhau trong reconciliation

LdapRepository phù hợp với CRUD và truy vấn entity thông thường. LdapTemplate hữu ích khi cần:

- Chọn chính xác attribute cần đọc.
- Tạo query/filter theo điều kiện.
- Gửi ModificationItem cho một số attribute.
- Dùng callback truy cập JNDI context/control.
- Xử lý operation theo DN và kiểm soát result code.

Không giả định repository.save(entity) tự kiểm tra version hoặc giải quyết conflict nhiều nguồn. Nếu yêu cầu conditional update, cần cơ chế được xác minh ở tầng LDAP protocol/server, hoặc một writer service duy nhất điều phối tất cả thay đổi.

Ví dụ sửa một field có chủ đích:

~~~java
ModificationItem[] changes = {
    new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("telephoneNumber", canonicalPhone))
};

ldapTemplate.modifyAttributes(personDn, changes);
~~~

Không đọc entity đầy đủ, thay một field rồi save toàn bộ nếu các field khác có thể vừa được nguồn khác sửa. Ghi đúng attribute do workflow sở hữu giúp giảm overwrite ngoài ý muốn. Tuy nhiên, targeted modify một mình vẫn không chống được hai writer cùng sửa đúng field; dùng revision/assertion hoặc single-writer nếu cần.

## 13. Merge cho multi-valued attribute

Với attribute nhiều giá trị, phải xác định semantics của từng phần tử.

Ví dụ group membership:

~~~text
Trạng thái đã đọc: {lan, binh}
Nguồn A thêm minh: {lan, binh, minh}
Nguồn B xóa binh: {lan}
~~~

Nếu chỉ lấy union, kết quả là {lan, binh, minh} và thao tác xóa của B bị mất. Nếu remove-wins, kết quả có thể là {lan, minh}. Nếu add-wins, phần tử bị xóa có thể xuất hiện lại.

Một số chiến lược:

| Policy | Kết quả khi add và remove cùng phần tử | Phù hợp |
|---|---|---|
| Add-wins | Giữ phần tử | Tập nhãn/metadata ít nhạy cảm |
| Remove-wins | Xóa phần tử | Một số quyền cần ưu tiên thu hồi |
| Source owner wins | Nguồn sở hữu membership quyết định | Group do identity governance quản lý |
| Explicit operation log | Xử lý theo event/version và actor | Membership có audit nghiêm ngặt |
| Manual conflict | Không tự merge | Quyền đặc biệt/high impact |

Với quyền truy cập, policy phải được security owner phê duyệt. Không dùng union mặc định nếu điều đó có thể giữ lại quyền đã bị thu hồi.

Nếu chỉ thêm/xóa một giá trị trong LDAP, dùng ADD_ATTRIBUTE hoặc REMOVE_ATTRIBUTE trên giá trị cụ thể để tránh replace toàn bộ snapshot. Nhưng nếu có hai writer đồng thời, vẫn cần policy/version để xử lý duplicate, add/remove ordering và quyền sở hữu.

## 14. Delete conflict và tombstone

Delete thường khó đối soát hơn update vì entry biến mất, trong khi một nguồn khác có thể vẫn giữ bản ghi cũ.

Ví dụ:

1. HR chấm dứt hợp đồng và yêu cầu disable tài khoản.
2. Job cũ chạy trễ, thấy employee vẫn còn trong snapshot.
3. Job cũ tạo lại LDAP entry đã bị xóa.

Không nên dùng “entry không tìm thấy” để suy luận rằng nghiệp vụ yêu cầu tạo lại. Cần một trạng thái lifecycle rõ ràng.

Một cách là soft delete/tombstone nghiệp vụ:

~~~text
employeeId: E-1042
lifecycleState: DEPROVISIONED
deletedAt: 2026-11-26T10:15:00Z
sourceRevision: 83
~~~

Tombstone có thể nằm trong JDBC hoặc một event ledger bền vững. Nó giữ thông tin rằng identity đã bị deprovision để job cũ không tạo lại entry.

Quy trình xóa:

1. Ghi trạng thái DEPROVISIONED và revision mới tại nguồn có thẩm quyền.
2. Phát event disable/delete.
3. Worker kiểm tra revision và identity.
4. Disable hoặc xóa LDAP entry theo retention policy.
5. Ghi kết quả và giữ tombstone đủ lâu để mọi consumer vượt qua event cũ.
6. Chỉ purge tombstone sau thời hạn replay/reconciliation được quy định.

LDAP không có một soft-delete semantics phổ quát cho mọi server. Tombstone và deleted object trong Active Directory có cơ chế riêng. Ứng dụng nên tách lifecycle nghiệp vụ khỏi việc entry hiện đang tồn tại trong DIT.

## 15. Rename/move và conflict identity

DN có thể thay đổi do rename hoặc move. Reconciliation cần phân biệt:

- Cùng một identity chuyển sang DN mới.
- Một entry cũ bị xóa và entry mới được tạo.
- Hai entry khác nhau vô tình dùng cùng business key.
- Job cũ ghi vào DN cũ sau khi rename.

Nên lưu mapping:

| Business key | Directory identity | Current DN | Revision |
|---|---|---|---|
| E-1042 | entryUUID/objectGUID | uid=lan,ou=employees,... | 83 |

Khi DN thay đổi:

1. Resolve theo business key hoặc stable directory identifier.
2. Xác minh entry đích thực sự là cùng identity.
3. Cập nhật mapping DN trong JDBC.
4. Phát event đổi DN cho các consumer phụ thuộc.
5. Vô hiệu cache theo DN cũ.
6. Không tự tạo entry mới chỉ vì lookup DN cũ không thấy.

Nếu directory không cung cấp stable identifier có thể dùng qua vòng đời, ứng dụng cần quy tắc rename/move và mapping ledger riêng.

## 16. Operational attributes và version marker theo sản phẩm

Không có một thuộc tính version chuẩn duy nhất dùng được giống nhau trên mọi LDAP server.

| Directory | Metadata thường gặp | Cách dùng và giới hạn |
|---|---|---|
| LDAP generic | modifyTimestamp, createTimestamp | Operational timestamps; hữu ích quan sát, không phải global revision/lock |
| OpenLDAP | entryCSN, contextCSN | Change sequence metadata gắn với syncrepl/replication; không nên xem như app-level version portable |
| Active Directory | uSNChanged | USN do từng DC cấp; không replicated, không so trực tiếp giữa các DC |
| Active Directory | whenChanged, replication metadata | Hữu ích kiểm tra/audit theo semantics AD; không thay assertion/version contract của ứng dụng |
| Ứng dụng | appRevision/custom version | Có thể làm optimistic token nếu mọi writer cùng tuân thủ và server hỗ trợ conditional update |

### Active Directory uSNChanged

Microsoft mô tả uSNChanged là update sequence number do domain controller cục bộ cấp. Giá trị tăng theo thay đổi trên DC đó và **không được replicate**. Vì vậy, không so uSNChanged của hai DC như một global order. Khi dùng làm change tracking, phải gắn watermark với đúng DC/invocation context và tuân theo hướng dẫn AD.

### OpenLDAP entryCSN/contextCSN

OpenLDAP dùng entryCSN để theo dõi thay đổi entry và contextCSN để biểu diễn trạng thái đồng bộ của naming context trong syncrepl. Các giá trị này phục vụ replication engine; không thay thế business revision hoặc policy phân xử field conflict giữa JDBC và LDAP.

## 17. LDAP Content Synchronization và incremental change feed

RFC 4533 mô tả LDAP Content Synchronization Operation. Client có thể:

- Thực hiện refreshOnly để lấy bản ban đầu hoặc poll thay đổi.
- Dùng syncCookie để tiếp tục một synchronization session.
- Dùng refreshAndPersist để nhận thông báo khi entry thay đổi.
- Nhận trạng thái add, modify, delete theo sync controls.

RFC 4533 đang ở trạng thái **Experimental**, không phải Internet Standards Track. Server phải hỗ trợ extension và client phải triển khai các controls tương ứng. Không giả định mọi directory hoặc Spring Data LDAP repository tự cung cấp abstraction đồng bộ này.

Điểm quan trọng:

- Sync cookie là trạng thái tiếp tục đồng bộ; lưu bền vững và cập nhật có thứ tự.
- DN có thể thay đổi; RFC 4533 dùng entry UUID để nhận diện entry ổn định hơn DN trong luồng sync.
- Server có thể yêu cầu refresh lại nếu không thể tiếp tục incremental sync.
- Thông báo thay đổi giúp cập nhật bản sao, nhưng không quyết định nguồn nào có thẩm quyền cho business field.
- Refresh/persist không tạo transaction với JDBC.
- Cần giữ cùng base, scope, filter và attribute selection trong một sync session theo yêu cầu protocol.

OpenLDAP syncrepl triển khai LDAP Sync với cookie, entryCSN/contextCSN và refreshOnly/refreshAndPersist. Đây là khả năng directory server, không phải một tính năng CRUD mặc định của LdapRepository.

## 18. Kiến trúc reconciliation loop

Một reconciliation loop có thể chia thành các bước:

~~~mermaid
flowchart TD
    A["Load source state + version"]
    B["Load target LDAP state"]
    C["Resolve stable identity"]
    D["Canonicalize fields"]
    E["Apply ownership / merge policy"]
    F{"Conflict resolvable?"}
    G["Create conflict record"]
    H["Build desired-state diff"]
    I["Conditional LDAP update"]
    J{"Update succeeded?"}
    K["Read back / verify"]
    L["Record checkpoint + audit"]
    M["Retry or re-read latest state"]
    A --> B --> C --> D --> E --> F
    F -->|No| G
    F -->|Yes| H --> I --> J
    J -->|Yes| K --> L
    J -->|Assertion failed / stale| M --> B
~~~

Mỗi vòng lặp cần:

1. Đọc snapshot có revision từ nguồn authoritative.
2. Đọc trạng thái LDAP hiện tại theo business key.
3. Kiểm tra identity và duplicate.
4. Canonicalize các field trước khi so sánh.
5. Áp dụng ownership/merge policy.
6. Tạo diff chỉ gồm attribute được workflow sở hữu.
7. Ghi có điều kiện nếu có version token.
8. Đọc lại hoặc xác minh kết quả.
9. Lưu audit/checkpoint.
10. Đưa conflict không tự giải quyết vào queue.

Nếu không có conditional write, hãy serialize tất cả writer qua một service/queue duy nhất hoặc chấp nhận khả năng race và thực hiện reconciliation lại. Không giả định read-then-write là atomic.

## 19. Incremental sync, watermark và checkpoint

Khi dữ liệu lớn, không nên full scan liên tục nếu có change feed đáng tin cậy. Có thể dùng watermark:

~~~text
lastCompletedWatermark = 5000

Read changes where sourceSequence > 5000
Apply each change idempotently
Persist new checkpoint only after durable application
~~~

Checkpoint phải có scope:

- Source system/instance.
- Directory server/DC hoặc replication provider.
- Search base, scope, filter và attribute projection.
- Sync cookie hoặc sequence/watermark.
- Thời điểm cập nhật.
- Phiên bản parser/mapping.

Quy tắc quan trọng:

- Chỉ advance checkpoint sau khi mọi thay đổi trước checkpoint đã được ghi bền vững hoặc đưa vào conflict/dead-letter ledger.
- Nếu event trùng, xử lý idempotent.
- Nếu event đến sai thứ tự, dùng revision/source sequence để loại stale update.
- Nếu cookie hết hạn hoặc server trả refresh-required, chạy full refresh có kiểm soát.
- Nếu filter/scope thay đổi, thường phải tạo synchronization session mới và reconcile lại nội dung tương ứng.
- Không dùng một watermark từ DC này để tiếp tục polling trên DC khác nếu semantics server không cho phép.

## 20. Conflict ledger và audit trail

Không nên chỉ ghi log exception rồi bỏ qua conflict. Hãy lưu một record có thể điều tra và replay:

| Field | Mục đích |
|---|---|
| conflictId | Identity duy nhất của conflict |
| businessKey | Nhân viên/đối tượng liên quan |
| sourceSystem | Nguồn phát thay đổi |
| targetSystem | Hệ thống bị đối soát |
| attributeName | Field xung đột |
| observedSourceVersion | Revision nguồn |
| observedTargetVersion | Revision đích |
| sourceValueHash | Hash/định danh giá trị nguồn nếu cần |
| targetValueHash | Hash/định danh giá trị đích |
| policy | Quy tắc đã áp dụng hoặc cần phê duyệt |
| status | OPEN, RESOLVED, REJECTED, RETRY |
| createdAt/resolvedAt | Thời điểm điều tra |
| resolutionActor | Service hoặc người phê duyệt |

Tránh lưu plaintext của password, token, certificate hoặc PII đầy đủ nếu không cần thiết. Nếu cần lưu snapshot để audit, áp dụng encryption, access control và retention.

Một conflict đã resolve cần giữ policy và version dùng để resolve. Điều này giúp giải thích vì sao dữ liệu hiện tại có giá trị đó và tránh cùng một conflict quay lại vô hạn.

## 21. Idempotency và xử lý event trùng

Incremental sync, queue và retry thường có at-least-once delivery. Cùng một event có thể đến nhiều lần.

Một consumer idempotent nên:

1. Dùng eventId/sourceRevision làm deduplication key.
2. Lưu lastAppliedRevision theo business key và source.
3. Bỏ qua event có revision nhỏ hơn hoặc bằng revision đã áp dụng.
4. Nếu revision nhảy có gap, kiểm tra có cần fetch snapshot mới không.
5. Chỉ đánh dấu applied sau khi LDAP state đã được xác minh hoặc operation được chấp nhận theo hợp đồng.
6. Lưu kết quả theo event để retry không tạo side effect lặp.

Không dùng timestamp đơn thuần làm dedup key nếu nhiều event có thể cùng thời điểm hoặc event được replay.

Với Add entry, nếu nhận entryAlreadyExists, đọc lại và so business key/desired state. Với Delete, noSuchObject có thể là trạng thái đích đã đạt. Với Modify, timeout là unknown outcome; đọc lại trước khi gửi lại.

## 22. Xử lý conflict khi nhiều replica LDAP cùng ghi

Nếu nhiều LDAP server writable, replication conflict resolution là một tầng riêng.

Ví dụ Active Directory multi-master replication có metadata theo attribute và quy tắc version/time/originating invocation để xử lý update. OpenLDAP multi-provider replication dùng CSN và SID theo cơ chế syncrepl. Các chi tiết này khác nhau giữa sản phẩm và version.

Ứng dụng nên:

- Ghi qua endpoint được thiết kế cho writable updates và theo topology vận hành.
- Không đọc từ replica chậm rồi ghi snapshot cũ vào writer khác.
- Hiểu replication convergence và độ trễ đọc-sau-ghi.
- Không tự so metadata nội bộ vendor như thể chúng là version portable.
- Sau khi ghi, xác minh ở writer/replica phù hợp với consistency requirement.
- Nếu nhiều hệ thống cùng là writer, có ownership/version ở tầng nghiệp vụ.

Reconciliation giữa JDBC và LDAP cần phân biệt conflict do app dual-write với conflict do replication nội bộ. Nếu không, ứng dụng có thể liên tục “sửa” một trạng thái mà directory replication vẫn đang hội tụ.

## 23. Mô hình code service: reconcile một field có ownership

Ví dụ HR sở hữu employeeStatus. Service đọc trạng thái mong muốn từ nguồn và so với LDAP; nếu khác, nó chỉ sửa attribute này.

~~~java
public ReconcileResult reconcileEmployeeStatus(
        EmployeeSnapshot source,
        DirectoryPerson current) {

    if (!source.employeeId().equals(current.getEmployeeId())) {
        return ReconcileResult.identityConflict();
    }

    EmploymentStatus desired = source.employmentStatus();
    EmploymentStatus actual = current.getEmploymentStatus();

    if (desired == actual) {
        return ReconcileResult.noChange();
    }

    return ReconcileResult.updateRequired(
            source.revision(),
            actual,
            desired);
}
~~~

Đoạn code trên chỉ tính quyết định, chưa ghi LDAP. Service ghi theo policy:

~~~java
ModificationItem[] changes = {
    new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute(
                    "employeeStatus",
                    decision.desired().directoryValue()))
};

// Nếu có assertion control, đính kèm expected revision vào cùng Modify.
ldapTemplate.modifyAttributes(personDn, changes);
~~~

Nếu nguồn HR là owner duy nhất và tất cả thay đổi LDAP đều được xem là drift, có thể sửa lại giá trị theo HR snapshot. Nếu có writer khác được phép thay đổi cùng field, phải bổ sung revision/assertion hoặc đưa conflict vào review. Không dùng kết quả read hiện tại làm bằng chứng rằng nó vẫn đúng tại thời điểm Modify.

## 24. Observability và vận hành

Theo dõi reconciliation bằng các metric không chứa PII:

- reconciliation_runs_total{source,target,result}
- reconciliation_entries_scanned
- reconciliation_entries_changed
- reconciliation_conflicts_total{attribute,policy}
- reconciliation_assertion_failed_total
- reconciliation_stale_events_total
- reconciliation_retry_total{reason}
- reconciliation_dead_letter_total
- reconciliation_checkpoint_age_seconds
- reconciliation_lag_seconds

Tên trên là metric gợi ý, không phải metric mặc định của Spring LDAP.

Dashboard nên cho biết:

- Số conflict đang mở và tuổi conflict lớn nhất.
- Tỷ lệ conflict tự giải quyết/manual.
- Số event trễ, trùng và stale bị bỏ qua.
- Checkpoint hiện tại và thời điểm full refresh gần nhất.
- Tỷ lệ assertionFailed.
- Số entry duplicate theo business key.
- Thời gian hội tụ sau một thay đổi nguồn.
- Số lượng tombstone đang giữ.

Không dùng DN, email hoặc employeeId làm metric label có cardinality cao. Log có thể chứa correlation ID/conflict ID và business key đã được bảo vệ theo policy.

## 25. Bảo mật và quyền ghi

Reconciliation job thường có quyền rộng vì nó đọc và sửa nhiều entry. Cần giảm phạm vi quyền:

- Bind identity chỉ đọc/ghi các OU và attribute thuộc trách nhiệm của job.
- Không cho job sửa attribute do nguồn khác sở hữu.
- Tách quyền đọc và quyền ghi nếu policy yêu cầu.
- Dùng TLS và xác minh certificate.
- Validate business key rồi dựng DN bằng API DN phù hợp.
- Dùng filter builder hoặc LDAP SDK để encode filter assertion.
- Không nhận raw LDAP filter từ người dùng.
- Bảo vệ conflict ledger và outbox khỏi truy cập trái phép.
- Audit thao tác manual resolution, actor, lý do và revision.
- Có kill switch để dừng reconciliation nếu phát hiện job đang ghi sai diện rộng.

Một lỗi mapping hoặc ownership policy có thể gây overwrite hàng nghìn entry. Trước khi bật job trên production, chạy dry-run, giới hạn số entry mỗi batch, canary theo OU và có phương án dừng/khôi phục.

## 26. Kiểm thử đối soát và conflict

### Ma trận test chức năng

| Kịch bản | Kết quả mong đợi |
|---|---|
| Hai nguồn cập nhật field khác owner | Mỗi field theo đúng owner |
| Event cũ đến sau event mới | Stale event bị bỏ qua |
| Event gửi hai lần | Không tạo side effect lặp |
| Hai writer cùng revision | Chỉ một conditional modify thành công |
| Assertion revision không còn đúng | assertionFailed, đọc lại và resolve |
| LDAP không hỗ trợ assertion control | Fail closed hoặc chuyển writer queue |
| Hai entry có cùng business key | Conflict identity, không chọn tùy tiện |
| DN được rename | Mapping business key cập nhật, không tạo duplicate |
| Attribute absent và empty | Được phân biệt theo contract |
| Add và remove cùng membership | Policy add-wins/remove-wins/owner được áp dụng |
| Delete đến trước update cũ | Tombstone ngăn tái tạo entry |
| Sync cookie không còn hợp lệ | Full refresh theo quy trình |
| Replica chưa hội tụ | Không ghi đè bằng snapshot stale |
| Manual resolution | Có audit actor, policy và revision |

### Race condition test với Assertion Control

1. Tạo entry revision 10.
2. Hai client cùng đọc revision 10.
3. Client A gửi Modify có assertion revision=10 và đổi revision thành 11.
4. Client B gửi Modify có assertion revision=10.
5. Xác nhận A thành công, B nhận assertionFailed.
6. B đọc lại revision 11 và tính lại conflict.
7. Kiểm tra không có update nào từ B bị ghi một phần.

Test cần chạy với LDAP server thực có hỗ trợ Assertion Control; mock LdapTemplate không chứng minh server thực thi control nguyên tử.

### Test incremental sync

Nếu triển khai RFC 4533 hoặc vendor-specific change feed:

- Test initial refresh.
- Test add/modify/delete notifications.
- Test DN rename.
- Test reconnect và cookie resume.
- Test cookie không hợp lệ/refresh-required.
- Test event trùng và out-of-order.
- Test checkpoint chỉ tiến sau khi thay đổi đã được apply bền vững.
- Test thay đổi search base/filter tạo session mới.

## 27. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Job đồng bộ ghi đè field của IT | Không có field ownership | Tạo ownership matrix và chỉ update field thuộc owner |
| Snapshot cũ ghi đè dữ liệu mới | Không có revision/conditional write | Assertion Control hoặc single-writer |
| Timestamp mới hơn nhưng dữ liệu cũ | Clock skew hoặc event replay | Dùng source revision/sequence |
| So sánh DN sai | So raw string | Parse bằng LdapName |
| Rename tạo duplicate | Dùng DN làm business identity | Dùng business key/stable directory ID |
| Delete xong entry xuất hiện lại | Event cũ tái tạo entry | Tombstone và revision |
| Group membership mất thay đổi | Replace toàn bộ set | Operation log/policy và add/remove có điều kiện |
| uSNChanged khác giữa DC | Attribute local, không replicated | Gắn watermark với đúng DC |
| entryCSN bị dùng như app version | Nhầm metadata replication với business version | Tạo appRevision riêng |
| Sync cookie bị từ chối | Session/cookie không còn hợp lệ | Full refresh có kiểm soát |
| Assertion Control bị bỏ qua | Control không critical hoặc server không hỗ trợ | Kiểm tra supportedControl và fail closed |
| Conflict loop lặp vô hạn | Không ghi ledger hoặc không có policy | Lưu conflict state, retry có giới hạn |
| Reconciliation sửa nhầm replica | Không hiểu topology/replication lag | Chọn writer và consistency policy |
| Manual sửa không audit | Không có conflict ledger | Ghi actor, reason và revision |

## 28. Bài tập thực hành

**Bối cảnh:** hệ thống nhân sự có JDBC là nguồn dữ liệu chính cho employeeId, departmentNumber và employeeStatus. LDAP được IT quản lý cho telephoneNumber và group membership. Một job đồng bộ hai chiều chạy mỗi 5 phút.

Thực hiện trên database và directory test:

1. Viết ownership matrix cho ít nhất sáu attribute.
2. Tạo custom attribute employeeId và appRevision trong schema test, hoặc dùng attribute đã được tổ chức phê duyệt.
3. Tạo một user entry và lưu mapping employeeId ↔ DN ↔ stable directory identifier.
4. Viết canonicalizer cho DN, email, phone và multi-valued membership.
5. Tạo hai nguồn cùng cập nhật employeeStatus và telephoneNumber; xác nhận field ownership quyết định nguồn thắng.
6. Mô phỏng stale event đến sau event mới; dùng sourceRevision để bỏ qua event cũ.
7. Kiểm tra Root DSE supportedControl cho OID Assertion Control 1.3.6.1.1.12.
8. Dùng LdapTemplate.executeReadWrite và JNDI LdapContext để gửi conditional Modify; dùng BER encoder đã kiểm thử.
9. Chạy hai client cùng revision; xác nhận chỉ một update thành công.
10. Thêm conflict ledger cho assertionFailed, duplicate identity và manual review.
11. Mô phỏng DN rename; xác nhận reconciliation không tạo entry mới.
12. Mô phỏng delete và event cũ; kiểm tra tombstone ngăn tái tạo.
13. Tạo multi-valued membership conflict; áp dụng add-wins/remove-wins hoặc owner policy đã chọn.
14. Nếu directory hỗ trợ LDAP Content Sync, thử initial refresh, cookie, modify/delete và reconnect; ghi rõ RFC 4533 là Experimental.
15. Viết job full reconciliation và incremental reconciliation có checkpoint.
16. Mô phỏng replica lag và kiểm tra job không ghi snapshot cũ ngược lại writer.
17. Đo conflict count, stale event count, checkpoint age, convergence lag và số lần manual review.
18. Viết runbook dừng job, replay event và xử lý conflict diện rộng.

**Tiêu chí hoàn thành:** người học giải thích được nguồn dữ liệu có thẩm quyền theo từng field, phát hiện stale/concurrent write, dùng revision và assertion control đúng điều kiện, phân biệt change feed với conflict resolution, và xây được reconciliation có audit, tombstone, checkpoint và kiểm thử race condition.

## 29. Tổng kết và tài liệu tham khảo

Đối soát dữ liệu không chỉ là tìm hai giá trị khác nhau rồi chọn một. Hệ thống phải biết **ai sở hữu field, hai giá trị thuộc cùng identity hay không, phiên bản nào mới hơn theo quy tắc tin cậy, và thay đổi có được ghi nguyên tử với điều kiện đã đọc hay không**.

Các nguyên tắc cần nhớ:

- Định nghĩa system of record và field ownership trước khi đồng bộ.
- Dùng business key/stable identifier; DN có thể đổi.
- Canonicalize theo schema và contract từng field.
- Không dựa vào client timestamp như global ordering nếu chưa bảo đảm clock và semantics.
- Dùng revision và LDAP Assertion Control cho conditional update khi server hỗ trợ.
- Không nhầm assertion control với LDAP transaction hay change synchronization.
- Giữ tombstone để ngăn event cũ tái tạo entry đã deprovision.
- Lưu sync cookie/checkpoint bền vững và chỉ advance sau khi apply thành công.
- Phân biệt application conflict với replication conflict của directory server.
- Có conflict ledger, audit, retry, reconciliation và manual review.
- Kiểm thử race condition trên LDAP server thực, không chỉ mock repository.

Tài liệu tham khảo:

- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528): conditional operation, atomic assertion evaluation và result code assertionFailed.
- [RFC 4533 — LDAP Content Synchronization Operation](https://www.rfc-editor.org/rfc/rfc4533): refreshOnly, refreshAndPersist, syncCookie và trạng thái add/modify/delete; RFC đang ở trạng thái Experimental.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): executeReadWrite và truy cập DirContext có quản lý.
- [Spring LDAP — ContextExecutor API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/ContextExecutor.html): callback thực hiện thao tác trên DirContext.
- [OpenLDAP 2.6 Administrator's Guide — Replication](https://openldap.org/doc/admin26/replication.html): syncrepl, entryCSN, contextCSN, refreshOnly và refreshAndPersist.
- [Microsoft Learn — Polling for Changes Using uSNChanged](https://learn.microsoft.com/en-us/windows/win32/ad/polling-for-changes-using-usnchanged): cách dùng uSNChanged và giới hạn do giá trị không replicated giữa các DC.
- [Microsoft Open Specifications — uSNChanged](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adls/b2bce146-f6e3-4d68-8348-3b71aeafdc9d): thuộc tính USN do local directory cấp và không replicated.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository abstraction và cấu hình Spring Data LDAP.
