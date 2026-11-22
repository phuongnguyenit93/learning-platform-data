# Kiểm chứng cache bằng kết quả và số truy vấn thực tế trong JPA

Khi một ứng dụng sử dụng **Jakarta Persistence (JPA)**, việc bật cache hoặc nhìn thấy annotation `@Cacheable` chưa đủ để khẳng định hệ thống đã giảm truy vấn database. Một bài kiểm chứng tốt phải trả lời **đồng thời hai câu hỏi**:

1. **Kết quả có đúng không?** Entity, dữ liệu và số bản ghi trả về có phản ánh hợp đồng nghiệp vụ và các thay đổi đã commit không?
2. **Truy vấn thực tế diễn ra thế nào?** Có bao nhiêu SQL statements thực sự được gửi tới JDBC/database, bao nhiêu lần cache hit/miss, truy vấn nào được tránh và truy vấn nào vẫn được chạy?

Nếu chỉ kiểm tra response đúng, cache có thể **không hề phát huy tác dụng**. Nếu chỉ kiểm tra số SQL giảm, cache có thể **trả dữ liệu cũ hoặc sai phạm vi người dùng**. Vì vậy, cần kiểm thử cả **correctness** và **observable cache behavior** trong một môi trường có thể lặp lại.

Bài thuộc chương **Bộ nhớ đệm** của chủ đề **Data Persistence Relational Access ORM JPA**, tập trung vào **kiểm chứng cache bằng kết quả và số truy vấn thực tế**. Các ví dụ dùng Java 17+, `jakarta.persistence`, JUnit 5 và Hibernate 6 khi cần công cụ đo; chỉ rõ phần nào là chuẩn JPA và phần nào phụ thuộc provider.

**Thông điệp chính:** *Cache chỉ được xem là đã kiểm chứng khi ta có fixture và ranh giới đo rõ ràng, xác nhận dữ liệu trả về đúng, đồng thời quan sát được số SQL và những cache counters ở đúng phạm vi.*

---

## 1. Ba cơ chế thường bị gọi chung là “cache”

Trong JPA, không phải mọi lần tránh SQL đều bắt nguồn từ cùng một loại cache.

~~~text
Application / service
         |
         v
   EntityManager
         |
         v
   Persistence context
   First-level cache (L1)
         |
         | nếu chưa có managed entity tương ứng
         v
   Shared second-level cache (L2)
         |
         | miss / bypass / invalidated
         v
       Database

Một JPQL query có thể đi qua cơ chế query cache
riêng để tái sử dụng danh sách kết quả hoặc dữ liệu
đã được lưu theo quy tắc của provider.
~~~

### 1.1. First-level cache (L1)

L1 là **identity map của persistence context**. Khi một entity đã được quản lý trong context, `em.find(Entity.class, id)` lần nữa thường trả **đúng managed Java instance đó** mà không cần SELECT thêm.

~~~java
InventoryItem first =
    em.find(InventoryItem.class, id);

InventoryItem second =
    em.find(InventoryItem.class, id);

assertSame(first, second);
~~~

Điều được chứng minh ở đây là **identity và phạm vi context**. Không được từ đó suy luận rằng L2 hoặc query cache đã hoạt động.

### 1.2. Second-level cache (L2)

L2 thường là **shared cache giữa các persistence contexts** của cùng provider/factory, nếu được hỗ trợ và cấu hình. Nó có thể tránh truy vấn database ngay cả khi EntityManager mới chưa quản lý entity đó.

~~~text
EntityManager A                 EntityManager B
      |                               |
 L1 context A                    L1 context B
      |                               |
      +---------------+---------------+
                      |
                      v
                 L2 cache region
                      |
                      v
                   Database
~~~

Hai EntityManagers **không chia sẻ cùng một managed instance** chỉ vì L2 hit. Một L2 hit giúp tái tạo/trả entity data cho context mới theo provider, còn identity của object vẫn được quản lý riêng trong từng L1.

### 1.3. Query cache

Query cache lưu hoặc tái sử dụng **kết quả của một truy vấn** theo query/parameters và quy tắc invalidation của provider. Với Hibernate, một JPQL query **không tự động được cache** chỉ vì entity bên trong có cache L2.

Ví dụ Hibernate-specific:

~~~java
List<InventoryItem> items = em.createQuery(
    """
    SELECT i
    FROM InventoryItem i
    WHERE i.quantity >= :min
    ORDER BY i.id
    """,
    InventoryItem.class
)
.setParameter("min", 10)
.setHint("org.hibernate.cacheable", true)
.getResultList();
~~~

Query cache còn cần **được bật và có cache backend phù hợp**. Hint đơn lẻ không phải bằng chứng rằng query result cache đang hoạt động.

### 1.4. Bảng đối chiếu

| Cơ chế | Phạm vi | Có tự cache mọi JPQL query? | Cách kiểm chứng trọng tâm |
| --- | --- | --- | --- |
| L1 | Một persistence context | Không | `assertSame`, `em.contains`, delta SQL trong cùng context |
| L2 | Chia sẻ giữa contexts tùy provider | Không | Hai EM mới, L2 hit/miss, delta SQL load entity |
| Query cache | Theo provider/query key | Chỉ query được cấu hình và đủ điều kiện | Query miss/hit và SQL SELECT count |
| Application cache | Tầng service khác JPA | Theo thiết kế riêng | Key, TTL/invalidation, quyền và source-of-truth |

**Không lấy một chỉ số chung “cache hit” để kết luận cả L1, L2 và query cache đều tốt.**

---

## 2. Mục tiêu kiểm chứng: dữ liệu đúng và truy vấn được tránh

Một test có ý nghĩa nên có **hai nhóm assertions**.

**Nhóm A — kết quả:**

- Đúng entity ID, SKU, quantity, version.
- Cùng context trả cùng managed instance.
- Hai contexts trả object Java độc lập.
- Sau update/commit, context mới nhìn thấy dữ liệu phù hợp với transaction isolation và cache strategy.
- Không vô tình trả dữ liệu của tenant/user khác.
- Không mất hàng hoặc sai thứ tự khi query có bộ lọc.

**Nhóm B — hành vi:**

- Lần đầu load một ID khi L1/L2 miss cần bao nhiêu SELECT?
- Lần thứ hai cùng context có tạo SELECT mới không?
- Lần đầu load bằng EM mới nhưng L2 warm có tránh được SELECT không?
- JPQL query có tiếp tục chạy SQL nếu query cache chưa bật?
- Bật query cache và lặp lại đúng query có tạo query cache hit không?
- Sau update, cache result có được invalidated/refreshed đúng hay không?
- Với collection LAZY, số SELECT có tăng theo số parent (N+1) không?

Ví dụ bảng kỳ vọng **giả định với một entity đơn giản, không có eager associations và môi trường thử nghiệm được cô lập**:

| Thử nghiệm | Kết quả phải đúng | Kỳ vọng quan sát |
| --- | --- | --- |
| `find(id)` đầu tiên, cold cache | Đúng row | Có DB SELECT khi không có cache hit |
| `find(id)` lần 2, cùng EM | Cùng instance | Không thêm SELECT entity-by-ID |
| `find(id)` từ EM khác, L2 bật/warm | Đúng dữ liệu, object khác | Có thể L2 hit, không cần SELECT |
| `find(id)` từ EM khác, L2 tắt | Đúng dữ liệu, object khác | Thường có SELECT |
| JPQL filter không query cache | Đúng tập kết quả | Query vẫn có thể chạy SQL mỗi lần |
| JPQL filter query cache warm | Đúng tập kết quả | Query-cache hit; SELECT thực tế tùy state/cấu hình |
| Update rồi kiểm tra ở context mới | Giá trị mới | Không nhận dữ liệu stale do cache sai |

Chữ **“thường”, “có thể”, “kỳ vọng”** ở đây rất quan trọng: số SQL là đặc điểm cụ thể của provider, cache backend, dialect, mapping, flush mode và test fixture. Đừng áp một hằng số phổ quát lên mọi JPA implementation.

## 3. Entity mẫu và dữ liệu thử nghiệm

Dùng một entity nhỏ, không có association EAGER, để tách cache behavior khỏi N+1/lazy loading.

~~~java
package com.example.inventory.domain;

import jakarta.persistence.Cacheable;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_items")
@Cacheable
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 80)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @Version
    @Column(nullable = false)
    private Long version;

    protected InventoryItem() {
    }

    public InventoryItem(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public Long getVersion() {
        return version;
    }

    public void changeQuantity(int newValue) {
        if (newValue < 0) {
            throw new IllegalArgumentException(
                "Quantity cannot be negative"
            );
        }
        this.quantity = newValue;
    }
}
~~~

Schema PostgreSQL minh họa:

~~~sql
CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    quantity INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_inventory_nonnegative
        CHECK (quantity >= 0)
);
~~~

Những điều cần hiểu:

- `@Cacheable` là metadata JPA về eligibility với shared cache; **nó không tự cài cache provider/backend**.
- `@Version` giúp kiểm tra optimistic concurrency; không tự đồng bộ mọi L1 contexts đang giữ entity cũ.
- Entity không khai báo `@ManyToOne`/`@OneToMany`, giúp test entity-by-ID dễ cô lập.
- Cấu hình `GenerationType.IDENTITY` có thể khiến INSERT được phát sớm; **không đếm SQL của fixture vào số SELECT của phép đo**.

### 3.1. Fixture phải được commit trước phép đo

~~~java
private static Long createFixture(
        EntityManagerFactory emf,
        int quantity) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        InventoryItem item = new InventoryItem(
            "SKU-" + java.util.UUID.randomUUID(),
            quantity
        );

        em.persist(item);
        em.flush();

        Long id = item.getId();

        em.getTransaction().commit();

        return id;
    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
~~~

Đây là helper cho **application-managed RESOURCE_LOCAL EntityManager**. Với Spring/JTA, transaction do framework/container quản lý nên dùng fixture helper tương ứng.

Không dùng cùng EntityManager của fixture để đo cold-cache read, bởi persistence context vừa tạo fixture đã có managed instance của entity đó.

### 3.2. Giá trị kỳ vọng phải xác định

Giả sử fixture tạo:

~~~text
id       = runtime-generated ID
sku      = unique SKU
quantity = 10
version  = giá trị do provider quản lý
~~~

Test nên assert ít nhất ID và quantity, khi cần thì SKU/version. Không nên chỉ assert `result != null`: một cache stale vẫn có thể trả object không null.

---

## 4. Điều gì được xem là “truy vấn thực tế”?

Có nhiều counters khác nhau, và chúng **không cùng đơn vị đo**.

| Chỉ số | Đo cái gì? | Có chắc là số SELECT database không? |
| --- | --- | --- |
| Số lần gọi `repository.findById` | Số invocation trong Java | **Không** |
| `EntityManager.find` count | Số lần gọi API | **Không** |
| Hibernate `getPrepareStatementCount()` | Số JDBC prepared statements do Hibernate chuẩn bị | **Không**, có cả DML và các lệnh khác |
| Hibernate entity load/fetch counts | Entity materialization/fetch events | **Không** |
| L2 hit/miss/put | Tương tác với shared cache | **Không** |
| Query-cache hit/miss/put | Tương tác query cache | **Không** |
| SQL logs | SQL ORM gửi qua tầng logging | Gần hơn, nhưng phải phân biệt statement đã thực thi |
| JDBC proxy/statement listener | SQL execute calls tại JDBC boundary | Có thể đếm đúng theo loại, nếu cấu hình đúng |
| Database query statistics | Statements database quan sát | Có thể gồm nguồn khác, cần cô lập |
| Application timing | Độ trễ use case | Không phải số SQL |

Nếu test cần câu khẳng định **“lần thứ hai không gửi SELECT xuống database”**, hãy sử dụng công cụ đủ gần **JDBC execute boundary** hoặc SQL observer có kiểm chứng, không chỉ đếm invocation repository.

### 4.1. Hibernate Statistics rất hữu ích nhưng cần đọc đúng

Hibernate cung cấp `org.hibernate.stat.Statistics`, có các counters:

~~~java
SessionFactory sf =
    emf.unwrap(org.hibernate.SessionFactory.class);

Statistics stats =
    sf.getStatistics();

stats.setStatisticsEnabled(true);
stats.clear();

long statements = stats.getPrepareStatementCount();
long l2Hits = stats.getSecondLevelCacheHitCount();
long l2Misses = stats.getSecondLevelCacheMissCount();
long l2Puts = stats.getSecondLevelCachePutCount();
long queryHits = stats.getQueryCacheHitCount();
long queryMisses = stats.getQueryCacheMissCount();
long queryPuts = stats.getQueryCachePutCount();
~~~

Cần imports:

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
~~~

Đây là **Hibernate-specific API**, không phải phần bắt buộc của Jakarta Persistence.

### 4.2. Prepared-statement count không phải SELECT count

Nếu một test gọi:

~~~java
em.persist(item);
em.flush();
em.find(InventoryItem.class, id);
~~~

counter prepared statements có thể bao gồm INSERT, SELECT, UPDATE, sequence-related commands hoặc những SQL khác.

Với entity test cache, nên:

1. Tạo fixture trước.
2. Commit fixture và đóng context.
3. Evict/warm caches theo kịch bản.
4. Reset counters sau setup.
5. Chỉ thực hiện thao tác đọc muốn đo.
6. Phân biệt lệnh SELECT với tổng prepared statements.

Trong **kịch bản đọc một entity đơn giản không tạo DML**, delta `getPrepareStatementCount()` có thể là một proxy hữu ích cho số lệnh JDBC, nhưng không nên gọi nó là “số SELECT tuyệt đối” trong mọi hoàn cảnh.

### 4.3. Counters có phạm vi SessionFactory

`Statistics` thường tổng hợp hoạt động của một SessionFactory. Nếu các tests chạy song song hoặc background jobs cùng dùng factory, counters có thể bị nhiễu.

Vì vậy test dùng `stats.clear()` và so delta cần:

- Chạy cô lập hoặc tạo factory riêng theo class/test.
- Không có request khác dùng chung factory trong cửa sổ đo.
- Tránh warm-up/migration/fixture nằm trong vùng đo.
- Đọc counter ngay sau hành động cần kiểm chứng.
- Ghi rõ Hibernate/provider version và cache config.

Không dùng `stats.clear()` như một thao tác được khuyến nghị tùy ý trong production: đó là instrumentation dùng có chủ đích.

---

## 5. Test L1: lần hai trong cùng EntityManager

Đây là thí nghiệm nền tảng, nên thực hiện đầu tiên vì **không cần L2/query cache**.

~~~java
@Test
void samePersistenceContextReusesManagedInstance() {
    Long id = createFixture(emf, 10);

    EntityManager em = emf.createEntityManager();

    try {
        InventoryItem first =
            em.find(InventoryItem.class, id);

        InventoryItem second =
            em.find(InventoryItem.class, id);

        assertNotNull(first);
        assertSame(first, second);
        assertTrue(em.contains(first));

        assertEquals(10, first.getQuantity());
        assertEquals(id, second.getId());

    } finally {
        em.close();
    }
}
~~~

**Bằng chứng correctness:** hai `find` cùng ID trả object có giá trị đúng, và object identity là một.

**Bằng chứng behavior:** nếu SQL observer được đặt quanh **lần find thứ hai**, không nên thấy một SELECT entity-by-ID mới chỉ vì lời gọi `find` đó (giả định entity đã managed hợp lệ và không có flush/query phụ khác).

### 5.1. Không nhầm cùng Java reference với L2 hit

`assertSame(first, second)` kiểm tra identity trong **L1**, không chứng minh shared-cache hit. Thậm chí L2 có thể hoàn toàn tắt mà test vẫn đúng.

### 5.2. Đặt phép đo chính xác

~~~java
InventoryItem first = em.find(InventoryItem.class, id);

// Baseline bắt đầu sau lần load đầu.
long before = stats.getPrepareStatementCount();

InventoryItem second = em.find(InventoryItem.class, id);

long delta =
    stats.getPrepareStatementCount() - before;

assertSame(first, second);
assertEquals(0L, delta);
~~~

Assertion delta 0 phù hợp khi:

- Hibernate Statistics đã bật.
- Test cô lập.
- Không có side effects SQL khác trong cửa sổ đo.
- Entity đã managed.
- `find` lần hai không bị đặc tả hoặc provider buộc làm việc khác.

Đó là test hành vi cụ thể của một stack, không phải một assertion portable tuyệt đối giữa mọi JPA provider.

## 6. Test clear(): L1 không còn giữ entity

~~~java
@Test
void clearDetachesAndSubsequentFindReturnsAnotherInstance() {
    Long id = createFixture(emf, 10);

    EntityManager em = emf.createEntityManager();

    try {
        InventoryItem before =
            em.find(InventoryItem.class, id);

        assertTrue(em.contains(before));

        em.clear();

        assertFalse(em.contains(before));

        InventoryItem after =
            em.find(InventoryItem.class, id);

        assertNotSame(before, after);
        assertTrue(em.contains(after));
        assertEquals(10, after.getQuantity());

    } finally {
        em.close();
    }
}
~~~

Điều cần kết luận:

- `clear()` làm context quên managed instance cũ.
- Object cũ vẫn tồn tại trong Java nhưng detached.
- `find()` sau clear tạo/lấy managed instance mới.
- **Không thể kết luận sẽ có SQL SELECT chỉ từ `clear`**, vì L2 có thể warm và trả data cho lần find tiếp theo.

### 6.1. Vì sao clear chưa đủ làm “cold cache”?

L1 đã clear, nhưng L2 chưa chắc bị evict.

~~~text
Before clear:
  L1 holds Item#101
  L2 may hold Item#101

After clear:
  L1 no longer holds Item#101
  L2 may STILL hold Item#101

Next find:
  L1 miss -> L2 hit -> no SELECT
~~~

Muốn kiểm chứng DB SELECT sau clear, phải **cô lập hoặc evict L2** theo test setup.

## 7. Test hai EntityManager: không chung L1

~~~java
@Test
void twoEntityManagersHaveIndependentManagedInstances() {
    Long id = createFixture(emf, 10);

    EntityManager em1 = emf.createEntityManager();
    EntityManager em2 = emf.createEntityManager();

    try {
        InventoryItem first =
            em1.find(InventoryItem.class, id);

        InventoryItem second =
            em2.find(InventoryItem.class, id);

        assertNotSame(first, second);
        assertTrue(em1.contains(first));
        assertTrue(em2.contains(second));
        assertFalse(em1.contains(second));
        assertFalse(em2.contains(first));

        assertEquals(first.getId(), second.getId());
        assertEquals(first.getQuantity(), second.getQuantity());

    } finally {
        em2.close();
        em1.close();
    }
}
~~~

Đây là chứng minh **L1 scope** bằng object identity. Nếu em2 không phát SQL, có thể là **L2 hit**, không phải hai contexts chia sẻ một managed object.

### 7.1. Bảng phân biệt trực quan

| Hiện tượng | Khả năng liên quan |
| --- | --- |
| `first == second` trong một context | L1 identity map |
| `first != second` ở hai contexts | Two independent L1 contexts |
| Context mới không SELECT | L2 hit hoặc cache/driver behavior khác |
| Query chạy SQL nhưng trả object đã managed | Query execution và L1 identity cùng tồn tại |
| Query result lần hai không SELECT | Query cache có thể liên quan nếu đã cấu hình |

---

## 8. Bật và kiểm chứng L2 theo Hibernate

`@Cacheable` của Jakarta Persistence biểu thị entity có thể sử dụng shared cache theo shared-cache mode. Tuy nhiên, **Hibernate còn cần cấu hình region factory/cache provider** để L2 thực sự hoạt động.

Ví dụ metadata JPA + Hibernate:

~~~java
@Entity
@Table(name = "inventory_items")
@Cacheable
@org.hibernate.annotations.Cache(
    usage = org.hibernate.annotations.CacheConcurrencyStrategy.READ_WRITE,
    region = "inventory-item-region"
)
public class InventoryItem {
    // Mapping như entity ví dụ.
}
~~~

Đoạn trên là **cách thay/bổ sung annotation trên cùng entity**, không phải một class InventoryItem thứ hai cần tạo trong project.

Cấu hình Hibernate minh họa:

~~~properties
hibernate.generate_statistics=true
hibernate.cache.use_second_level_cache=true
hibernate.cache.use_query_cache=false
hibernate.cache.region.factory_class=jcache
jakarta.persistence.sharedCache.mode=ENABLE_SELECTIVE
~~~

**Lưu ý tương thích:** tên cấu hình region factory có thể dùng dạng class/alias khác tùy Hibernate 6.x, module `hibernate-jcache` và version. Phải cài cache backend cùng JCache provider (chẳng hạn Ehcache với phiên bản tương thích) hoặc một region factory phù hợp. Các property ở trên chỉ mô tả mục tiêu cấu hình, **không đủ để bảo đảm L2 hoạt động trên một project chưa cài backend**.

### 8.1. CacheConcurrencyStrategy có ý nghĩa gì?

Các strategies thường gặp của Hibernate:

| Strategy | Tình huống thường dùng | Cảnh báo |
| --- | --- | --- |
| `READ_ONLY` | Dữ liệu không thay đổi | Không thích hợp với entity thường xuyên update |
| `READ_WRITE` | Entity có cập nhật và cần cơ chế đồng bộ cache phù hợp | Có overhead/invalidation semantics |
| `NONSTRICT_READ_WRITE` | Cho phép mô hình nhất quán lỏng hơn | Không phù hợp nếu đòi hỏi strong consistency |
| `TRANSACTIONAL` | Khi backend/provider hỗ trợ transactional cache | Phụ thuộc nhiều vào cache provider |

Chọn strategy theo **tính nhất quán dữ liệu**, không chỉ theo hit rate.

Entity `InventoryItem` có thay đổi quantity nên ví dụ dùng `READ_WRITE` để minh họa. Đây không phải lời hứa rằng mọi cache provider và transaction architecture sẽ có consistency hoàn toàn giống nhau.

---

## 9. Đo L2 cold miss và warm hit bằng hai contexts

Một test L2 tốt cần ba thời điểm:

1. **Cold:** context mới, shared cache entry được evict trước lần đọc.
2. **Warm:** context mới đọc cùng entity để đưa data vào cache.
3. **Hit:** context mới khác đọc lại, query observer thấy không cần SELECT entity-by-ID; L2 hit counter tăng.

Sơ đồ:

~~~text
Setup fixture + commit
        |
        v
evict L2 entry Item#101
        |
        v
EM A find(id)
  L1 miss
  L2 miss
  DB SELECT
  L2 put / warm
        |
      close EM A
        |
        v
EM B find(id)
  L1 miss
  L2 hit
  DB SELECT may be avoided
        |
      close EM B
~~~

### 9.1. Evict đúng entry

JPA shared cache API:

~~~java
emf.getCache().evict(
    InventoryItem.class,
    id
);
~~~

Đây là lệnh nhắm tới **L2/shared cache**, không clear L1 trong một EntityManager đang mở.

Nếu muốn làm lạnh toàn shared cache:

~~~java
emf.getCache().evictAll();
~~~

Dùng `evictAll()` trong một test cô lập, không gọi tùy tiện trên application production có nhiều requests vì nó có thể làm tăng database load toàn hệ thống.

### 9.2. Test khung với Hibernate Statistics

~~~java
@Test
void warmedSecondLevelCacheServesAnotherContext() {
    Long id = createFixture(emf, 10);

    emf.getCache().evict(InventoryItem.class, id);

    SessionFactory sf =
        emf.unwrap(SessionFactory.class);

    Statistics stats = sf.getStatistics();
    stats.setStatisticsEnabled(true);
    stats.clear();

    EntityManager firstEm = emf.createEntityManager();
    InventoryItem first;

    try {
        first = firstEm.find(InventoryItem.class, id);
        assertEquals(10, first.getQuantity());
    } finally {
        firstEm.close();
    }

    long hitsBefore = stats.getSecondLevelCacheHitCount();
    long statementsBefore = stats.getPrepareStatementCount();

    EntityManager secondEm = emf.createEntityManager();

    try {
        InventoryItem second =
            secondEm.find(InventoryItem.class, id);

        assertNotSame(first, second);
        assertEquals(id, second.getId());
        assertEquals(10, second.getQuantity());
    } finally {
        secondEm.close();
    }

    long hitsDelta =
        stats.getSecondLevelCacheHitCount() - hitsBefore;

    long statementsDelta =
        stats.getPrepareStatementCount() - statementsBefore;

    assertTrue(
        hitsDelta >= 1L,
        "Expected an L2 hit with enabled and working region"
    );

    assertEquals(
        0L,
        statementsDelta,
        "This isolated by-ID read should avoid new JDBC statements"
    );
}
~~~

**Điều kiện để assertion có ý nghĩa:**

- L2 thực sự được cấu hình, entity eligible và region hoạt động.
- Test không chạy song song trên cùng SessionFactory.
- Không có associations EAGER hay background SQL làm nhiễu.
- Cache chưa hết hạn hoặc bị invalidated giữa các lần đọc.
- Provider/strategy có thể cache entity ngay sau lần đọc đầu.
- Fixture đã commit, và L2 entry được evict trước warm-up.

Nếu kết quả là `hitsDelta == 0`, cần kiểm tra **cache config và runtime behavior**; đừng sửa test thành “chỉ cần dữ liệu đúng” rồi khẳng định L2 đã hoạt động.

### 9.3. Put count không phải điều kiện duy nhất

Một `L2 hit` ở lần đọc thứ hai là chỉ dấu cụ thể hơn cho reuse. `put` counter có thể thay đổi bởi warm-up, lifecycle, cache region và provider implementation. Đừng buộc mọi test phải có chính xác một put ở một thời điểm nếu stack chưa được đặc tả.

### 9.4. Có thể kiểm tra Cache.contains

~~~java
boolean present =
    emf.getCache().contains(
        InventoryItem.class,
        id
    );
~~~

Nó trả lời câu hỏi **shared cache có entry entity này không** theo API JPA, nhưng không chứng minh JDBC SELECT đã được tránh. Kết hợp nó với counters và SQL observer.

---

## 10. L1 có thể che khuất L2: lỗi test kinh điển

Một test sai mục tiêu:

~~~java
EntityManager em = emf.createEntityManager();

InventoryItem first =
    em.find(InventoryItem.class, id);

InventoryItem second =
    em.find(InventoryItem.class, id);
~~~

rồi thấy không có SQL thứ hai và kết luận **“L2 hit”**.

Sự thật: **L1 đã đủ để giải thích** hiện tượng đó. Muốn kiểm tra L2 phải sử dụng **EntityManager khác** sau khi lần đầu đã warm shared cache.

### 10.1. Không reset L2 bằng em.clear

~~~java
em.clear();
~~~

chỉ làm context hiện tại quên managed entities. L2 vẫn có thể giữ dữ liệu. Để test đúng:

- Muốn cold L1: dùng EM mới hoặc clear.
- Muốn cold L2: evict shared cache entry/region theo API hoặc cấu hình backend.
- Muốn cold query cache: dùng provider API/region invalidation phù hợp.
- Muốn cold database buffer cache: đây là tầng khác; **không cần** và thường **không nên** thao tác trong JPA cache integration tests.

Đừng đánh đồng database page cache với JPA L1/L2.

---

## 11. Kiểm chứng JPQL query có tiếp tục thực thi SQL

Giả sử L1 đã có một entity:

~~~java
InventoryItem item =
    em.find(InventoryItem.class, id);
~~~

Sau đó gọi:

~~~java
List<InventoryItem> first = em.createQuery(
    """
    SELECT i
    FROM InventoryItem i
    WHERE i.quantity >= :min
    ORDER BY i.id
    """,
    InventoryItem.class
)
.setParameter("min", 10)
.getResultList();
~~~

Một lần gọi lại cùng JPQL:

~~~java
List<InventoryItem> second = em.createQuery(
    """
    SELECT i
    FROM InventoryItem i
    WHERE i.quantity >= :min
    ORDER BY i.id
    """,
    InventoryItem.class
)
.setParameter("min", 10)
.getResultList();
~~~

**Nếu query cache không bật/không được dùng**, provider vẫn có thể thực thi SELECT để xác định tập rows khớp, dù entity objects sau đó có thể lấy từ L1 identity map.

### 11.1. Kết quả giống nhau không chứng minh query cache

~~~java
assertEquals(first.size(), second.size());
~~~

chỉ xác nhận hai tập kết quả có kích thước như nhau. Nó không cho biết query được thực thi một hay hai lần.

Muốn kiểm chứng:

- Dùng query cache enabled/disabled như các cấu hình test tách biệt.
- Đặt SQL observer ở query execution.
- Assert số SELECT hoặc query-cache hit/miss delta.
- Xác minh đầy đủ ID/quantity của rows, không chỉ list size.

### 11.2. Query cache khác L2 entity cache

Hibernate query cache có thể lưu **query result identity information** rồi cần tải entity state qua L2 hoặc DB tùy trường hợp. Một query-cache hit không mặc nhiên có nghĩa **không có bất kỳ SELECT nào**.

Ví dụ:

~~~text
Query cache hit:
    IDs = [101, 102, 103]

L2 entity cache:
    101 hit
    102 miss -> DB SELECT
    103 hit
~~~

Vì vậy phải đo cả:

- Query-cache hits.
- L2 hits/misses.
- JDBC SELECTs.
- Kết quả returned.

Không dùng một query-cache counter để kết luận toàn bộ request không truy vấn DB.

## 12. Bật query cache và kiểm tra hit

Hibernate-specific cấu hình:

~~~properties
hibernate.cache.use_query_cache=true
hibernate.generate_statistics=true
~~~

Cùng với L2/cache backend phù hợp, query có thể đặt hint:

~~~java
private List<InventoryItem> findAtLeast(
        EntityManager em,
        int minQuantity) {

    return em.createQuery(
        """
        SELECT i
        FROM InventoryItem i
        WHERE i.quantity >= :min
        ORDER BY i.id
        """,
        InventoryItem.class
    )
    .setParameter("min", minQuantity)
    .setHint("org.hibernate.cacheable", true)
    .getResultList();
}
~~~

Một kịch bản kiểm chứng:

~~~text
A. Cold query cache + cold/controlled L2.
B. EM1 gọi query(min=10), assert IDs và quantities.
C. Đóng EM1.
D. EM2 gọi lại đúng query(min=10).
E. Assert kết quả giống hợp đồng.
F. Assert query cache hit tăng.
G. Assert SQL theo đúng kỳ vọng cấu hình.
~~~

### 12.1. Query key cần được giữ nhất quán

Để so sánh lần đầu/lần sau:

- Cùng query text/semantics.
- Cùng parameter values/types.
- Cùng pagination, sorting và query hints liên quan.
- Cùng tenant/authorization scope theo contract.
- Cùng cache region phù hợp.
- Không có intervening updates làm query cache invalidated.

Chỉ cần thay `min=10` thành `min=11` thì đó là **query key khác**, không nhất thiết hit.

### 12.2. Một test skeleton

~~~java
@Test
void identicalCachedQueryCanHitOnSecondExecution() {
    Long id = createFixture(emf, 15);

    SessionFactory sf =
        emf.unwrap(SessionFactory.class);

    Statistics stats = sf.getStatistics();
    stats.setStatisticsEnabled(true);

    // Cần làm lạnh query region bằng provider API
    // hoặc dùng cache region/test factory cô lập.
    // Không khẳng định em.clear() sẽ xóa query cache.
    stats.clear();

    EntityManager em1 = emf.createEntityManager();

    try {
        List<InventoryItem> rows =
            findAtLeast(em1, 15);

        assertTrue(
            rows.stream().anyMatch(i -> i.getId().equals(id))
        );
    } finally {
        em1.close();
    }

    long hitsBefore = stats.getQueryCacheHitCount();

    EntityManager em2 = emf.createEntityManager();

    try {
        List<InventoryItem> rows =
            findAtLeast(em2, 15);

        assertTrue(
            rows.stream().anyMatch(i -> i.getId().equals(id))
        );
    } finally {
        em2.close();
    }

    long hitDelta =
        stats.getQueryCacheHitCount() - hitsBefore;

    assertTrue(hitDelta >= 1L);
}
~~~

Đây là skeleton cho **một Hibernate setup đã cấu hình query cache và isolate/warm query region đúng**. Phần “cold query cache” phải được thực hiện theo provider/cache backend cụ thể; `Statistics.clear()` **chỉ reset counters, không xóa cache entries**.

Đó là sai lầm rất hay gặp trong test: reset số đếm nhưng không reset cache, khiến lần gọi đầu vốn đã là cache hit từ test trước.

## 13. Đo SELECT thực qua JDBC proxy

Nếu yêu cầu chính xác “số SELECT chạy xuống database”, có thể đặt một **JDBC proxy/instrumentation layer** quanh DataSource bằng công cụ phù hợp, ví dụ datasource-proxy hoặc P6Spy, hoặc giám sát từ database.

Ý tưởng:

~~~text
Service/repository
       |
       v
JPA provider
       |
       v
DataSource / JDBC proxy  <---- đếm execute calls, loại SQL
       |
       v
JDBC driver
       |
       v
Database
~~~

Phép đo nên phân biệt:

- SELECT.
- INSERT/UPDATE/DELETE.
- Transaction control/DDL nếu observer ghi nhận.
- Prepared/batched statements.
- Nhiều result sets hoặc procedures.
- Statements từ request/test khác.

### 13.1. Vì sao một SQL log không luôn đủ?

SQL logger có thể ghi khi statement được chuẩn bị, trước khi JDBC thực thi. Một số logging settings không hiển thị JDBC batches hoặc database-internal SQL như mong muốn.

Vì thế phải hiểu observer đang đếm:

- **SQL text được provider tạo**,
- **Prepared statements**,
- **JDBC execute calls**, hay
- **Statements thực sự database nhận**.

Một tool tốt vẫn phải được cấu hình/cô lập đúng. Không trộn số của nhiều request vào một test rồi gọi đó là “SELECT count của service A”.

### 13.2. StatementInspector của Hibernate

Hibernate có `StatementInspector` để quan sát SQL được provider chuẩn bị:

~~~java
package com.example.inventory.test;

import org.hibernate.resource.jdbc.spi.StatementInspector;
import java.util.concurrent.atomic.AtomicInteger;

public final class SqlInspectionCounter
        implements StatementInspector {

    private final AtomicInteger inspectedSql =
        new AtomicInteger();

    @Override
    public String inspect(String sql) {
        inspectedSql.incrementAndGet();
        return sql;
    }

    public int count() {
        return inspectedSql.get();
    }

    public void reset() {
        inspectedSql.set(0);
    }
}
~~~

Có thể đăng ký inspector qua cấu hình Hibernate hoặc programmatic bootstrap theo provider/version.

**Giới hạn quan trọng:** `StatementInspector` quan sát câu SQL tại bước chuẩn bị, không phải công cụ bảo đảm một-một với số **JDBC execute calls**. Nó hữu ích cho query shape/count trong test, nhưng nếu tiêu chí là statements thực thi, hãy dùng JDBC proxy hoặc DB-side monitoring.

### 13.3. Bộ đếm trên inspector toàn cục dễ bị nhiễu

Nếu cùng inspector phục vụ nhiều threads/tests:

~~~java
AtomicInteger count;
~~~

nó có thể đếm cả câu SQL từ request khác. Cần session/test isolation, thread-specific context hoặc đóng vùng đo rõ. Không gắn một global counter vào production app rồi assert chính xác per-request mà không có correlation.

---

## 14. Cách ghi nhận kết quả một thí nghiệm cache

Một bảng kết quả nên đi kèm **điều kiện đo**, không chỉ một số:

| Trường | Ví dụ |
| --- | --- |
| Scenario | find Item#101, EM mới, L2 warm |
| JPA provider | Hibernate 6.x |
| Database | PostgreSQL (version mục tiêu) |
| L1 status | Cold (EntityManager mới) |
| L2 status | Warm sau EM khác |
| Query cache | Disabled |
| Entity mapping | `@Cacheable` + region READ_WRITE |
| Fixture | id=101, quantity=10, version=V |
| Assertions | id/quantity/version đúng, instance khác |
| L2 hit delta | 1 trong môi trường cô lập |
| JDBC SELECT delta | 0 trong môi trường cô lập |
| Kết luận | L2 đã trả entity state đúng và tránh SELECT ở lần đọc warm |

Đây là **mẫu báo cáo minh họa**, không phải số đo thực tế của bài học. Khi chạy project thật, thay bằng logs/counters đo được.

### 14.1. Quan sát cùng một tình huống qua hai chiều

Nếu:

~~~text
result.quantity = 10
L2 hit delta = 1
SELECT delta = 0
~~~

trong test clean/warm đúng, có cơ sở nói L2 đã phục vụ lần đọc này.

Nhưng nếu DB đã được cập nhật sang quantity=20 mà cache trả 10, phép kiểm chứng **đã phát hiện correctness failure**, cho dù cache-hit rất tốt.

---

## 15. Thí nghiệm data correctness sau UPDATE

Giả sử có hai transactions:

~~~text
T1: update Item#101 quantity=10 -> 20, commit.
T2: đọc Item#101 sau commit trong EM mới.
~~~

Expected result: tùy transaction isolation và cache strategy, trong một **read transaction mới ở trạng thái thông thường có thể thấy commit trước đó**, hệ thống cần trả `quantity=20` theo yêu cầu consistency của nghiệp vụ.

### 15.1. Test update rồi read từ context mới

~~~java
@Test
void committedUpdateIsVisibleToFreshContext() {
    Long id = createFixture(emf, 10);

    EntityManager writer = emf.createEntityManager();

    try {
        writer.getTransaction().begin();

        InventoryItem item =
            writer.find(InventoryItem.class, id);

        item.changeQuantity(20);

        writer.getTransaction().commit();

    } catch (RuntimeException ex) {
        if (writer.getTransaction().isActive()) {
            writer.getTransaction().rollback();
        }
        throw ex;
    } finally {
        writer.close();
    }

    EntityManager reader = emf.createEntityManager();

    try {
        InventoryItem result =
            reader.find(InventoryItem.class, id);

        assertNotNull(result);
        assertEquals(20, result.getQuantity());

    } finally {
        reader.close();
    }
}
~~~

Test xác nhận **cache behavior không làm sai kết quả** theo setup của giao dịch đọc mới. Nếu L2 bật, provider phải đồng bộ/invalidate shared cache theo concurrency strategy thích hợp.

### 15.2. Không chỉ assert cache hit

Một test chỉ viết:

~~~java
assertTrue(
    stats.getSecondLevelCacheHitCount() > 0
);
~~~

mà không assert quantity/version có thể bỏ qua một lỗi cache staleness.

Tính đúng **luôn quan trọng hơn** số truy vấn tránh được.

### 15.3. Read cũ trong EntityManager đã mở là chuyện khác

Nếu một EntityManager đã managed `InventoryItem#101` quantity=10 **trước khi** writer commit, rồi gọi `find` lần nữa, nó có thể vẫn trả 10 vì L1.

~~~java
InventoryItem before =
    oldEm.find(InventoryItem.class, id);

// writer commit quantity=20.

InventoryItem again =
    oldEm.find(InventoryItem.class, id);

assertSame(before, again);
~~~

Không nên coi kết quả này là bằng chứng L2 invalidation sai; **L1 context giữ identity và state theo unit of work**. Muốn thử shared-cache correctness, sử dụng **EntityManager mới**, không dùng context đang giữ entity cũ.

---

## 16. Thí nghiệm evict: phân biệt L2 eviction và L1 retention

Một case quan trọng:

~~~java
InventoryItem held =
    em.find(InventoryItem.class, id);

emf.getCache().evict(
    InventoryItem.class,
    id
);

InventoryItem again =
    em.find(InventoryItem.class, id);

assertSame(held, again);
~~~

Dù L2 entry vừa bị evict, `em` vẫn quản lý `held`. Evict L2 **không detach L1**.

Muốn kiểm tra lần đọc DB sau eviction:

~~~java
EntityManager fresh = emf.createEntityManager();

try {
    InventoryItem loaded =
        fresh.find(InventoryItem.class, id);
} finally {
    fresh.close();
}
~~~

Với L2 entry đã thực sự bị loại, không có cache khác làm nhiễu, observer thường thấy SELECT để lấy row.

### 16.1. Counter sau eviction

Phải đo **sau khi** eviction và từ EM mới. Nếu dùng cùng EM, L1 hit có thể khiến số SELECT vẫn 0, dẫn đến kết luận sai rằng L2 eviction không hoạt động.

### 16.2. Evict region hoặc evictAll

Khi cần test vùng dữ liệu rộng hơn, JPA `Cache` hỗ trợ những overload `evict` và `evictAll`. Chỉ dùng trong test có quyền sở hữu cache state; không dọn cache production của toàn hệ thống như một bước kiểm thử thông thường.

---

## 17. CacheRetrieveMode và CacheStoreMode

JPA có hints để điều khiển tương tác với shared cache:

~~~java
InventoryItem item = em.find(
    InventoryItem.class,
    id,
    java.util.Map.of(
        "jakarta.persistence.cache.retrieveMode",
        jakarta.persistence.CacheRetrieveMode.BYPASS,
        "jakarta.persistence.cache.storeMode",
        jakarta.persistence.CacheStoreMode.BYPASS
    )
);
~~~

Cần nhớ:

- `CacheRetrieveMode.BYPASS` hướng tới việc không lấy data từ shared L2.
- `CacheStoreMode.BYPASS` hướng tới việc không đưa state vào shared L2.
- `CacheStoreMode.REFRESH` mang semantics refresh/update shared cache theo JPA.
- Các hints không có nghĩa `EntityManager.find` sẽ bỏ qua **managed instance đã có trong L1**.

### 17.1. Test BYPASS phải dùng context mới

Sai:

~~~java
InventoryItem first = em.find(InventoryItem.class, id);

InventoryItem second = em.find(
    InventoryItem.class,
    id,
    bypassProperties
);
~~~

rồi đếm SQL và suy ra shared cache đã bypass. Trong cùng context, `first` đã managed.

Đúng hướng:

1. Xây fixture và commit.
2. Warm L2 trong EM A.
3. Đóng EM A.
4. Đo lần `find` với BYPASS trên EM B mới.
5. So với lần `find` không BYPASS trên EM C mới.
6. Assert dữ liệu và delta SQL/L2 tương ứng.

Đừng mặc định provider sẽ báo cùng exact hit/miss counters dưới mọi hint combination.

---

## 18. Cache staleness sau native SQL và bulk update

Một case quan trọng cho correctness:

~~~java
InventoryItem item =
    em.find(InventoryItem.class, id);

int affected = em.createQuery(
    """
    UPDATE InventoryItem i
    SET i.quantity = :value
    WHERE i.id = :id
    """
)
.setParameter("value", 40)
.setParameter("id", id)
.executeUpdate();
~~~

Bulk JPQL/native DML không hoạt động hoàn toàn như sửa managed entity rồi dirty checking. `item` trong L1 có thể vẫn giữ `quantity=10`, dù database đã nhận UPDATE.

### 18.1. Query count đẹp nhưng dữ liệu có thể sai

~~~text
Managed Item#101 quantity=10
Bulk UPDATE DB quantity=40
em.find(Item#101) -> same managed object quantity=10
New SELECT count -> 0
~~~

0 SELECT không phải bằng chứng cache “đúng”; đó có thể là **stale managed state**.

### 18.2. Giải pháp phải theo boundary

Nếu có pending managed changes, cần cân nhắc `em.flush()` trước bulk DML, rồi `em.clear()` hoặc `em.refresh(item)` phù hợp khi muốn đọc state mới. Không gọi clear mù quáng nếu còn entities đang có changes cần giữ.

Đối với L2, cache invalidation sau bulk/native operations phụ thuộc provider, đường cập nhật và cấu hình. Nếu SQL thay đổi database **ngoài JPA** (job khác, trigger, ETL, direct JDBC), ứng dụng cần chiến lược TTL/eviction/refresh phù hợp; không giả định JPA biết mọi thay đổi.

### 18.3. Một test cụ thể về external changes

Kịch bản:

1. Warm L2 với quantity=10.
2. Dùng **một connection/JDBC unit-of-work khác** UPDATE database thành 40 và commit.
3. Từ EM mới thử `find(id)`.
4. Quan sát có trả 10 do stale cache không.
5. Evict L2 hoặc dùng BYPASS theo contract.
6. Đọc lại, assert quantity=40 và SQL behavior.
7. Thiết kế production invalidation policy từ kết quả này.

**Đây là bài test về chính sách invalidation**, không được xem là bằng chứng L2 mặc định luôn an toàn trước mọi thay đổi ngoài ORM.

---

## 19. Transaction isolation có thể làm phép đo stale-data sai

Giả sử T1 đọc quantity=10 ở isolation giữ snapshot, T2 commit quantity=40, rồi T1 tiếp tục SELECT.

Ngay cả khi L1/L2 được bypass, database vẫn có thể trả snapshot cũ theo isolation.

Do đó stale read có ít nhất ba nguồn:

- L1 vẫn giữ managed instance.
- L2/query cache có entry stale.
- Database isolation/snapshot chưa cho transaction nhìn thấy commit mới.

Test nên:

- Đặt transaction boundaries rõ.
- So sánh tại **transaction mới** khi muốn kiểm tra committed latest state.
- Biết isolation level của database.
- Không tự kết luận cache lỗi khi kết quả do repeatable-read snapshot.
- Không dùng một transaction dài để đo nhiều trạng thái update khác nhau mà không kiểm soát snapshot.

### 19.1. @Version không tự refresh

Entity version field giúp phát hiện stale updates, không đẩy giá trị mới vào mọi persistence contexts ngay khi một transaction khác commit.

Khi assert freshness, cần **context/transaction đúng** và thiết kế cache invalidation phù hợp, không dựa riêng vào `@Version`.

## 20. Test cache trong môi trường nhiều người dùng/tenant

Một cache hiệu quả về số truy vấn nhưng **trả kết quả của tenant khác** là lỗi nghiêm trọng.

Ví dụ query:

~~~jpql
SELECT i
FROM InventoryItem i
WHERE i.quantity >= :min
~~~

nếu ứng dụng multi-tenant và dữ liệu không được phân vùng/filtered đúng, response có thể bị lẫn dữ liệu.

Trong test query cache, phải xác nhận:

- Cache key và query semantics tôn trọng tenant scope.
- Tenant discriminator hoặc database schema được áp đúng.
- Quyền truy cập được kiểm tra trước khi trả data.
- Cùng query text ở hai tenant không dẫn tới dùng sai kết quả.
- L2 entity region được cấu hình hỗ trợ tenancy theo provider/model.

Không tự giả định một cache backend chung sẽ ngăn cross-tenant leak.

### 20.1. Test security và performance cùng lúc

Một test đúng cần assert:

~~~text
Tenant A thấy IDs của A, không thấy IDs của B.
Tenant B thấy IDs của B, không thấy IDs của A.
Cache hits may occur, but data separation must remain correct.
~~~

Sau đó mới kiểm tra số SQL ở từng tenant và trường hợp warm-cache phù hợp.

---

## 21. N+1: cache có thể che vấn đề chứ không sửa fetch plan

Giả sử 100 orders cùng trỏ tới các customers, mapper gọi:

~~~java
orders.stream()
    .map(o -> o.getCustomer().getEmail())
    .toList();
~~~

Nếu quan hệ `customer` LAZY:

- Khi L2 cold, có thể phát nhiều SELECT.
- Khi L2 warm, số SELECT giảm.
- Nếu nhiều orders cùng customer, L1 có thể giúp tái sử dụng instance.
- Nếu test chỉ chạy warm-cache, N+1 của fetch plan có thể bị che giấu.

**Một endpoint không nên chỉ đạt hiệu năng tốt khi cache đã warm.** Khi cache cold/restarted hoặc dataset có nhiều keys mới, query storm có thể xuất hiện.

### 21.1. Test theo hai nhiệt độ cache

| Test | Trạng thái | Câu hỏi |
| --- | --- | --- |
| Cold | L1 mới, L2/query cache cold | Fetch plan có tạo N+1 không? |
| Warm | Cache đã được đọc trước | Cache giúp giảm bao nhiêu SQL? |
| Mixed | Một phần keys hit, phần còn lại miss | Có query storm khi hit rate thấp không? |
| After update | Cache invalidated/updated | Correctness có còn đúng? |

Nếu endpoint có N+1 ở cold state, cân nhắc `JOIN FETCH`, `EntityGraph`, DTO projection hoặc batch fetching phù hợp thay vì chỉ mở rộng cache.

### 21.2. Không chỉ đếm SELECT, đo rows và thời gian

Một query join nhiều collections có thể chỉ là **một SELECT** nhưng trả hàng chục nghìn SQL rows do row multiplication.

Cần đo:

- Statements.
- Rows returned/processed.
- Bytes transferred.
- Cache-hit ratio.
- Database execution time.
- Application latency và memory.
- Kích thước response thực.

0 hoặc 1 SELECT không tự bảo đảm use case nhanh nhất.

---

## 22. Thí nghiệm so sánh warm-up và lần đo thật

Một sai lầm phổ biến: dùng lần đo đầu làm benchmark, sau đó kết luận lần hai nhanh hơn hoàn toàn nhờ cache.

Lần đầu có thể bao gồm:

- JPA/metadata initialization.
- Hibernate query-plan compilation.
- JDBC connection pool startup.
- Database buffer cache warmup.
- JIT compilation.
- Cache provider startup.
- Prepared statement caches.

Đó là những hiệu ứng **khác với L2/query cache**.

### 22.1. Phân tách cold-cache test và timing benchmark

Đối với **behavior correctness**:

- Evict đúng cache region.
- Reset observation counters.
- Quan sát SQL/hits/misses.
- Assert returned data.

Đối với **performance benchmark**:

- Warm-up runtime đủ.
- Chạy nhiều iterations có thống kê.
- Dùng dữ liệu/queries đại diện.
- Đo p50/p95/p99 khi phù hợp.
- Tránh test khác làm nhiễu.
- Không dùng một lần chạy 2 ms vs 3 ms để kết luận cache có lợi 33%.

### 22.2. Cache-hit ratio không phải luôn tốt hơn

Nếu L2 region nhỏ nhưng dữ liệu liên tục thay đổi, chi phí invalidation, serialization và synchronization có thể vượt lợi ích giảm SELECT.

Test cần so sánh **latency end-to-end**, throughput, memory và contention, không chỉ nhắm tối đa hit ratio.

## 23. Test fixture/counters phải được cô lập

Một quy trình lặp lại được:

~~~text
1. Tạo fixture trong transaction riêng.
2. Commit và đóng EntityManager fixture.
3. Evict/warm đúng L1/L2/query region theo kịch bản.
4. Reset observer counters (không nhầm với evict cache).
5. Mở EntityManager mới.
6. Thực hiện đúng thao tác cần đo.
7. Assert đầy đủ dữ liệu.
8. Đọc counters/SQL trong cùng vùng đo.
9. Đóng EntityManager / rollback nếu cần.
10. Ghi nhận điều kiện DB/provider/cache configuration.
~~~

Nếu `stats.clear()` chỉ reset counters mà query cache vẫn warm từ bài test trước, “cold query test” có thể nhận cache hit ngay bước đầu.

Nếu chỉ `em.clear()` mà L2 vẫn warm, “DB first read” có thể không SELECT. Do đó **setup state và reset instrumentation là hai thao tác khác nhau**.

### 23.1. Tests chạy song song

Hibernate `Statistics` thường có scope factory. Hai tests cùng lúc có thể cùng tăng counter.

Giải pháp:

- Chạy một nhóm đo SQL tuần tự.
- Dùng factory/database/schema cô lập cho test class nếu cần.
- Dùng per-request/per-test JDBC observer với correlation.
- Hạn chế background task trong cửa sổ đo.
- Không assert số statements tuyệt đối khi không thể cô lập.

### 23.2. Không dùng @Transactional test như một context vô hạn

Một test Spring gắn `@Transactional` ở test method có thể khiến fixture và các `find` cùng chung persistence context. Điều này dễ làm test L2 **xanh giả**.

Khi cần hai contexts:

- Tách fixture/setup transaction.
- Gọi service methods qua transaction boundaries thật.
- Dùng `TransactionTemplate` hoặc separate EntityManagers phù hợp.
- Không dựa vào hai lời gọi repository bên trong cùng transaction.

---

## 24. L1 test với Hibernate Statistics: ví dụ tập trung

Đây là ví dụ một phép đo có tính chất **kiểm tra hành vi cụ thể**.

~~~java
@Test
void secondFindInSameContextDoesNotPrepareAnotherStatement() {
    Long id = createFixture(emf, 10);

    // Nếu L2 bật, có thể giữ nguyên, vì phép đo chỉ
    // quan sát lần find thứ hai sau khi L1 đã có entity.
    SessionFactory sf =
        emf.unwrap(SessionFactory.class);

    Statistics stats = sf.getStatistics();
    stats.setStatisticsEnabled(true);

    EntityManager em = emf.createEntityManager();

    try {
        InventoryItem first =
            em.find(InventoryItem.class, id);

        assertEquals(10, first.getQuantity());

        // Chỉ reset counters sau khi L1 được warm.
        stats.clear();

        InventoryItem second =
            em.find(InventoryItem.class, id);

        assertSame(first, second);

        assertEquals(
            0L,
            stats.getPrepareStatementCount()
        );

    } finally {
        em.close();
    }
}
~~~

**Điều test này không chứng minh:** không chứng minh có L2 hit, không chứng minh truy vấn JPQL được cache, không chứng minh hiệu năng production.

Nếu đang test trong một factory dùng chung với tests khác, `stats.clear()` sẽ tác động counters của toàn factory và phép đo không còn cô lập; cần cơ chế isolate.

## 25. Query-cache test phải kiểm tra invalidation sau update

Không đủ để kiểm tra “query chạy hai lần và lần hai hit”. Cần thêm kịch bản:

~~~text
Initial dataset:
  A quantity=15
  B quantity=5

Cached query: quantity >= 10
Expected: [A]

Transaction changes B quantity=20, commit

Repeat cached query in new transaction/context
Expected: [A, B]
~~~

Nếu cache trả lại `[A]` sau update khi contract yêu cầu dữ liệu mới, có lỗi consistency/invalidation.

### 25.1. Kiểm tra tập IDs, không chỉ size

Sai:

~~~java
assertEquals(2, result.size());
~~~

Có thể trả hai records sai.

Tốt hơn:

~~~java
Set<Long> ids = result.stream()
    .map(InventoryItem::getId)
    .collect(java.util.stream.Collectors.toSet());

assertEquals(Set.of(idA, idB), ids);
~~~

Khi order matters:

~~~java
assertEquals(
    List.of(idA, idB),
    result.stream()
        .map(InventoryItem::getId)
        .toList()
);
~~~

Hãy chọn assertion phù hợp với `ORDER BY` thật sự trong JPQL.

### 25.2. Query cache có thể invalidated vì update nhiều bảng

Một provider có thể quản lý timestamps/region invalidation liên quan tới những query spaces (tables) bị thay đổi. Hành vi cụ thể tùy Hibernate version/configuration. Test không nên hardcode “lần query thứ ba bắt buộc cache miss đúng một lần” nếu backend/region chưa được mô tả rõ; điều bắt buộc là **dữ liệu đúng** và hành vi thực tế được quan sát.

---

## 26. Cách xử lý khi số truy vấn khác dự kiến

Một phép kiểm chứng cần điều tra có hệ thống, không lập tức tăng timeout hoặc nới assertion.

| Quan sát | Nguyên nhân khả dĩ | Kiểm tra |
| --- | --- | --- |
| L1 find lần hai vẫn SELECT | Query khác/flush phụ, context không giống nhau | EM scope, SQL observer |
| L2 test không hit | Backend không bật, entity không cacheable, entry evicted | Hibernate config, region stats |
| L2 test hit nhưng SQL vẫn chạy | EAGER association/secondary query, flush, observer đếm loại khác | SQL text, mapping |
| Query-cache hit = 0 | Query không đánh dấu cacheable, key khác, cache chưa bật | Hint/config/parameters |
| Query cache hit nhưng SELECT > 0 | Entity data L2 miss, secondary loads | L2 misses và SQL shape |
| Cold test có 0 SELECT | L2 còn warm, test dùng cùng EM, JDBC observer chưa gắn đúng | Cache eviction, new EM, instrumentation |
| Warm test có 1 SELECT | Entry hết hạn/evicted, provider strategy, query khác | Region state, logs |
| Cache trả quantity cũ | L1 stale, L2 invalidation, external SQL, isolation | New context, transaction, evict/refresh |
| Count tăng khi tăng N | N+1 association | Fetch plan, SQL statements by type |
| Count tăng khi không có request | Background/test khác dùng chung factory | Isolate statistics and pool |
| Cache hit cao nhưng latency cao | Serialization/invalidation contention, rows rộng | Timing/CPU/network |
| Count đúng nhưng API sai dữ liệu | Cache key/tenant/filter bug | Business/result assertions |

### 26.1. Đừng sửa test bằng cách chấp nhận mọi count

Khi kỳ vọng không khớp, nên xác định trước:

- Test đang chứng minh **một yêu cầu portable** hay **hành vi của Hibernate 6 với cấu hình xác định**?
- SQL observer đếm prepared statements hay JDBC executions?
- L1/L2/query cache đang cold hay warm?
- Có transaction khác sửa dữ liệu không?
- Có eager/lazy associations tạo SQL phụ không?
- Có background hoạt động trong vùng đo không?

Sau khi biết nguyên nhân mới điều chỉnh testcase hoặc expectation.

---

## 27. Reporting: ma trận kiểm chứng đủ dùng cho code review

Một báo cáo tốt có thể trình bày:

| Scenario | Correctness assertion | L1 | L2 | Query cache | SQL expectation |
| --- | --- | --- | --- | --- | --- |
| Same EM `find` twice | Same reference, expected values | Warm | Any | N/A | Second call: no entity SELECT |
| New EM, L2 evicted | Different reference, expected values | Cold | Cold | N/A | DB SELECT expected |
| New EM, L2 warm | Different reference, expected values | Cold | Warm | N/A | Entity SELECT avoided in isolated setup |
| JPQL no query cache | IDs/filter/order correct | Any | Any | Off | Query SQL may run each time |
| JPQL cached, same key | IDs/filter/order correct | New EM | Controlled | Warm | Query-cache hit; entity selects depend on L2 |
| After entity update | New quantity/version | New EM | Updated/invalidate | Controlled | Correct data, no stale response |
| After external SQL | Expected data per invalidation policy | New EM | May be stale | Controlled | Explicit eviction/bypass test |
| Cold list with lazy children | Complete DTO; no missing data | Cold | Cold | Off | Detect N+1 by growth vs N |

Không chỉ gửi cho reviewer một screenshot `SecondLevelCacheHitCount = 12` mà thiếu fixture, config và dữ liệu trả về.

---

## 28. Spring Data JPA: kiểm chứng ở tầng service

Một repository:

~~~java
public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    List<InventoryItem> findByQuantityGreaterThanEqual(
        int quantity
    );
}
~~~

Khi service gọi:

~~~java
@Transactional(readOnly = true)
public InventoryDto find(Long id) {
    InventoryItem item =
        repository.findById(id).orElseThrow();

    return new InventoryDto(
        item.getId(),
        item.getSku(),
        item.getQuantity(),
        item.getVersion()
    );
}
~~~

Hai lần gọi service có thể chạy trong **hai transactions/contexts** khác nhau, dù method repository giống nhau. Vì vậy:

- L1 hit của hai calls không được giả định.
- Nếu second call tránh SQL, có thể do L2.
- Nếu cả hai calls nằm trong một outer transaction, L1 có thể giải thích.
- Spring OSIV có thể khiến EntityManager sống lâu hơn service transaction trong một request.

### 28.1. Test annotation @Transactional có thể che L2

Một test:

~~~java
@Transactional
@Test
void testCaching() {
    service.find(id);
    service.find(id);
}
~~~

có thể dùng cùng outer transaction. Test này không mặc định chứng minh L2 caching giữa transactions.

Muốn test **cross-context L2**:

1. Tạo fixture và commit.
2. Không giữ một outer transaction bao cả test.
3. Warm từ transaction/context A.
4. Đọc từ transaction/context B.
5. Observe L2 hits và JDBC SQL.
6. Assert DTO values.

Dùng Spring `TransactionTemplate` hoặc transaction propagation đúng, không tự gọi private method có `REQUIRES_NEW` rồi cho rằng proxy advice sẽ chạy.

---

## 29. Tỷ lệ cache hit và độ trễ production

Sau khi integration tests xác nhận correctness, hệ thống production có thể theo dõi:

- L2 hit/miss rate theo region.
- Query-cache hit/miss rate nếu được dùng.
- JDBC SELECT counts và duration.
- Database CPU/read IOPS.
- Entity load/fetch counts.
- Cache evictions và memory usage.
- p95/p99 latency theo endpoint.
- Tỷ lệ errors, stale read incidents, optimistic conflicts.

### 29.1. Hit rate được tính trên phạm vi xác định

Một cách tính:

\[
\mathrm{hitRate} =
\frac{\mathrm{hits}}
{\mathrm{hits}+\mathrm{misses}}
\times 100\%
\]

Nếu 900 hits và 100 misses trong cùng vùng quan sát, hit rate là 90%.

Nhưng:

- Hit rate cao không bảo đảm đúng dữ liệu.
- Tỷ lệ này chỉ có ý nghĩa khi biết đang đo L2 hay query cache, trên region/time window nào.
- Miss của một tập keys lớn ít được dùng có thể bình thường.
- Cache hiệu quả cũng phụ thuộc chi phí xử lý một miss.

### 29.2. Một cache hit có thể tiết kiệm ít hoặc nhiều

Tránh một `SELECT id WHERE pk=?` nhanh có thể ít giá trị hơn tránh một query aggregate đắt đỏ. Nhưng query cache lại có invalidation chi phí cao khi dữ liệu cập nhật liên tục.

Cần đánh giá **net benefit** trên workload thật, không chỉ số hit tuyệt đối.

---

## 30. Test dưới tải và cold-start

Một test tích hợp đơn lẻ chưa mô tả toàn bộ hoạt động khi ứng dụng có nhiều instances và nhiều threads.

Các bài kiểm tra bổ sung:

- Cold start: tất cả cache regions mới rỗng.
- Warm traffic: tập keys phổ biến đã nằm trong cache.
- Cache churn: many unique keys, hit ratio thấp.
- Burst reads một key: tránh cache stampede nếu architecture yêu cầu.
- Frequent writes: invalidation và read-after-write.
- Cache provider restart: correctness khi cache empty.
- Multiple app nodes: consistency policy giữa các instances.
- Rolling deploy: version/schema change và cache entry compatibility.

**Không chạy load test nặng trên production thiếu kế hoạch**. Dùng môi trường có datasets đại diện, kiểm soát traffic và thu thập metrics tương ứng.

### 30.1. Những rủi ro của distributed cache

Khi shared cache nằm ngoài JVM, có thêm:

- Network latency.
- Serialization formats và class/schema version.
- Cross-node invalidation.
- TTL.
- Cache provider availability.
- Clock/expiration semantics.
- Failure modes khi cache node mất kết nối.

Các rủi ro này không xuất hiện đầy đủ trong test L1 đơn giản.

---

## 31. Bảo mật instrumentation và cache

SQL binding/logging có thể lộ dữ liệu cá nhân và thông tin nghiệp vụ.

Ví dụ Hibernate 6:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Chỉ bật TRACE trong test/dev được kiểm soát. Khi dùng production observability:

- Không log raw passwords/tokens/payment details.
- Redact parameters và tenant identifiers khi cần.
- Giới hạn retention và access permissions.
- Tách metrics tổng hợp khỏi raw SQL logs.
- Không expose endpoints xóa cache ra Internet.
- Không để testcase evictAll chạy trên shared production cache.
- Không cache dữ liệu nhạy cảm ngoài vùng chính sách bảo mật cho phép.

Một hệ thống cache nhanh nhưng lộ dữ liệu xuyên tenant/user là không đạt yêu cầu correctness và security.

---

## 32. Bài tập thực hành có lời giải

### Bài 1. Hai lần find cùng EM

~~~java
InventoryItem a = em.find(InventoryItem.class, id);
InventoryItem b = em.find(InventoryItem.class, id);
~~~

**Đáp án:** `a == b` theo L1 identity map trong context. Nếu không thấy SELECT thứ hai, chưa thể kết luận L2 đã hit.

### Bài 2. Hai EM, cùng ID

**Đáp án:** Hai managed Java instances độc lập. Nếu EM thứ hai tránh SELECT, shared L2 có thể là nguyên nhân, cần kiểm tra config/counters/SQL.

### Bài 3. Gọi em.clear rồi em.find

**Đáp án:** L1 bị clear, nhưng L2 có thể warm. Không đảm bảo find mới sẽ chạy SELECT database.

### Bài 4. Gọi emf.getCache().evict

**Đáp án:** Evict L2, không detach managed entity hiện có trong một EM đang mở.

### Bài 5. Statistics.clear

**Đáp án:** Reset Hibernate counters, **không xóa cache entries**. Không coi đây là cold-cache setup.

### Bài 6. PreparedStatementCount = 3

**Đáp án:** Không nhất thiết có 3 SELECT. Có thể gồm INSERT/UPDATE và các JDBC statements khác. Cần phân loại SQL.

### Bài 7. Query-cache hit tăng 1 nhưng SELECT vẫn chạy

**Đáp án:** Có thể thiếu entity state trong L2 hoặc phát secondary queries. Xem L2 misses và SQL text; không đồng nhất query cache hit với zero SQL.

### Bài 8. JPQL query chạy hai lần, list giống nhau

**Đáp án:** Kết quả giống nhau không chứng minh cache. Kiểm tra query-cache hit/miss, SQL executions và query key.

### Bài 9. Thay parameter min

**Đáp án:** `min=10` và `min=11` thường là hai cache keys khác nhau. Không kỳ vọng hit từ một query key khác.

### Bài 10. @Cacheable mà không có provider

**Đáp án:** Annotation không tự cài L2 backend. Cần shared cache configuration, region factory và dependencies phù hợp.

### Bài 11. L2 hit tăng nhưng dữ liệu quantity sai

**Đáp án:** Test thất bại về correctness. Cache hit cao không bù được stale/incorrect data.

### Bài 12. Context A giữ quantity cũ sau B commit

**Đáp án:** L1 A có thể giữ managed state cũ; không tự kết luận shared L2 invalidation lỗi. Kiểm tra bằng context mới hoặc refresh theo contract.

### Bài 13. Bulk UPDATE xong find lại cùng EM

**Đáp án:** Managed instance có thể vẫn cũ. Cần chiến lược refresh/clear và version/invalidation.

### Bài 14. COUNT statements khi fixture còn trong vùng đo

**Đáp án:** INSERT/flush sẽ làm nhiễu count. Commit/đóng fixture trước và reset observer sau setup.

### Bài 15. Test query cache có @Transactional bao toàn method

**Đáp án:** Có thể chỉ kiểm tra L1 cùng transaction. Muốn cross-context cache, tạo transaction/context riêng cho mỗi lần gọi.

### Bài 16. Cache cold nhưng test có zero SELECT

**Đáp án:** Có thể L2/query cache chưa thực sự cold, dùng lại EM, observer sai scope hoặc database query không được đo. Xác định từng tầng.

### Bài 17. Tăng số orders từ 10 lên 100, SELECT tăng mạnh

**Đáp án:** Có thể N+1 lazy loading. Cache warm có thể che, cần test cold và sửa fetch plan nếu cần.

### Bài 18. Một SELECT nhưng 100.000 rows

**Đáp án:** Số SQL ít không tự đồng nghĩa nhanh; cần đo rows, network, memory và latency.

### Bài 19. Tenant A thấy entity B sau cache hit

**Đáp án:** Lỗi correctness/security nghiêm trọng. Kiểm tra tenant scope của query/cache key và authorization, không ưu tiên tăng hit rate.

### Bài 20. Đo Hibernate Statistics trong tests parallel

**Đáp án:** Counters scope SessionFactory có thể bị nhiễu. Cần isolate factory/tests hoặc per-request JDBC instrumentation.

### Bài 21. CacheRetrieveMode.BYPASS trong cùng EM có entity managed

**Đáp án:** Không phải phép đo hợp lệ để chứng minh bypass L2, vì L1 có thể phục vụ entity.

### Bài 22. External JDBC update sau khi L2 warm

**Đáp án:** Provider có thể không biết để invalidated cache; phải thiết kế TTL/evict/refresh và test read-after-write phù hợp.

### Bài 23. Tốc độ lần hai nhanh hơn lần đầu

**Đáp án:** Có thể do JIT, connection pool, DB buffer cache, query plan hoặc L2. Cần đếm SQL/cache counters và benchmark có warm-up.

### Bài 24. Test query cache update invalidation

**Đáp án:** Warm query `quantity>=10`, commit update đưa một row mới vào tập kết quả, query lại và assert chính xác IDs. Nếu dữ liệu cũ, invalidation chưa đáp ứng contract.

---

## 33. Checklist trước khi kết luận cache hoạt động

1. Đã xác định đang test L1, L2 hay query cache?
2. Cache provider/region backend thực sự được bật chưa?
3. Entity hoặc query có eligible/cacheable không?
4. Fixture đã commit trước phép đo chưa?
5. Test có dùng EntityManager mới đúng chỗ không?
6. L1/L2/query-cache state được thiết lập rõ là cold hay warm?
7. `Statistics.clear()` có bị hiểu nhầm là evict cache không?
8. SQL observer đếm prepared statements hay JDBC executions?
9. Có phân biệt SELECT với INSERT/UPDATE/DELETE không?
10. Có background requests/tests làm nhiễu counters không?
11. Có assert entity ID, quantity, version không?
12. Có assert đủ tập IDs và thứ tự nếu query yêu cầu không?
13. Hai contexts có trả managed instances riêng không?
14. L2 hit/miss/put counters có được quan sát cùng SQL không?
15. Query cache hit có được kiểm tra với cùng query key không?
16. Có test entity state khi query cache hit nhưng L2 miss không?
17. Có kiểm tra stale data sau commit không?
18. Có kiểm tra bulk/native/external updates không?
19. Có xác định database isolation và transaction boundaries không?
20. Có so cold và warm fetch plan để phát hiện N+1 không?
21. Có đo số rows, latency và memory nếu performance quan trọng không?
22. Cache key/tenant authorization có đúng không?
23. Logs/bind parameters có bảo vệ dữ liệu nhạy cảm không?
24. Test có đang chạy trên database/provider mục tiêu không?
25. Kết luận có ghi rõ config, fixture, counters và giới hạn không?

---

## 34. Kết luận

**Kiểm chứng cache bằng kết quả và số truy vấn thực tế** là một bài toán đo lường có kiểm soát, không phải bài toán “bật annotation rồi thấy ứng dụng nhanh hơn”.

~~~text
       Test fixture đã commit
                |
                v
      Thiết lập cache state
       cold / warm / evicted
                |
                v
      Mở đúng context scope
                |
                v
        Chạy use case thật
                |
                +--------------------+
                |                    |
                v                    v
       Assert dữ liệu đúng     Quan sát SQL/JDBC
       ID, state, version      SELECT, DML, rows
       tenant, query set       L2 hit/miss, query hit
                |                    |
                +---------+----------+
                          |
                          v
              Kết luận cache có
              đúng và có lợi không
~~~

Những điểm cốt lõi:

- **L1** được chứng minh qua entity identity trong **một persistence context**; nó không phải L2.
- **L2** cần kiểm tra qua **hai contexts độc lập**, L2 hit/miss và SQL thực tế, sau khi đã cô lập cache region.
- **Query cache** khác L2 entity cache; một query-cache hit không bảo đảm zero SQL khi entity state chưa có sẵn.
- **Kết quả đúng luôn là điều kiện bắt buộc**, đặc biệt sau update, external SQL và trong hệ thống nhiều tenant.
- **Số lần gọi Java, prepare-statement count và JDBC SELECT count không đồng nhất**; dùng công cụ phù hợp với điều muốn chứng minh.
- **Fixture, cache state, statistics và transaction boundary phải được cô lập**, nếu không các số đo dễ xanh giả.
- **Cache warm có thể che N+1 và vấn đề query plan**; kiểm tra cold/warm cùng rows và latency.
- **Không sử dụng cache metrics làm bằng chứng duy nhất** nếu chưa quan sát dữ liệu và SQL.

**Một cache được kiểm chứng tốt là cache trả đúng dữ liệu theo hợp đồng nhất quán và quyền truy cập, đồng thời có bằng chứng đo được rằng nó thực sự giảm công việc không cần thiết của database trên workload mục tiêu.**
