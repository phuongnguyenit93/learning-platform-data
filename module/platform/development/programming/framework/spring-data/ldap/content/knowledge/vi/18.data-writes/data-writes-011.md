# Kiểm tra ngữ nghĩa ghi lặp lại và trạng thái khi yêu cầu thất bại

Trong **Spring Data LDAP**, một thao tác ghi thường được gọi qua repository ODM hoặc `LdapTemplate`. Ví dụ: tạo người dùng, sửa email, thêm membership, xóa entry hoặc đổi DN. Ứng dụng production phải xử lý một tình huống khó: client đã gửi yêu cầu tới LDAP server nhưng không nhận được response.

Một timeout hoặc connection reset **không chứng minh thao tác chưa được thực hiện**. Server có thể đã ghi dữ liệu thành công rồi response bị mất trên đường về. Nếu client gửi lại yêu cầu một cách mù quáng, dữ liệu có thể bị ghi hai lần, bộ đếm tăng hai lần, entry bị xóa nhầm hoặc thao tác rename rơi vào trạng thái khó xác định.

Bài học này tập trung vào ba câu hỏi:

1. Nếu gửi lại cùng một thao tác LDAP, trạng thái directory có giữ nguyên hay thay đổi thêm?
2. Khi request thất bại, làm sao phân biệt thao tác chưa chạy, đã bị từ chối và đã chạy nhưng mất response?
3. Làm thế nào để thiết kế retry, đối soát, transaction bù trừ và kiểm thử sự cố an toàn?

Sau bài học, bạn có thể:

- Phân biệt idempotent operation và non-idempotent operation.
- Hiểu tính nguyên tử của một LDAP operation và giới hạn giữa nhiều operation.
- Đánh giá Add, Modify, Delete, ModifyDN và các thao tác Spring LDAP.
- Xử lý trạng thái không xác định sau timeout hoặc mất kết nối.
- Thiết kế idempotency key, operation marker và reconciliation.
- Dùng Assertion Control để cập nhật có điều kiện khi server hỗ trợ.
- Hiểu giới hạn của `@Transactional` và transaction bù trừ trong Spring LDAP.
- Viết integration test mô phỏng mất response sau khi server đã ghi.

## 1. Vấn đề: server có thể đã ghi dù client báo lỗi

Giả sử API nhận yêu cầu đổi email nhân viên:

```text
Client                  Application                  LDAP server
  |                         |                              |
  | PUT /people/lan/email   |                              |
  |------------------------>|                              |
  |                         | Modify email                 |
  |                         |----------------------------->|
  |                         |                              |
  |                         |                   Ghi thành công
  |                         |                              |
  |                         |<-----------------------------|
  |                         |       ModifyResponse success |
  |                         X                              |
  |                   Kết nối bị ngắt                       |
  |                                                        |
  |  Client không nhận response                             |
  |<-------------------------------------------------------|
  |                                                        |
  | Retry request?                                          |
  |                                                        |
```

Server đã cập nhật email, nhưng application không biết điều đó vì response không tới được nơi gọi. Nếu application trả lỗi 504 rồi client gửi lại, cùng một yêu cầu có thể được thực hiện lần nữa.

Đây là vấn đề phân tán phổ biến: **kết quả của operation và việc client nhận được response là hai sự kiện khác nhau**.

### 1.1. Bốn trạng thái cần phân biệt

| Trạng thái | Điều đã biết | Hành động |
| --- | --- | --- |
| Chưa gửi | Lỗi xảy ra trước khi request được gửi tới LDAP | Có thể thử lại nếu đầu vào còn hợp lệ |
| Bị từ chối rõ ràng | LDAP trả response với result code lỗi | Xử lý theo mã lỗi; không retry nếu lỗi dữ liệu/quyền |
| Thành công rõ ràng | LDAP trả response success | Ghi nhận operation đã áp dụng |
| Không xác định | Request có thể đã tới server nhưng client không nhận response | Đối soát directory trước khi retry |

Không nên gom mọi exception thành “LDAP thất bại”. Đặc biệt, `CommunicationException` hoặc timeout có thể xảy ra trước, trong hoặc sau khi server xử lý request. Chỉ exception class thường không đủ để xác định operation đã được áp dụng hay chưa.

### 1.2. HTTP timeout không hủy chắc chắn LDAP operation

Khi gateway hoặc client HTTP hết deadline:

- Client có thể ngừng chờ.
- Application có thể nhận tín hiệu đóng kết nối HTTP.
- LDAP operation đã gửi có thể vẫn đang được server xử lý.
- Application thread có thể chỉ phát hiện timeout sau khi operation kết thúc hoặc connection bị lỗi.

Vì vậy, không được suy ra rằng HTTP 504 đồng nghĩa LDAP chưa thay đổi dữ liệu. Cần có operation ID hoặc cơ chế tra cứu trạng thái để caller biết cách tiếp tục.

### 1.3. Exactly-once không tự có từ retry

Retry chỉ gửi lại request. Nó không tự bảo đảm request chỉ được áp dụng đúng một lần.

| Cơ chế | Bảo đảm |
| --- | --- |
| Gửi một lần | Tránh retry duplicate nhưng có thể bỏ lỡ operation nếu request chưa tới server |
| Retry vô hạn | Tăng khả năng cuối cùng request được xử lý, nhưng có thể lặp side effect |
| Retry có giới hạn | Kiểm soát tải và thời gian; vẫn cần reconciliation |
| Idempotency key + lưu trạng thái | Nhận diện các lần gọi cùng một operation nếu hệ thống ghi nhận key đúng cách |
| Conditional update/assertion | Ngăn update nếu trạng thái hiện tại không còn thỏa điều kiện |

Không có idempotency key nào tự có hiệu lực trong LDAP. Ứng dụng phải lưu hoặc đưa key vào dữ liệu directory theo một thiết kế có thể kiểm tra.

## 2. Tính nguyên tử của LDAP operation

LDAP không cung cấp transaction đa entry mặc định, nhưng từng update operation theo RFC 4511 có tính nguyên tử ở phạm vi operation.

### 2.1. Một ModifyRequest có nhiều thay đổi vẫn là một operation

Một LDAP ModifyRequest có thể chứa nhiều change:

```text
ModifyRequest
  object: uid=lan,ou=people,dc=example,dc=org
  changes:
    1. REPLACE mail = lan.new@example.org
    2. REPLACE telephoneNumber = +84-28-5555-0101
    3. ADD description = profile-reviewed
```

Theo RFC 4511, server phải thực hiện toàn bộ danh sách change theo thứ tự đã gửi như **một thao tác nguyên tử**:

- Nếu ModifyResponse trả lỗi, client có thể kỳ vọng không change nào trong request được áp dụng.
- Nếu ModifyResponse trả success, toàn bộ change đã được áp dụng.
- Nếu client không nhận được ModifyResponse, client không thể xác định change đã được áp dụng hay chưa.

Tính nguyên tử này chỉ áp dụng cho **một ModifyRequest trên một entry**. Hai ModifyRequest riêng biệt hoặc ModifyRequest trên hai entry không tự trở thành một transaction.

### 2.2. Nhiều operation không nguyên tử cùng nhau

Ví dụ quy trình tạo nhân viên và thêm vào nhóm:

```text
1. Add uid=lan,ou=people,...
2. Modify cn=engineering,ou=groups,...
   ADD member: uid=lan,ou=people,...
```

Nếu bước 1 thành công và bước 2 thất bại, entry nhân viên đã tồn tại nhưng membership chưa được thêm. LDAP không tự rollback bước 1.

Ứng dụng cần:

- Ghi lại từng bước và trạng thái.
- Có thể tiếp tục bước còn thiếu.
- Hoặc thực hiện compensating action nếu nghiệp vụ cho phép.
- Có reconciliation để tìm trạng thái dở dang sau crash/restart.

### 2.3. So sánh phạm vi nguyên tử

| Phạm vi | Nguyên tử mặc định? | Ghi chú |
| --- | --- | --- |
| Một AddRequest | Có, trong phạm vi tạo entry | Entry được tạo hoặc operation thất bại |
| Một ModifyRequest với nhiều ModificationItem | Có | Toàn bộ danh sách change là một operation |
| Một DeleteRequest | Có | Xóa một entry lá |
| Một ModifyDNRequest | Có | Đổi tên/di chuyển entry theo một operation |
| Hai ModifyRequest liên tiếp | Không | Operation đầu có thể thành công, operation sau thất bại |
| Add entry rồi thêm membership ở entry khác | Không | Cần workflow hoặc transaction extension |
| Nhiều operation trong Spring compensating transaction | Có cơ chế bù trừ phía client | Không phải transaction server-side thực sự |

## 3. Idempotency: gửi lại mà không tạo thêm thay đổi nghiệp vụ

Một operation là **idempotent** nếu thực hiện một lần hoặc nhiều lần với cùng điều kiện đầu vào tạo ra cùng trạng thái cuối cùng.

Ví dụ:

```text
Đặt mail = lan@example.org

Lần 1: mail -> lan@example.org
Lần 2: mail -> lan@example.org
Lần 3: mail -> lan@example.org

Trạng thái cuối vẫn là:
mail = lan@example.org
```

Ngược lại:

```text
Tăng loginCount thêm 1

Lần 1: 10 -> 11
Lần 2: 11 -> 12
Lần 3: 12 -> 13
```

Gửi lại cùng yêu cầu đã làm thay đổi trạng thái nhiều lần.

### 3.1. Idempotent không có nghĩa response giống nhau

Một request lặp lại có thể nhận result code khác:

- Lần đầu Delete trả success.
- Lần sau Delete trả noSuchObject vì entry đã bị xóa.

Trạng thái mong muốn “entry không còn tồn tại” vẫn đúng. Vì vậy cần phân biệt:

- **Idempotent state:** trạng thái directory cuối cùng không đổi khi lặp.
- **Idempotent response:** response của mọi lần gọi giống nhau.

LDAP không tự cung cấp idempotent response cho mọi thao tác. Ứng dụng có thể thiết kế idempotent state và quy tắc reconciliation để trả kết quả nghiệp vụ nhất quán.

### 3.2. Idempotency phải xét side effect phụ

Một Replace cùng giá trị có thể giữ nguyên giá trị business attribute, nhưng server vẫn có thể cập nhật operational attribute như `modifyTimestamp` hoặc ghi audit event. Vì vậy cần nói rõ idempotency đang xét:

- Trạng thái business attribute.
- Toàn bộ entry bao gồm operational attributes.
- Event/audit side effect.
- Kết quả trả về cho caller.

Đừng tuyên bố “hoàn toàn không có side effect” chỉ vì giá trị field chính không đổi.

## 4. Ngữ nghĩa ghi lặp lại theo từng operation

Các operation LDAP không có cùng tính chất. Bảng sau giúp xác định hành vi trước khi xây retry.

| Operation | Gửi lại sau khi lần đầu có thể thành công | Đánh giá |
| --- | --- | --- |
| Add entry | Thường nhận entryAlreadyExists | Không idempotent về response; cần kiểm tra entry và operation identity |
| Modify REPLACE giá trị cố định | Đưa attribute về cùng giá trị đích | Thường idempotent về business state |
| Modify ADD giá trị | Có thể nhận attributeOrValueExists | Không nên retry mù quáng |
| Modify DELETE giá trị | Có thể nhận noSuchAttribute nếu giá trị đã bị xóa | Cần đọc lại và xác minh trạng thái |
| Modify REPLACE attribute bằng tập rỗng | Xóa attribute nếu tồn tại; bỏ qua nếu không tồn tại | Có thể idempotent về trạng thái |
| Modify-Increment | Mỗi lần gửi tăng thêm một lượng | Không idempotent |
| Delete entry | Lần sau có thể nhận noSuchObject | Có thể idempotent về trạng thái “đã vắng mặt” nếu xác minh đúng entry |
| ModifyDN/rename | DN cũ có thể không còn, DN mới có thể đã tồn tại | Cần kiểm tra cả DN cũ và DN mới |
| Compare/Search/Lookup | Không sửa directory | Thường an toàn để đọc lại, nhưng kết quả có thể đổi do concurrent update |

Result code và exception cụ thể còn phụ thuộc server/provider. Hãy kiểm thử với directory product thực tế.

## 5. Add: không coi entryAlreadyExists là thành công ngay lập tức

LDAP Add chỉ thành công nếu DN đích chưa tồn tại. Nếu request đầu đã tạo entry nhưng response bị mất, lần retry có thể trả `entryAlreadyExists (68)`.

### 5.1. Tình huống duplicate Add

```text
Add uid=lan
     |
     v
Server tạo entry thành công
     |
     v
Response bị mất
     |
     v
Client retry Add uid=lan
     |
     v
entryAlreadyExists
```

Không nên xử lý mọi `entryAlreadyExists` như success. Có thể một request khác đã tạo entry cùng DN với nội dung khác.

### 5.2. Dùng DN ổn định và operation marker

Nếu schema cho phép, có thể đưa một request ID vào entry ngay trong AddRequest:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
applicationOperationId: req-2026-000184
```

Khi retry và nhận entryAlreadyExists:

1. Lookup DN đã định.
2. Đọc applicationOperationId.
3. Nếu marker khớp request ID và dữ liệu cần thiết khớp, có thể kết luận lần Add trước đã áp dụng.
4. Nếu marker khác hoặc dữ liệu khác, trả conflict để xử lý.
5. Nếu không có marker, không thể chứng minh entry hiện có do request trước tạo; cần quy tắc nghiệp vụ riêng.

Attribute marker phải được directory schema cho phép, có ACL phù hợp và được giữ đủ lâu để xử lý retry trễ. Nếu không thể thêm attribute tùy chỉnh, có thể dùng operation ledger bền vững ở tầng ứng dụng, nhưng phải thiết kế reconciliation vì ledger và LDAP không có transaction chung mặc định.

### 5.3. Không so sánh mỗi DN

DN chỉ xác định vị trí entry. DN tồn tại không chứng minh nội dung của entry là kết quả của request hiện tại.

Ví dụ hai request cùng tạo:

```text
uid=lan,ou=people,dc=example,dc=org
```

Request A muốn mail `lan@example.org`; request B muốn mail `lan.contractor@example.org`. Khi A nhận entryAlreadyExists, không thể tự kết luận A đã thành công chỉ vì DN tồn tại.

Hãy so sánh operation ID, business key, version và các attribute quan trọng.

## 6. Modify: phân biệt ADD, DELETE và REPLACE

LDAP ModifyRequest có danh sách thay đổi. Các kiểu change chuẩn gồm:

- `ADD_ATTRIBUTE`: thêm giá trị vào attribute.
- `REMOVE_ATTRIBUTE`: xóa giá trị hoặc toàn bộ attribute.
- `REPLACE_ATTRIBUTE`: thay toàn bộ giá trị hiện có bằng tập giá trị mới.

### 6.1. REPLACE giá trị đích thường phù hợp với retry

Ví dụ:

```java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ModificationItem replaceMail = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "lan@example.org"));

ldapTemplate.modifyAttributes(
        "uid=lan,ou=people",
        new ModificationItem[] {replaceMail});
```

Gửi lại cùng REPLACE sẽ đặt attribute mail về cùng giá trị. Đây thường là cách phù hợp khi API biểu diễn yêu cầu theo dạng **desired state**:

```text
Đặt mail thành lan@example.org
```

thay vì command mang tính cộng dồn:

```text
Thêm một email mới
```

Tuy nhiên, Replace toàn bộ attribute đa trị có thể ghi đè giá trị do một client khác vừa thêm. Muốn tránh lost update, cần version/assertion control hoặc quy tắc đồng bộ rõ ràng.

### 6.2. ADD cùng giá trị có thể lỗi khi retry

Ví dụ:

```java
ModificationItem addDescription = new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("description", "profile-reviewed"));
```

Nếu lần đầu đã thêm giá trị, lần sau có thể nhận `attributeOrValueExists (20)`. Đây không nhất thiết là lỗi dữ liệu cuối cùng; nhưng ứng dụng phải đọc lại để xác minh giá trị tồn tại và có đúng operation identity hay không.

Nếu nghiệp vụ chỉ cần “đảm bảo giá trị này tồn tại”, có thể thiết kế theo desired state: đọc giá trị hiện tại, chỉ gửi Add khi chưa có, hoặc dùng assertion control để xử lý điều kiện cạnh tranh. Đọc rồi Add riêng biệt có race condition nếu nhiều client cùng chạy.

### 6.3. DELETE giá trị có thể báo noSuchAttribute khi lặp

Ví dụ:

```java
ModificationItem removeDescription = new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("description", "profile-reviewed"));
```

Nếu lần đầu đã xóa giá trị, lần sau có thể nhận `noSuchAttribute (16)`. Nếu mục tiêu nghiệp vụ là “giá trị không còn tồn tại”, trạng thái hiện tại có thể đã đúng. Nhưng nếu entry không tồn tại hoặc caller không có quyền đọc, không được tự suy luận rằng thao tác trước đã thành công.

### 6.4. Replace với tập rỗng

RFC 4511 quy định Replace không có giá trị sẽ xóa toàn bộ attribute nếu attribute tồn tại; nếu không tồn tại thì bỏ qua. Điều này hữu ích khi đặt trạng thái “attribute không có giá trị”, nhưng cần phân biệt với việc xóa một giá trị cụ thể khỏi attribute đa trị.

### 6.5. Increment không an toàn khi retry

Một số directory hỗ trợ LDAP Modify-Increment theo RFC 4525:

```text
loginCount: 10

INCREMENT loginCount by 1
    -> 11

Retry cùng operation
    -> 12
```

Modify-Increment là extension, không phải mọi server đều hỗ trợ. Server hỗ trợ có thể công bố OID feature `1.3.6.1.1.14` ở root DSE. Dù operation được thực hiện nguyên tử, việc gửi lại cùng increment vẫn làm tăng thêm lần nữa. Cần operation ID, assertion hoặc một thiết kế khác nếu yêu cầu “mỗi request chỉ tăng một lần”.

### 6.6. Một ModifyRequest chứa nhiều change

Nếu một request thay mail, telephoneNumber và description trên cùng entry, hãy gửi trong một ModifyRequest khi chúng thuộc cùng một thay đổi nghiệp vụ:

```java
ModificationItem[] changes = {
    new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", "lan@example.org")),
    new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("telephoneNumber", "+84-28-5555-0101")),
    new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("description", "profile-reviewed"))
};

ldapTemplate.modifyAttributes(
        "uid=lan,ou=people",
        changes);
```

Server áp dụng danh sách này nguyên tử. Nếu response trả lỗi, không change nào được áp dụng; nếu response bị mất, vẫn phải đối soát toàn bộ trạng thái.

## 7. Delete: entry vắng mặt có thể là trạng thái mong muốn

LDAP Delete xóa một entry lá. Nếu request đầu thành công nhưng response bị mất, retry có thể nhận `noSuchObject (32)` vì DN không còn tồn tại.

Nếu API biểu diễn desired state:

```text
Đảm bảo uid=lan không còn tồn tại
```

thì việc DN đã vắng mặt có thể thỏa yêu cầu. Nhưng cần kiểm tra:

- DN có đúng entry mục tiêu không?
- Entry có bị di chuyển sang DN khác không?
- Caller có quyền đọc trạng thái không?
- Đang đọc từ node/replica có dữ liệu mới nhất không?
- Có tombstone hoặc audit marker để xác nhận nguyên nhân xóa không?

Nếu API biểu diễn command:

```text
Xóa đúng entry mà request này sở hữu
```

thì chỉ thấy DN vắng mặt chưa đủ để chứng minh request hiện tại đã xóa entry. Có thể một quản trị viên hoặc request khác đã xóa trước đó.

### 7.1. Delete không phải lúc nào cũng xóa subtree

LDAP Delete chuẩn chỉ xóa entry lá. Nếu entry có subordinate, server có thể từ chối. Một helper xóa recursive trong Spring LDAP có thể thực hiện nhiều thao tác delete theo thứ tự, không phải một DeleteRequest duy nhất. Khi có lỗi giữa chừng, một phần subtree có thể đã bị xóa.

Đối với recursive delete:

- Ghi lại danh sách DN hoặc checkpoint.
- Xác định thứ tự xóa.
- Có chính sách khôi phục/đối soát.
- Không giả định toàn subtree được xóa nguyên tử.

## 8. Rename/ModifyDN: kiểm tra cả DN cũ và DN mới

Một thao tác ModifyDN có thể đổi RDN, chuyển entry sang parent khác hoặc cả hai. Nếu request thành công nhưng response bị mất, retry với DN cũ có thể báo không tìm thấy entry.

Ví dụ:

```text
OLD:
uid=lan,ou=people,dc=example,dc=org

NEW:
uid=lan,ou=former-employees,dc=example,dc=org
```

Sau timeout:

1. Lookup DN cũ.
2. Lookup DN mới.
3. Nếu DN cũ không còn và DN mới tồn tại, kiểm tra entryUUID/business ID/operation marker.
4. Nếu DN mới là đúng entry đã di chuyển, ghi nhận rename đã áp dụng.
5. Nếu DN mới thuộc entry khác, báo conflict.
6. Nếu cả hai cùng tồn tại, xem xét dữ liệu đã được tạo/copy riêng hay chưa; không tự xóa.

### 8.1. Lưu ý về LdapTemplate và ODM update

Spring LDAP có các API:

- `LdapTemplate.rename(oldDn, newDn)` để di chuyển entry.
- `LdapTemplate.update(entity)` để cập nhật entity ODM.
- `LdapTemplate.modifyAttributes(dn, changes)` để gửi modification rõ ràng.

Theo API ODM, khi DN của entity thay đổi, thao tác update có thể được thực hiện bằng một unbind rồi bind ở DN mới. Đây là chuỗi thao tác, không phải một ModifyDNRequest đơn lẻ. Nếu yêu cầu chỉ là rename/move, hãy xem xét dùng `rename(...)` để diễn đạt đúng operation LDAP và đánh giá retry theo ModifyDN semantics.

## 9. Xử lý trạng thái không xác định sau lỗi

Khi client không nhận được response, hãy lưu trạng thái `UNKNOWN` thay vì ghi nhận `FAILED` ngay lập tức.

### 9.1. State machine cho một write request

```text
RECEIVED
   |
   v
IN_PROGRESS
   |
   +------ LDAP success response ------> APPLIED
   |
   +------ LDAP error response --------> REJECTED
   |
   +------ Timeout / connection lost --> UNKNOWN
                                            |
                                            v
                                       RECONCILING
                                         /   |    \
                                        /    |     \
                                  Applied  Not     Conflict
                                           applied
                                    |       |        |
                                    v       v        v
                                 APPLIED  RETRYABLE  MANUAL_REVIEW
                                            |
                                            v
                                         IN_PROGRESS
```

State machine giúp API, job nền và đội vận hành hiểu rõ request đang ở đâu.

### 9.2. Quy trình reconciliation

Khi trạng thái là UNKNOWN:

1. Giữ nguyên operation ID và idempotency key ban đầu.
2. Đọc entry từ authoritative directory endpoint nếu có thể.
3. Kiểm tra DN, business identifier, version và operation marker.
4. So sánh state hiện tại với desired state của request.
5. Nếu đã đúng state và marker xác nhận cùng operation, ghi APPLIED.
6. Nếu state vẫn là state cũ và chứng minh operation chưa áp dụng, có thể retry theo policy.
7. Nếu state thay đổi bởi một operation khác, ghi CONFLICT hoặc MANUAL_REVIEW.
8. Nếu directory vẫn không đọc được, giữ UNKNOWN và tiếp tục xử lý theo deadline/job policy.

Không đọc từ một replica có replication lag rồi kết luận operation chưa được áp dụng. Read-after-write reconciliation cần dùng endpoint có consistency phù hợp.

### 9.3. Không biến mọi lỗi thành retryable

| Lỗi | Kết luận thường gặp | Hướng xử lý |
| --- | --- | --- |
| Invalid DN / filter | Input không hợp lệ | REJECTED; sửa request |
| Invalid credentials | Cấu hình/bind sai | REJECTED hoặc dependency configuration incident |
| Insufficient access rights | ACL không cho phép | REJECTED; sửa quyền nếu đúng |
| Schema violation | Attribute/objectClass không hợp lệ | REJECTED; sửa mapping/schema |
| Entry already exists | DN đã tồn tại | Đọc lại và kiểm tra operation identity |
| No such object | DN không tồn tại | Đọc trạng thái và phân biệt đã xóa/đã di chuyển |
| CommunicationException | Có thể mất kết nối ở bất kỳ thời điểm nào | UNKNOWN nếu request có thể đã gửi |
| Read timeout | Có thể server đã xử lý nhưng response chưa tới | UNKNOWN |
| Pool acquire timeout trước khi gửi operation | Không mượn được context, operation chưa được gọi | Có thể retry sau khi pool phục hồi |
| Assertion failed | Điều kiện version/state không còn đúng | Đọc lại; không retry cùng assertion cũ |

Exception translation của Spring LDAP có thể bọc exception JNDI trong Spring `DataAccessException`. Hãy kiểm tra cause chain và LDAP result code; đừng phân loại chỉ bằng chuỗi message.

## 10. Idempotency key và operation ledger

API có thể nhận một idempotency key để nhận diện cùng một yêu cầu logic qua nhiều lần gửi:

```http
PUT /api/people/lan/email
Idempotency-Key: 7e90e2d4-9a35-4f7d-a4a2-9b1a4b8c10d1
Content-Type: application/json

{
  "email": "lan@example.org"
}
```

Ứng dụng lưu key cùng:

- Principal/tenant sở hữu request.
- Operation type.
- Target DN hoặc business identifier.
- Hash của payload chuẩn hóa.
- Trạng thái operation.
- Thời điểm nhận và thời điểm cập nhật.
- Kết quả đã xác nhận nếu có.

### 10.1. Cùng key, cùng payload

Nếu request thứ hai có cùng key và cùng payload:

- Nếu operation đã APPLIED, trả lại kết quả đã lưu.
- Nếu IN_PROGRESS, trả trạng thái đang xử lý hoặc cho caller tra cứu.
- Nếu UNKNOWN, kích hoạt reconciliation hoặc trả trạng thái chưa xác định.
- Không tạo một operation LDAP mới chỉ vì caller gửi lại HTTP request.

### 10.2. Cùng key, payload khác

Nếu key đã được dùng cho payload khác:

- Trả conflict.
- Không ghi LDAP.
- Ghi log audit an toàn.

Nếu cho phép cùng key dùng lại với payload khác, idempotency key không còn nhận diện một operation duy nhất.

### 10.3. Ledger và LDAP không tự có transaction chung

Ví dụ:

1. Ghi ledger IN_PROGRESS.
2. LDAP Add thành công.
3. Application crash trước khi ghi ledger APPLIED.

Khi khởi động lại, ledger vẫn IN_PROGRESS nhưng entry đã tồn tại. Reconciliation cần đọc directory và xác minh operation marker/state trước khi quyết định.

Chiều ngược lại cũng có thể xảy ra: ledger đã được ghi nhưng LDAP chưa nhận request. Do đó operation ledger phải hỗ trợ trạng thái UNKNOWN và tiến trình đối soát.

### 10.4. Marker trong cùng ModifyRequest

Nếu schema cho phép một attribute chứa operation ID, có thể kết hợp marker và thay đổi business trong cùng một ModifyRequest:

```text
Một ModifyRequest trên cùng entry:
  ADD applicationOperationId = req-184
  REPLACE mail = lan@example.org
  REPLACE version = 8
```

Các change trong ModifyRequest là một operation nguyên tử. Nếu retry và marker đã tồn tại, Add marker có thể thất bại với attributeOrValueExists; do ModifyRequest atomic, các change khác trong request retry cũng không được áp dụng. Sau đó đọc entry để xác minh marker và desired state.

Giải pháp này có điều kiện:

- Schema phải cho phép attribute marker và cardinality phù hợp.
- ACL phải cho phép ứng dụng ghi/đọc marker.
- Có chính sách retention để entry không tích lũy marker vô hạn.
- Marker phải gắn với target và operation type rõ ràng.
- Các thao tác trên nhiều entry vẫn cần ledger/workflow riêng.

## 11. Conditional write bằng LDAP Assertion Control

Khi nhiều client có thể sửa cùng entry, đọc rồi ghi theo hai bước dễ gặp race condition:

```text
Client A đọc version=7
Client B đọc version=7

Client A ghi mail=A, version=8
Client B ghi mail=B, version=8

Update của A có thể bị ghi đè bởi B
```

LDAP Assertion Control theo RFC 4528 cho phép gắn một điều kiện vào update operation. Server kiểm tra điều kiện và thực hiện update như **một hành động nguyên tử**. Nếu điều kiện sai, operation không được thực hiện.

### 11.1. Dùng version attribute

Giả sử entry có:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan.old@example.org
appVersion: 7
```

Client muốn cập nhật:

```text
Assertion filter: (appVersion=7)
Modify:
  REPLACE mail = lan@example.org
  REPLACE appVersion = 8
```

Nếu version vẫn là 7, server áp dụng update. Nếu client khác đã đổi version thành 8, assertion không thỏa và update bị từ chối. Client phải đọc lại và xử lý conflict.

### 11.2. Assertion Control OID

| Thuộc tính | Giá trị |
| --- | --- |
| RFC | RFC 4528 |
| Control OID | `1.3.6.1.1.12` |
| Nội dung | LDAP filter được BER-encode |
| Tác dụng | Chỉ thực hiện operation nếu filter/assertion đúng trên target entry |
| Phạm vi | Có thể gắn với Add, Delete, Modify, ModifyDN và Search theo RFC |

Server hỗ trợ nên công bố OID này trong root DSE attribute `supportedControl`. Client cần kiểm tra capability của server và đặt criticality phù hợp; nếu control là điều kiện bắt buộc, không cho phép server âm thầm bỏ qua.

### 11.3. Assertion failed không phải lỗi transient

Nếu assertion thất bại:

- Không gửi lại cùng assertion cũ một cách vô hạn.
- Đọc lại entry.
- So sánh version và dữ liệu hiện tại.
- Tính lại desired state nếu nghiệp vụ cho phép.
- Nếu có thay đổi xung đột, trả conflict để caller quyết định.

Assertion Control giải quyết race condition và lost update. Nó không tự tạo idempotency key, không thay thế reconciliation sau mất response và không gom nhiều entry thành một transaction.

### 11.4. Không thay assertion bằng Compare rồi Modify riêng

Luồng sau không an toàn khi có concurrent writer:

```text
Compare appVersion = 7
      |
      v
Modify mail, appVersion = 8
```

Một client khác có thể thay đổi entry giữa Compare và Modify. Assertion Control gắn điều kiện vào chính update operation, tránh khoảng trống thời gian đó.

## 12. Transaction và rollback trong Spring LDAP

Người mới từ relational database thường mong đợi có thể đặt `@Transactional` lên service và mọi LDAP operation sẽ được server commit/rollback như một database transaction.

Điều này cần hiểu chính xác:

- LDAP protocol chuẩn không cung cấp transaction đa operation mặc định.
- Một operation như Modify có tính nguyên tử riêng.
- Spring LDAP cung cấp **client-side compensating transaction** qua `ContextSourceTransactionManager`.
- RFC 5805 mô tả LDAP transaction extension ở trạng thái Experimental; không được giả định mọi server hỗ trợ.

### 12.1. ContextSourceTransactionManager

Spring LDAP cung cấp:

```java
org.springframework.ldap.transaction.compensating.manager
    .ContextSourceTransactionManager
```

Transaction manager này ghi lại trạng thái cần thiết trước các operation ghi và tạo operation bù trừ nếu transaction rollback.

Các operation được theo dõi gồm:

- bind
- unbind
- rebind
- rename
- modifyAttributes

Ví dụ cách bù trừ:

| Operation ban đầu | Hành động bù trừ điển hình |
| --- | --- |
| bind entry | unbind entry vừa tạo |
| rename | rename về DN ban đầu |
| modifyAttributes | gửi modification ngược để khôi phục giá trị |
| unbind | chuyển entry tới DN tạm; commit mới xóa hẳn, rollback chuyển về |
| rebind | giữ entry cũ ở DN tạm; rollback khôi phục entry cũ |

Một số thao tác cần DN tạm và renaming strategy. Xóa subtree đệ quy có thể cần chiến lược temporary subtree khác với mặc định.

### 12.2. Đây không phải transaction server-side

Spring LDAP compensating transaction có giới hạn:

- LDAP server không biết transaction đang diễn ra.
- Không có isolation; client khác vẫn có thể sửa entry trong lúc transaction chạy.
- Nếu connection bị mất, transaction manager có thể không còn khả năng rollback.
- Operation bù trừ có thể thất bại hoặc không khôi phục hoàn toàn trạng thái.
- Ghi lại trạng thái và thực hiện bù trừ tạo thêm operation và overhead.

Vì thế, không được tuyên bố rollback chắc chắn chỉ vì method có `@Transactional`.

### 12.3. Cấu hình Java minh họa

Ví dụ dưới đây dùng API constructor của Spring LDAP 4.1+:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.transaction.compensating.manager.ContextSourceTransactionManager;
import org.springframework.ldap.transaction.compensating.manager.TransactionAwareContextSourceProxy;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class LdapTransactionConfiguration {

    @Bean
    ContextSource ldapTransactionAwareContextSource(
            @Qualifier("ldapContextSource") ContextSource target) {
        return new TransactionAwareContextSourceProxy(target);
    }

    @Bean
    LdapTemplate ldapTemplate(
            @Qualifier("ldapTransactionAwareContextSource")
            ContextSource transactionAwareSource) {
        return new LdapTemplate(transactionAwareSource);
    }

    @Bean
    PlatformTransactionManager ldapTransactionManager(
            @Qualifier("ldapContextSource") ContextSource target) {
        return new ContextSourceTransactionManager(target);
    }
}
```

Bean `ldapContextSource` là ContextSource gốc đã cấu hình endpoint, base DN và credential. `LdapTemplate` phải dùng `TransactionAwareContextSourceProxy`; transaction manager nhận ContextSource gốc.

Service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

@Service
public class PersonProvisioningService {

    private final LdapTemplate ldapTemplate;

    public PersonProvisioningService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Transactional(transactionManager = "ldapTransactionManager")
    public void provisionPersonAndMembership(
            PersonEntry person,
            String groupDn) {

        ldapTemplate.create(person);
        addMemberToGroup(groupDn, person.getDn());
    }

    private void addMemberToGroup(String groupDn, Name personDn) {
        ModificationItem addMember = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", personDn.toString()));

        ldapTemplate.modifyAttributes(
                groupDn,
                new ModificationItem[] {addMember});
    }
}
```

Ví dụ cho thấy cách đặt ranh giới transaction ở service. Cần cấu hình phần thêm membership bằng một operation ghi thông qua cùng LdapTemplate và cùng transaction-aware ContextSource.

### 12.4. Đừng nhầm compensating transaction với exactly-once

Transaction manager có thể cố gắng khôi phục trạng thái khi method ném exception trong khi client còn liên lạc được với server. Nhưng nếu connection mất sau khi server áp dụng operation:

- Client có thể không biết operation đã chạy.
- Transaction manager có thể không gửi được operation bù trừ.
- Directory có thể giữ một phần hoặc toàn bộ thay đổi.

Sau lỗi mạng, vẫn cần reconciliation và operation ledger.

### 12.5. Transaction extension RFC 5805

RFC 5805 mô tả LDAP Transactions với Start Transaction, Transaction Specification Control và End Transaction. RFC này có trạng thái **Experimental**, không phải Internet Standards Track. Phải xác minh directory server cụ thể hỗ trợ extension và cách client/library tích hợp trước khi dựa vào nó.

Không giả định `ContextSourceTransactionManager` tự dùng RFC 5805. Đây là cơ chế bù trừ phía client.

### 12.6. Không tự suy ra transaction chung với JDBC

Trong Spring LDAP 4.0, JDBC Transaction Integration cũ đã bị loại bỏ. Một method có annotation `@Transactional` không tự biến LDAP và relational database thành một XA transaction. Với workflow cập nhật cả hai nguồn:

- Dùng outbox/workflow state.
- Lưu operation ID và trạng thái từng resource.
- Thiết kế retry và compensation.
- Đối soát sau crash.
- Không trả trạng thái hoàn tất trước khi cả hai phía được xác minh.

## 13. Spring Data LDAP repository và LdapTemplate: chọn API theo semantics

Repository ODM tiện cho CRUD entity. Nhưng khi cần điều khiển chi tiết retry, assertion control hoặc modification operation, `LdapTemplate` thường thể hiện semantics rõ hơn.

| API | Dùng khi | Cần lưu ý |
| --- | --- | --- |
| Repository `save(...)` | CRUD entity theo abstraction repository | Không nên giả định mọi implementation đều idempotent |
| `LdapTemplate.create(entity)` | Add entry mới | DN phải chưa tồn tại |
| `LdapTemplate.update(entity)` | Cập nhật entity ODM | Nếu DN thay đổi, ODM có thể dùng unbind + bind |
| `LdapTemplate.delete(entity)` | Xóa entry | Retry cần xác minh DN và entry identity |
| `LdapTemplate.rename(oldDn, newDn)` | Di chuyển/đổi DN | Retry cần kiểm tra DN cũ và DN mới |
| `LdapTemplate.modifyAttributes(dn, items)` | Cập nhật attribute cụ thể | Một ModifyRequest có danh sách change nguyên tử |
| `LdapTemplate.rebind(...)` | Thay entry bằng entry mới | Thường tương đương unbind rồi bind; cần đánh giá rủi ro |

### 13.1. Ưu tiên thay đổi attribute rõ ràng khi cần retry

Ví dụ cập nhật một field:

```java
ModificationItem replaceMail = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", desiredEmail));

ldapTemplate.modifyAttributes(
        personDn,
        new ModificationItem[] {replaceMail});
```

Ý định của request rõ: đặt mail thành giá trị đích. So với rebind toàn entry, modification cụ thể thường giảm phạm vi thay đổi và dễ reconciliation hơn.

### 13.2. ODM update khi DN thay đổi

Theo API `LdapTemplate.update(Object)`, nếu DN tính từ field `@Id`/`@DnAttribute` khác DN hiện tại, implementation có thể di chuyển bằng unbind rồi bind. Đây là chuỗi operation và có thể có trạng thái trung gian.

Nếu cần đổi DN:

- Xác định operation mong muốn là rename/move.
- Cân nhắc `LdapTemplate.rename(...)`.
- Kiểm tra schema/naming attributes.
- Có operation ID hoặc reconciliation cho DN cũ/mới.
- Không retry update toàn entity mà chưa kiểm tra entry hiện tại.

## 14. Retry policy an toàn

Một retry policy tốt phải biết operation type, request deadline, idempotency và loại lỗi.

### 14.1. Quy trình quyết định

```text
Nhận lỗi khi ghi LDAP
       |
       v
Request chắc chắn chưa gửi?
   | Có                 | Không / không biết
   v                    v
Retry nếu còn deadline  Có LDAP response?
                            | Có             | Không
                            v                v
                       Result code lỗi?   UNKNOWN
                         | Có | Không        |
                         v    v              v
                      REJECTED APPLIED   Reconcile state
                                             |
                                  +----------+----------+
                                  |          |          |
                               Applied    Unchanged   Conflict
                                  |          |          |
                                  v          v          v
                               APPLIED    Retry safe   Manual/
                                           nếu policy   conflict
                                           cho phép
```

### 14.2. Quy tắc retry

- Chỉ retry lỗi transient; không retry lỗi credentials, ACL, schema hoặc input.
- Ưu tiên desired-state update như Replace giá trị cố định.
- Với Add/Delete/Rename, đối soát DN và operation identity trước.
- Với Increment hoặc operation cộng dồn, không retry nếu không có deduplication/conditional logic.
- Dùng cùng idempotency key cho mọi lần thử của cùng một request logic.
- Giới hạn số lần thử và tổng thời gian theo deadline.
- Dùng exponential backoff có jitter khi lỗi transient.
- Tránh retry ở nhiều tầng cùng lúc.
- Khi trạng thái vẫn UNKNOWN, giữ trạng thái và tiếp tục reconciliation thay vì báo FAILED giả.

### 14.3. Không retry lỗi nghiệp vụ

| LDAP result/exception | Ý nghĩa | Hành động |
| --- | --- | --- |
| `entryAlreadyExists (68)` | DN đã tồn tại | Lookup và xác minh marker/nội dung |
| `noSuchObject (32)` | Entry đích không tồn tại | Kiểm tra đã xóa, đã move hay DN sai |
| `attributeOrValueExists (20)` | Giá trị đã tồn tại | Đọc lại; xác minh desired state |
| `noSuchAttribute (16)` | Attribute/giá trị không tồn tại | Đọc lại; không lặp cùng Delete một cách mù quáng |
| `assertionFailed (122)` | Điều kiện cập nhật không còn đúng | Đọc lại version và xử lý conflict |
| `insufficientAccessRights (50)` | Không đủ quyền | Sửa ACL/service account |
| `invalidAttributeSyntax (21)` | Giá trị sai syntax | Sửa dữ liệu |
| `objectClassViolation (65)` | Entry không phù hợp schema | Sửa objectClass/attribute |
| `unavailableCriticalExtension (12)` | Server không hỗ trợ control critical được yêu cầu | Kiểm tra capability/server |
| CommunicationException/timeout | Mất liên lạc, kết quả có thể không xác định | Reconcile trước khi retry |

Mã result code là thông tin quan trọng. Không biến mọi exception Spring thành retryable chỉ vì nó là runtime exception.

## 15. Thiết kế API khi kết quả ghi chưa xác định

Nếu operation có thể mất response, API nên có cách cho caller tra cứu trạng thái.

### 15.1. Ví dụ response đồng bộ

Nếu LDAP trả success:

```json
{
  "operationId": "req-2026-000184",
  "status": "APPLIED",
  "resourceDn": "uid=lan,ou=people,dc=example,dc=org"
}
```

Nếu timeout và chưa thể xác minh:

```json
{
  "operationId": "req-2026-000184",
  "status": "UNKNOWN",
  "message": "The directory write outcome is being reconciled."
}
```

Không trả một thông báo chung “write failed, retry immediately” khi trạng thái chưa xác định.

### 15.2. Endpoint tra cứu trạng thái

Ví dụ:

```http
GET /api/operations/req-2026-000184
```

Response:

```json
{
  "operationId": "req-2026-000184",
  "status": "RECONCILING",
  "createdAt": "2026-11-26T10:30:00Z",
  "updatedAt": "2026-11-26T10:30:02Z"
}
```

Caller có thể polling với khoảng chờ hợp lý hoặc nhận callback/event theo kiến trúc ứng dụng.

### 15.3. Trạng thái nghiệp vụ đề xuất

| State | Ý nghĩa |
| --- | --- |
| RECEIVED | Đã nhận yêu cầu và cấp operation ID |
| IN_PROGRESS | Đang thực hiện LDAP write |
| APPLIED | Đã xác minh directory ở trạng thái mong muốn |
| REJECTED | LDAP trả lỗi xác định hoặc validation từ chối |
| UNKNOWN | Không biết server đã áp dụng hay chưa |
| RECONCILING | Đang đọc lại directory để xác định kết quả |
| RETRYABLE | Đã xác minh chưa áp dụng và có thể thử lại |
| CONFLICT | Entry đã thay đổi theo cách không phù hợp với request |
| COMPENSATED | Operation bù trừ đã được xác minh |
| MANUAL_REVIEW | Không thể tự xác định hoặc tự khôi phục an toàn |

Không phải ứng dụng nào cũng cần mọi state, nhưng cần phân biệt UNKNOWN với REJECTED.

## 16. Observability và audit

Để xử lý write lỗi, cần ghi đủ thông tin vận hành nhưng không làm lộ dữ liệu nhạy cảm.

Nên ghi:

- Operation ID/idempotency key.
- Logical directory và loại operation.
- DN đã được chuẩn hóa hoặc mã tham chiếu đã redaction.
- LDAP result code nếu có.
- Exception class/cause đã lọc thông tin nhạy cảm.
- Thời gian gửi, thời gian response, số lần retry.
- Trạng thái trước/sau reconciliation.
- Version hoặc operation marker được dùng.
- Kết quả compensation nếu có.

Không ghi:

- Bind password hoặc credential người dùng.
- Toàn bộ entry/Attributes nếu chứa dữ liệu cá nhân.
- Raw filter chứa dữ liệu nhạy cảm.
- Access token hoặc secret.

Metric hữu ích:

| Metric | Mục đích |
| --- | --- |
| ldap_write_total theo operation/result | Theo dõi số lần ghi và kết quả |
| ldap_write_unknown_total | Phát hiện write có outcome không xác định |
| ldap_reconciliation_total theo state | Theo dõi backlog đối soát |
| ldap_retry_total | Phát hiện retry storm |
| ldap_compensation_failure_total | Phát hiện rollback bù trừ thất bại |
| ldap_duplicate_request_total | Đo số request trùng idempotency key |
| ldap_assertion_failed_total | Theo dõi concurrent update conflict |

Không dùng DN hoặc idempotency key làm metric label vì cardinality cao. Dùng log/trace correlation thay cho label.

## 17. Kiểm thử idempotency và lỗi sau khi gửi

Unit test có thể kiểm tra cách phân loại exception, nhưng không mô phỏng chính xác tình huống server đã ghi và response bị mất. Cần integration test với LDAP server và một proxy/fault injector có thể cắt response.

### 17.1. Test Add bị mất response

1. Client gửi Add.
2. LDAP server tạo entry.
3. Proxy chặn response success.
4. Application nhận timeout/communication error.
5. Application chuyển operation sang UNKNOWN.
6. Reconciliation lookup DN và operation marker.
7. Xác minh marker khớp và đánh APPLIED.
8. Không tạo entry lần thứ hai.

### 17.2. Test Modify bị mất response

Seed entry với mail cũ và version 7. Gửi Modify đặt mail mới/version 8 rồi chặn response.

Kỳ vọng:

- Application không tự ghi REJECTED.
- Reconciliation đọc thấy mail mới/version 8.
- Operation được đánh APPLIED nếu marker/version chứng minh đúng request.
- Retry không ghi đè một update mới hơn.

### 17.3. Test ModifyRequest atomicity

Gửi một ModifyRequest có:

- Replace mail hợp lệ.
- Add attribute/value vi phạm schema hoặc duplicate.

Khi server trả lỗi, xác minh không có change nào trong request được áp dụng. Sau đó mô phỏng mất response và xác minh trạng thái UNKNOWN.

### 17.4. Ma trận test operation

| Test | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| Add duplicate | Add lần đầu thành công, response bị chặn, retry | Lookup và xác minh marker; không coi mọi entryAlreadyExists là success |
| Modify Replace | Replace giá trị cố định nhiều lần | Business state giữ nguyên |
| Modify Add | Add cùng giá trị hai lần | Xử lý attributeOrValueExists bằng reconciliation |
| Modify Delete | Delete cùng giá trị hai lần | Xác minh giá trị đã vắng mặt |
| Modify Increment | Increment rồi mất response, retry | Không tăng hai lần; dùng dedupe/conditional logic |
| Delete entry | Delete rồi mất response, retry | Xác minh DN vắng mặt và identity |
| Rename | Rename rồi mất response, retry | Kiểm tra DN cũ, DN mới và entry identity |
| Concurrent version | Hai client cùng cập nhật version 7 | Chỉ một assertion version 7 thành công |
| Duplicate API request | Cùng idempotency key gửi đồng thời | Chỉ một logical operation được thực hiện |
| Same key, payload khác | Caller dùng lại key sai payload | Conflict, không ghi LDAP |
| Crash sau LDAP success | Crash trước khi ghi ledger APPLIED | Reconciliation phục hồi trạng thái |
| Compensation failure | Mất connection trong rollback | UNKNOWN/MANUAL_REVIEW, không tuyên bố rollback thành công |
| Multi-entry workflow | Entry đầu thành công, entry sau lỗi | Resume/compensate theo workflow state |

### 17.5. Kiểm thử trên đúng directory server

Các control và extension không được hỗ trợ đồng đều. Kiểm tra:

- Assertion Control OID `1.3.6.1.1.12` trong `supportedControl`.
- Modify-Increment feature OID `1.3.6.1.1.14` trong `supportedFeatures` nếu dùng.
- RFC 5805 transaction extension nếu có ý định sử dụng.
- Quyền đọc marker/version và quyền ghi operation ID.
- Hành vi replication và read-after-write trên topology thật.

Không giả định test server đơn giản hỗ trợ đầy đủ mọi extension giống directory production.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Timeout bị coi là operation thất bại | Nhầm response mất với server không áp dụng | Đưa trạng thái vào UNKNOWN và reconciliation |
| Retry Add nhận entryAlreadyExists rồi trả success | Không kiểm tra entry có thuộc request trước không | So sánh operation marker/business identity |
| Retry Delete nhận noSuchObject rồi trả success | Không kiểm tra DN/ownership | Xác minh desired state và identity |
| Retry ADD_ATTRIBUTE nhận duplicate value | Operation không idempotent về response | Đọc lại attribute và marker |
| Retry Increment làm tăng hai lần | Increment là thao tác cộng dồn | Dùng operation ID/assertion hoặc không retry |
| Rename retry báo source DN không tồn tại | Lần đầu đã move entry | Kiểm tra cả DN cũ và DN mới |
| Hai ModifyRequest được xem là một transaction | Nhầm atomicity một request với nhiều request | Dùng workflow/compensation hoặc server extension |
| @Transactional được xem là rollback tuyệt đối | Nhầm compensating transaction với server transaction | Hiểu giới hạn connection loss và isolation |
| LdapTemplate update đổi DN nhưng retry không rõ trạng thái | ODM có thể unbind rồi bind | Dùng rename phù hợp hoặc reconciliation |
| Compare rồi Modify bị lost update | Race giữa hai request riêng | Assertion Control trên update |
| Ledger ghi APPLIED trước khi LDAP thành công | Thứ tự cập nhật state sai | Dùng IN_PROGRESS/UNKNOWN và reconcile |
| LDAP đã ghi nhưng ledger chưa cập nhật | Crash giữa hai resource | Reconciliation theo operation marker/state |
| Retry ở HTTP, service và repository cùng lúc | Nhiều tầng khuếch đại request | Chọn một tầng retry có deadline |
| Đọc từ replica cũ rồi kết luận chưa ghi | Replication lag | Đọc authoritative endpoint/consistency phù hợp |
| Compensation thất bại nhưng trả rollback success | Không kiểm tra operation bù trừ | Ghi COMPENSATION_FAILED/MANUAL_REVIEW |

## 19. Bài tập tự luyện

**Câu 1.** Application gửi Add, server tạo entry nhưng response bị mất. Retry trả entryAlreadyExists. Có thể coi ngay là thành công không?

*Gợi ý:* Không. Lookup entry và xác minh operation marker hoặc identity/nội dung.

**Câu 2.** Vì sao Replace một giá trị cố định thường an toàn hơn Increment khi retry?

*Gợi ý:* Replace đưa state về giá trị đích; Increment cộng thêm mỗi lần gửi.

**Câu 3.** Một ModifyRequest có ba ModificationItem. Server trả lỗi. Client có thể kỳ vọng một hoặc hai item đã áp dụng không?

*Gợi ý:* Không. Danh sách change trong một ModifyRequest là một operation nguyên tử.

**Câu 4.** Client không nhận ModifyResponse. Có thể kết luận tất cả change đã được áp dụng không?

*Gợi ý:* Không. Khi response không được nhận, kết quả operation không xác định.

**Câu 5.** Delete retry nhận noSuchObject. Khi nào có thể coi desired state đã đạt?

*Gợi ý:* Khi đã xác minh đúng DN/entry mục tiêu thực sự vắng mặt và policy nghiệp vụ chấp nhận trạng thái đó.

**Câu 6.** Vì sao Compare rồi Modify không đủ để chống lost update?

*Gợi ý:* Client khác có thể thay đổi entry giữa hai operation. Dùng Assertion Control gắn vào Modify.

**Câu 7.** Spring LDAP ContextSourceTransactionManager có phải transaction server-side không?

*Gợi ý:* Không. Đây là compensating transaction phía client, không có isolation và không thể rollback nếu mất kết nối.

**Câu 8.** Vì sao idempotency key trong HTTP header chưa đủ?

*Gợi ý:* LDAP server không tự hiểu key. Application phải lưu key/operation state hoặc ghi marker có thể đối soát.

**Câu 9.** Sau khi LDAP ghi thành công, application crash trước khi ledger ghi APPLIED. Phục hồi thế nào?

*Gợi ý:* Đọc lại directory, kiểm tra marker/version/desired state rồi cập nhật ledger.

**Câu 10.** Khi ODM update entity mà DN thay đổi, cần lưu ý gì?

*Gợi ý:* Spring LDAP có thể thực hiện unbind rồi bind. Đây là chuỗi operation; cần đánh giá retry và cân nhắc rename.

## 20. Ghi nhớ

- **Timeout không chứng minh write thất bại.** Nếu request có thể đã gửi nhưng response không tới, trạng thái là UNKNOWN.
- LDAP đảm bảo tính nguyên tử cho từng update operation; một ModifyRequest có nhiều change được áp dụng như một operation.
- Atomicity của một operation không mở rộng sang nhiều request hoặc nhiều entry.
- Add retry có thể gặp entryAlreadyExists; phải xác minh operation identity và dữ liệu.
- Modify Replace giá trị cố định thường phù hợp retry hơn Add/Delete value hoặc Increment.
- Delete retry có thể gặp noSuchObject; xác minh đúng DN và desired state trước khi kết luận.
- Rename retry cần kiểm tra cả DN cũ và DN mới.
- Modify-Increment RFC 4525 là extension; operation nguyên tử nhưng không idempotent khi gửi lại.
- Idempotency key phải gắn với operation ledger hoặc marker có thể đối soát; key HTTP tự nó không deduplicate LDAP.
- Assertion Control RFC 4528 hỗ trợ conditional update nguyên tử và giúp tránh lost update.
- ContextSourceTransactionManager của Spring LDAP cung cấp compensating transaction phía client, không phải transaction server-side tuyệt đối.
- RFC 5805 LDAP Transactions là Experimental; xác minh server support trước khi sử dụng.
- Với lỗi không xác định, reconcile state trước khi retry; không báo FAILED giả hoặc APPLIED khi chưa xác minh.
- Kiểm thử mất response sau khi server ghi, duplicate request, concurrent update, compensation failure và replication lag.

**Tài liệu tham khảo chính thức:**

- [RFC 4511 — LDAP: The Protocol, mục 4.6–4.10](https://www.rfc-editor.org/rfc/rfc4511): semantics và atomicity của Modify, Add, Delete, ModifyDN, Compare; trạng thái không xác định khi ModifyResponse không được nhận.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528): control OID 1.3.6.1.1.12, điều kiện nguyên tử cho update.
- [RFC 4525 — LDAP Modify-Increment Extension](https://www.rfc-editor.org/rfc/rfc4525): increment operation, feature OID và cách kết hợp assertion/pre-read/post-read.
- [RFC 5805 — LDAP Transactions](https://www.rfc-editor.org/rfc/rfc5805): LDAP transaction extension ở trạng thái Experimental.
- [Spring LDAP — Transaction Support](https://docs.spring.io/spring-ldap/reference/transaction-support.html): ContextSourceTransactionManager, compensating operations, giới hạn rollback và transaction configuration.
- [Spring LDAP API — ContextSourceTransactionManager](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/ContextSourceTransactionManager.html): constructor, ContextSource và cơ chế bù trừ.
- [Spring LDAP API — TransactionAwareContextSourceProxy](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/transaction/compensating/manager/TransactionAwareContextSourceProxy.html): proxy để giữ DirContext trong transaction và ghi nhận rollback operation.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): create, update, delete, rename, modifyAttributes và ODM behavior.
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): bind, rebind và modifyAttributes.
