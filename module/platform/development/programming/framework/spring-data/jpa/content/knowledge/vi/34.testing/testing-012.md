# Kiểm thử khóa, xung đột đồng thời và rollback

## 1. Mục tiêu

Khi nhiều request cùng đọc và cập nhật một Entity, dữ liệu có thể bị ghi đè hoặc thay đổi giữa thời điểm kiểm tra và thời điểm ghi. Spring Data JPA dựa trên cơ chế khóa của JPA/Hibernate và transaction của database để kiểm soát các tình huống này.

Bài học hướng dẫn cách kiểm thử:
- Optimistic locking bằng `@Version`, phát hiện hai transaction cùng cập nhật một phiên bản dữ liệu.
- Pessimistic locking bằng `@Lock(LockModeType.PESSIMISTIC_WRITE)`, giữ khóa khi transaction đang xử lý.
- Xung đột đồng thời bằng hai transaction và hai persistence context độc lập.
- Rollback khi nghiệp vụ ném exception hoặc không thỏa điều kiện.
- Kiểm tra dữ liệu sau commit/rollback bằng transaction mới.
- Phân biệt test chạy trong transaction của `@DataJpaTest` với transaction thật do Service quản lý.

Sau bài học, bạn có thể tạo integration test chứng minh một cập nhật cạnh tranh bị từ chối, một khóa ghi làm transaction khác phải chờ và một thao tác thất bại không để lại thay đổi đã commit.

## 2. Vì sao cần kiểm thử concurrency?

Giả sử kho có 10 sản phẩm. Hai request cùng đọc số lượng 10 và mỗi request đặt mua 1 sản phẩm. Nếu cả hai cùng ghi số lượng mới là 9 mà không có cơ chế bảo vệ, một lần giảm có thể bị mất. Kết quả sai là 9, trong khi hai đơn đã được xác nhận.

Đây là lost update. Các lỗi liên quan thường xuất hiện khi:

- Hai transaction đọc cùng một phiên bản Entity.
- Một transaction thay đổi dữ liệu sau khi transaction khác đã đọc.
- Ứng dụng kiểm tra trạng thái ở Java, sau đó ghi mà không xác nhận lại điều kiện tại database.
- Một transaction ghi nhiều bảng rồi gặp lỗi giữa chừng.

Unit test thông thường chạy tuần tự và thường dùng một persistence context, nên khó phát hiện các lỗi này. Cần integration test tạo transaction độc lập, có thời điểm đọc/ghi được điều phối và kiểm tra kết quả sau khi transaction kết thúc.

## 3. Optimistic locking với @Version

Optimistic locking phù hợp khi xung đột không xảy ra thường xuyên. Entity có một thuộc tính version được đánh dấu `@Version`. Khi JPA cập nhật Entity managed, provider đưa version hiện tại vào điều kiện `WHERE` và tăng version.

SQL do Hibernate tạo thường có dạng:

```sql
update stock_items
set available = ?, version = ?
where id = ? and version = ?;
```

Nếu transaction khác đã cập nhật cùng dòng, version trong database không còn khớp. UPDATE thứ hai tác động 0 dòng và provider báo optimistic locking conflict, thường qua `OptimisticLockException` hoặc exception được Spring dịch sang `OptimisticLockingFailureException`.

### 3.1. Entity có version

`src/main/java/com/example/stock/StockItem.java`:

```java
package com.example.stock;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "stock_items")
public class StockItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private int available;

    @Version
    @Column(nullable = false)
    private long version;

    protected StockItem() {
        // JPA cần constructor không tham số.
    }

    public StockItem(int available) {
        if (available < 0) {
            throw new IllegalArgumentException("Available quantity cannot be negative");
        }
        this.available = available;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (available < quantity) {
            throw new IllegalStateException("Insufficient stock");
        }
        available -= quantity;
    }

    public Long getId() { return id; }
    public int getAvailable() { return available; }
    public long getVersion() { return version; }
}
```

JPA quản lý version khi Entity được cập nhật theo dirty checking hoặc merge. Không tự gán version trong domain method; provider chịu trách nhiệm tăng version.

### 3.2. Repository và Service

`src/main/java/com/example/stock/StockItemRepository.java`:

```java
package com.example.stock;

import java.util.Optional;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface StockItemRepository extends JpaRepository<StockItem, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select s from StockItem s where s.id = :id")
    Optional<StockItem> findByIdForUpdate(@Param("id") Long id);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
           update StockItem s
           set s.available = :newAvailable,
               s.version = s.version + 1
           where s.id = :id
             and s.version = :expectedVersion
           """)
    int updateIfVersionMatches(
            @Param("id") Long id,
            @Param("expectedVersion") long expectedVersion,
            @Param("newAvailable") int newAvailable);
}
```

`src/main/java/com/example/stock/StockService.java`:

```java
package com.example.stock;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StockService {
    private final StockItemRepository repository;

    public StockService(StockItemRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserveOptimistically(Long id, int quantity) {
        StockItem item = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Stock item not found"));
        item.reserve(quantity);
    }

    @Transactional
    public void reservePessimistically(Long id, int quantity) {
        StockItem item = repository.findByIdForUpdate(id)
                .orElseThrow(() -> new IllegalArgumentException("Stock item not found"));
        item.reserve(quantity);
    }

    @Transactional
    public void reserveThenFail(Long id, int quantity) {
        StockItem item = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Stock item not found"));
        item.reserve(quantity);
        repository.flush();
        throw new IllegalStateException("Simulated downstream failure");
    }

    @Transactional
    public void saveDetached(StockItem staleItem) {
        repository.saveAndFlush(staleItem);
    }

    @Transactional
    public void setAvailableIfVersionMatches(Long id, long expectedVersion, int newAvailable) {
        int affected = repository.updateIfVersionMatches(id, expectedVersion, newAvailable);
        if (affected != 1) {
            throw new IllegalStateException("Stock changed or no longer exists");
        }
    }
}
```

`reserveOptimistically` dùng Entity có `@Version`; nếu một transaction khác đã cập nhật cùng version, một lần flush/commit sẽ thất bại. `reservePessimistically` tải dòng bằng khóa ghi và giữ khóa đến khi transaction commit hoặc rollback. `reserveThenFail` cố ý ném unchecked exception sau khi flush để kiểm tra rollback.

## 4. Pessimistic locking với @Lock

Pessimistic locking yêu cầu database khóa dòng trong lúc transaction đang xử lý. Spring Data JPA cho phép gắn `@Lock` lên phương thức query Repository:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select s from StockItem s where s.id = :id")
Optional<StockItem> findByIdForUpdate(@Param("id") Long id);
```

`PESSIMISTIC_WRITE` thường được triển khai bằng câu SQL tương đương `SELECT ... FOR UPDATE`. Transaction khác muốn lấy khóa xung đột trên cùng dòng sẽ phải chờ, hoặc nhận lock timeout/deadlock exception tùy database và cấu hình.

Các lock mode thường gặp:

| Lock mode | Ý nghĩa khái quát |
| --- | --- |
| `PESSIMISTIC_READ` | Yêu cầu khóa đọc để ngăn transaction khác sửa dữ liệu theo semantics database/provider. |
| `PESSIMISTIC_WRITE` | Yêu cầu khóa ghi, thường dùng cho thao tác đọc rồi cập nhật. |
| `PESSIMISTIC_FORCE_INCREMENT` | Khóa pessimistic và yêu cầu tăng version của Entity versioned. |

Khóa pessimistic phải được lấy trong transaction đang hoạt động. Không gọi Repository lấy khóa rồi kết thúc transaction trước khi thực hiện cập nhật; khi transaction kết thúc, khóa được giải phóng.

Không giữ khóa trong lúc gọi dịch vụ ngoài, chờ người dùng hoặc thực hiện công việc kéo dài. Transaction càng dài thì lock contention và nguy cơ deadlock càng cao.

### 4.1. Thiết lập timeout

JPA cho phép yêu cầu lock timeout qua query hint, nhưng khả năng hỗ trợ và cách diễn giải phụ thuộc provider/database:

```java
import jakarta.persistence.QueryHint;
import jakarta.persistence.QueryHints;

@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(@QueryHint(name = "jakarta.persistence.lock.timeout", value = "3000"))
@Query("select s from StockItem s where s.id = :id")
Optional<StockItem> findByIdForUpdate(@Param("id") Long id);
```

Ví dụ trên dùng hint Jakarta Persistence với giá trị millisecond. Không giả định mọi database đều áp dụng chính xác cùng một timeout; kiểm tra tài liệu Hibernate và database mục tiêu, rồi viết test cho lock timeout/deadlock nếu đó là hợp đồng của ứng dụng.

## 5. Cấu hình integration test

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data JPA, Hibernate và H2. `@DataJpaTest` cấu hình Repository, EntityManager và transaction manager cho test slice.

`src/test/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:stock-lock-db;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=10000
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
```

Test concurrency cần nhiều transaction độc lập. `@DataJpaTest` mặc định chạy mỗi test trong một transaction do test framework quản lý; vì vậy ví dụ sẽ tắt transaction bao ngoài bằng `@Transactional(propagation = NOT_SUPPORTED)` và tạo transaction tường minh bằng `TransactionTemplate`.

Điều này giúp mỗi thread có persistence context riêng và transaction thật sự commit/rollback trước khi test đọc kết quả.

## 6. Kiểm thử optimistic conflict bằng hai transaction đồng thời

Test sau dùng hai thread. Cả hai transaction đọc cùng một version trước khi được cho phép cập nhật. Sau đó cả hai cùng giảm tồn kho một đơn vị.

Vì cả hai đọc cùng version, chỉ một transaction được commit. Transaction còn lại phải nhận optimistic locking conflict. Số lượng cuối cùng là 9, không phải 8; thao tác thất bại phải được retry nếu nghiệp vụ muốn áp dụng cả hai yêu cầu.

`src/test/java/com/example/stock/StockConcurrencyTest.java`:

```java
package com.example.stock;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import jakarta.persistence.OptimisticLockException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@DataJpaTest
@Import(StockService.class)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class StockConcurrencyTest {
    @Autowired
    private StockItemRepository repository;

    @Autowired
    private StockService service;

    @Autowired
    private PlatformTransactionManager transactionManager;

    private TransactionTemplate transactions;

    @BeforeEach
    void setUp() {
        transactions = new TransactionTemplate(transactionManager);
        transactions.executeWithoutResult(status -> repository.deleteAllInBatch());
    }

    private Long createStock(int available) {
        return transactions.execute(status ->
                repository.saveAndFlush(new StockItem(available)).getId());
    }

    private int readAvailable(Long id) {
        return transactions.execute(status -> repository.findById(id)
                .orElseThrow().getAvailable());
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for concurrent test");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Concurrent test interrupted", ex);
        }
    }

    private static boolean hasCause(Throwable error, Class<? extends Throwable> type) {
        for (Throwable current = error; current != null; current = current.getCause()) {
            if (type.isInstance(current)) {
                return true;
            }
        }
        return false;
    }

    @Test
    void onlyOneConcurrentOptimisticUpdateCanCommitFromTheSameVersion() throws Exception {
        Long id = createStock(10);
        CountDownLatch bothLoaded = new CountDownLatch(2);
        CountDownLatch allowUpdates = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        java.util.concurrent.Callable<String> update = () -> {
            try {
                transactions.execute(status -> {
                    StockItem item = repository.findById(id).orElseThrow();
                    bothLoaded.countDown();
                    await(allowUpdates);
                    item.reserve(1);
                    repository.flush();
                    return null;
                });
                return "COMMITTED";
            } catch (RuntimeException ex) {
                if (hasCause(ex, OptimisticLockingFailureException.class)
                        || hasCause(ex, OptimisticLockException.class)) {
                    return "CONFLICT";
                }
                throw ex;
            }
        };

        List<String> outcomes;
        try {
            Future<String> first = pool.submit(update);
            Future<String> second = pool.submit(update);
            assertThat(bothLoaded.await(10, TimeUnit.SECONDS)).isTrue();
            allowUpdates.countDown();
            outcomes = List.of(first.get(10, TimeUnit.SECONDS),
                    second.get(10, TimeUnit.SECONDS));
        } finally {
            allowUpdates.countDown();
            pool.shutdownNow();
        }

        assertThat(outcomes).containsExactlyInAnyOrder("COMMITTED", "CONFLICT");
        assertThat(readAvailable(id)).isEqualTo(9);
    }

    @Test
    void staleDetachedEntityCannotOverwriteANewerVersion() {
        Long id = createStock(10);
        StockItem stale = transactions.execute(status -> repository.findById(id).orElseThrow());

        service.reserveOptimistically(id, 2);

        assertThatThrownBy(() -> service.saveDetached(stale))
                .satisfies(error -> assertThat(
                        hasCause(error, OptimisticLockingFailureException.class)
                                || hasCause(error, OptimisticLockException.class)).isTrue());

        assertThat(readAvailable(id)).isEqualTo(8);
    }

    @Test
    void runtimeExceptionRollsBackTheStockChange() {
        Long id = createStock(10);

        assertThatThrownBy(() -> service.reserveThenFail(id, 3))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("Simulated downstream failure");

        assertThat(readAvailable(id)).isEqualTo(10);
    }
}
```

Test đầu dùng barrier để bảo đảm cả hai transaction đã đọc cùng version trước khi cập nhật. `flush()` làm lỗi optimistic locking xuất hiện ngay trong callback nếu có xung đột; commit vẫn được quản lý bởi `TransactionTemplate`. Test thứ hai giữ một Entity detached có version cũ, cập nhật dữ liệu bằng transaction khác rồi thử merge snapshot cũ. Test rollback đọc lại số lượng trong transaction mới để chứng minh thay đổi đã bị hủy.

Chạy test từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi là `BUILD SUCCESS`. Các test xác nhận một transaction thắng và một transaction conflict, Entity stale không ghi đè version mới, và runtime exception rollback thay đổi. Đây là kết quả kỳ vọng của ví dụ; chưa có log build thực tế.

## 7. Kiểm thử pessimistic lock

Với `PESSIMISTIC_WRITE`, transaction thứ nhất giữ khóa trên một dòng. Transaction thứ hai yêu cầu khóa cùng dòng và phải chờ cho đến khi transaction thứ nhất kết thúc.

Thêm test sau vào `StockConcurrencyTest`:

```java
@Test
void pessimisticWriteLockMakesAnotherTransactionWait() throws Exception {
    Long id = createStock(10);
    CountDownLatch firstHasLock = new CountDownLatch(1);
    CountDownLatch releaseFirst = new CountDownLatch(1);
    CountDownLatch secondIsStarting = new CountDownLatch(1);
    ExecutorService pool = Executors.newFixedThreadPool(2);

    try {
        Future<?> first = pool.submit(() -> transactions.executeWithoutResult(status -> {
            StockItem item = repository.findByIdForUpdate(id).orElseThrow();
            firstHasLock.countDown();
            await(releaseFirst);
            item.reserve(1);
        }));

        assertThat(firstHasLock.await(10, TimeUnit.SECONDS)).isTrue();

        Future<?> second = pool.submit(() -> transactions.executeWithoutResult(status -> {
            secondIsStarting.countDown();
            StockItem item = repository.findByIdForUpdate(id).orElseThrow();
            item.reserve(1);
        }));

        assertThat(secondIsStarting.await(10, TimeUnit.SECONDS)).isTrue();
        assertThatThrownBy(() -> second.get(250, TimeUnit.MILLISECONDS))
                .isInstanceOf(java.util.concurrent.TimeoutException.class);

        releaseFirst.countDown();
        first.get(10, TimeUnit.SECONDS);
        second.get(10, TimeUnit.SECONDS);
    } finally {
        releaseFirst.countDown();
        pool.shutdownNow();
    }

    assertThat(readAvailable(id)).isEqualTo(8);
}
```

Test kiểm tra transaction thứ hai chưa hoàn tất trong lúc transaction đầu giữ khóa. Sau khi nhả khóa, cả hai transaction lần lượt giảm tồn kho và kết quả cuối cùng là 8.

Timeout 250 ms chỉ là khoảng quan sát để xác nhận transaction thứ hai đang chờ trong test này, không phải cấu hình lock timeout của ứng dụng. Lock timing phụ thuộc database, driver và môi trường CI. Với hệ thống production dùng PostgreSQL, MySQL hoặc SQL Server, nên chạy cùng test trên engine đó bằng Testcontainers và chọn timeout phù hợp.

## 8. Rollback khi nghiệp vụ thất bại

Spring transaction mặc định rollback khi method transactional ném `RuntimeException` hoặc `Error`. Checked exception không tự động rollback theo mặc định; nếu cần, khai báo `rollbackFor`.

Service `reserveThenFail` ở trên đã:

1. Đọc StockItem trong transaction.
2. Giảm số lượng bằng domain method.
3. Flush để gửi UPDATE xuống database.
4. Ném `IllegalStateException` trước khi transaction commit.

Test cần gọi Service qua Spring proxy để interceptor áp dụng `@Transactional`. Sau khi exception thoát khỏi method, transaction phải rollback.

### 8.1. Rollback với checked exception

Nếu method ném checked exception và nghiệp vụ vẫn yêu cầu rollback, khai báo rõ:

```java
@Transactional(rollbackFor = PaymentRejectedException.class)
public void reserveAndCharge(Long id, int quantity) throws PaymentRejectedException {
    StockItem item = repository.findById(id).orElseThrow();
    item.reserve(quantity);
    paymentGateway.charge(quantity);
}
```

Ví dụ trên giả định `PaymentRejectedException` là checked exception. Nếu không cấu hình `rollbackFor`, Spring mặc định có thể commit thay đổi khi checked exception thoát khỏi method. Cũng cần chú ý exception bị bắt rồi không ném lại: transaction interceptor không nhìn thấy exception đó, trừ khi code chủ động đánh dấu rollback-only.

### 8.2. Rollback khi affected count không đúng

Với bulk update, Service có thể kiểm tra số dòng tác động rồi ném runtime exception nếu số lượng không đạt yêu cầu:

```java
@Transactional
public void setAvailableExactly(Long id, long expectedVersion, int newAvailable) {
    int affected = repository.updateIfVersionMatches(id, expectedVersion, newAvailable);
    if (affected != 1) {
        throw new IllegalStateException("Unexpected affected row count: " + affected);
    }
}
```

Đặt update và kiểm tra count trong cùng transaction. Khi exception thoát khỏi Service, transaction rollback theo quy tắc rollback của Spring. Không bắt exception rồi tiếp tục commit nếu nghiệp vụ yêu cầu all-or-nothing.

## 9. Tại sao test transaction cần thiết kế riêng?

`@DataJpaTest` mặc định mở transaction cho test method và rollback khi test kết thúc. Điều này thuận tiện cho test Repository đơn giản, nhưng có thể che khuất cách Service quản lý transaction hoặc khiến nhiều thao tác trong test dùng chung một persistence context.

Đối với test concurrency/rollback:

- Dùng `@Transactional(propagation = NOT_SUPPORTED)` để tắt transaction bao ngoài do test framework tạo.
- Dùng `TransactionTemplate` để mở transaction riêng cho từng thao tác.
- Chạy hai transaction trên hai thread để chúng có EntityManager/persistence context riêng.
- Chờ cả hai transaction đọc dữ liệu trước khi cho phép ghi để tái hiện xung đột một cách có kiểm soát.
- Đọc kết quả trong transaction mới sau khi các transaction cạnh tranh đã hoàn tất.

Không dùng cùng một EntityManager hoặc Entity object managed từ thread này sang thread khác. EntityManager không thread-safe; mỗi transaction/thread cần persistence context riêng.

## 10. Kiểm thử deadlock và lock timeout

Deadlock xảy ra khi các transaction giữ khóa theo thứ tự khác nhau và chờ tài nguyên của nhau. Ví dụ:

- Transaction A khóa dòng 1 rồi chờ dòng 2.
- Transaction B khóa dòng 2 rồi chờ dòng 1.

Database phát hiện chu trình chờ và hủy một transaction. Ứng dụng cần xử lý exception phù hợp và có thể retry toàn bộ transaction nếu thao tác có tính idempotent.

Khi kiểm thử deadlock/timeout:

1. Tạo ít nhất hai transaction độc lập.
2. Dùng latch/barrier để điều phối thứ tự khóa.
3. Đặt lock timeout ngắn ở môi trường test nếu database hỗ trợ.
4. Xác nhận một transaction thất bại bằng exception phù hợp của provider/database.
5. Kiểm tra transaction bị hủy không để lại dữ liệu ghi dở.
6. Chạy test trên database production hoặc Testcontainers; H2 không đảm bảo tái hiện giống mọi engine.

Không bắt buộc viết test deadlock cho mọi Repository. Chỉ thêm khi ứng dụng thực sự dùng nhiều pessimistic lock hoặc có rủi ro khóa theo nhiều thứ tự.

## 11. So sánh optimistic và pessimistic locking

| Tiêu chí | Optimistic (`@Version`) | Pessimistic (`@Lock`) |
| --- | --- | --- |
| Cách bảo vệ | Kiểm tra version khi update/delete. | Lấy khóa database trước hoặc trong lúc đọc để ngăn cập nhật xung đột. |
| Phù hợp | Xung đột ít, transaction ngắn, có thể retry. | Xung đột thường xuyên hoặc cần tuần tự hóa thao tác trên một dòng. |
| Tác động khi cạnh tranh | Một transaction có thể thất bại khi flush/commit. | Transaction khác có thể phải chờ, timeout hoặc deadlock. |
| Tài nguyên | Không giữ khóa ghi trong suốt thời gian đọc thông thường. | Giữ khóa đến commit/rollback. |
| Kiểm thử | Hai transaction đọc cùng version rồi cùng ghi; xác nhận một transaction conflict. | Transaction A giữ lock, transaction B yêu cầu cùng lock và phải chờ. |

Không có chiến lược tốt nhất cho mọi hệ thống. Optimistic locking thường là điểm bắt đầu hợp lý cho dữ liệu ít xung đột; pessimistic locking phù hợp khi cần kiểm soát truy cập đồng thời chặt chẽ và thời gian giữ khóa ngắn.

## 12. Lưu ý về bulk update và @Version

JPQL bulk UPDATE/DELETE chạy trực tiếp trên database, bỏ qua dirty checking và optimistic locking tự động của Entity. Nếu bulk query thay đổi Entity có `@Version`, cần tăng version tường minh và thêm điều kiện version mong đợi vào `WHERE` khi nghiệp vụ cần compare-and-set.

Ví dụ phương thức Repository ở phần trước dùng:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
       update StockItem s
       set s.available = :newAvailable,
           s.version = s.version + 1
       where s.id = :id
         and s.version = :expectedVersion
       """)
int updateIfVersionMatches(
        @Param("id") Long id,
        @Param("expectedVersion") long expectedVersion,
        @Param("newAvailable") int newAvailable);
```

Nếu count bằng 0, version không khớp hoặc dòng không tồn tại. Bulk query không tự ném optimistic locking exception chỉ vì version không khớp; Service cần kiểm tra affected count và xử lý conflict.

## 13. Kiểm thử trên database production

H2 hữu ích cho kiểm thử JPA cơ bản, nhưng locking, isolation, deadlock, timeout, generated SQL và kiểu dữ liệu có thể khác database production.

Nếu ứng dụng chạy PostgreSQL, MySQL hoặc SQL Server, nên có một nhóm integration test chạy trên đúng engine bằng Testcontainers:

```java
@Testcontainers
@SpringBootTest
class StockDatabaseConcurrencyIT {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Cấu hình datasource từ container và chạy cùng kịch bản transaction.
}
```

Đoạn trên chỉ minh họa cách khởi tạo container; cấu hình datasource động, dependency Testcontainers và migration phải được bổ sung theo build của dự án. Không coi test H2 là bằng chứng đầy đủ cho hành vi lock của PostgreSQL/MySQL.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Hai request cùng cập nhật nhưng không có conflict | Entity thiếu `@Version` hoặc thao tác không đi qua Entity versioned. | Thêm `@Version` và kiểm thử hai transaction độc lập. |
| Optimistic exception chỉ xuất hiện khi commit | Provider trì hoãn SQL đến flush/commit. | Gọi `flush()` trong test khi muốn quan sát lỗi tại vị trí cụ thể; vẫn xác nhận transaction rollback. |
| Test concurrency chỉ có một persistence context | Test chạy trong một transaction hoặc dùng chung EntityManager. | Tắt transaction test bao ngoài và tạo transaction độc lập trên từng thread. |
| Pessimistic lock không giữ đến lúc cập nhật | Transaction kết thúc trước khi thao tác ghi hoàn tất. | Đặt đọc khóa và cập nhật trong cùng `@Transactional` method. |
| Test lock chập chờn trên CI | Dùng delay cố định, không điều phối thứ tự transaction. | Dùng `CountDownLatch`/barrier, timeout có giới hạn và kiểm thử trên DB mục tiêu. |
| Rollback test vẫn thấy giá trị cũ trong object | Đọc object managed cũ trong persistence context. | Clear/refresh hoặc đọc lại trong transaction mới. |
| Runtime exception không rollback | Exception bị bắt và nuốt, hoặc method không chạy qua Spring transaction proxy. | Để exception thoát khỏi transactional method hoặc đánh dấu rollback-only. |
| Checked exception vẫn commit | Spring mặc định rollback runtime exception và Error, không phải mọi checked exception. | Khai báo `rollbackFor` nếu nghiệp vụ yêu cầu. |
| Test deadlock không tái hiện trên H2 | Locking/isolation khác database production. | Chạy test trên đúng engine bằng Testcontainers. |
| Một transaction bị conflict nhưng dữ liệu vẫn thay đổi | Test không kiểm tra trạng thái sau khi transaction kết thúc hoặc đã bắt exception trong transaction. | Xác nhận rollback và đọc lại dữ liệu bằng transaction mới. |

## 15. Quy trình viết test đáng tin cậy

1. Seed dữ liệu trong transaction riêng và commit trước khi bắt đầu kịch bản.
2. Tạo các transaction/persistence context độc lập cho từng actor.
3. Dùng latch hoặc barrier để kiểm soát thời điểm đọc, lấy khóa và cập nhật.
4. Flush khi cần buộc provider gửi SQL và bộc lộ conflict ngay trong test.
5. Thu thập outcome của từng transaction: commit, optimistic conflict, lock timeout hoặc deadlock.
6. Chờ mọi transaction hoàn tất trước khi kiểm tra dữ liệu.
7. Đọc dữ liệu bằng transaction mới, không dựa vào Entity object cũ.
8. Kiểm tra cả kết quả nghiệp vụ lẫn version/quantity trong database.
9. Xác nhận rollback không để lại thay đổi đã commit.
10. Chạy lại kịch bản khóa trên database production bằng Testcontainers nếu hành vi database-specific ảnh hưởng nghiệp vụ.

## 16. Checklist hoàn thành

- [ ] Giải thích được lost update và lý do cần kiểm thử concurrency.
- [ ] Khai báo `@Version` trên Entity.
- [ ] Dùng hai transaction độc lập để kiểm tra optimistic locking.
- [ ] Xác nhận chỉ một transaction cùng version có thể commit.
- [ ] Khai báo `@Lock(LockModeType.PESSIMISTIC_WRITE)` trên Repository.
- [ ] Kiểm tra transaction thứ hai phải chờ khi transaction thứ nhất giữ khóa.
- [ ] Hiểu lock được giữ đến commit/rollback.
- [ ] Dùng `@Transactional` và runtime exception để kiểm tra rollback.
- [ ] Dùng `rollbackFor` khi checked exception cần rollback.
- [ ] Đọc lại dữ liệu bằng transaction mới sau commit/rollback.
- [ ] Tắt transaction bao ngoài của `@DataJpaTest` khi cần kiểm soát transaction độc lập.
- [ ] Phân biệt hành vi H2 với database production và bổ sung Testcontainers khi cần.

Khi hoàn thành, bạn có thể kiểm chứng bằng integration test rằng optimistic locking phát hiện cập nhật cạnh tranh, pessimistic locking tuần tự hóa thao tác trên cùng dòng và transaction rollback giữ dữ liệu nhất quán khi nghiệp vụ thất bại.