# Giao dịch bù trừ không phục hồi đầy đủ khi gặp sự cố

Trong **Spring Data LDAP**, một service có thể gọi nhiều thao tác repository hoặc LdapTemplate để cập nhật entry, membership và cấu trúc directory. ContextSourceTransactionManager của Spring LDAP hỗ trợ giao dịch bù trừ phía client: thư viện ghi nhận trạng thái trước mỗi thao tác và thực hiện operation ngược khi Spring yêu cầu rollback.

Cơ chế này giúp phục hồi nhiều lỗi nghiệp vụ thông thường, nhưng không tạo transaction ACID trên LDAP server. Server không biết ranh giới transaction, không khóa entry cho transaction và không giữ một bản commit log để client phục hồi sau khi JVM dừng. Mất kết nối, process crash, concurrent update, quyền thay đổi hoặc lỗi ngay trong pha commit/rollback đều có thể khiến directory chỉ được phục hồi một phần.

Bài học này hướng dẫn cách nhận diện những tình huống đó, xác định dữ liệu đang ở trạng thái nào và xây dựng quy trình đối soát/phục hồi có kiểm soát. Trọng tâm là **không nhầm yêu cầu rollback với bằng chứng rằng rollback đã thành công**.

Sau bài học, bạn có thể:

- Mô tả recording, preparation, commit và rollback của Spring LDAP.
- Phân biệt rollback thành công, rollback thất bại và kết quả không xác định.
- Phân tích failure window của bind, unbind, rebind, rename và modifyAttributes.
- Tìm nguyên nhân từ network failure, process crash, ACL, schema, DN collision và concurrent writes.
- Hiểu vì sao operation bù trừ có thể ghi đè thay đổi hợp lệ của client khác.
- Thiết kế operation journal, reconciliation và manual recovery.
- Kiểm thử lỗi giữa từng bước và kiểm chứng trạng thái directory sau cùng.

## 1. Điều gì có nghĩa là giao dịch bù trừ không phục hồi đầy đủ?

Một transaction được coi là phục hồi đầy đủ khi trạng thái directory sau rollback khớp với trạng thái nghiệp vụ trước transaction, trong phạm vi dữ liệu mà ứng dụng cam kết quản lý. Với LDAP compensating transaction, kết quả này chỉ đạt được nếu mọi operation cần bù trừ đều được ghi nhận, client còn liên lạc được với server, operation ngược vẫn hợp lệ và không có tác nhân khác làm thay đổi trạng thái liên quan.

Các biểu hiện thường gặp:

- Service ném exception sau khi đã ghi một hoặc nhiều entry.
- Spring báo rollback hoặc phát sinh lỗi trong quá trình rollback.
- Entry được rename sang DN tạm nhưng không quay về DN ban đầu.
- Entry mới đã được bind tại DN cũ, trong khi bản cũ vẫn còn ở staging subtree.
- Attribute đã được sửa nhưng modification ngược bị từ chối.
- Một số thao tác được hoàn tác, một số thao tác khác vẫn còn hiệu lực.
- JVM dừng giữa transaction; sau khi khởi động lại, directory giữ trạng thái trung gian nhưng transaction manager không còn stack operation trong bộ nhớ.
- Client nhận timeout và không biết operation cuối cùng đã được áp dụng hay chưa.

### 1.1. Phân biệt ba kết quả

| Kết quả | Điều có thể kết luận | Trạng thái ứng dụng nên ghi |
| --- | --- | --- |
| Rollback được xác nhận | Các operation bù trừ cần thiết đã trả thành công và trạng thái sau đó được xác minh | COMPENSATED |
| Rollback thất bại rõ ràng | Một operation bù trừ trả lỗi xác định, ví dụ insufficient access hoặc DN conflict | COMPENSATION_FAILED |
| Kết quả không xác định | Mất kết nối/timeout khi operation bù trừ có thể đã tới server | UNKNOWN hoặc RECONCILIATION_REQUIRED |

Không suy ra COMPENSATED chỉ từ việc method ném exception. Exception có thể là lỗi nghiệp vụ ban đầu; operation rollback sau đó cũng có thể thất bại. Tương tự, không coi mọi lỗi rollback là bằng chứng directory chắc chắn còn sai: response có thể bị mất sau khi server đã thực hiện operation.

### 1.2. Một ví dụ đơn giản

Ứng dụng cần tạo nhân viên và thêm nhân viên vào nhóm:

~~~text
1. bind uid=lan,ou=people
2. modify cn=engineering,ou=groups
3. gửi event "employee-created"
~~~

Nếu bước 2 thất bại, Spring có thể cố unbind entry vừa tạo ở bước 1. Nhưng nếu server đã xóa entry và response của operation bù trừ bị mất, ứng dụng không thể khẳng định trạng thái chỉ dựa vào exception. Nếu bước 3 đã gửi event ra message broker, rollback LDAP cũng không thu hồi event đó.

Giao dịch bù trừ chỉ điều phối các LDAP operation đã được proxy ghi nhận. Nó không tự đảo ngược side effect ở hệ thống bên ngoài.

## 2. Cơ chế Spring LDAP ghi nhận và hoàn tác operation

ContextSourceTransactionManager là một PlatformTransactionManager. Nó làm việc cùng TransactionAwareContextSourceProxy để các modifying operation đi qua LdapTemplate được ghi nhận trong transaction.

Với một transaction, mỗi operation có thể trải qua bốn pha:

1. **Recording:** đọc/ghi nhận thông tin cần thiết để tạo operation bù trừ.
2. **Preparation:** thực hiện operation ban đầu hoặc đưa entry vào trạng thái tạm.
3. **Commit:** hoàn tất phần việc còn chờ, ví dụ xóa entry đã được chuyển sang DN tạm.
4. **Rollback:** chạy operation ngược để cố phục hồi trạng thái ban đầu.

### 2.1. Những operation được hỗ trợ

| LDAP operation | Preparation | Commit | Rollback |
| --- | --- | --- | --- |
| bind | Tạo entry tại DN đích | Không cần thao tác thêm | unbind entry vừa tạo |
| rename | Đổi DN | Không cần thao tác thêm | Rename về DN ban đầu |
| unbind | Rename entry sang DN tạm | Xóa entry tại DN tạm | Rename entry về DN ban đầu |
| rebind | Rename entry cũ sang DN tạm | Bind entry mới ở DN gốc rồi xóa entry tạm | Rename entry cũ về DN gốc |
| modifyAttributes | Áp dụng thay đổi attribute | Không cần thao tác thêm | Gửi modification ngược |

Không phải mọi operation đều được xử lý bằng cách xóa rồi tạo lại. unbind và rebind dùng DN tạm vì client có thể không đọc được toàn bộ attribute của entry để dựng lại chính xác. Với modifyAttributes, Spring LDAP tạo các ModificationItem bù trừ dựa trên thông tin ghi nhận trước operation.

### 2.2. Operation manager giữ stack bù trừ

Implementation mặc định DefaultCompensatingTransactionOperationManager quản lý một stack các CompensatingTransactionOperationExecutor và thực hiện rollback theo thứ tự ngược với thứ tự operation đã ghi nhận.

Ví dụ:

~~~text
Preparation:
  A. bind user
  B. modify group
  C. rename profile

Rollback theo thứ tự ngược:
  C. rename profile về DN cũ
  B. khôi phục group
  A. unbind user
~~~

Thứ tự ngược giúp xử lý dependency theo kiểu stack. Tuy nhiên, nó không tạo isolation và không bảo đảm mọi operation ngược sẽ thành công. Khi một bước rollback gặp lỗi, hãy xem exception/log cụ thể và đối soát directory; không tự giả định các bước còn lại đã hoàn tất.

### 2.3. Transaction manager và proxy phải dùng cùng ContextSource

Wiring quan trọng:

~~~text
ContextSource gốc
       |
       +----------------------> ContextSourceTransactionManager
       |
       +--> TransactionAwareContextSourceProxy
                    |
                    v
                LdapTemplate
                    |
                    v
              LDAP operations
~~~

ContextSourceTransactionManager nhận ContextSource gốc. LdapTemplate nhận TransactionAwareContextSourceProxy bọc quanh chính ContextSource đó. Proxy giữ DirContext trong transaction và ghi nhận các modifying operation.

Nếu LdapTemplate dùng context source khác, hoặc một số thao tác đi qua context source gốc/raw JNDI context, các thao tác đó có thể nằm ngoài transaction bù trừ.

### 2.4. Transaction nên bao quanh service nghiệp vụ

Ranh giới transaction thường nên nằm ở service thực hiện một use case:

~~~java
@Service
public class EmployeeProvisioningService {

    private final LdapTemplate ldapTemplate;

    public EmployeeProvisioningService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Transactional(transactionManager = "ldapTxManager",
                   rollbackFor = Exception.class)
    public void provision(EmployeeEntry employee) throws Exception {
        ldapTemplate.create(employee);
        addEmployeeToDefaultGroup(employee);
        updateProvisioningMarker(employee);
    }
}
~~~

Đây là ví dụ minh họa ranh giới service. ldapTemplate phải được cấu hình qua transaction-aware proxy và cùng target ContextSource với manager. rollbackFor = Exception.class làm rõ chính sách nếu method có thể ném checked exception; nếu chỉ dùng mặc định của Spring, checked exception không tự động kích hoạt rollback.

Không bắt exception rồi trả kết quả thành công bên trong method transactional nếu vẫn muốn rollback:

~~~java
@Transactional(transactionManager = "ldapTxManager")
public boolean provision(EmployeeEntry employee) {
    try {
        ldapTemplate.create(employee);
        updateGroups(employee);
        return true;
    } catch (DataAccessException ex) {
        log.error("Provision failed", ex);
        return false; // Spring sees a normal return
    }
}
~~~

Trong ví dụ này, exception đã bị nuốt và method trả bình thường. Nếu cần xử lý tại chỗ, phải đánh dấu transaction rollback-only bằng cơ chế Spring phù hợp hoặc ném exception ra khỏi ranh giới transactional. Cũng cần nhớ self-invocation trong cùng bean có thể bỏ qua proxy transaction.

## 3. Vì sao rollback có thể không khôi phục đầy đủ?

Rollback bù trừ là một chuỗi LDAP operation mới. Nó chịu mọi điều kiện mạng, ACL, schema, naming context và cạnh tranh dữ liệu như operation thông thường.

### 3.1. Mất kết nối trước hoặc trong rollback

~~~text
Application                  LDAP server
    |                            |
    | 1. bind / modify            |
    |---------------------------->|
    |                            | Applied
    |<----------------------------|
    |         success             |
    |                            |
    | 2. business error           |
    |                            |
    | 3. compensation             |
    |---------------------------->|
    X       connection lost       |
                                 |
~~~

Server không nhận biết transaction của Spring. Nếu connection bị ngắt, manager không thể yêu cầu server rollback một transaction đang mở. Với operation bù trừ đã gửi nhưng mất response, client cũng không biết operation đó đã chạy hay chưa.

### 3.2. JVM crash làm mất operation stack

Operation manager mặc định lưu các executor trong bộ nhớ. Nếu process bị kill sau khi preparation đã thay đổi directory nhưng trước commit/rollback, stack executor không tự được phục hồi khi ứng dụng khởi động lại.

Ví dụ:

~~~text
T0: rename uid=lan -> uid=lan_temp
T1: JVM crash
T2: ứng dụng khởi động lại
T3: không còn transaction stack trong process mới
T4: entry vẫn nằm ở uid=lan_temp
~~~

Đây là lý do workflow quan trọng cần một operation journal bền vững do ứng dụng quản lý. Không coi transaction manager nội bộ là durable recovery log.

### 3.3. Concurrent writer thay đổi cùng entry

Spring LDAP không cung cấp transaction isolation. Một client khác có thể nhìn thấy trạng thái trung gian và sửa cùng entry:

~~~text
T0 App A: rename uid=lan -> uid=lan_temp
T1 App B: bind uid=lan mới
T2 App A: rollback rename uid=lan_temp -> uid=lan
T3 Server: từ chối vì DN uid=lan đã tồn tại
~~~

Rollback của App A thất bại dù request bù trừ hợp lệ về cú pháp. Một transaction khác đã thay đổi điều kiện cần để phục hồi.

### 3.4. ACL hoặc schema thay đổi giữa transaction

Một operation có thể thành công ở preparation nhưng operation ngược bị từ chối:

- Service account được quyền rename entry sang staging nhưng không được rename về OU cũ.
- ACL bị quản trị viên thay đổi giữa transaction.
- Schema/objectClass được cập nhật khiến attribute cũ không còn hợp lệ.
- DN tạm nằm trong naming context không cho phép move như dự kiến.
- Password/service credential hết hạn hoặc bị khóa.

Không kiểm thử chỉ với một bind account có quyền Directory Admin. Cần kiểm tra đúng quyền production tối thiểu cho cả preparation, commit và rollback.

### 3.5. DN đích bị chiếm hoặc entry bị di chuyển

Rollback rename cần DN gốc còn trống. Nếu client khác tạo entry cùng DN hoặc một quy trình khác di chuyển entry tạm, rename ngược sẽ thất bại.

Đối với rebind, commit có nhiều bước: tạo entry mới tại DN gốc và xóa entry cũ tại DN tạm. Nếu một bước thành công còn bước sau lỗi, directory có thể chứa cả bản mới và bản cũ ở staging.

### 3.6. Operation ngược không phải phép đảo tuyệt đối

Một phép bù trừ thường được xây dựng từ trạng thái đã đọc trước operation. Nó không phải một phép đảo toán học độc lập với các thay đổi sau đó.

Ví dụ:

~~~text
Ban đầu: mail = old@example.org
App A:   REPLACE mail = new@example.org
App B:   REPLACE mail = other@example.org
App A rollback: REPLACE mail = old@example.org
~~~

Rollback của A có thể ghi đè thay đổi hợp lệ của B. Directory cuối có thể giống trạng thái ban đầu của A nhưng đã làm mất cập nhật mới hơn của B.

Với attribute đa trị, việc thêm/xóa giá trị có thể có semantics khác với Replace toàn bộ attribute. Với operational attributes do server quản lý, client không thể tự khôi phục chính xác mọi giá trị.

### 3.7. Side effect nằm ngoài LDAP

ContextSourceTransactionManager chỉ điều phối operation LDAP qua context được quản lý. Nó không tự rollback:

- JDBC write.
- HTTP call sang dịch vụ khác.
- Message đã publish.
- Email/notification đã gửi.
- File/object storage đã cập nhật.
- Audit event ở hệ thống độc lập.

Nếu một use case cập nhật LDAP và các hệ thống khác, cần workflow/saga và trạng thái cho từng resource.

## 4. Failure window theo từng LDAP operation

### 4.1. bind

Preparation tạo entry mới. Rollback dùng unbind để xóa entry đó.

| Failure window | Trạng thái có thể gặp |
| --- | --- |
| Lỗi trước khi bind tới server | Entry chưa tồn tại |
| Bind thành công, bước tiếp theo thất bại | Entry mới cần được xóa |
| Unbind bù trừ bị ACL từ chối | Entry mới còn tồn tại |
| Unbind bù trừ timeout | Chưa biết entry còn hay đã bị xóa |
| Client khác sửa entry trước rollback | Unbind có thể xóa dữ liệu client khác vừa thêm |

Trước khi kết luận cần xóa entry, kiểm tra DN, business ID và operation ID. Không xóa entry chỉ vì DN trùng với request ban đầu.

### 4.2. unbind

Preparation rename entry gốc sang DN tạm. Commit xóa entry tạm; rollback rename entry về DN cũ.

| Failure window | Trạng thái có thể gặp |
| --- | --- |
| Rename sang DN tạm thất bại | Entry có thể vẫn ở DN gốc |
| Rename thành công, JVM crash | Entry nằm ở DN tạm |
| Rollback rename về DN cũ bị collision | Entry còn ở staging, DN gốc thuộc entry khác |
| Commit unbind bị timeout | Entry tạm có thể còn hoặc đã bị xóa |
| ACL đổi trước commit | Entry tạm còn lại dù transaction không hoàn tất |

Đừng cho cron job xóa mọi entry có hậu tố _temp. Tên tạm không đủ để chứng minh entry đã được commit xóa.

### 4.3. rebind

Preparation giữ entry cũ ở DN tạm. Commit bind entry mới tại DN gốc rồi unbind entry tạm. Rollback cố đưa entry cũ về DN gốc.

| Failure window | Trạng thái có thể gặp |
| --- | --- |
| Rename entry cũ thất bại | Entry cũ có thể vẫn ở DN gốc |
| Rename thành công, bind entry mới thất bại | Entry cũ nằm ở DN tạm |
| Bind entry mới thành công, unbind entry cũ thất bại | Có thể tồn tại bản mới ở DN gốc và bản cũ ở staging |
| Rollback rename cũ bị collision | Entry cũ không thể quay lại DN gốc |
| Response bị mất sau bind/unbind | Trạng thái cần đọc lại từ server |

Rebind có nhiều bước ở pha commit. Khi commit lỗi, không giả định manager đã tự khôi phục mọi bước trước đó.

### 4.4. rename

Preparation rename entry từ DN nguồn sang DN đích; rollback rename ngược.

Rollback có thể thất bại nếu:

- DN nguồn đã được tái sử dụng.
- DN đích không còn tồn tại.
- Entry bị di chuyển tiếp bởi client khác.
- ACL không cho rename ngược.
- Rename đi qua naming context/server boundary không được hỗ trợ.
- Entry có child khiến kiểu rename/move bị directory từ chối.

Trước khi retry, đọc cả DN nguồn và DN đích, rồi so sánh identifier ổn định nếu có.

### 4.5. modifyAttributes

Preparation áp dụng thay đổi; rollback gửi các ModificationItem bù trừ đã được tạo từ trạng thái cũ.

Rủi ro:

- Giá trị gốc không đọc được đầy đủ.
- Attribute nhiều giá trị bị thay đổi đồng thời.
- Client khác cập nhật cùng attribute.
- Modification ngược vi phạm schema hoặc ACL hiện tại.
- Operational attribute do server quản lý không thể khôi phục bằng client.
- Response của operation ngược bị mất.

Không tự suy ra rollback modify luôn là Replace toàn bộ entry về snapshot ban đầu. Executor dùng các modification bù trừ cho operation cụ thể; behavior phụ thuộc loại modification và trạng thái đã ghi nhận.

Một LDAP ModifyRequest có thể chứa nhiều ModificationItem và server áp dụng danh sách change trong request đó như một operation nguyên tử theo RFC 4511. Vì vậy, một request Modify không được server xác nhận thành công không nên được mô tả là đã khôi phục vài attribute nhưng bỏ sót vài attribute khác. Trạng thái dở dang thường xuất hiện giữa **nhiều ModifyRequest riêng biệt** trong cùng transaction, hoặc khi client mất response và chưa biết request đã được áp dụng hay chưa.

## 5. Commit failure cũng có thể để lại trạng thái trung gian

Nhiều ứng dụng chỉ quan tâm rollback failure. Nhưng commit cũng có thể gồm các operation LDAP mới, đặc biệt với unbind và rebind.

Ví dụ commit của rebind:

~~~text
Entry cũ đã ở DN tạm
        |
        v
Bind entry mới tại DN gốc
        |
        v
Unbind entry cũ tại DN tạm
~~~

Nếu bind mới thành công nhưng unbind entry tạm thất bại:

- DN gốc có entry mới.
- DN tạm vẫn giữ entry cũ.
- Caller có thể nhận lỗi commit.
- Một lần retry toàn bộ use case có thể gặp entryAlreadyExists hoặc tạo side effect lặp.

Đối với unbind, commit xóa entry tạm. Nếu server đã xóa entry nhưng response bị mất, caller không biết commit đã hoàn tất hay chưa. Không thể khôi phục entry bằng rename nếu nó đã bị xóa.

### 5.1. Phân biệt lỗi nghiệp vụ và lỗi commit

| Loại lỗi | Ý nghĩa | Hành động |
| --- | --- | --- |
| Exception trong service trước commit | Spring có thể bắt đầu rollback theo rollback rule | Kiểm tra kết quả compensation |
| Exception trong operation bù trừ | Rollback không được xác nhận đầy đủ | COMPENSATION_FAILED hoặc UNKNOWN |
| Exception trong commit cleanup | Operation ban đầu có thể đã được áp dụng một phần | Reconcile trước khi retry |
| Timeout sau commit operation | Server có thể đã hoàn tất | Đối soát trạng thái thật |

Spring transaction status là trạng thái điều phối của framework. Nó không phải bản kiểm kê từng entry LDAP đã được phục hồi. Cần ghi trạng thái nghiệp vụ riêng nếu use case yêu cầu khả năng khôi phục sau crash.

## 6. Dấu hiệu và nguyên nhân thường gặp

| Dấu hiệu | Nguyên nhân có thể | Bằng chứng cần thu thập |
| --- | --- | --- |
| Entry còn ở staging OU | JVM crash, rollback rename thất bại, commit chưa chạy | DN tạm, operation ID, audit log, entry UUID |
| DN gốc có entry mới, staging vẫn còn entry cũ | Rebind commit dở dang | So sánh stable ID và attributes |
| Rollback rename nhận entryAlreadyExists | Client khác tái tạo DN gốc | Lookup cả source và destination |
| Modify rollback bị insufficientAccessRights | ACL thay đổi hoặc quyền thiếu | Bind identity, ACL effective, LDAP result code |
| Modify rollback lỗi schema | Schema đổi hoặc inverse modification không hợp lệ | Attribute syntax/objectClass/schema version |
| Connection reset khi rollback | Network, server restart, load balancer timeout | Trace ID, timestamp, server audit |
| Chỉ một phần subtree được xử lý | Recursive delete gồm nhiều operation | Danh sách DN theo depth và operation sequence |
| Service trả lỗi nhưng dữ liệu đã đổi | Operation thành công, response mất | Đọc lại authoritative directory |
| Search thấy entry tạm | Staging nằm trong search base hoặc ACL rộng | Base DN, scope, filter và referral |
| Rollback không chạy dù có exception | Exception bị bắt, checked exception không nằm trong rollback rule, proxy bị bypass | Call path, annotation, transaction logs |

### 6.1. Đừng chẩn đoán chỉ bằng message text

Spring LDAP có thể chuyển exception JNDI thành DataAccessException hoặc exception chuyên biệt. Log message không đủ để phân biệt:

- LDAP result code rõ ràng.
- Timeout trước khi gửi request.
- Timeout sau khi request đã tới server.
- Lỗi do đóng context.
- Lỗi do transaction proxy/wiring.

Ghi exception class, cause chain, LDAP result code nếu có, operation type và phase. Không log bind password, toàn bộ entry hoặc raw attribute nhạy cảm.

## 7. Thiết kế operation journal cho khả năng phục hồi sau crash

Transaction manager nội bộ ghi nhận operation để rollback trong vòng đời transaction hiện tại. Nếu ứng dụng cần phục hồi sau JVM crash, cần một journal bền vững ở tầng ứng dụng.

Một bản ghi operation có thể chứa:

| Trường | Mục đích |
| --- | --- |
| operationId | Định danh duy nhất cho use case |
| stepId | Định danh bước trong workflow |
| directoryId | Logical directory được cập nhật |
| operationType | bind, unbind, rebind, rename, modify |
| targetIdentity | Stable business ID/entryUUID/objectGUID nếu có |
| sourceDn / targetDn | DN trước và sau operation, có thể mã hóa/redact |
| beforeFingerprint | Fingerprint các field cần phục hồi |
| desiredFingerprint | Fingerprint trạng thái mong muốn |
| phase | PREPARED, APPLIED, COMPENSATING, UNKNOWN... |
| attempt | Số lần thử operation/compensation |
| lastResultCode | LDAP result code gần nhất |
| updatedAt | Thời điểm cập nhật |

Không nhất thiết lưu toàn bộ LDAP entry vào journal. Chỉ lưu dữ liệu tối thiểu cần cho đối soát và phục hồi, tuân thủ chính sách bảo vệ dữ liệu. Nếu cần snapshot, mã hóa và giới hạn quyền truy cập.

### 7.1. State machine ở tầng ứng dụng

~~~text
RECEIVED
   |
   v
IN_PROGRESS
   |
   +---- commit confirmed --------> COMPLETED
   |
   +---- business failure --------> ROLLBACK_REQUESTED
                                      |
                                      v
                               COMPENSATING
                                 /      \
                                /        \
                     all verified      failure/timeout
                           |                |
                           v                v
                     COMPENSATED       RECONCILIATION_REQUIRED
                                            |
                                            v
                                      RECONCILING
                                       /   |    \
                                      /    |     \
                                  RESTORED PARTIAL UNKNOWN
                                     |      |      |
                                     v      v      v
                                  RECOVERED MANUAL_REVIEW
~~~

Các state này thuộc journal ứng dụng, không phải state enum do ContextSourceTransactionManager tự cung cấp.

### 7.2. Ghi journal trước và sau mỗi bước

Một workflow có thể:

1. Ghi IN_PROGRESS cùng operation ID.
2. Ghi step PREPARED với DN/identity trước khi gửi LDAP request.
3. Thực hiện operation.
4. Nếu nhận success, ghi APPLIED.
5. Nếu mất response, ghi UNKNOWN.
6. Nếu cần rollback, ghi COMPENSATING trước khi gửi operation ngược.
7. Chỉ ghi COMPENSATED sau khi response thành công và read-back xác nhận.

Journal và LDAP không có transaction chung mặc định. Có thể crash giữa việc ghi journal và gửi LDAP hoặc giữa LDAP success và cập nhật journal. Vì vậy, reconciliation vẫn cần thiết.

## 8. Quy trình reconciliation khi rollback không đầy đủ

Reconciliation xác định trạng thái thực tế của directory và quyết định nên tiếp tục compensation, hoàn tất nghiệp vụ hay chuyển sang xử lý thủ công.

### 8.1. Bước 1: ngăn thay đổi cạnh tranh

- Tạm dừng job đồng bộ hoặc retry đang tác động cùng logical resource nếu có thể.
- Dùng application lock theo business key nếu kiến trúc có hỗ trợ.
- Không khóa toàn directory nếu chỉ một DN bị ảnh hưởng.
- Ghi nhận thời điểm và server endpoint được kiểm tra.

Lock ở application không thay thế transaction isolation phía LDAP. Nó chỉ giảm nguy cơ có writer khác trong phạm vi ứng dụng đã tham gia cùng cơ chế lock.

### 8.2. Bước 2: thu thập trạng thái thực tế

Với mỗi target, kiểm tra:

- DN gốc.
- DN tạm/staging nếu có.
- Stable identifier như entryUUID hoặc objectGUID nếu server cung cấp.
- Các attribute nghiệp vụ liên quan.
- Operational timestamp/version nếu có và hiểu đúng semantics.
- DN references ở group/entry khác.
- Audit log phía directory nếu có.

Không chỉ kiểm tra exists(DN). DN có thể được tái sử dụng bởi entry khác.

### 8.3. Bước 3: phân loại theo trạng thái

| DN gốc | DN tạm | Bằng chứng identity | Hướng xử lý |
| --- | --- | --- | --- |
| Có entry cũ | Không có | ID khớp | Có thể đã phục hồi; xác minh attributes và references |
| Không có | Có entry cũ | ID khớp | Entry vẫn staged; cân nhắc rename về hoặc tiếp tục commit theo journal |
| Có entry mới | Có entry cũ | Hai ID khác nhau | Rebind commit có thể dở dang; không xóa bản nào khi chưa xác định policy |
| Có entry khác | Có entry cũ | ID khác nhau | DN conflict; cách ly và xử lý thủ công |
| Không có | Không có | Audit cho biết delete đã hoàn tất | Có thể hoàn tất trạng thái nếu nghiệp vụ xác nhận |
| Không có | Không có | Không có bằng chứng | UNKNOWN; tìm audit/replication evidence hoặc manual review |

### 8.4. Bước 4: chọn phục hồi hay hoàn tất nghiệp vụ

Không phải lúc nào khôi phục trạng thái cũ cũng là lựa chọn đúng. Ví dụ:

- Nếu request hủy tài khoản đã được phê duyệt và delete commit thực sự thành công, có thể hoàn tất trạng thái COMPLETED.
- Nếu transaction thất bại trước commit và entry gốc còn ở staging, có thể rename về DN cũ.
- Nếu DN cũ đã được tái sử dụng, không rename đè lên entry mới.
- Nếu có cả entry cũ và mới, quyết định giữ phiên bản nào dựa trên operation journal và business ID.

Mỗi quyết định phải có người/logic được ủy quyền, lý do và audit record.

### 8.5. Bước 5: xác minh sau sửa chữa

Sau một operation sửa chữa:

1. Đọc lại DN nguồn và đích.
2. Kiểm tra stable ID và các attribute nghiệp vụ.
3. Kiểm tra group membership/DN references.
4. Chạy search nghiệp vụ với base/scope thực tế.
5. Xác minh không còn entry staging ngoài dự kiến.
6. Cập nhật journal sang RECOVERED hoặc MANUAL_REVIEW.

Chỉ đóng incident khi trạng thái được xác minh, không chỉ vì lệnh LDAP trả success.

## 9. Xử lý từng trường hợp staging còn sót

### 9.1. Entry bị unbind đang nằm ở temporary DN

Kiểm tra:

- DN gốc có đang trống không?
- DN tạm có đúng stable identity của entry ban đầu không?
- Operation journal nói commit hay rollback?
- Service account có quyền rename về?
- Có client nào đã tạo DN gốc mới không?

Nếu DN gốc trống và identity xác nhận đúng entry cũ, có thể thực hiện rename về theo quy trình phục hồi được phê duyệt. Nếu DN gốc đã tồn tại, không overwrite hoặc unbind entry đó tự động.

### 9.2. Rebind có cả bản mới và bản cũ

Kiểm tra nội dung và stable ID:

~~~text
DN gốc:
  uid=lan,ou=people
  employeeNumber=E-104
  mail=lan.new@example.org

DN staging:
  uid=lan_temp,ou=tx-staging
  employeeNumber=E-104
  mail=lan.old@example.org
~~~

Nếu cả hai là cùng business identity, cần xác định request đang ở commit hay rollback. Không xóa staging entry cho tới khi xác nhận bản gốc mới là phiên bản được chấp nhận và tất cả references đã đúng.

### 9.3. Nhiều ModifyRequest trong transaction chỉ được bù trừ một phần

So sánh từng ModifyRequest riêng được transaction thực hiện:

| Operation riêng | Giá trị trước | Giá trị sau preparation | Giá trị sau rollback |
| --- | --- | --- | --- |
| Modify #1: mail | old@example.org | new@example.org | old@example.org |
| Modify #2: telephoneNumber | 100 | 200 | 200 |
| Modify #3: description | staff | staff-reviewed | staff |

Ví dụ minh họa ba ModifyRequest riêng trong cùng transaction: compensation của request #1 và #3 đã được xác minh, request #2 chưa khôi phục được. Một request Modify đơn lẻ với nhiều ModificationItem vẫn có semantics nguyên tử theo LDAP; không suy diễn rằng server đã áp dụng một phần các item trong cùng request bị từ chối. Hãy kiểm tra transaction log và audit server trước khi gửi modification sửa tiếp. Với attribute đa trị, phải so sánh tập giá trị và semantics; không dùng Replace toàn bộ nếu có thay đổi hợp lệ của client khác.

## 10. Vì sao không nên tự động retry compensation một cách mù quáng?

Operation bù trừ cũng có thể không idempotent hoặc không an toàn nếu trạng thái đã thay đổi.

Ví dụ:

- Rename về DN cũ lần hai có thể báo noSuchObject vì entry đã được khôi phục.
- Unbind bù trừ lần hai có thể báo noSuchObject hoặc xóa nhầm entry mới nếu DN đã được tái sử dụng.
- Modify ngược lần hai có thể ghi đè giá trị client khác.
- Bind bù trừ lần hai có thể gặp entryAlreadyExists.

Trước mỗi retry:

1. Đọc trạng thái hiện tại.
2. Xác minh identity và operation ID.
3. Kiểm tra desired state của compensation đã đạt chưa.
4. Kiểm tra điều kiện DN/ACL/schema.
5. Chỉ gửi operation nếu trạng thái hiện tại còn phù hợp.
6. Sau operation, đọc lại để xác minh.

Nếu server hỗ trợ LDAP Assertion Control, ứng dụng có thể thiết kế conditional update/rename phù hợp. Tuy nhiên, ContextSourceTransactionManager không tự biến mọi compensation thành conditional operation; logic này cần được thiết kế và kiểm thử riêng.

## 11. Cấu hình và wiring thường gây rollback không chạy

Không phải mọi trường hợp entry không được khôi phục đều là lỗi server. Một số trường hợp transaction manager không tham gia operation.

| Cấu hình/luồng gọi sai | Hậu quả |
| --- | --- |
| LdapTemplate dùng ContextSource gốc thay vì transaction-aware proxy | Modifying operation không được intercept đúng |
| Manager dùng ContextSource khác với template | Transaction gắn vào resource khác |
| Một DAO tạo InitialDirContext trực tiếp | Operation đi ngoài proxy |
| Repository dùng template khác | Repository write không nằm trong transaction mong đợi |
| Service gọi method transactional bằng self-invocation | Spring proxy có thể không được đi qua |
| Exception bị catch và nuốt | Method kết thúc bình thường, không có rollback tự động |
| Checked exception không nằm trong rollback rule | Transaction có thể commit theo default rollback rules |
| Dùng nhiều transaction manager nhưng chỉ một manager được chỉ định | Chỉ resource thuộc manager đó được quản lý |

### 11.1. Kiểm tra wiring

Danh sách kiểm tra:

- Manager và LdapTemplate dùng cùng target ContextSource.
- LdapTemplate nhận TransactionAwareContextSourceProxy.
- ContextSourceTransactionManager nhận target ContextSource.
- Repository được tạo từ cùng cấu hình LdapTemplate/ContextSource.
- Transaction annotation nằm trên method được gọi qua Spring proxy.
- rollbackFor phù hợp loại exception.
- Không có raw JNDI context hoặc connection source thứ hai trong cùng workflow.

### 11.2. Kiểm tra transaction boundary

Transaction quá rộng làm tăng thời gian giữ context và thời gian trạng thái trung gian tồn tại. Tránh gọi HTTP, chờ người dùng, tải file hoặc thực hiện công việc chậm bên trong transaction LDAP.

Nếu use case cần nhiều hệ thống, hãy chia thành workflow có bước và trạng thái riêng. Đừng cố kéo một @Transactional bao quanh LDAP, JDBC, HTTP và message broker rồi kỳ vọng chúng rollback cùng nhau.

## 12. Recursive delete và subtree staging

Xóa subtree thường là một chuỗi delete theo depth-first; LDAP Delete operation chuẩn chỉ xóa entry lá. Khi dùng DefaultTempEntryRenamingStrategy, entry tạm vẫn nằm trong cây nguồn với RDN đổi suffix. Các entry cha có thể vẫn còn child và không thể bị rename/xóa theo trình tự mong muốn.

Với transaction có create/delete subtree, Spring LDAP yêu cầu xem xét DifferentSubtreeTempEntryRenamingStrategy để đưa entry tạm sang subtree staging riêng đã tồn tại.

Ngay cả khi dùng staging subtree:

- Cần ACL cho rename/move vào staging và rename ngược.
- Cần đảm bảo DN tạm không collision.
- Cần kiểm soát search để entry tạm không lộ ra.
- Cần reconciliation sau crash.
- Cần kiểm thử server hỗ trợ move/ModifyDN trong naming context đó.

Không xem việc đổi strategy là bảo đảm rollback đầy đủ. Strategy chỉ quyết định DN tạm; nó không tạo durable journal, isolation hoặc tự dọn entry sau process crash.

## 13. Quy trình vận hành khi phát hiện compensation failure

Một runbook thực tế nên đi theo trình tự:

### 13.1. Bảo toàn bằng chứng

- Ghi operation ID, trace ID, transaction manager và logical directory.
- Thu thập exception/cause chain và LDAP result code.
- Ghi thời gian bắt đầu, preparation, commit/rollback attempt.
- Ghi DN nguồn/đích đã redaction theo chính sách.
- Thu thập server audit log và replication status nếu có.
- Không xóa staging entry trước khi snapshot/đối soát.

### 13.2. Khoanh vùng tác động

- Xác định danh sách entry và attribute transaction đã chạm tới.
- Xác định client/job nào có thể đã ghi cùng các DN.
- Tạm dừng retry tự động cho operation ID bị ảnh hưởng.
- Kiểm tra side effect ở JDBC, message broker và dịch vụ ngoài LDAP.

### 13.3. Đánh giá trạng thái

- Lookup DN gốc, DN tạm và DN đích.
- So sánh stable identity.
- So sánh attribute trước/sau theo journal.
- Kiểm tra references và membership.
- Xác định server/replica đang đọc và mức độ replication lag.

### 13.4. Thực hiện remediation

- Nếu trạng thái đã đúng, cập nhật journal sau khi có read-back evidence.
- Nếu có thể bù trừ an toàn, thực hiện operation nhỏ, có log và kiểm tra kết quả.
- Nếu DN conflict hoặc identity không rõ, chuyển manual review.
- Nếu cần hoàn tất forward operation, xác minh nghiệp vụ cho phép trước.
- Không dùng một script cleanup chung cho mọi staging entry.

### 13.5. Đóng incident

- Đọc lại dữ liệu sau remediation.
- Xác minh search nghiệp vụ và group references.
- Cập nhật journal/audit.
- Ghi root cause và failure window.
- Bổ sung integration test tái hiện sự cố.
- Chỉ bật lại retry/job sau khi trạng thái không còn mơ hồ.

## 14. Thiết kế workflow bền vững thay cho một transaction dài

Với quy trình quan trọng, hãy mô hình hóa mỗi bước thành workflow:

~~~text
Provision employee
    |
    v
Create LDAP entry
    |
    v
Verify LDAP entry
    |
    v
Add group membership
    |
    v
Verify membership
    |
    v
Publish completion event
~~~

Mỗi bước có:

- Operation ID và step ID.
- Trạng thái trước/sau.
- Retry policy riêng.
- Compensation riêng.
- Reconciliation query.
- Timeout và escalation.

Ví dụ state của một workflow:

| Step | Trạng thái | Compensation |
| --- | --- | --- |
| Create person | APPLIED | Xóa đúng entry nếu identity vẫn khớp |
| Add membership | UNKNOWN | Đọc membership rồi quyết định |
| Update profile | NOT_STARTED | Không cần |
| Publish event | NOT_STARTED | Không cần |

Nếu membership không được thêm, workflow có thể retry bước đó sau khi xác minh. Nếu không thể phục hồi an toàn, chuyển MANUAL_REVIEW và giữ bằng chứng. Đây là saga/workflow ở tầng ứng dụng, không phải tính năng durable saga có sẵn của Spring LDAP.

### 14.1. Operation journal và outbox

Nếu cần publish event sau LDAP update:

- Ghi intent/event vào outbox bền vững.
- Chỉ phát event khi LDAP state đã được xác minh theo policy.
- Dùng idempotency key ở consumer.
- Có reconciliation giữa outbox và directory.

Outbox không tạo transaction chung với LDAP. Nó giúp ghi nhận ý định và xử lý gửi lặp, nhưng vẫn cần xử lý crash giữa LDAP write và outbox state update.

### 14.2. Giới hạn với JDBC

Spring LDAP 4.0 đã loại bỏ JDBC Transaction Integration cũ. Không giả định @Transactional trên service có thể làm LDAP và JDBC thành một transaction nguyên tử. Khi use case chạm cả hai resource, dùng workflow/journal, retry có điều kiện và compensation rõ ràng.

## 15. Logging, metrics và cảnh báo

Ghi log theo operation, không chỉ log một stack trace ở cuối request.

Các trường hữu ích:

- operationId, stepId, traceId.
- directoryId, operationType.
- phase: RECORD, PREPARE, COMMIT, ROLLBACK, RECONCILE.
- DN đã redaction hoặc reference ID.
- LDAP result code và exception class.
- Attempt number và latency.
- Stable identity/fingerprint nếu được phép.
- Kết quả read-back và final state.

Metric nên có:

| Metric | Ý nghĩa |
| --- | --- |
| ldap_compensation_attempt_total | Tổng operation bù trừ |
| ldap_compensation_failure_total | Số compensation thất bại |
| ldap_compensation_unknown_total | Số operation có kết quả không xác định |
| ldap_staging_entry_count | Số entry staging được phát hiện |
| ldap_reconciliation_backlog | Số workflow chờ đối soát |
| ldap_reconciliation_age_seconds | Tuổi của incident chưa giải quyết |
| ldap_commit_cleanup_failure_total | Lỗi ở pha commit cleanup |
| ldap_rollback_duration | Thời gian rollback |

Không dùng DN, username, email hoặc operation ID làm metric label vì cardinality cao và có thể chứa dữ liệu cá nhân. Dùng log/trace có kiểm soát để truy vết.

### 15.1. Cảnh báo nên kích hoạt khi

- Có compensation failure.
- Có operation ở trạng thái UNKNOWN quá thời hạn.
- Staging entry tồn tại vượt ngưỡng vận hành.
- Commit cleanup thất bại.
- Reconciliation backlog tăng liên tục.
- Tỷ lệ rollback timeout tăng sau deploy hoặc directory maintenance.

Staging entry tồn tại không tự động đồng nghĩa lỗi; cần đối chiếu operation journal và transaction age.

## 16. Kiểm thử failure window

Unit test kiểm tra mapper/logic phân loại exception. Để kiểm tra compensation thực tế, cần integration test với LDAP server và fault injection có kiểm soát.

### 16.1. Ma trận test

| Test | Điểm gây lỗi | Kỳ vọng |
| --- | --- | --- |
| Bind rồi rollback | Sau bind, trước bước tiếp theo | Entry được unbind và read-back xác nhận |
| Unbind rollback | Sau rename sang DN tạm | Entry được rename về DN gốc |
| Unbind commit | Sau stage rename, khi xóa DN tạm | Lỗi commit được phân loại và reconciliation kiểm tra |
| Rebind commit | Sau bind entry mới, trước unbind entry cũ | Phát hiện hai bản và không xóa mù |
| Nhiều ModifyRequest rollback | Sau nhiều modify riêng, làm compensation của một bước thất bại | Xác định rõ step nào đã bù trừ; kiểm tra atomicity trong từng ModifyRequest |
| Rename rollback | Sau rename, trước rollback | Entry về DN nguồn |
| Network cut | Khi gửi compensation | UNKNOWN/RECONCILIATION_REQUIRED |
| Process kill | Sau preparation, trước commit | Journal phát hiện operation chưa kết thúc |
| DN collision | Client khác tạo DN gốc trước rollback | Conflict, không overwrite |
| ACL revoked | Thu hồi quyền move/delete giữa các pha | Compensation failure được ghi nhận |
| Schema change | Thay đổi schema giữa prepare và rollback | Phát hiện constraint/schema failure |
| Concurrent modify | Client B đổi cùng attribute | Không ghi đè thay đổi mới một cách âm thầm |
| Recursive delete | Lỗi ở một node giữa cây | Xác định chính xác node đã staged/deleted |
| Swallowed exception | Catch exception trong transactional method | Test chứng minh transaction không rollback tự động |
| Wrong ContextSource | Template bypass proxy | Test phát hiện operation không được enlist |

### 16.2. Mô phỏng mất response

Một proxy/fault injector trong môi trường test có thể:

1. Cho request LDAP đi tới server.
2. Chờ server xử lý.
3. Chặn response trên đường về.
4. Để application nhận CommunicationException/timeout.
5. Đọc lại directory bằng một connection mới.

Test này phân biệt được “server chưa áp dụng” với “server đã áp dụng nhưng response bị mất”. Chỉ đóng socket trước khi request tới server chưa kiểm tra được failure window quan trọng này.

### 16.3. Test concurrent writer

Điều phối hai client bằng latch/barrier:

~~~text
Client A: stage rename entry
Client B: create/reuse original DN
Client A: trigger rollback
Test: inspect original DN and staging DN
~~~

Kỳ vọng là adapter phát hiện conflict, không ghi đè entry của B. Không dùng Thread.sleep dài để tạo race không ổn định.

### 16.4. Kiểm tra sau mỗi test

- DN gốc.
- DN tạm.
- Stable identity.
- Attributes nghiệp vụ.
- Membership references.
- Staging subtree.
- Operation journal.
- Server audit log nếu test environment hỗ trợ.

Không chỉ assert exception type. Một test transaction chỉ có giá trị khi kiểm tra trạng thái LDAP cuối cùng.

## 17. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Có exception nhưng entry vẫn ở DN tạm | Rollback chưa chạy hoặc rename ngược thất bại | Kiểm tra transaction proxy, journal, ACL và DN đích |
| Rollback chỉ phục hồi một số attribute | Inverse modification lỗi hoặc concurrent update | So sánh từng attribute và read-back |
| Entry mới và cũ cùng tồn tại | Rebind commit dở dang | So sánh identity, quyết định forward/compensate |
| Rollback bị entryAlreadyExists | DN gốc đã được tái sử dụng | Không overwrite; manual conflict resolution |
| Compensation timeout | Không biết server đã áp dụng chưa | UNKNOWN và reconciliation |
| Staging entry bị xóa nhầm | Cleanup theo TTL/suffix thiếu identity check | Dừng cleanup, dùng journal và stable ID |
| Không có rollback khi checked exception | Rollback rule không bao gồm checked exception | Cấu hình rollbackFor phù hợp |
| Không có rollback khi catch exception | Method kết thúc bình thường | Ném lại hoặc đánh dấu rollback-only |
| Repository write không rollback | Repository dùng ContextSource/template khác | Đồng bộ bean wiring |
| Raw JNDI write không rollback | Bypass transaction-aware proxy | Đưa operation qua resource được quản lý |
| Rollback làm mất update của client khác | Không có isolation/conditional compensation | Assertion/version/lock ở tầng ứng dụng |
| Subtree delete lỗi giữa chừng | Temporary rename còn trong source subtree | Chọn staging strategy và test recursive flow |
| Log nói rollback nhưng chưa verify | Log event chỉ ghi attempt | Tách ROLLBACK_REQUESTED khỏi COMPENSATED |

## 18. Bài tập tự luyện

**Câu 1.** Vì sao ContextSourceTransactionManager không thể bảo đảm rollback khi connection bị mất?

*Gợi ý:* LDAP server không biết transaction client-side; manager không thể gửi operation bù trừ nếu mất liên lạc.

**Câu 2.** Tại sao JVM crash sau khi unbind đã rename sang DN tạm có thể để lại entry staging?

*Gợi ý:* Operation executor/stack mặc định nằm trong process; process mới không tự có durable transaction record để tiếp tục.

**Câu 3.** Một rollback rename nhận entryAlreadyExists ở DN gốc. Có nên xóa entry ở DN gốc để retry không?

*Gợi ý:* Không. DN có thể đã được tái sử dụng bởi client khác; phải xác minh stable identity và business ownership.

**Câu 4.** Vì sao rollback modify có thể ghi đè dữ liệu hợp lệ của client khác?

*Gợi ý:* Compensation dùng trạng thái cũ đã ghi nhận và không có isolation; client khác có thể thay đổi cùng attribute sau preparation.

**Câu 5.** Rebind commit thất bại sau khi bind entry mới nhưng trước khi xóa entry cũ có thể tạo trạng thái nào?

*Gợi ý:* Entry mới ở DN gốc và entry cũ vẫn ở DN tạm.

**Câu 6.** Vì sao không nên dùng cron xóa mọi entry có suffix _temp?

*Gợi ý:* Không xác định được transaction/identity/commit state; có thể xóa bản duy nhất còn khả năng phục hồi.

**Câu 7.** Cần kiểm tra gì nếu repository không rollback dù service có @Transactional?

*Gợi ý:* Repository dùng đúng template/context source không, proxy transaction có được đi qua không, exception có kích hoạt rollback không.

**Câu 8.** Khi nào một workflow nên chuyển MANUAL_REVIEW?

*Gợi ý:* DN conflict, identity không rõ, cả bản cũ/mới cùng tồn tại, hoặc operation bù trừ không thể thực hiện an toàn.

**Câu 9.** Vì sao log rollback started không đủ để đánh dấu transaction COMPENSATED?

*Gợi ý:* Đây chỉ là ý định/attempt; cần kết quả operation và read-back xác nhận.

**Câu 10.** Vì sao cần operation journal dù Spring LDAP đã ghi nhận operation?

*Gợi ý:* Journal nội bộ của transaction manager không phải durable recovery log sau JVM crash; journal ứng dụng giúp đối soát và vận hành.

## 19. Ghi nhớ

- ContextSourceTransactionManager cung cấp **client-side compensating transaction**, không phải transaction server-side có isolation.
- Spring LDAP ghi nhận operation và tạo executor để thực hiện preparation, commit hoặc rollback.
- Operation manager mặc định giữ stack compensation và rollback theo thứ tự ngược.
- Mất kết nối có thể khiến compensation không gửi được hoặc response bị mất; kết quả phải được xem là UNKNOWN.
- JVM crash có thể làm mất operation stack trong bộ nhớ và để lại trạng thái trung gian.
- Concurrent writer có thể tái sử dụng DN hoặc sửa attribute khiến operation ngược thất bại hoặc ghi đè dữ liệu mới.
- unbind và rebind có staging/commit cleanup; commit failure cũng có thể để lại entry tạm.
- modifyAttributes compensation không bảo đảm khôi phục tuyệt đối khi có concurrent update hoặc inverse modification bị từ chối.
- Đảm bảo manager và LdapTemplate dùng cùng target ContextSource; template phải đi qua TransactionAwareContextSourceProxy.
- Exception bị nuốt, checked exception ngoài rollback rule, self-invocation hoặc raw JNDI context có thể làm rollback không chạy như mong đợi.
- Không tự động dọn staging entry chỉ theo suffix hoặc TTL; xác minh operation ID và stable identity.
- Workflow quan trọng cần durable operation journal, state machine, reconciliation, audit và manual recovery.
- Chỉ đánh dấu COMPENSATED sau khi trạng thái directory được xác minh bằng read-back.
- Kiểm thử fault injection, network loss, process crash, concurrent writer, ACL/schema changes và commit cleanup.

**Tài liệu tham khảo chính thức:**

- [Spring LDAP 4.2 — Transaction Support](https://docs.spring.io/spring-ldap/reference/transaction-support.html): vòng đời compensating transaction, operation matrix, giới hạn isolation/network và cấu hình.
- [Spring LDAP API — ContextSourceTransactionManager](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/ContextSourceTransactionManager.html): giới hạn client-side, ContextSource target và proxy.
- [Spring LDAP API — TransactionAwareContextSourceProxy](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/TransactionAwareContextSourceProxy.html): giữ DirContext trong transaction và intercept modifying operations.
- [Spring LDAP API — DefaultCompensatingTransactionOperationManager](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/transaction/compensating/support/DefaultCompensatingTransactionOperationManager.html): stack operation executor và thứ tự rollback ngược.
- [Spring LDAP API — CompensatingTransactionOperationExecutor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/transaction/compensating/CompensatingTransactionOperationExecutor.html): contract perform, commit và rollback.
- [Spring LDAP API — ModifyAttributesOperationExecutor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/ModifyAttributesOperationExecutor.html): modification bù trừ cho modifyAttributes.
- [Spring LDAP API — UnbindOperationExecutor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/UnbindOperationExecutor.html): DN gốc, DN tạm, commit và rollback của unbind.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules và hành vi với exception.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): semantics của LDAP operations, ModifyDN và result codes.
- [RFC 5805 — LDAP Transactions (Experimental)](https://www.rfc-editor.org/rfc/rfc5805): LDAP transaction extension; không đồng nhất với Spring LDAP client-side compensation.
