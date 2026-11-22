# Xóa dữ liệu cache qua API Cache của EntityManagerFactory trong JPA

Trong **Jakarta Persistence (JPA)**, việc truy vấn một entity không phải lúc nào cũng tạo SQL `SELECT`. Một entity đã có trong **persistence context** của `EntityManager` có thể được trả trực tiếp từ bộ nhớ cấp một; một entity đã được lưu trong **cache dùng chung cấp hai** có thể được nạp lại mà không cần đọc toàn bộ dữ liệu từ database.

Caching giúp giảm số lần truy cập database, đặc biệt đối với dữ liệu được đọc nhiều và thay đổi ít. Tuy nhiên, cache cũng mang lại một câu hỏi quan trọng:

> **Khi một bản ghi đã thay đổi ở database, làm thế nào xóa bản cache cũ để lần đọc tiếp theo không tiếp tục nhận dữ liệu không còn phù hợp?**

JPA cung cấp API chuẩn:

```java
EntityManagerFactory emf = ...;
Cache cache = emf.getCache();
```

Các thao tác chính gồm:

```java
cache.evict(Product.class, productId);
cache.evict(Product.class);
cache.evictAll();
```

Chúng cho phép ứng dụng yêu cầu **loại bỏ dữ liệu entity khỏi second-level cache** gắn với một `EntityManagerFactory`. Song, có một giới hạn cực kỳ quan trọng:

> **`EntityManagerFactory.getCache().evict(...)` không tự xóa các managed entities đang nằm trong persistence context của một `EntityManager` đã mở; cũng không tự ghi dữ liệu xuống database, không tự commit/rollback transaction và không phải API chuẩn để xóa mọi loại query cache hoặc collection cache riêng của provider.**

Bài học thuộc chương **Bộ nhớ đệm** trong module **Data Persistence Relational Access ORM JPA**. Ta sẽ tìm hiểu mô hình cache JPA, từng phương thức của `Cache`, cách chọn phạm vi eviction, kết hợp với `EntityManager.refresh()` và `clear()`, xử lý sau bulk JPQL/native SQL, tình huống cập nhật từ hệ thống ngoài, transaction timing, môi trường nhiều instance, những rủi ro hiệu năng và chiến lược kiểm thử thực tế.

---

## 1. Ba lớp dữ liệu cần phân biệt

Trước khi xóa cache, cần biết **dữ liệu đang ở đâu**.

Một ứng dụng JPA có thể nhìn nhận ba lớp lưu trữ:

```text
              Application service
                     |
                     v
      +-------------------------------+
      | EntityManager                 |
      | Persistence Context           |
      | First-level cache (L1)        |
      | Managed entities theo identity|
      +-------------------------------+
                     |
           lookup khi L1 không có
                     |
                     v
      +-------------------------------+
      | EntityManagerFactory          |
      | Shared / Second-level cache   |
      | L2 (nếu được bật/hỗ trợ)       |
      +-------------------------------+
                     |
        Cache miss / bypass / reload
                     |
                     v
      +-------------------------------+
      | Database                      |
      | Bảng, cột, index, constraints |
      +-------------------------------+
```

Ba lớp này **không có cùng vòng đời và phạm vi tác động**.

| Lớp | Chủ sở hữu | Phạm vi thường gặp | Công cụ liên quan |
| --- | --- | --- | --- |
| **Persistence context / L1** | `EntityManager` | Một đơn vị công việc hoặc một EntityManager | `find()`, `contains()`, `clear()`, `detach()`, `refresh()` |
| **Shared cache / L2** | `EntityManagerFactory` và provider | Dùng chung giữa nhiều EntityManagers của cùng factory, tùy cấu hình | `EntityManagerFactory.getCache()` |
| **Database** | DBMS | Dữ liệu bền vững và transactions | SQL DML, constraints, commit/rollback |

Trong JPA, L1 là một đặc tính cơ bản của persistence context. L2 là **tùy chọn** và phụ thuộc shared cache mode, cấu hình, provider và cơ chế cache tương ứng.

### 1.1. Ví dụ về L1

```java
Product first = em.find(Product.class, 101L);
Product second = em.find(Product.class, 101L);

System.out.println(first == second);
```

Trong cùng persistence context, một identity của entity được biểu diễn bởi một managed instance; với entity cùng ID, `find()` thường trả lại instance đang managed, không cần dựng một object độc lập từ database.

Lúc này **L1 quyết định việc trả entity**, cho dù second-level cache có entry hay không.

### 1.2. Ví dụ về L2

Giả sử:

```text
EntityManager #1:
    find(Product#101)
    -> database load
    -> provider có thể lưu vào shared cache
    close()

EntityManager #2:
    find(Product#101)
    -> nếu L2 có entry phù hợp
    -> provider có thể tái sử dụng dữ liệu đã cache
```

Hai EntityManagers khác nhau không chia sẻ **managed object instance** của L1. L2 thường chứa **dữ liệu đã cache** ở dạng do provider quản lý, và provider sử dụng dữ liệu đó để tái lập entity trong persistence context mới.

Đây là cơ chế giúp nhiều lượt đọc giảm SQL khi cache phù hợp.

### 1.3. L2 không nhất thiết đang bật

Không được giả định rằng:

```java
emf.getCache()
```

đồng nghĩa mọi entity tự động được cache.

Caching phụ thuộc:

- Shared cache mode của persistence unit.
- `@Cacheable` và metadata mapping.
- Cấu hình L2 của provider.
- Cache implementation/region.
- Loại entity/association.
- Trạng thái cache tại thời điểm truy cập.

**Nếu shared cache không sử dụng entity đó, `evict(...)` có thể không đem lại thay đổi quan sát được về số SQL.**

## 2. API Cache được lấy từ đâu?

JPA định nghĩa giao diện `jakarta.persistence.Cache`.

```java
import jakarta.persistence.Cache;
import jakarta.persistence.EntityManagerFactory;

EntityManagerFactory emf = ...;

Cache cache = emf.getCache();
```

`Cache` là **giao diện dùng chung cấp factory**, không phải đối tượng thuộc riêng một `EntityManager`.

### 2.1. Những thao tác quan trọng

| API | Mục đích | Phạm vi |
| --- | --- | --- |
| `contains(Class<?> cls, Object primaryKey)` | Hỏi cache có dữ liệu của entity với type và ID tương ứng không | Một entity |
| `evict(Class<?> cls, Object primaryKey)` | Yêu cầu loại bỏ entity cụ thể khỏi cache | Một entity |
| `evict(Class<?> cls)` | Yêu cầu loại bỏ các entity đã cache của type tương ứng | Một entity type |
| `evictAll()` | Yêu cầu loại bỏ các entity đã cache thuộc phạm vi cache | Toàn bộ entity cache của factory |
| `unwrap(Class<T> cls)` | Truy cập đối tượng/provider API đặc thù khi có hỗ trợ | Phụ thuộc provider |

**Chú ý:** `unwrap(...)` làm code phụ thuộc provider nếu sử dụng extension. Chương này ưu tiên các phương thức eviction chuẩn trước.

### 2.2. Ví dụ trực tiếp

```java
Cache cache = emf.getCache();

boolean cached =
    cache.contains(Product.class, 101L);

cache.evict(Product.class, 101L);

cache.evict(Product.class);

cache.evictAll();
```

Đây là **ba mức độ eviction khác nhau**, không phải ba bước bắt buộc phải thực hiện liên tiếp.

Trong một ứng dụng thật, nếu chỉ cần xóa Product#101, **chỉ gọi**:

```java
cache.evict(Product.class, 101L);
```

Không gọi thêm `evict(Product.class)` hoặc `evictAll()` chỉ để “chắc ăn” nếu không có lý do nghiệp vụ rõ.

## 3. Mô hình entity Product để minh họa

Giả sử dịch vụ catalog quản lý sản phẩm:

```java
package com.example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
@Cacheable
public class Product {

    @Id
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    @Version
    private Long version;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }

    public Long getVersion() {
        return version;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Price must not be negative"
            );
        }

        this.price = newPrice;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                "Product name is required"
            );
        }

        this.name = newName;
    }
}
```

`@Cacheable` là metadata chuẩn JPA liên quan đến shared caching. Nhưng **sự có mặt của annotation không bảo đảm provider đã bật L2 hoặc cache entry chắc chắn xuất hiện**.

### 3.1. Schema minh họa

Ví dụ PostgreSQL:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    active BOOLEAN NOT NULL,
    version BIGINT NOT NULL
);
```

`@Version` cho phép provider dùng version để kiểm soát optimistic concurrency khi cập nhật entity qua đường managed-entity thông thường.

**Cache eviction và version checking là hai cơ chế riêng**:

- `@Version` bảo vệ khỏi những cập nhật dựa trên version cũ.
- `Cache.evict(...)` yêu cầu không tái sử dụng cache entry nhất định trong các lần đọc phù hợp.

Eviction không tự tăng version và không thay thế transaction consistency.

## 4. Xóa cache của một entity: evict(Class, primaryKey)

Đây là lựa chọn có phạm vi hẹp nhất trong API chuẩn.

```java
Cache cache = emf.getCache();

cache.evict(Product.class, 101L);
```

Ý nghĩa: yêu cầu bỏ dữ liệu shared cache của `Product` có primary key `101L`.

### 4.1. Khi nào phù hợp?

- Một sản phẩm cụ thể bị thay đổi ngoài JPA.
- Một bản ghi vừa được một batch job cập nhật và ứng dụng biết ID.
- Một hệ thống nhập dữ liệu báo thay đổi Product#101.
- Một tác vụ quản trị cần làm mới một entity cụ thể.
- Một thao tác native/bulk DML có thể ảnh hưởng một ID xác định.

### 4.2. Class và ID phải đúng

```java
cache.evict(Product.class, 101L);
```

khác:

```java
cache.evict(Product.class, "101");
```

nếu primary key Java của entity là `Long`.

Đừng tự cho rằng provider sẽ biến mọi String thành ID số. Cần dùng đúng type và key tương ứng với JPA entity identity.

### 4.3. Entity có composite primary key

Ví dụ entity có `@EmbeddedId`:

```java
@Embeddable
public class InventoryBalanceId
        implements java.io.Serializable {

    private Long warehouseId;
    private Long productId;

    // Constructors, equals và hashCode phù hợp.
}
```

```java
@Entity
public class InventoryBalance {

    @EmbeddedId
    private InventoryBalanceId id;

    // ...
}
```

Eviction dùng **đối tượng key**:

```java
InventoryBalanceId id =
    new InventoryBalanceId(/* warehouseId, productId */);

emf.getCache().evict(InventoryBalance.class, id);
```

Đoạn code trên là ví dụ cấu trúc; constructor và các phần triển khai của ID class cần được định nghĩa đúng JPA trước khi dùng. Không dùng chỉ `warehouseId` nếu identity thật gồm cả warehouse và product.

### 4.4. Có cần gọi contains() trước không?

Có thể kiểm tra:

```java
Cache cache = emf.getCache();

if (cache.contains(Product.class, 101L)) {
    cache.evict(Product.class, 101L);
}
```

nhưng **thường không cần**. `evict(...)` có thể được gọi trực tiếp; không cần một bước kiểm tra trước chỉ để quyết định xóa.

Ngoài ra còn có race condition:

```text
Thread A: contains(Product#101) -> false
Thread B: populates cache Product#101
Thread A: bỏ qua evict
```

Hoặc:

```text
Thread A: contains(Product#101) -> true
Thread B: evicts Product#101
Thread A: evict lần nữa
```

Vì vậy, `contains()` không phải khóa đồng bộ hoặc bảo đảm nguyên tử **check-and-evict**. Nếu mục tiêu thực sự là invalidation, hãy **gọi evict trực tiếp**.

## 5. Xóa toàn bộ entity type: evict(Class)

```java
Cache cache = emf.getCache();

cache.evict(Product.class);
```

Ý nghĩa: yêu cầu loại bỏ những dữ liệu của entity type `Product` khỏi cache.

### 5.1. Khi nào cần xóa cả type?

- Batch update thay đổi rất nhiều Product, không giữ danh sách ID.
- Thay đổi tính toán giá khiến nhiều sản phẩm bị ảnh hưởng.
- Tác vụ nhập danh mục làm thay đổi tập record rộng.
- Không thể xác định đáng tin những keys bị sửa.

### 5.2. Vì sao tốn hơn evict theo ID?

Một entity type có thể có hàng trăm nghìn cache entries. Sau khi loại bỏ chúng, các request sau đó cần nạp lại từ database hoặc nguồn dữ liệu tương ứng. Hậu quả có thể là **cache miss tăng mạnh**, tải database đột biến và latency tăng.

Nếu chỉ 12 sản phẩm trong 100.000 sản phẩm thay đổi và ứng dụng biết IDs, gọi:

```java
for (Long productId : changedProductIds) {
    cache.evict(Product.class, productId);
}
```

thường có phạm vi ảnh hưởng hẹp hơn `cache.evict(Product.class)`.

### 5.3. Có tác động đến subclasses không?

Với inheritance mapping và cache regions của provider, chi tiết tổ chức cache có thể phức tạp. Không nên suy từ `evict(BaseEntity.class)` rằng **mọi cache entry thuộc mọi subtype/region** đã bị xóa theo đúng mong đợi trong mọi provider/version.

Khi ứng dụng có entity inheritance, cần đối chiếu entity type và provider-specific cache region mapping để lựa chọn phạm vi eviction phù hợp.

## 6. Xóa cache rộng nhất: evictAll()

```java
Cache cache = emf.getCache();

cache.evictAll();
```

Đây là lựa chọn mạnh nhất trong nhóm các phương thức eviction chuẩn của `jakarta.persistence.Cache` dành cho entity cache.

### 6.1. Khi nào cân nhắc?

- Một đợt migration hoặc import làm thay đổi nhiều loại entity.
- Một sự cố cache consistency không còn biết những keys nào bị ảnh hưởng.
- Tác vụ vận hành có chủ đích để loại bỏ phần lớn entity entries.
- Một đợt đồng bộ lớn từ hệ thống khác sau khi xác nhận đã commit.

### 6.2. Tại sao không gọi thường xuyên?

`evictAll()` có thể:

- Làm mất phần lớn tỷ lệ cache hit vừa tích lũy.
- Khiến database phải phục vụ nhiều truy vấn lặp lại.
- Tạo **cache stampede** khi nhiều request cùng tải các entities phổ biến.
- Tăng CPU, network và heap churn khi cache được làm nóng lại.
- Gây thời gian đáp ứng xấu sau sự kiện invalidation.

Đây không phải thao tác “dọn rác” nên gọi ở cuối mọi HTTP request.

### 6.3. evictAll không phải xóa mọi loại cache trong hệ thống

Các thành phần khác có thể tồn tại:

```text
EntityManagerFactory
    |
    +-- Standard JPA entity L2 cache
    |
    +-- Provider-specific query result cache
    |
    +-- Provider-specific collection regions
    |
    +-- Application Caffeine/Redis cache
    |
    +-- HTTP/CDN cache
```

`Cache.evictAll()` **không phải API chuẩn để xóa tất cả những lớp cache này**. Những cache riêng của Hibernate/EclipseLink, Spring `@Cacheable`, Redis hoặc CDN có contract invalidation độc lập.

Nếu mục tiêu là đồng bộ toàn bộ hệ thống cache, phải xác định **từng lớp** và cơ chế riêng của nó.

## 7. Cache.contains() thực sự cho biết gì?

```java
boolean present =
    emf.getCache().contains(Product.class, 101L);
```

`contains` hỏi **cache liên quan tới EntityManagerFactory** có dữ liệu của entity với type và key tương ứng hay không.

### 7.1. Nó không kiểm tra L1

```java
boolean managed = em.contains(product);
```

và:

```java
boolean inL2 =
    emf.getCache().contains(Product.class, product.getId());
```

là hai câu hỏi khác:

| Kiểm tra | Ý nghĩa |
| --- | --- |
| `em.contains(entity)` | Entity instance đó có đang managed trong persistence context của `em` không? |
| `cache.contains(Entity.class, id)` | Shared cache có dữ liệu tương ứng theo API Cache không? |

Một entity có thể:

- Có trong L1 nhưng không có trong L2.
- Có trong L2 nhưng chưa có trong L1 của EntityManager vừa tạo.
- Có ở cả hai.
- Chưa có ở cả hai, dù row vẫn tồn tại ở database.

### 7.2. contains() không bảo đảm dữ liệu mới nhất

Nếu `contains(Product.class, 101L) == true`, nó không nói:

- Entry chắc chắn còn mới so với database.
- Entry vừa được tạo khi nào.
- Version trong cache có bằng version mới nhất không.
- Truy vấn tiếp theo chắc chắn cache hit.
- L1 của caller đang thấy đúng giá trị.

`contains()` chỉ là tín hiệu về **sự có mặt trong cache** theo khả năng provider, không phải phép kiểm tra consistency với database.

### 7.3. contains() không phải số liệu performance

Ngay cả khi `contains()` trả true, một `find()` có thể lấy dữ liệu từ L1 và không cần tra L2. Nếu provider không cache entity đó, `contains()` có thể false dù hệ thống vẫn hoạt động chính xác.

Để đo hiệu năng L2 cần statistics/logs/metrics phù hợp của provider và database, không chỉ đếm số lần gọi `contains()`.

## 8. Quan trọng nhất: evict L2 không làm mất managed entity trong L1

Giả sử:

```java
EntityManager em = emf.createEntityManager();

Product product1 =
    em.find(Product.class, 101L);

// Xóa L2 entry tương ứng.
emf.getCache().evict(Product.class, 101L);

// Cùng EntityManager:
Product product2 =
    em.find(Product.class, 101L);

System.out.println(product1 == product2);
```

Trong cùng persistence context, `product2` vẫn có thể là **chính managed instance `product1`**. EntityManager không bắt buộc truy vấn database lại chỉ vì shared cache entry bị evict.

### 8.1. Sơ đồ

```text
EntityManager A (L1)
   Product#101, price=100
          |
          | emf.getCache().evict(Product.class, 101)
          v
Second-level cache:
   Product#101 entry removed
          |
          | em.find(Product.class, 101)
          v
EntityManager A vẫn có Product#101 managed
   -> có thể trả price=100 từ L1
```

Đây là lý do thường gặp nhất khiến người viết code nhận xét:

> “Tôi đã gọi evict nhưng query vẫn trả dữ liệu cũ.”

Thực ra **evict đã tác động đến L2**, còn dữ liệu cũ đang nằm trong L1.

### 8.2. refresh() và clear() giải quyết vấn đề khác

`EntityManager.refresh(entity)` và `EntityManager.clear()` thuộc API của persistence context.

| Thao tác | Mục tiêu chính | Phạm vi |
| --- | --- | --- |
| `emf.getCache().evict(Product.class, id)` | Loại bỏ shared entity cache entry | L2 |
| `em.refresh(product)` | Làm mới state của managed entity từ database theo semantics JPA | Entity trong L1; tác động L2 tùy fetch/store strategy |
| `em.clear()` | Detach toàn bộ managed entities khỏi persistence context | L1 của một EntityManager |
| `em.detach(product)` | Detach một entity instance | L1 của EntityManager |
| `em.close()` | Đóng EntityManager application-managed | Kết thúc scope của EM |
| `em.flush()` | Đồng bộ pending changes với database | Transaction, **không phải cache eviction** |

### 8.3. Không đánh đồng clear và cache.evictAll

```java
em.clear();
```

không có nghĩa mọi EntityManager khác bị clear hoặc L2 đã bị evict.

Ngược lại:

```java
emf.getCache().evictAll();
```

không có nghĩa mọi EntityManager đang mở sẽ tự detach hết objects.

### 8.4. Làm mới một managed instance

```java
Product product = em.find(Product.class, 101L);

// Giả sử thay đổi ở database đã được commit bên ngoài.
em.refresh(product);
```

`refresh()` yêu cầu đồng bộ state entity với database theo JPA, nhưng phải cân nhắc:

- Entity cần ở trạng thái managed.
- Có thể cần transaction theo loại EntityManager/lock mode.
- Những thay đổi local chưa lưu có thể bị ghi đè.
- Provider có thể phát sinh exception nếu state/lock/version không cho phép refresh.
- L2/query cache của các EntityManagers khác **không mặc nhiên được invalidated toàn bộ** chỉ vì refresh một entity.

Nếu đang xử lý lỗi transaction hoặc optimistic conflict, **không dùng refresh để cứu một transaction đã rollback-only**.

### 8.5. Khi nào chọn EntityManager mới?

Đối với một luồng đọc cần chắc chắn không dùng L1 cũ, tạo **EntityManager mới** sau khi cập nhật dữ liệu đã commit và chính sách L2 đã được xử lý thường rõ ràng hơn:

```java
emf.getCache().evict(Product.class, 101L);

try (EntityManager fresh = emf.createEntityManager()) {
    Product reloaded = fresh.find(Product.class, 101L);
    // Đọc dữ liệu trong persistence context mới.
}
```

Tùy phiên bản Jakarta Persistence, `EntityManager` là `AutoCloseable` nên cú pháp try-with-resources có thể áp dụng; với môi trường/container-managed EM, phải theo lifecycle container, không tự đóng EM inject bằng `@PersistenceContext`.

Nếu có yêu cầu **đọc ngay database thay vì L2**, có thể kết hợp cache retrieve mode như phần sau.

## 9. Ba API dễ nhầm: evict, refresh và clear

Một cách nhớ nhanh:

```text
evict (Cache API) :
    "Đừng giữ bản cached entity này ở shared L2."

refresh (EntityManager API) :
    "Làm mới managed entity này từ database."

clear (EntityManager API) :
    "Không tiếp tục quản lý những entity instances
     hiện có trong persistence context này."
```

### 9.1. Tình huống chỉ cần evict

Một external batch job đã commit thay đổi Product#101. Application biết ID và những request mới sẽ dùng EntityManager mới.

```java
emf.getCache().evict(Product.class, 101L);
```

Đây là hành động hợp lý để tránh tái sử dụng L2 entry cũ cho những lượt đọc sau, nếu entity đang được shared-cache.

### 9.2. Tình huống phải xử lý L1

Một service dài hạn đang giữ managed Product#101. External writer vừa cập nhật database.

```java
cache.evict(Product.class, 101L);
```

không đủ để state trong service đổi ngay. Cần lựa chọn có chủ đích:

- `refresh(product)` nếu muốn tiếp tục dùng managed instance và có thể refresh an toàn.
- `detach(product)` hoặc `clear()` rồi load lại phù hợp.
- Kết thúc scope cũ, mở EntityManager mới.

### 9.3. Đừng clear trước khi flush nếu còn pending changes

Sai:

```java
product.changePrice(newPrice);
em.clear();
```

Nếu chưa flush/commit, việc detach có thể khiến thay đổi trong managed object không được ghi như mong muốn.

Đối với workflow ghi, phải xác định transaction state trước khi chọn refresh/clear. Các phương thức này không thay thế việc hoàn tất hoặc rollback transaction.

## 10. Mối quan hệ giữa second-level cache và shared cache mode

Cấu hình JPA quyết định entity nào **đủ điều kiện** sử dụng shared cache.

Trong `persistence.xml` có thể có:

```xml
<persistence-unit name="catalogPU">
    <shared-cache-mode>ENABLE_SELECTIVE</shared-cache-mode>
</persistence-unit>
```

Đoạn trên minh họa phần tử bên trong persistence unit; một file `persistence.xml` hoàn chỉnh còn có phần namespace, provider/database và cấu hình khác.

Các chế độ tiêu chuẩn gồm:

| Shared cache mode | Ngữ nghĩa tổng quát |
| --- | --- |
| `ALL` | Cache tất cả entities, trừ các cấu hình loại trừ theo chuẩn. |
| `NONE` | Không yêu cầu shared caching các entities. |
| `ENABLE_SELECTIVE` | Chỉ những entities được khai báo cacheable phù hợp mới được cache. |
| `DISABLE_SELECTIVE` | Shared cache được dùng trừ những entities được khai báo không cacheable phù hợp. |
| `UNSPECIFIED` | Để hành vi phụ thuộc provider và cấu hình mặc định. |

### 10.1. @Cacheable

```java
@Entity
@Cacheable(true)
public class Product {
    // ...
}
```

hoặc:

```java
@Entity
@Cacheable(false)
public class AuditEvent {
    // ...
}
```

`@Cacheable` thể hiện metadata mong muốn theo shared cache mode, không bắt buộc ứng dụng phải gọi eviction sau mọi thay đổi.

### 10.2. Nếu cache không bật?

Nếu persistence unit không dùng L2, việc gọi:

```java
emf.getCache().evict(Product.class, 101L);
```

có thể không có cache entry hữu ích để loại bỏ. Không nên cố tạo “cache hit” chỉ vì mục tiêu của bài học là API eviction.

### 10.3. Không dùng Cache API để bật L2

`Cache.evict(...)` chỉ liên quan invalidation. Nó **không tự bật cache** nếu provider chưa cấu hình. Để sử dụng L2, cần thiết lập shared cache mode và cấu hình cache provider/region phù hợp với môi trường.

## 11. Cache retrieve/store modes cho một lần đọc

JPA có những enum và hints chuẩn cho cache behavior của một thao tác:

- `CacheRetrieveMode.USE`.
- `CacheRetrieveMode.BYPASS`.
- `CacheStoreMode.USE`.
- `CacheStoreMode.BYPASS`.
- `CacheStoreMode.REFRESH`.

Cần phân biệt **cache hint trong một thao tác đọc** với **eviction toàn cục của shared cache entry**.

### 11.1. BYPASS khi đọc

Ví dụ:

```java
import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.EntityManager;

Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);

Product product = em.find(
    Product.class,
    101L,
    hints
);
```

Đoạn code cần `java.util.Map`. `CacheRetrieveMode.BYPASS` yêu cầu không dùng shared cache để lấy dữ liệu trong thao tác tương ứng.

**Quan trọng:** Nếu Product#101 đã managed trong **chính EntityManager đó**, `find()` có thể trả instance từ L1. BYPASS của shared cache **không biến `find()` thành truy vấn luôn bỏ qua L1**.

### 11.2. BYPASS không đồng nghĩa evict

```text
BYPASS:
    Lần đọc hiện tại không dùng L2 để retrieve state.

EVICT:
    Loại bỏ entry L2 để các lần truy cập liên quan
    không còn dùng chính entry đó.
```

Một query BYPASS không nhất thiết xóa entry cũ trong shared cache. Nếu cache entry đã stale và cần invalidation rộng hơn, hãy xem chính sách cache store/refresh và `evict` phù hợp.

### 11.3. REFRESH store mode

Ví dụ một lần đọc cố hướng tới việc cập nhật shared cache từ database:

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS,
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.REFRESH
);

Product product = em.find(
    Product.class,
    101L,
    hints
);
```

`CacheStoreMode.REFRESH` yêu cầu làm mới dữ liệu cache theo semantics của hint, nhưng không được hiểu là:

- Ép mọi managed instance ở những EntityManagers khác thay đổi tức thời.
- Làm mới tất cả query caches riêng của provider.
- Ngăn mọi transaction khác tạo race với quá trình đọc.
- Tự commit pending changes.

### 11.4. Ma trận lựa chọn

| Mục tiêu | API phù hợp |
| --- | --- |
| Xóa một entity L2 cũ | `Cache.evict(Entity.class, id)` |
| Xóa mọi cached instances của một entity type | `Cache.evict(Entity.class)` |
| Xóa mọi cached entity data của factory | `Cache.evictAll()` |
| Lần đọc này không dùng L2 để retrieve | `CacheRetrieveMode.BYPASS` |
| Có chủ đích refresh dữ liệu đã managed từ DB | `EntityManager.refresh(entity)` |
| Bỏ trạng thái managed hiện có của một EM | `EntityManager.clear()` hoặc `detach()` |

## 12. Khi nào JPA tự quản lý cache consistency?

Một entity được thay đổi theo đường quản lý thông thường:

```java
EntityTransaction tx = em.getTransaction();

tx.begin();

Product product = em.find(Product.class, 101L);
product.changePrice(new BigDecimal("120.00"));

tx.commit();
```

Trong một cấu hình cache có hỗ trợ và tuân thủ hợp đồng provider, JPA/provider có trách nhiệm phối hợp dữ liệu entity đã thay đổi với cơ chế cache của nó. **Không cần thêm `evict(Product.class, 101L)` vào mọi thao tác `persist`, `merge` hay dirty checking chỉ vì ứng dụng có L2.**

### 12.1. Tránh invalidation thủ công dư thừa

Một service:

```java
@Transactional
public void changePrice(long id, BigDecimal price) {
    Product product = em.find(Product.class, id);
    product.changePrice(price);
    emf.getCache().evict(Product.class, id);
}
```

không nhất thiết tốt hơn phương án để provider quản lý cache cho thao tác entity thông thường. Gọi eviction trong lúc transaction còn mở còn đặt ra câu hỏi về thời điểm invalidation và khả năng cache bị nạp lại giữa transaction.

Chỉ thêm eviction khi có **lý do rõ ràng**: cập nhật ngoài provider, tích hợp cache đặc biệt hoặc trường hợp provider-specific cần giải pháp nhất định.

### 12.2. Những thao tác đáng quan tâm hơn

Các tình huống dễ làm cache mất đồng bộ là:

- SQL UPDATE/DELETE thực thi ngoài đường quản lý entity thông thường.
- JPQL bulk update/delete.
- Native SQL trực tiếp.
- Stored procedure.
- JDBC jobs.
- Hệ thống khác ghi thẳng database.
- ETL/import chạy đồng thời.
- Migration hoặc data correction.

Trong các trường hợp này, provider có thể không biết chính xác những entity entries nào đã thay đổi. **Không được mặc định rằng mọi cache đều tự invalidated chính xác theo từng ID.**

## 13. Sau JPQL bulk UPDATE: xử lý cả L1 và L2

JPQL bulk update:

```jpql
UPDATE Product p
SET p.active = false
WHERE p.price < :threshold
```

được thực thi bằng:

```java
int rows = em.createQuery(
        "UPDATE Product p " +
        "SET p.active = false " +
        "WHERE p.price < :threshold"
    )
    .setParameter(
        "threshold",
        new BigDecimal("10.00")
    )
    .executeUpdate();
```

**Bulk JPQL DML không đồng bộ từng managed entity trong persistence context giống như dirty checking thông thường.**

### 13.1. Hai vấn đề độc lập

Sau bulk UPDATE có thể tồn tại:

1. **L1 stale:** EntityManager đang giữ Product objects với state cũ.
2. **L2 stale hoặc invalidation chưa phù hợp:** shared cache có thể còn entries không khớp dữ liệu mới nếu provider không xử lý tự động ở phạm vi cần thiết.

Provider có thể có cơ chế tự invalidation cho bulk JPQL; hành vi cụ thể phụ thuộc implementation, query type và configuration. Không phải cứ thấy bulk UPDATE là kết luận chắc chắn mọi L2 entry stale, nhưng **phải thiết kế và xác minh**.

### 13.2. Quy trình minh họa

Trong transaction:

```java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    // Nếu có managed changes phải được ghi trước bulk DML.
    em.flush();

    em.createQuery(
        "UPDATE Product p " +
        "SET p.active = false " +
        "WHERE p.price < :threshold"
    )
    .setParameter(
        "threshold",
        new BigDecimal("10.00")
    )
    .executeUpdate();

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Sau khi commit thành công, nếu provider/architecture đòi manual invalidation và không xác định được IDs:

```java
emf.getCache().evict(Product.class);
```

Nếu ứng dụng vẫn dùng EntityManager cũ đã load Products, phải xử lý L1 riêng, hoặc kết thúc scope cũ và mở EM mới.

### 13.3. Không gọi clear() bừa bãi

Nếu transaction có các pending managed changes cần giữ, `em.clear()` trước flush có thể làm mất chúng.

Một cách tổ chức an toàn là cho batch operation chạy trong **EntityManager riêng**, kết thúc transaction rồi đóng EM; các request mới dùng persistence context mới. Nếu thực sự cần clear trong transaction, phải hiểu trạng thái flush và tác động tới các entities khác.

### 13.4. Tại sao thời điểm invalidation quan trọng?

Nếu evict trước khi transaction bulk DML commit, một request khác có thể cache-miss và nạp **dữ liệu cũ chưa bị thay đổi** từ database, sau đó lưu lại vào L2.

Nếu evict sau commit, vẫn có race window trước lúc evict, và provider/cluster cache có thể có quy tắc consistency khác.

Vì vậy “evict sau commit” là một **điểm phối hợp thường hợp lý**, không phải bằng chứng có atomic consistency giữa commit database và eviction trong mọi hệ thống.

## 14. Sau native SQL và stored procedure

Ứng dụng có thể chạy:

```java
em.createNativeQuery(
    "UPDATE products SET price = ? WHERE id = ?"
)
.setParameter(1, new BigDecimal("150.00"))
.setParameter(2, 101L)
.executeUpdate();
```

Nếu provider không nhận diện đầy đủ những bảng/rows bị thay đổi để làm mới cache, L2 có nguy cơ không đồng bộ. Một stored procedure còn có thể thay đổi nhiều bảng mà code JPA không biết.

### 14.1. Khi biết chính xác ID

```java
emf.getCache().evict(Product.class, 101L);
```

### 14.2. Khi biết loại entity nhưng không biết IDs

```java
emf.getCache().evict(Product.class);
```

### 14.3. Khi thay đổi nhiều entity types

```java
Cache cache = emf.getCache();

cache.evict(Product.class);
cache.evict(Category.class);
cache.evict(InventoryBalance.class);
```

Phạm vi này có thể tốt hơn `evictAll()` nếu biết rõ tập entity types bị ảnh hưởng.

### 14.4. Nếu stored procedure cập nhật bảng liên quan

Giả sử:

```text
update_catalog_data()
    |
    +-- UPDATE products
    +-- UPDATE categories
    +-- UPDATE prices
```

Không thể chỉ evict Product rồi khẳng định Category cache vẫn đúng. Cần xác định **những entity types và associations** có state bị thay đổi bởi procedure.

Một chiến lược có thể gồm:

- Định nghĩa contract “routine này thay đổi những bảng/entity nào”.
- Sau commit thành công, phát sự kiện invalidation chứa entity types/IDs.
- Xử lý entity caches và cache regions riêng nếu được sử dụng.
- Có integration tests trên provider/driver thực tế.

## 15. Hệ thống bên ngoài cập nhật database

Đây là use case rõ ràng nhất của manual eviction.

Ví dụ:

```text
Application A:
    JPA + EntityManagerFactory
    L2 cached Product#101 price=100

External ERP:
    UPDATE products SET price=120 WHERE id=101
    COMMIT

Application A:
    Nếu L2 chưa được invalidated,
    lần đọc mới có thể thấy price=100
```

### 15.1. Một quy trình phù hợp

```text
External writer commits update
            |
            v
Publish change event (productId=101)
            |
            v
Application receives event
            |
            v
emf.getCache().evict(Product.class, 101L)
            |
            v
Future reads from a fresh EM
can reload updated database state
```

### 15.2. Sự kiện có thể đến muộn

Nếu external writer commit lúc 10:00:00 nhưng event đến lúc 10:00:03, trong ba giây đó ứng dụng có thể đọc cache cũ.

Tùy nghiệp vụ, có thể chấp nhận **eventual consistency** hoặc cần cơ chế phối hợp chặt hơn. Manual eviction không biến distributed event delivery thành atomic database/cache transaction.

### 15.3. Sự kiện có thể lặp

Một consumer có thể nhận cùng event nhiều lần. Gọi:

```java
cache.evict(Product.class, 101L);
```

nhiều lần thường vẫn tương thích với ý định “không giữ entry này”, nhưng các workflow có thêm logic ngoài eviction cần thiết kế idempotent. Không dùng “event chỉ đến một lần” làm điều kiện correctness.

### 15.4. Thứ tự event có thể bị đảo

Một sản phẩm thay đổi từ version 5 → 6 → 7. Nếu event version 7 đến trước event version 6, một cơ chế cache update trực tiếp có thể ghi dữ liệu cũ lên mới.

**Eviction** đơn thuần thường ít phụ thuộc payload version hơn **cache put** trực tiếp, nhưng race giữa load, event và invalidation vẫn cần được đánh giá. Với yêu cầu nhất quán cao, có thể cần version-aware cache keys/entries, transactional messaging hoặc kiến trúc chuyên dụng.

## 16. Nhiều application instances và cache phân tán

Một hệ thống sản xuất có thể chạy:

```text
                   Load balancer
                 /      |       \
                v       v        v
             App A    App B    App C
              |        |        |
           EMF/L2   EMF/L2    EMF/L2
                 \     |      /
                    Database
```

Gọi:

```java
emf.getCache().evict(Product.class, 101L);
```

trên App A **không tự bảo đảm** L2 ở App B và App C được invalidated nếu cache của chúng là local/không có cơ chế cluster coordination phù hợp.

### 16.1. Có hai kiểu triển khai

**Cache cục bộ mỗi instance:**

- App A có L2 riêng.
- App B có L2 riêng.
- Evict ở A chỉ xử lý cache trong phạm vi provider/EMF của A.
- Cần event invalidation/coordination để B biết thay đổi.

**Distributed/coherent cache provider:**

- Nhiều instances có thể dùng cache cluster hỗ trợ invalidation hoặc đồng bộ.
- Hành vi vẫn phụ thuộc cấu hình consistency mode và topology.
- Cần xác nhận chuyện key ownership, replication và failure recovery.

### 16.2. Không suy từ tên "second-level cache" ra tính phân tán

L2 có nghĩa là cache nằm ngoài persistence context của một EntityManager và có thể dùng chung trong phạm vi factory. Nó **không mặc nhiên là Redis, không mặc nhiên có cluster invalidation và không mặc nhiên đảm bảo linearizable reads**.

### 16.3. Khi hệ thống cần đọc mới nhất tuyệt đối

Nếu một use case yêu cầu đọc dữ liệu chính xác tại một điểm transaction, không nên chỉ dựa vào cache eviction bất đồng bộ. Cần xem:

- Transaction isolation.
- Cơ chế lock/version.
- Bypass cache với một EntityManager phù hợp.
- Đọc trực tiếp database.
- Consistency mode của distributed cache.
- Trình tự commit và thông báo invalidation.

Đánh đổi correctness/availability/performance phải được xác định theo nghiệp vụ.

## 17. Entity cache khác query result cache

Một tình huống:

```jpql
SELECT p
FROM Product p
WHERE p.active = true
ORDER BY p.name
```

Một số provider có **query result cache** riêng, lưu danh sách IDs hoặc dữ liệu tương đương của kết quả truy vấn. Đây là tính năng thường **provider-specific**, không phải mặc định được điều khiển đầy đủ bởi `jakarta.persistence.Cache`.

### 17.1. Hai loại stale data

Giả sử Product#101 đổi `active` từ true sang false.

**Entity L2 cache stale:** thông tin entity Product#101 có `active=true` cũ.

**Query cache stale:** cache của câu truy vấn “active products” vẫn chứa ID 101 trong danh sách kết quả.

Evict entity Product#101 có thể giải quyết entry entity cũ nhưng **không nhất thiết loại bỏ danh sách IDs của query cache** trong mọi provider.

### 17.2. Cache của Hibernate

Hibernate có API/cấu hình riêng cho query cache và các entity/collection regions. Việc xóa query result cache hoặc collection cache theo region có thể cần Hibernate-specific API từ `SessionFactory`/`Cache` của Hibernate.

Đừng đặt những lệnh gọi Hibernate-specific dưới nhãn **“API Cache chuẩn JPA”**. Khi dùng extension, cần ghi rõ sự phụ thuộc provider và version.

### 17.3. Application cache còn là tầng khác

Spring `@Cacheable` dùng `CacheManager`, Caffeine/Redis có cơ chế key TTL/evict riêng; JPA `Cache.evictAll()` không tự xóa dữ liệu trong những cache application đó.

Ví dụ:

```text
Controller -> Spring service cache
                   |
                   v
             JPA EntityManager
                   |
                   v
             JPA second-level cache
                   |
                   v
                Database
```

Nếu Spring service cache chứa DTO Product#101 cũ, việc evict JPA L2 **không sửa DTO đang nằm trong Spring cache**.

## 18. Collection cache và association graph

Giả sử:

```java
@Entity
public class Category {

    @Id
    private Long id;

    @OneToMany(mappedBy = "category")
    private List<Product> products;
}
```

Một provider có thể cache:

- Entity data của Category.
- Entity data của Product.
- Collection membership của `category.products` trong một region riêng.
- Query results của các truy vấn liên quan.

### 18.1. Xóa Product không chắc xóa collection membership

Khi một Product được chuyển sang Category khác, thông tin:

```text
Category#10.products contains Product#101
```

có thể nằm trong collection cache riêng của provider.

`Cache.evict(Product.class, 101L)` không phải một lời hứa portable rằng collection membership của tất cả Categories đã được invalidated phù hợp.

### 18.2. Xóa Category cũng không phải cascade eviction

```java
cache.evict(Category.class, 10L);
```

không được hiểu là tự xóa toàn bộ `Product` entities liên quan, bất kể `CascadeType.ALL` hoặc `FetchType.EAGER`.

**Fetch, cascade và cache eviction là các cơ chế độc lập.**

### 18.3. Khi thay đổi quan hệ

Cần xác định:

- Foreign key/membership thay đổi ở đâu.
- Những entity cache entries nào chứa state liên quan.
- Collection regions nào được cache.
- Query cache có lưu danh sách liên quan không.
- Provider có tự invalidation với managed changes không.
- Nếu external writer thay đổi quan hệ, cơ chế đồng bộ nào cần bổ sung.

Không chỉ nhìn một dòng `cache.evict(Entity.class, id)` rồi khẳng định toàn bộ graph đã được làm mới.

## 19. Mẫu CacheInvalidationService đơn giản

Trong ứng dụng Java hoặc Spring, có thể bọc API chuẩn để đặt tên hành vi rõ hơn và tránh lạm dụng `evictAll()`.

```java
package com.example.catalog;

import jakarta.persistence.Cache;
import jakarta.persistence.EntityManagerFactory;
import java.util.Collection;
import java.util.Objects;

public final class CatalogCacheInvalidator {

    private final EntityManagerFactory emf;

    public CatalogCacheInvalidator(
            EntityManagerFactory emf) {
        this.emf = Objects.requireNonNull(emf);
    }

    public void evictProduct(long productId) {
        Cache cache = emf.getCache();
        cache.evict(Product.class, productId);
    }

    public void evictProducts(
            Collection<Long> productIds) {

        Objects.requireNonNull(productIds);

        Cache cache = emf.getCache();

        for (Long id : productIds) {
            cache.evict(
                Product.class,
                Objects.requireNonNull(id)
            );
        }
    }

    public void evictAllProducts() {
        emf.getCache().evict(Product.class);
    }

    public void evictAllEntityCache() {
        emf.getCache().evictAll();
    }
}
```

### 19.1. Vì sao tách service?

- Rõ mục đích “làm mất hiệu lực Product cache”.
- Không để mọi layer tùy ý gọi `evictAll()`.
- Có nơi để ghi metrics/audit khi invalidation xảy ra.
- Dễ bổ sung event fan-out tới các instances nếu cần.
- Có chỗ để thêm provider-specific behavior trong infrastructure, không rò sang domain.

### 19.2. Đừng che giấu tác động rộng

Tên method nên thể hiện phạm vi. `evictAllEntityCache()` là thao tác lớn hơn rất nhiều so với `evictProduct(id)`.

Không viết một method chung tên `refreshCache()` mà bên trong gọi `evictAll()` cho tất cả yêu cầu.

### 19.3. Service không giải quyết transaction timing

Bọc `Cache` không tự bảo đảm call được thực hiện sau commit. Caller vẫn cần điều phối thời điểm invalidation phù hợp với nguồn dữ liệu được sửa.

## 20. Spring: eviction sau transaction commit

Một use case có external/native update được điều phối trong Spring transaction có thể cần **chỉ phát invalidation sau khi transaction commit thành công**.

Có thể triển khai:

```java
import jakarta.persistence.EntityManagerFactory;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public void registerEvictionAfterCommit(
        EntityManagerFactory emf,
        long productId) {

    if (!TransactionSynchronizationManager
            .isSynchronizationActive()) {
        throw new IllegalStateException(
            "A Spring transaction synchronization is required"
        );
    }

    TransactionSynchronizationManager
        .registerSynchronization(
            new TransactionSynchronization() {

                @Override
                public void afterCommit() {
                    emf.getCache().evict(
                        Product.class,
                        productId
                    );
                }
            }
        );
}
```

Đoạn code minh họa Spring infrastructure; nó cần được gọi ở vị trí phù hợp trong transaction đang hoạt động, nơi transaction synchronization được bật. Chỉ kiểm tra synchronization active chưa tự chứng minh transaction đang ghi database đúng mà nghiệp vụ cần.

### 20.1. Điều gì tốt hơn so với evict trước commit?

Nếu transaction rollback, callback `afterCommit()` sẽ không chạy như một commit thành công; ứng dụng tránh invalidation vô ích cho những thay đổi chưa tồn tại.

### 20.2. Điều gì vẫn chưa được giải quyết?

- Có một khoảng thời gian giữa database commit và callback eviction.
- Callback có thể lỗi khi database đã commit.
- Event invalidation phân tán có thể đến muộn hoặc mất.
- Những EntityManagers khác vẫn có state trong L1.
- Query/collection caches riêng có thể cần cơ chế khác.

Do đó cách này là một **mẫu tích hợp hữu ích**, không phải một transaction phân tán nguyên tử giữa database và cache.

### 20.3. Với managed JPA updates thông thường

Nếu thao tác chỉ thay đổi một `Product` managed và provider đã quản lý L2 consistency đúng, không cần tự đăng ký callback eviction chỉ để lặp lại cơ chế provider. Trước khi thêm manual invalidation, phải có yêu cầu cụ thể.

## 21. Hành vi sau eviction và race conditions

Eviction là một hành động vào cache tại một thời điểm. Các transaction khác vẫn có thể đang tải dữ liệu.

Ví dụ:

```text
T1: Reader A cache miss, bắt đầu SELECT Product#101
T2: Writer B commit price=120
T3: Writer B evict Product#101
T4: Reader A nhận kết quả price=100 từ snapshot cũ
T5: Provider/cache có thể xử lý kết quả load theo policy riêng
```

Nếu cache provider không có cơ chế versioning/coordination đúng, một cache fill chậm có thể làm dữ liệu cũ xuất hiện lại sau eviction.

**Không dùng một lần evict thủ công làm chứng minh tuyệt đối về linearizability** khi có concurrent loads và writes.

### 21.1. Cách giảm rủi ro

- Dùng cache provider có consistency strategy phù hợp.
- Có version hoặc timestamp để nhận diện stale state.
- Phát event invalidation từ nguồn update đáng tin.
- Tạo idempotent invalidation event processing.
- Cân nhắc bypass cache cho những luồng cần độ mới cao.
- Kiểm thử concurrent read/write theo DBMS/provider thật.

### 21.2. Trường hợp yêu cầu mạnh hơn eventual consistency

Ví dụ chính sách giá tại thời điểm thanh toán có thể yêu cầu **xác nhận giá hiện hành trong transaction** thay vì dựa trên catalog L2 cache đã từng hiển thị ở UI.

Cached catalog phù hợp để duyệt sản phẩm, nhưng nghiệp vụ thanh toán phải có cách xác nhận state theo invariant và consistency phù hợp.

## 22. Độ rộng eviction và tác động hiệu năng

Có ba lựa chọn chính:

| Phương án | Khả năng xóa dữ liệu liên quan | Tác động cache hit |
| --- | --- | --- |
| `evict(Product.class, id)` | Một entry entity | Thường nhỏ nhất |
| `evict(Product.class)` | Toàn bộ Product entity entries | Trung bình đến lớn |
| `evictAll()` | Mọi cached entity data trong phạm vi factory | Rộng nhất |

### 22.1. Chọn mức hẹp nhất đủ đúng

Nếu biết chính xác ID, ưu tiên eviction theo ID. Nếu thay đổi không rõ IDs nhưng có thể giới hạn entity type, dùng eviction theo class. Chỉ dùng `evictAll()` khi lý do và tác động đã được đánh giá.

### 22.2. Cache stampede

Sau eviction rộng, 1.000 requests có thể cùng yêu cầu một Product rất phổ biến. Tùy cache strategy, nhiều request có thể cùng truy vấn database và làm tăng tải đột ngột.

Các kỹ thuật mitigation phụ thuộc provider/hạ tầng:

- Cache warmup.
- Rate limiting ở tầng app.
- Request coalescing/single-flight.
- TTL và refresh policies.
- Phân vùng cache.
- Chủ động điều tiết batch invalidation.

JPA `Cache` chuẩn không cung cấp đầy đủ API cho các chiến lược này.

### 22.3. Eviction không xóa dung lượng database

`cache.evictAll()` không phải `DELETE FROM products`. Nó không xóa rows hoặc schema và không giải phóng dung lượng bảng database. Nó chỉ tác động tới dữ liệu cached trong phạm vi API tương ứng.

## 23. Một ví dụ theo dòng thời gian: Product bị thay đổi ngoài JPA

Giả sử:

```text
Database Product#101:
    price=100, version=3

L2 Product#101:
    price=100, version=3
```

Một external job chạy, **commit**:

```sql
UPDATE products
SET price = 120,
    version = version + 1
WHERE id = 101;
```

External writer đã cập nhật version theo contract ví dụ. Nhưng App A có thể vẫn giữ L2 entry price=100/version=3 nếu không nhận thông báo invalidation.

### 23.1. Chỉ evict entry cụ thể

```java
emf.getCache().evict(Product.class, 101L);
```

### 23.2. Đọc bằng EntityManager mới

```java
EntityManager em = emf.createEntityManager();

try {
    Map<String, Object> hints = Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    );

    Product product =
        em.find(Product.class, 101L, hints);

    System.out.println(product.getPrice());
} finally {
    em.close();
}
```

Nếu database transaction, isolation và external update đã commit như giả định, lần đọc mới có thể lấy price=120. `BYPASS` được sử dụng để diễn đạt rõ nhu cầu không đọc state từ L2 trong lần `find`.

Không suy kết quả trên thành lời hứa rằng mọi transaction/session đều nhìn thấy ngay cùng snapshot bất kể isolation hay replication lag.

### 23.3. Một EntityManager cũ thì sao?

Nếu EM cũ đang managed Product#101 price=100, eviction của L2 không thay đổi object ấy.

Cần kết thúc persistence context cũ hoặc chủ động refresh theo nghiệp vụ và transaction state. Đừng tiếp tục dùng giá trị cũ trong một phép tính nhạy cảm chỉ vì đã gọi `cache.evict` ở nơi khác.

## 24. Composite ID, tenant và bảo mật

Cache keys phải tương ứng đúng với entity identity.

### 24.1. Composite primary key

```java
cache.evict(
    InventoryBalance.class,
    new InventoryBalanceId(3L, 101L)
);
```

Đoạn này giả định `InventoryBalanceId` có constructor và `equals/hashCode` phù hợp. Không thay key bằng chuỗi `"3-101"` nếu mapping JPA dùng ID class.

### 24.2. Multi-tenancy

Trong multi-tenant system, cùng ID `101` có thể xuất hiện ở hai tenants. Cách provider xây cache key/region có thể phụ thuộc tenant configuration.

Không cho phép một request tự chọn tenant/key tùy ý để evict data của tenant khác. Đồng thời không giả định `evict(Product.class, 101L)` từ một tenant context sẽ có hiệu lực “đúng tenant” trên mọi provider; phải hiểu multi-tenant cache behavior của implementation.

### 24.3. Eviction không phải authorization

Một API nội bộ nhận `entityClass` và `id` rồi cho caller gọi `evictAll()` có thể tạo rủi ro denial-of-service về hiệu năng. Chỉ expose các hành động invalidation cần thiết và có quyền kiểm soát.

Không cung cấp endpoint công khai như:

```text
POST /admin/cache/evictAll
```

mà không có xác thực, phân quyền, audit, rate limiting và kế hoạch vận hành phù hợp.

## 25. Cache API không thay thế chiến lược transaction

Có những hiểu nhầm:

> “Tôi evict trước khi cập nhật, vậy lần đọc tiếp theo chắc chắn thấy dữ liệu mới.”

Không. Nếu transaction update chưa commit, một reader có thể đọc lại dữ liệu cũ và tái đưa nó vào cache.

> “Tôi evict sau khi cập nhật entity, vậy không cần commit.”

Không. Eviction không lưu dữ liệu hoặc kết thúc transaction.

> “Tôi gọi evictAll trong transaction, rollback sẽ phục hồi cache entry.”

Không có hợp đồng JPA chuẩn biến eviction và rollback database thành một transaction nguyên tử. **Không dựa vào rollback để tự khôi phục những entries đã bị evict.**

> “Đã evict, một EntityManager đang mở sẽ tự thấy version mới.”

Không. L1 có đời sống riêng.

### 25.1. Một bảng phân biệt thao tác

| Thao tác | Có ghi database? | Có tác động L1? | Có tác động L2? |
| --- | --- | --- | --- |
| `em.flush()` | Có thể thực thi DML pending | Đồng bộ managed changes | Provider có thể phối hợp theo chiến lược |
| `tx.commit()` | Hoàn tất transaction nếu thành công | Context/lifecycle theo loại EM | Provider đồng bộ cache theo chính sách |
| `em.refresh(entity)` | Đọc lại dữ liệu từ DB theo semantics | Làm mới managed instance | Tùy cache strategy/hints |
| `em.clear()` | Không tự commit DML | Detach toàn bộ managed entities | Không tự evict L2 |
| `emf.getCache().evict(Entity.class, id)` | Không | Không tự detach/refresh | Xóa entity entry tương ứng |
| `emf.getCache().evict(Entity.class)` | Không | Không tự clear EM khác | Xóa entries của entity type |
| `emf.getCache().evictAll()` | Không | Không tự clear mọi EM | Xóa shared cached entity data |

## 26. Kiểm thử cache eviction đúng cách

Caching phụ thuộc provider và cấu hình, nên cần integration tests với cùng DBMS/provider/cache strategy mục tiêu.

### 26.1. Những câu hỏi test quan trọng

1. Entity type có thực sự cacheable không?
2. Sau một lần đọc và đóng EntityManager, provider có đưa entity vào L2 không?
3. `cache.contains(...)` phản ánh trạng thái cache mà provider cung cấp như thế nào?
4. Evict theo ID có làm entry tương ứng biến mất không?
5. Evict theo class có ảnh hưởng những IDs khác của class đó không?
6. EvictAll có ảnh hưởng các entity cache regions liên quan không?
7. EntityManager cũ có tiếp tục giữ managed instance không?
8. Query cache riêng có cần invalidation khác không?
9. External/native/bulk update có làm dữ liệu đọc lại mới đúng không?
10. Nhiều app nodes có nhận invalidation đúng không?

### 26.2. Test phải phân biệt hai EntityManagers

Không nên:

```java
Product p1 = em.find(Product.class, 101L);
cache.evict(Product.class, 101L);
Product p2 = em.find(Product.class, 101L);

assertNotSame(p1, p2);
```

Vì cùng EntityManager có thể trả cùng một managed instance; test đó **hiểu sai phạm vi của Cache.evict**.

### 26.3. Mẫu kiểm tra có tính định hướng

```java
Cache cache = emf.getCache();

EntityManager em1 = emf.createEntityManager();
try {
    em1.find(Product.class, 101L);
} finally {
    em1.close();
}

boolean before =
    cache.contains(Product.class, 101L);

cache.evict(Product.class, 101L);

boolean after =
    cache.contains(Product.class, 101L);

System.out.println(
    "Cache before=" + before + ", after=" + after
);

EntityManager em2 = emf.createEntityManager();
try {
    Product p = em2.find(Product.class, 101L);
    // Kiểm tra nghiệp vụ/state theo DB fixture.
} finally {
    em2.close();
}
```

Đây là **mẫu quan sát**, không phải unit test portable yêu cầu `before` luôn true: nếu L2 không bật/không lưu Product, `before` có thể false.

### 26.4. Không dùng SQL count làm sự thật duy nhất

Số SQL queries có thể bị tác động bởi:

- L1.
- L2.
- JDBC/database cache.
- Query cache riêng.
- EAGER associations.
- Batching.
- Các truy vấn phụ của provider.

Nên đối chiếu SQL logs với metrics 2LC hit/miss/put/evict của provider nếu có, trong điều kiện test đã cô lập và dữ liệu ổn định.

### 26.5. Test external writer

Để kiểm tra stale L2 thực sự:

1. Tạo dữ liệu test và đưa entity vào cache nếu config cho phép.
2. Dùng connection/transaction **ngoài đường JPA provider đang quản lý** để cập nhật database.
3. Commit external write.
4. Kiểm tra behavior của một EntityManager mới trước/sau invalidation.
5. Xác nhận giá trị version/business fields đúng.
6. Kiểm tra case multi-node nếu sản phẩm có nhiều instances.

Nếu dùng `em.createNativeQuery("UPDATE ...")` qua cùng provider, provider có thể tự biết bảng bị thay đổi và invalidated cache — vì vậy test này **không hoàn toàn tương đương external writer độc lập**.

## 27. Lưu ý về SQL bulk DELETE

Nếu một JPQL bulk delete hoặc external job xóa Product#101:

```sql
DELETE FROM products WHERE id = 101;
```

mà L2 vẫn chứa entry cũ, ứng dụng có thể gặp dữ liệu không khớp database trong lần đọc sau nếu cache strategy không bảo vệ.

Một invalidation theo ID:

```java
cache.evict(Product.class, 101L);
```

có thể cần thiết khi writer ngoài JPA commit.

### 27.1. L1 vẫn có object cũ

EntityManager mở trước đó có thể đang managed Product#101 và vẫn trả object này. Xóa L2 không khiến JPA tự biến managed object đó thành `null`.

### 27.2. Quan hệ và FK

Khi Product bị xóa, một association cache hoặc query cache liên quan có thể vẫn chứa membership cũ. Không nên chỉ evict Product rồi khẳng định mọi Category/Product relationship đều được cập nhật. Cần xem toàn bộ data flow và cache regions.

### 27.3. @Version và external DELETE

Nếu managed entity sau đó bị cập nhật theo version/ID cũ, provider có thể báo optimistic locking failure hoặc lỗi liên quan. Cache eviction không thay thế cơ chế phát hiện xung đột ở thời điểm ghi.

## 28. Những sai lầm thường gặp

### 28.1. Dùng EntityManager.clear() để xóa L2

Sai. `clear()` chỉ detach managed objects trong một persistence context.

### 28.2. Dùng Cache.evictAll() để xóa L1 của mọi EM

Sai. Eviction L2 không tự xóa managed instances đang có.

### 28.3. Nghĩ evict() thực thi DELETE SQL

Sai. Nó không xóa database rows.

### 28.4. Nghĩ evict() tự commit transaction

Sai. Nó không thay thế `commit()`.

### 28.5. Kiểm tra contains() rồi mới evict như một thao tác nguyên tử

Sai. Có race condition giữa hai calls; có thể evict trực tiếp.

### 28.6. Nghĩ contains() = true chứng minh dữ liệu đang mới

Sai. Nó không so sánh với version mới nhất tại database.

### 28.7. Evict một ID nhưng kỳ vọng mọi entities liên quan bị xóa theo cascade

Sai. Cache eviction không phải cascade PERSIST/MERGE/REMOVE.

### 28.8. Evict entity nhưng quên query cache

Sai nếu provider cache cả kết quả truy vấn và không tự invalidation đầy đủ.

### 28.9. Evict entity nhưng quên collection cache

Sai nếu membership của collection được cache ở region riêng.

### 28.10. EvictAll để làm mới Spring @Cacheable

Sai. Spring CacheManager có API và key space riêng.

### 28.11. Tự evict mọi lúc sau JPA-managed update

Không nhất thiết. Provider thường chịu trách nhiệm cache consistency cho managed changes theo contract của nó; eviction dư thừa làm giảm cache hit và tăng race complexity.

### 28.12. Evict trước khi writer commit rồi cho rằng đã xong

Sai. Reader khác có thể cache miss rồi nạp dữ liệu database cũ.

### 28.13. Cho rằng afterCommit eviction là atomic với database commit

Sai. Có thể có race window/callback failure.

### 28.14. Cho rằng eviction ở App A luôn làm App B mất cache entry

Sai nếu chưa có cơ chế distributed cache coherence hoặc invalidation messaging phù hợp.

### 28.15. Chạy evictAll sau mỗi request

Không phù hợp về hiệu năng: xóa lợi ích của L2 và tạo cache misses lớn.

### 28.16. Gọi refresh() trên detached entity

`refresh()` yêu cầu entity managed theo semantics JPA; không được dùng thay cho merge/find tùy tiện.

### 28.17. Clear persistence context đang có pending changes mà không hiểu hậu quả

Có thể bỏ các thay đổi chưa đồng bộ.

### 28.18. Dùng BYPASS và kỳ vọng bỏ qua L1

Cache retrieve hint dành cho shared cache; managed entity có thể vẫn được trả từ persistence context.

### 28.19. Cho rằng cache API tự bật L2

Không. Shared cache mode/provider configuration mới quyết định caching.

### 28.20. Không tính composite ID/tenant vào eviction key

Có thể xóa sai phạm vi hoặc không xóa được entry mong muốn.

### 28.21. Nghĩ evictAll xóa cache của mọi EntityManagerFactory trong process

Mỗi factory có cache scope riêng theo provider; không giả định một lời gọi tự điều phối mọi factories.

### 28.22. Dùng Cache để giải quyết dirty read/lost update

Sai mục tiêu. Các vấn đề transaction isolation và concurrency cần transaction/locking/version/invariants tương ứng.

## 29. Bài tập thực hành

### Bài 1 — Xóa một sản phẩm

Ứng dụng biết external job đã cập nhật Product#200.

**Đáp án:**

```java
emf.getCache().evict(Product.class, 200L);
```

Đây là invalidation hẹp cho một entity.

### Bài 2 — Xóa mọi sản phẩm

Một batch job thay đổi giá toàn bộ danh mục Products, không còn danh sách ID chính xác.

**Đáp án:**

```java
emf.getCache().evict(Product.class);
```

Phải đánh giá tác động cache misses sau đó.

### Bài 3 — Migration nhiều entity types

Migration thay đổi dữ liệu Products, Categories và Suppliers.

**Gợi ý:** Nếu biết các types, có thể evict từng class tương ứng; `evictAll()` chỉ khi cần phạm vi rộng hơn. Cần kiểm tra query/collection caches riêng.

### Bài 4 — L1 stale sau evict

Một EntityManager đã load Product#101. Sau đó gọi `emf.getCache().evict(Product.class,101L)` và `em.find(Product.class,101L)` vẫn cho instance cũ.

**Đáp án:** Hoàn toàn có thể vì L1 đang managed. Cần refresh/clear/detach hoặc EntityManager mới tùy ngữ cảnh.

### Bài 5 — Xóa L2 bằng clear()

```java
em.clear();
```

**Câu hỏi:** Mọi cached Product trong factory có bị evict?

**Đáp án:** Không. Đây là thao tác của persistence context.

### Bài 6 — Cache chứa hay entity managed?

```java
em.contains(p);
emf.getCache().contains(Product.class,p.getId());
```

**Đáp án:** Dòng đầu kiểm tra managed instance trong L1; dòng sau kiểm tra shared cache entry.

### Bài 7 — contains() rồi evict()

Hai threads có thể thêm/xóa cache entry xen kẽ.

**Đáp án:** Không dựa vào check-then-evict để tạo atomicity; gọi evict trực tiếp khi có sự kiện invalidation.

### Bài 8 — Bulk update trong same EntityManager

Một service load 10 Products rồi thực hiện JPQL bulk update đổi active.

**Đáp án:** Managed Products có thể stale. Cần xử lý L1 riêng, và xem chính sách L2 invalidation của provider; đừng chỉ evict L2.

### Bài 9 — SQL update bên ngoài

ERP commit giá mới nhưng ứng dụng không nhận event trong vài giây.

**Đáp án:** Có cửa sổ eventual consistency. Cache API không tự biết những external writes; cần event/coordination hoặc bypass cache cho use case nhạy cảm.

### Bài 10 — Query cache stale

Query cache của "active products" vẫn trả ID của sản phẩm vừa inactive dù entity Product#101 đã evicted.

**Đáp án:** Cần xem query cache provider-specific và invalidation tương ứng. `Cache.evict(Product.class, 101L)` không phải lời hứa xóa mọi query results.

### Bài 11 — Collection cache

Một Product chuyển Category; Category.products được provider cache ở region riêng.

**Đáp án:** Phải xem cache invalidation cho collection membership, không chỉ Product entity data.

### Bài 12 — Multi-node

Evict Product#101 ở App A, App B vẫn trả giá cũ.

**Đáp án:** Kiểm tra App B dùng cache local hay distributed; thiết kế invalidation event hoặc coherent cache phù hợp.

### Bài 13 — CacheStoreMode.REFRESH

Một lần đọc muốn bypass shared cache và làm mới cache state.

**Gợi ý:** Dùng `CacheRetrieveMode.BYPASS` cùng `CacheStoreMode.REFRESH` theo query/find hints, nhưng đảm bảo EntityManager không đang giữ stale instance trong L1.

### Bài 14 — EvictAll trong API hot path

Mỗi request trang catalog gọi `evictAll()` rồi `find()`.

**Đáp án:** Không hợp lý nếu muốn tận dụng L2. Cần invalidation theo sự kiện dữ liệu thay đổi, không theo mỗi lần đọc.

### Bài 15 — Transaction rollback

Service evict Product#101 trước khi commit, sau đó update bị rollback.

**Đáp án:** Eviction không tự rollback cùng database; entry có thể đã bị xóa không cần thiết, và race fill có thể xảy ra. Phải thiết kế timing phù hợp.

### Bài 16 — Composite ID

Entity InventoryBalance có key `(warehouseId, productId)`.

**Đáp án:** Evict bằng ID object tương ứng, không chỉ một thành phần của key.

### Bài 17 — Managed update bình thường

`Product` managed được sửa qua setter rồi transaction commit, provider L2 hoạt động đúng.

**Đáp án:** Không mặc định phải gọi eviction thủ công; provider quản lý consistency theo contract của nó. Chỉ thêm invalidation nếu có lý do cụ thể.

### Bài 18 — Cache eviction và version

External SQL cập nhật giá mà không tăng version, sau đó ứng dụng evict entity.

**Đáp án:** Eviction giúp loại cache entry nhưng **không tự sửa versioning contract**. Các writer JPA khác vẫn có thể gặp lost-update risk nếu version ngoài JPA không được cập nhật đúng.

## 30. Câu hỏi tự kiểm tra

**1. Lấy giao diện cache cấp hai của một persistence unit qua API nào?**

`EntityManagerFactory.getCache()`.

**2. Giao diện Cache thuộc package nào trong Jakarta Persistence?**

`jakarta.persistence.Cache`.

**3. Xóa một entity có ID cụ thể bằng phương thức nào?**

`cache.evict(Entity.class, primaryKey)`.

**4. Xóa mọi cached entities của một entity type bằng phương thức nào?**

`cache.evict(Entity.class)`.

**5. Xóa toàn bộ cached entity data của factory bằng phương thức nào?**

`cache.evictAll()`.

**6. Phương thức nào hỏi shared cache có entry tương ứng hay không?**

`cache.contains(Entity.class, primaryKey)`.

**7. Cache.contains() có chứng minh dữ liệu mới nhất không?**

Không.

**8. EntityManager.contains(entity) khác Cache.contains(Class,id) thế nào?**

Một bên kiểm tra managed instance trong L1; bên kia kiểm tra shared L2 cache.

**9. Cache.evict có tự clear persistence context không?**

Không.

**10. em.clear() có tự evict L2 không?**

Không.

**11. em.refresh(entity) phục vụ mục đích nào?**

Làm mới state managed entity từ database theo semantics JPA, không phải xóa toàn bộ L2.

**12. Có nên clear khi còn pending changes chưa flush không?**

Cần hết sức thận trọng vì những changes có thể bị bỏ.

**13. Khi chỉ biết 3 changed IDs, nên dùng evictAll hay evict từng ID?**

Ưu tiên evict từng ID nếu đủ đáp ứng consistency requirements.

**14. @Cacheable có tự bật hạ tầng L2 không?**

Không. Còn cần shared cache mode/provider configuration phù hợp.

**15. Bulk JPQL UPDATE có tự đồng bộ mọi managed entities không?**

Không. Bulk DML có thể khiến persistence context stale.

**16. Có cần manual eviction sau mọi managed JPA update không?**

Không mặc định. Provider có trách nhiệm phối hợp cache khi cập nhật entity theo đường bình thường.

**17. Vì sao external JDBC writer là tình huống đáng quan tâm?**

Provider JPA có thể không biết những rows nào bị thay đổi để invalidation.

**18. Evict trước commit có một rủi ro gì?**

Reader khác có thể load dữ liệu cũ rồi đưa trở lại cache trước khi writer commit.

**19. Evict sau commit có bảo đảm atomic consistency không?**

Không. Có thể có race window/callback hoặc event delivery failure.

**20. Cache.evictAll có chắc xóa Hibernate query cache không?**

Không được giả định. Query cache có API/strategy riêng của provider.

**21. Cache.evict Product#101 có chắc xóa Category.products collection cache không?**

Không được giả định.

**22. Evict ở một app node có tự xóa L2 local của node khác không?**

Không nếu không có cache coherence hoặc invalidation coordination.

**23. CacheRetrieveMode.BYPASS có bypass L1 không?**

Không. Nó áp dụng với shared cache retrieval; L1 vẫn có thể trả managed instance.

**24. Eviction có viết DML xuống database không?**

Không.

**25. Lợi ích của eviction theo ID so với evictAll?**

Phạm vi nhỏ hơn, giữ được các cache entries không liên quan, giảm cache miss.

**26. Multi-tenant system cần lưu ý điều gì?**

Cache key/region và invalidation phải đúng tenant semantics, không lộ hoặc xóa sai phạm vi.

**27. Cache API chuẩn có giải quyết cache stampede không?**

Không; cần chiến lược provider/hạ tầng riêng.

**28. Kiểm thử eviction bằng một EntityManager duy nhất có thể sai ở đâu?**

L1 giữ entity nên kết quả `find` không chứng minh hiệu quả của L2 eviction.

**29. Khi nào dùng evictAll hợp lý?**

Khi thực sự cần invalidation phạm vi toàn bộ shared entity cache, có cân nhắc tác động vận hành.

**30. Nguyên tắc quan trọng nhất?**

**Xác định đúng lớp cache đang gây dữ liệu cũ và xóa ở phạm vi hẹp nhất đủ đúng, đồng thời quản lý transaction, persistence context và các cache riêng khác.**

## 31. Tình huống tổng hợp: đồng bộ giá từ ERP

Một hệ thống bán hàng dùng JPA có:

- `Product` và `Category` được L2 cache.
- Màn hình catalog có query cache của provider.
- Spring service có cache DTO riêng.
- Ba app instances cùng phục vụ request.
- ERP ghi giá mới trực tiếp vào database.

Một luồng đồng bộ đúng cần xem **nhiều loại cache**, không chỉ một lệnh `evict`.

### 31.1. Mục tiêu nghiệp vụ

Khi ERP commit Product#101 đổi giá từ 100 lên 120:

1. Các request catalog mới không giữ giá cũ quá giới hạn chấp nhận được.
2. Trang checkout phải xác nhận giá theo consistency requirement chặt hơn.
3. App B/C không dùng cache cũ mãi nếu App A đã nhận event.
4. Không xóa toàn bộ cache của mọi entity chỉ vì một Product.
5. Không làm mất pending JPA changes trong những transactions khác.
6. Không đưa dữ liệu sai vào DTO cache.

### 31.2. Luồng đề xuất

```text
ERP changes Product#101
       |
       v
ERP DB transaction COMMIT
       |
       v
Outbox/CDC/change event
       |
       v
Catalog invalidation consumer
       |
       +-- Product L2 cache:
       |     emf.getCache().evict(Product.class,101L)
       |
       +-- Provider query cache (if enabled):
       |     invalidate affected result regions
       |
       +-- Spring DTO cache:
       |     evict Product#101 / related DTO keys
       |
       +-- Other app nodes:
       |     broadcast/coherent invalidation
       |
       v
New EntityManager read
       |
       v
Reload current database state
       |
       v
Serve catalog response
```

### 31.3. Tại checkout

Không chỉ dựa vào cache entry từng hiển thị ở catalog. Checkout cần một transaction/domain rule xác định giá và tồn kho hiện hành, ví dụ sử dụng dữ liệu mới nhất theo isolation/lock/version policy thích hợp.

### 31.4. Khi event bị mất

Một hệ thống muốn chống mất event có thể sử dụng transactional outbox hoặc change-data-capture với monitoring và retry, thay vì lời gọi HTTP eviction không bền vững. Có thể dùng TTL như một lớp bảo vệ bổ sung, nhưng TTL cũng không bảo đảm update chính xác tại commit.

### 31.5. Khi cache lớn

Nếu mỗi ngày có một triệu events, không nên gọi `evictAll()` cho từng event. Cần kết hợp invalidation theo ID và cơ chế batch/coalesce phù hợp.

### 31.6. Hậu điều kiện cần quan sát

- Số sự kiện invalidation nhận/xử lý.
- Lag từ commit tới cache eviction.
- Tỷ lệ L2 cache hit/miss.
- Query cache hit/miss nếu bật.
- Lượt đọc phát hiện stale version.
- Tải database sau batch eviction.
- Chênh lệch kết quả giữa các instances.
- Số lần invalidation lỗi hoặc bị retry.

Việc quan sát như vậy giúp xác định **khả năng giữ nhất quán theo mức sản phẩm yêu cầu**, thay vì chỉ khẳng định một lần gọi API đã “làm mới toàn bộ dữ liệu”.

## 32. Ghi nhớ cuối bài

API chuẩn để thao tác cache cấp hai của JPA được truy cập qua:

```java
Cache cache = entityManagerFactory.getCache();
```

Ba mức xóa chính:

```java
// Một entity cụ thể:
cache.evict(Product.class, 101L);

// Mọi entity đã cache thuộc một type:
cache.evict(Product.class);

// Tất cả cached entity data của factory:
cache.evictAll();
```

Và phương thức kiểm tra:

```java
boolean present =
    cache.contains(Product.class, 101L);
```

Những điều cần hiểu sâu hơn cú pháp:

1. **`Cache` chủ yếu tác động tới shared/L2 entity cache của EntityManagerFactory**; không xóa persistence context L1 của các EntityManagers đang mở.
2. **`evict` không sửa database, không commit transaction và không đồng nghĩa `refresh` hoặc `clear`.**
3. **Chọn phạm vi hẹp nhất đủ đúng**: theo ID trước, theo class khi cần, `evictAll` khi có chủ đích rõ.
4. **Cache.contains không chứng minh freshness**, và kiểm tra trước eviction không tạo atomicity.
5. **Không cần manual eviction sau mọi managed JPA write** nếu provider đang quản lý cache consistency đúng; đặc biệt chú ý bulk/native SQL và external writers.
6. **Transaction timing quan trọng**: evict trước commit có thể cho phép nạp lại dữ liệu cũ; evict sau commit không tự tạo tính nguyên tử phân tán.
7. **Query cache, collection cache, Spring/Redis cache và cache của app nodes khác** có thể cần những cơ chế invalidation riêng.
8. **Entity graph, composite keys, tenancy và provider configuration** quyết định phạm vi dữ liệu thực sự liên quan.
9. **Đo và kiểm thử với EntityManagers độc lập, DBMS/provider/cache thật**; không suy hiệu quả L2 eviction chỉ từ một lời gọi `find()` trong cùng persistence context.

Kết luận: **xóa cache đúng nghĩa là xóa đúng bản dữ liệu ở đúng tầng, đúng thời điểm và đúng phạm vi**. `EntityManagerFactory.getCache()` cung cấp công cụ chuẩn cho invalidation entity cache cấp hai; để ứng dụng thực sự không trả dữ liệu lỗi thời, vẫn phải thiết kế nhất quán giữa transactions, L1, L2, provider-specific caches, những hệ thống ghi ngoài JPA và các ứng dụng chạy song song.
