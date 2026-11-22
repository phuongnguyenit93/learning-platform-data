# Mô phỏng hai giao dịch tranh chấp tồn kho và xử lý xung đột

## Mục tiêu

Khi hai request cùng đặt mua một mặt hàng, chúng có thể đọc cùng số lượng tồn kho rồi cùng quyết định rằng còn đủ hàng. Nếu mỗi transaction ghi giá trị mới dựa trên dữ liệu cũ mà không kiểm tra xung đột, hệ thống có thể xác nhận nhiều đơn hơn số hàng thực tế. Đây là một dạng lost update dẫn đến overbooking.

Bài thực hành này tạo hai transaction độc lập, buộc cả hai đọc cùng một phiên bản tồn kho trước khi ghi, sau đó quan sát cách JPA phát hiện xung đột bằng optimistic locking. Ta cũng kiểm tra retry trong transaction mới, pessimistic locking, câu UPDATE có điều kiện, idempotency và cách chạy test trên database thật.

Sau bài này, bạn có thể:

- Giải thích race condition khi nhiều request cùng giữ một mặt hàng.
- Xác định invariant tồn kho và bảo vệ nó ở cả domain lẫn database.
- Dùng @Version để phát hiện cập nhật dựa trên phiên bản cũ.
- Viết integration test với hai thread, hai transaction và một điểm đồng bộ xác định.
- Xác nhận một transaction commit, transaction còn lại nhận optimistic locking conflict.
- Retry an toàn bằng transaction mới và tải lại dữ liệu.
- So sánh optimistic locking, pessimistic locking và atomic conditional UPDATE.
- Xử lý deadlock, timeout, rollback và request lặp.
- Kiểm tra hành vi concurrency bằng Testcontainers.

## 1. Tình huống và invariant cần bảo vệ

Giả sử một mặt hàng đang có 10 đơn vị có thể bán. Hai request độc lập cùng muốn giữ 7 đơn vị:

| Thời điểm | Transaction T1 | Transaction T2 | Available trong DB |
|---|---|---|---:|
| 1 | Đọc available = 10 | | 10 |
| 2 | | Đọc available = 10 | 10 |
| 3 | Tính 10 - 7 = 3 | | 10 |
| 4 | | Tính 10 - 7 = 3 | 10 |
| 5 | Ghi available = 3 | | 3 |
| 6 | | Ghi available = 3 | 3 |

Nếu cả hai lần ghi đều thành công dựa trên dữ liệu cũ, hệ thống đã hứa 14 đơn vị trong khi chỉ có 10. Giá trị database cuối cùng có thể là 3 nhưng hai đơn hàng đều được xác nhận. Chỉ kiểm tra available trong Java không ngăn được tình huống này vì hai transaction có thể cùng đọc một snapshot cũ.

Invariant tối thiểu:

- available luôn lớn hơn hoặc bằng 0.
- Một lần giữ hàng chỉ thành công khi available đủ lớn.
- Cùng một yêu cầu nghiệp vụ không được trừ tồn kho nhiều lần.
- Nếu một transaction thất bại, các thay đổi của transaction đó phải rollback.

Điều kiện kiểm tra và phép thay đổi phải được bảo vệ tại thời điểm ghi bằng version, row lock hoặc một câu lệnh UPDATE có điều kiện.

## 2. Tạo entity có optimistic locking

Entity đại diện cho lượng hàng có thể bán:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_item")
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Column(nullable = false)
    private int available;

    protected InventoryItem() {
    }

    public InventoryItem(int available) {
        if (available < 0) {
            throw new IllegalArgumentException(
                "Available quantity cannot be negative");
        }
        this.available = available;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }

        if (available < quantity) {
            throw new InsufficientStockException(
                "Not enough stock: available=" + available
                    + ", requested=" + quantity);
        }

        available -= quantity;
    }

    public Long getId() {
        return id;
    }

    public int getAvailable() {
        return available;
    }

    public long getVersion() {
        return version;
    }
}
~~~

Ngoại lệ nghiệp vụ:

~~~java
public class InsufficientStockException extends RuntimeException {

    public InsufficientStockException(String message) {
        super(message);
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {
}
~~~

Trường @Version được JPA provider quản lý. Ứng dụng không tự tăng trường này trong luồng cập nhật entity thông thường. Khi tải entity, mỗi transaction nhận cả available và version hiện tại. Khi flush hoặc commit, provider tạo câu UPDATE có điều kiện tương đương:

~~~sql
UPDATE inventory_item
   SET available = ?, version = ?
 WHERE id = ? AND version = ?;
~~~

Giả sử T1 và T2 đều tải version = 0. Transaction ghi trước cập nhật được hàng có version = 0 và tăng version. UPDATE của transaction còn lại không còn khớp version cũ, nên provider phát hiện số hàng cập nhật bằng 0 và ném optimistic locking exception.

Câu SQL thực tế phụ thuộc provider, dialect và mapping. Ý nghĩa quan trọng là câu UPDATE phải kiểm tra version đã đọc, không chỉ kiểm tra ID.

## 3. Service giữ hàng trong transaction

Service tải entity, gọi hành vi miền và để dirty checking ghi thay đổi:

~~~java
import jakarta.persistence.EntityNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryReservationService {

    private final InventoryRepository inventoryRepository;

    public InventoryReservationService(
            InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void reserve(Long itemId, int quantity) {
        InventoryItem item = inventoryRepository.findById(itemId)
            .orElseThrow(() ->
                new EntityNotFoundException("Inventory item not found"));

        item.reserve(quantity);
    }
}
~~~

Entity được tải trong transaction nên đang được quản lý. Khi reserve() giảm available, JPA ghi nhận thay đổi. SQL có thể chỉ được phát lúc flush hoặc commit. Vì vậy, service chạy đến dòng cuối chưa có nghĩa transaction đã commit; caller chỉ coi thao tác thành công khi lời gọi qua Spring proxy kết thúc mà không có lỗi commit.

Không bắt optimistic locking exception bên trong transaction rồi tiếp tục dùng entity cũ. Transaction có thể đã rollback hoặc bị đánh dấu rollback-only. Hãy để lỗi thoát ra ngoài transaction boundary, sau đó tải lại dữ liệu trong transaction mới.

## 4. Mô phỏng hai transaction cùng đọc một version

Để test tái hiện race condition ổn định, phải bảo đảm cả hai transaction đều đọc entity trước khi bất kỳ transaction nào ghi. Nếu chỉ khởi chạy hai thread rồi hy vọng chúng chạy đúng thời điểm, test có thể lúc pass lúc không.

Ta dùng:

- Hai thread độc lập.
- Một transaction riêng cho mỗi thread.
- CyclicBarrier để chờ đến khi cả hai đã đọc xong.
- flush() để buộc UPDATE chạy và phát hiện conflict ngay trong callback.
- Một transaction mới để xác nhận trạng thái cuối ở database.

Ví dụ integration test với @DataJpaTest và TransactionTemplate:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManager;
import jakarta.persistence.OptimisticLockException;
import jakarta.persistence.PersistenceContext;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@DataJpaTest
class InventoryConcurrencyTest {

    @Autowired
    private PlatformTransactionManager transactionManager;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void onlyOneTransactionCanReserveFromTheSameVersion()
            throws Exception {

        TransactionTemplate transactions =
            new TransactionTemplate(transactionManager);
        transactions.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        Long itemId = transactions.execute(status -> {
            InventoryItem item = new InventoryItem(10);
            entityManager.persist(item);
            entityManager.flush();
            return item.getId();
        });

        CyclicBarrier bothTransactionsRead = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<String> first = pool.submit(() ->
                reserveInOwnTransaction(
                    transactions, itemId, 7, bothTransactionsRead));

            Future<String> second = pool.submit(() ->
                reserveInOwnTransaction(
                    transactions, itemId, 7, bothTransactionsRead));

            String firstResult = first.get(15, TimeUnit.SECONDS);
            String secondResult = second.get(15, TimeUnit.SECONDS);

            assertThat(List.of(firstResult, secondResult))
                .containsExactlyInAnyOrder(
                    "COMMITTED", "OPTIMISTIC_CONFLICT");

            Integer remaining = transactions.execute(status -> {
                entityManager.clear();
                return entityManager.find(InventoryItem.class, itemId)
                    .getAvailable();
            });

            assertThat(remaining).isEqualTo(3);
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(15, TimeUnit.SECONDS);

            transactions.executeWithoutResult(status -> {
                InventoryItem item =
                    entityManager.find(InventoryItem.class, itemId);
                if (item != null) {
                    entityManager.remove(item);
                }
            });
        }
    }

    private String reserveInOwnTransaction(
            TransactionTemplate transactions,
            Long itemId,
            int quantity,
            CyclicBarrier bothTransactionsRead) {

        try {
            transactions.executeWithoutResult(status -> {
                InventoryItem item =
                    entityManager.find(InventoryItem.class, itemId);

                awaitBothReads(bothTransactionsRead);

                item.reserve(quantity);
                entityManager.flush();
            });

            return "COMMITTED";
        } catch (RuntimeException ex) {
            if (hasCause(ex, OptimisticLockException.class)
                    || hasCause(
                        ex, OptimisticLockingFailureException.class)) {
                return "OPTIMISTIC_CONFLICT";
            }
            throw ex;
        }
    }

    private void awaitBothReads(CyclicBarrier barrier) {
        try {
            barrier.await(10, TimeUnit.SECONDS);
        } catch (Exception ex) {
            throw new IllegalStateException(
                "Both transactions did not reach the read barrier", ex);
        }
    }

    private boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expectedType) {

        Throwable current = error;
        while (current != null) {
            if (expectedType.isInstance(current)) {
                return true;
            }
            if (current.getCause() == current) {
                break;
            }
            current = current.getCause();
        }
        return false;
    }
}
~~~

Test method dùng Propagation.NOT_SUPPORTED để không có transaction test bao ngoài. Fixture được tạo và commit bằng TransactionTemplate trước khi hai thread chạy. Mỗi worker gọi executeWithoutResult() với REQUIRES_NEW, do đó có transaction riêng và persistence context riêng.

EntityManager được inject là shared proxy của Spring, proxy tìm EntityManager gắn với transaction hiện tại của từng thread. Không chia sẻ một instance EntityManager thật giữa hai thread vì persistence context không thread-safe.

Cả hai worker đọc available = 10 và cùng version trước khi barrier mở. Sau đó mỗi worker trừ 7 và flush. Một UPDATE thành công; UPDATE còn lại không còn khớp version và transaction rollback. Kết quả mong đợi là đúng một COMMITTED, một OPTIMISTIC_CONFLICT, và available cuối cùng bằng 3.

Transaction nào thắng phụ thuộc lịch chạy thread. Test không nên khẳng định T1 luôn thắng hoặc T2 luôn thắng. Barrier có timeout để test thất bại rõ ràng nếu một worker không tới điểm đồng bộ. Fixture được xóa trong transaction riêng ở finally để test không để lại dữ liệu.

## 5. Vì sao cần flush và đọc lại bằng transaction mới?

save() hoặc thay đổi field trên entity managed chưa chắc đã phát SQL ngay. Nếu bỏ flush(), lỗi optimistic locking có thể chỉ xuất hiện lúc commit, khiến vị trí phát sinh lỗi khó xác định hơn trong test.

flush() đồng bộ persistence context với database nhưng không commit transaction. Khi flush phát hiện conflict, transaction hiện tại phải rollback. Nếu lỗi chỉ được phát lúc commit, TransactionTemplate.execute() vẫn ném exception sau khi callback kết thúc và trước khi trả kết quả cho caller.

Sau khi hai worker kết thúc, test dùng transaction mới và gọi clear() trước khi tải lại entity. Điều này tránh đọc nhầm trạng thái từ persistence context cũ. Kết quả cuối phải được xác nhận từ database: available = 3, version đã tăng một lần và không có lần giữ hàng thứ hai.

Không dùng một transaction duy nhất cho cả hai worker. Cũng không chỉ gọi hai phương thức tuần tự trong cùng transaction vì cách đó không mô phỏng hai transaction cùng giữ version cũ.

## 6. Retry conflict trong transaction mới

Optimistic locking conflict có nghĩa dữ liệu đã thay đổi sau khi transaction hiện tại đọc nó. Retry cần tải entity mới và chạy lại quy tắc nghiệp vụ từ đầu. Không tái sử dụng entity stale hoặc tiếp tục trong transaction đã rollback.

Một cách điều phối retry tường minh bằng TransactionTemplate:

~~~java
import jakarta.persistence.EntityNotFoundException;
import jakarta.persistence.OptimisticLockException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

public class InventoryRetryCoordinator {

    private final InventoryRepository inventoryRepository;
    private final PlatformTransactionManager transactionManager;

    public InventoryRetryCoordinator(
            InventoryRepository inventoryRepository,
            PlatformTransactionManager transactionManager) {
        this.inventoryRepository = inventoryRepository;
        this.transactionManager = transactionManager;
    }

    public void reserveWithRetry(Long itemId, int quantity) {
        TransactionTemplate attemptTransaction =
            new TransactionTemplate(transactionManager);
        attemptTransaction.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                attemptTransaction.executeWithoutResult(status -> {
                    InventoryItem item =
                        inventoryRepository.findById(itemId)
                            .orElseThrow(() ->
                                new EntityNotFoundException(
                                    "Inventory item not found"));

                    item.reserve(quantity);
                });
                return;
            } catch (RuntimeException ex) {
                boolean conflict =
                    hasOptimisticConflict(ex);

                if (!conflict || attempt == maxAttempts) {
                    throw ex;
                }

                pauseBeforeRetry(attempt);
            }
        }
    }

    private boolean hasOptimisticConflict(Throwable error) {
        Throwable current = error;
        while (current != null) {
            if (current instanceof OptimisticLockException
                    || current instanceof OptimisticLockingFailureException) {
                return true;
            }
            if (current.getCause() == current) {
                break;
            }
            current = current.getCause();
        }
        return false;
    }

    private void pauseBeforeRetry(int attempt) {
        try {
            Thread.sleep(50L * attempt);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Retry was interrupted", ex);
        }
    }
}
~~~

Mỗi vòng lặp gọi executeWithoutResult() với REQUIRES_NEW, nên transaction trước đã kết thúc trước khi lần thử mới bắt đầu. Entity được tải lại từ database trong từng lần thử. Ví dụ dùng backoff tuyến tính để dễ đọc; production nên dùng backoff có giới hạn và jitter.

Trong tình huống hai request cùng giữ 7 từ lượng 10, request thắng commit và available còn 3. Request thua nhận conflict, retry, tải lại available = 3 rồi ném InsufficientStockException. Đây là kết quả nghiệp vụ đúng. Hết hàng không phải lỗi transient để retry tiếp.

Coordinator cần nằm ngoài transaction bao trùm. Nếu một transaction ngoài đang hoạt động và worker dùng REQUIRED, các lần thử có thể tham gia cùng transaction đó, làm mất ý nghĩa retry độc lập. REQUIRES_NEW tạm ngưng transaction bên ngoài nếu có.

## 7. Phân biệt conflict, hết hàng và lỗi hạ tầng

Không gom mọi exception vào một vòng retry:

| Tình huống | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Optimistic locking conflict | Một transaction khác đã cập nhật version | Tải lại và retry có giới hạn |
| InsufficientStockException | Dữ liệu mới không còn đủ hàng | Từ chối yêu cầu; không retry |
| EntityNotFoundException | Mặt hàng không tồn tại | Trả lỗi nghiệp vụ phù hợp |
| Deadlock | Database hủy một transaction để phá vòng chờ | Retry toàn bộ transaction mới nếu thao tác an toàn |
| Lock timeout | Không lấy được khóa trong thời hạn | Retry có giới hạn hoặc trả lỗi tạm thời |
| Constraint violation | Dữ liệu vi phạm quy tắc database | Kiểm tra nguyên nhân; không retry mặc định |
| Connection failure | Kết quả commit có thể chưa rõ với caller | Tra cứu bằng idempotency key trước khi gửi lại |

Với lỗi kết nối ngay lúc commit, caller có thể không biết transaction đã commit hay chưa. Không được suy luận rằng timeout đồng nghĩa database chưa ghi dữ liệu. Hãy dùng request ID ổn định để kiểm tra kết quả đã được áp dụng hay chưa trước khi thực hiện lại.

## 8. Lựa chọn khác: pessimistic locking

Optimistic locking cho phép nhiều transaction đọc đồng thời rồi phát hiện xung đột khi ghi. Nếu một mặt hàng thường xuyên bị tranh chấp, có thể dùng pessimistic write lock để tuần tự hóa thao tác trên hàng đó.

Repository:

~~~java
import jakarta.persistence.LockModeType;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select i
          from InventoryItem i
         where i.id = :id
        """)
    Optional<InventoryItem> findForUpdate(@Param("id") Long id);
}
~~~

Service:

~~~java
@Transactional
public void reserveWithPessimisticLock(Long itemId, int quantity) {
    InventoryItem item = inventoryRepository.findForUpdate(itemId)
        .orElseThrow(() ->
            new EntityNotFoundException("Inventory item not found"));

    item.reserve(quantity);
}
~~~

Transaction đầu lấy khóa ghi trên hàng tồn kho. Transaction thứ hai muốn lấy khóa tương ứng phải chờ hoặc thất bại theo lock timeout của provider/database. Sau khi transaction đầu commit, transaction thứ hai tiếp tục và kiểm tra số lượng mới. Nếu available chỉ còn 3, yêu cầu giữ 7 bị từ chối.

Pessimistic locking phù hợp khi xung đột ghi thường xuyên và transaction ngắn. Không gọi HTTP, gửi email hoặc chờ người dùng trong lúc giữ khóa. Nếu một transaction cần khóa nhiều mặt hàng, hãy khóa theo thứ tự ID ổn định để giảm nguy cơ deadlock. Lock timeout và hint cụ thể phụ thuộc provider; hãy kiểm tra hành vi trên database triển khai.

## 9. Lựa chọn khác: UPDATE có điều kiện

Nếu nghiệp vụ chỉ cần giảm số lượng và kiểm tra đủ hàng, có thể để database thực hiện điều kiện và phép trừ trong cùng một câu lệnh:

~~~java
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update InventoryItem i
           set i.available = i.available - :quantity
         where i.id = :itemId
           and i.available >= :quantity
        """)
    int reserveIfAvailable(
        @Param("itemId") Long itemId,
        @Param("quantity") int quantity
    );
}
~~~

Kiểm tra quantity lớn hơn 0 ở service trước khi gọi query. Kết quả:

- 1: một hàng được cập nhật; thao tác giữ hàng thành công.
- 0: không có hàng phù hợp; có thể mặt hàng không tồn tại hoặc không đủ hàng.

Điều kiện available >= quantity và phép trừ chạy nguyên tử tại database. Hai request không thể cùng đọc một giá trị cũ trong Java rồi ghi đè lẫn nhau bằng kết quả tính trước đó.

Đây là JPQL bulk update. Nó bỏ qua dirty checking, callback entity và không tự đồng bộ persistence context. flushAutomatically đồng bộ thay đổi đang chờ trước query; clearAutomatically clear persistence context sau query. Nếu entity đã được tải trước đó, không dùng đối tượng cũ như trạng thái mới nhất.

Bulk update cũng không tự thực hiện optimistic version check như cập nhật entity thông thường. Nếu cùng bảng còn được cập nhật qua entity có @Version, cần thiết kế version/audit/event nhất quán và kiểm thử cả hai đường ghi. Dùng conditional UPDATE khi quy tắc có thể biểu diễn gọn trong một câu lệnh; dùng aggregate method và locking khi nghiệp vụ có nhiều invariant cần kiểm tra.

## 10. Deadlock, lock timeout và thứ tự khóa

Deadlock có thể xuất hiện khi hai transaction giữ các khóa khác nhau rồi chờ khóa mà transaction kia đang giữ. Ví dụ T1 khóa mặt hàng A rồi chờ B, trong khi T2 khóa B rồi chờ A.

Các biện pháp giảm rủi ro:

- Khóa nhiều hàng theo cùng thứ tự, chẳng hạn tăng dần theo ID.
- Giữ transaction ngắn và chỉ tải những hàng cần thiết.
- Không gọi dịch vụ ngoài khi đang giữ database lock.
- Cấu hình lock timeout và transaction timeout phù hợp.
- Retry toàn bộ transaction trong transaction mới khi database xác định lỗi có thể retry.
- Giới hạn số lần retry, dùng backoff và jitter.
- Ghi metric về deadlock, lock wait, timeout và số lần retry.

Khi database hủy một transaction do deadlock, transaction đó phải rollback. Không bắt lỗi rồi tiếp tục dùng persistence context hoặc transaction đã thất bại. Retry phải tải lại dữ liệu và thực hiện lại toàn bộ quy tắc nghiệp vụ.

## 11. Idempotency để request lặp không trừ hàng hai lần

@Version ngăn hai transaction ghi dựa trên cùng version, nhưng không tự ngăn cùng một request nghiệp vụ được gửi lại sau khi lần đầu đã commit. Ví dụ server commit giữ 2 đơn vị nhưng response bị mất; client timeout và gửi lại request. Nếu lần gửi lại được coi là request mới, tồn kho có thể bị trừ thêm 2.

Dùng một idempotency key ổn định do caller tạo hoặc do hệ thống cấp trước lần thử đầu tiên. Lưu key cùng kết quả nghiệp vụ và bảo vệ bằng unique constraint:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
    name = "stock_reservation",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_stock_reservation_request",
        columnNames = "request_id"
    )
)
public class StockReservation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "request_id", nullable = false, updatable = false)
    private String requestId;

    @Column(name = "item_id", nullable = false, updatable = false)
    private Long itemId;

    @Column(nullable = false, updatable = false)
    private int quantity;

    protected StockReservation() {
    }

    public StockReservation(
            String requestId,
            Long itemId,
            int quantity) {
        this.requestId = requestId;
        this.itemId = itemId;
        this.quantity = quantity;
    }
}
~~~

Trong cùng transaction, service cần:

1. Ghi reservation theo requestId và flush để kiểm tra unique constraint.
2. Tải InventoryItem và gọi reserve(quantity).
3. Commit cả reservation và thay đổi available cùng nhau.

Nếu bước giữ hàng thất bại, transaction rollback cả bản ghi reservation. Nếu cùng requestId được gửi lại, unique constraint ngăn tạo reservation thứ hai. Tầng gọi xử lý duplicate sau khi transaction thất bại: tải reservation đã commit trong transaction mới, xác nhận itemId và quantity khớp payload ban đầu, rồi trả lại kết quả cũ. Nếu cùng key nhưng payload khác, trả lỗi xung đột thay vì coi đó là request trùng hợp lệ.

Không dùng findByRequestId() rồi mới save() như cơ chế chống trùng duy nhất. Hai transaction có thể cùng đọc thấy chưa tồn tại. Unique constraint ở database mới là hàng rào cuối cùng khi request đến đồng thời.

## 12. Rollback và ranh giới transaction

Spring mặc định rollback transaction khi phương thức transactional ném RuntimeException hoặc Error. Vì InsufficientStockException trong ví dụ kế thừa RuntimeException, thay đổi trước đó trong cùng transaction sẽ rollback.

Với checked exception, mặc định Spring không rollback trong mọi trường hợp. Nếu nghiệp vụ yêu cầu rollback, khai báo rõ rollbackFor:

~~~java
@Transactional(rollbackFor = ReservationRejectedException.class)
public void reserveForOrder(Long itemId, int quantity)
        throws ReservationRejectedException {
    // load item, validate and update
}
~~~

Không bắt exception rồi trả về bình thường trong cùng transaction nếu transaction đã bị đánh dấu rollback-only. Khi cần xử lý lỗi và retry, để exception thoát khỏi transaction worker, sau đó bắt ở coordinator không có transaction bao ngoài.

Đối với một use case giữ hàng và tạo đơn trong cùng database, hãy quyết định rõ hai thao tác phải atomic hay có thể đi theo trạng thái PENDING rồi xác nhận sau. Nếu chúng thuộc cùng một transaction cục bộ, lỗi giữ hàng phải rollback phần tạo đơn theo yêu cầu nghiệp vụ. Nếu tách thành nhiều service/database, cần outbox/Saga và idempotency thay vì giả định @Transactional cục bộ bao phủ mọi hệ thống.

## 13. Kiểm thử với database thật bằng Testcontainers

H2 hữu ích cho test nhanh, nhưng lock behavior, isolation, deadlock, timeout và câu SQL có thể khác database production. Với test concurrency quan trọng, nên chạy cùng loại database với môi trường triển khai.

Ví dụ cấu hình PostgreSQL Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class InventoryConcurrencyIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void testRunsAgainstPostgres() {
        // Reuse the two-transaction test from the previous section.
    }
}
~~~

Đây là phần cấu hình test container; đưa test concurrency ở phần trước vào cùng test class hoặc một lớp base dùng chung. Nếu dự án dùng Flyway hoặc Liquibase, để migration tạo schema như production thay vì chỉ dựa vào Hibernate tự generate DDL.

Testcontainers không tự làm test concurrency đúng. Vẫn cần hai transaction độc lập, barrier để đồng bộ thời điểm đọc, flush/commit để phát hiện conflict và transaction mới để xác nhận dữ liệu cuối.

## 14. Các kịch bản kiểm thử cần có

Ngoài test hai request cùng giữ 7 từ lượng 10, hãy kiểm tra:

1. Một request thành công: available = 10, giữ 4, kết quả còn 6.
2. Không đủ hàng: available = 3, yêu cầu giữ 7, nhận lỗi nghiệp vụ và database vẫn là 3.
3. Hai transaction cùng version: cả hai đọc 10, cùng giữ 7; đúng một commit và một conflict.
4. Retry sau conflict: transaction mới đọc available = 3 và từ chối yêu cầu 7.
5. Pessimistic lock: transaction thứ hai chờ, sau đó đọc số lượng mới và từ chối nếu không đủ.
6. Conditional UPDATE: hai request đồng thời; tổng số hàng cập nhật không vượt lượng có thể giữ.
7. Deadlock/timeout: giả lập lỗi khóa; transaction bị hủy và retry có giới hạn.
8. Request lặp cùng idempotency key: chỉ tạo một reservation và chỉ trừ hàng một lần.
9. Cùng key, payload khác: request thứ hai bị từ chối.
10. Rollback: lỗi sau khi tạo reservation nhưng trước commit phải rollback cả reservation và thay đổi tồn kho.
11. Đọc sau commit: kiểm tra trạng thái bằng transaction mới, không chỉ bằng entity đang nằm trong persistence context cũ.

Không assert transaction T1 luôn thắng. Chỉ assert tập kết quả có một success và một conflict. Test cần timeout cho barrier và Future để lỗi đồng bộ không làm suite treo vô hạn.

## 15. Lỗi thường gặp

- Dùng một transaction hoặc một EntityManager cho cả hai thread nên không mô phỏng concurrency thật.
- Không đồng bộ thời điểm đọc nên hai transaction không giữ cùng version.
- Chỉ gọi save() mà không flush hoặc chờ commit, khiến lỗi xuất hiện ngoài vị trí test mong đợi.
- Bắt optimistic locking exception bên trong transaction rồi tiếp tục dùng entity stale.
- Retry entity cũ thay vì tải lại trong transaction mới.
- Coi conflict là hết hàng; chỉ sau khi đọc lại mới biết yêu cầu có đủ hàng hay không.
- Retry InsufficientStockException hoặc constraint violation như lỗi transient.
- Chỉ kiểm tra entity trong persistence context, không đọc lại database bằng transaction mới.
- Dùng @Version nhưng một đường bulk/native update khác bỏ qua version.
- Dùng pessimistic lock quá lâu hoặc khóa nhiều hàng theo thứ tự khác nhau.
- Không có idempotency key nên request timeout sau commit có thể trừ hàng lần thứ hai.
- Kết luận về locking production chỉ từ H2 mà không kiểm tra database thật.

## 16. Checklist triển khai

- Xác định invariant: available không âm và reservation không vượt số lượng có thể bán.
- Chọn @Version khi xung đột không quá thường xuyên và chấp nhận retry.
- Dùng PESSIMISTIC_WRITE khi cần tuần tự hóa thao tác và có thể giữ transaction ngắn.
- Dùng conditional UPDATE khi quy tắc có thể biểu diễn bằng một câu lệnh nguyên tử.
- Đảm bảo mọi đường ghi đều tuân thủ cùng quy tắc version, audit và event.
- Retry conflict/deadlock có giới hạn trong transaction mới, với backoff và jitter.
- Không retry lỗi nghiệp vụ hết hàng hoặc lỗi dữ liệu vĩnh viễn.
- Dùng idempotency key và unique constraint để chống request lặp.
- Kiểm tra rollback và đọc lại kết quả sau commit.
- Chạy integration test với database cùng loại production bằng Testcontainers.
- Theo dõi conflict rate, retry count, lock wait, deadlock, timeout và số request bị từ chối vì hết hàng.

Kết quả mong đợi của mô phỏng là chỉ một trong hai request giữ được 7 đơn vị từ lượng tồn 10. Transaction còn lại phát hiện version đã thay đổi; khi retry trên dữ liệu mới, nó thấy chỉ còn 3 và bị từ chối. Việc kết hợp transaction boundary, concurrency control và idempotency giúp Spring Data JPA bảo vệ tồn kho ngay cả khi nhiều request đến đồng thời hoặc client phải gửi lại yêu cầu.