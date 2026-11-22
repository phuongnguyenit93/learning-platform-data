# Chọn chế độ cache bằng CacheRetrieveMode và CacheStoreMode trong JPA

Trong một ứng dụng dùng **Jakarta Persistence (JPA)**, hai lần truy cập cùng một entity không nhất thiết dẫn tới hai câu SQL giống nhau. Entity có thể đã nằm trong **persistence context (first-level cache)** của `EntityManager` hiện tại, hoặc một bản sao của state entity có thể được lưu trong **shared cache (second-level cache)** dùng chung giữa nhiều persistence contexts. Cơ chế này giúp giảm số lần đọc cơ sở dữ liệu, nhưng cần được quản lý cẩn thận khi dữ liệu được cập nhật bởi nhiều giao dịch, nhiều node ứng dụng hoặc hệ thống bên ngoài JPA.

JPA định nghĩa hai enum tiêu chuẩn để điều khiển cách một thao tác đọc tương tác với **shared entity cache**:

~~~java
import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.CacheStoreMode;

CacheRetrieveMode.USE;
CacheRetrieveMode.BYPASS;

CacheStoreMode.USE;
CacheStoreMode.BYPASS;
CacheStoreMode.REFRESH;
~~~

Hai hướng điều khiển độc lập:

- **`CacheRetrieveMode`:** có **đọc state entity từ shared cache** khi cần tìm entity không?
- **`CacheStoreMode`:** có **đưa state entity đọc được vào shared cache**, bỏ qua việc lưu, hay **buộc làm mới cache từ database** không?

Ví dụ:

~~~java
Product product = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS,
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.REFRESH
    )
);
~~~

Ví dụ này minh họa việc muốn nạp state từ database và làm mới shared cache của Product. Tuy nhiên, còn một giới hạn quan trọng: **nếu Product đã được quản lý trong chính persistence context của `em`, JPA có thể dùng managed instance hiện có thay vì tạo một lần đọc DB mới.** Các cache mode trên không phải lệnh xóa first-level cache hoặc “luôn SELECT lại bất chấp mọi trạng thái”.

Bài học tập trung vào cách chọn đúng từng mode, thiết lập chúng cho `find()` và query, phối hợp `@Cacheable`, shared-cache-mode, `refresh()`/`evict()`, transaction và phiên bản entity, tránh nhầm lẫn giữa cache hit và dữ liệu mới nhất, và kiểm thử trên provider thực.

## 1. Vì sao phải chọn chế độ cache?

Giả sử bảng `products`:

~~~text
id | sku        | name          | price  | version
10 | JAVA-BOOK  | Java Handbook | 100000 | 7
~~~

Một service thường đọc thông tin Product để hiển thị danh mục. Nếu hàng nghìn requests cùng đọc cùng một Product ít thay đổi, shared cache có thể giúp giảm truy vấn:

~~~text
Request A / EntityManager A  ──┐
                              ├── Shared Entity Cache
Request B / EntityManager B  ──┤        Product#10
                              │
Request C / EntityManager C  ──┘
                              |
                              v
                          Database
~~~

Nhưng khi nhân viên quản trị vừa cập nhật giá bằng SQL ngoài ứng dụng:

~~~text
Database: Product#10.price = 120000
Shared cache: Product#10.price = 100000
~~~

một request mới có thể nhận state cũ nếu cache không được invalidated/updated theo đúng giao thức.

Ứng dụng cần chọn:

- Với màn hình danh mục cho phép dữ liệu có độ trễ nhỏ: **ưu tiên cache để giảm tải**.
- Với một thao tác cần đọc state mới hơn do thay đổi ngoài JPA: **bỏ qua lượt đọc shared cache**, có thể làm mới cached state.
- Với một tác vụ đọc không muốn làm nóng shared cache bằng hàng loạt entities ít được truy cập lại: **bỏ qua ghi state mới vào cache**.
- Với dữ liệu cực kỳ nhạy cảm về nhất quán: không chỉ chọn hint, mà còn cần transaction, validation, locking và database constraints.

**Cache mode là công cụ điều khiển hiệu năng/độ mới của quá trình load entity, không phải cơ chế thay thế transaction isolation.**

## 2. Phân biệt ba lớp “cache” thường bị trộn lẫn

Sơ đồ khái quát:

~~~text
Ứng dụng gọi em.find(Product.class, 10L)
              |
              v
    ┌───────────────────────┐
    │ Persistence context   │
    │ First-level cache     │
    │ (mỗi EntityManager)   │
    └───────────────────────┘
              |
              | chưa có managed Product#10
              v
    ┌───────────────────────┐
    │ Shared entity cache   │
    │ Second-level cache    │
    │ (tùy cấu hình)        │
    └───────────────────────┘
              |
              | miss/bypass/refresh
              v
    ┌───────────────────────┐
    │ Database / JDBC       │
    │ Rows, isolation, MVCC │
    └───────────────────────┘
~~~

### First-level cache: persistence context

Trong một persistence context:

~~~java
Product first = em.find(Product.class, 10L);
Product second = em.find(Product.class, 10L);

System.out.println(first == second); // true
~~~

JPA quản lý **một instance** theo entity identity trong context. Điều này phục vụ identity map, dirty checking và transaction semantics. Nó **không phải shared cache** mà `CacheRetrieveMode`/`CacheStoreMode` chủ yếu điều khiển.

### Second-level cache: shared entity cache

Nếu provider bật cơ chế shared cache và Product đủ điều kiện được cache, state của Product có thể được giữ lại để EntityManager khác dùng:

~~~text
EntityManager A tải Product#10 -> L2 có thể được điền.
EntityManager A đóng.
EntityManager B mới tìm Product#10 -> L2 có thể được dùng.
~~~

Không phải mọi provider/ứng dụng mặc định bật L2 cache theo cùng cách. Shared cache cần được hỗ trợ, cấu hình và kiểm chứng.

### Query cache: không phải API cache chuẩn của hai enum

Một số provider, ví dụ Hibernate, có **query result cache**: lưu danh sách IDs hoặc kết quả truy vấn theo query/parameters. JPA chuẩn không định nghĩa một API portable thống nhất để bật mọi loại query-result cache.

**Đừng nhầm cache state entity với cache kết quả JPQL.** Hai enum ở bài này diễn đạt shared entity state cache; một provider-specific query cache có thể có cấu hình riêng.

## 3. Hai chiều điều khiển: retrieve và store

Hãy hình dung một lần cần load Product#10:

~~~text
                      CẦN LOAD ENTITY
                            |
                            v
                 CacheRetrieveMode ?
                      /         \
                   USE         BYPASS
                    |             |
              Có thể tra L2     Không dùng L2
                    |         làm nguồn state
                    +------┬------+
                           |
                           v
                 Product state được lấy
                           |
                           v
                   CacheStoreMode ?
                 /         |         \
               USE       BYPASS      REFRESH
                |          |            |
          Cho phép store   Không       Buộc refresh
          state phù hợp    store       từ DB và cập
                           state       nhật cache theo
                                       ngữ nghĩa mode
~~~

Sơ đồ là **mô hình giải thích**, không phải thứ tự SQL/call stack bắt buộc của JPA provider. Đặc biệt, `CacheStoreMode.REFRESH` có semantics làm mới từ database và có thể làm cho lựa chọn retrieve không còn ý nghĩa thông thường.

### Câu hỏi chọn mode

| Câu hỏi của use case | Hướng lựa chọn |
| --- | --- |
| Có chấp nhận shared cache làm nguồn state không? | `CacheRetrieveMode.USE` hoặc `BYPASS` |
| Có muốn đưa state load được vào shared cache không? | `CacheStoreMode.USE` hoặc `BYPASS` |
| Có cần ép làm mới state cache từ database ở lần load không? | `CacheStoreMode.REFRESH` |

Hai chiều này chỉ hữu ích khi hiểu được **first-level cache ưu tiên managed identity** và shared cache có thật sự được bật cho loại entity đó.

## 4. CacheRetrieveMode.USE

~~~java
CacheRetrieveMode.USE
~~~

Ý nghĩa: **cho phép** provider dùng shared cache khi cần lấy state entity.

Ví dụ:

~~~java
Product p = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.USE
    )
);
~~~

Nếu Product chưa managed trong `em` nhưng state phù hợp đã có trong shared cache, provider **có thể** lấy nó từ cache thay vì SELECT lại database.

### USE không có nghĩa chắc chắn cache hit

L2 có thể:

- Chưa được cấu hình/bật.
- Không cache entity Product do `@Cacheable`/shared-cache-mode.
- Chưa có Product#10.
- Đã evict/expire Product#10.
- Bị invalidation vì cập nhật.
- Không thể phục vụ vì version/transaction strategy của provider.

Vì thế `USE` nghĩa **được phép sử dụng** cache, không phải “bắt buộc không có SQL”.

### Khi nào phù hợp?

Danh mục sản phẩm, thông tin tham khảo hoặc entity có tần suất đọc cao, cập nhật ít và cache consistency được cấu hình phù hợp.

## 5. CacheRetrieveMode.BYPASS

~~~java
CacheRetrieveMode.BYPASS
~~~

Ý nghĩa: **không dùng shared cache làm nguồn lấy state entity** cho operation được áp dụng.

Ví dụ:

~~~java
Product p = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
~~~

Nếu Product chưa managed trong context hiện tại, provider sẽ không dùng bản shared entity state đã cache làm nguồn load theo mode này.

### BYPASS không đồng nghĩa “luôn query database”

Đây là lỗi dễ mắc nhất.

~~~java
Product a = em.find(Product.class, 10L);

// Giả sử transaction khác cập nhật Product#10.

Product b = em.find(
    Product.class,
    10L,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
~~~

Nếu Product#10 **đã managed** trong `em`, `b` có thể chính là `a` và state vẫn cũ. Shared cache BYPASS **không xóa identity map first-level**.

Để kiểm soát việc đọc lại một managed entity, dùng `em.refresh(entity)` theo semantics phù hợp, hoặc kết thúc context hiện tại rồi tải ở context mới. Phần sau giải thích chi tiết.

### Khi nào phù hợp?

- Lượt load muốn không dựa trên một shared cache có khả năng stale.
- Một nghiệp vụ kiểm tra state sau khi hệ thống ngoài vừa update database.
- Chẩn đoán: so sánh hành vi khi lấy từ shared cache và khi bỏ qua shared cache.

**Không coi BYPASS là một lời hứa consistency tuyệt đối** trước replica lag, database isolation, concurrent commits hoặc first-level cached state.

## 6. CacheStoreMode.USE

~~~java
CacheStoreMode.USE
~~~

Ý nghĩa: cho phép đưa dữ liệu entity đọc từ database vào shared cache theo cơ chế provider, và quản lý cached state khi entity được cập nhật/commit theo các rules liên quan.

Ví dụ:

~~~java
Product product = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.USE
    )
);
~~~

### Tại sao có store mode riêng?

Một request có thể **không muốn đọc dữ liệu cũ từ cache**, nhưng sau khi đọc database lại **muốn đưa state mới vào cache** để các request tiếp theo được hưởng lợi:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS,
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.USE
);

Product product = em.find(
    Product.class,
    productId,
    hints
);
~~~

Về ý định, đây là **bỏ qua shared cache khi đọc, nhưng cho phép cập nhật/điền cache từ state mới load**. Nó hữu ích khi muốn làm nóng cache có kiểm soát nhưng không tin state cached cũ.

### USE không có nghĩa luôn cache mọi entity

Các điều kiện `@Cacheable`, shared-cache-mode, cache provider, eviction, capacity và transaction strategy vẫn có hiệu lực. Với entity không cacheable, lựa chọn USE không biến nó thành cacheable bất chấp cấu hình.

## 7. CacheStoreMode.BYPASS

~~~java
CacheStoreMode.BYPASS
~~~

Ý nghĩa: **không lưu state entity được load bằng operation đó vào shared cache** theo store-mode semantics.

~~~java
Product product = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.BYPASS
    )
);
~~~

### Khi nào dùng?

Ví dụ một tác vụ phân tích đọc 100.000 Product chỉ một lần. Nếu mọi entity đi vào một L2 cache có dung lượng hữu hạn, chúng có thể đẩy những entity “nóng” ra khỏi cache, làm giảm hiệu quả ở những request quan trọng.

Một query:

~~~java
List<Product> products = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.tenantId = :tenant " +
        "ORDER BY p.id",
        Product.class)
    .setParameter("tenant", tenantId)
    .setHint(
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.BYPASS)
    .setMaxResults(500)
    .getResultList();
~~~

Điều này bày tỏ ý định **không làm nóng L2 với state load được**. Nhưng `StoreMode.BYPASS` không tự biến query thành streaming, không giới hạn first-level cache, và không giảm số hàng nếu query thiếu phân trang.

### BYPASS không có nghĩa xóa entries cũ

Nếu shared cache đã có một Product#10, `CacheStoreMode.BYPASS` không phải lệnh `evict(Product.class, 10L)`. Nó nói về **việc store dữ liệu mới** theo operation, không phải API xóa state cache đang có.

Nếu cần loại bỏ entry cũ, dùng JPA `Cache.evict(...)` hoặc cơ chế provider cụ thể, đồng thời xử lý consistency của writers.

## 8. CacheStoreMode.REFRESH

~~~java
CacheStoreMode.REFRESH
~~~

Ý nghĩa: **buộc làm mới state entity dùng cho cache từ database** theo semantics của chế độ REFRESH, thay vì tin vào state cached hiện có khi thực hiện load phù hợp.

Ví dụ:

~~~java
Product product = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.REFRESH
    )
);
~~~

Một operation trên entity **chưa managed trong context** có thể dùng mode này để chủ động lấy state mới từ DB và cập nhật shared entity cache.

### REFRESH có ghi DB không?

`CacheStoreMode.REFRESH` được dùng cho hành vi **đọc/làm mới cache**, không phải một thao tác business UPDATE Product. Tất nhiên, provider có thể cần đồng bộ pending changes theo flush semantics của một query/operation, nhưng mode REFRESH tự nó không có nghĩa “ghi giá mới vào Product”.

### REFRESH không đồng nghĩa EntityManager.refresh()

Hai API này khác nhau:

~~~java
CacheStoreMode.REFRESH
~~~

là **chế độ cache cho operation**.

~~~java
em.refresh(managedProduct);
~~~

là **một thao tác trực tiếp yêu cầu nạp lại state của managed entity từ database** theo JPA semantics.

Khi entity đã managed, mode REFRESH không phải công cụ portable để thay thế hoàn toàn `em.refresh(entity)`. Phân biệt rõ first-level và shared cache sẽ giúp tránh tự tin sai rằng mode REFRESH đã đổi state trong object Java hiện có.

## 9. Bảng tổng hợp các enum

| Enum | Giá trị | Hành vi hướng đến | Không bảo đảm |
| --- | --- | --- | --- |
| `CacheRetrieveMode` | `USE` | Có thể đọc entity state từ shared cache | Chắc chắn cache hit |
| `CacheRetrieveMode` | `BYPASS` | Không dùng shared cache để lấy state | Bỏ qua managed entity trong L1 |
| `CacheStoreMode` | `USE` | Có thể đưa state phù hợp vào shared cache | Mọi entity luôn có entry |
| `CacheStoreMode` | `BYPASS` | Không store state load được vào shared cache | Tự xóa các entry đã cache |
| `CacheStoreMode` | `REFRESH` | Yêu cầu refresh state cache từ DB | Đảm bảo object managed cũ tự được refresh theo mọi tình huống |

### Nguyên tắc

Khi phân tích một lời gọi JPA, hãy hỏi theo thứ tự:

1. Entity đã **managed trong persistence context hiện tại** chưa?
2. Shared cache có được bật/áp dụng cho loại entity này không?
3. Operation có retrieve mode gì?
4. Operation có store mode gì?
5. Database/transaction đang có snapshot hoặc version nào?

Không đánh giá chỉ bằng tên `BYPASS` hoặc `REFRESH`.

## 10. Các tổ hợp retrieve/store phổ biến

| Retrieve | Store | Mục đích thường gặp |
| --- | --- | --- |
| `USE` | `USE` | Chế độ cho phép sử dụng và bổ sung shared cache bình thường |
| `BYPASS` | `USE` | Không lấy từ L2; cho phép store state vừa load từ DB |
| `USE` | `BYPASS` | Có thể dùng L2 sẵn có nhưng hạn chế store state mới |
| `BYPASS` | `BYPASS` | Bỏ qua cả đọc và ghi shared cache cho load phù hợp |
| `USE` | `REFRESH` | Làm mới cached state từ DB; retrieve USE không phải là lời hứa sẽ dùng cached state cũ |
| `BYPASS` | `REFRESH` | Thể hiện rõ chủ đích load từ DB và refresh shared cache; BYPASS có thể dư về mặt lựa chọn nguồn |

### Vì sao hai mode không phải mọi tổ hợp đều độc lập hoàn toàn?

Khi store mode là `REFRESH`, mục tiêu của operation là **làm mới state từ DB**, không đơn thuần tra một entry cũ. Bởi vậy không nên diễn giải `USE + REFRESH` là “cứ dùng state cũ nếu cache có, rồi gọi đó là refresh”.

### Không có tổ hợp nào là “strong consistency mode”

Ngay cả `BYPASS + REFRESH` cũng không tự:

- Tạo snapshot mới nếu entity đã managed trong context cũ.
- Bỏ qua database isolation/MVCC.
- Đọc primary thay vì replica nếu hạ tầng định tuyến sai.
- Khóa row khỏi concurrent update.
- Đồng bộ tất cả các cache ứng dụng/HTTP/CDN khác.

Cache modes là một phần trong thiết kế nhất quán, không phải một transaction protocol toàn diện.

## 11. Default modes và cấu hình

Với shared cache được sử dụng theo cách thông thường, các chế độ phổ biến mặc định là:

~~~java
CacheRetrieveMode.USE
CacheStoreMode.USE
~~~

Nhưng giá trị **hiệu lực** trên một operation còn chịu:

- Cấu hình persistence unit/provider.
- Properties ở EntityManager.
- Map hints của `find()`/`refresh()`.
- Query hints được chỉ định tường minh.
- Sự tồn tại và policy của shared cache.
- Entity có cacheable không.

### Cấu hình mặc định không nghĩa cache thực sự bật

Nếu persistence unit đặt shared cache mode là NONE hoặc provider chưa cấu hình second-level cache, dù property báo USE, việc nạp entity vẫn có thể phải đọc database.

**USE là một quyền lựa chọn, không phải lệnh buộc provider tạo cache.**

## 12. @Cacheable và shared-cache-mode quyết định entity có thể được cache

Ví dụ:

~~~java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
@Cacheable(true)
public class Product {
    @Id
    private Long id;
    // ...
}
~~~

`@Cacheable` chỉ định điều kiện về việc entity state được tham gia shared cache trong các shared-cache modes liên quan.

### Các chế độ SharedCacheMode

| Chế độ | Chính sách khái quát |
| --- | --- |
| `ALL` | Cho phép cache tất cả entities thuộc persistence unit |
| `NONE` | Không dùng shared entity cache |
| `ENABLE_SELECTIVE` | Chỉ cache entities được đánh dấu `@Cacheable(true)` |
| `DISABLE_SELECTIVE` | Cache entities trừ những loại đánh dấu `@Cacheable(false)` |
| `UNSPECIFIED` | Nhà cung cấp persistence quyết định hành vi mặc định |

### XML cấu hình ví dụ

~~~xml
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">
  <persistence-unit name="shopPU"
                    transaction-type="RESOURCE_LOCAL">
    <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
    <shared-cache-mode>ENABLE_SELECTIVE</shared-cache-mode>
    <properties>
      <!-- Cấu hình L2 cache provider/region factory riêng
           còn phụ thuộc Hibernate version và cache provider. -->
    </properties>
  </persistence-unit>
</persistence>
~~~

Đây là đoạn cấu hình minh họa, **không phải bộ `persistence.xml` hoàn chỉnh chạy sẵn ở mọi môi trường**. Với Hibernate cần cấu hình cache region factory, cache provider và dependencies phù hợp phiên bản nếu muốn L2 thực sự hoạt động.

### Hiểu đúng thứ tự quyết định

~~~text
Persistence unit shared-cache-mode
         |
         v
Entity có đủ điều kiện cache?  --- Không ---> không dùng L2 cho entity đó
         |
        Có
         |
         v
Provider/cache backend được bật và cấu hình?
         |
         v
Operation CacheRetrieveMode / CacheStoreMode
         |
         v
Lấy hoặc lưu entity state theo mode
~~~

Không dùng `CacheRetrieveMode.USE` để cố ép một entity `@Cacheable(false)` vào shared cache khi cấu hình không cho phép.

## 13. Mô hình entity Product xuyên suốt

Ví dụ một Product có giá và version:

~~~java
package com.example.shop.domain;

import jakarta.persistence.Cacheable;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
@Cacheable(true)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Version
    @Column(nullable = false)
    private Long version;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public Long getVersion() {
        return version;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Giá phải không âm");
        }
        price = newPrice;
    }
}
~~~

Ở đây:

- `@Entity` và `@Id` định danh persistent entity.
- `@Cacheable(true)` cho phép Product tham gia shared cache khi shared-cache-mode thích hợp.
- `@Version` phục vụ optimistic locking khi update theo đường ghi JPA managed entity.
- `tenantId` là phạm vi quyền truy cập dữ liệu, **không phải biến thể cache mode**.

### DDL tương ứng

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    sku VARCHAR(100) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_product_tenant_sku
        UNIQUE (tenant_id, sku),
    CONSTRAINT ck_product_price_nonnegative
        CHECK (price >= 0)
);
~~~

DDL có thể cần điều chỉnh cú pháp identity theo DBMS. Khi thiết kế multi-tenant, nên quyết định unique key và entity identity phù hợp; ở ví dụ này ID là khóa chính global, còn tenant scope được service kiểm tra riêng.

## 14. Entity không nên cache: ví dụ StockSnapshot

Tồn kho thường thay đổi nhanh. Một số nghiệp vụ không nên dựa vào L2 entity state như nguồn quyết định cuối cùng.

~~~java
@Entity
@Table(name = "inventory")
@Cacheable(false)
public class Inventory {

    @Id
    private Long productId;

    @Column(nullable = false)
    private long availableQuantity;

    @Version
    private Long version;

    protected Inventory() {
    }

    public long getAvailableQuantity() {
        return availableQuantity;
    }
}
~~~

Khai báo `@Cacheable(false)` có hiệu lực phụ thuộc `SharedCacheMode`; ví dụ ở chế độ DISABLE_SELECTIVE hoặc ENABLE_SELECTIVE, cách chọn entity không cache được thể hiện rõ.

### Vì sao không chỉ dùng BYPASS mỗi lần đọc Inventory?

Nếu **mọi** operation luôn bypass L2, thì cấu hình entity không tham gia shared cache có thể đơn giản hơn, giảm nguy cơ một đường code quên hint. Tuy nhiên:

- Bỏ L2 không tự xử lý lost update.
- Transaction isolation và first-level cache vẫn có tác động.
- Hai transaction vẫn có thể cùng đọc một số lượng tồn kho.
- Quyết định trừ kho cần atomic SQL/lock/version/constraint phù hợp.

**Dữ liệu thay đổi nhanh và có invariant nghiêm ngặt phải được bảo vệ ở database transaction**, không chỉ bằng việc tắt cache.

## 15. Các key chuẩn dùng trong Map hints

Jakarta Persistence dùng các property names:

~~~text
jakarta.persistence.cache.retrieveMode
jakarta.persistence.cache.storeMode
~~~

Gán giá trị enum:

~~~java
Map<String, Object> hints = new HashMap<>();
hints.put(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS);
hints.put(
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.USE);
~~~

### Tên key có phân biệt chữ hoa/thường không?

Có. Property name là literal string; dùng **đúng** tên được chuẩn định nghĩa. Các dạng như:

~~~text
jakarta.persistence.cache.retrievemode
jakarta.persistence.cache.storemode
jakarta.persistence.cache.retrieve_mode
~~~

không phải cùng tên chuẩn.

### javax.persistence cho dự án JPA cũ

Trong các dự án JPA 2.x dùng namespace Java EE cũ, key bắt đầu bằng:

~~~text
javax.persistence.cache.retrieveMode
javax.persistence.cache.storeMode
~~~

Với Jakarta Persistence 3.x, dùng `jakarta.persistence.*`. Không trộn hai namespace một cách tùy tiện; kiểm tra phiên bản API/provider đang chạy.

## 16. find() với retrieve USE và store USE

Đây là trường hợp ứng dụng **cho phép cache hoạt động bình thường**.

~~~java
import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.CacheStoreMode;
import jakarta.persistence.EntityManager;
import java.util.Map;

Product product = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.USE,
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.USE
    )
);
~~~

Khi Product chưa managed:

~~~text
L2 có Product#10?
   |
   +-- Có -> provider có thể lấy cached state
   |
   +-- Không -> database SELECT
               -> state có thể được đưa vào L2
~~~

### Trường hợp phù hợp

- Product catalog được truy cập thường xuyên.
- Dữ liệu ổn định hoặc update chủ yếu qua cùng JPA provider/cache protocol.
- Cache eviction/expiration và cache topology được giám sát.
- Có thể chấp nhận consistency guarantees mà hệ thống hiện tại cung cấp.

Không mặc định mọi Product SELECT sẽ biến mất; JPQL listing, filter/search và association loading vẫn có chi phí riêng.

## 17. find() với retrieve BYPASS, store USE

~~~java
Product product = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS,
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.USE
    )
);
~~~

Ý định:

1. Không dùng state shared cache cũ làm nguồn khi load.
2. Lấy Product từ database nếu không có managed instance.
3. Cho phép lưu state load được vào shared cache.

### Một use case

Sau một sự kiện quản trị hoặc batch ngoài JPA cập nhật dữ liệu tham khảo, một service muốn đọc state mới hơn từ DB rồi để cache được điền lại.

### Giới hạn

- Nếu Product đã managed trong cùng `em`, mode không bảo đảm đọc mới.
- Nếu database read đi tới replica chậm, state được nạp vẫn có thể cũ so với primary.
- Nếu concurrent writer commit ngay sau SELECT, cache vừa điền lại đã có thể không phải dữ liệu mới nhất tuyệt đối; cần protocol invalidation/versioning phù hợp.

## 18. find() với retrieve USE, store BYPASS

~~~java
Product product = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.USE,
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.BYPASS
    )
);
~~~

Đây là lựa chọn ít được chú ý:

- Có thể dùng một cached entity state đã có.
- Nếu phải lấy từ DB, operation không yêu cầu đưa state ấy vào L2.

### Khi nào dùng?

Một request đọc tham khảo một số Product rất ít được dùng lại, nhưng không có lý do phải cấm dùng cache nếu có entry sẵn. Ứng dụng muốn tránh L2 cache pollution.

### Không dùng khi cần loại bỏ dữ liệu stale

Vì retrieve vẫn USE, nếu L2 có Product stale, operation vẫn có thể đọc cached state đó. Store BYPASS không bảo đảm freshness.

## 19. find() với retrieve BYPASS, store BYPASS

~~~java
Product product = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS,
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.BYPASS
    )
);
~~~

Ý định là **bỏ qua shared cache cho cả retrieve và store** của load này.

### Dùng cho dữ liệu không muốn làm nóng cache

Ví dụ một job đối soát cần đọc Product nhưng không muốn giữ state của nhiều items hiếm gặp trong L2.

### Có tương đương cache NONE không?

Không hoàn toàn:

- Hai mode ở đây áp dụng cho operation đã chọn.
- `SharedCacheMode.NONE` là chính sách rộng hơn của persistence unit.
- `@Cacheable(false)` là lựa chọn entity-level theo shared-cache mode.
- First-level cache trong EntityManager vẫn hoạt động.
- Những operations khác vẫn có thể sử dụng/cache Product.

### Nếu cả USE và BYPASS đều vẫn phát SELECT thì sao?

Có thể do L2 chưa bật, entry cache miss, Product không cacheable hoặc query trả DTO/scalar không dùng shared entity state. Chỉ nhìn SQL không đủ để suy ra hint bị bỏ qua; xem cache statistics và cấu hình.

## 20. find() với CacheStoreMode.REFRESH

~~~java
Product product = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.REFRESH
    )
);
~~~

Mục đích: làm mới cached Product state từ DB khi operation thực hiện một load phù hợp.

### Ví dụ trước và sau

~~~text
L2 cached Product#10:
  price = 100000, version=7

Database Product#10:
  price = 120000, version=8

Find ở context mới với storeMode=REFRESH:
  - yêu cầu state được lấy lại từ database;
  - cập nhật shared cache theo mode nếu entity/cache áp dụng.
~~~

### REFRESH có thay thế việc evictAll không?

Không. REFRESH nhắm vào **entity state liên quan operation**, không có nghĩa “xóa hoặc làm mới mọi entry toàn persistence unit”.

### REFRESH có bảo đảm tất cả associations được fresh?

Không mặc định. EAGER/LAZY fetch plan, collection state, entities trong relationship, first-level managed objects và khả năng provider cache các association đều có semantics riêng. Nếu cần refresh một object graph cụ thể, phải xác định rõ những entity/association cần xử lý và đo provider behavior.

## 21. Case study: cách dùng mode khi Product đã managed

Đây là một thí nghiệm tư duy rất quan trọng.

~~~java
EntityManager em = emf.createEntityManager();

Product first = em.find(Product.class, productId);
BigDecimal priceBefore = first.getPrice();

// Giả sử một transaction khác đã cập nhật giá trong DB.

Product again = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS,
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.REFRESH
    )
);
~~~

Trong một context, JPA identity map thường giữ:

~~~java
first == again // true khi cùng managed identity
~~~

Do đó không được khẳng định:

~~~text
again.getPrice() chắc chắn là giá vừa cập nhật.
~~~

### Hướng đọc lại state của managed entity

Nếu muốn **explicitly reload state vào managed entity**, dùng:

~~~java
em.refresh(first);
~~~

trong một lifecycle/transaction hợp lệ, chú ý rằng refresh có thể **ghi đè pending changes trên first** và chịu database isolation.

Nếu muốn không tái sử dụng first-level context:

~~~java
em.close();

EntityManager freshEm =
    emf.createEntityManager();
try {
    Product fresh = freshEm.find(
        Product.class,
        productId,
        Map.of(
            "jakarta.persistence.cache.retrieveMode",
            CacheRetrieveMode.BYPASS,
            "jakarta.persistence.cache.storeMode",
            CacheStoreMode.REFRESH
        )
    );
} finally {
    freshEm.close();
}
~~~

Trong thực tế phải áp transaction boundaries phù hợp với `RESOURCE_LOCAL`/JTA và data access requirements; ví dụ mới chỉ thể hiện ý định tách persistence contexts.

## 22. em.refresh() làm gì khác với CacheStoreMode.REFRESH?

### EntityManager.refresh(entity)

~~~java
Product p = em.find(Product.class, productId);
em.refresh(p);
~~~

`refresh()` yêu cầu cập nhật lại **persistent state của managed instance** từ database theo quy tắc JPA. Nó có thể hữu ích khi JPA entity state trong RAM đã stale.

### CacheStoreMode.REFRESH

~~~java
Map.of(
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.REFRESH
)
~~~

Đây là một hint điều khiển **cách operation tương tác với shared cache**. Nó không phải một lời gọi trực tiếp vào một managed instance nhất định như `em.refresh(p)`.

### Có thể kết hợp

JPA có các overload `refresh()` nhận Map properties/hints trong API phù hợp, ví dụ:

~~~java
em.refresh(
    p,
    Map.of(
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.REFRESH
    )
);
~~~

Điều này minh họa một **explicit refresh** trên managed entity cùng một định hướng store mode cho shared cache. Provider/DBMS quyết định SQL và cache coordination chi tiết.

### Cảnh báo quan trọng

Nếu `p` đã được thay đổi trong Java nhưng chưa flush:

~~~java
p.changePrice(new BigDecimal("150000.00"));
em.refresh(p);
~~~

thao tác refresh có thể **mất pending change** và thay bằng state DB. Không dùng refresh như một thao tác “đọc thêm” an toàn vô điều kiện.

## 23. em.clear() có giải quyết shared cache không?

~~~java
em.clear();
~~~

`clear()` làm rỗng **first-level persistence context** bằng cách detach các managed entities. Nó **không phải lệnh evict toàn shared cache**.

Ví dụ:

~~~text
L1: Product#10 price=100000
L2: Product#10 price=100000
DB: Product#10 price=120000
~~~

Sau:

~~~java
em.clear();
~~~

có thể:

~~~text
L1: không còn managed Product#10
L2: vẫn có Product#10 price=100000
DB: price=120000
~~~

Nếu `em.find(Product.class, 10L)` dùng `CacheRetrieveMode.USE`, state từ L2 vẫn có thể được dùng.

### Cách kết hợp

~~~java
em.clear();

Product fresh = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
~~~

Điều này diễn đạt rõ việc bỏ qua L1 **bằng clear** và bỏ qua L2 **bằng retrieve BYPASS**.

**Nhưng:** `clear()` detach toàn bộ managed entities và có thể làm mất pending changes chưa flush. Nó không phải lựa chọn phù hợp trong mọi transaction đang sửa nhiều entities. Có thể chọn context mới thay vì clear context làm việc hiện tại.

## 24. JPA Cache API: kiểm tra và evict shared cache

JPA chuẩn có:

~~~java
import jakarta.persistence.Cache;

Cache cache = emf.getCache();
~~~

Một số thao tác:

~~~java
boolean present =
    cache.contains(Product.class, productId);

cache.evict(Product.class, productId);

cache.evict(Product.class);

cache.evictAll();
~~~

### Ý nghĩa

| API | Mục đích |
| --- | --- |
| `contains(Product.class,id)` | Kiểm tra entity có mặt trong shared cache theo contract |
| `evict(Product.class,id)` | Yêu cầu loại entry của entity identity cụ thể |
| `evict(Product.class)` | Yêu cầu loại cached state của entity class |
| `evictAll()` | Yêu cầu loại toàn bộ shared entity cache |

### Tại sao evict không giống BYPASS?

- BYPASS quyết định một **operation** có đọc/ghi shared cache theo mode hay không.
- Evict chủ động **loại bỏ cached state hiện có**.

Sau `cache.evict(Product.class,id)`, những EntityManager **đang giữ managed Product#10** vẫn có thể tiếp tục dùng state cũ từ first-level cache. Evict L2 **không đồng bộ ngược mọi object Java đang tồn tại**.

### Có nên gọi evictAll() cho mọi cập nhật?

Không. Đây là thao tác rộng, có thể làm cache hit rate tụt mạnh và khiến nhiều queries đồng loạt quay lại DB. Nếu cần invalidation do một Product bị cập nhật ngoài JPA, evict **đúng entity identity** hoặc thiết kế invalidation protocol theo sự kiện.

## 25. Hai lớp cache trong một ví dụ cụ thể

Ban đầu:

~~~text
DB Product#10: price=100000, version=7
L2: chưa có
L1-A: chưa có
L1-B: chưa có
~~~

### Bước 1: EntityManager A load mặc định

~~~java
Product a = emA.find(Product.class, 10L);
~~~

Một provider có L2 bật có thể:

~~~text
DB SELECT -> price 100000
L1-A -> Product#10 100000
L2 -> Product#10 100000 (nếu store allowed)
~~~

### Bước 2: EntityManager B load từ L2

~~~java
Product b = emB.find(Product.class, 10L);
~~~

Có thể:

~~~text
L2 HIT -> price 100000
L1-B -> Product#10 100000
Không cần SQL SELECT entity này
~~~

### Bước 3: Một job JDBC cập nhật DB ngoài cache protocol

~~~sql
UPDATE products
SET price=120000, version=8
WHERE id=10;
~~~

L2 có thể vẫn chứa giá cũ nếu external writer không invalidates cache.

### Bước 4: B gọi find BYPASS trong cùng emB

~~~java
Product bAgain = emB.find(
    Product.class,
    10L,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
~~~

Không được hứa sẽ ra 120000, vì **L1-B vẫn đang có Product#10**.

### Bước 5: New EntityManager C + BYPASS

~~~java
Product c = emC.find(
    Product.class,
    10L,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS,
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.REFRESH
    )
);
~~~

Nếu DB read nhất quán với update ở bước 3 và không có snapshot cũ/replica lag, C có thể thấy price=120000 và shared cache được refresh theo mode.

**Kết luận:** Điều quan trọng không chỉ là chọn hai enum, mà còn là **context nào đang đọc, transaction nào đã commit và đường ghi nào đã tham gia cache invalidation protocol**.

## 26. Setting hint trên JPQL TypedQuery

Một cách phổ biến:

~~~java
import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.CacheStoreMode;
import jakarta.persistence.TypedQuery;

TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p " +
    "WHERE p.tenantId = :tenant " +
    "ORDER BY p.id",
    Product.class
);

List<Product> products = query
    .setParameter("tenant", tenantId)
    .setHint(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS)
    .setHint(
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.BYPASS)
    .setMaxResults(100)
    .getResultList();
~~~

### Hint tác động lên điều gì?

Nó biểu diễn chính sách shared entity cache áp dụng cho entity state được load trong query theo contract/provider.

**Nó không tự biến JPQL query thành “không dùng query-result cache của mọi provider”**. Nếu Hibernate query cache được bật cho một query bằng extension vendor-specific, phải xem thêm cách cấu hình bypass/refresh query result cache của chính Hibernate.

### Không nhất thiết giảm số câu SELECT

Nhiều JPQL queries phải chạy SQL để xác định **những entity IDs nào thỏa WHERE/ORDER BY**, ngay cả khi entity state của từng ID có mặt trong L2. Không có bảo đảm “Query trả 100 Product ở L2 thì chỉ gọi getResultList là không có SELECT”.

## 27. Query trả DTO không có managed entity

DTO:

~~~java
package com.example.shop.dto;

import java.math.BigDecimal;

public record ProductRow(
    Long id,
    String sku,
    String name,
    BigDecimal price) {
}
~~~

JPQL:

~~~java
List<ProductRow> rows = em.createQuery(
        "SELECT NEW com.example.shop.dto.ProductRow(" +
        "p.id, p.sku, p.name, p.price) " +
        "FROM Product p " +
        "WHERE p.tenantId = :tenant " +
        "ORDER BY p.id",
        ProductRow.class)
    .setParameter("tenant", tenantId)
    .setHint(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS)
    .setMaxResults(50)
    .getResultList();
~~~

### Có được kết luận DTO bypass DB vì L2 cache hit không?

Không. Query projection trả scalar fields/constructor DTO, không phải load một managed Product entity state theo kiểu `em.find`. Database thường phải thực hiện JPQL query và trả các cột được chọn.

### Hai enum có còn hữu ích không?

Chúng có ý nghĩa trong phạm vi cache entity mà query/provider có thể sử dụng; nhưng đối với **pure scalar/DTO projection**, đừng mong hai hint điều khiển một thứ tương đương với cache DTO kết quả. Nếu cần query-result caching, đó là một thiết kế/cơ chế khác.

### API danh sách

Một endpoint chỉ đọc id/sku/name/price thường nên dùng DTO projection để giảm tải persistent entity state và serialization graph, thay vì kỳ vọng L2 cache xử lý mọi bài toán hiệu năng.

## 28. Query result cache của Hibernate khác gì?

Ở Hibernate, những khái niệm dễ gặp:

~~~text
Persistence context / first-level cache
Second-level entity cache
Second-level collection cache (provider-specific)
Query result cache (provider-specific)
~~~

Ví dụ một Hibernate query-result cache có thể lưu danh sách IDs hoặc các giá trị liên quan query, nhưng invalidation của nó cần được điều phối với entity/table changes.

### Không nhầm API

- `CacheRetrieveMode`/`CacheStoreMode` thuộc JPA/Jakarta Persistence.
- Các Hibernate cache hints, `CacheMode`, query cache regions, `@org.hibernate.annotations.Cache` và cache concurrency strategies là **provider-specific**.

Một số dự án còn dùng Spring Cache `@Cacheable`:

~~~java
@org.springframework.cache.annotation.Cacheable("products")
public ProductDto getProduct(long id) { ... }
~~~

Nó không phải `jakarta.persistence.Cacheable`. Một cái cache kết quả lời gọi method theo Spring Cache; cái còn lại điều chỉnh khả năng một JPA entity tham gia shared persistence cache.

### Ba loại “Cacheable”

| Annotation | Thuộc về | Cache gì? |
| --- | --- | --- |
| `jakarta.persistence.Cacheable` | JPA | Entity state trong shared persistence cache theo mode |
| `org.hibernate.annotations.Cache` | Hibernate | Region/concurrency strategy cache entity/collection tùy provider |
| `org.springframework.cache.annotation.Cacheable` | Spring Cache | Kết quả method theo key/TTL/cache manager |

**Không dùng các annotations như thể chúng thay thế lẫn nhau.**

## 29. Hibernate-specific cache modes không giống enum JPA

Một số tutorial dùng:

~~~java
org.hibernate.CacheMode.NORMAL
org.hibernate.CacheMode.GET
org.hibernate.CacheMode.PUT
org.hibernate.CacheMode.REFRESH
org.hibernate.CacheMode.IGNORE
~~~

Đây là **API Hibernate**, không phải `jakarta.persistence.CacheRetrieveMode` hoặc `CacheStoreMode`.

Hibernate có thể map các lựa chọn retrieve/store của JPA sang cache mode nội bộ tương ứng, nhưng chi tiết triển khai/giá trị phụ thuộc phiên bản.

### Khi nào nên dùng JPA enums?

Nếu ứng dụng muốn giữ tính portable giữa providers và chỉ cần các chiến lược cơ bản USE/BYPASS/REFRESH, dùng JPA enum và chuẩn hints.

### Khi nào cần Hibernate API?

Khi use case cần những tính năng provider-specific như cache regions, query cache strategies hoặc statistics mà JPA không chuẩn hóa. Cần ghi rõ code phụ thuộc Hibernate.

## 30. Query hint có thể bị bỏ qua trong những tình huống nào?

JPA providers có thể không hỗ trợ tất cả **vendor-specific hints** và có khác biệt trong việc thực hiện một số hành vi/cache backend. Một số hints không được hỗ trợ có thể bị bỏ qua thay vì làm query lỗi ngay.

Với **tên chuẩn** `jakarta.persistence.cache.retrieveMode` và `jakarta.persistence.cache.storeMode`, ý nghĩa được đặc tả; nhưng thực tế chỉ quan sát được hiệu ứng nếu entity/shared cache phù hợp và operation đi qua đường cache đó.

### Những nguyên nhân thường gặp

1. Persistence unit không bật shared cache.
2. Entity không cacheable.
3. Entity đã managed trong L1.
4. Query trả scalar/DTO, không phải entity state từ L2.
5. Một association/fetch plan khác phát SQL.
6. Cache entry đã bị evicted hoặc chưa warm up.
7. Provider-specific cache configuration chưa hoàn chỉnh.
8. L2 cluster invalidation/provider semantics thay đổi hành vi quan sát được.

### Cách chẩn đoán

Đừng chỉ nói “hint không có tác dụng” vì vẫn thấy một SELECT. Hãy quan sát **SQL + cache hit/miss/put metrics + context lifetime + entity cache eligibility**.

## 31. Các mode ở EntityManager scope và per-operation

JPA có cơ chế properties/hints gắn với operation như `find` và `Query.setHint`. Một số properties có thể được thiết lập ở EntityManager factory/EntityManager level theo contract và mức hỗ trợ provider.

Ví dụ dùng:

~~~java
em.setProperty(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);
~~~

Đây là cách đặt property cho EntityManager trong phạm vi provider/JPA-supported operation; nhưng không nên giả định nó ảnh hưởng ngay tới mọi cached object hiện có.

### Ưu tiên override cụ thể

Nếu một service chỉ có **một query** cần BYPASS:

~~~java
query.setHint(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);
~~~

thường rõ mục đích hơn việc thay đổi property global làm ảnh hưởng các queries khác trong context.

### Không dùng một EntityManager dùng chung qua nhiều threads

EntityManager không phải resource thread-safe thông thường. Nếu thay cache properties qua nhiều requests trên cùng EntityManager, ngoài race còn có thể làm sai scope của operation.

Mỗi request/transaction cần persistence context theo lifecycle được framework quản lý.

## 32. Shared cache và @Version

Entity versioned:

~~~java
@Version
private Long version;
~~~

Version có thể giúp JPA provider kiểm tra các cập nhật cạnh tranh và phối hợp cache concurrency strategies, nhưng **không phải lời hứa mọi cached state luôn mới tuyệt đối**.

### Kịch bản JPA writer

~~~text
Product#10 ở DB và L2: price=100000, v=7
TX_A đọc và sửa Product qua JPA managed entity
TX_A commit: DB price=120000, v=8
Provider quản lý cache update/invalidate theo chiến lược đã cấu hình
~~~

Một L2 cache concurrency strategy phù hợp có thể giảm nguy cơ reader lấy cached state không hợp lệ khi transaction commit.

### Kịch bản external writer

~~~text
Job JDBC trực tiếp:
UPDATE products SET price=130000, version=9 WHERE id=10
COMMIT
~~~

JPA provider đang chạy ở process khác có thể **không nhận được thông báo invalidation** nếu không có cơ chế chia sẻ sự kiện/cache cluster.

### Kết luận

Version, cache invalidation và transaction isolation giải quyết những lớp khác nhau. Một Product có version=9 ở DB không tự khiến tất cả cache entries trên mọi node bị xóa nếu chúng không tham gia giao thức đồng bộ.

## 33. Shared cache và transaction isolation

Giả sử hai transaction:

~~~text
Transaction A:
  Lấy Product#10
  Có thể sử dụng L2

Transaction B:
  UPDATE Product#10
  COMMIT

Transaction A:
  Dùng Product#10 đã managed
~~~

Ngay cả nếu L2 được làm mới ngay sau B commit, **L1 của A có thể vẫn giữ managed Product cũ**. Cách transaction A được phép nhìn thay đổi từ B còn liên quan DB isolation và persistence context semantics.

### Cache BYPASS không nâng isolation

~~~java
CacheRetrieveMode.BYPASS
~~~

không tương đương:

~~~text
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

Và:

~~~java
CacheStoreMode.REFRESH
~~~

không tương đương:

~~~sql
SELECT ... FOR UPDATE;
~~~

### Dữ liệu tài chính hoặc tồn kho

Nếu quyết định nghiệp vụ yêu cầu bảo vệ invariant trong tình huống concurrent writers, hãy dùng transaction locking, conditional UPDATE, `@Version` hoặc database constraints phù hợp. Cache BYPASS chỉ giảm một nguồn stale data; nó không tự ngăn lost update.

## 34. Khi nào nên tránh cache dữ liệu nhạy cảm về nhất quán?

Một số dữ liệu như:

- Số lượng tồn kho có thể đặt ngay.
- Hạn mức thanh toán còn lại.
- Trạng thái chống trùng giao dịch.
- Phiên bản tài liệu quan trọng trong workflow phê duyệt.

thường phải được quyết định bằng transaction/read-write protocol đáng tin.

### Một ví dụ sai

~~~java
Inventory inv = em.find(
    Inventory.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);

if (inv.getAvailableQuantity() >= quantity) {
    // Sau read, transaction khác vẫn có thể thay đổi stock.
    createOrder();
}
~~~

Chỉ bypass L2 không khóa row hoặc bảo vệ invariant giữa check và update.

### Một phương án đáng cân nhắc

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - :q,
    version = version + 1
WHERE product_id = :productId
  AND available_quantity >= :q;
~~~

Kết hợp booking/order writes trong **cùng database transaction**. Nếu UPDATE ảnh hưởng 0 rows, xử lý hết hàng/conflict theo policy thay vì tạo order như thể còn hàng.

**Dùng mode cache đúng không thay thế thiết kế ghi an toàn.**

## 35. Đọc một Product trong một transaction có thay đổi chưa flush

Giả sử:

~~~java
Product p = em.find(Product.class, id);
p.changePrice(new BigDecimal("130000.00"));

Product again = em.find(
    Product.class,
    id,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
~~~

Trong context hiện tại, `again` là cùng managed instance. Nó có thể trả `130000` là **giá trong Java RAM chưa commit**, không phải giá vừa được SELECT database vì BYPASS.

### Không suy ra DB đã commit

Trước commit:

~~~text
Java managed Product.price = 130000
DB committed Product.price = 100000
~~~

Một BYPASS hint trên find không làm thay đổi cơ chế dirty checking và transaction. Để biết một write đã commit chưa, cần kết quả transaction boundary, không phải gọi find thêm.

### Nếu gọi refresh?

`em.refresh(p)` có thể ghi đè thay đổi `130000` trong RAM bằng state DB, vì vậy không dùng refresh để “xác minh commit” khi transaction đang dirty.

## 36. Refresh từ database có thể vẫn thấy dữ liệu cũ

Hãy xét:

~~~text
T1: Transaction A bắt đầu dưới isolation snapshot-like.
T2: Transaction A đọc Product#10 version=7.
T3: Transaction B cập nhật Product#10 version=8 và COMMIT.
T4: Transaction A yêu cầu refresh hoặc BYPASS.
~~~

Giá trị A nhận còn phụ thuộc:

- DBMS sử dụng snapshot nào cho SELECT tại T4.
- Isolation level và locking semantics.
- Entity đã managed hay được detach.
- Routing tới primary/replica.
- Cách provider xử lý refresh và cache.

Do đó **đọc lại từ database không có nghĩa thấy commit mới nhất ở mọi isolation**.

### Hướng thực hành khi cần state mới

Thường cần:

1. Kết thúc transaction/context cũ phù hợp.
2. Bắt đầu một transaction/read boundary mới với visibility phù hợp.
3. Bypass/refresh shared cache nếu có nguy cơ stale.
4. Đọc trên nguồn dữ liệu đáp ứng consistency policy.
5. Kiểm tra version hoặc business precondition trước khi ghi.

Đừng dùng cache hint như một cách lách semantics của isolation.

## 37. Cache không thay authorization và tenant isolation

Nếu hệ thống multi-tenant:

~~~text
Tenant A: Product#10
Tenant B: Product#10
~~~

thì mô hình entity identity và cách cache key được cấu hình phải đảm bảo không trộn state giữa tenants.

### Không tin rằng cache mode tự lọc tenant

~~~java
Product p = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
~~~

Không có đoạn nào trong CacheRetrieveMode định nghĩa:

~~~text
Chỉ trả Product thuộc currentTenant.
~~~

Authorization phải được enforce độc lập: truy vấn theo tenant/ACL, validate owner, Row Level Security nếu dùng và isolation của cache theo multi-tenant provider configuration.

### Một service đọc rõ tenant scope

~~~java
List<Product> found = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.id = :id AND p.tenantId = :tenant",
        Product.class)
    .setParameter("id", productId)
    .setParameter("tenant", tenantId)
    .setHint(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS)
    .setMaxResults(1)
    .getResultList();
~~~

Query này kiểm tra tenant ở WHERE. Tuy nhiên nếu Product đã managed/second-level cache có tương tác phức tạp, cần kiểm thử behavior theo provider và tenant strategy cụ thể; cache mode chỉ là một phần.

## 38. Phân trang và cache pollution

Một job lấy 100.000 Product:

~~~java
for (int page = 0; page < 1000; page++) {
    List<Product> batch = query
        .setFirstResult(page * 100)
        .setMaxResults(100)
        .getResultList();
    process(batch);
}
~~~

Nếu store mode là USE và Product cacheable, việc đọc rất nhiều Product hiếm gặp có thể làm shared cache bị thay thế các hot entries.

### Một lựa chọn

~~~java
query.setHint(
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.BYPASS);
~~~

### Nhưng vẫn cần quản lý L1

Một EntityManager sống qua toàn bộ vòng lặp có thể tích lũy managed Product objects trong first-level cache. `CacheStoreMode.BYPASS` **không giải phóng managed objects ở L1**.

Với batch read-only, có thể:

- Dùng DTO projection thay vì entities.
- Tạo persistence context mới theo từng batch.
- Dùng streaming/cursor của provider khi phù hợp.
- Flush/clear có chủ đích nếu batch còn ghi.

### Đừng dùng offset pagination trên tập đang được cập nhật mà quên drift

Nếu `process(batch)` đổi điều kiện WHERE, các phần tử trang sau có thể bị bỏ sót do offset shift. Đây là lỗi batch pagination, không phải lỗi cache. Keyset/cursor hoặc stable IDs thường phù hợp hơn.

## 39. Khi nào nên store BYPASS?

Những tình huống có thể hợp lý:

1. Export lớn, đọc mỗi entity một lần.
2. Data migration/backfill đọc hàng loạt đối tượng ít được truy cập lại.
3. Một truy vấn kiểm tra ngắn hạn không muốn làm nóng shared cache.
4. Job phân tích có access pattern khác với workload API hàng ngày.

### Khi nào không nên?

Nếu entity thường được dùng lại ngay sau lần load đầu và hệ thống có L2 cache đúng, store BYPASS sẽ làm mất cơ hội cache warm-up, tăng SELECT về lâu dài.

### Điều cần đo

- Cache hit ratio trước/sau job.
- Evictions trên hot regions.
- DB SELECT count.
- Time to first response và steady-state latency.
- Memory/GC/cache backend bandwidth.

Không quyết định chỉ dựa trên cảm giác “không nên cache dữ liệu nhiều”.

## 40. Khi nào nên retrieve BYPASS?

Những tình huống:

- Dữ liệu có khả năng được cập nhật ngoài JPA cache protocol.
- Một thao tác kiểm tra yêu cầu không sử dụng entry shared cache cũ.
- Đối chiếu giá trị từ DB với giá trị đang được cache để chẩn đoán.
- Một bước cache warm-up muốn ưu tiên DB làm nguồn rồi store lại.

### Không nên dùng BYPASS ở mọi query chỉ vì sợ stale

Nếu L2 cache được cấu hình đồng bộ đúng và workload đọc rất lớn, bypass tất cả có thể:

- Giảm hit ratio thực tế.
- Tăng tải DB.
- Tăng latency và contention.
- Bỏ lợi ích cache mà không cải thiện invariant consistency.

Nếu vấn đề gốc là external writer không invalidates cache, nên sửa **cache invalidation protocol** hoặc tắt cache cho entity đó, thay vì rải rác BYPASS hints ở một vài service mà không có chính sách chung.

## 41. Khi nào nên REFRESH?

`CacheStoreMode.REFRESH` có thể hữu ích khi:

- Muốn chủ động làm mới cached state của một entity.
- Đang kiểm tra hoặc phục hồi cache sau các writes ngoài JPA.
- Một service cần load Product mới và cho các readers tiếp theo dùng state mới.

### Hạn chế

- Không refresh toàn persistence unit.
- Không tự giải quyết object managed cũ trong contexts khác.
- Không bảo đảm transaction thấy mọi concurrent commit.
- Có thể tạo thêm database traffic đáng kể.
- Nếu dùng trên nhiều truy vấn lớn, có thể đánh mất lợi ích L2.

### Một chính sách tốt hơn cho thay đổi ngoài JPA

Khi một batch/import cập nhật Product#10:

1. Đảm bảo write và version update đúng database.
2. Sau commit, phát sự kiện invalidation có idempotency và thứ tự phù hợp.
3. Evict/update đúng Product cache entry hoặc region liên quan.
4. Khi cần, reader dùng BYPASS/REFRESH để nạp lại.
5. Đo cache consistency dưới tải concurrent và nhiều nodes.

REFRESH chỉ là **một công cụ** trong policy ấy.

## 42. Tính tương thích với optimistic locking

Một Product cached với:

~~~text
price = 100000
version = 7
~~~

Trong khi DB:

~~~text
price = 120000
version = 8
~~~

Nếu code lấy object stale và cố update qua managed JPA entity versioned, provider có thể phát hiện version conflict ở flush/commit.

### Không dùng conflict như một công cụ refresh cache

Sai:

~~~text
Đọc cached state cũ.
Cố UPDATE.
Nếu OptimisticLockException -> cứ retry trong same context.
~~~

Sau conflict, transaction có thể rollback-only và entity managed còn stale. Nếu nghiệp vụ cho phép retry, **transaction/context mới**, đọc lại state và revalidate invariants. Cache retrieve BYPASS/REFRESH có thể giúp tránh L2 stale trong attempt mới, nhưng không thay thế retry protocol.

### Kiểm tra expectedVersion từ client

Ngay cả khi server dùng BYPASS và đọc Product version=8, nếu client gửi form đã xem version=7, server phải kiểm tra expectedVersion/If-Match để không âm thầm ghi đè lựa chọn của người khác.

Cache mode không tự biết client đã chỉnh sửa dựa trên phiên bản nào.

## 43. Database writes qua JPA và cache invalidation

Với JPA managed entity:

~~~java
em.getTransaction().begin();

Product p = em.find(Product.class, id);
p.changePrice(new BigDecimal("120000.00"));

em.getTransaction().commit();
~~~

Provider có trách nhiệm phối hợp database state và shared cache theo JPA/cache configuration và transaction semantics tương ứng.

### Điều không nên kết luận

Không thể chỉ từ `@Version` hoặc `CacheStoreMode.USE` kết luận:

- Mọi node trong cluster đều invalidate ngay lập tức.
- Không thể có stale reads trong bất cứ khoảng thời gian nào.
- Native SQL/bulk UPDATE ở nơi khác được nhận biết tự động.
- Mọi collection associations được cập nhật cùng lúc và nhất quán như một cache transaction hoàn toàn atomic trên mọi backend.

### Khi có external writes

Một hệ thống dùng:

~~~text
Application A: JPA
Application B: JDBC
Data migration: SQL script
Stored procedure: trực tiếp UPDATE products
~~~

phải có **chính sách invalidation đồng nhất**. Đừng coi JPA annotations trong Application A là cách tự động kiểm soát những writes của B.

## 44. Cache eviction và transaction commit boundary

Một kỹ thuật thường dùng khi external write cập nhật Product:

~~~java
cache.evict(Product.class, productId);
~~~

Nhưng **thời điểm evict** quan trọng.

### Evict quá sớm

~~~text
TX_A: UPDATE Product nhưng chưa commit.
Application evict Product khỏi L2.
TX_B: đọc DB vẫn thấy state cũ, có thể điền lại L2.
TX_A: COMMIT.
L2 có nguy cơ giữ state cũ nếu không có invalidation sau commit.
~~~

### Evict sau commit

Khi write thực sự commit, invalidation theo event sau commit thường tránh tình huống cache bị làm nóng lại bằng state cũ trong cửa sổ trước commit.

### Cũng cần nghĩ về race

Ngay cả invalidation sau commit vẫn có những race giữa readers/writers phân tán. Hệ thống cần version comparison, cache concurrency strategy hoặc event ordering phù hợp nếu yêu cầu consistency cao.

**Không có một dòng `evict()` đơn lẻ bảo đảm cluster-wide strong consistency trong mọi kiến trúc.**

## 45. Cẩn trọng với cache cache-penetration/stampede

Khi nhiều requests cùng thấy miss sau eviction:

~~~text
Product#10 bị evict.
1.000 requests đến trong thời gian ngắn.
Tất cả muốn tải Product#10 từ DB.
~~~

Một số cache providers có chiến lược đồng bộ/cấp cache entry, nhưng không thể mặc định rằng JPA L2 tự giới hạn lượng request concurrent theo một cách chung.

### Các biện pháp giảm rủi ro

- Điều chỉnh cache TTL/capacity theo workload.
- Warm up những hot entities có chọn lọc.
- Dùng cache provider có chiến lược chống stampede phù hợp.
- Không gọi `evictAll()` quá thường xuyên.
- Đo cache miss peaks và DB load sau deploy/batch updates.

### Không giải quyết bằng REFRESH mọi request

Nếu mọi request đều dùng `CacheStoreMode.REFRESH` để bảo đảm mới, hệ thống có thể chuyển hầu hết tải đọc về DB, làm mất lợi ích shared cache.

## 46. Hibernate statistics để quan sát cache

JPA chuẩn có `Cache.contains()` và `evict()`, nhưng **không định nghĩa bộ metrics hit/miss/put chi tiết giống nhau trên mọi provider**.

Ví dụ Hibernate có thể cung cấp statistics của `SessionFactory`:

~~~java
SessionFactory sf =
    emf.unwrap(SessionFactory.class);

Statistics stats = sf.getStatistics();

long hits = stats.getSecondLevelCacheHitCount();
long misses = stats.getSecondLevelCacheMissCount();
long puts = stats.getSecondLevelCachePutCount();
~~~

Đây là Hibernate-specific API, cần:

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
~~~

và cấu hình statistics phù hợp, ví dụ bật thống kê trong môi trường test. Tên/lifecycle của API phụ thuộc Hibernate version.

### Đọc metrics đúng cách

- **Hit:** provider thực sự tìm được state phù hợp trong L2.
- **Miss:** có tra nhưng không có state phù hợp.
- **Put:** có đưa state vào L2.

Những metrics không đồng nghĩa hoàn toàn với số SQL: một query có thể gây SELECT để xác định IDs, trong khi entity state được lấy từ L2; ngược lại một query DTO không tạo L2 hit.

### Không đo chỉ một request rồi kết luận

Cache cần warm-up và eviction policies; test phải kiểm soát state ban đầu và tạo **EntityManager mới** giữa các lượt để first-level cache không che lấp L2 behavior.

## 47. Kiểm thử cơ bản: USE → BYPASS → REFRESH

Thiết lập fixture:

~~~text
Product#10:
  price=100000
  version=7
~~~

### Giai đoạn A: warm shared cache

~~~java
EntityManager emA = emf.createEntityManager();
try {
    Product p = emA.find(
        Product.class,
        productId,
        Map.of(
            "jakarta.persistence.cache.retrieveMode",
            CacheRetrieveMode.USE,
            "jakarta.persistence.cache.storeMode",
            CacheStoreMode.USE
        )
    );
    assertNotNull(p);
} finally {
    emA.close();
}
~~~

### Giai đoạn B: tạo shared cache stale một cách có kiểm soát

Trong một integration test chuyên biệt, một connection/JDBC operation ngoài JPA cache protocol update Product và commit:

~~~sql
UPDATE products
SET price=120000, version=8
WHERE id=10;
~~~

Chú ý nếu test dùng cùng transaction chưa commit hoặc cache provider có external invalidation, kết quả cần điều chỉnh; mục tiêu là kiểm tra một fixture stale L2 thực.

### Giai đoạn C: EntityManager mới với retrieve USE

~~~java
EntityManager emB = emf.createEntityManager();
try {
    Product p = emB.find(Product.class, productId);

    // Có thể thấy cached state cũ nếu L2 vẫn còn.
    // Đừng khẳng định mọi provider chắc chắn trả 100000.
} finally {
    emB.close();
}
~~~

### Giai đoạn D: EntityManager mới với retrieve BYPASS

~~~java
EntityManager emC = emf.createEntityManager();
try {
    Product p = emC.find(
        Product.class,
        productId,
        Map.of(
            "jakarta.persistence.cache.retrieveMode",
            CacheRetrieveMode.BYPASS,
            "jakarta.persistence.cache.storeMode",
            CacheStoreMode.REFRESH
        )
    );

    // Nếu đọc được committed state mới từ DB:
    assertEquals(
        new BigDecimal("120000.00"),
        p.getPrice());
} finally {
    emC.close();
}
~~~

### Vì sao mỗi giai đoạn tạo EntityManager mới?

Để không lấy ngay Product từ first-level identity map. Nếu dùng một EntityManager xuyên suốt test, kết quả có thể bị chi phối bởi state managed, không còn đo đúng retrieve/store mode của shared cache.

## 48. Kiểm thử store BYPASS không làm nóng cache

Một bài test khác:

1. Evict Product#10 khỏi L2.
2. Tạo EntityManager mới, load Product#10 với `retrieve=BYPASS` và `store=BYPASS`.
3. Đóng EntityManager.
4. Kiểm tra cache statistics/contains nếu provider/cache backend hỗ trợ đáng tin.
5. Load Product#10 với `retrieve=USE` và quan sát hit/miss.

### Pseudocode

~~~java
Cache cache = emf.getCache();
cache.evict(Product.class, productId);

EntityManager em = emf.createEntityManager();
try {
    em.find(
        Product.class,
        productId,
        Map.of(
            "jakarta.persistence.cache.retrieveMode",
            CacheRetrieveMode.BYPASS,
            "jakarta.persistence.cache.storeMode",
            CacheStoreMode.BYPASS
        )
    );
} finally {
    em.close();
}

boolean cached =
    cache.contains(Product.class, productId);
~~~

Với một cache provider hoạt động theo mode đúng và fixture đã được cô lập, kết quả mong muốn là operation này không chủ động đưa Product vào L2. Nhưng test concurrent/shared cache có thể bị tác động bởi requests khác và cache implementation; kết hợp metrics cụ thể, không coi `contains()` là công cụ đo mọi chi tiết nội bộ.

## 49. Kiểm thử REFRESH khi L1 đã chứa entity

Một test cần phân biệt:

~~~text
Case 1:
  EntityManager mới, Product chưa managed.
  find(... CacheStoreMode.REFRESH).

Case 2:
  EntityManager đã managed Product.
  find(... CacheStoreMode.REFRESH).

Case 3:
  EntityManager đã managed Product.
  em.refresh(product).
~~~

### Những gì test cần quan sát

- Có SQL SELECT mới hay không?
- Product Java object có cùng identity không?
- Version/price trả về là bao nhiêu?
- Cache hit/miss/put thay đổi thế nào?
- Có transaction/database snapshot đang che committed update không?

**Không đánh đồng Case 1 với Case 2**. Đó là cách rất nhanh phát hiện một giả định sai rằng `CacheStoreMode.REFRESH` buộc mọi `find()` SELECT lại ngay cả khi entity đã managed.

## 50. Kiểm thử phối hợp với @Version

Một scenario:

~~~text
TX_A:
  Load Product#10 version=7

TX_B:
  Update Product#10 version=8
  COMMIT

TX_A:
  Cố sửa Product#10 và FLUSH
~~~

Nếu cả hai writes theo optimistic version protocol, TX_A cần phát hiện conflict hoặc database từ chối transaction theo isolation, **dù cache mode của TX_A ban đầu là USE**.

### Điều cần phân biệt

- **Cache hit/miss:** state ban đầu được lấy từ đâu.
- **Optimistic conflict:** provider có phát hiện version cũ khi ghi không.
- **Transaction isolation:** DBMS cho phép/không cho phép lịch sử concurrent nào.

Không coi cache hit là bằng chứng UPDATE sẽ bị ghi đè; cũng không coi `@Version` là cơ chế làm cache luôn fresh.

## 51. Bẫy khi benchmarking cache modes

Một benchmark:

~~~java
for (int i = 0; i < 1000; i++) {
    em.find(Product.class, productId);
}
~~~

chủ yếu có thể đo **L1 identity map**, không đo L2. Sau lần đầu, 999 lần còn lại trả cùng managed instance.

### Benchmark L2 đúng hơn

~~~text
1. Khởi tạo EntityManagerFactory và cache provider.
2. Warm L2 nếu muốn đo hit scenario.
3. Tạo EntityManager mới cho mỗi thử nghiệm.
4. find Product theo mode cần đo.
5. Đóng EntityManager.
6. Thu SQL metrics + L2 hit/miss/put + latency.
7. Lặp trên nhiều entity keys và phân phối truy cập đại diện.
~~~

### Phân tách ba kịch bản

| Kịch bản | Mục đích |
| --- | --- |
| Cold cache | Đo SELECT từ DB và store overhead |
| Warm cache + USE | Đo lợi ích L2 hit |
| Warm cache + BYPASS | Đo chi phí khi không dùng L2 |

Đừng tính cache hit ratio từ một service có nhiều loại queries rồi quy toàn bộ latency cho CacheRetrieveMode. Network, DB, serialization, transaction và association fetching vẫn ảnh hưởng.

## 52. Cache và fetch plan là hai trục riêng

Entity:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Category category;
~~~

và:

~~~java
@OneToMany(mappedBy = "product", fetch = FetchType.LAZY)
private List<ProductReview> reviews;
~~~

`FetchType.LAZY/EAGER` quyết định **khi nào association cần được nạp** theo semantics JPA/provider.

`CacheRetrieveMode`/`CacheStoreMode` quyết định **cách thao tác nạp entity state tương tác với shared cache**.

### Hai trục không thay thế nhau

Một Product với `FetchType.LAZY` category có thể được tải từ L2, nhưng truy cập category sau đó vẫn có thể phát SQL hoặc cache lookup riêng khi category chưa managed.

Ngược lại, `CacheRetrieveMode.BYPASS` không có nghĩa provider phải fetch mọi LAZY association ngay lập tức.

### Khi cần detail view

Với API Product detail cần Category name và Reviews, query-level fetch plan như `JOIN FETCH`, `EntityGraph` hoặc DTO projection vẫn quan trọng. Cache mode không giải quyết N+1 queries chỉ bằng một enum.

## 53. Tác động của refresh đối với relationship/collection

Một entity root và các associations có thể dùng nhiều loại state:

~~~text
Product#10
  price
  version
  category -> Category#2
  reviews  -> Collection<ProductReview>
~~~

REFRESH Product không có nghĩa:

- Mọi Category trong hệ thống được refresh.
- Mọi ProductReview trong cache được evict.
- Mọi EntityManager đang quản lý Category#2 thấy state mới ngay.

JPA có rules về cascade refresh và provider-managed relationship state, nhưng phạm vi cụ thể phải được hiểu theo mapping, cascade type, fetch plan và cache provider.

### CascadeType.REFRESH khác CacheStoreMode.REFRESH

~~~java
@ManyToOne(cascade = CascadeType.REFRESH)
private Category category;
~~~

`CascadeType.REFRESH` lan truyền một **entity lifecycle refresh operation** theo mapping.

~~~java
CacheStoreMode.REFRESH
~~~

là **shared cache store mode**.

Tên “REFRESH” giống nhau nhưng chức năng khác. Không thêm cascade REFRESH khắp graph chỉ để cố cập nhật cache.

## 54. Evict association/entity khác nhau

Khi Category#2 thay tên:

~~~java
cache.evict(Category.class, categoryId);
~~~

điều này nhắm vào cached state của **Category#2**. Nó không có nghĩa tự xóa mọi Product#10..#N hay mọi cached query result có chứa tên Category, tùy provider cache structure.

Nếu Product DTO chứa `categoryName` được cache riêng ở Spring Cache/Redis, việc evict Category L2 **không tự invalidates DTO cache đó**.

### Cần xác định dependency graph

~~~text
Database Category
    |
    +-- JPA L2 Category region
    |
    +-- Hibernate query result cache
    |
    +-- Spring Cache ProductDto
    |
    +-- CDN/HTTP response cache
~~~

Mỗi lớp có cơ chế invalidation riêng. CacheRetrieveMode/CacheStoreMode chỉ đề cập một lớp cụ thể của JPA.

## 55. Security và dữ liệu nhạy cảm trong cache

Một shared cache có thể làm entity state sống lâu hơn request/transaction của một người dùng. Do đó:

- Không cache thông tin chỉ được phép xem trong phạm vi cụ thể nếu tenant/auth isolation chưa bảo đảm.
- Không đưa credentials, secrets hoặc token vào entity cache nếu không có lý do và chính sách bảo mật rõ ràng.
- Kiểm tra cache key, cache region và serialization/encryption của provider.
- Quản lý data retention/eviction phù hợp.
- Không log cache content hoặc SQL bind params chứa dữ liệu nhạy cảm bừa bãi.

### Bypass không phải security boundary

`CacheRetrieveMode.BYPASS` không kiểm tra user roles. Một entity được load từ DB nhưng sai tenant vẫn là rò rỉ dữ liệu.

**Security phải được enforce bởi authorization, query filters, tenancy model và database controls**, không phải cache hint.

## 56. Những lỗi thường gặp

| Hiện tượng hoặc hiểu nhầm | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Đặt BYPASS nhưng không thấy SELECT mới | Entity đã managed trong L1 | Dùng context mới/refresh có chủ đích |
| USE nhưng không có cache hit | L2 chưa bật/không cacheable/cache miss | Kiểm tra SharedCacheMode, provider metrics |
| USE nghĩa “không SQL” | Query/associations vẫn có thể truy vấn | Đo toàn use case |
| Store BYPASS nghĩa “evict entry cũ” | BYPASS là chính sách store operation | Dùng `Cache.evict` |
| REFRESH làm mọi entity cache được fresh | Chỉ những state liên quan operation | Evict/refresh đúng scope |
| Refresh mode giống em.refresh() | Hai API khác mục tiêu | Tách L1 refresh và L2 store mode |
| em.clear() xóa L2 | Clear chỉ tác động persistence context | Dùng Cache API riêng |
| em.refresh() luôn an toàn khi entity dirty | Pending changes có thể bị ghi đè | Flush/rollback/thiết kế boundary |
| Store BYPASS tiết kiệm mọi bộ nhớ | Entity vẫn vào L1 | Quản lý EntityManager lifecycle/DTO |
| Cache BYPASS tránh lost update | Vẫn có concurrent writers | @Version/lock/atomic SQL |
| @Version tự invalidates mọi cache node | External writers/cluster cần protocol | Cache backend/invalidation design |
| Query DTO được phục vụ từ L2 entity cache | Projection không phải managed entity load | Xem query execution/cache riêng |
| Hibernate query cache là JPA L2 entity cache | Hai lớp cache khác | Cấu hình/đo riêng |
| Spring Cache @Cacheable giống JPA @Cacheable | Khác API và cache keys | Đặt đúng annotation |
| @Cacheable(true) tự bật toàn bộ cache | Cần SharedCacheMode/provider backend | Cấu hình và kiểm thử |
| REFRESH mọi GET để luôn mới | DB load tăng, không giải quyết race | Thiết kế consistency policy |
| External JDBC UPDATE nhưng cache vẫn stale | Không có invalidation | Evict/event/version protocol |
| Evict trước commit rồi hết stale | Reader có thể repopulate bằng state cũ | Invalidation after commit/ordering |
| @Cacheable(false) bảo vệ auth | Không liên quan quyền truy cập | ACL/tenant checks |
| Test dùng cùng EntityManager A cho mọi lượt | L1 che hiệu ứng L2 | Tạo nhiều contexts |
| Chỉ dựa số SELECT để kết luận cache | Query filtering/cross associations | SQL + cache metrics |
| Đổi cache mode nhưng không reset transaction | Snapshot cũ vẫn có thể chi phối | Transaction visibility phù hợp |
| Query hint khác tên chuẩn do viết hoa sai | Property không được nhận | Dùng đúng literal Jakarta |
| Dùng javax hint với Jakarta provider mà không kiểm chứng | Namespace khác thế hệ | Dùng jakarta.* cho JPA 3.x |
| EvictAll mỗi lần sửa Product | Cache hit rate sụt mạnh | Evict đúng entity/region |
| Bypass tất cả thay vì sửa cache protocol | Tải DB tăng, lỗi consistency còn | Sửa invalidation hoặc disable L2 có chọn lọc |
| Bulk update bypass version/cache rules | Managed state và cache có thể stale | Protocol write/clear/evict phù hợp |

## 57. Quy trình chọn mode theo use case

Khi thiết kế một read operation, có thể đi theo quy trình:

1. **Xác định entity và data freshness requirement.** Dữ liệu ít thay đổi hay cập nhật hàng giây?
2. **Xác định các đường ghi.** Chỉ JPA cùng provider hay còn JDBC/procedure/migration?
3. **Kiểm tra SharedCacheMode và @Cacheable.** Entity có thật sự tham gia L2?
4. **Xác định persistence context scope.** Entity đã managed chưa?
5. **Chọn retrieve mode.** Có tin L2 làm nguồn state không?
6. **Chọn store mode.** Muốn điền L2, bỏ lưu, hay refresh?
7. **Xác định transaction isolation và DB routing.** Đọc primary/replica và snapshot ra sao?
8. **Xem fetch plan.** Query trả entity, DTO, association hay aggregate?
9. **Thiết kế invalidation.** External write có làm cache stale không?
10. **Đo lường.** Cache hit/miss/put, SQL, latency, DB load.
11. **Kiểm thử concurrency.** Hai EntityManagers, external writer, multiple nodes nếu có.
12. **Ghi tài liệu quyết định** để các service khác không dùng một mode trái ngược trên cùng entity mà không hiểu tác động.

### Bảng lựa chọn thực dụng

| Use case | Retrieve | Store | Nhận xét |
| --- | --- | --- | --- |
| Danh mục Product ổn định, cache chuẩn | USE | USE | Cho phép tái sử dụng cache |
| Kiểm tra dữ liệu mới từ DB, muốn warm cache | BYPASS | USE hoặc REFRESH | Cân nhắc stale entry/refresh semantics |
| Export entities dùng một lần | BYPASS | BYPASS | Tránh L2 pollution; vẫn quản lý L1 |
| Đọc entity hiếm gặp, chấp nhận cached entry sẵn | USE | BYPASS | Không chủ động store thêm |
| Tái tải shared cached state có nguy cơ stale | BYPASS/USE | REFRESH | Dùng context phù hợp, không nhầm với em.refresh |
| Tồn kho cần bảo vệ giao dịch | Bypass cache nếu hợp lý | BYPASS nếu không muốn store | Vẫn cần atomic UPDATE/lock/constraint |
| API read-only DTO | Tùy | Tùy | Query projection thường không nhờ L2 entity state |

**Không dùng bảng như một lệnh cứng:** mỗi cache provider, workload và consistency requirement phải được xác minh bằng integration tests.

## 58. Bài tập thực hành

### Bài 1 — Hai enum

`CacheRetrieveMode` và `CacheStoreMode` khác nhau ở đâu?

**Gợi ý:** retrieve kiểm soát đọc từ shared cache; store kiểm soát việc lưu/làm mới entity state trong shared cache.

### Bài 2 — Giá trị hợp lệ

CacheRetrieveMode có bao nhiêu giá trị chuẩn? CacheStoreMode có bao nhiêu?

**Gợi ý:** retrieve `USE`, `BYPASS`; store `USE`, `BYPASS`, `REFRESH`.

### Bài 3 — First-level cache

Trong cùng EntityManager, đã nạp Product#10 rồi, gọi `find(... retrieve BYPASS)` có chắc SELECT lại DB không?

**Gợi ý:** không; managed instance có thể được tái sử dụng từ persistence context.

### Bài 4 — CacheStoreMode.BYPASS

Một Product có sẵn trong L2. Chỉ gọi `find(... store BYPASS)` có đảm bảo entry cũ bị xóa không?

**Gợi ý:** không; BYPASS store không phải evict.

### Bài 5 — Evict một entry

Bạn muốn loại Product#10 khỏi shared cache. API chuẩn nào phù hợp?

**Gợi ý:** `emf.getCache().evict(Product.class, 10L)` với ID đúng kiểu.

### Bài 6 — Evict L1

`Cache.evict(Product.class,10L)` có làm một EntityManager đang giữ managed Product#10 đổi giá ngay không?

**Gợi ý:** không; L1 không được refresh tự động chỉ vì L2 evict.

### Bài 7 — CacheStoreMode.REFRESH

Khi nào mode REFRESH được dùng? Có đồng nghĩa mọi entity trong persistence unit đều làm mới không?

**Gợi ý:** ép refresh cached state của load phù hợp từ DB; không phải evictAll.

### Bài 8 — em.refresh

`em.refresh(product)` có thể gây mất thay đổi gì?

**Gợi ý:** pending changes trên managed Product chưa flush có thể bị thay bằng state DB.

### Bài 9 — @Cacheable

`@Cacheable(true)` trên Product có tự bật L2 cache ở mọi provider không?

**Gợi ý:** không; còn shared-cache-mode/cache backend configuration.

### Bài 10 — SharedCacheMode

Khác biệt giữa ENABLE_SELECTIVE và DISABLE_SELECTIVE là gì?

**Gợi ý:** ENABLE_SELECTIVE chỉ cache entities được chọn true; DISABLE_SELECTIVE cache trừ loại bị false.

### Bài 11 — USE/BYPASS

Bạn muốn bỏ qua shared cached Product nhưng cho phép lưu state mới đọc từ DB. Chọn tổ hợp nào?

**Gợi ý:** `CacheRetrieveMode.BYPASS` + `CacheStoreMode.USE`.

### Bài 12 — BYPASS/BYPASS

Bạn muốn một batch chỉ đọc nhiều entities nhưng không tra và không làm nóng L2. Chọn mode nào?

**Gợi ý:** retrieve BYPASS, store BYPASS.

### Bài 13 — USE/BYPASS

Tại sao retrieve USE + store BYPASS vẫn có khả năng trả cached state cũ?

**Gợi ý:** retrieve USE cho phép dùng L2 entry đã có; store BYPASS không loại bỏ nó.

### Bài 14 — @Version

Product có `@Version`. Một native SQL update ngoài JPA không invalidates L2. Version có đảm bảo mọi readers nhận state mới không?

**Gợi ý:** không; version là một phần concurrency protocol, cache invalidation vẫn cần được quản lý.

### Bài 15 — First-level state

Trong một transaction, Product đã được sửa giá trong Java nhưng chưa commit. Gọi find BYPASS có chứng minh giá đó đã commit không?

**Gợi ý:** không; object có thể vẫn là managed instance chứa state chưa commit.

### Bài 16 — Database isolation

Một transaction đang ở snapshot cũ. Dùng retrieve BYPASS và store REFRESH có chắc đọc được commit mới của transaction khác không?

**Gợi ý:** không; DB isolation/snapshot và managed state vẫn quyết định visibility.

### Bài 17 — Query DTO

Một constructor projection trả ProductRow gồm id/sku/price. Có bắt buộc sử dụng L2 entity cache để phục vụ DTO query không?

**Gợi ý:** không; scalar/DTO projection khác entity state load.

### Bài 18 — Query cache

Hibernate query cache có phải cùng API với JPA CacheRetrieveMode không?

**Gợi ý:** không; query result cache là provider-specific.

### Bài 19 — Spring Cache

`org.springframework.cache.annotation.Cacheable` có giống `jakarta.persistence.Cacheable` không?

**Gợi ý:** không; cache method results khác shared JPA entity cache.

### Bài 20 — L1 memory

Batch export dùng store BYPASS nhưng cùng EntityManager load 100.000 Products. Vì sao vẫn có thể dùng nhiều RAM?

**Gợi ý:** first-level persistence context vẫn quản lý entities; dùng DTO/new EM/batch lifecycle phù hợp.

### Bài 21 — Cache warm-up

Bạn vừa evict Product cache do import dữ liệu mới. Vì sao việc tất cả request cùng dùng REFRESH có thể gây quá tải DB?

**Gợi ý:** mọi request ép lấy state từ DB, gây stampede; cần warm-up/throttling/cache strategy.

### Bài 22 — Multi-tenant

Một find BYPASS trả Product thuộc tenant khác. Đây có phải bug của CacheRetrieveMode không?

**Gợi ý:** không; thiếu authorization/tenant isolation.

### Bài 23 — Evict timing

Tại sao evict shared cache trước khi transaction UPDATE commit có thể dẫn tới entry stale được làm nóng trở lại?

**Gợi ý:** reader đọc DB committed state cũ rồi store lại L2 trước khi writer commit.

### Bài 24 — Statistics

Một benchmark gọi `em.find(Product.class,10L)` 1.000 lần trên **cùng EntityManager**. Vì sao không đo được L2 hit đúng?

**Gợi ý:** sau lần đầu, L1 identity map thường phục vụ các lần còn lại.

### Bài 25 — Real test

Thiết kế test so sánh USE, BYPASS và REFRESH bằng EntityManagers mới và update JDBC ngoài cache protocol.

**Gợi ý:** warm L2, commit external update, tạo từng EM mới để load theo mode, quan sát SQL/L2 stats và state.

### Bài 26 — Cache invalidation

Hệ thống có JPA, JDBC, stored procedures và Spring Cache. Vì sao chỉ đặt `@Cacheable(true)` chưa đủ?

**Gợi ý:** nhiều đường ghi/cache layers cần invalidation/consistency protocol riêng.

### Bài 27 — Transaction

Trong checkout, bạn bypass L2 trước khi kiểm tra tồn kho nhưng không lấy lock/conditional UPDATE. Có còn nguy cơ oversell không?

**Gợi ý:** có; cache mode không làm check-then-act thành atomic.

### Bài 28 — REFRESH và cascade

`CacheStoreMode.REFRESH` có giống `CascadeType.REFRESH` không?

**Gợi ý:** không; một cái là cache mode, một cái là lifecycle cascade.

### Bài 29 — Tên hint

Viết chính xác hai property names Jakarta Persistence dùng cho retrieve/store.

**Gợi ý:** `jakarta.persistence.cache.retrieveMode` và `jakarta.persistence.cache.storeMode`.

### Bài 30 — Phân tích use case

Một API public catalog có read traffic lớn, update qua JPA thống nhất, L2 hoạt động tốt. Có nên mặc định mọi request dùng BYPASS/BYPASS không?

**Gợi ý:** thường không; USE/USE có thể hiệu quả hơn. Đo và xác định freshness requirement.

## 59. Bảng ghi nhớ nhanh

| Cần nhớ | Câu trả lời |
| --- | --- |
| CacheRetrieveMode có giá trị nào? | `USE`, `BYPASS` |
| CacheStoreMode có giá trị nào? | `USE`, `BYPASS`, `REFRESH` |
| Retrieve USE | Cho phép đọc shared entity cache |
| Retrieve BYPASS | Không dùng L2 để lấy state trong load phù hợp |
| Store USE | Cho phép store entity state vào L2 |
| Store BYPASS | Không store state của load, không tự evict |
| Store REFRESH | Làm mới cached state từ database khi load phù hợp |
| First-level cache? | Persistence context của EntityManager |
| Second-level cache? | Shared entity cache được provider hỗ trợ/cấu hình |
| BYPASS L2 có bỏ L1 không? | Không |
| REFRESH mode có thay em.refresh? | Không mặc định |
| em.clear() có evict L2 không? | Không |
| em.refresh(entity) có thể mất pending changes? | Có |
| Cache API chuẩn | `emf.getCache().contains()/evict()/evictAll()` |
| Entity nào cache được? | Tùy SharedCacheMode, @Cacheable và provider |
| Query cache có portable qua hai enum không? | Không phải cùng API JPA chuẩn |
| Có thể dùng cache với @Version? | Có, nhưng phải quản lý coherence đúng |
| Cache bypass thay database locking được không? | Không |
| External SQL có tự invalidate L2? | Không được mặc định |
| Khi nào dùng BYPASS/USE? | Muốn load từ DB, cho phép store cache |
| Khi nào dùng BYPASS/BYPASS? | Không tra/không làm nóng L2 cho load |
| Khi nào dùng REFRESH? | Muốn làm mới cached entity state từ DB |
| Query DTO có chắc dùng entity L2? | Không |
| Multi-tenant do cache mode bảo vệ? | Không |
| Test L2 đúng? | Context mới, cache warm-up, SQL + stats |
| Cách chọn mode | Theo workload, data freshness, invalidation và transaction |

## Kết luận

**`CacheRetrieveMode` và `CacheStoreMode` là hai công cụ chuẩn của Jakarta Persistence giúp biểu đạt cách một thao tác nạp entity tương tác với shared entity cache.** `CacheRetrieveMode.USE` cho phép sử dụng cached state, còn `BYPASS` bỏ qua shared cache khi lấy state; `CacheStoreMode.USE` cho phép lưu, `BYPASS` không lưu, và `REFRESH` yêu cầu làm mới cached state từ database. Có thể đặt các mode qua hai property hints `jakarta.persistence.cache.retrieveMode` và `jakarta.persistence.cache.storeMode` trên `EntityManager.find()` hoặc `Query.setHint()` theo phạm vi operation.

Tuy nhiên, **shared cache không phải persistence context**. Nếu một entity đã managed trong EntityManager hiện tại, BYPASS/REFRESH mode không phải lời hứa rằng JPA bỏ qua identity map và SELECT lại. `em.refresh(entity)`, `em.clear()` và `EntityManagerFactory.getCache().evict(...)` giải quyết những việc khác nhau; không dùng chúng thay thế cho nhau một cách máy móc. Các annotation `@Cacheable`, SharedCacheMode và cache backend cũng quyết định việc shared cache có thật sự hoạt động không.

Trong ứng dụng thực, hãy chọn mode theo **mức độ mới cần thiết của dữ liệu, tần suất đọc/ghi, các đường cập nhật ngoài JPA, transaction isolation, multi-tenancy và hiệu năng**. Khi dữ liệu có invariant quan trọng như tồn kho hoặc thanh toán, bypass cache không thể thay optimistic locking, pessimistic locking, atomic conditional UPDATE hay constraints. Khi có nhiều cache layers hoặc nhiều writers, cần một chính sách invalidation nhất quán và integration tests dùng **nhiều EntityManager, state đã commit và cache metrics thật**.

Nguyên tắc cuối cùng là **tách bạch nguồn dữ liệu, nơi lưu bản sao, vòng đời persistence context và ranh giới transaction**. Chỉ khi hiểu rõ bốn yếu tố đó, việc chọn USE, BYPASS hay REFRESH mới mang lại hiệu năng và độ mới dữ liệu mong muốn thay vì tạo cảm giác an toàn sai.
