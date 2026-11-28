# Chi phí, quyền bổ sung và tác động nhìn thấy từ bên ngoài

Giao dịch bù trừ (compensating transaction) giúp đưa một quy trình nhiều bước về trạng thái nghiệp vụ chấp nhận được khi một bước thất bại sau khi các bước trước đã thành công. Nhưng compensation không miễn phí. Nó có thể cần thêm lần đọc và ghi LDAP, lưu snapshot dữ liệu, cấp quyền Delete hoặc Modify rộng hơn, giữ journal lâu hơn, xử lý cạnh tranh với tác nhân khác và sửa những side effect mà hệ thống bên ngoài đã nhìn thấy.

Trong Spring Data LDAP, một quy trình tạo tài khoản có thể gồm Add entry người dùng, thêm DN vào group, bật tài khoản, ghi trạng thái vào database và phát sự kiện cho hệ thống khác. Nếu bước sau thất bại, xóa entry người dùng không nhất thiết đưa toàn bộ hệ thống về trạng thái ban đầu: group membership có thể đã được đọc, email có thể đã gửi, token có thể đã phát hành, audit event vẫn còn và một replica LDAP có thể đã nhìn thấy thay đổi.

Bài thuộc chương **Giao dịch bù trừ** của mô-đun `SPRING_DATA_LDAP`. Chúng ta sẽ đánh giá chi phí của compensation, xác định quyền LDAP mà thao tác bù cần ngoài quyền của luồng ghi ban đầu, phân loại side effect theo mức độ nhìn thấy, thiết kế trạng thái pending/active, lưu journal, xử lý compensation thất bại và kiểm thử các tác động vượt ra ngoài LDAP.

> **Nguyên tắc:** compensation là một thao tác mới nhằm sửa hậu quả nghiệp vụ. Nó không xóa lịch sử, không tự thu hồi những gì hệ thống khác đã quan sát và không bảo đảm khôi phục chính xác mọi trạng thái kỹ thuật ban đầu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt rollback nguyên tử với compensation trong một saga nhiều bước.
2. Nhận diện chi phí bổ sung khi lưu snapshot, thực hiện thao tác bù và đối soát.
3. Tính được quyền LDAP mà thao tác bù cần ngoài quyền của thao tác thuận.
4. Giải thích vì sao Delete, Rename và đổi password không phải lúc nào cũng có thao tác nghịch đảo hoàn hảo.
5. Đánh giá side effect mà ứng dụng khác, người dùng hoặc hệ thống tích hợp có thể nhìn thấy.
6. Thiết kế trạng thái pending để trì hoãn việc công bố một tài khoản chưa hoàn tất.
7. Dùng operation journal để theo dõi từng bước thuận và từng bước bù.
8. Chỉ bù các thao tác đã được xác nhận áp dụng; đối soát thao tác còn UNKNOWN.
9. Thiết kế compensation có điều kiện, idempotent và an toàn khi có concurrent update.
10. Phân biệt quyền của actor gọi API, Bind identity của ứng dụng và LDAP ACL.
11. Xử lý group membership, dữ liệu nhạy cảm, audit, event, cache và token sau compensation.
12. Kiểm thử compensation thành công, thất bại, timeout và side effect đã được phát ra.

## 2. Compensation không phải rollback

Trong transaction cơ sở dữ liệu, rollback có thể đưa các thay đổi thuộc cùng transaction về trạng thái trước commit. Với workflow LDAP phối hợp nhiều request hoặc nhiều hệ thống, ta thường không có một transaction chung bao trùm mọi bước.

Ví dụ provisioning:

1. Add entry người dùng vào LDAP.
2. Thêm DN người dùng vào group.
3. Bật tài khoản để đăng nhập.
4. Cập nhật hồ sơ trong database ứng dụng.
5. Phát sự kiện cho hệ thống cấp quyền.
6. Gửi email hướng dẫn cho người dùng.

Nếu bước 5 thất bại, các bước 1–4 có thể đã commit và email ở bước 6 có thể đã được gửi bởi một worker khác. Compensation có thể:
- Xóa membership vừa thêm.
- Disable tài khoản.
- Xóa entry nếu entry đó vẫn thuộc operation này và chưa được sử dụng.
- Đánh dấu hồ sơ ứng dụng là provisioning failed.
- Phát sự kiện điều chỉnh cho consumer đã nhận sự kiện trước đó.

Những hành động này không làm như thể chưa từng có provisioning. Chúng tạo ra trạng thái mới để khôi phục tính nhất quán nghiệp vụ.

| Khái niệm | Ý nghĩa | Phạm vi |
| --- | --- | --- |
| Rollback | Hủy các thay đổi chưa commit trong transaction | Các resource tham gia cùng transaction |
| Compensation | Thực hiện operation mới để sửa hậu quả của operation đã commit | Các hệ thống và bước đã được saga ghi nhận |
| Retry | Gửi lại một operation | Chỉ an toàn khi có điều kiện idempotency phù hợp |
| Reconciliation | Đọc và so sánh trạng thái thực tế với trạng thái mong muốn | Xác định operation đã áp dụng hay chưa |
| Corrective action | Tạo thay đổi mới để xử lý hậu quả không thể đảo ngược | Side effect đã nhìn thấy hoặc đã phát tán |

### 2.1. Compensation không khôi phục chính xác trạng thái kỹ thuật

Giả sử Add một entry thành công rồi Delete entry đó để bù. Nếu sau đó tạo lại cùng DN, entry mới có thể có:
- Operational attribute khác như entry UUID, CSN hoặc timestamp.
- Giá trị mặc định khác do server/plugin áp dụng.
- Quan hệ group hoặc referential integrity khác.
- Audit history mới.
- Password không thể khôi phục.
- ACL hoặc metadata được tạo bởi provisioning hook khác.

Về nghiệp vụ, người dùng có thể lại tồn tại. Về kỹ thuật, đó không phải cùng một entry ban đầu.

### 2.2. Compensation cũng có thể thất bại

Một compensation là LDAP write khác. Nó có thể gặp LDAP server unavailable, ACL từ chối, entry đã bị actor khác thay đổi, DN đích đã được sử dụng, parent entry không còn tồn tại, schema không cho phép trạng thái khôi phục hoặc timeout sau khi server đã áp dụng thao tác bù nhưng response bị mất.

Do đó cần theo dõi cả trạng thái thuận và trạng thái bù. Không đánh dấu saga là rolled back chỉ vì đã gọi method compensation.

## 3. Quy trình ví dụ: tạo người dùng và cấp quyền nhóm

Giả sử directory có cấu trúc:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=groups
│   └── cn=engineering
└── ou=service
    ├── cn=svc-directory-writer
    └── cn=svc-directory-compensator
~~~

Entry người dùng Lan:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
employeeNumber: EMP-2048
accountLifecycle: pending
~~~

Group:

~~~ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: uid=minh,ou=people,dc=example,dc=org
~~~

Quy trình muốn:
1. Tạo Lan ở trạng thái pending.
2. Thêm DN của Lan vào member của engineering.
3. Xác minh membership.
4. Chuyển lifecycle sang active.
5. Ghi nhận provisioning hoàn tất.
6. Phát event và gửi notification.

`accountLifecycle` trong ví dụ là thuộc tính minh họa, chỉ dùng nếu schema và các ứng dụng tiêu thụ đã hỗ trợ. Nó không phải thuộc tính chuẩn chung của mọi LDAP server. Với Active Directory, trạng thái account enable/disable có semantics riêng; phải dùng adapter và quy tắc đúng server.

~~~mermaid
sequenceDiagram
    participant API as Application service
    participant J as Saga journal
    participant L as LDAP directory
    participant E as Event consumers
    participant U as User
    API->>J: Prepare saga
    API->>L: Add user as pending
    L-->>API: Add success
    API->>J: Record step applied
    API->>L: Add group membership
    L-->>API: Modify success
    API->>J: Record membership applied
    API->>L: Activate account
    L-->>API: Modify success
    API->>J: Mark directory ready
    API->>E: Publish UserProvisioned
    API->>U: Send invitation
~~~

Nếu thêm membership thất bại với một LDAP error response xác định, saga có thể bù bước Add user bằng Delete hoặc giữ lại account pending để retry theo policy. Nếu membership timeout và kết quả UNKNOWN, phải đối soát trước khi quyết định bù user; không thể giả định membership chưa được thêm.

## 4. Các nhóm chi phí của compensation

Chi phí không chỉ là số LDAP request. Cần xem cả dữ liệu cần giữ, quyền cần cấp, thời gian xử lý và ảnh hưởng tới các consumer.

| Nhóm chi phí | Phát sinh từ đâu | Hệ quả |
| --- | --- | --- |
| Đọc và snapshot | Đọc attribute trước khi Modify/Delete | Thêm round-trip, quyền Read và lưu dữ liệu |
| Write amplification | Thao tác thuận cộng thao tác bù | Tăng tải LDAP và độ trễ |
| Journal và retention | Lưu trạng thái từng bước, snapshot, retry | Tốn storage và công sức vận hành |
| Quyền bổ sung | Delete, restore, Modify membership, Rename ngược | Tăng blast radius nếu credential bị lộ |
| Concurrency | Kiểm tra version, identity và precondition | Cần control hoặc đối soát, xử lý conflict |
| Side effect bên ngoài | Event, email, token, cache, downstream job | Cần corrective action hoặc cơ chế thu hồi riêng |
| Vận hành | Compensation thất bại hoặc UNKNOWN | Cần dashboard, alert và quy trình xử lý thủ công |
| Kiểm thử | Mô phỏng lỗi ở mọi ranh giới | Tăng số scenario và thời gian duy trì test |

### 4.1. Chi phí đọc trước khi ghi

Để bù một Modify, ứng dụng thường cần biết giá trị cũ. Ví dụ:

~~~java
Attributes before = ldapTemplate.lookup(
        personDn,
        attrs -> attrs
);
~~~

Nếu chỉ lưu giá trị mới mà không lưu giá trị cũ, ứng dụng không biết phải khôi phục gì khi bước sau thất bại.

Snapshot làm phát sinh:
- Một hoặc nhiều Search/Lookup bổ sung.
- Quyền đọc các attribute cần phục hồi.
- Dung lượng lưu snapshot.
- Quy định mã hóa và retention.
- Rủi ro snapshot đã cũ do actor khác cập nhật sau lần đọc.

Snapshot không tự tạo ra tính nhất quán. Nếu có concurrent update, compensation phải kiểm tra rằng entry vẫn ở version/giá trị do saga ghi trước khi restore.

### 4.2. Chi phí write amplification

Một workflow gồm 3 LDAP writes có thể phát sinh 3 writes bù. Một lần timeout còn có thể cần nhiều lần đọc đối soát.

Ví dụ:
- Add user.
- Add member.
- Modify lifecycle active.
- Khi thất bại: Remove member.
- Delete hoặc disable user.
- Đối soát từng thao tác bù.

Tải LDAP tăng khi lỗi xảy ra đúng lúc server đang quá tải. Compensation có thể làm tình hình tệ hơn nếu không có backoff, concurrency limit và circuit breaker phù hợp.

### 4.3. Chi phí lưu trữ và bảo vệ journal

Journal cần đủ thông tin để quyết định hành động tiếp theo, nhưng không nên sao chép toàn bộ directory entry một cách mặc định.

Cần quyết định:
- Lưu attribute nào để phục hồi.
- Có cần lưu DN cũ và DN mới không.
- Có lưu stable ID và fingerprint không.
- Snapshot có chứa dữ liệu cá nhân hoặc thông tin nhạy cảm không.
- Ai được đọc journal.
- Thời gian giữ và cách xóa snapshot theo retention policy.
- Audit record nào phải giữ lâu hơn snapshot.

Không lưu plaintext password, Bind password, private key hoặc token trong journal. Với password operation, compensation thường là một thao tác thay thế credential mới, không phải khôi phục secret cũ.

## 5. Quyền bổ sung mà compensation cần

Quyền của luồng thuận và luồng bù có thể khác nhau. Một account chỉ được Add entry chưa chắc có quyền Delete entry để bù. Một account chỉ được Modify group membership chưa chắc có quyền đọc snapshot hoặc restore attribute.

Bảng sau mô tả quyền theo ví dụ OpenLDAP ACL; cú pháp và cách đánh giá ACL phải được kiểm tra trên server đang dùng.

| Thao tác thuận | Quyền thường cần cho luồng thuận | Compensation dự kiến | Quyền bổ sung có thể cần |
| --- | --- | --- | --- |
| Add user | Add vào parent; quyền phù hợp trên entry mới | Delete user | Delete trên entry và quyền liên quan tới children của parent theo ACL server |
| Add group member | Modify attribute member | Remove đúng member value | Modify member trên group |
| Remove group member | Modify attribute member | Add lại member value | Modify member, và schema phải cho phép membership được phục hồi |
| Replace attribute | Modify attribute | Restore giá trị cũ | Read giá trị cũ trước đó và Modify attribute |
| Delete user | Delete entry | Recreate user | Add vào parent, Add attributes, có thể cần quyền tạo credential và các quan hệ liên quan |
| Rename/Move | ModifyDN | Rename về DN cũ | Quyền Rename/Move ở nguồn/đích và quyền kiểm tra DN collision |
| Disable account | Modify trạng thái account | Enable lại | Quyền Modify thuộc tính trạng thái |
| Enable account | Modify trạng thái account | Disable lại | Quyền Modify thuộc tính trạng thái |
| Phát event | Quyền publish | Phát event điều chỉnh | Quyền publish event loại corrective/revoked |
| Gửi email | Quyền gửi notification | Gửi thông báo sửa sai | Không thể thu hồi email đã nhận; cần policy notification khác |

### 5.1. OpenLDAP Delete có thể cần quyền trên cả entry và parent

Với OpenLDAP, ACL cho Delete liên quan đến quyền trên pseudo-attribute `entry` của entry đích và `children` của parent entry. Chi tiết phụ thuộc thứ tự ACL và cấu hình thực tế.

Điều đó có nghĩa một service account được phép Add một entry chưa chắc đã được phép Delete entry ấy. Khi thiết kế compensator, cần kiểm thử bằng đúng Bind DN và ACL, không dùng rootdn để xác nhận.

Active Directory có ACL model khác, gồm quyền Delete trên object và/hoặc Delete Child tại parent tùy loại đối tượng và policy. Không áp cú pháp ACL OpenLDAP cho AD.

### 5.2. Snapshot làm tăng quyền Read

Một compensator cần khôi phục attribute cũ phải biết giá trị cũ. Điều này có thể đòi quyền Search/Read trên các attribute mà luồng thuận không cần đọc.

Ví dụ:
- Luồng thuận chỉ Replace `title`.
- Luồng bù cần biết `title` trước đó.
- Nếu attribute bị ACL ẩn, snapshot không đầy đủ và không thể restore chính xác.

Không mở quyền Read rộng trên toàn directory chỉ để bù một vài attribute. Chỉ đọc các field cần thiết trong base DN hẹp.

### 5.3. Quyền phục hồi Delete thường rộng hơn quyền ghi thông thường

Để xóa user đã tạo, compensator cần Delete. Để phục hồi một user đã bị xóa, nó cần Add vào parent, tạo lại attributes, xử lý group membership và có thể provision credential mới.

Recreate không khôi phục các operational attributes do server quản lý. Vì vậy, cấp quyền restore không đồng nghĩa ứng dụng có thể khôi phục nguyên trạng entry cũ.

### 5.4. Tách identity của writer và compensator

Có thể dùng hai Bind identity:
- `directoryWriter` cho operation thuận trong phạm vi OU cụ thể.
- `directoryCompensator` cho các action bù đã được phê duyệt.

Tách identity giúp audit biết ai thực hiện bước thuận và ai thực hiện bước bù. Tuy nhiên, account compensator có quyền mạnh hơn sẽ trở thành mục tiêu có giá trị cao.

Các nguyên tắc:
- Giới hạn subtree, attribute và operation.
- Secret riêng, xoay vòng riêng.
- Không cấp quyền quản trị toàn directory nếu chỉ cần bù trong `ou=people` và `ou=groups`.
- Không tự động chuyển sang rootdn/Domain Admin khi writer bị ACL từ chối.
- Ghi actor, saga ID, target stable ID và lý do của mọi thao tác bù.
- Có policy phê duyệt riêng cho compensation phá hủy như Delete hoặc recursive cleanup.

### 5.5. Ma trận quyền là một phần của thiết kế

Trước khi triển khai saga, tạo ma trận rõ ràng:

| Identity | People OU | Groups OU | Journal DB | Event bus |
| --- | --- | --- | --- | --- |
| API reader | Search/Read cần thiết | Search/Read cần thiết | Read operation status | Không publish |
| Directory writer | Add/Modify/Read theo workflow | Modify membership | Ghi saga step | Không publish trực tiếp nếu không cần |
| Compensator | Delete/Modify giới hạn | Modify membership giới hạn | Đọc journal, ghi compensation result | Publish corrective event nếu được giao |
| Reconciliation worker | Read/Lookup | Read/Lookup | Ghi trạng thái đối soát | Không phát event cho tới khi policy xác nhận |
| Notification worker | Không cần LDAP write | Không cần LDAP write | Đọc outbox | Gửi email/notification |

Đây là ma trận minh họa. Quyền thực tế cần dựa trên ACL, schema và server. Không gom tất cả vào một service account có quyền Read/Write/Delete toàn bộ directory chỉ để code đơn giản hơn.

## 6. Không phải operation nào cũng có compensation hoàn hảo

Một compensation đúng cần xét dữ liệu cũ, identity, quan hệ và side effect. “Gửi lệnh ngược lại” chưa đủ.

### 6.1. Add entry rồi Delete entry

Luồng thuận:

~~~java
ldapTemplate.bind(personDn, null, personAttributes);
~~~

Compensation có thể là:

~~~java
ldapTemplate.unbind(personDn);
~~~

Chỉ xóa khi:
- Add ban đầu được xác nhận thành công.
- Entry vẫn có stable provisioning ID của saga.
- Entry chưa bị một actor khác sửa đổi hoặc nhận thêm dữ liệu nghiệp vụ.
- Không có child entry cần giữ lại.
- Không có quy tắc retention cấm xóa.

LDAP Delete chuẩn chỉ xóa entry lá. Nếu entry đã có children, Delete có thể bị từ chối. Không dùng recursive delete như một cách bù mặc định.

Nếu entry đã được hệ thống khác dùng, disable/tombstone có thể phù hợp hơn hard delete.

### 6.2. Add group member rồi Remove member

Luồng thuận:

~~~java
ModificationItem addMember = new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("member", personDn.toString()));

ldapTemplate.modifyAttributes(
        groupDn,
        new ModificationItem[] { addMember });
~~~

Compensation:

~~~java
ModificationItem removeMember = new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("member", personDn.toString()));

ldapTemplate.modifyAttributes(
        groupDn,
        new ModificationItem[] { removeMember });
~~~

Đây là thao tác bù hợp lý nếu membership được thêm bởi saga và chưa bị actor khác thay đổi.

Nhưng với schema `groupOfNames`, group thường phải có ít nhất một `member`. Nếu xóa thành viên cuối cùng, server có thể từ chối do schema violation. Khi đó phải có policy riêng: giữ member kỹ thuật hợp lệ, xóa group nếu đúng nghiệp vụ, hoặc dùng loại group/schema cho phép rỗng. Không xóa member cuối cùng rồi giả định compensation luôn hợp lệ.

### 6.3. Modify attribute rồi khôi phục giá trị cũ

Ví dụ luồng thuận:

~~~java
ModificationItem updateTitle = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("title", "Senior Developer"));

ldapTemplate.modifyAttributes(
        personDn,
        new ModificationItem[] { updateTitle });
~~~

Compensation cần snapshot giá trị `title` trước khi sửa, sau đó Replace về giá trị cũ.

Rủi ro: người quản trị có thể đã thay `title` thành `Engineering Manager` sau operation của saga. Nếu compensator Replace về `Developer`, nó ghi đè thay đổi mới.

Vì vậy, cần:
- Ghi stable ID và version/precondition khi đọc.
- Kiểm tra giá trị hiện tại vẫn là giá trị saga đã ghi.
- Chỉ restore nếu precondition còn đúng.
- Nếu có thay đổi khác, ghi CONFLICT và yêu cầu xử lý.

### 6.4. Delete rồi Add lại không phải restore hoàn hảo

Sau Delete, một số thông tin có thể không đọc lại được hoặc không được phép lưu trong snapshot:
- Password hash/secret.
- Operational attributes.
- UUID/CSN/timestamp.
- Server-generated metadata.
- Quan hệ được plugin/overlay duy trì.
- Audit event và replication history.

Nếu phải phục hồi một entry đã xóa, đó là **re-provisioning** theo dữ liệu được phép khôi phục, không phải rollback nguyên trạng. Cần tạo identity mới hoặc xử lý stable identifier theo policy của directory.

### 6.5. Rename/Move rồi rename ngược

Spring LDAP có thể gọi:

~~~java
ldapTemplate.rename(oldDn, newDn);
~~~

Compensation có thể rename từ DN mới về DN cũ. Nhưng thao tác bù có thể thất bại nếu DN cũ đã được entry khác sử dụng, parent OU cũ đã bị xóa, entry đã được di chuyển tiếp, RDN attribute bị thay đổi hoặc ACL ở nguồn/đích không cho Rename.

Đối soát cả hai DN và stable identity trước khi rename ngược. Không dùng DN đơn thuần để xác định đúng object sau khi rename.

### 6.6. Password không thể rollback bằng snapshot thông thường

Password thường được lưu dưới dạng hash hoặc xử lý qua password operation của server. Ứng dụng không thể đọc plaintext password cũ để khôi phục.

Nếu password mới đã được đặt nhưng workflow thất bại, hành động phù hợp có thể là disable account, yêu cầu reset password mới, thu hồi session/token liên quan, gửi thông báo bảo mật hoặc chuyển sang quy trình helpdesk/identity management.

Không lưu password cũ hoặc password mới trong saga journal để cố tạo compensation giả.

## 7. Side effect nào bên ngoài LDAP có thể nhìn thấy?

Một thay đổi LDAP có thể được quan sát bởi nhiều thành phần khác trước khi saga hoàn tất.

| Side effect | Ai có thể nhìn thấy? | Có thể đảo ngược không? |
| --- | --- | --- |
| Entry được Add | Ứng dụng Search directory, đồng bộ, admin | Có thể Delete/Disable, nhưng audit và identity không biến mất |
| Group membership được Modify | Authorization service, ứng dụng phân quyền | Có thể Remove, nhưng quyền có thể đã được sử dụng |
| Account được Enable | Người dùng, hệ thống đăng nhập | Có thể Disable, nhưng session đã cấp cần thu hồi riêng |
| Event được publish | Consumer, data lake, audit pipeline | Không xóa được việc consumer đã nhận; có thể phát corrective event |
| Email được gửi | Người nhận và mail gateway | Không thể thu hồi đáng tin cậy; chỉ gửi thông báo đính chính |
| Token được cấp | Client, API gateway, resource server | Cần revoke/expire token; token offline có thể còn hiệu lực tới hạn |
| Cache/search index | Ứng dụng đọc cache, search UI | Có thể invalidate/rebuild, nhưng có cửa sổ dữ liệu cũ |
| Audit log | Security/SOC, compliance | Không được xóa để giả vờ operation chưa xảy ra |
| Replication | LDAP replica/DC khác | Không thể “làm như chưa từng replicate”; cần ghi thay đổi tiếp theo |
| Webhook/downstream job | Hệ thống tích hợp | Cần compensation hoặc event sửa sai theo hợp đồng |

### 7.1. Membership có thể tạo quyền ngay lập tức

Nếu một hệ thống authorization đọc `member` để cấp quyền truy cập repository, thêm user vào group có thể cấp quyền ngay sau khi directory cập nhật.

Nếu saga sau đó Remove member:
- User có thể đã tải dữ liệu.
- API token có thể đã được cấp.
- Job nền có thể đã bắt đầu.
- Cache authorization có thể chưa hết hạn.
- Một replica khác có thể vẫn nhìn thấy membership cũ.

Remove membership là bước bù directory; nó không tự thu hồi dữ liệu đã truy cập hoặc credential đã cấp.

### 7.2. Enable account có thể phát sinh session

Khi account được bật, người dùng hoặc hệ thống SSO có thể đăng nhập. Disable account sau đó không nhất thiết thu hồi session hiện có, refresh token, access token đã ký, cookie ở browser, credential cache ở client hoặc session trên ứng dụng downstream.

Nếu enable là bước cuối trước khi công bố, cần phối hợp với session/token service để thu hồi khi compensation yêu cầu.

### 7.3. Event và email không thể “undo”

Một event `PersonProvisioned` đã được consumer nhận có thể tạo account ở ứng dụng khác, cấp license, gửi welcome email, tạo ticket/record HR hoặc kích hoạt workflow onboarding.

Phát một event `PersonProvisioningCancelled` không làm event đầu biến mất. Consumer cần hiểu event điều chỉnh và xử lý idempotent theo saga/resource ID.

Email đã gửi cũng không thể thu hồi đáng tin cậy. Có thể gửi email đính chính, nhưng người nhận đã nhìn thấy nội dung đầu tiên.

### 7.4. Audit phải giữ cả hành động thuận và hành động bù

Không xóa log hoặc audit record của operation thuận khi compensation chạy. Audit nên thể hiện ai yêu cầu operation, saga ID/operation ID, LDAP target stable ID, operation thuận và kết quả, lý do compensation, actor/identity thực hiện compensation, kết quả compensation và corrective action đã phát.

Audit là lịch sử sự kiện, không phải bản sao trạng thái hiện tại. Xóa audit để tạo cảm giác rollback hoàn hảo là sai cả về kỹ thuật lẫn vận hành.

## 8. Giảm side effect bằng trạng thái pending và staged activation

Một cách giảm chi phí compensation là trì hoãn thời điểm entry trở nên hữu dụng với hệ thống khác.

Quy trình gợi ý:

1. Add entry với trạng thái pending/disabled.
2. Hoàn tất các thuộc tính cần thiết.
3. Cập nhật group membership.
4. Xác minh DN, stable ID và membership.
5. Bật account hoặc chuyển lifecycle sang active.
6. Chỉ sau khi trạng thái active được xác nhận, phát event công khai và gửi notification.

~~~mermaid
flowchart TD
    A["Add account: PENDING"] --> B["Apply required attributes"]
    B --> C["Add required group membership"]
    C --> D["Verify directory state"]
    D --> E{"All prerequisites valid?"}
    E -->|No| F["Keep pending / compensate"]
    E -->|Yes| G["Activate account"]
    G --> H{"Activation confirmed?"}
    H -->|No / unknown| I["Reconcile activation"]
    H -->|Yes| J["Publish external event"]
    J --> K["Send notification"]
~~~

### 8.1. Pending phải được consumer thực sự tôn trọng

Chỉ thêm attribute `accountLifecycle=pending` không đủ nếu các ứng dụng khác bỏ qua attribute này và vẫn coi entry là active.

Cần xác định:
- Hệ thống đăng nhập có kiểm tra lifecycle không.
- Group authorization có loại user pending khỏi quyết định không.
- Search API có lọc pending không.
- Đồng bộ downstream có bỏ qua pending không.
- Admin UI có hiển thị trạng thái pending rõ ràng không.

Nếu không thể bảo đảm mọi consumer hiểu thuộc tính, dùng cơ chế activation có semantics thật của directory hoặc giữ entry ở vùng staging/OU chưa được consumer sử dụng.

### 8.2. Active/disabled là server-specific

LDAP không có một attribute `enabled` phổ quát cho mọi server. Active Directory dùng quy tắc riêng như `userAccountControl`; các directory khác có thể dùng schema/policy khác.

Không dùng một đoạn code generic Replace `accountLifecycle` rồi tuyên bố đã disable đăng nhập nếu hệ thống xác thực không kiểm tra attribute đó.

### 8.3. Staging không loại bỏ hoàn toàn compensation

Staged activation giảm khả năng side effect xảy ra trước khi provisioning hoàn tất. Nhưng vẫn cần compensation nếu Add pending user đã tạo entry, group membership đã được thêm, một bước activation timeout, một external consumer nhìn thấy pending hoặc directory/database gặp lỗi sau khi đã ghi.

Nó giảm phạm vi phải sửa sai, không biến workflow thành transaction nguyên tử.

## 9. Thiết kế saga journal cho cả bước thuận và bước bù

Một journal hữu ích phải trả lời được:
- Bước thuận nào đã được gửi?
- Bước nào đã được xác nhận?
- Bước nào UNKNOWN?
- Compensation nào đã được lập kế hoạch?
- Compensation nào đã chạy và kết quả ra sao?
- External side effect nào đã phát?
- Còn quyền hoặc hành động thu hồi nào cần thực hiện?

Ví dụ cấu trúc:

| Field | Ý nghĩa |
| --- | --- |
| `sagaId` | ID của toàn bộ workflow |
| `operationId` | ID duy nhất của từng bước |
| `stepName` | ADD_PERSON, ADD_MEMBER, ACTIVATE, PUBLISH_EVENT |
| `forwardStatus` | PREPARED, DISPATCHING, APPLIED, REJECTED, UNKNOWN |
| `compensationStatus` | NOT_REQUIRED, PENDING, DISPATCHING, APPLIED, FAILED, UNKNOWN |
| `targetDn` | DN được thao tác |
| `stableId` | Định danh entry không đổi theo policy |
| `beforeState` | Snapshot tối thiểu cần cho compensation |
| `expectedAfterState` | Trạng thái mà bước thuận dự kiến tạo |
| `externalEffectStatus` | NOT_SENT, SENT, CONFIRMED, CORRECTION_REQUIRED |
| `attemptCount` | Số lần dispatch/reconcile/compensate |
| `lastFailureType` | Loại lỗi kỹ thuật, không chứa secret |
| `createdAt` / `updatedAt` | Thời điểm cập nhật |

### 9.1. Lưu journal trước khi gửi request

Thứ tự an toàn:

~~~text
1. Ghi saga và bước ở PREPARED.
2. Claim bước bằng compare-and-set sang DISPATCHING.
3. Gửi LDAP request.
4. Nhận success -> APPLIED.
5. Nhận LDAP error xác định -> REJECTED.
6. Mất response -> UNKNOWN.
~~~

Nếu process chết khi journal còn `DISPATCHING`, recovery worker phải xem kết quả là chưa rõ. Không được giả định request chưa rời process.

### 9.2. Snapshot cần được tối thiểu hóa

Không lưu toàn bộ `Attributes` một cách mặc định. Chỉ lưu field cần phục hồi và có căn cứ nghiệp vụ.

Ví dụ snapshot: giá trị `title` cũ, danh sách group membership mà saga dự kiến thay đổi, DN cũ trước ModifyDN, stable ID và provisioning marker, giá trị lifecycle trước/sau.

Snapshot có thể chứa dữ liệu nhân sự. Mã hóa khi lưu, giới hạn quyền truy cập và đặt retention phù hợp. Không lưu password, Bind credential hoặc token.

### 9.3. Không xóa journal khi compensation xong

Giữ record theo retention policy để audit và phân tích. Có thể xóa snapshot nhạy cảm sớm hơn, nhưng giữ event metadata và kết quả để chứng minh operation thuận đã làm gì, compensation đã làm gì, vì sao phải bù và có external side effect nào cần corrective action.

## 10. Chỉ bù bước đã xác nhận áp dụng

Một quy tắc quan trọng là không bù theo suy đoán.

| Forward status | Hành động |
| --- | --- |
| `APPLIED` | Có thể lập kế hoạch compensation nếu policy yêu cầu. |
| `REJECTED` | Không bù bước này; xử lý lỗi đã xác nhận. |
| `UNKNOWN` | Đối soát trạng thái directory trước; không bù hoặc retry mù. |
| `PREPARED` chưa dispatch | Không có side effect LDAP; có thể hủy bước. |
| `DISPATCHING` sau process crash | Xem như UNKNOWN cho tới khi có bằng chứng. |
| `CONFLICT` | Dừng tự động, không ghi đè trạng thái khác. |

### 10.1. Vì sao không bù khi UNKNOWN?

Giả sử Add group membership timeout. Nếu saga lập tức Remove member:
- Nếu Add chưa được áp dụng, Remove có thể xóa membership tồn tại từ trước.
- Nếu Add đã được áp dụng, Remove có thể đúng.
- Nếu một actor khác vừa thêm membership vì lý do khác, Remove có thể xóa quyền hợp lệ của họ.

Trước khi bù, cần xác minh member value có tồn tại và việc thêm có thuộc saga hay không. DN/member value không tự mang provenance. Có thể cần journal, marker nghiệp vụ hoặc quy tắc ownership để biết saga có quyền đảo ngược thay đổi này.

### 10.2. Compensation theo thứ tự ngược

Nếu các bước thuận là A → B → C, thường lập kế hoạch bù theo C → B → A. Nhưng thứ tự ngược chỉ là điểm bắt đầu; phải xét dependency và side effect.

Ví dụ:
- Disable account trước khi remove group membership nếu cần chặn đăng nhập ngay.
- Revoke token trước khi xóa user nếu token có thể còn dùng được.
- Remove membership trước khi Delete user nếu group schema/ACL yêu cầu.
- Giữ audit và phát corrective event sau khi đã xác định trạng thái.

Không áp dụng reverse order máy móc nếu nó tạo ra cửa sổ truy cập trái phép.

## 11. Compensation phải có precondition và idempotency

Một thao tác bù có thể được retry do timeout hoặc worker restart. Cần thiết kế để lần chạy lại không làm hỏng trạng thái mới.

### 11.1. Kiểm tra stable identity trước khi Delete

Không chỉ kiểm tra DN tồn tại. DN có thể được tái sử dụng.

Trước khi xóa entry đã tạo:
1. Lookup DN.
2. So stable ID hoặc provisioning marker.
3. Kiểm tra trạng thái hiện tại vẫn thuộc saga.
4. Kiểm tra không có thay đổi ngoài phạm vi được phép.
5. Chỉ Delete khi precondition còn đúng.

Nếu DN đã thuộc object khác, ghi CONFLICT và không xóa.

### 11.2. Dùng assertion/version khi server hỗ trợ

LDAP Assertion Control (RFC 4528) có thể gắn điều kiện vào update. Server chỉ thực hiện operation nếu filter assertion còn đúng tại thời điểm xử lý. Điều này hữu ích để tránh compensation ghi đè thay đổi đồng thời.

Ví dụ khái niệm:
- Forward Modify ghi version `provisioningVersion=7`.
- Compensation chỉ restore nếu entry vẫn có version 7.
- Nếu version đã thành 8, có actor khác đã thay đổi; không tự ghi đè.

Phải kiểm tra directory hỗ trợ Assertion Control, cách gửi control qua provider và schema/version attribute. Assertion không thay thế saga journal hoặc reconciliation sau timeout.

### 11.3. Retry compensation cũng có trạng thái UNKNOWN

Nếu Remove membership timeout:
- Không đánh dấu compensation FAILED ngay.
- Đọc lại member attribute trên endpoint phù hợp.
- Xác minh member value có còn không.
- Nếu vắng mặt và không có xung đột, có thể đánh dấu compensation APPLIED theo desired state.
- Nếu còn nhưng version đã thay đổi, ghi CONFLICT.
- Nếu chưa đủ bằng chứng, giữ UNKNOWN.

## 12. Ví dụ Java: bù membership và user có kiểm soát

Đoạn code sau minh họa các thao tác LDAP cốt lõi. Các interface journal, ownership check và event adapter là thành phần ứng dụng, không phải API có sẵn của Spring LDAP.

### 12.1. Adapter thao tác group membership

~~~java
package com.example.directory.adapter;

import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;

public class GroupMembershipAdapter {

    private final LdapTemplate ldapTemplate;

    public GroupMembershipAdapter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void addMember(Name groupDn, Name personDn) {
        ModificationItem add = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", personDn.toString()));

        ldapTemplate.modifyAttributes(
                groupDn,
                new ModificationItem[] { add });
    }

    public void removeMember(Name groupDn, Name personDn) {
        ModificationItem remove = new ModificationItem(
                DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("member", personDn.toString()));

        ldapTemplate.modifyAttributes(
                groupDn,
                new ModificationItem[] { remove });
    }
}
~~~

Adapter này giả định group schema cho phép thao tác `member` tương ứng. Với `groupOfNames`, cần xét ràng buộc member cuối cùng. Với Active Directory, kiểm tra schema, ACL và semantics group thực tế.

### 12.2. Ownership check trước khi Delete user

~~~java
public void deleteProvisionedPerson(
        Name personDn,
        String expectedProvisioningId) {

    PersonSnapshot current = personReader.read(personDn);

    if (!expectedProvisioningId.equals(
            current.provisioningId())) {
        throw new CompensationConflictException(
                "Entry no longer belongs to this saga");
    }

    if (current.hasSubordinateEntries()) {
        throw new CompensationConflictException(
                "Entry is no longer a leaf");
    }

    ldapTemplate.unbind(personDn);
}
~~~

`PersonSnapshot`, `personReader` và `CompensationConflictException` là kiểu/adapter do ứng dụng định nghĩa. Kiểm tra ownership phải dựa trên attribute hoặc stable ID có trong schema và được bảo vệ khỏi thay đổi trái phép.

Delete LDAP thông thường chỉ áp dụng cho entry lá. Nếu entry đã có children, không tự chuyển sang recursive delete để làm compensation.

### 12.3. Orchestrator với trạng thái rõ ràng

~~~java
public ProvisioningResult provision(PersonCommand command) {
    Saga saga = journal.prepare(command);

    try {
        journal.claimStep(saga.id(), "ADD_PERSON");
        personDirectory.createPending(command, saga.id());
        journal.markApplied(saga.id(), "ADD_PERSON");

        journal.claimStep(saga.id(), "ADD_GROUP_MEMBER");
        groupDirectory.addMember(
                command.groupDn(), command.personDn());
        journal.markApplied(saga.id(), "ADD_GROUP_MEMBER");

        journal.claimStep(saga.id(), "ACTIVATE_PERSON");
        personDirectory.activate(command.personDn());
        journal.markApplied(saga.id(), "ACTIVATE_PERSON");

        journal.markDirectoryReady(saga.id());
        outbox.enqueuePersonProvisioned(saga.id(), command);
        return ProvisioningResult.accepted(saga.id());

    } catch (WriteOutcomeUnknownException unknown) {
        journal.markNeedsReconciliation(
                saga.id(), unknown.operationId());
        return ProvisioningResult.pending(saga.id());

    } catch (ConfirmedDirectoryFailure failure) {
        compensationCoordinator.compensateConfirmedSteps(
                saga.id(), failure);
        return ProvisioningResult.failedOrCompensating(saga.id());
    }
}
~~~

Đây là skeleton minh họa; cần triển khai transaction của journal, compare-and-set claim, exception classification và recovery worker. Không bắt mọi `RuntimeException` rồi coi là `ConfirmedDirectoryFailure`. Lỗi transport hoặc lỗi không xác định có thể mang kết quả UNKNOWN.

### 12.4. Không phát event trước khi directory sẵn sàng

`outbox.enqueuePersonProvisioned` chỉ được gọi sau khi các bước directory cần thiết đã được xác nhận. Worker phát event cần:
- Dùng event ID ổn định.
- Retry publish theo outbox status.
- Yêu cầu consumer deduplicate.
- Có event corrective nếu saga đã công bố rồi mới phải bù.
- Không xóa event gốc khỏi audit khi phát event sửa sai.

Outbox giúp phát event đáng tin cậy từ database, nhưng không tạo transaction nguyên tử chung giữa database và LDAP. Nếu LDAP đã commit mà journal/outbox database update thất bại, recovery worker vẫn phải đối soát LDAP trước khi quyết định tiếp tục.

## 13. Side effect bên ngoài: dùng event điều chỉnh, không giả vờ xóa lịch sử

Giả sử event `PersonProvisioned` đã tới consumer. Consumer cấp license và gửi email. Sau đó saga phát hiện group membership không đúng và phải disable account.

Không thể:
- Thu hồi event đã được consumer xử lý khỏi lịch sử.
- Bảo đảm email biến mất khỏi inbox.
- Tự thu hồi license nếu consumer không hỗ trợ.
- Xóa audit record của consumer.
- Thu hồi token chỉ bằng cách xóa entry LDAP.

Cần một hợp đồng corrective event, ví dụ:
- `PersonProvisioningRevoked`.
- `PersonAccessSuspended`.
- `GroupMembershipCorrectionRequested`.
- `CredentialResetRequired`.

Event sửa sai cần chứa:
- `sagaId` và `eventId`.
- Resource stable ID.
- Trạng thái mới có hiệu lực.
- Version/sequence để consumer bỏ qua event cũ đến muộn.
- Lý do ở mức được phép công khai.
- Thời điểm và correlation ID.

Consumer phải xử lý idempotent và không áp dụng event cũ hơn trạng thái mới nhất. Nếu event bus không bảo đảm ordering, dùng version hoặc sequence do ứng dụng quản lý.

## 14. Outbox, journal và ranh giới database/LDAP

Transactional outbox thường được dùng để lưu event trong cùng transaction database với thay đổi business record, sau đó worker publish event. Tuy nhiên, LDAP không tham gia transaction database đó theo mặc định.

Một trình tự có thể là:

1. Tạo saga journal trong database.
2. Gửi Add/Modify LDAP.
3. Xác nhận hoặc reconcile trạng thái LDAP.
4. Cập nhật journal thành directory ready.
5. Ghi outbox event trong database.
6. Worker publish event.
7. Cập nhật event delivery status.

Nếu saga journal và outbox cùng nằm trong một database, hãy cập nhật trạng thái directory-ready và insert outbox record trong **cùng một database transaction**. Như vậy hai thay đổi database hoặc cùng commit hoặc cùng rollback. Transaction này vẫn không bao gồm LDAP: directory có thể đã commit trước khi database transaction bắt đầu hoặc trong lúc ứng dụng đang xử lý response.

Có thể xảy ra crash sau bước 2 nhưng trước bước 4. Khi đó journal còn trạng thái chưa hoàn tất; recovery worker phải đọc LDAP để xác định thực tế. Không được tạo event `PersonProvisioned` chỉ vì database có record PREPARED.

Có thể xảy ra crash sau bước 5 nhưng trước bước 6. Outbox worker sẽ publish lại. Consumer cần idempotency để không cấp license hoặc gửi email hai lần.

### 14.1. Không gửi email đồng bộ giữa các LDAP writes

Nếu gửi email ngay sau Add nhưng trước khi membership/activation hoàn tất, người dùng có thể nhận lời mời vào một account chưa sẵn sàng.

Nên:
- Tạo notification intent trong journal.
- Chỉ dispatch sau khi directory state đã xác nhận.
- Dùng notification ID ổn định.
- Nếu đã gửi và phải bù, gửi email điều chỉnh theo policy.
- Không gửi lại welcome email chỉ vì worker retry sau crash.

### 14.2. Outbox không thu hồi token hoặc session

Nếu event consumer cấp token/session, compensation phải gọi API thu hồi tương ứng. Token JWT đã ký và không có introspection/revocation list có thể còn hiệu lực đến expiration. Cần thiết kế TTL, revocation và authorization check phù hợp từ đầu.

## 15. Chọn chiến lược: hard delete, disable hay giữ pending?

Không phải lỗi nào cũng cần xóa entry.

| Chiến lược | Ưu điểm | Chi phí/rủi ro |
| --- | --- | --- |
| Hard delete | Entry biến mất khỏi nhánh directory | Khó khôi phục identity, cần Delete ACL, tham chiếu có thể còn, audit vẫn tồn tại |
| Disable/suspend | Giữ entry và stable identity, có thể ngăn đăng nhập nếu server/consumer hỗ trợ | Cần quyền Modify, phải thu hồi session/token, consumer phải tôn trọng trạng thái |
| Giữ pending | Trì hoãn side effect và công bố | Cần lifecycle state và mọi consumer hiểu pending |
| Tombstone/soft delete | Giữ dấu vết để đối soát/khôi phục | Cần schema, retention, ACL và quy trình purge |
| Manual remediation | Tránh tự động phá hủy khi trạng thái mơ hồ | Tốn thời gian vận hành và cần người có thẩm quyền |

### 15.1. Khi nào hard delete phù hợp?

Có thể phù hợp khi entry mới tạo chỉ thuộc saga, chưa được sử dụng bởi consumer khác, không có child entry, group reference đã được xử lý, chính sách retention cho phép và có bằng chứng entry vẫn có stable ID của saga.

### 15.2. Khi nào disable/suspend phù hợp hơn?

Thường phù hợp khi account đã được công bố hoặc có thể đã đăng nhập, không thể khôi phục đầy đủ sau Delete, cần giữ identity để audit/đối soát, có session/token cần thu hồi riêng và directory có semantics disable đáng tin cậy.

### 15.3. Khi nào nên dừng và yêu cầu xử lý thủ công?

- Entry DN đã được tái sử dụng.
- Snapshot không đầy đủ.
- Concurrent update không thể phân biệt.
- Compensation cần quyền ngoài phạm vi policy.
- Một event không thể đảo ngược đã kích hoạt hệ thống downstream không hỗ trợ correction.
- Operation hoặc compensation vẫn UNKNOWN sau thời gian đối soát cho phép.

Không ép mọi saga phải kết thúc bằng success hoặc rolled back. `MANUAL_REVIEW`/`NEEDS_REMEDIATION` là trạng thái vận hành hợp lệ.

## 16. Bảng tình huống: chi phí và tác động quan sát

| Tình huống | Chi phí compensation | Quyền bổ sung | Side effect có thể đã nhìn thấy |
| --- | --- | --- | --- |
| Add user rồi group Modify thất bại | Lookup ownership, Delete/Disable user, journal | Read + Delete/Modify | Entry có thể đã được Search hoặc đồng bộ |
| Add member rồi activation lỗi | Read group, Remove member, kiểm tra member cuối | Read + Modify member | Quyền truy cập có thể đã được cấp |
| Modify title rồi bước DB lỗi | Snapshot, compare, restore | Read + Modify title | UI/cache có thể đã hiển thị title mới |
| Delete user rồi downstream lỗi | Recreate hoặc manual restore | Add + Modify + quyền tạo credential | Audit, replica, tham chiếu đã thay đổi |
| Rename rồi consumer lỗi | Lookup hai DN, rename ngược | Read + Rename/Move | Consumer có thể đã lưu DN mới |
| Enable account rồi notification lỗi | Disable, revoke session/token | Modify status + quyền revoke | Người dùng có thể đã đăng nhập |
| Event đã publish rồi saga thất bại | Publish corrective event, consumer retry | Publish corrective event | Consumer đã xử lý event gốc |
| Email đã gửi rồi membership rollback | Gửi thông báo điều chỉnh | Notification send | Người nhận đã đọc email |
| Password đã đổi rồi workflow lỗi | Reset/rotate credential, revoke sessions | Password operation + session revoke | Người dùng có thể thử password mới |
| Compensation timeout | Reconcile và retry có điều kiện | Read + quyền bù | Trạng thái directory chưa rõ |

## 17. Xử lý compensation thất bại

Compensation cần state machine riêng:

~~~mermaid
stateDiagram-v2
    [*] --> NOT_REQUIRED
    NOT_REQUIRED --> PENDING: forward step confirmed
    PENDING --> DISPATCHING: claim compensation
    DISPATCHING --> APPLIED: compensation success confirmed
    DISPATCHING --> FAILED: confirmed rejection
    DISPATCHING --> UNKNOWN: timeout / connection lost
    UNKNOWN --> APPLIED: reconciliation proves desired state
    UNKNOWN --> PENDING: proven not applied and safe to retry
    UNKNOWN --> CONFLICT: state changed by another actor
    FAILED --> MANUAL_REVIEW: retry policy exhausted
    CONFLICT --> MANUAL_REVIEW
    APPLIED --> [*]
~~~

### 17.1. Compensation retry không giống forward retry

Compensator cần biết forward step nào đã được xác nhận, compensation có thể chạy nhiều lần không, precondition nào phải còn đúng, side effect downstream nào đã được phát và có thể retry tự động hay cần phê duyệt.

Không retry liên tục khi ACL từ chối hoặc schema violation. Những lỗi này cần sửa policy hoặc thay đổi kế hoạch.

### 17.2. Timeout khi bù

Nếu `removeMember` timeout, group có thể đã được cập nhật. Đọc lại member attribute trước khi gửi Remove lần nữa. Nếu membership đã vắng, ghi desired state achieved. Nếu còn nhưng group version thay đổi hoặc actor khác thêm lại member, ghi conflict.

### 17.3. Không dùng compensation để che lỗi

Không bắt lỗi rồi ghi log “rollback complete” nếu chỉ một phần action đã chạy. Saga cần có kết quả trung thực:
- `COMPENSATED`.
- `PARTIALLY_COMPENSATED`.
- `COMPENSATION_UNKNOWN`.
- `MANUAL_REVIEW`.
- `FORWARD_COMPLETED`.
- `FORWARD_UNKNOWN`.

## 18. Kiểm thử chi phí, quyền và side effect

Unit test chỉ kiểm tra method được gọi không chứng minh ACL, directory semantics hoặc consumer thực sự nhìn thấy gì. Cần test integration với LDAP server và test doubles cho các hệ thống bên ngoài.

### 18.1. Test ACL writer và compensator riêng

Tạo hai Bind identity:
- Writer chỉ có quyền cần thiết để Add user và Modify membership.
- Compensator có quyền bù trong OU test.

Kiểm thử:
1. Writer Add user thành công.
2. Writer thử Delete user và bị ACL từ chối nếu policy không cấp quyền đó.
3. Compensator Delete đúng entry fixture thành công.
4. Compensator thử xóa entry ngoài OU và bị từ chối.
5. Reader không có quyền Modify/Delete.
6. Không test bằng rootdn/Domain Admin.

### 18.2. Test membership và schema

Với group `groupOfNames`:
- Thêm một member mới.
- Remove member vừa thêm khi group còn member khác.
- Thử remove member cuối cùng và xác minh schema behavior.
- Mô phỏng actor khác thêm member giữa forward và compensation.
- Xác minh compensator không xóa membership ngoài ownership.

### 18.3. Test external visibility

Dùng fake consumer/event recorder:
- Trước activation, consumer không nhận `PersonProvisioned`.
- Sau khi directory state được xác nhận, event được enqueue.
- Khi outbox worker restart, event có thể publish lại nhưng consumer deduplicate.
- Nếu saga bị bù sau khi event đã publish, corrective event được phát.
- Email notification không bị gửi lặp.
- Token/session service nhận yêu cầu revoke khi policy cần.

### 18.4. Ma trận test

| Kịch bản | Kỳ vọng |
| --- | --- |
| Add user success, Add member rejected | Compensation chỉ xử lý user đã xác nhận Add |
| Add member timeout | Reconcile group trước khi Remove member hoặc bù user |
| Activation success, event publish fail | Directory state giữ đúng; outbox retry |
| Event đã publish, bước sau thất bại | Corrective event, không xóa audit/event gốc |
| Delete compensation gặp ACL denial | Saga chuyển FAILED/MANUAL_REVIEW |
| Compensation timeout sau khi server áp dụng | Reconcile desired state trước retry |
| Entry bị actor khác sửa | Precondition fail, ghi CONFLICT |
| DN được tái sử dụng | Không xóa object mới |
| GroupOfNames còn member cuối | Không vi phạm schema khi bù |
| Password operation đã thành công | Không tìm cách khôi phục secret cũ; reset/revoke theo policy |
| Notification worker restart | Không gửi email hai lần cho cùng notification ID |
| Process crash sau LDAP commit | Journal recovery đối soát LDAP |
| Replica lag | Không kết luận operation thất bại từ replica chưa đồng bộ |
| Audit write thất bại | Không tuyên bố compensation hoàn tất nếu audit bắt buộc chưa ghi |
| Consumer nhận event cũ đến muộn | Version/sequence ngăn ghi đè trạng thái mới |

## 19. Quan sát và vận hành

Để đánh giá chi phí thực, theo dõi các chỉ số:

| Metric | Ý nghĩa |
| --- | --- |
| `saga.compensation.started` | Số lần bắt đầu bù |
| `saga.compensation.applied` | Số compensation đã xác nhận |
| `saga.compensation.failed` | Số compensation bị từ chối |
| `saga.compensation.unknown` | Số compensation chưa rõ kết quả |
| `saga.compensation.duration` | Thời gian hoàn tất bù |
| `saga.compensation.manual_review` | Số saga cần người xử lý |
| `ldap.compensation.read.count` | Số lookup/search bổ sung |
| `ldap.compensation.write.count` | Số LDAP write bổ sung |
| `saga.external_correction.count` | Số corrective event/notification |
| `saga.pending.age` | Tuổi saga chưa hoàn tất |

Theo dõi thêm tỷ lệ saga cần compensation, số LDAP request trung bình cho một provisioning, tỷ lệ compensation thành công theo operation type, tỷ lệ conflict do concurrent update, số event/email đã phát trước khi phải sửa sai, thời gian từ UNKNOWN tới reconciliation và số saga cần manual review.

Không dùng UID, email hoặc DN cá nhân làm metric label vì có thể tạo cardinality lớn và làm lộ dữ liệu. Log có correlation ID và resource key đã được bảo vệ theo chính sách.

### 19.1. Audit compensation

Audit record cần giữ cả hai phía:

~~~text
sagaId: 7c1...
step: ADD_GROUP_MEMBER
forwardStatus: APPLIED
compensationStatus: APPLIED
actor: svc-directory-compensator
target: person-key:EMP-2048
reason: activation prerequisite failed
externalCorrection: NOT_REQUIRED
~~~

Không ghi toàn bộ attributes hoặc password vào audit. DN và stable ID cũng cần được phân loại theo chính sách dữ liệu của tổ chức.

## 20. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi compensation là rollback | Kỳ vọng trạng thái kỹ thuật quay lại hoàn toàn | Mô tả desired state và giới hạn khôi phục |
| Cấp writer quyền Delete toàn directory | Tăng blast radius | Tách identity và giới hạn subtree |
| Dùng admin để bù khi ACL từ chối | Che lỗi policy, tạo đường leo thang quyền | Dừng và xử lý theo quyền đã phê duyệt |
| Không lưu snapshot trước Modify | Không biết giá trị cũ để restore | Snapshot tối thiểu trước write |
| Restore snapshot mà không kiểm tra version | Ghi đè concurrent update | Assertion/precondition và conflict |
| Delete rồi Add lại để giả rollback | Mất operational metadata/identity | Re-provision hoặc giữ tombstone |
| Bù ngay khi forward UNKNOWN | Có thể đảo ngược operation chưa xảy ra hoặc xóa dữ liệu của actor khác | Reconcile trước |
| Remove member cuối groupOfNames | Schema violation | Xác định policy group rỗng/retention |
| Xóa entry có child bằng recursive delete mặc định | Có thể xóa cả subtree ngoài ý muốn | Chỉ Delete leaf; workflow subtree riêng |
| Nghĩ Remove member thu hồi mọi quyền đã cấp | Session/token/cache có thể còn hiệu lực | Revoke ở hệ thống authorization |
| Nghĩ gửi corrective event xóa event cũ | Consumer đã xử lý event gốc | Event điều chỉnh có version/idempotency |
| Gửi email trước khi provisioning hoàn tất | Người dùng thấy trạng thái chưa sẵn sàng | Staged activation và notification sau xác nhận |
| Xóa audit khi bù | Mất lịch sử và không thể điều tra | Audit append-only |
| Nghĩ outbox tạo transaction LDAP+DB | Có khoảng trống giữa LDAP và database | Saga journal + reconciliation |
| Không theo dõi compensation timeout | Saga bị kẹt hoặc bù hai lần | Compensation state machine |
| Không tính chi phí Read snapshot | ACL và dữ liệu lưu trữ không đủ | Quy hoạch quyền, snapshot và retention |
| Coi Disable account là thu hồi token | Token/session cũ vẫn dùng được | Tích hợp revocation riêng |
| Bù mọi bước theo thứ tự ngược máy móc | Có thể mở cửa sổ truy cập hoặc vi phạm dependency | Thiết kế dependency và thứ tự theo nghiệp vụ |

## 21. Checklist thiết kế compensation

| Hạng mục | Câu hỏi cần trả lời |
| --- | --- |
| Business outcome | Trạng thái cuối nào được xem là an toàn/chấp nhận được? |
| Forward steps | Bước nào có thể commit độc lập? |
| Compensation | Hành động bù cụ thể cho từng bước là gì? |
| Non-invertible data | Có password, operational attribute hoặc identity không thể restore không? |
| Snapshot | Attribute nào phải đọc/lưu trước khi ghi? |
| Retention | Snapshot/journal giữ bao lâu và ai truy cập? |
| Privileges | Writer và compensator cần quyền nào trên từng subtree/attribute? |
| Least privilege | Có thể giới hạn quyền bù theo OU/operation không? |
| Ownership | Làm sao chứng minh entry/value thuộc saga trước khi bù? |
| Concurrency | Có version/assertion/precondition không? |
| UNKNOWN | Đối soát ở đâu và bao lâu trước khi manual review? |
| External effects | Consumer, email, token, cache, audit đã nhìn thấy gì? |
| Corrective action | Có event revoke/correction hoặc API thu hồi không? |
| Activation | Có thể giữ pending/disabled cho tới khi hoàn tất không? |
| Idempotency | Retry compensation có an toàn không? |
| Audit | Có giữ cả forward và compensation event không? |
| Testing | Đã test ACL, concurrency, partial failure, timeout và side effect chưa? |
| Operations | Ai xử lý saga PARTIAL/UNKNOWN/MANUAL_REVIEW? |

## 22. Bài tập thực hành

**Bài 1 — Tính chi phí Add/compensate.** Tạo một user pending, sau đó cố ý làm bước Add group member thất bại. Liệt kê số LDAP read/write, quyền bổ sung và journal record cần có để Delete user an toàn.

**Bài 2 — So sánh writer/compensator.** Tạo hai Bind DN với ACL khác nhau. Chứng minh writer có thể Add trong OU test nhưng không Delete; compensator chỉ Delete trong OU được giao. Xác minh cả hai đều không có quyền trên OU khác.

**Bài 3 — Snapshot và restore.** Đọc `title` trước Modify, ghi giá trị mới rồi giả lập bước sau thất bại. Restore giá trị cũ nếu version không đổi; tạo concurrent update để xác minh compensation chuyển CONFLICT thay vì ghi đè.

**Bài 4 — Group membership.** Add một DN vào group, sau đó bù bằng Remove đúng member. Thử trường hợp member cuối của `groupOfNames` và xác định policy phù hợp với schema.

**Bài 5 — Delete không hoàn hảo.** Tạo user có stable ID, xóa rồi thử tạo lại cùng DN. So sánh operational metadata và giải thích vì sao đây là re-provisioning thay vì rollback.

**Bài 6 — Rename compensation.** Rename một entry rồi tạo entry khác tại DN cũ. Khi saga yêu cầu rename ngược, compensator phải phát hiện collision và chuyển MANUAL_REVIEW.

**Bài 7 — Password side effect.** Mô phỏng password change thành công nhưng bước membership thất bại. Thiết kế quy trình disable/reset/revoke session; tuyệt đối không lưu plaintext password trong journal.

**Bài 8 — External event.** Publish `PersonProvisioned` cho consumer giả, sau đó buộc saga compensation. Phát corrective event và xác minh consumer giữ trạng thái mới nhất, không xóa event/audit cũ.

**Bài 9 — Outbox crash.** Dừng worker sau khi event đã publish nhưng trước khi đánh dấu delivered. Khởi động lại, xác minh consumer deduplicate theo event ID.

**Bài 10 — Compensation UNKNOWN.** Làm proxy drop response sau khi LDAP đã Remove membership. Recovery worker phải đọc lại group, xác nhận member vắng mặt rồi mới đánh dấu compensation APPLIED.

**Bài 11 — Pending activation.** Tạo entry pending, xác minh các consumer không cấp quyền, sau đó kích hoạt và mới phát event. Kiểm tra một consumer cố tình bỏ qua lifecycle attribute để thấy vì sao pending phải được tất cả consumer tôn trọng.

**Bài 12 — Cost review.** Đo số LDAP operations và thời gian của workflow bình thường so với workflow phải bù. Đánh giá liệu staged activation, tombstone hoặc manual remediation có giảm chi phí và side effect không.

## 23. Câu hỏi tự đánh giá

1. Compensation khác rollback ở điểm nào?
2. Vì sao Add rồi Delete không khôi phục chính xác entry cũ?
3. Chi phí nào phát sinh khi phải snapshot attribute trước Modify?
4. Vì sao snapshot cần retention và bảo vệ dữ liệu?
5. Writer có quyền Add thì có mặc nhiên có quyền Delete không?
6. OpenLDAP ACL liên quan entry và children như thế nào khi Delete?
7. Vì sao compensator có thể cần quyền Read mà writer không cần?
8. Vì sao không nên dùng rootdn/Domain Admin để bù?
9. Khi nào Remove member là compensation phù hợp?
10. Vì sao groupOfNames có thể từ chối xóa member cuối cùng?
11. Vì sao Delete rồi Add lại không phải restore hoàn hảo?
12. Những rủi ro nào có thể xảy ra khi Rename ngược?
13. Vì sao password không thể được khôi phục từ snapshot thông thường?
14. Group membership đã được consumer dùng có thể tạo side effect gì?
15. Vì sao Disable account không nhất thiết thu hồi session/token?
16. Event đã publish có thể được “undo” như thế nào?
17. Vì sao không được xóa audit event gốc khi compensation?
18. Pending state cần được consumer tôn trọng ra sao?
19. Outbox có tạo transaction nguyên tử giữa LDAP và database không?
20. Vì sao phải đối soát forward step UNKNOWN trước khi bù?
21. Compensation cần precondition/version check để tránh vấn đề gì?
22. Khi nào saga nên chuyển MANUAL_REVIEW?
23. Vì sao compensation cũng cần state machine và idempotency?
24. Những metric nào cho thấy chi phí compensation đang tăng?

**Ghi nhớ:** trước khi thiết kế compensation, hãy tính cả thao tác đọc/ghi bổ sung, snapshot, quyền Delete/Modify/restore, chi phí journal và side effect bên ngoài. Chỉ bù operation đã được xác nhận hoặc đã được đối soát; dùng stable identity và precondition để tránh đảo ngược thay đổi của actor khác. Account pending, outbox, corrective event, session revocation và audit append-only giúp giảm tác động nhìn thấy, nhưng không biến nhiều hệ thống thành một transaction nguyên tử.

### Tài liệu tham khảo

- [Spring LDAP — LdapOperations API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html): các thao tác Bind, Modify, Rename và Unbind được dùng trong luồng thuận/bù.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): thao tác LDAP và quản lý context.
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): Bind, Modify Attributes, Rebind, Rename và Unbind.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): semantics Add, Modify, Delete, ModifyDN và giới hạn của operation LDAP.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528.html): điều kiện assertion để bảo vệ update khỏi concurrent modification.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): entry, DN, attribute, schema và operational attributes.
- [RFC 4519 — LDAP Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519.html): schema groupOfNames và thuộc tính member.
- [OpenLDAP Administrator's Guide — Access Control](https://www.openldap.org/doc/admin26/access-control.html): ACL, quyền entry/children và kiểm soát thao tác directory.
- [OpenLDAP — Referential Integrity Overlay](https://www.openldap.org/software/man.cgi?query=slapo-refint): cơ chế duy trì một số DN references khi entry bị Delete hoặc Rename.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction abstraction và giới hạn resource participation.
- [Transactional Outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html): lưu event bền vững và phát lại theo cơ chế outbox.
- [Microsoft Learn — Active Directory Security](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/plan/security-best-practices/understanding-security-groups): security groups và quyền truy cập trong Active Directory.
