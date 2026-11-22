# Xử lý tranh chấp tài nguyên bằng khóa bi quan có kiểm thử

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Thực hành tổng hợp

Khi hai yêu cầu đồng thời cố đặt cùng sản phẩm cuối cùng, giữ cùng ghế, nhận cùng công việc từ hàng đợi hoặc chỉnh sửa cùng một bản ghi, kết quả không chỉ phụ thuộc đoạn Java kiểm tra điều kiện. Cả hai transactions có thể đọc cùng một trạng thái trước khi một transaction kịp ghi. Nếu không thiết kế đồng bộ hóa ở tầng database, hệ thống có nguy cơ **bán vượt tồn kho, nhận trùng một tài nguyên, mất cập nhật hoặc vi phạm bất biến nghiệp vụ**.

**Khóa bi quan (pessimistic locking)** là một cách giải quyết: transaction xin khóa tài nguyên từ database **trước khi thực hiện thao tác dễ tranh chấp**, để các transaction khác muốn lấy khóa xung đột phải chờ, thất bại hoặc bỏ qua theo chính sách và khả năng database.

Trong JPA, cách biểu đạt quen thuộc là:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("""
    select s from StockItem s
    where s.id = :id
      and s.tenantId = :tenant
    """)
Optional<StockItem> lockStock(
    @Param("id") Long id,
    @Param("tenant") String tenant
);
~~~

Sau đó application service phải dùng entity được khóa **trong một transaction còn hoạt động**:

~~~java
@Transactional
public ReservationResult reserve(
        String tenant, Long stockId, int quantity) {

    StockItem stock = repository
        .lockStock(stockId, tenant)
        .orElseThrow(StockNotFoundException::new);

    stock.reserve(quantity);

    return new ReservationResult(
        stock.getId(), stock.getAvailable()
    );
}
~~~

Nhưng một annotation **chưa phải chứng minh đúng đắn**. Bài thực hành này xây dựng ví dụ hoàn chỉnh, mô phỏng hai giao dịch thật, giải thích ba chế độ khóa của JPA, kiểm thử sự chờ khóa và timeout trên PostgreSQL, xử lý rollback, deadlock, phân quyền theo tenant, retry, hiệu năng và cách lựa chọn giữa khóa bi quan, khóa lạc quan, atomic SQL.

## 1. Mục tiêu của bài thực hành

Sau khi hoàn thành, bạn có thể:

1. Tái hiện race condition đọc–kiểm tra–ghi khi hai transactions tranh chấp một row.
2. Giải thích tại sao Java synchronized hoặc kiểm tra trước khi lưu không đủ cho nhiều application instances.
3. Dùng **LockModeType.PESSIMISTIC_WRITE** trong JPA/Spring Data Repository.
4. Đặt **@Transactional** ở use-case service để giữ khóa qua toàn bộ đoạn kiểm tra và cập nhật.
5. Phân biệt **PESSIMISTIC_READ**, **PESSIMISTIC_WRITE**, **PESSIMISTIC_FORCE_INCREMENT** và optimistic locking.
6. Hiểu quan hệ giữa khóa cấp database, @Version, flush, commit và rollback.
7. Viết integration test có **hai threads, hai transactions thực, CountDownLatch/Future** thay vì chỉ test tuần tự.
8. Kiểm thử trường hợp yêu cầu thứ hai phải chờ hoặc bị timeout khi row đã bị khóa.
9. Xử lý deadlock/lock timeout, retry bounded và idempotency mà không tái sử dụng transaction lỗi.
10. Đánh giá phạm vi khóa, query plan, transaction duration và các phương án thay thế.

**Phạm vi minh họa:** Jakarta Persistence, Spring Data JPA, Spring Boot 3.x, JUnit 5 và PostgreSQL qua Testcontainers. Những SQL/hints liên quan **NOWAIT**, **SKIP LOCKED** hoặc **lock_timeout** được đánh dấu là hành vi phụ thuộc database/provider; không gọi chúng là guarantee di động của JPA.

## 2. Bài toán xuyên suốt: bán sản phẩm còn ít hàng

Giả sử bảng quản lý tồn kho có row:

| stock_id | tenant_id | sku | available | version |
|---:|---|---|---:|---:|
| 101 | tenant-a | KB-001 | 5 | 0 |

Hai khách cùng lúc mỗi người muốn **4 sản phẩm**. Quy tắc nghiệp vụ:

- Quantity phải dương.
- Không được bán nhiều hơn số lượng còn lại.
- Một giao dịch đặt thành công làm available giảm đúng quantity.
- Nếu yêu cầu thất bại vì hết hàng, available không được thay đổi.
- Một user ở tenant khác không được khóa hoặc sửa row này.
- Nếu service tạo thêm Order/Outbox trong cùng use case, mọi writes phải cùng commit hoặc rollback.

### 2.1. Interleaving sai khi không có concurrency control

~~~text
T1                                T2
--------------------------------  --------------------------------
BEGIN                             BEGIN
SELECT available → 5              SELECT available → 5
5 >= 4 ✓                          5 >= 4 ✓
available = 1                     available = 1
UPDATE stock SET available=1      UPDATE stock SET available=1
COMMIT                            COMMIT

Hệ thống ghi hai đơn 4 + 4,
nhưng tồn kho chỉ giảm từ 5 xuống 1.
~~~

Chi tiết kết quả thực tế phụ thuộc SQL, @Version và isolation level. Một JPA entity có @Version hoạt động đúng có thể khiến một transaction thất bại bằng optimistic locking, không tạo kết quả sai như trên. Sơ đồ mô tả **mối nguy nếu không có cơ chế chống tranh chấp phù hợp**, không khẳng định mọi JPA update nhất định bị lost update.

### 2.2. Diễn tiến mong đợi với khóa bi quan

~~~text
T1                                T2
--------------------------------  --------------------------------
BEGIN                             BEGIN
SELECT ... FOR UPDATE             SELECT ... FOR UPDATE
Nhận row lock ✓                   Đợi row lock của T1
Đọc available = 5
reserve(4) → 1
UPDATE available = 1
COMMIT → giải phóng lock
                                  Nhận lock, thấy available = 1
                                  1 >= 4 ✗
                                  ROLLBACK/không ghi
                                  Trả INSUFFICIENT_STOCK

Chỉ một yêu cầu thành công.
Available cuối = 1.
~~~

Với PostgreSQL ở READ COMMITTED và một locking query phù hợp, transaction chờ row lock sẽ quan sát bản ghi được cập nhật sau khi transaction giữ khóa kết thúc. Cần kiểm chứng theo chính database, isolation và query strategy đang sử dụng; ở isolation cao hơn có thể xuất hiện serialization error thay vì đơn giản thấy giá trị mới.

### 2.3. Vì sao một unit test tuần tự không đủ?

Một test:

~~~java
service.reserve(101L, 4);
assertThrows(
    InsufficientStockException.class,
    () -> service.reserve(101L, 4)
);
~~~

chỉ xác nhận business validation sau lần ghi đầu tiên. Nó **không chứng minh** hai transactions đồng thời được tuần tự hóa bằng khóa; cơ chế khóa có thể bị gỡ bỏ mà test vẫn pass. Cần integration test thật sự giữ khóa ở một transaction và khiến transaction khác cạnh tranh.

## 3. Khóa bi quan là gì và không phải gì?

### 3.1. Khóa được database quản lý

Khi transaction xin khóa row, hệ quản trị database điều phối quyền truy cập với transactions khác, kể cả chúng chạy ở:
- Hai threads trong một JVM;
- Hai process của cùng dịch vụ;
- Hai application servers khác nhau;
- Một background job và một HTTP request;
- Những services khác cùng truy cập database.

Đây là khác biệt quan trọng với **Java synchronized/ReentrantLock**, vốn chỉ điều phối code trong phạm vi process/lock instance phù hợp.

### 3.2. Không phải khóa của object Java

Hai EntityManagers có thể load hai ProductStock Java objects khác nhau đại diện cùng database row. Database row lock, không phải Java object identity, quyết định transaction nào có thể thực thi locking write.

### 3.3. Khóa thường có vòng đời gắn với transaction

Một row lock được lấy trong transaction thường được giữ cho đến khi transaction kết thúc (COMMIT/ROLLBACK), theo cơ chế DB và loại lock. **em.flush() không phải commit** và **em.clear() không phải unlock**.

### 3.4. SELECT thông thường có thể không bị chặn

Trong PostgreSQL MVCC với READ COMMITTED, một SELECT không yêu cầu locking read thường có thể đọc committed version cũ ngay cả khi một transaction khác giữ row-level FOR UPDATE lock. Không hiểu PESSIMISTIC_WRITE là “chặn tất cả lượt xem row”.

Khóa nhằm điều phối **những operations xung đột** như UPDATE/DELETE hoặc locking reads tương ứng. Tập khóa xung đột chính xác tùy DB và lock mode.

### 3.5. Khóa bi quan không tự thay quy tắc nghiệp vụ

Ngay cả sau khi lấy lock, service vẫn phải kiểm tra:

~~~java
if (available < quantity) {
    throw new InsufficientStockException();
}
~~~

Nếu bỏ kiểm tra và cứ trừ, hệ thống có thể bán vượt tồn kho một cách **tuần tự**, không cần race condition. Lock bảo vệ khoảng đọc–kiểm tra–ghi; nó không tạo business invariant thay bạn.

### 3.6. Không khóa dài xuyên network call

Một use case giữ row lock rồi chờ cổng thanh toán vài giây có thể làm mọi khách khác phải chờ row đó. Thường nên:
1. Giữ transaction ngắn để tạo reservation trong database;
2. Commit;
3. Gọi payment bên ngoài;
4. Xử lý kết quả qua workflow/outbox/compensation.

Khóa bi quan giải quyết tranh chấp tài nguyên trong **một DB transaction ngắn**, không thay thế saga hay workflow dài.

## 4. Các lock mode JPA liên quan

### 4.1. PESSIMISTIC_READ

~~~java
entityManager.find(
    StockItem.class,
    stockId,
    LockModeType.PESSIMISTIC_READ
);
~~~

Mục đích là xin một dạng shared/read lock phù hợp để chống những changes không tương thích trong lúc đọc. Tuy nhiên provider/DB có thể map chế độ này khác nhau, thậm chí dùng stronger lock khi dialect không hỗ trợ shared lock tương ứng.

**Không mặc định** nhiều PESSIMISTIC_READ requests luôn song song hoặc luôn block mọi writers giống nhau trên mọi DB.

### 4.2. PESSIMISTIC_WRITE

~~~java
entityManager.find(
    StockItem.class,
    stockId,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Dùng khi đọc state rồi sẽ thay đổi state mà cần chống concurrent writers. Trong PostgreSQL/Hibernate, thường tương ứng SQL locking kiểu **FOR UPDATE**, nhưng SQL thực tế còn phụ thuộc dialect, joins và provider version.

### 4.3. PESSIMISTIC_FORCE_INCREMENT

~~~java
entityManager.lock(
    stock,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);
~~~

Chế độ yêu cầu khóa bi quan kèm tăng version cho **versioned entity** theo JPA semantics. Có ích khi cần báo một state change mang tính logic cho optimistic participants dù không có field thường nào thay đổi; nhưng gây write/contend thêm. Nó không phải lựa chọn mặc định cho mọi stock reservation.

### 4.4. Không nhầm với OPTIMISTIC/OPTIMISTIC_FORCE_INCREMENT

~~~java
entityManager.lock(stock, LockModeType.OPTIMISTIC);
~~~

Optimistic locking dùng version check, không phải row lock trước mọi thay đổi. OPTIMISTIC_FORCE_INCREMENT yêu cầu version increment theo optimistic semantics, không đồng nghĩa giữ PESSIMISTIC_WRITE lock.

### 4.5. Bảng so sánh

| Lock mode | Ý định | Điểm cần chú ý |
|---|---|---|
| NONE | Không yêu cầu lock riêng | Isolation/normal writes vẫn có cơ chế của DB |
| OPTIMISTIC | Kiểm tra version | Không lock row trước mọi thao tác |
| OPTIMISTIC_FORCE_INCREMENT | Kiểm tra và tăng version | Có thể tạo thêm UPDATE |
| PESSIMISTIC_READ | Lock để đọc nhất quán theo khả năng DB | Mapping shared lock phụ thuộc dialect |
| PESSIMISTIC_WRITE | Lock để đọc–sửa cạnh tranh | Dễ tăng contention nếu tx dài |
| PESSIMISTIC_FORCE_INCREMENT | Pessimistic lock và tăng version | Yêu cầu versioned entity, overhead |

### 4.6. Dùng LockModeType ở đâu?

Các đường JPA phổ biến:

~~~java
em.find(StockItem.class, id, LockModeType.PESSIMISTIC_WRITE);

em.lock(managedStock, LockModeType.PESSIMISTIC_WRITE);

em.createQuery(
    "select s from StockItem s where s.id = :id",
    StockItem.class
)
.setParameter("id", id)
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
.getSingleResult();
~~~

Trong Spring Data JPA, dùng **@Lock** trên repository query method. Các đường này cùng biểu đạt ý định khóa, nhưng nên hiểu query shape/provider SQL và transaction boundary thực tế.

## 5. Các lớp code của bài thực hành

Sơ đồ modules minh họa:

~~~text
src/main/java/com/example/locking/
  LockingDemoApplication.java
  domain/
    StockItem.java
    InsufficientStockException.java
    StockNotFoundException.java
  repository/
    StockRepository.java
  application/
    StockReservationService.java
    ReservationResult.java

src/test/java/com/example/locking/
  StockReservationIntegrationTest.java
  LockBlockingIntegrationTest.java
  LockTimeoutIntegrationTest.java
  TwoRowDeadlockIntegrationTest.java

src/test/resources/
  application-test.yml
~~~

Các lớp test có thể gom trong một class trong project nhỏ, nhưng mỗi test cần ranh giới transaction rõ, tránh trạng thái test này rò sang test khác.

Phần code dùng **Jakarta** namespace thay vì **javax.persistence**. Java records yêu cầu Java version hỗ trợ (ví dụ Java 17). Nếu ứng dụng dùng Spring Boot 2/JPA cũ, chuyển dependencies và imports theo stack tương ứng, không trộn namespaces.

## 6. Khai báo StockItem và business invariant

### 6.1. Entity

~~~java
package com.example.locking.domain;

import jakarta.persistence.*;

@Entity
@Table(
    name = "stock_items",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_stock_tenant_sku",
        columnNames = {"tenant_id", "sku"}
    )
)
public class StockItem {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Version
    private Long version;

    @Column(
        name = "tenant_id",
        nullable = false,
        updatable = false,
        length = 64
    )
    private String tenantId;

    @Column(nullable = false, length = 64)
    private String sku;

    @Column(nullable = false)
    private int available;

    protected StockItem() {
    }

    public StockItem(
            String tenantId,
            String sku,
            int available) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId");
        }
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku");
        }
        if (available < 0) {
            throw new IllegalArgumentException("available");
        }

        this.tenantId = tenantId;
        this.sku = sku;
        this.available = available;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity must be positive"
            );
        }

        if (available < quantity) {
            throw new InsufficientStockException();
        }

        available -= quantity;
    }

    public void replenish(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity");
        }
        available = Math.addExact(available, quantity);
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getSku() {
        return sku;
    }

    public int getAvailable() {
        return available;
    }
}
~~~

Một domain exception:

~~~java
package com.example.locking.domain;

public class InsufficientStockException
        extends RuntimeException {

    public InsufficientStockException() {
        super("INSUFFICIENT_STOCK");
    }
}
~~~

Một exception khi không thấy row trong tenant scope:

~~~java
package com.example.locking.domain;

public class StockNotFoundException
        extends RuntimeException {

    public StockNotFoundException() {
        super("STOCK_NOT_FOUND");
    }
}
~~~

### 6.2. Vì sao available là primitive int?

Trong ví dụ, số hàng tồn là số nguyên không âm, DB column NOT NULL. Trong hệ thống thực tế cần cân nhắc:
- Hàng có thể chia lẻ không? Sử dụng đơn vị/quy đổi hoặc BigDecimal theo domain.
- Quantity tối đa có thể vượt int không?
- Reservation/available/onHand có cần bảng riêng không?
- Có điều chỉnh âm/tồn kho âm cho workflows đặc biệt không?
- Có nhiều kho và nhiều stock rows cho một SKU không?

Không đổi kiểu dữ liệu vì locking; locking bảo vệ invariant đã được mô hình hóa đúng.

### 6.3. @Version bổ sung bảo vệ

Dù thực hành chủ yếu dùng PESSIMISTIC_WRITE, giữ @Version là hữu ích:
- Bảo vệ đường ghi khác chỉ dùng optimistic locking;
- Phát hiện stale state nếu ai đó ghi không tuân thủ khóa của use case;
- Hỗ trợ kiểm thử concurrency theo các chiến lược khác;
- Tăng độ rõ ràng về versioned entity.

Tuy nhiên một **native SQL UPDATE** hoặc writer ngoài JPA không tự tăng version nếu không chủ động cập nhật; khi có nhiều đường ghi cần một versioning contract thống nhất.

### 6.4. Domain rule vẫn được kiểm tra bên trong transaction

Khi row được khóa, service gọi reserve. Nếu quantity=4 nhưng available chỉ còn 1, method ném InsufficientStockException, transaction kết thúc thất bại và DB không bị trừ thêm.

## 7. DDL và transaction scope ở database

Một schema PostgreSQL minh họa:

~~~sql
CREATE SEQUENCE stock_items_seq
    START WITH 1
    INCREMENT BY 50;

CREATE TABLE stock_items (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    sku VARCHAR(64) NOT NULL,
    available INTEGER NOT NULL,
    CONSTRAINT uk_stock_tenant_sku
        UNIQUE (tenant_id, sku),
    CONSTRAINT ck_stock_available_nonnegative
        CHECK (available >= 0)
);

CREATE INDEX idx_stock_tenant_sku
    ON stock_items(tenant_id, sku);
~~~

**Đây là DDL minh họa**, không nên chạy song song với Hibernate auto-ddl khi chưa đồng bộ effective sequence generator. Khi dùng @GeneratedValue(strategy=SEQUENCE) không khai báo generator tùy chỉnh, tên sequence và allocation strategy **phụ thuộc provider/config**. Trong production, định nghĩa @SequenceGenerator tường minh và migration khớp strategy; hoặc điều chỉnh DDL theo mapping thực. Bài test ở phần sau có thể dùng Hibernate create-drop để tránh phải tự viết sequence tên không chắc chắn.

Trong thực tế:
- Nếu query khóa theo primary key id, DB thường có index primary key sẵn;
- Nếu khóa theo tenantId + sku, unique index hỗ trợ tìm đúng row;
- Tránh query khóa không có index làm quét nhiều rows và tăng wait/congestion;
- Thêm CHECK available >= 0 để database chặn trạng thái sai do mọi đường ghi, nhưng CHECK **không thay concurrency control**.

### 7.1. Vì sao database CHECK không thay khóa?

Với cả hai transactions đọc available=5 rồi ghi available=1, row cuối vẫn >=0, nên CHECK không phát hiện đã bán tổng cộng 8. Lock/@Version/atomic conditional update cần bảo vệ race đọc–kiểm tra–ghi.

### 7.2. Tenant scope không được bỏ qua

Một query:

~~~sql
SELECT * FROM stock_items WHERE id = 101 FOR UPDATE;
~~~

có thể khóa row của tenant khác nếu ứng dụng dùng client-supplied ID tùy ý. Service phải áp authorization và query theo **id + tenantId**, hoặc có enforced row-level security policy đáng tin.

### 7.3. Transaction isolation

Phần thực hành mặc định dựa trên PostgreSQL **READ COMMITTED** hoặc isolation đã kiểm soát để giải thích visibility sau lock wait. Không giả định một transaction ở REPEATABLE READ/SERIALIZABLE sẽ luôn xử lý theo đúng cùng timeline: serialization failure có thể xảy ra, cần rollback/retry phù hợp.

## 8. Repository: khai báo @Lock đúng chỗ

### 8.1. Spring Data JPA repository

~~~java
package com.example.locking.repository;

import com.example.locking.domain.StockItem;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface StockRepository
        extends JpaRepository<StockItem, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select s
        from StockItem s
        where s.id = :id
          and s.tenantId = :tenant
        """)
    Optional<StockItem> lockByIdAndTenant(
        @Param("id") Long id,
        @Param("tenant") String tenant
    );

    @Query("""
        select s
        from StockItem s
        where s.id = :id
          and s.tenantId = :tenant
        """)
    Optional<StockItem> findByIdAndTenant(
        @Param("id") Long id,
        @Param("tenant") String tenant
    );
}
~~~

Trong controller/service:
- **lockByIdAndTenant** dùng khi cần serializing read–modify–write.
- **findByIdAndTenant** dùng để đọc bình thường; không cấp một khóa PESSIMISTIC_WRITE chỉ vì UI xem số hàng tồn.
- Save kế thừa từ JpaRepository hỗ trợ persist; với entity managed sau locking query, **dirty checking** thường tự đồng bộ available khi flush/commit.

### 8.2. @Lock không tự mở transaction bảo vệ toàn use case

Nếu service gọi locking query **ngoài transaction phù hợp**, provider có thể ném TransactionRequiredException hoặc repository method có transaction rất ngắn kết thúc trước khi service sửa entity. Cả hai đều không đáp ứng yêu cầu.

**Đúng:** đặt @Transactional tại service điều phối, gọi locking repository method, kiểm tra invariant, sửa managed entity và kết thúc transaction sau tất cả các writes.

### 8.3. EntityManager.setLockMode

Một cách không dùng repository annotation:

~~~java
StockItem stock = em.createQuery(
    """
    select s from StockItem s
    where s.id = :id
      and s.tenantId = :tenant
    """,
    StockItem.class
)
.setParameter("id", id)
.setParameter("tenant", tenantId)
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
.getSingleResult();
~~~

Ưu điểm: lock mode gắn trực tiếp với query được tạo. Cần bắt NoResultException theo contract và để transaction boundary ở application service/decorator.

### 8.4. Lấy lock sau khi đã nạp entity

~~~java
StockItem stock = em.find(StockItem.class, stockId);
em.lock(stock, LockModeType.PESSIMISTIC_WRITE);
stock.reserve(quantity);
~~~

Điều này có thể hợp lệ với managed entity, nhưng nếu đã đọc state trước khi có lock, cần hiểu **dữ liệu lúc lock có còn đúng không** và provider refresh/version behavior. Với workflow nhạy cảm, **locking read từ đầu** dễ reasoning hơn; nếu lock sau, phải kiểm tra state dưới lock và không dựa vào snapshot cũ chưa được làm mới.

### 8.5. Query locks qua joins

Một JPQL query JOIN FETCH nhiều relations cùng PESSIMISTIC_WRITE có thể tạo SQL với scope khóa rộng hoặc provider follow-on locking; DB có thể không cho dùng locking clause với một số join/aggregation. Khi chỉ cần khóa StockItem, ưu tiên query đơn giản theo PK/unique key, tải graph khác có kiểm soát.

### 8.6. Tên method không là bảo đảm

Một method tên findForUpdate không tự lấy khóa nếu thiếu @Lock/setLockMode/native FOR UPDATE. Kiểm tra SQL generated và **concurrent integration test** để tránh refactor làm mất behavior.

## 9. Application service: transaction bao trọn quyền, lock, kiểm tra và ghi

### 9.1. Result DTO

~~~java
package com.example.locking.application;

public record ReservationResult(
    Long stockId,
    int remaining
) {}
~~~

### 9.2. StockReservationService

~~~java
package com.example.locking.application;

import com.example.locking.domain.*;
import com.example.locking.repository.StockRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StockReservationService {

    private final StockRepository repository;

    public StockReservationService(
            StockRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public ReservationResult reserve(
            String authorizedTenant,
            Long stockId,
            int quantity) {

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity must be positive"
            );
        }

        StockItem stock = repository
            .lockByIdAndTenant(stockId, authorizedTenant)
            .orElseThrow(StockNotFoundException::new);

        stock.reserve(quantity);

        // StockItem managed: JPA dirty checking sẽ
        // UPDATE khi flush/commit.
        return new ReservationResult(
            stock.getId(),
            stock.getAvailable()
        );
    }
}
~~~

**authorizedTenant** trong ví dụ là một giá trị do tầng xác thực/ủy quyền tin cậy cung cấp. Trong HTTP production API, không để client tự tùy ý gửi tenantId rồi tin rằng nó được quyền sửa row; một TenantContext hoặc Principal-based access service nên sở hữu quyết định.

### 9.3. Vì sao @Transactional ở service, không chỉ repository?

Nếu transaction chỉ bao câu SELECT lock ở repository rồi kết thúc, lock có thể được giải phóng trước khi gọi stock.reserve. Toàn bộ khoảng:
1. Lấy lock;
2. Kiểm tra available;
3. Trừ quantity;
4. Persist các related writes nếu có;
5. Commit;

phải ở trong transaction theo business unit of work.

### 9.4. Nếu phải tạo đơn hàng hoặc outbox?

Mở rộng phương thức:

~~~java
@Transactional
public OrderReceipt placeOrder(PlaceOrderCommand cmd) {
    String tenant = tenantAccess.requireOrderPermission();

    StockItem stock = repository
        .lockByIdAndTenant(cmd.stockId(), tenant)
        .orElseThrow(StockNotFoundException::new);

    stock.reserve(cmd.quantity());

    Order order = orderRepository.save(
        Order.place(tenant, cmd, clock.instant())
    );

    outboxRepository.save(
        OutboxMessage.fromOrder(order)
    );

    return OrderReceipt.from(order);
}
~~~

Các Order/Outbox classes là business skeleton, nhưng **điểm thiết kế** rất cụ thể: stock + order + outbox ở **cùng database transaction**. Nếu outbox INSERT lỗi, stock không được commit. Không gọi payment gateway/email ngay dưới row lock.

### 9.5. Lưu ý commit-time exception

Phần body của một Spring @Transactional method có thể tạo ReservationResult trước khi transaction interceptor flush/commit. Caller gọi **qua Spring proxy** chỉ nhận success khi invocation transaction hoàn tất thành công; nếu commit lỗi, exception có thể phát sinh **sau khi method body đã return**. Error mapping và retry nên ở caller/interceptor sau transaction boundary.

### 9.6. Không nuốt lỗi rồi return success

~~~java
@Transactional
public ReservationResult brokenReserve(...) {
    StockItem stock = repository
        .lockByIdAndTenant(...)
        .orElseThrow();

    try {
        stock.reserve(quantity);
    } catch (RuntimeException ex) {
        log.warn("ignored", ex);
    }

    return new ReservationResult(...);
}
~~~

Catch-and-ignore có thể trả success dù không có reservation. Nếu cần classify lỗi, propagate application exception hoặc kết thúc transaction rõ theo policy.

### 9.7. Không dùng em.clear để “giải phóng lock” sớm

Nếu service gọi em.flush(); em.clear(); trước commit, row lock database vẫn có thể được giữ đến transaction end. Clear chỉ detach managed entities; lock lifetime không phụ thuộc việc Java object còn attached hay không.




## 10. Chuẩn bị môi trường integration test

Một H2 in-memory database có thể khác PostgreSQL về:
- SQL locking syntax;
- Row-level lock conflicts;
- MVCC visibility;
- Transaction isolation;
- Lock timeout/SQLState;
- Deadlock detection;
- DDL và indexes.

Vì bài này tập trung **tranh chấp tài nguyên thực**, nên nên chạy kiểm thử concurrency trên **PostgreSQL thực qua Testcontainers**. Không chỉ dựa vào mocked repository hoặc H2.

### 10.1. Dependencies cần có

Với Maven/Gradle, project cần các nhóm dependency tương ứng:
- Spring Boot Starter Data JPA;
- Spring Boot Starter Validation nếu API nhận DTO có Bean Validation;
- PostgreSQL JDBC driver;
- Spring Boot Starter Test (JUnit Jupiter, Spring Test);
- Testcontainers PostgreSQL module;
- Testcontainers JUnit Jupiter integration.

**Chú ý versions:** Dùng Spring Boot/Testcontainers versions tương thích và Docker/OCI runtime sẵn sàng để Testcontainers khởi chạy DB. Bài không khóa vào một version cụ thể; cấu hình dependency phải theo BOM/management của project thay vì ghép ngẫu nhiên versions.

### 10.2. Testcontainers PostgreSQL fixture

~~~java
package com.example.locking;

import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.util.UUID;

@SpringBootTest
@Testcontainers
class StockReservationIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void dataSource(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url", POSTGRES::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username", POSTGRES::getUsername
        );
        registry.add(
            "spring.datasource.password", POSTGRES::getPassword
        );
        registry.add(
            "spring.jpa.hibernate.ddl-auto",
            () -> "create-drop"
        );
    }

    @Autowired
    StockRepository repository;

    @Autowired
    StockReservationService service;

    @Autowired
    PlatformTransactionManager transactionManager;

    private TransactionTemplate tx;
    private Long stockId;

    @BeforeEach
    void setUp() {
        tx = new TransactionTemplate(transactionManager);

        stockId = tx.execute(status ->
            repository.saveAndFlush(
                new StockItem(
                    "tenant-a",
                    "SKU-" + UUID.randomUUID(),
                    5
                )
            ).getId()
        );
    }
}
~~~

Đoạn này là **khung test class**; các test methods dưới đây đặt vào bên trong class tương ứng, cùng imports JUnit assert, java.util.concurrent và domain/repository classes.

**Tuyệt đối không đặt @Transactional trên chính test method/test class** nếu muốn test boundary của service như một transaction thực. Nếu test framework mở outer transaction rồi rollback sau test, service @Transactional(REQUIRED) có thể chỉ join outer test transaction, làm kết quả commit/lock tests sai lệch.

### 10.3. Vì sao fixture được ghi bằng TransactionTemplate?

~~~java
stockId = tx.execute(status ->
    repository.saveAndFlush(
        new StockItem("tenant-a", uniqueSku, 5)
    ).getId()
);
~~~

Sau khi tx.execute return thành công, transaction fixture đã commit theo TransactionTemplate. Hai workers có thể nhìn thấy row này từ **hai transaction riêng**. Nếu tạo fixture trong uncommitted test transaction, workers có thể không thấy row hoặc bị block vì lock của setup.

### 10.4. Không giả định ddl-auto=create-drop là cấu hình production

Hibernate auto-DDL là tiện cho test minh họa. Production cần migrations có quản lý phiên bản; không deploy create-drop lên database thật. Với integration tests sát production hơn, dùng Flyway/Liquibase migrations và không tự override ddl-auto trong test.

### 10.5. Chạy tests trên một DB cô lập

Các test có thể ghi khóa và chủ động timeout. Không chạy trên DB production, không dùng một row SKU cố định của ứng dụng thật; fixture riêng theo test giúp giảm giao thoa.

### 10.6. Các transaction cần connection riêng

Hai workers được chạy ở threads khác nhau. Với Spring JPA imperative transactions, mỗi thread tham gia transaction/context tương ứng qua transaction manager/proxy. Connection pool phải đủ connections để:
- Worker giữ lock;
- Worker tranh lock;
- Main thread setup/readback khi cần.

Với pool size=1, test có thể đứng chờ connection pool thay vì thực sự tranh row-level lock; cần tránh kết luận sai.

## 11. Integration test thứ nhất: hai người cùng tranh tồn kho

Mục tiêu: hai requests mỗi request cần 4 chiếc, available=5. Chỉ **một request** được thành công. Test này kiểm chứng kết quả nghiệp vụ khi chạy đồng thời, nhưng chưa tự chứng minh rằng đúng **PESSIMISTIC_WRITE** (một implementation @Version đúng cũng có thể cho cùng kết quả).

### 11.1. Test dùng ExecutorService và hai latches

~~~java
@Test
void concurrentReservationsCannotOversell()
        throws Exception {

    ExecutorService executor =
        Executors.newFixedThreadPool(2);

    CountDownLatch ready = new CountDownLatch(2);
    CountDownLatch start = new CountDownLatch(1);

    Callable<String> attempt = () -> {
        ready.countDown();

        if (!start.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "Workers did not start"
            );
        }

        try {
            service.reserve("tenant-a", stockId, 4);
            return "SUCCESS";
        } catch (InsufficientStockException ex) {
            return "SOLD_OUT";
        }
    };

    try {
        Future<String> first = executor.submit(attempt);
        Future<String> second = executor.submit(attempt);

        assertTrue(ready.await(5, TimeUnit.SECONDS));

        start.countDown();

        String a = first.get(10, TimeUnit.SECONDS);
        String b = second.get(10, TimeUnit.SECONDS);

        assertEquals(
            Set.of("SUCCESS", "SOLD_OUT"),
            Set.of(a, b)
        );

        Integer remaining = tx.execute(status ->
            repository.findByIdAndTenant(
                stockId, "tenant-a"
            )
            .orElseThrow()
            .getAvailable()
        );

        assertEquals(1, remaining);
    } finally {
        start.countDown();
        executor.shutdownNow();
    }
}
~~~

Cần imports java.util.Set, java.util.concurrent.*, JUnit assertions; Spring repositories/service đã inject ở test fixture.

### 11.2. Tại sao dùng ready và start?

- ready đếm khi cả hai worker đã đi tới start gate;
- start.countDown() cho phép chúng cùng cạnh tranh;
- Không dùng Thread.sleep(50) để đoán scheduling;
- Future.get với deadline tránh test treo vô hạn.

Ngay cả khi khởi động gần nhau, scheduler không bảo đảm SQL xảy ra cùng nanosecond. Test này xác nhận **outcome**, còn test giữ khóa và timeout ở mục sau cung cấp bằng chứng sát hơn về lock behavior.

### 11.3. Tại sao assert kết quả là một success, một sold-out?

Nếu ProductStock.available ban đầu 5 và mỗi request reserve 4:
- Giao dịch thành công thứ nhất giảm 5 → 1;
- Giao dịch còn lại lấy lock sau và thấy 1;
- reserve(4) ném InsufficientStockException;
- Không tạo oversell.

Nếu một request fail bởi lock timeout thay vì sold-out, test này không pass; đó là behavior khác cần policy/test riêng.

### 11.4. Vì sao không catch mọi RuntimeException như SOLD_OUT?

Sai:

~~~java
catch (RuntimeException ex) {
    return "SOLD_OUT";
}
~~~

Một DataAccessException, connection failure, deadlock hoặc optimistic conflict không phải “hết hàng”. Test sẽ che lỗi thật. Chỉ catch **domain error** InsufficientStockException; mọi lỗi kỹ thuật khác khiến Future.get ném ExecutionException và test fail.

### 11.5. Vì sao đọc lại sau futures hoàn thành?

Cả hai proxy invocations đã kết thúc, tương ứng transactions đã commit/rollback hoặc lỗi. Readback qua TransactionTemplate tạo một read unit of work mới, không lấy object managed cũ đã cache giá trị available trước commit.

### 11.6. Phiên bản cần tránh: test @Transactional

Nếu test method bọc outer transaction, service calls ở worker threads không tự join nó; fixture chưa commit có thể không visible. @Transactional trên test còn có thể làm main-thread readback thấy state khác. Với concurrency test, **không bọc test bằng một outer rollback-only transaction**.

## 12. Integration test thứ hai: giữ khóa rõ ràng giữa hai transactions

Mục tiêu: kiểm chứng transaction A giữ PESSIMISTIC_WRITE lock, transaction B không thể hoàn tất locking reservation trước khi A kết thúc.

### 12.1. Helper để đợi latch có deadline

~~~java
private static void awaitLatch(
        CountDownLatch latch,
        String description) {

    try {
        if (!latch.await(8, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "Timed out waiting for " + description
            );
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(
            "Interrupted: " + description, ex
        );
    }
}
~~~

Khi chạy trong transaction callback, helper có thể ném RuntimeException để transaction rollback nếu gate không được nhả đúng hạn.

### 12.2. Tách hai threads, hai physical transactions

~~~java
@Test
void competingLockingReadWaitsForHolder()
        throws Exception {

    ExecutorService executor =
        Executors.newFixedThreadPool(2);

    CountDownLatch locked = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    CountDownLatch secondStarted = new CountDownLatch(1);

    Future<?> holder = executor.submit(() -> {
        tx.executeWithoutResult(status -> {
            StockItem stock = repository
                .lockByIdAndTenant(
                    stockId, "tenant-a"
                )
                .orElseThrow();

            locked.countDown();
            awaitLatch(release, "release holder");

            stock.reserve(1);
        });
    });

    try {
        assertTrue(locked.await(5, TimeUnit.SECONDS));

        Future<ReservationResult> competitor =
            executor.submit(() -> {
                secondStarted.countDown();
                return service.reserve(
                    "tenant-a", stockId, 1
                );
            });

        assertTrue(
            secondStarted.await(5, TimeUnit.SECONDS)
        );

        // Trong khoảng holder đang giữ row lock,
        // competitor không được hoàn tất reservation.
        assertThrows(
            TimeoutException.class,
            () -> competitor.get(
                200, TimeUnit.MILLISECONDS
            )
        );

        release.countDown();

        holder.get(10, TimeUnit.SECONDS);

        ReservationResult result =
            competitor.get(10, TimeUnit.SECONDS);

        assertEquals(3, result.remaining());

        Integer remaining = tx.execute(status ->
            repository.findByIdAndTenant(
                stockId, "tenant-a"
            ).orElseThrow().getAvailable()
        );

        assertEquals(3, remaining);
    } finally {
        release.countDown();
        executor.shutdownNow();
    }
}
~~~

### 12.3. Vì sao holder giữ khóa trong transaction callback?

TransactionTemplate mở transaction cho callback:
- Repository locking query lấy row lock;
- Signal locked sau khi query hoàn tất;
- Chờ gate release trong khi transaction vẫn active;
- reserve(1);
- Callback kết thúc, TransactionTemplate commit và giải phóng row lock.

Service ở worker B chạy trong transaction của nó, phải chờ row lock holder trước khi đọc–sửa.

### 12.4. Giới hạn của assertTimeout ở test blocking

Điều kiện competitor không hoàn tất trong 200ms có thể bị ảnh hưởng bởi scheduler, startup hoặc connection pool. **Đây là test integration bổ sung**, không phải phép chứng minh tuyệt đối rằng B đã chạm chính xác SQL lock khi time window hết. Kiểm thử timeout PostgreSQL ở mục kế tiếp cho tín hiệu trực tiếp hơn về tranh chấp row lock.

Có thể tăng độ tin cậy bằng:
- Một instrumentation hook ngay trước locking repository query;
- JDBC proxy/DB wait event observation;
- Bảo đảm connection pool đủ;
- Có real PostgreSQL fixture;
- Chạy nhiều iterations/metrics.

Không xây test chỉ dựa vào Thread.sleep và thời điểm CPU scheduling.

### 12.5. Kiểm tra final remaining=3

Available=5, holder reserve 1 → 4; competitor reserve 1 sau holder → 3. Nếu competitor làm việc trên stale snapshot không có concurrency guard, test có thể phát hiện giá trị cuối sai hoặc conflicts bất thường.

### 12.6. Test cần chống treo khi assertion thất bại

finally luôn release.countDown, để holder không giữ DB lock vô hạn nếu assert trước đó lỗi. executor.shutdownNow được dùng sau attempt; khi môi trường test chậm hoặc lock timeout không đúng, futures deadlines giúp báo lỗi thay vì test treo mãi.

## 13. Integration test thứ ba: lock timeout thật trên PostgreSQL

Một bài test quan trọng hơn kiểm tra “Future vẫn chưa hoàn tất” là yêu cầu database **thử lấy khóa nhưng phải báo timeout** khi row đang do transaction khác giữ.

### 13.1. PostgreSQL hỗ trợ lock_timeout

Trong PostgreSQL, setting **lock_timeout** giới hạn thời gian một statement chờ để lấy lock. Có thể đặt giá trị **LOCAL** trong transaction để tránh ảnh hưởng những transactions khác dùng chung connection pool.

Ví dụ SQL:

~~~sql
BEGIN;

SELECT set_config('lock_timeout', '250ms', true);

SELECT *
FROM stock_items
WHERE id = 101
FOR UPDATE;

COMMIT;
~~~

Tham số true của set_config yêu cầu phạm vi local theo transaction. Nếu row đang bị một transaction khác khóa và thời gian chờ vượt 250ms, PostgreSQL thường phát lỗi lock unavailable/lock timeout; statement thất bại và transaction cần rollback.

**Đây là PostgreSQL-specific behavior**, không phải JPA chuẩn. MySQL, SQL Server, Oracle có cú pháp timeout/locking và semantics riêng.

### 13.2. Test dùng EntityManager đã bind vào transaction hiện tại

Thêm fixture vào class test:

~~~java
@PersistenceContext
EntityManager em;
~~~

Test:

~~~java
@Test
void lockAttemptTimesOutWhenRowIsHeld()
        throws Exception {

    ExecutorService executor =
        Executors.newSingleThreadExecutor();

    CountDownLatch holderLocked = new CountDownLatch(1);
    CountDownLatch releaseHolder = new CountDownLatch(1);

    Future<?> holder = executor.submit(() -> {
        tx.executeWithoutResult(status -> {
            repository.lockByIdAndTenant(
                stockId, "tenant-a"
            ).orElseThrow();

            holderLocked.countDown();

            awaitLatch(
                releaseHolder, "release after timeout test"
            );
        });
    });

    try {
        assertTrue(
            holderLocked.await(5, TimeUnit.SECONDS)
        );

        RuntimeException failure = assertThrows(
            RuntimeException.class,
            () -> tx.executeWithoutResult(status -> {

                // PostgreSQL-specific transaction-local setting.
                em.createNativeQuery(
                    """
                    select set_config(
                        'lock_timeout', '250ms', true
                    )
                    """
                ).getSingleResult();

                // Transaction B phải lấy khóa xung đột
                // với transaction A đang giữ.
                repository.lockByIdAndTenant(
                    stockId, "tenant-a"
                ).orElseThrow();
            })
        );

        assertNotNull(failure);

    } finally {
        releaseHolder.countDown();
        holder.get(10, TimeUnit.SECONDS);
        executor.shutdownNow();
    }
}
~~~

Thêm imports:
- jakarta.persistence.EntityManager;
- jakarta.persistence.PersistenceContext;
- java.util.concurrent.*;
- JUnit assertions.

### 13.3. Vì sao tx.executeWithoutResult trong main thread?

Holder được chạy trong worker thread, đang giữ khóa transaction A. Main test thread mở một transaction B bằng TransactionTemplate, đặt PostgreSQL lock_timeout local trên **connection của transaction B**, rồi gọi locking repository query trong cùng transaction đó.

Khi timeout:
- Statement của B thất bại;
- JPA/Spring có thể bọc exception qua nhiều tầng;
- TransactionTemplate rollback B;
- Holder A chỉ giải phóng khóa sau releaseHolder;
- finally không để A giữ khóa vô hạn.

### 13.4. Tại sao chỉ assert RuntimeException ở ví dụ cơ bản?

Các wrappers khác nhau theo Hibernate/Spring versions:
- JPA LockTimeoutException;
- JPA PessimisticLockException;
- org.springframework.dao.CannotAcquireLockException;
- org.springframework.dao.PessimisticLockingFailureException;
- Exception khác chứa JDBC driver cause.

Nếu cần khẳng định chính xác **PostgreSQL SQLSTATE 55P03**, hãy unwrap cause chain đến SQLException hoặc instrument JDBC layer. Cần lưu ý một số lỗi PostgreSQL khác cũng dùng SQLSTATE lock-not-available category tùy statement; test nên kết hợp tình huống holder đang giữ lock và trace tương ứng.

**Không catch mọi RuntimeException như dấu hiệu đã đúng behavior** ở production. Đây là test rút gọn minh họa; một test mạnh hơn nên kiểm tra SQLState/error category cụ thể và đo lock wait theo DB.

### 13.5. Không dựa vào JPA timeout hint như một guarantee tuyệt đối

JPA có standard hint **jakarta.persistence.lock.timeout**, thường biểu diễn timeout bằng milliseconds. Ví dụ:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.lock.timeout", 250
);

StockItem stock = em.find(
    StockItem.class,
    stockId,
    LockModeType.PESSIMISTIC_WRITE,
    hints
);
~~~

Nhưng hint support và cách provider/dialect chuyển thành SQL có thể khác nhau; một số hints có thể bị bỏ qua khi DB không hỗ trợ cơ chế tương ứng. **Không suy ra** cứ đặt 250 là mọi driver/DB bảo đảm chính xác 250ms.

Với PostgreSQL integration test cần timeout có thể dự đoán, đặt **SET LOCAL lock_timeout** trong transaction giúp ràng buộc vào backend cụ thể, đồng thời đánh dấu sự phụ thuộc rõ ràng.

### 13.6. Phân biệt các loại timeout

| Timeout | Nơi phát sinh | Điều nó giới hạn |
|---|---|---|
| lock_timeout | PostgreSQL | Thời gian statement chờ lock |
| statement_timeout | PostgreSQL | Tổng thời gian chạy statement |
| query timeout hint | JPA/provider/driver | Thời gian thực thi query tùy hỗ trợ |
| transaction timeout | Spring/JTA | Thời gian unit of work tùy manager |
| connection acquisition timeout | Connection pool | Chờ lấy connection |
| socket/network timeout | JDBC driver/network | Network operations |

Nếu pool chỉ có một connection, transaction B có thể chờ pool timeout thay vì chờ **row lock**, và test sẽ thất bại vì lý do khác. Một benchmark/test phải xác định nguồn timeout.

### 13.7. Có cần test transaction A vẫn commit sau khi B timeout?

Có thể thêm:
1. Holder A reserve(1);
2. B timeout trong lúc A giữ lock;
3. Release A;
4. Assert A commit thành công;
5. Read available=4;
6. Assert B không ghi gì.

Cần chắc chắn B rollback và không làm hỏng A; hai transactions độc lập không tự ảnh hưởng rollback state của nhau.

## 14. LockTimeoutException và PessimisticLockException

### 14.1. JPA phân biệt phạm vi rollback do lỗi lock

Các exception JPA thường gặp:
- **LockTimeoutException:** một tình huống không lấy được lock nhưng chỉ statement-level rollback theo contract mà provider báo;
- **PessimisticLockException:** tình huống lock failure dẫn tới transaction-level rollback;
- PersistenceException hoặc wrapper provider khác;
- Spring DataAccessException đã được dịch từ provider/driver exception.

Không suy rằng **mọi PostgreSQL lock_timeout** sẽ xuất hiện nguyên dạng LockTimeoutException; backend SQL statement failure có thể làm cả DB transaction aborted, tùy đường thực thi và provider.

### 14.2. Sau lock failure, an toàn nhất là kết thúc transaction

Trong một use case Spring:

~~~java
@Transactional
public ReservationResult reserve(...) {
    return repository.lockByIdAndTenant(...)
        .map(stock -> {
            stock.reserve(quantity);
            return new ReservationResult(
                stock.getId(), stock.getAvailable()
            );
        })
        .orElseThrow(StockNotFoundException::new);
}
~~~

Nếu locking query ném exception:
- Để exception propagate khỏi transactional entrypoint;
- Rollback theo rule phù hợp;
- Không tiếp tục ghi những entities khác trong transaction đang có lỗi;
- Nếu retry, bắt đầu transaction và persistence context **mới**.

### 14.3. Đừng trả “hết hàng” khi thực chất là lock timeout

“Hết hàng” nghĩa stock đã được đọc và domain xác nhận available không đủ. “Không lấy được khóa” nghĩa hệ thống **chưa quyết định** có đủ hàng hay không do contention/timeout.

API có thể trả:
- BUSINESS: INSUFFICIENT_STOCK khi kiểm tra domain fail;
- RETRYABLE: STOCK_BUSY / LOCK_CONFLICT khi lock timeout;
- TRANSIENT_TRANSACTION_FAILURE khi deadlock/serialization failure;
- GENERIC_FAILURE khi không xác định.

HTTP mapping tùy contract; đừng tiết lộ SQL/tenant/stack trace vào public response.

### 14.4. Không retry vô hạn

Một lock conflict có thể là transient, nhưng:
- Retry đồng loạt tạo thundering herd;
- Giữ connections lâu;
- Tạo deadlock khác;
- Gây starvation cho business requests;
- Ngăn không cho phép hủy job.

Dùng **bounded retry**, backoff có jitter và global deadline phù hợp. Mỗi retry phải chứa trọn **business unit of work** trên transaction mới, không chỉ retry một JDBC statement lẻ.

### 14.5. Những lỗi không nên retry như lock timeout

- Quantity âm;
- SKU không tồn tại;
- Tenant không được phép;
- Sản phẩm đã ngừng bán theo business rule;
- UNIQUE key mismatch của idempotency;
- FK/schema migration mismatch;
- Serialization payload invalid.

Phân loại errors tránh biến request sai thành truy vấn chờ DB kéo dài.

## 15. NOWAIT: không muốn xếp hàng chờ khóa

Một số nghiệp vụ yêu cầu phản hồi nhanh rằng “tài nguyên đang được xử lý” thay vì chờ hàng giây.

PostgreSQL:

~~~sql
BEGIN;

SELECT id, tenant_id, sku, available
FROM stock_items
WHERE id = :id
FOR UPDATE NOWAIT;

-- Nếu row bị khóa xung đột,
-- câu SELECT trả lỗi ngay.
COMMIT;
~~~

### 15.1. NOWAIT dùng khi nào?

- Người dùng chọn một tài nguyên hiếm và UI cần phản hồi nhanh;
- Một control-plane operation có deadline ngắn;
- Job xử lý task có thể retry sau;
- Một thao tác mà chờ làm giảm trải nghiệm hoặc tốn pool connections.

### 15.2. NOWAIT không thay domain validation

Sau khi có lock, vẫn cần kiểm tra available/ownership/business status. Không phải chỉ vì NOWAIT thành công thì reservation chắc chắn hợp lệ.

### 15.3. JPA portability

Một số Hibernate versions/dialects chuyển lock timeout hint giá trị 0 thành NOWAIT, nhưng không phải guarantee chung cho mọi JPA provider và DB. Nếu hệ thống dựa vào NOWAIT, dùng API/provider dialect đã được test, hoặc native SQL được encapsulate trong repository adapter.

### 15.4. Native SQL vẫn cần transaction

~~~java
em.createNativeQuery(
    """
    SELECT id
    FROM stock_items
    WHERE id = :id
    FOR UPDATE NOWAIT
    """
)
.setParameter("id", id)
.getResultList();
~~~

Một native SQL query khóa row bên trong active transaction; nếu nó chỉ tồn tại trong repository method rồi transaction commit trước khi domain update, bảo vệ vẫn không đủ.

### 15.5. Behavior khi không tìm thấy row

Không tìm thấy row không giống NOWAIT conflict. Query trả empty result nếu không có row thỏa predicate; nếu row đang bị khóa, NOWAIT báo lỗi. Mapping HTTP/business statuses cần phân biệt hai trường hợp.

## 16. SKIP LOCKED: chọn tài nguyên khác thay vì chờ

Một use case khác: nhiều workers chọn các tasks chưa xử lý từ cùng bảng, không nhất thiết yêu cầu đúng một stock ID duy nhất.

PostgreSQL:

~~~sql
SELECT id, status, created_at
FROM background_jobs
WHERE status = 'PENDING'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED
LIMIT 20;
~~~

Nếu một row đang bị transaction khác khóa, query có thể **bỏ qua row đó** và nhận rows khác đang sẵn sàng.

### 16.1. SKIP LOCKED phù hợp với queue-like workloads

- Nhiều workers claim pending tasks;
- Có nhiều tasks thay thế được;
- Không cần đợi đúng một row;
- Work item được đánh dấu claimed/processing trong transaction;
- Có lease/timeout/reclaim policy cho worker crash.

### 16.2. Không áp SKIP LOCKED bừa vào order cùng stock ID

Khách muốn mua StockItem#101. Nếu row đang bị khóa và query SKIP LOCKED trả empty, không được tự suy “hết hàng” hoặc chọn một stock row của tenant/SKU khác. Với exact resource, chờ/NOWAIT/atomic SQL thường diễn đạt business semantics tốt hơn.

### 16.3. Fairness và starvation

SKIP LOCKED không cam kết thứ tự công bằng tuyệt đối. Một row liên tục bị khóa có thể bị skip nhiều lần; job worker cần:
- Retry/backoff;
- Stale lease recovery;
- Monitoring pending age;
- Work prioritization;
- Dead-letter/quarantine policies.

### 16.4. Native query cho queue claim

~~~java
List<Number> ids = em.createNativeQuery(
    """
    select id
    from background_jobs
    where status = 'PENDING'
    order by created_at, id
    for update skip locked
    limit :batchSize
    """
)
.setParameter("batchSize", batchSize)
.getResultList();
~~~

Kết quả native query scalar ID có thể trả kiểu Number/BigInteger/Long tùy provider/driver; cần map cẩn thận. Trong cùng transaction, update job status thành CLAIMED rồi commit trước khi worker xử lý external work lâu dài.

### 16.5. Lock không phải distributed lease

Database row lock giải phóng khi transaction kết thúc. Nếu worker cần xử lý 10 phút ngoài transaction, không nên giữ row lock cả 10 phút. Thay bằng **claim record/leaseUntil/status** được commit nhanh; lease recovery và idempotent processing giải quyết worker crash.

### 16.6. JPA/Hibernate hints cho SKIP LOCKED

Một số provider có constants hoặc lock timeout convention tương ứng SKIP LOCKED, nhưng đó là provider-specific; không coi một numeric hint như -2 là contract phổ quát của Jakarta Persistence. Cần inspect generated SQL và chạy integration tests trên target database.

## 17. Deadlock: khi hai transactions khóa tài nguyên theo thứ tự khác nhau

Khóa bi quan giảm một loại race, nhưng có thể gây **deadlock** nếu nhiều transactions cùng cần nhiều rows và lấy khóa theo thứ tự xung đột.

### 17.1. Sơ đồ deadlock hai rows

~~~text
T1                                  T2
----------------------------------  ----------------------------------
BEGIN                               BEGIN
LOCK Stock#A ✓                      LOCK Stock#B ✓
LOCK Stock#B → chờ T2              LOCK Stock#A → chờ T1

Wait-for graph:
T1 ──waits for B held by──> T2
T2 ──waits for A held by──> T1

Database phát hiện deadlock và hủy một transaction.
~~~

Trong PostgreSQL, deadlock detection có thể xảy ra sau một khoảng delay; lỗi thường dẫn tới rollback transaction nạn nhân. Transaction còn lại có thể tiếp tục khi lock được giải phóng.

### 17.2. Quy tắc quan trọng: khóa theo thứ tự ổn định

Nếu một giao dịch cần cập nhật nhiều StockItems, hãy định nghĩa một thứ tự, ví dụ:
- Sort theo primary key tăng dần;
- Hoặc theo tenantId + stockId ổn định;
- Mọi code paths cùng tuân thủ cùng thứ tự.

~~~java
List<Long> orderedIds = stockIds.stream()
    .distinct()
    .sorted()
    .toList();

for (Long stockId : orderedIds) {
    StockItem stock = repository
        .lockByIdAndTenant(stockId, tenantId)
        .orElseThrow(StockNotFoundException::new);

    reserveAccordingToRequest(stock);
}
~~~

Phần reserveAccordingToRequest đại diện logic business map stockId→quantity. Lấy lock theo sorted IDs giảm nguy cơ deadlock do thứ tự trái chiều, nhưng **không bảo đảm loại bỏ mọi deadlock**: database còn locks trên indexes, foreign keys, other rows hoặc triggers.

### 17.3. Một query IN và ORDER BY có đủ không?

Một query:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("""
    select s
    from StockItem s
    where s.id in :ids
    order by s.id
    """)
List<StockItem> lockAll(
    @Param("ids") List<Long> ids
);
~~~

có thể giúp cố định result order, nhưng **result ordering không luôn là bảo đảm tuyệt đối về thứ tự physical lock acquisition** trên mọi DB/query plan. Nếu correctness/deadlock policy phụ thuộc strict order, cần kiểm tra SQL execution behavior và có thể lock từng row theo thứ tự đã sort trong một transaction.

### 17.4. Nếu deadlock vẫn xảy ra

Không thể chỉ “thử lại câu SELECT” sau khi database đã abort transaction. Cần:
1. Rollback transaction nạn nhân;
2. Bỏ persistence context đã lỗi;
3. Backoff với jitter;
4. Mở transaction mới;
5. Đọc state mới;
6. Chạy lại toàn business operation nếu idempotent và deadline cho phép.

### 17.5. PostgreSQL SQLSTATE

Deadlock trong PostgreSQL thường có SQLSTATE **40P01**, khác với lock-not-available **55P03**. Serialization failure thường **40001**. Spring/provider có thể bọc errors; khi phân loại retry, unwrap SQLState một cách thận trọng ở infrastructure boundary.

Không gửi SQLState hoặc raw SQL lên public API nếu không cần.

## 18. Thực hành mô phỏng deadlock có kiểm soát

Bài test deadlock cần:
- Hai rows đã commit;
- Hai workers, mỗi worker một transaction;
- Worker A khóa A trước, B khóa B trước;
- Một barrier bảo đảm cả hai đã giữ khóa đầu tiên;
- Mỗi worker thử khóa row còn lại;
- Database giải quyết deadlock bằng việc fail một transaction;
- finally giải phóng threads/resources.

### 18.1. Khung test

~~~java
@Test
void oppositeLockOrderCanDeadlock()
        throws Exception {

    Long stockA = tx.execute(status ->
        repository.saveAndFlush(
            new StockItem(
                "tenant-a",
                "A-" + UUID.randomUUID(),
                10
            )
        ).getId()
    );

    Long stockB = tx.execute(status ->
        repository.saveAndFlush(
            new StockItem(
                "tenant-a",
                "B-" + UUID.randomUUID(),
                10
            )
        ).getId()
    );

    CountDownLatch firstLocksHeld = new CountDownLatch(2);
    CountDownLatch allowSecondLock = new CountDownLatch(1);

    ExecutorService executor =
        Executors.newFixedThreadPool(2);

    Callable<String> first = () -> attemptTwoLocks(
        stockA, stockB,
        firstLocksHeld, allowSecondLock
    );

    Callable<String> second = () -> attemptTwoLocks(
        stockB, stockA,
        firstLocksHeld, allowSecondLock
    );

    try {
        Future<String> fa = executor.submit(first);
        Future<String> fb = executor.submit(second);

        assertTrue(
            firstLocksHeld.await(5, TimeUnit.SECONDS)
        );

        allowSecondLock.countDown();

        String ra = fa.get(15, TimeUnit.SECONDS);
        String rb = fb.get(15, TimeUnit.SECONDS);

        // Ít nhất một transaction thường sẽ nhận
        // lỗi tranh chấp/deadlock khi cả hai đã giữ
        // một row khác nhau và cùng yêu cầu row còn lại.
        assertTrue(
            ra.startsWith("ERROR:")
                || rb.startsWith("ERROR:")
        );
    } finally {
        allowSecondLock.countDown();
        executor.shutdownNow();
    }
}
~~~

### 18.2. Helper attemptTwoLocks

~~~java
private String attemptTwoLocks(
        Long firstId,
        Long secondId,
        CountDownLatch firstLocksHeld,
        CountDownLatch allowSecondLock) {

    try {
        tx.executeWithoutResult(status -> {
            repository.lockByIdAndTenant(
                firstId, "tenant-a"
            ).orElseThrow();

            firstLocksHeld.countDown();
            awaitLatch(
                allowSecondLock, "second lock gate"
            );

            repository.lockByIdAndTenant(
                secondId, "tenant-a"
            ).orElseThrow();
        });

        return "COMMITTED";
    } catch (RuntimeException ex) {
        return "ERROR:" + ex.getClass().getSimpleName();
    }
}
~~~

**Giải thích:** Vì cả A và B đã giữ khóa row đầu tiên trước khi gate mở, mỗi transaction cố lấy row bị transaction còn lại giữ. Đây là một cách tái hiện vòng chờ, thay vì trông vào Thread.sleep.

**Giới hạn:** Test trên môi trường/DB được cấu hình đúng vẫn có thể fail bởi lock timeout, query deadline hoặc scheduling hạ tầng. Với một deadlock-specific regression, phải unwrap và assert **SQLSTATE 40P01** của transaction nạn nhân; ở đây test minh họa cấu trúc đồng bộ để học. Không sử dụng test này như benchmark throughput hoặc chạy trên DB chung.

### 18.3. Vì sao không nuốt lỗi và commit tiếp?

Helper trả error string **sau khi TransactionTemplate đã thoát và rollback** vì exception. Nó không catch exception bên trong transaction callback rồi tiếp tục ghi state không xác định.

### 18.4. Giảm deadlock bằng chính sách sort

Một biến thể:
- A và B đều sort [stockA, stockB] theo ID;
- Cả hai xin khóa thấp nhất trước;
- Một worker chờ worker còn lại ngay từ khóa đầu;
- Không thể tạo đúng vòng chờ hai khóa như ví dụ trái thứ tự.

Cần integration test riêng cho algorithm sort nếu nó là contract quan trọng.

### 18.5. Không dùng deadlock như cách phân phối tải

Deadlock detection là cơ chế bảo vệ database, không phải queue scheduler. Nếu hệ thống thường xuyên deadlock, giảm contention, thứ tự locks, transaction durations hoặc redesign business state, thay vì chỉ tăng số retries.

## 19. Rollback khi đã khóa và sửa managed entity

### 19.1. Flush không phải commit

Trong transaction:

~~~java
StockItem stock = repository
    .lockByIdAndTenant(id, "tenant-a")
    .orElseThrow();

stock.reserve(2);

entityManager.flush();

throw new IllegalStateException("simulate failure");
~~~

Nếu exception khiến transaction rollback thành công, available ở database phải trở lại giá trị trước transaction dù SQL UPDATE đã được gửi tại flush.

### 19.2. Test rollback sau flush

~~~java
@Test
void rollbackAfterFlushRestoresStock() {

    Integer before = tx.execute(status ->
        repository.findByIdAndTenant(
            stockId, "tenant-a"
        ).orElseThrow().getAvailable()
    );

    assertThrows(
        IllegalStateException.class,
        () -> tx.executeWithoutResult(status -> {

            StockItem stock = repository
                .lockByIdAndTenant(
                    stockId, "tenant-a"
                )
                .orElseThrow();

            stock.reserve(2);
            em.flush();

            throw new IllegalStateException(
                "force rollback"
            );
        })
    );

    Integer after = tx.execute(status ->
        repository.findByIdAndTenant(
            stockId, "tenant-a"
        ).orElseThrow().getAvailable()
    );

    assertEquals(before, after);
}
~~~

em là Spring-managed EntityManager proxy được inject với @PersistenceContext, bind vào transaction của TransactionTemplate. Test này phải dùng **transaction mới** để đọc sau rollback, không kiểm tra object managed cũ còn trong memory.

### 19.3. Khóa được giải phóng khi rollback

Sau khi transaction A rollback, một transaction B có thể lấy row lock (nếu không có holder khác). Có thể thêm test gọi service.reserve trong transaction mới, xác nhận operation thành công.

### 19.4. Không catch rồi lặng lẽ return

Nếu business validation fail, throw InsufficientStockException để transaction rollback. Không catch rồi trả ReservationResult giả; kết quả “không đặt được hàng” khác với “đã đặt thành công”.

### 19.5. Lỗi ở bước thứ hai của use case

Khi use case bao cả:
- reserve stock;
- persist order;
- persist outbox;

thử ép OutboxRepository.fail trước commit. Sau rollback, DB phải giữ stock như cũ và không có Order/Outbox mới. Đây là **integration test của transaction boundary**, không chỉ locking test.

## 20. Kiểm thử isolation: hành vi ở READ COMMITTED và REPEATABLE READ

### 20.1. PostgreSQL READ COMMITTED

Trong điều kiện phù hợp, transaction B chờ SELECT FOR UPDATE có thể đọc row version mới sau khi A commit. Test stock reservation 5→1 rồi B thấy 1 thể hiện behavior này.

### 20.2. PostgreSQL REPEATABLE READ

Khi snapshot của B đã được hình thành và row bị thay đổi bởi transaction A, B có thể gặp serialization failure khi cố khóa/update row thay vì tiếp tục với một row mới. Không viết unit test chung kỳ vọng mọi isolation level sẽ trả InsufficientStockException.

### 20.3. SERIALIZABLE

Có thể tạo serialization failures ngay cả khi code dùng row locks. Hãy chuẩn bị retry toàn transaction đối với các failures được phân loại retryable và xét idempotency.

### 20.4. Spring isolation annotation

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public ReservationResult reserve(...) {
    // ...
}
~~~

Nếu method REQUIRED tham gia outer transaction, isolation annotation của inner method **không tự thay đổi isolation của physical transaction đang tồn tại**. Test cần gọi bean proxy ngoài một transaction sẵn có, hoặc dùng transaction policy rõ.

### 20.5. Không giả định Isolation.DEFAULT

Isolation.DEFAULT dùng cấu hình database/transaction manager. Không suy ra cùng một behavior trên PostgreSQL, Oracle, SQL Server, MySQL hoặc test database khác.

### 20.6. Snapshot và multi-row invariants

Nếu nghiệp vụ cần khóa nhiều rows để giữ invariant như “ít nhất một operator active”, chỉ khóa một row có thể chưa đủ. Thiết kế:
- Lock set liên quan theo thứ tự;
- Coordination row;
- Serializable + retry;
- Database constraints nếu có thể;
- Atomic SQL hoặc aggregate design phù hợp.

Khóa bi quan không thể bảo vệ một invariant nếu code **khóa sai tài nguyên**.

## 21. Khóa theo resource key, không theo dòng tìm thấy đầu tiên

### 21.1. Query thiếu key/tenant có thể khóa quá rộng

Sai:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select s from StockItem s where s.available > 0")
List<StockItem> lockAllAvailable();
~~~

Một request nhỏ có thể khóa nhiều stock rows, tăng contention lớn và giảm throughput. Nếu chỉ mua StockItem#101, khóa chính row đó.

### 21.2. Query theo ID và tenant

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("""
    select s
    from StockItem s
    where s.id = :id
      and s.tenantId = :tenant
    """)
Optional<StockItem> lockByIdAndTenant(...);
~~~

Đây là phạm vi khóa dễ dự đoán hơn. Primary key lookup thường có index tốt; tenant predicate bảo vệ scope truy cập, nhưng **authorization phải đến từ trusted identity**, không chỉ client-supplied string.

### 21.3. Khóa row không tồn tại?

Nếu query không tìm thấy row, cơ sở dữ liệu thường không trả một row lock trên chính row chưa tồn tại. Với nghiệp vụ “tạo nếu chưa tồn tại” có race giữa hai transactions:
- Hai bên đều query thấy missing;
- Cả hai INSERT cùng unique key;
- Database UNIQUE quyết định conflict.

Cần UNIQUE constraint/UPSERT hoặc khóa coordination key/row khác nếu cần. Đừng giả định PESSIMISTIC_WRITE trên empty result ngăn concurrent INSERT cho key đó trên mọi DB/isolation.

### 21.4. Phạm vi của SELECT FOR UPDATE qua joins

Một locking query có JOIN có thể khóa nhiều tables/rows hoặc có hạn chế SQL theo DB. PostgreSQL hỗ trợ forms như FOR UPDATE OF table_alias, nhưng JPA provider có cách phát SQL riêng. Cần xem generated SQL và DB lock observations nếu scope quan trọng.

### 21.5. Indexes và execution plan

Lock theo một filter không có index có thể quét nhiều rows trước khi tìm target; I/O tăng, transaction kéo dài, nhiều locks/gaps có thể xảy ra tùy DB. Khi thao tác hot:
- Index đúng lookup key;
- Avoid broad scans;
- Limit result set;
- Dùng query timeout/lock timeout có policy;
- Theo dõi DB wait events;
- Test với row counts giống production.

## 22. So sánh khóa bi quan với khóa lạc quan

Cùng một invariant tồn kho có thể được bảo vệ bằng nhiều chiến lược. Khóa bi quan không phải luôn nhanh nhất hoặc đơn giản nhất.

### 22.1. Optimistic locking với @Version

Luồng:
1. T1 và T2 có thể đọc cùng available=5/version=7 mà chưa khóa.
2. Mỗi bên tính reserve(4) → available=1.
3. T1 UPDATE với version predicate thành công, version tăng.
4. T2 UPDATE dựa trên version cũ ảnh hưởng 0 rows hoặc bị JPA provider phát hiện conflict.
5. T2 rollback, có thể retry bằng cách reload state; lần sau thấy available=1 và bị từ chối nghiệp vụ.

Ưu điểm:
- Tránh blocking lock sớm trong tình huống xung đột thấp;
- Phù hợp reads nhiều/writes ít;
- Dễ bảo vệ stale changes nếu mọi JPA writers tuân @Version.

Nhược điểm:
- Conflict bị phát hiện **muộn** ở flush/commit;
- Có thể phải retry cả unit of work;
- Với hot row, tỉ lệ conflict/rollback cao;
- External effects trước commit làm retry nguy hiểm;
- Native writers phải phối hợp versioning.

### 22.2. Pessimistic locking

Luồng:
1. T1 lấy row lock, đọc available=5;
2. T2 xin lock và chờ/thất bại theo policy;
3. T1 reserve(4), commit;
4. T2 lấy lock sau commit, đọc available=1 và fail business check.

Ưu điểm:
- Tránh việc hai transactions cùng tiến hành dựa trên stale writable row khi dùng locking read đúng;
- Giảm vòng retry do optimistic conflicts trên hot rows;
- Có thể kiểm soát chờ qua NOWAIT/timeout.

Nhược điểm:
- Blocking và lock wait latency;
- Deadlock khi khóa nhiều rows;
- Dễ gây pool exhaustion nếu transactions dài;
- Không thay domain validation;
- Phụ thuộc DB/provider locking semantics;
- Có thể giảm throughput dưới contention cao.

### 22.3. Bảng lựa chọn

| Tiêu chí | Optimistic @Version | Pessimistic lock |
|---|---|---|
| Khi xung đột thấp | Thường phù hợp | Có thể thêm overhead |
| Khi một row rất hot | Có thể nhiều retries | Có thể giúp serial hóa rõ |
| Chờ trước khi sửa | Thường không | Có |
| Phát hiện conflict | Flush/commit | Khi xin lock hoặc thao tác |
| Deadlock do row lock sớm | Ít hơn ở read phase | Có thể tăng |
| Cần retry | Khi stale write | Khi timeout/deadlock/serialization |
| Transaction dài | Vẫn không tốt | Đặc biệt nguy hiểm |
| Portable JPA concept | Có | Có, nhưng SQL/timeout phụ thuộc DB |
| Native SQL writers | Cần increment version đúng | Cần tuân lock/concurrency policy |
| Nhiều application instances | Hoạt động qua DB | Hoạt động qua DB |
| User-facing latency | Conflict có thể xuất hiện cuối | Có thể chờ row lock |

Không chọn chiến lược chỉ theo tên. Đo conflict rate, throughput, p95/p99 latency, lock wait, retry count và DB resources trên workload thật.

## 23. Phương án thứ ba: atomic conditional UPDATE

Với một invariant đơn giản như **available >= quantity**, không nhất thiết phải load managed entity rồi xin row lock trước khi trừ. Một SQL statement nguyên tử có thể vừa kiểm tra vừa cập nhật:

~~~sql
UPDATE stock_items
SET available = available - :quantity,
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenant
  AND available >= :quantity;
~~~

Nếu affected row count = 1, reservation thành công. Nếu = 0, có thể do:
- ID không tồn tại;
- Sai tenant;
- Hết hàng;
- Row bị xóa/thay trạng thái;
- Business predicate khác không thỏa.

Không tự gộp mọi trường hợp 0 thành INSUFFICIENT_STOCK nếu API cần phân biệt not-found/forbidden. Có thể query lại trong transaction hoặc trả một mã chung để tránh data enumeration, tùy security policy.

### 23.1. Tại sao câu SQL này có thể tránh lost update?

Database thực hiện điều kiện **available >= quantity** và phép trừ trong một atomic UPDATE statement. Với PostgreSQL READ COMMITTED, khi hai updates xung đột cùng row, một statement có thể chờ rồi đánh giá điều kiện trên row version phù hợp sau khi bên kia commit. Kết quả là không trừ hai lần vượt lượng available nếu predicate/SQL được dùng nhất quán.

### 23.2. Native update trong JPA

~~~java
int affected = em.createNativeQuery(
    """
    UPDATE stock_items
    SET available = available - :qty,
        version = version + 1
    WHERE id = :id
      AND tenant_id = :tenant
      AND available >= :qty
    """
)
.setParameter("qty", quantity)
.setParameter("id", stockId)
.setParameter("tenant", authorizedTenant)
.executeUpdate();
~~~

Đây là **PostgreSQL/JDBC SQL pattern**, không phải managed-entity dirty checking. Nó bypass per-entity callbacks và JPA @Version auto-handling; manual version increment nhằm phối hợp với versioned JPA writers. Query có thể làm persistence context **stale** nếu StockItem đã managed. Flush/clear/refresh và concurrency policy cần được thiết kế nếu trộn hai đường ghi.

### 23.3. Khi nào atomic UPDATE tốt hơn?

- Business rule chỉ là một số lượng và predicate;
- Không cần nạp entity graph hoặc callbacks;
- Workload rất hot/high throughput;
- Muốn giảm SELECT + UPDATE round trips;
- Có thể biểu diễn invariant bằng SQL transactionally;
- Event/Order writes vẫn được tổ chức trong **cùng transaction**.

Không chọn atomic UPDATE nếu domain có nhiều bước phức tạp hoặc callbacks/cascades cần chạy theo managed-entity lifecycle mà bạn chưa thay thế an toàn.

### 23.4. Locking và atomic SQL không phải hai thế giới tách biệt

Database vẫn dùng locking/concurrency control nội bộ cho UPDATE. Khác biệt là application không thực hiện một SELECT locking read trước rồi sửa object, mà giao phép kiểm tra/trừ cho **một statement**.

### 23.5. Test cùng contract cho hai implementations

Có thể định nghĩa interface:

~~~java
public interface StockReservationPort {
    ReservationResult reserve(
        String tenantId, Long stockId, int quantity
    );
}
~~~

Một adapter dùng JPA pessimistic locking, adapter khác dùng native conditional UPDATE. Dùng cùng scenario tests:
- 5 available, hai requests mỗi bên 4;
- Quantity âm;
- Tenant khác;
- Commit failure rollback;
- High contention repeated runs.

Chỉ so benchmark sau khi cả hai implementations giữ **cùng business correctness contract**.

## 24. Transaction boundary quyết định hiệu lực của khóa

### 24.1. Lock được giữ khi transaction đang active

~~~java
@Transactional
public void reserve(...) {
    StockItem item = repo.lockByIdAndTenant(...).orElseThrow();
    item.reserve(quantity);
    // Transaction commit sau khi method qua proxy return.
}
~~~

Trong Spring proxy-based setup, transaction bao locking query và managed update; khóa không nên bị giải phóng ở giữa.

### 24.2. Sai khi service không @Transactional

~~~java
public void reserve(...) {
    StockItem item = repo.lockByIdAndTenant(...).orElseThrow();
    item.reserve(quantity);
}
~~~

Nếu repository method tự có transaction ngắn, khóa được giải phóng khi query method kết thúc. Entity có thể detached hoặc không được flush về DB như kỳ vọng. Nếu repository không tự tạo transaction, provider có thể báo TransactionRequiredException. Đừng suy khóa luôn tồn tại chỉ vì method tên lockByIdAndTenant.

### 24.3. @Transactional self-invocation

~~~java
@Service
class StockService {

    public void handle(...) {
        this.reserve(...); // Gọi trực tiếp cùng object.
    }

    @Transactional
    public void reserve(...) {
        // ...
    }
}
~~~

Với Spring proxy transactions thông dụng, self-invocation không đi qua transaction interceptor. Cần method public entrypoint được gọi qua injected bean/proxy, bean khác hoặc TransactionTemplate.

### 24.4. Proxy commit sau method body

ReservationResult được tạo trong method body trước khi commit, nhưng caller qua Spring proxy nhận kết quả sau khi transaction interceptor xử lý thành công. Commit-time deadlock/optimistic/constraint errors có thể xuất hiện sau method body, vì vậy caller hoặc outer interceptor phải chịu trách nhiệm error translation.

### 24.5. Flush/clear không giải phóng lock

~~~java
em.flush();
em.clear();
~~~

Không đồng nghĩa COMMIT; row lock vẫn có thể giữ đến transaction end. Để giảm lock duration, rút ngắn transaction (không phải clear cho nhanh).

### 24.6. REQUIRES_NEW không giải quyết mọi tranh chấp

Một outer transaction đang giữ lock rồi gọi inner REQUIRES_NEW cần cùng row có thể tự gây blocking/deadlock-like wait nếu outer transaction bị suspend nhưng chưa giải phóng lock. Không dùng REQUIRES_NEW tùy tiện để “lấy khóa mới” cho row đang bị outer giữ.

### 24.7. Các repository phải dùng cùng transaction manager

Nếu lockStock dùng DataSource A, order writes dùng DataSource B với local transaction manager khác, một @Transactional ở service không tự cho atomicity cả hai. Cần hiểu resource ownership/JTA/XA hoặc dùng saga/outbox phù hợp.

### 24.8. Read-only transaction không phù hợp với reservation

~~~java
@Transactional(readOnly = true)
public void reserve(...) {
    // update managed entity
}
~~~

readOnly là hint/cấu hình provider/transaction manager, không được dùng cho write operation. Một số systems có thể không flush changes như kỳ vọng hoặc DB từ chối write; cần write transaction rõ.

## 25. Retry policy cho khóa bi quan

### 25.1. Retry toàn đơn vị công việc

Khi lock timeout/deadlock:
1. Cho transaction hiện tại rollback;
2. Đóng/bỏ persistence context lỗi;
3. Backoff ngoài transaction;
4. Tạo transaction mới;
5. Lấy khóa và đọc lại stock;
6. Kiểm tra domain rule lần nữa;
7. Ghi toàn bộ Order/Outbox liên quan và commit.

**Không** retry chỉ đoạn stock.reserve() trên cùng object đã detached/stale sau failure.

### 25.2. Coordinator retry nằm ngoài transactional service

Một cấu trúc:

~~~java
@Service
public class ReservationRetryCoordinator {

    private final StockReservationService transactionalService;

    public ReservationRetryCoordinator(
            StockReservationService transactionalService) {
        this.transactionalService = transactionalService;
    }

    public ReservationResult reserveWithRetry(
            String tenant, Long stockId, int quantity) {

        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return transactionalService.reserve(
                    tenant, stockId, quantity
                );
            } catch (RuntimeException failure) {

                if (!isRetryableConcurrencyFailure(failure)
                        || attempt == maxAttempts) {
                    throw failure;
                }

                backoffOutsideTransaction(attempt);
            }
        }

        throw new IllegalStateException("unreachable");
    }
}
~~~

**isRetryableConcurrencyFailure** và **backoffOutsideTransaction** là application/infrastructure utilities cần implement theo SQLState/provider exception types và deadlines. Quan trọng là **chỉ retry các lỗi thật sự retryable**, không catch mọi RuntimeException rồi retry.

Vì coordinator không @Transactional, mỗi invocation qua proxied StockReservationService.reserve có thể mở transaction mới. Nếu coordinator bị bọc trong outer transaction REQUIRED, semantics sẽ thay đổi; cần guardrail rõ.

### 25.3. Exponential backoff với jitter

Một policy minh họa:
- Attempt 1: ngay;
- Attempt 2: random trong khoảng 40–120ms;
- Attempt 3: random trong khoảng 100–300ms;
- Dừng khi tổng deadline vượt giới hạn.

Các con số chỉ là ví dụ, phải theo SLA và lock distribution. **Không sleep trong transaction**; giảm pool/lock pressure trước khi retry.

### 25.4. Không retry business failures

Nếu transaction chờ xong rồi đọc available=1 < 4, đây là **hết hàng**, không phải timeout. Retry 10 lần không tạo thêm stock. Có thể thông báo khách hoặc chờ replenishment qua workflow riêng.

### 25.5. Idempotency khi tạo Order

Nếu reservation service còn tạo Order và client retry do network timeout ở commit, có thể transaction đầu đã commit. Phải có:
- Request ID/idempotency key;
- UNIQUE(tenant_id, request_key);
- Kiểm tra payload same intent;
- Return prior committed result khi phù hợp;
- Không tạo Order mới hoặc trừ stock lần nữa.

Pessimistic lock bảo vệ stock row, **không thay idempotency** của toàn business command.

### 25.6. Deadlock ở nhiều rows

Nếu retry deadlock, cần khóa theo thứ tự ổn định, giảm transaction scope hoặc partition load. Nếu chỉ tăng retry count, database vẫn có cùng wait cycle và latency có thể xấu hơn.

## 26. Khóa bi quan và multi-tenancy

### 26.1. Một row ID không tự có quyền truy cập

Một client biết StockItem ID=101 của tenant-a không có nghĩa được đọc/sửa/khóa row đó. Service phải lấy tenant từ principal/trusted context, rồi query theo id + tenant.

### 26.2. Test truy cập sai tenant

~~~java
@Test
void cannotReserveStockFromAnotherTenant() {

    assertThrows(
        StockNotFoundException.class,
        () -> service.reserve(
            "tenant-b", stockId, 1
        )
    );

    Integer remaining = tx.execute(status ->
        repository.findByIdAndTenant(
            stockId, "tenant-a"
        ).orElseThrow().getAvailable()
    );

    assertEquals(5, remaining);
}
~~~

Trong production, không để user truyền raw tenant string tự do. Test này chứng minh repository query scope đúng, nhưng còn cần HTTP/security integration tests cho principal-based tenant resolution.

### 26.3. Khóa nhầm tenant vẫn có thể gây DoS

Ngay cả nếu không sửa row, một endpoint cho caller bất kỳ xin PESSIMISTIC_WRITE lock trên arbitrary stock ID có thể làm tenant khác phải chờ. Authorization/query scoping phải xảy ra **trước hoặc trong locking query**, không khóa rồi mới kiểm tra permission.

### 26.4. Tenant-scoped uniqueness

Nếu stock được định danh bởi tenant+sku, dùng UNIQUE(tenant_id, sku). Không chỉ UNIQUE(sku) nếu cùng SKU có thể tồn tại độc lập theo tenant.

### 26.5. Cross-tenant relational constraints

Một foreign key chỉ theo stock_id có thể bảo đảm row tồn tại nhưng không tự ngăn Order của tenant-b tham chiếu StockItem tenant-a, nếu schema cho phép. Cân nhắc composite keys/FKs, row-level security và application checks phù hợp.

## 27. Những lỗi thường gặp khi triển khai PESSIMISTIC_WRITE

### 27.1. Khóa ở repository nhưng transaction kết thúc quá sớm

Một method Spring Data JPA @Lock có thể được gọi độc lập mà không có outer @Transactional. Tùy method/transaction config, lock có thể không lấy được hoặc chỉ tồn tại đến hết repository call. Nếu service sửa object **sau khi lock đã mất**, race vẫn tồn tại.

**Giải pháp:** đặt @Transactional bao read–check–write ở application service; test bằng hai transactions đồng thời.

### 27.2. Dùng Java synchronized làm khóa hệ thống phân tán

~~~java
public synchronized ReservationResult reserve(...) {
    // JPA query và update
}
~~~

Nó chỉ tuần tự hóa những threads gọi qua **cùng Java object instance**. Khi deploy ba application pods, mỗi pod có lock riêng, không ngăn transactions giữa pods. Database lock hoặc atomic SQL mới có scope qua các process dùng chung DB.

### 27.3. Lock một row nhưng sửa row khác

Nếu code khóa ProductCatalog row còn business invariant lại nằm ở StockItem row, transactions vẫn có thể cùng update StockItem mà không tranh lock ProductCatalog như dự tính.

**Chọn lock target theo tài nguyên bất biến**, không chỉ một entity tiện lấy.

### 27.4. Lấy lock sau khi quyết định nghiệp vụ

Sai:

~~~java
StockItem stock = repository.findById(stockId).orElseThrow();
if (stock.getAvailable() >= quantity) {
    repository.lockByIdAndTenant(stockId, tenantId);
    stock.reserve(quantity);
}
~~~

Check available trước khi lock có thể dùng stale state. Tốt hơn là **locking read trước**, rồi kiểm tra trên state đã được bảo vệ. Nếu phải lock sau, cần refresh/recheck theo provider/DB semantics.

### 27.5. @Version không tự bảo vệ mọi native SQL writers

Nếu một process ngoài JPA UPDATE stock_items SET available=... nhưng không tăng version, optimistic participants có thể không phát hiện mọi stale writes. Khóa bi quan đúng có thể điều phối DB writes tranh chấp, nhưng nếu external writer làm các operations khác không tôn trọng invariant, cần thống nhất data access strategy/DB constraints.

### 27.6. Bắt lock timeout rồi tiếp tục trên transaction cũ

Trong PostgreSQL, một statement error thường để transaction ở trạng thái aborted cho đến ROLLBACK. Không thể chỉ em.clear rồi tiếp tục repository.save như một transaction mới.

### 27.7. Tăng transaction timeout mà không giảm contention

Nếu hot stock row luôn bị chờ, cho phép mỗi request chờ 60 giây có thể làm connection pool nghẽn nặng hơn. Cần xem:
- Hot key distribution;
- Transaction duration;
- Connection pool capacity;
- Lock wait percentile;
- Retry rate;
- Availability of atomic update/queueing;
- Business acceptable response time.

### 27.8. @Lock trên query trả quá nhiều rows

Một PESSIMISTIC_WRITE query không giới hạn WHERE hoặc JOIN rộng có thể khóa nhiều rows/tables hơn cần thiết, làm operations độc lập cũng phải chờ. Giảm scope và tối ưu indexes.

### 27.9. Tin rằng SQL logs có FOR UPDATE là đủ

Generated SQL có FOR UPDATE là dấu hiệu hữu ích, nhưng chưa chứng minh:
- Câu SQL thực sự chạy trong active transaction;
- Lock được giữ đủ lâu;
- Tenant filter đúng;
- Caller không bypass service;
- Database đã được config như test;
- Retry/rollback đúng.

Cần concurrency tests và database-state assertions.

### 27.10. Test với @Transactional trên test class

Nếu test class có outer transaction rollback sau test, fixture có thể chưa commit khi worker thread muốn đọc, hoặc service REQUIRED bị outer test transaction che boundaries. Bỏ outer test transaction và quản lý fixtures bằng TransactionTemplate.

### 27.11. Chỉ test hai lời gọi tuần tự

Sau call 1, call 2 thấy stock đã giảm. Dù không @Lock, test có thể vẫn pass. Phải tạo overlap có kiểm soát bằng latches/gates và chạy hai transactions thực.

### 27.12. Dùng Thread.sleep như đồng bộ hóa chính

Thread.sleep(20) không bảo đảm một transaction đã lấy lock hay transaction kia đã bắt đầu query. Dùng CountDownLatch/Barrier để báo các **milestones thực**, và deadline chống treo. Với lock timeout, xác minh SQLState hoặc DB wait events.

### 27.13. Dùng chung EntityManager giữa hai threads

JPA EntityManager không thread-safe. Nếu hai threads share cùng instance/raw persistence context, test không đại diện hai transactions độc lập và có thể gặp lỗi state không dự đoán. Spring @PersistenceContext shared proxy có thể resolve theo transaction của từng thread, nhưng không tự share underlying EntityManager.

### 27.14. Connection pool chỉ có một connection

Hai workers cần hai physical connections. Nếu pool max=1, worker B có thể chờ **connection acquisition** chứ không phải row lock. Thiết kế test connection capacity và đo đúng timeout category.

### 27.15. Transaction A chờ latch nhưng không được release

Nếu assertion fail trước release.countDown, holder giữ DB transaction/lock và test suite treo. Luôn:
- release trong finally;
- Future.get với deadline;
- shutdown executor;
- Rollback khi callback fail;
- Không tái dùng test database state không được cleanup.

### 27.16. Khóa nhầm row tenant khác

Một method lockById(id) không kiểm tra tenant có thể biến endpoint thành phương tiện làm chậm tenant khác. Use-case query phải có ID + tenant scope và trusted authorization.

### 27.17. Tạo thiếu row nhưng kỳ vọng khóa tránh duplicate INSERT

SELECT FOR UPDATE không tìm thấy row không phải một uniqueness gate di động. Dùng UNIQUE constraint/UPSERT hoặc coordination resource phù hợp.

### 27.18. Chọn SKIP LOCKED cho exact reservation

SKIP LOCKED có thể trả empty khi row đang bị xử lý, không đồng nghĩa stock không tồn tại hoặc hết hàng. Nếu cần mua đúng SKU, việc bỏ qua row là business contract khác.

## 28. Quan sát khóa và lock waits trên PostgreSQL

### 28.1. pg_stat_activity

Trong test/staging, có thể quan sát những sessions đang chờ:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    query
FROM pg_stat_activity
WHERE datname = current_database();
~~~

Khi một transaction chờ row lock, wait_event_type thường liên quan đến **Lock**, nhưng detail có thể là transactionid/tuple hoặc dạng khác tùy PostgreSQL version và tình huống. Không nhất thiết thấy một dòng tuple lock rõ ràng trong pg_locks cho mọi lock wait.

### 28.2. pg_blocking_pids

Có thể xem session đang bị chặn bởi session nào:

~~~sql
SELECT
    a.pid AS waiting_pid,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_activity a
WHERE a.wait_event_type = 'Lock';
~~~

Khi test giữ khóa bằng latch, quan sát pg_blocking_pids có thể giúp xác nhận transaction B đang chờ transaction A, nhưng đây là một bước chẩn đoán database-specific, không cần chạy trong mọi unit test.

### 28.3. pg_locks

~~~sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE database = (
    SELECT oid FROM pg_database
    WHERE datname = current_database()
);
~~~

Một row update/locking statement cũng có thể giữ **table-level lock modes** phục vụ thao tác; điều đó không có nghĩa nó đã khóa toàn bộ rows của table. Phân biệt row locks, relation locks, transactionid waits và conflict matrix.

### 28.4. Quyền truy cập monitoring

Production monitoring views có thể chứa SQL text/identifiers, là dữ liệu nhạy cảm. Chỉ cấp quyền phù hợp, che parameters khi cần và không đưa toàn bộ SQL logs vào public API.

### 28.5. Các metrics nên thu thập

| Metric | Ý nghĩa |
|---|---|
| Row-lock wait duration p50/p95/p99 | Độ trễ do contention |
| Lock timeout count | Tài nguyên quá hot hoặc policy quá chặt |
| Deadlock count | Lock ordering/transaction design |
| Transaction duration | Thời gian giữ locks |
| Connection acquire wait | Phân biệt pool contention |
| Retry attempts | Nguy cơ retry storm |
| Reservation success/fail | Business outcome |
| Insufficient-stock count | Thật sự hết hàng |
| SQL statements per reservation | N+1/queries không cần |
| DB CPU/I/O/WAL | Database saturation |
| Unknown commit outcome count | Cần reconciliation |
| Pending queue job age | Starvation với SKIP LOCKED |

Cần phân biệt **business sold-out** với **technical lock timeout** trong metrics để vận hành không đưa ra giải pháp sai.

### 28.6. Không log mỗi lần chờ khóa bằng PII

Một metric label theo stockId/SKU có thể tạo high cardinality hoặc lộ dữ liệu. Có thể thống kê theo endpoint, operation, tenant tier hoặc nhóm hot keys được bảo vệ, thay vì đưa mọi ID vào metric labels.

## 29. Đo hiệu năng và đánh đổi ở hot rows

### 29.1. Một row rất hot là nút cổ chai tự nhiên

Nếu hàng nghìn requests cùng update một stock row, thao tác cần tuần tự hóa một phần. PESSIMISTIC_WRITE khiến các requests xếp hàng; tăng CPU của application không tự làm row write song song.

Có thể:
- Giảm thời gian giữ lock;
- Dùng atomic conditional UPDATE;
- Tách đọc không cần khóa khỏi critical section;
- Hạn chế số requests cùng lúc cho một hot key;
- Queue/reservation token theo business;
- Partition inventory nếu mô hình cho phép;
- Dùng optimistic strategy khi conflict rate thấp.

### 29.2. Benchmark phải đo kết quả đúng

Một implementation không khóa có thể đạt throughput cao vì **bỏ mất updates** hoặc bán vượt tồn kho. So sánh hợp lệ chỉ khi cả hai implementations đáp ứng invariant, có kiểm thử data reconciliation sau mỗi run.

### 29.3. Ma trận benchmark

| Case | Lock strategy | Contention | Metrics |
|---|---|---|---|
| A | No explicit lock + @Version | Thấp | Throughput, optimistic conflicts |
| B | PESSIMISTIC_WRITE | Thấp | Lock overhead |
| C | PESSIMISTIC_WRITE | Cao một hot key | Wait p95/p99, pool pressure |
| D | Atomic conditional UPDATE | Cao một hot key | UPDATE affected count, throughput |
| E | PESSIMISTIC_WRITE + NOWAIT policy | Cao | Fast-fail, retry rate |
| F | SKIP LOCKED task queue | Nhiều jobs | Claim throughput, pending age |

Những con số như “20% nhanh hơn” không thể khẳng định nếu chưa chạy trên workload/database/driver/SQL thực tế.

### 29.4. Tác động của network latency

Một transaction giữ lock 20ms nhưng có thêm remote call 500ms có thể giữ lock ~520ms. Khi 100 users tranh cùng row, latency tích lũy tăng mạnh. Tối ưu transaction scope thường có tác động lớn hơn thay lock hint.

### 29.5. Pessimistic lock và batch operations

Một job sửa nhiều stock rows nên:
1. Giới hạn batch size;
2. Sort row IDs;
3. Mở transaction;
4. Lấy locks theo thứ tự;
5. Áp rules;
6. Flush/commit;
7. Retry whole chunk khi deadlock;
8. Ghi checkpoint sau commit.

Không giữ một transaction hàng giờ với hàng chục nghìn row locks chỉ vì muốn tránh conflicting jobs.

### 29.6. Đổi isolation cũng có cost

SERIALIZABLE có thể tăng serialization failures và retry overhead. PESSIMISTIC_WRITE có thể tạo lock waits. Atomic UPDATE có thể đơn giản SQL nhưng làm application state stale. Mọi chiến lược đều có đánh đổi; chọn dựa trên **invariant + đo lường + operational resilience**.

## 30. Kiểm thử hồi quy khi refactor Repository

### 30.1. Thay @Query có thể làm mất lock

Nếu method trước:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select s from StockItem s where s.id = :id")
Optional<StockItem> lockById(Long id);
~~~

được refactor thành method thường không có @Lock, unit tests chỉ assert kết quả tuần tự có thể vẫn xanh.

Concurrency test với holder lock và timeout/wait sẽ phát hiện regression nếu người sửa bỏ lock thật.

### 30.2. Thay @Transactional có thể đổi physical boundary

Chuyển service.reserve từ @Transactional sang method không transaction hoặc thêm @Async khiến lock lifetime và persistence context thay đổi. Integration test phải gọi qua bean proxy thật, không mock transaction manager.

### 30.3. Thay datasources hoặc DB version

Một query lock hoạt động trên PostgreSQL có thể có SQL khác trên MySQL/Oracle. Khi đổi dialect/provider version, cần test:
- Lock SQL actual;
- NOWAIT/SKIP LOCKED support;
- Timeout behavior;
- Isolation/serialization rules;
- Deadlock classification;
- DB constraint enforcement.

### 30.4. Thay câu query lọc tenant

Thay lockByIdAndTenant thành findById có thể gây BOLA và lock nhầm tài nguyên tenant khác. Negative test tenant-b gọi stockId của tenant-a nên tiếp tục chạy trong pipeline.

### 30.5. Thay @Version

Nếu gỡ @Version, đường ghi optimistic khác có thể mất bảo vệ. Ngay cả khi pessimistic lock vẫn hoạt động tại endpoint chính, cần biết những writers khác đang phụ thuộc version. Test concurrent managed update của những writers đó riêng.

### 30.6. Thay strategy từ JPA lock sang native SQL

Nếu chuyển sang atomic UPDATE, integration tests phải xác nhận:
- Tenant predicate đúng;
- Available không âm;
- Affected row count chính xác;
- Version increment tương thích JPA writers;
- Transaction rollback Order/Outbox;
- Không có stale managed entity write đè state.

### 30.7. Test không được tự che lỗi

Một test catch mọi RuntimeException rồi return SOLD_OUT sẽ vẫn xanh khi SQL query hỏng. Chỉ catch expected domain exception; technical failure phải khiến test fail và có diagnostics.

## 31. Bài tập thực hành có hướng dẫn

Các bài sau dựa trên StockItem, StockRepository, StockReservationService và PostgreSQL integration test ở các mục trước. Với mỗi bài, ghi rõ:
- **Transaction nào giữ khóa, đến khi nào?**
- **Hai threads có thực sự mở hai physical transactions không?**
- **Kết quả DB đã commit được kiểm tra bằng gì?**
- **Lỗi business và lỗi tranh chấp database được phân biệt ra sao?**
- **Nếu DB/provider khác PostgreSQL, phần nào phải thay đổi?**

### Bài 1. Tái hiện race không bảo vệ

Tạo một service đọc StockItem bằng query thường và sửa available, không dùng @Lock/@Version hoặc conditional UPDATE. Cho hai threads cùng đọc available=5 và reserve 4. Mô tả cách phối hợp latches để kiểm tra nguy cơ lost update.

**Lưu ý:** Không triển khai endpoint không an toàn này ở production; dùng database test cô lập và chỉ so sánh để thấy vì sao concurrency control cần thiết.

### Bài 2. Bảo vệ bằng PESSIMISTIC_WRITE

Thêm @Lock(LockModeType.PESSIMISTIC_WRITE) vào repository method và gọi trong @Transactional service. Chạy lại scenario hai requests quantity=4, stock=5. Xác định expected success/failure và remaining.

### Bài 3. Kiểm tra với một request quantity âm

Gọi service.reserve(..., -1). Exception nên là domain/input validation hay lock timeout? Có cần lấy khóa trước khi biết input invalid không? Di chuyển validation tới vị trí hợp lý.

### Bài 4. Khi quantity bằng zero

Gọi reserve(..., 0). Domain invariant của StockItem xử lý thế nào? Nếu API chấp nhận zero như no-op, cần thiết kế contract rõ; không chỉ bỏ guard để giảm exception.

### Bài 5. Java synchronized và nhiều pods

Hai application pods mỗi pod có một StockReservationService synchronized. Chúng có cùng Java monitor không? Vì sao database lock có scope phù hợp hơn?

### Bài 6. Lock mode khác nhau

So sánh PESSIMISTIC_READ, PESSIMISTIC_WRITE và PESSIMISTIC_FORCE_INCREMENT khi đọc và sửa StockItem. Trên PostgreSQL, SQL thực tế có thể khác thế nào? Đâu là yêu cầu JPA portable, đâu là dialect-specific?

### Bài 7. Cùng stock row ở hai EntityManagers

Tạo EntityManager A và B, mỗi bên load StockItem#101. Objects A/B có thể khác nhau trong Java heap không? Việc @Lock bảo vệ dựa trên Java object identity hay database row?

### Bài 8. Không có transaction

Bỏ @Transactional ở service nhưng giữ repository @Lock. Kết quả có thể là TransactionRequiredException hoặc khóa được nhả quá sớm như thế nào? Tại sao test phải xác định actual transaction boundary?

### Bài 9. Transaction ở repository quá ngắn

Đặt @Transactional chỉ quanh repository.lockByIdAndTenant, còn service sửa entity sau repository call. Nếu repository đã commit/close context, bảo vệ còn tồn tại không?

### Bài 10. Spring proxy self-invocation

Một method public handle() gọi this.reserve(), trong khi reserve() có @Transactional. Giải thích khi nào Spring proxy không intercept, và đề xuất tách bean/TransactionTemplate.

### Bài 11. Test fixture chưa commit

Trong @Transactional test method, tạo StockItem nhưng không commit. Hai worker threads dùng transactions riêng cố đọc StockItem đó. Vì sao có thể không thấy fixture? Cách tạo fixture bằng TransactionTemplate?

### Bài 12. Test dùng connection pool max=1

Một worker giữ row lock, worker khác cố query. Nó có thể đang chờ connection chứ không chờ row lock không? Thiết kế pool và instrumentation để phân biệt.

### Bài 13. Concurrency test hai requests

Viết test với ready/start CountDownLatch và hai Futures. Từ available=5, mỗi request reserve 4: expected outcomes và final database value là gì?

### Bài 14. Không catch mọi exception trong test

Nếu Future job catch RuntimeException và trả SOLD_OUT, một connection failure có thể bị che như thế nào? Chỉ catch expected InsufficientStockException.

### Bài 15. Lock holder test

Một worker mở TransactionTemplate, lock StockItem, signal locked, đợi release latch. Worker thứ hai gọi service.reserve. Thiết kế timeout/finally để tránh test treo.

### Bài 16. Scheduler timing

Vì sao assert Future.get(200ms) timeout không chứng minh chắc chắn SQL đã tới database? Đề xuất DB wait-event observation hoặc lock_timeout test mạnh hơn.

### Bài 17. PostgreSQL lock_timeout

Dùng SELECT set_config('lock_timeout','250ms',true) trong transaction B rồi xin PESSIMISTIC_WRITE lock khi A giữ row. Expected exception và rollback behavior là gì?

### Bài 18. LockTimeoutException vs PessimisticLockException

Giải thích khác biệt JPA statement-level vs transaction-level rollback. Vì sao một PostgreSQL lock_timeout không nhất thiết được wrap thành đúng một JPA exception type giữa các versions?

### Bài 19. Timeout ở connection pool

Pool acquisition timeout và PostgreSQL lock_timeout có thể có triệu chứng tương tự ở client nhưng nguyên nhân khác nhau. Nêu metrics/logs cần xem.

### Bài 20. NOWAIT

Viết PostgreSQL SELECT ... FOR UPDATE NOWAIT cho một StockItem. Khi row đang bị khóa, query trả empty hay exception? Phân biệt với not-found.

### Bài 21. SKIP LOCKED

Viết query claim 20 PENDING background_jobs bằng FOR UPDATE SKIP LOCKED. Vì sao phù hợp job queue nhưng không hợp mua chính xác StockItem#101?

### Bài 22. Worker crash khi claim jobs

Nếu transaction claim commit rồi worker xử lý job 10 phút và crash, row lock có còn giữ không? Thiết kế leaseUntil/status/reclaim/idempotency.

### Bài 23. Starvation với SKIP LOCKED

Một job thường xuyên bị skip vì liên tục bị khóa. Thiết kế monitoring pending age, fair retry và requeue policy.

### Bài 24. Deadlock hai stock rows

T1 lock A rồi B; T2 lock B rồi A. Vẽ wait-for graph. Database cần làm gì để thoát deadlock? Application retry ở scope nào?

### Bài 25. Khóa theo ID tăng dần

Với yêu cầu reserve ba SKUs, sort IDs tăng dần trước locking. Vì sao giảm deadlock? Có loại bỏ mọi deadlock liên quan FK/index triggers không?

### Bài 26. ORDER BY và physical lock order

Một JPQL SELECT ... WHERE id IN :ids ORDER BY id PESSIMISTIC_WRITE có bảo đảm physical lock acquisition order trên mọi DB/query plans không? Nếu chính sách bắt buộc thứ tự nghiêm ngặt, cần kiểm tra hoặc thiết kế gì?

### Bài 27. PostgreSQL deadlock SQLSTATE

Phân biệt 40P01, 40001 và 55P03. Lỗi nào thường retryable nếu business command có idempotency? Có nên retry lỗi “SKU không tồn tại” không?

### Bài 28. Rollback sau flush

Trong một transaction, lock row, reserve 2, em.flush rồi ném RuntimeException. Query trong transaction mới sẽ thấy available đã giảm không? Tại sao flush không phải commit?

### Bài 29. Clear không unlock

Transaction A lock StockItem, em.flush, em.clear nhưng chưa commit. Transaction B có thể vẫn bị chặn không? Tại sao EntityManager detach khác DB lock release?

### Bài 30. READ COMMITTED sau lock wait

T1 reserve 4 và commit; T2 đã chờ PESSIMISTIC_WRITE lock. Sau khi được giải phóng, T2 thường thấy available bao nhiêu trên PostgreSQL READ COMMITTED? Nếu ở REPEATABLE READ có thể xuất hiện khác biệt gì?

### Bài 31. Cross-tenant khóa nhầm

User tenant-b có id của StockItem tenant-a. Query chỉ theo id có thể gây rủi ro bảo mật và DoS thế nào? Sửa thành id+authorized tenant và viết negative test.

### Bài 32. Khóa một row không tồn tại

Hai transactions cùng query SELECT FOR UPDATE cho SKU mới chưa có row, rồi cùng INSERT. Khóa bi quan trên empty result có bảo đảm unique không? Database UNIQUE/UPSERT giải quyết ra sao?

### Bài 33. PESSIMISTIC_WRITE trên query quá rộng

Query lock tất cả rows có available>0, sau đó chỉ cập nhật một row. Nêu các tài nguyên không liên quan có thể bị chặn. Thiết kế index/query theo ID.

### Bài 34. Lấy khóa quá muộn

Service đọc available trước bằng query thường, sau đó mới lock. Nếu stock thay đổi giữa hai bước, business decision có thể sai thế nào? Sửa workflow.

### Bài 35. So với optimistic locking

Dùng @Version nhưng không xin PESSIMISTIC_WRITE. Trong scenario hai requests reserve 4 từ available=5, làm thế nào một transaction có thể nhận OptimisticLockException? Retry cần làm gì?

### Bài 36. Atomic conditional UPDATE

Viết SQL UPDATE available = available - :qty WHERE available >= :qty AND tenant_id=:tenant AND id=:id. Vì sao affected row count=1 chứng minh update thành công? 0 rows có những nguyên nhân nào?

### Bài 37. Bulk/native update và JPA context stale

Nếu StockItem đã managed trong EntityManager, sau đó native SQL UPDATE trực tiếp thay available và version, managed object có tự đồng bộ không? Cần flush/refresh/clear policy nào?

### Bài 38. @Version và PESSIMISTIC_FORCE_INCREMENT

Khi nào có thể cần tăng version dù không đổi business fields? Tại sao PESSIMISTIC_FORCE_INCREMENT không là default cho mọi reads?

### Bài 39. Remote API dưới row lock

Một service khóa stock rồi gọi payment gateway mất 3 giây. Nêu lock wait, connection pool và khách hàng khác bị ảnh hưởng. Thiết kế reservation + outbox/saga thay thế.

### Bài 40. Retry bounded

Lock timeout xảy ra ở attempt 1. Chỉ retry transaction mới, maxAttempts=3, backoff có jitter. Vì sao không sleep trong transaction lỗi?

### Bài 41. Không retry sold-out

Transaction B đợi T1 commit rồi thấy available=1 < quantity=4. Nó có nên retry như lock timeout không? Nêu business error phù hợp.

### Bài 42. Idempotency khi đặt hàng

Network timeout xảy ra ngay sau COMMIT, client gửi lại cùng requestKey. PESSIMISTIC_WRITE có tự ngăn tạo Order thứ hai không? Thiết kế UNIQUE(tenant_id,request_key) và same-intent validation.

### Bài 43. Ghi Order/Outbox trong cùng transaction

Reserve stock thành công, nhưng Outbox INSERT fail. DB cần giữ trạng thái nào? Viết integration test kiểm tra stock, order và outbox sau rollback.

### Bài 44. Monitoring lock waits

Viết PostgreSQL query pg_stat_activity/pg_blocking_pids để tìm sessions bị chặn. Vì sao một transactionid wait không nhất thiết hiện như row lock tuple trong pg_locks?

### Bài 45. Benchmark hot row

Thiết kế workload 1.000 concurrent reservation requests, so sánh PESSIMISTIC_WRITE, optimistic @Version và atomic UPDATE. Cần đo những metrics nào và kiểm tra invariant cuối cùng thế nào?

### Bài 46. Regressions khi đổi Repository

Developer xóa @Lock nhưng test tuần tự vẫn xanh. Integration test nào có khả năng phát hiện? Vì sao SQL log và business outcome test cần bổ trợ nhau?

### Bài 47. Database khác PostgreSQL

Chuyển PostgreSQL sang MySQL/Oracle. Phần nào trong bài portable JPA, phần nào cần điều chỉnh SQL timeout, NOWAIT/SKIP LOCKED, isolation và exception classification?

### Bài 48. Persistence context trong đa luồng

Hai threads dùng chung raw EntityManager. Tại sao không hợp lệ? Mô tả cách Spring transaction-scoped EntityManager proxy và mỗi worker transaction khác nhau.

### Bài 49. Không tin test chỉ assert exception type

Một lock timeout test assertThrows(RuntimeException.class) có thể pass do query syntax sai. Nâng cấp bằng việc unwrap SQLException SQLState và xác nhận holder đã lấy khóa thực.

### Bài 50. Thiết kế hệ thống reservation hoàn chỉnh

Thiết kế workflow:
1. Authenticated tenant và permission;
2. Request DTO/validation;
3. Idempotency key;
4. StockRepository locking query theo ID+tenant;
5. Transaction boundary ở PlaceOrder service;
6. Domain check/reserve;
7. Order/Outbox cùng commit;
8. Lock timeout/NOWAIT policy;
9. Retry bounded cho deadlock/serialization;
10. Không retry sold-out;
11. API error codes an toàn;
12. Monitoring lock waits/deadlocks;
13. Testcontainers PostgreSQL;
14. Two-thread/latch concurrent tests;
15. Rollback/tenant/idempotency tests;
16. So sánh với atomic UPDATE khi hot key quá tải.

Giải thích **tại sao mỗi thao tác nằm trong hoặc ngoài transaction**, cách không để remote calls kéo dài row lock, và những điều kiện nào phải được chứng minh bằng integration tests trước khi triển khai production.

## 32. Checklist triển khai khóa bi quan có kiểm thử

### 32.1. Mô hình dữ liệu và bất biến

1. **Đã xác định tài nguyên nào thực sự tranh chấp chưa?**
2. **Invariant có được mô tả bằng một câu kiểm chứng được không?**
3. **Có business rule kiểm tra available >= quantity không?**
4. **Có cấm quantity <= 0 ở DTO/domain không?**
5. **Có database CHECK available >= 0 nếu phù hợp không?**
6. **Có UNIQUE cho tenant + SKU hoặc business key không?**
7. **Có @Version khi còn optimistic writers không?**
8. **Có đảm bảo native writers cập nhật version khi cần không?**
9. **Có tránh dùng generated ID/sequence strategy lệch schema không?**
10. **Có xác định row đang bị khóa là row đại diện invariant không?**

### 32.2. Repository và khóa

11. **Repository locking method có @Lock(PESSIMISTIC_WRITE) hoặc tương đương không?**
12. **Có query theo ID/unique key chính xác không?**
13. **Có tenant predicate hoặc RLS đúng không?**
14. **Có tránh locking query quét nhiều rows không cần thiết không?**
15. **Có index phù hợp với locking query không?**
16. **Có kiểm tra generated SQL FOR UPDATE/lock syntax trên target DB không?**
17. **Có biết LockModeType.PESSIMISTIC_READ mapping phụ thuộc dialect không?**
18. **Có tránh dùng PESSIMISTIC_FORCE_INCREMENT bừa bãi không?**
19. **Có phân biệt query không có row với lock timeout không?**
20. **Có tránh giả định khóa missing row ngăn INSERT trùng không?**
21. **Có hiểu join/fetch locking scope có thể rộng không?**
22. **Có chú ý provider follow-on locking khi query phức tạp không?**

### 32.3. Transaction boundaries

23. **Locking read có nằm trong active transaction không?**
24. **@Transactional ở service bao cả read–check–write không?**
25. **Có gọi service qua Spring proxy thật không?**
26. **Có tránh self-invocation/private method bypass không?**
27. **Có tránh repository method commit trước khi sửa entity không?**
28. **Có hiểu em.flush không phải COMMIT không?**
29. **Có hiểu em.clear không giải phóng database lock không?**
30. **Có tránh giữ row lock trong khi gọi HTTP/payment/email không?**
31. **Có tránh @Transactional(readOnly=true) trên reservation không?**
32. **Có dùng transaction manager/datasource đúng không?**
33. **Có biết REQUIRES_NEW có thể phá atomicity của use case không?**
34. **Có giữ Order/Stock/Outbox chung transaction nếu business đòi hỏi không?**
35. **Có xử lý lỗi xuất hiện ở commit sau method body không?**

### 32.4. Concurrency và deadlock

36. **Đã biết isolation level thực tế của production DB chưa?**
37. **Có test READ COMMITTED locking behavior không?**
38. **Có hiểu REPEATABLE READ/SERIALIZABLE có thể phát sinh serialization failure không?**
39. **Nếu khóa nhiều rows, có thứ tự ổn định không?**
40. **Có giảm thời gian giữ locks để hạn chế deadlock không?**
41. **Có phân biệt lock wait với connection pool wait không?**
42. **Có timeout/deadline rõ cho hot resource không?**
43. **Có bounded retry cho deadlock/serialization/lock-timeout khi phù hợp không?**
44. **Có retry trên transaction/context mới không?**
45. **Có đọc lại current state trước reapply business command không?**
46. **Có tránh retry InsufficientStockException như transient SQL lỗi không?**
47. **Có idempotency key cho Order hoặc reservation API khi cần không?**
48. **Có handling cho commit outcome unknown không?**

### 32.5. NOWAIT, SKIP LOCKED và locks đặc thù DB

49. **NOWAIT được dùng khi business muốn fast-fail thật không?**
50. **Có phân biệt NOWAIT conflict với resource not found không?**
51. **Có kiểm chứng PostgreSQL-specific lock_timeout qua Testcontainers không?**
52. **Có tránh coi standard JPA lock.timeout hint là guarantee trên mọi DB không?**
53. **Có dùng SKIP LOCKED chỉ khi tài nguyên thay thế được không?**
54. **Với queue workers, có lease/claim/retry/reclaim policy không?**
55. **Có monitoring starvation/pending age khi SKIP LOCKED không?**
56. **Có tránh giữ DB row lock suốt thời gian xử lý external work dài không?**
57. **Có document provider/dialect-specific SQL và conversion không?**

### 32.6. Tests và tính ổn định của tests

58. **Concurrency integration tests có dùng PostgreSQL/Testcontainers hoặc target DB không?**
59. **Test fixtures có commit trước khi workers bắt đầu không?**
60. **Có tránh @Transactional outer test làm che commit semantics không?**
61. **Có hai physical transactions/connections cho tranh chấp không?**
62. **Có tránh share raw EntityManager giữa threads không?**
63. **Connection pool đủ cho holder và competitor không?**
64. **Có CountDownLatch/Barrier thay vì chỉ Thread.sleep không?**
65. **Có xác nhận holder đã lấy lock trước khi mở competitor không?**
66. **Có Future.get với deadline để tránh treo không?**
67. **Có release.countDown trong finally không?**
68. **Có kiểm tra một success + một sold-out khi stock=5, qty=4 không?**
69. **Có kiểm tra final remaining=1 sau hai requests không?**
70. **Có test blocking lock và release holder không?**
71. **Có test PostgreSQL lock_timeout với holder thực không?**
72. **Có unwrap SQLState khi cần chứng minh lock error category không?**
73. **Có tránh catch mọi RuntimeException và ghi là sold-out không?**
74. **Có test rollback sau em.flush không để lại partial update không?**
75. **Có test cross-tenant access không khóa/sửa stock khác tenant không?**
76. **Có test row không tồn tại và UNIQUE race không?**
77. **Có test multi-row deadlock hoặc lock order nếu workflow cần không?**
78. **Có test JPA @Version với writers khác khi kết hợp pessimistic locking không?**
79. **Có test Order/Outbox rollback cùng Stock khi lỗi không?**
80. **Có test idempotent retries sau commit outcome unknown nếu API có orders không?**

### 32.7. Vận hành và hiệu năng

81. **Có metrics lock wait p95/p99 và lock timeout count không?**
82. **Có DB deadlock/serialization failure tracking không?**
83. **Có đo connection acquire wait và transaction duration không?**
84. **Có phân biệt business sold-out vs technical conflict trong metrics không?**
85. **Có giảm SQL N+1 trong critical section không?**
86. **Có tránh log raw SQL/PII/high-cardinality IDs không?**
87. **Có benchmark hot row workload thay vì chỉ single-thread throughput không?**
88. **Có so với optimistic locking và atomic UPDATE khi phù hợp không?**
89. **Có xác minh cùng business invariant trước khi so benchmark không?**
90. **Có chính sách overload/backpressure thay vì retry storm không?**
91. **Có circuit/timeout policy khi database lock waits vượt SLA không?**
92. **Có migration/index monitoring khi traffic tăng không?**
93. **Có phương án graceful shutdown cho job đang giữ transaction không?**
94. **Có runbook phân biệt pool timeout, lock timeout và deadlock không?**
95. **Có regression test bắt lỗi refactor bỏ @Lock hoặc @Transactional không?**

## 33. Bảng quyết định nhanh

| Bối cảnh | Giải pháp thường cân nhắc | Cảnh báo |
|---|---|---|
| Ít update, nhiều read | Optimistic @Version | Retry stale writes |
| Một stock row nóng | PESSIMISTIC_WRITE hoặc atomic UPDATE | Row bottleneck |
| Client muốn fail nhanh khi đang bận | NOWAIT/lock timeout ngắn | Không nhầm busy với sold-out |
| Queue có nhiều jobs thay thế được | FOR UPDATE SKIP LOCKED | Starvation/lease recovery |
| Giữ một ghế duy nhất | Lock đúng seat/availability resource | Tenant/owner checks |
| Cập nhật nhiều rows | Lock theo thứ tự ổn định | Deadlock vẫn có thể do FK/index |
| Cùng một rule số học đơn giản | Atomic conditional UPDATE | JPA context stale/callbacks |
| Cần domain methods/cascade | Managed entity + locking query | Transaction scope |
| Chỉ cần xem số lượng hàng | Normal read hoặc projection | Không khóa write không cần thiết |
| Cần snapshot nhiều reads | Isolation/read transaction phù hợp | DB semantics khác nhau |
| Job xử lý phút/giờ | Lease/claim và workflow | Không giữ DB row lock xuyên external work |
| Order+Stock+Outbox | Một DB transaction ở use case | External messages sau commit |
| Multi-datasource transaction | JTA/XA hoặc saga | Local tx không tự atomic |
| Concurrent test | Threads + separate transactions + latches | Không dùng shared EntityManager |
| Lock timeout test | PostgreSQL Testcontainers + lock_timeout | SQLState/wrappers cần xác minh |
| Deadlock test | Hai rows, ngược thứ tự và barrier | Cleanup/rollback bắt buộc |
| Production diagnosis | pg_stat_activity, pg_blocking_pids | Quyền truy cập SQL text |

## 34. Sơ đồ quyết định chọn concurrency control

~~~text
        Có thao tác có thể cùng sửa một tài nguyên?
                         |
                   +-----+-----+
                   |           |
                 Không        Có
                   |           |
                   v           v
           Query/read bình   Xác định invariant
           thường hoặc       và DB resource
           optimistic             |
                                 v
                   Có thể diễn đạt trong một
                    atomic SQL UPDATE không?
                           /         \
                         Có          Không
                          |             |
                          v             v
                   Cân nhắc atomic   Phải load
                   conditional SQL   domain entity
                          |             |
                          |             v
                          |      Conflict thường xuyên?
                          |          /          \
                          |        Ít           Nhiều
                          |         |             |
                          |         v             v
                          |     Optimistic     PESSIMISTIC_WRITE
                          |     @Version       + bounded wait
                          |         |             |
                          +---------+-------------+
                                    |
                                    v
                      Use-case @Transactional
                      (read-check-write cùng tx)
                                    |
                                    v
                        Tenant + authorization
                                    |
                                    v
                       Domain invariant + DB
                       UNIQUE/CHECK/FK/Version
                                    |
                                    v
                    Có remote call hoặc event ngoài DB?
                          /                  \
                        Có                 Không
                         |                    |
                         v                    v
                    Outbox/saga            Commit
                    sau commit
                         |
                         v
                     Verify DB state
                         |
                         v
                    Concurrent integration
                    test + timeout + rollback
                         |
                         v
                    Observe metrics/lock waits
~~~

## 35. Một câu trả lời mẫu khi code review

Giả sử đồng nghiệp hỏi: **“Tại sao không chỉ dùng synchronized để trừ tồn kho?”**

Một cách trả lời có căn cứ:

1. Dịch vụ có thể chạy nhiều instances; synchronized chỉ bảo vệ Java monitor trong một instance.
2. Tài nguyên tranh chấp là **database stock row**, nên concurrency control cần có hiệu lực giữa mọi writers.
3. Một locking JPQL query dùng PESSIMISTIC_WRITE để xin row lock.
4. Application service có @Transactional bao lấy lock–check–reserve–Order/Outbox.
5. Domain method kiểm tra available trước khi trừ; database có CHECK để bảo vệ trạng thái không âm.
6. Nếu lock timeout/deadlock, rollback và retry toàn transaction trong context mới theo policy; không gọi “hết hàng” khi chưa đọc state.
7. Có integration test trên PostgreSQL: hai threads cùng reserve 4 từ stock=5, chỉ một thành công; test khác giữ lock để competitor timeout; test rollback sau flush và test tenant scope.
8. Có metrics lock waits, connection pool và retry counts; khi contention cao cân nhắc atomic conditional UPDATE.
9. Không giữ transaction mở trong lúc gọi payment gateway; sau commit dùng outbox/workflow.

Câu trả lời này gắn **thiết kế, transaction scope, correctness test và operational behavior** với nhau, thay vì chỉ đưa ra một annotation.

## 36. Tổng kết

**Xử lý tranh chấp tài nguyên bằng khóa bi quan có kiểm thử** là kỹ năng kết hợp giữa JPA, database transaction, business invariants và integration testing. Bản thân @Lock là cách khai báo **ý định khóa**, nhưng correctness chỉ đến từ **việc chọn đúng row, lấy lock trước business decision, giữ khóa đến khi ghi xong, và kiểm thử bằng những transactions thực**.

### 36.1. Mẫu JPA cần nhớ

Repository:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("""
    select s from StockItem s
    where s.id = :id and s.tenantId = :tenant
    """)
Optional<StockItem> lockByIdAndTenant(
    Long id, String tenant
);
~~~

Application service:

~~~java
@Transactional
public ReservationResult reserve(
        String authorizedTenant, Long stockId, int qty) {

    StockItem stock = repository
        .lockByIdAndTenant(stockId, authorizedTenant)
        .orElseThrow(StockNotFoundException::new);

    stock.reserve(qty);

    return new ReservationResult(
        stock.getId(), stock.getAvailable()
    );
}
~~~

**Lock thuộc database transaction**, không thuộc lifetime của một Java object. @Transactional phải bao cả locking read và managed update; commit/rollback mới xác định outcome cuối cùng.

### 36.2. Mẫu test cần nhớ

~~~text
Setup committed StockItem available=5
                  |
                  v
Start worker A and worker B together
                  |
                  v
Both call real @Transactional service
                  |
                  v
One gets PESSIMISTIC_WRITE lock
                  |
                  v
Reserve(4), COMMIT → available=1
                  |
                  v
Other sees 1, fails InsufficientStock
                  |
                  v
Fresh transaction reads DB:
  success count = 1
  remaining = 1

Plus:
  holder-lock test → second waits
  lock_timeout test → DB confirms conflict
  rollback test → no partial changes
  tenant test → no unauthorized lock/write
~~~

Không chỉ test tuần tự, không mock row lock và không dùng Thread.sleep làm cơ chế đồng bộ chính. Dùng PostgreSQL/Testcontainers hoặc DB tương đương target, latches, transactions tách biệt, future deadlines và DB-state readback.

### 36.3. Những điều khóa bi quan không tự giải quyết

- Không thay domain check available >= qty;
- Không tự cấp quyền tenant;
- Không khóa row chưa tồn tại một cách di động;
- Không tránh mọi deadlock;
- Không sửa business workflow cần nhiều databases;
- Không rollback email/payment đã gửi;
- Không ngăn requests trùng nếu thiếu idempotency;
- Không bảo đảm NOWAIT/SKIP LOCKED portable giữa mọi DBs;
- Không làm long transactions trở nên rẻ;
- Không tự giải quyết mất cập nhật ở các đường native SQL/legacy writers không đồng bộ policy;
- Không tạo kết quả chắc chắn khi connection đứt đúng lúc COMMIT.

### 36.4. Ba câu hỏi quyết định

1. **Đang khóa đúng tài nguyên của invariant chưa?** Ví dụ row StockItem theo id+tenant, không phải một entity liên quan ngẫu nhiên.
2. **Khóa có tồn tại suốt read–check–write trong một transaction không?** Nếu repository tự kết thúc transaction trước use case, thiết kế vẫn sai.
3. **Đã chứng minh bằng kiểm thử tranh chấp thật chưa?** Hai workers, hai transactions, database target, timeout/deadlock/rollback behavior và trạng thái DB sau commit.

**Kết luận:** Hãy dùng PESSIMISTIC_WRITE khi cần tuần tự hóa những thay đổi tranh chấp trên một tài nguyên cụ thể, nhưng luôn đi cùng **transaction boundary đúng, domain invariant, tenant authorization, error/retry policy và integration tests thực sự cạnh tranh**. Khi lock wait trở thành nút cổ chai, so sánh với optimistic @Version hoặc atomic conditional SQL trên cùng tính đúng đắn, rồi chọn phương án dựa trên số liệu và khả năng vận hành của hệ thống.














