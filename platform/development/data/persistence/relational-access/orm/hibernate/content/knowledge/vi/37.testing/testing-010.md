# Kiểm thử khóa lạc quan, khóa bi quan và giao dịch đồng thời

Khi nhiều request cùng đọc và sửa một bản ghi, kết quả cuối cùng phụ thuộc vào cách ứng dụng và database phối hợp các giao dịch. Hai người cùng sửa một đơn hàng, hai request cùng trừ tồn kho hoặc hai worker cùng nhận một công việc đều có thể tạo ra xung đột. Nếu không kiểm soát, một lần ghi có thể ghi đè kết quả của lần ghi khác, hoặc một invariant nghiệp vụ có thể bị phá vỡ dù từng transaction riêng lẻ đều chạy thành công.

Hibernate và Jakarta Persistence hỗ trợ hai nhóm cơ chế thường dùng:

- **Khóa lạc quan (optimistic locking):** cho phép nhiều transaction cùng đọc và làm việc độc lập; khi ghi, kiểm tra dữ liệu có bị transaction khác thay đổi từ lúc đọc hay không. Cách phổ biến là dùng thuộc tính `@Version`.
- **Khóa bi quan (pessimistic locking):** yêu cầu database khóa row hoặc tập rows trong transaction. Transaction khác cần lock xung đột phải chờ hoặc thất bại theo timeout/deadlock policy.

Kiểm thử hai cơ chế này không thể chỉ gọi repository hai lần tuần tự. Cần tạo **các transaction thực sự độc lập**, mỗi transaction có Persistence Context/EntityManager riêng, rồi điều phối thời điểm đọc, khóa, ghi và commit. Nếu test không tái hiện được cạnh tranh thực tế, nó có thể xanh dù production vẫn gặp lost update.

Bài học thuộc chương **Kiểm thử** của module *Data Persistence Relational Access ORM Hibernate*. Các ví dụ sử dụng Hibernate ORM 6.x, Jakarta Persistence, JUnit 5 và Spring transaction infrastructure. Lock timeout, SQL locking và isolation behavior cần được kiểm trên DBMS/driver thực tế vì có khác biệt giữa các hệ quản trị.

## 1. Vấn đề cần kiểm thử

Giả sử bảng accounts:

~~~text
accounts
id | balance | version
7  | 1000    | 0
~~~

Hai transaction cùng đọc balance 1000:

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant DB as Database
    participant B as Transaction B
    A->>DB: Read balance 1000
    B->>DB: Read balance 1000
    A->>DB: Write balance 900
    DB-->>A: Commit
    B->>DB: Write value calculated from old state
    DB-->>B: Commit or conflict
~~~

Nếu B ghi giá trị tính từ snapshot cũ mà không phát hiện A đã commit, kết quả có thể là **lost update**. Hai thao tác rút 100 phải tạo balance 800; nếu cả hai cùng tính từ 1000 rồi ghi 900, một lần rút đã bị mất.

Một test concurrency cần trả lời:

1. Hai transaction có thực sự đọc cùng version/state không?
2. Transaction nào được phép commit?
3. Transaction còn lại phải chờ, thất bại hay retry?
4. Dữ liệu cuối cùng có giữ invariant không?
5. Transaction lỗi có rollback sạch không?
6. Kết quả có tương ứng DBMS production không?

## 2. Phân biệt isolation level và locking

| Cơ chế | Vai trò |
| --- | --- |
| Transaction isolation | Quy định transaction quan sát thay đổi của transaction khác ở mức nào |
| Optimistic locking | Phát hiện entity đã đổi so với version đã đọc |
| Pessimistic locking | Giữ database lock trên tài nguyên trong transaction |
| Database constraints | Chặn state vi phạm invariant dù nhiều writers cạnh tranh |
| Atomic SQL update | Gộp điều kiện và mutation trong một statement |

Các isolation levels phổ biến là READ UNCOMMITTED, READ COMMITTED, REPEATABLE READ và SERIALIZABLE. Chi tiết anomaly được phép khác nhau theo DBMS. Isolation level cao không tự động bảo vệ mọi business invariant.

### 2.1. Các anomaly cần hiểu

- **Lost update:** hai transactions ghi dựa trên cùng state cũ và một write ghi đè write kia.
- **Non-repeatable read:** cùng transaction đọc một row hai lần và nhận hai giá trị khác nhau sau khi transaction khác commit.
- **Phantom rows:** một query theo predicate được chạy lại và thấy rows mới/xóa rows do transaction khác thay đổi.
- **Write skew:** hai transactions đọc nhiều rows rồi sửa các rows khác nhau, nhưng kết quả kết hợp vi phạm invariant chung. Version trên từng row có thể không phát hiện vì không row nào bị cả hai cùng sửa.

Với write skew, có thể cần khóa aggregate/root row, database constraint hoặc SERIALIZABLE isolation, chứ không chỉ thêm `@Version` vào mọi entity.

## 3. Optimistic locking với @Version

Jakarta Persistence hỗ trợ version attribute để phát hiện xung đột khi update/delete entity.

~~~java
@Entity
@Table(name = "products")
public class Product {

    @Id
    private Long id;

    @Column(nullable = false)
    private BigDecimal price;

    @Version
    private long version;

    protected Product() {}

    public BigDecimal getPrice() {
        return price;
    }

    public long getVersion() {
        return version;
    }

    public void changePrice(BigDecimal newPrice) {
        this.price = newPrice;
    }
}
~~~

Hibernate quản lý version khi entity được ghi. SQL có hình dạng khái niệm:

~~~sql
update products
set price = :newPrice,
    version = :nextVersion
where id = :id
  and version = :versionReadEarlier;
~~~

Nếu row đã có version mới, predicate không match. Hibernate nhận ra không có row được cập nhật như mong đợi và báo optimistic locking conflict, thường qua `OptimisticLockException` hoặc exception được Spring dịch tương ứng.

### 3.1. Version attribute

JPA hỗ trợ một số kiểu version numeric và temporal theo specification/provider. Numeric version thường dễ kiểm thử và ít phụ thuộc độ chính xác timestamp của DB/driver.

Không tự tăng version bằng setter nghiệp vụ. Hibernate quản lý version của entity versioned; ghi đè thủ công có thể làm sai semantics.

### 3.2. Exception xuất hiện ở đâu?

Conflict có thể được phát hiện tại:

- `EntityManager.merge()` hoặc quá trình đồng bộ detached state.
- `flush()` khi Hibernate thực hiện UPDATE/DELETE.
- `commit()` vì commit có thể kích hoạt flush.

Một setter chỉ thay Java state; SQL thường chưa chạy cho đến flush/commit. Vì vậy test không nên chỉ assert exception ngay tại dòng gọi setter.

### 3.3. Detached entity và merge

`merge(detached)` copy state của detached object vào một managed instance và trả về instance managed ấy. Không tiếp tục dùng detached object như thể nó đã được attach.

Nếu detached instance mang version cũ, conflict có thể được phát hiện tại merge/flush/commit. Test phải tạo hai snapshots trong các persistence contexts riêng để tái hiện tình huống này.

## 4. Kiểm thử optimistic conflict với hai EntityManagers

Một test đáng tin phải dùng hai EntityManagers độc lập và hai transactions độc lập. Không chia sẻ một EntityManager giữa threads vì EntityManager/Hibernate Session không thread-safe.

Giả sử Product 42 ban đầu có price 100 và version 0:

~~~text
Transaction A đọc price=100, version=0
Transaction B đọc price=100, version=0
Transaction A đổi price=120 và commit
Transaction B đổi price=110 rồi flush/commit
Kết quả mong đợi: B nhận optimistic conflict
Database cuối cùng: price=120
~~~

### 4.1. Điều phối bằng CountDownLatch

Ví dụ JUnit 5 dưới đây minh họa cách tạo race có kiểm soát. Fixture Product 42 phải được commit trước khi test chạy. Mỗi worker mở EntityManager riêng:

~~~java
@Test
void staleWriterMustFailWithOptimisticLocking() throws Exception {
    CountDownLatch staleReadCompleted = new CountDownLatch(1);
    CountDownLatch winnerCommitted = new CountDownLatch(1);

    ExecutorService pool = Executors.newSingleThreadExecutor();

    try {
        Future<Boolean> staleWriter = pool.submit(() -> {
            try (EntityManager em =
                    entityManagerFactory.createEntityManager()) {

                EntityTransaction tx = em.getTransaction();
                tx.begin();

                try {
                    Product product = em.find(Product.class, 42L);

                    assertEquals(
                            new BigDecimal("100.00"),
                            product.getPrice()
                    );

                    staleReadCompleted.countDown();
                    await(winnerCommitted);

                    product.changePrice(
                            new BigDecimal("110.00")
                    );

                    em.flush();
                    tx.commit();

                    return false;
                } catch (RuntimeException ex) {
                    if (tx.isActive()) {
                        tx.rollback();
                    }
                    return containsOptimisticLockFailure(ex);
                }
            }
        });

        assertTrue(
                staleReadCompleted.await(10, TimeUnit.SECONDS)
        );

        try (EntityManager em =
                entityManagerFactory.createEntityManager()) {

            EntityTransaction tx = em.getTransaction();
            tx.begin();

            try {
                Product product = em.find(Product.class, 42L);
                product.changePrice(new BigDecimal("120.00"));
                tx.commit();
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw ex;
            }
        } finally {
            winnerCommitted.countDown();
        }

        assertTrue(staleWriter.get(10, TimeUnit.SECONDS));

        try (EntityManager verify =
                entityManagerFactory.createEntityManager()) {
            Product current = verify.find(Product.class, 42L);

            assertEquals(
                    new BigDecimal("120.00"),
                    current.getPrice()
            );
            assertEquals(1L, current.getVersion());
        }
    } finally {
        pool.shutdownNow();
    }
}
~~~

Các helper `await` và `containsOptimisticLockFailure` cần được triển khai trong test fixture. Helper nhận diện exception nên duyệt cause chain để tìm `OptimisticLockException` hoặc exception provider/Spring tương ứng; không coi mọi RuntimeException là conflict.

Ví dụ helper chờ có timeout:

~~~java
private static void await(CountDownLatch latch) {
    try {
        if (!latch.await(10, TimeUnit.SECONDS)) {
            throw new AssertionError(
                    "Timed out waiting for transaction"
            );
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(ex);
    }
}
~~~

### 4.2. Vì sao test này có ý nghĩa?

- Writer cũ đọc xong trước khi writer mới commit.
- Writer mới commit trên EntityManager khác.
- Writer cũ chỉ tiếp tục sau commit của writer mới.
- Hai transactions không chia sẻ Persistence Context.
- Conflict được quan sát tại flush/commit boundary, nơi version check thực sự xảy ra.
- Một EntityManager mới xác minh database state cuối cùng.

Fixture phải được commit trước khi hai workers bắt đầu. Nếu test dùng Spring transaction mặc định và rollback cuối test, fixture chưa commit có thể không nhìn thấy từ connection/thread khác.

### 4.3. Tránh test giả

- Không dùng cùng EntityManager cho hai “transactions”.
- Không chạy hai updates tuần tự trong cùng Persistence Context.
- Không bắt mọi RuntimeException rồi coi là optimistic conflict.
- Không chỉ assert exception mà bỏ qua database state cuối.
- Không kiểm kết quả qua object còn nằm trong L1 cache cũ.

## 5. Kiểm thử optimistic locking với Spring TransactionTemplate

Trong Spring, `TransactionTemplate` có thể tạo transaction tường minh cho từng task. Một shared EntityManager proxy được inject qua `@PersistenceContext` có thể resolve target EntityManager gắn với transaction/thread hiện hành khi transaction manager được cấu hình đúng.

Khung ví dụ:

~~~java
TransactionTemplate tx =
        new TransactionTemplate(transactionManager);

Future<?> writer = executor.submit(() ->
    tx.execute(status -> {
        Product product =
                entityManager.find(Product.class, 42L);

        // Đọc, điều phối barrier và thay đổi entity.
        product.changePrice(new BigDecimal("120.00"));
        entityManager.flush();

        return null;
    })
);
~~~

Đây chỉ là khung; test đầy đủ phải có hai task, barriers và exception assertions như phần trước. Không truyền raw EntityManager đang được mở ở thread test sang worker. Với test concurrency phức tạp, dùng `EntityManagerFactory.createEntityManager()` trong từng task giúp lifecycle rõ hơn.

## 6. Kiểm thử lost update bằng bộ đếm

~~~java
@Entity
public class DownloadCounter {

    @Id
    private Long id;

    private long count;

    @Version
    private long version;

    protected DownloadCounter() {}

    public void increment() {
        count++;
    }

    public long getCount() {
        return count;
    }
}
~~~

Giả sử count ban đầu là 0. Hai transactions cùng đọc 0 và cùng increment.

Không có optimistic locking, cả hai có thể ghi 1; một increment bị mất. Có `@Version`, một transaction commit và transaction stale nhận conflict.

Assertions nên xác nhận:

- Có ít nhất một transaction thành công.
- Writer stale nhận đúng optimistic failure.
- Count cuối là 1 nếu không retry.
- Version tăng theo số update được commit.
- Không có write nào âm thầm ghi đè state của transaction khác.

### 6.1. Retry có thể làm count cuối cùng bằng 2

Nếu nghiệp vụ cho phép retry, transaction thất bại phải **đọc lại state mới và tính lại command** trong transaction mới. Sau retry thành công, count có thể bằng 2.

Không retry bằng cách flush lại detached snapshot cũ. Với inventory decrement, retry phải kiểm lại quantity; nếu không còn đủ, kết quả đúng là business rejection. Các side effects như gửi email, chuyển tiền hoặc phát message cần idempotency/outbox để tránh lặp khi transaction được retry.

### 6.2. Chỉ retry lỗi có thể retry

Optimistic conflict, deadlock, connection loss, constraint violation và business validation failure có chính sách khác nhau. Phân loại exception, giới hạn attempts và dùng backoff phù hợp; không retry vô hạn hoặc retry mọi RuntimeException.

## 7. Pessimistic locking với LockModeType

Jakarta Persistence cung cấp các lock modes:

| Lock mode | Ý nghĩa tổng quát |
| --- | --- |
| `PESSIMISTIC_READ` | Yêu cầu lock đọc để ngăn các thay đổi xung đột theo khả năng DB/provider |
| `PESSIMISTIC_WRITE` | Yêu cầu lock ghi, thường dùng khi chuẩn bị sửa row |
| `PESSIMISTIC_FORCE_INCREMENT` | Khóa pessimistic và buộc tăng version trên entity versioned |
| `OPTIMISTIC` | Yêu cầu optimistic version check |
| `OPTIMISTIC_FORCE_INCREMENT` | Optimistic check và buộc tăng version |
| `READ` / `WRITE` | Tên legacy alias cho optimistic lock modes |

Ví dụ khóa Inventory trước khi reserve:

~~~java
@Transactional
public void reserve(Long inventoryId, int quantity) {
    Inventory inventory = entityManager.find(
            Inventory.class,
            inventoryId,
            LockModeType.PESSIMISTIC_WRITE
    );

    if (inventory == null) {
        throw new EntityNotFoundException();
    }

    inventory.reserve(quantity);
}
~~~

Hibernate thường yêu cầu database lock tương ứng, ví dụ SQL có `FOR UPDATE` trên DBMS hỗ trợ. Lock thường được giữ đến transaction commit/rollback.

### 7.1. Khóa qua query

~~~java
List<Inventory> rows = entityManager.createQuery(
        """
        select i from Inventory i
        where i.warehouseId = :warehouseId
        order by i.id
        """,
        Inventory.class
    )
    .setParameter("warehouseId", warehouseId)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .getResultList();
~~~

Nếu query trả nhiều rows, lock footprint có thể lớn. Ordering ổn định giúp các code paths nhất quán hơn về thứ tự xử lý, nhưng database execution plan và lock behavior vẫn phụ thuộc DBMS.

### 7.2. PESSIMISTIC_READ không luôn là shared lock

Một số DBMS/provider không hỗ trợ shared row locks với semantics giống nhau; Hibernate có thể dùng strategy khác hoặc nâng thành lock mạnh hơn. Kiểm tra SQL và behavior thực tế, không suy ra chỉ từ tên enum.

### 7.3. Lock timeout

JPA có hint `jakarta.persistence.lock.timeout`, thường biểu diễn milliseconds:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.lock.timeout",
    1000
);

Inventory inventory = entityManager.find(
        Inventory.class,
        inventoryId,
        LockModeType.PESSIMISTIC_WRITE,
        hints
);
~~~

Database/driver/provider có thể không hỗ trợ hoặc không tuân thủ chính xác hint. Test cần chạy trên DBMS production-equivalent.

JPA có thể báo `LockTimeoutException` hoặc `PessimisticLockException` tùy phạm vi transaction bị rollback. Spring có thể dịch exception thành các kiểu locking failure riêng. Assert theo contract của layer đang test và provider/DBMS mục tiêu.

## 8. Kiểm thử pessimistic locking với hai transaction

Một test cần chứng minh transaction B chỉ tiếp tục sau khi A nhả lock, hoặc B thất bại khi timeout.

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant DB as Database
    participant B as Transaction B
    A->>DB: Acquire PESSIMISTIC_WRITE
    DB-->>A: Lock acquired
    B->>DB: Request conflicting lock
    Note over B,DB: B waits or times out
    A->>DB: Update row
    A->>DB: Commit
    DB-->>B: Lock granted
    B->>DB: Read current row state
    B->>DB: Update row
    B->>DB: Commit
~~~

Khung test sử dụng EntityManagers khác nhau:

~~~java
CountDownLatch firstHasLock = new CountDownLatch(1);
CountDownLatch releaseFirst = new CountDownLatch(1);
CountDownLatch secondStarted = new CountDownLatch(1);

Future<?> first = pool.submit(() -> {
    try (EntityManager em = emf.createEntityManager()) {
        EntityTransaction tx = em.getTransaction();
        tx.begin();

        try {
            Inventory row = em.find(
                    Inventory.class,
                    5L,
                    LockModeType.PESSIMISTIC_WRITE
            );

            firstHasLock.countDown();
            await(releaseFirst);

            row.reserve(1);
            tx.commit();
        } catch (RuntimeException ex) {
            if (tx.isActive()) tx.rollback();
            throw ex;
        }
    }
});

assertTrue(firstHasLock.await(10, TimeUnit.SECONDS));

Future<?> second = pool.submit(() -> {
    try (EntityManager em = emf.createEntityManager()) {
        EntityTransaction tx = em.getTransaction();
        tx.begin();

        try {
            secondStarted.countDown();

            Inventory row = em.find(
                    Inventory.class,
                    5L,
                    LockModeType.PESSIMISTIC_WRITE
            );

            row.reserve(1);
            tx.commit();
        } catch (RuntimeException ex) {
            if (tx.isActive()) tx.rollback();
            throw ex;
        }
    }
});

assertTrue(secondStarted.await(10, TimeUnit.SECONDS));
releaseFirst.countDown();

first.get(10, TimeUnit.SECONDS);
second.get(10, TimeUnit.SECONDS);
~~~

Đây là khung minh họa serialized access. Để chứng minh thời gian chờ một cách đáng tin cậy, dùng DB lock timeout hoặc quan sát lock state trong database. Latch báo “thread B sắp gọi find” chưa chứng minh SQL đã đến DB. Không dùng `Thread.sleep()` tùy ý rồi suy luận B chắc chắn đã chạm lock.

### 8.1. Test lock timeout theo DBMS

Một test cụ thể có thể:

1. Transaction A lấy `PESSIMISTIC_WRITE` và giữ transaction bằng latch.
2. Transaction B dùng connection khác yêu cầu cùng lock với timeout ngắn.
3. B nhận timeout/locking failure theo DBMS.
4. Xác nhận B rollback hoặc transaction state đúng contract.
5. A commit/rollback và nhả lock.
6. Một transaction mới xác minh row state.

Với PostgreSQL, có thể đặt `lock_timeout` trong transaction. Đây là DB-specific; không dùng làm giả định portable cho mọi provider.

### 8.2. Phân biệt chờ lock với chờ connection

Nếu pool chỉ có một connection, worker B có thể đang chờ lấy connection chứ chưa hề yêu cầu row lock. Pool test phải đủ connections cho các transactions cạnh tranh. Khi test timeout, xem thread dump, pool metrics và DB sessions để phân biệt hai loại wait.

## 9. Deadlock khi khóa nhiều rows

~~~mermaid
flowchart TD
    A["A locks row 1"] --> B["A requests row 2"]
    C["B locks row 2"] --> D["B requests row 1"]
    B --> E["A waits for B"]
    D --> F["B waits for A"]
    E --> G["Deadlock cycle"]
    F --> G
    G --> H["Database aborts a transaction"]
~~~

Ví dụ A khóa Account 1 rồi muốn Account 2; B khóa Account 2 rồi muốn Account 1. Mỗi transaction chờ lock do transaction kia giữ. Database phát hiện cycle và hủy một transaction theo chính sách của nó.

### 9.1. Tái hiện deadlock trong test

- A mở transaction, khóa row 1 rồi báo latch.
- B mở transaction, khóa row 2 rồi báo latch.
- Sau khi cả hai đã giữ lock đầu tiên, mở barrier để A yêu cầu row 2 và B yêu cầu row 1.
- Xác nhận ít nhất một transaction nhận deadlock/locking failure.
- Xác nhận transaction bị abort không để partial committed state.
- Dùng bounded timeout và cleanup để test không treo.

Deadlock tests phụ thuộc DBMS và scheduling. Latches giúp tạo trạng thái ban đầu, còn DB lock monitor/timeout giúp xác nhận database thực sự nhận các requests cạnh tranh.

### 9.2. Giảm deadlocks

- Khóa rows theo cùng một thứ tự ổn định ở mọi code path.
- Giữ transaction ngắn.
- Không gọi HTTP/service ngoài khi đang giữ row locks.
- Tạo index phù hợp với predicates.
- Khóa ít rows nhất có thể.
- Đặt timeout và retry policy cho transaction có thể chạy lại an toàn.

## 10. Invariant nhiều rows và write skew

Khóa một entity không nhất thiết bảo vệ invariant liên quan nhiều entities.

Ví dụ quy tắc: phòng họp chỉ được có một booking trùng giờ. Hai transactions có thể cùng query “không có booking xung đột”, rồi insert hai Booking rows khác nhau. Không row nào bị cả hai cùng update, nên `@Version` trên từng Booking có thể không phát hiện.

Các cách bảo vệ có thể gồm:

- Database exclusion/unique constraint nếu DBMS hỗ trợ biểu diễn invariant.
- Khóa một Room/aggregate root row trước khi kiểm tra và insert.
- Serializable isolation.
- Reservation/slot table với unique key.

Ví dụ khóa root row:

~~~java
Room room = em.find(
        Room.class,
        roomId,
        LockModeType.PESSIMISTIC_WRITE
);

bookingService.assertAvailable(room, start, end);
em.persist(new Booking(room, start, end));
~~~

Transaction thứ hai phải chờ khóa Room; sau khi A commit, B đọc lại bookings và thấy conflict. Tất cả code paths tạo Booking phải tuân thủ cùng protocol; writer ngoài có thể bypass, nên DB constraint vẫn là lớp bảo vệ tốt nếu có thể.

## 11. Atomic SQL có thể thay cho read-then-write

Không phải counter/inventory update nào cũng cần lock entity riêng. Một câu UPDATE atomic có thể đủ:

~~~sql
update inventory
set available = available - :quantity
where tenant_id = :tenantId
  and sku = :sku
  and available >= :quantity;
~~~

Kiểm affected count:

- 1: update thành công.
- 0: không có row phù hợp, không đủ hàng hoặc không thuộc tenant hiện hành.

Test concurrency có thể chạy nhiều requests đồng thời và xác minh available không âm, tổng lượng reserve không vượt lượng ban đầu. DB constraint `CHECK(available >= 0)` bổ sung bảo vệ nếu phù hợp.

Atomic statement vẫn dùng internal database locks khi thực thi, nhưng không giống một application-managed `SELECT FOR UPDATE` protocol kéo dài qua nhiều bước.

## 12. Spring @Transactional và test concurrency

Spring transactions thường gắn với thread hiện hành. Mỗi worker cần transaction và Persistence Context riêng.

### 12.1. Tránh transaction bao ngoài test

Spring TestContext có thể mở transaction cho test thread và rollback khi test kết thúc. Worker threads không tự tham gia transaction đó. Nếu fixture được tạo trong test transaction chưa commit, transaction khác có thể không nhìn thấy.

Một pattern dễ hiểu:

1. Tạo fixture và commit trước.
2. Chạy workers, mỗi worker mở transaction riêng.
3. Chờ workers hoàn tất.
4. Mở EntityManager mới để verify.
5. Cleanup fixture trong transaction riêng.

### 12.2. Không chia sẻ EntityManager giữa threads

Không viết:

~~~java
EntityManager em = entityManagerFactory.createEntityManager();

executor.submit(() -> em.find(Product.class, 42L));
executor.submit(() -> em.find(Product.class, 42L));
~~~

EntityManager/Hibernate Session không thread-safe. Mỗi task cần EntityManager riêng, transaction riêng và close đúng cách.

### 12.3. Shared EntityManager proxy

Một proxy inject qua `@PersistenceContext` có thể resolve target EntityManager gắn với transaction hiện hành trên thread khi Spring transaction manager được cấu hình đúng. Nhưng không truyền raw target EntityManager giữa threads. Với test phức tạp, tạo EntityManager trực tiếp từ EntityManagerFactory trong mỗi worker làm ownership rõ hơn.

## 13. Rollback và exception handling

Sau optimistic/pessimistic lock failure:

- Không tiếp tục dùng transaction như thể vẫn hợp lệ.
- Rollback hoặc để transaction manager hoàn tất rollback.
- Đóng Persistence Context hoặc clear theo lifecycle phù hợp.
- Retry, nếu được phép, phải dùng transaction mới.
- Đọc state mới trước khi tính lại command.

`OptimisticLockException` thường dẫn tới rollback transaction. `PessimisticLockException` và `LockTimeoutException` có semantics khác nhau về phạm vi rollback theo JPA/database. Spring có thể dịch exception tại service boundary.

Test ở JPA layer có thể assert exception JPA; test ở service layer có thể assert exception Spring đã translate. Đừng bắt mọi exception rồi coi là locking failure.

## 14. Retry sau optimistic conflict

Một retry an toàn phải đọc state mới và tính lại command:

~~~text
Attempt 1:
  Read version 4
  Compute new state
  Commit -> optimistic conflict

Attempt 2:
  Open a new transaction
  Read latest version 5
  Recompute from current state
  Commit -> success or another conflict
~~~

Không dùng lại snapshot/version cũ. Giới hạn số attempts và dùng backoff phù hợp. Retry chỉ an toàn khi command idempotent hoặc có operation ID/idempotency key.

Với inventory decrement, retry phải kiểm lại quantity. Nếu không còn đủ, trả business rejection. Với gửi email, thanh toán hoặc phát message, dùng outbox/idempotency để ngăn side effects lặp.

## 15. Kiểm thử trên database thật

H2 hữu ích cho test nhanh nhưng lock semantics, isolation, SQL dialect và deadlock behavior có thể khác PostgreSQL, MySQL, Oracle hoặc SQL Server.

Với code concurrency-critical, ưu tiên integration tests trên DBMS production-equivalent, có thể dùng Testcontainers.

Cần khớp:

- Database version.
- JDBC driver.
- Hibernate dialect/version.
- Transaction isolation.
- Connection pool.
- Schema, indexes và constraints.
- Lock timeout configuration.
- Database roles/permissions.
- Cache provider nếu cache ảnh hưởng behavior.

Ví dụ cấu trúc JUnit 5:

~~~java
@Testcontainers
class InventoryConcurrencyIT {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    // Tạo DataSource/EntityManagerFactory trỏ vào container.
    // Mỗi worker mở EntityManager và transaction riêng.
}
~~~

### 15.1. Pool cần đủ connections

Nếu test có hai transactions đồng thời, pool một connection có thể khiến transaction thứ hai chờ lấy connection trước khi cạnh tranh row lock. Khi đó test đo pool starvation thay vì database locking.

Cấu hình test pool đủ cho tất cả concurrent transactions và connections phụ. Khi timeout, kiểm thread dump, pool metrics và database sessions.

### 15.2. Testcontainers không tự tạo concurrency

Testcontainers chỉ cung cấp database instance. Test vẫn phải mở nhiều physical connections/transactions và điều phối thời điểm thực sự cạnh tranh.

## 16. Lock timeout, query timeout và transaction timeout

| Timeout | Phạm vi |
| --- | --- |
| Lock timeout | Thời gian chờ lấy lock |
| Query/statement timeout | Thời gian thực thi statement |
| Transaction timeout | Thời gian cho transaction theo framework/configuration |

Query timeout không nhất thiết giống lock timeout. Transaction timeout của Spring cũng không luôn được gửi xuống database như cùng một setting.

Một test tốt:

1. Cấu hình timeout ở layer phù hợp.
2. Giữ lock A bằng latch.
3. Yêu cầu transaction B lấy cùng lock.
4. Xác nhận exception và rollback theo DBMS.
5. Xác nhận connection được trả pool và transaction sau vẫn hoạt động.
6. Dùng bounded waits để test không treo.

## 17. Những lỗi khiến test concurrency không đáng tin

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng một EntityManager cho nhiều threads | Persistence Context không thread-safe | Mỗi worker một EntityManager |
| Chỉ gọi hai service tuần tự | Không tạo race window | Transactions thật đồng thời |
| Fixture chưa commit | Worker không thấy dữ liệu | Commit fixture trước |
| Dùng `Thread.sleep()` để sắp lịch | Timing không xác định | CountDownLatch/CyclicBarrier |
| Bắt mọi RuntimeException | Che lỗi SQL/connection/assertion | Kiểm cause chain và exception contract |
| Chỉ assert exception | Không biết DB state cuối | Verify bằng context mới |
| Chỉ test H2 | Behavior khác production | Test DBMS production-equivalent |
| Pool chỉ có một connection | Worker chờ pool thay vì lock | Tăng pool capacity |
| Không cleanup latch/threads | Test có thể treo | finally, shutdown và bounded Future.get |
| Retry cùng detached entity | Version/state vẫn cũ | Transaction mới và load lại |
| Test transaction rollback bao ngoài | Fixture không commit | Dùng transaction setup tường minh |
| Không kiểm invariants nhiều rows | Bỏ sót write skew | Constraint/root lock/serializable tests |

## 18. Kiểm thử tenant scope cùng concurrency

Với shared-table tenancy, hai tenants có thể có cùng local SKU:

~~~text
inventory
tenant_id | sku | available | version
alpha     | X-1 | 10        | 0
beta      | X-1 | 20        | 0
~~~

Mutation phải có tenant predicate:

~~~sql
update inventory
set available = available - :amount,
    version = version + 1
where tenant_id = :tenantId
  and sku = :sku
  and available >= :amount;
~~~

Test alpha reserve 3 units rồi xác minh:

- Alpha còn 7.
- Beta vẫn 20.
- Affected count của alpha là 1.
- Transaction không giữ lock/EntityManager của tenant khác.
- RLS/tenant context được thiết lập đúng nếu có.

Với database-per-tenant hoặc schema-per-tenant, test connection routing thay vì chỉ kiểm predicate.

## 19. Quan sát khi test concurrency thất bại

Thông tin hữu ích:

- SQL statements liên quan đến row.
- Hibernate SQL/bind logs ở môi trường test có kiểm soát.
- Transaction begin/commit/rollback timestamps.
- Thread/task IDs.
- Entity ID và version đã đọc.
- Lock mode, timeout và isolation level.
- Database lock/wait information.
- Connection pool active/idle/pending counts.
- Exception class và cause chain.
- Final row state sau khi workers kết thúc.

Không log dữ liệu nhạy cảm hoặc mọi bind values ở production chỉ để debug lock. Dùng operation IDs và identifiers được phép ghi log.

## 20. Checklist thiết kế test

1. Có ít nhất hai transactions độc lập thật sự không?
2. Mỗi transaction có EntityManager/Session riêng không?
3. Fixture đã commit trước khi workers đọc chưa?
4. Thời điểm đọc/lock có được đồng bộ bằng latch/barrier không?
5. Latches và futures có timeout không?
6. Optimistic test có xác nhận hai writers đọc cùng version không?
7. Conflict được assert tại flush/commit boundary thích hợp không?
8. Pessimistic test có xác minh lock được giữ đến transaction completion không?
9. Lock timeout đã được kiểm trên DBMS mục tiêu chưa?
10. Có test deadlock khi khóa nhiều rows không?
11. Final state được verify bằng EntityManager mới không?
12. Transaction lỗi có rollback sạch không?
13. Retry có đọc lại state trong transaction mới không?
14. Invariants nhiều rows/write skew đã được xét chưa?
15. Bulk DML có test riêng về version/cache behavior không?
16. Pool đủ connections cho concurrent transactions không?
17. Tenant scope được kiểm nếu dùng shared tables không?
18. Test chạy trên DBMS/driver gần production không?
19. Có tránh Thread.sleep làm synchronization không?
20. Logs đủ chẩn đoán mà không lộ dữ liệu nhạy cảm không?

## 21. Bài tập thực hành

### Bài 1 — Optimistic conflict

Product có price=100 và version=0. Hai EntityManagers đọc cùng row. A commit price=120 trước, B sau đó cố ghi 110. Mô tả version predicate và exception mong đợi.

### Bài 2 — Lost update

Viết test hai threads cùng increment DownloadCounter có `@Version`. Assertions nào chứng minh không mất increment?

### Bài 3 — Flush hay commit?

Tại sao test chỉ gọi setter rồi assert exception ngay lập tức là sai? Optimistic exception có thể xuất hiện ở những điểm nào?

### Bài 4 — Detached merge

Hai detached copies cùng Product có cùng version. A merge và commit; B merge sau. Giải thích managed instance trả về từ merge và thời điểm conflict có thể xảy ra.

### Bài 5 — Pessimistic write

Hai transactions gọi `find(Product.class, id, PESSIMISTIC_WRITE)`. Điều gì xảy ra khi A giữ lock còn B yêu cầu cùng lock? Vì sao cần test DBMS thật?

### Bài 6 — Lock timeout

Thiết kế test A giữ lock, B dùng timeout ngắn. Những exception JPA/Spring nào có thể xuất hiện và vì sao class có thể khác giữa providers?

### Bài 7 — Deadlock

A khóa row 1 rồi row 2; B khóa row 2 rồi row 1. Thiết kế latch choreography và xác minh rollback.

### Bài 8 — Write skew

Hai transactions cùng kiểm tra còn một chỗ rồi mỗi transaction insert một booking khác nhau. Vì sao version trên từng Booking có thể không đủ? Đề xuất constraint hoặc root lock.

### Bài 9 — Spring test transaction

Test method có `@Transactional` tạo fixture chưa commit, sau đó worker thread đọc. Vì sao worker có thể không thấy fixture? Sửa transaction setup.

### Bài 10 — Pool starvation

Concurrency test chỉ có một connection. Vì sao nó có thể không kiểm tra row lock? Cần bao nhiêu connections cho hai writers?

### Bài 11 — Retry

Sau optimistic conflict, vì sao không nên retry cùng detached entity? Mô tả transaction mới đọc lại state và tính lại command.

### Bài 12 — Bulk SQL

Bulk UPDATE thay đổi entity có `@Version`. Viết SQL expected-version predicate và nêu assertions về affected count/version.

### Bài 13 — Tenant concurrency

Alpha và beta có cùng SKU. Alpha reserve inventory. Test phải xác minh gì để beta stock và locks không bị ảnh hưởng?

### Bài 14 — Isolation levels

Phân biệt non-repeatable read, phantom và lost update. Nêu choreography hai transactions cho từng tình huống.

### Bài 15 — Production parity

Test H2 pass nhưng PostgreSQL production deadlock. Những khác biệt DBMS/driver/lock strategy nào cần đưa vào test environment?

**Gợi ý:** (1) version mismatch; (2) một commit và một conflict; (3) flush/commit mới chạy SQL; (4) merge trả managed instance; (5) B chờ hoặc timeout; (6) LockTimeoutException/PessimisticLockException tùy transaction rollback; (7) barrier sau mỗi lock; (8) root lock/constraint/serializable; (9) thread-bound test transaction chưa commit; (10) pool đủ connections; (11) state cũ; (12) expected version predicate; (13) tenant predicate và verify beta unchanged; (14) mô phỏng từng anomaly; (15) DBMS/driver thật.

## 22. Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): locking, versioning, transactions, persistence context và batching.
- [Hibernate ORM 6.6 Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/): Session lock APIs, LockOptions và provider behavior.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): version attributes, optimistic/pessimistic lock modes, lock timeout và transaction semantics.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction propagation, rollback và TransactionTemplate.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): assertions, lifecycle và test execution.
- [Java Concurrency Utilities](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html): ExecutorService, CountDownLatch, CyclicBarrier, Future và timeout coordination.
- [Testcontainers Documentation](https://java.testcontainers.org/): integration tests với database thật trong container.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locks, deadlocks và lock conflicts.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): isolation levels và concurrent transaction behavior.

**Kết luận:** kiểm thử concurrency phải tái hiện nhiều transactions độc lập trên database thật. Với optimistic locking, dùng `@Version` và xác minh writer giữ version cũ nhận conflict tại flush/commit, sau đó kiểm state cuối bằng context mới. Với pessimistic locking, dùng `PESSIMISTIC_WRITE`/lock mode phù hợp, giữ transaction có kiểm soát và xác minh transaction cạnh tranh chờ hoặc timeout theo DBMS. Latches/barriers tạo thứ tự đọc và ghi; bounded timeouts ngăn test treo. Ngoài exception, luôn kiểm rollback, version, dữ liệu cuối, invariants nhiều rows, tenant scope và retry behavior. Không chia sẻ EntityManager giữa threads, không dùng Thread.sleep để đồng bộ và không coi H2 là bằng chứng thay thế DBMS production.
