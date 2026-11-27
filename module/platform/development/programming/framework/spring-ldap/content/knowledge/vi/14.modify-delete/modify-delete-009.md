# Đảm bảo thao tác thất bại không để trạng thái nửa chừng trong Spring LDAP

## 1. Một cập nhật thất bại có thể để lại những gì?

Giả sử dịch vụ nhân sự dùng **Spring LDAP** để thay email, bổ sung số điện thoại và xóa ghi chú cũ của một người dùng. Một quy trình khác cần xóa tài khoản LDAP, gỡ tham chiếu khỏi các nhóm và cập nhật cơ sở dữ liệu ứng dụng.

Nếu lỗi xuất hiện giữa các lời gọi độc lập, trạng thái có thể lệch: email đã đổi nhưng ghi chú vẫn còn; tài khoản đã bị xóa nhưng database vẫn đánh dấu đang hoạt động; hoặc một số thành viên nhóm đã được gỡ nhưng những nhóm khác chưa thay đổi.

**Điều cốt lõi là phải phân biệt đơn vị nguyên tử của LDAP với transaction của cả quy trình nghiệp vụ.**

- Một **LDAP Modify request** chứa nhiều sửa đổi trên **cùng một entry** được server áp dụng theo thứ tự **như một thao tác nguyên tử**: nếu một sửa đổi không hợp lệ, không được để lại những sửa đổi khác của cùng request ở trạng thái đã commit.
- Một **LDAP Delete request** tác động lên một entry đích, không mặc nhiên xóa nguyên tử cả cây LDAP hay các tham chiếu trong entry khác.
- Nhiều yêu cầu `modifyAttributes`, `unbind`, `rename`, thao tác SQL hoặc gọi API bên ngoài **không tự thành một transaction chung** chỉ vì chúng được gọi trong một phương thức Java.

Bài này thuộc chương **Modify và delete** trong module **Spring LDAP**. Kiến thức liên quan bao gồm DN, schema, filter, `LdapTemplate`, `DirContextAdapter`, `LdapClient`/ODM, `ContextSource`, xác thực, kết nối TLS, pooling, xử lý lỗi và kiểm thử thư mục an toàn.

**Sau bài học, bạn có thể:**

1. Nhận biết thao tác LDAP nào nguyên tử ở phạm vi một entry.
2. Gộp các thay đổi liên quan vào một `ModificationItem[]` để tránh cập nhật dở dang.
3. Phân biệt lỗi bị server từ chối rõ ràng với kết quả **chưa biết** sau khi mất response.
4. Thiết kế xóa user an toàn khi có quan hệ nhóm, dữ liệu SQL và các dịch vụ phụ thuộc.
5. Áp dụng idempotency, checkpoint, bù trừ và đối soát cho quy trình nhiều bước.
6. Kiểm thử thất bại có chủ đích, mất kết nối, ACL/schema và tính nhất quán của dữ liệu.

## 2. So sánh một Modify request với ba Modify request

Giả sử entry thử nghiệm ban đầu:

~~~ldif
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
description: active
description: onboarding
~~~

Mục tiêu: đổi email thành `alice.new@example.org`, thêm `+84 28 3333 4444` và bỏ **đúng một giá trị** `onboarding`, giữ `active`.

### 2.1. Ba request: có khả năng cập nhật một phần

~~~text
Request 1: REPLACE mail                   -> thành công
Request 2: ADD telephoneNumber            -> thành công
Request 3: REMOVE description=onboarding  -> thất bại

Hậu quả: mail và phone có thể đã đổi, description vẫn còn onboarding.
~~~

Nếu Request 3 bị server từ chối, LDAP **không tự rollback** hai request đã thành công trước đó.

### 2.2. Một request: nguyên tử trên entry

~~~text
LDAP Modify request duy nhất
  |
  +-- REPLACE mail
  +-- ADD telephoneNumber
  +-- REMOVE description=onboarding
  |
  v
LDAP server kiểm tra toàn bộ danh sách và quyền/schema
  |
  +-- thành công: áp dụng cả ba
  |
  +-- từ chối: không áp dụng một phần danh sách
~~~

Nguyên tắc này thuộc ngữ nghĩa của LDAP Modify. Nó không bảo đảm rằng server, extension hoặc ứng dụng khác không có side effect bên ngoài entry; các hiệu ứng mở rộng cần được hiểu theo hạ tầng triển khai.

### 2.3. Bảng ranh giới quan trọng

| Công việc | Số request thông thường | Tính nguyên tử có thể dựa vào |
| --- | --- | --- |
| Sửa ba thuộc tính trong một entry bằng một Modify | 1 | Có cho danh sách Modify của entry đó |
| Sửa email rồi sửa điện thoại bằng hai Modify | 2 | Chỉ mỗi request riêng |
| Sửa user rồi sửa group | 2 | Không có transaction chung mặc định |
| Xóa một entry không có con | 1 Delete | Một thao tác Delete với entry đích |
| Xóa toàn subtree bằng nhiều Delete | Nhiều request | Có thể xóa dở dang |
| Sửa LDAP rồi commit SQL | Hai hệ thống | Không có atomicity chung mặc định |
| LDAP Modify bị timeout sau khi gửi | Có thể một request | Client **chưa biết** server đã áp dụng chưa |

Một số LDAP server có transaction extension hoặc overlay riêng. Chỉ dùng chúng khi đã kiểm tra sản phẩm, phiên bản và hợp đồng thực tế; không coi đó là tính năng mặc định của `LdapTemplate`.

## 3. Sử dụng ModificationItem[] để gộp thay đổi

`ModificationItem` là kiểu **JNDI** biểu diễn một phép sửa thuộc tính, thường kết hợp `BasicAttribute` và một trong ba mã:

| Mã thao tác | Ý nghĩa |
| --- | --- |
| `DirContext.ADD_ATTRIBUTE` | Thêm thuộc tính hoặc một số giá trị |
| `DirContext.REPLACE_ATTRIBUTE` | Đặt lại tập giá trị của thuộc tính |
| `DirContext.REMOVE_ATTRIBUTE` | Xóa một giá trị cụ thể hoặc toàn thuộc tính |

Đây là ví dụ sửa ba thuộc tính bằng **một lần gọi**:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

// Giả định ldapTemplate là bean đã được cấu hình.
Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "alice")
        .build();

ModificationItem[] changes = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "alice.new@example.org")
    ),
    new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("telephoneNumber", "+84 28 3333 4444")
    ),
    new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("description", "onboarding")
    )
};

ldapTemplate.modifyAttributes(dn, changes);
~~~

Với `ContextSource.base = dc=example,dc=org`, DN tương đối `uid=alice,ou=people` trỏ đến DN đầy đủ `uid=alice,ou=people,dc=example,dc=org`.

Nếu tất cả thay đổi hợp lệ, trạng thái dự kiến:

~~~ldif
dn: uid=alice,ou=people,dc=example,dc=org
mail: alice.new@example.org
telephoneNumber: +84 28 1111 2222
telephoneNumber: +84 28 3333 4444
description: active
~~~

### 3.1. Thứ tự của danh sách có ý nghĩa

LDAP Modify xử lý các thay đổi theo thứ tự xuất hiện. Nếu cùng sửa một thuộc tính, chuỗi `REMOVE` rồi `ADD` có thể khác `ADD` rồi `REMOVE`, đặc biệt khi thuộc tính đơn trị hoặc giá trị trùng.

**“Thực hiện theo thứ tự” không có nghĩa server commit mỗi phần tử riêng lẻ.** Danh sách của một request vẫn được áp dụng như một thao tác nguyên tử. Không tự sắp xếp lại mảng khi có phụ thuộc thứ tự.

### 3.2. Atomicity không ngăn một yêu cầu sai nhưng hợp lệ

Nếu `telephoneNumber` có ba giá trị nhưng code dùng `REPLACE_ATTRIBUTE` với chỉ một giá trị, những số còn lại có thể mất. Đây là lỗi diễn đạt **ý định nghiệp vụ**, không phải vi phạm atomicity.

Muốn bổ sung một giá trị vào thuộc tính đa trị thì cân nhắc `ADD_ATTRIBUTE`; muốn xóa đúng một giá trị, dùng `REMOVE_ATTRIBUTE` kèm giá trị. Không thay toàn bộ tập giá trị chỉ vì form gửi một phần dữ liệu.

### 3.3. Một phần tử không hợp lệ làm request thất bại

Nếu entry không có `description: onboarding`, yêu cầu `REMOVE_ATTRIBUTE` có thể gặp `noSuchAttribute` (code 16). Khi đó cả request phải thất bại mà không áp dụng thay email hoặc thêm phone trong cùng request đó.

Nếu ACL chỉ cho phép thay mail nhưng không cho sửa phone, server cũng có thể từ chối cả Modify. **Đừng tách request chỉ để làm “phần được phép” cập nhật trước**, trừ khi nghiệp vụ chấp nhận trạng thái từng phần và quy trình theo dõi rõ ràng.

## 4. Vì sao ba lời gọi modifyAttributes không tạo một transaction?

Ví dụ ba mảng `ModificationItem[]` độc lập:

~~~java
ldapTemplate.modifyAttributes(dn, mailChanges);
ldapTemplate.modifyAttributes(dn, phoneChanges);
ldapTemplate.modifyAttributes(dn, noteChanges);
~~~

Từng lời gọi được thực thi riêng. Nếu lời thứ nhất và thứ hai đã trả thành công, lỗi của lời thứ ba không khiến Spring LDAP tự phát lệnh ngược để hủy hai bước trước.

Nếu ba thay đổi có chung điều kiện thành công/thất bại và cùng entry, tốt hơn là gộp:

~~~java
ModificationItem[] allChanges = {
    mailChanges[0],
    phoneChanges[0],
    noteChanges[0]
};

ldapTemplate.modifyAttributes(dn, allChanges);
~~~

Đoạn minh họa giả định mỗi mảng ban đầu chứa đúng một phần tử. Với một danh sách động, hãy giữ thứ tự và kiểm tra các thao tác có mâu thuẫn không.

**Giới hạn:** gộp một request chỉ có thể áp dụng nếu tất cả thay đổi thuộc **cùng entry**. Không thể gộp sửa user và sửa group thành một mảng rồi kỳ vọng LDAP tự biết hai DN.

## 5. DirContextAdapter cũng không tạo transaction đa entry

Spring LDAP cho phép đọc entry dưới dạng `DirContextOperations`, thay đổi trạng thái adapter rồi gửi một lần:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "alice")
        .build();

DirContextOperations context = ldapTemplate.lookupContext(dn);

context.setAttributeValue("mail", "alice.new@example.org");
context.addAttributeValue("telephoneNumber", "+84 28 3333 4444");
context.removeAttributeValue("description", "onboarding");

ldapTemplate.modifyAttributes(context);
~~~

Các setter/add/remove thay đổi **đối tượng ở phía client**; `modifyAttributes(context)` mới gửi LDAP Modify. Adapter có thể cung cấp `getModificationItems()` để quan sát delta.

Cần lưu ý:

- Không giả định một setter luôn sinh đúng một opcode cụ thể trên mọi phiên bản; hãy kiểm thử với dữ liệu gốc và phiên bản Spring LDAP.
- Tránh sửa trực tiếp `context.getAttributes()` rồi mặc định cơ chế dirty tracking nhận biết mọi thay đổi; ưu tiên API của `DirContextOperations`.
- `lookupContext(dn)` rồi `modifyAttributes(context)` là **hai bước tách biệt theo thời gian**. Adapter không tự giải quyết thay đổi đồng thời xảy ra giữa hai bước.
- Sửa user qua một adapter rồi sửa group qua adapter khác vẫn tạo **hai request** và không có atomicity chung.

**Đổi entry mới và sửa entry cũ là hai việc khác nhau:** `LdapTemplate.bind(context)` trong Spring LDAP tạo entry (LDAP Add); `modifyAttributes` sửa entry hiện có; `rename` thay DN/RDN.

## 6. Delete một entry không đồng nghĩa xóa cả nhánh

Để xóa một entry có DN đã biết:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "training-01")
        .build();

ldapTemplate.unbind(dn);
~~~

Một LDAP Delete thông thường tác động lên **entry tại DN đích**, không mặc nhiên xóa nguyên tử cả subtree hoặc mọi tham chiếu trong entry khác.

### 6.1. Delete một entry còn con thường bị từ chối

~~~text
ou=engineering,ou=people,dc=example,dc=org
  |
  +-- uid=bob
  +-- uid=carol
~~~

Xóa `ou=engineering` bằng một LDAP Delete thông thường khi còn con có thể trả LDAP result code **66 — notAllowedOnNonLeaf**. `unbind(dn)` không phải lệnh “xóa đệ quy tất cả entry bên dưới”.

Nếu ứng dụng tự xóa từng con rồi mới xóa OU:

~~~text
Delete uid=bob     -> thành công
Delete uid=carol   -> thất bại
Delete OU          -> không thể hoàn tất

Cây đã mất Bob, nhưng Carol và OU vẫn còn.
~~~

Một số LDAP server có subtree-delete extension/control riêng, nhưng cần kiểm tra khả năng hỗ trợ và semantics cụ thể; không suy đoán tính nguyên tử của một extension từ API Delete thông thường.

### 6.2. Group membership có thể ở entry khác

Một người dùng có thể được tham chiếu từ entry nhóm:

~~~text
uid=alice,ou=people,...          (entry người dùng)
cn=developers,ou=groups,...      (thuộc tính member chứa DN Alice)
~~~

Nếu ứng dụng xóa user và đồng thời sửa membership của group, đó là **hai entry khác nhau** và thường là hai request LDAP.

Có server cài overlay/plugin **referential integrity** để tự điều chỉnh tham chiếu khi entry bị xóa hoặc đổi tên. Tuy nhiên, **không mặc định mọi server hoặc schema làm điều đó**. Trước khi triển khai, hãy kiểm tra đặc tính hạ tầng, quyền sửa nhóm và yêu cầu nghiệp vụ.

### 6.3. Xóa là thao tác có thể khó hoàn tác hoàn toàn

Ngay cả khi ứng dụng lưu một bản sao thuộc tính rồi Add lại entry sau khi xóa, bạn **không chắc tái tạo đầy đủ** operational attributes, `entryUUID`, timestamp, thông tin xác thực, membership, quyền hoặc state do server quản lý. Vì vậy, “Delete rồi nếu lỗi thì Add lại” **không phải rollback hoàn hảo**.

Muốn an toàn cần xem xét **deprovisioning có giai đoạn**, giữ bản ghi kiểm toán, xác minh điều kiện và chỉ xóa vật lý ở bước phù hợp.

## 7. Phân biệt kết quả bị từ chối và kết quả không xác định

Một thao tác ghi có ba trạng thái quan sát quan trọng:

| Quan sát từ client | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| Server xác nhận **success** | Request được xử lý thành công theo hợp đồng | Đọc lại nếu nghiệp vụ cần |
| Server trả **error rõ ràng** | Request bị từ chối theo mã LDAP | Xử lý nguyên nhân, không giả định success |
| **Không nhận được response** | Mất kết nối, timeout hoặc lỗi mạng sau khi gửi | Outcome **unknown**; không kết luận thành công hay thất bại |

### 7.1. Mất response sau Modify

~~~text
Client                         LDAP server
  |                                 |
  +------ LDAP Modify ------------->|
  |                                 +-- Có thể đã áp dụng
  X <------ Response ---------------|
       Kết nối đứt trước khi nhận
~~~

Lúc này client không thể biết chắc request đã được commit chưa. Một hành động `ADD_ATTRIBUTE` retry có thể gặp `attributeOrValueExists` (code 20) vì lần đầu đã thêm giá trị. Một `REMOVE_ATTRIBUTE` retry có thể gặp `noSuchAttribute` (code 16) vì lần đầu đã xóa.

**Không retry mù quáng.** Trước hết nên đọc lại trạng thái entry bằng tài khoản có quyền, tại endpoint phù hợp, so sánh với ý định và xác định liệu có tác nhân khác sửa trong thời gian đó không.

### 7.2. Mất response sau Delete

Nếu Delete đã được server xử lý nhưng response mất, lần gọi lại có thể nhận `noSuchObject` (code 32). Nó có thể là dấu hiệu request trước đã thành công, nhưng **cũng có thể do DN sai, ACL che dữ liệu hoặc một tác nhân khác xóa entry**.

Chỉ coi Delete là “đã hoàn tất” khi chính sách nghiệp vụ cho phép trạng thái đích là entry vắng và việc đối soát đã đủ tin cậy; không biến mọi code 32 thành bằng chứng thực hiện thành công.

### 7.3. Readback cũng có giới hạn

- Đọc từ replica có thể chịu độ trễ so với server ghi.
- ACL của tài khoản đọc có thể không cho thấy thuộc tính cần xác minh.
- Dữ liệu được trả về đúng có thể do một client khác sửa.
- Sau mất kết nối, chính thao tác readback cũng có thể thất bại.

Vì vậy workflow cần trạng thái **UNKNOWN/PENDING_RECONCILIATION** thay vì ép mọi lỗi thành “SUCCESS” hoặc “FAILED”.

## 8. Atomicity khác isolation: ngăn lost update

Một Modify request là nguyên tử nhưng vẫn có thể **ghi đè cập nhật mới của người khác**.

~~~text
T1 Client A đọc: telephoneNumber = [P1]
T2 Client B thêm P2
T3 Client A REPLACE bằng [P1, P3]

Kết quả có thể là [P1, P3]; giá trị P2 bị mất.
~~~

Đây là **lost update**, không phải server commit một Modify request dở dang.

### 8.1. Giảm nguy cơ lost update

- Muốn thêm một giá trị đa trị, ưu tiên **ADD giá trị cụ thể** hơn là đọc tập rồi REPLACE.
- Muốn bỏ một giá trị, ưu tiên **REMOVE giá trị cụ thể** nếu server/schema cho phép.
- Không thay cả tập giá trị chỉ vì client gửi một trường cập nhật.
- Khi nghiệp vụ yêu cầu “chỉ sửa nếu entry còn ở phiên bản đã đọc”, cân nhắc **LDAP Assertion Control (RFC 4528)** hoặc cơ chế điều kiện tương ứng **nếu LDAP server và client hỗ trợ**.
- Không mặc định `modifyTimestamp` là ETag hoàn hảo: phải xét quyền đọc, độ phân giải, replication và matching rules.

Assertion Control là điều kiện được kiểm tra tại server cùng thao tác, **không tự có** khi ứng dụng dùng `DirContextAdapter` hoặc `LdapQueryBuilder`. Cách truyền control phụ thuộc vào client API và server, phải kiểm thử tích hợp theo đúng phiên bản sử dụng.

### 8.2. Ba tính chất thường bị đánh đồng

| Khái niệm | Một LDAP Modify trên một entry | Quy trình nhiều bước |
| --- | --- | --- |
| **Atomicity** | Có cho danh sách Modify trong request | Không có mặc định |
| **Isolation/khả năng chống lost update** | Không tự bảo vệ chuỗi đọc-rồi-ghi ở ứng dụng | Cần điều kiện đồng thời, version hoặc policy |
| **Durability** | Theo hợp đồng và cấu hình server sau success | Cần xét từng hệ thống, replication và lưu trữ |

Đừng dùng từ **transaction** nếu chưa xác định chính xác tài nguyên và ranh giới mà nó bao phủ.


## 9. Thiết kế cập nhật/xóa nhiều bước như một workflow có trạng thái

Khi nghiệp vụ phải sửa nhiều entry hoặc nhiều hệ thống, thay vì giả vờ có một transaction, hãy mô tả **các bước có thể quan sát, thử lại và đối soát**.

Ví dụ quy trình deprovisioning một nhân viên:

~~~text
Yêu cầu được ủy quyền
         |
         v
VALIDATE_REQUEST
         |
         v
DISABLE_ACCESS          (theo cơ chế được directory hỗ trợ)
         |
         v
REMOVE_GROUP_LINKS      (có thể nhiều group, từng checkpoint)
         |
         v
DELETE_USER             (LDAP Delete theo chính sách)
         |
         v
SYNC_APPLICATION_DB     (cập nhật trạng thái bên ngoài)
         |
         v
COMPLETE
~~~

**Đây là thứ tự minh họa**, không phải thứ tự đúng cho mọi hệ thống. Trong hạ tầng cụ thể, tham chiếu nhóm, policy vô hiệu hóa, audit và đặc tính plugin referential integrity có thể yêu cầu thứ tự khác. Cần cùng đội IAM/LDAP xác định trước khi triển khai.

### 9.1. Vì sao nên có bước “vô hiệu hóa trước khi xóa”?

Nếu phải xóa user khỏi nhiều nhóm, quá trình có thể kéo dài. Với một cơ chế **disable account thật sự được server xác nhận và có hiệu lực đối với authentication**, hệ thống có thể giảm rủi ro người dùng tiếp tục đăng nhập trong khi deprovisioning đang diễn ra.

**Không được coi việc ghi `description=disabled` là biện pháp khóa đăng nhập**, trừ khi hạ tầng xác định rõ nó được dùng trong chính sách xác thực. Các directory có cơ chế khóa/vô hiệu hóa tài khoản khác nhau; cần dùng tính năng được vendor/schema và chính sách bảo mật hỗ trợ.

Nếu bước disable thất bại, có thể dừng quy trình và báo vận hành thay vì tiếp tục những thao tác nhạy cảm.

### 9.2. Lưu checkpoint bền vững

Mỗi công việc cần có một bản ghi trạng thái riêng, ví dụ:

| Trường workflow | Ý nghĩa |
| --- | --- |
| `operationId` | Định danh ổn định cho yêu cầu deprovision |
| `targetDn` | DN đã được xác minh, lưu/log theo chính sách dữ liệu |
| `requestedBy` | Danh tính gọi nghiệp vụ được ủy quyền |
| `phase` | VALIDATED, DISABLED, GROUPS_UPDATED, DELETED, COMPLETE |
| `perStepStatus` | PENDING, SUCCEEDED, FAILED, UNKNOWN |
| `attempts` | Số lần thử có giới hạn |
| `lastErrorCategory` | VALIDATION, ACL, SCHEMA, CONFLICT, NETWORK, UNKNOWN |
| `updatedAt` | Thời điểm phục vụ vận hành/đối soát |

Nên lưu tiến độ vào kho bền vững trước khi bước tiếp theo bắt đầu và ghi kết quả khi có bằng chứng. Trường hợp response mất thì lưu **UNKNOWN**, không tự gán **FAILED**.

**Đừng chỉ lưu biến trạng thái trong RAM**: nếu process chết giữa bước thứ ba, bản ghi bền vững giúp một worker khác tiếp tục đối soát thay vì xóa nhầm hoặc lặp lại vô hạn.

### 9.3. Trạng thái trung gian phải có ý nghĩa bảo mật

Trạng thái **DISABLED** có thể là một điểm dừng an toàn hơn trạng thái “một nửa group đã được gỡ nhưng tài khoản vẫn đăng nhập được”, nếu cơ chế vô hiệu hóa thực sự có hiệu lực. Trạng thái **GROUPS_PARTIAL** cần được hiển thị rõ để người vận hành biết dữ liệu nhóm có thể chưa đồng bộ.

Không được đánh dấu **COMPLETE** chỉ vì lệnh `unbind` trả thành công trong khi các bước SQL, group hoặc hệ thống phụ thuộc vẫn còn treo.

## 10. Saga và bù trừ: hữu ích nhưng không phải rollback hoàn hảo

Một **saga** là chuỗi thao tác độc lập, mỗi bước có kết quả và có thể có **compensating action** để phục hồi một phần trạng thái nghiệp vụ khi bước sau thất bại.

Ví dụ một workflow:

| Bước | Hành động | Khi lỗi sau bước này |
| --- | --- | --- |
| 1 | Xác minh yêu cầu và target DN | Dừng, chưa thay dữ liệu |
| 2 | Vô hiệu hóa tài khoản theo policy server | Giữ trạng thái disable nếu ưu tiên an toàn; cảnh báo |
| 3 | Gỡ membership từng group | Đối soát nhóm đã xử lý, retry phần còn thiếu |
| 4 | Xóa user theo chính sách | Nếu Delete thất bại, giữ checkpoint và kiểm tra trạng thái |
| 5 | Đồng bộ SQL/tác vụ khác | Retry riêng; không tự phục hồi user chỉ để làm SQL “thành công” |

### 10.1. Bù trừ không đồng nghĩa phép đảo đối xứng

Có những thao tác tương đối dễ đảo khi được kiểm soát: ví dụ một giá trị `description` được thêm rồi cần loại bỏ. Nhưng “đảo” vẫn có thể thất bại vì concurrency, ACL hoặc dữ liệu thay đổi.

**Delete rồi Add lại** thường không khôi phục hoàn toàn:

- Entry UUID và timestamps do server quản lý có thể khác.
- Password hashes/policy/authentication state có thể không được sao lưu hoặc không thể tái tạo.
- Group references, ACL, external IDs và workflow phụ thuộc có thể đã đổi.
- Dữ liệu audit hoặc hiệu ứng plugin không nhất thiết được hoàn tác.

Do đó, **compensation là một thao tác nghiệp vụ được thiết kế**, không phải sự bảo đảm ACID rollback. Đôi khi cách an toàn là **giữ account disabled** và mở sự cố vận hành, thay vì tạo lại một tài khoản có thể được cấp quyền nhầm.

### 10.2. Không sao lưu mù quáng toàn bộ entry nhạy cảm

Nếu cần bản chụp phục vụ rollback/đối soát, chỉ lưu **thuộc tính thật sự cần thiết** trong kho có mã hóa, giới hạn truy cập và retention rõ ràng. Không lưu plaintext password, token, toàn bộ chứng chỉ hoặc hash nhạy cảm vào log/workflow chỉ vì muốn “hoàn nguyên mọi thứ”.

Khi yêu cầu khôi phục dữ liệu directory ở quy mô lớn, nên dùng quy trình backup/restore của quản trị viên thay vì một script tự dựng lại hàng nghìn entry.

## 11. Một thiết kế điều phối không che lỗi: mã Java minh họa

Không có transaction chung được giả định trong service. Thay vào đó, một giao diện bền vững lưu tiến độ theo từng bước:

~~~java
public enum DeprovisionPhase {
    VALIDATED,
    ACCESS_DISABLED,
    GROUP_LINKS_UPDATED,
    LDAP_ENTRY_DELETED,
    APPLICATION_SYNCED,
    COMPLETE,
    NEEDS_RECONCILIATION
}
~~~

Một tập hợp hợp đồng nghiệp vụ:

~~~java
import javax.naming.Name;

public interface DeprovisionJournal {
    // Lưu tiến độ bền vững, gắn với operationId;
    // cập nhật có điều kiện để tránh hai worker xử lý cùng operation.
    void checkpoint(String operationId, DeprovisionPhase phase);

    void markUnknown(String operationId, String step);
}

public interface DirectoryAccessPolicy {
    // Phải thực sự chặn xác thực theo cơ chế của LDAP server.
    void disableUser(Name dn);

    // Gỡ tham chiếu thành viên theo model nhóm thực tế,
    // với checkpoint/đối soát cho từng group.
    void removeGroupReferences(Name dn);

    // Xác minh trạng thái đọc lại khi response không chắc chắn.
    boolean entryDefinitelyAbsent(Name dn);
}
~~~

Service **minh họa thứ tự và giới hạn**, không phải một thư viện transaction hoàn chỉnh:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;

public class DeprovisionCoordinator {
    private final LdapTemplate ldapTemplate;
    private final DirectoryAccessPolicy accessPolicy;
    private final DeprovisionJournal journal;

    public DeprovisionCoordinator(
            LdapTemplate ldapTemplate,
            DirectoryAccessPolicy accessPolicy,
            DeprovisionJournal journal) {
        this.ldapTemplate = ldapTemplate;
        this.accessPolicy = accessPolicy;
        this.journal = journal;
    }

    public void execute(String operationId, Name dn) {
        // Giả định đã xác thực/ủy quyền và khóa xử lý operationId,
        // đã kiểm tra DN thuộc OU được phép.
        try {
            journal.checkpoint(
                    operationId, DeprovisionPhase.VALIDATED);

            accessPolicy.disableUser(dn);
            journal.checkpoint(
                    operationId, DeprovisionPhase.ACCESS_DISABLED);

            accessPolicy.removeGroupReferences(dn);
            journal.checkpoint(
                    operationId, DeprovisionPhase.GROUP_LINKS_UPDATED);

            ldapTemplate.unbind(dn);
            journal.checkpoint(
                    operationId, DeprovisionPhase.LDAP_ENTRY_DELETED);

            // Bước đồng bộ ứng dụng khác phải được thực hiện riêng
            // và checkpoint khi có bằng chứng thành công.
        } catch (RuntimeException failure) {
            journal.markUnknown(operationId, "current-step");
            throw failure;
        }
    }
}
~~~

**Các giới hạn cần nhìn nhận thẳng:**

1. Phần `DeprovisionJournal` là interface cần implementation **bền vững**, không phải object in-memory.
2. Đoạn code đánh dấu unknown cho mọi exception để **không tuyên bố sai rằng bước thất bại chưa làm gì**. Một triển khai production nên **phân loại lỗi rõ**: error server xác nhận và timeout sau khi gửi không giống nhau.
3. Ngay cả khi `checkpoint` được gọi sau lệnh LDAP, nếu process chết **giữa success và checkpoint**, trạng thái journal vẫn cũ. Worker chạy lại phải **đối soát** trước khi gửi thao tác lần nữa.
4. `removeGroupReferences` có thể gồm nhiều LDAP request. Nó phải tự lưu checkpoint từng group và xử lý retry/idempotency.
5. Service chưa có phần `APPLICATION_SYNCED` và `COMPLETE`. **Không** coi nó là một workflow đã hoàn thiện; những phần còn lại cần thiết kế theo hệ thống thực tế.
6. Không coi rollback tự động sẽ xảy ra chỉ vì tầng service được gắn `@Transactional`. Annotation của một transaction manager SQL không tự bao trùm LDAP server.

Ví dụ giúp đặt đúng **ranh giới trách nhiệm**, không nên copy vào production mà thiếu transaction journal, locking, authorization, lifecycle, mã lỗi và kiểm thử.

### 11.1. Mỗi thao tác nên có tiền điều kiện và hậu điều kiện

Ví dụ với bước Delete:

- **Tiền điều kiện:** yêu cầu hợp lệ; entry DN được xác minh là đúng người; quyền Delete phù hợp; quy trình đã đạt các checkpoint bắt buộc.
- **Hậu điều kiện:** entry không còn trong nguồn ghi theo chính sách xác minh; công việc được đánh dấu DELETED.
- **Lỗi từ chối:** giữ checkpoint trước và ghi nguyên nhân.
- **Timeout không rõ kết quả:** đánh dấu UNKNOWN, đọc lại/truy nguyên request trước khi retry.

Một bước “có thể retry” phải được thiết kế để kiểm tra trạng thái đích, không chỉ gọi đi gọi lại cùng API.

## 12. Đối chiếu một Modify nguyên tử bằng LDIF

Một tệp `update-alice.ldif` thể hiện nhiều thay đổi **trong cùng một Modify request**:

~~~ldif
dn: uid=alice,ou=people,dc=example,dc=org
changetype: modify
replace: mail
mail: alice.new@example.org
-
add: telephoneNumber
telephoneNumber: +84 28 3333 4444
-
delete: description
description: onboarding
~~~

Dấu `-` phân tách từng phép sửa. Chúng thuộc cùng record `changetype: modify` cho một DN.

Chạy **trên LDAP test server** bằng tài khoản editor được cấp quyền:

~~~bash
ldapmodify -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-editor,ou=system,dc=example,dc=org" -W \
  -f update-alice.ldif
~~~

`-W` yêu cầu nhập mật khẩu tương tác. Không đưa credentials vào command-line history hoặc log. Cấu hình LDAPS phải xác minh chứng chỉ và hostname.

### 12.1. Thử lỗi có chủ đích để kiểm tra atomicity

Chuẩn bị entry riêng cho test có `mail: before@example.org` và **không có** `description: missing-note`.

LDIF thử nghiệm:

~~~ldif
dn: uid=atomic-test,ou=people,dc=example,dc=org
changetype: modify
replace: mail
mail: after@example.org
-
delete: description
description: missing-note
~~~

Kết quả kỳ vọng với LDAP Modify theo chuẩn: bước delete giá trị không tồn tại khiến request bị từ chối; **mail phải còn** `before@example.org`. Nếu thấy mail mới, cần xem lại cách gửi request, có phải hai record/two requests khác nhau, có tác nhân khác sửa hoặc server/extension có hành vi khác mong đợi.

**Không** chạy một bài test có chủ đích gây lỗi trên entry sản xuất.

### 12.2. Đọc lại bằng ldapsearch

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "uid=atomic-test,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" dn mail description telephoneNumber
~~~

Khi dùng `ContextSource.base = dc=example,dc=org`, Java truyền DN tương đối `uid=atomic-test,ou=people`, còn tham số `-b` của ldapsearch thường dùng DN đầy đủ.

## 13. Kiểm thử tích hợp: chứng minh “không có trạng thái nửa chừng”

Unit test có thể xác minh một method Java gọi `modifyAttributes` đúng **một lần** với mảng ba phần tử. Nhưng chỉ integration test với LDAP server thật hoặc container/directory test mới chứng minh schema, ACL và ngữ nghĩa thực thi.

### 13.1. Ví dụ JUnit 5: request lỗi phải giữ nguyên mail

Giả sử test fixture cung cấp `LdapTemplate` trỏ đến server thử nghiệm, entry `atomic-test` đã tồn tại, có `objectClass=inetOrgPerson` và `mail: before@example.org`. Entry đó **không chứa** `description: missing-note`.

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.*;

class AtomicModifyIntegrationTest {
    private final LdapTemplate template;

    // Fixture/Spring Test cần cung cấp template.
    AtomicModifyIntegrationTest(LdapTemplate template) {
        this.template = template;
    }

    @Test
    void invalidSecondChangeCannotPartiallyReplaceMail() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "atomic-test")
                .build();

        ModificationItem[] changes = {
            new ModificationItem(
                    DirContext.REPLACE_ATTRIBUTE,
                    new BasicAttribute("mail", "after@example.org")
            ),
            new ModificationItem(
                    DirContext.REMOVE_ATTRIBUTE,
                    new BasicAttribute("description", "missing-note")
            )
        };

        assertThrows(RuntimeException.class,
                () -> template.modifyAttributes(dn, changes));

        String mailAfter = template.lookup(
                dn,
                (AttributesMapper<String>) attrs ->
                        String.valueOf(attrs.get("mail").get())
        );

        assertEquals("before@example.org", mailAfter);
    }
}
~~~

**Lưu ý kiểm thử:** `assertThrows(RuntimeException.class)` trong khung trên chỉ minh họa rằng request bị từ chối qua hệ ngoại lệ runtime của Spring LDAP. Trong code dự án, nên assert **loại ngoại lệ/mã LDAP phù hợp** chứ không bắt mọi exception. Nếu failure xuất phát từ kết nối mất response, test chưa chứng minh atomicity; phải có test riêng xử lý trạng thái UNKNOWN.

Ví dụ cần test fixture thật, setup/teardown, cấu hình ACL/schema và bảo đảm mail ban đầu đã được khởi tạo. Không nên dùng constructor JUnit dạng trên mà không cấu hình injection tương ứng.

### 13.2. Test đọc lại toàn bộ các thuộc tính liên quan

Khi request **thành công**, xác minh:

- `mail` chứa giá trị mới.
- `telephoneNumber` có cả số cũ và số mới.
- `description` vẫn còn `active` và không còn `onboarding`.
- `uid`, `cn`, `sn` không bị thay đổi.
- Test không dựa vào thứ tự giá trị của thuộc tính đa trị.

Với JNDI, `Attribute.get()` chỉ đọc một giá trị; nếu cần toàn bộ tập, dùng `Attribute.getAll()` và đóng `NamingEnumeration` đúng cách. Đừng coi kết quả mapper thiếu một thuộc tính là bằng chứng nó đã bị xóa nếu ACL có thể ẩn thuộc tính đó.

### 13.3. Ma trận failure injection

| Ca | Cách tạo điều kiện test | Kết quả mong đợi |
| --- | --- | --- |
| Modify ba thuộc tính thành công | Dữ liệu hợp schema/ACL | Cả ba thay đổi, không chạm trường khác |
| Phần tử Modify thứ hai sai | Xóa một giá trị không tồn tại | Không có thay đổi một phần của request |
| Vi phạm MUST | Cố xóa `sn` của `person` | Request từ chối; entry còn hợp schema |
| Thiếu quyền sửa một thuộc tính | Editor có ACL hạn chế | Cả request Modify bị từ chối |
| Hai Modify độc lập, request sau thất bại | Gửi hai lần riêng | Request trước có thể đã commit |
| Delete entry không con | DN test hợp lệ, ACL Delete cho phép | Entry đích bị xóa |
| Delete OU còn child | Parent chứa entry con | Thường từ chối với code 66 |
| Delete nhiều child, lỗi ở giữa | Test danh sách nhiều DN | Workflow cần checkpoint và đối soát |
| Mất response sau Modify | Fault injection network | Outcome UNKNOWN, không retry mù |
| Mất response sau Delete | Fault injection network | Đọc lại và xác minh ownership |
| Update đồng thời | Hai client đọc rồi sửa | Xử lý mất cập nhật theo policy |
| LDAP + SQL, SQL lỗi sau LDAP success | Giả lập SQL failure | Journal còn bước SQL pending, không gọi toàn bộ “rolled back” |
| Reader cố sửa/xóa | Dùng account read-only | Server từ chối, không tự nâng quyền |
| TLS sai | Cert/hostname không hợp lệ | Kết nối thất bại an toàn |

Hãy dùng DN duy nhất theo test, không thao tác tài khoản thật. Khi test xóa, chỉ xóa entry **do test tạo và sở hữu**. Cần phân biệt lỗi server được nhận rõ ràng với lỗi không chắc request đã gửi đến server chưa.

## 14. Cấu hình ContextSource, TLS và quyền tối thiểu

Một ví dụ Spring Java Config dùng thông tin từ môi trường:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConfiguration {
    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
~~~

~~~yaml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

`app.ldap.*` là property minh họa do ứng dụng tự định nghĩa. Nếu dùng Spring Boot auto-configuration, có các thuộc tính `spring.ldap.*` tương ứng; tránh tạo bean trùng nhau mà không kiểm soát cái nào được inject.

### 14.1. Quyền hạn ghi xóa

Tài khoản reader chỉ cần tra cứu; tài khoản editor/provisioner chỉ nên được sửa hoặc xóa entry trong OU được phê duyệt. Dùng admin account cho mọi thao tác khiến tác động của lỗi lập trình lớn hơn nhiều.

`ContextSource.getReadWriteContext()` không tự cấp quyền. **ACL do LDAP server thực thi**. Đặc biệt, Delete user và sửa các group ở OU khác nhau có thể yêu cầu các quyền khác nhau; giải pháp không nên chỉ là “cấp quyền admin” mà phải thiết kế workflow và ACL theo từng bước.

### 14.2. TLS, pooling và trạng thái kết nối

- Dùng **LDAPS** với xác minh chuỗi chứng chỉ/hostname hoặc **StartTLS** được kích hoạt thật trước khi simple bind.
- URL `ldap://` không tự bật StartTLS; không truyền credentials trên kết nối chưa bảo vệ.
- Mật khẩu bind lấy từ secret manager/biến môi trường, không hard-code hoặc log.
- Pooling có thể cải thiện hiệu năng, **không** tạo atomicity hoặc thay ACL.
- Với nhiều bind identity/StartTLS, phải kiểm tra tương thích pool, cách trả context và không tái sử dụng sai danh tính.
- Khi lấy `DirContext` trực tiếp phải đóng nó đúng cách; `LdapTemplate` thường quản lý lifecycle cho các thao tác của template.

Một operation thành công nhưng response mất vì pool/socket lỗi cần được xử lý như **UNKNOWN**, không được coi là chắc chắn thất bại.

## 15. Những phản mẫu cần tránh

| Phản mẫu | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Ba lời gọi Modify riêng cho một cập nhật cần nguyên tử | Có thể commit dở dang | Gộp một `ModificationItem[]` |
| REPLACE cả thuộc tính đa trị từ dữ liệu form một phần | Làm mất giá trị không nhìn thấy | ADD/REMOVE giá trị cụ thể hoặc kiểm soát phiên bản |
| Catch mọi exception và trả success | Che lỗi ACL/schema/network | Phân loại kết quả và trạng thái UNKNOWN |
| Retry ADD/REMOVE/DELETE ngay sau timeout | Có thể gây duplicate hoặc lỗi giả | Readback và đối soát trước retry |
| Dùng `@Transactional` SQL để mong LDAP rollback | Không có distributed transaction tự động | Journal/saga/compensation rõ ràng |
| Xóa LDAP trước, bỏ qua nhóm và hệ thống phụ thuộc | Tham chiếu mồ côi hoặc lệch trạng thái | Quy trình deprovision có checkpoint |
| Xóa subtree bằng vòng lặp không theo dõi | Xóa một phần khi lỗi giữa chừng | Kiểm kê và lưu tiến độ từng entry |
| “Rollback” Delete bằng Add lại mọi thuộc tính | Không khôi phục chắc UUID/password/metadata | Backup/restore theo chính sách, staged delete |
| Log toàn bộ entry hoặc error diagnostic | Lộ dữ liệu cá nhân, DN và secrets | Redaction, log tối thiểu, audit kiểm soát |
| Khẳng định readback từ replica chứng minh commit mới nhất | Có thể bị replication lag | Chọn endpoint và mức nhất quán phù hợp |

## 16. Bài thực hành có hướng dẫn

**Bối cảnh:** ứng dụng Spring LDAP cần đổi hồ sơ của `uid=training-01` và sau đó có một yêu cầu deprovision liên quan đến group, nhưng phải tránh báo “thành công” khi còn trạng thái chưa xử lý.

1. **Chuẩn bị directory test** có entry `training-01` với `mail`, hai giá trị `description` và một giá trị `telephoneNumber`; dùng LDAPS đã xác minh chứng chỉ.
2. **Thực hành Modify đơn:** tạo ba `ModificationItem` REPLACE/ADD/REMOVE và gửi qua **một** `ldapTemplate.modifyAttributes(dn, changes)`.
3. **Đọc lại:** so sánh toàn bộ tập giá trị, không dựa vào thứ tự. Kiểm tra các thuộc tính không liên quan vẫn giữ nguyên.
4. **Tạo lỗi có chủ đích:** yêu cầu REMOVE giá trị `description` không tồn tại; quan sát server từ chối và xác minh mail cũng không đổi.
5. **So sánh ba request:** gửi ba thay đổi thành ba Modify khác nhau, làm request cuối thất bại. Phân tích vì sao hai request đầu có thể đã commit.
6. **Thử schema/ACL:** cố xóa `sn` bắt buộc và dùng reader identity để Modify; giải thích các nhóm lỗi.
7. **Thử Delete:** xóa một entry riêng do test tạo; thử xóa OU còn entry con trong môi trường test và ghi lại lỗi.
8. **Thiết kế workflow:** viết các phase VALIDATED, DISABLED, GROUPS_UPDATED, DELETED, SYNCED, COMPLETE và UNKNOWN; giải thích điều kiện vào/ra mỗi phase.
9. **Mô phỏng timeout:** xem trạng thái khi server có thể đã nhận request nhưng client mất response. Viết kế hoạch readback và retry có giới hạn.
10. **Đánh giá concurrent update:** hai client cùng sửa phone, so sánh REPLACE toàn tập với ADD giá trị cụ thể.
11. **Kiểm tra ranh giới hệ thống:** giả lập SQL lỗi sau khi LDAP Delete thành công; xác minh journal giữ bước SQL chưa hoàn thành, không tuyên bố rollback LDAP.
12. **Dọn dữ liệu test** theo quyền được cấp, chỉ xóa entry mà bài test tạo; bảo vệ secrets và không ghi toàn bộ thông tin cá nhân vào log.

### Câu hỏi tự kiểm tra

1. Vì sao một `ModificationItem[]` với ba phần tử khác với ba lời gọi `modifyAttributes`?
2. Tính nguyên tử của LDAP Modify bảo vệ những gì, và không bảo vệ những gì?
3. Tại sao `REPLACE_ATTRIBUTE` trên thuộc tính đa trị có thể làm mất dữ liệu dù request vẫn nguyên tử?
4. Một LDAP Delete thông thường có xóa nguyên tử toàn subtree không?
5. Vì sao xóa user rồi bỏ group membership có thể để lại trạng thái không nhất quán?
6. Nếu một Modify request bị server từ chối rõ ràng, các phần tử trước đó của **cùng request** có được phép ở trạng thái đã áp dụng không?
7. Khi timeout sau khi gửi Delete, tại sao không được khẳng định server chưa xóa entry?
8. Vì sao retry `ADD_ATTRIBUTE` có thể trả lỗi trùng sau khi response lần đầu bị mất?
9. Readback ở replica khác có thể gặp vấn đề gì?
10. Khi nào cần Assertion Control hoặc chiến lược điều kiện đồng thời?
11. Saga/compensation khác ACID rollback thế nào?
12. Vì sao Add lại entry vừa Delete không luôn khôi phục đúng trạng thái ban đầu?
13. `@Transactional` của database SQL có bao trùm LDAP server không, nếu không có hạ tầng giao dịch được tích hợp rõ ràng?
14. Vì sao tài khoản editor cần quyền tối thiểu ngay cả khi validation đầu vào tốt?
15. Test nào chứng minh nhiều thao tác trong **một** Modify request không commit dở dang?

## 17. Tổng kết

Để **thao tác Modify/Delete thất bại không để trạng thái nửa chừng**, trước hết phải hiểu phạm vi bảo đảm: **LDAP Modify có tính nguyên tử cho danh sách thay đổi của một entry trong một request; LDAP Delete thông thường tác động lên một entry**. Nhiều request, nhiều entry và nhiều hệ thống **không tự có transaction chung**. Spring LDAP giúp gộp thay đổi bằng `LdapTemplate.modifyAttributes(dn, ModificationItem[])` hoặc `DirContextAdapter`, nhưng không tự ngăn lost update hay biến xóa nhiều bước thành thao tác nguyên tử.

Với quy trình phức tạp, cần thiết kế **checkpoint bền vững, idempotency, nhận diện kết quả UNKNOWN, đối soát, quyền tối thiểu và bù trừ theo nghiệp vụ**. Đặc biệt, khi response mất sau khi gửi yêu cầu, không retry mù quáng. Xác minh TLS, ACL/schema, đặc tính group references và kết quả thực tế qua kiểm thử tích hợp giúp giữ cho dữ liệu LDAP và những hệ thống phụ thuộc nhất quán, an toàn và có thể phục hồi khi xảy ra sự cố.
