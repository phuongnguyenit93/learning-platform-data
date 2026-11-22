# Kiểm thử đồng thời bằng nhiều EntityManager độc lập

Một chương trình JPA có thể chạy đúng khi một người dùng thao tác, nhưng sai khi hai request đến gần như cùng lúc. Hai giao dịch có thể cùng đọc số lượng tồn kho, cùng thấy rằng một mã đơn hàng chưa tồn tại, cùng cố thay đổi trạng thái của một entity hoặc cạnh tranh khóa trên cùng một dòng. Những lỗi như **lost update**, **ghi trùng business key**, **deadlock**, **lock timeout** hay **write skew** thường không xuất hiện trong unit test đơn luồng.

Xét tình huống:

```text
Kho còn 10 sản phẩm

Request A: mua 7
Request B: mua 6

A đọc 10 -> cho phép mua 7
B đọc 10 -> cho phép mua 6

Nếu hệ thống ghi đè trạng thái không kiểm soát,
hai đơn đều được chấp nhận dù tổng yêu cầu là 13.
```

Để kiểm tra đúng hiện tượng này, ta cần **hai persistence context độc lập**, **hai transaction thực** và, với các trường hợp cần race chính xác, **hai luồng có lịch đồng bộ rõ**. Hai biến Java khác nhau trỏ vào cùng một entity trong *một* EntityManager không thể tái hiện tình huống hai giao dịch độc lập.

Bài **“Kiểm thử đồng thời bằng nhiều EntityManager độc lập”** thuộc chương **“Kiểm thử JPA”**, module **Data Persistence Relational Access ORM JPA**. Nội dung tập trung vào phương pháp thiết kế, lập trình và diễn giải kiểm thử concurrency: từ `@Version` và optimistic locking, `PESSIMISTIC_WRITE`, transaction isolation, ràng buộc UNIQUE cho đến các bài kiểm thử đa luồng bằng JUnit/Testcontainers, tránh flaky tests và quan sát trạng thái đã commit.

## 1. Mục tiêu của bài kiểm thử đồng thời

Sau khi thực hành, bạn cần phân biệt được:

1. `EntityManagerFactory` và `EntityManager` khác nhau về khả năng dùng chung giữa các luồng.
2. Hai `EntityManager` độc lập tạo hai persistence contexts, nhưng chỉ trở thành hai transaction độc lập khi boundary được tổ chức đúng.
3. Cách tạo tình huống hai bên cùng đọc một phiên bản, rồi một bên commit trước bên còn lại.
4. Khác biệt giữa `flush()` thành công và `commit()` thành công.
5. Cách chứng minh một optimistic conflict thực sự khiến thay đổi thua cuộc bị rollback.
6. Cách kiểm thử `PESSIMISTIC_WRITE` mà không dựa vào `Thread.sleep()` để điều khiển thứ tự.
7. Vì sao pre-check `existsBy...` không thay UNIQUE constraint trong database.
8. Cách dùng `CountDownLatch`/`CyclicBarrier`/`ExecutorService` có timeout, không tạo test treo vô hạn.
9. Những yếu tố khiến kết quả khác nhau giữa H2 và PostgreSQL/MySQL/Oracle.
10. Cách xác định correctness invariants, test bằng database thật và đo độ ổn định qua nhiều lần chạy.

### 1.1. Đừng chỉ kiểm tra “có exception”

Một kiểm thử tốt phải xác minh **kết quả lưu trữ cuối cùng**:

- Nếu hai giao dịch cùng update bản ghi có version, giao dịch thua có để lại state nào không?
- Nếu hai client cùng tạo business key, database có đúng **một row** không?
- Nếu hai orders cùng đặt giữ hàng, tổng số hàng đã bán có vượt stock không?
- Nếu giao dịch lock timeout, transaction thất bại đã được rollback/đóng resources chưa?
- Nếu API retry, có ghi trùng event/order hoặc trừ tồn kho hai lần không?

Để thấy câu trả lời, cần reload trong **EntityManager mới** hoặc query ở transaction/connection độc lập sau khi các giao dịch đã hoàn tất.

## 2. Bốn thành phần của một thí nghiệm concurrency

| Thành phần | Vai trò | Sai lầm thường gặp |
|---|---|---|
| `EntityManagerFactory` | Tạo `EntityManager`, thường được chia sẻ trong ứng dụng | Tạo một factory cho mỗi thread không cần thiết |
| `EntityManager` | Persistence context/identity map của một luồng làm việc | Dùng chung một instance cho nhiều worker threads |
| `Transaction` | Đơn vị atomic commit/rollback theo DB | Tưởng mỗi repository method có transaction riêng |
| `Connection`/DB transaction | Resource thật thực thi SQL và khóa | Connection pool chỉ có một kết nối khiến test bị tuần tự hóa hoặc deadlock phía client |

### 2.1. `EntityManagerFactory` có thể chia sẻ

`EntityManagerFactory` được thiết kế để tạo nhiều `EntityManager` và thường được dùng chung trong ứng dụng. Test có thể dùng một factory initialized cho cả suite:

```java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();
```

### 2.2. `EntityManager` không thread-safe

**Không** truyền cùng `emA` vào hai threads để gọi `find`/`persist`/`flush` song song. `EntityManager` chứa identity map, dirty-checking state và lifecycle bookkeeping, không phải tài nguyên để nhiều luồng tùy ý thao tác đồng thời.

Đúng hơn:

```text
Thread A
  -> EntityManager A
  -> Transaction A
  -> Database

Thread B
  -> EntityManager B
  -> Transaction B
  -> Database
```

### 2.3. Hai EntityManager không luôn bảo đảm hai transaction độc lập

Trong ứng dụng JTA hoặc Spring-managed persistence context, một `@PersistenceContext` proxy có thể tra cứu EntityManager gắn với transaction hiện tại. Hai biến tham chiếu/proxy khác nhau chưa chắc đại diện cho hai unit-of-work độc lập.

Để test **hai transaction độc lập**, cần kiểm tra transaction boundaries/propagation, cách EntityManager được bind và việc mỗi worker thực sự kết nối đến database trong transaction riêng.

### 2.4. Cùng một EntityManager không mô phỏng concurrent updates

```java
UserAccount a = em.find(UserAccount.class, 10L);
UserAccount b = em.find(UserAccount.class, 10L);

assertSame(a, b); // Cùng persistent identity trong một context.
```

Nếu cùng managed entity instance, một thread sửa state thì thread còn lại không có “snapshot cũ độc lập” giống hai request thật.

### 2.5. Hai EM có thể đọc ra hai Java objects khác nhau

```java
UserAccount a = emA.find(UserAccount.class, 10L);
UserAccount b = emB.find(UserAccount.class, 10L);

assertNotSame(a, b);
```

Khi cả hai không null và cùng PK, chúng là hai Java entity instances do hai contexts quản lý. Điều này **chưa** tự bảo đảm hai transactions đã bắt đầu hoặc cùng đọc đúng version; thiết lập thêm transaction và lịch đọc.

## 3. Mô hình dùng xuyên suốt: tồn kho có phiên bản

Giả định một kho đơn giản có số lượng còn lại. Business invariant:

> `availableQuantity` không được âm; hai giao dịch không được cùng bán quá số hàng còn lại.

### 3.1. Entity `InventoryItem`

```java
package example.inventory;

import jakarta.persistence.*;

@Entity
@Table(
    name = "inventory_items",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_inventory_tenant_sku",
        columnNames = {"tenant_id", "sku"}
    )
)
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "tenant_id", nullable = false,
            updatable = false, length = 64)
    private String tenantId;

    @Column(name = "sku", nullable = false,
            updatable = false, length = 64)
    private String sku;

    @Column(name = "available_quantity", nullable = false)
    private int availableQuantity;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected InventoryItem() {}

    public InventoryItem(
            String tenantId, String sku, int initialQuantity) {
        if (initialQuantity < 0) {
            throw new IllegalArgumentException(
                "Quantity must be non-negative");
        }
        this.tenantId = tenantId;
        this.sku = sku;
        this.availableQuantity = initialQuantity;
    }

    public void reserve(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException(
                "Reservation must be positive");
        }
        if (amount > availableQuantity) {
            throw new IllegalStateException(
                "Insufficient inventory");
        }
        availableQuantity -= amount;
    }

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public int getAvailableQuantity() {
        return availableQuantity;
    }
    public long getVersion() { return version; }
}
```

### 3.2. Cơ chế `@Version`

Khi update managed entity, provider thường phát SQL có điều kiện version, khái niệm như:

```sql
UPDATE inventory_items
SET available_quantity = 3,
    version = 8
WHERE id = 100
  AND version = 7;
```

Nếu một transaction khác đã cập nhật version thành 8, câu UPDATE của bản sao cũ có thể ảnh hưởng **0 rows**, dẫn đến optimistic locking conflict. Thứ tự và cách provider thực thi SQL phụ thuộc dialect/version, nhưng **version check ở database** là phần trọng yếu.

### 3.3. Database constraint thêm một tuyến phòng thủ

Trên PostgreSQL:

```sql
ALTER TABLE inventory_items
ADD CONSTRAINT ck_inventory_nonnegative
CHECK (available_quantity >= 0);
```

Domain method kiểm tra lượng trước khi trừ. DB CHECK bảo vệ khi có writer khác hoặc bug bỏ qua method. Nhưng DB CHECK một mình **không ngăn lost update** nếu cả hai ghi một lượng không âm; cần concurrency control thích hợp.

### 3.4. Ví dụ dữ liệu ban đầu

```text
id = 100
tenant_id = TENANT_A
sku = SKU-RED
available_quantity = 10
version = 7
```

Hai transactions đều muốn reserve 7 và 6. Bài kiểm thử cần bảo đảm không thể có hai successful bookings cộng 13 trong khi tồn kho chỉ 10.

## 4. Ba tầng kiểm thử thường bị nhầm

### 4.1. Unit test của domain method

```java
InventoryItem item =
    new InventoryItem("TENANT_A", "SKU-RED", 10);

item.reserve(7);
assertEquals(3, item.getAvailableQuantity());
```

Nó kiểm tra logic đơn luồng. Không kiểm tra SQL UPDATE, transaction isolation, optimistic conflicts hay unique constraint.

### 4.2. JPA integration test một transaction

```java
em.getTransaction().begin();
InventoryItem item = em.find(InventoryItem.class, id);
item.reserve(7);
em.getTransaction().commit();
```

Nó kiểm tra mapping và persistence lifecycle cơ bản nhưng không chứng minh hai users không có race.

### 4.3. Concurrency integration test

```text
EM A + Tx A: READ version 7
EM B + Tx B: READ version 7
EM A + Tx A: UPDATE + COMMIT
EM B + Tx B: UPDATE + COMMIT -> conflict
```

Đây là bài kiểm thử có **hai persistence snapshots** và **điểm tương tác được kiểm soát**.

### 4.4. Không mock EntityManager để chứng minh locking

Mockito/fake repository có thể mô phỏng exception, nhưng không kiểm chứng database lock manager, SQL row-count detection, JDBC isolation hay commit-time conflicts. Dùng mock cho application error handling; dùng **database thực/tương đương production** cho tính đúng đắn concurrency.

## 5. Chuẩn bị môi trường kiểm thử độc lập

Một thiết lập thường gồm:

- JUnit Jupiter (JUnit 5).
- Jakarta Persistence/Hibernate provider đúng major version của ứng dụng.
- DataSource/connection pool.
- PostgreSQL/MySQL/Oracle thực hoặc container test tương đương production.
- Migrations tạo schema/constraints như production.
- Fixture dữ liệu riêng cho mỗi test và cleanup có kiểm soát.

### 5.1. Không nhất thiết phải bật `ddl-auto=create-drop`

Nếu production dùng Flyway/Liquibase, chạy **chính migrations ấy** vào database test mới giúp tránh trường hợp JPA tự tạo unique/version columns mà migration production chưa có. Sau đó có thể bật Hibernate schema validation phù hợp.

### 5.2. Sử dụng Testcontainers

Ví dụ skeleton:

```java
@Testcontainers
class InventoryConcurrencyIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    // Setup DataSource and EntityManagerFactory
    // from postgres.getJdbcUrl()/username/password.
    // Apply migrations before tests.
}
```

Version image mang tính minh họa; chọn PostgreSQL version phù hợp hệ thống. Testcontainers chỉ cấp database isolated, vẫn cần bootstrap JPA/migrations và quản lý connections.

### 5.3. Connection pool phải đủ cho các transactions cùng lúc

Nếu test muốn 2 transactions giữ connection đồng thời nhưng pool chỉ có 1 connection:

```text
Thread A giữ connection
Thread B chờ connection từ pool
Thread A chờ Thread B đạt barrier
=> Test deadlock ở application level
```

Thường đặt pool capacity ít nhất bằng số concurrent workers thực sự cần connection cộng overhead hợp lý. Tránh pool quá nhỏ tạo “lock wait” giả không liên quan database rows.

### 5.4. Đặt timeout ở nhiều tầng

- Timeout chờ latch/barrier.
- Timeout chờ `Future.get`.
- JDBC query/lock timeout nếu cần.
- Test framework/global suite timeout.
- Cleanup executor và EntityManager trong `finally`.

Một test concurrency không được treo vô hạn khi code có lỗi.

### 5.5. Tạo fixture đã commit

Tạo row `InventoryItem` trong một transaction **hoàn tất commit trước** khi hai workers bắt đầu:

```java
Long seedStock(int quantity) {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();
    try {
        tx.begin();
        InventoryItem item = new InventoryItem(
            "TENANT_A", "SKU-RED", quantity);
        em.persist(item);
        tx.commit();
        return item.getId();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    } finally {
        em.close();
    }
}
```

Nếu fixture chỉ được `flush()` nhưng chưa commit, một EM khác có thể không đọc thấy row tùy isolation. Đừng bắt đầu race trên dữ liệu chưa được công bố.

## 6. Bài kiểm thử thứ nhất: hai EntityManager đọc cùng một phiên bản

Đây là test **deterministic sequencing**: không nhất thiết dùng hai threads để chứng minh optimistic concurrency. Ta chủ động giữ hai transactions/contexts rồi commit A trước B.

### 6.1. Kịch bản

```text
Step 1: Seed row stock=10, version=7
Step 2: A.begin(), A.find() -> stock=10, version=7
Step 3: B.begin(), B.find() -> stock=10, version=7
Step 4: A.reserve(7), A.commit() -> stock=3, version=8
Step 5: B.reserve(6), B.commit() -> optimistic conflict
Step 6: B rollback/close
Step 7: New EntityManager reads stock=3
```

### 6.2. Java/JUnit skeleton

```java
@Test
void staleTransactionCannotOverwriteCommittedStock() {
    Long itemId = seedStock(10);

    EntityManager emA = emf.createEntityManager();
    EntityManager emB = emf.createEntityManager();

    EntityTransaction txA = emA.getTransaction();
    EntityTransaction txB = emB.getTransaction();

    try {
        txA.begin();
        txB.begin();

        InventoryItem a = emA.find(
            InventoryItem.class, itemId);
        InventoryItem b = emB.find(
            InventoryItem.class, itemId);

        assertEquals(10, a.getAvailableQuantity());
        assertEquals(10, b.getAvailableQuantity());
        assertEquals(a.getVersion(), b.getVersion());
        assertNotSame(a, b);

        a.reserve(7);
        txA.commit();

        b.reserve(6); // B vẫn thấy snapshot quantity=10.

        assertThrows(RuntimeException.class, txB::commit);
        // Check nested cause/error category matches an
        // optimistic conflict for the chosen provider.

    } finally {
        if (txA.isActive()) txA.rollback();
        if (txB.isActive()) txB.rollback();
        emA.close();
        emB.close();
    }

    try (EntityManager verification =
            emf.createEntityManager()) {
        InventoryItem current = verification.find(
            InventoryItem.class, itemId);
        assertEquals(3, current.getAvailableQuantity());
    }
}
```

Trong các JPA API versions, `EntityManager` có thể hoặc không implement `AutoCloseable`; để portable, thay khối try-with-resources ở bước verification bằng `try/finally { verification.close(); }` nếu API/version không hỗ trợ. Đoạn này là skeleton diễn giải testcase, cần điều chỉnh imports và exception assertions theo stack. Một số dialect/isolation combinations có thể phát hiện serialization/lock conflict thay vì type exception cụ thể, vì thế test phải xác định **expected conflict class** trên DB đang dùng.

### 6.3. Trạng thái sau test

Đừng chỉ viết:

```java
assertThrows(RuntimeException.class, txB::commit);
```

rồi kết luận đúng. Có thể transaction B fail vì connection outage hoặc SQL syntax error. Cần phân loại nguyên nhân (optimistic lock row count, version conflict hoặc serialization-related error như thiết kế) và assert **DB stock=3**, không bị thay thành 4.

### 6.4. Không cố tiếp tục transaction B sau lỗi

Nếu `commit`/`flush` báo persistence exception, context/transaction có thể rollback-only. Rollback nếu còn active và đóng EM; không sửa `b` rồi commit lại trong cùng context. Retry business command trong transaction mới sau khi đọc state mới.

### 6.5. Version có thể bắt đầu từ 0 hoặc 1

Giá trị ban đầu của `@Version` tùy provider/strategy. Kiểm tra `b.getVersion() == a.getVersion()` trước cập nhật và **khác sau commit** nếu cần, không hardcode mọi test phải bắt đầu từ version=7.

### 6.6. Đừng đo số lượng UPDATE statements thay correctness invariant

Hibernate `@DynamicUpdate`, JDBC batching hoặc provider settings có thể thay số SQL statements. Điều cần bảo đảm là chỉ một optimistic write từ cùng base version được commit, còn stale write không ghi đè.

## 7. Khi nào cần hai luồng thực sự?

Hai `EntityManager` trong cùng một test thread đủ để tạo thứ tự:

```text
A read -> B read -> A commit -> B commit
```

cho nhiều optimistic-locking tests. Nhưng với **blocking locks, simultaneous INSERT, deadlock, transaction isolation visibility, lock timeout**, cần ít nhất hai worker threads để một transaction có thể đang chờ DB trong khi transaction khác vẫn chạy.

### 7.1. Phân biệt interleaving và parallel execution

- **Interleaving có chủ đích**: lập thứ tự các bước database trước/sau để tạo race một cách xác định.
- **Parallel execution**: hai threads thực sự đồng thời chờ/đi vào các thao tác JDBC.
- **Stress test**: nhiều threads chạy lặp lại dưới contention và scheduler không xác định.

Không cần áp stress test cho mọi correctness case; một interleaving được kiểm soát thường dễ debug và ổn định hơn.

### 7.2. Phần lớn race cần “đồng thời về mặt transaction” hơn “cùng nanosecond”

Hai giao dịch có thể overlap hàng trăm milliseconds, cùng đọc version N rồi lần lượt update; optimistic conflict vẫn xảy ra. Đồng bộ dữ liệu bằng barriers/latches giúp bảo đảm trạng thái đầu vào, không phải ép CPU thực thi cùng một chu kỳ.

### 7.3. Không đoán thứ tự qua sleep

Sai:

```java
Thread.sleep(100);
// Hy vọng thread B đã đọc row.
```

Thời gian sleep không chứng minh thread B đã hoàn thành SQL, còn phụ thuộc scheduler, CI load, network, database locks. Dùng handshake signal đúng sau khi sự kiện đã xảy ra.

### 7.4. Có thể dùng transaction riêng không có thread riêng?

Với resource-local `EntityManager`, hai EM + hai transaction objects có thể được điều khiển tuần tự trong một thread mà vẫn giữ độc lập. Với transaction framework thread-bound như Spring, cần xem transaction propagation/manager và thường dùng hai threads để tránh tình trạng mọi thao tác vô tình chạy trong cùng transaction.

## 8. Công cụ điều phối thread trong JUnit

Những primitives phổ biến:

| Công cụ | Công dụng |
|---|---|
| `CountDownLatch` | Một hoặc nhiều thread chờ một mốc đã xảy ra |
| `CyclicBarrier` | Nhiều threads chờ nhau trước giai đoạn tiếp theo |
| `Phaser` | Nhiều pha đồng bộ có thể thay số parties |
| `ExecutorService` | Quản lý worker threads và futures |
| `Future.get(timeout)` | Chờ kết quả có giới hạn thời gian |
| `CompletableFuture` | Kết hợp async tasks, nhưng không tự tạo transaction |
| `AtomicReference` | Chuyển kết quả/exception giữa threads khi cần |

### 8.1. Latch dùng để xác nhận SQL READ đã xong

```java
CountDownLatch bothRead = new CountDownLatch(2);
CountDownLatch mayWrite = new CountDownLatch(1);
```

Trong worker:

```java
InventoryItem item = em.find(
    InventoryItem.class, itemId);

bothRead.countDown();
if (!mayWrite.await(5, TimeUnit.SECONDS)) {
    throw new TimeoutException(
        "Timed out waiting to write");
}

item.reserve(amount);
```

Test coordinator:

```java
assertTrue(bothRead.await(5, TimeUnit.SECONDS));
mayWrite.countDown();
```

Như vậy ta biết **cả hai reads đã hoàn tất** trước khi cho phép writes, miễn worker countDown đặt đúng sau `find` và không bỏ qua exceptions.

### 8.2. Barrier cho hai worker cùng tiến vào giai đoạn

```java
CyclicBarrier beforeWrite = new CyclicBarrier(2);
```

Mỗi worker đọc entity rồi:

```java
beforeWrite.await(5, TimeUnit.SECONDS);
item.reserve(amount);
```

Các workers không được phép chạy write trước khi cả hai đến barrier. Tuy nhiên **ai commit trước** vẫn phụ thuộc scheduler/database và có thể thay đổi. Nếu test chỉ cần “một thành công, một thất bại”, điều này hợp lệ.

### 8.3. Đừng đặt barrier ở vị trí đã bị DB lock

Ví dụ nguy hiểm:

```text
T1: lock row X -> wait at barrier
T2: try lock row X -> blocked by DB
T2: never reaches barrier
T1: waits forever without timeout
```

Đặt barrier **trước** thao tác có thể block hoặc dùng coordinator chấp nhận giao dịch B đang chờ lock.

### 8.4. Khi một thread ném exception trước latch

Nếu worker thất bại khi `em.find`, nó không `countDown`; thread khác có thể chờ timeout. Luôn dùng timed awaits và propagate worker exceptions qua `Future.get`; trong teardown giải phóng latches/executor để không treo.

### 8.5. Timeout không nên quá ngắn

`await(100, MILLISECONDS)` có thể ổn trên laptop nhưng flaky trên shared CI. Chọn timeout đủ cho môi trường thực tế, vẫn hữu hạn, và dùng logs/diagnostics khi timeout. Không xem timeout là bằng chứng duy nhất của database lock.

### 8.6. Thread interruption là tín hiệu cần xử lý

Nếu bắt `InterruptedException`, thường khôi phục interrupted flag bằng `Thread.currentThread().interrupt()` khi chuyển thành unchecked error hoặc propagate. Không nuốt interruption rồi tiếp tục transaction như không có chuyện gì.

## 9. Mẫu worker: một EntityManager một transaction một nhiệm vụ

Để tránh chia sẻ `EntityManager` qua threads, có thể tổ chức callback:

```java
@FunctionalInterface
interface TransactionWork<T> {
    T run(EntityManager em) throws Exception;
}

<T> T inNewEntityManager(TransactionWork<T> work)
        throws Exception {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();
        T result = work.run(em);
        tx.commit();
        return result;
    } catch (Exception | Error failure) {
        if (tx.isActive()) {
            try {
                tx.rollback();
            } catch (RuntimeException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
        }
        throw failure;
    } finally {
        em.close();
    }
}
```

Đây là **resource-local JPA** helper, không áp nguyên dạng cho application-managed JTA transactions. Trong JTA, dùng `UserTransaction`/transaction manager hoặc Spring `TransactionTemplate` và persistence-context binding phù hợp.

### 9.1. Chỉ trả DTO/ID khỏi worker

```java
record ReservationOutcome(
    boolean committed,
    Long itemId,
    String errorType
) {}
```

Không đưa một **managed entity** từ worker A sang thread B rồi sửa trực tiếp nó; các entities sau khi EM đóng có thể detached và chứa lazy relationships.

### 9.2. Ghi nhận exception có cấu trúc

Khi nhiều futures chạy, đặt job name/transaction label trong diagnostic result để phân biệt:

```text
worker-A read version 1
worker-B read version 1
worker-A commit success
worker-B optimistic conflict
```

Logs cần tránh nhạy cảm nếu test dùng dữ liệu giống production; ghi ids giả/test data, timestamps hoặc event phases.

### 9.3. Exception không nên bị đổi thành “success=false” quá sớm

Nếu test muốn phân biệt optimistic conflict với connection failure, worker không được catch mọi `Exception` và coi tất cả như expected conflict. Có thể trả result có `exception` hoặc propagate qua Future để main test kiểm tra exception category.

### 9.4. Teardown an toàn

Sau test, đóng executor:

```java
executor.shutdownNow();
if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
    // Log diagnostic for leaked workers.
}
```

Nếu worker đã giữ DB lock, `shutdownNow`/interrupt không luôn hủy JDBC statement ngay; nên có DB statement/lock timeout và đóng connections/EntityManagers trong workers' finally.

## 10. Thí nghiệm hai luồng: cùng đọc, rồi cạnh tranh commit

Để chứng minh một optimistic writer thắng, không cần biết A hay B thắng trước. Chỉ cần:

1. Cả hai thực sự đọc cùng base version.
2. Mỗi worker sửa entity của **chính EntityManager**.
3. Transactions được phép commit cạnh tranh.
4. Một commit thành công, một conflict khi cả hai sửa cùng row.
5. State cuối bằng một outcome hợp lệ, không phải tổng hợp sai.

### 10.1. Code skeleton sử dụng barrier

```java
@Test
void competingReservationsCannotBothCommit()
        throws Exception {

    Long itemId = seedStock(10);
    CyclicBarrier bothLoaded = new CyclicBarrier(2);
    ExecutorService pool = Executors.newFixedThreadPool(2);

    Callable<Boolean> reserveSeven = () ->
        tryReserve(itemId, 7, bothLoaded);
    Callable<Boolean> reserveSix = () ->
        tryReserve(itemId, 6, bothLoaded);

    try {
        Future<Boolean> a = pool.submit(reserveSeven);
        Future<Boolean> b = pool.submit(reserveSix);

        boolean aCommitted = a.get(15, TimeUnit.SECONDS);
        boolean bCommitted = b.get(15, TimeUnit.SECONDS);

        assertNotEquals(aCommitted, bCommitted);

        EntityManager verify = emf.createEntityManager();
        try {
            InventoryItem after = verify.find(
                InventoryItem.class, itemId);
            int quantity = after.getAvailableQuantity();
            assertTrue(quantity == 3 || quantity == 4);
        } finally {
            verify.close();
        }
    } finally {
        pool.shutdownNow();
        pool.awaitTermination(10, TimeUnit.SECONDS);
    }
}
```

### 10.2. Worker code và xử lý optimistic conflict

```java
boolean tryReserve(
        Long itemId, int amount, CyclicBarrier barrier)
        throws Exception {

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();
    try {
        tx.begin();
        InventoryItem item = em.find(
            InventoryItem.class, itemId);

        // Cả hai phải đọc cùng committed initial state.
        assertEquals(10, item.getAvailableQuantity());
        barrier.await(10, TimeUnit.SECONDS);

        item.reserve(amount);
        tx.commit();
        return true;
    } catch (RuntimeException failure) {
        if (tx.isActive()) tx.rollback();

        if (isExpectedOptimisticConflict(failure)) {
            return false;
        }
        throw failure;
    } finally {
        if (tx.isActive()) tx.rollback();
        em.close();
    }
}
```

`isExpectedOptimisticConflict` là helper thuộc test stack cần kiểm tra JPA `OptimisticLockException`/Spring wrapper/provider cause chain và/hoặc serialization conflict được test cho phép. Nếu `barrier.await` ném `TimeoutException`/`BrokenBarrierException`, code propagate thay vì coi là optimistic failure.

### 10.3. Vì sao code không assert A luôn thắng?

Scheduler, DB locking và thread startup có thể làm A hoặc B commit trước. Business invariant không phụ thuộc thứ tự: nếu A thắng, stock=3; nếu B thắng, stock=4; **không được cả hai báo committed** trên cùng version.

### 10.4. Đừng coi mọi lỗi là mong đợi

`ExecutionException`/`TimeoutException` từ `Future.get` báo test failure/infra. `SQLGrammarException` hay `ConnectionException` cũng không phải optimistic conflict. Kết quả “một true một false” chỉ có ý nghĩa nếu false được tạo **đúng vì conflict**.

### 10.5. Có thể xảy ra conflict trước commit

Một số providers/dialects/strategies có thể flush ở thời điểm sớm hơn hoặc lock/check khi gọi `em.flush`. Test không được cố định câu “exception chỉ xảy ra ở commit”; xác minh toàn bộ operation từ write đến transaction completion.

### 10.6. Vì sao hai requests cùng đọc quantity=10?

Barrier đặt sau `find` nhưng trước `reserve`. Cả hai thực hiện READ trước khi một bên cho phép write. Nếu isolation mạnh hoặc cơ chế lock được kích hoạt ngay khi find, cần điều chỉnh schedule cho đúng yêu cầu.

## 11. `flush()` khác `commit()` trong concurrency tests

`flush()` đồng bộ pending changes từ persistence context thành SQL **trong transaction hiện tại**. `commit()` hoàn tất transaction nếu thành công.

### 11.1. Đừng gọi `flush` rồi tuyên bố ghi thành công

```java
em.persist(order);
em.flush();
// Chưa chắc row visible cho transaction khác;
// chưa chắc transaction commit thành công.
```

Nếu DB dùng deferred constraints, lỗi UNIQUE/FK có thể xuất hiện ở commit. Với isolation thông thường, một transaction khác không đọc thấy uncommitted row.

### 11.2. SQL có thể chạy trước explicit flush

`GenerationType.IDENTITY` có thể yêu cầu INSERT sớm để lấy ID; auto-flush có thể xảy ra trước một JPQL query; provider/JDBC batching còn ảnh hưởng thời điểm SQL phát. Không viết test dựa trên giả định mọi `persist` chỉ giữ object trong RAM đến cuối.

### 11.3. Assert sau commit

Để biết giá trị cuối, tạo EntityManager mới sau khi tất cả futures/transactions kết thúc:

```java
EntityManager verify = emf.createEntityManager();
try {
    InventoryItem current =
        verify.find(InventoryItem.class, itemId);
    assertEquals(expected, current.getAvailableQuantity());
} finally {
    verify.close();
}
```

Đừng đọc lại bằng EM B đã load stale entity, vì nó có thể trả bản sao trong L1 cache thay vì query DB.

### 11.4. Không được rollback một transaction đã commit

`EntityTransaction.isActive()` giúp chỉ rollback khi còn active, nhưng nên xử lý rollback exception một cách rõ; nếu commit đã hoàn tất, rollback không còn ý nghĩa.

### 11.5. Resource leak có thể làm test sau thất bại

Luôn `close` EMs và trả JDBC connections về pool. Một test ngắn có thể pass nhưng nếu quên close, suite lớn sẽ timeout pool sau vài lần chạy.

## 12. Optimistic locking không thay kiểm tra business logic

`@Version` giải quyết việc hai transactions cập nhật **cùng version của một entity**, nhưng không tự đảm bảo mọi business invariant.

### 12.1. Nếu chỉ một transaction chấp nhận?

Trong stock=10, A reserve 7 và B reserve 6:

```text
A success -> available=3
B conflict -> B retries on new version
B sees 3 < 6 -> domain rejects reservation
```

Nếu retry giữ nguyên business action, nó phải **reload stock hiện tại** và chạy lại kiểm tra `amount <= availableQuantity`.

### 12.2. Không retry blind merge detached entity

Nếu B gặp conflict, làm:

```java
em.merge(staleInventoryItem);
```

trong transaction mới mà không reload/revalidate có thể tạo lỗi nghiệp vụ hoặc stale overwrite tùy graph/version. Retry an toàn là **thực hiện lại command trên state mới**, không “ép” stale object xuống DB.

### 12.3. Mỗi retry là một transaction độc lập

Sau optimistic exception, affected transaction thường không thể tiếp tục một cách an toàn. Đóng EM hoặc discard context, bắt đầu transaction mới, đọc entity mới rồi thử lại với giới hạn retry/backoff theo policy.

### 12.4. Đừng retry mọi conflict vô hạn

Khi load cao, hàng trăm writers cùng retry có thể tăng contention. Chọn bounded retries, jitter/backoff hoặc chuyển sang pessimistic/atomic SQL strategy khi workload thực tế cần.

### 12.5. Trả đúng API semantics

Nếu business action “reserve 6” không còn đủ hàng sau retry, trả out-of-stock/domain conflict, không đánh đồng với “500 database unavailable”. Nếu chỉ bị optimistic conflict nhưng chưa retry, API có thể trả 409/412 theo contract và để client refresh.

## 13. Kiểm thử ràng buộc UNIQUE khi hai giao dịch cùng tạo bản ghi

Một race khác không liên quan `@Version`: hai transaction cùng kiểm tra một business key chưa tồn tại rồi đều muốn insert.

### 13.1. Entity `CustomerAccount`

```java
@Entity
@Table(
    name = "customer_accounts",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_accounts_tenant_email",
        columnNames = {"tenant_id", "email"}
    )
)
public class CustomerAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "email", nullable = false)
    private String email;

    protected CustomerAccount() {}

    public CustomerAccount(String tenantId, String email) {
        this.tenantId = tenantId;
        this.email = email;
    }
}
```

Ràng buộc UNIQUE thật phải nằm trong database migrations/schema thực tế; annotation chỉ nêu metadata/schema-generation intent.

### 13.2. Tình huống pre-check bị race

```text
T1: SELECT EXISTS(tenant=A,email=x) -> false
T2: SELECT EXISTS(tenant=A,email=x) -> false
T1: INSERT account A/x -> COMMIT success
T2: INSERT account A/x -> unique violation
```

Một method `existsByTenantIdAndEmail` trước `save` có thể giúp trả lỗi sớm, nhưng **không bảo đảm uniqueness** khi có hai transactions chạy song song.

### 13.3. Test xác định một winner bằng hai EntityManager

Một lịch kiểm thử ổn định có thể:

1. Tạo hai EM + hai transactions.
2. Đảm bảo cả hai pre-check cùng trả false trước bất kỳ INSERT nào.
3. Commit T1 INSERT.
4. T2 thử INSERT và commit trong transaction đã thực hiện pre-check trước đó.
5. Assert T2 nhận database UNIQUE violation.
6. Query ở EM thứ ba, assert đúng một row cho `(tenant,email)`.

Lịch này thể hiện race logic một cách deterministic ngay cả khi hai INSERT không đua cùng microsecond.

### 13.4. Tại sao không cho cả hai cùng INSERT khi T1 chưa commit mà không có coordinator?

Trong nhiều RDBMS, INSERT trùng unique key của T2 có thể **block chờ kết quả transaction T1**. Nếu thread T1 lại đang chờ một barrier yêu cầu T2 hoàn tất INSERT, test tự tạo deadlock/hang. Thiết kế synchronization points trước operation có thể block.

### 13.5. Kết quả trên database không có UNIQUE

Nếu production schema chưa tạo constraint, cả hai transactions có thể commit và lưu hai rows. Vì vậy test phải kiểm tra **physical database constraint**, không chỉ có `@Table(uniqueConstraints=...)` trong source.

### 13.6. Giá trị null và collation

`UNIQUE(tenant_id,email)` có thể cho phép nhiều NULLs tùy DB. `email` nên `NOT NULL` nếu business yêu cầu. Nếu cần case-insensitive uniqueness, normalization/DB functional index/collation phải được test riêng; `A@example.com` và `a@example.com` có thể là trùng hay khác tùy policy/schema.

### 13.7. Đừng phân loại mọi `DataIntegrityViolationException` là duplicate email

Ứng dụng có thể vi phạm NOT NULL, FK hoặc CHECK. Kiểm tra SQLState/constraint name và root cause theo DB/provider để mapping chính xác sang “email đã dùng”. Với một lần exception ở transaction, rollback trước khi tiếp tục.

## 14. Bài test UNIQUE với hai threads và barrier

Một cách tổ chức:

```text
Worker A                       Worker B
--------                       --------
Tx A begin                     Tx B begin
SELECT exists -> false         SELECT exists -> false
signal checked A               signal checked B
wait ready                     wait ready
                |
         both checked
                |
allow INSERT A                 allow INSERT B
INSERT/commit A                INSERT/commit B
                |
         one winner
                |
      query committed rows
```

### 14.1. Một test outcome phù hợp

Nếu cả hai attempts cùng key và DB constraint đang enforce, kết quả mong đợi:

```text
successful commits = 1
duplicate-key failures = 1
rows(tenant,email) = 1
```

Không bắt buộc A thắng. Có thể database báo conflict ngay ở INSERT/flush hoặc commit, tùy generator, batching, constraint deferrability.

### 14.2. Đếm trạng thái commit, không đếm `persist` return

```java
em.persist(account);
// persist() return không có nghĩa committed.
```

Chỉ đánh dấu `committed=true` **sau khi `tx.commit()` hoàn tất thành công**.

### 14.3. Nếu một worker fail trước barrier

Coordinator nên timeout và propagate exception, không cho test vô hạn đợi đủ “hai pre-check thành công”. Ghi rõ failure phase: begin, query, barrier, insert, flush hay commit.

### 14.4. Không dùng global static email fixture

Một test chạy song song với test khác có thể dùng cùng `"test@example.com"` và gây unique violation không liên quan. Chọn namespace/tenant fixture riêng, reset schema có kiểm soát hoặc dùng dữ liệu ngẫu nhiên **chỉ để tạo identity**, rồi ghi nó vào diagnostics.

### 14.5. Cleanup tránh race với thread chưa kết thúc

Đừng xóa fixture ngay sau `Future.get` timeout khi worker còn đang chạy và giữ connection. Hủy/yêu cầu ngừng, chờ termination, rollback/close trong workers, rồi cleanup bằng transaction riêng.

## 15. Pessimistic locking: khóa row trước khi sửa

Optimistic locking cho phép nhiều reads rồi phát hiện xung đột khi write. Với contention cao hoặc một invariant cần quyết định dựa trên state mới nhất, có thể dùng **pessimistic locking**.

### 15.1. `PESSIMISTIC_WRITE`

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();
try {
    tx.begin();

    InventoryItem item = em.find(
        InventoryItem.class,
        itemId,
        LockModeType.PESSIMISTIC_WRITE);

    item.reserve(7);
    tx.commit();
} finally {
    if (tx.isActive()) tx.rollback();
    em.close();
}
```

Provider thường chuyển yêu cầu này thành SQL locking tương ứng, ví dụ PostgreSQL có thể sử dụng `SELECT ... FOR UPDATE`. Cách thực hiện cụ thể phụ thuộc DB/dialect và khả năng áp khóa.

### 15.2. Mục đích của test

```text
T1 lock row item #100
T2 try lock same row -> waits or times out
T1 commit/rollback -> releases lock
T2 acquires lock -> reads current state -> validates
```

Khác optimistic mode, T2 có thể **chờ trước khi đọc/sửa** hoặc nhận lỗi lock acquisition, tùy lock mode/query/isolation/timeouts.

### 15.3. Không kỳ vọng hai transactions cùng lock PESSIMISTIC_WRITE trên một row thành công ngay lập tức

Nếu DB thực hiện exclusive row locks, T2 không thể giữ cùng một exclusive lock tương thích với T1 khi T1 chưa release. Một test mà cả hai worker cố `find(... PESSIMISTIC_WRITE)` rồi chờ nhau ở barrier **sau** `find` rất dễ treo.

### 15.4. Mẫu đồng bộ cho test lock

- T1 bắt đầu transaction, acquire lock và phát `lockHeld.countDown()`.
- T2 đợi tín hiệu `lockHeld`, sau đó báo `aboutToAcquire.countDown()` và thực hiện locking find.
- Coordinator không chờ T2 báo `lockAcquired` trước khi cho T1 release; có thể kiểm tra T2 chưa hoàn thành trong một khoảng bounded, nhưng đây chỉ là evidence bổ sung về blocking.
- T1 commit và release.
- T2 tiếp tục, đọc state mới và xử lý.
- Hai transactions đóng resources.

### 15.5. Code skeleton

```java
CountDownLatch lockHeld = new CountDownLatch(1);
CountDownLatch aboutToLock = new CountDownLatch(1);
CountDownLatch releaseFirst = new CountDownLatch(1);

Callable<Void> first = () -> {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();
    try {
        tx.begin();
        em.find(
            InventoryItem.class,
            itemId,
            LockModeType.PESSIMISTIC_WRITE);
        lockHeld.countDown();

        if (!releaseFirst.await(10, TimeUnit.SECONDS)) {
            throw new TimeoutException("Release not received");
        }
        tx.commit();
        return null;
    } finally {
        if (tx.isActive()) tx.rollback();
        em.close();
    }
};

Callable<Void> second = () -> {
    if (!lockHeld.await(10, TimeUnit.SECONDS)) {
        throw new TimeoutException("First lock not acquired");
    }

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();
    try {
        tx.begin();
        aboutToLock.countDown();
        InventoryItem item = em.find(
            InventoryItem.class,
            itemId,
            LockModeType.PESSIMISTIC_WRITE);

        // T1 đã release trước khi T2 lock thành công
        // nếu DB dùng exclusive row-lock semantics.
        item.reserve(6);
        tx.commit();
        return null;
    } finally {
        if (tx.isActive()) tx.rollback();
        em.close();
    }
};
```

Coordinator (skeleton):

```java
Future<Void> a = pool.submit(first);
Future<Void> b = pool.submit(second);

assertTrue(aboutToLock.await(10, TimeUnit.SECONDS));
releaseFirst.countDown();

a.get(15, TimeUnit.SECONDS);
b.get(15, TimeUnit.SECONDS);
```

Trong ví dụ này T1 chỉ lock mà không sửa, nên T2 có thể reserve thành công sau T1 commit. Để kiểm tra **state mới sau lock**, cho T1 `reserve(7)` trước commit, rồi T2 cố reserve(6); T2 phải thấy stock=3 và từ chối. Cần releaseFirst trong `finally` của coordinator để test không treo nếu assertion/worker fail.

### 15.6. Không dùng thời gian làm correctness assertion duy nhất

Nếu `b.get(100ms)` timeout khi T1 giữ lock, điều đó có thể vì T2 chưa được scheduler chạy hoặc đang đợi JDBC connection. Kết hợp event markers, DB lock diagnostics nếu cần, outcome/data assertions và pool capacity phù hợp.

## 16. Lock timeouts và lock acquisition errors

Khi không muốn T2 chờ quá lâu, JPA có lock timeout hint:

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.lock.timeout", 500
);

InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE,
    hints);
```

Giá trị hint thường biểu diễn milliseconds theo Jakarta Persistence contract, nhưng mức hỗ trợ và khả năng áp chính xác phụ thuộc provider/dialect/JDBC/database. Test phải xác nhận trên DB thực.

### 16.1. Phân biệt các lỗi

- `LockTimeoutException`: JPA semantic lock timeout trong một số trường hợp, có thể chỉ statement rollback.
- `PessimisticLockException`: pessimistic lock failure có thể dẫn tới transaction rollback.
- `QueryTimeoutException`: statement timeout liên quan query execution, không nhất thiết chỉ row lock.
- `SQLTransientException`/vendor SQLState: DB-specific lock/deadlock failure.

Không khẳng định tất cả database luôn ném cùng một subclass hoặc cùng thời điểm.

### 16.2. Timeout từ `Future.get` không phải DB timeout

`future.get(5, SECONDS)` có thể timeout vì scheduling, pool starvation, lock wait hoặc deadlock; nó chỉ nói **test chưa nhận kết quả**. Để kết luận DB lock timeout, inspect thrown DB/JPA exception và SQLState/diagnostics.

### 16.3. `NOWAIT` và `SKIP LOCKED`

Một số DB/provider hỗ trợ khóa không chờ hoặc bỏ qua rows bị khóa. Đây thường là tính năng dialect/provider-specific, không mặc định portable. Test riêng behavior nếu job queue/worker allocation dựa vào `SKIP LOCKED`; đọc kết quả khác nhau không nhất thiết là lỗi.

### 16.4. Release lock khi rollback

Nếu T1 rollback, row-level locks do transaction giữ thường được release theo DB semantics. T2 có thể tiếp tục. Test cả case commit và rollback của holder khi cần.

### 16.5. Không dùng lock như mutex toàn ứng dụng

Pessimistic DB lock bảo vệ rows/keys mà DB lock manager quản lý, không tự khóa các cache entries, external services hoặc những logical invariants không gắn với rows đã khóa.

## 17. Optimistic và pessimistic locking: chọn test theo quyết định

| Tiêu chí | Optimistic `@Version` | Pessimistic `PESSIMISTIC_WRITE` |
|---|---|---|
| Khi đọc | Thường không lock write row ngay | Yêu cầu DB lock khi đọc/lúc query |
| Xung đột | Phát hiện khi update/flush/commit | Chờ/timeout/deadlock khi tranh khóa |
| Phù hợp | Ít contention, nhiều reads | Contention cao, cần serialization tại row |
| Failures | Optimistic conflict | Lock timeout/deadlock/transaction abort |
| Test chính | Hai bên đọc version N, chỉ một commit | Holder lock, waiter chờ/release |
| Chi phí | Retry logic | DB locks/connection wait |
| Rủi ro | Stale writes nếu thiếu version/bulk bypass | Deadlock, long waits, throughput giảm |

### 17.1. Cùng một invariant có nhiều giải pháp

Bài toán reserve stock có thể được bảo vệ bằng:

- Managed entity `@Version` và retry.
- `PESSIMISTIC_WRITE` trước khi trừ.
- Atomic conditional SQL update.

Mỗi giải pháp cần test concurrency riêng; không phải một cách duy nhất “đúng” cho mọi workload.

### 17.2. Test cần phản ánh chiến lược production

Nếu production sử dụng atomic SQL decrement, một test chỉ kiểm tra `@Version` của entity không chứng minh endpoint đúng. Test phải đi qua service/repository path đang được deploy.

## 18. Atomic conditional UPDATE: kiểm thử không bán quá số lượng

Với một số workloads, thay vì load entity rồi trừ, có thể dùng một SQL UPDATE có điều kiện:

```sql
UPDATE inventory_items
SET available_quantity = available_quantity - :requested,
    version = version + 1
WHERE id = :item_id
  AND tenant_id = :tenant_id
  AND available_quantity >= :requested;
```

Sau đó kiểm tra affected row count.

### 18.1. Vì sao atomic statement hữu ích?

Predicate `available_quantity >= :requested` được database đánh giá trong hoạt động UPDATE có atomicity/locking semantics của DB. Dưới những isolation/statement semantics phù hợp, hai concurrent updates không thể cùng giảm từ số hàng cũ nếu số dư không đủ cho cả hai; một update thường phải chờ rồi đánh giá trên state phù hợp hoặc thất bại/retry do serialization.

### 18.2. JPQL bulk update

```java
int updated = em.createQuery(
        "update InventoryItem i " +
        "set i.availableQuantity = " +
        "    i.availableQuantity - :requested, " +
        "    i.version = i.version + 1 " +
        "where i.id = :id " +
        "and i.tenantId = :tenant " +
        "and i.availableQuantity >= :requested")
    .setParameter("requested", amount)
    .setParameter("id", itemId)
    .setParameter("tenant", tenantId)
    .executeUpdate();
```

Nếu numeric `@Version` được increment tường minh như trên, bulk SQL có thể duy trì version semantics cho các managed-entity writers khác. Tuy nhiên JPQL bulk DML **không tự áp per-entity lifecycle callbacks/validation**, và persistence context đã load InventoryItem có thể stale. Chọn transaction boundary rõ, hoặc clear/refresh khi cần.

### 18.3. Kiểm thử đồng thời

Fixture: stock=10.

```text
Worker A: request reserve 7
Worker B: request reserve 6

Expected:
    affected rows A/B = (1,0) hoặc (0,1)
    committed stock = 3 hoặc 4
    never negative
    no oversold orders committed
```

Với DB isolation cao, một worker có thể gặp serialization error thay vì affected count=0. Test phải xác định policy: retry serialized operation trong transaction mới, rồi assert business invariant.

### 18.4. Row count là một phần transaction result

`executeUpdate()==1` chưa đồng nghĩa transaction commit thành công. Khi ứng dụng còn phải lưu `Order`/`Reservation` cùng transaction, chỉ đánh dấu reservation success sau khi toàn bộ unit-of-work commit. Nếu order insert fail và transaction rollback, stock decrement cũng phải rollback.

### 18.5. Tính idempotency

Client có thể retry cùng HTTP request sau network timeout. Nếu reserve action không có idempotency key/unique request ID, dù mỗi atomic UPDATE đúng, retry có thể trừ tồn kho **hai lần** khi stock vẫn đủ.

Đây là vấn đề khác race trên quantity. Test “hai requests cùng `requestId`” để bảo đảm chỉ một reservation business operation được ghi nếu API hứa idempotency.

### 18.6. Không giả định mọi bulk UPDATE hỗ trợ `RETURNING` portable

PostgreSQL `UPDATE ... RETURNING` có thể trả row/version mới, nhưng không thuộc portable JPQL bulk update; cần native SQL/driver framework và integration tests nếu dùng.

## 19. Isolation levels: hai transaction nhìn thấy dữ liệu thế nào?

Locking và isolation là hai trục liên quan nhưng không giống nhau.

### 19.1. Các mức phổ biến

| Isolation | Khả năng quan sát và bảo vệ theo SQL model |
|---|---|
| READ UNCOMMITTED | Có thể cho phép dirty reads theo DB; nhiều DB nâng hành vi thực lên READ COMMITTED |
| READ COMMITTED | Tránh đọc uncommitted; repeated reads có thể thấy dữ liệu khác |
| REPEATABLE READ | Bảo vệ một số non-repeatable reads; phantom/write-skew behavior tùy DB |
| SERIALIZABLE | Kết quả tương đương một thứ tự thực thi tuần tự nếu các transactions commit; có thể phải abort/retry |

Các hàng trên là **mô hình khái quát**; implementation khác nhau giữa PostgreSQL snapshot isolation, MySQL InnoDB, SQL Server row-versioning và Oracle. Không suy từ tên isolation level ra mọi lock/collision result mà không test target RDBMS.

### 19.2. JPA không có một property portable cho mọi isolation setting

JPA xử lý transactions/lifecycle/locking. Isolation thường được cấu hình qua DataSource/JDBC, transaction manager hoặc DB session defaults. Ví dụ Spring:

```java
@Transactional(
    isolation = Isolation.REPEATABLE_READ
)
public void operation() { /* ... */ }
```

Behavior phụ thuộc transaction manager, connection, datasource và DB support. Không gọi `setTransactionIsolation` trên connection bất kỳ giữa một transaction đã mở mà không hiểu framework.

### 19.3. Verify isolation thực tế

Với PostgreSQL:

```sql
SHOW transaction_isolation;
```

hoặc kiểm tra `java.sql.Connection.getTransactionIsolation()` trong đúng transaction/connection. Đừng mặc định Spring annotation đã đổi isolation nếu method bị self-invocation hoặc transaction cũ đang active và propagation là REQUIRED.

### 19.4. Bài test isolation cần hỏi câu cụ thể

Ví dụ “T1 SELECT số orders; T2 INSERT/COMMIT; T1 SELECT lại” để phát hiện non-repeatable/phantom observation. Cách test khác với “hai transactions cùng update một entity version”.

### 19.5. READ COMMITTED không tự ngăn lost update

Ở nhiều DB, một read-modify-write implementation không có version/lock/atomic predicate có thể ghi đè state đã được transaction khác cập nhật. Locking or version/conditional SQL phù hợp vẫn cần thiết.

## 20. Non-repeatable read: cùng EM, hai query có thể khác database snapshot

Một test giả định:

```text
T1 begin, SELECT item.quantity -> 10
T2 begin, UPDATE item.quantity -> 8, COMMIT
T1 SELECT item.quantity again -> ?
```

Ở READ COMMITTED, query thứ hai có thể thấy 8 trên DB. Nhưng **EntityManager L1 cache** có thể làm `em.find(Item,id)` lần hai trả chính managed instance cũ 10, không phát SQL.

### 20.1. Không nhầm persistence context caching với isolation

```java
InventoryItem first = emA.find(
    InventoryItem.class, itemId);
InventoryItem second = emA.find(
    InventoryItem.class, itemId);

assertSame(first, second);
```

JPA có thể không truy cập database cho lần find thứ hai, dù transaction isolation cho phép thấy committed data mới.

### 20.2. Dùng `refresh` một cách có chủ đích

```java
emA.refresh(first);
```

`refresh` yêu cầu provider reload state (theo transaction isolation hiện tại), giúp test quan sát DB. Tuy nhiên có thể làm mất những local unflushed changes trên entity và không được tùy tiện dùng trong business code.

### 20.3. `clear` và query độc lập

`emA.clear()` detach toàn bộ managed entities rồi `find` lại, nhưng transaction snapshot có thể vẫn không thấy T2 commit nếu isolation là REPEATABLE READ. Vì vậy:

```text
clear != change transaction isolation
refresh != bypass database snapshot rules
```

### 20.4. Thiết kế test cẩn trọng

Nếu mục tiêu là đo **database READ COMMITTED repeat-read behavior**, dùng JDBC SELECT scalar qua transaction A, hoặc clear/refresh có ý thức và xác minh SQL thật. Nếu mục tiêu là **JPA persistence context stale view**, dùng `find` cùng EM là một test khác.

### 20.5. Phân biệt snapshot và transaction

Một EntityManager có thể tồn tại lâu hơn một transaction; cách state giữ trong L1 cache và transaction begin/end có thể khiến giá trị đọc được khác một JDBC-only test. Các bài test concurrency phải xác định cả **context lifetime** và **transaction lifetime**.

## 21. Phantom reads: kiểm thử các rows xuất hiện mới

Tình huống:

```text
T1: SELECT COUNT(*) FROM orders WHERE status='PENDING' -> 5
T2: INSERT new PENDING order, COMMIT
T1: SELECT COUNT(*) same predicate -> ?
```

### 21.1. READ COMMITTED

T1 có thể thấy count=6 ở truy vấn thứ hai vì mỗi statement quan sát dữ liệu committed mới theo DB behavior.

### 21.2. REPEATABLE READ

Tùy DB, T1 có thể giữ snapshot và trả count=5. Không gán behavior duy nhất cho mọi RDBMS từ tên REPEATABLE READ.

### 21.3. Query aggregate không nhất thiết hit L1 giống `find`

`COUNT`/JPQL query thường thực thi SQL; EntityManager không tự trả toàn bộ kết quả aggregate từ managed entity cache. Tuy nhiên auto-flush, query cache (nếu bật) và transaction snapshot còn ảnh hưởng. Chọn test setup minh bạch.

### 21.4. Không dùng phantom test để chứng minh row update locking

Phantom/range predicate có những hành vi khác lost-update trên một row. Nếu business invariant là “tối đa 100 active bookings”, cần xem locking predicate/range, SERIALIZABLE hoặc aggregate counter DB constraint strategy, không chỉ optimistic version của từng booking entity.

### 21.5. Giữ transaction A thật sự mở

Nếu test gọi hai queries A ở hai transactions khác nhau, đó không phải repeat-read trong một transaction. Ghi rõ begin/end boundaries trong logs và tests.

## 22. Write skew: hai rows khác nhau, cùng vi phạm một invariant

`@Version` trên một row mạnh khi hai transactions cùng sửa **chính row đó**. Nhưng một business invariant có thể trải qua nhiều rows.

### 22.1. Ví dụ bác sĩ trực ca

```text
on_call_doctors
    Alice: on_call=true, version=1
    Bob:   on_call=true, version=1

Invariant: ít nhất một bác sĩ phải on_call.
```

Hai transactions:

```text
T1 đọc: Bob vẫn on_call -> cho phép Alice nghỉ
T2 đọc: Alice vẫn on_call -> cho phép Bob nghỉ

T1 update Alice.on_call=false, version=2
T2 update Bob.on_call=false, version=2

Mỗi transaction sửa một row khác nhau.
```

Kết quả nếu cả hai commit:

```text
Alice off
Bob off
Invariant bị phá
```

Mỗi row version check vẫn pass vì không có hai writers cùng sửa một row.

### 22.2. Vì sao đó không phải lost update đơn giản?

Không row nào bị ghi đè bởi update của transaction khác. Lỗi do hai transactions cùng đọc một **điều kiện tổng thể** rồi viết vào các rows khác nhau, tạo một state không được phép.

### 22.3. Cách kiểm thử

1. Seed hai rows on_call=true, commit.
2. T1 và T2 bắt đầu trong isolation đang khảo sát.
3. T1 đọc mọi on-call doctors, thấy count=2.
4. T2 cũng đọc count=2 trước khi bên nào write.
5. T1 set Alice off; T2 set Bob off.
6. Cả hai thử commit.
7. Reload bằng EM thứ ba, assert invariant còn đúng hoặc test cố tình chứng minh configuration hiện tại không bảo đảm.

### 22.4. Giải pháp

- SERIALIZABLE isolation và retry khi một transaction bị serialization abort.
- Khóa một row “guard”/parent shift hoặc khóa tất cả rows liên quan theo thứ tự ổn định.
- Chuyển invariant sang một counter/DB constraint model phù hợp.
- Thiết kế aggregate root có version chung khi mọi writers phải update cùng guard row.

Không tin `@Version` trên Alice và Bob tự bảo vệ điều kiện “ít nhất một người trực”.

### 22.5. PostgreSQL snapshot isolation

PostgreSQL REPEATABLE READ dùng snapshot isolation và có thể cho phép write-skew trong một số trường hợp; SERIALIZABLE có thể abort một transaction để duy trì serializability. Test trên RDBMS/version mục tiêu, không dùng kết quả H2 để suy rộng.

## 23. Serializable transactions và retry

SERIALIZABLE không có nghĩa mọi concurrent operations sẽ “cứ chờ đến lượt” rồi đều commit.

### 23.1. Có thể xảy ra serialization failure

Database có thể phát hiện không thể sắp xếp lịch thực thi thành một serial order hợp lệ và abort một transaction. PostgreSQL thường dùng SQLSTATE `40001` cho serialization failure; DB khác có mã/exception khác.

### 23.2. Retry **toàn bộ** transaction

Nếu transaction thất bại vì serialization conflict:

```text
begin new transaction
  -> reload source rows
  -> re-evaluate business invariant
  -> make updates
commit
```

Không chỉ retry câu SQL cuối với cached entity state cũ, và không tiếp tục context đã rollback-only.

### 23.3. Test retry policy

Test cần xác nhận:

- Conflict được nhận diện đúng.
- Retry có giới hạn số lần.
- Mỗi retry tạo transaction/EntityManager context mới.
- Business validation được chạy lại.
- External side effects không bị phát trùng.
- Kết quả cuối vẫn giữ invariant.

### 23.4. Retry và idempotency khác nhau

Retry transaction do serialization là phản ứng trước DB concurrency failure; idempotency là bảo vệ business action khi client/message gửi lại. Hai vấn đề có liên quan nhưng không thay nhau.

### 23.5. Không biến mọi lỗi thành serialization retry

UNIQUE violation do business key đã tồn tại, permission denied, invalid input và SQL syntax error thường không nên retry vô điều kiện. Cần phân loại failure.

## 24. Deadlock: hai transactions khóa tài nguyên theo thứ tự ngược

Ví dụ:

```text
T1: LOCK row A
T2: LOCK row B
T1: try LOCK row B -> wait for T2
T2: try LOCK row A -> wait for T1
```

Hai transactions tạo **chu trình chờ**. Database deadlock detector thường chọn một victim để rollback/reject operation.

### 24.1. Cách tạo test

- Seed row A và B đã commit.
- T1 `PESSIMISTIC_WRITE` row A, signal `lockedA`.
- T2 `PESSIMISTIC_WRITE` row B, signal `lockedB`.
- Khi cả hai signals đã tới, T1 cố lock B và T2 cố lock A.
- Chờ kết quả có timeout.
- Assert ít nhất một transaction bị deadlock abort theo DB semantics; transaction còn lại có thể tiến tiếp sau victim rollback.
- Cleanup và đọc trạng thái cuối.

### 24.2. Không đặt barrier sau second lock

Nếu mỗi thread chờ acquire second lock rồi mới đến barrier, cả hai có thể block trước barrier. Dùng barrier **sau first lock, trước second lock**.

### 24.3. DB victim không xác định

Không viết test mặc định “T2 luôn chết”; database có thể chọn T1 hoặc T2 làm deadlock victim. Nếu production handler retry deadlock victim, test assert invariant cuối và retry bounds.

### 24.4. Giảm deadlock bằng thứ tự khóa nhất quán

Nếu mọi business operations khóa A trước B theo tăng dần ID, cơ hội tạo chu trình giảm. Test có thể chạy hai requests với opposite business direction nhưng code vẫn lock theo sorted IDs, và assert cả hai hoàn thành mà không gây deadlock trong scenario đó.

### 24.5. Deadlock khác application-level barrier deadlock

DB deadlock có thể có SQLState/lock diagnostics, trong khi test bị kẹt vì `CountDownLatch` đặt sai không phải lỗi DB. Phân biệt bằng logs, thread dump, DB waiting sessions và phase markers.

### 24.6. Không tạo deadlock test trong production

Deadlock experiments nên chạy trên database test cô lập; chúng có thể gây rollback/locks và ảnh hưởng hệ thống nếu thực hiện trên live data.

## 25. Spring `@Transactional` trong test: những hiểu lầm nguy hiểm

Khi dùng Spring Data JPA, các phương thức repository/service thường chạy trong transaction do Spring quản lý. Kiểm thử concurrency cần đảm bảo **không vô tình dồn tất cả operations vào cùng một transaction**.

### 25.1. Test method có `@Transactional`

```java
@SpringBootTest
@Transactional
class InventoryServiceTest {

    @Test
    void test() {
        // ...
    }
}
```

Nhiều Spring test setups mặc định rollback transaction của test method khi kết thúc. Đó là tiện lợi với integration tests đơn giản, nhưng **không phải cách thích hợp để kiểm tra commit/visibility giữa các transactions** nếu không kiểm soát boundary.

### 25.2. Fixture uncommitted không được thread khác thấy

Nếu test tạo `InventoryItem` trong test transaction chưa commit rồi tạo worker thread gọi service `@Transactional`:

```text
Test thread Tx A: persist item, flush, not commit
Worker thread Tx B: find item -> may not see item
```

Thread mới không tự kế thừa Spring test transaction được bind vào thread gốc. Kiểm thử có thể fail vì fixture invisible, không phải vì version lock.

### 25.3. Worker thread không tự tham gia transaction của test thread

Spring transaction context trong mô hình thông thường gắn với thread. Nếu gọi service trong worker executor, service `@Transactional` có thể tạo một transaction khác. Điều này hữu ích để test concurrency, nhưng dữ liệu test setup/cleanup phải được commit và quản lý riêng.

### 25.4. Không nên đặt `@Transactional` ở mức test class cho concurrency tests một cách mặc định

Cho các tests muốn hai commits độc lập, có thể để test method **không** dùng wrapping test transaction, hoặc dùng Spring Test `TestTransaction`/`TransactionTemplate`/`@Transactional(propagation=NOT_SUPPORTED)` tùy context để tạo fixture và worker transactions rõ ràng.

### 25.5. `REQUIRES_NEW` có giới hạn

`Propagation.REQUIRES_NEW` suspend current transaction và bắt đầu một transaction khác khi được Spring proxy gọi đúng. Nhưng nếu gọi method nội bộ qua `this` (self-invocation) trong proxy mode, annotation có thể không có tác dụng.

### 25.6. Hai service objects không nhất thiết tạo hai transactions

Hai repository calls trong cùng thread cùng active transaction với propagation `REQUIRED` có thể tham gia **cùng transaction**, dù methods ở hai beans. Đừng đếm số gọi `@Transactional` như số transactions thực sự.

### 25.7. OpenEntityManagerInView không làm một test concurrency đúng hơn

Open Session/EntityManager in View có thể kéo dài persistence context trong web request nhưng không tự tạo transaction concurrency schedule. Với correctness tests, nên xác định service transaction boundaries độc lập.

## 26. Sử dụng `TransactionTemplate` để tạo transaction độc lập

Nếu không cần trực tiếp thao tác resource-local `EntityTransaction`, Spring `TransactionTemplate` giúp tổ chức transactions có kiểm soát.

### 26.1. Setup mẫu

```java
@Autowired
PlatformTransactionManager transactionManager;

@PersistenceContext
EntityManager em;

TransactionTemplate newTx() {
    TransactionTemplate template =
        new TransactionTemplate(transactionManager);
    template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    return template;
}
```

### 26.2. Hai threads, mỗi thread gọi transaction template

```java
Callable<Integer> reserveWork(
        Long itemId,
        int amount,
        CyclicBarrier loadedBarrier) {

    return () -> newTx().execute(status -> {
        InventoryItem item =
            em.find(InventoryItem.class, itemId);
        try {
            loadedBarrier.await(
                10, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        } catch (BrokenBarrierException
                 | TimeoutException e) {
            throw new IllegalStateException(e);
        }
        item.reserve(amount);
        return item.getAvailableQuantity();
    });
}
```

Ở đây `em` là Spring `@PersistenceContext` proxy có khả năng tìm EntityManager được bind với **transaction của worker thread**, không phải chia sẻ một raw application-managed EntityManager giữa threads. Điều kiện là Spring JPA transaction integration được cấu hình đúng.

### 26.3. Lưu ý propagation với test transaction

Ngay cả REQUIRES_NEW cũng cần connection pool đủ và parent test transaction không giữ fixture locks/resources. Nếu test thread giữ một uncommitted fixture, worker REQUIRES_NEW không đọc thấy nó.

### 26.4. Kết quả callback không đồng nghĩa transaction thành công trước `execute` trả về?

`TransactionTemplate.execute(...)` quản lý commit/rollback trước khi trả kết quả cho caller trong trường hợp bình thường. Một exception ở commit có thể propagate ra khỏi `execute`; test phải bắt đúng conflict type, không chỉ tin callback return.

### 26.5. Cách kiểm thử service thật

Nếu production business logic nằm trong `InventoryService.reserve(...)` được annotate `@Transactional`, ưu tiên gọi **service thật** trong hai worker threads (không tự write SQL bỏ qua service), để test xác minh authorization, retry và transaction rules đang được deploy.

### 26.6. Khi nào dùng resource-local helper?

Resource-local EM là cách minh họa rất rõ persistence context/transaction, phù hợp pure JPA tests. Với Spring-managed/JTA stacks, `TransactionTemplate` hoặc service proxy đáng tin cậy hơn việc tự `em.getTransaction()` trên container-managed EntityManager.

## 27. Spring Test `TestTransaction` và lifecycle fixture

Spring Test có `TestTransaction` để điều khiển test-managed transaction trong các trường hợp được hỗ trợ.

### 27.1. Tách fixture setup khỏi race

Một cách:

```text
Test-managed Tx:
    persist fixtures
    flagForCommit + end

Start worker transactions A/B:
    simulate race

Independent verification:
    query committed state

Cleanup:
    explicit transaction
```

### 27.2. Đừng rollback test transaction rồi tưởng undo worker commits

Một worker `REQUIRES_NEW` hoặc thread-bound transaction riêng có thể **commit thật**; rollback wrapper test transaction không rollback những commits đó. Teardown phải cleanup dữ liệu của worker transactions hoặc dùng ephemeral database/schema cho từng test.

### 27.3. Transaction boundary nên là một phần của test log

Ví dụ:

```text
seed tx committed id=100
worker-A tx begin
worker-B tx begin
worker-A read version=0
worker-B read version=0
worker-A tx committed
worker-B tx rollback optimistic conflict
verify tx read quantity=3
```

Các phase labels giúp phân biệt test bị lỗi do data setup, barrier, transaction annotation hay SQL.

## 28. Transaction propagation và self-invocation

### 28.1. Một annotation không đủ tạo boundary

```java
@Service
class InventoryService {

    public void run() {
        reserveInNewTransaction(); // this-call, no proxy dispatch.
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW)
    public void reserveInNewTransaction() {
        // ...
    }
}
```

Với Spring proxy-based transactions, lời gọi nội bộ cùng object có thể bypass interceptor nên **không** tạo transaction mới như mong đợi.

### 28.2. Cách sửa

- Gọi method trên một Spring bean proxy khác.
- Dùng `TransactionTemplate`/programmatic transaction boundary.
- Dùng AspectJ transaction weaving nếu kiến trúc chủ động cấu hình và test tương ứng.

### 28.3. Test bằng kết quả thực, không chỉ proxy count

Không đủ assert method `reserveInNewTransaction` được gọi. Kiểm tra transaction status, connection binding và committed DB outcome; một method được gọi không bảo đảm annotation đã được áp.

### 28.4. Transaction synchronization callbacks

Nếu service dùng `TransactionSynchronizationManager.registerSynchronization(...)` để phát event after commit, worker transaction riêng phải thực sự có synchronization active. Test concurrency không chỉ assert DB row mà có thể cần assert exactly-once outbox/event behavior.

## 29. Connection pool starvation và “giả deadlock”

Ví dụ pool size=1 nhưng hai transactions cùng cần connection:

```text
T1: get connection -> success
T1: wait for T2 read complete

T2: get connection -> blocked on pool
T2: never read, never signals
```

Test timeout nhưng **không phải** database deadlock hoặc lock conflict.

### 29.1. Quan sát pool metrics

HikariCP hoặc pool tương đương thường có active/idle/pending counts. Với một test hai concurrent DB transactions, xác nhận:

- Pool max size đủ.
- Test không giữ connection ngoài ý muốn trong coordinator.
- Migrations/health check không chiếm hết connections.
- Transaction B đã thực sự gửi SQL tới DB trước khi suy luận lock wait.

### 29.2. Tách pool wait với DB lock wait

Pool wait xảy ra trước khi có JDBC connection. DB lock wait xảy ra sau khi statement đã đến DB, chờ row/table lock. Các metric/stack traces/DB catalog giúp phân biệt.

### 29.3. Không tăng pool size như cách chữa mọi test

Nếu test dùng barrier sai sau locking statement, pool size=100 vẫn có thể treo. Kiểm tra choreography trước khi thay cấu hình.

### 29.4. Chạy tests song song có thể gây cạn pool

JUnit parallel execution nhiều testcases, mỗi case spawn nhiều workers, có thể đòi nhiều hơn pool max. Chọn isolation/resource limits phù hợp hoặc tắt parallelization cho nhóm contention tests nếu không có môi trường riêng.

### 29.5. Một worker giữ connection quá lâu

Long-running stream/transaction hoặc debug breakpoints có thể giữ DB locks. Đặt resource teardown và bounded await; tránh để một test lỗi làm hỏng suite kế tiếp.

## 30. Thread safety và transaction context

### 30.1. Không chia sẻ raw EntityManager

`EntityManager` không thread-safe. Mỗi task tự tạo và đóng EM hoặc sử dụng Spring proxy quản lý EM theo current transaction/thread.

### 30.2. Có thể chia sẻ EntityManagerFactory

`EntityManagerFactory` được thiết kế dùng chung và tạo nhiều EMs. Test thường bootstrap một factory cho một cấu hình persistence unit.

### 30.3. Không truyền managed entity giữa threads

Một managed entity object giữ reference tới graph của persistence context. Khi chuyển sang thread khác mà không đảm bảo lifecycle, bạn có thể đọc stale state, lazy-load không đúng context hoặc ghi đè ngoài ý muốn.

### 30.4. JPA thread-safe settings khác Java object thread safety

Ngay cả khi entity có `@Version`, bản thân Java object không trở thành thread-safe. Hai threads cùng thay field của **cùng một Java object** có data race trong Java memory model trước khi JPA/DB có cơ hội phát hiện.

### 30.5. Transaction contexts không tự truyền qua executor

Trong Spring thông thường, `@Transactional` không tự propagate vào thread của `CompletableFuture.supplyAsync` hoặc raw `ExecutorService`. Nếu worker cần transaction, tạo boundary trong worker bằng proxied service/transaction manager. Không cố clone ThreadLocal transaction state.

### 30.6. Security context cũng không tự truyền

Nếu concurrency test gọi service cần principal/tenant, thiết lập security context hợp lệ trong từng worker theo test framework hoặc truyền explicit, validated command context. Không dùng mutable global actor variable.

### 30.7. ThreadLocal cleanup

Nếu test manually sets tenant/security context, xóa trong `finally` sau task, tránh thread pool reuse làm tenant của task trước rò sang task sau.

## 31. L1 cache, L2 cache và quan sát stale state

JPA L1 cache là một phần của từng EntityManager. L2 cache (nếu bật) có thể được chia sẻ rộng hơn theo `EntityManagerFactory`.

### 31.1. L1 cache không chia sẻ giữa EM A/B

`emA.find(id)` và `emB.find(id)` trả các managed objects riêng; thay đổi trong A không tự cập nhật Java object trong B.

### 31.2. L2 cache có thể ảnh hưởng source của SELECT

Provider có thể dùng shared L2 cache để hydrate entity trong một transaction. Concurrency/invalidation/locking behavior phụ thuộc cache provider/strategy. Khi kiểm thử **DB isolation chính xác**, cần biết cache có bật không và quan sát SQL thật.

### 31.3. Không xem `em.clear()` là xóa shared L2 cache

`em.clear()` giải phóng state của L1 context. L2 cache có API evict riêng như `emf.getCache().evict(...)` nếu provider hỗ trợ. Test cần phân biệt mục tiêu: kiểm tra JPA cache consistency hay database transaction behavior.

### 31.4. Dùng verification context mới vẫn cần hiểu cache

Nếu mục tiêu chứng minh persisted DB value, một EntityManager mới **có thể** đọc từ L2 cache. Với test chuyên về DB outcome, có thể dùng direct JDBC query hoặc eviction/cache bypass hint, theo provider/config, để xác nhận physical row.

### 31.5. Không tắt cache vô điều kiện ở mọi test

Nếu production dùng L2 cache, hãy có ít nhất nhóm integration tests kiểm tra cache invalidation dưới concurrency. Tuy nhiên các tests cần cô lập DB isolation nên chạy với cache disabled/bypassed để không lẫn nguyên nhân.

### 31.6. Bulk update và L2 consistency

Bulk JPQL/native SQL có thể bỏ qua managed entity lifecycle và ảnh hưởng cache synchronization tùy provider. Test sau bulk writer nên xác nhận reload/cached readers không thấy stale state ngoài policy.

## 32. Test fixtures và dữ liệu độc lập cho mỗi test

### 32.1. Không dùng chung một business key không reset

Nếu hai testcases cùng dùng `(TENANT_A,SKU-RED)`, một test có thể làm hỏng fixture của test khác. Tạo ID/business key riêng hoặc reset DB/schema trước mỗi test.

### 32.2. Seed data phải commit

Không dựa vào test-managed transaction auto rollback trong Spring để tạo fixture visible cho workers; commit setup riêng trước khi bắt đầu concurrency scenario.

### 32.3. Cleanup phải đến sau workers

Chỉ xóa rows khi:

- Tất cả futures đã hoàn thành hoặc được canceled.
- Workers đã rollback/close.
- Không còn transaction giữ lock cần thiết.

### 32.4. Parallel JUnit tests

Nếu tests chạy parallel, cô lập theo schema/tenant/test prefix thay vì cùng truncate table. Một test cleanup bảng chung có thể xóa fixture test khác, tạo flaky failures.

### 32.5. Identity/sequence không bắt buộc reset về 1

Test nên giữ `Long id` do DB cấp, không hardcode ID=1 trừ khi fixture explicitly assigns. Sequence gaps do failed transactions có thể là bình thường.

### 32.6. Unique fixtures vs stress randomness

Randomized IDs giúp tránh collisions giữa tests, nhưng không được randomize business outcome assertions thành không dự đoán được. Dùng seed cố định khi cần tái lập một lịch, và log random seed nếu stress testing.

## 33. `OPTIMISTIC_FORCE_INCREMENT` và `PESSIMISTIC_FORCE_INCREMENT`

JPA có các lock modes yêu cầu tăng version của entity phù hợp dù transaction không thay đổi scalar state thông thường.

### 33.1. Lý do dùng force increment

Một aggregate root `PurchaseOrder` có version N, nhưng business operation chỉ thêm `OrderItem` trong child table. Nếu version parent không tăng theo mapping/provider, một concurrent command chỉ nhìn `PurchaseOrder.version` có thể không phát hiện collection mutation.

Một cách thiết kế là chủ động yêu cầu lock/version increment ở aggregate root:

```java
PurchaseOrder order = em.find(
    PurchaseOrder.class, orderId);

em.lock(
    order,
    LockModeType.OPTIMISTIC_FORCE_INCREMENT);

// Validate and modify aggregate children.
```

Semantics và thời điểm version increment phụ thuộc provider/JPA lifecycle; cần test thực tế rằng những concurrent operations dùng cùng aggregate root version không thể đều commit trên bản cũ.

### 33.2. `PESSIMISTIC_FORCE_INCREMENT`

```java
em.lock(
    order,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT);
```

Kết hợp yêu cầu pessimistic lock và version increment theo JPA rules khi entity/version support cho phép. Không cần cho mọi update; dùng khi aggregate concurrency contract đòi hỏi.

### 33.3. Force increment không tự khóa mọi child tables

Version của parent là một concurrency guard nếu **mọi writers tuân thủ protocol**. Một JDBC job thêm item nhưng không cập nhật/check parent version có thể phá giả định. Test cả các đường ghi ngoại lệ.

### 33.4. Kiểm thử

Tạo hai transactions đọc cùng parent version; mỗi bên thêm child khác nhau và yêu cầu force increment parent. Assert không có cả hai commits thành công nếu business yêu cầu exclusive aggregate edit. Sau conflict, reload và xác nhận số child rows.

### 33.5. Lock mode không được hỗ trợ trên mọi mapping

Versionless entities, provider capabilities, DB dialect và lock mode validity khác nhau. Có thể gặp `PersistenceException`/`UnsupportedOperationException` hoặc các lỗi tương ứng. Chọn test với mapping/version phù hợp, không tùy tiện force version trên entity không có version.

## 34. Pessimistic lock scope và association graph

`PESSIMISTIC_WRITE` trên parent không luôn đồng nghĩa database khóa **mọi row con**.

### 34.1. Mục tiêu “khóa aggregate”

Với:

```text
PurchaseOrder(id=10, version=3)
  |- OrderItem(id=101)
  |- OrderItem(id=102)
```

Nếu transaction A lock PurchaseOrder, một transaction B có thể vẫn update OrderItem#101 qua SQL trực tiếp nếu DB không có cơ chế lock xung đột trên row con hoặc protocol riêng.

### 34.2. `jakarta.persistence.lock.scope`

JPA có lock scope hints/`PessimisticLockScope` để mô tả khóa pessimistic trên một số relationships theo spec/provider. Phạm vi vật lý, join tables/owned collections và hỗ trợ DB khác nhau; đừng giả định `EXTENDED` luôn khóa toàn bộ graph tùy ý.

### 34.3. Test đúng invariant

Nếu application hứa “chỉ một transaction được chỉnh bất cứ child nào trong Order #10”, hãy test:

1. A lock parent.
2. B cố update child through actual service.
3. Xác nhận B chờ/abort/concurrency guard như contract.
4. Reload parent/children sau commit.

### 34.4. Chọn một concurrency protocol nhất quán

Một protocol khả thi:

```text
Every command modifying aggregate children:
    lock parent first
    validate parent state
    modify children
    commit
```

Đường ghi nào bỏ lock parent có thể bypass policy. Test API, scheduled jobs và bulk updates cùng protocol.

### 34.5. Lock order

Nếu command cần lock nhiều parent rows, lock theo thứ tự deterministic IDs để giảm deadlock. Test hai requests thao tác A→B và B→A nhưng khóa theo sorted order.

## 35. Flush mode có thể làm thay đổi thời điểm xảy ra conflict

### 35.1. `FlushModeType.AUTO`

JPA có thể flush trước query để đảm bảo consistency phù hợp. Nếu test chờ optimistic error ở commit nhưng giữa chừng gọi một JPQL query, exception có thể xuất hiện sớm hơn.

### 35.2. `FlushModeType.COMMIT`

Provider có thể trì hoãn synchronization tới commit. Nhưng không nên dựa vào “không có SQL trước commit trong mọi tình huống”, vì identity generation/callbacks/provider specifics.

### 35.3. Test phải bao trùm cả operation phase

Một helper:

```java
try {
    item.reserve(amount);
    em.flush();
    tx.commit();
} catch (RuntimeException failure) {
    // Classify and rollback.
}
```

Chỗ phát exception có thể là `flush` hoặc `commit`. Không chỉ wrap riêng `em.flush()` trong `assertThrows` nếu DB deferred constraint chỉ fail ở commit.

### 35.4. Auto flush trước pre-check

Nếu test đã thay pending state trong cùng EM rồi gọi `existsBy...`, JPA có thể auto flush. Điều này có thể làm thay đổi lock/visibility schedule. Trong test race, xác định rõ **khi nào mutate managed entity** và **khi nào gọi query có thể auto-flush**.

### 35.5. Không chỉnh flush mode để “che” lỗi

Đổi flush mode nhằm làm test pass không sửa incorrect concurrency contract. Hãy chọn flush mode phù hợp use case và assert exception timing linh hoạt theo spec/provider.

## 36. Kiểm thử race với business side effects

Một transaction đặt hàng có thể gồm:

```text
reserve stock
insert order
insert order items
insert payment intent
insert outbox event
commit
```

### 36.1. Một transaction fail phải rollback toàn bộ DB state

Nếu transaction B reserve thất bại vì version conflict hoặc insufficient stock, assert:

- Không có committed order của B.
- Không có item rows của B.
- Không có outbox event “OrderConfirmed” của B.
- Không có stock decrement của B.

### 36.2. External side effects không nằm trong DB transaction

Nếu service gửi email/webhook/payment gateway request trước DB commit, optimistic conflict ở commit có thể tạo email/order charge sai. Kiểm thử cần xác minh external side effect chỉ phát theo transaction outcome, dùng transactional outbox/after-commit mechanisms và idempotency phù hợp.

### 36.3. Retry event cần idempotency

Một event consumer có thể nhận cùng `OrderConfirmed` hai lần. Database UNIQUE request key/event ID giúp tránh trừ stock hai lần. Test concurrent retries/duplicates chứ không chỉ một worker xử lý event.

### 36.4. Ràng buộc giữa nhiều rows

Nếu transaction update InventoryItem và tạo Reservation riêng, một uniqueness constraint trên `reservation_request_id` có thể bảo vệ exactly-once business action khi client retry. Chọn số lượng affected rows/record count làm correctness asserts.

### 36.5. Không chỉ assert quantity

Trong một lỗi ghi trùng order, stock có thể vẫn không âm nhưng customer bị charge hai lần. Kiểm thử phải xét **toàn bộ business invariant** chứ không chỉ một column.

## 37. Concurrency và quan hệ nhiều-nhiều

Hai EntityManagers cùng sửa `@ManyToMany` associations có thể gây duplicate links, lost changes hoặc constraint conflicts.

### 37.1. Ví dụ

```text
T1: load User.roles -> [USER]
T2: load User.roles -> [USER]

T1: add SUPPORT
T2: add AUDITOR
```

Kết quả mong muốn theo domain có thể là `[USER,SUPPORT,AUDITOR]`, nhưng cơ chế lưu join table, collection ownership, version và concurrency protocol quyết định outcome thực.

### 37.2. Parent version không mặc định bảo vệ mọi collection updates

JPA provider có thể tăng version khi owning collection thay đổi theo mapping, nhưng hành vi cụ thể với inverse side, join table và native updates cần được kiểm chứng. Nếu cần merge concurrent membership changes, chọn protocol rõ (parent version/lock/atomic insert constraint).

### 37.3. Unique pair trong join table

```sql
UNIQUE (user_id, role_id)
```

ngăn duplicate exact membership rows, nhưng không ngăn một transaction xóa role mà transaction khác vừa thêm nếu application thay toàn bộ collection snapshot thiếu concurrency control.

### 37.4. Orphan removal trong concurrency

Hai writers cùng sửa child collections với `orphanRemoval=true` có thể vô tình xóa child mới được thêm nếu merge stale detached graph. Test bằng hai EM độc lập, kiểm tra child rows sau commit/retry và không merge graph nguyên từ client.

### 37.5. Test membership update bằng DB state

Không chỉ assert Java `Set.size()` trong mỗi EM; một EM có thể giữ stale collection snapshot. Reload join table/entity graph trong context mới sau khi transactions hoàn tất.

## 38. Soft delete, uniqueness và concurrent restores

Business key có thể chỉ unique trong các rows đang active:

```text
tenant_id, sku, deleted_at
```

### 38.1. Partial unique index

PostgreSQL:

```sql
CREATE UNIQUE INDEX ux_products_active_sku
ON products (tenant_id, sku)
WHERE deleted_at IS NULL;
```

Hai transactions cùng restore hai archived rows có cùng tenant+SKU: chỉ một should succeed nếu policy yêu cầu active uniqueness.

### 38.2. Bài kiểm thử

1. Tạo hai rows archived cùng key, commit.
2. A/B hai EM độc lập load từng row archived.
3. Barriers đảm bảo cả hai quyết định restore trước write.
4. A/B set `deletedAt=null` rồi commit cạnh tranh.
5. Assert một commit thành công; row active count cho key == 1.

### 38.3. Không dùng `UNIQUE(tenant,sku,deleted_at)` thay partial unique một cách máy móc

NULL semantics có thể khiến nhiều active rows (`deleted_at=NULL`) không conflict trên DB mà NULLs được coi distinct. Đây là DB-specific uniqueness behavior cần test.

### 38.4. Temporal uniqueness là yêu cầu domain

Nếu business cho phép tái sử dụng SKU ở bản ghi đã xóa, schema constraints và application restore/create policy phải cùng bảo vệ race. Không dựa vào pre-check count trước restore.

## 39. Kiểm thử multiple tenants cùng business key

`UNIQUE(tenant_id,sku)` có hai mục tiêu:

- **Không** cho hai records cùng key trong một tenant.
- **Cho phép** hai tenants khác nhau dùng cùng SKU nếu requirement là tenant-local uniqueness.

### 39.1. Hai concurrency tests riêng

**Same tenant**:

```text
A inserts (TENANT_A, SKU-RED)
B inserts (TENANT_A, SKU-RED)
Expected: one committed
```

**Different tenants**:

```text
A inserts (TENANT_A, SKU-RED)
B inserts (TENANT_B, SKU-RED)
Expected: both committed
```

### 39.2. Concurrency không thay authorization

Tenant isolation phải được enforce ở resource queries và references. Một test duplicate key cross-tenant pass không chứng minh user A không thể update item của tenant B.

### 39.3. Case normalization

Nếu SKU uniqueness case-insensitive, hai concurrent writes `sku-red` và `SKU-RED` cần được coi như trùng theo business policy. DB collation/normalized index và test phải thống nhất.

## 40. JPA bulk UPDATE và optimistic version

JPQL bulk updates:

```java
em.createQuery(
    "update InventoryItem i " +
    "set i.availableQuantity = :qty " +
    "where i.id = :id")
  .setParameter("qty", 5)
  .setParameter("id", itemId)
  .executeUpdate();
```

không tự quản lý entity version/lifecycle giống managed entity update.

### 40.1. Rủi ro

Nếu một EM khác đã load InventoryItem version=3, bulk update mà không increment version có thể thay DB quantity sang 5 nhưng vẫn giữ version=3. EM cũ update tiếp có thể pass version check và overwrite.

### 40.2. Test minh họa

```text
T1 load item version=3
T2 bulk UPDATE quantity=5 (version remains 3), COMMIT
T1 update quantity=7 and COMMIT

Expected if protocol broken:
T1 may overwrite T2 because version unchanged.
```

Đây là testcase để **phát hiện lỗi kiến trúc**, không phải behavior mong muốn. Đặt invariant/expected failure theo mục tiêu của project và test provider thực.

### 40.3. Sửa bằng versioned conditional bulk update

```java
int affected = em.createQuery(
    "update InventoryItem i " +
    "set i.availableQuantity = :qty, " +
    "    i.version = i.version + 1 " +
    "where i.id = :id " +
    "and i.version = :expectedVersion")
  .setParameter("qty", 5)
  .setParameter("id", itemId)
  .setParameter("expectedVersion", version)
  .executeUpdate();
```

Xử lý 0 affected rows như conflict/stale state; clear/refresh context theo transaction design.

### 40.4. Native SQL và database triggers

Một external JDBC/native writer phải tuân thủ protocol tương tự hoặc DB-level guard nếu invariant cần bảo vệ. `@Version` ở Java không tự áp lên SQL writers ngoài JPA.

### 40.5. Không xem bulk DML là “nhanh hơn nên an toàn hơn”

Bulk SQL có thể giảm số round trips nhưng bypass callbacks, dirty checking, entity cache sync và domain methods. Concurrency tests phải đi qua đúng write path và kiểm tra hậu quả.

## 41. Chẩn đoán một concurrency test thất bại

Một lỗi `TimeoutException` không đủ nói transaction bị deadlock. Cần biết test đang đứng ở giai đoạn nào.

### 41.1. Ghi dấu các phase

```text
[A] transaction begin
[A] before SELECT
[A] after SELECT: quantity=10 version=1
[A] ready at barrier
[B] transaction begin
[B] after SELECT: quantity=10 version=1
[B] ready at barrier
[A] before UPDATE/commit
[B] before UPDATE/commit
[A] transaction committed
[B] optimistic conflict, rollback completed
[TEST] verified quantity=3 version=2
```

Từ timeline, ta xác định được cả hai đã đọc cùng state hay chưa, bên nào bị blocked và exception xuất hiện ở bước nào.

### 41.2. Log transaction/resource identity

Có thể ghi worker label, Java thread name, transaction ID/session ID ở DB khi được phép và có API hỗ trợ. Không dùng Java `Thread.currentThread().getId()` làm bằng chứng hai SQL statements thuộc hai DB transactions.

### 41.3. Xem SQL và parameters có kiểm soát

Log SQL UPDATE với version predicate và timing để biết lỗi do optimistic rowcount hay DB lock. Tránh log PII/password/access tokens. Với high-volume tests, giới hạn log output để không che root cause.

### 41.4. Phân biệt các loại waiting

| Hiện tượng | Nguồn chờ | Cách kiểm chứng |
|---|---|---|
| Worker đợi barrier | Java synchronization | Thread dump/phase labels |
| Worker đợi connection | JDBC pool | Pool pending/active metrics |
| SQL đợi row lock | Database | DB session wait/lock views |
| SQL đang scan chậm | Database execution | EXPLAIN/statement stats |
| Transaction đợi commit | Flush/deferred constraints/DB | Transaction logs/SQLState |
| Future bị timeout | Test coordinator | Worker phase/exception context |

### 41.5. PostgreSQL: quan sát active sessions

Trên **test database**:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers,
    query
FROM pg_stat_activity
WHERE datname = current_database();
```

`pg_blocking_pids` và các fields mô tả DB blocking relationships, nhưng quyền xem query text/session details phụ thuộc DB role. Không chạy thao tác kill session bừa bãi, và không ghi sensitive SQL text vào logs công khai.

### 41.6. PostgreSQL: xem locks

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE database = (
    SELECT oid
    FROM pg_database
    WHERE datname = current_database()
)
ORDER BY pid, granted, relation_name;
```

View này giúp xem một số locks và sessions, nhưng row-level lock waits không nhất thiết được hiển thị như một hàng `tuple` lock trực quan; có thể chờ transaction ID lock. Dùng `pg_blocking_pids`, query progress và provider SQL cùng nhau.

### 41.7. MySQL/SQL Server/Oracle

Mỗi DB có catalog/session views và deadlock tracing riêng. Không dùng SQL PostgreSQL nguyên văn trên MySQL/InnoDB, SQL Server hay Oracle; cùng JPA mapping vẫn có thể cho lock timings khác nhau.

### 41.8. Giữ nguyên root exception

Nếu một worker ném SQL exception, giữ cause chain trong `ExecutionException.getCause()` hoặc propagated exception. Không catch rồi trả false không có thông tin; test sẽ không phân biệt optimistic conflict với network timeout.

### 41.9. Cẩn thận khi điều tra bằng debugger

Một breakpoint ở thread giữ lock có thể khiến worker khác timeout hoặc deadlock, làm behavior thay đổi. Sử dụng logs/trace points và timeout lớn hơn phù hợp khi debug thủ công trên DB test.

## 42. Thiết kế test chống flaky

Concurrency tests vốn nhạy scheduler và DB timing, nhưng vẫn có thể được thiết kế **ổn định, có chẩn đoán và tái lập**.

### 42.1. Đồng bộ đúng sự kiện

Đừng ngủ cố định để “đợi transaction A”. Đặt latch ngay **sau** event A đã hoàn tất: row loaded, lock acquired, tx committed.

### 42.2. Điều khiển tối thiểu lịch cần thiết

Muốn chứng minh lost update? Chỉ cần cả hai cùng đọc base version trước writes. Không cần bắt A luôn chạy trước B. Muốn chứng minh lock blocking? Cần A giữ lock trước khi B thử lock.

### 42.3. Không đòi thứ tự winner không có business meaning

Nếu hai concurrent actions đối xứng, assert:

```text
committedCount == 1
failedCount == 1
persistedInvariant holds
```

không assert cứng “A phải thắng”.

### 42.4. Tất cả waits có timeout

`CountDownLatch.await`, `CyclicBarrier.await`, `Future.get` và connection/statement lock waits cần bounded waiting phù hợp. Bất kỳ nơi nào worker chờ vô hạn đều có thể làm CI treo.

### 42.5. Release latch trong `finally` của coordinator

Nếu một assertion fail trước khi `release.countDown()`, worker holder có thể kẹt. Đặt một đoạn cleanup giải phóng latches và shutdown executor dù test thành công hay không.

### 42.6. Không kết thúc test khi futures còn đang ghi DB

Sau timeout, yêu cầu cancel/interrupt, đồng thời chờ worker cleanup và close resources; JDBC cancellation không luôn tức thời. Nếu không thể chờ an toàn, isolation bằng DB container riêng giúp loại bỏ side effects sau suite.

### 42.7. Sử dụng test database nhất quán

H2 hoặc SQLite in-memory có thể serialize writes khác PostgreSQL production. Chọn database tương đương deployment cho correctness tests về locks/unique constraints/isolation.

### 42.8. Không lạm dụng isolation SERIALIZABLE để làm mọi test pass

Nếu production dùng READ COMMITTED, test chỉ chạy SERIALIZABLE sẽ che lost update mà deployment có thể gặp. Cấu hình test theo môi trường thực, hoặc lập explicit tests cho isolation migration.

### 42.9. CI load không phải lỗi business

Timeout pool/cpu contention trên CI có thể làm một test fail, nhưng không đồng nghĩa database concurrency bug. Report rõ loại timeout, đo worker phases, chọn reasonable timeouts và resources; không giải quyết bằng cách xóa assertion correctness.

### 42.10. Stress tests là lớp bổ sung

Một stress test với 100 threads/10.000 operations tăng xác suất phát hiện race, nhưng nếu fail ngẫu nhiên khó tái lập, cần seed/lịch/log. Dùng deterministic tests cho các interleavings đã biết, stress tests cho coverage lịch thực thi rộng hơn.

### 42.11. Đảm bảo assertion đọc committed state

Kiểm tra từ EM mới/JDBC connection sau completion. Nếu đọc từ EM B đã cache row cũ, test có thể báo quantity=10 dù DB quantity=3.

### 42.12. Không dùng local JVM lock để che DB race

`synchronized` trên một service instance trong test có thể tuần tự hóa requests và làm mọi race “pass”, nhưng production chạy nhiều JVM/pods không chia sẻ lock đó. Cần DB-level concurrency protocol nếu invariant liên quan shared database.

## 43. Một mẫu kết quả có thể tái lập

Thay vì log thô 1.000 dòng, báo cáo outcome rõ:

```yaml
scenario: optimistic_reservation
database: postgres-test
baseQuantity: 10
requested:
  workerA: 7
  workerB: 6
bothReadInitialState: true
attempts:
  workerA: committed
  workerB: optimistic_conflict
finalQuantity: 3
finalVersionIncremented: true
invariantPreserved: true
transactionResourcesClosed: true
```

Đây là **mẫu định dạng minh họa**, không phải file output bắt buộc của dự án. Không cần biết thread nào chạy trước ở mọi millisecond; cần biết hành vi được kiểm chứng.

### 43.1. Phân biệt status test

| Status | Nghĩa |
|---|---|
| PASSED | Business invariant và expected conflict/success pattern đúng |
| FAILED_CORRECTNESS | Hai commits tạo state sai |
| FAILED_UNEXPECTED_EXCEPTION | SQL/transaction error ngoài contract |
| FAILED_TIMEOUT | Không hoàn thành trong bounded time; chưa biết root cause |
| FAILED_SETUP | Fixture không visible, schema/connection sai |
| INCONCLUSIVE | Chưa tạo được required concurrency interleaving |

Không biến FAILED_TIMEOUT thành PASSED chỉ vì một worker “có vẻ đang bị khóa”; cần quan sát thực.

### 43.2. Thu thập version/row-count outcome

Trong optimistic test, ghi baseVersion, committedVersion, quantity cuối và conflict category. Trong unique test, ghi số commits, số DB rows, và constraint name. Trong pessimistic test, ghi lock acquisition/release phases.

### 43.3. Phiên bản test DB/provider

Khi nâng JDBC driver, Hibernate hoặc DB version, timing/exceptions/locking strategies có thể đổi. Lưu version metadata trong test report để debug regressions, không hardcode assertion vào một exception string không ổn định.

## 44. Các bẫy thường gặp và cách nhận diện

| Hiện tượng | Suy luận sai | Nguyên nhân cần kiểm tra |
|---|---|---|
| Hai EntityManagers cùng đọc object | “Hai transactions độc lập chắc chắn” | Transaction boundary chưa được thiết lập |
| `emA.find` và `emA.find` trả cùng object | “JPA có lỗi cache” | Đó là L1 identity map đúng |
| Thread B không thấy fixture | “Isolation quá mạnh” | Fixture chưa commit trong test thread |
| Test treo tại barrier | “DB deadlock” | Một thread đang block trước barrier |
| Test treo tại getConnection | “PESSIMISTIC_WRITE block” | Connection pool starvation |
| `persist` không ném lỗi | “INSERT committed” | SQL/constraint ở flush/commit |
| `flush` thành công | “Transaction đã thành công” | Deferred checks/commit còn có thể fail |
| Optimistic test fail không đúng type | “JPA không hỗ trợ @Version” | Provider wrapper/isolation serialization behavior |
| Hai writes cùng thành công | “@Version sai” | Hai transactions không đọc cùng version hoặc update không cùng row |
| Bulk UPDATE không tăng version | “Đó là mặc định an toàn” | Bulk DML bypass version management |
| Pessimistic holder release mà waiter vẫn fail | “Lock vô ích” | Waiter timeout/transaction aborted/pool problem |
| UNIQUE duplicate race pass trên local | “Production cũng an toàn” | Local schema auto-generated khác migration production |
| Query sau update đọc old value | “DB commit không có tác dụng” | L1/L2 cache/stale transaction snapshot |
| Hai users cùng sửa children không conflict | “Parent @Version bảo vệ mọi thứ” | Child writes không bump parent version |
| Deadlock victim cố định trong test | “T2 luôn rollback” | DB chọn victim không xác định |
| JUnit `@Transactional` test tự rollback | “Các worker commits cũng rollback” | Worker transactions độc lập vẫn commit |
| ThreadLocal actor/tenant sai | “Repository tự biết tenant” | Security context không propagate/cleanup |
| Stress test pass 1000 lần | “Không bao giờ race” | Không thể chứng minh không có interleaving khác |
| Unique violation nhưng có 2 rows | “Constraint enforce rồi” | Constraint chưa đúng scope/database |
| Stock không âm nhưng 2 orders charge | “Business transaction an toàn” | Thiếu idempotency/transaction atomicity |

## 45. Bộ ca kiểm thử concurrency nên có trong một dự án JPA

| Mã | Scenario | Setup | Expected invariant |
|---|---|---|---|
| C01 | Hai EM độc lập | Cùng PK/version | Hai Java instances, hai contexts |
| C02 | Optimistic conflict | Hai reads version N | Một commit, stale write rollback |
| C03 | Retry after optimistic | Stock 10; reserve 7 và 6 | Retry re-evaluates insufficient stock |
| C04 | Pessimistic wait | T1 lock row | T2 không vượt lock trước release |
| C05 | Lock timeout | T1 giữ lock lâu có giới hạn | T2 nhận expected lock error |
| C06 | UNIQUE race | Hai inserts cùng tenant/email | Một row committed |
| C07 | Cross-tenant unique | Cùng SKU, tenant khác nhau | Cả hai rows hợp lệ |
| C08 | Soft delete restore | Hai archived cùng SKU | Active count tối đa một |
| C09 | Read committed visibility | T2 commit giữa hai reads | Theo DB snapshot contract |
| C10 | Write skew | Hai rows cùng bảo vệ invariant | Invariant giữ nhờ serializable/guard |
| C11 | Deadlock | Lock A→B và B→A | Victim rollback, no partial write |
| C12 | Lock order | Both operations lock sorted IDs | No deadlock in scenario |
| C13 | Atomic decrement | Two quantities > stock when summed | No oversell |
| C14 | Duplicate client request | Same request ID | One business reservation |
| C15 | Bulk update version | External writer và managed entity | Version protocol not bypassed |
| C16 | Collection edits | Two users add/remove children | No lost intended membership |
| C17 | Audit/outbox rollback | One transaction conflicts | No false success event |
| C18 | Test fixture isolation | Tests run parallel | No cross-test interference |
| C19 | L2 cache invalidation | Writer commits, reader reloads | Cache policy respected |
| C20 | Pool pressure | 2 concurrent Tx | No fake deadlock from pool |

### 45.1. Ưu tiên theo rủi ro

Không cần viết đủ 20 cases cho một CRUD app nhỏ. Chọn những invariants có hậu quả lớn: tiền, kho, quyền, booking, issuance of unique numbers, order state transitions. Một bài test đúng trên unique constraint hoặc stock reserve có giá trị hơn nhiều stress test không assert nghiệp vụ.

### 45.2. Kiểm thử API path thực tế

Repository-level tests bảo vệ DB semantics. Service/API integration tests còn kiểm tra transaction annotation, authorization, retry, idempotency và error mapping. Với concurrency bug từng xảy ra ở production, ưu tiên tái hiện chính write path đó.

### 45.3. Test deletion/cascade concurrency nếu có

Nếu một thread xóa parent còn thread khác thêm child, cần xem FK, cascade `REMOVE`, orphanRemoval và transaction outcome. Invariant có thể là “không có orphan child” hoặc “không được tạo child dưới deleted parent”. Thử trên DB với foreign keys thực.

## 46. Bài tập thực hành

### Bài 1 — Hai persistence contexts

Tạo hai EntityManagers từ cùng EntityManagerFactory, dùng cả hai tìm cùng `InventoryItem#100`. Assert hai Java objects không phải cùng reference nhưng có cùng ID và version. Giải thích vì sao cần hai EM để mô phỏng hai clients.

### Bài 2 — Seed fixture đã commit

Viết helper tạo một InventoryItem stock=10 trong transaction riêng, commit và đóng EM. Sau đó tạo EM khác đọc lại. Thử thay `commit` thành `flush` mà không commit; nêu outcome visibility phụ thuộc isolation/DB.

### Bài 3 — Optimistic conflict deterministic

Hai EM đọc version N trước khi writes; A reserve 7 rồi commit; B reserve 6 từ snapshot cũ. Assert B conflict và DB stock cuối bằng 3. Không hardcode initial version=0.

### Bài 4 — Một test cố ý không có `@Version`

Thử loại bỏ version mapping trong một setup thử nghiệm cô lập rồi tái hiện read-modify-write. Quan sát lost update trên DB/isolation đang dùng và giải thích vì sao kết quả có thể khác nếu DB áp serialization/retry.

### Bài 5 — Đặt barrier sau khi load

Dùng `CyclicBarrier(2)` để chắc cả A/B load cùng stock=10 trước reserve. Assert một commit và một optimistic conflict; không hardcode worker nào thắng.

### Bài 6 — Không dùng `Thread.sleep`

Thay một test đang dùng `Thread.sleep(200)` để đoán T2 đã read bằng `CountDownLatch` báo `afterRead`. Đặt bounded timeout và propagation exceptions.

### Bài 7 — Test tránh false positive

Trong worker catch mọi RuntimeException rồi trả false. Thiết kế helper phân biệt `OptimisticLockException`/provider wrapper với `ConnectionException`/SQL error. Assert false chỉ khi conflict mong đợi.

### Bài 8 — Verify DB state bằng context mới

Sau khi A commit, B còn giữ L1 cache stock=10. So sánh `emB.find` với một EM thứ ba. Nếu L2 cache enabled, thiết kế direct JDBC verification hoặc cache bypass để kiểm tra physical row.

### Bài 9 — UNIQUE race

Tạo `CustomerAccount` có UNIQUE(tenant_id,email). Hai transactions cùng pre-check email chưa tồn tại, rồi cùng insert. Assert một commit success, một duplicate-key failure và DB có một row.

### Bài 10 — Unique không tồn tại trong production schema

Để annotation `@UniqueConstraint` trong entity nhưng cố tình bỏ DB constraint trong một test DB riêng. Chạy same-key insert test và quan sát vì sao cả hai có thể commit; giải thích giới hạn của annotation.

### Bài 11 — Case-insensitive email

Hai concurrent requests tạo `User@Example.com` và `user@example.com`. Với yêu cầu business case-insensitive, chọn normalized column hoặc DB expression unique index; test đúng semantics trên database mục tiêu.

### Bài 12 — Pessimistic write lock

T1 lock item bằng `PESSIMISTIC_WRITE`, T2 chạy trong thread khác cố lock cùng row. Thiết kế latches để T1 release sau khi T2 đã bắt đầu attempt; kiểm tra T2 chỉ tiếp tục theo lock contract.

### Bài 13 — Không đặt barrier sau blocking call

Cho sơ đồ T1 lock row rồi chờ barrier, T2 cố lock row trước barrier. Giải thích tại sao test treo và viết lại choreography an toàn.

### Bài 14 — Lock timeout

T1 giữ lock với bounded release. T2 dùng `jakarta.persistence.lock.timeout` hoặc DB statement timeout phù hợp. Xác định expected exception SQLState/provider category, rollback và assert row không bị update sai.

### Bài 15 — Lock release khi rollback

T1 lock row rồi rollback. T2 đang đợi lock. Test T2 có thể tiếp tục sau rollback và quan sát state theo đúng transaction semantics.

### Bài 16 — Atomic conditional UPDATE

Viết bulk JPQL update `quantity=quantity-:n` với WHERE `quantity>=:n` và tenant scope. Hai requests 7/6 trên stock=10 phải không oversell; assert affected row counts/serialization retry semantics.

### Bài 17 — Idempotent reservation

Hai concurrent requests có cùng `requestId` nhưng stock đủ cho hai lượt. Thiết kế bảng `reservations(request_id UNIQUE, item_id, amount)` và transaction logic bảo đảm chỉ một business reservation được commit.

### Bài 18 — TransactionTemplate

Viết Spring integration test mà hai executor workers gọi `TransactionTemplate` với propagation REQUIRES_NEW, mỗi worker tạo transaction riêng và cùng đọc version N. Kiểm tra không dùng chung raw EntityManager.

### Bài 19 — Spring test `@Transactional` rollback trap

Trong test method có `@Transactional`, tạo fixture rồi spawn worker thread. Tại sao worker có thể không thấy fixture? Sửa bằng setup transaction đã commit và cleanup độc lập.

### Bài 20 — Spring self-invocation

Một bean gọi `this.reserveInNewTransaction()` có `@Transactional(REQUIRES_NEW)`. Viết test chứng minh transaction boundary có/không áp dụng trong proxy mode, rồi refactor qua proxied bean/TransactionTemplate.

### Bài 21 — Connection pool capacity

Tạo 2 workers nhưng pool max size=1, đặt barrier sau khi cả hai queries hoàn tất. Giải thích vì sao test có thể treo trước khi DB row locking bắt đầu. Đề xuất cấu hình pool và stage diagnostics phù hợp.

### Bài 22 — Phantom reads

T1 đếm orders PENDING, T2 insert/commit PENDING order, T1 đếm lại trong cùng transaction. Chạy trên DB ở READ COMMITTED và REPEATABLE READ, ghi nhận behavior thực.

### Bài 23 — Non-repeatable read và L1 cache

T1 find inventory=10, T2 commit inventory=8. T1 find lần nữa thấy gì? Thử `refresh` hoặc direct JDBC query để phân biệt persistence context cache với isolation snapshot.

### Bài 24 — Write skew

Hai doctors đều on call, mỗi transaction kiểm tra còn người khác trực rồi tự nghỉ. Viết một test chứng minh failure dưới isolation cho phép, sau đó chọn SERIALIZABLE hoặc guard-row locking để giữ invariant.

### Bài 25 — Deadlock A/B

T1 lock row A rồi B, T2 lock B rồi A. Đồng bộ sau first locks; assert deadlock victim/rollback và resource cleanup mà không phụ thuộc thread thắng cụ thể.

### Bài 26 — Thứ tự lock

Viết helper lock hai inventory IDs theo thứ tự tăng dần. Chạy concurrent transfers A→B và B→A; so sánh nguy cơ deadlock với mã khóa theo input order.

### Bài 27 — Bulk UPDATE bypass version

T1 load InventoryItem version=3. T2 bulk UPDATE quantity mà không bump version, commit. T1 UPDATE với version=3. Viết regression test cho lỗi lost overwrite và sửa bulk query bằng explicit numeric version increment.

### Bài 28 — Force increment parent

Hai transactions cùng chỉnh OrderItems khác nhau dưới cùng PurchaseOrder. Dùng `OPTIMISTIC_FORCE_INCREMENT` hoặc shared version protocol; assert không cả hai cùng ghi trên stale aggregate version.

### Bài 29 — Concurrent role membership

T1/T2 load cùng `User.roles`; T1 add SUPPORT, T2 add AUDITOR. Thiết kế invariant mong muốn, parent version/locking strategy và reload join table sau commits.

### Bài 30 — Soft-delete restore race

Tạo hai archived product rows cùng tenant/SKU. Concurrent restore hai rows dưới PostgreSQL partial unique index. Assert chỉ một active row sau transactions.

### Bài 31 — Cross-tenant business key

Chạy hai cặp concurrent inserts: cùng tenant/SKU và khác tenant/cùng SKU. Assert đúng một và đúng hai commits tương ứng theo UNIQUE(tenant_id,sku).

### Bài 32 — Retry với business invariant

Stock=10, requests reserve 7 và 6. Khi B optimistic conflict, retry B trong transaction mới. Assert B nhìn stock=3 rồi bị reject vì không đủ, không cố ghi stock=4 từ stale state.

### Bài 33 — Outbox rollback

Service reserve stock, tạo Order và outbox event trong cùng transaction; worker B conflict. Assert không có B order hoặc success event, ngay cả khi object được tạo trong Java trước commit.

### Bài 34 — Repeat run diagnostics

Chạy một deterministic concurrency test nhiều lần trong CI test environment cô lập; log worker phases, DB/provider version, transaction outcomes và final row count. Nếu fail, phân loại correctness vs timeout/infra.

### Bài 35 — Full scenario bảo vệ đặt hàng

Tạo hệ thống mô phỏng:

```text
InventoryItem(tenant, sku, quantity, version)
SalesOrder(id, tenant, requestId, status)
Reservation(orderId, itemId, quantity)
OutboxEvent(requestId, type, payload)
```

Hãy thiết kế concurrency tests cho: hai requests cạnh tranh stock, duplicate requestId, cross-tenant identity, optimistic retry, transaction rollback, outbox exactly-once logical effect và DB constraints. Xác định assertions phải kiểm tra sau commit bằng connection/EntityManager độc lập.

## 47. Câu hỏi tự kiểm tra

**1. Vì sao cần nhiều EntityManager để kiểm thử cập nhật đồng thời?**

Vì mỗi EntityManager có persistence context/identity map riêng. Nhiều contexts mô phỏng các clients/units of work đọc và sửa independently.

**2. EntityManager có thread-safe không?**

Không. Không dùng cùng một raw EntityManager cho nhiều threads song song.

**3. EntityManagerFactory có thể dùng chung không?**

Có. Một EntityManagerFactory thường có thể tạo nhiều EMs và được chia sẻ trong ứng dụng.

**4. Hai EntityManagers có tự bảo đảm hai transactions độc lập không?**

Không hoàn toàn. Cần thiết lập rõ transaction boundaries, nhất là khi Spring/JTA proxies hoặc transaction context binding tham gia.

**5. Cùng một EM gọi `find` hai lần với một PK thường trả gì?**

Cùng managed entity instance trong persistence context nếu entity còn được quản lý.

**6. Hai EM tìm cùng PK có trả cùng Java object không?**

Thường không; mỗi context quản lý object riêng, dù cả hai biểu diễn cùng database row.

**7. Một unit test của `reserve` có chứng minh chống oversell không?**

Không. Nó không có concurrent transactions/SQL locking.

**8. Một integration test đơn transaction có đủ chống lost update không?**

Không. Nó không tạo stale snapshot từ transaction thứ hai.

**9. `@Version` giúp gì khi hai transactions sửa cùng row?**

Provider kiểm tra version để phát hiện update dựa trên stale state, từ chối một writer theo optimistic locking semantics.

**10. Optimistic conflict có nhất thiết xuất hiện khi gọi setter không?**

Không. Thường phát hiện khi SQL UPDATE xảy ra ở flush/commit hoặc thời điểm tương ứng theo provider.

**11. Cần assert gì sau optimistic conflict?**

Expected conflict category, transaction rollback và DB state cuối chỉ chứa thay đổi thắng cuộc.

**12. Vì sao không hardcode initial version luôn là 0?**

Provider/version generation có thể khác. So base version giữa hai EM và expected increment theo behavior thực.

**13. `flush()` có đồng nghĩa transaction committed không?**

Không. Nó đồng bộ SQL trong transaction, còn commit có thể fail.

**14. `persist()` trả về có nghĩa INSERT committed không?**

Không. SQL có thể chạy sau đó và transaction có thể rollback.

**15. Vì sao verification nên dùng EM mới?**

Để tránh stale state từ L1 cache của EM đã đọc trước và nhìn dữ liệu sau transaction completion.

**16. EM mới có thể vẫn chịu ảnh hưởng L2 cache không?**

Có nếu provider dùng L2 cache; có thể cần bypass/evict hoặc direct JDBC cho DB-level verification.

**17. Khi nào chỉ cần hai EM một thread?**

Khi có thể tạo interleaving deterministic: A read, B read, A commit, B commit.

**18. Khi nào cần hai worker threads?**

Khi kiểm thử blocking locks, simultaneous operations, deadlocks, lock timeouts hoặc DB concurrency overlap.

**19. Vì sao không dùng `Thread.sleep` để đồng bộ?**

Sleep không chứng minh SQL event đã xảy ra, phụ thuộc scheduler và CI load.

**20. `CountDownLatch` dùng vào việc gì?**

Báo hiệu một phase đã hoàn tất hoặc giữ workers tới khi coordinator cho đi tiếp.

**21. `CyclicBarrier` có ích ở điểm nào?**

Giữ nhiều workers ở cùng một phase cho đến khi đủ participants rồi cùng tiến tới giai đoạn kế tiếp.

**22. Vì sao barrier sau blocking lock dễ treo?**

Một worker giữ lock và chờ barrier, worker khác bị chặn trước khi đến barrier.

**23. `Future.get(timeout)` timeout có chứng minh DB lock timeout không?**

Không. Nó chỉ chứng minh worker chưa hoàn tất; có thể do pool starvation/barrier/scheduler.

**24. Vì sao mọi awaits phải có timeout?**

Để tránh test treo vô hạn khi worker fail hoặc lock không release.

**25. Nếu A/B cùng optimistic write, có cần A luôn thắng không?**

Không; assert outcome bất biến: một winner, một conflict và DB invariant đúng.

**26. `@Version` có ngăn ghi trùng email không?**

Không. Unique business key cần DB UNIQUE constraint, kể cả khi có pre-check.

**27. Hai pre-check `existsByEmail` cùng trả false có thể dẫn đến gì?**

Cả hai cố insert; DB UNIQUE phải từ chối một commit nếu key thực sự unique.

**28. Annotation `@UniqueConstraint` có bảo đảm DB production enforce unique không?**

Không. Constraint phải tồn tại trong physical schema từ migration/DDL.

**29. UNIQUE failure có thể xảy ra lúc nào?**

Tại INSERT/flush hoặc commit (đặc biệt với deferred constraints), tùy DB/provider.

**30. Khi test duplicate race, verify gì ngoài exception?**

Đúng một row committed cho business key và không có partial effects của transaction thua.

**31. `PESSIMISTIC_WRITE` có ý nghĩa gì?**

Yêu cầu pessimistic write lock trên entity theo DB/provider semantics, thường làm transaction cạnh tranh chờ hoặc fail.

**32. Pessimistic lock có tự khóa mọi children của entity không?**

Không mặc định; scope phụ thuộc mapping, provider, DB và chosen locking protocol.

**33. Lock timeout JPA hint có luôn được DB hỗ trợ chính xác không?**

Không. Support/granularity phụ thuộc provider/dialect/database.

**34. `LockTimeoutException` có giống `PessimisticLockException` không?**

Không hoàn toàn; chúng diễn tả các loại lock failures/rollback semantics khác nhau theo JPA contract.

**35. Optimistic và pessimistic locking cái nào luôn tốt hơn?**

Không có đáp án chung. Chọn theo contention, throughput, latency, retry policy và invariants.

**36. Có thể tránh oversell bằng atomic conditional UPDATE không?**

Có trong các database/isolation semantics phù hợp, nếu UPDATE có WHERE available>=requested, kiểm tra affected rows và transaction commit.

**37. `executeUpdate()==1` có đồng nghĩa order đã committed không?**

Không. Còn các DB writes và transaction commit có thể thất bại.

**38. Vì sao retry optimistic phải reload state?**

State cũ đã bị thay đổi; business condition có thể không còn đúng.

**39. Retry stale detached entity bằng merge ngay có an toàn không?**

Không nếu không revalidate version, business invariants và graph state.

**40. `READ COMMITTED` thường bảo vệ điều gì?**

Không đọc dữ liệu chưa commit; non-repeatable observations có thể xảy ra tùy DB.

**41. `REPEATABLE READ` có loại trừ mọi write skew không?**

Không trên mọi DB; snapshot isolation có thể cho phép write skew.

**42. `SERIALIZABLE` có đảm bảo mọi concurrent transactions đều commit được không?**

Không. DB có thể abort một transaction do serialization conflict, application phải retry đúng.

**43. Write skew khác lost update thế nào?**

Hai transactions sửa các rows khác nhau nhưng cùng phá một invariant xuyên rows; không có một row bị hai writers ghi đè trực tiếp.

**44. `@Version` trên từng doctor row có bảo vệ “ít nhất một doctor on call” không?**

Không mặc định, vì T1/T2 sửa các doctor rows khác nhau.

**45. Deadlock xảy ra khi nào?**

Khi có chu trình chờ khóa, ví dụ T1 giữ A đợi B và T2 giữ B đợi A.

**46. Database có luôn chọn T2 làm deadlock victim không?**

Không. Victim có thể khác nhau theo DB/lịch.

**47. Giảm deadlock bằng cách nào?**

Lock các resources theo thứ tự ổn định, giữ transactions ngắn và có retry cho failures được phân loại đúng.

**48. `@Transactional` trên Spring test class có thể gây gì cho concurrency tests?**

Fixture chưa commit không visible cho worker transactions, và test rollback không tự undo commits của workers.

**49. Spring transaction context có tự truyền qua raw ExecutorService không?**

Không trong setup thread-bound thông thường; mỗi worker cần transaction boundary của mình.

**50. Spring self-invocation có thể phá `REQUIRES_NEW` thế nào?**

Lời gọi `this.method()` không qua proxy nên transaction advice có thể không chạy.

**51. `TransactionTemplate` dùng để làm gì?**

Tạo/chỉ định transaction boundaries programmatically, có thể dùng REQUIRES_NEW trong worker.

**52. Pool size=1 có thể làm test hai workers treo vì sao?**

T1 giữ connection và chờ T2, còn T2 không lấy được connection để đi đến barrier.

**53. Vì sao không share raw EntityManager giữa threads?**

Nó không thread-safe, gây race trong persistence context/identity map và lifecycle.

**54. Vì sao phải clear ThreadLocal security context sau worker?**

Thread pool tái sử dụng threads; actor/tenant của task trước có thể rò sang task sau.

**55. Bulk JPQL UPDATE có tự increment `@Version` như entity update không?**

Không mặc định; application phải thiết kế version/rowcount protocol tương ứng.

**56. Bulk JPQL UPDATE có thể làm managed entity stale không?**

Có. Persistence context không được đồng bộ tự động với bulk DML.

**57. `OPTIMISTIC_FORCE_INCREMENT` nhằm mục đích gì?**

Yêu cầu version increment như một optimistic concurrency guard, hữu ích khi bảo vệ aggregate thay đổi ngoài scalar parent fields.

**58. `@Version` trên parent có tự bảo vệ mọi native child update không?**

Không. Mọi writers phải tuân thủ shared version/locking protocol.

**59. Soft-delete active uniqueness có thể cần gì?**

Partial unique index/DB-specific design để chỉ active rows bị unique, nhất là khi NULL semantics ảnh hưởng.

**60. Làm sao tránh false positive trong test?**

Phân loại expected failure, xác nhận đúng lịch đọc/ghi, kiểm tra DB committed state và phân biệt DB lock với barrier/pool timeout.

**61. Khi concurrent request thất bại có cần kiểm tra outbox không?**

Có nếu operation tạo sự kiện; không để success event của transaction rollback lọt ra ngoài.

**62. Vì sao stress test pass nhiều lần chưa chứng minh không còn race?**

Nó chỉ chạy một số lịch scheduler/DB; có thể còn các interleavings khác chưa gặp.

**63. Vì sao nên chạy tests trên RDBMS giống production?**

Locking, isolation, SQLState, unique/deferrable constraints và driver behavior khác nhau giữa DBs.

**64. Có nên dùng một JVM `synchronized` để bảo vệ stock xuyên nhiều application instances?**

Không đủ; locks đó không chia sẻ giữa JVMs/pods. Cần DB/distributed coordination theo thiết kế.

**65. Kết luận quan trọng nhất khi kiểm thử concurrency JPA?**

**Dùng persistence contexts và transactions độc lập, kiểm soát interleaving, phân loại conflict đúng và xác minh business invariants bằng dữ liệu đã commit.**

## 48. Checklist trước khi đưa concurrency test vào CI

### 48.1. Môi trường

1. Dùng RDBMS và JDBC/provider stack đủ gần production.
2. Schema được tạo bằng migration chain phù hợp với production.
3. Physical constraints/indices/version columns tồn tại thật.
4. Test có DataSource/pool size đủ cho concurrent active transactions.
5. Isolation/locking settings được xác định trên connection thật.
6. Không dùng production database hoặc shared user data cho race experiments.
7. Mỗi test có fixtures riêng và cơ chế cleanup không đụng test khác.
8. Dữ liệu fixture được commit trước khi workers bắt đầu.
9. Cần kiểm tra L2 cache/query cache đã bật hay bị bypass.
10. Hạn chế JUnit parallel execution nếu tests dùng chung schema/pool.

### 48.2. Persistence context và transaction boundaries

11. Mỗi worker có một raw EntityManager riêng hoặc Spring transaction-bound EntityManager proxy.
12. Không chia sẻ raw EntityManager/managed entities giữa worker threads.
13. Mỗi worker thực sự dùng một DB transaction độc lập.
14. Spring `@Transactional`/`REQUIRES_NEW` được gọi qua proxy/TransactionTemplate phù hợp.
15. Tránh test-managed transaction chưa commit giữ fixture invisible.
16. Có begin, commit/rollback, close trong `try/finally`.
17. Worker báo `committed` chỉ sau transaction commit thành công.
18. Persistence exception được phân loại; không chỉ catch-all rồi coi success.
19. Transaction đã fail không bị tiếp tục dùng để retry.
20. Retry bắt đầu context/transaction mới và re-evaluate business rule.

### 48.3. Điều phối concurrency

21. Đã định nghĩa rõ interleaving cần tạo (hai reads trước writes, lock holder trước waiter, v.v.).
22. `CountDownLatch`/`CyclicBarrier` được đặt **sau event đã xảy ra hoặc trước operation blocking** phù hợp.
23. Không dùng `Thread.sleep` làm chứng cứ test đúng lịch.
24. Mọi latch/barrier/future waits có bounded timeout.
25. Coordinator release latches trong `finally` nếu assertion lỗi.
26. Exceptions/timeout từ worker được propagate về test thread.
27. Không giả định thread A luôn là winner nếu business không yêu cầu.
28. Không đặt barrier ở vị trí transaction không thể đến do DB lock.
29. Connection-pool starvation được phân biệt với row lock wait.
30. Cleanup chỉ xảy ra khi worker transactions đã dừng/đóng.

### 48.4. Correctness assertions

31. Assert cả hai transactions đã đọc cùng base state nếu test yêu cầu.
32. Optimistic conflicts được kiểm tra đúng exception category/cause.
33. Unique conflicts được xác minh bằng constraint/SQLState khi cần.
34. Không chỉ assert exception; reload database ở fresh context/connection.
35. Invariant stock không âm và không oversold business operations.
36. Duplicate-key scenario chỉ có một row committed.
37. Cross-tenant business keys không bị ràng buộc quá mức nếu requirement tenant-local.
38. Failed transaction không để lại partial rows/order/outbox events.
39. Lock timeout/deadlock không được nhầm với future/barrier/pool timeout.
40. Retry không biến một client request thành nhiều business actions.
41. Bulk SQL writers tuân thủ version/tenant predicates khi cần.
42. Parent/child collection invariants được kiểm tra sau concurrent edits.
43. Write-skew invariants trải nhiều rows được thử dưới isolation thực tế.
44. Cache invalidation được kiểm thử riêng nếu L2 cache bật trên production.

### 48.5. Vận hành và chẩn đoán

45. Ghi worker phases, transaction outcomes, version IDs và DB/provider version.
46. Timeout đủ hữu hạn nhưng không quá ngắn so với shared CI.
47. Log SQL/DB diagnostic có kiểm soát thông tin nhạy cảm.
48. Có khả năng phân biệt FAILED_SETUP/FAILED_TIMEOUT/FAILED_CORRECTNESS.
49. Nếu test stress randomized, log seed để tái lập.
50. Những concurrency tests quan trọng được chạy định kỳ trên environment giống production.

## 49. Tổng kết

**Kiểm thử đồng thời bằng nhiều EntityManager độc lập** là cách chuyển những lỗi phụ thuộc timing từ “thỉnh thoảng xuất hiện trên production” thành các kịch bản có thể quan sát và xác minh.

Những điểm quan trọng nhất:

1. **EntityManagerFactory có thể chia sẻ, EntityManager không thread-safe.** Mỗi concurrent worker dùng persistence context riêng; không đưa cùng raw EM vào hai threads.
2. **Hai EM và hai transaction là hai điều kiện khác nhau.** Cần hiểu resource-local vs Spring/JTA binding và xác nhận mỗi worker có transaction độc lập thực.
3. **Dùng interleaving deterministic trước stress test.** Để kiểm thử optimistic conflict, cho cả hai EM đọc cùng version rồi commit theo thứ tự hoặc dùng barrier trước writes.
4. **`@Version` ngăn stale write trên entity version được bảo vệ.** Một writer phải conflict khi cập nhật cùng version đã bị writer khác thay đổi; sau conflict, rollback/reload trước retry.
5. **`persist`/`flush` không chứng minh commit.** Business success chỉ được xác nhận sau transaction completion; SQL/constraint conflict có thể xuất hiện muộn.
6. **UNIQUE là trách nhiệm của database.** Hai pre-checks có thể cùng false; chỉ constraint thực tại DB mới ngăn duplicate business key qua nhiều transactions.
7. **Pessimistic locking đòi choreography riêng.** Một thread giữ lock, thread khác có thể wait/timeout; không đặt barrier sau operation đang bị DB block.
8. **Isolation levels khác nhau theo RDBMS.** Phải test READ COMMITTED/REPEATABLE READ/SERIALIZABLE trên target DB và hiểu non-repeatable read, phantom, write skew.
9. **`@Version` không bảo vệ mọi invariant xuyên nhiều rows.** Với write skew, có thể cần serializable transaction, guard row locking hoặc schema redesign.
10. **Bulk DML/native SQL có thể bypass version/callbacks.** Dùng atomic scoped predicates, affected-row checks và explicit version handling nếu phù hợp.
11. **Spring test transactions dễ che hoặc tạo lỗi giả.** Test `@Transactional` rollback, thread-bound transactions, REQUIRES_NEW self-invocation và fixture uncommitted phải được xử lý rõ.
12. **Connection pool, Java barriers và database locks là ba nguồn chờ khác nhau.** Timeout không tự chứng minh DB deadlock; cần event phases và diagnostics.
13. **Kiểm chứng committed state từ context độc lập.** L1/L2 caches có thể che dữ liệu DB mới; direct JDBC giúp xác nhận physical row khi cần.
14. **Business invariant quan trọng hơn số exception.** Test stock, order, unique key, audit/outbox, retries và tenant scope theo hành vi thực tế của service.
15. **Không dựa vào sleep/race ngẫu nhiên làm tiêu chí pass.** Dùng bounded latches/barriers, typed errors, deterministic schedules, resource cleanup và representative DB fixtures.

### 49.1. Sơ đồ ghi nhớ

```text
             Business invariant
                     |
                     v
           Seed committed fixture
                     |
            +--------+--------+
            |                 |
            v                 v
      EntityManager A    EntityManager B
      Transaction A      Transaction B
            |                 |
      Read base state    Read base state
            |                 |
            +----- BARRIER ---+
            |                 |
         Modify             Modify
            |                 |
           Commit / Flush / Lock
            |                 |
            +--------+--------+
                     |
              classify outcome
                     |
         +-----------+------------+
         |                        |
       winner                  loser
      committed           conflict/rollback
         |                        |
         +-----------+------------+
                     |
          Fresh EntityManager/JDBC
                     |
                     v
          Verify committed invariant
```

### 49.2. Tự đánh giá thiết kế test bằng ba câu hỏi

**Câu 1 — Có thật hai giao dịch độc lập không?** Nếu chưa, test chưa mô phỏng được tình huống concurrent requests.

**Câu 2 — Có ép được interleaving cần thiết không?** Nếu chưa, test pass có thể do hai workers vô tình chạy tuần tự, không phải do locking đúng.

**Câu 3 — Có chứng minh database sau commit vẫn giữ business invariant không?** Nếu chỉ nhìn exception hoặc Java object trong context cũ, kết luận chưa đủ.

> **Quy tắc dễ nhớ:** *Kiểm thử concurrency JPA không phải “cho hai threads chạy thật nhanh”. Đó là đặt hai persistence contexts vào đúng trạng thái cạnh tranh, điều khiển thời điểm quyết định và quan sát hệ quả đã commit trên database thực.*
