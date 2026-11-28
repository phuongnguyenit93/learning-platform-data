# Giới hạn rollback khi mất kết nối hoặc thao tác bù thất bại

Một service cập nhật LDAP theo nhiều bước: thay đổi thuộc tính nhân viên, gỡ nhân viên khỏi nhóm cũ, rồi thêm vào nhóm mới. Bước cuối phát sinh lỗi nghiệp vụ nên Spring bắt đầu rollback. Nhưng đúng lúc đó, kết nối LDAP bị ngắt. Ứng dụng không biết lệnh cập nhật cuối đã tới server chưa, cũng không thể gửi các thao tác bù còn lại.

Đây là giới hạn quan trọng của **compensating transaction** trong Spring LDAP. `ContextSourceTransactionManager` ghi nhận trạng thái trước các thao tác thay đổi và cố gắng thực hiện thao tác ngược để khôi phục dữ liệu. Cơ chế này chạy ở phía client, phụ thuộc kết nối LDAP và không tạo ra một transaction ACID do server quản lý. Nếu mất mạng làm transaction thất bại, Spring LDAP nêu rõ rằng transaction manager không thể khôi phục trạng thái; khả năng rollback có thể mất hoàn toàn. LDAP cũng không cung cấp isolation cho chuỗi thao tác bù này. [ContextSourceTransactionManager API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/ContextSourceTransactionManager.html).

Bài thuộc chương **Giao dịch bù trừ** của module `SPRING_DATA_LDAP`: truy cập dịch vụ thư mục LDAP qua Spring Data LDAP, ánh xạ entry phân cấp sang Java object, hiểu DN, `objectClass`, schema, repository, `LdapTemplate`, CRUD, filter an toàn, bảo mật kết nối và kiểm thử directory. Trọng tâm là nhận diện những trạng thái rollback không thể khẳng định, xử lý khi thao tác bù thất bại và thiết kế quy trình phục hồi có thể kiểm tra được.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao rollback của `ContextSourceTransactionManager` là **bù trừ phía client**, không phải rollback server-side.
- Phân biệt lỗi thao tác có LDAP response rõ ràng với trường hợp mất response và **không biết server đã áp dụng lệnh hay chưa**.
- Mô tả cách Spring LDAP ghi lại trạng thái trước thao tác, tạo executor bù và chạy các thao tác bù theo thứ tự ngược.
- Nhận diện nguyên nhân khiến compensation thất bại: network, ACL, schema, DN thay đổi, entry bị xóa hoặc dữ liệu bị writer khác sửa.
- Hiểu giới hạn của rollback khi `DirContext` mất kết nối và khi cleanup của thao tác tạm thời thất bại.
- Bảo toàn cả lỗi nghiệp vụ ban đầu và lỗi rollback trong log/diagnostic.
- Không retry mù một thao tác ghi khi kết quả trước đó còn chưa xác định.
- Thiết kế trạng thái `UNKNOWN`, nhật ký phục hồi bền vững, reconciliation và thao tác bù idempotent.
- Kiểm tra trạng thái LDAP sau sự cố bằng một kết nối mới và một danh tính có quyền phù hợp.
- Viết integration test có fault injection để xác minh rollback thành công, rollback thất bại và outcome không xác định.

## 2. Rollback của Spring LDAP thực sự làm gì?

LDAP core protocol định nghĩa các operation như Add, Delete, Modify và Modify DN. Mỗi request được server xử lý và trả response. Spring LDAP cung cấp `ContextSourceTransactionManager` để phối hợp nhiều thao tác thay đổi bằng cách **ghi nhận trạng thái cần thiết trước từng thao tác**, sau đó thực hiện các thao tác bù nếu transaction phải rollback.

Một transaction có thể hình dung như sau:

~~~text
Bắt đầu transaction
  |
  +-- Ghi lại trạng thái trước operation A
  +-- Thực hiện operation A
  |
  +-- Ghi lại trạng thái trước operation B
  +-- Thực hiện operation B
  |
  +-- Ghi lại trạng thái trước operation C
  +-- Thực hiện operation C
  |
  +-- Thành công? -------------------- Có --> Commit/cleanup
                 |
                 Không
                 |
                 v
        Chạy compensation C
        Chạy compensation B
        Chạy compensation A
                 |
                 v
          Kết thúc rollback
~~~

Mỗi operation sửa đổi được Spring LDAP hỗ trợ có recorder/executor tương ứng. Recorder thu thập dữ liệu trước thao tác; executor thực hiện thao tác, commit hoặc rollback tùy kết quả transaction. `DefaultCompensatingTransactionOperationManager` quản lý stack các executor và thực hiện rollback theo **thứ tự ngược**. [DefaultCompensatingTransactionOperationManager API](https://docs.spring.io/spring-ldap/reference/4.0/api/java/org/springframework/transaction/compensating/support/DefaultCompensatingTransactionOperationManager.html).

Các operation được transaction-aware proxy theo dõi gồm:

- `bind`
- `unbind`
- `rebind`
- `rename`
- `modifyAttributes`

Việc ghi nhận và bù trừ chỉ hoạt động khi các thao tác đi qua `TransactionAwareContextSourceProxy` gắn với đúng `ContextSource` của `ContextSourceTransactionManager`. Nếu một đoạn code bypass proxy và dùng một `ContextSource` khác, manager không thể ghi nhận đầy đủ các thay đổi đó. [Spring LDAP transaction manager](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/ContextSourceTransactionManager.html).

### 2.1. Vì sao không thể gọi đây là ACID rollback?

Có ba giới hạn cần nhớ:

1. **Client-side:** Spring ghi lại dữ liệu và gửi các operation ngược qua LDAP connection. Server không giữ một transaction chung cho toàn bộ chuỗi thao tác.
2. **Không có isolation:** client khác có thể đọc hoặc sửa cùng entry trong lúc transaction của ứng dụng đang chạy.
3. **Phụ thuộc network:** nếu lỗi transaction do network failure, transaction manager không có khả năng bảo đảm khôi phục trạng thái LDAP.

Vì vậy, “Spring đã gọi rollback” và “directory chắc chắn trở về đúng trạng thái ban đầu” là hai kết luận khác nhau. Cần biết thao tác bù đã được gửi, server có trả response thành công hay không, và trạng thái sau cùng đã được xác minh chưa.

## 3. Bốn trạng thái cần phân biệt khi xử lý sự cố

Trong vận hành, không nên chỉ có hai nhãn `SUCCESS` và `FAILED`. Với LDAP, ít nhất cần phân biệt:

| Trạng thái | Ý nghĩa | Hành động tiếp theo |
|---|---|---|
| `KNOWN_REJECTED` | Server trả LDAP result code xác nhận operation bị từ chối | Phân tích lỗi; với một Modify request bị trả lỗi, các thay đổi trong request đó không được áp dụng theo semantics của RFC 4511 |
| `KNOWN_APPLIED` | Client nhận response thành công | Ghi nhận operation đã được server xác nhận |
| `OUTCOME_UNKNOWN` | Request có thể đã tới server nhưng client không nhận được response | Đọc lại trạng thái trước khi retry hoặc bù |
| `COMPENSATION_FAILED` | Một thao tác bù nhận lỗi hoặc không thể hoàn tất | Ghi nhận recovery cần xử lý |
| `COMPENSATION_UNKNOWN` | Thao tác bù có thể đã được server áp dụng nhưng response bị mất | Reconcile trước khi thử lại |
| `STATE_VERIFIED` | Đã đọc directory và xác nhận trạng thái khớp mục tiêu phục hồi | Đóng recovery record |

`KNOWN_APPLIED` chỉ nói server đã trả response thành công cho operation đó. Nó không có nghĩa toàn bộ workflow nhiều operation đã hoàn tất. `STATE_VERIFIED` là kết quả của bước đối soát sau sự cố, không thể suy ra chỉ từ việc method Java không ném exception.

### 3.1. Một Modify request có tính atomic riêng

RFC 4511 quy định server trả một `ModifyResponse` cho một `ModifyRequest`. Nếu response báo lỗi, client có thể kỳ vọng không có modification nào trong request đó được áp dụng; nếu response báo thành công, tất cả các modification trong request đã được áp dụng. Nhưng nếu **không nhận được response**, client không thể xác định operation đã được áp dụng hay chưa. [RFC 4511 — LDAP Modify operation](https://www.rfc-editor.org/rfc/rfc4511).

~~~text
Server trả resultCode = insufficientAccessRights
  -> Biết request bị từ chối.

Server trả resultCode = success
  -> Biết request đã hoàn tất.

TCP/TLS bị ngắt sau khi gửi request, trước khi nhận response
  -> Không biết request đã được áp dụng hay chưa.
~~~

Không được đổi `OUTCOME_UNKNOWN` thành `KNOWN_REJECTED` chỉ vì phía Java nhận `CommunicationException` hoặc `SocketException`.

## 4. Mất kết nối ở những thời điểm khác nhau

Vị trí của lỗi trong vòng đời operation quyết định điều có thể kết luận:

| Thời điểm mất kết nối | Điều client biết | Rủi ro |
|---|---|---|
| Trước khi tạo được kết nối | Request LDAP chưa thể được gửi qua connection đó | Thường chưa có thay đổi từ request này; vẫn cần xác nhận không có retry/connection khác |
| Trong bind | Không thể hoàn tất phiên xác thực | Không thể giả định các thao tác sau đã chạy |
| Trước khi gửi LDAP request | Nếu xác minh chắc chắn request chưa được gửi | Operation chưa được server nhận qua connection đó |
| Sau khi gửi request, trước response | Không biết server đã áp dụng hay chưa | `OUTCOME_UNKNOWN` |
| Sau response thành công, trước khi ghi trạng thái ứng dụng | LDAP đã xác nhận nhưng ứng dụng có thể chưa lưu được tiến độ | Journal có thể chưa phản ánh thay đổi |
| Trong lúc chạy compensation | Không biết thao tác bù đã áp dụng hay chưa | `COMPENSATION_UNKNOWN` |
| Trong cleanup của commit | Các operation chính có thể đã hoàn tất nhưng dữ liệu tạm chưa được dọn | Có thể còn entry tại temporary DN hoặc trạng thái cleanup chưa xác định |

Spring LDAP nêu trực tiếp giới hạn network failure: khi transaction failure do lỗi mạng, `ContextSourceTransactionManager` không có cách nào khôi phục trạng thái directory; khả năng rollback có thể mất hoàn toàn. Vì vậy, một lỗi kết nối không tự chứng minh dữ liệu đã quay lại trước transaction.

### 4.1. Ví dụ: mất response sau khi thêm member vào group

Ứng dụng gửi:

~~~java
ModificationItem addMember = new ModificationItem(
    DirContext.ADD_ATTRIBUTE,
    new BasicAttribute("member", memberDn)
);

ldapTemplate.modifyAttributes(
    groupDn,
    new ModificationItem[] { addMember }
);
~~~

LDAP server có thể đã thêm `memberDn` vào group, nhưng connection bị đóng trước khi response về client. Java nhận exception và không biết member đã được thêm hay chưa.

Nếu gọi lại ngay cùng lệnh `ADD_ATTRIBUTE`, server có thể trả `attributeOrValueExists` nếu lần đầu đã thành công. Nếu ứng dụng hiểu lỗi đó là “chưa thêm được” rồi thử thêm bằng cách khác, dữ liệu có thể càng khó đối soát.

Cách đúng là:

1. Ghi nhận outcome là `UNKNOWN`.
2. Kết nối lại tới đúng directory endpoint/naming context.
3. Đọc entry group và thuộc tính `member`.
4. So sánh trạng thái hiện tại với trạng thái trước và trạng thái mong muốn.
5. Chọn hành động tiếp theo dựa trên kết quả đọc, không dựa trên suy đoán từ exception.

## 5. Khi thao tác bù thất bại

Một transaction có thể ghi nhận được dữ liệu ban đầu và gửi được thao tác bù, nhưng server từ chối thao tác đó. Các nguyên nhân phổ biến:

| Nguyên nhân | Ví dụ | Hậu quả |
|---|---|---|
| Network vẫn chưa phục hồi | Connection mất khi rollback bắt đầu | Không gửi được operation bù hoặc không nhận được response |
| ACL thay đổi | Service account không còn quyền sửa group | Compensation bị `insufficientAccessRights` |
| Entry đã bị xóa | DN mục tiêu không còn tồn tại | Compensation nhắm tới DN không tồn tại |
| Entry đã bị rename/move | Writer khác chuyển entry sang OU khác | DN cũ không còn trỏ tới entry dự kiến |
| Dữ liệu bị writer khác sửa | Attribute hiện tại khác before-image | Bù mù có thể ghi đè thay đổi mới |
| DN tạm bị chiếm | Temporary DN đã có entry khác | Rename/restore không thực hiện được |
| Schema hoặc constraint | Thao tác bù tạo ra trạng thái không hợp lệ | Server từ chối modification |
| Thiếu dữ liệu ban đầu | Account không đọc được một attribute cần khôi phục | Compensation không có đủ before-image |
| Cleanup thất bại | Entry được giữ ở temporary location nhưng chưa xóa được | Dữ liệu tạm còn trong directory |

**Rollback thất bại không có nghĩa mọi compensation đều thất bại.** Một số bước có thể đã được thực hiện, một số bước chưa chạy, một số bước có outcome không rõ. Hãy xem từng operation trong workflow và kiểm tra trạng thái directory thực tế.

### 5.1. Thao tác bù có thể không phải phép đảo đơn giản

Ví dụ:

- `bind` thường được bù bằng `unbind`.
- `modifyAttributes` cần các `ModificationItem` ngược, dựa trên giá trị trước đó.
- `rename` cần đổi DN về vị trí ban đầu.
- `unbind` không thể luôn được bù bằng cách bind lại từ một bản sao attributes, vì có thể không đọc được toàn bộ thuộc tính ban đầu.

Để xử lý trường hợp `unbind`, Spring LDAP dùng chiến lược đặc biệt: `UnbindOperationExecutor` có thể **rename entry tới một DN tạm** trong `performOperation()`. Khi commit, entry tạm mới được unbind; khi rollback, executor rename entry về DN ban đầu. [UnbindOperationExecutor API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/transaction/compensating/UnbindOperationExecutor.html).

Nếu rollback rename thất bại, entry có thể còn ở DN tạm. Nếu cleanup trong commit thất bại, entry tạm có thể chưa được xóa. Vì vậy, quy trình vận hành phải biết cách tìm và đối soát temporary DN theo strategy/version đang dùng.

## 6. Ví dụ workflow nhiều bước và thứ tự bù

Giả sử nhân viên Lan được chuyển từ group `developers` sang `platform`. Workflow:

1. Gỡ DN của Lan khỏi `developers`.
2. Thêm DN của Lan vào `platform`.
3. Cập nhật thuộc tính `description` của Lan.

Nếu bước 3 thất bại do một lỗi nghiệp vụ, transaction manager sẽ yêu cầu các thao tác đã ghi nhận được bù theo thứ tự ngược:

~~~mermaid
sequenceDiagram
    participant S as MembershipService
    participant L as LDAP
    S->>L: REMOVE member từ developers
    L-->>S: success
    S->>L: ADD member vào platform
    L-->>S: success
    S->>L: MODIFY description
    L-->>S: error
    Note over S: Bắt đầu compensation
    S->>L: Bù ADD: REMOVE member khỏi platform
    S->>L: Bù REMOVE: ADD member lại developers
    L-->>S: Kết quả từng thao tác bù
~~~

Sơ đồ cho thấy **ý định** của compensation. Trong thực tế, operation bị server từ chối rõ ràng có thể chưa tạo thay đổi cần bù; recorder/executor quản lý chi tiết này. Không tự viết lại stack rollback theo suy đoán của ứng dụng.

### 6.1. Ví dụ service imperative

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MembershipTransactionService {

    private final LdapTemplate ldapTemplate;

    public MembershipTransactionService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Transactional(transactionManager = "ldapTxManager")
    public void moveMember(
            Name oldGroupDn,
            Name newGroupDn,
            Name personDn) {

        String memberDn = personDn.toString();

        ModificationItem removeFromOld = new ModificationItem(
            DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("member", memberDn)
        );

        ModificationItem addToNew = new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("member", memberDn)
        );

        ldapTemplate.modifyAttributes(
            oldGroupDn,
            new ModificationItem[] { removeFromOld }
        );

        ldapTemplate.modifyAttributes(
            newGroupDn,
            new ModificationItem[] { addToNew }
        );

        // Giả lập lỗi nghiệp vụ sau hai thao tác LDAP.
        throw new IllegalStateException(
            "Simulated validation failure"
        );
    }
}
~~~

Điều kiện của ví dụ:

- `LdapTemplate` phải dùng `TransactionAwareContextSourceProxy`.
- `ldapTxManager` phải dùng đúng target `ContextSource` tương ứng.
- `oldGroupDn` và `newGroupDn` nằm trong naming context được cấu hình.
- Service account có quyền đọc dữ liệu cần ghi nhận và quyền thực hiện các thao tác bù.
- Group `developers` vẫn còn ít nhất một member khác nếu schema `groupOfNames` yêu cầu `member` không rỗng.
- `personDn` được xây dựng/kiểm tra từ dữ liệu đáng tin cậy; không lấy DN tùy ý từ client.

Exception runtime thoát khỏi method để transaction interceptor kích hoạt rollback. Không catch rồi bỏ qua exception ngay trong method transactional.

### 6.2. Cấu hình ContextSource và transaction manager

Ví dụ cấu hình tường minh:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.transaction.compensating.manager.ContextSourceTransactionManager;
import org.springframework.ldap.transaction.compensating.manager.TransactionAwareContextSourceProxy;

@Configuration
class LdapTransactionConfiguration {

    @Bean("transactionAwareContextSource")
    ContextSource transactionAwareContextSource(
            @Qualifier("targetContextSource") ContextSource target) {
        return new TransactionAwareContextSourceProxy(target);
    }

    @Bean("ldapTemplate")
    LdapTemplate ldapTemplate(
            @Qualifier("transactionAwareContextSource")
            ContextSource transactionAware) {
        return new LdapTemplate(transactionAware);
    }

    @Bean("ldapTxManager")
    ContextSourceTransactionManager ldapTxManager(
            @Qualifier("targetContextSource") ContextSource target) {
        return new ContextSourceTransactionManager(target);
    }
}
~~~

Đây là cấu hình minh họa theo API Spring LDAP được tham chiếu. Tên package và constructor có thể thay đổi giữa các major version; hãy đối chiếu dependency thực tế. Điểm không thay đổi trong mô hình là:

- Transaction manager nhận **target ContextSource**.
- `LdapTemplate` dùng **TransactionAwareContextSourceProxy** bọc target đó.
- Hai bean phải tham chiếu cùng một target context source.
- Các thao tác ghi phải đi qua proxy để được ghi nhận.

Không tạo `LdapTemplate` thứ hai dùng raw source rồi gọi nó bên trong cùng workflow; thao tác đi vòng ngoài proxy có thể không tham gia compensation.

## 7. Giữ lại lỗi nghiệp vụ và lỗi rollback

Khi business method ném exception, Spring transaction interceptor gọi rollback. Nếu rollback cũng phát sinh lỗi hệ thống, exception quan sát ở caller có thể là `TransactionSystemException` hoặc một exception transaction khác tùy phiên bản và đường thực thi.

Spring Framework cung cấp `TransactionSystemException` để biểu diễn lỗi hệ thống transaction; class này có các method `getApplicationException()` và `getOriginalException()` để truy cập lỗi ứng dụng ban đầu khi có. [TransactionSystemException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionSystemException.html).

### 7.1. Bắt lỗi ở bên ngoài transaction proxy

Đặt facade không transactional gọi một bean transactional khác:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.TransactionSystemException;

@Service
public class MembershipFacade {

    private final MembershipTransactionService transactionService;
    private final RecoveryRecorder recoveryRecorder;

    public MembershipFacade(
            MembershipTransactionService transactionService,
            RecoveryRecorder recoveryRecorder) {
        this.transactionService = transactionService;
        this.recoveryRecorder = recoveryRecorder;
    }

    public void moveMember(
            Name oldGroupDn,
            Name newGroupDn,
            Name personDn,
            String operationId) {

        try {
            transactionService.moveMember(
                oldGroupDn, newGroupDn, personDn
            );
        } catch (TransactionSystemException ex) {
            Throwable original = ex.getOriginalException();
            Throwable application = ex.getApplicationException();

            recoveryRecorder.recordRollbackFailure(
                operationId,
                original,
                application,
                ex
            );

            throw ex;
        }
    }
}
~~~

`RecoveryRecorder` là thành phần ứng dụng cần tự triển khai để ghi nhật ký phục hồi bền vững. Ví dụ trên chỉ minh họa vị trí bắt lỗi; cần bổ sung dữ liệu operation, DN/aggregate identity đã được bảo vệ, trạng thái trước/sau và phân loại lỗi.

Nếu rollback hoàn tất bình thường, caller thường nhận exception nghiệp vụ ban đầu. Nếu rollback có lỗi hệ thống, exception transaction có thể trở thành exception nổi bật. Không giả định một exception đơn lẻ luôn chứa đủ thông tin để khẳng định toàn bộ directory đã phục hồi.

### 7.2. Không nuốt lỗi hoặc gọi rollback lần thứ hai

Không làm:

~~~java
try {
    transactionService.moveMember(...);
} catch (Exception ex) {
    log.warn("LDAP failed", ex);
    // Tiếp tục trả thành công cho caller.
}
~~~

Và không gọi một rollback thủ công khác sau khi transaction proxy đã hoàn tất rollback. Nếu cần phục hồi, đó là **một workflow recovery mới** sau khi đã đọc trạng thái directory, không phải gọi lại transaction rollback đã kết thúc.

Hãy giữ cả:

- Lỗi gốc khiến workflow phải rollback.
- Lỗi phát sinh khi thực hiện compensation.
- Operation nào đã được xác nhận thành công.
- Operation nào có response lỗi rõ ràng.
- Operation nào mất response và có outcome không xác định.

## 8. Phân biệt rollback không hoàn tất với rollback chưa được xác minh

Có ba mức kết luận hữu ích:

| Mức kết luận | Điều đã biết | Có thể đóng sự cố? |
|---|---|---|
| `ROLLBACK_REQUESTED` | Transaction manager đã bắt đầu xử lý rollback | Chưa |
| `COMPENSATION_EXECUTED` | Các thao tác bù đã chạy và trả thành công theo đường client | Chưa chắc đã xác minh trạng thái tổng thể |
| `STATE_VERIFIED` | Đọc lại directory cho thấy trạng thái khớp before-image/mục tiêu phục hồi | Có thể đóng nếu không còn step pending |

Một rollback method kết thúc bình thường là tín hiệu tốt, nhưng với nghiệp vụ quan trọng, ứng dụng vẫn nên xác minh những invariant chính sau sự cố, đặc biệt nếu có replica, cache hoặc nhiều writer.

Nếu rollback ném exception, không được ghi `ROLLBACK_COMPLETE`. Ghi `COMPENSATION_FAILED` hoặc `COMPENSATION_UNKNOWN` tùy loại lỗi và tạo recovery item.

## 9. Mất kết nối khi rollback đang diễn ra

Trường hợp này khác với mất kết nối ở operation nghiệp vụ:

1. Operation A đã được server xác nhận.
2. Operation B đã được server xác nhận.
3. Operation C lỗi, transaction yêu cầu rollback.
4. Compensation cho B gửi tới LDAP.
5. Server có thể đã áp dụng bù cho B nhưng response bị mất.
6. Compensation cho A có thể chưa được gửi hoặc không thể gửi vì connection không còn dùng được.

Trạng thái cuối cùng có thể là:

~~~text
Operation A: forward applied
Operation B: forward applied
Operation C: known rejected
Compensation B: outcome unknown
Compensation A: not confirmed
Overall state: PARTIAL_OR_UNKNOWN
~~~

Không thể dựa vào stack trace để tự suy ra entry đang ở đâu. Phải kết nối lại, đọc dữ liệu và đối soát từng DN/attribute tham gia workflow.

### 9.1. Khi server trả response lỗi rõ ràng

Nếu compensation `REMOVE_ATTRIBUTE member=...` nhận `noSuchAttribute`, có thể entry đã không còn giá trị đó trước khi bù, hoặc một writer khác đã xóa. Không tự động coi mọi `noSuchAttribute` là thành công; cần xác minh trạng thái mong muốn và ý nghĩa nghiệp vụ.

Nếu compensation nhận `insufficientAccessRights`, đó là lỗi quyền; không retry liên tục bằng cùng principal. Nếu nhận `noSuchObject`, kiểm tra DN, parent, rename và endpoint trước khi quyết định phục hồi.

## 10. Tại sao concurrent writer có thể làm compensation nguy hiểm?

`ContextSourceTransactionManager` không cung cấp isolation. Một client khác có thể thay đổi entry trong lúc transaction A đang chạy.

Ví dụ:

~~~text
Ban đầu: description = "Developer"

Transaction A:
  Đổi description thành "Platform Engineer"

Client B:
  Đổi description thành "Engineering Lead"

Transaction A:
  Bước sau thất bại
  Compensation ghi lại "Developer"
~~~

Nếu compensation ghi đè bằng before-image cũ, thay đổi hợp lệ của client B có thể bị mất.

Điều này không phải lỗi riêng của LDAP client. Nó là hệ quả của việc bù trừ bằng thao tác ghi mới trong một directory không có isolation chung cho chuỗi operation.

### 10.1. Giảm nguy cơ ghi đè

- Chỉ bù đúng attribute/value mà workflow sở hữu.
- Không thay toàn bộ entry từ một snapshot cũ nếu chỉ cần sửa một thuộc tính.
- Dùng giá trị bất biến hoặc version attribute nếu mô hình dữ liệu hỗ trợ.
- Dùng LDAP Assertion Control (RFC 4528) khi server hỗ trợ để yêu cầu trạng thái hiện tại vẫn khớp điều kiện trước khi sửa.
- Khi phát hiện trạng thái khác before-image và after-image dự kiến, chuyển sang reconciliation/manual review thay vì ghi đè.
- Phân vùng ownership: tránh hai workflow cùng quản lý một attribute/entry nếu không có conflict policy.

Assertion Control không tự tạo transaction nhiều entry; nó chỉ giúp một operation có điều kiện được thực hiện nếu assertion phù hợp.

## 11. Thiết kế compensation có thể retry an toàn

Không phải mọi thao tác bù đều idempotent. Ví dụ:

- `ADD_ATTRIBUTE member=X` lần thứ hai có thể báo giá trị đã tồn tại.
- `REMOVE_ATTRIBUTE member=X` có thể báo không có giá trị để xóa.
- `rename oldDn -> newDn` có thể thất bại nếu entry đã được chuyển hoặc DN đích đang bị chiếm.
- `unbind` có thể thất bại nếu entry đã bị xóa bởi writer khác.

Trước khi retry, phải xác định **trạng thái hiện tại** và **trạng thái đích**.

### 11.1. Mẫu reconciliation cho một giá trị member

Mục tiêu nghiệp vụ là member `personDn` không còn nằm trong group `oldGroupDn`.

Quy trình:

1. Đọc group từ LDAP bằng một kết nối mới.
2. Kiểm tra attribute `member`.
3. Nếu giá trị đã vắng mặt, đánh dấu compensation đã đạt mục tiêu.
4. Nếu giá trị vẫn còn, kiểm tra version/ownership và quyền ghi.
5. Gửi thao tác xóa có điều kiện nếu server hỗ trợ; nếu không, áp dụng policy conflict đã định.
6. Đọc lại để xác minh.
7. Ghi kết quả cùng operation ID.

Pseudo-code:

~~~java
public RecoveryResult ensureMemberAbsent(
        Name groupDn,
        String memberDn) {

    GroupSnapshot current = directoryReader.readGroup(groupDn);

    if (!current.members().contains(memberDn)) {
        return RecoveryResult.ALREADY_RESTORED;
    }

    if (!recoveryPolicy.mayModify(current, memberDn)) {
        return RecoveryResult.CONFLICT_REQUIRES_REVIEW;
    }

    directoryWriter.removeMember(groupDn, memberDn);

    GroupSnapshot verified = directoryReader.readGroup(groupDn);

    return verified.members().contains(memberDn)
        ? RecoveryResult.STILL_PRESENT
        : RecoveryResult.RESTORED;
}
~~~

`GroupSnapshot`, `directoryReader`, `directoryWriter`, `recoveryPolicy` và `RecoveryResult` là abstraction của ứng dụng, không phải class có sẵn trong Spring LDAP. Mục tiêu của ví dụ là mô tả cách **đọc trước, kiểm tra, sửa, đọc lại** thay vì retry blindly.

## 12. Nhật ký phục hồi bền vững

Transaction manager lưu thông tin compensation cho transaction đang thực thi, nhưng ứng dụng cần một cơ chế riêng nếu muốn phục hồi sau khi JVM dừng, process crash hoặc network outage kéo dài.

Một recovery journal có thể lưu:

| Trường | Ý nghĩa |
|---|---|
| `operation_id` | ID duy nhất cho workflow; dùng làm idempotency key |
| `aggregate_key` | Khóa logic của người/nhóm, không nhất thiết là raw DN |
| `target_dn_ref` | DN hoặc tham chiếu được bảo vệ/che trong log |
| `operation_sequence` | Thứ tự operation trong workflow |
| `operation_type` | `MODIFY`, `BIND`, `UNBIND`, `RENAME` |
| `before_state` | Trạng thái trước thao tác cần để phục hồi |
| `desired_state` | Trạng thái nghiệp vụ mong muốn |
| `forward_status` | `PLANNED`, `APPLIED`, `REJECTED`, `UNKNOWN` |
| `compensation_status` | `NOT_REQUIRED`, `PENDING`, `APPLIED`, `FAILED`, `UNKNOWN` |
| `attempt_count` | Số lần recovery đã thử |
| `last_error` | Loại lỗi và thông tin đã được làm sạch |
| `updated_at` | Thời điểm cập nhật trạng thái |

Không ghi raw password, bind credentials hoặc toàn bộ dữ liệu cá nhân vào journal. `before_state` có thể chứa thông tin nhạy cảm; phải giới hạn quyền đọc, mã hóa và đặt retention phù hợp.

### 12.1. Ví dụ state machine

~~~mermaid
stateDiagram-v2
    [*] --> PLANNED
    PLANNED --> FORWARD_SENT
    FORWARD_SENT --> APPLIED: response success
    FORWARD_SENT --> REJECTED: response error
    FORWARD_SENT --> UNKNOWN: response lost
    APPLIED --> COMPENSATION_PENDING: rollback requested
    UNKNOWN --> RECONCILIATION_PENDING
    COMPENSATION_PENDING --> COMPENSATED: compensation success
    COMPENSATION_PENDING --> COMPENSATION_FAILED: explicit failure
    COMPENSATION_PENDING --> COMPENSATION_UNKNOWN: response lost
    COMPENSATION_FAILED --> RECONCILIATION_PENDING
    COMPENSATION_UNKNOWN --> RECONCILIATION_PENDING
    RECONCILIATION_PENDING --> STATE_VERIFIED: state matches target
    RECONCILIATION_PENDING --> MANUAL_REVIEW: conflict or unsafe
    RECONCILIATION_PENDING --> COMPENSATION_PENDING: safe retry
    COMPENSATED --> STATE_VERIFIED
    STATE_VERIFIED --> [*]
~~~

Đây là state machine nghiệp vụ minh họa. Spring LDAP không tự tạo các trạng thái này; ứng dụng phải lưu và quản lý.

### 12.2. Outbox không biến LDAP thành transaction ACID

Có thể lưu ý định thay đổi vào database outbox rồi để worker thực hiện LDAP workflow. Cách này giúp không mất **ý định công việc** khi process crash và cho phép retry/reconcile có kiểm soát.

Nhưng database outbox và LDAP vẫn là hai hệ thống riêng. Không có transaction chung bao trùm cả database commit và nhiều LDAP operations chỉ vì dùng outbox. Worker vẫn phải xử lý `UNKNOWN`, compensation failure, idempotency và đối soát trạng thái directory.

## 13. Không retry mù sau lỗi network

Một policy retry cần phân biệt operation đọc, ghi và compensation:

| Tình huống | Chính sách |
|---|---|
| Search lỗi connect trước khi gửi request | Có thể retry có giới hạn nếu deadline còn đủ |
| Modify nhận LDAP response lỗi rõ ràng | Sửa nguyên nhân; không retry cùng request một cách máy móc |
| Modify mất response | Đọc lại state trước khi quyết định retry |
| Compensation nhận lỗi ACL/schema | Không retry liên tục; sửa quyền/schema hoặc chuyển review |
| Compensation mất response | Đọc lại trạng thái rồi mới quyết định |
| LDAP server báo busy/unavailable | Backoff có jitter, giới hạn attempt và tổng thời gian |
| DN đích bị chiếm hoặc entry đã đổi vị trí | Reconcile theo định danh ổn định; không ghi đè mù |

Một retry vô hạn có thể tạo retry storm và làm LDAP server quá tải. Một retry ghi không idempotent có thể tạo dữ liệu trùng hoặc ghi đè thay đổi của client khác.

### 13.1. Quy tắc thực hành

- Có deadline tổng cho workflow và từng attempt.
- Dùng exponential backoff có jitter.
- Giới hạn số lần thử.
- Phân loại lỗi có thể phục hồi và lỗi không thể phục hồi.
- Không retry sau khi caller đã hủy nếu operation ghi có outcome chưa rõ.
- Ghi lại attempt và response/result code.
- Khi vượt số lần retry, chuyển `MANUAL_REVIEW` hoặc queue phục hồi thay vì lặp mãi.

## 14. Quy trình phục hồi khi directory mất kết nối

Khi LDAP trở lại sau sự cố:

1. **Dừng ghi mới vào aggregate bị ảnh hưởng** nếu chưa biết trạng thái hiện tại.
2. Tìm recovery records ở `UNKNOWN`, `COMPENSATION_FAILED` hoặc `COMPENSATION_UNKNOWN`.
3. Kết nối đúng LDAP endpoint/naming context bằng service account được cấp quyền đọc và phục hồi.
4. Đọc các DN và attributes liên quan bằng connection mới.
5. So sánh trạng thái thực tế với `before_state` và `desired_state`.
6. Phân loại: đã trở về trạng thái cũ, đã ở trạng thái đích, trạng thái trung gian hoặc có conflict.
7. Chỉ thực hiện compensation/retry nếu trạng thái hiện tại cho phép và không ghi đè thay đổi ngoài workflow.
8. Đọc lại sau recovery và ghi `STATE_VERIFIED`.
9. Nếu không thể xác định an toàn, giữ trạng thái pending và chuyển cho người vận hành.

### 14.1. Đọc từ đúng directory node

Nếu directory có nhiều replica, một lần đọc từ node chưa đồng bộ có thể cho kết quả cũ. Reconciliation phải biết topology và consistency requirement:

- Đọc từ writable/authoritative node nếu có quy định.
- Không dùng một replica stale làm bằng chứng chắc chắn thao tác chưa được áp dụng.
- Ghi nhận endpoint/node đã đọc.
- Chờ replication theo policy nếu workflow phụ thuộc replication.
- Không retry trên nhiều node một cách mù quáng.

## 15. Trường hợp unbind/rebind và DN tạm

Spring LDAP có thể di chuyển entry tới một DN tạm khi thực hiện `unbind` hoặc `rebind`, bởi việc đọc đầy đủ tất cả attributes để dựng lại entry không phải lúc nào cũng khả thi. Nếu rollback, executor rename entry từ temporary DN về DN gốc; nếu commit, executor xóa entry khỏi vị trí tạm.

Điều này dẫn tới một số câu hỏi khi có lỗi:

- Entry có đang ở DN gốc hay DN tạm?
- DN tạm được tạo theo strategy nào trong phiên bản đang dùng?
- Parent của DN tạm còn tồn tại không?
- Account có quyền rename giữa hai vị trí không?
- Có một entry khác chiếm DN gốc trước khi rollback không?
- Cleanup sau commit đã xóa entry tạm chưa?

Không tự xây một quy tắc tìm temporary DN từ tên mặc định nếu chưa xác minh `TempEntryRenamingStrategy` và cấu hình thực tế. Với lỗi cleanup, cần dùng strategy/configuration của ứng dụng để tìm và đối soát đúng entry.

## 16. Mã LDAP hữu ích khi chẩn đoán compensation

| LDAP result code | Tên | Ý nghĩa thường gặp trong recovery |
|---:|---|---|
| 16 | `noSuchAttribute` | Attribute/value cần xóa không còn tồn tại |
| 19 | `constraintViolation` | Compensation vi phạm constraint |
| 20 | `attributeOrValueExists` | Value đã có, có thể do operation trước đã thành công |
| 21 | `invalidAttributeSyntax` | Giá trị bù không đúng syntax |
| 32 | `noSuchObject` | DN hoặc parent không tìm được |
| 34 | `invalidDNSyntax` | DN bù không hợp lệ |
| 49 | `invalidCredentials` | Bind account không xác thực được |
| 50 | `insufficientAccessRights` | Không đủ quyền thực hiện thao tác bù |
| 51 | `busy` | Server tạm thời bận |
| 52 | `unavailable` | Directory không sẵn sàng |
| 53 | `unwillingToPerform` | Server từ chối thao tác theo policy/constraint |
| 68 | `entryAlreadyExists` | DN đích đã tồn tại |

Mã lỗi chỉ cho biết kết quả của operation nhận response. Nếu response bị mất, client có thể không biết result code. Khi đó cần dùng trạng thái `UNKNOWN` và đọc lại.

## 17. Kiểm soát quyền để compensation có thể chạy

Một lỗi thiết kế phổ biến là service account có đủ quyền cho thao tác nghiệp vụ nhưng **không đủ quyền cho thao tác ngược**.

Ví dụ:

- Có quyền thêm entry nhưng không có quyền xóa entry.
- Có quyền xóa member khỏi group nhưng không được thêm lại.
- Có quyền rename entry sang OU tạm nhưng không được rename về OU cũ.
- Có quyền sửa `mail` nhưng không có quyền đọc giá trị cũ cần để bù.
- Có quyền đọc entry nhưng không có quyền đọc một số attributes nhạy cảm.

Vì vậy, khi thiết kế ACL cho một workflow có compensation, cần kiểm tra **cả forward permission lẫn compensation permission** trên đúng DN/attribute.

Không cấp quyền admin toàn directory chỉ để rollback dễ hơn. Hãy giới hạn quyền theo OU và operation cần thiết, rồi kiểm thử với đúng service account.

## 18. Kiểm thử failure injection

Unit test với mock có thể xác minh ứng dụng phân loại exception và ghi recovery record. Nhưng để kiểm chứng giới hạn network và LDAP protocol, cần integration test với directory riêng hoặc proxy test có khả năng tạo lỗi mạng.

### 18.1. Ma trận kiểm thử

| Kịch bản | Cách tạo lỗi trong môi trường test | Kết quả cần kiểm chứng |
|---|---|---|
| Business exception sau hai Modify thành công | Ném runtime exception sau bước thứ hai | Spring gọi compensation theo thứ tự ngược |
| Forward Modify bị LDAP từ chối | Dùng account thiếu quyền hoặc schema không hợp lệ | Request có response lỗi; kiểm tra trạng thái theo result code |
| Response forward bị mất | Proxy cắt kết nối sau khi server nhận request | Client ghi `OUTCOME_UNKNOWN`; đọc lại trước retry |
| Rollback connection bị mất | Ngắt network sau khi business exception kích hoạt rollback | Không báo `ROLLBACK_COMPLETE`; tạo recovery record |
| Compensation bị ACL từ chối | Thu hồi quyền test cho operation ngược | Ghi `COMPENSATION_FAILED` và nguyên nhân |
| Compensation response bị mất | Cắt kết nối sau khi server nhận operation bù | Ghi `COMPENSATION_UNKNOWN`; reconcile |
| Entry bị rename bởi writer khác | Client thứ hai đổi DN giữa forward và rollback | Không ghi đè; phát hiện conflict |
| Temporary DN cleanup lỗi | Chặn rename/unbind tại bước cleanup | Kiểm tra entry tạm còn tồn tại và được đối soát |
| Replica lag | Đọc từ node chậm đồng bộ | Không kết luận từ replica stale |
| Recovery chạy lại | Gửi cùng recovery job nhiều lần | Không tạo duplicate hoặc phá trạng thái đã đúng |

### 18.2. Test rollback thành công sau lỗi nghiệp vụ

Một integration test cơ bản có thể kiểm tra trạng thái cuối của group:

~~~java
@Test
void restoresMembershipWhenLaterStepFails() {
    assertThatThrownBy(() ->
        membershipService.moveMemberAndFail(
            oldGroupDn, newGroupDn, personDn
        )
    ).isInstanceOf(IllegalStateException.class);

    Set<String> oldMembers = directoryReader.readMembers(oldGroupDn);
    Set<String> newMembers = directoryReader.readMembers(newGroupDn);

    assertThat(oldMembers).contains(personDn.toString());
    assertThat(newMembers).doesNotContain(personDn.toString());
}
~~~

`membershipService.moveMemberAndFail(...)` là method test-only hoặc test fixture được thiết kế để ném lỗi sau các thao tác forward. `directoryReader` nên đọc bằng một context mới, không dựa trên transaction-bound `DirContext` vừa được sử dụng trong workflow.

Test này chứng minh compensation đã đưa các invariant được kiểm tra về trạng thái mong muốn trên directory test. Nó không chứng minh mọi network failure đều có thể rollback.

### 18.3. Test rollback thất bại

Một test riêng cần chủ động làm cho thao tác bù bị từ chối, ví dụ thay đổi ACL test hoặc dùng một proxy LDAP test có thể từ chối operation ngược.

Điều cần assert:

- Caller nhận exception transaction/system phù hợp với version.
- Recovery journal ghi nhận operation ID và lỗi gốc.
- Recovery status không bị ghi thành `STATE_VERIFIED`.
- Directory được đọc lại để xác định step nào đã được áp dụng.
- Không tự retry khi trạng thái chưa được xác định.
- Sau khi sửa ACL hoặc khôi phục kết nối, recovery workflow có thể chạy lại an toàn.

Không dựa vào một mock ném exception để khẳng định LDAP server đã áp dụng hoặc chưa áp dụng request.

### 18.4. Test mất response

Mô phỏng network fault cần đặt ở vị trí **sau khi server đã nhận request nhưng trước khi client nhận response**. Đây là kịch bản quan trọng nhất để kiểm tra `OUTCOME_UNKNOWN`.

Một proxy TCP/TLS hoặc LDAP test harness có thể giúp tạo tình huống này. Sau khi fault xảy ra:

1. Reconnect.
2. Lookup entry/group.
3. Kiểm tra giá trị đã thay đổi hay chưa.
4. Chỉ retry khi trạng thái hiện tại và policy cho phép.
5. Xác nhận recovery record chuyển sang trạng thái đúng.

Một test chỉ ngắt socket trước khi gửi request không tái hiện được ambiguity của response loss.

## 19. Ghi log, metrics và cảnh báo

Một log recovery nên mô tả operation mà không làm lộ dữ liệu directory:

~~~text
event=ldap.compensation.failed
operationId=7d81a4
workflow=move-membership
step=remove-from-old-group
targetRef=group:developers
forwardStatus=APPLIED
compensationStatus=FAILED
ldapResult=insufficientAccessRights
recoveryRequired=true
~~~

Các metrics nên có:

- Số transaction rollback được yêu cầu.
- Số compensation hoàn tất.
- Số compensation lỗi rõ ràng.
- Số operation có outcome không xác định.
- Số recovery job đang chờ.
- Số lần retry và số lần chuyển manual review.
- Thời gian từ lúc lỗi đến lúc state được xác minh.
- Số entry còn ở temporary DN nếu ứng dụng có workflow sử dụng DN tạm.

Không dùng raw DN, UID, email hoặc filter có PII làm metric label. Dùng alias hoặc hash/ID tham chiếu có kiểm soát; thông tin chi tiết đặt trong log bảo vệ quyền truy cập.

### 19.1. Khi nào cần cảnh báo ngay?

- `OUTCOME_UNKNOWN` trên thao tác ghi quan trọng.
- `COMPENSATION_FAILED` do ACL/schema.
- Temporary DN còn tồn tại quá thời hạn.
- Recovery queue tăng liên tục.
- Một operation ID có nhiều lần retry nhưng không hội tụ.
- Nhiều transaction cùng sửa một aggregate/entry.
- LDAP node liên tục mất kết nối trong giai đoạn rollback.

Đừng chỉ cảnh báo theo tổng số exception. Một lỗi read-only có thể ít nghiêm trọng hơn một compensation failure khiến trạng thái membership hoặc account không nhất quán.

## 20. API và thông báo cho caller khi rollback chưa chắc chắn

Nếu một request cập nhật hồ sơ gặp lỗi và compensation cũng thất bại, không nên trả thông điệp “đã rollback, dữ liệu không thay đổi”.

Có thể trả response có operation ID để người gọi tra cứu:

~~~json
{
  "status": "RECOVERY_REQUIRED",
  "operationId": "7d81a4",
  "message": "Directory update could not be confirmed. Recovery is in progress."
}
~~~

Đây là response contract minh họa. API thực tế có thể dùng `500` hoặc `503` tùy nguyên nhân và khả năng retry, nhưng phải nói rõ **kết quả cập nhật chưa được xác minh**.

Không trả DN nội bộ, LDAP server host, bind DN, raw diagnostic message hoặc dữ liệu before-image cho caller không được phép xem.

## 21. Khi nào cần dùng saga/reconciliation thay vì chỉ dựa vào transaction manager?

Spring LDAP compensation hữu ích khi workflow nhỏ, các operation có thể đảo ngược và dữ liệu cần khôi phục có thể ghi nhận đầy đủ. Nhưng nếu nghiệp vụ có nhiều hệ thống, thời gian dài, nhiều writer hoặc cần phục hồi sau process crash, hãy thiết kế một saga/recovery workflow cấp ứng dụng:

- Mỗi bước có operation ID và trạng thái bền vững.
- Các thao tác được thiết kế idempotent hoặc có điều kiện.
- Có thể đọc trạng thái hiện tại và đối chiếu với before/desired state.
- Có bounded retry, backoff và dead-letter/manual review.
- Có công cụ cho operator xem và xử lý recovery item.
- Có audit trail về ai/worker nào thực hiện forward và compensation.

Nếu yêu cầu nghiệp vụ cần tính atomic mạnh giữa nhiều thay đổi LDAP, hãy đánh giá lại cách mô hình hóa: gom thay đổi vào một LDAP Modify request nếu cùng một entry và phù hợp semantics; dùng một thuộc tính trạng thái/flag để biểu diễn workflow; hoặc chọn một hệ thống lưu trữ có transaction phù hợp. Không dùng `@Transactional` như lời hứa atomicity cho nhiều LDAP entries.

## 22. Checklist xử lý rollback failure

| Câu hỏi | Cần xác minh |
|---|---|
| Có đúng `ContextSource` và proxy? | Transaction manager dùng target; `LdapTemplate` dùng transaction-aware proxy |
| Operation nào đã được server xác nhận? | Tách `APPLIED`, `REJECTED`, `UNKNOWN` |
| Có operation nào mất response? | Không retry trước khi đọc lại trạng thái |
| Compensation nào đã chạy? | Ghi theo sequence và operation ID |
| Compensation có bị ACL/schema từ chối? | Xác minh quyền và result code |
| Entry có bị đổi DN? | Tra cứu theo định danh ổn định và kiểm tra temporary DN |
| Có writer khác thay đổi cùng entry? | So sánh before-image với state hiện tại |
| Before-image có đầy đủ? | Có quyền đọc và lưu các giá trị cần khôi phục |
| Có lỗi cleanup? | Kiểm tra temporary entry và bước commit cleanup |
| Exception gốc còn được giữ? | Kiểm tra `TransactionSystemException` và cause/application exception |
| Có recovery journal? | Trạng thái được lưu bền vững, không chỉ trong memory |
| Retry có idempotent? | Kiểm tra state trước khi gửi lại |
| Đã đọc lại directory? | Xác minh trên node phù hợp |
| Có lộ PII/secret trong log? | Không để DN, credential và attribute nhạy cảm lộ ra |
| Đã kiểm thử mất response? | Fault injection sau khi server nhận request |
| Recovery đã hội tụ? | Chỉ đóng khi state được xác minh |

## 23. Bài tập thực hành

### Bài 1 — Phân loại outcome

Một `modifyAttributes` gửi request tới LDAP nhưng client nhận `CommunicationException`. Phân loại kết quả là `KNOWN_REJECTED`, `KNOWN_APPLIED` hay `OUTCOME_UNKNOWN`? Nêu các bước cần thực hiện trước khi retry.

### Bài 2 — Compensation theo thứ tự ngược

Một workflow thực hiện `bind` entry mới, `modifyAttributes` của group và `rename` entry. Bước cuối ném exception. Liệt kê thứ tự compensation mà operation manager mặc định sử dụng và mô tả một nguyên nhân khiến mỗi bước bù có thể thất bại.

### Bài 3 — Mất response trong rollback

Operation B đã được áp dụng. Khi rollback, compensation cho B được gửi nhưng response bị mất. Tại sao không thể kết luận B đã được khôi phục? Hãy thiết kế một truy vấn đọc để xác minh trạng thái.

### Bài 4 — Concurrent writer

Transaction A thay `description`; client B thay `description` trước khi A rollback. Tại sao compensation của A có thể ghi đè dữ liệu B? Đề xuất dùng attribute ownership hoặc Assertion Control để giảm nguy cơ.

### Bài 5 — Temporary DN

Một `unbind` được chuyển tới DN tạm. Rollback mất kết nối trước khi rename trở lại. Hãy nêu cách tìm entry tạm theo strategy cấu hình, xác minh attributes và quyết định khôi phục an toàn.

### Bài 6 — Exception diagnostics

Một caller nhận `TransactionSystemException`. Hãy xác định cách lấy lỗi ứng dụng ban đầu, lỗi hệ thống rollback và cách ghi cả hai vào recovery journal mà không làm mất root cause.

### Bài 7 — Recovery journal

Thiết kế bảng lưu operation ID, DN reference, before-state, desired-state, forward status, compensation status, attempt count và last error. Nêu cách bảo vệ dữ liệu nhạy cảm trong before-state.

### Bài 8 — Failure injection

Viết kế hoạch integration test cho ba trường hợp: LDAP từ chối compensation, response của forward Modify bị mất, response của compensation bị mất. Với mỗi trường hợp, xác định trạng thái journal và bước reconciliation.

### Bài 9 — Idempotent compensation

Một compensation xóa member khỏi group có thể được chạy nhiều lần. Thiết kế workflow kiểm tra membership trước khi gửi Modify và đọc lại sau khi gửi. Xử lý thế nào khi entry đã được client khác sửa?

### Bài 10 — Chọn kiến trúc phục hồi

Một workflow cập nhật LDAP và database, có thể kéo dài vài phút và cần tiếp tục sau khi JVM restart. Vì sao một `@Transactional` bao quanh cả hai resource không đảm bảo XA? Hãy đề xuất saga/outbox với operation ID và reconciliation.

## 24. Kết luận và tài liệu tham khảo

`ContextSourceTransactionManager` cung cấp **compensating transaction phía client**: Spring LDAP ghi nhận trạng thái trước các operation thay đổi và cố gắng khôi phục bằng các operation ngược. Cơ chế này hữu ích nhưng không phải ACID transaction. Network failure có thể làm mất hoàn toàn khả năng rollback; mất response sau khi gửi Modify khiến client không biết request đã được áp dụng hay chưa; concurrent writer có thể khiến compensation ghi đè dữ liệu mới.

Khi rollback hoặc một thao tác bù thất bại, hãy giữ riêng lỗi nghiệp vụ và lỗi rollback, ghi nhận trạng thái `UNKNOWN` khi không thể kết luận, reconnect và đọc directory để đối soát. Chỉ retry khi trạng thái hiện tại đã được kiểm tra và thao tác bù an toàn. Với workflow quan trọng hoặc kéo dài, cần recovery journal bền vững, idempotency, reconciliation, metrics và quy trình manual review.

Tài liệu chính thức để đối chiếu:

- [Spring LDAP — ContextSourceTransactionManager API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/transaction/compensating/manager/ContextSourceTransactionManager.html)
- [Spring LDAP — DefaultCompensatingTransactionOperationManager API](https://docs.spring.io/spring-ldap/reference/4.0/api/java/org/springframework/transaction/compensating/support/DefaultCompensatingTransactionOperationManager.html)
- [Spring LDAP — UnbindOperationExecutor API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/transaction/compensating/UnbindOperationExecutor.html)
- [Spring LDAP — ModifyAttributesOperationExecutor API](https://docs.spring.io/spring-ldap/reference/4.1-SNAPSHOT/api/java/org/springframework/ldap/transaction/compensating/ModifyAttributesOperationExecutor.html)
- [Spring Framework — TransactionSystemException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionSystemException.html)
- [Spring Framework — PlatformTransactionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html)
- [RFC 4511 — LDAP Modify operation and response semantics](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528)
