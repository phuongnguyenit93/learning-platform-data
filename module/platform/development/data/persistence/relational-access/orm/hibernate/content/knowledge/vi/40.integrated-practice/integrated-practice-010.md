# Thực nghiệm bộ nhớ đệm cấp hai với trường hợp dữ liệu đổi ngoài ORM

## 1. Tình huống: database đã thay đổi nhưng ứng dụng vẫn đọc dữ liệu cũ

Một ứng dụng dùng Hibernate để cache thông tin Product. Người dùng mở trang chi tiết và Hibernate tải Product có giá `100.00` vào second-level cache (L2). Sau đó một tiến trình ETL, một service khác hoặc DBA chạy SQL trực tiếp để đổi giá thành `125.00`.

Database hiện chứa `125.00`, nhưng ứng dụng Hibernate vẫn có thể trả về `100.00` từ L2 cache.

Đây là vấn đề **cache invalidation khi dữ liệu thay đổi ngoài ORM**. Hibernate chỉ có thể quản lý cache nhất quán cho những thay đổi mà nó biết hoặc được cache provider thông báo. Một câu SQL chạy từ JDBC connection độc lập, script quản trị, trigger hoặc ứng dụng khác có thể không thông báo cho cache của Hibernate.

Điểm quan trọng là phải phân biệt ba lớp dữ liệu:

- **Persistence context (L1):** các entity đang được quản lý trong một `EntityManager`/`Session`.
- **Second-level cache (L2):** cache chia sẻ giữa các persistence contexts trong cùng cache infrastructure.
- **Query cache:** cache kết quả truy vấn, chẳng hạn danh sách entity IDs hoặc scalar values.

Mỗi lớp có thể giữ dữ liệu cũ theo cách khác nhau. `EntityManager.clear()` chỉ xử lý L1; nó không tự xóa L2 hoặc query cache.

### 1.1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt L1, L2 entity cache, collection cache và query cache.
2. Tái hiện dữ liệu stale sau khi JDBC/native SQL/ETL thay đổi database.
3. Hiểu vì sao Hibernate không tự biết mọi thay đổi ngoài ORM.
4. Dùng JPA `Cache.evict()` và Hibernate `SessionFactory.getCache()` để invalidation.
5. Xử lý entity, collection và query cache theo đúng vùng bị ảnh hưởng.
6. Đặt invalidation sau commit và tránh race condition do xóa cache quá sớm.
7. Thiết kế invalidation giữa nhiều application nodes.
8. Chọn cache concurrency strategy phù hợp với tần suất cập nhật.
9. Bảo vệ `@Version`, audit fields và business invariants khi external writer cập nhật.
10. Dùng `CacheRetrieveMode.BYPASS`, `CacheStoreMode.REFRESH` và cache statistics để chẩn đoán.
11. Viết integration tests chứng minh cache stale và xác nhận invalidation.
12. Quyết định khi nào nên tắt L2 cho entity thường xuyên bị thay đổi ngoài Hibernate.

## 2. L1, L2 và query cache khác nhau thế nào?

### 2.1. First-level cache: persistence context

Mỗi `EntityManager`/Hibernate `Session` có persistence context riêng. Khi entity được load, Hibernate quản lý một instance theo identity trong context đó.

```java
Product first = entityManager.find(Product.class, 42L);
Product second = entityManager.find(Product.class, 42L);

assert first == second;
```

Lần `find` thứ hai có thể trả cùng object mà không truy vấn database. Nếu một câu JDBC bên ngoài thay đổi row, object đang managed vẫn giữ state cũ.

`entityManager.clear()` detach toàn bộ managed entities trong context hiện tại. Đây là thao tác xử lý L1, không phải L2.

### 2.2. Second-level entity cache

L2 cache nằm ngoài một persistence context và có thể được chia sẻ giữa nhiều Sessions thông qua cache provider.

Ví dụ entity được bật cache:

```java
@Entity
@Cacheable
@org.hibernate.annotations.Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog.products"
)
public class Product {
    @Id
    private Long id;

    private String name;
    private BigDecimal price;
}
```

Khi một Session tải Product, Hibernate có thể lấy state từ L2 hoặc đưa state vừa đọc vào L2. Một Session khác có thể sử dụng entry đó.

L2 cache không phải nguồn dữ liệu bền vững. Database vẫn là nơi lưu state có thẩm quyền; L2 là bản sao để giảm database reads.

### 2.3. Collection cache

Hibernate có thể cache membership/state của collection association:

```java
@OneToMany(mappedBy = "category")
@org.hibernate.annotations.Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog.category-products"
)
private Set<Product> products;
```

Collection cache có thể lưu danh sách identifiers hoặc dữ liệu collection theo cơ chế provider. Nếu external SQL thêm/xóa Product khỏi Category hoặc đổi foreign key, collection cache có thể vẫn phản ánh membership cũ.

Evict entity Product không nhất thiết evict collection `Category.products`. Hai vùng cache là hai dữ liệu khác nhau.

### 2.4. Query cache

Query cache lưu kết quả của những queries được bật cache, thường là identifiers hoặc scalar result values; entity state có thể vẫn được lấy từ L2.

Ví dụ:

```java
List<Product> products = entityManager.createQuery("""
    select p from Product p
    where p.category.id = :categoryId
    order by p.name
    """, Product.class)
    .setParameter("categoryId", categoryId)
    .setHint("org.hibernate.cacheable", true)
    .getResultList();
```

Nếu external SQL đổi `category_id`, query cache có thể còn giữ danh sách IDs cũ. Nếu chỉ evict từng Product entity, kết quả query cache cũ vẫn có thể không chứa Product mới hoặc vẫn chứa Product đã chuyển category.

### 2.5. Bảng so sánh

| Cache layer | Phạm vi | Ví dụ dữ liệu stale | Cách xử lý |
|---|---|---|---|
| L1 / persistence context | Một EntityManager/Session | Managed Product vẫn có giá cũ | `refresh()`, `clear()` hoặc transaction mới |
| L2 entity cache | Chia sẻ qua Sessions | Product ID 42 vẫn có state cũ | Evict entity entry/region |
| L2 collection cache | Collection role/owner | Category.products chứa IDs cũ | Evict collection entry/region |
| Query cache | Query result region | Danh sách IDs/filter result cũ | Evict query region hoặc invalidation theo query spaces |
| Database | Nguồn dữ liệu bền vững | State sau external commit | Xác nhận transaction/commit và replication state |

## 3. Vì sao external SQL không tự invalidation L2?

Hibernate quản lý cache thông qua event và các thao tác persistence mà nó thực hiện hoặc nhận biết. Ví dụ khi ứng dụng gọi:

```java
Product product = entityManager.find(Product.class, id);
product.changePrice(new BigDecimal("125.00"));
```

Hibernate theo dõi dirty state, flush SQL và phối hợp cache provider theo concurrency strategy. Nó biết entity type/identifier và các query spaces bị ảnh hưởng.

Nhưng khi một script chạy:

```sql
UPDATE products
SET price = 125.00
WHERE id = 42;
```

qua một connection độc lập, Hibernate không nhận được event tương ứng. Cache provider không tự suy ra mọi bảng và entity đã bị tác động từ một SQL statement mà nó không quan sát.

Các nguồn thay đổi ngoài ORM có thể gồm:

- `JdbcTemplate` hoặc JDBC connection không đi qua Hibernate.
- Một ứng dụng khác dùng cùng database.
- ETL/import jobs.
- Stored procedures chạy từ scheduler.
- Database triggers do một thao tác khác kích hoạt.
- DBA chạy SQL trực tiếp.
- Data migration hoặc backfill scripts.
- CDC/replication jobs ghi dữ liệu.
- Một service dùng ORM khác hoặc native data access framework.

Ngay cả khi external writer dùng cùng database server, nó không tự tham gia vào L2 cache protocol của Hibernate.

### 3.1. Cùng database không có nghĩa cùng cache

Database transaction có thể commit thành công trong khi cache của một ứng dụng vẫn giữ entry cũ. Database không biết cache region của Hibernate trên application node nào cần invalidation, trừ khi kiến trúc chủ động xây dựng cơ chế đó.

### 3.2. Cùng JVM cũng chưa chắc Hibernate biết

Một `JdbcTemplate` trong cùng Spring application có thể dùng cùng DataSource và cùng transaction, nhưng câu SQL vẫn bypass Hibernate dirty checking và L2 cache event path.

Dùng chung transaction giúp atomicity ở database; nó không tự bảo đảm mọi cache regions được đồng bộ.

### 3.3. Trigger cũng là external mutation theo góc nhìn ORM

Một trigger có thể đổi `updated_at`, status hoặc foreign key khi Hibernate ghi một bảng khác. Nếu Hibernate không biết trigger đã thay đổi các rows/entities khác, L2 cache của những entities liên quan có thể stale.

Nếu trigger có side effects tới các bảng cacheable, cần một invalidation policy cho các vùng đó hoặc không cache các entities bị trigger cập nhật.

## 4. Thực nghiệm cơ bản: tái hiện L2 cache stale

Giả sử Product được cache bằng Hibernate L2 và database ban đầu có:

```text
products
+----+----------+--------+
| id | name     | price  |
+----+----------+--------+
| 42 | Keyboard | 100.00 |
+----+----------+--------+
```

### 4.1. Bật L2 cache

Cấu hình khái niệm trong Spring Boot:

```properties
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.cache.region.factory_class=<cache-provider-region-factory>
```

Tên region factory và dependency cụ thể phụ thuộc cache provider/version đang dùng. Hibernate không tự cung cấp một distributed cache backend duy nhất cho mọi ứng dụng; chọn provider tương thích với Hibernate version.

Mapping:

```java
@Entity
@Cacheable
@org.hibernate.annotations.Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog.products"
)
public class Product {
    @Id
    private Long id;

    private String name;
    private BigDecimal price;
}
```

### 4.2. Session A tải Product

```java
Product product = entityManager.find(Product.class, 42L);
System.out.println(product.getPrice()); // 100.00
```

Sau khi Session kết thúc, state có thể được đưa vào L2 theo cache strategy/provider.

### 4.3. External writer cập nhật database

```java
jdbcTemplate.update(
    "update products set price = ? where id = ?",
    new BigDecimal("125.00"),
    42L
);
```

Transaction của JDBC writer commit. Database hiện chứa `125.00`.

### 4.4. Session B đọc lại

Một EntityManager mới tránh việc object cũ còn nằm trong L1:

```java
Product reloaded = entityManager.find(Product.class, 42L);
System.out.println(reloaded.getPrice());
```

Nếu L2 entry chưa bị invalidation, Hibernate có thể trả `100.00` từ cache mà không đọc row mới từ database.

### 4.5. Xác nhận trực tiếp từ database

Đọc bằng JDBC hoặc một transaction với cache retrieval bypass:

```sql
SELECT price
FROM products
WHERE id = 42;
```

Kết quả `125.00` trong database nhưng `100.00` qua Hibernate cho thấy cache stale. Phải bảo đảm lần đọc Hibernate dùng persistence context mới; nếu không, stale state có thể đến từ L1 thay vì L2.

## 5. Phân biệt stale L1 với stale L2 trong thực nghiệm

Để tìm đúng lớp gây lỗi, làm theo thứ tự:

1. Tải entity trong EntityManager A.
2. Giữ lại giá trị và đóng/kết thúc A.
3. External writer cập nhật và commit database.
4. Tạo EntityManager B mới.
5. Đọc entity qua B và quan sát kết quả.
6. Evict L2 entry.
7. Tạo EntityManager C mới rồi đọc lại.
8. So sánh với direct JDBC read.

Diễn giải:

| Kết quả | Nguyên nhân có khả năng |
|---|---|
| Cùng EntityManager trả giá cũ, EntityManager mới trả giá mới | L1 stale, L2 không stale |
| EntityManager mới vẫn trả cũ, sau L2 eviction trả mới | L2 stale |
| Sau eviction vẫn trả cũ, direct SQL trả mới | Kiểm tra L1, query cache, replica lag, transaction snapshot hoặc cache provider |
| Direct SQL cũng trả cũ | External transaction chưa commit, cập nhật sai database/schema hoặc đọc nhầm replica |
| Entity fields mới nhưng danh sách membership cũ | Collection/query cache có thể stale |

Đừng kết luận L2 stale chỉ từ một lần `find()` trong cùng transaction đã load entity trước đó.

## 6. JPA Cache API: evict một entity hoặc toàn bộ entity type

JPA cung cấp `Cache` API thông qua `EntityManagerFactory`:

```java
Cache cache = entityManagerFactory.getCache();

// Evict một entity instance theo primary key.
cache.evict(Product.class, productId);

// Evict mọi cached instances của Product.
cache.evict(Product.class);

// Evict toàn bộ shared cache của persistence unit.
cache.evictAll();
```

### 6.1. Evict một entity entry

Dùng khi biết chính xác ID bị external writer thay đổi:

```java
entityManagerFactory.getCache()
    .evict(Product.class, 42L);
```

Đây là lựa chọn hẹp, tránh xóa cache của các Product khác.

### 6.2. Evict cả entity type

Nếu external SQL update một tập lớn Product IDs và không có danh sách affected IDs đáng tin:

```java
entityManagerFactory.getCache().evict(Product.class);
```

Cách này invalidation toàn bộ cache entries của entity type. Nó đơn giản nhưng có thể tạo cache miss burst và nhiều database reads sau đó.

### 6.3. Evict toàn bộ shared cache

```java
entityManagerFactory.getCache().evictAll();
```

Đây là biện pháp rộng, có thể gây cache stampede hoặc làm giảm hiệu năng trên toàn persistence unit. Chỉ dùng cho tác vụ vận hành có phạm vi rõ, migration lớn hoặc recovery khi không thể xác định regions bị ảnh hưởng.

### 6.4. Cache.evict không clear L1

JPA `Cache.evict()` xử lý shared cache. Nếu EntityManager hiện tại đang giữ Product trong persistence context, getter vẫn có thể trả object cũ.

Khi cần đồng bộ cả L1 và L2:

```java
entityManager.clear(); // L1 hiện tại
entityManagerFactory.getCache().evict(Product.class, productId); // L2
```

Hoặc refresh một entity managed cụ thể nếu phù hợp.

## 7. Hibernate Cache API: evict entity, collection và query regions

JPA Cache API tập trung vào entity shared cache. Hibernate cung cấp API rộng hơn qua `SessionFactory.getCache()`.

### 7.1. Evict entity data

```java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

org.hibernate.Cache cache = sessionFactory.getCache();

// Một Product.
cache.evictEntityData(Product.class, productId);

// Toàn bộ entity region của Product.
cache.evictEntityData(Product.class);
```

Nếu mapping dùng explicit region name, Hibernate API cũng có các overload theo entity name/region tùy version. Đối chiếu JavaDoc đúng Hibernate version trước khi dùng overload cụ thể.

### 7.2. Evict collection data

Giả sử Category có collection cache `products`. Có thể evict collection entry của một Category:

```java
cache.evictCollectionData(Category.class, "products", categoryId);
```

Hoặc evict collection region cho role đó:

```java
cache.evictCollectionData(Category.class, "products");
```

Collection role thường có dạng `fully.qualified.EntityName.collectionProperty`. API Hibernate 6 cung cấp overload theo entity class/role và collection role; xác nhận method signature đúng version dự án.

### 7.3. Evict query cache

Nếu external update có thể thay đổi kết quả của cached queries:

```java
cache.evictQueryRegions();
```

Thao tác này evict query cache regions. Nếu ứng dụng đặt tên region riêng cho query, có thể evict region cụ thể qua API phù hợp:

```java
cache.evictQueryRegion("catalog.product-search");
```

Không evict query cache nếu query caching không được sử dụng hoặc không bị ảnh hưởng. Nhưng nếu external SQL thay đổi predicates, sort keys, membership hoặc scalar results của cached queries, phải có invalidation phù hợp.

### 7.4. Evict mọi cache regions

Hibernate có API evict all regions:

```java
cache.evictAllRegions();
```

Phạm vi rộng hơn một entity entry. Tránh gọi sau mọi external update nhỏ; chọn entity/collection/query regions cần invalidation.

## 8. Entity cache, collection cache và query cache phải được xử lý riêng

Giả sử external SQL thực hiện:

```sql
UPDATE products
SET category_id = 20,
    price = 125.00
WHERE id = 42;
```

Các vùng có thể bị ảnh hưởng:

1. Entity Product#42: field `price` và `category_id` cũ.
2. Collection Category#10.products: vẫn có thể chứa Product#42.
3. Collection Category#20.products: có thể chưa chứa Product#42.
4. Query cache của `Product where category.id = 10`: có thể còn kết quả cũ.
5. Query cache của `Product where category.id = 20`: có thể không chứa ID 42.

Một invalidation policy có thể cần:

```java
cache.evictEntityData(Product.class, 42L);
cache.evictCollectionData(Category.class, "products", oldCategoryId);
cache.evictCollectionData(Category.class, "products", newCategoryId);
cache.evictQueryRegions();
```

Ví dụ này minh họa phạm vi; cần biết `oldCategoryId` trước update và mapping collection thực tế. Nếu không biết owner IDs hoặc ảnh hưởng lan rộng, evict collection region/type liên quan thay vì đoán.

### 8.1. Chỉ evict entity có thể vẫn để collection stale

Nếu query đọc `category.getProducts()` từ collection cache, evict Product#42 không nhất thiết làm Hibernate tải lại membership collection.

### 8.2. Chỉ evict collection có thể vẫn để entity stale

Collection có thể trả đúng IDs nhưng mỗi Product ID vẫn được hydrate từ L2 với giá cũ.

### 8.3. Chỉ evict entity/collection có thể vẫn để query result stale

Query cache có thể trả danh sách IDs hoặc scalar values được tính trước external update. Evict các entity entries không nhất thiết làm query result cache tự biết membership đã đổi.

## 9. Query cache và query spaces

Hibernate query cache thường kết hợp query result regions với timestamps/query-space tracking. Khi Hibernate thực hiện mutation trên các query spaces mà nó biết, cache infrastructure có thể xác định query results nào cần xem là stale.

External SQL bypass Hibernate không tự cập nhật thông tin query spaces/timestamps trong cache. Vì vậy query cache có thể tiếp tục cung cấp result cũ.

### 9.1. Named query cache region

Ví dụ query cacheable:

```java
List<Product> findByCategory(Long categoryId) {
    return entityManager.createQuery("""
        select p from Product p
        where p.category.id = :categoryId
        order by p.name
        """, Product.class)
        .setParameter("categoryId", categoryId)
        .setHint("org.hibernate.cacheable", true)
        .setHint("org.hibernate.cacheRegion", "catalog.product-search")
        .getResultList();
}
```

Khi external SQL thay đổi `category_id`, query region có thể cần eviction:

```java
sessionFactory.getCache()
    .evictQueryRegion("catalog.product-search");
```

Query cache region name phải khớp tên thực tế. Nếu query dùng default region, evict default/query regions theo API/version phù hợp.

### 9.2. Native SQL trong Hibernate có thể khai báo synchronized spaces

Nếu native query chạy qua Hibernate Session, có thể khai báo các entity/tables bị ảnh hưởng:

```java
NativeQuery<?> query = entityManager
    .createNativeQuery("""
        update products
        set price = :price
        where category_id = :categoryId
        """)
    .unwrap(NativeQuery.class);

query.addSynchronizedEntityClass(Product.class);
query.setParameter("price", new BigDecimal("125.00"));
query.setParameter("categoryId", categoryId);

int updated = query.executeUpdate();
```

Synchronized query spaces giúp Hibernate biết các bảng liên quan cho một số hoạt động auto-flush và query-cache invalidation. Đây là Hibernate-specific API.

**Khai báo query spaces không làm mới managed entities trong L1.** Nếu entity đã được load, vẫn cần `refresh()`/`clear()` trước khi tiếp tục dùng state mới.

### 9.3. JDBC ngoài Hibernate không có query-space metadata

```java
jdbcTemplate.update(
    "update products set price = ? where category_id = ?",
    price, categoryId
);
```

Hibernate không nhìn thấy statement này và không tự suy ra query spaces. Ứng dụng phải chủ động invalidation entity/collection/query regions liên quan.

## 10. Thời điểm invalidation: sau commit, không phải trước commit

Một lỗi tinh vi xảy ra khi xóa cache trước khi transaction external writer commit.

Giả sử:

1. Writer A chuẩn bị cập nhật Product từ `100` thành `125`.
2. A evict L2 khi transaction vẫn chưa commit.
3. Reader B cache miss và đọc database.
4. B vẫn thấy `100` vì A chưa commit.
5. B đưa `100` trở lại L2.
6. A commit `125`.
7. Không có lần eviction nào nữa.

Kết quả: L2 lại chứa `100` sau khi database đã commit `125`.

### 10.1. Thứ tự nên dùng

```text
External writer
    |
    | UPDATE products ...
    v
Database transaction
    |
    | COMMIT
    v
Publish invalidation event
    |
    v
Cache nodes evict affected regions/keys
    |
    v
New readers load committed database state
```

Evict sau commit để cache miss kế tiếp đọc được state đã commit.

### 10.2. Nếu external writer và Hibernate dùng cùng Spring transaction

Có thể đăng ký callback `afterCommit`:

```java
@Transactional
public void updateProductWithJdbc(
        Long productId,
        BigDecimal newPrice) {

    jdbcTemplate.update("""
        update products
        set price = ?, version = version + 1
        where id = ?
        """, newPrice, productId);

    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                sessionFactory.getCache()
                    .evictEntityData(Product.class, productId);

                sessionFactory.getCache()
                    .evictQueryRegions();
            }
        }
    );
}
```

Imports cụ thể gồm Spring transaction synchronization APIs và Hibernate `SessionFactory`. Ví dụ này giả định JDBC và JPA tham gia cùng transaction manager/DataSource và `sessionFactory` là instance đang phục vụ application.

Nếu method chạy mà không có transaction synchronization active, callback không thể được đăng ký theo cách này; service phải có transaction boundary rõ.

### 10.3. Callback afterCommit chỉ evict cache của provider mà nó gọi

Nếu ứng dụng có nhiều nodes với local cache, callback trên node A không tự xóa cache của node B. Cần provider cluster invalidation hoặc phát event để các nodes khác xử lý.

### 10.4. Event delivery phải đáng tin

Nếu event publish thất bại sau khi database commit, cache có thể stale. Các cách tăng độ tin cậy:

- Transactional outbox ghi invalidation event trong cùng database transaction.
- CDC đọc committed changes và phát event.
- Message broker có retry/acknowledgement.
- Consumer idempotent vì eviction lặp lại thường an toàn.
- Monitoring event lag và dead-letter queue.
- Reconciliation/periodic region eviction khi phát hiện event bị mất.

Không chỉ gửi message fire-and-forget rồi coi cache đã được đồng bộ.

## 11. Invalidation trong hệ thống nhiều application nodes

Giả sử có ba application nodes:

```text
             Load balancer
             /     |     \
          Node A Node B Node C
            |      |      |
          L2-A   L2-B   L2-C
             \     |     /
                Database
```

Nếu mỗi node có local L2 cache:

1. Node A nhận external update.
2. Node A evict Product#42 khỏi local cache.
3. Node B và C vẫn có entry cũ.
4. Request tiếp theo vào B/C có thể trả giá cũ.

### 11.1. Distributed cache provider

Một số cache providers hỗ trợ clustered invalidation/replication. Cần cấu hình và xác nhận:

- Region có thực sự distributed không?
- Eviction có propagate tới mọi nodes không?
- Propagation là synchronous hay asynchronous?
- Network partition xử lý ra sao?
- Node mới join có state/cache lifecycle thế nào?
- Cache topology và key serialization có tương thích không?

Đừng suy luận rằng dùng Hibernate L2 đồng nghĩa mọi nodes tự chia sẻ invalidation.

### 11.2. Pub/sub invalidation event

External writer có thể phát event:

```json
{
  "eventType": "ProductChanged",
  "entityType": "Product",
  "entityId": 42,
  "version": 18,
  "changedAt": "2026-05-01T10:30:00Z"
}
```

Mỗi node nhận event và evict entry tương ứng:

```java
public void onProductChanged(ProductChanged event) {
    sessionFactory.getCache()
        .evictEntityData(Product.class, event.entityId());

    sessionFactory.getCache()
        .evictQueryRegions();
}
```

Event cần được phát sau commit hoặc qua outbox/CDC. `version` hữu ích để bỏ qua events cũ hoặc theo dõi thứ tự, nhưng việc so sánh version và eviction semantics phải được thiết kế nhất quán.

### 11.3. Evict một key hay toàn region?

- Biết chính xác IDs: evict từng entry.
- Không biết IDs nhưng biết entity type: evict entity region.
- Thay đổi collection membership: evict collection regions liên quan.
- Thay đổi query membership/scalars: evict query regions bị ảnh hưởng.
- Bulk update rất rộng: có thể evict toàn bộ vùng liên quan thay vì phát hàng triệu key events.

Evict toàn region tạo nhiều cache misses; cân nhắc database capacity và cache warm-up sau invalidation.

### 11.4. Node offline hoặc mất event

Một node offline trong thời gian event được phát có thể quay lại với cache cũ nếu provider không bảo đảm state/invalidations khi reconnect. Khi node khởi động lại hoặc mất kết nối event bus, cần:

- Clear/evict regions trước khi nhận traffic.
- Replay invalidation events còn thiếu.
- Dùng version/generation watermark.
- Hoặc vô hiệu hóa cache region trong thời gian recovery.

## 12. Chọn concurrency strategy phù hợp với external writers

Hibernate có các cache concurrency strategies. Chúng điều khiển tương tác giữa ORM sessions và cache provider; không tự biến external SQL thành một Hibernate-aware update.

### 12.1. READ_ONLY

Dành cho dữ liệu gần như bất biến sau khi tạo, ví dụ country codes hoặc catalog reference không đổi thường xuyên.

Nếu external SQL thay đổi entity được cache READ_ONLY, ứng dụng vẫn có thể trả data cũ và strategy này không phải cơ chế đồng bộ external writers. Dữ liệu thực sự mutable không nên được đặt READ_ONLY chỉ vì muốn tăng tốc.

### 12.2. NONSTRICT_READ_WRITE

Cho phép một khoảng stale window trong những tình huống cập nhật ít thường xuyên và chấp nhận dữ liệu cũ tạm thời.

Đây không phải giải pháp invalidation đáng tin cho external writers. Nếu external update không thông báo cache, stale state có thể tồn tại tới khi TTL/eviction tự nhiên.

### 12.3. READ_WRITE

Dùng soft-locking/coordination của cache provider quanh ORM updates để giảm khả năng đọc state không nhất quán trong các luồng được Hibernate quản lý.

Một external JDBC writer không tự tham gia soft-lock protocol đó. Vì vậy READ_WRITE không bảo đảm cache được invalidation khi SQL chạy ngoài ORM.

### 12.4. TRANSACTIONAL

Dựa vào cache provider và transaction integration có khả năng transactional phù hợp. Đây là cấu hình đòi hỏi provider hỗ trợ semantics cần thiết; không thể chỉ bật property rồi có strong consistency giữa database và mọi external writers.

Nếu external writer không tham gia cùng transaction/cache protocol, vẫn phải có cơ chế đồng bộ riêng.

### 12.5. Bảng chọn chiến lược

| Strategy | Use case phù hợp | External update |
|---|---|---|
| READ_ONLY | Dữ liệu bất biến | Không tự cập nhật; external mutation phá giả định |
| NONSTRICT_READ_WRITE | Dữ liệu ít đổi, chấp nhận stale window | Cần TTL/invalidation; stale window có thể kéo dài |
| READ_WRITE | Dữ liệu mutable do Hibernate quản lý | External writer không tham gia soft-lock protocol |
| TRANSACTIONAL | Provider có transactional cache integration | External writer phải tham gia protocol tương thích |

**Chiến lược cache không thay thế invalidation contract.** Khi có external writers, quyết định đầu tiên là cache có còn phù hợp với yêu cầu consistency hay không.

## 13. Cache TTL và expiry không phải strong consistency

Cache provider thường có thể cấu hình:

- Time to live (TTL).
- Time to idle (TTI).
- Maximum entries/size.
- Eviction policy.
- Expiry sau access hoặc write.

TTL giúp giới hạn thời gian entry tồn tại, nhưng không bảo đảm reader luôn thấy giá trị mới ngay sau database commit.

Ví dụ TTL 5 phút có nghĩa entry có thể stale gần 5 phút nếu không có invalidation event. Nó không có nghĩa dữ liệu tự đồng bộ trong 5 phút đầu.

### 13.1. Chọn TTL theo freshness requirement

| Dữ liệu | Freshness requirement | Cách tiếp cận |
|---|---|---|
| Country/reference codes | Ít đổi, stale ngắn chấp nhận được | L2 + TTL dài |
| Product catalog | Đổi theo đợt, cần cập nhật trong vài giây | Event invalidation + TTL dự phòng |
| Inventory/available quantity | Cần rất mới | Không cache L2 hoặc dùng cơ chế consistency chặt |
| Account balance | Tài chính/consistency cao | Tránh stale cache cho quyết định ghi |
| Dashboard aggregate | Có thể trễ một khoảng | TTL/cache riêng với freshness metadata |

### 13.2. TTL là lớp dự phòng

Nếu event invalidation bị mất, TTL có thể giới hạn thời gian stale. Nhưng nếu yêu cầu “ngay sau commit mọi reader phải thấy giá trị mới”, TTL không đủ.

### 13.3. Stale-while-revalidate

Một số hệ thống chấp nhận trả dữ liệu cũ trong lúc refresh nền. Đây là policy sản phẩm cần được xác định rõ, không phải hành vi ngầm của L2. Không dùng stale-while-revalidate cho dữ liệu cần consistency chặt nếu chưa có quyết định nghiệp vụ.

## 14. External updates và @Version

Cache invalidation chỉ xử lý việc đọc state mới. Nó không tự bảo vệ optimistic locking.

Giả sử Product có:

```java
@Version
private long version;
```

Hibernate đã tải Product với `version=7` vào L1/L2. External SQL đổi giá nhưng không tăng version:

```sql
UPDATE products
SET price = 125.00
WHERE id = 42;
```

Một Hibernate transaction khác vẫn giữ entity version 7 có thể phát UPDATE với predicate `version=7`. Vì database version vẫn là 7, update đó có thể thành công và ghi đè giá external writer.

### 14.1. External writer phải tôn trọng version policy

Nếu version column là optimistic-lock token, external SQL nên tăng version atomically:

```sql
UPDATE products
SET price = 125.00,
    version = version + 1
WHERE id = 42;
```

Sau đó ORM update với old version sẽ affected zero rows và có thể phát hiện conflict.

### 14.2. Cache eviction không thay version increment

Evict Product#42 khỏi L2 không làm các managed instances đã tồn tại trong L1 đổi version. Một Session đang mở có thể tiếp tục giữ version cũ.

Do đó, external writer cần phối hợp cả:

1. Database update và version policy.
2. L1 lifecycle của các Sessions đang mở.
3. L2 entity/collection cache invalidation.
4. Query cache invalidation.
5. Multi-node event propagation.

### 14.3. Bulk update nhiều rows

Nếu external SQL thay đổi nhiều entities có `@Version`, cập nhật version cho tất cả rows bị tác động. Nếu không biết rows nào được đổi, có thể cần version increment trong statement:

```sql
UPDATE products
SET status = 'INACTIVE',
    version = version + 1
WHERE last_sold_at < ?;
```

Cần kiểm tra external writers khác cũng tuân thủ cùng convention. Một writer bỏ qua version có thể phá optimistic-lock guarantee của cả hệ thống.

## 15. External writers và audit fields/domain events

Hibernate callbacks và Envers không tự chạy khi một external process thực hiện SQL.

Nếu bảng có:

- `updated_at`.
- `updated_by`.
- `version`.
- Audit history.
- Outbox events.
- Search-index synchronization.
- Derived tables/materialized views.

thì external writer phải tuân theo policy tương ứng.

Ví dụ:

```sql
UPDATE products
SET price = ?,
    updated_at = CURRENT_TIMESTAMP,
    updated_by = ?,
    version = version + 1
WHERE id = ?;
```

Đây mới chỉ là update các cột; nó không tự tạo Envers revision hoặc domain event. Nếu các hệ thống downstream cần biết thay đổi, dùng outbox/CDC hoặc cơ chế audit phù hợp.

### 15.1. Cache invalidation event không nhất thiết là domain event

`ProductCacheInvalidated` chỉ nói cache entry cần bị xóa. Nó không mô tả đầy đủ business action, actor, old/new values hoặc side effects.

Có thể dùng một domain event giàu thông tin để nhiều consumers xử lý, nhưng tách rõ:
- Cache invalidation.
- Audit/compliance.
- Search index update.
- Business notification.

Không dùng một thông điệp eviction đơn giản làm audit trail.

## 16. Bypass L2 cho một lần đọc cần freshness cao

JPA có cache retrieve/store modes. Chúng hữu ích khi cần bỏ qua L2 trong một operation.

### 16.1. CacheRetrieveMode.BYPASS

Yêu cầu provider không lấy entity từ shared cache cho lần load đó.

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);

Product product = entityManager.find(
    Product.class,
    productId,
    hints
);
```

Entity vẫn có thể được trả từ L1 nếu đã managed trong persistence context. Muốn kiểm tra database, hãy dùng EntityManager mới hoặc clear trước khi find.

### 16.2. CacheStoreMode.BYPASS

Không đưa state đọc được vào shared cache:

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS,
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.BYPASS
);

Product product = entityManager.find(
    Product.class,
    productId,
    hints
);
```

Dùng khi một read path cần đọc database mà không làm thay đổi shared cache state.

### 16.3. CacheStoreMode.REFRESH

Nếu muốn đọc database và refresh shared cache entry từ state mới:

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS,
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.REFRESH
);

Product product = entityManager.find(
    Product.class,
    productId,
    hints
);
```

Cách này yêu cầu bỏ qua retrieval cũ và cập nhật shared cache theo dữ liệu được đọc. Cần kiểm tra provider/version behavior và transaction semantics.

### 16.4. Bypass cache không tự giải quyết query/collection cache

Các modes trên áp dụng cho entity cache retrieval/storage của operation JPA tương ứng. Nếu query result hoặc collection cache đang stale, phải xử lý đúng vùng cache đó. Một entity find bypass không bảo đảm query cache membership đã mới.

### 16.5. Không dùng bypass như giải pháp mặc định cho mọi request

Nếu mọi request đều bypass L2, cache không còn đem lại lợi ích nhưng vẫn có complexity. Chỉ dùng cho operation cần freshness cao hoặc diagnostic path có chủ đích.

## 17. Lựa chọn kiến trúc khi có external writers

Có một số mô hình phổ biến.

### 17.1. Mô hình A: Hibernate là writer duy nhất

Tất cả thay đổi đi qua cùng ORM/cache integration.

Ưu điểm:
- Hibernate biết entity changes và query spaces.
- Lifecycle/version/cache strategy có thể phối hợp.
- Dễ kiểm soát transaction boundaries.

Phù hợp khi không có ETL/SQL writers ngoài ứng dụng hoặc mọi thay đổi được đưa qua service layer.

### 17.2. Mô hình B: External writer phát invalidation event

External writer commit database rồi phát event/outbox. Các application nodes evict cache regions/keys liên quan.

Ưu điểm:
- Cho phép nhiều writers.
- Invalidation có thể gần real-time.
- Có thể scale tới nhiều nodes.

Cần giải quyết:
- Event delivery reliability.
- Event ordering/duplication.
- Node offline.
- Invalidation scope.
- Race giữa commit và consumer.
- Cache provider propagation.

### 17.3. Mô hình C: CDC-based invalidation

Change Data Capture đọc transaction log/binlog/WAL rồi phát events sau commit.

Ưu điểm:
- Có thể quan sát nhiều nguồn ghi khác nhau.
- Không yêu cầu mọi writer tự publish event.
- Event phản ánh changes đã commit theo CDC semantics.

Cần giải quyết:
- Mapping table changes thành entity/collection/query regions.
- Transaction ordering.
- Schema evolution.
- Event lag và replay.
- Bulk update tạo lượng event lớn.
- Định danh primary key/tenant.

### 17.4. Mô hình D: Không dùng L2 cho entities mutable ngoài ORM

Nếu không thể bảo đảm invalidation đáng tin, bỏ L2 cho entity/collection bị external writers thay đổi.

Ưu điểm:
- Tránh stale shared-cache entries.
- Ít phụ thuộc event delivery.
- Semantics dễ hiểu hơn.

Chi phí:
- Tăng database reads.
- Có thể cần tối ưu query/index/read model.
- Có thể cache các reference data độc lập khác.

### 17.5. Mô hình E: TTL với stale window được chấp nhận

Phù hợp với dữ liệu không nhạy về freshness. Document TTL và maximum stale window, theo dõi cache age và có cơ chế force refresh khi cần.

Không dùng TTL như bảo đảm strong consistency.

## 18. Thực nghiệm multi-node và cache invalidation

Giả sử hai nodes A/B có L2 cache riêng hoặc distributed regions.

Quy trình kiểm thử:

1. Node A load Product#42 để populate cache.
2. Node B load Product#42 để populate cache.
3. External writer commit giá mới.
4. Phát invalidation event.
5. Node A nhận event và evict entry.
6. Node B nhận event và evict entry.
7. Gửi request đọc qua từng node.
8. Xác nhận cả hai node thấy giá mới.
9. Tắt một node trong lúc event được phát, restart node.
10. Xác nhận node khởi động lại không phục vụ entry stale.

### 18.1. Kiểm tra event lặp

Gửi cùng invalidation event hai lần. Eviction thường nên idempotent; kết quả không được gây lỗi hoặc làm cache hỏng.

### 18.2. Kiểm tra event đến sai thứ tự

Ví dụ Product version 12 và 13 được cập nhật liên tiếp. Nếu event version 12 đến sau event 13, không nên để consumer làm sống lại state cũ. Evict-only event thường an toàn hơn việc ghi payload event cũ vào cache; nếu cache được cập nhật trực tiếp từ event payload, phải so version trước khi put.

### 18.3. Kiểm tra mất kết nối

Ngắt message broker/network trong lúc external writer commit. Xác nhận outbox/CDC retry và node không phục vụ stale data vượt freshness contract.

### 18.4. Kiểm tra cache stampede

Evict toàn region có thể khiến nhiều requests cùng lúc miss và truy vấn database. Đo load sau invalidation burst, sử dụng provider-specific single-flight/locking/TTL jitter nếu phù hợp.

## 19. Cache statistics và công cụ chẩn đoán

Bật Hibernate Statistics trong test/diagnostic profile:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Đọc counters:

```java
Statistics statistics = entityManagerFactory
    .unwrap(SessionFactory.class)
    .getStatistics();

long hits = statistics.getSecondLevelCacheHitCount();
long misses = statistics.getSecondLevelCacheMissCount();
long puts = statistics.getSecondLevelCachePutCount();
long queryCacheHits = statistics.getQueryCacheHitCount();
long queryCacheMisses = statistics.getQueryCacheMissCount();
```

Tên counters và semantics cần đối chiếu Hibernate version đang dùng.

### 19.1. Đo trước và sau invalidation

Một test có thể:

1. Reset Statistics.
2. Đọc Product để populate cache.
3. Đọc lại trong EntityManager mới.
4. Xác nhận L2 hit tăng.
5. External update.
6. Evict entity entry.
7. Đọc lại.
8. Xác nhận cache miss/load mới hoặc put theo provider behavior.

Không khẳng định mỗi lần đọc nhất thiết có một hit/put nếu provider có access strategy, transaction timing hoặc cache settings khác.

### 19.2. Không dùng Statistics toàn cục trong tests song song

Statistics thường ở cấp SessionFactory. `clear()` có thể ảnh hưởng test/request khác. Chạy test cache-count tuần tự hoặc dùng instrumentation/provider metrics có scope phù hợp.

### 19.3. Quan sát cả cache provider metrics

Ngoài Hibernate counters, theo dõi:

- Region size/entry count.
- Hit/miss/put/eviction.
- Expiration count.
- Cache memory/heap/off-heap.
- Replication/invalidation latency.
- Network errors.
- Rebalance/reconnect events.
- Cache provider operation failures.

Hibernate Statistics không cung cấp mọi metric của distributed cache provider.

## 20. Integration test: external JDBC update làm L2 stale rồi evict

Ví dụ test khái niệm. Cần một L2 provider đang hoạt động và Product được đánh dấu cacheable.

```java
@SpringBootTest(properties = {
    "spring.jpa.properties.hibernate.cache.use_second_level_cache=true",
    "spring.jpa.open-in-view=false"
})
class ExternalWriterCacheIT {

    @Autowired
    private EntityManagerFactory emf;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private TransactionTemplate transactionTemplate;

    @Test
    void evictingL2MakesExternalChangeVisible() {
        Long id = seedCommittedProduct("100.00");

        // EntityManager mới: load Product và đưa state vào L2.
        transactionTemplate.execute(status -> {
            Product product = entityManager().find(Product.class, id);
            assertThat(product.getPrice())
                .isEqualByComparingTo("100.00");
            return null;
        });

        // External writer commit database update.
        jdbcTemplate.update(
            "update products set price = ? where id = ?",
            new BigDecimal("125.00"),
            id
        );

        // Evict shared entity entry sau khi external update đã commit.
        emf.getCache().evict(Product.class, id);

        // Transaction/EntityManager mới đọc state từ database.
        BigDecimal price = transactionTemplate.execute(status ->
            entityManager().find(Product.class, id).getPrice()
        );

        assertThat(price).isEqualByComparingTo("125.00");
    }
}
```

Đây là cấu trúc minh họa; helper `entityManager()` đại diện cho EntityManager transaction-scoped được inject qua Spring, và `seedCommittedProduct` phải commit trước các bước đo. Trong test thực tế cần bảo đảm L2 cache thực sự bật, provider được cấu hình, entity mapping cacheable và không có outer test transaction giữ L1 state.

### 20.1. Test chứng minh stale trước khi evict

Để tái hiện đầy đủ, đọc Product trong một transaction mới sau external update nhưng trước eviction, xác nhận provider trả entry cũ nếu cache strategy/provider đang cho phép scenario đó. Sau đó evict và đọc lại.

Không nên viết assertion stale cứng cho mọi provider/configuration vì cache provider có thể có expiry/invalidation riêng; test mục tiêu phải xác nhận behavior của hệ thống đang triển khai.

### 20.2. Test L1 riêng

Trong một transaction, load entity rồi external JDBC update. Ngay cả khi evict L2, managed object vẫn có thể stale. Test riêng `refresh()` hoặc `clear()` để phân biệt L1 và L2.

### 20.3. Test collection membership

Tạo Category A/B, cache cả hai collections. External SQL đổi `products.category_id`. Evict Product entity thôi chưa đủ; test collection cache và query cache sau khi evict đúng regions.

## 21. Integration test: CacheRetrieveMode và CacheStoreMode

Để đọc database mà không lấy stale entity từ L2:

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS,
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.BYPASS
);

Product product = entityManager.find(
    Product.class,
    productId,
    hints
);
```

Trước khi chạy, dùng EntityManager mới hoặc clear persistence context. Nếu entity đã managed trong L1, cache retrieve mode không buộc Hibernate bỏ managed instance hiện có.

Để load database state rồi refresh shared cache:

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS,
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.REFRESH
);
```

Test cần xác nhận:
- Kết quả trả về đúng state đã commit.
- L2 entry cũ được thay thế theo provider semantics.
- Một EntityManager mới tiếp theo đọc state mới.
- Query/collection cache liên quan được invalidation riêng nếu cần.

## 22. Race conditions trong invalidation

Cache invalidation không chỉ là gọi `evict()`. Thời điểm và thứ tự event rất quan trọng.

### 22.1. Evict trước commit

Reader có thể cache lại old database state trước khi writer commit. Đây là race đã mô tả ở phần 10.

### 22.2. Evict sau commit nhưng event bị trễ

Trong khoảng từ database commit đến lúc consumer evict, reader có thể lấy entry cũ. Nếu yêu cầu freshness tuyệt đối, asynchronous invalidation tạo một stale window không thể loại bỏ chỉ bằng event bus.

Các lựa chọn:
- Không cache entity đó.
- Đồng bộ invalidation trước khi xác nhận operation hoàn tất, với protocol phù hợp.
- Đọc trực tiếp database cho freshness-critical paths.
- Dùng version/fencing token để ngăn state cũ được chấp nhận.
- Chấp nhận và document bounded staleness nếu nghiệp vụ cho phép.

### 22.3. Evict rồi request cũ put state cũ trở lại

Một Session bắt đầu trước external update có thể đang đọc state cũ; sau khi cache bị evict, Session đó có thể hoàn thành và đưa stale state trở lại cache tùy timing/provider strategy.

Các giải pháp mạnh hơn cần coordination/version-aware cache writes, transaction isolation và provider semantics phù hợp. Đừng giả định một lệnh eviction đơn lẻ loại bỏ mọi in-flight readers.

### 22.4. Version/generation-based invalidation

Có thể gắn version hoặc generation number vào event/cache protocol. Khi consumer nhận event mới hơn, nó tăng generation hoặc evict key. Cache fill từ một read thuộc generation cũ phải bị từ chối nếu protocol hỗ trợ.

Đây thường là logic ở application/cache layer hoặc provider integration, không phải tính năng tự động có sẵn chỉ bằng `@Cache`.

## 23. Bulk external updates và invalidation scope

Một ETL job có thể đổi 200.000 Products. Evict từng ID sau update có thể tạo lượng event lớn và phức tạp.

### 23.1. Evict toàn entity region

Nếu phần lớn Product rows thay đổi, evict Product region có thể đơn giản hơn. Sau đó cache được populate dần theo reads.

### 23.2. Evict collection regions

Nếu category membership thay đổi rộng, collection region liên quan cần invalidation. Nếu không biết owner IDs, evict toàn collection role có thể là lựa chọn an toàn hơn.

### 23.3. Evict query regions

Nếu query cache chứa queries phụ thuộc bảng products, cần evict các query regions liên quan hoặc toàn bộ query cache nếu không thể xác định chính xác.

### 23.4. Tránh invalidation storm

Evict quá nhiều regions cùng lúc có thể làm database quá tải bởi cache misses. Có thể:

- Chạy maintenance window hoặc giới hạn traffic.
- Warm lại một số read models sau update.
- Chia update/invalidation theo partition.
- Dùng TTL jitter và cache provider stampede protection.
- Tạm bypass cache cho workload liên quan.
- Theo dõi DB connection pool và latency trong quá trình warm-up.

## 24. Database replication và đọc từ replica

Một nguyên nhân dễ nhầm với L2 stale là replication lag.

Giả sử external writer commit trên primary, nhưng Hibernate datasource đọc từ replica chưa nhận transaction đó. Ngay cả sau khi evict L2, query miss có thể đọc replica và vẫn thấy dữ liệu cũ.

Phân biệt:

- Direct read trên primary trả state mới.
- Read trên replica trả state cũ.
- L2 hit trả state cũ.
- L1 managed object trả state cũ.

Nếu hệ thống dùng read/write splitting, invalidation consumer cần hiểu nguồn đọc. Với read-after-write consistency, có thể route request tới primary trong một khoảng thời gian hoặc dùng replication position/LSN token để chờ replica catch up.

Evict L2 không giải quyết replication lag.

## 25. Khi nào nên tắt L2 cho entity bị external writers cập nhật?

Nếu external writes thường xuyên, không có event đáng tin cậy hoặc yêu cầu freshness chặt, cân nhắc không cache entity đó.

Ví dụ:

```java
@Entity
@Cacheable(false)
public class InventoryBalance {
    @Id
    private Long productId;

    private long availableQuantity;
}
```

Hoặc không đặt Hibernate `@Cache` trên entity/collection này.

### 25.1. Không nhất thiết tắt L2 toàn ứng dụng

Có thể chỉ loại khỏi L2 những entities mutable bị external writers tác động, trong khi vẫn cache:
- Country/reference tables.
- Product metadata ít thay đổi.
- Immutable lookup entities.
- Collections không bị thay đổi ngoài ORM.

Tách cache policy theo domain và freshness requirement.

### 25.2. Cache ở application layer cũng có cùng bài toán

Nếu chuyển từ Hibernate L2 sang Redis/Caffeine/custom cache, external update vẫn cần invalidation. Vấn đề không biến mất khi thay công nghệ cache; chỉ thay cơ chế key, eviction và propagation.

### 25.3. Cache ít lợi ích nếu luôn phải bypass

Nếu mọi read đều yêu cầu `CacheRetrieveMode.BYPASS`, cân nhắc bỏ L2 cho entity thay vì giữ một cache không được dùng.

## 26. Checklist thiết kế external-writer invalidation

Trước khi bật L2 cho một entity, trả lời:

1. Có những writer nào ngoài Hibernate?
2. Chúng cập nhật bảng/cột nào?
3. Có trigger/stored procedure thay đổi bảng liên quan không?
4. Entity cache region nào bị ảnh hưởng?
5. Collection roles nào bị ảnh hưởng bởi FK/membership changes?
6. Query cache regions nào chứa kết quả phụ thuộc các bảng đó?
7. External writer có biết primary keys/owner IDs bị đổi không?
8. Có increment `@Version` theo policy không?
9. Audit fields và domain events được tạo bằng cách nào?
10. Invalidation xảy ra sau commit bằng cơ chế nào?
11. Event delivery có retry/outbox/CDC không?
12. Mọi application nodes có nhận invalidation không?
13. Node offline/restart được đồng bộ ra sao?
14. Có stale window bao lâu?
15. TTL có phải fallback không?
16. Freshness-critical paths có bypass cache không?
17. L1 contexts đang mở được xử lý thế nào?
18. L2 provider strategy có phù hợp không?
19. Cache stampede sau eviction được kiểm soát ra sao?
20. Có integration tests với external SQL và multi-node không?

## 27. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| EntityManager hiện tại trả state cũ | L1 managed entity stale | `refresh()` hoặc `clear()` |
| EntityManager mới vẫn trả state cũ | L2 entity entry stale | Evict entity entry/region |
| Entity fields mới nhưng collection membership cũ | Collection cache stale | Evict collection role/owner region |
| Query vẫn trả IDs cũ | Query cache stale | Evict query region/regions |
| `clear()` xong vẫn thấy state cũ | L2/query cache hoặc replica lag | Xác định cache layer, bypass/evict và đọc primary |
| Evict trước commit rồi cache lại state cũ | Reader repopulate từ database chưa commit | Invalidation sau commit |
| Node A mới, Node B cũ | Local caches không propagate eviction | Distributed invalidation/event bus |
| External update không tăng version | Optimistic lock có thể bị bypass | External writer tăng version atomically |
| Cache stale tới TTL | Không có invalidation event | Event/CDC/outbox hoặc bỏ L2 |
| Cache eviction làm DB quá tải | Region eviction/cache stampede | Warm-up, rate limit, provider protection |
| JDBC update xong query cache vẫn cũ | Hibernate không biết query spaces | Evict query region hoặc CDC invalidation |
| Trigger đổi bảng liên quan nhưng cache không đổi | ORM không biết trigger side effect | Explicit invalidation hoặc bỏ cache vùng đó |
| Test stale không ổn định | Cache provider expiry/transaction/test context khác nhau | Cô lập provider config và cache stats |
| Evict L2 nhưng getter vẫn cũ | Object còn managed trong L1 | Refresh/clear context hiện tại |
| Sau restart node dữ liệu vẫn cũ | Cache persisted/off-heap hoặc startup warm-up | Clear/reconcile cache trước nhận traffic |
| External update trên primary nhưng read vẫn cũ | Replica lag | Route read-after-write tới primary hoặc chờ replication |
| Cache invalidation event bị mất | Fire-and-forget publish | Transactional outbox/CDC, retry và monitoring |
| Một Product mới không xuất hiện trong category list | Collection/query cache membership stale | Evict collection và query regions |
| Product cũ vẫn xuất hiện sau khi chuyển category | Query/collection membership stale | Invalidate cả old/new owners và affected query regions |
| Bulk update gây lock contention | Một statement tác động quá nhiều rows | Chia batch có kiểm soát và đo lock duration |

## 28. Bài tập thực hành

**Bài 1 — Bật L2.** Cấu hình cache provider tương thích, đánh dấu Product cacheable và đọc một Product trong hai EntityManagers.

**Bài 2 — External JDBC update.** Cache Product giá 100, dùng JdbcTemplate đổi thành 125, mở EntityManager mới và quan sát cache behavior.

**Bài 3 — Phân biệt L1/L2.** Thử đọc trong cùng EntityManager, EntityManager mới và sau L2 eviction.

**Bài 4 — JPA Cache API.** Evict một Product ID, toàn bộ Product entity type và toàn shared cache; so cache misses.

**Bài 5 — Collection cache.** Cache Category.products, đổi Product.category_id bằng SQL và kiểm tra old/new collections.

**Bài 6 — Query cache.** Cache query Product theo category, external update membership và kiểm tra query region trước/sau eviction.

**Bài 7 — Invalidation timing.** Evict trước commit, cho reader chạy trong lúc writer chưa commit rồi quan sát stale repopulation. Sau đó chuyển eviction sang afterCommit.

**Bài 8 — Spring afterCommit.** Dùng TransactionSynchronization để evict entity/query regions sau JDBC update trong cùng transaction.

**Bài 9 — Multi-node.** Chạy hai application instances với cache riêng, external update và phát invalidation event đến cả hai.

**Bài 10 — Event failure.** Mô phỏng broker downtime; dùng outbox/CDC retry và xác nhận cache cuối cùng được evict.

**Bài 11 — Version.** External SQL đổi Product nhưng không tăng version; thử ORM update từ stale entity. Sau đó thêm version increment và xác nhận optimistic conflict.

**Bài 12 — Cache modes.** Dùng CacheRetrieveMode.BYPASS + CacheStoreMode.BYPASS để đọc database; thử CacheStoreMode.REFRESH để cập nhật L2.

**Bài 13 — TTL.** Thử TTL khác nhau và đo maximum stale window khi không có event invalidation.

**Bài 14 — Bulk ETL.** Cập nhật hàng nghìn Product, evict region và đo database load/cache warm-up.

**Bài 15 — Trigger.** Tạo trigger cập nhật audit/related table, xác định cache regions cần invalidation.

**Bài 16 — Replica lag.** Nếu môi trường hỗ trợ read replica, so sánh stale L2 với stale replica sau external commit.

**Bài 17 — Cache-disabled comparison.** Tắt L2 cho InventoryBalance và đo trade-off freshness/DB load.

**Bài 18 — Recovery.** Tắt một node trong lúc event được phát, restart và xác nhận node không phục vụ cache stale.

## 29. Câu hỏi tự kiểm tra

**1. Vì sao external SQL có thể làm L2 stale?**

Vì Hibernate không nhận được event/query-space information từ writer ngoài ORM để invalidation cache entries.

**2. `EntityManager.clear()` có xóa L2 không?**

Không. Nó detach managed entities trong persistence context hiện tại.

**3. JPA `Cache.evict(Product.class, id)` xử lý gì?**

Evict shared-cache entry của entity type và primary key đó; nó không clear managed instance trong L1.

**4. Vì sao phải evict collection cache riêng?**

Collection membership/IDs là cache data riêng; evict entity entry không bảo đảm owner collection được làm mới.

**5. Vì sao query cache có thể stale dù entity L2 đã evict?**

Query result có thể chứa IDs/scalars cũ, không chỉ entity state.

**6. Vì sao eviction nên xảy ra sau commit?**

Evict trước commit cho phép reader cache lại database state cũ trước khi writer commit.

**7. READ_WRITE có tự bảo vệ external JDBC updates không?**

Không. External writer không tham gia Hibernate/cache provider soft-lock protocol.

**8. TTL có bảo đảm strong consistency không?**

Không. TTL chỉ giới hạn thời gian entry tồn tại; stale data có thể được trả trước khi hết TTL.

**9. External writer nên làm gì với `@Version`?**

Tăng version atomically theo policy để Hibernate phát hiện stale updates.

**10. Cache invalidation ở node A có tự lan sang node B không?**

Chỉ khi cache provider hoặc event infrastructure được cấu hình để propagate invalidation.

**11. `CacheRetrieveMode.BYPASS` có bỏ qua L1 không?**

Không. Entity đã managed trong persistence context vẫn có thể được trả từ L1; cần EntityManager mới hoặc clear.

**12. Synchronized query spaces có thay managed entities không?**

Không. Chúng giúp Hibernate nhận diện query spaces cho một số flush/query-cache behavior, không refresh L1 entities.

**13. Khi nào nên tắt L2 cho một entity?**

Khi external updates thường xuyên, invalidation không đáng tin hoặc freshness requirement không chấp nhận stale window.

**14. Query cache và collection cache khác nhau thế nào?**

Query cache lưu kết quả query; collection cache lưu state/membership của một collection association.

**15. Nếu evict L2 rồi vẫn đọc dữ liệu cũ, cần kiểm tra gì?**

L1, query/collection cache, replica lag, transaction snapshot, event timing và database/schema đang đọc.

## 30. Ghi nhớ

- Database và Hibernate L2 là hai hệ thống state riêng. **External SQL commit không tự invalidation cache của Hibernate**.
- Phân biệt L1 persistence context, L2 entity cache, collection cache và query cache; mỗi lớp có cách xử lý riêng.
- `EntityManager.clear()` chỉ detach managed entities trong L1, không xóa shared L2/query cache.
- JPA `Cache.evict()` có thể evict một entity hoặc entity type; Hibernate `SessionFactory.getCache()` có API rộng hơn cho entity, collection và query regions.
- Khi external update đổi fields, evict entity entry; khi đổi foreign-key/membership, xử lý collection regions; khi đổi query membership/scalars, xử lý query cache.
- **Evict sau commit**. Evict trước commit có thể để reader cache lại state cũ.
- Với nhiều nodes, cần distributed invalidation, outbox/CDC hoặc event bus đáng tin; local eviction ở một node không đủ.
- READ_WRITE/TRANSACTIONAL strategies không tự phối hợp với writers ngoài Hibernate; TTL chỉ tạo bounded stale window.
- External writers phải tôn trọng `@Version`, audit fields, tenant scope và business invariants.
- CacheRetrieveMode.BYPASS/CacheStoreMode.BYPASS giúp đọc không lấy/không ghi L2; chúng không bỏ qua entity đã managed trong L1.
- Synchronized query spaces cho native queries giúp Hibernate biết các bảng liên quan nhưng không refresh managed objects.
- Nếu không thể bảo đảm invalidation theo freshness contract, không cache entity mutable đó bằng L2.
- Test bằng external JDBC/ETL path, EntityManagers mới, cache stats và multi-node scenarios; không kết luận L2 stale từ một stale object trong L1.

### Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide — Second-level Cache](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#caching)
- [Hibernate ORM 6.6 User Guide — Query Cache](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#caching-query)
- [Hibernate ORM 6.6 JavaDoc — Cache](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Cache.html)
- [Hibernate ORM 6.6 JavaDoc — CacheConcurrencyStrategy](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/CacheConcurrencyStrategy.html)
- [Hibernate ORM 6.6 JavaDoc — NativeQuery](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/query/NativeQuery.html)
- [Jakarta Persistence 3.1 Specification — Shared Cache](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1)
- [Jakarta Persistence 3.1 API — Cache](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/cache)
- [Jakarta Persistence 3.1 API — CacheRetrieveMode](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/cacheretrievemode)
- [Jakarta Persistence 3.1 API — CacheStoreMode](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/cachestoremode)
- [Spring Framework Reference — Transaction Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)

