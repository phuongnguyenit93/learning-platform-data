# Thay đổi qua JDBC, ứng dụng khác hoặc native SQL và nguy cơ dữ liệu cũ

## 1. Vì sao database đã cập nhật nhưng Hibernate vẫn trả giá trị cũ?

Giả sử một ứng dụng quản lý giá sản phẩm dùng Hibernate ORM. Lúc 09:00, một request nạp sản phẩm `Product#42` với giá 100. Đến 09:01, một chương trình ETL dùng JDBC trực tiếp đổi giá thành 120. Request tiếp theo vẫn nhận 100 mặc dù lệnh SQL của ETL đã commit thành công.

Đây không nhất thiết là database “chưa lưu”. Có thể Hibernate đang trả dữ liệu từ **persistence context (first-level cache)**, **second-level cache** hoặc **query cache**, trong khi các lớp cache đó không biết về thay đổi vừa xảy ra ở ngoài cơ chế entity lifecycle của Hibernate.

~~~text
Ứng dụng A / Hibernate                  Ứng dụng B / JDBC
--------------------------------        ----------------------------
Session A / persistence context         UPDATE products
  Product#42.price = 100                 SET price = 120
               |                         WHERE id = 42;
          L2 cache                       COMMIT;
  Product#42.price = 100                         |
               |                                  |
               +--------------?-------------------+
                              |
                     Không có notification/
                     invalidation bắt buộc
                              |
                              v
                   Database price = 120
                   Cached Java price = 100
~~~

Nguy cơ này xuất hiện khi dữ liệu bị thay đổi qua:

- `JdbcTemplate`, JDBC `PreparedStatement`, jOOQ, MyBatis hoặc một JDBC connection khác.
- `EntityManager.createNativeQuery("update ...")` hoặc Hibernate `Session` native mutation.
- JPQL/HQL **bulk UPDATE/DELETE**, vốn không đi qua dirty checking của từng managed entity.
- Stored procedures, triggers, foreign-key cascades hoặc một database job.
- Một microservice, batch ETL, admin script hoặc ứng dụng khác dùng chung database.
- Một Hibernate `SessionFactory` khác mà cache/provider không phối hợp invalidation đúng cách.

Bài học trong chương **Bộ nhớ đệm** giải thích rõ vì sao dữ liệu cũ xuất hiện, cách phân biệt ba tầng cache, điều gì được Hibernate tự đồng bộ và điều gì **ứng dụng phải tự chịu trách nhiệm**, cùng phương án xử lý phù hợp với mức nhất quán nghiệp vụ.

**Nguyên tắc quan trọng:** Hibernate không thể tự biết mọi câu SQL được thực thi bởi một kết nối, service hoặc chương trình bên ngoài. `flush`, `refresh`, `clear`, **eviction** và **cache invalidation** có mục đích khác nhau; không có một lệnh duy nhất sửa mọi loại dữ liệu cũ.

## 2. Ba tầng lưu dữ liệu cần tách biệt

### 2.1. First-level cache (L1) / persistence context

Mỗi `EntityManager` hoặc Hibernate `Session` quản lý một tập entity nhất quán về **identity** trong phạm vi context. Với một entity class và identifier, thông thường chỉ có một managed instance:

~~~java
Product first = entityManager.find(Product.class, 42L);
Product second = entityManager.find(Product.class, 42L);

System.out.println(first == second); // true trong cùng context
~~~

L1 gắn với context, không phải một cache dùng chung toàn ứng dụng. Nó là nền tảng cho entity identity, dirty checking, lazy loading và transaction write-behind.

Khi một SQL khác cập nhật trực tiếp hàng `products.id = 42`, một `Product` đã được load vào L1 có thể vẫn giữ `price = 100`. Ngay cả nếu có một câu native SQL trả về giá 120, getter của managed entity vẫn có thể trả 100.

**L1 luôn tồn tại trong mô hình EntityManager/Session thông thường.** Nó không bị tắt bằng `hibernate.cache.use_second_level_cache=false`.

### 2.2. Second-level cache (L2) / cache giữa các Session

L2 cache là tùy chọn, thường được cấu hình qua Hibernate cache region factory và cache provider phù hợp (ví dụ JCache + provider). Nó lưu state của entity/collection theo cache region để các Session khác có thể dùng lại thay vì truy vấn DB.

~~~text
Session 1  ----\
Session 2  -----+--> SessionFactory / L2 cache --> Database
Session 3  ----/
~~~

Ví dụ:

1. Session 1 load Product#42 từ DB: price=100.
2. L2 được phép cache entity state.
3. Session 1 đóng.
4. External JDBC đổi DB thành 120 rồi commit.
5. Session 2 mới gọi `find(Product.class, 42L)`.
6. Nếu L2 còn entry 100 và không có invalidation, Session 2 có thể thấy giá cũ.

Vì thế **mở Session mới chỉ loại L1 cũ**, không tự bảo đảm tránh L2 stale.

### 2.3. Query cache

Query cache là một tính năng riêng, tùy chọn. Nó lưu thông tin về kết quả của những truy vấn được đánh dấu cacheable, ví dụ danh sách identifiers hoặc scalar result values, cùng thông tin phục vụ kiểm tra tính hợp lệ theo query spaces/timestamps.

~~~text
HQL: select p from Product p where p.active = true
       |          + tham số + pagination + các yếu tố query key
       v
 Query-result cache
       |
       +--> Có thể chứa IDs [42, 43, 44]
       |
       +--> L2/entity cache có thể cung cấp state của mỗi Product
       |
       v
 Database khi cache miss/entry invalid
~~~

Query cache **không đồng nghĩa** L2 entity cache. Có ít nhất hai tình huống:

- Query-result cache lưu danh sách IDs cũ, nên một Product mới đủ điều kiện bị bỏ qua hoặc Product đã hết điều kiện vẫn xuất hiện trong tập IDs.
- Query-result cache còn hợp lệ nhưng L2 entity cache chứa field value cũ, nên kết quả entity có state cũ.

Với scalar/DTO query, dữ liệu trả về từ cache có thể stale trực tiếp, không chỉ stale ở bước load entity.

### 2.4. Bảng so sánh phạm vi và thao tác

| Tầng | Phạm vi | Mặc định / bật thế nào | Dữ liệu cũ do external write? |
|---|---|---|---|
| Persistence context (L1) | Một EntityManager/Session | Gắn với entity management | Có, nếu instance đã được load |
| Entity/collection L2 | Thường theo SessionFactory/cache regions | Tùy cấu hình provider và mapping | Có, nếu external write không invalidation |
| Query cache | Theo SessionFactory/query-result regions | Bật riêng và đánh dấu query cacheable | Có, nếu query-result/timestamps không được invalidation |
| Cache ở Redis/API/CDN/application | Tùy ứng dụng | Ngoài hợp đồng JPA/Hibernate mặc định | Có, cần invalidation riêng |
| Database buffer cache | Database engine | Do DB quản lý | Khác bản chất: không phải Java entity cache |

Đừng nhầm database buffer cache với Hibernate cache; SQL engine chịu trách nhiệm tính đúng đắn transaction của nó, còn Java caches cần một giao thức phối hợp với những nguồn ghi.

## 3. Entity và thiết lập minh họa

Giả sử bảng:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(18, 2) NOT NULL,
    active BOOLEAN NOT NULL,
    version BIGINT NOT NULL
);
~~~

Entity mẫu dùng Jakarta Persistence và Hibernate-specific cache annotation:

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
@Cacheable
@Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
public class Product {

    @Id
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    @Version
    private long version;

    protected Product() {}

    public Long getId() { return id; }
    public BigDecimal getPrice() { return price; }
    public boolean isActive() { return active; }
    public long getVersion() { return version; }

    public void changePrice(BigDecimal nextPrice) {
        if (nextPrice == null || nextPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid price");
        }
        price = nextPrice;
    }
}
~~~

`@Cacheable` và `@Cache(READ_WRITE)` **không tự bật toàn bộ cache infrastructure**. Dự án còn cần có cache provider/region factory phù hợp, cấu hình Hibernate, cache regions và chiến lược đồng bộ. Đây là ví dụ mapping để phân tích hành vi, không phải một dự án biên dịch đầy đủ.

### 3.1. Bật cache theo cấu hình phù hợp

Cấu hình minh họa:

~~~properties
hibernate.cache.use_second_level_cache=true
hibernate.cache.use_query_cache=true
hibernate.generate_statistics=true
~~~

Trong Spring Boot, các property Hibernate có thể được truyền qua:

~~~properties
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.cache.use_query_cache=true
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Để L2 hoạt động còn phải cấu hình **region factory/provider** thực tế; chỉ ba dòng trên chưa đủ trong mọi môi trường. Cache provider khác nhau có các giới hạn riêng về clustering, TTL, serialization, eviction và transactional consistency.

**Không bật query cache bừa bãi cho mọi truy vấn.** Query cache hiệu quả trong workload có nhiều lần đọc với predicate ổn định và ít thay đổi; những truy vấn ghi/chỉnh điều kiện thường xuyên có thể bị invalidation liên tục, khiến cache chỉ thêm overhead.

### 3.2. READ_ONLY, NONSTRICT_READ_WRITE, READ_WRITE không có nghĩa external SQL được theo dõi

Các cache concurrency strategies kiểm soát cách Hibernate phối hợp cache với **những thay đổi Hibernate biết và quản lý**, không thể tự thông báo về mọi external JDBC update.

| Chiến lược | Ý nghĩa ở mức định hướng | Nguy cơ khi có external writer |
|---|---|---|
| `READ_ONLY` | Dùng với dữ liệu không được cập nhật qua ORM | External update phá giả định immutable; cache có thể cũ lâu |
| `NONSTRICT_READ_WRITE` | Chấp nhận cửa sổ dữ liệu cũ trong một số tình huống | External writes vẫn cần invalidation riêng |
| `READ_WRITE` | Phối hợp cache với ghi qua Hibernate theo chiến lược provider | Không tự phát hiện JDBC/ứng dụng khác |
| `TRANSACTIONAL` | Phụ thuộc provider và transaction coordination | Không tự giải quyết những writer ngoài cơ chế phối hợp |

Không chọn `READ_WRITE` rồi kết luận mọi source ghi đồng bộ theo thời gian thực. Strategy chỉ là một phần của consistency model.

## 4. Kịch bản 1: native SQL làm L1 cũ ngay trong cùng transaction

### 4.1. Ví dụ cập nhật trực tiếp

Giả sử giá DB ban đầu là 100:

~~~java
@Transactional
public BigDecimal updateAndRead(Long id) {
    Product product = entityManager.find(Product.class, id);

    entityManager.createNativeQuery(
        """
        UPDATE products
           SET price = :newPrice,
               version = version + 1
         WHERE id = :id
        """
    )
    .setParameter("newPrice", new BigDecimal("120.00"))
    .setParameter("id", id)
    .executeUpdate();

    return product.getPrice(); // Có thể vẫn là 100!
}
~~~

Vì câu native UPDATE không đi qua `product.changePrice()` và dirty checking của `Product` đang managed, instance trong L1 có thể vẫn giữ 100. `@Version` không làm Java object tự nhận thông báo rằng SQL đã tăng version.

Ngay cả lần gọi:

~~~java
Product second = entityManager.find(Product.class, id);
~~~

trong **cùng EntityManager** cũng có thể trả chính object `product` đã cũ, không truy vấn DB mới.

### 4.2. Giải pháp nhỏ nhất: refresh entity còn tồn tại

~~~java
Product product = entityManager.find(Product.class, id);

int updated = entityManager.createNativeQuery(
    """
    UPDATE products
       SET price = :price,
           version = version + 1
     WHERE id = :id
    """
)
.setParameter("price", new BigDecimal("120.00"))
.setParameter("id", id)
.executeUpdate();

if (updated != 1) {
    throw new IllegalStateException("Product not found");
}

entityManager.refresh(product);

BigDecimal freshPrice = product.getPrice();
~~~

`refresh(product)` yêu cầu object còn managed và row vẫn tồn tại/được DB nhìn thấy theo transaction isolation; nó nạp lại state từ database vào managed object.

Lưu ý:
- Local changes chưa flush trên entity được refresh có thể **bị ghi đè**.
- Refresh không biến transaction khác thành có thể quan sát được nếu isolation/snapshot chưa cho phép.
- Refresh một Product không tự cập nhật mọi managed object/collection/DTO hay cache của hệ thống khác.
- Nếu native SQL đã DELETE row đó, `refresh` có thể ném exception.

### 4.3. Khi nhiều rows bị sửa: clear/context boundary

~~~java
entityManager.flush(); // Chỉ khi có pending changes cần giữ.

entityManager.createNativeQuery(
    "UPDATE products SET active = false WHERE price > :threshold"
)
.setParameter("threshold", new BigDecimal("1000.00"))
.executeUpdate();

entityManager.clear(); // Detach toàn bộ managed entities.

List<Product> reloaded = entityManager.createQuery(
    "select p from Product p where p.active = true",
    Product.class
).getResultList();
~~~

`clear()` xử lý **L1**; nó không tự buộc L2/query cache trong mọi môi trường phải invalidation. Hãy xác định native query đi qua Hibernate có metadata dependency thích hợp hay không và cache provider có nhận invalidation nào.

### 4.4. Vì sao clear có thể nguy hiểm?

~~~java
Product p = entityManager.find(Product.class, 42L);
p.changePrice(new BigDecimal("105.00")); // Pending change.

entityManager.clear(); // Có thể bỏ pending change chưa flush.
~~~

Clear detach managed entities; dirty checking không còn xử lý object đó. Nếu cần lưu local changes, `flush()` trước `clear()` khi đúng với thứ tự nghiệp vụ. Không đưa `clear()` vào mọi repository method chỉ để “chắc chắn sạch cache”; nó có thể làm hỏng một transaction lớn đang chia sẻ persistence context.

### 4.5. Query scalar không tự cập nhật entity

~~~java
Product product = entityManager.find(Product.class, id);

Number value = (Number) entityManager.createNativeQuery(
    "SELECT price FROM products WHERE id = :id"
).setParameter("id", id)
 .getSingleResult();
~~~

Với cột DECIMAL, JDBC result có thể là `BigDecimal`; dùng kiểu mapping phù hợp thay vì giả định là `Number` trong mọi provider/driver. Kết quả SQL có thể đọc dữ liệu mới, nhưng `product.getPrice()` vẫn là state Java cũ. Hai phép đọc khác tầng nên không nhất thiết giống nhau nếu chưa refresh.
+## 5. Kịch bản 2: JDBC hoặc ứng dụng khác sửa DB, L2 vẫn cũ

### 5.1. Một Session mới không bảo đảm nhận giá trị mới

Giả sử cache L2 của Product#42 đã có giá 100:

~~~java
// Session A
Product p = entityManagerA.find(Product.class, 42L);
// p.price = 100

entityManagerA.close();
~~~

Một ứng dụng quản trị độc lập thực thi:

~~~sql
UPDATE products
SET price = 120.00, version = version + 1
WHERE id = 42;

COMMIT;
~~~

Sau đó:

~~~java
// Session B mới, cùng SessionFactory / cache region.
Product freshSessionProduct =
    entityManagerB.find(Product.class, 42L);
~~~

Session B có **L1 mới**, nhưng nếu L2 cache còn entry cũ và không có notification/invalidation, giá đọc được có thể vẫn là 100.

Đây là lý do **`entityManager.clear()` không đủ để sửa mọi dữ liệu cũ**. Clear chỉ dọn identity map của EntityManager hiện tại; nó không tự có quyền buộc một cache provider ở process khác xóa entry cũ.

### 5.2. Vì sao Hibernate không tự biết external UPDATE?

Hibernate có thể theo dõi DML mà nó trực tiếp quản lý vì biết entity mapping, table spaces, cache region và transaction lifecycle. Nhưng một JDBC connection độc lập chỉ nói chuyện với database.

~~~text
Ứng dụng ETL                          Hibernate ORM
-------------                         -------------
UPDATE products
COMMIT  ------------------------->    Database
                                           ^
                                           |
                                   L2 cache chưa được báo
                                           |
                                     Cache hit -> 100
~~~

Database không mặc định gửi cho Hibernate một sự kiện “Product#42 đã thay đổi” có đầy đủ entity type, ID, query-space và thời điểm commit. Muốn nhận thông báo cần một cơ chế **do kiến trúc ứng dụng thiết kế**, chẳng hạn event, CDC, outbox hoặc invalidation tập trung.

### 5.3. Evict một entity ở L2 qua Jakarta Persistence

JPA có `Cache` API:

~~~java
import jakarta.persistence.Cache;
import jakarta.persistence.EntityManagerFactory;

Cache cache = entityManagerFactory.getCache();

// Sau khi xác định Product#42 đã thay đổi ở database:
cache.evict(Product.class, 42L);
~~~

Lệnh này yêu cầu xóa entry tương ứng khỏi **shared cache** theo khả năng provider. Nếu external SQL sửa nhiều Product IDs:

~~~java
for (Long productId : changedIds) {
    cache.evict(Product.class, productId);
}
~~~

Hoặc, khi không thể xác định IDs:

~~~java
cache.evict(Product.class); // Evict cả Product entity cache region.
~~~

Nếu cần thao tác rất rộng:

~~~java
cache.evictAll(); // Evict entity cache entries của các entity classes.
~~~

Phạm vi, cách triển khai và chi phí phụ thuộc JPA provider/cache provider. Evict nhiều entries có thể làm tăng cache misses và tải DB đột biến.

**Đặc biệt:** `Cache.evict(...)` không cập nhật đối tượng `Product` đang managed trong EntityManager bất kỳ. Một context đang giữ Product#42 có thể vẫn trả price=100 cho đến khi refresh/clear/context mới.

### 5.4. Hibernate SessionFactory Cache API

Khi đã chấp nhận phụ thuộc Hibernate:

~~~java
import org.hibernate.SessionFactory;

SessionFactory factory =
    entityManagerFactory.unwrap(SessionFactory.class);

// Entity data:
factory.getCache().evictEntityData(Product.class, 42L);

// Toàn bộ entity data của Product:
factory.getCache().evictEntityData(Product.class);
~~~

Hibernate còn cung cấp API liên quan collection/natural-id/query regions tùy version. Chỉ evict entity `Product` không có nghĩa mọi collection cache hoặc query cache tương ứng được dọn theo đúng thời điểm.

Ví dụ danh sách Product IDs đã được cache trong một query-result region; `evictEntityData(Product.class, 42L)` chỉ xử lý entity data của Product. Nếu danh sách IDs vẫn cũ do external update, cần xử lý query cache nữa.

### 5.5. Khi Product được truy cập qua collection cache

Giả sử `Category.products` là một association collection được cache riêng. External INSERT một Product thuộc Category#9. L2 entity cache Product có thể không chứa Product mới, nhưng **collection cache** của Category#9 vẫn có danh sách IDs cũ:

~~~text
Category#9.products cached IDs = [41, 42]
Database Category#9 product IDs = [41, 42, 99]
~~~

Evict Product#99 không thêm ID 99 vào collection cache của Category#9. Cần invalidation **collection region/key tương ứng** hoặc tránh cache collection mutable được ghi bởi external systems.

Trong Hibernate Cache API, các method như `evictCollectionData(...)` tồn tại theo version và mapping role. Nếu không chắc role/owner ID, có thể evict cả collection region nhưng phải cân nhắc phạm vi.

### 5.6. Cẩn thận khi app có nhiều SessionFactory/process

Eviction gọi ở một `SessionFactory` chỉ tác động cache mà factory/provider đó quản lý. Nếu nhiều JVM có cache local độc lập, gọi `evictEntityData(...)` ở node A **không tự** xóa cache node B. Muốn đồng bộ liên node cần:
- Provider hỗ trợ shared/distributed invalidation phù hợp.
- Một kênh event/invalidation tới tất cả nodes.
- Hoặc bỏ L2 cho dữ liệu mutable có external writers khi không thể đảm bảo phối hợp.

Một Redis cache chung cũng không giải quyết tự động nếu ETL chỉ sửa SQL và **không xóa Redis entry**. Shared cache không đồng nghĩa shared change notifications.

## 6. Kịch bản 3: query cache còn bộ kết quả cũ

### 6.1. Cách query cache được bật và sử dụng

Trong một môi trường Hibernate có cache provider và query cache được cấu hình:

~~~properties
hibernate.cache.use_query_cache=true
~~~

Một query muốn cache kết quả thường phải được đánh dấu cacheable:

~~~java
import org.hibernate.Session;
import org.hibernate.query.SelectionQuery;

Session session = entityManager.unwrap(Session.class);

SelectionQuery<Product> query = session.createSelectionQuery(
    """
    select p
    from Product p
    where p.active = true
    order by p.id
    """,
    Product.class
);

query.setCacheable(true);

List<Product> products = query.getResultList();
~~~

Không phải mọi HQL SELECT đều được cache chỉ vì bật `hibernate.cache.use_query_cache=true`. Hibernate thường yêu cầu opt-in cho query cụ thể, hoặc có cấu hình/hint tương ứng.

### 6.2. Một thay đổi có thể làm kết quả query sai dù entity cache đúng

Giả sử query cache lưu IDs:

~~~text
Query key: all active products
IDs: [41, 42]
~~~

Một ứng dụng B dùng SQL chuyển Product#42 thành `active = false` và thêm Product#99 ở trạng thái active. Database đúng phải trả `[41, 99]`. Nhưng query cache không được invalidation có thể vẫn trả `[41, 42]`.

Ngay cả khi Product#42 đã bị evict khỏi entity L2, query-result cache vẫn có thể cung cấp **danh sách ID sai**. Query cache và entity cache cần được nghĩ như hai loại thông tin khác nhau:

- **Entity data**: giá, tên, trạng thái của một Product theo ID.
- **Query result set**: những Product IDs hoặc scalar rows nào đáp ứng một predicate cụ thể.

Nếu status thay đổi làm membership của result set khác đi, chỉ reload một entity không bảo đảm query cache trả đúng số lượng và thứ tự IDs.

### 6.3. Query-space timestamps và invalidation

Trong Hibernate hiện đại, query cache dựa vào thông tin liên quan những **query spaces** (các bảng dữ liệu mà query đọc) và timestamp/logic invalidation của Hibernate để quyết định cached result còn hợp lệ.

Một mô hình khái niệm:

~~~text
Query result cached at T1
    query spaces: products
               |
               v
Hibernate-managed UPDATE products at T2
               |
               v
Update timestamps / invalidation recorded for products
               |
               v
Query cache nhận biết result T1 cũ -> query DB lại
~~~

Khi UPDATE đi qua Hibernate và nó biết table/query space bị thay đổi, provider có cơ sở để invalidation query results liên quan.

**External JDBC UPDATE không tự thông báo sự thay đổi cho Hibernate update-timestamps tracking.** Vì thế query-result entry có thể vẫn được xem là hợp lệ dù database đã đổi.

Cơ chế và region names có thể thay đổi theo Hibernate version. Trong Hibernate 6.x có những region mặc định liên quan query results và update timestamps (ví dụ `default-query-results-region` và `default-update-timestamps-region`), nhưng nên xem config/Javadoc đúng phiên bản.

### 6.4. Không để query timestamp cache hết hạn trước query results

Hibernate User Guide lưu ý cache region dùng để theo dõi update timestamps cần được bảo quản phù hợp so với TTL/eviction của query results; nếu timestamps bị evict hoặc expire theo policy không phù hợp, logic kiểm tra tính mới của cached queries có thể mất thông tin cần thiết.

Đừng đặt TTL/LRU ngắn cho update-timestamps region rồi cho rằng query cache luôn tự hiểu mọi thay đổi. Với các hệ có external writers, cơ chế query timestamps chỉ giải quyết những writes Hibernate nhận biết và tham gia invalidation.

### 6.5. Chủ động evict query-result cache regions

Hibernate Cache API hỗ trợ evict query caches theo version, ví dụ:

~~~java
SessionFactory factory =
    entityManagerFactory.unwrap(SessionFactory.class);

factory.getCache().evictQueryRegions();
~~~

Đây là giải pháp có phạm vi rộng: xóa query-result cache regions do factory quản lý. Nó có thể gây cold-cache traffic lớn; không dùng sau mọi single-row update nếu có giải pháp chính xác hơn.

Nếu ứng dụng dùng named query regions, Hibernate có thể cho evict region cụ thể:

~~~java
factory.getCache().evictQueryRegion("catalog-active-products");
~~~

Cần bảo đảm query thực tế được cấu hình trong đúng region và dùng đúng API Hibernate version. Ngoài ra phải xử lý entity/collection cache nếu chúng cũng stale.

### 6.6. Cache invalidation và những thay đổi làm thay đổi query result

| Thay đổi DB | Nguy cơ entity L2 | Nguy cơ query cache |
|---|---|---|
| Giá Product#42 đổi 100 → 120 | Price của #42 cũ | Scalar query trả price có thể cũ; query lọc/sort theo price có thể sai |
| Product#42 active → false | Entity state cũ | Query “active products” có thể vẫn chứa #42 |
| INSERT Product#99 active | #99 chưa có entity entry, nhưng collection cache có thể cũ | Query active có thể thiếu #99 |
| DELETE Product#42 | Entity entry cũ | Query cached IDs có thể chứa #42 |
| External UPDATE foreign key | Entity/association state có thể cũ | Query theo quan hệ hoặc cached collection membership có thể cũ |
| DB trigger thay dữ liệu bảng khác | Các region của bảng phụ có thể cũ | Query phụ thuộc bảng phụ có thể cũ |

Lớp cache nào cần invalidation phụ thuộc **cột và quan hệ bị tác động**, không chỉ tên bảng trong câu SQL ban đầu.

## 7. Native SQL chạy qua Hibernate: trường hợp Hibernate có thể biết query space

### 7.1. Đường native SQL vẫn có Hibernate đứng giữa

Không phải mọi native SQL đều “ngoài Hibernate” theo cùng một mức độ. Câu SQL chạy bằng `EntityManager.createNativeQuery()` hoặc `Session.createNativeQuery()` vẫn được tạo/thực thi qua provider, nên Hibernate có thể nhận được một số thông tin về SQL, transaction và query spaces.

Tuy nhiên, Hibernate **không phải một SQL parser tổng quát** có thể luôn suy ra chính xác:
- Những bảng/cột nào bị thay đổi trong mọi vendor SQL.
- Trigger/procedure side effects.
- Những entity/collection cache regions liên quan.
- Generated database values của mọi row đã sửa.
- Những process khác đang ghi cùng dữ liệu.

Vì vậy, không nên mặc định native DML luôn invalidation đúng và tối thiểu tất cả caches. Hãy đọc Hibernate version docs về native query synchronization và đo/test hành vi.

### 7.2. addSynchronizedEntityClass

Hibernate có thể cho phép khai báo entity có liên quan với một native query:

~~~java
import org.hibernate.Session;
import org.hibernate.query.NativeQuery;

Session session = entityManager.unwrap(Session.class);

NativeQuery<?> query = session.createNativeQuery(
    """
    UPDATE products
    SET price = :price, version = version + 1
    WHERE id = :id
    """
);

query.addSynchronizedEntityClass(Product.class);
query.setParameter("price", new BigDecimal("120.00"));
query.setParameter("id", 42L);

int affected = query.executeUpdate();
~~~

`addSynchronizedEntityClass(Product.class)` khai báo dependency với tables/query spaces của Product mapping. Hibernate có thể dùng thông tin này trong **auto-flush checking** và **cache invalidation** cho native query theo contract của phiên bản.

Một số phiên bản Hibernate nếu không có synchronization metadata khi chạy native mutation có thể thực hiện invalidation **rộng hơn cần thiết** để an toàn; phiên bản khác/API path có thể có hành vi khác. Vì thế không khẳng định “native SQL luôn giữ cache cũ” **hay** “native SQL luôn tự xóa đúng Product#42”. Cần xác định chính xác đường query API, version và SQL impact.

### 7.3. addSynchronizedQuerySpace

Khi dùng tên bảng/query space:

~~~java
NativeQuery<?> query = session.createNativeQuery(
    "UPDATE products SET active = false WHERE id = :id"
);

query.addSynchronizedQuerySpace("products");
query.setParameter("id", 42L);
query.executeUpdate();
~~~

`addSynchronizedQuerySpace` khai báo dependency theo query space. Tên cần phù hợp mapping/schema. Nếu native SQL ảnh hưởng nhiều bảng hoặc triggers chạm bảng khác, một query space đơn lẻ không diễn tả đầy đủ tác động.

**Điều đặc biệt dễ nhầm:** synchronization metadata giúp Hibernate biết điều kiện **flush/cache coordination**, nhưng **không** tự gọi `refresh()` cho một Product#42 đang managed trong L1. L1 stale vẫn là một vấn đề riêng.

### 7.4. Native SELECT cũng cần query spaces cho auto-flush

Giả sử context có pending change ở Product#42 nhưng SQL cần đọc state mới:

~~~java
Product product = entityManager.find(Product.class, 42L);
product.changePrice(new BigDecimal("130.00"));

Session session = entityManager.unwrap(Session.class);

NativeQuery<?> query = session.createNativeQuery(
    "SELECT price FROM products WHERE id = :id"
);

query.addSynchronizedEntityClass(Product.class);
query.setParameter("id", 42L);

Object price = query.getSingleResult();
~~~

Trong chế độ AUTO, Hibernate có thể dùng metadata query spaces để biết SQL cần thấy pending entity updates và flush khi phù hợp. `EntityManager` native query và `Session` native query có lịch sử auto-flush khác nhau theo Hibernate/JPA version.

Nếu correctness phụ thuộc vào SQL đọc được pending updates, một `entityManager.flush()` **tường minh trước native SELECT** thường làm thứ tự rõ hơn, trong transaction phù hợp.

### 7.5. Hibernate biết bảng vẫn chưa đồng nghĩa biết từng ID

Ngay cả khi Hibernate invalidation một entity/query region tương ứng native mutation, nó có thể không xác định được **chính xác các IDs** mà một câu SQL phức tạp tác động. Cơ chế region-level invalidation đôi khi là lựa chọn bảo thủ.

Khi update qua JDBC **không đi qua Hibernate Session** hoặc từ một ứng dụng hoàn toàn khác, `addSynchronizedEntityClass` trên một query không tồn tại ở process đó không giúp gì. Cần event/cache eviction từ nguồn ghi hoặc giới hạn cache.

### 7.6. Bulk HQL/JPQL UPDATE/DELETE cũng là thay đổi set-based

~~~java
int updated = entityManager.createQuery(
    "update Product p set p.active = false where p.price > :threshold"
)
.setParameter("threshold", new BigDecimal("1000.00"))
.executeUpdate();
~~~

Bulk HQL/JPQL thường để Hibernate nhận biết entity/query spaces của statement nên có thể phối hợp invalidation shared caches theo các quy tắc provider. **Nhưng** câu bulk UPDATE không đồng bộ Java fields của từng Product đã managed trong L1, không tự gọi lifecycle methods/cascade/optimistic locking như entity-level update.

Vì vậy:

- **L1:** có thể phải `refresh` hoặc `clear`.
- **L2/query cache:** Hibernate có thể invalidation theo khả năng và query spaces khi DML đi qua nó; vẫn phải kiểm tra provider behavior, đặc biệt với native SQL, triggers và custom cache provider.
- **External application caches:** không tự nhận thông báo trừ khi được tích hợp.

Không đưa bulk JPQL và external JDBC vào cùng một kết luận quá đơn giản “không có cache invalidation nào”.

## 8. Cùng transaction nhưng hai loại stale data khác nhau

### 8.1. Flush trước SQL, refresh sau SQL

Đôi khi một service vừa sửa entity vừa chạy native SQL:

~~~java
@Transactional
public Product updateAndNormalize(Long id) {
    Product product = entityManager.find(Product.class, id);

    product.changePrice(new BigDecimal("115.00"));
    entityManager.flush(); // Managed changes -> DB trong transaction.

    entityManager.createNativeQuery(
        """
        UPDATE products
        SET price = round(price * 1.05, 2),
            version = version + 1
        WHERE id = :id
        """
    ).setParameter("id", id)
     .executeUpdate();

    entityManager.refresh(product); // DB -> Java managed instance.
    return product;
}
~~~

Đây là ví dụ phối hợp hai con đường ghi lên cùng row — cần đặc biệt cẩn trọng với `@Version` và thứ tự flush. Trong ứng dụng thật thường nên chọn **một nguồn ghi chính** cho invariant nghiệp vụ, thay vì liên tục trộn entity dirty checking với native DML.

### 8.2. Flush không phải commit

~~~text
Java changes
   |
   v
flush() ------> SQL UPDATE đã thực thi trong transaction
                         |
                         | chưa commit
                         v
                  SQL/native reads cùng transaction
                         |
                         v
                     commit/rollback
~~~

`flush()` chỉ đẩy pending SQL vào transaction. Nó không tự commit, không làm transaction khác chắc chắn thấy các thay đổi và không giải quyết cache của process khác.

### 8.3. Refresh không phá transaction isolation

Nếu transaction A dùng snapshot isolation/REPEATABLE READ, và transaction B vừa commit một update, A gọi `refresh` vẫn chỉ có thể đọc phiên bản dữ liệu mà isolation/database cho phép. Không lặp `clear(); refresh();` với hy vọng vượt qua MVCC.

Trường hợp này cần transaction boundary/isolation phù hợp. L1 stale và DB snapshot visibility là hai nguyên nhân khác nhau, dù đều biểu hiện “thấy dữ liệu cũ”.
+## 9. JDBC, JdbcTemplate và những cập nhật không đi qua entity cache tracking

### 9.1. JDBC thuần ghi trực tiếp

Một chương trình nhập giá có thể dùng:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
         """
         UPDATE products
         SET price = ?, version = version + 1
         WHERE id = ?
         """
     )) {

    ps.setBigDecimal(1, new BigDecimal("120.00"));
    ps.setLong(2, 42L);
    int count = ps.executeUpdate();

    if (count != 1) {
        throw new SQLException("Product not found");
    }
}
~~~

Nếu connection đang ở auto-commit mode thì mỗi statement có thể commit ngay; nếu không, chủ transaction phải commit/rollback theo chính sách. Đoạn này không gọi API Hibernate nên **không có tín hiệu tự động** tới L2/query cache của một Hibernate SessionFactory tồn tại ở nơi khác.

Nếu bảng Products được cache và đã có readers:
- Những read contexts đã mở có thể giữ managed Product cũ.
- L2 entity cache có thể giữ state cũ.
- Query cache có thể giữ membership/scalar values cũ.
- Những lớp application/HTTP cache có thể vẫn trả response cũ.

Một chương trình ETL cần được xem là **một nguồn ghi** trong chiến lược nhất quán của toàn hệ thống, không chỉ là tập SQL statements.

### 9.2. JDBC trong cùng Hibernate Session cũng không gọi entity dirty checking

Hibernate có API `Session.doWork`:

~~~java
Session session = entityManager.unwrap(Session.class);

session.doWork(connection -> {
    try (PreparedStatement ps = connection.prepareStatement(
        """
        UPDATE products
           SET price = ?,
               version = version + 1
         WHERE id = ?
        """
    )) {
        ps.setBigDecimal(1, new BigDecimal("125.00"));
        ps.setLong(2, 42L);
        ps.executeUpdate();
    }
});
~~~

`doWork` cung cấp JDBC Connection của Session cho callback, nhưng SQL đó vẫn là **JDBC do ứng dụng tự chạy**. Hibernate không tự phân tích every SQL statement trong `PreparedStatement` để biết Product nào đã đổi. Vì vậy hãy lập kế hoạch xử lý:
- L1 đang giữ Product liên quan.
- L2/query/collection regions có thể stale.
- Generated values, triggers, version increments.
- Transaction/connection ownership.

Không tự `connection.commit()`, `rollback()` hoặc `close()` trong callback nếu connection do Hibernate/transaction manager quản lý. Chỉ đóng `PreparedStatement`/`ResultSet` do code tự mở.

### 9.3. Spring JdbcTemplate và JPA trong một service

~~~java
@Service
public class ProductMaintenanceService {

    private final JdbcTemplate jdbcTemplate;

    @PersistenceContext
    private EntityManager entityManager;

    public ProductMaintenanceService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public BigDecimal adjustPrice(Long id, BigDecimal next) {
        Product product = entityManager.find(Product.class, id);
        if (product == null) {
            throw new IllegalArgumentException("Product missing");
        }

        // Nếu đang có entity changes pending mà SQL phụ thuộc,
        // chủ động flush theo thứ tự cần thiết.
        entityManager.flush();

        int affected = jdbcTemplate.update(
            """
            UPDATE products
               SET price = ?,
                   version = version + 1
             WHERE id = ?
            """,
            next, id
        );

        if (affected != 1) {
            throw new IllegalStateException("No row updated");
        }

        // Làm mới object đang managed trong context hiện tại.
        entityManager.refresh(product);

        return product.getPrice();
    }
}
~~~

Đây là ví dụ về **L1 synchronization**. Nó chưa phải toàn bộ chiến lược cho L2/query caches. Cũng chỉ đúng về transaction atomicity khi `JdbcTemplate` và JPA thực sự tham gia **cùng** transaction resource/manager.

Một method `@Transactional` không tự đảm bảo hai DataSources hoặc hai transaction managers khác nhau sẽ commit/rollback cùng nhau. Kiểm tra Spring configuration, XA/JTA nếu cần, connection routing và propagation.

### 9.4. Spring Data @Modifying chỉ giải quyết một phần

Repository có thể định nghĩa:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query(
    value = "UPDATE products SET active = false WHERE id = :id",
    nativeQuery = true
)
int deactivate(@Param("id") Long id);
~~~

Trong Spring Data JPA:
- `flushAutomatically` yêu cầu flush EntityManager **trước** modifying query.
- `clearAutomatically` yêu cầu clear EntityManager **sau** modifying query.

Hai cờ này quản lý **persistence context (L1)**. Chúng không phải cam kết evict mọi L2/query region trên mọi provider/version và không gửi invalidation tới các application khác. Ngoài ra, `clearAutomatically` detach toàn bộ managed entities trong transaction, nên có thể gây bất ngờ nếu caller còn dùng chúng.

Nếu cache correctness phụ thuộc những SQL effects phức tạp, cần quản lý cache ở tầng riêng, thay vì xem `@Modifying(clearAutomatically=true)` là phép giải tuyệt đối.

## 10. Eviction khi nào: thời điểm commit quan trọng không kém mục tiêu

### 10.1. Evict trước commit có thể tạo race

Giả sử ứng dụng A chạy UPDATE trong transaction chưa commit và ngay lập tức evict L2 Product#42:

~~~text
T0: DB committed price=100, L2 price=100
T1: Transaction A UPDATE price=120 (chưa commit)
T2: A evict L2 Product#42
T3: Reader B cache miss -> DB đọc committed price=100
T4: B repopulate L2 với price=100
T5: A commit price=120
T6: L2 vẫn có thể giữ 100 nếu không có invalidation khác
~~~

Đây là ví dụ cho thấy một lần eviction **trước** khi transaction ghi commit có thể chưa đủ. Một concurrent reader có thể lấp cache bằng giá trị cũ trong khoảng thời gian đó.

### 10.2. Evict sau commit cũng có cửa sổ trễ

Nếu A commit ở T5 và evict ở T6, các readers giữa T5–T6 vẫn có thể đọc stale cache. Evict sau commit giảm nguy cơ repopulate dữ liệu chưa commit nhưng không biến hệ thống thành giao dịch atomically coordinated giữa DB và cache.

Để chấp nhận hay loại bỏ cửa sổ trễ, phải trả lời câu hỏi nghiệp vụ:

- Giá hiển thị chỉ cần eventual consistency trong vài giây?
- Giá lúc checkout phải đọc đúng authoritative DB state?
- Tồn kho có yêu cầu atomic write/invariant?
- Một quyết định tài chính có cho phép đọc từ cache cũ không?

Mức độ chặt của consistency quyết định chiến lược phù hợp.

### 10.3. Minh họa đăng ký invalidation sau transaction commit trong Spring

Nếu phần SQL đã chạy trong Spring-managed transaction và chỉ một Product bị ảnh hưởng, có thể **đăng ký callback** evict shared cache sau khi transaction thực sự commit:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Transactional
public void changePriceWithJdbc(Long id, BigDecimal price) {
    int affected = jdbcTemplate.update(
        """
        UPDATE products
           SET price = ?,
               version = version + 1
         WHERE id = ?
        """,
        price, id
    );

    if (affected != 1) {
        throw new IllegalStateException("Product not found");
    }

    // L1 hiện tại có thể giữ Product cũ nếu đã load.
    entityManager.clear(); // Chỉ an toàn khi có chủ đích.

    if (!TransactionSynchronizationManager.isSynchronizationActive()) {
        throw new IllegalStateException("Transaction synchronization required");
    }

    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                entityManagerFactory.getCache().evict(Product.class, id);

                // Nếu external JDBC làm query-result caches stale:
                SessionFactory sf =
                    entityManagerFactory.unwrap(SessionFactory.class);
                sf.getCache().evictQueryRegions();
            }
        }
    );
}
~~~

Đây là **mẫu diễn giải**; nó giả định các field `jdbcTemplate`, `entityManager`, `entityManagerFactory` đã được inject, transaction dùng cùng DB và Hibernate là JPA provider. Trong ứng dụng thực tế, không nhất thiết evict **mọi** query region như ví dụ vì tác động rất rộng.

Các điểm cần cân nhắc:
- `entityManager.clear()` làm detached **tất cả** entity trong context, không chỉ Product. Nếu caller giữ pending changes, đây có thể là lựa chọn sai.
- Callback có thể gặp lỗi cache/network **sau khi DB đã commit**; rollback DB lúc đó không còn khả thi.
- Nếu process crash sau DB commit trước callback, invalidation có thể bị bỏ lỡ.
- Nhiều nodes/cache local chưa chắc cùng nhận callback từ node hiện tại.
- Evict chỉ một entity entry không đủ nếu query/collection caches hoặc triggers cũng bị ảnh hưởng.
- Nếu gọi method nội bộ trong cùng Spring bean (self-invocation), `@Transactional` proxy có thể không được áp dụng như kỳ vọng.

Vì vậy **afterCommit eviction hợp với những trường hợp đơn giản, chấp nhận một stale window nhỏ**, nhưng không phải cơ chế đảm bảo exactly-once invalidation giữa DB và cache.

### 10.4. Cần độ tin cậy cao hơn: transactional outbox hoặc CDC

Khi external writes, cache consistency và multiple service instances là yêu cầu nghiêm túc, một mô hình tốt hơn:

~~~text
Transaction ghi database
       |
       +--> UPDATE products
       |
       +--> INSERT outbox event(productId=42, version=8)
       |
       v
   COMMIT atomically
       |
       v
Outbox publisher / CDC đọc committed change
       |
       v
Durable message bus
       |
       +--> Node A: evict L2/query/application cache
       +--> Node B: evict L2/query/application cache
       +--> Node C: evict L2/query/application cache
~~~

Nếu dùng CDC trên transaction log, không nhất thiết cần outbox cho mọi kiểu thay đổi; nhưng cần biết cách chuyển change event thành entity/collection/query cache invalidation. Với complex joins/triggers, một bảng SQL đổi có thể ảnh hưởng nhiều cache keys.

Để giữ độ tin cậy:
- Dùng event IDs, versions và idempotent consumers.
- Có retry/dead-letter và monitoring.
- Tính tới event ordering.
- Hạn chế invalidation vô tình xóa state mới do event cũ đến trễ; cache value có thể mang version/timestamp để so sánh.
- Có kế hoạch cold-cache/reconciliation khi missed events xảy ra.
- Đo độ trễ **DB commit → các nodes đã invalidate**, không chỉ thời gian publisher gửi message.

CDC/outbox vẫn thường cung cấp eventual consistency cho caches, không tự biến DB và cache thành một transaction phân tán đồng bộ tuyệt đối.

## 11. Ứng dụng khác và nhiều nodes: chọn chính sách cache theo quyền sở hữu dữ liệu

### 11.1. Một database, nhiều nguồn ghi

Một thiết kế có thể gồm:
- Service Catalog dùng Hibernate L2/cache.
- Service Pricing dùng JDBC để cập nhật giá.
- ETL từ đối tác chạy SQL staging và merge.
- Admin chạy migrations.
- Worker reindexing hoặc trigger ở DB.

Nếu Product có các fields do nhiều nguồn ghi, cache đọc không thể dựa trên giả định “mọi write đều đi qua Hibernate Catalog Service”.

Nên xác định **ownership của từng loại dữ liệu**:

| Mô hình ghi | Gợi ý chính sách |
|---|---|
| Hibernate service là nguồn ghi duy nhất | Hibernate L2 có thể phù hợp với invalidation do ORM quản lý |
| Một service khác ghi và phát event đáng tin cậy | Có thể cache với subscriber invalidation và giới hạn stale window |
| Bất kỳ SQL client nào cũng có thể sửa dữ liệu | Cân nhắc không bật L2/query cache cho những entity mutable |
| Chỉ cập nhật theo lịch, stale vài phút được phép | TTL + refresh/invalidation theo lịch có thể đủ |
| Giá tại checkout phải đúng ngay | Đọc/kiểm tra authoritative state trong transaction, không dựa cache eventual |
| Dữ liệu gần immutable (country codes, static catalog) | READ_ONLY cache phù hợp nếu cơ chế publish mới/invalidation rõ ràng |

### 11.2. Shared cache không giải quyết hết

Một Redis/Hazelcast/Infinispan cluster có thể đồng bộ entries giữa các JVM khi **cache API** được gọi. Nhưng khi JDBC script chỉ chạy:

~~~sql
UPDATE products SET price = 120 WHERE id = 42;
~~~

không có thao tác cache tương ứng được phát đi. Provider không tự biết trừ khi có tích hợp external event/CDC hoặc một quy trình polling/TTL được thiết kế.

### 11.3. Multi-node L1 là các object khác nhau

Mỗi request/session trên từng node vẫn có L1 riêng. Evict L2 thông qua một distributed cache không làm một managed Product#42 đang nằm trong transaction dài của node khác tự đổi giá trị. Với transaction dài:
- `refresh` hoặc context mới có thể cần thiết ở nơi đó.
- DB isolation/snapshot vẫn có hiệu lực.
- Không tự cập nhật Java references giữa JVMs.
- Tránh giữ Session/EntityManager dài hơn unit of work.

### 11.4. Application-level cache và API response cache là một tầng nữa

Ngay cả sau `SessionFactory.getCache().evictEntityData(...)`, một `@Cacheable` ở Spring Cache, Redis DTO cache hoặc HTTP/CDN cache có thể tiếp tục trả JSON cũ.

Phải liệt kê **mọi cache key** dùng Product data:

~~~text
Hibernate L1:            Product#42 trong Session hiện tại
Hibernate L2:            Product#42
Hibernate query cache:   query active-products, filter price
Collection cache:        Category#9.products
Spring Cache:            product-summary:42
Redis DTO cache:         catalog-card:42
CDN:                     /catalog/product/42
Client app cache:        cached API response
~~~

Không có một Hibernate eviction call nào tự xóa tất cả những tầng đó.

## 12. Đọc dữ liệu bắt buộc mới: bypass cache đúng tầng

### 12.1. Cache retrieve hints của JPA

Jakarta Persistence có các cache modes/hints liên quan shared cache:

~~~java
import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.CacheStoreMode;

Product product = entityManager.find(
    Product.class,
    42L,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS,
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.REFRESH
    )
);
~~~

Ý định:
- `CacheRetrieveMode.BYPASS`: không dùng **shared cache** cho read này, theo JPA provider contract.
- `CacheStoreMode.REFRESH`: cho phép cập nhật shared cache bằng dữ liệu được nạp lại, theo semantics provider.

**Nhưng:** nếu L1 hiện tại đã có managed Product#42, `find` thường trả instance đó. Shared-cache bypass không đồng nghĩa bypass persistence context identity map. Khi cần dữ liệu DB mới:
- `entityManager.refresh(product)` cho entity đang managed.
- Hoặc `entityManager.clear()` rồi find với cache bypass (chỉ khi clear an toàn).
- Hoặc transaction/context mới với bypass shared cache.

### 12.2. Hints không phải câu lệnh “không dùng bất kỳ cache nào”

JPA cache hints tập trung vào shared persistence cache; chúng không mặc định điều khiển:
- Cache ở Spring/Redis/CDN.
- Connection pool.
- Database buffer cache.
- Query cache của những queries khác không dùng hint.
- Transaction isolation snapshot.

Hãy dùng đúng cơ chế cho từng tầng.

### 12.3. Có thể không cache những entity được nhiều writer chỉnh sửa

Đôi khi lựa chọn đáng tin cậy nhất là **không bật L2/query cache** cho dữ liệu rất mutable và có nhiều external writers. Một database có index tốt, connection pooling phù hợp và DTO projection có thể đủ nhanh.

Không đánh đổi tính đúng đắn của giá thanh toán, số dư, giới hạn tín dụng hoặc phân quyền để giảm vài milliseconds từ cache mà không có một consistency contract rõ ràng.
+## 13. Optimistic locking không tự làm cache luôn mới

### 13.1. `@Version` chủ yếu bảo vệ cập nhật cạnh tranh

Giả sử Product có:

~~~java
@Version
private long version;
~~~

Hibernate entity-level UPDATE thường dùng version như một điều kiện optimistic locking:

~~~sql
UPDATE products
SET price = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Nếu row đã thay đổi version ở database, Hibernate có thể phát hiện conflict khi flush entity cũ.

Nhưng **optimistic locking không phải một subscription mechanism**:
- Nó không gửi thông báo tới L1 đã load.
- Nó không tự evict shared L2 cache khi external SQL cập nhật DB.
- Nó không tự invalidation cached query result bị external INSERT/DELETE làm đổi membership.
- Nó không khiến client response cache đang giữ Product DTO nhận value mới.

### 13.2. External writer phải tôn trọng version strategy

Nếu external JDBC update:

~~~sql
UPDATE products
SET price = 120
WHERE id = 42;
~~~

mà không đổi `version`, entity-level optimistic locking trong transaction khác có thể không phát hiện việc row vừa bị thay đổi, dẫn tới lost update tùy thứ tự giao dịch và SQL.

Một thiết kế khi external writer có read version:

~~~sql
UPDATE products
   SET price = :new_price,
       version = version + 1
 WHERE id = :id
   AND version = :expected_version;
~~~

Ứng dụng kiểm tra affected-row count. Nếu bằng 0, phải xử lý conflict/row không tồn tại theo nghiệp vụ, không tự retry vô hạn.

Ngay cả khi external SQL có tăng version chính xác, **cache stale vẫn có thể xảy ra** nếu invalidation không được thực hiện. Version giúp phát hiện conflict khi ghi, không bảo đảm mọi phép đọc lấy state mới.

### 13.3. Một cached Product có version cũ cũng là cached data cũ

Nếu L2 trả Product#42 version=7 sau khi DB version đã là 8, object có thể vẫn hiển thị stale price. Khi ứng dụng cố cập nhật entity, optimistic locking có thể phát hiện lỗi, nhưng UI đã hiển thị sai trước đó.

Với nghiệp vụ yêu cầu quyết định ngay dựa trên dữ liệu mới (tồn kho, số dư, giới hạn rủi ro), không nên xem “write sau sẽ conflict” là đủ để cho phép stale read. Hãy đọc lại state authoritative trong transaction xử lý decision và kiểm tra điều kiện cập nhật bằng DB constraints/conditional SQL phù hợp.

## 14. Những thay đổi gián tiếp: trigger, stored procedure, FK và quan hệ

### 14.1. Trigger có thể làm nhiều bảng stale

Ví dụ một UPDATE ở `order_lines` kích hoạt trigger tính lại `purchase_orders.total_amount`. SQL nhìn thấy ban đầu chỉ ghi `order_lines`, nhưng **cache entity PurchaseOrder** và cached query doanh thu cũng bị ảnh hưởng.

~~~text
UPDATE order_lines
      |
      v
Database trigger
      |
      +--> UPDATE purchase_orders.total_amount
      |
      +--> INSERT audit_entries
      |
      v
Những cache regions có thể stale:
  OrderLine
  PurchaseOrder
  Order.total projection / query results
  Audit query results
~~~

Khi xây invalidation map, phải tính **toàn bộ side effects**, không chỉ table đứng sau từ khóa UPDATE trong câu SQL ban đầu.

### 14.2. Stored procedure thường là ranh giới mù

~~~java
StoredProcedureQuery procedure =
    entityManager.createStoredProcedureQuery("reprice_catalog");

procedure.execute();
~~~

Procedure có thể sửa Product, PriceHistory, CategorySummary và nhiều bảng khác. Hibernate không nhất thiết biết toàn bộ ảnh hưởng nếu chỉ gọi một tên procedure. Sau procedure:
- Nếu cần đọc entity đang managed, refresh/clear phù hợp.
- Nếu cache L2/query chứa dữ liệu bị ảnh hưởng, lập kế hoạch invalidation.
- Nếu procedure chạy qua transaction riêng, xác định commit boundary.
- Nếu thay đổi lớn, phát sự kiện/CDC hoặc evict các regions được xác định có chủ đích.

### 14.3. FK ON DELETE CASCADE có thể bỏ qua Java graph

Một SQL:

~~~sql
DELETE FROM categories WHERE id = 9;
~~~

có thể làm database cascade xóa nhiều Product liên quan (nếu schema được thiết kế vậy), nhưng những Product đã managed trong L1 và Product/collection caches có thể vẫn tồn tại. Tránh chỉ evict Category#9 rồi cho rằng mọi Product và query results liên quan đều đúng.

Nếu cần callbacks và cascade semantics của ORM, entity-level `remove` có thể là công cụ thích hợp hơn bulk/native SQL; tuy nhiên điều đó lại có performance/transaction trade-offs riêng.

### 14.4. Natural ID caches

Nếu entity có `@NaturalId` và cache natural ID, external SQL thay đổi natural key như `sku` có thể khiến natural-id cache mapping từ SKU cũ đến ID cũ bị stale. Entity cache eviction không mặc định tương đương mọi natural-id/collection/query-region invalidation.

Khi natural IDs mutable và nhiều nguồn ghi, cân nhắc không cache natural ID hoặc thiết kế invalidation đầy đủ. Kiểm tra Hibernate Cache API tương ứng với version cho natural-id region eviction.

## 15. Chẩn đoán dữ liệu cũ theo lớp, thay vì xóa mọi cache

Một lỗi thường được báo là “Hibernate cache sai”. Để tìm chính xác lớp nào sai, thử **tách nguồn quan sát**.

### 15.1. Quy trình đọc từng tầng

1. **Kiểm tra DB authoritative** bằng một SQL scalar query trên đúng primary database/tenant/schema và transaction phù hợp. Đừng đọc nhầm replica đang lag.
2. **Kiểm tra transaction visibility**: lệnh external UPDATE đã commit chưa? Reader đang ở snapshot isolation nào?
3. **Kiểm tra L1**: EntityManager hiện tại đã quản lý entity này chưa?
4. **Kiểm tra L2**: entity có cacheable không, cache region/config có hoạt động không, đang hit hay miss?
5. **Kiểm tra query cache**: câu truy vấn có `setCacheable(true)`/hint và query-result region nào?
6. **Kiểm tra association/collection caches**: có danh sách child IDs cũ không?
7. **Kiểm tra Spring/Redis/API/CDN cache** nếu Hibernate đã trả mới mà response vẫn cũ.
8. **Kiểm tra invalidation path**: ai chịu trách nhiệm publish event/evict sau external DB commit? Có lỗi retry/trễ/đứt kết nối không?
9. **Kiểm tra phiên bản và driver/dialect** nếu native query synchronization có hành vi khác mong đợi.

Không gọi evictAll ở bước đầu tiên rồi bỏ qua việc truy tìm nguyên nhân. Việc đó có thể làm hệ thống tạm đúng và che giấu một invalidation bug sẽ lặp lại.

### 15.2. em.contains và Cache.contains không chứng minh freshness

~~~java
Product product = entityManager.find(Product.class, 42L);
boolean managed = entityManager.contains(product);

boolean maybeCached = entityManagerFactory.getCache()
    .contains(Product.class, 42L);
~~~

`entityManager.contains(product)` cho biết managed state trong context, không cho biết fields có đồng bộ với DB mới nhất không. Shared Cache `contains` cho biết provider nhận entry là present theo contract, không cam kết entry tương ứng commit mới nhất từ một external application.

### 15.3. Hibernate statistics

Khi bật Hibernate statistics có chủ đích:

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory factory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics stats = factory.getStatistics();

System.out.println(
    "L2 hits = " + stats.getSecondLevelCacheHitCount()
);
System.out.println(
    "L2 misses = " + stats.getSecondLevelCacheMissCount()
);
System.out.println(
    "Query cache hits = " + stats.getQueryCacheHitCount()
);
~~~

Các counters này có ý nghĩa trong phạm vi SessionFactory, tùy Hibernate version và cache provider. Dữ liệu traffic khác có thể làm số liệu nhiễu. Quan sát một L2 hit trùng thời điểm stale read là dấu hiệu có ích, nhưng không tự chứng minh giá trị stale nằm tại đó nếu còn L1/query/application cache.

Đừng bật full SQL bind-value logging không kiểm soát trong production nếu chứa dữ liệu nhạy cảm.

### 15.4. Lập bảng “nguồn sự thật” cho một request

Ví dụ khi xảy ra sự cố:

| Quan sát | Price | Giải thích khả dĩ |
|---|---:|---|
| DB primary đã commit | 120 | Giá trị authoritative hiện tại |
| Raw JDBC SELECT cùng primary | 120 | SQL đọc state mới |
| EntityManager đang mở | 100 | L1 giữ entity cũ |
| EntityManager mới (L2 bật) | 100 | Có thể hit L2 cũ |
| EntityManager mới, bypass L2 | 120 | L2/invalidation có khả năng là nguyên nhân |
| Cached HQL scalar SELECT | 100 | Query-result cache có thể còn entry cũ |
| API response sau ORM | 100 | Có thể còn cache ở Spring/Redis/CDN |

Không coi đây là chuỗi trạng thái chắc chắn sẽ xuất hiện trên mọi provider: isolation, cache setup và SQL path quyết định kết quả. Bảng là công cụ tổ chức điều tra.

## 16. Integration test nên chứng minh những ranh giới nào?

### 16.1. Test 1: native UPDATE và managed entity stale

Thiết lập Product#42 có price=100.

~~~java
@Transactional
public BigDecimal readAfterNativeUpdate(Long id) {
    Product product = entityManager.find(Product.class, id);

    entityManager.createNativeQuery(
        """
        UPDATE products
           SET price = :price,
               version = version + 1
         WHERE id = :id
        """
    )
    .setParameter("price", new BigDecimal("120.00"))
    .setParameter("id", id)
    .executeUpdate();

    // Không giả định product.getPrice() đã là 120.

    entityManager.refresh(product);
    return product.getPrice();
}
~~~

Integration test xác nhận sau refresh giá là 120, với transaction, fixture và DB version phù hợp. Không cần assert “trước refresh chắc chắn là 100” nếu một test chỉ nhằm chứng minh correctness của service đã refresh; test riêng có thể khảo sát provider semantics.

### 16.2. Test 2: external JDBC commit rồi mở Session khác

Thiết kế test thực sự có **hai giao dịch độc lập**:

~~~text
Transaction A: JPA load Product#42, L2 enabled -> close/commit
Transaction B: external JDBC UPDATE Product#42 -> COMMIT
Transaction C: JPA find Product#42 using new EntityManager
Check: price with existing cache policy
Then evict relevant L2/query cache
Transaction D: new EntityManager find -> check new price
~~~

Nếu dùng Spring `@Transactional` bao trùm toàn bộ test, một JDBC operation có thể vô tình tham gia transaction test và rollback cùng nó. Hãy dùng transaction boundaries rõ (ví dụ TransactionTemplate có configuration phù hợp hoặc connection độc lập được commit) để mô phỏng external writer đúng thực tế.

Sau external change, xác nhận L2 hit/miss và khả năng stale **theo config đang thử**; không yêu cầu mọi provider đều stale để test “pass”. Mục tiêu là chứng minh chính sách invalidation của ứng dụng đưa kết quả về mới đúng contract.

### 16.3. Test 3: cached query thay đổi membership

1. Cache query “select active Products” với 2 entries.
2. External SQL update một Product thành inactive và insert một Product active mới, rồi commit.
3. Chạy query có cacheable hint tương tự.
4. Kiểm tra chính sách invalidation có loại ID bị tắt và thêm ID mới không.
5. Kiểm tra cả trường hợp entity L2 đã evict nhưng query cache chưa evict.
6. Nếu dùng query-result region riêng, kiểm thử đúng region thay vì evict tất cả.

Kết quả cần dựa trên tập dữ liệu từ DB authoritative, không chỉ số entity loads.

### 16.4. Test 4: event invalidation qua hai app instances

Với hai SessionFactories hoặc hai ứng dụng thực:
- Warm caches ở cả node A và B.
- Chạy external write rồi commit.
- Phát event/CDC/outbox.
- Chờ mỗi subscriber xác nhận event với id/version.
- Query lại từ cả A, B bằng EntityManager mới.
- Theo dõi stale window và số event misses.
- Kiểm tra một node offline rồi online: có replay/reconciliation hay không.

Unit test dùng cùng một SessionFactory không xác nhận cluster invalidation.

### 16.5. Test 5: transaction fail/rollback

1. External JDBC UPDATE được thực thi trong transaction nhưng sau đó rollback.
2. Không được publish “committed change” nếu thực tế không commit.
3. Nếu cache eviction được gọi quá sớm, reader có thể repopulate cache bằng giá cũ; quan sát behavior.
4. Nếu callback afterCommit fail, phải có cơ chế retry/monitoring hoặc một stale window được chấp nhận.
5. Kiểm tra event idempotency khi cùng event được gửi nhiều lần.

### 16.6. Test 6: trigger hoặc stored procedure thay đổi bảng thứ hai

Nếu Product update cập nhật CategorySummary qua trigger:
- Dùng SQL thật để kích hoạt trigger.
- Kiểm tra Product và CategorySummary L2.
- Kiểm tra query cache của báo cáo tổng hợp.
- Đảm bảo invalidation map tính đủ hai bảng và các collection liên quan.

## 17. Các lỗi phổ biến và hướng xử lý

| Hiện tượng | Khả năng nguyên nhân | Cách tiếp cận |
|---|---|---|
| Native UPDATE xong getter vẫn cũ | Managed entity giữ L1 state | `refresh` một entity hoặc `clear` an toàn |
| `find` lại trong cùng EntityManager vẫn cũ | Identity map trả object cũ | Refresh thay vì tìm lại trong cùng context |
| Mở Session mới vẫn cũ | L2 cache entry stale | Evict đúng entity region/key, đọc lại |
| Query active Products chứa ID đã inactive | Query-result cache stale | Invalidate query cache/query spaces |
| Entity fields đúng nhưng danh sách category vẫn thiếu child | Cached collection membership stale | Evict collection cache role/owner |
| `Cache.evict` đã gọi nhưng getter trong transaction vẫn cũ | L1 chưa refresh | Refresh/clear/context mới |
| `clear` đã gọi nhưng Session mới vẫn cũ | L2/query/application cache hoặc replica lag | Phân tầng điều tra |
| Native query registered query spaces nhưng object vẫn cũ | Query-space metadata không refresh L1 | Refresh/clear |
| External JDBC không gây Hibernate cache eviction | Không đi qua ORM/cache integration | Event/CDC/evict hoặc tắt cache |
| HQL bulk UPDATE xong L1 stale | Bulk mutation bỏ qua managed object sync | Refresh/clear trong transaction |
| `@Modifying(clearAutomatically=true)` vẫn trả cache cũ | Chỉ xử lý L1 | Xem L2/query cache và provider |
| Evict trước commit xong giá cũ quay lại | Reader repopulate trước commit | After-commit/event, consistency design |
| AfterCommit callback thất bại | DB commit và cache invalidation không atomic | Outbox/CDC/retry/monitor |
| Node A đã evict nhưng node B vẫn cũ | Cache local độc lập hoặc subscriber thiếu | Distributed invalidation/replay |
| `CacheStoreMode.REFRESH` nhưng find vẫn trả object cũ | L1 đã có managed identity | `refresh` object hoặc context mới |
| `@Version` không ngăn stale read | Version bảo vệ write conflict, không refresh cache | Read consistency riêng |
| Trigger sửa bảng khác nhưng chỉ evict Product | Invalidation không tính side effects | Map đủ entity/query/collection regions |
| Query cache bị “miss” nhưng response cũ | L2 hoặc Spring/Redis/CDN cache | Xác định tầng trả response |
| Refresh không thấy B đã commit | DB snapshot isolation/replica | Kiểm tra transaction visibility |
| EvictAll làm latency tăng mạnh | Cache stampede/cold cache | Thu hẹp invalidation, warm-up |
| External DELETE nhưng Product vẫn tồn tại ở Java | L1/entity/collection caches stale | Detach/clear và invalidation |
| Query cache luôn hết hạn/không hiệu quả | Dữ liệu đổi thường xuyên hoặc invalidation rộng | Giảm cacheable queries hoặc tắt query cache |

## 18. Bài tập tự luyện

### Bài 1 — Phân biệt L1 và L2

Session A đã load Product#42, external JDBC đổi giá, Session A `find` lại vẫn thấy cũ.

**Hỏi:** tầng nào chắc chắn cần nghĩ đến đầu tiên?

**Đáp án:** L1 persistence context của Session A. `find` có thể trả cùng managed instance. Refresh/clear/context boundary là hướng xử lý trước mắt.

### Bài 2 — Session mới vẫn stale

Session A đóng; Session B mới vẫn nhận giá cũ.

**Hỏi:** có thể vì sao dù L1 A đã không còn?

**Đáp án:** L2 entity cache hoặc query/application cache, cũng cần kiểm tra DB transaction/replica. Mở Session mới không tự đảm bảo L2 bị xóa.

### Bài 3 — Cached query giữ ID sai

Query “active products” cache IDs `[41, 42]`; external SQL tắt Product#42.

**Hỏi:** evict entity data Product#42 có đủ không?

**Đáp án:** không mặc định. Query-result cache còn danh sách IDs cũ; cần invalidation query cache/query space phù hợp.

### Bài 4 — JDBC đổi giá một Product

ETL có danh sách Product IDs đã thay đổi và vừa commit.

**Hỏi:** API JPA nào có thể dùng để evict một entry?

**Đáp án:** `entityManagerFactory.getCache().evict(Product.class, id)`, ngoài việc xử lý các caches khác nếu có.

### Bài 5 — Vì sao clear không đủ?

`em.clear()` rồi mở EntityManager mới nhưng vẫn đọc giá cũ.

**Định hướng:** clear chỉ xử lý L1. L2, query cache, Spring cache hoặc read replica có thể đang cũ.

### Bài 6 — NativeQuery query space

`Session.createNativeQuery` cập nhật `products` và gọi `addSynchronizedEntityClass(Product.class)`.

**Hỏi:** metadata này có tự đổi field của managed Product#42 không?

**Đáp án:** không. Nó phục vụ query-space/flush/cache coordination theo Hibernate version, không thay thế refresh L1.

### Bài 7 — Cập nhật có trigger

SQL UPDATE Products kích hoạt trigger cập nhật CategorySummary.

**Hỏi:** chỉ evict Product cache có chắc đầy đủ?

**Đáp án:** không. Phải xét cache entity/query/collection của các bảng do trigger tác động.

### Bài 8 — Query cache có còn đáng dùng?

Danh sách sản phẩm active liên tục thay đổi hàng trăm lần mỗi giây.

**Hỏi:** có nên cache mọi query active-products không?

**Định hướng:** chưa chắc. Invalidation thường xuyên có thể làm query cache kém hiệu quả; cân nhắc cache ít queries hơn hoặc đọc DB/DTO tối ưu.

### Bài 9 — Evict trước commit

A UPDATE price=120 chưa commit, evict cache, B đọc và cache lại price=100, A commit.

**Hỏi:** tại sao eviction một lần chưa đủ?

**Đáp án:** reader có thể repopulate cache bằng old committed data trước khi A commit. Cần xác định commit-aware invalidation và stale window.

### Bài 10 — Crash sau commit

DB commit thành công nhưng process crash trước khi gửi event evict cache.

**Hỏi:** một callback afterCommit không bền vững có đáp ứng yêu cầu không bỏ lỡ invalidation không?

**Đáp án:** không. Cần cơ chế durable outbox/CDC/event replay hoặc reconciliation phù hợp.

### Bài 11 — Shared Redis

Hai nodes cùng dùng Redis cache nhưng admin trực tiếp chạy UPDATE DB.

**Hỏi:** Redis có tự đổi value không?

**Đáp án:** không, trừ khi có integration/notification/TTL/invalidation. Shared cache không tự phát hiện mọi SQL.

### Bài 12 — Cache bypass

`em.find(Product.class, id, hints)` có `CacheRetrieveMode.BYPASS` nhưng EntityManager đã managed Product#42.

**Hỏi:** BYPASS có chắc lấy instance mới từ DB không?

**Đáp án:** không. BYPASS tác động tới shared cache; L1 identity map vẫn có hiệu lực. Refresh hoặc context mới khi cần.

### Bài 13 — Optimistic locking

External SQL cập nhật price mà không tăng `version`.

**Hỏi:** có vấn đề nào ngoài stale cache?

**Đáp án:** có thể làm mất khả năng phát hiện concurrent write và gây lost update. External writer phải tuân thủ locking/version strategy của hệ thống.

### Bài 14 — Dữ liệu cần strong consistency

Checkout cần kiểm tra giá cuối cùng và tồn kho trước thanh toán.

**Hỏi:** có nên dựa vào cached Product từ request trước đó không?

**Định hướng:** không nên lấy cache eventual làm nguồn xác thực cuối. Dùng authoritative transaction/conditional SQL/locking phù hợp và xử lý conflict.

### Bài 15 — Spring Data @Modifying

Repository có `clearAutomatically=true`.

**Hỏi:** nó tự gửi invalidation tới L2 cache ở node khác không?

**Đáp án:** không có bảo đảm như vậy. Cờ này clear EntityManager hiện tại; chiến lược L2/distributed cache cần được thiết kế riêng.

### Bài 16 — Thử nghiệm integration

Mock repository trả giá 120 sau external update.

**Hỏi:** đã chứng minh cache invalidation của Hibernate chạy đúng chưa?

**Đáp án:** chưa. Phải test DB, SessionFactory/cache provider và transaction boundaries thật.

## 19. Tổng kết: cache mới đúng khi mọi nguồn ghi đều có chính sách nhất quán

Từ một native SQL, JDBC script hoặc ứng dụng thứ hai, có thể phát sinh **ba lớp dữ liệu cũ độc lập**:

| Nơi stale | Dấu hiệu | Cách tiếp cận |
|---|---|---|
| **L1 persistence context** | Getter/find trong cùng EntityManager vẫn cũ | `refresh`/`clear`/`detach`/context mới theo phạm vi |
| **L2 entity/collection/natural-id caches** | Session mới vẫn thấy entity/association cũ | Evict đúng entries/regions, event invalidation hoặc không cache |
| **Query-result cache** | Danh sách IDs, scalar/aggregate rows không phản ánh điều kiện mới | Query-space invalidation/evict query region hoặc không cache query |

Ngoài ra, cần kiểm tra Spring/Redis/CDN cache, read replica lag và database transaction isolation; Hibernate không quản lý toàn bộ những nguồn ấy.

Ghi nhớ:

1. `flush()` đưa pending managed changes xuống database trong transaction; **không** phải lệnh làm mới cache.
2. `refresh(entity)` nạp lại một managed entity từ database; có thể ghi đè local changes chưa flush.
3. `clear()` detach mọi managed entities của L1, không xóa hết L2/query/application caches.
4. `EntityManagerFactory.getCache().evict(...)` giải quyết shared entity cache theo provider contract; không tự cập nhật L1 đang mở.
5. `SessionFactory.getCache().evictQueryRegions()` có thể xóa query-result cache, nhưng phạm vi rộng và có chi phí.
6. Native SQL qua Hibernate có khả năng query-space synchronization/invalidation theo version, nhưng không thể suy diễn tự động mọi SQL/trigger side effect.
7. External JDBC, ETL hoặc microservice ghi DB **không tự thông báo** cho Hibernate caches.
8. `@Version` giúp bảo vệ concurrent writes khi mọi writer tuân thủ strategy; không tự bảo đảm fresh reads.
9. Eviction sau commit giảm một số race nhưng vẫn có failure/staleness window; yêu cầu cao hơn cần outbox/CDC/retry/reconciliation.
10. **Bỏ cache cho dữ liệu quá mutable hoặc có nhiều writer** có thể tốt hơn một invalidation scheme không đáng tin cậy.

Một cách tư duy cuối:

~~~text
Nguồn ghi dữ liệu
     |
     v
Database commit
     |
     +--> Người dùng Session hiện tại?
     |        refresh / clear L1
     |
     +--> Entity/collection/natural-id L2?
     |        eviction / provider coordination / events
     |
     +--> Query-result cache?
     |        query-space invalidation / query region eviction
     |
     +--> App/Redis/CDN/client caches?
              invalidation khác, ngoài Hibernate
~~~

Câu hỏi quyết định không chỉ là **“đã bật cache chưa?”** mà là **“ai có quyền ghi dữ liệu này, và sau mỗi commit, ai sẽ làm mới hoặc vô hiệu hóa từng cache đang chứa nó?”**

### Tài liệu chính thức

- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — chọn User Guide/Javadocs đúng version và dialect.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — caching, flushing, native SQL synchronization, bulk mutations.
- [Hibernate ORM 6.6 Javadocs — Cache](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Cache.html) — cache eviction APIs.
- [Hibernate ORM 6.6 Javadocs — NativeQuery](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/query/NativeQuery.html) — `addSynchronizedEntityClass` và `addSynchronizedQuerySpace`.
- [Hibernate ORM 6.6 Javadocs — Statistics](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/stat/Statistics.html) — cache statistics.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — persistence context, Cache API, cache modes, refresh/clear và bulk DML.
- [Spring Data JPA Documentation](https://docs.spring.io/spring-data/jpa/reference/) — repository modifying queries và transaction.
- [Spring Framework Transaction Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction.html) — commit callbacks, transaction boundaries.

> Các ví dụ hướng tới Hibernate ORM 6.x/Jakarta Persistence. Cache invalidation thực tế còn phụ thuộc Hibernate version, cache region factory/provider, region configuration, query-space metadata, transaction integration và database concurrency. Khi yêu cầu correctness cao, phải xác nhận trên database/cache provider thật và thiết kế chính sách cho **mọi nguồn ghi**, không chỉ những SQL được Hibernate trực tiếp tạo ra.



