# Evict, hết hạn và giới hạn việc xóa đệm quá rộng

Bộ nhớ đệm (cache) giúp Hibernate giảm số lần truy vấn database và cải thiện độ trễ cho các dữ liệu được đọc lặp lại. Tuy nhiên, cache cũng tạo ra một câu hỏi quan trọng: **khi dữ liệu nguồn thay đổi, thành phần nào cần bị loại bỏ khỏi cache, trong phạm vi nào và vào thời điểm nào?**

Nếu không vô hiệu hóa dữ liệu cũ khi cần, ứng dụng có thể trả kết quả lỗi thời (*stale data*). Nếu gọi lệnh xóa toàn bộ cache quá thường xuyên, ứng dụng có thể mất gần hết lợi ích caching, đồng thời tạo đột biến truy vấn database khi nhiều request cùng tải lại dữ liệu (*cache stampede*).

Bài học này phân biệt ba thao tác thường bị đánh đồng:

- **Evict/invalidate**: loại bỏ một cache entry hoặc một tập entries để lần đọc sau phải tìm dữ liệu từ nguồn phù hợp.
- **Expiration**: cho entry hết hiệu lực sau thời gian hoặc chính sách của cache provider, ví dụ time-to-live (TTL).
- **Refresh/reload**: đọc lại dữ liệu hiện hành rồi cập nhật object hoặc cache theo chính sách tương ứng.

Trong Hibernate cần phân biệt **first-level cache của Persistence Context**, **second-level cache (L2) dùng chung giữa sessions**, và **query results cache**. Chúng có phạm vi, API và điều kiện nhất quán khác nhau. Một lệnh `EntityManager.clear()` không xóa mọi entry L2; một lệnh `Cache.evict(Customer.class, id)` không làm entity đã được managed trong EntityManager khác tự cập nhật; xóa entity L2 cũng không tự bảo đảm mọi query cache, collection cache hay external cache đều đã nhất quán.

Nguyên tắc xuyên suốt: **chỉ vô hiệu hóa phạm vi nhỏ nhất đủ bảo đảm tính đúng đắn, dựa vào transaction boundary, chiến lược cache và mô hình ghi dữ liệu thực tế**.

## 1. Vì sao cần quản lý eviction?

Giả sử database lưu:

```text
customers
+----+------+--------+
| id | name | status |
+----+------+--------+
| 42 | An   | ACTIVE |
+----+------+--------+
```

Ứng dụng đã đọc Customer#42 và dữ liệu được đưa vào L2. Sau đó một hệ thống khác dùng JDBC trực tiếp cập nhật:

```sql
UPDATE customers
SET status = 'INACTIVE'
WHERE id = 42;
```

Nếu Hibernate không biết thao tác này, lần đọc qua một Persistence Context mới có thể tiếp tục nhận dữ liệu cũ từ L2, tùy cache policy và entry validity.

Để ứng dụng thấy thay đổi, có thể vô hiệu hóa đúng entry:

```java
EntityManagerFactory emf = ...;

emf.getCache().evict(Customer.class, 42L);
```

Nhưng nếu một EntityManager đã load và đang giữ `Customer#42`, lệnh trên **không thay object managed đó**. Muốn lấy lại state trong context hiện tại có thể cần:

```java
em.refresh(customer);
```

hoặc đóng context, mở context mới và tải lại sau khi bảo đảm L2 đã được invalidated.

Tình huống này minh họa ba chủ thể khác nhau:

```text
Database row Customer#42
        |
        +----> Persistence Context A / L1
        |         └─ Customer#42 đang managed
        |
        +----> Hibernate L2 cache
        |         └─ Customer#42 cache entry
        |
        +----> Query results cache (nếu bật)
                  └─ Query keys/results liên quan
```

Xóa một lớp không đồng nghĩa tất cả các lớp còn lại tự mất dữ liệu.

## 2. Ba lớp cache thường gặp

| Lớp | Phạm vi | Đối tượng chính | API quản lý tiêu biểu |
| --- | --- | --- | --- |
| First-level cache (L1) | Một `EntityManager` / Hibernate `Session` | Managed entities, entity entries, snapshots | `detach`, `clear`, `refresh`, Hibernate `Session.evict` |
| Second-level cache (L2) | `EntityManagerFactory` / `SessionFactory`, tùy provider | Entity state, collection cache, natural-id cache | JPA `Cache.evict`, Hibernate `Cache.evictEntityData`, `evictCollectionData` |
| Query results cache | Cache của kết quả truy vấn đã đánh dấu cacheable | Kết quả truy vấn theo query key/params/pagination | Hibernate `evictQueryRegion`, `evictQueryRegions`, query cache settings |

Một số ứng dụng còn có:

- Application cache như Spring Cache (`@Cacheable`, `@CacheEvict` của Spring).
- Redis/cache ở service boundary.
- CDN/browser cache.
- Database buffer cache.
- HTTP response cache.

Những lớp ngoài Hibernate **không tự bị xóa** chỉ vì bạn gọi API của `EntityManagerFactory.getCache()`.

### 2.1. Một truy vấn có thể không chạm tới L2

L2 không phải lúc nào cũng bật hoặc được cấu hình cho mọi entity. Nếu provider L2 chưa được cài đặt, `@Cacheable` không đồng nghĩa tất cả entities đều được lưu ở một cache region thật.

Cũng có thể entity đã ở L1: `em.find(Customer.class, 42L)` có thể trả trực tiếp object managed mà không hỏi L2 hoặc database. Vì vậy các thử nghiệm eviction phải tách rõ **đọc lại trong cùng EntityManager** và **đọc trong một EntityManager mới**.

## 3. Entity minh họa với cấu hình cache

Giả sử có `Customer` và `PurchaseOrder`:

```java
package com.example.domain;

import jakarta.persistence.*;
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;
import org.hibernate.annotations.NaturalId;
import org.hibernate.annotations.NaturalIdCache;

import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
@Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "customer.entity"
)
@NaturalIdCache(region = "customer.natural-id")
public class Customer {

    @Id
    private Long id;

    @NaturalId(mutable = false)
    @Column(nullable = false, unique = true)
    private String email;

    private String displayName;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    @Cache(
        usage = CacheConcurrencyStrategy.READ_WRITE,
        region = "customer.orders"
    )
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {}

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public String getDisplayName() { return displayName; }
    public List<PurchaseOrder> getOrders() { return orders; }

    public void rename(String name) {
        displayName = name;
    }
}
```

```java
package com.example.domain;

import jakarta.persistence.*;
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Table(name = "purchase_orders")
@Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "order.entity"
)
public class PurchaseOrder {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(nullable = false)
    private String orderNumber;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
}
```

Các region được đặt tên rõ:

```text
customer.entity      -> State của Customer theo identifier
customer.orders      -> Cache collection role Customer.orders
customer.natural-id  -> Ánh xạ natural-id để tìm Customer
order.entity         -> State của PurchaseOrder
```

**Các cache regions không phải một vùng duy nhất.** Có thể evict entity entry `Customer#42` mà collection cache của `Customer.orders` vẫn còn entry theo owner key.

`@Cache` ở đây là `org.hibernate.annotations.Cache`, không phải annotation `@Cacheable` của Spring Framework. Khả năng hoạt động phụ thuộc Hibernate cache provider và region factory được cấu hình.

## 4. Cấu hình L2 cache và query cache

Một cấu hình Hibernate thường gồm:

```properties
hibernate.cache.use_second_level_cache=true
hibernate.cache.region.factory_class=jcache
hibernate.cache.use_query_cache=true
```

Đây là ví dụ định hướng cho hệ thống dùng JCache integration. Cần thêm Hibernate `hibernate-jcache` module tương thích, một JCache provider thực tế và cấu hình region/TTL theo provider. Tên strategy/region factory alias có thể khác theo Hibernate major version; nếu alias `jcache` không được hỗ trợ ở phiên bản triển khai, dùng class region factory tương ứng được Javadoc Hibernate ghi nhận.

Với Spring Boot:

```properties
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.cache.use_query_cache=true
spring.jpa.properties.hibernate.cache.region.factory_class=jcache
```

Đây chỉ là bước bật tính năng. Không đủ để bảo đảm một region đã được tạo với TTL hoặc concurrency strategy đúng. Cần kiểm tra dependencies, boot logs và các cache regions thật được tạo.

### 4.1. L2 và query cache có thể bật riêng

- L2 entity/collection caching có thể được dùng mà không cache query results.
- Query result cache cần bật `hibernate.cache.use_query_cache` và đánh dấu những query cụ thể là cacheable.
- Bật query cache toàn hệ thống **không có nghĩa mọi truy vấn tự động được cache**.
- Một query cache hit không bảo đảm mọi entity state đều có sẵn trong L2; cache thường cần resolve identifiers qua L1/L2/database.

### 4.2. Dùng provider đúng version

Hibernate 5, 6 và 7 có những khác biệt về API và caching internals. JCache/Ehcache/Infinispan cũng khác về expiry, clustering và transaction integration. Hãy đối chiếu phiên bản đang triển khai trước khi sao chép một XML/config từ dự án cũ.

## 5. `EntityManager.clear()`: xóa quản lý L1, không phải L2

```java
EntityManager em = emf.createEntityManager();

Customer c = em.find(Customer.class, 42L);
System.out.println(em.contains(c)); // true

em.clear();

System.out.println(em.contains(c)); // false
```

Sau `clear()`:

- `c` là **detached**, không còn được EntityManager này quản lý.
- Dirty checking không tự đồng bộ các thay đổi mới trên `c`.
- Những lazy associations chưa khởi tạo có thể gặp lỗi nếu dùng mà không còn context hợp lệ.
- `clear()` không xóa tất cả L2 entries trong `EntityManagerFactory`.
- `clear()` không bắt mọi EntityManager khác phải bỏ những object managed riêng của chúng.

### 5.1. Thứ tự flush/clear khi có thay đổi

Đừng viết:

```java
Customer c = em.find(Customer.class, 42L);
c.rename("Tên mới");

em.clear(); // Thay đổi đang chờ có thể bị bỏ.
em.flush();
```

Nếu muốn ghi rồi giải phóng context:

```java
c.rename("Tên mới");
em.flush();
em.clear();
```

**Flush không phải commit**. SQL có thể đã được gửi trong transaction, nhưng vẫn có thể rollback. `clear()` không thay thế transaction commit.

### 5.2. `Session.evict(entity)` là thao tác L1 khác

Hibernate Session có thể detach một entity cụ thể:

```java
import org.hibernate.Session;

Session session = em.unwrap(Session.class);
session.evict(c);
```

Về ý nghĩa, đây là thao tác trên Session/Persistence Context, gần với `em.detach(c)`:

```java
em.detach(c);
```

Không nhầm `Session.evict(c)` với `SessionFactory.getCache().evictEntityData(...)` ở L2. Dù cùng dùng từ “evict”, chúng thuộc hai phạm vi khác nhau.

## 6. `EntityManager.detach(entity)` và `refresh(entity)`

Nếu chỉ muốn ngừng quản lý một entity:

```java
em.detach(customer);
```

Nếu muốn đồng bộ trạng thái managed entity với database:

```java
em.refresh(customer);
```

Khác biệt:

- `detach`: tách khỏi L1; không đọc lại DB.
- `refresh`: yêu cầu đọc lại state phù hợp từ database vào managed entity.
- `clear`: detach **tất cả** entities của context.
- `flush`: đồng bộ pending state đến DB trong transaction.
- L2 `evict`: loại entry của shared cache, không cập nhật object Java đã managed.

Một thao tác refresh có thể chịu ảnh hưởng optimistic locking/isolation, cascade refresh, pending changes và cache-store rules. Đừng gọi refresh cho hàng nghìn entities chỉ để “xóa cache”.

### 6.1. `find()` trong cùng context có thể vẫn trả object cũ

```java
Customer first = em.find(Customer.class, 42L);

emf.getCache().evict(Customer.class, 42L);

Customer second = em.find(Customer.class, 42L);

System.out.println(first == second); // Thường true.
```

Evict L2 không phá identity map của `em`. Nếu database được cập nhật ngoài Hibernate, `second` có thể vẫn chứa state cũ giống `first` cho đến khi context được refresh/clear/đóng theo semantics phù hợp.

## 7. JPA `Cache.evict(entityClass, primaryKey)`: xóa đúng một ID

API chuẩn:

```java
import jakarta.persistence.Cache;

Cache cache = emf.getCache();

cache.evict(Customer.class, 42L);
```

Mục tiêu là loại state của entity type + identifier khỏi shared second-level cache theo JPA provider.

Lần đọc sau qua một **Persistence Context mới** có thể phải lấy dữ liệu từ DB hoặc những lớp cache/provider khác tùy configuration.

### 7.1. `Cache.contains()` giúp kiểm tra sự hiện diện, không chứng minh freshness

```java
boolean present =
    emf.getCache().contains(Customer.class, 42L);
```

Giá trị `true` cho biết provider coi entity đã có entry trong shared cache theo API. Nó **không chứng minh** dữ liệu trong cache trùng DB mới nhất, và không phải kiểm tra cache của mọi node khác trong cluster.

### 7.2. Scope của khóa

Đúng hơn:

```java
cache.evict(Customer.class, 42L);
```

so với:

```java
cache.evict(Customer.class);
```

nếu chỉ Customer#42 bị cập nhật ở ngoài ORM và provider/cache policy cho phép key-level eviction.

Một lần evict theo class có thể loại **mọi entry Customer** trong L2 — tác động rộng hơn nhiều lần.

## 8. JPA `Cache.evict(entityClass)` và `Cache.evictAll()`

JPA hỗ trợ:

```java
Cache cache = emf.getCache();

cache.evict(Customer.class); // Mọi entry entity type Customer.
cache.evictAll();            // Mọi cached entity trong phạm vi JPA Cache.
```

Dùng theo mức độ cần thiết:

| API | Phạm vi ý định | Chi phí/rủi ro |
| --- | --- | --- |
| `evict(Customer.class, 42L)` | Một entity theo ID | Hẹp nhất trong nhóm |
| `evict(Customer.class)` | Tất cả Customer entries | Làm giảm hit rate của cả entity type |
| `evictAll()` | Toàn bộ entity cache theo API JPA | Rất rộng, có thể tạo read miss spike |

**Không mặc định `Cache.evictAll()` xóa mọi Hibernate collection/query/natural-id region hay mọi cache ngoài ORM.** API JPA nói về second-level cache của entities; Hibernate có API bổ sung cho các loại region khác.

### 8.1. Khi nào class-level eviction hợp lý?

Ví dụ:

- Migration cập nhật một tỷ lệ lớn records của cùng entity type bên ngoài Hibernate.
- Khóa bị thay đổi theo cách không thể liệt kê đầy đủ IDs bị ảnh hưởng.
- Chính sách security/consistency yêu cầu mọi Customer entries phải được nạp lại, và có kế hoạch vận hành tránh thundering herd.
- Một sự kiện hiếm không có đủ metadata để chọn keys cụ thể.

Không nên gọi `cache.evict(Customer.class)` sau mỗi lần thay đổi một customer profile nếu đã có ID chính xác.

## 9. Hibernate `SessionFactory.getCache()` quản lý nhiều region hơn JPA Cache

Hibernate cung cấp API riêng:

```java
import org.hibernate.SessionFactory;
import org.hibernate.Cache;

SessionFactory sf = emf.unwrap(SessionFactory.class);
Cache hibernateCache = sf.getCache();
```

Các thao tác minh họa:

```java
hibernateCache.evictEntityData(Customer.class, 42L);

hibernateCache.evictEntityData(Customer.class);

hibernateCache.evictCollectionData(
    "com.example.domain.Customer.orders",
    42L
);

hibernateCache.evictNaturalIdData(Customer.class);

hibernateCache.evictQueryRegion("orders.search");

hibernateCache.evictQueryRegions();
```

Ý nghĩa:

- `evictEntityData(Customer.class, 42L)`: entity cache entry theo ID.
- `evictEntityData(Customer.class)`: mọi entity entries của Customer trong region tương ứng.
- `evictCollectionData(role, ownerId)`: collection cache entry của role + owner.
- `evictNaturalIdData(Customer.class)`: natural-id cache data của entity type.
- `evictQueryRegion(name)`: một named query-results cache region.
- `evictQueryRegions()`: các query-result regions liên quan.

Chữ ký và tên package của API có thể khác ở Hibernate major version cũ; đối chiếu Javadoc chính xác. Các thao tác có nghĩa trong phạm vi regions được Hibernate/cache provider quản lý, không phải xóa mọi Redis/Spring cache trên toàn hệ thống.

### 9.1. Dùng role name chứ không dùng tên bảng khi evict collection

Collection role thường là:

```text
com.example.domain.Customer.orders
```

đây là **entity name + property collection**, không phải table name `purchase_orders`.

Nếu ứng dụng đổi entity name, field hoặc mapping role, tên region/role phải được kiểm tra lại.

### 9.2. Natural ID cache là một loại state khác

Nếu Customer dùng:

```java
@NaturalId(mutable = false)
private String email;
```

và có `@NaturalIdCache`, Hibernate có thể cache ánh xạ natural key → identifier.

Evict entity by ID **không nên được coi là lời hứa mọi natural-id cache keys đều được reset theo cách phù hợp với mọi external write**. Nếu external process thay đổi natural IDs, cần xét natural-id region riêng, và tốt nhất không sửa natural-id bất biến trái mapping.

## 10. Thứ tự ưu tiên: ID → owner key → region → all

Khi cần invalidation, xác định **đối tượng nào thực sự thay đổi**.

Ví dụ external system cập nhật `Customer#42.displayName`:

```java
cache.evict(Customer.class, 42L);
```

Nếu nó thêm/xóa một order của Customer#42 ngoài Hibernate, có thể cần xem cả collection cache:

```java
hibernateCache.evictCollectionData(
    "com.example.domain.Customer.orders",
    42L
);
```

Nếu `PurchaseOrder#901` bị sửa thuộc tính:

```java
hibernateCache.evictEntityData(PurchaseOrder.class, 901L);
```

Với query cache có cached scalar report về tổng order, có thể phải invalidated query-result region liên quan hoặc dùng cơ chế query-space synchronization phù hợp.

### 10.1. Bảng lựa chọn scope

| Thay đổi ngoài ORM | Cache có khả năng stale | Eviction mục tiêu |
| --- | --- | --- |
| Đổi tên Customer#42 | `Customer#42` L2 | Entity by ID |
| Thêm Order#901 cho Customer#42 | Collection `Customer.orders` theo owner; query results | Collection owner key và query cache phụ thuộc |
| Đổi total Order#901 | `PurchaseOrder#901` L2; cached aggregate queries | Entity by ID và query-result invalidation phù hợp |
| Thay email natural-id | Customer entity, natural-id index | Entity entry và natural-id region/keys theo cơ chế phù hợp |
| Bulk update 100 Customer IDs biết trước | 100 entity entries | Evict từng ID, hoặc region nếu giá trị/chi phí vận hành cho phép |
| Migration sửa hầu hết Customer | Nhiều Customer entries | Region-level eviction có kế hoạch |
| Deployment schema/type incompatible | Cache payload/regions liên quan | Roll/version cache regions hoặc vùng bị ảnh hưởng |
| Thay dữ liệu trong DB nhưng không biết bảng/IDs | Không xác định | Cần bổ sung change metadata/CDC; broad invalidation chỉ là fallback |

L2 eviction theo ID không có nghĩa Hibernate tự cập nhật query cache scalar kết quả. Cần phân biệt loại cached state.

## 11. Cache collection khác cache entity con

Trong ví dụ:

```java
@OneToMany(mappedBy = "customer")
@org.hibernate.annotations.Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "customer.orders"
)
private List<PurchaseOrder> orders;
```

Collection cache thường lưu thông tin cần thiết để tái tạo membership/association collection, ví dụ các identifiers của các order thuộc một customer. Nó không đồng nghĩa toàn bộ thuộc tính của mỗi `PurchaseOrder` đã được lưu cùng một entry collection.

Một sơ đồ:

```text
customer.entity:
  Customer#42 -> state Customer

customer.orders:
  Customer#42 -> membership [901, 902, 903]

order.entity:
  Order#901 -> state Order#901
  Order#902 -> state Order#902
  Order#903 -> state Order#903
```

Nếu external SQL thêm Order#904 cho Customer#42, cache collection `Customer.orders` có thể vẫn trả `[901,902,903]`.

Evict chỉ:

```java
hibernateCache.evictEntityData(PurchaseOrder.class, 904L);
```

không bảo đảm membership collection được làm mới. Cần invalidation của owner collection entry nếu ứng dụng có cache region này:

```java
hibernateCache.evictCollectionData(
    "com.example.domain.Customer.orders",
    42L
);
```

Ngược lại, evict collection membership không nhất thiết evict state của mọi child entity. Mỗi mục tiêu có region/key riêng.

### 11.1. Quan hệ hai chiều và thay đổi FK

Nếu một order chuyển từ Customer#42 sang Customer#43 ngoài ORM, cả hai owner collections có thể đổi:

```java
hibernateCache.evictCollectionData(role, 42L);
hibernateCache.evictCollectionData(role, 43L);
```

Và entity `PurchaseOrder` liên quan cũng cần được invalidated nếu FK được lưu trong entity state. Đây là ví dụ điển hình cần biết **old owner ID và new owner ID** để chỉ xóa đúng khóa.

## 12. Query results cache là gì?

Đối với một Hibernate HQL query:

```java
import org.hibernate.Session;
import org.hibernate.query.Query;

Session session = em.unwrap(Session.class);

Query<PurchaseOrder> query = session.createQuery("""
    select o
    from PurchaseOrder o
    where o.customer.id = :customerId
      and o.status = :status
    order by o.id
    """, PurchaseOrder.class);

query.setParameter("customerId", 42L);
query.setParameter("status", "PAID");

query.setCacheable(true);
query.setCacheRegion("orders.search");

List<PurchaseOrder> orders = query.getResultList();
```

Khi `hibernate.cache.use_query_cache=true`, Hibernate có thể lưu kết quả truy vấn theo query key gồm SQL/HQL semantics, bind parameters, pagination/filters và các yếu tố liên quan.

Query cache không phải một map đơn giản kiểu `Customer#42 -> object`. Nó có thể lưu identifiers cho entity results và/hoặc giá trị scalar để trả lại khi query cùng điều kiện được gọi.

### 12.1. Query cache không tự động đồng nghĩa ít SQL

Nếu cached query results chứa entity identifiers nhưng entity state không có trong L2, Hibernate vẫn có thể phải thực hiện SQL để resolve entities.

Ngược lại, nếu query projection trả scalar aggregate và kết quả được cache, dữ liệu scalar đó có thể stale nếu database thay đổi ngoài Hibernate mà không có invalidation.

### 12.2. Query cache không cache mọi query

Bật:

```properties
hibernate.cache.use_query_cache=true
```

là bật khả năng. Một query cụ thể cần:

```java
query.setCacheable(true);
```

hoặc một hint/cách cấu hình tương đương đúng Hibernate version. Đừng giả định mọi repository query được cache chỉ nhờ một property.

## 13. Xóa một query region thay vì tất cả query cache

Nếu query đã đặt region:

```java
query.setCacheRegion("orders.search");
```

thì khi cần xóa kết quả của nhóm query đó:

```java
sf.getCache().evictQueryRegion("orders.search");
```

Phạm vi hẹp hơn:

```java
sf.getCache().evictQueryRegions();
```

vì `evictQueryRegions()` vô hiệu hóa query-result regions ở mức rộng.

Một hệ thống có thể có:

```text
orders.search
orders.statistics
reference-data.lookups
dashboard.summary
```

Khi external update chỉ ảnh hưởng dashboard summary, không nên tự động xóa tất cả lookup/search regions nếu có cách biết chính xác region liên quan.

### 13.1. Evict region không đồng nghĩa evict một query key

Với những API phổ biến trên Hibernate Cache, đơn vị xóa query results thường là **region**, không phải arbitrary một query key + tham số. Khi muốn cực kỳ tinh vi ở mức từng query result, cần thiết kế riêng/invalidation mechanism phù hợp thay vì cố suy tạo một API không có.

Region design vì thế là một quyết định quan trọng: query có tần suất thay đổi/invalidation khác nhau nên được nhóm vào regions phù hợp.

## 14. Hibernate theo dõi invalidation của query cache thế nào?

Để tránh dùng kết quả truy vấn cũ sau ORM updates, Hibernate dùng cơ chế theo dõi những query spaces/tables bị thay đổi và timestamp/invalidation metadata tương ứng. Tên region và implementation chi tiết có thể khác theo phiên bản, nhưng ý tưởng:

```text
Query results cache
  Query key -> cached results + thời điểm có hiệu lực

Update-timestamps/invalidation metadata
  Bảng/query space -> mốc thay đổi gần đây

Khi đọc cache:
  nếu query spaces đã thay đổi sau kết quả cache -> miss/requery
```

Các thay đổi **được Hibernate biết và đồng bộ đúng** có thể làm invalidation query cache tự động theo query spaces bị ảnh hưởng.

**Thay đổi ngoài Hibernate** (JDBC trực tiếp, dịch vụ khác, migration chạy ngoài app) không chắc cập nhật metadata này. Đây là lý do phải có cơ chế invalidation theo sự kiện hoặc TTL/đảm bảo consistency khác.

### 14.1. Không cấu hình timestamps region hết hạn sớm hơn query results

Một nguyên tắc trong tài liệu Hibernate: cache của update timestamps/invalidation metadata không được cho hết hạn trước những query results còn có thể sống. Nếu metadata biến mất sớm, Hibernate có thể không còn đủ thông tin để xác định cached query result đã stale hay chưa.

Với các provider có TTL/TTI, cần kiểm tra chính xác cách Hibernate dùng timestamps region theo version và **không tùy tiện đặt TTL ngắn trên nó**. Region chứa query results và region chứa update timestamps có vai trò khác nhau.

### 14.2. Evict query cache không làm mới L1

Ngay cả khi query cache đã được evict, query có thể trả managed entity cùng ID đang ở L1 với state cũ. Kiểm tra consistency cần xét cả object lifecycle và transaction isolation.

## 15. Normal ORM update thường tự phối hợp với cache

Ví dụ:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

Customer c = em.find(Customer.class, 42L);
c.rename("Tên mới");

tx.commit();
```

Khi update đi qua Hibernate và các cache strategies được hỗ trợ/cấu hình đúng, Hibernate có cơ chế cập nhật hoặc invalidate L2 entry và query cache spaces liên quan như một phần quản lý lifecycle/transaction.

**Không nên luôn thêm `Cache.evictAll()` sau mọi `save()`/`commit()`**:

- Làm thừa hoặc phá lợi ích của chiến lược consistency đã có.
- Giảm hit rate không cần thiết.
- Tạo tải database đột biến.
- Không giải quyết những lớp khác như HTTP cache hay local business cache.

Điểm cần xác minh là cache concurrency strategy, query caching và transaction provider phù hợp với pattern ghi của ứng dụng. Invalidation thủ công quan trọng nhất khi dữ liệu **bị thay đổi ngoài đường đi Hibernate có thể theo dõi** hoặc ở những tình huống application-specific.

## 16. Bulk HQL/JPQL DML và native SQL khác nhau

Một bulk HQL:

```java
int updated = em.createQuery("""
    update Customer c
    set c.displayName = :name
    where c.id in :ids
    """)
    .setParameter("name", "New display name")
    .setParameter("ids", List.of(42L, 43L))
    .executeUpdate();
```

không đi qua dirty checking từng managed entity như khi gọi `c.rename()`.

Hibernate thường biết entity/query spaces bị bulk HQL update và có cơ chế cache invalidation tương ứng; nhưng các object `Customer#42`, `Customer#43` đã nằm trong L1 của EntityManager hiện tại vẫn có thể giữ state cũ.

Với native SQL:

```java
em.createNativeQuery("""
    update customers
    set name = ?
    where id = ?
    """)
    .setParameter(1, "New name")
    .setParameter(2, 42L)
    .executeUpdate();
```

khả năng Hibernate biết chính xác các query spaces bị thay đổi phụ thuộc đường gọi, synchronization info, provider/version. Hibernate có thể chọn invalidation rất rộng khi thiếu thông tin; trong các tình huống khác, một external SQL writer nằm ngoài Hibernate sẽ hoàn toàn không thể phát event cho cache.

### 16.1. Cung cấp synchronized query spaces cho NativeQuery

Khi dùng Hibernate NativeQuery:

```java
import org.hibernate.Session;
import org.hibernate.query.NativeQuery;

Session session = em.unwrap(Session.class);

NativeQuery<?> q = session.createNativeQuery("""
    update customers
    set name = :name
    where id = :id
    """);

q.addSynchronizedEntityClass(Customer.class);
q.setParameter("name", "New name");
q.setParameter("id", 42L);

q.executeUpdate();
```

API synchronized entity/query spaces giúp Hibernate biết operation liên quan tới những bảng/entity spaces nào để xử lý flush và cache invalidation theo cơ chế của version đó.

Với native query **ngoài ORM** (JDBC từ process khác), lời gọi này không thể chạy; phải có cơ chế thông báo thay đổi riêng.

### 16.2. Tránh clear toàn cache chỉ vì native query

Khi một native query có thể khai báo synchronized spaces, điều này thường tốt hơn việc chấp nhận coarse invalidation vì Hibernate không biết query ảnh hưởng bảng nào. Nếu có IDs bị thay đổi, ứng dụng còn có thể invalidation theo ID cho những cache regions cụ thể trong một flow được thiết kế rõ.

Không mặc định SQL native luôn chỉ invalidate một row; query spaces là thông tin cấp bảng/space, còn key-level invalidation đòi hỏi biết những identifiers đã thay đổi.

## 17. Ghi ngoài Hibernate: invalidation theo sự kiện

Ví dụ:

```text
Service A (JDBC writer) ---> UPDATE customers
                           |
                           v
                       DB COMMIT
                           |
                           v
                     Change event:
                     CustomerUpdated(id=42)
                           |
                           v
                Service B (Hibernate cache)
                     evict Customer#42
```

Các cách truyền sự kiện:

- Transactional outbox.
- CDC (change-data-capture) từ database log.
- Message broker với retry/deduplication.
- Event nội bộ trong cùng process sau commit, nếu tất cả writers cùng process.
- Scheduled reconciliation nếu không có real-time event.

Thông tin tối thiểu cho invalidation chính xác thường gồm:

- Entity/table type.
- Primary key/tenant key.
- Loại thay đổi: INSERT/UPDATE/DELETE.
- Old/new relationship owner IDs nếu collection membership thay đổi.
- Version/sequence hoặc một cơ chế xử lý out-of-order events.
- Những query/materialized views phụ thuộc vào thay đổi.

### 17.1. Event thiếu ID làm eviction rộng hơn cần thiết

Event dạng:

```text
"Customer table changed"
```

chỉ đủ để biết một region bị ảnh hưởng, không đủ để xóa `Customer#42`. Nếu hệ thống thường xuyên nhận event như vậy, buộc phải evict toàn Customer region, làm mất rất nhiều hit rate.

Event dạng:

```text
CustomerUpdated(tenantId=5, customerId=42)
```

cho phép invalidation theo khóa chính xác hơn, nếu provider API/tenant key model hỗ trợ.

### 17.2. After-commit không giải quyết mọi race

Nếu evict **trước khi database transaction commit**, một reader có thể miss cache, đọc **giá trị cũ** từ database, rồi đưa dữ liệu cũ trở lại cache. Do đó invalidation thường cần gắn với thời điểm commit đã thành công hoặc phối hợp transaction-aware cache strategy.

Nhưng ngay cả khi phát event after-commit, nếu event delivery bị trễ, readers vẫn có một khoảng stale window. Cần nói rõ consistency model và xử lý retries/out-of-order events; không hứa tuyệt đối zero-stale với asynchronous invalidation.

## 18. Eviction và transaction boundary

Có ba thời điểm cần phân biệt:

```text
(1) UPDATE được thực hiện trong DB transaction
(2) DB COMMIT thành công
(3) Cache entry bị invalidated trên node(s)
```

Nếu (3) xảy ra quá sớm, có nguy cơ read-repopulate từ dữ liệu chưa commit.

Nếu (3) xảy ra quá muộn, người đọc có thể nhìn thấy stale entry giữa (2) và (3).

Một số cache concurrency strategies/providers hỗ trợ transactional hoặc locking behavior riêng để thu hẹp khoảng race trong các updates do Hibernate quản lý. Với external writers, phải thiết kế protocol invalidation phù hợp — ví dụ outbox/CDC, versioned keys, hoặc consistency boundary qua DB.

### 18.1. Không gọi `evictAll()` bên trong transaction để “chắc chắn”

```java
tx.begin();
updateOneCustomer();
emf.getCache().evictAll();
tx.commit();
```

Cách này có thể:

- Xóa quá nhiều entries.
- Tạo cache misses trước khi commit.
- Cho readers nạp lại dữ liệu cũ.
- Không làm mới những entities đang managed trong các sessions khác.

Giải pháp đúng không phải “evict càng rộng càng an toàn”; phải đồng bộ **đúng khóa và đúng thời điểm**.

## 19. TTL: hết hạn theo thời gian sống

*Time-to-live (TTL)* quy định một cache entry có thời gian sống tối đa kể từ mốc mà provider xác định (thường creation/update).

Ví dụ policy ở cache provider:

```text
region: customer.entity
TTL: 10 phút
```

Nếu entry được ghi vào lúc 10:00:

```text
10:00  Cache put Customer#42
10:05  Cache hit
10:10  Entry hết hạn theo TTL policy
10:11  Đọc lại -> cache miss -> DB load
```

Đây là minh họa. Một số providers thực hiện expiry **lazy** khi truy cập entry; số khác có background cleanup. “Expired” không có nghĩa JVM lập tức thu hồi mọi byte chính xác tại thời điểm TTL vừa hết.

### 19.1. TTL không thay thế consistency khi cần cập nhật tức thời

Nếu DB đổi ở 10:01 nhưng TTL còn tới 10:10, cache có thể phục vụ state cũ thêm khoảng chín phút, trừ khi có eviction/invalidation khác.

Vì vậy:

- Dữ liệu tham khảo ít thay đổi có thể chấp nhận TTL dài.
- Trạng thái quyền truy cập, tồn kho, hạn mức hoặc thông tin cần nhất quán chặt phải có chiến lược mạnh hơn TTL đơn thuần.
- TTL có thể là **mạng an toàn bổ sung** cho những invalidation events bị mất, không phải lời hứa không có stale data.

### 19.2. TTL đặt ở provider, không chỉ ở annotation Hibernate

`@Cache(usage=READ_WRITE, region="customer.entity")` nói về cache strategy và region, không tự định nghĩa “entry này hết hạn sau 10 phút”.

Expiry policy thường nằm ở JCache/Ehcache/Infinispan configuration hoặc policy backend tương ứng. Các providers khác nhau có định dạng XML/YAML/Java config khác nhau; không có một thuộc tính Hibernate chung `hibernate.cache.ttl=600` áp dụng mọi region/provider.

## 20. TTI và TTL khác nhau

*Time-to-idle (TTI)* cho entry hết hạn nếu không được truy cập trong một khoảng thời gian. TTL thường giới hạn vòng đời từ creation/update, độc lập với số lần đọc.

| Tiêu chí | TTL | TTI |
| --- | --- | --- |
| Mốc tính | Tuổi entry theo policy | Thời gian không được dùng |
| Entry “nóng” được đọc liên tục | Vẫn có thể hết TTL | Có thể tiếp tục sống |
| Rủi ro stale khi không có invalidation | Bị giới hạn theo tuổi entry | Entry nóng có thể tồn tại rất lâu |
| Phù hợp | Giới hạn stale window theo thời gian | Giữ hot entries, bỏ cold entries |
| Do ai cấu hình? | Cache provider | Cache provider |

Nếu dữ liệu có thể bị sửa ngoài Hibernate, **TTI đơn thuần có thể rất nguy hiểm** cho hot keys: mỗi lần đọc lại gia hạn thời gian tồn tại, khiến entry cũ tiếp tục sống.

Có thể dùng kết hợp TTL + TTI nếu provider hỗ trợ và đã xác định rõ semantics.

## 21. Eviction theo dung lượng khác expiration

Cache provider có thể evict entries vì capacity:

```text
Max entries/weight reached
       |
       v
Evict một số entry theo policy
```

Đây là eviction để quản lý memory, không nhất thiết liên quan dữ liệu cũ.

- LRU/LFU hoặc policies tương tự chọn entries ít được dùng.
- TTL/TTI chọn entries theo thời gian.
- Manual eviction chọn entries theo logic ứng dụng.
- ORM invalidation chọn entries theo thay đổi persistence state.

Một entry bị loại vì capacity có thể hoàn toàn đang chính xác; lần đọc sau chỉ cần lấy lại.

Một entry còn trong capacity có thể đã stale nếu external writer đổi DB mà không có invalidation.

**Đừng hiểu “cache tự evict khi đầy” như một cơ chế bảo đảm dữ liệu luôn mới.**

## 22. Cache concurrency strategy và phạm vi nhất quán

Hibernate có các chiến lược cache entity/collection như:

| Strategy | Đặc điểm chính | Cân nhắc |
| --- | --- | --- |
| `READ_ONLY` | Phù hợp dữ liệu không đổi | Không dùng cho entity được update thường xuyên |
| `NONSTRICT_READ_WRITE` | Chấp nhận khả năng stale window ở một số trường hợp | Chỉ dùng khi nghiệp vụ chịu được eventual consistency |
| `READ_WRITE` | Cơ chế phối hợp updates/invalidation phù hợp hơn với dữ liệu mutable | Chi phí locking/soft-lock/coordination tùy provider |
| `TRANSACTIONAL` | Dựa vào khả năng transactional cache provider | Không được mọi provider/region hỗ trợ |

Không nên chọn concurrency strategy chỉ dựa vào tốc độ benchmark; phải bắt đầu từ **yêu cầu nhất quán**.

Ví dụ một bảng mã tỉnh/thành ít đổi có thể phù hợp `READ_ONLY`. Một cấu hình người dùng được cập nhật mỗi ngày có thể dùng `READ_WRITE` nếu cache provider hỗ trợ đúng. Một counter cần linearizable reads không thể được bảo đảm chỉ bằng việc đặt TTL 30 giây.

### 22.1. `READ_ONLY` và update ngoại lệ

Dữ liệu thực sự immutable không cần eviction thường xuyên. Nhưng nếu có migration sửa bảng tham chiếu được cache READ_ONLY, cần kế hoạch rolling invalidation/restart/versioned cache region. Không được giả định cập nhật DB ngoài ORM sẽ tự cập nhật entry READ_ONLY trên mọi node.

## 23. Tránh xóa vùng đệm quá rộng sau từng thay đổi

Một anti-pattern:

```java
public void renameCustomer(long id, String name) {
    updateDatabase(id, name);

    emf.getCache().evictAll();
}
```

Nếu chỉ một customer thay đổi, `evictAll()` làm mất hit rate của toàn bộ cached entities, không chỉ Customer#id.

Với ứng dụng có hàng nghìn request/giây:

```text
Mỗi lần update một customer
        |
        v
Evict all entity cache
        |
        v
Hàng loạt requests tiếp theo bị cache miss
        |
        v
Database SELECT tăng đột biến
        |
        v
Cache ấm lại
        |
        v
Lần update kế tiếp evict all lần nữa
```

Đây là cách biến cache thành một hệ thống luôn cold.

### 23.1. Mở rộng scope theo nhu cầu, không theo sự tiện tay

Thứ tự quyết định nên là:

1. Evict đúng entity ID.
2. Evict đúng collection owner key nếu membership thay đổi.
3. Evict đúng natural-id/query region phụ thuộc.
4. Evict entity type/region nếu không thể biết các keys.
5. Evict toàn cache chỉ cho sự kiện đặc biệt với kế hoạch tải lại.

**Không thể bảo đảm mọi dependent region tự được vô hiệu hóa chỉ bằng xóa một entity ID.** Độ chính xác cần dựa vào dependency model và cơ chế ORM/provider thực sự dùng.

## 24. Thiết kế cache regions để hỗ trợ invalidation hẹp

Một hệ thống có thể chia:

```text
Region: customers.core
  - Customer state

Region: customers.orders
  - Collection membership

Region: orders.core
  - Order state

Region: orders.search
  - Query results phục vụ tìm đơn

Region: dashboard.daily
  - Aggregate query results

Region: reference.country-codes
  - Lookup data ít thay đổi
```

Nếu tất cả query cache dùng chung default region, khi cần invalidation theo nghiệp vụ ở một nhóm query, bạn có thể phải xóa một vùng quá rộng.

Nếu phân chia quá nhiều regions, cấu hình và quan sát lại phức tạp. Chọn region theo:

- Mức thay đổi dữ liệu.
- Cùng dependency/invalidation policy.
- TTL/TTI khác nhau.
- Throughput, size và hot keys.
- Khả năng vận hành provider và metrics.

Không coi region name là ranh giới security; cache key còn phải chứa đủ tenant/context thông tin theo provider/application design.

## 25. Phân biệt Spring `@CacheEvict` với Hibernate L2 eviction

Spring Framework cũng có:

```java
@org.springframework.cache.annotation.CacheEvict(
    cacheNames = "customerDetails",
    key = "#customerId"
)
public void invalidateCustomerView(Long customerId) {
    // ...
}
```

Annotation này làm việc với **Spring Cache abstraction** và `CacheManager` đã cấu hình. Nó không tự động tương đương với:

```java
emf.getCache().evict(Customer.class, customerId);
```

Ứng dụng có thể có cả hai:

```text
Spring Cache "customerDetails"
      |
      └─ CustomerView DTO

Hibernate L2 "customer.entity"
      |
      └─ Entity state Customer#42
```

Khi dữ liệu thay đổi:

- Spring Cache có thể cần evict DTO view.
- Hibernate L2 có thể cần evict entity entry nếu thay đổi ngoài ORM.
- Query cache có thể cần invalidation độc lập.
- HTTP/browser cache có thể còn response cũ.

### 25.1. `allEntries=true` ở Spring cũng là broad eviction

```java
@CacheEvict(
    cacheNames = "customerDetails",
    allEntries = true
)
```

loại mọi entries của Spring cache region đó, không phải chỉ một customer. Khi có ID, ưu tiên key-level eviction nếu nghiệp vụ cho phép.

### 25.2. Redis không tự trở thành Hibernate L2 cache

Redis có thể được dùng cho Spring Cache hoặc làm backend cho một Hibernate-compatible provider/integration. Chỉ vì ứng dụng có Redis không có nghĩa Hibernate đang dùng Redis làm L2.

Để biết cache nào bị evict, kiểm tra **CacheManager/RegionFactory thực tế** và vị trí API được gọi.

## 26. Multi-node deployment và distributed invalidation

Ví dụ hai application nodes:

```text
Node A:
  EntityManagerFactory A
  L2 cache A

Node B:
  EntityManagerFactory B
  L2 cache B

          Shared database
```

Nếu Node A gọi:

```java
emfA.getCache().evict(Customer.class, 42L);
```

lệnh này tác động cache mà Node A's provider quản lý. Nếu mỗi node dùng local-only cache, Node B có thể vẫn giữ Customer#42 cũ.

Có thể cần:

- Distributed/cluster-aware cache provider với invalidation/replication.
- Pub/Sub invalidation events tới mọi nodes.
- Versioned cache keys hoặc shared coherent cache.
- TTL làm fallback.
- Traffic routing/consistency boundary cho các thao tác cần read-after-write.

### 26.1. Không mặc định “cache shared” có nghĩa zero-stale

Một distributed cache có thể có replication/invalidation asynchronous. Node B vẫn có thể đọc entry cũ trong một khoảng thời gian. Cần xác định consistency guarantees của provider và cơ chế lỗi mạng.

### 26.2. Node restart khác eviction toàn cluster

Restart Node A có thể làm mất L1 và local L2 trên node đó, nhưng không xóa tất cả entries ở distributed cache hoặc Node B. Không dùng “restart giải quyết stale data” làm chiến lược invalidation lâu dài.

## 27. Cache stampede sau broad eviction

Nếu cache region chứa hot data bị xóa toàn bộ:

```text
Evict 100.000 keys
      |
      v
10.000 requests đồng thời
      |
      v
10.000 cache misses
      |
      v
Database chịu tải đột biến
```

Trong thực tế, cùng một hot key có thể bị nhiều request tải lại đồng thời (*thundering herd*).

Các kỹ thuật giảm rủi ro:

- Evict theo ID thay vì all/region.
- Dùng request coalescing/single-flight khi provider/app cho phép.
- Pre-warm một số hot keys sau planned invalidation.
- Stagger/jitter TTL ở application caches nếu phù hợp.
- Giới hạn concurrent DB reads khi hồi phục.
- Dùng circuit breaker/rate limiting thận trọng để không làm mất dữ liệu.
- Theo dõi cache miss spikes và DB CPU/latency.

### 27.1. Không pre-warm trước khi DB commit

Nếu preload cache trước khi transaction update commit, bạn có thể nạp lại dữ liệu cũ. Pre-warm phải được thiết kế theo consistency boundary đúng.

## 28. TTL quá ngắn cũng có thể làm cache vô dụng

Giả sử một region có nhiều entries, mỗi request cách nhau vài phút, nhưng TTL chỉ 2 giây. Tỷ lệ hit có thể gần 0 dù caching được cấu hình thành công.

Ngược lại, TTL 24 giờ có thể giữ dữ liệu stale rất lâu nếu không có event invalidation.

Khi chọn expiry policy, đo:

- Mức độ thay đổi của dữ liệu.
- Tần suất và locality của reads.
- Hit/miss rate từng region.
- Tỷ lệ cache entries bị evict vì expiry/capacity.
- Stale tolerance của business.
- DB query cost và p95/p99 latency.
- Chi phí invalidation events.
- Khả năng hồi phục sau failover/cold start.

**TTL là chính sách theo dữ liệu và business, không phải một con số “tối ưu cho Hibernate” áp mọi region.**

## 29. Cache retrieve/store modes của Jakarta Persistence

JPA có các cache hints cho shared cache:

```java
import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.CacheStoreMode;

Map<String, Object> properties = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS,
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.BYPASS
);

Customer customer = em.find(
    Customer.class,
    42L,
    properties
);
```

Ý định:

- `CacheRetrieveMode.USE`: cho phép lấy từ shared cache.
- `CacheRetrieveMode.BYPASS`: không lấy state từ shared cache cho operation phù hợp.
- `CacheStoreMode.USE`: lưu cache theo policy thông thường.
- `CacheStoreMode.BYPASS`: tránh lưu vào shared cache.
- `CacheStoreMode.REFRESH`: yêu cầu refresh shared cache từ DB theo semantics JPA/provider khi operation áp dụng.

### 29.1. Hints không thay thế refresh L1

Nếu Customer#42 **đã được managed** trong cùng EntityManager, `find()` có thể trả object ở L1 dù truyền cache-retrieve bypass. Muốn chính entity đó đọc lại DB, dùng:

```java
em.refresh(customer);
```

hoặc tải ở một context mới phù hợp.

### 29.2. Hints ảnh hưởng shared cache, không phải mọi query cache

Retrieve/store hints mô tả shared entity cache interactions, còn Hibernate query result cache là một cơ chế riêng. Nếu muốn tắt query caching cho một query:

```java
session.createQuery(hql, Customer.class)
    .setCacheable(false)
    .getResultList();
```

Không dùng một hint chung rồi giả định mọi cache layer đều được bypass trong mọi API/provider.

## 30. `refresh()` có thể cần thiết khi L1 đã stale

Giả sử Customer#42 được load trước khi service khác cập nhật.

```java
Customer customer = em.find(Customer.class, 42L);
```

Một external update đã commit:

```sql
UPDATE customers
SET display_name = 'Tên mới'
WHERE id = 42;
```

Sau đó:

```java
emf.getCache().evict(Customer.class, 42L);
```

lệnh này chỉ tác động L2, nên `customer` đang managed vẫn có thể có `displayName` cũ.

Để đưa lại state:

```java
em.refresh(customer);
```

Không dùng `clear()` khi context đang có những thay đổi của entities khác chưa flush; vì nó detach tất cả.

### 30.1. `refresh()` có thể mất thay đổi chưa flush

Nếu application vừa:

```java
customer.rename("Tên tạm");
```

mà chưa flush, `em.refresh(customer)` có thể ghi đè giá trị trong memory bằng dữ liệu DB. Trước khi refresh cần quyết định rõ **discard local changes hay persist chúng**.

### 30.2. Read-after-write qua transaction khác

Ngay cả khi L2 đã evict, một transaction giữ snapshot cũ ở isolation level như repeatable read có thể tiếp tục thấy state cũ. Cache invalidation **không vượt qua transaction isolation**.

Muốn bảo đảm thấy commit mới, có thể cần kết thúc transaction hiện tại/mở transaction mới hoặc dùng cơ chế consistency phù hợp.

## 31. Evict sau bulk import hay migration

Một migration SQL cập nhật 50.000 Customers ngoài Hibernate:

```sql
UPDATE customers
SET status = 'VERIFIED'
WHERE imported_batch_id = 778;
```

Có hai chiến lược:

**A. Biết IDs affected**

- Query/ghi nhận danh sách IDs được sửa một cách đáng tin cậy.
- Evict những entity keys đó.
- Evict các collection/query regions phụ thuộc nếu cần.
- Phát event tới mọi node nếu L2 local.

**B. Không biết IDs hoặc sửa gần toàn bộ region**

- Evict toàn Customer entity region.
- Chỉ invalidation những query-result regions liên quan.
- Chuẩn bị cho miss spike/pre-warm hot keys.
- Kiểm tra các node distributed cache.
- Giám sát DB sau migration.

Đừng tự động gọi `evictAll()` cho toàn hệ thống nếu chỉ `Customer` thay đổi.

### 31.1. Evict sau commit, không sau mỗi row đang import

Nếu một import cập nhật 50.000 rows, gọi evict sau mỗi UPDATE trước khi commit vừa tốn chi phí vừa tạo race. Tốt hơn là tập hợp changed keys theo chunk/transaction và invalidation sau commit thành công theo hệ thống events/consistency strategy.

Với dữ liệu đã được Hibernate quản lý trực tiếp, nên ưu tiên ORM cache consistency mechanisms thay vì tự duplicate invalidation.

## 32. Chẩn đoán stale cache theo từng lớp

Khi người dùng báo “cập nhật DB nhưng API vẫn trả dữ liệu cũ”, đừng ngay lập tức xóa mọi cache.

Một chuỗi câu hỏi:

1. **Dữ liệu DB có thực sự commit?** Kiểm tra transaction.
2. **Request đọc bằng EntityManager mới hay context tồn tại lâu?** Nếu cùng context, L1 có thể giữ state.
3. **Entity đó có L2 region không?** Kiểm tra `@Cache`, provider và config.
4. **Có query cache không?** Query có `setCacheable(true)`/region nào?
5. **Có collection cache không?** Membership có thể stale.
6. **Có Spring/Redis/HTTP cache không?** Những layers khác cần invalidation riêng.
7. **Write path là ORM hay JDBC/external service?** External writes không nhất thiết báo Hibernate.
8. **Node nào trả dữ liệu?** Local caches có đồng bộ không?
9. **Có transaction isolation snapshot không?** Một transaction cũ có thể chưa thấy commit mới.
10. **TTL/TTI configured ở đâu?** Provider policy có hoạt động như mong đợi không?

### 32.1. Dùng kiểm thử theo giả thuyết

Ví dụ nghi L1:

```java
Customer fromCurrent = em.find(Customer.class, id);
```

So sánh với một `EntityManager` mới sau external commit và targeted L2 eviction. Nếu context mới có dữ liệu đúng còn context cũ sai, L1/transaction visibility là hướng điều tra.

Ví dụ nghi query cache: chạy cùng HQL với `.setCacheable(false)` trong context mới. Nếu kết quả khác cached query, xem query cache invalidation/update timestamps và external writes.

Đây là cách chẩn đoán, không phải chỉ định “bypass cache” vĩnh viễn ở production.

## 33. Hibernate Statistics: đo hit, miss, put và eviction impact

Bật thống kê (ở môi trường phù hợp):

```properties
hibernate.generate_statistics=true
```

Lấy:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sf = emf.unwrap(SessionFactory.class);
Statistics stats = sf.getStatistics();

long l2Hits = stats.getSecondLevelCacheHitCount();
long l2Misses = stats.getSecondLevelCacheMissCount();
long l2Puts = stats.getSecondLevelCachePutCount();

long queryHits = stats.getQueryCacheHitCount();
long queryMisses = stats.getQueryCacheMissCount();
long queryPuts = stats.getQueryCachePutCount();

System.out.println(
    "L2 hits=" + l2Hits +
    ", misses=" + l2Misses +
    ", puts=" + l2Puts
);
```

Chỉ số nên quan sát:

- L2 hit/miss/put theo vùng và theo workload.
- Query cache hit/miss/put.
- Cache eviction/expiration do provider báo cáo.
- SQL SELECT count trước và sau invalidation.
- Database CPU/latency khi broad eviction.
- Cache memory/entry count và capacity evictions.
- Stale-read incidents hoặc độ trễ từ DB commit đến invalidation event.
- Retry/out-of-order events ở distributed systems.

### 33.1. Statistics không phải phép đo tuyệt đối mọi lớp cache

Hibernate Statistics không cho biết Spring Cache/Redis HTTP cache đang hit ra sao, và có thể bị nhiễu khi nhiều transactions/tests dùng chung SessionFactory.

Không thể kết luận stale data chỉ từ hit rate. Một region có hit rate cao nhưng invalidation sai vẫn có thể thường xuyên trả dữ liệu lỗi thời.

### 33.2. Tránh test dựa vào số lần GC/TTL chính xác

TTL có thể thực thi lazy hoặc async. Test nên kiểm soát clock nếu provider cho phép, hoặc đặt expiry policy test phù hợp và xác nhận behavior một cách bền vững thay vì sleep vài mili giây rồi assert timing chính xác tuyệt đối.

## 34. Integration test: evict một entity L2

Test cần cấu hình L2 provider và entity cache thực.

```java
import static org.junit.jupiter.api.Assertions.*;

@Test
void evictOneEntityDoesNotRequireEvictAll() {
    EntityManagerFactory emf = ...;
    Long id = 42L;

    try (EntityManager first = emf.createEntityManager()) {
        Customer customer = first.find(Customer.class, id);
        assertNotNull(customer);
    }

    jakarta.persistence.Cache cache = emf.getCache();

    // Entry có thể đã được put vào L2, tùy chiến lược/provider.
    cache.evict(Customer.class, id);

    assertFalse(cache.contains(Customer.class, id));

    try (EntityManager second = emf.createEntityManager()) {
        Customer loaded = second.find(Customer.class, id);
        assertNotNull(loaded);
    }
}
```

Đoạn này là test body minh họa: cần JUnit fixture, seeded row và cache provider thực. Với Jakarta Persistence version không hỗ trợ EntityManager qua try-with-resources/AutoCloseable, dùng `try/finally { em.close(); }`.

### 34.1. Test phải dùng EntityManager mới

Nếu cả hai lần `find()` ở cùng `EntityManager`, L1 có thể khiến test không hề kiểm tra L2. Đây là lỗi test rất phổ biến.

### 34.2. Test hiện diện không đồng nghĩa test SQL

`cache.contains(...)` kiểm tra tình trạng cache provider báo cho entry đó. Để xác minh một lần đọc sau eviction đã phải đi DB, dùng SQL/StatementInspector metrics hoặc Hibernate Statistics trong môi trường test cô lập.

## 35. Integration test: evict L2 không refresh L1

Một test mô tả sự khác biệt:

```java
EntityManager em1 = emf.createEntityManager();

try {
    Customer managed = em1.find(Customer.class, 42L);
    String before = managed.getDisplayName();

    // Giả định external JDBC connection khác đã UPDATE và COMMIT.
    externalJdbcUpdateAndCommit(42L, "Updated externally");

    emf.getCache().evict(Customer.class, 42L);

    // Managed object trong em1 vẫn có thể giữ state cũ.
    String stillInMemory = managed.getDisplayName();

    em1.refresh(managed);

    assertEquals("Updated externally", managed.getDisplayName());
} finally {
    em1.close();
}
```

`externalJdbcUpdateAndCommit` là helper test cần triển khai bằng một connection/transaction riêng, không phải API có sẵn.

Kiểm thử này phải xét transaction isolation: nếu `em1` đang ở một transaction snapshot cũ, `refresh` có thể không thấy update mới. Để test deterministic, chọn isolation/transaction boundary cho phép đọc commit mới, hoặc mở context/transaction mới.

## 36. Integration test: collection cache và query cache

Cần seed Customer#42 và các PurchaseOrders.

Một flow cho collection membership:

1. EntityManager A load và initialize `customer.getOrders()`.
2. Đóng EntityManager A để dữ liệu có cơ hội vào collection cache.
3. External JDBC INSERT một order mới cho Customer#42, rồi commit.
4. Evict collection owner key qua Hibernate Cache.
5. Mở EntityManager B mới và load collection.
6. Assert membership có order mới.

```java
sf.getCache().evictCollectionData(
    "com.example.domain.Customer.orders",
    42L
);
```

Nếu child entity cũng đã có cached state stale, evict entry entity tương ứng. Không dựa vào collection eviction để cập nhật mọi field child.

Flow cho query cache:

1. Bật query cache và query `.setCacheable(true).setCacheRegion("orders.search")`.
2. Chạy query hai lần trong các context phù hợp và xác nhận cache behavior.
3. Thay đổi DB bằng external writer.
4. Evict **đúng query region** `orders.search`.
5. Chạy lại query với context mới, assert results đúng.

Không chạy song song với các test khác dùng cùng provider region vì cache statistics/invalidation có thể bị nhiễu.

## 37. Tình huống multi-tenant và key isolation

Nếu hệ thống dùng nhiều tenants có thể có cùng `Customer#42` trong hai tenant khác nhau:

```text
Tenant A / Customer#42
Tenant B / Customer#42
```

Cache key đúng phải phân biệt tenant theo cơ chế multi-tenancy provider. Không tự tạo một custom shared cache key chỉ bằng `customerId` nếu có nguy cơ trả dữ liệu cross-tenant.

Khi xử lý external invalidation event:

```text
CustomerUpdated(tenantId=A, id=42)
```

cần biết provider có API eviction gắn tenant context nào và cách cache key của nó được triển khai. Không khẳng định overload chỉ nhận `(Customer.class, 42L)` luôn đủ để nhắm riêng Tenant A trong mọi cấu hình multi-tenancy.

Nếu provider không cung cấp API targeted eviction tenant-aware theo yêu cầu, cần thiết kế adapter hoặc invalidation event phù hợp. Không evict toàn cluster chỉ vì thiếu tenant metadata mà không đánh giá hậu quả.

### 37.1. Cache invalidation cũng là vấn đề bảo mật

Dữ liệu quyền truy cập, cấu hình pricing theo tenant và session revocation có yêu cầu nhất quán khác catalog lookups. Với cache stale có thể lộ dữ liệu/cho phép thao tác trái quyền, nên chọn chiến lược mạnh hơn TTL đơn thuần: kiểm tra authoritative data tại điểm bảo mật hoặc dùng cơ chế invalidation/consistency có bảo đảm rõ.

## 38. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `evict(Customer.class, id)` rồi vẫn thấy giá trị cũ | Entity đang managed trong L1 hoặc transaction snapshot cũ | `refresh`, context/transaction mới theo isolation phù hợp |
| `em.clear()` rồi đọc vẫn có state cũ | L2 entry chưa invalidated | Evict đúng L2 key hoặc sửa update path |
| Evict entity nhưng collection vẫn thiếu child mới | Collection membership cache riêng | Evict collection role + owner ID |
| Query aggregate vẫn trả kết quả cũ | Query result cache chưa invalidated hoặc external write | Evict query region, xem update timestamps/query spaces |
| `Cache.evictAll()` gây DB spike | Xóa cache quá rộng | Invalidate theo ID/region nhỏ hơn, pre-warm khi cần |
| TTL đặt trong `@Cache` không có hiệu lực | Hibernate annotation không tự cấu hình provider expiry | Cấu hình expiry ở cache provider |
| Entry hot không bao giờ hết hạn | Dùng TTI không có hard TTL | Thêm TTL hoặc event invalidation |
| Cache hết hạn nhưng heap không giảm ngay | Expiration lazy/background cleanup | Xem provider eviction/storage metrics |
| Query cache hit nhưng vẫn có SELECT | Resolve entity IDs thiếu L2 state | Xem entity caching và fetch plan |
| ORM update vẫn stale sau native bulk SQL | L1 không đồng bộ hoặc cache spaces không được theo dõi đúng | Clear/refresh, synchronized spaces, test API |
| Node A đã evict nhưng Node B vẫn stale | Cache local và invalidation không phân phối | Cluster-aware provider/pubsub events |
| Natural-id lookup trả ID cũ | Natural-id region bị stale | Invalidate natural-id mapping phù hợp |
| Update SQL ngoài ORM không làm cache miss | Hibernate không thấy external writes | Outbox/CDC/eviction event/TTL |
| Evict trước commit rồi stale được cache lại | Race giữa DB visibility và cache read | After-commit coordination/transactional strategy |
| `@CacheEvict` Spring không xóa L2 | Hai cache abstractions khác nhau | Xóa đúng Spring cache và/hoặc Hibernate L2 |
| L2 hit rate thấp dù cache bật | TTL quá ngắn, capacity thấp, không cache entity phù hợp | Đo region config, hit/miss, workload |
| `evictAll()` không xóa HTTP cache | Cache ngoài Hibernate | Invalidate từng cache layer theo hệ thống |
| Test cache pass dù L2 hỏng | Test tái sử dụng một EntityManager | Dùng context khác và SQL/Statistics metrics |
| Multi-tenant đọc lẫn dữ liệu | Custom cache key thiếu tenant | Đảm bảo key isolation và permission checks |

## 39. Anti-pattern cần tránh

**“Cứ mỗi lần save thì evict toàn bộ cache cho chắc.”** Không. ORM updates có cơ chế phối hợp cache riêng; eviction quá rộng làm mất hit rate và có thể tạo race.

**“Evict một ID là mọi query liên quan tự được refresh.”** Không chắc. Entity L2, collection membership và query results là những cache targets khác nhau.

**“`clear()` giống `evictAll()`.”** Không. Clear là L1 của một EntityManager; evictAll thuộc shared entity cache.

**“`Session.evict()` là lệnh xóa distributed cache.”** Không. Nó detach entity khỏi Session.

**“TTL ngắn đồng nghĩa dữ liệu luôn đúng.”** Không. Vẫn có stale window và các trường hợp transaction isolation.

**“TTI hợp với mọi hot key.”** Không. Entry nóng có thể sống lâu bất kể đã stale nếu không có hard TTL/invalidation.

**“`Cache.contains()` chứng minh database và cache đồng bộ.”** Không. Nó chỉ quan sát sự hiện diện theo API provider.

**“Cache miss sau eviction chắc chắn đọc đúng version mới nhất.”** Không nếu transaction snapshot cũ, DB replica lag, external write chưa commit hoặc reader dùng L1 object cũ.

**“Các node trong cluster luôn tự đồng bộ cache.”** Không. Phụ thuộc provider topology và invalidation protocol.

**“Spring `@CacheEvict` tự xóa Hibernate L2.”** Không. Hai cache managers có thể hoàn toàn độc lập.

**“Xóa cache thường xuyên là cách sửa lỗi dữ liệu.”** Nó có thể che bug trong change events, transaction ordering, security filtering và cache key design. Hãy tìm nguyên nhân gốc.

## 40. Quy trình ra quyết định: evict, refresh hay để hết hạn?

**Bước 1 — Xác định dữ liệu cũ nằm ở đâu.** L1 entity, L2 entity, collection region, natural-id region, query cache, Spring/Redis hay HTTP cache?

**Bước 2 — Kiểm tra writer.** Hibernate managed update, bulk HQL, native SQL, JDBC ngoài ORM, service khác hay migration?

**Bước 3 — Kiểm tra commit và isolation.** DB state đã commit chưa? Request có đang giữ transaction snapshot cũ không?

**Bước 4 — Xác định yêu cầu consistency.** Dữ liệu có thể stale trong vài giây/phút hay phải được đảm bảo read-after-write?

**Bước 5 — Chọn phạm vi nhỏ nhất.** Entity ID trước; collection owner key; natural-id/query region liên quan; entity type/region; toàn cache chỉ khi cần.

**Bước 6 — Xác định thời điểm invalidation.** Tránh evict trước commit nếu có nguy cơ repopulate dữ liệu cũ. Với asynchronous events cần chấp nhận/giảm stale window.

**Bước 7 — Quyết định có cần refresh L1 không.** Evict L2 không sửa object managed hiện tại. Nếu cần đọc state mới ngay, dùng refresh hoặc context/transaction mới phù hợp.

**Bước 8 — Chọn TTL/TTI.** Tùy region, mức thay đổi và độ nhạy của dữ liệu. Không dùng hard TTL ngắn cho timestamps metadata cần sống lâu hơn query results.

**Bước 9 — Xem cluster topology.** Local hay distributed regions, invalidation events có tới mọi nodes không, tenant key có đúng không?

**Bước 10 — Đo tác động.** Hit/miss, SQL SELECT count, DB CPU, p95 latency, stampede và stale-read incidents.

**Bước 11 — Kiểm thử tình huống biên.** External updates, relationship changes, query cache scalar, node A/B, missed event, rollback, concurrency.

**Bước 12 — Giám sát sau triển khai.** Broad invalidation cần logging/rate limit/metric alert và phương án giảm DB load.

## 41. Bài tập tình huống

### Bài 1 — L1 và L2

Một EntityManager đã load Customer#42. Bạn gọi:

```java
emf.getCache().evict(Customer.class, 42L);
```

Sau đó `em.find(Customer.class,42L)` trong **cùng EntityManager** có chắc đọc DB lại không?

**Đáp án:** Không. Entity đã managed trong L1 có thể được trả lại từ identity map. Dùng refresh hoặc context/transaction mới phù hợp nếu cần thấy DB mới.

### Bài 2 — Một customer thay đổi

Chỉ Customer#42 đổi `displayName`. Nên dùng:

```java
cache.evict(Customer.class, 42L);
```

hay:

```java
cache.evictAll();
```

**Đáp án:** Key-level eviction theo ID nếu cache provider và update path cần manual invalidation. Evict toàn bộ là quá rộng.

### Bài 3 — `clear()` trước flush

Bạn sửa managed Customer nhưng chưa flush, rồi gọi `em.clear()`. Điều gì có thể xảy ra?

**Đáp án:** Những thay đổi chưa đồng bộ có thể bị bỏ khi entity bị detach. Nếu cần ghi rồi giải phóng L1, flush trước clear.

### Bài 4 — Thêm order ngoài ORM

External writer thêm một Order vào Customer#42. Evict `PurchaseOrder#newId` đã đủ làm `Customer.orders` cache membership mới không?

**Đáp án:** Không chắc. Collection cache entry theo owner ID có thể cần eviction riêng, đồng thời xem query cache phụ thuộc.

### Bài 5 — Query cache

Query cache region `orders.search` stale sau external update. Có cần `evictQueryRegions()` cho tất cả regions không?

**Đáp án:** Nếu xác định được region, ưu tiên `evictQueryRegion("orders.search")`. Chỉ dùng broad eviction khi cần.

### Bài 6 — TTL 10 phút

Dữ liệu DB đổi sau một phút, không có invalidation event. TTL còn lại chín phút. Cache có thể stale bao lâu?

**Đáp án:** Có thể đến khi entry hết TTL hoặc bị evict bởi cơ chế khác, tùy provider policy. TTL không bảo đảm thấy update ngay.

### Bài 7 — TTI

Một entry được đọc mỗi 10 giây với TTI 1 phút. Nó có thể sống mãi dù DB đã đổi ngoài ORM không?

**Đáp án:** Có thể, nếu TTI được gia hạn theo access và không có hard TTL/invalidation.

### Bài 8 — Spring Cache

Dùng Spring `@CacheEvict(cacheNames="customerDetails")` có chắc xóa Hibernate L2 `customer.entity` không?

**Đáp án:** Không. Spring Cache abstraction và Hibernate L2 là các lớp riêng trừ khi có cấu hình/integration rõ ràng.

### Bài 9 — Two-node

Node A evict local L2 Customer#42; Node B vẫn trả state cũ. Nguyên nhân?

**Đáp án:** Local-only cache/không có distributed invalidation; cần cluster-aware provider hoặc event fanout tới các nodes.

### Bài 10 — Evict trước commit

Transaction cập nhật Customer nhưng evict L2 trước commit; reader khác cache-miss, đọc giá trị cũ rồi cache lại. Đây là lỗi gì?

**Đáp án:** Race giữa transaction visibility và cache repopulation. Cần phối hợp invalidation theo commit/consistency protocol.

### Bài 11 — Natural ID

Email là natural-id có cache riêng. External SQL thay email. Chỉ evict entity L2 ID có đủ không?

**Đáp án:** Không nên giả định. Natural-id mapping cache cũng có thể stale; cần invalidation phù hợp và cân nhắc tính bất biến của natural-id.

### Bài 12 — Query cache timestamps

Vì sao không đặt TTL 2 giây cho update timestamps cache khi query results sống 30 phút?

**Đáp án:** Có nguy cơ metadata invalidation mất trước kết quả query, khiến provider thiếu thông tin về dữ liệu đã đổi; cần chính sách expiry theo Hibernate guide/version.

### Bài 13 — Bulk HQL

Bạn chạy bulk HQL update rồi managed Customer#42 vẫn cũ. Vì sao?

**Đáp án:** Bulk DML không đi qua dirty checking của object đã managed; L1 cần refresh/clear/context mới tùy use case.

### Bài 14 — Capacity eviction

Một region tự evict entry vì đầy bộ nhớ. Điều đó chứng minh entry stale không?

**Đáp án:** Không. Entry có thể hoàn toàn chính xác, bị evict chỉ vì capacity policy.

### Bài 15 — Dashboard stale

Dashboard cache lưu aggregate `count(*)`, entity `Customer#42` vừa bị invalidated. Dashboard tự đổi không?

**Đáp án:** Không chắc. Cached scalar query result cần invalidation theo query spaces/region hoặc cơ chế cập nhật ngoài ORM.

### Bài 16 — Evict theo class

Migration cập nhật 99% Customer entries, danh sách IDs không có. Region-wide eviction có hợp lý không?

**Đáp án:** Có thể là fallback hợp lý nếu cần consistency, nhưng phải chuẩn bị tải lại, đo DB spike và xử lý distributed caches/query dependencies.

### Bài 17 — Security cache

Quyền truy cập user bị thu hồi nhưng DTO trong application cache vẫn còn TTL 24 giờ. Có nên chỉ chờ TTL không?

**Đáp án:** Không nếu nghiệp vụ cần thu hồi có hiệu lực sớm. Cần authoritative permission checks hoặc invalidation mạnh, không trông chờ TTL dài.

### Bài 18 — Đo đúng tác động

Sau `evictAll()` tỷ lệ SQL SELECT tăng mạnh. Nên đo gì để quyết định scope eviction?

**Đáp án:** Hit/miss per region, DB statement/latency, số affected IDs, query cache dependencies và cache stampede. Dùng targeted invalidation nếu có thể.

## 42. Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — Caching](https://docs.hibernate.org/stable/orm/userguide/html_single/#caching): L2 cache, cache concurrency strategies, collection/query caching và invalidation.
- [Hibernate ORM User Guide — Persistence Context](https://docs.hibernate.org/stable/orm/userguide/html_single/#pc): L1 cache, managed/detached entities, `clear`, `detach`, `refresh`.
- [Hibernate ORM Javadoc — `Cache`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/Cache.html): entity, collection, natural-id và query region eviction.
- [Hibernate ORM Javadoc — `Session`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/Session.html): L1 `evict`, `clear`, `refresh`.
- [Hibernate ORM User Guide — Query Cache](https://docs.hibernate.org/stable/orm/userguide/html_single/#caching-query): query results, update timestamps và query cache management.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): shared cache, entity lifecycle, cache interaction modes.
- [Jakarta Persistence 3.2 — `Cache`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/Cache.html): `contains`, `evict(Class, key)`, `evict(Class)`, `evictAll()`.
- [Jakarta Persistence 3.2 — `EntityManager`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/EntityManager.html): `clear`, `detach`, `refresh`, `find`.
- [Jakarta Persistence 3.2 — `CacheRetrieveMode`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/CacheRetrieveMode.html): USE/BYPASS.
- [Jakarta Persistence 3.2 — `CacheStoreMode`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/CacheStoreMode.html): USE/BYPASS/REFRESH.
- [Spring Framework Reference — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): Spring `@CacheEvict` và application caches.
- [JCache JSR-107 Specification](https://jcp.org/en/jsr/detail?id=107): cache expiry policy abstraction và semantics.
- [Ehcache Documentation](https://www.ehcache.org/documentation/3.10/expiry.html): TTL/TTI configuration theo cache provider, cần đối chiếu version.

**Phạm vi phiên bản:** Các API của `EntityManagerFactory.getCache()` thuộc Jakarta Persistence. Hibernate `Cache.evictEntityData`, `evictCollectionData`, `evictNaturalIdData`, `evictQueryRegion` và RegionFactory/JCache integration là Hibernate-specific. TTL/TTI, capacity eviction và cluster semantics phụ thuộc cache provider. Hãy kiểm tra đúng Hibernate/JCache/Ehcache/Infinispan versions của ứng dụng trước khi chọn cấu hình.

## Kết luận

Eviction đúng không phải **xóa càng nhiều càng an toàn**, mà là **vô hiệu hóa đúng lớp cache, đúng khóa, đúng thời điểm và đúng dependency**. `EntityManager.clear()` và `detach()` tác động L1; `EntityManagerFactory.getCache().evict(Entity.class, id)` xóa entity entry ở shared L2; Hibernate bổ sung API cho collection, natural-id và query-result regions. Một object đã managed trong L1 không tự thay đổi chỉ vì L2 bị evict, và cache ở Spring/Redis/HTTP layer cần xử lý riêng.

TTL/TTI giúp giới hạn thời gian sống và quản lý dung lượng nhưng không thay thế consistency khi dữ liệu bị ghi ngoài Hibernate. Cần đặc biệt thận trọng với query-cache update timestamps, các race trước/sau commit, external writes và đồng bộ multi-node.

Hãy bắt đầu bằng **evict theo ID/collection owner key**, mở rộng sang đúng region khi cần, và chỉ dùng `evictAll()` trong những sự kiện thực sự yêu cầu với kế hoạch phục hồi hit rate. Cuối cùng, đo SQL, cache hit/miss, stale-read incidents và DB latency; kiểm thử qua EntityManagers/transactions/nodes tách biệt để chứng minh dữ liệu thật sự được làm mới, thay vì chỉ kiểm tra rằng một lệnh evict không ném exception.
