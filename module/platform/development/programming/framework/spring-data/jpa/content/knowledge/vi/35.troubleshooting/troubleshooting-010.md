# Lỗi khóa lạc quan, khóa bi quan và deadlock

Khi nhiều request cùng đọc và cập nhật một dữ liệu, ứng dụng phải kiểm soát xung đột để tránh ghi đè thay đổi của nhau hoặc giữ tài nguyên quá lâu. Spring Data JPA dựa trên cơ chế khóa của JPA và database để hỗ trợ hai chiến lược chính:

- **Optimistic locking (khóa lạc quan):** cho phép nhiều transaction đọc cùng dữ liệu; khi cập nhật, kiểm tra dữ liệu có bị thay đổi từ lúc đọc hay không.
- **Pessimistic locking (khóa bi quan):** khóa hàng dữ liệu ở database để transaction khác không thể thực hiện một số thao tác xung đột cho đến khi khóa được giải phóng.

Deadlock xảy ra khi các transaction giữ khóa mà transaction khác đang cần, tạo thành vòng chờ. Database thường phát hiện vòng chờ và hủy một transaction làm nạn nhân. Ứng dụng cần nhận diện đúng loại lỗi, thiết kế thứ tự truy cập nhất quán và chỉ retry sau khi transaction cũ đã kết thúc.

## 1. Hiểu xung đột cập nhật và lost update

Giả sử kho còn 10 sản phẩm. Hai request cùng đọc số lượng là 10:

1. Transaction A đọc 10 và muốn trừ 7.
2. Transaction B cũng đọc 10 và muốn trừ 6.
3. A ghi 3.
4. B ghi 4 dựa trên giá trị cũ 10.

Nếu không có cơ chế kiểm soát cạnh tranh, một cập nhật có thể ghi đè cập nhật còn lại. Kết quả cuối cùng là 3 hoặc 4 tùy thứ tự ghi, trong khi cả hai yêu cầu đã được xử lý như thể cùng thành công. Đây là lost update.

Không phải mọi truy cập đồng thời đều là lỗi. Nhiều transaction có thể đọc cùng dữ liệu một cách an toàn. Vấn đề phát sinh khi chúng cùng thay đổi dữ liệu và kết quả cần bảo đảm invariant nghiệp vụ, ví dụ tồn kho không âm, số dư không bị mất cập nhật hoặc trạng thái đơn hàng không bị chuyển ngược.

## 2. Optimistic locking với @Version

### Cơ chế

Optimistic locking giả định xung đột không thường xuyên. Entity có một trường version được đánh dấu bằng `@Version`. Khi provider cập nhật entity, nó dùng giá trị version đã đọc làm điều kiện trong câu lệnh SQL và tăng version nếu cập nhật thành công.

Ví dụ về ý tưởng SQL:

```sql
UPDATE inventory
   SET available = 3,
       version = 8
 WHERE id = 100
   AND version = 7;
```

Nếu transaction khác đã cập nhật hàng và version hiện tại không còn là 7, câu lệnh ảnh hưởng 0 hàng. Provider nhận ra xung đột và ném lỗi optimistic locking. Nhờ vậy, cập nhật dựa trên snapshot cũ không âm thầm ghi đè dữ liệu mới.

### Khai báo version trong entity

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Inventory {

    @Id
    private Long id;

    private int available;

    @Version
    private Long version;

    protected Inventory() {
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (available < quantity) {
            throw new IllegalStateException("Insufficient inventory");
        }
        available -= quantity;
    }

    public int getAvailable() {
        return available;
    }
}
```

Các kiểu dữ liệu version portable thường dùng gồm `int`, `Integer`, `short`, `Short`, `long`, `Long` và `java.sql.Timestamp`. Dùng một trường version duy nhất cho entity và để JPA provider quản lý giá trị của nó; không tự tăng version trong setter thông thường.

### Service cập nhật với optimistic locking

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository inventoryRepository;

    public InventoryService(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void reserve(Long inventoryId, int quantity) {
        Inventory inventory = inventoryRepository.findById(inventoryId)
            .orElseThrow(() -> new IllegalArgumentException("Inventory not found"));

        inventory.reserve(quantity);

        // Entity đang managed; dirty checking sẽ ghi thay đổi khi flush/commit.
    }
}
```

Hai transaction có thể cùng tải một entity với version giống nhau. Transaction commit trước cập nhật thành công và tăng version. Transaction còn lại sẽ gặp optimistic locking failure khi flush hoặc commit.

Không nên chỉ kiểm tra lỗi quanh lệnh setter. Xung đột thường chỉ được phát hiện khi provider phát SQL, tức tại `flush()` hoặc khi transaction commit.

### Exception thường gặp

Ở tầng JPA, lỗi thường là `jakarta.persistence.OptimisticLockException`. Khi đi qua Spring repository exception translation, ứng dụng có thể nhận các kiểu trong Spring DAO như `OptimisticLockingFailureException` hoặc `ObjectOptimisticLockingFailureException`, tùy đường thực thi và provider.

Lỗi này có nghĩa snapshot của transaction không còn phù hợp để cập nhật. Không nên tự động ghi lại giá trị cũ hoặc lặp lại cùng object detached. Cần tải lại trạng thái mới, kiểm tra lại quy tắc nghiệp vụ và quyết định có thể thử lại hay phải báo xung đột cho người dùng.

### Các lock mode lạc quan

JPA còn có các lock mode:

- `LockModeType.OPTIMISTIC`: yêu cầu kiểm tra version để bảo vệ khỏi cập nhật xung đột.
- `LockModeType.OPTIMISTIC_FORCE_INCREMENT`: ngoài kiểm tra optimistic, yêu cầu tăng version, kể cả khi không có thay đổi field thông thường.

Có thể dùng khi một thao tác nghiệp vụ cần đánh dấu aggregate/entity đã được kiểm soát cạnh tranh dù dữ liệu scalar không đổi. Không cần dùng force increment cho mọi lần đọc.

## 3. Pessimistic locking với LockModeType

### Cơ chế

Pessimistic locking yêu cầu database khóa tài nguyên ngay trong transaction, thường là hàng được truy vấn. Transaction khác có thể phải chờ, bị timeout hoặc nhận lỗi tùy loại lock, isolation level và database.

Các lock mode thường gặp:

- `PESSIMISTIC_READ`: yêu cầu khóa đọc để ngăn cập nhật xung đột trong thời gian khóa.
- `PESSIMISTIC_WRITE`: yêu cầu khóa ghi, thường được dùng khi sắp sửa cập nhật dữ liệu và cần tuần tự hóa các writer.
- `PESSIMISTIC_FORCE_INCREMENT`: kết hợp khóa bi quan với tăng version của entity có version.

Cách database triển khai lock cụ thể phụ thuộc provider, dialect, engine và loại truy vấn. Ví dụ với database hỗ trợ, `PESSIMISTIC_WRITE` thường được triển khai bằng câu lệnh tương tự `SELECT ... FOR UPDATE`.

### Khai báo @Lock trong Spring Data JPA

Spring Data JPA cung cấp annotation `@Lock` để gắn lock mode vào query method:

```java
import java.util.Optional;

import jakarta.persistence.LockModeType;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<Inventory, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from Inventory i where i.id = :id")
    Optional<Inventory> findByIdForUpdate(@Param("id") Long id);
}
```

Service sử dụng phương thức này trong transaction:

```java
@Service
public class InventoryService {

    private final InventoryRepository inventoryRepository;

    public InventoryService(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void reserveWithLock(Long id, int quantity) {
        Inventory inventory = inventoryRepository.findByIdForUpdate(id)
            .orElseThrow(() -> new IllegalArgumentException("Inventory not found"));

        inventory.reserve(quantity);
    }
}
```

Transaction lấy khóa, kiểm tra số lượng, cập nhật entity và giữ khóa cho đến khi transaction kết thúc. Request khác cần khóa xung đột trên cùng hàng phải chờ hoặc thất bại theo timeout/lock policy.

Phương thức repository lấy lock phải chạy trong transaction đang hoạt động. Đặt ranh giới `@Transactional` ở service thường phù hợp vì thao tác đọc có khóa, kiểm tra và cập nhật cần nằm trong cùng transaction.

### Khi nào dùng pessimistic locking?

Phù hợp khi:

- Xung đột xảy ra thường xuyên.
- Transaction cần đọc rồi cập nhật một tài nguyên mà không muốn nhiều writer cùng đi qua giai đoạn xử lý.
- Thao tác ngắn và có thể giữ lock trong thời gian nhỏ.
- Nghiệp vụ yêu cầu tuần tự hóa cập nhật, ví dụ phân bổ một tài nguyên khan hiếm.

Không phù hợp khi transaction kéo dài, gọi dịch vụ ngoài trong lúc đang giữ lock, hoặc tải nhiều hàng không cần thiết. Những trường hợp đó làm tăng thời gian chờ và nguy cơ deadlock.

### Lock timeout

Có thể cấu hình lock timeout bằng query hint JPA, ví dụ:

```java
import jakarta.persistence.QueryHint;

import org.springframework.data.jpa.repository.QueryHints;

@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.lock.timeout",
        value = "3000"
    )
)
@Query("select i from Inventory i where i.id = :id")
Optional<Inventory> findByIdForUpdate(@Param("id") Long id);
```

Giá trị ví dụ là 3000 mili giây. Hỗ trợ hint và cách áp dụng có thể khác nhau theo JPA provider và database; một số hệ thống không thể bảo đảm chính xác timeout được yêu cầu. Hãy kiểm tra SQL và cấu hình thực tế của provider.

Lock timeout khác deadlock: timeout nghĩa transaction không lấy được lock trong thời gian cho phép; deadlock nghĩa tồn tại vòng chờ giữa các transaction. Cả hai có thể được dịch thành các exception Spring DAO liên quan tới khóa.

## 4. So sánh optimistic và pessimistic locking

| Tiêu chí | Optimistic locking | Pessimistic locking |
|---|---|---|
| Cách hoạt động | Phát hiện xung đột lúc cập nhật/flush/commit bằng version | Giữ khóa database trong transaction |
| Tình huống phù hợp | Xung đột ít, đọc nhiều, transaction ngắn | Xung đột thường xuyên, cần tuần tự hóa writer |
| Tác động khi có xung đột | Một transaction thất bại và cần xử lý lại nghiệp vụ | Transaction khác chờ, timeout hoặc bị từ chối |
| Chi phí | Ít giữ lock trong lúc đọc; có thể phải xử lý retry | Giữ lock và tăng thời gian chờ |
| Phụ thuộc | Trường `@Version` và provider | Lock mode, transaction, database và dialect |
| Rủi ro chính | Người dùng nhận xung đột khi dữ liệu thay đổi đồng thời | Lock contention, timeout và deadlock |

Không có chiến lược tốt nhất cho mọi entity. Chọn theo tần suất xung đột, thời gian transaction, mức độ quan trọng của invariant và khả năng xử lý xung đột ở tầng nghiệp vụ.

## 5. Deadlock là gì?

Deadlock (bế tắc) xảy ra khi một nhóm transaction giữ các lock mà transaction khác trong nhóm đang cần, tạo thành chu trình chờ không thể tự tiến triển.

Ví dụ:

- Transaction A khóa hàng X, sau đó cần khóa hàng Y.
- Transaction B khóa hàng Y, sau đó cần khóa hàng X.
- A chờ B giải phóng Y.
- B chờ A giải phóng X.

```text
Transaction A                  Transaction B
-------------                  -------------
LOCK row X                     LOCK row Y
REQUEST row Y  ------------->  đang giữ row Y
đang giữ row X  <------------- REQUEST row X
       \                           /
        \_______ vòng chờ ________/
```

Database thường có bộ phát hiện deadlock. Khi phát hiện chu trình, database chọn một transaction làm nạn nhân và rollback transaction đó để giải phóng khóa cho transaction còn lại. Transaction bị chọn có thể nhận lỗi deadlock từ JDBC/provider và được Spring dịch thành exception truy cập dữ liệu.

Deadlock không đồng nghĩa với hai transaction chỉ chờ nhau quá lâu. Lock timeout có thể xảy ra mà không có chu trình. Cần xem thông báo database và log để phân biệt.

## 6. Nguyên nhân phổ biến gây deadlock

### Truy cập nhiều hàng theo thứ tự khác nhau

Đây là nguyên nhân kinh điển: transaction A khóa X rồi Y, còn transaction B khóa Y rồi X. Thống nhất thứ tự khóa sẽ giảm nguy cơ tạo chu trình.

### Transaction giữ lock quá lâu

Một transaction giữ lock trong lúc:

- Gọi HTTP hoặc dịch vụ bên ngoài.
- Chờ người dùng nhập dữ liệu.
- Xử lý file hoặc tính toán nặng.
- Thực hiện nhiều câu query không liên quan.
- Xử lý batch quá lớn.

Thời gian giữ lock càng lâu thì cơ hội chồng lấn với transaction khác càng cao.

### Query thiếu index hoặc phạm vi khóa rộng

Một query không có index phù hợp có thể quét nhiều hàng, làm thời gian thực thi tăng và tùy engine có thể khóa nhiều tài nguyên hơn dự kiến. Điều kiện truy vấn và index phù hợp giúp database tìm đúng hàng nhanh hơn.

### Cập nhật nhiều bảng hoặc quan hệ theo thứ tự khác nhau

Các transaction cùng cập nhật entity và quan hệ liên quan nhưng đi theo thứ tự khác nhau có thể tạo chu trình khóa. Cascade, trigger và foreign key cũng có thể khiến database cần thêm lock ngoài những câu lệnh nhìn thấy trực tiếp ở Java.

### Lock escalation và hành vi riêng của database

Một số engine có chiến lược quản lý lock, mức khóa hoặc cơ chế phát hiện deadlock khác nhau. Không suy luận chính xác phạm vi khóa chỉ từ annotation JPA; hãy kiểm tra SQL thực tế và tài liệu của database đang dùng.

## 7. Chẩn đoán deadlock và lỗi khóa

### Bước 1: Xác định exception gốc

Các exception có thể gặp:

- `OptimisticLockException` ở JPA hoặc exception optimistic locking được Spring dịch.
- `PessimisticLockException` khi lỗi khóa làm transaction thất bại.
- `LockTimeoutException` khi chờ khóa vượt giới hạn; theo JPA, timeout có thể không buộc toàn transaction rollback trong mọi trường hợp, tùy loại lỗi và provider.
- Exception Spring DAO như `PessimisticLockingFailureException`, `CannotAcquireLockException` hoặc các subtype liên quan.
- Exception JDBC/SQL chứa mã lỗi và thông báo deadlock của database.

Tên exception cụ thể phụ thuộc database driver, provider và Spring exception translation. Hãy ghi log cả exception chain và SQL state/vendor error code thay vì chỉ log message ngoài cùng.

### Bước 2: Xác định SQL và thứ tự lấy khóa

Bật log SQL và transaction khi điều tra:

```yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.orm.jpa: DEBUG
    org.hibernate.SQL: DEBUG
```

Nếu cần bind parameter, có thể bật logger bind parameter của Hibernate tương ứng phiên bản đang dùng; log giá trị nhạy cảm cần được xử lý theo chính sách bảo mật dữ liệu.

Đối chiếu timestamp của các transaction, SQL update/select, lock request và thời điểm rollback. Tập trung vào những hàng và bảng mà hai transaction cùng truy cập.

### Bước 3: Kiểm tra database

Thông tin deadlock do database cung cấp thường hữu ích hơn stack trace Java vì database nhìn thấy toàn bộ chu trình khóa.

Ví dụ:

- **MySQL/InnoDB:** kiểm tra `SHOW ENGINE INNODB STATUS` để xem deadlock gần nhất; trên các phiên bản phù hợp có thể xem thêm `performance_schema.data_locks` và `data_lock_waits`.
- **PostgreSQL:** xem `pg_stat_activity`, `pg_locks` và quan hệ blocking bằng các view hệ thống; log server có thể chứa thông tin deadlock chi tiết.

Cú pháp và quyền truy cập phụ thuộc phiên bản, cấu hình và quyền database. Không chạy truy vấn chẩn đoán có thể làm lộ dữ liệu nhạy cảm trong môi trường production.

### Bước 4: Tái hiện với concurrency test

Dùng hai thread/transaction độc lập, hai connection database thật và barrier/latch để kiểm soát thứ tự thao tác. Không dùng một EntityManager chia sẻ giữa hai thread. Test phải xác minh:

- Cả hai transaction thực sự chạy đồng thời.
- Thứ tự lock được tạo đúng như tình huống lỗi.
- Một transaction nhận deadlock/lock failure như dự kiến.
- Database không để lại trạng thái dữ liệu một phần.
- Kết quả cuối cùng thỏa invariant nghiệp vụ.

Test chỉ chạy tuần tự hoặc dùng một transaction test bao ngoài sẽ không tái hiện đúng cạnh tranh giữa hai transaction độc lập.

## 8. Cách phòng tránh deadlock

1. **Thống nhất thứ tự khóa:** mọi luồng nghiệp vụ cập nhật nhiều hàng nên truy cập theo cùng thứ tự, ví dụ sắp xếp ID tăng dần trước khi khóa.
2. **Giữ transaction ngắn:** chỉ đặt các thao tác database cần tính nguyên tử bên trong transaction.
3. **Không gọi dịch vụ ngoài khi đang giữ lock:** thực hiện HTTP, gửi email hoặc xử lý file sau khi transaction kết thúc, hoặc dùng outbox.
4. **Dùng index phù hợp:** tối ưu điều kiện WHERE, JOIN và truy vấn lấy lock để tránh quét phạm vi lớn.
5. **Khóa đúng phạm vi:** chỉ lấy các hàng cần thiết; tránh pessimistic lock trên truy vấn rộng.
6. **Giảm kích thước batch:** chia batch lớn thành phần nhỏ có ranh giới transaction rõ ràng khi nghiệp vụ cho phép.
7. **Giữ thứ tự cập nhật bảng nhất quán:** các use case cùng chạm nhiều bảng nên theo cùng một trình tự.
8. **Đặt timeout hợp lý:** giới hạn thời gian chờ để request không treo vô hạn, đồng thời theo dõi timeout để phát hiện contention.
9. **Không giữ EntityManager hoặc transaction qua nhiều thread:** EntityManager không thread-safe; mỗi transaction/thread cần phạm vi quản lý phù hợp.

## 9. Retry sau optimistic lock, lock timeout hoặc deadlock

Retry có thể phù hợp với lỗi cạnh tranh tạm thời, nhưng phải thực hiện đúng ranh giới transaction.

### Nguyên tắc retry an toàn

- Transaction cũ phải rollback/kết thúc trước khi thử lại.
- Mỗi lần thử phải đọc lại dữ liệu mới trong transaction mới.
- Chạy lại toàn bộ nghiệp vụ và kiểm tra invariant từ đầu.
- Giới hạn số lần thử; dùng backoff và jitter để tránh các request va chạm lặp lại.
- Chỉ retry loại lỗi được xác định là tạm thời.
- Bảo đảm thao tác idempotent hoặc có cơ chế chống xử lý trùng.
- Không retry vô hạn và không retry lỗi nghiệp vụ như thiếu tồn kho.

Đặc biệt, không bắt optimistic locking exception rồi tiếp tục dùng entity stale trong cùng transaction. Transaction có thể đã bị đánh dấu rollback-only; dữ liệu và persistence context không còn phù hợp để tiếp tục.

### Tổ chức retry bên ngoài transaction

Một cách dễ kiểm soát là đặt vòng retry ở bean không có transaction bao ngoài; mỗi lần gọi worker service có `@Transactional` riêng. Khi worker ném lỗi, transaction của worker kết thúc/rollback trước khi caller quyết định thử lại.

Ví dụ cấu trúc:

```java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.stereotype.Service;

@Service
public class InventoryRetryFacade {

    private final InventoryTransactionService transactionService;

    public InventoryRetryFacade(
            InventoryTransactionService transactionService) {
        this.transactionService = transactionService;
    }

    // Không đặt @Transactional ở facade này.
    public void reserve(Long id, int quantity) {
        int maxAttempts = 3;

        for (int attempt = 1; ; attempt++) {
            try {
                transactionService.reserveOnce(id, quantity);
                return;
            } catch (OptimisticLockingFailureException
                     | PessimisticLockingFailureException ex) {
                if (attempt >= maxAttempts) {
                    throw ex;
                }
                waitBeforeRetry(attempt);
            }
        }
    }

    private void waitBeforeRetry(int attempt) {
        try {
            Thread.sleep(100L * attempt);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Retry interrupted", ex);
        }
    }
}
```

Worker phải là một Spring bean riêng:

```java
@Service
public class InventoryTransactionService {

    private final InventoryRepository repository;

    public InventoryTransactionService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserveOnce(Long id, int quantity) {
        Inventory inventory = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Not found"));

        inventory.reserve(quantity);
    }
}
```

Đây là khung minh họa. Trong production, backoff nên có jitter và metric; chỉ bắt các exception đã xác định là tạm thời. Tên exception được Spring dịch có thể khác theo provider/database. Tách facade và transactional worker thành hai bean giúp ranh giới retry bao ngoài transaction và tránh self-invocation bỏ qua proxy.

### Retry và tác dụng phụ bên ngoài

Không gửi email, thu tiền qua cổng thanh toán hoặc gọi API không idempotent bên trong đoạn có thể chạy lại. Nếu transaction rollback sau khi tác dụng phụ đã xảy ra, lần retry có thể lặp tác dụng phụ. Dùng idempotency key, outbox hoặc tách side effect sau commit để kiểm soát.

Với optimistic lock, sau khi tải lại dữ liệu mới, có thể thấy yêu cầu ban đầu không còn hợp lệ. Ví dụ số lượng tồn kho không đủ nữa; lúc đó phải trả lỗi nghiệp vụ thay vì retry tiếp.

## 10. Bulk update và giới hạn của @Version

JPQL bulk update/delete và native SQL tác động trực tiếp lên database, không thực hiện dirty checking từng entity như thao tác entity thông thường. Không mặc định rằng bulk update sẽ tự kiểm tra và tăng `@Version` theo cách provider làm khi cập nhật managed entity.

Ví dụ một bulk update có điều kiện version cần được thiết kế tường minh:

```sql
UPDATE inventory
   SET available = :newAvailable,
       version = version + 1
 WHERE id = :id
   AND version = :expectedVersion;
```

Nếu số hàng cập nhật là 0, có thể bản ghi không tồn tại hoặc version đã thay đổi; ứng dụng cần phân biệt theo yêu cầu nghiệp vụ. Sau bulk update, persistence context có thể chứa entity stale; hãy refresh hoặc clear có kiểm soát trước khi tiếp tục sử dụng các entity đó.

Nếu cần optimistic locking tự động của JPA, ưu tiên cập nhật entity managed với trường `@Version`. Nếu dùng bulk SQL vì hiệu năng, phải tự thiết kế điều kiện version, tăng version, kiểm tra số hàng ảnh hưởng và đồng bộ persistence context.

## 11. Chọn chiến lược theo tình huống

| Tình huống | Chiến lược gợi ý | Lý do |
|---|---|---|
| Dữ liệu ít bị cập nhật đồng thời, nhiều lượt đọc | Optimistic locking với `@Version` | Ít giữ khóa trong thời gian đọc |
| Nhiều request cùng sửa một hàng trong khoảng thời gian ngắn | Cân nhắc `PESSIMISTIC_WRITE` | Tuần tự hóa writer tại database |
| Cập nhật nhiều hàng theo một nghiệp vụ | Thứ tự khóa thống nhất, transaction ngắn; chọn optimistic/pessimistic theo contention | Giảm chu trình chờ |
| Lỗi deadlock hiếm và có thể thử lại | Retry có giới hạn sau rollback | Database đã hủy transaction nạn nhân |
| Lỗi optimistic lock do người khác sửa trước | Tải lại và đánh giá lại nghiệp vụ | Dữ liệu đầu vào đã cũ |
| Lỗi thiếu tồn kho hoặc vi phạm quy tắc nghiệp vụ | Không retry mù quáng | Đây không phải xung đột tạm thời |

## 12. Checklist chẩn đoán

Khi gặp lỗi khóa hoặc deadlock trong Spring Data JPA:

1. Ghi lại exception gốc, SQL state, vendor error code và transaction ID/correlation ID.
2. Xác định lỗi là optimistic conflict, lock timeout, deadlock hay lỗi constraint khác.
3. Xác định transaction nào đang giữ khóa và transaction nào đang chờ.
4. Kiểm tra entity có `@Version` hay repository query có `@Lock` không.
5. Xem SQL thực tế, điều kiện WHERE, index và thứ tự truy cập hàng/bảng.
6. Kiểm tra transaction có giữ lock trong lúc gọi API ngoài hoặc xử lý lâu không.
7. Chọn cách xử lý: tải lại và kiểm tra lại nghiệp vụ, điều chỉnh lock strategy, tối ưu query hoặc retry sau rollback.
8. Viết concurrency integration test để xác nhận dữ liệu cuối cùng vẫn thỏa invariant.

## Kết luận

Optimistic locking dùng `@Version` để phát hiện một transaction đang cập nhật dựa trên dữ liệu cũ. Pessimistic locking dùng `LockModeType` và `@Lock` để yêu cầu database giữ khóa trong transaction. Deadlock là vòng chờ giữa các transaction, thường được database phát hiện và rollback một transaction.

Hãy chọn chiến lược khóa theo mức độ cạnh tranh thực tế, giữ transaction ngắn, thống nhất thứ tự truy cập tài nguyên và kiểm tra exception gốc. Nếu cần retry, chỉ thử lại sau khi transaction cũ đã kết thúc, trong transaction mới, với số lần giới hạn và toàn bộ quy tắc nghiệp vụ được kiểm tra lại.
