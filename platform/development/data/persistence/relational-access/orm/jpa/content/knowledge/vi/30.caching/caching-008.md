# Phân biệt cache entity và cache kết quả truy vấn

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Bộ nhớ đệm

Trong hệ thống dùng JPA, nhiều lập trình viên nói “đã bật cache” nhưng vẫn thấy câu JPQL được thực thi, hoặc ngược lại: một câu truy vấn được cache nhưng ứng dụng vẫn phải gửi SQL để tải từng entity. Những hiện tượng đó không nhất thiết là lỗi. Chúng xuất phát từ việc **cache dữ liệu của entity** và **cache kết quả của truy vấn** là hai cơ chế khác nhau.

- **Cache entity** thường gắn với khóa định danh: “Với entity loại `Product` và ID `42`, có state nào đã được lưu trong cache để tái tạo entity không?”
- **Cache kết quả truy vấn** gắn với mô tả truy vấn và tham số: “Với câu truy vấn Products đang bán, giá tối thiểu `100`, sort theo `price` và giới hạn 20 dòng, tập kết quả nào đã được tính trước?”
- **Persistence context / first-level cache** lại là một tầng khác: các managed entities đã được nạp vào **EntityManager hiện tại**, bảo đảm identity và làm nền cho dirty checking.
- **Cache kế hoạch truy vấn** (*query plan cache*) chỉ giữ phần phân tích/biên dịch kế hoạch thực thi hoặc metadata, **không có nghĩa giữ các hàng kết quả**.

Vì vậy, cần phân biệt **ba lớp dữ liệu trong ORM** và cả cache khác tầng (Spring method cache, HTTP cache, database buffer/result cache). Khi thiết kế hoặc debug, câu hỏi đúng không phải “Cache có bật chưa?” mà là **loại cache nào, key là gì, dữ liệu gì được lưu, phạm vi là gì, khi nào bị vô hiệu và đo hit/miss bằng cách nào?**

Bài này tập trung vào chuẩn **Jakarta Persistence (JPA)**, chỉ rõ phần nào là JPA portable và phần nào thường thuộc **Hibernate ORM/provider-specific**. Ví dụ sử dụng `jakarta.persistence.*`. Nếu dự án dùng JPA cũ với `javax.persistence.*`, tên package và hint prefix tương ứng khác nhau.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích sự khác biệt giữa **first-level cache**, **second-level entity cache** và **query result cache**.
2. Phân biệt cache entity theo `(entity type, primary key)` với cache kết quả theo `(query, parameters, pagination, filters, ...)`.
3. Biết vì sao một `EntityManager` có thể trả cùng Java object instance mà không phải chạy SQL.
4. Hiểu vai trò của `EntityManagerFactory` và `Cache` trong shared entity cache chuẩn JPA.
5. Dùng `@Cacheable`, `SharedCacheMode`, `CacheRetrieveMode` và `CacheStoreMode` đúng phạm vi.
6. Hiểu chuẩn JPA **không định nghĩa API cấu hình query result cache chung** tương đương các cơ chế query cache của Hibernate.
7. Phân biệt `@Cacheable` của Jakarta Persistence với `@Cacheable` của Spring Cache.
8. Hiểu vì sao có L2 entity cache vẫn phải chạy JPQL SQL khi query result chưa được cache.
9. Hiểu vì sao trúng query cache vẫn có thể phát SELECT tải entity nếu entity state chưa sẵn có trong L1/L2.
10. Giải thích invalidation khi thêm/sửa/xóa entity, thay đổi membership của kết quả lọc và updates ngoài ORM.
11. Phân biệt xóa entity khỏi L1, evict L2 và evict query cache.
12. Hiểu cache mode hints và giới hạn của `refresh()`, `clear()`, `evict()`.
13. Phân tích ảnh hưởng cache tới dữ liệu nhạy cảm, tenant isolation, consistency và transaction.
14. Biết khi nào **nên** cache query thường lặp, khi nào không nên cache truy vấn có tham số đa dạng hoặc dữ liệu thay đổi liên tục.
15. Dùng logging và thống kê Hibernate để đo entity hits/misses và query cache hits/misses riêng.
16. Thiết kế thí nghiệm cold/warm caches với EntityManager mới để tránh kết luận sai.
17. Nhận biết tác động của collection caching, lazy association và N+1.
18. Thiết kế chiến lược invalidation/TTL phù hợp với SLA về độ mới dữ liệu.

## 2. Bản đồ các lớp cache

```text
                           APPLICATION
                                |
                                v
                   EntityManager / Session
                  +------------------------+
                  | FIRST-LEVEL CACHE (L1) |
                  | managed entities       |
                  | scoped to context      |
                  +------------------------+
                                |
                     JPA operation / JPQL
                                |
              +-----------------+------------------+
              |                                    |
              v                                    v
    SHARED ENTITY CACHE (L2)              QUERY RESULT CACHE
    theo (type, primary key)              theo query + params + ...
    entity state                          IDs/scalars/tuples tùy provider
              |                                    |
              +-----------------+------------------+
                                |
                                v
                  SQL / DATABASE ENGINE
                     tables and indexes
                                |
                      DB buffer / plan cache
```

Sơ đồ đơn giản hóa: thứ tự truy cập cache không phải lúc nào cũng là một đường đi duy nhất. Ví dụ, khi thực thi JPQL mà **không có query result cache**, provider có thể vẫn gửi SQL xác định các rows phù hợp rồi materialize entity states từ L1/L2 tùy kế hoạch. Khi query cache trả IDs, việc lấy các entity theo ID có thể đi qua L1/L2 hoặc database. Vì vậy không hình dung query cache như “nằm phía trên L2 và thay thế mọi thứ”.

### 2.1. Bảng so sánh nhanh

| Khía cạnh | L1 persistence context | L2 entity cache | Query result cache |
|---|---|---|---|
| Mức hỗ trợ | Cốt lõi JPA | Chuẩn JPA có shared cache API/modes; triển khai tùy provider | Không có API query-result-cache portable chung trong JPA |
| Phạm vi | Một persistence context / EntityManager | Thường chia sẻ giữa các EntityManagers thuộc cùng EntityManagerFactory / cache region | Theo provider/cache regions và lifetime cấu hình |
| Key logic | Entity identity | Entity type + primary key, có thể kèm tenant/region | Query + parameters + pagination + filters/sort/tenant/context |
| Nội dung | Managed instances, trạng thái theo dõi | State cần tái tạo entity, không phải Java managed instance dùng chung | Tập ID, scalar/tuple/projection result, metadata tùy provider |
| Bật mặc định? | Luôn có trong JPA entity management | Phụ thuộc provider, cấu hình và SharedCacheMode | Thường opt-in, phụ thuộc provider |
| Có thay JPQL SELECT trên DB? | Không bảo đảm | **Không tự động** | Có thể, nếu query eligible và cache hit |
| Có giúp `find` theo ID? | Có | Có, nếu enabled và hit | Không phải mục tiêu chính |
| Có dirty checking? | Có | Không | Không |
| Bị xóa bằng `em.clear()`? | Có, detach managed entities | Không | Không |
| Bị xóa bằng `emf.getCache().evict(...)`? | Không tự xóa L1 đang managed | Có theo API JPA | Không mặc nhiên |
| Nguy cơ stale | Context sống lâu | Invalidation/TTL/provider/out-of-band writes | Dependency invalidation/TTL/external writers |

**Ý trọng tâm:** cùng gọi là “cache” nhưng dữ liệu, key, phạm vi và cách vô hiệu của chúng khác nhau.

---

## 3. First-level cache: điểm nền cần hiểu trước

Mỗi `EntityManager` quản lý một **persistence context**: tập các entity instances có identity và lifecycle riêng.

Ví dụ:

```java
EntityManager em = emf.createEntityManager();

try {
    Product first = em.find(Product.class, 42L);
    Product second = em.find(Product.class, 42L);

    System.out.println(first == second); // true khi cùng managed identity
} finally {
    em.close();
}
```

Với entity cùng type/ID đang managed trong một persistence context, JPA đảm bảo identity ở mức Java object: `first` và `second` đại diện cùng managed entity instance. Lần `find` thứ hai thường được giải quyết từ persistence context mà không cần SELECT riêng.

### 3.1. L1 không phải một cache tùy chọn để bật/tắt

Persistence context là thành phần nền tảng của JPA, không phải tính năng chỉ có khi thiết lập Hibernate L2. Nếu cấu hình không dùng L2 và không dùng query cache, **L1 vẫn tồn tại**.

### 3.2. L1 giữ object có trạng thái managed

L1 chứa managed entity state, phục vụ:

- Identity map.
- Change tracking / dirty checking.
- Quan hệ trong object graph.
- Merge, persist, remove và flush.
- Đồng bộ unit of work với transaction.

Một entity ở L1 có thể đã thay đổi trong Java mà chưa flush/commit. Không nên coi dữ liệu L1 luôn trùng ngay lập tức với giá trị committed trong database.

### 3.3. L1 tồn tại theo persistence context, không phải theo một SQL

Trong transaction-scoped context, lifecycle thường gắn với transaction của container/framework. Với application-managed EntityManager, context có thể sống đến `close()`, có thể trải qua nhiều transaction tùy mô hình sử dụng.

Vì vậy, “L1 chỉ tồn tại đúng một transaction trong mọi cách dùng JPA” là phát biểu quá mạnh.

### 3.4. Không share EntityManager giữa threads

EntityManager không phải đối tượng thread-safe để nhiều threads thao tác đồng thời. L1 không phải distributed cache hay cache chia sẻ cho toàn bộ request threads.

---

## 4. Second-level cache: entity state được chia sẻ

**Second-level cache (L2)** được gọi là cache cấp hai vì nằm bên ngoài một persistence context đơn lẻ, thường gắn với `EntityManagerFactory`/`SessionFactory` và cache region của provider.

Ví dụ:

```text
EntityManager A              EntityManager B
      |                            |
   L1 của A                     L1 của B
      |                            |
      +-----------+----------------+
                  |
                  v
        L2: Product#42 -> cached state
                  |
                  v
               DATABASE
```

Nếu Product#42 không có trong L1 của B nhưng có trong L2 và đủ điều kiện sử dụng cache, provider có thể tái tạo một managed Product instance mới **trong B** mà không cần SELECT cho cùng entity state.

### 4.1. L2 không lưu cùng Java object instance để mọi EM cùng sửa

```java
EntityManager a = emf.createEntityManager();
EntityManager b = emf.createEntityManager();

try {
    Product pA = a.find(Product.class, 42L);
    Product pB = b.find(Product.class, 42L);

    System.out.println(pA == pB);
} finally {
    a.close();
    b.close();
}
```

Hai persistence contexts riêng **không yêu cầu** trả cùng Java object instance. Thông thường chúng là các managed instances riêng biệt; `pA == pB` không phải tiêu chí xác định một L2 cache hit.

L2 chia sẻ **data/state** để tái tạo instances, không phải chia sẻ một entity Java object managed giữa mọi EntityManager.

### 4.2. L2 key theo entity identity

Khái niệm:

```text
Entity cache key:
  entityName = demo.domain.Product
  primaryKey = 42
  tenantId   = tenant-1 (nếu multi-tenancy scheme yêu cầu)
  region     = productRegion (provider-defined)
```

Cách mã hóa key cụ thể là chi tiết của provider/cache implementation. Nhưng nguyên tắc là **truy cập theo định danh entity**, không phải theo câu JPQL tìm kiếm.

### 4.3. L2 và query result khác nhau ngay từ câu hỏi

```text
L2 hỏi:
  Product#42 có cached state không?

Query cache hỏi:
  SELECT p WHERE p.active=true ORDER BY price
  với filter params X, Y có cached result không?
```

L2 không tự biết “những Product nào có active=true” chỉ vì đã cache nhiều Products.

---

## 5. Query result cache: cache câu hỏi và câu trả lời

Một truy vấn:

```jpql
SELECT p
FROM Product p
WHERE p.active = true
  AND p.category = :category
ORDER BY p.price ASC, p.id ASC
```

với `category = "BOOK"` có thể tạo kết quả:

```text
[Product#12, Product#19, Product#42]
```

**Query result cache** có thể lưu một biểu diễn của **tập kết quả tương ứng với truy vấn và tham số**.

Key logic thường bao gồm:

```text
query:
  SELECT p ... WHERE active=true AND category=:category
bindings:
  category="BOOK"
pagination:
  offset=0, maxResults=20
sort/filter context:
  ORDER BY price ASC,id ASC
tenant/security context:
  tenant-1, filters applied
```

Kết quả có thể là entity IDs, scalar values, tuples hoặc một dạng nội bộ khác tùy query và provider/version.

### 5.1. Query cache không phải query plan cache

Hai khái niệm:

- **Query plan cache:** lưu cây phân tích, plan/AST, mapping/parameter metadata để giảm chi phí phân tích/biên dịch.
- **Query result cache:** lưu kết quả dữ liệu đã tính của một query với các bind values cụ thể để có thể tránh thực thi lại SQL tương ứng nếu còn hợp lệ.

Khi thấy Hibernate nói “query plan cache hit”, **không được kết luận SQL SELECT data đã được bỏ qua**.

### 5.2. Query cache không phải “cache tất cả câu JPQL tự động”

Trong Hibernate ORM, query result caching là chức năng cần được **cấu hình/bật** và thường cần **đánh dấu từng truy vấn cacheable**. Bật second-level cache không tự biến mọi JPQL query thành cacheable query.

### 5.3. Query cache không thể bất biến khi bảng thay đổi

Nếu một Product mới được thêm vào category BOOK, kết quả `WHERE active=true AND category='BOOK'` có thể phải thay đổi. Query cache cần invalidation/revalidation hợp lý; nếu không, nó trả thiếu hoặc thừa IDs/scalars.

---

## 6. Ba lượt truy vấn quan trọng để phân biệt

Giả sử Product#42 đã tồn tại trong database, và ta dùng Hibernate với cấu hình L2/query cache có hiệu lực.

### 6.1. Lượt A — `find` trong cùng EntityManager

```java
Product p1 = em.find(Product.class, 42L);
Product p2 = em.find(Product.class, 42L);
```

Dự đoán cần kiểm tra:

- Lần đầu có thể nạp từ DB/L2.
- Lần hai dùng L1 nếu entity còn managed.
- Không thể dùng kết quả này để chứng minh **L2** đã hit vì chỉ một persistence context.

### 6.2. Lượt B — `find` ở EntityManager mới

```java
EntityManager em1 = emf.createEntityManager();
Product p1 = em1.find(Product.class, 42L);
em1.close();

EntityManager em2 = emf.createEntityManager();
Product p2 = em2.find(Product.class, 42L);
em2.close();
```

Nếu Product thuộc L2 cache, entry đã được put và chưa stale/evicted, lần `find` ở EM2 **có thể** là L2 hit. Đây là phép thử phù hợp hơn cho entity cache.

### 6.3. Lượt C — Chạy cùng JPQL ở hai EntityManagers mới

```java
List<Product> first = queryBooks(em1);
List<Product> second = queryBooks(em2);
```

Nếu chỉ bật L2 mà **không bật query result cache**, query JPQL xác định tập Products thỏa predicate thường **vẫn cần SQL**, dù một số entity states đã được cache.

Nếu bật query cache và query được đánh dấu cacheable, lượt thứ hai có thể hit query cache và bỏ được SQL truy vấn tập kết quả — nhưng nó vẫn có thể cần SQL tải entity IDs thiếu trong L1/L2.

---

## 7. Bảng bốn tình huống cache entity và query cache

| L2 entity cache | Query result cache | Trường hợp JPQL trả entity |
|---|---|---|
| Tắt | Tắt | Query thực thi SQL; entity materialize từ DB/persistence context |
| Bật, query cache tắt | Tắt | JPQL thường vẫn thực thi SQL tìm tập kết quả; có thể tận dụng L2 tùy cách materialize |
| Tắt hoặc L2 miss | Bật, query result hit | Có thể bỏ SQL tìm IDs/tuples nhưng vẫn cần SELECT entity state bị thiếu |
| Bật, query cache hit | Bật | Có thể tránh cả SQL query result và nhiều SQL entity loads nếu mọi cache entry còn hợp lệ |

Bảng diễn tả **khả năng**, không phải một cam kết provider-independent về số SELECT. Hành vi materialization, cache eligibility, fetch plan và consistency strategy phụ thuộc provider/version.

### 7.1. Câu hỏi chẩn đoán

Nếu query cache hit nhưng SQL vẫn chạy, hỏi:

- Query cache có đang lưu entity IDs?
- Những entity IDs đó có trong L1/L2 chưa?
- Có association LAZY được truy cập khi map DTO không?
- Có cache region/collection bị miss không?
- Query có fetch graph khác kỳ vọng không?
- Có SQL khác (sequence, flush, lazy load) mà bạn nhầm là SQL query gốc không?

Nếu L2 hits tăng nhưng SQL JPQL vẫn chạy, hỏi:

- Query đã được đánh dấu cacheable chưa?
- Query cache globally enabled chưa?
- Có quá nhiều query keys khác nhau khiến query cache miss?
- Query bị invalidate do cập nhật tables liên quan?
- Có dữ liệu bị đổi bởi bulk SQL/ngoài provider không?

---

## 8. Entity mẫu dùng xuyên suốt

Ta có danh mục sản phẩm và đơn hàng.

```text
Category (1) -------- (N) Product
                              |
                              +-- id
                              +-- sku
                              +-- name
                              +-- price
                              +-- active
                              +-- updatedAt
                              +-- version
                              +-- category
```

### 8.1. Category

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "categories")
public class Category {

    @Id
    private Long id;

    @Column(nullable = false, unique = true, length = 80)
    private String code;

    @Column(nullable = false, length = 150)
    private String name;

    protected Category() {}

    public Long getId() { return id; }

    public String getCode() { return code; }

    public String getName() { return name; }
}
```

### 8.2. Product

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {

    @Id
    private Long id;

    @Column(nullable = false, unique = true, length = 80)
    private String sku;

    @Column(nullable = false, length = 180)
    private String name;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    private Long version;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "category_id", nullable = false)
    private Category category;

    protected Product() {}

    public Long getId() { return id; }

    public String getSku() { return sku; }

    public String getName() { return name; }

    public BigDecimal getPrice() { return price; }

    public boolean isActive() { return active; }

    public Instant getUpdatedAt() { return updatedAt; }

    public Long getVersion() { return version; }

    public Category getCategory() { return category; }

    public void changePrice(BigDecimal next, Instant now) {
        Objects.requireNonNull(next);
        Objects.requireNonNull(now);

        if (next.signum() < 0) {
            throw new IllegalArgumentException("Price must be >= 0");
        }

        price = next;
        updatedAt = now;
    }

    public void deactivate(Instant now) {
        active = false;
        updatedAt = Objects.requireNonNull(now);
    }
}
```

`@ManyToOne(fetch=LAZY)` trong ví dụ là một hint trì hoãn theo JPA, không bảo đảm provider không fetch Category ngay. Nó cũng **không tự bật cache cho Category**.

### 8.3. DDL minh họa

```sql
CREATE TABLE categories (
    id BIGINT PRIMARY KEY,
    code VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL
);

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(180) NOT NULL,
    price DECIMAL(19,2) NOT NULL,
    active BOOLEAN NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    version BIGINT,
    category_id BIGINT NOT NULL,
    CONSTRAINT fk_product_category
      FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE INDEX idx_products_category_active_price_id
  ON products(category_id, active, price, id);
```

DDL là minh họa; cú pháp boolean/timestamp/index và mapping `Instant` tùy DBMS/JDBC provider. Chưa cấu hình cache ở mức SQL/schema: các cache ORM thuộc lớp Java/provider.

---

## 9. Chuẩn JPA cung cấp gì cho shared entity cache?

JPA có các thành phần:

- `jakarta.persistence.Cacheable`.
- `jakarta.persistence.SharedCacheMode`.
- `jakarta.persistence.CacheRetrieveMode`.
- `jakarta.persistence.CacheStoreMode`.
- `jakarta.persistence.Cache`.
- `EntityManagerFactory.getCache()`.
- Các hints `jakarta.persistence.cache.retrieveMode` và `jakarta.persistence.cache.storeMode`.

Chúng dành cho **shared entity cache/state**, không phải API chung để đánh dấu một JPQL query result cacheable.

### 9.1. @Cacheable của Jakarta Persistence

```java
import jakarta.persistence.Cacheable;

@Entity
@Cacheable(true)
public class Product {
    // ...
}
```

`@Cacheable(true)` đánh dấu entity phù hợp cho shared cache **theo SharedCacheMode và provider configuration**. Nó không thay thế cấu hình cache provider/region cụ thể, cũng không có nghĩa mọi phép truy vấn trả Product đều được cache result.

### 9.2. SharedCacheMode

| Mode | Ý nghĩa |
|---|---|
| `ALL` | Các entities được chia sẻ cache |
| `NONE` | Không dùng shared cache cho entities |
| `ENABLE_SELECTIVE` | Cache những entities được chọn bằng `@Cacheable(true)` |
| `DISABLE_SELECTIVE` | Cache đa số entities trừ những entities được đánh dấu `@Cacheable(false)` |
| `UNSPECIFIED` | Provider quyết định behavior theo cấu hình mặc định |

Đây là **policy ở persistence unit**, không phải một query result cache setting.

### 9.3. Ví dụ persistence.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
  <persistence-unit name="shopPU"
                    transaction-type="RESOURCE_LOCAL">

    <class>demo.domain.Category</class>
    <class>demo.domain.Product</class>

    <shared-cache-mode>ENABLE_SELECTIVE</shared-cache-mode>

    <!-- JDBC/provider/cache region settings được cấu hình
         riêng theo môi trường, không tự suy từ JPA annotation. -->
  </persistence-unit>
</persistence>
```

Dùng namespace/version đúng với Jakarta Persistence của dự án. Ví dụ không tự tạo một cache provider; nó mô tả lựa chọn entities eligible.

### 9.4. Cần có implementation thực sự

Shared cache API là một phần chuẩn, nhưng việc hỗ trợ/kích hoạt và cách cấu hình region/storage khác giữa providers. Không suy “thêm `@Cacheable` rồi mọi `find` EM khác sẽ cache hit” nếu provider chưa có region factory/adapter được cấu hình.

---

## 10. CacheRetrieveMode và CacheStoreMode

JPA cung cấp hints để hướng dẫn việc **đọc từ** và **ghi vào** shared cache:

```java
import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.CacheStoreMode;

Map<String, Object> hints = new HashMap<>();

hints.put(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);

hints.put(
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.BYPASS
);

Product product = em.find(Product.class, 42L, hints);
```

Imports:

```java
import java.util.Map;
import java.util.HashMap;
```

### 10.1. CacheRetrieveMode

| Mode | Ý định |
|---|---|
| `USE` | Cho phép lấy state từ shared cache theo cơ chế provider |
| `BYPASS` | Bỏ qua shared cache khi retrieve trong phạm vi hint |

### 10.2. CacheStoreMode

| Mode | Ý định |
|---|---|
| `USE` | Cho phép đưa state nạp được vào shared cache |
| `BYPASS` | Không lưu vào shared cache theo hint |
| `REFRESH` | Buộc lấy state mới phù hợp và làm mới dữ liệu shared cache theo semantics/provider |

### 10.3. Bypass L2 không xóa entity đã managed trong L1

Điểm quan trọng:

```java
Product a = em.find(Product.class, 42L);

// Cùng EntityManager: Product#42 đã managed.
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);

Product b = em.find(Product.class, 42L, hints);
```

Không được coi `BYPASS` là bảo đảm `b` sẽ query lại database khi `Product#42` đã nằm trong **L1**. Hint nhắm tới **shared cache**, còn persistence context vẫn ưu tiên identity managed. Muốn quan sát DB state mới, hãy thiết kế `refresh` hoặc dùng context mới cùng transaction/isolation phù hợp.

### 10.4. Cache hints không phải “đọc bất chấp isolation”

Dù bypass L2, SQL vẫn chịu transaction isolation, MVCC, replica routing và database constraints. BYPASS không cam kết đọc “giá trị mới nhất trên toàn thế giới” trong một transaction đang nhìn snapshot cũ.

---

## 11. JPA Cache API: kiểm tra và evict entity state

```java
import jakarta.persistence.Cache;

Cache cache = emf.getCache();

boolean present = cache.contains(Product.class, 42L);

cache.evict(Product.class, 42L);

cache.evict(Product.class);

cache.evictAll();
```

Ý nghĩa:

- `contains(Product.class, 42L)`: hỏi provider shared cache có state cho entity identity đó hay không theo API.
- `evict(Product.class, 42L)`: loại một entry entity.
- `evict(Product.class)`: loại các entries thuộc entity type.
- `evictAll()`: yêu cầu loại cached entities ở shared cache theo API.

### 11.1. Điều `Cache.evict()` không làm

Nó không tự:

- Detach Product#42 đã managed trong mọi EntityManager đang mở.
- Xóa database row.
- Undo pending changes trong transaction.
- Đảm bảo query result cache regions được xóa.
- Thay đổi dữ liệu trên các cache tiers khác như Spring Cache hoặc HTTP cache.

### 11.2. Một thí nghiệm dễ gây kết luận sai

```java
Product p1 = em.find(Product.class, 42L);

emf.getCache().evict(Product.class, 42L);

Product p2 = em.find(Product.class, 42L);
```

Nếu `p1 == p2` và không có SQL ở lệnh cuối, nguyên nhân rất có thể là **L1** chứ không phải `evict` thất bại. Muốn đo L2 eviction, mở **EntityManager mới** sau evict.

### 11.3. Cache.contains không đồng nghĩa query result cache hit

`cache.contains(Product.class, 42L) == true` chỉ liên quan entity state của ID 42. Nó không nói truy vấn `WHERE active=true ORDER BY price` đã có cached result.

---

## 12. Cách xác định entity cache key và query cache key

### 12.1. Entity cache key

Thường gắn với identity:

```text
Product, ID=42
```

Nếu Product#42 có `price=125`, L2 entry giúp provider tái tạo Product#42 ở context khác. Thay query lọc giá không làm entity key trở thành “Product price >= 100”.

### 12.2. Query result cache key

Ví dụ:

```text
Query:
  SELECT p FROM Product p
  WHERE p.active=true AND p.price >= :minimum
  ORDER BY p.price ASC,p.id ASC

minimum=100
firstResult=0
maxResults=20
tenant=1
```

Query khác:

```text
minimum=200
```

thường là **một cache key khác**. Trang 2:

```text
firstResult=20
maxResults=20
```

cũng thường là key khác.

### 12.3. Giá trị của các tham số phải được đưa vào phân biệt

Nếu cache query không phân biệt `minimum=100` và `minimum=200`, nó sẽ trả sai dữ liệu. Provider chịu trách nhiệm xây key phù hợp với query parameters, filters, pagination, tenant context và các yếu tố liên quan đến kết quả.

### 12.4. Nhiều key không có nghĩa cache hiệu quả

Nếu mỗi request có một giá trị keyword/price/date range ngẫu nhiên, tỉ lệ lặp lại query key có thể rất thấp. Query cache phải giữ nhiều entries nhưng hiếm hit.

Đây là một trong những lý do **query result caching cần đánh giá workload**, không bật cho mọi tìm kiếm.

---

## 13. Đường đi của `find` khi L2 cache warm

Một ví dụ:

```text
EM1.find(Product#42)
  L1 miss
  L2 miss
  SELECT Product#42
  managed Product instance trong EM1
  put L2 tùy cache policy/lifecycle

EM1.close()

EM2.find(Product#42)
  L1 miss
  L2 hit
  managed Product instance mới trong EM2
  có thể không cần SELECT Product#42
```

### 13.1. Phải có EM mới để phân biệt L1/L2

Không dùng hai lần `find` trong cùng EM làm kết luận “L2 hit”.

### 13.2. Khi nào L2 không được dùng?

Một số nguyên nhân:

- Entity không eligible theo `SharedCacheMode`/`@Cacheable`.
- Provider cache chưa được bật/cấu hình đúng.
- Region có miss, expired, evicted.
- Cache retrieve mode BYPASS.
- Dữ liệu không được store theo policy.
- Provider xử lý special mapping/version/tenant context khác.
- Một entity có trạng thái hoặc loading path không đủ điều kiện cache.

### 13.3. L2 không bảo đảm toàn association graph được cache

Product#42 có Category LAZY. Việc cache Product#42 không nhất thiết cache Category#7 hoặc collections liên quan. Khi truy cập `product.getCategory().getName()` có thể cần một lần tải riêng.

---

## 14. Đường đi của JPQL khi chỉ bật L2

Giả sử:

```jpql
SELECT p
FROM Product p
WHERE p.active = true
ORDER BY p.price ASC, p.id ASC
```

Khi chỉ có L2:

```text
JPQL execution
    |
    v
SQL để xác định rows thỏa WHERE và ORDER BY
    |
    v
Materialize Product entities
    |
    +-- có thể tái sử dụng managed entities L1
    |
    +-- có thể tận dụng cached states L2 tùy provider
    |
    +-- có thể tải entity state từ SQL/DB
```

**L2 không tự lưu kết quả của mọi predicate.** Vì vậy việc query chạy SQL nhiều lần là bình thường dù L2 entity cache đang hoạt động.

### 14.1. Tại sao provider không thể chỉ quét L2 để trả danh sách?

L2 thường không chứa **tất cả** Products, có thể chỉ chứa những Products từng được tải. Không có bảo đảm rằng dữ liệu cache là tập đầy đủ để đánh giá `WHERE active=true` và sắp xếp. Database mới là nơi xác định tập kết quả theo query semantics, trừ khi có query result cache hoặc một cơ chế khác đã được provider xác định là hợp lệ.

### 14.2. Có cache entity không đồng nghĩa SQL SELECT = 0

Ví dụ test có 100 Products trong L2 mà JPQL query vẫn chạy SELECT để tìm 20 IDs đúng thứ tự. Đây không nhất thiết là bug cache.

---

## 15. Đường đi của JPQL khi query result cache hit

Một query result cache (Hibernate ví dụ) có thể giữ:

```text
Query key: active=true, category=BOOK, sort=price, page=0
Cached result: [Product#12, Product#19, Product#42]
```

Lượt sau:

```text
Query request
      |
      v
QUERY RESULT CACHE HIT
      |
      +-- Product#12: L1/L2 hit
      +-- Product#19: L1/L2 miss -> có thể SQL load
      +-- Product#42: L1/L2 hit
      |
      v
List<Product>
```

### 15.1. Query cache hit không mặc nhiên đồng nghĩa 0 SQL

Nếu cached query result chứa IDs và L2 không có entity state tương ứng, provider có thể cần SQL để fetch entities. Điều này đặc biệt quan trọng khi một query cache được bật nhưng entity cache bị tắt hoặc cache entries bị evicted.

### 15.2. Scalar/DTO queries có thể có cách lưu khác

Một query:

```jpql
SELECT p.id, p.name, p.price
FROM Product p
WHERE p.active = true
```

có thể được cache dưới dạng scalar tuples/row values tùy provider/version, không cần dựng entity managed như một `SELECT p`. **Không áp đặt** rằng mọi loại query cache của mọi Hibernate version chỉ lưu IDs; cách lưu cụ thể là chi tiết implementation.

### 15.3. Query cache hit vẫn có thể gây lazy SELECT

Dù query trả Products nhanh, code:

```java
for (Product p : products) {
    System.out.println(p.getCategory().getName());
}
```

có thể kích hoạt SELECT tải Category nếu chưa loaded. Query result cache không tự giải quyết N+1 của associations.

---

## 16. Chuẩn JPA không định nghĩa query result cache API chung

Điểm cần ghi rõ khi giảng dạy:

- `@Cacheable` trong `jakarta.persistence`: đánh dấu entity đối với **shared cache**.
- `EntityManagerFactory.getCache()`: API thao tác với **entity cache**.
- `SharedCacheMode`/retrieve/store modes: điều khiển **shared cache behavior**.
- Một query result cache có cách đánh dấu/đọc stats/evict regions **phụ thuộc provider**.

Không có annotation chuẩn JPA tương đương:

```java
// Minh họa ý tưởng, KHÔNG phải annotation chuẩn JPA:
@CacheThisJpaQueryResult
```

để áp cho mọi provider và tự tạo portable query result cache.

### 16.1. Hibernate ORM có query cache extension

Ví dụ Hibernate:

```java
TypedQuery<Product> query = em.createQuery(
    """
    SELECT p
    FROM Product p
    WHERE p.active = true
      AND p.category.code = :code
    ORDER BY p.price ASC, p.id ASC
    """,
    Product.class);

query.setParameter("code", "BOOK");

// Hibernate-specific (không portable Jakarta Persistence).
query.setHint("org.hibernate.cacheable", true);
```

Trên Hibernate, có thể dùng API/provider constants tương ứng với phiên bản để tránh phụ thuộc trực tiếp vào chuỗi hint. Với các provider khác, hint này có thể bị bỏ qua hoặc không được hỗ trợ.

### 16.2. Truy vấn nào cũng cacheable?

Không nên. Query cache thường được bật **có chọn lọc** cho queries lặp lại với cùng tham số, dữ liệu ít đổi và chi phí query đủ lớn để lợi ích vượt overhead của invalidation/cache storage.

---

## 17. Hibernate: cấu hình L2 và query cache

Một số property Hibernate thường thấy:

```properties
hibernate.cache.use_second_level_cache=true
hibernate.cache.use_query_cache=true
hibernate.generate_statistics=true
```

Đây là **Hibernate properties**, không phải các property chuẩn Jakarta Persistence.

### 17.1. Bật property chưa tạo một backend cache hoàn chỉnh

Để sử dụng L2 và query cache thực sự, Hibernate cần **region factory/cache provider** được cấu hình, ví dụ tích hợp JCache qua module phù hợp và implementation JCache tương thích.

Khái niệm cấu hình:

```properties
hibernate.cache.region.factory_class=jcache
```

Giá trị region factory, dependencies, JCache provider URI, cache definitions và cách cấu hình khác nhau theo Hibernate/Cache provider version. Không copy một cấu hình từ bài viết về Hibernate 5 vào dự án Hibernate 6/7 mà không kiểm tra compatibility.

### 17.2. Một setup tiêu biểu gồm

1. Chọn Hibernate ORM version.
2. Thêm module tích hợp cache tương thích (ví dụ `hibernate-jcache` khi dùng JCache).
3. Thêm implementation cache provider được hỗ trợ.
4. Cấu hình region factory/backend.
5. Xác định `SharedCacheMode`/entity eligibility.
6. Đặt concurrency/cache policies phù hợp.
7. Bật query cache chỉ khi cần.
8. Đánh dấu chính xác queries cacheable.
9. Cấu hình eviction/TTL/size cho regions.
10. Bật statistics khi đo và tắt/giảm overhead khi production policy yêu cầu.

### 17.3. Không dùng example properties như cam kết tương thích mọi bản

Tên/hỗ trợ chi tiết, region layouts và caching behavior đã thay đổi theo các thế hệ Hibernate. Hãy đối chiếu với dependencies thực tế của dự án. Bài này tập trung vào **phân biệt cơ chế**, không thay thế tài liệu version-specific.

---

## 18. Đánh dấu entity bằng @Cacheable và Hibernate @Cache

Với một dự án Hibernate sử dụng shared cache, entity có thể được khai báo:

```java
import jakarta.persistence.Cacheable;
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Cacheable
@Cache(usage = CacheConcurrencyStrategy.READ_WRITE,
       region = "catalog.products")
public class Product {
    // ...
}
```

### 18.1. Hai annotation khác nhau

- `jakarta.persistence.Cacheable`: portable entity cache eligibility.
- `org.hibernate.annotations.Cache`: chọn concurrency strategy và region theo Hibernate extension.

Không nhầm chúng với annotation:

```java
org.springframework.cache.annotation.Cacheable
```

của Spring Cache, dùng cho **method-level caching**.

### 18.2. Concurrency strategy quyết định trade-offs

Hibernate có các cache concurrency strategies như `READ_ONLY`, `READ_WRITE`, `NONSTRICT_READ_WRITE`, `TRANSACTIONAL` (mức hỗ trợ cụ thể phụ thuộc provider/backend và version).

| Strategy (Hibernate) | Ý tưởng tổng quát | Lưu ý |
|---|---|---|
| `READ_ONLY` | Dữ liệu gần như bất biến | Không phù hợp entity thường xuyên update |
| `READ_WRITE` | Hướng đến đọc/ghi có đồng bộ hóa cache nhất định | Có overhead và semantics cụ thể, không đồng nghĩa database isolation tuyệt đối |
| `NONSTRICT_READ_WRITE` | Cho phép mức nhất quán lỏng hơn | Có thể chấp nhận stale window theo thiết kế |
| `TRANSACTIONAL` | Phối hợp cache với transaction phù hợp | Backend/infrastructure phải hỗ trợ |

Không chọn strategy chỉ vì tên nghe “an toàn”. Phải xác minh data freshness requirements và cache topology.

### 18.3. @Version có giải quyết mọi vấn đề cache không?

`@Version` hỗ trợ optimistic concurrency trong ORM. Nó không tự thông báo cho mọi external writer hoặc tất cả cache nodes nếu dữ liệu được thay bằng SQL ngoài cơ chế invalidation của provider.

---

## 19. Hibernate query cache bằng unwrap

Ngoài hint có thể dùng Hibernate API:

```java
TypedQuery<Product> jpaQuery = em.createQuery(
    """
    SELECT p
    FROM Product p
    WHERE p.active = true
    ORDER BY p.price ASC, p.id ASC
    """,
    Product.class);

org.hibernate.query.Query<Product> hibernateQuery =
    jpaQuery.unwrap(org.hibernate.query.Query.class);

hibernateQuery.setCacheable(true);
hibernateQuery.setCacheRegion("catalog.activeProducts");

List<Product> products = hibernateQuery.getResultList();
```

Đoạn code minh họa ý tưởng; phép unwrap generic có thể sinh warning unchecked tùy Java/compiler, và API chi tiết cần đối chiếu với Hibernate version. Quan trọng là `setCacheable(true)` và `setCacheRegion(...)` thuộc **Hibernate**, không phải contract của `jakarta.persistence.TypedQuery`.

### 19.1. Query cache region không phải entity cache region

`catalog.activeProducts` có thể chứa **query result entries**. `catalog.products` có thể chứa entity states. Tên region giống nhau/khác nhau không làm hai loại cache tự có cùng key/value hoặc invalidation APIs.

### 19.2. Cùng truy vấn với tham số khác là key khác

```java
query.setParameter("minPrice", new BigDecimal("100"));
```

và:

```java
query.setParameter("minPrice", new BigDecimal("200"));
```

thường là hai query cache entries khác nhau. Đừng mong query cache hit vì “chúng dùng chung JPQL text”.

---

## 20. Phân trang và query cache

Giả sử:

```jpql
SELECT p
FROM Product p
WHERE p.active = true
ORDER BY p.price ASC, p.id ASC
```

API dùng:

```java
query.setFirstResult(0);
query.setMaxResults(20);
```

Trang kế tiếp:

```java
query.setFirstResult(20);
query.setMaxResults(20);
```

Hai kết quả là **hai đoạn khác nhau** của tập dữ liệu và thường cần các cache keys khác nhau.

### 20.1. Query cache dễ có cardinality key rất lớn

Một tìm kiếm có:

- 10.000 từ khóa khác nhau.
- 50 price ranges.
- Nhiều sort orders.
- Hàng trăm offsets.
- Filter theo tenant/user.
- Thay đổi trạng thái dữ liệu thường xuyên.

sẽ tạo rất nhiều tổ hợp query keys. Cache hit rate thấp, nhưng bộ nhớ/cache churn cao.

### 20.2. Dùng query cache cho trang đầu phổ biến

Một use case có thể hợp lý:

```text
Top 20 sản phẩm đang bán chạy trong category BOOK
Sort theo một ranking được cập nhật mỗi 10 phút
Rất nhiều người dùng yêu cầu cùng một trang
```

Nếu sự nhất quán cho phép và key lặp nhiều, query cache hoặc application response cache có thể có giá trị.

### 20.3. Trang sâu và bộ lọc riêng từng người dùng

Các trang sâu ít ai mở, query params khác nhau và dữ liệu thay đổi liên tục thường không phù hợp query cache. Trước tiên nên tối ưu query/index và cân nhắc keyset pagination.

---

## 21. Invalidation: điểm khó nhất của query result cache

Giả sử query cache lưu:

```text
SELECT p WHERE active=true AND category='BOOK'
Result IDs: [12,19,42]
```

Transaction khác thêm Product#99 active=true thuộc BOOK:

```text
Database now should return [12,19,42,99].
```

Nếu query cache không biết thay đổi `products`, nó sẽ tiếp tục trả kết quả cũ.

### 21.1. Entity cache invalidation chưa đủ

Ngay cả khi Product#99 đã có L2 entry mới, cache query result cũ vẫn không chứa ID 99. Đây là lý do hai cache cần phối hợp:

- Entity cache trả state cho một ID.
- Query cache phải biết lúc nào tập IDs/tuples có thể không còn hợp lệ.

### 21.2. Entity price thay đổi cũng có thể đổi thứ tự

Nếu Product#42 đổi price từ 200 xuống 50, query `ORDER BY price ASC` phải sắp lại. Entity cache Product#42 được cập nhật không tự sửa **thứ tự IDs** trong một query result entry đã cache.

### 21.3. DELETE và deactivation

Nếu Product#19 bị xóa hoặc `active=false`, query result cũ không được tiếp tục trả nó như một thành viên hợp lệ sau khi consistency policy yêu cầu kết quả mới.

### 21.4. COUNT query cũng chịu invalidation

Nếu query cache chứa:

```jpql
SELECT COUNT(p)
FROM Product p
WHERE p.active = true
```

thì INSERT/DELETE/change active có thể làm count stale. Cache result cho aggregate không tự an toàn hơn entity query; cần invalidation đúng.

---

## 22. Hibernate invalidation và query spaces

Trong Hibernate ORM, query caching thường phối hợp với thông tin **những bảng/query spaces** mà query phụ thuộc và một cơ chế cập nhật trạng thái thời điểm thay đổi. Provider dùng metadata để quyết định cached query result có còn dùng được sau các writes mà nó biết.

Khái niệm:

```text
Cached query Q:
  depends on tables: products, categories

Transaction modifies products:
  product inserted/updated/deleted

Provider knows Q depends on products:
  Q result may be invalidated/revalidated

Next Q execution:
  cache miss / recompute / put new result
```

### 22.1. “Update timestamps region” là implementation concern

Hibernate query cache có cơ chế quản lý timestamps/update information cho các query spaces. Tên regions/cách lưu/strategy thay đổi theo Hibernate version. Vì vậy:

- Đừng hard-code một internal region name từ bài hướng dẫn cũ.
- Đừng evict/tắt timestamps region tùy tiện.
- TTL/eviction quá ngắn cho metadata invalidation có thể gây nguy cơ incorrect reuse tùy cache strategy.
- Đọc tài liệu và statistics của Hibernate version đang dùng.

### 22.2. Invalidation có thể coarse-grained

Một query lọc category BOOK vẫn có thể bị invalidate khi một Product thuộc category khác được update, vì provider theo dõi ở mức table/query space chứ không hiểu mọi điều kiện vị từ đến mức row-by-row.

Do đó, dữ liệu update thường xuyên có thể khiến query cache miss liên tục dù query key lặp rất nhiều.

### 22.3. Không cam kết “chỉ invalidate đúng các query bị ảnh hưởng”

Provider thường đánh đổi giữa tính đúng và chi phí theo dõi dependencies. Cơ chế invalidation có thể rộng hơn những rows thực sự thay đổi.

---

## 23. Các write paths ảnh hưởng invalidation ra sao?

| Đường thay đổi dữ liệu | Cần đánh giá |
|---|---|
| `em.persist`/dirty checking/`remove` và commit | Provider thường có cơ chế đồng bộ L2/query invalidation |
| JPQL bulk `UPDATE`/`DELETE` | Bỏ qua lifecycle từng managed entity; provider có thể invalidate affected regions/query spaces, cần kiểm tra |
| Native SQL chạy qua provider | Provider có thể không suy được đầy đủ affected query spaces; cần test/synchronization/eviction |
| JDBC riêng, migration hoặc script | ORM không tự biết tất cả thay đổi |
| Trigger/stored procedure | Side effects có thể ảnh hưởng thêm bảng ngoài SQL gọi |
| External service ghi database | Phải thiết kế coherence/invalidation |
| Direct DB admin update | Không bảo đảm ORM caches nhận tín hiệu |
| Replica lag | Cache và truy vấn có thể nhìn các nguồn dữ liệu khác nhau |

### 23.1. Bulk update không đồng nghĩa cập nhật entities đang managed

Ví dụ:

```java
int changed = em.createQuery(
    """
    UPDATE Product p
    SET p.active = false
    WHERE p.price < :threshold
    """)
    .setParameter("threshold", new BigDecimal("10.00"))
    .executeUpdate();
```

Bulk update tác động DB nhưng **không đồng bộ ngay state của mọi Product instance đã managed** trong persistence context. Bất kể L2/query cache invalidation của provider, L1 có thể giữ state cũ. Sau bulk DML cần thiết kế `clear`/refresh/transaction boundary phù hợp.

### 23.2. Native updates và dependent tables

Nếu một stored procedure sửa cả `products` và `categories`, provider có thể không biết đầy đủ side effects. Query result cache phụ thuộc hai bảng có thể cần eviction theo API provider hoặc một invalidation workflow riêng.

### 23.3. Không xem TTL là thay thế invalidation correctness

TTL 60 giây chỉ giới hạn một loại stale window; nếu nghiệp vụ yêu cầu đọc đúng dữ liệu sau commit, “sau một phút sẽ đúng” không đáp ứng. Ngược lại, nếu SLA chấp nhận stale 30 giây, một cache có TTL/invalidation policy tương ứng có thể hợp lý. **Phải viết rõ freshness contract.**

---

## 24. Evict entity cache không mặc nhiên xóa query cache

Ví dụ:

```java
emf.getCache().evict(Product.class, 42L);
```

Thao tác này nhắm đến **entry entity Product#42** trong shared cache. Nếu query cache có result IDs chứa 42, không được mặc định rằng nó cũng bị xóa chỉ vì entity entry bị evict.

### 24.1. Hệ quả

Query cache có thể vẫn hit và trả ID 42, rồi provider phải tải Product#42 từ DB vì entity state đã bị evict. Điều này khác một query cache invalidation.

### 24.2. Evict query cache cần API provider

Với Hibernate, có các API cache regions ở `SessionFactory`, ví dụ phương thức có ý nghĩa:

```java
org.hibernate.SessionFactory sessionFactory =
    emf.unwrap(org.hibernate.SessionFactory.class);

// Hibernate-specific; API chi tiết phụ thuộc phiên bản.
sessionFactory.getCache().evictQueryRegions();
```

Đoạn này mô tả khả năng evict các query regions. Trong production, thường nên evict **region cụ thể** nếu version/API hỗ trợ, tránh xóa mọi query cache không cần thiết.

### 24.3. Query cache eviction không tự evict entity L2

Ngược lại, xóa query cache result không tự có nghĩa xóa mọi Product state trong L2. Lượt query sau có thể phải chạy SQL tìm IDs, nhưng provider vẫn có thể tận dụng entity cache khi materialize.

### 24.4. Không dùng evictAll() như nút sửa dữ liệu chung

`Cache.evictAll()` có thể làm nhiều cache entries lạnh, tạo đột biến database load. Trước khi dùng, cần xác định thật sự cache nào đang stale và đường invalidation nào bị thiếu.

---

## 25. Entity cache và collection cache

Một entity có quan hệ collection:

```java
@OneToMany(mappedBy = "category", fetch = FetchType.LAZY)
private List<Product> products;
```

Ngay cả khi Category được cache L2, **danh sách Product IDs trong `category.products` không mặc nhiên được cache** theo cùng chính sách.

### 25.1. Collection cache là một vùng dữ liệu khác

Hibernate có thể cache collection associations bằng cấu hình riêng, ví dụ:

```java
@OneToMany(mappedBy = "category", fetch = FetchType.LAZY)
@org.hibernate.annotations.Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog.categoryProducts"
)
private List<Product> products;
```

Cấu hình này provider-specific; cần mapping Category–Product tương ứng và imports Hibernate. Nó **không phải query result cache**.

### 25.2. Ba thứ khác nhau

```text
Entity cache:
  Category#7 -> state(name="Books", ...)

Collection cache:
  Category#7.products -> [Product#12,#19,#42] (conceptual)

Query result cache:
  SELECT p WHERE category='BOOK' AND active=true
    -> [#12,#42] (conceptual)
```

Collection cache trả membership của association cụ thể, còn query result cache có thể đại diện tập kết quả theo một query/filter bất kỳ.

### 25.3. N+1 vẫn có thể xảy ra

Nếu load 100 Categories và gọi `category.getProducts()` cho từng Category, query cache của một JPQL khác không có nghĩa collections đã loaded. Có thể cần collection cache, batch fetching hoặc một fetch plan riêng. Đừng giải quyết N+1 chỉ bằng cách bật query cache trên unrelated query.

---

## 26. L1, L2 và query cache qua vòng đời transaction

### 26.1. Trong một EntityManager đang managed

```java
Product product = em.find(Product.class, 42L);
product.changePrice(new BigDecimal("120.00"), Instant.now());
```

`product.getPrice()` phản ánh thay đổi Java ngay, dù `flush()/commit()` chưa xảy ra. Query cache/L2 ở phạm vi shared cache không phải nơi công bố giá pending này như một committed value cho transaction khác.

### 26.2. Flush và transaction consistency

Trước JPQL query, provider có thể tự flush pending changes theo `FlushModeType.AUTO` khi cần để kết quả query hợp lý trong transaction. Query cache cần xử lý transaction-local changes và database modifications theo semantics của provider; **đừng dựa vào cached query result để đọc chưa-flush changes một cách tùy tiện**.

### 26.3. Commit/rollback

Entity cache write-through/update/invalidation thường được phối hợp với transaction lifecycle theo provider strategy. Sau rollback, shared cache không được coi như chứa committed state của pending changes đã bị hủy.

### 26.4. Transaction read-your-writes

Nếu ứng dụng yêu cầu một query trong cùng transaction phản ánh các thay đổi đã thực hiện, flush mode và provider execution semantics cần được hiểu. Đừng dùng một query result cache với stale outcome như lời giải thích mặc định cho mọi sai khác; trước tiên kiểm tra pending changes, flush, isolation, filters và L1 state.

---

## 27. Dữ liệu cũ có thể đến từ L1, không phải L2

Một tình huống:

```java
EntityManager em = emf.createEntityManager();

Product product = em.find(Product.class, 42L);

// Transaction khác cập nhật giá Product#42 và commit.

Product again = em.find(Product.class, 42L);
```

`again` thường là cùng managed instance của L1, không tự refresh giá mới. Dù L2 đã được invalidated, persistence context hiện tại vẫn có thể giữ state cũ.

### 27.1. Cách chẩn đoán

Dùng:

```java
em.refresh(product);
```

hoặc đóng EM cũ/mở EM mới phù hợp để quan sát state theo DB transaction visibility. Không chỉ gọi `emf.getCache().evict(Product.class,42L)` rồi mong L1 đổi theo.

### 27.2. em.clear và Cache.evict khác nhau

| Operation | Tác dụng chủ yếu |
|---|---|
| `em.clear()` | Detach tất cả managed entities trong **EM đó** |
| `em.detach(product)` | Detach một entity instance trong EM đó |
| `em.refresh(product)` | Nạp lại state của managed entity từ DB theo semantics hiện hành |
| `emf.getCache().evict(Product.class,42L)` | Evict shared cache state của entity identity |
| Provider query cache eviction | Evict cached query result entries/regions |

Nếu gọi `em.clear()` khi có pending changes chưa flush, những thay đổi không được đồng bộ có thể bị mất. Phải quyết định transaction/unit of work trước khi clear.

### 27.3. Refresh có bảo đảm đọc latest committed trên mọi isolation?

Không. Database isolation/snapshot và routing ảnh hưởng dữ liệu nhìn thấy. Dù provider yêu cầu DB refresh, một transaction trên snapshot cũ vẫn có visibility rules riêng.

---

## 28. Phân biệt Spring Cache @Cacheable và JPA @Cacheable

Một source file có thể import:

```java
import jakarta.persistence.Cacheable;
```

để nói entity eligible cho JPA shared cache.

Trong Spring service:

```java
import org.springframework.cache.annotation.Cacheable;

@Service
public class CatalogService {

    @Cacheable(cacheNames = "catalogList",
               key = "#categoryCode")
    public List<ProductCard> listCategory(String categoryCode) {
        // Repository query...
        return repository.findCardsByCategory(categoryCode);
    }
}
```

Đây là **Spring method cache**, có thể cache **giá trị method return** theo categoryCode (và key logic do cấu hình quyết định).

### 28.1. Spring method cache không tự hiểu Hibernate query spaces

Nếu Product mới được thêm, Spring Cache không tự biết `catalogList` phải invalidate chỉ vì JPA đã commit insert. Ứng dụng cần `@CacheEvict`, event/invalidation workflow hoặc TTL phù hợp.

### 28.2. JPA entity cache không cache method response

L2 có Product#42 state không có nghĩa Spring `listCategory("BOOK")` đã có method-result cache entry. Hai cơ chế có cache key và lifecycle khác nhau.

### 28.3. Spring @Cacheable không nhất thiết đủ cho correctness

Nếu method phụ thuộc user/tenant, key chỉ `#categoryCode` có thể khiến tenant này nhận dữ liệu của tenant khác nếu các tenants có catalogs khác nhau và cache chung. Cần key chứa đúng partition/filters/security context hoặc tách cache region, và tuyệt đối không thay authorization check bằng việc “trả dữ liệu đã cache”.

### 28.4. @CacheEvict khác JPA Cache.evict

`org.springframework.cache.annotation.CacheEvict` invalidates Spring cache entries. `EntityManagerFactory.getCache().evict` nhắm tới JPA shared cache. Chúng không tự thay thế nhau.

---

## 29. Database buffer cache và database result cache khác ORM caches

Database thường có cache của:

- Data pages/index pages trong buffer pool.
- Parsed/planned SQL statements.
- Một số hệ quản trị có server-side result caching.
- Materialized views/indexes.

Nếu chạy cùng JPQL hai lần và lần thứ hai nhanh hơn, đó có thể là **DB buffer cache warm** dù JPA không dùng query result cache.

### 29.1. Phân biệt bằng metrics

Nếu lần hai vẫn có SELECT tới DB nhưng nhanh hơn, có thể do:

- DB buffer cache.
- Prepared-statement/plan reuse.
- Disk/cache warm.
- JVM JIT.
- Connection pool warm.

Muốn chứng minh Hibernate query result cache hit, cần **query cache hit metrics** và SQL logging, không chỉ so timing.

### 29.2. Cache plan không bỏ SQL

Plan cache hit giúp giảm parse/plan overhead, không phải tự trả kết quả SELECT từ RAM của Hibernate.

### 29.3. DB-side query/result cache có invalidation riêng

Nếu database engine dùng result cache, kết quả có thể nhanh/không đọc bảng nhưng đó là mechanism của DB, không phải JPA query cache. Hãy phân biệt nơi cache nằm và ai chịu trách nhiệm invalidation.

---

## 30. Hiệu năng: khi nào nên dùng L2 entity cache?

L2 phù hợp nếu:

- Entity được đọc theo ID rất nhiều lần giữa các EntityManagers.
- Entity ít thay đổi so với lượng read.
- Object state tương đối nhỏ/ổn định.
- Shared cache backend và invalidation strategy đáp ứng freshness requirements.
- Dữ liệu có access distribution cho tỉ lệ hit tốt.
- Chi phí đọc DB/serialization đủ lớn để lợi ích vượt overhead.

Ví dụ:

```text
Category#7 ("BOOK")
Country#VN ("Vietnam")
TaxRule#42 (ít thay đổi)
StaticLookup#13
```

### 30.1. Không phải entity nào cũng hợp lý để cache

Một `Order` cập nhật trạng thái liên tục hoặc chứa fields lớn có thể gây churn và coherence overhead. Cache quá nhiều entities còn làm tăng heap/distributed cache memory và eviction pressure.

### 30.2. L2 cache không thay index

Nếu query tìm Products theo giá/category không có index phù hợp, L2 không tự sửa SQL scan. Entity cache phát huy rõ nhất khi truy cập các identity keys đã biết.

### 30.3. Cache theo ID và đa tenant

Nếu cùng ID tồn tại trong nhiều tenant contexts (database-per-tenant/schema-per-tenant/discriminator), cache key/coherence phải partition đúng. Cần sử dụng multi-tenancy feature của provider có hỗ trợ và kiểm thử cross-tenant isolation.

---

## 31. Hiệu năng: khi nào nên dùng query result cache?

Query result cache có thể hữu ích khi:

- Cùng query text và bind values được lặp lại thường xuyên.
- Kết quả tương đối nhỏ.
- Tables liên quan ít bị update.
- Query đủ đắt so với chi phí cache lookup/invalidation.
- Tỉ lệ hit cao sau warm-up.
- Freshness SLA cho phép strategy của provider.
- Entity state trong L2 hoặc scalar result có cơ hội tránh SQL thứ cấp.

Ví dụ:

```text
Top categories theo lượt truy cập, cập nhật ít lần mỗi giờ.
Bộ lọc hằng số: active=true, featured=true.
Trang đầu của danh mục phổ biến.
Danh sách trạng thái được cấu hình hiếm khi đổi.
```

### 31.1. Khi query cache có thể phản tác dụng

- Tìm kiếm text có keyword riêng từng request.
- Filter động rất nhiều combinations.
- OFFSET/page sâu đa dạng.
- Bảng được update liên tục khiến cache invalidated.
- Query result lớn, mỗi entry tốn bộ nhớ.
- Dữ liệu liên tục thay đổi ranking/order.
- Access pattern phân tán, ít key nào được gọi lần hai.

### 31.2. Query cache có thể tăng overhead khi không hit

Mỗi cacheable query có chi phí lookup, put, dependency management và memory usage. Nếu gần như mọi request đều miss hoặc bị invalidate trước khi tái sử dụng, hiệu năng có thể tệ hơn không cache.

### 31.3. Cache ít nhưng đúng query

Một chiến lược tốt thường là chọn một số queries có **tần suất lặp key cao** và benchmark từng query region, thay vì bật cacheable cho mọi repository method.

---

## 32. Hai kiểu “stale” phải phân biệt

### 32.1. Entity state stale

```text
Product#42 trong L2:
  price = 100

Database:
  Product#42 price = 120
```

Nếu provider không invalidate/update L2 sau thay đổi, `find(Product#42)` ở context mới có thể trả state cũ.

### 32.2. Query result membership/order stale

```text
Cached result:
  SELECT p WHERE price < 110 ORDER BY price
  => [#42,#51]

Database sau update #42 price=120:
  đúng ra => [#51]
```

Ngay cả khi Product#42 state trong L2 đã là 120, cached **membership** vẫn còn ID 42 nếu query result invalidation chưa xảy ra. Đó là lỗi khác.

### 32.3. Cả hai có thể stale đồng thời

Có thể vừa sai giá entity, vừa sai tập ID của query. Chỉ evict Product#42 khỏi L2 có thể sửa stale entity state khi lần sau nạp lại, nhưng chưa chắc sửa stale query membership.

---

## 33. Cache correctness khi cập nhật bằng external writer

Giả sử ứng dụng A dùng Hibernate và L2/query cache. Ứng dụng B dùng JDBC trực tiếp cập nhật `products`.

```text
App A:
  cached Product#42 price=100
  cached query [#42,#51]

App B:
  JDBC UPDATE products SET price=120 WHERE id=42
  COMMIT

App A:
  không nhận invalidation từ ORM của App B
```

Lúc này có nguy cơ stale cache nếu không có một hệ thống coherence chung.

### 33.1. Những hướng giải quyết

- Chuyển writes qua cùng cơ chế ORM/cache có thể invalidate.
- Event-driven invalidation (outbox/CDC/message bus) với ordering/retries hợp lý.
- TTL ngắn nếu SLA chấp nhận stale.
- Explicit eviction ở boundary công việc đã biết.
- Disable cache cho dữ liệu có writes ngoài tầm kiểm soát.
- Đọc trực tiếp DB với cache bypass/refresh khi cần consistency mạnh.

### 33.2. Invalidation event không tự đáng tin tuyệt đối

Một event có thể bị mất, trễ, gửi trùng hoặc reorder. Nếu correctness quan trọng, cần thiết kế idempotent invalidation, retry, monitoring và recovery/reconciliation. Không chỉ “có Kafka” là đã giải quyết coherency.

### 33.3. Đừng bỏ qua versioning của messages

Nếu entry mới đã được cập nhật mà một invalidation event cũ đến muộn, cách invalidation theo version/timestamp hoặc evict-only event có thể khác nhau. Cần đánh giá chiến lược cụ thể, nhất là khi sử dụng distributed caches.

---

## 34. Cache trong cụm nhiều application instances

Nếu mỗi node có một local in-memory L2:

```text
Node A L2: Product#42 price=100
Node B L2: Product#42 price=100
Database: price=100

Node A updates Product#42 to 120, commits.
Node A local cache updated/evicted.
Node B local cache vẫn có price=100 nếu không có cluster invalidation.
```

### 34.1. Local cache không tự thành distributed cache

Cache backend có thể hỗ trợ cluster topology, distributed storage hoặc invalidation messages, nhưng phải cấu hình đúng. Một provider L2 enabled trên từng JVM không tự bảo đảm cache coherence giữa nodes.

### 34.2. Shared distributed cache vẫn có consistency model

Distributed cache có network latency, partitions, eventual invalidation, replication/recovery. Cần kiểm chứng behavior dưới concurrent writes và node failures.

### 34.3. Chọn theo nhu cầu

Một static reference table ít thay đổi có thể chấp nhận TTL local. Một giá tiền cần nhất quán chặt có thể yêu cầu invalidation mạnh, bypass trong critical path hoặc một nguồn đọc authoritative khác.

---

## 35. Cache và transaction isolation

L2/query cache là cơ chế tối ưu, không phải transaction isolation level.

Các tình huống cần hiểu:

- `READ COMMITTED` có thể cho các statements khác nhau nhìn committed state khác nhau.
- `REPEATABLE READ` có snapshot/locking semantics khác nhau theo DBMS.
- `SERIALIZABLE` không phải “query cache tự đồng bộ dữ liệu”.
- Trong cùng persistence context, managed state có thể không tự đổi sau concurrent commit.
- Shared cache policy có thể ảnh hưởng lúc dữ liệu được nạp, nhưng không thay thế database constraints/locks.

### 35.1. Cache không giải quyết lost update

Dùng `@Version`, optimistic locking, pessimistic locking, atomic SQL update hoặc transaction design thích hợp. Đừng xem việc Product nằm trong cache là cơ chế ngăn hai threads ghi đè giá.

### 35.2. Caching dữ liệu cần đọc mới nhất

Nếu quyết định nghiệp vụ đòi hỏi giá trị tại thời điểm giao dịch (ví dụ số dư, tồn kho, hạn mức), cần xác định nơi dữ liệu authoritative và cơ chế consistency. Có thể phải bypass shared cache hoặc lock/read DB trong transaction, nhưng điều đó không tự bảo đảm correctness nếu update logic không đồng bộ.

### 35.3. Trạng thái một giao dịch chưa commit không nên công bố tùy tiện qua shared caches

Provider/cache concurrency strategy thường phối hợp với transaction nhằm tránh lộ pending changes sai. Không viết code dùng cache ngoài transaction để công bố dữ liệu trước commit mà không có policy thích hợp.

---

## 36. Query cache với thống kê COUNT/SUM

Ví dụ:

```jpql
SELECT COUNT(p)
FROM Product p
WHERE p.active = true
```

hoặc:

```jpql
SELECT AVG(p.price)
FROM Product p
WHERE p.active = true
```

Các query dạng scalar/aggregate có thể được Hibernate cache nếu đủ điều kiện/cấu hình. Nhưng:

- Khi insert/deactivate Products, COUNT thay đổi.
- Khi update price, AVG thay đổi.
- Cache result không tự biết “chỉ đổi đúng một row nên cộng/trừ delta”.
- Invalidation có thể ảnh hưởng query spaces rộng.

### 36.1. Đếm totalElements cho Page

Một `Page<ProductCard>` thường có content query và count query riêng. Query result cache cho content **không mặc nhiên cache count**; đó là hai query khác với keys/results khác nhau.

### 36.2. Cẩn thận với count query cập nhật liên tục

Đếm Orders đang chờ xử lý có thể thay đổi mỗi giây. Cache count result đôi khi chỉ làm tăng stale metadata và invalidation churn. Nếu UI chỉ cần `hasNext`, dùng Slice/pageSize+1 có thể phù hợp hơn.

### 36.3. Không dùng cache như materialized aggregate không được quản lý

Nếu báo cáo lớn cần cập nhật theo chu kỳ, materialized view/report table với refresh policy rõ đôi khi dễ quản lý hơn một query cache bị invalidate liên tục. Đây là lựa chọn kiến trúc theo workload.

---

## 37. Query cache và native SQL

Với native SQL:

```java
Query query = em.createNativeQuery(
    """
    SELECT id, name, price
    FROM products
    WHERE active = true
    ORDER BY price, id
    """
);
```

Việc query được provider cacheable hay không và provider biết phụ thuộc những tables nào có thể cần cấu hình/metadata riêng.

### 37.1. Query spaces

Nếu ORM không xác định được tables thay đổi liên quan đến native query, invalidation có thể thiếu hoặc quá rộng tùy provider strategy. Một số Hibernate APIs cho phép khai báo synchronized query spaces/entities cho native queries, nhưng tên API cụ thể phụ thuộc version.

### 37.2. Không dựa vào query cache cho SQL có side effects

Native/stored-procedure SQL có thể có hành vi ngoài đọc, trigger, temporary table hoặc external function. Query result cache chỉ nên dùng khi tính hợp lệ và dependencies có thể hiểu/kiểm soát. Không cache query có side effects hay phụ thuộc ngữ cảnh không nằm trong key.

### 37.3. Các yếu tố session có thể ảnh hưởng kết quả

Timezone/session variables/row-level security, database settings, collation hoặc tenant schema có thể thay đổi result dù SQL text/parameters nhìn giống nhau. Phải đảm bảo query cache key/partition phản ánh những factors thực sự làm đổi kết quả, hoặc không cache loại query đó.

---

## 38. Query cache và dữ liệu nhạy cảm

Một cached query result có thể chứa IDs/tuples phản ánh:

- Tenant boundaries.
- User permissions.
- Các trường nhạy cảm.
- Trạng thái private/archived.
- Giá theo khách hàng cụ thể.

### 38.1. Không cache kết quả của người A rồi trả cho người B

Nếu query có dynamic security filters, providers có thể có cơ chế đưa filters/tenant context vào key. Nhưng nếu authorization được áp dụng ngoài query, hoặc dùng Spring method cache key thiếu user context, có nguy cơ cross-user data exposure.

### 38.2. Cache key không thay authorization

Mỗi request phải xác thực/quyền truy cập đúng. “Cursor/cache key của người dùng trước” không được tin như bằng chứng người dùng hiện tại được xem dữ liệu.

### 38.3. PII trong cache backend

Distributed caches, metrics/logs, dump files và debug tooling có thể chứa thông tin nhạy cảm. Cần access control, encryption/TTL phù hợp và policy lưu trữ dữ liệu.

---

## 39. Quan sát SQL để biết cache nào thực sự hoạt động

Một thí nghiệm không nên chỉ in:

```java
System.out.println("Took 15 ms");
```

vì thời gian phụ thuộc DB buffer, JVM, network, CPU scheduling, connection pool và nhiều yếu tố khác.

Nên thu:

- SQL statement count.
- Thời gian query.
- L1 context behavior.
- L2 hits/misses/puts.
- Query cache hits/misses/puts.
- Query key và cache region có ý nghĩa.
- Rows returned và entity loads.
- Cache evictions/expirations.
- Cache size/heap/network.
- Transaction boundary và DB writes.

### 39.1. Dữ liệu cold/warm

```text
Cold:
  L1 mới
  L2/query cache cold/evicted theo mục tiêu thử
  DB buffer có thể vẫn warm

Warm:
  L1 mới
  L2/query cache đã được populate
  Query text/params giống lượt trước
```

Phải ghi rõ “cold” là cold ở **tầng nào**. Xóa L2 không làm DB OS buffer trở thành cold.

### 39.2. Khi đo query cache, dùng EntityManager mới

Nếu chạy hai lần trong cùng EM, L1 có thể che SQL tải entity, làm khó phân biệt query cache và L2. Dùng EM mới cho từng run để kết quả dễ diễn giải.

---

## 40. Hibernate Statistics: chỉ số L2 và query cache riêng

Hibernate có API thống kê. Tùy version, có thể đọc các counters:

```java
org.hibernate.SessionFactory sessionFactory =
    emf.unwrap(org.hibernate.SessionFactory.class);

org.hibernate.stat.Statistics stats =
    sessionFactory.getStatistics();

stats.setStatisticsEnabled(true);

// Chuẩn bị riêng ngoài transaction/data operations cần đo.
stats.clear();

// Thực hiện các thao tác JPA ở những EntityManagers mới.
// ...

long l2Hits = stats.getSecondLevelCacheHitCount();
long l2Misses = stats.getSecondLevelCacheMissCount();
long l2Puts = stats.getSecondLevelCachePutCount();

long queryHits = stats.getQueryCacheHitCount();
long queryMisses = stats.getQueryCacheMissCount();
long queryPuts = stats.getQueryCachePutCount();

System.out.println("L2 hits: " + l2Hits);
System.out.println("L2 misses: " + l2Misses);
System.out.println("L2 puts: " + l2Puts);

System.out.println("Query cache hits: " + queryHits);
System.out.println("Query cache misses: " + queryMisses);
System.out.println("Query cache puts: " + queryPuts);
```

Đây là **Hibernate-specific API**. Tên và cách tính/khả năng statistics có thể thay đổi theo version. Không dùng nó như API Jakarta Persistence portable.

### 40.1. Ý nghĩa của các counters

- **L2 hit**: provider tìm entity/collection cache entry theo cơ chế tương ứng.
- **L2 miss**: cache lookup không thấy entry.
- **L2 put**: state được đưa vào L2.
- **Query cache hit**: một cacheable query có reusable result entry.
- **Query cache miss**: không tìm thấy/không còn hợp lệ result entry.
- **Query cache put**: query result được cache.

Không cộng đơn giản L2 hits với query hits để suy SQL giảm đúng bằng tổng. Một query cache hit có thể giải quyết nhiều IDs, hoặc phát thêm SQL cho missing entities.

### 40.2. Clearing statistics không có nghĩa clearing caches

`stats.clear()` thường reset **counters**, không xóa L2 hoặc query cache data. Khi thiết kế cold/warm test, cần eviction bằng cache APIs riêng và tạo EntityManagers mới.

### 40.3. Đo sau mọi operation liên quan

Nếu khi map DTO code truy cập associations LAZY, những SQL thêm phải nằm trong khoảng đo. Không chỉ ghi SQL từ lời gọi JPQL mà quên phần serialization.

---

## 41. Thí nghiệm A: tách L1 hit khỏi L2 hit

Thiết lập:

1. Bật SQL logging và thống kê Hibernate nếu dùng.
2. Chọn Product#42 đủ điều kiện L2.
3. Evict L2 entry của Product#42 bằng API phù hợp.
4. Mở EntityManager A.
5. Gọi `find` hai lần trong A.
6. Đóng A.
7. Mở EntityManager B.
8. Gọi `find` ID 42 trong B.
9. Ghi SQL, L2 counters và object identity.

### 41.1. Kết quả cần lý giải

| Thao tác | Điều cần quan sát |
|---|---|
| A.find(42) lần đầu | DB hoặc cache path tùy cold setup |
| A.find(42) lần hai | L1 managed identity; thường không SELECT mới |
| B.find(42) | L2 opportunity; hit nếu L2 được populate và còn entry |
| A/B Java object equality | `==` giữa hai EM không phải chỉ số L2 |

### 41.2. Thử lại với retrieve BYPASS

Dùng `CacheRetrieveMode.BYPASS` trong B để xem L2 lookup/hit và SQL thay đổi. Nhớ bắt đầu bằng context mới; nếu Product đã managed trong B, bypass không chứng minh được điều bạn muốn đo.

---

## 42. Thí nghiệm B: L2 không tự cache JPQL result

Thiết lập chỉ L2; **query result cache tắt hoặc query không cacheable**.

Query:

```jpql
SELECT p
FROM Product p
WHERE p.active = true
  AND p.category.code = :code
ORDER BY p.price, p.id
```

Lượt 1:

```java
EntityManager em1 = emf.createEntityManager();
List<Product> first = queryByCategory(em1, "BOOK");
em1.close();
```

Lượt 2:

```java
EntityManager em2 = emf.createEntityManager();
List<Product> second = queryByCategory(em2, "BOOK");
em2.close();
```

Cần đo:

- Có SQL thực thi JPQL ở cả hai lượt không?
- L2 hits có tăng không?
- Entity loads/hydration thay đổi không?
- Cùng result IDs nhưng có cùng Java instances không? (Hai contexts riêng không yêu cầu cùng instances.)

### 42.1. Phải giải thích đúng

Nếu lượt 2 vẫn chạy SELECT để xác định Products nhưng entity cache có hit, đó không phải bằng chứng entity cache vô dụng. Nó cho thấy **query cache và entity cache có trách nhiệm khác nhau**.

---

## 43. Thí nghiệm C: Query cache hit và L2 hit

Thiết lập:

1. Bật shared entity cache.
2. Bật Hibernate query cache.
3. Chọn một JPQL query có tham số cố định.
4. Đánh dấu query cacheable.
5. Dùng EntityManager mới mỗi lần chạy.
6. Query lượt đầu để populate.
7. Query lượt hai với **đúng cùng parameters/pagination**.
8. Ghi SQL + query cache counters + L2 counters.

### 43.1. Kịch bản mong đợi khi warm

Nếu cache entries còn hợp lệ và không có writes invalidating data, lượt sau có thể:

- Query cache hit.
- Tránh SQL cho việc xác định tập result.
- Tận dụng L2 để materialize entity state.
- Vẫn phát SQL cho associations hoặc entity states thiếu cache.

### 43.2. Kịch bản query cache hit nhưng SQL khác vẫn xuất hiện

Evict entity L2 entries nhưng giữ query cache result (nếu provider cho phép và không gây thay đổi khác). Chạy lại cùng cacheable query:

- Query cache hit có thể vẫn xảy ra.
- Provider có thể SELECT những entity states cần nạp theo IDs đã cache.

Đây là bài thử trực tiếp chứng minh hai cache khác nhau.

### 43.3. Đừng chỉ dựa trên thời gian chạy

Lượt hai nhanh hơn có thể do DB cache. Cần đồng thời có query cache hit metric hoặc query SQL gốc được bỏ qua theo log.

---

## 44. Thí nghiệm D: Đổi tham số và trang

Chạy cùng JPQL cacheable:

```text
Q(category="BOOK", page=0, size=20)
Q(category="BOOK", page=1, size=20)
Q(category="TOY", page=0, size=20)
Q(category="BOOK", page=0, size=20)
```

Ghi:

- Query cache hit/miss.
- SQL statements.
- Cached result key variations.
- Tỉ lệ reuse của trang đầu so với trang sâu.

### 44.1. Điều cần kết luận

Một query có cùng JPQL text nhưng khác parameter/pagination không mặc nhiên cùng cache entry. Khi quay lại tổ hợp đã chạy và còn hợp lệ, mới có cơ hội hit.

### 44.2. Sort order cũng làm thay đổi tập kết quả

`ORDER BY price ASC` và `ORDER BY price DESC` cần kết quả khác nhau. Cache key phải phân biệt query semantics, không thể chỉ khóa theo entity class.

---

## 45. Thí nghiệm E: INSERT làm thay đổi membership

1. Cache query `WHERE active=true AND category=BOOK`.
2. Xác nhận query result warm.
3. Trong EntityManager/transaction khác, `persist` Product mới active BOOK.
4. Commit.
5. Mở EntityManager mới.
6. Chạy cùng query cacheable.
7. Kiểm tra Product mới có xuất hiện không.
8. Đo query cache miss/invalidation.
9. Kiểm tra SQL và L2 state của Product mới.
10. Ghi coherence theo stack thực tế.

### 45.1. Điều quan trọng

Nếu chỉ nhìn L2 Product mới có entry mà không kiểm tra query membership, bạn chưa chứng minh query cache được invalidate đúng.

### 45.2. Transaction timing

Không thực hiện truy vấn kiểm tra trước khi INSERT commit rồi kỳ vọng thấy Product mới ở transaction khác. Ghi rõ transaction isolation và cache invalidation boundary.

---

## 46. Thí nghiệm F: UPDATE làm đổi thứ tự và filter

1. Cache query `WHERE active=true AND price < 200 ORDER BY price ASC,id ASC`.
2. Chọn Product#42 đang nằm trong result.
3. Trong transaction khác, đổi price của #42 từ 100 thành 250.
4. Commit.
5. Chạy query lại ở EM mới.
6. Kiểm tra Product#42 không còn phù hợp.
7. Đo invalidation query cache và L2 update/eviction.
8. Thử đổi price từ 100 thành 150 (vẫn phù hợp) để kiểm tra **thứ tự** thay đổi.
9. Ghi SQL/IDs/price.
10. Phân biệt stale entity state với stale result membership/order.

### 46.1. Hai chiều thay đổi

- Product **rời khỏi tập kết quả**: membership invalidation cần xảy ra.
- Product **vẫn thuộc tập nhưng đổi thứ tự**: cached order phải được đánh giá lại.
- Product **đổi field không ảnh hưởng query**: provider vẫn có thể invalidate vì query-space tracking coarse-grained.

---

## 47. Thí nghiệm G: DELETE và eviction

1. Cache query gồm Product#42.
2. Gọi `emf.getCache().evict(Product.class,42L)`.
3. Chạy lại cacheable query, quan sát query cache hit và entity loads.
4. Sau đó xóa Product#42 bằng JPA trong transaction.
5. Commit.
6. Chạy lại query ở EM mới.
7. Kiểm tra #42 không còn xuất hiện.
8. Phân biệt **entity eviction** với **query invalidation do DELETE**.

### 47.1. Tránh hiểu nhầm

Evict L2 một entity không tương đương DELETE database row. Kết quả query vẫn có thể chứa ID của entity đó khi nó còn tồn tại và thỏa điều kiện.

---

## 48. Thí nghiệm H: Bulk JPQL và persistence context

1. Mở EM A và load Product#42 thành managed.
2. Dùng bulk JPQL update Product#42 trong transaction phù hợp.
3. Quan sát state của Product#42 đang managed trong A.
4. `clear()` hoặc dùng EM mới để đọc DB state.
5. Đo L2/query cache behavior.
6. Đảm bảo cacheable query có kết quả tương ứng với DB sau commit.
7. Thử native SQL update trên DB test.
8. Ghi nhận provider có/không có invalidation tự động cho native path cụ thể.
9. Dùng explicit eviction/synchronization theo API provider khi cần.

### 48.1. Hai lỗi thường đi cùng nhau

- L1 stale vì bulk DML bypass managed entities.
- L2/query cache stale nếu provider không nhận biết đầy đủ external modifications.

Chữa một lớp không mặc nhiên chữa lớp còn lại.

---

## 49. Thí nghiệm I: Spring @Cacheable khác Hibernate query cache

Tạo Spring service:

```java
@org.springframework.cache.annotation.Cacheable(
    cacheNames = "productCards",
    key = "#categoryCode"
)
public List<ProductCard> list(String categoryCode) {
    return repository.findCards(categoryCode);
}
```

Thử:

1. Gọi `list("BOOK")` hai lần thông qua Spring proxy.
2. Quan sát repository/JPA method có được gọi lần hai không.
3. So sánh với một Hibernate cacheable JPQL query.
4. Sửa Product và commit.
5. Không evict Spring cache, quan sát method cache có thể trả kết quả cũ.
6. Thêm invalidation policy phù hợp.
7. Kiểm tra cache key nếu request có tenant/user-specific filters.
8. Giải thích vì sao Spring @Cacheable không có query-space invalidation tự động theo JPA.

### 49.1. Spring proxy và self-invocation

Trong cấu hình Spring caching theo proxy thông thường, một method trong cùng bean gọi trực tiếp method `@Cacheable` của chính nó có thể không qua proxy, làm cache interceptor không chạy. Đó là vấn đề Spring method interception, không phải bằng chứng JPA query cache thất bại.

---

## 50. Thí nghiệm J: Cache collections và N+1

1. Tạo 50 Categories, mỗi Category có 20 Products.
2. Load Categories bằng JPQL.
3. Truy cập Products cho từng Category.
4. Ghi số SQL collection loads.
5. Bật L2 cho Category entities.
6. Thử lại với EM mới.
7. Kiểm tra N+1 đã được giải quyết chưa.
8. Cấu hình collection caching hoặc batch fetching theo provider nếu phù hợp.
9. So sánh JOIN FETCH, DTO projection và collection cache.
10. Ghi footprint của Product objects và SQL rows.

### 50.1. Không dùng cache để che một query plan sai

Một query fetch 1.000.000 rows rồi mới áp dụng pagination trong memory vẫn có thể rất nặng dù L2/query cache có hit trong vài lượt. Cần sửa cardinality/fetch plan trước khi phụ thuộc cache.

---

## 51. EntityGraph, JOIN FETCH và cache

Một query có Entity Graph:

```java
EntityGraph<Product> graph =
    em.createEntityGraph(Product.class);

graph.addAttributeNodes("category");

TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p WHERE p.active = true",
    Product.class);

query.setHint(
    "jakarta.persistence.loadgraph",
    graph
);
```

### 51.1. Fetch plan không phải cache policy

`fetchgraph/loadgraph` diễn đạt attributes cần tải cho use case. Nó không tự bật L2 entity caching hoặc query result caching.

### 51.2. Query cache và fetch plan phải được hiểu cùng nhau

Nếu query cache hit nhưng graph yêu cầu Category chưa cached, provider vẫn phải bảo đảm fetch semantics, có thể cần SQL bổ sung. Đừng suy “query cache hit tức graph đã đủ”.

### 51.3. Static EAGER không tự biến query cache thành entity graph cache

Một association EAGER cần được tải theo mapping/query semantics; nó có thể được lấy qua JOIN/secondary SELECT. Query cache entries không mặc nhiên chứa toàn bộ deep object graph.

---

## 52. Cache đa tenant: identity và query context

Một multi-tenant app có thể có Product ID=42 ở tenant A và tenant B nhưng giá khác nhau.

### 52.1. L2 entity identity phải tenant-aware

Cache identity không thể đơn giản là `Product.class + 42` nếu cùng key có ý nghĩa khác nhau ở các tenants trong topology đó. Provider multi-tenancy integration phải xác định partition/tenant key và cache region semantics.

### 52.2. Query cache key phải tenant-aware

Query `SELECT p FROM Product p WHERE p.active=true` nhìn giống nhau về text nhưng có thể chạy trong schema/tenant khác nhau. Cache results phải được partition/synchronized theo tenant.

### 52.3. Không thay security enforcement bằng cache configuration

Cần tiếp tục kiểm tra authorization và mandatory filters ở data access layer. Query cache không phải thành phần chịu trách nhiệm quyết định ai được xem row nào.

---

## 53. Cách đọc cache statistics đúng

Giả sử:

```text
L2 entity cache:
  hits   = 950
  misses = 50

Query result cache:
  hits   = 5
  misses = 995
```

Diễn giải:

- Có nhiều entity lookup tận dụng L2.
- Query result cache hit rate rất thấp.
- Chưa chắc bật query cache có lợi dù entity cache hữu ích.

### 53.1. Hit rate tính thế nào?

```text
hit rate = hits / (hits + misses)
```

nếu denominator khác 0. Nhưng chỉ số này cần đặt trong bối cảnh query cost, result size, invalidation và scope đo.

### 53.2. Tỉ lệ hit cao không đồng nghĩa hiệu năng cao

Nếu cached query trả 50.000 entity IDs và provider phải tải nhiều entity states thiếu L2, cache hit chưa chắc giảm latency.

### 53.3. Tỉ lệ hit thấp không đồng nghĩa cache hoàn toàn vô dụng

Một số truy vấn rất đắt và ít lặp vẫn có thể được lợi trong workload cụ thể, nhưng cần đo công sức/cache memory và eviction overhead.

### 53.4. Quan sát theo cache region và query

Global counters có thể che việc một query hiệu quả còn 99 queries khác gây churn. Khi có API theo vùng/query, đo riêng query group và endpoint.

---

## 54. Đo cache trong test integration có kiểm soát

Một quy trình:

1. Chạy database mục tiêu (hoặc database test tương thích nếu chỉ kiểm tra logic).
2. Chuẩn bị dữ liệu cố định và commit.
3. Bật provider metrics/logging phù hợp.
4. Reset thống kê.
5. Evict caches **đúng loại** cần tạo cold state.
6. Dùng EM mới để chạy query lượt 1.
7. Đóng EM.
8. Dùng EM mới chạy lại query với cùng params.
9. Ghi SQL/metrics.
10. Chạy một write transaction và commit.
11. Dùng EM mới query lại.
12. So sánh expected data và cache invalidation.

### 54.1. Không gọi tất cả là “cold”

- L1 cold: tạo EM mới.
- L2 cold: evict appropriate entity region/entries.
- Query cache cold: evict query result region/entries qua provider API.
- DB buffer cold: là chuyện riêng của DB, không phải do `stats.clear()`.
- Plan cache cold: cũng là chuyện khác.

### 54.2. Kết quả cần có cả correctness lẫn performance

Một test query cache có hit nhưng trả stale data là **không đạt correctness**, dù nhanh. Một cache rất đúng nhưng gây overhead hơn lợi ích cần được điều chỉnh về hiệu năng.

---

## 55. Một báo cáo cache nên ghi gì?

```text
TEST CASE:
  product list by category

ENVIRONMENT:
  JPA provider/version:
  DBMS/version:
  Cache backend/version:
  L2 enabled:
  Query cache enabled:
  Entity cache strategy:
  Query cache region:
  Cache TTL/size:
  Transactions/isolation:

QUERY:
  JPQL:
  Parameters:
  Pagination:
  Sort:
  Tenant/security filters:

COLD RUN:
  SQL statements:
  L2 hit/miss/put:
  Query hit/miss/put:
  Latency:
  Result IDs:

WARM RUN:
  SQL statements:
  L2 hit/miss/put:
  Query hit/miss/put:
  Latency:
  Result IDs:

WRITE INVALIDATION:
  Persist/update/remove:
  Commit time:
  SQL:
  Result after commit:
  Cache metrics:

CONCLUSION:
  Which cache was effective?
  Is result correct?
  What freshness guarantee holds?
  What is the memory and invalidation cost?
  What changes are needed?
```

---

## 56. Những hiểu lầm thường gặp

### 56.1. “Có L2 thì JPQL không còn chạy SQL”

Sai. L2 cache entity states theo ID, không mặc nhiên cache tập IDs/rows của mọi truy vấn.

### 56.2. “Query cache hit thì chắc chắn không có SELECT nào”

Sai. Query cache có thể trả IDs, sau đó cần SELECT entity states/associations thiếu ở L1/L2.

### 56.3. “@Cacheable của JPA chính là Hibernate query cache”

Sai. `jakarta.persistence.Cacheable` mô tả shared entity cache eligibility, không đánh dấu JPQL query result.

### 56.4. “Spring @Cacheable tự đồng bộ với JPA”

Sai. Spring method cache và ORM caches là các tầng khác nhau; invalidation phải được thiết kế tương ứng.

### 56.5. “Hai lần find không SQL chứng minh L2 hoạt động”

Chưa đủ. Nếu cùng EntityManager, L1 có thể là nguyên nhân.

### 56.6. “Cache.evict(Product.class,id) sẽ xóa Product trong mọi EntityManager”

Sai. Managed entities đang ở L1 không tự bị detach hoặc refresh.

### 56.7. “em.clear() là xóa L2/query cache”

Sai. `clear` detach managed entities trong một persistence context, không xóa shared cache regions.

### 56.8. “Query cache chỉ cần lưu JPQL text làm key”

Sai. Query params, pagination, filters, tenant/sort context có thể làm thay đổi kết quả.

### 56.9. “Cùng JPQL text nghĩa luôn cache hit”

Không khi bind values khác, result bị invalidated, cache entry evicted hoặc query không cacheable.

### 56.10. “Thêm INSERT Product mới thì entity cache đủ làm query biết”

Sai. Query result membership còn cần được invalidated/recomputed.

### 56.11. “Chỉ đổi price thì query result cache không cần invalidation”

Sai nếu filter/order/projection phụ thuộc price. Kể cả không phụ thuộc, provider có thể invalidation ở mức query spaces rộng hơn.

### 56.12. “COUNT query không bao giờ cần invalidation”

Sai. COUNT kết quả cũng phụ thuộc inserts/deletes/updates của dữ liệu lọc.

### 56.13. “Query cache luôn tốt khi query phức tạp”

Không. Nếu parameters rất đa dạng hoặc bảng thay đổi liên tục, overhead/invalidation có thể lớn hơn lợi ích.

### 56.14. “Query plan cache hit có nghĩa result cache hit”

Sai. Plan cache giữ kế hoạch/phân tích, không giữ chính result rows.

### 56.15. “Một entity trong L2 luôn có mọi collection”

Sai. Entity regions và collection association regions là những khái niệm khác nhau.

### 56.16. “TTL đủ để bảo đảm dữ liệu nhất quán ngay sau commit”

Không. TTL chỉ giới hạn khoảng tồn tại của entry theo policy, không phải transaction coherence guarantee.

### 56.17. “Provider luôn biết một SQL script bên ngoài đã sửa bảng”

Sai. External writes/DB triggers/stored procedures có thể cần explicit invalidation hoặc không dùng cache.

### 56.18. “Bật READ_WRITE cache strategy là tương đương SERIALIZABLE”

Sai. Cache concurrency strategy không thay thế database transaction isolation hoặc nghiệp vụ locking.

### 56.19. “Cache cùng dữ liệu của mọi tenant là vô hại”

Sai. Partition/key/filter không đúng có thể lộ dữ liệu và gây correctness/security issues.

### 56.20. “Dựa vào latency nhanh hơn để chứng minh query cache hit”

Không đủ. DB buffer, JIT, pooling và statement-plan reuse cũng làm lượt sau nhanh hơn.

---

## 57. Bài thực hành tổng hợp: lựa chọn cache cho Catalog API

Thiết kế hai endpoints:

**Endpoint A:**

```http
GET /api/products/42
```

Nhiệm vụ:

- Đọc Product theo primary key.
- Product ít thay đổi.
- Có nhiều lượt đọc từ nhiều EntityManagers.

**Endpoint B:**

```http
GET /api/products?category=BOOK&minPrice=100&sort=price&page=0
```

Nhiệm vụ:

- Lọc/sort/paginate theo tham số.
- Dữ liệu có thể thêm/sửa/xóa.
- Một phần request có query key trùng lặp.

### 57.1. Đánh giá Endpoint A

L2 entity cache là ứng viên hợp lý nếu Product eligible, cache strategy phù hợp và cần kiểm soát freshness.

Query result cache không phải cơ chế cần thiết nhất cho `find` theo ID.

### 57.2. Đánh giá Endpoint B

Cần biết:

- Có bao nhiêu distinct parameter combinations?
- Trang đầu có được gọi lặp nhiều không?
- Bảng Products update bao nhiêu lần/giờ?
- Cache result có bị invalidate liên tục không?
- Các entities trong query result có thuộc L2 không?
- Số SQL loads sau query cache hit là bao nhiêu?
- Có filters theo tenant/permission không?
- Query trả DTO values hay entities?
- Dữ liệu có thể stale trong bao lâu?

Nếu query key rất đa dạng, ưu tiên index, DTO projection, stable pagination và SQL optimization trước. Nếu có một số category pages hot với key lặp, cân nhắc cache có chọn lọc.

### 57.3. Ra quyết định bằng số liệu

Tạo báo cáo cho cả:

- Warm L2, query cache OFF.
- Warm L2, query cache ON cho selected queries.
- L2 OFF, query cache ON (để quan sát entity SQL loads).
- L2/query cache ON dưới workload có updates.
- Application-level response cache nếu muốn so sánh với caching DTO response.

Không giả định case “mọi cache ON” luôn nhanh nhất.

---

## 58. Câu hỏi ôn tập

1. L1 persistence context có key và phạm vi gì?
2. L1 có tồn tại khi không bật Hibernate L2 không?
3. Vì sao hai lần `find` cùng EM không chứng minh L2 hit?
4. L2 entity cache thường lưu dữ liệu theo khóa nào?
5. L2 có chia sẻ cùng Java managed entity object giữa hai EntityManagers không?
6. Query result cache thường keyed theo những gì?
7. Vì sao query parameters khác nhau làm cache keys khác?
8. Vì sao `setFirstResult`/`setMaxResults` có thể tạo cached results khác?
9. Query plan cache khác query result cache thế nào?
10. `@Cacheable` của Jakarta Persistence dành cho loại cache nào?
11. `SharedCacheMode.ENABLE_SELECTIVE` có ý nghĩa gì?
12. `SharedCacheMode.DISABLE_SELECTIVE` khác `ENABLE_SELECTIVE` thế nào?
13. `EntityManagerFactory.getCache()` trả API cho mục đích gì?
14. `Cache.contains(Product.class,42)` có cho biết query result cache hit không?
15. `Cache.evict(Product.class,42)` có detach Product#42 trong EM khác không?
16. `em.clear()` ảnh hưởng L1, L2 và query cache thế nào?
17. CacheRetrieveMode.BYPASS có bắt buộc bypass L1 không?
18. CacheStoreMode.REFRESH có mục đích gì?
19. Vì sao chuẩn JPA không cung cấp portable query cache switch giống Hibernate?
20. Trong Hibernate, query cache được đánh dấu trên query như thế nào?
21. Hibernate entity `@Cache` khác Jakarta `@Cacheable` ở đâu?
22. Spring `@Cacheable` khác cả hai annotation ORM thế nào?
23. Vì sao L2 hit có thể tăng trong khi JPQL SQL vẫn chạy?
24. Vì sao query cache hit có thể vẫn phát SQL entity loads?
25. Query result cache có nhất thiết chỉ lưu IDs không?
26. Entity cache có tự cache @OneToMany collection membership không?
27. Collection cache khác query result cache như thế nào?
28. Query cache invalidation cần theo dõi điều gì khi bảng Products thay đổi?
29. INSERT Product mới có thể làm cache query cũ sai như thế nào?
30. Đổi Product price có thể làm cache query sai ở những khía cạnh nào?
31. Vì sao COUNT query cũng phải invalidate?
32. Query-space invalidation có thể quá rộng ở điểm nào?
33. Vì sao update thường xuyên khiến query cache ít hit?
34. Bulk JPQL update tác động managed entities đang ở L1 thế nào?
35. Native/external SQL writes có thể gây stale caches vì sao?
36. Cache TTL có bảo đảm dữ liệu đúng ngay sau commit không?
37. Entity cache eviction và query cache eviction khác nhau thế nào?
38. Hibernate statistics có counters nào cho L2 và query cache?
39. Vì sao `stats.clear()` không phải xóa caches?
40. Cache hit rate cao có đủ để kết luận endpoint nhanh không?
41. Vì sao lần chạy thứ hai nhanh hơn không tự chứng minh Hibernate cache hit?
42. Test cold/warm phải dùng EntityManager mới ở đâu?
43. Làm sao phân biệt DB buffer cache với query result cache?
44. Khi nào L2 phù hợp hơn query result cache?
45. Khi nào query cache phù hợp hơn?
46. Khi nào nên không cache result truy vấn đa tham số?
47. Cache theo categoryCode thiếu tenant context có thể gây lỗi gì?
48. Spring method cache cần cơ chế invalidation nào khi JPA commit update?
49. Query cache có thay thế index và pagination design không?
50. Với read-critical dữ liệu tài chính, cần kiểm soát gì ngoài cache?
51. Cache regions riêng cho entity và query giúp quan sát những gì?
52. Vì sao provider version ảnh hưởng API/config query cache?
53. Nếu Product đã bị xóa nhưng cached query result vẫn chứa ID, có thể xảy ra điều gì?
54. Vì sao việc sửa một row ở category TOY vẫn có thể invalidate query BOOK?
55. Khi nào nên dùng DTO projection thay vì trả managed entities trong cacheable query?
56. Nếu client cần tổng kết quả Page, content query cache có tự cache count query không?
57. Một hệ thống nhiều nodes dùng local cache cần kiểm chứng gì?
58. Nếu data freshness SLA là 30 giây, bạn sẽ mô tả cache policy thế nào?
59. Nếu SLA yêu cầu read-after-write strict, chỉ TTL có đủ không?
60. Bạn sẽ viết biên bản test nào để chứng minh cả correctness và performance?

---

## 59. Bảng ghi nhớ cuối bài

| Câu hỏi | Trả lời ngắn |
|---|---|
| Cache gì khi gọi `find(Product,42)`? | L1 trước; L2 có thể giúp giữa các contexts |
| L1 thuộc phạm vi nào? | Persistence context / EntityManager |
| L2 cache theo key nào? | Entity identity, type + PK (+ partition/tenant tùy provider) |
| Query result cache theo key nào? | Query + params + pagination + filters/context |
| L2 tự tránh JPQL SQL? | **Không bảo đảm** |
| Query cache hit tự tránh mọi SQL? | **Không**, entity/association loads có thể còn |
| `@Cacheable` của JPA? | Entity shared-cache eligibility |
| JPA có query result cache annotation portable? | **Không có cơ chế tương đương chung** |
| Hibernate query cache? | Provider extension, opt-in và per-query cacheable |
| Spring `@Cacheable`? | Cache method result, invalidation độc lập |
| `em.clear()`? | Clear/detach L1 trong EM hiện tại |
| `emf.getCache().evict(...)`? | Evict entity shared cache state |
| Evict query result regions? | Provider-specific API |
| CacheRetrieveMode.BYPASS? | Bypass shared cache, không mặc nhiên L1 |
| Entity cache giúp membership query? | Không tự biết tập rows thỏa WHERE |
| Query cache stale vì? | DML/params/dependencies/external writes |
| Entity cache stale vì? | State thay đổi nhưng entry chưa đồng bộ |
| Collection cache? | Membership/state của collection association, khác query result |
| Có nên cache mọi JPQL? | Không |
| Đo thế nào? | SQL logs + L2/query stats + correctness + latency |
| Điều kiện thành công? | Kết quả đúng, hit có ý nghĩa, chi phí/TTL phù hợp |

### Sơ đồ tóm tắt

```text
     em.find(Product.class, id)
                |
                v
       L1 identity map?
         /           \
       HIT          MISS
        |             |
        v             v
     Managed       L2 state?
     instance       /    \
                  HIT    MISS
                   |       |
                   v       v
                Entity   SQL lookup
               instance  by primary key


     JPQL SELECT ... WHERE ...
                |
                v
        QUERY RESULT CACHE?
           /            \
         HIT            MISS
          |               |
          v               v
     Cached IDs/rows    Execute SQL query
          |               |
          +-------+-------+
                  |
                  v
       Materialize entity results
        /          |          \
     L1 hits     L2 hits    DB loads
                  |
                  v
           Application result
```

**Nguyên tắc cuối bài:** **entity cache** trả lời câu hỏi *“đã có state của entity với ID này chưa?”*; **query result cache** trả lời câu hỏi *“đã có tập kết quả của truy vấn với bộ tham số và ngữ cảnh này chưa?”*. Chúng có key, phạm vi, chi phí và chính sách invalidation khác nhau. L1 persistence context là tầng riêng luôn cần hiểu để không chẩn đoán nhầm; cache plan, Spring method cache và database cache lại là những cơ chế khác nữa. Một chiến lược đúng phải đồng thời bảo đảm **tính chính xác sau các đường ghi dữ liệu**, **cô lập tenant/security**, **độ mới phù hợp nghiệp vụ**, và **lợi ích hiệu năng được đo bằng SQL/cache metrics**, chứ không chỉ nhìn thấy một annotation `@Cacheable` hoặc một lần chạy nhanh hơn.

