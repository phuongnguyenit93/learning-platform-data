# Optimistic/pessimistic locking, timeout và chuyển đổi lỗi

Khi nhiều request cùng đọc rồi cập nhật một hàng MySQL, ứng dụng phải kiểm soát cách các transaction cạnh tranh. **Optimistic locking** phát hiện một transaction đã làm dữ liệu thay đổi kể từ lúc transaction khác đọc; **pessimistic locking** khóa dữ liệu trong lúc transaction đang xử lý để hạn chế transaction khác sửa cùng tài nguyên. Timeout giới hạn thời gian chờ khóa hoặc thực thi, còn exception translation chuyển lỗi từ JDBC/JPA thành loại lỗi nhất quán ở tầng Spring.

Không có một chiến lược khóa phù hợp cho mọi thao tác. Optimistic locking thường phù hợp khi xung đột hiếm và transaction ngắn. Pessimistic locking hữu ích khi xung đột thường xuyên hoặc nghiệp vụ cần giữ quyền cập nhật trong một khoảng xử lý ngắn. Dù chọn cách nào, ứng dụng vẫn phải có transaction boundary rõ ràng, timeout hữu hạn và cách xử lý lỗi có thể phục hồi.

Bài học thuộc chương **Spring Boot và JPA** của module DATABASE_MYSQL. Module bao quát thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, tối ưu truy vấn, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Ví dụ dùng Spring Boot 3, Spring Data JPA, Jakarta Persistence và MySQL InnoDB; với Spring Boot 2, package persistence thường dùng tiền tố javax thay cho jakarta.

Sau bài học, bạn có thể:

- Giải thích lost update và vai trò của version column.
- Cấu hình optimistic locking bằng @Version.
- Dùng LockModeType để yêu cầu pessimistic lock.
- Đặt timeout cho transaction, query và lock.
- Phân biệt deadlock, lock wait timeout và optimistic conflict.
- Hiểu exception translation từ JPA/Hibernate sang Spring DataAccessException.
- Thiết kế retry ngoài transaction đã thất bại.
- Kiểm tra lock wait và kiểm thử cạnh tranh bằng nhiều transaction.

## 1. Vấn đề đồng thời: lost update

Giả sử tài khoản A có số dư 1.000. Hai request cùng đọc số dư, mỗi request muốn trừ 100:

1. Transaction T1 đọc 1.000.
2. Transaction T2 cũng đọc 1.000.
3. T1 tính 900 và ghi 900.
4. T2 tính 900 và ghi 900.
5. Cả hai request đều nghĩ đã trừ tiền, nhưng số dư cuối là 900 thay vì 800.

Đây là lost update: một cập nhật ghi đè kết quả của cập nhật khác vì cả hai dựa trên cùng một giá trị cũ.

~~~text
T1                         T2
|                          |
|---- đọc balance=1000 ----|
|                          |---- đọc balance=1000
|---- tính 900 ------------|
|                          |---- tính 900
|---- ghi balance=900 -----|
|                          |---- ghi balance=900
|                          |
Kết quả: 900, trong khi hai lần trừ 100 phải cho 800.
~~~

InnoDB cung cấp các cơ chế khóa và isolation level, nhưng ứng dụng cần chọn cách đọc/cập nhật phù hợp. Chỉ dùng @Transactional không tự động ngăn mọi lost update. Transaction có thể bao gồm nhiều câu lệnh, nhưng nếu hai transaction đều đọc trước rồi ghi giá trị tuyệt đối mà không kiểm tra version hoặc giữ khóa, kết quả vẫn có thể sai.

## 2. Hai chiến lược khóa

| Tiêu chí | Optimistic locking | Pessimistic locking |
|---|---|---|
| Cách hoạt động | Phát hiện xung đột khi ghi bằng version hoặc điều kiện tương đương | Giữ khóa trong transaction để ngăn cập nhật cạnh tranh |
| Phù hợp | Xung đột hiếm, nhiều lượt đọc, transaction ngắn | Xung đột thường xuyên hoặc cần tuần tự hóa thao tác |
| Chi phí khi không có conflict | Thấp, không cần giữ khóa dài từ lúc đọc | Có chi phí lấy/giữ khóa |
| Khi có conflict | Một transaction thất bại và có thể phải chạy lại | Transaction khác phải chờ hoặc timeout |
| Rủi ro vận hành | Retry storm nếu xung đột liên tục | Deadlock, lock wait, giữ khóa quá lâu |
| Phạm vi bảo vệ | Hàng có version và câu lệnh cập nhật đúng version | Hàng/range bị database khóa theo execution plan và isolation level |

Cả hai cơ chế đều cần transaction. Optimistic locking không có nghĩa là không dùng database lock: câu UPDATE vẫn lấy khóa InnoDB khi thực thi. Khác biệt là ứng dụng không giữ khóa độc quyền từ thời điểm đọc; nó kiểm tra version tại thời điểm ghi.

Pessimistic locking cũng không thay thế constraint. Unique key, foreign key, CHECK constraint và điều kiện UPDATE vẫn cần thiết để bảo vệ invariant dữ liệu.

## 3. Optimistic locking với @Version

Jakarta Persistence hỗ trợ optimistic locking bằng version attribute. Entity khai báo một thuộc tính được đánh dấu @Version:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
@Table(name = "account", schema = "banking")
public class Account {
    @Id
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal balance;

    @Version
    @Column(nullable = false)
    private Long version;

    protected Account() {
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getBalance() {
        return balance;
    }

    public Long getVersion() {
        return version;
    }

    public void debit(BigDecimal amount) {
        if (balance.compareTo(amount) < 0) {
            throw new IllegalStateException("Insufficient funds");
        }
        balance = balance.subtract(amount);
    }
}
~~~

Với entity này, Hibernate dùng version để kiểm tra cập nhật. SQL có dạng khái quát:

~~~sql
UPDATE banking.account
SET balance = ?, version = ?
WHERE id = ?
  AND version = ?;
~~~

Giả sử entity được đọc với version = 7. Khi cập nhật thành công, provider tăng version lên 8 và chỉ cập nhật nếu hàng vẫn có version = 7. Nếu transaction khác đã cập nhật trước và version hiện tại là 8, câu UPDATE có thể tác động 0 hàng. Provider nhận ra xung đột và ném lỗi optimistic locking.

Không tự gán version trong code nghiệp vụ. Provider quản lý version khi insert/update entity. Dùng kiểu version được JPA hỗ trợ như int, Integer, long, Long, short, Short, java.sql.Timestamp hoặc kiểu temporal phù hợp theo đặc tả/provider. Long thường dễ theo dõi và có phạm vi lớn.

### 3.1. Khởi tạo version trong schema

DDL có thể khai báo cột version:

~~~sql
CREATE TABLE banking.account (
  id BIGINT NOT NULL,
  balance DECIMAL(19,2) NOT NULL,
  version BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (id)
) ENGINE=InnoDB;
~~~

Khi Hibernate insert entity mới, provider sẽ khởi tạo version theo mapping. Nếu dữ liệu được tạo bằng SQL ngoài JPA, phải bảo đảm version có giá trị hợp lệ. Mọi đường ghi ngoài JPA cần tuân theo cùng quy ước version để không phá cơ chế phát hiện xung đột.

### 3.2. Khi nào conflict được phát hiện?

Xung đột thường được phát hiện khi provider flush thay đổi xuống database. Flush có thể xảy ra:

- Khi gọi EntityManager.flush().
- Trước một query cần đồng bộ persistence context theo flush mode.
- Khi transaction commit.
- Theo thời điểm provider quyết định flush.

Do đó, repository.save(entity) trả về không có nghĩa commit đã thành công. Lỗi có thể chỉ xuất hiện lúc flush hoặc khi transaction commit ở cuối phương thức @Transactional.

Có thể gọi flush để phát hiện lỗi sớm hơn trong một luồng xử lý:

~~~java
account.debit(amount);
entityManager.flush();
~~~

Flush gửi SQL xuống database nhưng không commit transaction. Transaction vẫn có thể rollback sau đó; cũng có thể phát sinh lỗi khác ở commit. Không bắt lỗi optimistic conflict rồi tiếp tục dùng entity/persistence context như chưa có gì xảy ra.

### 3.3. Xử lý OptimisticLockException

JPA định nghĩa OptimisticLockException. Khi dùng Spring, lỗi thường được chuyển thành một loại OptimisticLockingFailureException trong hệ thống exception của Spring.

Một service cơ bản:

~~~java
@Service
public class AccountService {
    private final AccountRepository accounts;

    public AccountService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void debit(Long accountId, BigDecimal amount) {
        Account account = accounts.findById(accountId)
            .orElseThrow(() -> new EntityNotFoundException("Account not found"));

        account.debit(amount);
    }
}
~~~

Nếu hai request cùng sửa entity với cùng version, một request có thể commit trước; request còn lại thất bại khi flush/commit. Transaction thất bại phải rollback. Nếu nghiệp vụ cho phép, ứng dụng có thể đọc lại trạng thái mới và thực hiện lại toàn bộ thao tác trong một transaction mới.

Không retry chỉ câu UPDATE cuối cùng với version cũ. Cần đọc lại dữ liệu và tính lại quyết định nghiệp vụ từ trạng thái mới.

## 4. Optimistic locking với Spring Data JPA

Repository có thể dùng JpaRepository thông thường:

~~~java
public interface AccountRepository
        extends JpaRepository<Account, Long> {
}
~~~

Spring Data JPA và provider quản lý version khi entity được cập nhật. Code service không cần tự viết điều kiện version trong mọi câu lệnh nếu tất cả thao tác ghi đều đi qua cơ chế entity lifecycle.

Một số điểm cần chú ý:

- Entity phải được quản lý trong persistence context khi thay đổi để dirty checking hoạt động.
- Với entity detached, save thường dẫn đến merge; kết quả merge là một instance được quản lý khác. Không tiếp tục dùng object detached để suy luận version mới.
- Không sửa version field thủ công.
- Đảm bảo tất cả đường ghi quan trọng đều tuân theo version contract.
- Xử lý lỗi ở ranh giới transaction, không chỉ quanh lời gọi repository.

### 4.1. DTO và cập nhật entity

API nên nhận dữ liệu thay đổi qua DTO, tải entity hiện tại rồi áp dụng các field được phép thay đổi. Tránh nhận nguyên entity từ client và merge mù quáng vì client có thể gửi version cũ, field nhạy cảm hoặc giá trị không được phép sửa.

Ví dụ:

~~~java
public record ChangeAccountRequest(
    BigDecimal debitAmount,
    Long expectedVersion
) {}
~~~

Có thể so sánh expectedVersion của request với version entity đã tải để trả lỗi nghiệp vụ dễ hiểu. Tuy nhiên, so sánh ở Java không thay thế kiểm tra @Version khi flush: một transaction khác vẫn có thể cập nhật sau bước so sánh. Version predicate ở database mới là lớp bảo vệ cuối.

## 5. Bulk update và native SQL có thể bỏ qua @Version

JPQL bulk update, Criteria bulk update và native SQL không đi qua entity lifecycle theo cách thông thường. Chúng không tự động cập nhật version như dirty checking entity và không đồng bộ trạng thái của các entity đã nạp trong persistence context.

Ví dụ bulk update:

~~~java
@Modifying
@Query("""
    update Account a
       set a.balance = a.balance - :amount
     where a.id = :id
       and a.balance >= :amount
    """)
int debitIfEnough(
    @Param("id") Long id,
    @Param("amount") BigDecimal amount
);
~~~

Câu lệnh này dùng điều kiện atomic để trừ tiền khi đủ số dư, nhưng không tự dùng @Version. Nếu cần optimistic version check trong bulk update, hãy đưa version vào predicate và tăng version tường minh:

~~~java
@Modifying
@Query("""
    update Account a
       set a.balance = a.balance - :amount,
           a.version = a.version + 1
     where a.id = :id
       and a.version = :expectedVersion
       and a.balance >= :amount
    """)
int debitWithVersion(
    @Param("id") Long id,
    @Param("amount") BigDecimal amount,
    @Param("expectedVersion") Long expectedVersion
);
~~~

Nếu kết quả bằng 0, có thể hàng không tồn tại, version đã đổi hoặc số dư không đủ. Cần phân biệt các trường hợp bằng truy vấn/logic phù hợp nếu API cần trả lỗi riêng.

Sau bulk update, các entity cùng loại đã được nạp trong persistence context có thể stale. Dùng clearAutomatically/flushAutomatically khi phù hợp hoặc chủ động flush rồi clear EntityManager. Không đọc lại entity từ persistence context cũ và tin rằng nó phản ánh bulk update.

## 6. Pessimistic locking trong JPA

Pessimistic locking yêu cầu database khóa tài nguyên để transaction khác không thể thực hiện thao tác xung đột cho đến khi transaction hiện tại kết thúc hoặc lock timeout xảy ra.

Jakarta Persistence cung cấp các lock mode phổ biến:

| LockModeType | Ý nghĩa |
|---|---|
| NONE | Không yêu cầu lock bổ sung qua JPA. |
| READ | Tương đương optimistic read lock trong ngữ nghĩa JPA; không nên nhầm với khóa chia sẻ vật lý của InnoDB. |
| WRITE | Tương đương optimistic write lock; thường được ánh xạ sang version check. |
| OPTIMISTIC | Yêu cầu optimistic lock cho entity. |
| OPTIMISTIC_FORCE_INCREMENT | Optimistic lock và tăng version ngay cả khi không có thay đổi field thông thường. |
| PESSIMISTIC_READ | Yêu cầu khóa đọc ở database nếu provider hỗ trợ. |
| PESSIMISTIC_WRITE | Yêu cầu khóa ghi để ngăn transaction khác sửa/xóa hàng bị khóa. |
| PESSIMISTIC_FORCE_INCREMENT | Pessimistic lock và tăng version theo ngữ nghĩa JPA. |

Trong ứng dụng JPA, dùng PESSIMISTIC_WRITE cho thao tác cần đọc rồi cập nhật một hàng trong transaction ngắn. Với InnoDB, thao tác này thường được triển khai bằng locking read tương tự SELECT ... FOR UPDATE.

Không giữ pessimistic lock trong lúc gọi API bên ngoài, chờ người dùng hoặc xử lý CPU lâu. Lock được giữ đến khi transaction commit/rollback, vì vậy transaction càng dài thì nguy cơ contention và deadlock càng cao.

## 7. Dùng @Lock trong Spring Data JPA

Spring Data JPA hỗ trợ gắn lock mode lên phương thức repository bằng @Lock:

~~~java
public interface AccountRepository
        extends JpaRepository<Account, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from Account a where a.id = :id")
    Optional<Account> findByIdForUpdate(@Param("id") Long id);
}
~~~

Service phải gọi phương thức này bên trong transaction:

~~~java
@Service
public class LockedAccountService {
    private final AccountRepository accounts;

    public LockedAccountService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void debit(Long accountId, BigDecimal amount) {
        Account account = accounts.findByIdForUpdate(accountId)
            .orElseThrow(() -> new EntityNotFoundException("Account not found"));

        account.debit(amount);
    }
}
~~~

Nếu gọi locking query ngoài transaction, hành vi có thể không đúng yêu cầu hoặc provider/database sẽ báo lỗi. Không dựa vào một repository method có @Lock như thể nó tự tạo transaction bao trùm toàn bộ logic service.

### 7.1. Dùng EntityManager

Có thể yêu cầu lock khi tìm entity:

~~~java
Account account = entityManager.find(
    Account.class,
    accountId,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Hoặc khóa entity đã được quản lý:

~~~java
entityManager.lock(account, LockModeType.PESSIMISTIC_WRITE);
~~~

Cả hai phải chạy trong transaction phù hợp. Nếu entity đã có trong persistence context, provider có thể cần lấy lock trên hàng tương ứng; kiểm tra SQL phát ra và hành vi theo provider/version.

### 7.2. Locking query với JPQL

~~~java
TypedQuery<Account> query = entityManager.createQuery(
    "select a from Account a where a.id = :id",
    Account.class
);

query.setParameter("id", accountId);
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);

Account account = query.getSingleResult();
~~~

Locking query phù hợp khi cần lấy một tập entity theo điều kiện. Hãy xem execution plan và index; một predicate rộng có thể khóa nhiều record hoặc range hơn dự kiến tùy isolation level và access path của InnoDB.

## 8. Khóa hàng, index và phạm vi khóa của InnoDB

InnoDB khóa record/index record, không đơn giản chỉ khóa một dòng logic như cách mô tả ở mức ORM. Với locking read và update, phạm vi khóa phụ thuộc index được dùng, điều kiện tìm kiếm và isolation level.

Ở REPEATABLE READ, InnoDB có thể dùng next-key lock (record lock kết hợp gap lock) để ngăn phantom trong các trường hợp phù hợp. Một truy vấn khóa theo điều kiện thiếu index có thể quét và khóa nhiều record hơn mong đợi.

Ví dụ:

~~~sql
SELECT *
FROM sales.orders
WHERE customer_id = 42
FOR UPDATE;
~~~

Nếu customer_id không có index, engine có thể phải quét nhiều hàng. Khi dùng locking read, điều đó có thể tạo phạm vi khóa rộng, làm các transaction không liên quan phải chờ.

Tạo index phù hợp với predicate và kiểm tra kế hoạch:

~~~sql
CREATE INDEX idx_orders_customer_id
ON sales.orders(customer_id);

EXPLAIN
SELECT *
FROM sales.orders
WHERE customer_id = 42
FOR UPDATE;
~~~

Index không chỉ tối ưu tốc độ; nó còn giúp thu hẹp phạm vi record cần truy cập và khóa. Tuy nhiên, index mới làm tăng chi phí ghi và storage. Chọn index theo workload thực tế.

## 9. Pessimistic lock timeout

JPA cho phép truyền hint timeout cho lock. Với Jakarta Persistence, hint chuẩn thường dùng là jakarta.persistence.lock.timeout, giá trị tính bằng millisecond:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.lock.timeout", 3000
);

Account account = entityManager.find(
    Account.class,
    accountId,
    LockModeType.PESSIMISTIC_WRITE,
    hints
);
~~~

Provider có thể không hỗ trợ hoặc không thể áp dụng chính xác hint này trong mọi database/driver. Hãy xác nhận SQL và hành vi thực tế bằng integration test.

Với Spring Data JPA:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.lock.timeout",
        value = "3000"
    )
)
@Query("select a from Account a where a.id = :id")
Optional<Account> findForUpdate(@Param("id") Long id);
~~~

Nếu dùng Spring Boot 2/JPA cũ, tên hint có thể là javax.persistence.lock.timeout. Không trộn package javax và jakarta trong cùng ứng dụng.

## 10. Ba loại timeout không giống nhau

Ứng dụng thường cần nhiều timeout ở các lớp khác nhau:

| Timeout | Đơn vị thường dùng | Giới hạn điều gì? |
|---|---:|---|
| @Transactional(timeout = ...) | Giây | Thời gian transaction theo cấu hình transaction manager/provider. |
| jakarta.persistence.query.timeout | Millisecond | Thời gian thực thi query theo hint JPA/provider. |
| jakarta.persistence.lock.timeout | Millisecond | Thời gian chờ lấy lock theo hint JPA/provider. |
| innodb_lock_wait_timeout | Giây | Thời gian InnoDB chờ row lock trước khi báo lock wait timeout. |
| connectTimeout của JDBC | Millisecond | Thời gian thiết lập kết nối. |
| socketTimeout của JDBC | Millisecond | Thời gian chờ dữ liệu trên socket. |
| Timeout của connection pool | Theo pool | Thời gian chờ mượn connection từ pool. |

Ví dụ timeout transaction:

~~~java
@Transactional(timeout = 10)
public void updateOrder(Long orderId) {
    // Công việc transaction.
}
~~~

Ví dụ query timeout:

~~~java
query.setHint("jakarta.persistence.query.timeout", 5000);
~~~

Các giá trị trên là giới hạn ở lớp khác nhau. Transaction timeout không nhất thiết hủy ngay mọi câu SQL đang chạy; query timeout cũng không tự định nghĩa thời gian chờ lock trên mọi provider. Kiểm tra khả năng hỗ trợ và cấu hình thực tế.

### 10.1. innodb_lock_wait_timeout

MySQL có system variable innodb_lock_wait_timeout, tính bằng giây, để giới hạn thời gian chờ InnoDB row lock. Có thể kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'innodb_lock_wait_timeout';
~~~

Thời gian này không phải timeout cho mọi loại lock hoặc mọi hoạt động SQL. Metadata lock (MDL), network timeout và query execution có cơ chế khác.

Không tăng innodb_lock_wait_timeout để che giấu contention kéo dài. Tìm transaction giữ khóa, xem execution plan, rút ngắn transaction hoặc điều chỉnh thứ tự cập nhật trước.

### 10.2. Lock timeout và query timeout

Lock timeout xảy ra khi statement không lấy được lock cần thiết trong thời gian cho phép. Query timeout giới hạn thời gian thực thi query nói chung. Một query có thể chậm do scan, CPU hoặc I/O mà không chờ lock; ngược lại, query đơn giản có thể hết lock timeout khi hàng bị transaction khác giữ lâu.

Ghi nhận loại timeout cụ thể. Không chuyển mọi timeout thành thông báo "database unavailable".

## 11. Deadlock và lock wait timeout trong MySQL

Deadlock xảy ra khi các transaction tạo vòng chờ khóa. Ví dụ:

~~~text
Transaction T1                 Transaction T2
----------------              ----------------
Khóa hàng A                    Khóa hàng B
Chờ khóa hàng B                Chờ khóa hàng A
       \                         /
        \---- vòng chờ khóa -----/
~~~

InnoDB phát hiện deadlock và chọn một transaction làm nạn nhân để rollback. Ứng dụng thường thấy lỗi MySQL 1213 (Deadlock found when trying to get lock), SQLState thường thuộc nhóm 40001.

Lock wait timeout thường được báo bằng MySQL error 1205. Một transaction chờ khóa quá thời gian cấu hình nên statement bị thất bại.

Khác biệt quan trọng:

- Deadlock: database phát hiện chu trình chờ và chọn nạn nhân; transaction nạn nhân bị rollback.
- Lock wait timeout: statement chờ quá lâu và hết thời gian.
- Optimistic conflict: version predicate không còn khớp, provider báo dữ liệu đã bị sửa bởi transaction khác.

### 11.1. Hành vi rollback của MySQL khi timeout

Trong MySQL, innodb_rollback_on_timeout ảnh hưởng phạm vi rollback khi lock wait timeout. Khi tắt, mặc định phổ biến, InnoDB rollback statement bị timeout; khi bật, InnoDB rollback toàn transaction. Hãy kiểm tra cấu hình thực tế:

~~~sql
SHOW VARIABLES LIKE 'innodb_rollback_on_timeout';
~~~

Ở tầng Spring, nếu exception runtime thoát khỏi phương thức được quản lý bởi @Transactional, Spring thường đánh dấu transaction rollback theo quy tắc mặc định. Nhưng nếu code bắt exception rồi tiếp tục hoặc nuốt lỗi, trạng thái transaction có thể không như mong muốn.

Không tiếp tục commit một transaction sau lock timeout chỉ vì MySQL có thể đã rollback riêng statement. Hãy rollback toàn bộ đơn vị nghiệp vụ và chạy lại từ đầu nếu nghiệp vụ được phép retry.

## 12. Chuyển lỗi từ JPA/Hibernate sang Spring

Spring cung cấp exception translation để tầng service không phải phụ thuộc hoàn toàn vào mã lỗi JDBC hoặc exception riêng của Hibernate.

Một số nhóm exception thường gặp:

| Lỗi gốc hoặc tình huống | Nhóm lỗi Spring có thể gặp | Ý nghĩa |
|---|---|---|
| Optimistic version conflict | OptimisticLockingFailureException hoặc subclass JPA tương ứng | Entity đã bị cập nhật bởi transaction khác. |
| Không lấy được pessimistic lock | PessimisticLockingFailureException hoặc CannotAcquireLockException | Lock không thể lấy được trong điều kiện hiện tại. |
| Deadlock | DataAccessException subclass phản ánh concurrency/lock failure | Transaction bị chọn làm nạn nhân hoặc thao tác không thể tiếp tục. |
| Constraint violation | DataIntegrityViolationException | Vi phạm unique, foreign key, NOT NULL hoặc constraint khác. |
| Lỗi truy cập database chung | DataAccessException | Lỗi ở tầng data access cần phân loại thêm. |

Exception cụ thể phụ thuộc Spring version, persistence provider, driver và điểm lỗi. Có thể lỗi xuất hiện dưới dạng jakarta.persistence.OptimisticLockException, org.hibernate.StaleObjectStateException hoặc một subclass Spring sau khi exception translation được áp dụng.

### 12.1. @Repository và exception translation

Các bean repository được Spring quản lý có thể tham gia cơ chế exception translation. Spring chuyển lỗi persistence/SQL sang hệ thống DataAccessException nhất quán hơn.

~~~java
@Repository
public interface AccountRepository
        extends JpaRepository<Account, Long> {
}
~~~

Spring Data repository đã tích hợp cơ chế này. Với DAO tự viết dùng EntityManager/JdbcTemplate, cần để bean được Spring quản lý và dùng đúng abstraction để exception translation hoạt động.

Không bắt Throwable hoặc Exception chung rồi chuyển mọi lỗi thành "conflict". Giữ nguyên nguyên nhân và phân loại theo exception class, cause, SQLState và vendor code khi cần.

### 12.2. Logging lỗi hữu ích

Khi ghi log lỗi concurrency, nên có:

- Entity/table và khóa nghiệp vụ liên quan.
- Operation hoặc request ID.
- Transaction boundary và thời gian thực hiện.
- Lock mode/isolation level nếu liên quan.
- Exception class, SQLState và MySQL vendor code.
- Số lần retry và thời gian backoff.
- Host/database endpoint đã sử dụng.

Không log password, token, dữ liệu cá nhân hoặc toàn bộ câu SQL chứa literal nhạy cảm. Dùng bind parameter và log template/operation ID.

## 13. Quy tắc rollback của @Transactional

Spring mặc định rollback transaction khi phương thức @Transactional kết thúc bằng unchecked exception (RuntimeException hoặc Error). Checked exception không tự động gây rollback theo mặc định.

Ví dụ khai báo rollback cho checked exception:

~~~java
@Transactional(rollbackFor = BusinessRuleException.class)
public void processOrder(Long orderId)
        throws BusinessRuleException {
    // Các thao tác database.
}
~~~

OptimisticLockException và nhiều exception của Spring DataAccessException là unchecked. Nếu để chúng thoát khỏi transaction boundary, Spring sẽ rollback theo mặc định.

### 13.1. Không bắt rồi bỏ qua exception

Ví dụ nguy hiểm:

~~~java
@Transactional
public void updateAccount(Long id) {
    try {
        // Tải và cập nhật entity.
    } catch (OptimisticLockingFailureException ex) {
        log.warn("Conflict", ex);
        // Tiếp tục xử lý như thể update thành công.
    }
}
~~~

Sau conflict, transaction có thể đã bị đánh dấu rollback-only hoặc persistence context không còn thích hợp để tiếp tục. Khi phương thức kết thúc, commit có thể thất bại với UnexpectedRollbackException hoặc provider exception khác.

Nếu muốn retry, để exception thoát khỏi transaction attempt và thực hiện lần thử tiếp theo trong transaction mới.

## 14. Retry phải nằm ngoài transaction đã thất bại

Một lỗi concurrency không thể được giải quyết bằng cách lặp lại câu lệnh trong transaction đã bị rollback-only. Mỗi lần retry cần một transaction mới và thường cần tải lại entity từ database.

Một mẫu dễ hiểu là tách facade điều phối và bean thực hiện một lần thử:

~~~java
@Service
public class TransferFacade {
    private final TransferAttemptService attempts;

    public TransferFacade(TransferAttemptService attempts) {
        this.attempts = attempts;
    }

    // Không đặt @Transactional ở phương thức điều phối này.
    public void transfer(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                attempts.transferOnce(fromId, toId, amount);
                return;
            } catch (OptimisticLockingFailureException ex) {
                if (attempt == maxAttempts) {
                    throw ex;
                }

                pauseBeforeRetry(attempt);
            }
        }
    }

    private void pauseBeforeRetry(int attempt) {
        long delayMillis = Math.min(100L * (1L << (attempt - 1)), 1000L);
        try {
            Thread.sleep(delayMillis);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Retry interrupted", ex);
        }
    }
}
~~~

Bean thực hiện một lần thử:

~~~java
@Service
public class TransferAttemptService {
    private final AccountRepository accounts;

    public TransferAttemptService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transferOnce(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        Account from = accounts.findById(fromId)
            .orElseThrow(() -> new EntityNotFoundException("Source missing"));

        Account to = accounts.findById(toId)
            .orElseThrow(() -> new EntityNotFoundException("Target missing"));

        from.debit(amount);
        to.credit(amount);
    }
}
~~~

Hai class là hai Spring bean khác nhau để lời gọi transferOnce đi qua transactional proxy. Không gọi một phương thức @Transactional khác trong cùng object bằng self-invocation rồi mong proxy mở transaction mới.

Sau khi attempt ném exception, proxy rollback transaction trước khi exception quay lại facade. Lần gọi tiếp theo tạo transaction mới và nạp entity mới.

### 14.1. Những lỗi có thể retry

Có thể cân nhắc retry với:

- OptimisticLockingFailureException nếu nghiệp vụ có thể tính lại từ trạng thái mới.
- Deadlock hoặc lỗi lock tạm thời được phân loại phù hợp.
- Một số lỗi connection tạm thời, nhưng cần xử lý outcome unknown khi lỗi xảy ra trong commit.

Không retry tự động với:

- Sai cú pháp SQL hoặc thiếu cột/table.
- Thiếu quyền hoặc lỗi xác thực.
- Vi phạm nghiệp vụ không thể thay đổi bằng việc đọc lại.
- Duplicate key nếu đó là dấu hiệu request đã được xử lý hoặc dữ liệu đầu vào sai.
- Lỗi dữ liệu không hợp lệ hoặc vi phạm constraint cố định.

### 14.2. Retry và idempotency

Nếu thao tác chuyển tiền được gửi lại do client timeout, retry nội bộ không phải lớp duy nhất cần chống lặp. Dùng request ID duy nhất và lưu kết quả nghiệp vụ trong cùng transaction. Khi request đã hoàn tất, lần gọi lại trả kết quả cũ thay vì thực hiện thêm một lần chuyển tiền.

Không đặt sleep/backoff bên trong transaction đang giữ pessimistic lock. Rollback/close transaction trước, chờ ngoài transaction rồi mới bắt đầu lần thử mới.

## 15. Chọn optimistic hay pessimistic theo nghiệp vụ

| Nghiệp vụ | Gợi ý ban đầu | Lý do |
|---|---|---|
| Người dùng chỉnh hồ sơ cá nhân, xung đột ít | Optimistic | Có thể báo người dùng tải lại khi version đã đổi. |
| Chỉnh sửa tài liệu nhiều người cùng mở | Optimistic | Phát hiện stale edit và yêu cầu hợp nhất nội dung. |
| Trừ tồn kho hàng nóng | Atomic conditional UPDATE hoặc pessimistic tùy workload | Cần bảo đảm không bán vượt số lượng; đo contention. |
| Chuyển tiền giữa hai tài khoản | Optimistic hoặc pessimistic với transaction ngắn và thứ tự khóa nhất quán | Phải cập nhật cả hai tài khoản nguyên tử. |
| Cấp phát một tài nguyên duy nhất | Pessimistic lock hoặc unique constraint/atomic claim | Cần tránh hai worker nhận cùng tài nguyên. |
| Cập nhật trạng thái đơn hàng | Optimistic với version và state transition predicate | Phát hiện request cập nhật từ trạng thái cũ. |
| Đọc báo cáo | Thường không cần pessimistic lock | Lock đọc có thể cản writer mà không đem lại lợi ích nghiệp vụ. |

Đối với tồn kho, câu UPDATE có điều kiện thường là cách ngắn gọn:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE product_id = ?
  AND available >= 1;
~~~

Nếu update count là 1, đã giữ được một đơn vị tồn kho. Nếu bằng 0, sản phẩm không tồn tại hoặc không còn hàng. Có thể cần truy vấn bổ sung để phân biệt hai trường hợp. Câu lệnh này thực hiện kiểm tra điều kiện và cập nhật nguyên tử ở database.

Với nghiệp vụ nhiều hàng, nhiều bảng hoặc có logic đọc rồi quyết định phức tạp, chọn @Version hoặc pessimistic lock tùy mức cạnh tranh và yêu cầu trải nghiệm.

## 16. Pessimistic lock và thứ tự khóa

Khi một transaction cần khóa nhiều hàng, hãy lấy khóa theo thứ tự nhất quán để giảm nguy cơ deadlock.

Ví dụ hai tài khoản có ID 10 và 20. Mọi luồng chuyển tiền đều khóa ID nhỏ trước rồi ID lớn:

~~~java
List<Long> ids = Stream.of(fromId, toId)
    .sorted()
    .toList();

List<Account> locked = accounts.findAllByIdForUpdate(ids);
~~~

Repository có thể dùng query:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select a from Account a where a.id in :ids order by a.id")
List<Account> findAllByIdForUpdate(@Param("ids") Collection<Long> ids);
~~~

Đảm bảo thứ tự khóa thực tế bằng SQL và execution plan; ORDER BY ở JPQL không phải lúc nào cũng đủ để suy luận mọi chi tiết lock nội bộ. Nếu thứ tự khóa là invariant quan trọng, cân nhắc lấy từng khóa theo thứ tự rõ ràng trong cùng transaction hoặc dùng SQL phù hợp đã kiểm thử.

Không giả định database luôn khóa theo thứ tự mà collection truyền vào. Xác nhận trên MySQL và Hibernate version đang dùng.

## 17. Lock timeout, exception và trạng thái transaction

Khi lock timeout hoặc deadlock xảy ra, hãy coi transaction attempt hiện tại là thất bại và rollback toàn bộ đơn vị nghiệp vụ trước khi retry.

JPA phân biệt một số tình huống:
- PessimisticLockException biểu thị lỗi khóa khiến transaction bị rollback theo ngữ nghĩa JPA.
- LockTimeoutException biểu thị timeout khi lấy lock nhưng không nhất thiết đánh dấu transaction rollback-only theo đặc tả JPA.

Tuy nhiên, Spring @Transactional mặc định rollback khi unchecked exception thoát khỏi proxy. Nếu code bắt LockTimeoutException bên trong phương thức và tiếp tục, transaction có thể ở trạng thái khó dự đoán giữa provider và database. Cách vận hành an toàn cho nghiệp vụ ghi là dừng attempt, rollback transaction và bắt đầu transaction mới nếu cần retry.

Đừng cố tiếp tục từ giữa một chuỗi cập nhật nhiều bảng sau khi một thao tác lock đã thất bại.

## 18. Quan sát lock wait trên MySQL

Khi hệ thống chậm do khóa, cần tìm transaction đang chờ và transaction giữ khóa.

Trên MySQL 8.0, Performance Schema có thể cung cấp thông tin về data lock:

~~~sql
SELECT *
FROM performance_schema.data_locks;
~~~

Thông tin các quan hệ chờ khóa:

~~~sql
SELECT *
FROM performance_schema.data_lock_waits;
~~~

Kiểm tra transaction InnoDB:

~~~sql
SELECT *
FROM information_schema.innodb_trx;
~~~

Và báo cáo trạng thái InnoDB:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Các bảng và cột có thể cần quyền phù hợp. Output của SHOW ENGINE INNODB STATUS chứa nhiều phần; tập trung vào LATEST DETECTED DEADLOCK và transaction đang giữ/chờ lock.

Khi điều tra, ghi lại:

- Transaction ID và thời gian transaction mở.
- Thread/connection ID và user.
- SQL đang chạy hoặc statement trước đó.
- Index/table bị khóa.
- Lock mode và trạng thái WAITING/GRANTED.
- Isolation level.
- Application request ID.
- Thời gian giữ khóa và số request bị ảnh hưởng.

Không chỉ tăng timeout khi thấy lock wait. Xác định transaction giữ khóa quá lâu, thiếu index, thứ tự khóa không nhất quán hoặc transaction có thao tác ngoài database.

## 19. Kiểm thử optimistic conflict

Một integration test cần hai transaction độc lập đọc cùng version rồi cập nhật.

Luồng kiểm thử:

1. Tạo account với balance 100 và version 0.
2. Transaction A tải entity.
3. Transaction B tải cùng entity.
4. A thay đổi balance và commit; version tăng.
5. B thay đổi entity từ version cũ và thử commit.
6. Xác nhận B nhận optimistic locking failure.
7. Đọc lại entity trong transaction mới và kiểm tra balance/version.

Không dùng một EntityManager/persistence context duy nhất cho cả hai transaction vì nó có thể trả cùng managed entity và không tái hiện cạnh tranh thật. Dùng hai connection hoặc hai transaction manager context độc lập, có barrier để kiểm soát thứ tự.

## 20. Kiểm thử pessimistic lock và timeout

Dùng hai transaction:

1. T1 mở transaction và lấy PESSIMISTIC_WRITE trên account.
2. T1 giữ transaction chưa commit.
3. T2 yêu cầu PESSIMISTIC_WRITE cùng hàng.
4. T2 chờ đến khi T1 commit/rollback hoặc timeout.
5. Ghi nhận exception và thời gian chờ.
6. Xác nhận T2 có thể thử lại bằng transaction mới nếu nghiệp vụ cho phép.

Bài kiểm thử phải dùng MySQL/InnoDB tương tự production. H2 hoặc database giả lập có thể không tái hiện chính xác locking behavior, deadlock detection, timeout và SQL do Hibernate sinh ra.

## 21. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ @Transactional tự ngăn lost update | Hai transaction vẫn có thể ghi dựa trên cùng dữ liệu cũ | Dùng @Version, locking read hoặc atomic conditional UPDATE. |
| Không có @Version trên entity cần optimistic lock | Không phát hiện stale update theo version | Thêm version column và bảo đảm mọi đường ghi tuân thủ. |
| Dùng bulk update nhưng nghĩ @Version tự chạy | Version và persistence context có thể không đồng bộ | Đưa version predicate/tăng version tường minh hoặc dùng entity lifecycle. |
| Gọi PESSIMISTIC_WRITE ngoài transaction | Lock không được giữ qua toàn bộ logic | Đặt transaction ở service boundary. |
| Giữ lock khi gọi HTTP | Transaction dài, tăng lock wait và deadlock | Tách side effect bằng outbox hoặc xử lý ngoài transaction. |
| Bắt optimistic exception rồi tiếp tục | Transaction có thể rollback-only hoặc persistence context stale | Để lỗi thoát khỏi attempt; retry trong transaction mới. |
| Retry bên trong cùng @Transactional method | Lặp lại trên transaction đã thất bại | Tách retry orchestration khỏi transactional worker. |
| Tăng lock timeout để che contention | Request chờ lâu và giữ tài nguyên lâu hơn | Tìm blocker, index và transaction dài. |
| Dùng một thứ tự khóa khác nhau ở mỗi luồng | Tăng deadlock | Quy định thứ tự khóa nhất quán. |
| Chỉ kiểm thử bằng H2 | Không thấy khác biệt lock behavior của MySQL | Chạy integration test trên MySQL/InnoDB. |
| Retry thao tác không idempotent | Ghi trùng hoặc side effect lặp | Dùng request ID/unique key và lưu kết quả trong transaction. |

## 22. Bài tập thực hành

### Bài 1: Optimistic locking

Tạo entity Account có @Version. Mở hai transaction độc lập, tải cùng account, cập nhật từ cả hai rồi commit theo thứ tự. Quan sát version tăng và exception của transaction cũ.

### Bài 2: Pessimistic locking

Tạo repository method có @Lock(PESSIMISTIC_WRITE). Dùng hai transaction khóa cùng hàng, đo thời gian chờ và thử cấu hình lock timeout. Xác nhận lock được giải phóng sau commit/rollback.

### Bài 3: Bulk update

Viết một JPQL bulk update cho entity có @Version. Kiểm tra version có tăng hay không, rồi sửa câu lệnh để kiểm tra expected version và tăng version tường minh. Làm mới persistence context và so sánh kết quả.

### Bài 4: Deadlock

Tạo hai transaction cập nhật hai hàng theo thứ tự ngược nhau để tạo deadlock. Ghi nhận MySQL error code/SQLState và Spring exception. Thay đổi code để khóa theo thứ tự thống nhất rồi kiểm thử lại.

### Bài 5: Retry ngoài transaction

Tách facade điều phối và service transactional. Tạo optimistic conflict có kiểm soát, retry tối đa ba lần với backoff. Xác nhận mỗi lần thử dùng transaction/persistence context mới và request không bị thực hiện trùng.

### Bài 6: Timeout nhiều lớp

Đặt transaction timeout, query timeout và lock timeout khác nhau trong môi trường thử nghiệm. Tạo tình huống query chậm và tình huống chờ lock. Quan sát loại exception, thời gian phát sinh và trạng thái rollback.

## 23. Checklist trước khi triển khai production

- [ ] Entity có @Version khi nghiệp vụ cần phát hiện stale update.
- [ ] Các đường ghi ngoài JPA đã được xem xét để không phá version contract.
- [ ] Bulk JPQL/native SQL có version predicate và đồng bộ persistence context khi cần.
- [ ] Pessimistic lock chỉ được giữ trong transaction ngắn.
- [ ] Repository locking method được gọi từ service có transaction boundary.
- [ ] Index hỗ trợ predicate của locking query.
- [ ] Lock order nhất quán khi cập nhật nhiều hàng.
- [ ] Transaction, query, lock, connection và pool timeout được phân biệt.
- [ ] innodb_lock_wait_timeout và innodb_rollback_on_timeout đã được kiểm tra.
- [ ] Exception translation được kiểm thử với đúng Spring/JPA/provider version.
- [ ] Retry diễn ra ngoài transaction đã thất bại.
- [ ] Retry có giới hạn, backoff và idempotency phù hợp.
- [ ] Không giữ lock khi gọi dịch vụ ngoài hoặc chờ thao tác người dùng.
- [ ] Có giám sát lock wait, deadlock, transaction age và pool saturation.
- [ ] Integration test chạy trên MySQL/InnoDB tương thích production.
- [ ] Log có request ID, SQLState/vendor code và số lần retry nhưng không lộ secret.

Optimistic locking dùng version để phát hiện cập nhật dựa trên dữ liệu cũ; pessimistic locking giữ khóa trong transaction để điều phối truy cập cạnh tranh. Timeout cần được đặt ở đúng lớp, còn exception translation giúp ứng dụng phân loại lỗi nhất quán. Khi transaction thất bại, rollback toàn bộ attempt và chỉ retry bằng transaction mới nếu nghiệp vụ có thể lặp lại an toàn. Hãy kiểm thử trên MySQL/InnoDB thực tế, quan sát lock wait và deadlock, rồi chọn chiến lược dựa trên mức xung đột cùng yêu cầu của nghiệp vụ.

