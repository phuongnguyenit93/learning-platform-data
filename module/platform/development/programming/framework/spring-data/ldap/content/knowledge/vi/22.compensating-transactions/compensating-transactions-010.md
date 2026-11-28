# Phối hợp LDAP với JDBC và đối chiếu khả năng tích hợp theo phiên bản

> **Chương:** Giao dịch bù trừ  
> **Module:** SPRING_DATA_LDAP — truy cập dịch vụ thư mục LDAP qua Spring Data LDAP bằng mô hình repository và ánh xạ entry phân cấp sang đối tượng Java. Người học hiểu DN, objectClass, schema, truy vấn repository/LdapTemplate, CRUD, filter an toàn, bảo mật kết nối và kiểm thử với directory.

Một nghiệp vụ quản lý nhân viên thường cập nhật cả cơ sở dữ liệu quan hệ và LDAP. Ví dụ, khi tạo tài khoản nhân viên, ứng dụng có thể cần ghi hồ sơ vào bảng JDBC, tạo entry người dùng trong LDAP, thêm người dùng vào một số group và phát sự kiện để các hệ thống khác đồng bộ.

Khó khăn nằm ở chỗ JDBC và LDAP có cơ chế transaction khác nhau. JDBC có transaction cục bộ do database quản lý. LDAP protocol không định nghĩa transaction ACID tổng quát cho các thao tác Add, Modify, Delete và ModifyDN. Spring LDAP cung cấp **compensating transaction** ở phía client để cố gắng hoàn tác các thay đổi LDAP. Một số phiên bản còn có cơ chế ghép LDAP với JDBC theo một transaction logic, nhưng cơ chế đó không phải XA/2PC và đã bị loại bỏ ở Spring LDAP 4.0.

Vì vậy, trước khi chọn cách tích hợp, cần trả lời ba câu hỏi:

1. Ứng dụng đang dùng phiên bản Spring LDAP và Spring Data LDAP nào?
2. Mức đảm bảo cần đạt là transaction cục bộ, bù trừ best-effort hay đồng bộ bền vững giữa hai resource?
3. Nếu tiến trình dừng sau khi một resource đã commit, hệ thống sẽ retry, đối chiếu hay thực hiện compensation như thế nào?

Bài học này trình bày các giới hạn của từng phiên bản, cách cấu hình transaction LDAP riêng, cách đọc các API tích hợp JDBC cũ, và thiết kế outbox/saga phù hợp cho ứng dụng Spring Data LDAP hiện đại.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vì sao một phương thức có [@Transactional] không tự tạo transaction ACID xuyên JDBC và LDAP.
2. Phân biệt transaction JDBC, transaction bù trừ LDAP, transaction logic ghép hai resource và XA/JTA.
3. Mô tả cách [ContextSourceTransactionManager] ghi nhận trạng thái và thực hiện thao tác bù.
4. Cấu hình transaction LDAP độc lập bằng [ContextSourceTransactionManager] và [TransactionAwareContextSourceProxy].
5. Đối chiếu [ContextSourceAndDataSourceTransactionManager] giữa Spring LDAP 3.3 và 4.0 trở lên.
6. Hiểu vì sao cơ chế ghép JDBC/LDAP cũ không có two-phase commit và không hỗ trợ nested transaction.
7. Chọn outbox, saga/compensation hoặc callback sau commit theo yêu cầu nhất quán.
8. Thiết kế idempotency, retry, unknown outcome, reconciliation và checkpoint.
9. Quản lý version bằng Spring Boot BOM/Spring Data Release Train BOM và dependency graph.
10. Kiểm thử các cửa sổ lỗi khi JDBC và LDAP thành công/thất bại độc lập.

## 2. Tình huống thực tế: một nghiệp vụ, hai hệ thống lưu trữ

Giả sử ứng dụng tạo một nhân viên mới. Hồ sơ nhân viên thuộc JDBC; tài khoản xác thực và group membership nằm trong LDAP.

~~~text
                 API tạo nhân viên
                        |
                        v
                EmployeeService
                  /          \
                 v            v
           JDBC database    LDAP directory
           employee row     user entry + groups
~~~

Các dữ liệu có thể được phân chia như sau:

| Dữ liệu | Nơi lưu | Ví dụ |
|---|---|---|
| Mã nhân viên, phòng ban, trạng thái hợp đồng | JDBC | employee_id, department_id |
| Thông tin xác thực, DN, thuộc tính directory | LDAP | uid, cn, mail, userPassword |
| Group membership | LDAP | member, uniqueMember |
| Trạng thái đồng bộ | JDBC | provisioning_status |
| Sự kiện cần đồng bộ | JDBC outbox | EmployeeCreated |

Một luồng đơn giản có thể là:

1. INSERT nhân viên vào JDBC.
2. Tạo LDAP entry cho nhân viên.
3. Thêm DN vào group.
4. Đánh dấu nhân viên đã provision thành công.

Nếu bước 1 thành công nhưng bước 2 thất bại, hai hệ thống không còn cùng trạng thái. Nếu bước 2 thành công nhưng bước 1 rollback, LDAP có thể có tài khoản không gắn với hồ sơ JDBC. Nếu bước 3 thất bại, user tồn tại nhưng thiếu quyền group. Nếu client timeout sau khi gửi AddRequest, ứng dụng thậm chí không biết server đã tạo entry hay chưa.

Đây là bài toán **dual-write**: một nghiệp vụ ghi vào hai resource có ranh giới commit riêng.

## 3. Transaction JDBC không tự bao gồm LDAP

Trong Spring, [@Transactional] được điều phối bởi một [PlatformTransactionManager]. Nếu bean được cấu hình với [DataSourceTransactionManager], transaction đó quản lý connection JDBC. Các lời gọi [LdapTemplate] trong cùng phương thức không tự được enlist vào transaction JDBC.

~~~java
@Service
public class EmployeeService {

    private final JdbcTemplate jdbcTemplate;
    private final LdapTemplate ldapTemplate;

    public EmployeeService(
            JdbcTemplate jdbcTemplate,
            LdapTemplate ldapTemplate) {
        this.jdbcTemplate = jdbcTemplate;
        this.ldapTemplate = ldapTemplate;
    }

    @Transactional
    public void createEmployee(Employee employee) {
        jdbcTemplate.update(
                "insert into employee(id, name) values (?, ?)",
                employee.id(), employee.name());

        // Lời gọi LDAP không tự trở thành một phần của JDBC transaction.
        ldapTemplate.bind(
                employee.dn(),
                null,
                employee.attributes());
    }
}
~~~

Nếu method ném exception sau thao tác LDAP, JDBC transaction có thể rollback. Nhưng thao tác LDAP không được JDBC transaction manager quản lý nên entry LDAP có thể vẫn còn.

Ngược lại, nếu chọn [ContextSourceTransactionManager] làm transaction manager, nó quản lý thao tác LDAP theo cơ chế bù trừ; nó không tự quản lý transaction JDBC.

Khi ứng dụng có nhiều transaction manager, cần chỉ định manager phù hợp:

~~~java
@Transactional(transactionManager = "jdbcTransactionManager")
public void updateRelationalData() {
    // Chỉ JDBC transaction.
}

@Transactional(transactionManager = "ldapTransactionManager")
public void updateDirectoryData() {
    // Chỉ LDAP compensating transaction.
}
~~~

Không đặt hai annotation này lên hai method rồi giả định Spring tự hợp nhất chúng thành một transaction phân tán. Gọi một method transaction manager khác từ method đang có transaction cũng không tự tạo XA enlistment.

## 4. Phân biệt bốn cơ chế transaction

| Cơ chế | Ai quản lý? | Phạm vi | Giới hạn chính |
|---|---|---|---|
| JDBC local transaction | Database + JDBC transaction manager | Một JDBC resource | Không bao gồm LDAP |
| LDAP compensating transaction | Spring LDAP ở client | Các thao tác LDAP qua transaction-aware context | Không có isolation/atomicity phía server; rollback là thao tác bù |
| JDBC + LDAP transaction logic cũ | Spring LDAP manager kết hợp JDBC manager | Một luồng điều phối hai resource | Không phải XA/2PC; kết quả có thể không chắc chắn |
| XA/JTA distributed transaction | JTA coordinator và XA resource managers | Các resource có XA support | Cần resource thực sự hỗ trợ XA và cấu hình 2PC |

### XA và JTA cần điều kiện gì?

JTA không tự biến mọi client thành XA resource. Để một resource tham gia two-phase commit, cần resource manager cung cấp XA interface và transaction coordinator có thể enlist resource đó.

Spring LDAP ghi rõ hỗ trợ JDBC/LDAP của nó **không phải XA transaction**. LDAP server không tham gia vote trong giai đoạn prepare, do đó không có two-phase commit để bảo đảm cả hai resource commit hoặc rollback cùng nhau.

Không nên gọi một transaction logic là “distributed atomic transaction” chỉ vì cả hai thao tác được gọi trong cùng một method có [@Transactional].

## 5. Transaction LDAP: core operation và extension thử nghiệm

Các operation LDAP cơ bản như Add, Modify, Delete, ModifyDN và Search không tự được đóng gói thành một transaction nhiều entry tương tự JDBC. Tuy nhiên, cần biết rằng RFC 5805 có định nghĩa **LDAP Transactions extension** ở trạng thái Experimental. Extension này bổ sung Start Transaction, End Transaction và Transaction Specification control để nhóm nhiều update operation thành một transaction phía directory server.

RFC 5805 không phải Internet Standards Track specification. Server chỉ hỗ trợ nếu triển khai extension này và quảng bá các OID tương ứng trong Root DSE. Không thể giả định mọi LDAP server hoặc mọi client library đều hỗ trợ. Spring LDAP [ContextSourceTransactionManager] là cơ chế bù trừ phía client; nó không phải client triển khai RFC 5805.

Ví dụ:

~~~text
LDAP AddRequest user
LDAP ModifyRequest user attributes
LDAP ModifyRequest group member
~~~

Nếu client gửi các operation riêng lẻ ngoài một transaction extension được server hỗ trợ, mỗi operation được xử lý riêng. Nếu operation thứ ba thất bại, hai operation trước có thể đã được áp dụng.

Nếu directory quảng bá RFC 5805, client có thể kiểm tra các giá trị sau trong Root DSE:

| Thuộc tính Root DSE | OID | Ý nghĩa |
|---|---|---|
| supportedExtension | 1.3.6.1.1.21.1 | Start Transaction |
| supportedControl | 1.3.6.1.1.21.2 | Transaction Specification control |
| supportedExtension | 1.3.6.1.1.21.3 | End Transaction |

Ngay cả khi server hỗ trợ RFC 5805, transaction đó chỉ bao phủ các operation LDAP theo semantics extension. Nó không tự enlist JDBC và không tạo XA transaction xuyên JDBC/LDAP. Extension cũng có các giới hạn như không hỗ trợ nested transaction và transaction ID gắn với LDAP association. Phải xác minh khả năng của server và client trước khi dựa vào nó.

Spring LDAP cung cấp một lớp transaction phía client. [ContextSourceTransactionManager] ghi lại thông tin cần thiết trước khi thay đổi và cố gắng phục hồi trạng thái khi rollback. Server LDAP không biết các operation thuộc cùng một transaction Spring.

Điều đó có nghĩa:

- Không có isolation như transaction database.
- Client khác vẫn có thể đọc/ghi entry trong lúc transaction đang diễn ra.
- Nếu kết nối bị đứt, client có thể không biết operation cuối đã được áp dụng hay chưa.
- Thao tác bù có thể thất bại do ACL, schema, entry đã bị thay đổi hoặc server unavailable.
- Một compensation chạy sau có thể xung đột với thay đổi hợp lệ của client khác.

## 6. Spring LDAP compensating transaction hoạt động thế nào?

[ContextSourceTransactionManager] là một [PlatformTransactionManager] dành cho LDAP. Nó làm việc cùng [TransactionAwareContextSourceProxy] để giữ cùng một [DirContext] trong phạm vi transaction và ghi nhận các thao tác sửa đổi.

Các thao tác được hỗ trợ gồm:

- [bind]
- [unbind]
- [rebind]
- [rename]
- [modifyAttributes]

Với mỗi operation, Spring LDAP lưu thông tin đủ để xây dựng thao tác bù. Ví dụ:

| Operation ban đầu | Chuẩn bị/commit | Compensation khi rollback |
|---|---|---|
| bind | Tạo entry tại DN | unbind DN vừa tạo |
| rename | Đổi từ DN cũ sang DN mới | rename về DN cũ |
| modifyAttributes | Thực hiện các ModificationItem | Gửi ModificationItem đảo ngược |
| unbind | Ghi nhận DN, chuyển entry tới DN tạm | Đổi entry từ DN tạm về DN cũ |
| rebind | Chuyển entry cũ tới DN tạm, tạo dữ liệu mới | Phục hồi entry gốc từ DN tạm |

Một số thao tác cần DN tạm vì directory không phải lúc nào cũng trả về đầy đủ attribute để tạo lại entry sau khi xóa. Spring LDAP có [TempEntryRenamingStrategy] để xác định vị trí tạm.

### Hai chiến lược đổi DN tạm

- [DefaultTempEntryRenamingStrategy] thêm suffix vào RDN của entry trong cùng subtree.
- [DifferentSubtreeTempEntryRenamingStrategy] đưa entry tạm vào một subtree riêng đã tồn tại.

Với recursive delete hoặc thao tác trên subtree, chiến lược mặc định có thể không phù hợp vì không thể rename entry cha khi vẫn còn child. Cần chọn chiến lược khác subtree theo tài liệu Spring LDAP và kiểm thử trên directory thực tế.

## 7. Cấu hình transaction cho LDAP riêng

Ví dụ chính dưới đây dùng constructor của [ContextSourceTransactionManager] có từ Spring LDAP 4.1. Transaction manager nhận **ContextSource gốc**, còn LdapTemplate sử dụng một [TransactionAwareContextSourceProxy]. Proxy nằm trong package [org.springframework.ldap.transaction.compensating.manager].

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableTransactionManagement;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.transaction.compensating.manager.ContextSourceTransactionManager;
import org.springframework.ldap.transaction.compensating.manager.TransactionAwareContextSourceProxy;

@Configuration
@EnableTransactionManagement
public class LdapTransactionConfiguration {

    @Bean
    ContextSourceTransactionManager ldapTransactionManager(
            @Qualifier("targetContextSource") ContextSource target) {

        return new ContextSourceTransactionManager(target);
    }

    @Bean
    ContextSource transactionAwareContextSource(
            @Qualifier("targetContextSource") ContextSource target) {
        return new TransactionAwareContextSourceProxy(target);
    }

    @Bean
    LdapTemplate ldapTemplate(
            @Qualifier("transactionAwareContextSource")
            ContextSource transactionAwareContextSource) {
        return new LdapTemplate(transactionAwareContextSource);
    }
}
~~~

Với Spring LDAP 3.3 đến 4.0, constructor nhận ContextSource chưa có. Code tương ứng ở các phiên bản đó dùng no-argument constructor và [setContextSource(target)]. Từ 4.1, constructor được thêm và setter cũ bị deprecated; vì vậy nên dùng constructor khi dự án chạy 4.1+.

Trong cấu hình này:

- [targetContextSource] là ContextSource gốc đã cấu hình URL, base DN, bind credential và TLS.
- Transaction manager nhận ContextSource gốc qua constructor (hoặc [setContextSource] trên các phiên bản cũ).
- LdapTemplate dùng proxy transaction-aware để các thao tác ghi được ghi nhận.
- Không tạo một LdapTemplate khác dùng trực tiếp ContextSource gốc cho cùng luồng transactional.
- Repository và service cần dùng đúng LdapTemplate đã được cấu hình.

Một service có thể chọn transaction manager LDAP:

~~~java
@Service
public class DirectoryAccountService {

    private final LdapTemplate ldapTemplate;

    public DirectoryAccountService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Transactional(transactionManager = "ldapTransactionManager")
    public void createAccount(AccountEntry account) {
        ldapTemplate.create(account);
        // Có thể thực hiện thêm thao tác LDAP khác trong cùng transaction.
    }
}
~~~

Đây là transaction **chỉ dành cho các thao tác LDAP**. Nếu cùng nghiệp vụ còn ghi JDBC, transaction manager này không tự bao gồm JDBC.

### Khi nào nên dùng?

Phù hợp khi một use case cần nhiều thao tác LDAP phụ thuộc nhau, ví dụ:

- Tạo entry rồi gán thêm attribute.
- Đổi DN rồi cập nhật các thuộc tính liên quan trong cùng directory.
- Thực hiện một số thao tác LDAP mà muốn Spring LDAP cố gắng phục hồi nếu bước sau thất bại.

Không nên bật chỉ để bọc một operation đơn lẻ nếu không cần cơ chế bù. Transaction hỗ trợ thêm thao tác ghi nhận và overhead.

## 8. Đối chiếu khả năng tích hợp JDBC theo phiên bản Spring LDAP

Khả năng tích hợp JDBC thay đổi đáng kể ở các bản major mới. Cần đối chiếu **Spring LDAP version**, không suy luận từ Spring Data LDAP version.

| Spring LDAP | LDAP compensating transaction | Manager ghép LDAP + JDBC | Ghi chú |
|---|---|---|---|
| 1.2.x trở đi | Có [ContextSourceTransactionManager] | Có [ContextSourceAndDataSourceTransactionManager] | Cơ chế client-side, không XA |
| 2.x | Có | Có | Dùng transaction namespace hoặc Java config theo API phiên bản |
| 3.0–3.2.x | Có | Có | Vẫn là transaction logic, không 2PC |
| 3.3.x | Có | Có nhưng đã deprecated | Javadoc khuyến nghị không dùng cách ghép hai manager không có XA |
| 4.0.x trở lên | Có | **Đã loại bỏ** | API ghép JDBC dựa trên Spring Framework cũ đã bị xóa |
| 4.2.0 hiện hành | Có | Không có manager ghép JDBC cũ | Chọn outbox/saga hoặc cơ chế điều phối riêng |

Trong Spring LDAP 4.1+, [ContextSourceTransactionManager] có constructor nhận trực tiếp ContextSource; [setContextSource] bị deprecated để khuyến khích constructor injection. Đây là thay đổi API của manager LDAP riêng, khác với việc loại bỏ manager ghép JDBC ở 4.0.

Các mốc cần nhớ:

- [ContextSourceAndDataSourceTransactionManager] tồn tại từ Spring LDAP 1.2.
- Trong Spring LDAP 3.3, class này đã deprecated. Javadoc nói rõ việc ghép hai transaction manager không có XA là ý tưởng không tốt; không có two-phase commit và commit/rollback có thể cho kết quả không mong đợi.
- Spring LDAP 4.0 loại bỏ [ContextSourceAndDataSourceTransactionManager] và [ContextSourceAndHibernateTransactionManager] do chúng phụ thuộc API đã bị loại khỏi Spring Framework 7.
- [ContextSourceTransactionManager] dành riêng cho LDAP vẫn còn trong Spring LDAP 4.x.

**Nếu nâng từ 3.3 lên 4.x:** phải tìm và xóa cấu hình [data-source-ref] hoặc [session-factory-ref] khỏi transaction manager LDAP. Thay thế bằng thiết kế outbox/saga hoặc cơ chế nhất quán phù hợp. Chỉ nâng dependency mà không rà soát cấu hình transaction có thể làm ứng dụng không compile hoặc không khởi động.

## 9. Manager ghép JDBC/LDAP cũ không phải XA

Trong Spring LDAP 3.3.x, [ContextSourceAndDataSourceTransactionManager] có thể quản lý một transaction logic kết hợp JDBC và LDAP. Tuy nhiên class đã deprecated và không có XA/2PC.

Theo tài liệu Spring LDAP, khi commit:

1. Phần LDAP được thực hiện trước.
2. Nếu phần LDAP commit thất bại, hệ thống có thể rollback phần JDBC.
3. JDBC được quản lý theo cơ chế của [DataSourceTransactionManager].
4. Nested transaction không được hỗ trợ.

Đây không phải bảo đảm atomic tuyệt đối. Nếu LDAP đã commit thành công nhưng JDBC commit gặp lỗi hoặc tiến trình mất kết nối ở thời điểm không xác định, hai resource vẫn có thể lệch trạng thái. Vì server LDAP không tham gia prepare/vote, coordinator không thể hỏi LDAP có sẵn sàng commit hay không.

Javadoc 3.3 đánh dấu class này deprecated và nêu rõ không có two-phase commit. Spring LDAP 4.0 loại bỏ class.

### XML cấu hình lịch sử cho 3.3.x

Đối với hệ thống cũ đang sử dụng Spring LDAP 3.3.x, tài liệu mô tả thuộc tính [data-source-ref] trên phần tử transaction manager:

~~~xml
<ldap:transaction-manager data-source-ref="dataSource">
    <ldap:default-renaming-strategy />
</ldap:transaction-manager>

<tx:annotation-driven />
~~~

Đây là cấu hình **tham khảo để đọc/duy trì hệ thống cũ**, không phải mẫu khuyến nghị cho ứng dụng mới. Không sao chép cấu hình này sang Spring LDAP 4.0+ vì tích hợp JDBC đã bị loại bỏ.

Không nên tự viết một class kế thừa [AbstractPlatformTransactionManager] để ghép JDBC và LDAP rồi gọi nó là XA. Nếu tự điều phối, phải tự định nghĩa rõ thứ tự commit, compensation, unknown outcome, retry và reconciliation.

## 10. Bảng chọn kiến trúc theo nhu cầu

| Nhu cầu | Phương án phù hợp | Đảm bảo và đánh đổi |
|---|---|---|
| Chỉ có nhiều thao tác LDAP phụ thuộc nhau | ContextSourceTransactionManager | Cố gắng bù các thao tác LDAP khi rollback |
| Ghi JDBC là dữ liệu chính, LDAP là bản chiếu/tài khoản cần đồng bộ | Transactional Outbox | JDBC + event bền vững trong một local transaction; LDAP được cập nhật eventual |
| Điều phối nhiều bước với hành động hoàn tác | Saga/Compensation | Có trạng thái tiến trình; cần idempotency và xử lý compensation thất bại |
| Chỉ cần thông báo sau JDBC commit, mất thông báo hiếm khi chấp nhận được | TransactionSynchronization / AFTER_COMMIT | Best-effort; tiến trình có thể dừng trước callback |
| Bắt buộc atomic giữa nhiều resource | Chỉ dùng XA khi từng resource thật sự hỗ trợ XA | LDAP support của Spring LDAP không cung cấp XA |
| Hệ thống cũ đang chạy 3.3.x | Đánh giá manager ghép cũ và lập kế hoạch thay thế | API deprecated, không 2PC; không nên mở rộng thêm |

Với phần lớn hệ thống Spring Data LDAP hiện đại, mô hình **JDBC outbox + LDAP consumer idempotent** là lựa chọn dễ vận hành hơn khi JDBC là nguồn dữ liệu chính và LDAP là hệ thống đồng bộ hóa danh tính.

## 11. Transactional Outbox: ghi dữ liệu và sự kiện trong cùng JDBC transaction

Outbox giải quyết khoảng trống giữa “ghi database thành công” và “gửi yêu cầu cập nhật LDAP”.

Trong một JDBC transaction, ứng dụng ghi:

1. Bản ghi nhân viên.
2. Trạng thái provision ban đầu.
3. Một event trong bảng outbox.

Cả ba cùng commit hoặc rollback trong JDBC. Một worker riêng đọc outbox và cập nhật LDAP sau đó.

~~~mermaid
flowchart TD
    API["API tạo nhân viên"]
    TX["JDBC transaction"]
    EMP["INSERT employee"]
    OUT["INSERT outbox event"]
    COMMIT["COMMIT JDBC"]
    WORKER["Outbox worker"]
    CLAIM["Claim event + lease"]
    LDAP["Idempotent LDAP operation"]
    DONE["Mark event succeeded"]
    RETRY["Schedule retry / dead letter"]

    API --> TX
    TX --> EMP
    TX --> OUT
    EMP --> COMMIT
    OUT --> COMMIT
    COMMIT --> WORKER
    WORKER --> CLAIM
    CLAIM --> LDAP
    LDAP -->|success| DONE
    LDAP -->|temporary failure| RETRY
    RETRY --> WORKER
~~~

Nếu JDBC rollback, outbox event cũng rollback nên worker không nhìn thấy sự kiện chưa commit. Nếu JDBC commit thành công nhưng worker chưa chạy, event vẫn còn để xử lý sau.

Outbox không tạo transaction xuyên JDBC và LDAP. Nó làm cho yêu cầu đồng bộ được lưu bền vững cùng dữ liệu nguồn, sau đó cho phép retry và reconciliation.

## 12. Thiết kế bảng outbox

Ví dụ schema SQL theo cú pháp PostgreSQL:

~~~sql
create table employee (
    id              varchar(64) primary key,
    display_name    varchar(255) not null,
    email           varchar(255) not null,
    provisioning_status varchar(32) not null
);

create table outbox_event (
    event_id        uuid primary key,
    aggregate_id    varchar(64) not null,
    event_type      varchar(100) not null,
    payload         jsonb not null,
    status          varchar(24) not null,
    attempts        integer not null default 0,
    next_attempt_at timestamptz not null default now(),
    lease_owner     varchar(128),
    lease_until     timestamptz,
    created_at      timestamptz not null default now(),
    completed_at    timestamptz,
    last_error_code varchar(100),
    last_error      text
);

create index outbox_ready_idx
    on outbox_event(status, next_attempt_at, created_at);
~~~

Các trạng thái gợi ý:

| Status | Ý nghĩa |
|---|---|
| PENDING | Chờ worker xử lý |
| PROCESSING | Worker đã claim và đang xử lý |
| SUCCEEDED | LDAP đã được đối chiếu với trạng thái đích |
| RETRY | Lỗi tạm thời, chờ thử lại |
| DEAD | Vượt chính sách retry; cần vận hành xử lý |

Không lưu password LDAP hoặc credential trong payload. Event chỉ nên chứa business ID và các dữ liệu tối thiểu để worker dựng DN/attribute cần thiết. Nếu payload có dữ liệu cá nhân, áp dụng quyền truy cập, mã hóa và retention policy phù hợp.

## 13. Ghi JDBC và outbox trong một transaction

Ví dụ service chỉ thực hiện JDBC:

~~~java
@Service
public class EmployeeCommandService {

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public EmployeeCommandService(
            JdbcTemplate jdbcTemplate,
            ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    @Transactional(transactionManager = "jdbcTransactionManager")
    public UUID createEmployee(CreateEmployeeCommand command) {
        UUID eventId = UUID.randomUUID();

        jdbcTemplate.update(
                """
                insert into employee
                    (id, display_name, email, provisioning_status)
                values (?, ?, ?, ?)
                """,
                command.employeeId(),
                command.displayName(),
                command.email(),
                "PENDING");

        String payload = serialize(
                new EmployeeCreatedPayload(
                        command.employeeId(),
                        command.displayName(),
                        command.email()));

        jdbcTemplate.update(
                """
                insert into outbox_event
                    (event_id, aggregate_id, event_type, payload, status)
                values (?, ?, ?, cast(? as jsonb), ?)
                """,
                eventId,
                command.employeeId(),
                "EmployeeCreated",
                payload,
                "PENDING");

        return eventId;
    }

    private String serialize(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize outbox event", ex);
        }
    }
}

public record EmployeeCreatedPayload(
        String employeeId,
        String displayName,
        String email) {
}
~~~

Điểm quan trọng:

- Bản ghi employee và event outbox nằm trong cùng JDBC transaction.
- Nếu serialization hoặc INSERT outbox lỗi, employee cũng rollback.
- Event ID ổn định được dùng để theo dõi lần xử lý và audit.
- Worker chỉ thấy event sau khi JDBC commit.
- Ví dụ dùng SQL PostgreSQL cho JSONB; với database khác, thay kiểu cột/cast theo dialect.

Không gọi LDAP bên trong transaction JDBC này. Nếu gọi LDAP trước khi commit JDBC, hệ thống lại có dual-write và mất lợi ích của outbox.

## 14. Claim event và thực hiện LDAP bên ngoài JDBC transaction

Worker cần tránh hai instance cùng xử lý một event. Một chiến lược phổ biến là claim event bằng lease:

1. Trong JDBC transaction ngắn, chọn event PENDING/RETRY đến hạn.
2. Ghi PROCESSING, lease_owner và lease_until.
3. Commit transaction claim.
4. Gọi LDAP bên ngoài transaction JDBC.
5. Nếu trạng thái LDAP đạt mục tiêu, mở transaction mới đánh dấu SUCCEEDED.
6. Nếu lỗi tạm thời, mở transaction mới ghi RETRY và next_attempt_at.

Không giữ row lock JDBC trong lúc chờ LDAP network response. Lease cho phép worker khác tiếp tục khi worker cũ chết hoặc lease hết hạn.

Pseudo-code:

~~~java
public void process(OutboxEvent event) {
    try {
        ldapProvisioner.ensureEmployeeExists(
                event.employeeId(),
                event.displayName(),
                event.email());

        outboxWriter.markSucceeded(event.eventId());
    } catch (TemporaryDirectoryException ex) {
        outboxWriter.scheduleRetry(
                event.eventId(),
                nextBackoff(event.attempts()),
                classify(ex));
    } catch (PermanentDirectoryException ex) {
        outboxWriter.markDead(
                event.eventId(),
                classify(ex));
    }
}
~~~

Các method của [outboxWriter] chạy transaction JDBC ngắn và độc lập. [ldapProvisioner] thực hiện thao tác LDAP ngoài JDBC transaction.

### Vì sao cần lease?

Nếu worker chết sau khi claim nhưng trước khi gọi LDAP, event không được bỏ quên. Khi lease hết hạn, worker khác có thể claim lại.

Nếu worker cũ vẫn chạy sau khi lease hết hạn, hai worker có thể cùng gọi LDAP. Do đó lease giảm trùng lặp nhưng không thay thế idempotency. Hãy kiểm tra lease owner/version trước khi ghi kết quả để worker cũ không ghi đè trạng thái mới hơn.

## 15. LDAP operation phải idempotent

Outbox thường cung cấp delivery at-least-once: một event có thể được xử lý nhiều lần. Vì vậy LDAP operation cần có semantics an toàn khi retry.

Ví dụ mục tiêu là “entry có uid=lan, mail=lan@example.org và employeeStatus=active”. Worker nên thực hiện **ensure desired state**:

1. Tìm entry theo business key ổn định trong base được kiểm soát.
2. Nếu chưa có, tạo entry.
3. Nếu đã có, so sánh và cập nhật các attribute cần thiết.
4. Nếu DN đã tồn tại nhưng thuộc business identity khác, dừng và báo conflict.
5. Chỉ đánh dấu event thành công khi trạng thái đích đã được xác minh.

Bảng ví dụ:

| Thao tác | Retry an toàn khi nào? | Cách thiết kế |
|---|---|---|
| Add entry | DN chưa tồn tại; lần trước có thể đã thành công | Khi nhận entryAlreadyExists, đọc lại và so business ID/desired state |
| Replace attribute | Giá trị đích xác định và không có side effect phụ | Ghi lại cùng giá trị, rồi xác minh |
| Add value vào group | Giá trị có thể đã được thêm ở lần trước | Đọc/đối chiếu membership hoặc xử lý attributeOrValueExists theo hợp đồng |
| Delete entry | Mục tiêu là entry không còn | No-such-object có thể là trạng thái đích đã đạt |
| Rename DN | DN đích có thể đã được tạo bởi lần trước | Kiểm tra cả source DN và target DN trước khi retry |

Không bắt mọi exception rồi bỏ qua. Ví dụ DN đích tồn tại nhưng thuộc người dùng khác không phải thành công idempotent.

Nếu directory hỗ trợ custom attribute, có thể lưu event/version marker để đối chiếu; nhưng phải thiết kế schema và quyền phù hợp. Không thêm marker tùy tiện vào objectClass chuẩn.

## 16. Unknown outcome: timeout không chứng minh LDAP chưa ghi

Một tình huống khó:

1. Client gửi AddRequest.
2. LDAP server tạo entry.
3. Server gửi response nhưng kết nối bị đứt trước khi client nhận được.
4. Client nhận timeout/communication exception.

Ứng dụng không biết chắc AddRequest đã thành công hay chưa. Đây là **unknown outcome**.

Cách xử lý:

- Không retry mù với logic “exception nghĩa là chưa ghi”.
- Đọc lại theo business key/DN đích.
- So sánh attribute với desired state.
- Nếu entry đúng, đánh dấu event đã hoàn thành.
- Nếu entry không có, retry.
- Nếu DN tồn tại nhưng dữ liệu khác, đưa vào conflict/reconciliation.

Tương tự, nếu ModifyRequest timeout, đọc lại attribute trước khi gửi lại. Nếu DeleteRequest timeout, kiểm tra entry còn tồn tại hay không.

## 17. Backoff, retry và dead-letter

Không retry liên tục với cùng khoảng thời gian vì có thể làm LDAP server quá tải khi đang sự cố.

Ví dụ exponential backoff có jitter:

~~~java
Duration nextBackoff(int attempts) {
    int exponent = Math.min(attempts, 8);
    long baseMillis = 1_000L * (1L << exponent);
    long cappedMillis = Math.min(baseMillis, 300_000L);

    long jitter = ThreadLocalRandom.current()
            .nextLong(0, Math.max(1, cappedMillis / 4));

    return Duration.ofMillis(cappedMillis + jitter);
}
~~~

Đây là ví dụ minh họa; production cần giới hạn attempts, tổng thời gian retry và chính sách lỗi.

Phân loại lỗi:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | LDAP unavailable, timeout, connection reset | Retry với backoff |
| Rate/limit | Server busy, admin limit, throttling | Giảm concurrency, retry sau |
| Dữ liệu vĩnh viễn | Attribute không hợp lệ, schema violation | DEAD, sửa dữ liệu/schema |
| Xung đột nghiệp vụ | DN đã thuộc business ID khác | Manual reconciliation |
| Quyền truy cập | Insufficient access rights | Dừng retry nhanh, kiểm tra ACL |
| Unknown outcome | Timeout sau write | Read-after-timeout và reconcile |

Event DEAD cần có dashboard, cảnh báo và quy trình replay có kiểm soát. Không xóa event lỗi ngay khi vượt số lần retry; giữ thông tin đủ để phân tích và sửa trạng thái.

## 18. Compensation và Saga

Outbox giải quyết đồng bộ eventual. Một số nghiệp vụ cần điều phối nhiều bước và có hành động bù khi một bước thất bại. Đây là lúc saga phù hợp.

Ví dụ tạo tài khoản có các bước:

| Bước | Hành động | Compensation có thể có |
|---|---|---|
| 1 | Tạo hồ sơ employee trong JDBC | Đánh dấu hồ sơ CANCELLED hoặc xóa theo policy |
| 2 | Tạo LDAP user | Xóa LDAP user nếu chắc chắn thuộc operation hiện tại |
| 3 | Thêm user vào group | Xóa membership vừa thêm |
| 4 | Gửi event cho hệ thống khác | Gửi event thu hồi/compensating event nếu nghiệp vụ hỗ trợ |

Saga lưu trạng thái từng bước. Nếu bước 3 thất bại, orchestrator quyết định retry bước 3 hoặc bù bước 2 và bước 1.

~~~mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> JdbcCommitted: Ghi employee + outbox
    JdbcCommitted --> LdapCreated: Tạo/đối chiếu LDAP user
    LdapCreated --> GroupAssigned: Gán group
    GroupAssigned --> Completed
    LdapCreated --> RetryGroup: Group update lỗi tạm thời
    RetryGroup --> GroupAssigned: Retry thành công
    LdapCreated --> Compensating: Lỗi vĩnh viễn
    Compensating --> Cancelled: Bù LDAP/JDBC thành công
    Compensating --> NeedsReconciliation: Bù thất bại
    NeedsReconciliation --> Completed: Đối chiếu/sửa thủ công
    NeedsReconciliation --> Cancelled: Hoàn tất bù
    Completed --> [*]
    Cancelled --> [*]
~~~

### Compensation không phải rollback hoàn hảo

Một compensation là thao tác nghiệp vụ mới để đưa hệ thống về trạng thái chấp nhận được. Nó không xóa lịch sử và không luôn đảo ngược chính xác thao tác ban đầu.

Ví dụ:

- Xóa LDAP user có thể thất bại do ACL hoặc user đã được một hệ thống khác cập nhật.
- Xóa membership có thể xóa một thay đổi hợp lệ do admin khác vừa thực hiện nếu ứng dụng không biết ai đã thêm giá trị.
- Khôi phục attribute cũ có thể ghi đè thay đổi mới của người khác.
- Gửi email hoặc thông báo đã phát ra thì không thể “thu hồi” hoàn toàn.

Thiết kế compensation phải ghi rõ operation ID, business owner, giá trị trước/sau và điều kiện chỉ bù nếu trạng thái hiện tại vẫn do workflow đó tạo ra.

## 19. @TransactionalEventListener(AFTER_COMMIT) có đủ không?

Spring hỗ trợ callback sau khi transaction commit, ví dụ:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onEmployeeCreated(EmployeeCreated event) {
    ldapProvisioner.ensureEmployeeExists(event.employeeId());
}
~~~

Cách này tiện khi cần chạy side effect sau commit JDBC. Tuy nhiên, callback trong tiến trình không phải outbox bền vững.

Cửa sổ lỗi:

~~~text
JDBC commit thành công
        |
        v
Process crash trước khi callback chạy
        |
        v
Không có event bền vững để retry
~~~

Dùng AFTER_COMMIT khi side effect best-effort, có thể được tạo lại từ nguồn khác hoặc mất thông báo trong một khoảng thời gian là chấp nhận được.

Nếu việc tạo LDAP account là nghĩa vụ phải hoàn tất, hãy ghi event vào outbox trong cùng transaction JDBC. Callback có thể dùng để đánh thức worker sớm, nhưng outbox vẫn là nguồn bền vững.

## 20. Transaction synchronization không thay thế outbox

[TransactionSynchronizationManager] cho phép đăng ký callback vào vòng đời transaction hiện tại. Nó hữu ích để chạy code trước/sau commit hoặc cleanup resource.

Nhưng synchronization:

- Không làm LDAP trở thành JDBC resource.
- Không tạo XA enlistment.
- Không lưu callback qua restart process.
- Không bảo đảm callback được chạy nếu JVM chết đột ngột.
- Không tự retry khi LDAP unavailable.

Có thể kết hợp synchronization với outbox: sau commit, callback phát tín hiệu cho worker; worker vẫn đọc event bền vững từ bảng outbox. Nếu tín hiệu mất, polling tiếp tục tìm thấy event.

## 21. Version management: Spring LDAP và Spring Data LDAP là hai version line

Spring LDAP và Spring Data LDAP có chu kỳ phát hành riêng. Số major/minor của hai project không nhất thiết giống nhau.

- Spring LDAP cung cấp [LdapTemplate], [ContextSource], ODM và transaction support.
- Spring Data LDAP cung cấp repository abstraction dựa trên Spring LDAP.
- Spring Framework cung cấp transaction abstraction và [PlatformTransactionManager].
- Spring Boot BOM quản lý phiên bản dependency trong hệ sinh thái Boot.
- Spring Data Release Train BOM quản lý các module Spring Data tương thích với nhau.

Không chọn Spring LDAP 4.2 chỉ vì Spring Data LDAP cũng có số 4.2; hãy kiểm tra dependency graph thực tế và BOM đang quản lý.

### Phiên bản tham chiếu tại thời điểm biên soạn

Tại thời điểm đối chiếu tài liệu (26-11-2026), các dòng ổn định được tài liệu chính thức liệt kê gồm:

| Thành phần | Một số dòng stable được công bố | Ý nghĩa cho bài học |
|---|---|---|
| Spring LDAP | 3.3.8, 4.0.7, 4.1.3, 4.2.0 | 3.3 còn manager JDBC deprecated; 4.0+ đã loại bỏ |
| Spring Data LDAP | 3.5.13, 4.0.9, 4.1.3, 4.2.0 | Chọn theo Spring Data Release Train |
| Spring Framework | 6.x cho các dòng cũ; 7.0/7.1 cho các dòng mới | Spring LDAP 4.x được cập nhật theo Framework 7 |
| Spring Boot | BOM theo từng dòng Boot | Dùng BOM để quản lý Spring Framework, Spring LDAP và Spring Data |

Danh sách patch release thay đổi theo thời gian. Trước khi nâng cấp, kiểm tra release notes và dependency metadata chính thức.

## 22. Quản lý dependency bằng BOM

Với Spring Boot, ưu tiên để Boot BOM quản lý dependency. Không đặt version thủ công cho mọi module nếu không có lý do tương thích cụ thể.

Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
</dependencies>
~~~

Nếu không dùng Spring Boot, có thể import Spring Data Release Train BOM cho các module Spring Data, và quản lý Spring LDAP/Spring Framework theo dependency management tương ứng:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>2026.1.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi cần kiểm tra version được resolve:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.ldap,org.springframework.data,org.springframework
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-ldap-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-ldap --configuration runtimeClasspath
~~~

Không override riêng Spring LDAP mà bỏ qua Spring Framework version. Spring LDAP 4.x dùng Spring Framework 7; nếu classpath trộn Spring Framework 6 và 7 có thể gây lỗi linkage hoặc runtime.

## 23. Lộ trình nâng từ Spring LDAP 3.3 lên 4.x

Nếu ứng dụng hiện dùng [ContextSourceAndDataSourceTransactionManager], việc nâng lên 4.x cần thay đổi thiết kế, không chỉ đổi tên class.

Checklist:

1. Tìm mọi bean [ContextSourceAndDataSourceTransactionManager].
2. Tìm XML [data-source-ref] và [session-factory-ref] trong transaction manager.
3. Tìm [@Transactional] đang dựa vào manager ghép cũ.
4. Xác định JDBC có phải nguồn dữ liệu chính hay LDAP mới là nguồn authoritative.
5. Nếu JDBC là nguồn chính, tạo outbox trong cùng transaction JDBC.
6. Viết LDAP consumer idempotent và retry có backoff.
7. Bổ sung trạng thái provisioning/reconciliation.
8. Nếu cần workflow nhiều bước, triển khai saga với compensation rõ ràng.
9. Giữ [ContextSourceTransactionManager] riêng nếu vẫn cần compensating transaction cho nhiều thao tác LDAP.
10. Chạy integration test ở các cửa sổ lỗi trước khi triển khai.

Không thay manager ghép cũ bằng [ChainedTransactionManager] hoặc tự nối hai local transaction manager rồi giả định đã có XA. Một chuỗi commit có thể vẫn để lại trạng thái một resource đã commit còn resource kia rollback.

## 24. Ma trận lỗi khi phối hợp JDBC và LDAP

| JDBC | LDAP | Trạng thái có thể xảy ra | Cách xử lý |
|---|---|---|---|
| Commit | Thành công | Đồng bộ | Đánh dấu provisioning complete |
| Commit | Thất bại trước khi ghi | JDBC có nhưng LDAP thiếu | Retry event outbox |
| Commit | Timeout, unknown outcome | LDAP có thể đã ghi hoặc chưa | Read-after-timeout, reconcile rồi retry |
| Rollback | Chưa gọi LDAP | Không có bản ghi, không có entry | Không cần bù |
| Rollback | LDAP đã ghi trước đó | LDAP orphan | Compensation hoặc reconcile |
| Commit | LDAP thành công, group update lỗi | User tồn tại nhưng membership thiếu | Retry riêng bước group |
| Commit | Worker chết trước khi đánh dấu outbox | LDAP có thể đã thành công, event chưa hoàn tất | Retry idempotent |
| Compensation | LDAP rollback thành công | Trạng thái được bù | Đánh dấu workflow cancelled |
| Compensation | LDAP rollback thất bại | Trạng thái lệch còn tồn tại | NeedsReconciliation + cảnh báo |

Một workflow tốt lưu trạng thái đủ chi tiết để biết **bước nào đã thành công**, thay vì chỉ có một cờ success/failure chung.

## 25. Reconciliation: phát hiện và sửa trạng thái lệch

Retry xử lý lỗi ngắn hạn; reconciliation xử lý trạng thái đã lệch hoặc không rõ kết quả.

Ví dụ job đối chiếu định kỳ:

1. Đọc employee có provisioning_status không phải COMPLETE.
2. Tìm LDAP entry theo business key.
3. Nếu entry thiếu, tạo lại.
4. Nếu entry có nhưng attribute sai, sửa theo desired state.
5. Kiểm tra group membership cần thiết.
6. Ghi trạng thái kết quả và timestamp.
7. Nếu xung đột identity/schema/ACL, chuyển sang manual review.

Có thể thêm job đối chiếu ngược:

- LDAP entry không còn business record tương ứng.
- JDBC employee đã disabled nhưng LDAP account vẫn enabled.
- Group membership không khớp quyền nghiệp vụ.
- DN đã thay đổi nhưng reference ở JDBC/cache còn DN cũ.

Reconciliation cần có chính sách xử lý conflict. Không tự động xóa entry chỉ vì không tìm thấy JDBC row nếu directory còn được hệ thống khác quản lý hoặc có dữ liệu chưa đồng bộ.

## 26. Thiết kế trạng thái provisioning

Không nên biểu diễn toàn bộ workflow chỉ bằng boolean [ldapCreated]. Có thể dùng state machine:

| State | Ý nghĩa |
|---|---|
| NOT_REQUESTED | Chưa yêu cầu đồng bộ |
| PENDING | Event đã commit, chờ worker |
| PROCESSING | Đang thực hiện |
| LDAP_USER_READY | User entry đã được tạo/đối chiếu |
| GROUPS_READY | Group membership đã được gán |
| COMPLETE | LDAP đạt desired state |
| RETRY | Có lỗi tạm thời |
| COMPENSATING | Đang thực hiện thao tác bù |
| NEEDS_RECONCILIATION | Không thể tự xác định trạng thái |
| FAILED_PERMANENT | Lỗi vĩnh viễn cần xử lý nghiệp vụ |

State machine giúp API trả trạng thái minh bạch. Ví dụ API tạo employee có thể trả [202 Accepted] cùng provisioning status PENDING, thay vì báo “đã tạo tài khoản” trước khi LDAP thực sự sẵn sàng.

## 27. Kiểm thử tích hợp cho dual-write

Unit test chỉ xác minh logic service. Để kiểm tra transaction boundary và compensation, cần integration test với JDBC database và LDAP directory test.

### Các nhóm kiểm thử

| Nhóm test | Nội dung |
|---|---|
| JDBC transaction | Employee và outbox cùng commit/rollback |
| LDAP compensating transaction | Bind/modify/rename/unbind rollback theo recorder |
| Outbox worker | Claim lease, retry, mark success/dead |
| Idempotency | Chạy cùng event nhiều lần không tạo duplicate sai |
| Unknown outcome | Mô phỏng timeout sau khi server đã nhận write |
| Compensation | Compensation thành công và thất bại |
| Reconciliation | Sửa dữ liệu lệch giữa JDBC và LDAP |
| Version compatibility | Build/test với dependency line đang hỗ trợ |
| Security | ACL, bind identity, TLS và quyền đọc/ghi riêng |

### Failure injection cần có

1. JDBC INSERT employee thành công nhưng INSERT outbox thất bại.
2. JDBC commit thành công, LDAP server unavailable.
3. LDAP Add thành công nhưng client timeout trước response.
4. LDAP user tạo thành công, group Modify bị từ chối.
5. LDAP update thành công, worker chết trước khi mark outbox success.
6. Lease hết hạn khi worker cũ còn đang chạy.
7. Compensation gặp ACL denied.
8. Hai workflow đồng thời thay đổi cùng một entry.
9. LDAP entry tồn tại với business ID khác.
10. Nâng Spring LDAP từ 3.3 lên 4.x và xác nhận cấu hình manager cũ đã được thay thế.

Test cần xác minh cả database row, outbox state, LDAP entry và membership sau mỗi tình huống. Chỉ kiểm tra exception không đủ để chứng minh hệ thống đã phục hồi.

## 28. Bảo mật và vận hành

Khi phối hợp JDBC và LDAP:

- Dùng LDAPS hoặc StartTLS và xác minh chứng chỉ.
- Bind identity của worker chỉ có quyền cần thiết trên OU/group tương ứng.
- Tách service account đọc và ghi nếu policy yêu cầu.
- Không lưu bind password trong outbox payload hoặc log.
- Không đưa DN, email, UID nhạy cảm vào metric labels có cardinality cao.
- Audit event ID, business ID đã được bảo vệ, operation type và result code.
- Hạn chế quyền sửa trạng thái outbox; chỉ worker/service được phép claim và complete.
- Có cảnh báo cho event quá tuổi, retry vượt ngưỡng, DEAD và NEEDS_RECONCILIATION.
- Đặt giới hạn concurrency để không làm quá tải LDAP server.
- Theo dõi replication delay nếu directory có nhiều replica và workflow đọc sau ghi.
- Định nghĩa retention và purge outbox sau khi hết thời gian audit/replay.

Nếu dùng cache hoặc token chứa group authorities, cập nhật LDAP thành công chưa chắc quyền đã có hiệu lực ở mọi nơi ngay lập tức. Cần xác định thời gian cache refresh, session/token revocation và replication consistency.

## 29. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| JDBC rollback nhưng LDAP entry vẫn còn | Chỉ dùng DataSourceTransactionManager | Dùng outbox/saga hoặc transaction LDAP phù hợp |
| @Transactional bao quanh cả hai nhưng vẫn lệch | Một transaction manager chỉ quản lý một resource | Chỉ rõ manager và thiết kế integration riêng |
| Manager ghép không compile trên Spring LDAP 4.x | ContextSourceAndDataSourceTransactionManager đã bị loại bỏ | Thay bằng outbox/saga |
| Dùng manager ghép 3.3 nhưng tưởng là XA | API deprecated, không 2PC | Không dùng cho yêu cầu atomic tuyệt đối |
| LDAP rollback không phục hồi sau network failure | Server không biết transaction client | Reconcile theo desired state |
| Compensation ghi đè thay đổi của admin khác | Không có isolation | Conditional compensation/version guard |
| Worker tạo duplicate entry | Retry không idempotent | Read-before-retry và so business identity |
| Event bị xử lý hai lần | Outbox at-least-once/lease hết hạn | Idempotent LDAP consumer |
| Event mất sau JDBC commit | Chỉ dùng AFTER_COMMIT callback | Ghi outbox cùng transaction |
| Outbox stuck PROCESSING | Worker chết, lease không hết hoặc không có reclaim | Lease expiry và monitor |
| Mark success trước khi LDAP xác minh | Sai thứ tự workflow | Chỉ complete sau read/verify desired state |
| Nâng Spring Data nhưng Spring LDAP lệch | Quản lý version rời rạc | Dùng BOM và kiểm tra dependency tree |
| Recursive delete rollback lỗi | Temporary renaming strategy không phù hợp subtree | Chọn DifferentSubtreeTempEntryRenamingStrategy |
| Reconciliation xóa nhầm entry | Không phân biệt owner/source of truth | Xác minh business identity và policy trước khi sửa/xóa |

## 30. Bài tập thực hành

**Bối cảnh:** ứng dụng nhân sự lưu employee trong PostgreSQL và tài khoản trong LDAP. Khi tạo nhân viên, hệ thống cần tạo LDAP user, thêm vào group mặc định và cập nhật provisioning status.

Thực hiện trên môi trường test:

1. Tạo bảng employee và outbox_event theo schema đã học.
2. Viết service tạo employee và outbox event trong cùng JDBC transaction.
3. Kiểm tra khi INSERT outbox lỗi thì employee cũng rollback.
4. Viết worker claim event bằng lease, gọi LDAP ngoài JDBC transaction.
5. Tạo LDAP user theo desired state, xử lý DN đã tồn tại và xác minh business identity.
6. Thêm user vào group bằng thao tác idempotent.
7. Mark outbox success sau khi đọc lại và xác minh trạng thái LDAP.
8. Mô phỏng LDAP unavailable và kiểm tra retry/backoff.
9. Mô phỏng timeout sau AddRequest nhưng trước response; xác minh worker không tạo duplicate sai.
10. Mô phỏng worker chết sau LDAP success nhưng trước khi mark event success.
11. Viết reconciliation job cho employee PENDING quá thời hạn.
12. Viết saga state machine và compensation khi group membership không thể tạo.
13. Chạy integration test transaction LDAP riêng bằng ContextSourceTransactionManager.
14. Đọc Javadoc Spring LDAP 3.3 cho ContextSourceAndDataSourceTransactionManager và xác nhận class deprecated/no XA.
15. Nâng sample lên Spring LDAP 4.x; loại bỏ cấu hình data-source-ref và thay bằng outbox.
16. Kiểm tra dependency tree để xác nhận Spring Data LDAP, Spring LDAP và Spring Framework tương thích.
17. Viết báo cáo failure matrix và cách khôi phục từng trạng thái.

**Tiêu chí hoàn thành:** người học phân biệt được transaction JDBC và LDAP compensating transaction; giải thích chính xác vì sao manager ghép cũ không phải XA và bị loại bỏ ở Spring LDAP 4.0; triển khai được outbox worker idempotent, retry và reconciliation; đồng thời kiểm thử các cửa sổ lỗi giữa hai resource.

## 31. Tổng kết và tài liệu tham khảo

JDBC và LDAP có ranh giới transaction khác nhau. [@Transactional] chỉ điều phối resource mà transaction manager tương ứng quản lý. Spring LDAP cung cấp [ContextSourceTransactionManager] để ghi nhận các thay đổi LDAP và cố gắng phục hồi bằng compensation, nhưng đó không phải transaction server-side có isolation.

Cơ chế [ContextSourceAndDataSourceTransactionManager] từng cho phép ghép JDBC và LDAP trong một transaction logic. Tuy nhiên nó không có XA/2PC, đã deprecated trong Spring LDAP 3.3 và bị loại bỏ ở 4.0. Ứng dụng mới nên dùng outbox hoặc saga khi cần đồng bộ bền vững giữa JDBC và LDAP.

Các điểm cần nhớ:

- Tách rõ transaction manager JDBC và LDAP.
- Dùng transaction-aware ContextSource khi cần LDAP compensating transaction.
- Không gọi cơ chế ghép local managers là XA.
- Ghi outbox cùng dữ liệu nguồn trong một JDBC transaction.
- Gọi LDAP ngoài JDBC transaction và thiết kế consumer idempotent.
- Xử lý timeout như unknown outcome, không giả định chưa ghi.
- Có retry/backoff, lease, dead-letter và reconciliation.
- Compensation cần guard để tránh ghi đè thay đổi hợp lệ của client khác.
- Quản lý version bằng BOM và kiểm tra dependency graph.
- Kiểm thử failure injection với cả JDBC lẫn directory thật.

Tài liệu tham khảo:

- [Spring LDAP 4.2 — Transaction Support](https://docs.spring.io/spring-ldap/reference/transaction-support.html): compensating transaction, ContextSourceTransactionManager và xác nhận JDBC integration đã bị loại bỏ.
- [ContextSourceTransactionManager API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/ContextSourceTransactionManager.html): transaction LDAP phía client, giới hạn network failure/isolation và TransactionAwareContextSourceProxy.
- [ContextSourceAndDataSourceTransactionManager API — Spring LDAP 3.3](https://docs.spring.io/spring-ldap/docs/3.3.x/api/org/springframework/ldap/transaction/compensating/manager/ContextSourceAndDataSourceTransactionManager.html): class deprecated, không XA/2PC, nested transaction không hỗ trợ.
- [What’s New in Spring LDAP 4.0](https://docs.spring.io/spring-ldap/reference/4.0/whats-new.html): loại bỏ ContextSourceAndDataSourceTransactionManager và ContextSourceAndHibernateTransactionManager.
- [TransactionAwareContextSourceProxy API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/TransactionAwareContextSourceProxy.html): proxy giữ DirContext trong transaction và ghi nhận thao tác bù.
- [Getting Spring LDAP](https://docs.spring.io/spring-ldap/reference/getting-spring-ldap.html): quản lý dependency Spring LDAP với Spring Boot và standalone.
- [Spring Data LDAP Dependencies](https://www.springframework.org/spring-data/ldap/reference/data-commons/dependencies.html): Spring Data Release Train BOM và phiên bản Spring Data LDAP tương thích.
- [Spring Boot — Distributed Transactions with JTA](https://docs.spring.io/spring-boot/reference/io/jta.html): điều kiện JTA/XA với nhiều XA resources.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction abstraction và cách cấu hình transaction manager.
- [RFC 5805 — Lightweight Directory Access Protocol (LDAP) Transactions](https://www.rfc-editor.org/rfc/rfc5805): LDAP Transactions extension ở trạng thái Experimental, các OID discovery và giới hạn của transaction LDAP phía server.
