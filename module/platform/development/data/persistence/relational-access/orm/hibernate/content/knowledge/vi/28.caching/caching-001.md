# Phân biệt bộ nhớ đệm cấp một, cấp hai, truy vấn và bộ kết nối

Khi một ứng dụng dùng Hibernate chạy nhanh hơn ở lần truy cập thứ hai, chúng ta rất dễ nói: “dữ liệu đã được cache”. Nhưng **cache nào** đang tạo ra khác biệt? Cùng một hệ thống có thể có:

- **Bộ nhớ đệm cấp một (first-level cache, L1):** trạng thái entity nằm trong `Persistence Context` của một `Session`/`EntityManager`.
- **Bộ nhớ đệm cấp hai (second-level cache, L2):** trạng thái entity hoặc collection được chia sẻ giữa nhiều persistence contexts của cùng `SessionFactory`, nhờ một cache provider.
- **Bộ nhớ đệm kết quả truy vấn (query result cache):** lưu kết quả logic của một câu query và bộ tham số tương ứng để tránh chạy lại cùng query khi dữ liệu còn hợp lệ.
- **Bộ kết nối (connection pool):** tái sử dụng **kết nối database**, không tái sử dụng các entity hay kết quả truy vấn.

Ngoài bốn thành phần trên, còn có **Hibernate query-plan cache**, **JDBC prepared-statement cache**, **database execution-plan cache** và **database buffer pool**. Chúng hoạt động ở các tầng khác nhau. Không thể lấy việc số lượng connection ít đi làm bằng chứng rằng L2 cache đang hoạt động; cũng không thể lấy một lần `find()` không phát SQL để kết luận query cache đã trúng.

Bài này đặt các cơ chế vào đúng vị trí trong kiến trúc Hibernate ORM 6.x, giải thích vòng đời, cơ chế hit/miss, cấu hình, tính nhất quán và cách quan sát. Mục tiêu là nhận diện **đối tượng được tái sử dụng** và **ranh giới của cơ chế tái sử dụng**, từ đó chọn tối ưu phù hợp thay vì bật nhiều loại cache rồi kỳ vọng tất cả query sẽ nhanh hơn.

## 1. Sơ đồ tổng thể: mỗi tầng tái sử dụng thứ gì?

~~~mermaid
flowchart TD
    A["HTTP request / service use case"] --> B["EntityManager / Hibernate Session"]
    B --> C["Persistence Context - L1"]
    C -->|L1 miss hoặc cần query| D["Hibernate ORM"]
    D --> E["L2 cache: entity / collection regions"]
    D --> F["Query result cache: cached query results"]
    D --> G["Query plan cache: parsed/compiled query plan"]
    D -->|SQL thật sự cần chạy| H["JDBC DataSource / Connection Pool"]
    H --> I["Physical DB connection được tái sử dụng"]
    I --> J["Database"]
    J --> K["DB buffer pool / execution plan cache"]
~~~

Sơ đồ mang tính khái niệm, không biểu diễn thứ tự gọi bắt buộc của mọi code path. Ví dụ, một entity load bằng ID có thể tìm L1 rồi L2 trước khi cần SQL; một HQL query có thể được biên dịch nhờ query-plan cache, kiểm tra query result cache, và nếu miss thì mới thực thi SQL. Dù thứ tự cụ thể phụ thuộc loại operation, **mỗi cơ chế lưu một loại tài nguyên khác nhau**.

| Cơ chế | Lưu/tái sử dụng gì? | Phạm vi điển hình | Có trực tiếp tránh SQL không? |
| --- | --- | --- | --- |
| **L1** | Entity identity và state của managed entities, trạng thái collection trong persistence context | Một `Session`/`EntityManager` | Có, nếu truy cập lại managed identity phù hợp |
| **L2** | Entity/collection state theo cache regions và keys | Nhiều Sessions của cùng SessionFactory, tùy provider có thể phân tán | Có với những load paths được hỗ trợ và cache hit |
| **Query result cache** | Kết quả query theo query/parameters/pagination/filter context | Chia sẻ theo SessionFactory và cache regions | Có thể tránh thực thi lại query SQL; vẫn có thể phải load entity state |
| **Connection pool** | Connection/physical DB session đã mở | DataSource, nhiều request và transactions | Không; SQL vẫn chạy nếu ORM cần dữ liệu |
| **Hibernate query-plan cache** | Plan của HQL/JPQL/query metadata | SessionFactory | Tránh parse/compile lại query, không đồng nghĩa tránh SQL |
| **DB buffer pool** | Các trang dữ liệu/index từ đĩa | Database server/instance | Tránh disk I/O, nhưng SQL vẫn có thể chạy qua JDBC |

**Câu hỏi chẩn đoán đầu tiên:** “Đã tái sử dụng entity, kết quả truy vấn, query plan, database connection hay các trang dữ liệu trong bộ nhớ DB?”

## 2. Mô hình ví dụ

Giả sử một ứng dụng quản lý sản phẩm:

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {
    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ProductStatus status;

    @Version
    private long version;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {}

    public Long getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public ProductStatus getStatus() { return status; }
    public long getVersion() { return version; }
    public Category getCategory() { return category; }

    public void changePrice(BigDecimal newPrice) {
        this.price = newPrice;
    }
}
~~~

~~~java
package com.example.catalog;

import jakarta.persistence.*;

@Entity
@Table(name = "categories")
public class Category {
    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Category() {}

    public Long getId() { return id; }
    public String getName() { return name; }
}
~~~

~~~java
package com.example.catalog;

public enum ProductStatus {
    DRAFT, ACTIVE, DISCONTINUED
}
~~~

Mỗi `public` class/enum là một file Java riêng. Các ví dụ tập trung vào đọc dữ liệu; constructor nghiệp vụ, validations, getters đầy đủ và cấu hình schema không phải trọng tâm.

Một số tình huống sẽ bật L2 có chủ đích bằng `@Cacheable`/`@Cache`. **Entity trên đây chưa mặc định được đảm bảo có L2 cache**. Việc bật Hibernate hoặc JPA cache không có nghĩa mọi entity trong ứng dụng đều được cache theo cùng cách.

## 3. Bộ nhớ đệm cấp một: Persistence Context

**L1 cache gắn với từng persistence context và luôn là thành phần cốt lõi trong hoạt động managed entity của Hibernate.** Nó không cần một Redis/Ehcache riêng. Khi Hibernate quản lý một entity, persistence context lưu quan hệ giữa `(entity type, identifier)` và instance được quản lý.

### 3.1. Cùng EntityManager, cùng entity identity

~~~java
try (EntityManager em = entityManagerFactory.createEntityManager()) {
    Product first = em.find(Product.class, 10L);
    Product second = em.find(Product.class, 10L);

    System.out.println(first == second); // Thông thường true.
}
~~~

Nếu Product ID 10 tồn tại và `em` quản lý entity đó, lần `find()` thứ hai thường không cần SELECT nữa vì identity đã nằm trong L1. Cả hai biến trỏ tới **cùng một managed Java instance**.

Điểm quan trọng:

- L1 không phải bản sao serialize của Product.
- L1 hỗ trợ **identity map**: một persistence context không có hai managed instances độc lập cho cùng entity identity.
- Nó giúp Hibernate theo dõi trạng thái ban đầu, dirty checking, association proxies và những thao tác lifecycle khác.
- Nó phục vụ **tính đúng đắn và identity consistency**, không chỉ là tối ưu tốc độ.

Nếu Product không tồn tại, hành vi đối với negative lookup/cache miss tùy API và cơ chế; không nên suy ra mọi lần truy vấn ID không tồn tại đều được cache vĩnh viễn.

### 3.2. Hai EntityManager khác nhau: hai L1 riêng

~~~java
Product fromFirst;

try (EntityManager em1 = emf.createEntityManager()) {
    fromFirst = em1.find(Product.class, 10L);
}

try (EntityManager em2 = emf.createEntityManager()) {
    Product fromSecond = em2.find(Product.class, 10L);

    // Không kỳ vọng hai biến là cùng một managed instance.
    System.out.println(fromFirst == fromSecond); // Thường false.
}
~~~

`em1` và `em2` có hai persistence contexts khác nhau. Việc `em1` đã đọc Product không đưa Java object của nó vào L1 của `em2`. Nếu L2 tắt hoặc miss, `em2` cần đọc database lại.

Nếu L2 hoạt động, `em2` có thể lấy **entity state** từ L2 và tạo một managed instance mới trong L1 của chính nó. **L2 không khiến hai EntityManager chia sẻ cùng object reference**.

### 3.3. L1 hoạt động ra sao với truy vấn HQL?

Chạy lại một HQL query trong cùng EntityManager không đồng nghĩa query SQL được bỏ qua:

~~~java
List<Product> first = em.createQuery(
        "select p from Product p where p.status = :status",
        Product.class
    )
    .setParameter("status", ProductStatus.ACTIVE)
    .getResultList();

List<Product> second = em.createQuery(
        "select p from Product p where p.status = :status",
        Product.class
    )
    .setParameter("status", ProductStatus.ACTIVE)
    .getResultList();
~~~

Nếu query result cache không được dùng và không có tối ưu chuyên biệt, Hibernate vẫn có thể chạy SELECT hai lần để xác định tập kết quả. Nhưng nếu cả hai lần trả Product ID 10 trong cùng persistence context, object `Product` tương ứng thường vẫn là **cùng managed instance**.

Phân biệt rõ:

- **Entity identity đã có trong L1**: Hibernate không cần tạo managed instance thứ hai.
- **Tập rows nào phù hợp một query**: thường vẫn cần truy vấn database trừ khi query cache hoặc một cơ chế khác đáp ứng.

### 3.4. L1 và dirty checking

~~~java
EntityTransaction tx = em.getTransaction();
tx.begin();

Product product = em.find(Product.class, 10L);
product.changePrice(new BigDecimal("199.00"));

tx.commit();
~~~

Khi Product managed thay đổi, Hibernate dùng trạng thái được theo dõi để phát hiện thuộc tính dirty và flush UPDATE trong transaction (tùy flush mode). Đây là một phần công việc của persistence context.

**L1 không phải một cache chỉ đọc.** Nó lưu đối tượng đang làm việc trong unit of work và có thể chứa thay đổi chưa flush/chưa commit. Không được dùng trạng thái L1 của một Session như một nguồn “giá trị đã commit” có thể chia sẻ cho request khác.

### 3.5. Evict, detach, clear, refresh

Các thao tác thường dùng:

~~~java
em.detach(product);   // Bỏ riêng product khỏi persistence context.
em.clear();           // Bỏ toàn bộ managed entities khỏi context.
em.refresh(product);  // Tải lại state của managed product từ DB.
~~~

Lưu ý:

- `detach` làm entity không còn managed; một lần `find` tiếp theo có thể tải/tra cứu lại.
- `clear` xóa quản lý hiện tại, **không phải** câu lệnh xóa database rows.
- `refresh` cập nhật object managed từ nguồn persistent theo provider semantics; có thể làm mất thay đổi local chưa flush của entity.
- `flush` đồng bộ những thay đổi pending ra database transaction; **không xóa L1**.
- `close` kết thúc EntityManager và persistence context tương ứng (không nhất thiết đóng physical connection, vì có thể trả connection về pool).

Không dùng `clear()` để “tăng hiệu năng” tùy tiện nếu còn cần dirty checking hoặc pending state chưa flush; việc detach/clear có thể làm mất thay đổi chưa được ghi.

### 3.6. L1 không có TTL kiểu Redis

L1 tồn tại theo vòng đời persistence context, không có chính sách expire-after-write độc lập cho từng entity như distributed cache. Một EntityManager mở quá lâu có thể:

- Giữ nhiều managed objects trong bộ nhớ.
- Trả lại state cũ nếu dữ liệu bị cập nhật từ transaction khác.
- Tăng overhead dirty checking/flush.
- Dẫn tới lỗi thiết kế transaction hoặc bộ nhớ.

Đặt scope hợp lý, thường theo unit of work/request transaction thay vì giữ một EntityManager dùng chung vô thời hạn. `EntityManager` và Hibernate `Session` không an toàn cho truy cập đồng thời bởi nhiều thread.

## 4. L1 có thể khiến đọc thấy dữ liệu cũ

Giả sử transaction A đọc Product ID 10. Transaction B cập nhật giá Product và commit. Sau đó A gọi:

~~~java
Product same = em.find(Product.class, 10L);
~~~

Nếu Product vẫn managed trong L1, A có thể nhận lại **giá trị đã tải trước đó**. Kết quả không phải lúc nào phản ánh giá mới từ B. Đây là hành vi cần hiểu trong transaction isolation và persistence context.

### 4.1. Refresh khi thật sự cần đồng bộ

~~~java
Product product = em.find(Product.class, 10L);
em.refresh(product);
~~~

`refresh` yêu cầu provider đồng bộ lại state từ database theo ngữ nghĩa isolation/locking đang có. Nhưng nếu A có thay đổi local chưa flush, refresh có thể ghi đè chúng. Nếu tính nhất quán nghiệp vụ quan trọng, hãy chọn transaction scope, isolation hoặc locking phù hợp thay vì refresh bừa bãi.

### 4.2. Bulk update bypass managed state

~~~java
em.createQuery(
        "update Product p set p.price = :newPrice " +
        "where p.status = :status"
    )
    .setParameter("newPrice", new BigDecimal("150.00"))
    .setParameter("status", ProductStatus.ACTIVE)
    .executeUpdate();
~~~

Bulk HQL/JPQL DML không cập nhật đồng bộ từng managed Product trong L1 theo cách dirty checking thông thường. Nếu persistence context đang giữ Product liên quan, state có thể stale. Cần chủ động thiết kế `flush`/`clear`/`refresh` và transaction boundary theo hợp đồng cụ thể; không mặc định mọi managed object tự đổi theo bulk update.

**L1 cache độc lập với connection pool:** đổi/release JDBC connection không tự xóa các managed entities; ngược lại `clear()` không đồng nghĩa đóng physical connection.

## 5. Bộ nhớ đệm cấp hai: chia sẻ giữa các persistence contexts

L2 cache là vùng lưu **entity/collection state** chia sẻ giữa nhiều persistence contexts sử dụng cùng Hibernate `SessionFactory`. Nó thường cần cache region factory và cache provider phù hợp; ví dụ một implementation JCache hoặc một tích hợp cache provider được Hibernate hỗ trợ.

### 5.1. Cache hit giữa hai Sessions

~~~text
Session A:
  find(Product, 10)
    L1 miss -> L2 miss -> SELECT DB -> lưu Product state theo cache policy

Session A đóng:
  L1 A không còn

Session B:
  find(Product, 10)
    L1 B miss -> L2 hit -> hydrate managed Product trong L1 B
    có thể không cần SELECT DB
~~~

Điều này có thể giảm round trips và database workload khi cùng entity được truy cập nhiều lần giữa các requests.

Nhưng L2 thường không chia sẻ **chính Java object mutable** giữa các Sessions. Entity state trong cache được quản lý qua cache entries/regions; Session B dựng hoặc dùng instance managed theo identity map của nó. Cơ chế lưu dữ liệu cụ thể phụ thuộc cache provider và Hibernate version.

### 5.2. L2 không được mặc định cho mọi entity

Để một entity được cache cấp hai, thường cần đồng thời:

1. Cache region factory và provider được cấu hình đúng.
2. L2 caching được cho phép.
3. Entity/collection phù hợp với shared-cache policy và được chỉ định cacheable theo mapping.
4. Cache region/policy tương thích yêu cầu read/write consistency.
5. Các thao tác đọc dùng những loading paths có thể tận dụng cache.

Không nên nghĩ chỉ bật `hibernate.cache.use_second_level_cache=true` là mọi SELECT tự biến mất. Khi thiếu cache region factory/provider thích hợp, setting này không tự tạo một distributed cache.

### 5.3. Ví dụ annotation mapping

Với Hibernate-specific cache annotation:

~~~java
import jakarta.persistence.Cacheable;
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Cacheable
@Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
@Table(name = "products")
public class Product {
    // Id, basic fields, version, associations...
}
~~~

`@Cacheable` thuộc Jakarta Persistence. `@Cache` và `CacheConcurrencyStrategy` là extension của Hibernate; cache concurrency strategy điều chỉnh cách Hibernate phối hợp vùng cache với thao tác cập nhật.

Đây là **snippet thay đổi annotations** cho entity Product đã khai báo, không phải yêu cầu tạo thêm một class Product trùng tên.

### 5.4. JCache provider

Một cách tích hợp phổ biến trong Hibernate 6.x dùng `hibernate-jcache` cùng provider hỗ trợ JCache:

~~~xml
<!-- Ví dụ Maven: giữ Hibernate core và jcache cùng version. -->
<dependency>
  <groupId>org.hibernate.orm</groupId>
  <artifactId>hibernate-core</artifactId>
  <version>6.6.0.Final</version>
</dependency>

<dependency>
  <groupId>org.hibernate.orm</groupId>
  <artifactId>hibernate-jcache</artifactId>
  <version>6.6.0.Final</version>
</dependency>
~~~

Còn cần dependency và cấu hình của **JCache provider** phù hợp, ví dụ một provider dựa trên Ehcache hoặc Infinispan tùy stack. `hibernate-jcache` là lớp tích hợp của Hibernate, không tự cung cấp mọi tính năng backing cache.

Cấu hình tham khảo:

~~~properties
hibernate.cache.use_second_level_cache=true
hibernate.cache.region.factory_class=org.hibernate.cache.jcache.internal.JCacheRegionFactory

# Nhà cung cấp cache, region definitions, TTL, heap/off-heap,
# cluster settings... cần cấu hình tương ứng với provider.
~~~

Tên properties/khả năng provider có thể thay đổi theo Hibernate và cache backend. Các ví dụ version ở đây phục vụ minh họa cho dòng 6.x, không phải hướng dẫn lấy version mới nhất cho mọi dự án.

### 5.5. Region là gì?

L2 thường chia dữ liệu vào **cache regions** có thể có policy riêng:

- Entity region cho Product.
- Entity region cho Category.
- Collection region cho một association to-many được cache.
- Regions phục vụ query result hoặc timestamp/invalidation metadata nếu query cache bật.

Region giúp định cấu hình eviction, TTL, giới hạn memory, statistics và concurrency cho các nhóm dữ liệu khác nhau. Một region chứa dữ liệu hot của danh mục sản phẩm có thể có chính sách khác với dữ liệu biến động cao như tồn kho.

Đừng coi L2 cache là một bảng Java `Map<Long, Product>` đơn giản có thể tự ý đọc/ghi mà không qua Hibernate. ORM quản lý key, type metadata, version, transaction synchronization và invalidation theo cache strategy.

## 6. Những gì phù hợp và không phù hợp để đưa vào L2

### 6.1. Dữ liệu đọc nhiều, thay đổi ít

Những entity thường phù hợp:

- Danh mục loại sản phẩm.
- Bảng mã, tỉnh/thành, quốc gia, cấu hình tham chiếu ít thay đổi.
- Tài liệu/metadata tương đối ổn định.
- Một số entity được đọc bằng ID lặp lại với tần suất cao.

Những entity cần thận trọng:

- Số dư, tồn kho hoặc trạng thái đặt chỗ thay đổi liên tục.
- Dữ liệu có yêu cầu freshness tuyệt đối.
- Entity khổng lồ với nhiều trường đọc không thường xuyên.
- Dữ liệu mang quyền truy cập phức tạp hoặc có isolation giữa nhiều tenant.
- Dữ liệu bị cập nhật trực tiếp bởi ứng dụng khác mà không có cơ chế invalidation.

### 6.2. Cache concurrency strategies

Hibernate có các chiến lược như:

| Strategy | Định hướng dùng | Lưu ý |
| --- | --- | --- |
| `READ_ONLY` | Dữ liệu hầu như bất biến | Không phù hợp khi ORM cần cập nhật entity đã cache |
| `NONSTRICT_READ_WRITE` | Chấp nhận một cửa sổ dữ liệu cũ theo semantics provider | Không nên dùng cho quy tắc nghiệp vụ đòi consistency mạnh |
| `READ_WRITE` | Entity có thể cập nhật, cần cơ chế phối hợp cache với versioning/transaction | Không tự tương đương khóa giao dịch database |
| `TRANSACTIONAL` | Provider hỗ trợ transactional cache phù hợp | Không mặc định mọi cache backend đều hỗ trợ |

Tên strategy và điều kiện hỗ trợ cần kiểm tra đúng Hibernate/provider version. Không phải mọi caching provider đều thực thi mọi concurrency strategy như nhau.

### 6.3. L2 không phải “nguồn sự thật”

Database vẫn là nguồn dữ liệu bền vững của ORM. Cache có thể miss, bị evict, hết TTL, restart hoặc không đồng bộ trong sự cố mạng. Ứng dụng phải đúng về nghiệp vụ ngay cả khi L2 bị tắt.

Một thiết kế có nghiệp vụ chỉ đúng khi tất cả request đọc cùng bản sao trong cache nhưng không có DB constraint/transaction bảo vệ thường không an toàn. Ví dụ giảm tồn kho cần atomic update/locking trong DB, không chỉ đọc số lượng từ L2 rồi sửa giá trị trong bộ nhớ.

## 7. Entity cache và collection cache không giống nhau

Giả sử Category có danh sách Products:

~~~java
@OneToMany(mappedBy = "category", fetch = FetchType.LAZY)
private Set<Product> products = new HashSet<>();
~~~

Cache entity `Product` không tự động đồng nghĩa cache **danh sách Product IDs thuộc một Category**. Nếu muốn cache collection mapping, cần cấu hình collection cache phù hợp:

~~~java
@OneToMany(mappedBy = "category", fetch = FetchType.LAZY)
@Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
private Set<Product> products = new HashSet<>();
~~~

Ý nghĩa khái quát:

- Entity cache lưu state của từng Product.
- Collection cache có thể lưu tập phần tử/identifiers/association state theo owner key, tùy loại collection mapping.
- Một collection cache hit không nhất thiết cung cấp đầy đủ state của mọi element; Hibernate có thể còn cần entity loads, khi đó entity L2 cache có thể hỗ trợ.

Đây là lý do đo `collection cache hits` và `entity cache hits` riêng khi phân tích tải to-many.

### 7.1. Collection cache cần invalidation đúng

Nếu một Product chuyển từ Category A sang Category B, collection membership của A và B thay đổi. Cache region phải phản ánh thay đổi association, tùy owning side, mapping và cache strategy. Bulk update, native SQL hoặc write bên ngoài ORM có thể bỏ qua những đường invalidation thông thường.

Không bật collection cache chỉ vì UI thường mở danh mục; cần đánh giá tần suất thay đổi quan hệ và cách dữ liệu được ghi.

### 7.2. L2 không thay thế batch fetching

Một danh sách có 100 products và 100 categories có thể phát sinh N+1 nếu ứng dụng truy cập associations theo từng entity. Nếu L2 trúng nhiều Category, số SQL có thể giảm, nhưng trên cold cache hoặc keys mới, N+1 vẫn tồn tại. Fetch join, batch fetching hoặc DTO projection là những quyết định fetch plan độc lập với L2.

**Cache không nên là cách duy nhất để sửa một query plan sai.**

## 8. Bộ nhớ đệm kết quả truy vấn: lưu kết quả của một câu query

L2 entity cache trả lời: “đã có state của Product ID 10 chưa?”. Query result cache trả lời: “đã có **kết quả của truy vấn này với bộ tham số này** chưa?”.

Ví dụ một query:

~~~java
List<Product> products = em.createQuery(
        """
        select p from Product p
        where p.status = :status
        order by p.id
        """,
        Product.class
    )
    .setParameter("status", ProductStatus.ACTIVE)
    .getResultList();
~~~

Ngay cả khi Product ID 10, 11, 12 đều có trong L2, Hibernate vẫn có thể phải chạy query SQL để biết **những Product IDs nào hiện thỏa status ACTIVE và thứ tự của chúng**. Entity cache không tự cung cấp phép lọc/query result.

Nếu bật query result cache và đánh dấu query là cacheable, Hibernate có thể tái sử dụng tập kết quả đã được tính:

~~~text
Query:
  status = ACTIVE, sort = id ASC
  -> cached result: [10, 11, 12, 20, ...]

Lần chạy lại cùng query/parameters và cache entry còn hợp lệ:
  -> query result cache hit
  -> có thể không cần chạy SELECT tìm IDs nữa
~~~

### 8.1. Query cache không tự bật cho mọi query

Trong Hibernate 6.x có thể cho phép query caching qua cấu hình:

~~~properties
hibernate.cache.use_query_cache=true
~~~

Sau đó **từng query** cần được đánh dấu cacheable theo API Hibernate hoặc hint tương ứng:

~~~java
import org.hibernate.query.Query;
import org.hibernate.Session;

Session session = em.unwrap(Session.class);

List<Product> products = session.createQuery(
        "from Product p where p.status = :status order by p.id",
        Product.class
    )
    .setParameter("status", ProductStatus.ACTIVE)
    .setCacheable(true)
    .getResultList();
~~~

Một cách khác bằng Hibernate-specific query hint khi sử dụng JPA API:

~~~java
List<Product> products = em.createQuery(
        "select p from Product p where p.status = :status",
        Product.class
    )
    .setParameter("status", ProductStatus.ACTIVE)
    .setHint("org.hibernate.cacheable", true)
    .getResultList();
~~~

Tên hint là Hibernate-specific, không được chuẩn Jakarta Persistence bảo đảm trên mọi provider. Đừng nghĩ bật `hibernate.cache.use_query_cache=true` là Hibernate tự cache kết quả mọi truy vấn bất kể đánh dấu.

### 8.2. Cache key phụ thuộc query và tham số

Hai lần gọi query với `status=ACTIVE` và `status=DRAFT` là hai trường hợp khác nhau:

~~~java
.setParameter("status", ProductStatus.ACTIVE)
~~~

so với:

~~~java
.setParameter("status", ProductStatus.DRAFT)
~~~

Query cache phải phân biệt chúng. Các yếu tố ảnh hưởng cache key còn có query text/shape, pagination, filters và những context liên quan provider/tenant. Không tự suy ra bằng cách hash riêng chuỗi HQL trong ứng dụng; Hibernate quản lý cache key theo semantics của nó.

### 8.3. Query cache không nhất thiết chứa nguyên entity objects

Với query trả entity, Hibernate query cache thường lưu **định danh/kết quả logic** (và metadata cần thiết), không đơn giản đóng băng toàn bộ mutable entity graph thành một danh sách Java object chia sẻ.

Khi query cache hit:

1. Hibernate xác định kết quả query đã được cache.
2. Để trả entity, nó vẫn cần state của từng entity ID.
3. State có thể đến từ L1, L2 hoặc phải đọc database.
4. Entity trả về vẫn thuộc persistence context hiện tại theo identity semantics.

Vì thế **query cache hit không đồng nghĩa không có bất kỳ SELECT nào**. Nếu entity state không được cache và chưa managed, Hibernate có thể cần SQL để load entities theo IDs.

Đây là lý do query result caching thường hiệu quả hơn khi các entity result phù hợp cũng có chiến lược L2 cache, hoặc query trả scalar/DTO ổn định theo provider support.

### 8.4. Query cache và scalar/DTO results

Một query như:

~~~java
List<String> names = session.createQuery(
        "select p.name from Product p where p.status = :status",
        String.class
    )
    .setParameter("status", ProductStatus.ACTIVE)
    .setCacheable(true)
    .getResultList();
~~~

có thể cache những giá trị kết quả tương ứng theo Hibernate query cache support. Với aggregate, scalar, constructor projection, tuple hoặc native query, mức hỗ trợ và caching behavior phụ thuộc query/result mapping và version. Cần xác nhận cách cache hoạt động trong integration thực tế thay vì coi mọi result shape có cùng cơ chế.

### 8.5. Có thể gắn query vào region riêng

Hibernate query API có cách chỉ định cache region, ví dụ:

~~~java
List<Product> products = session.createQuery(
        "from Product p where p.status = :status",
        Product.class
    )
    .setParameter("status", ProductStatus.ACTIVE)
    .setCacheable(true)
    .setCacheRegion("catalog.activeProducts")
    .getResultList();
~~~

Region riêng cho phép cấu hình giới hạn memory, expiration và theo dõi metrics theo nhóm query. Region name không làm tăng tính đúng đắn của dữ liệu; invalidation vẫn phải bảo đảm phù hợp với những tables/entities mà query phụ thuộc.

## 9. Cache kết quả truy vấn phải bị invalidation khi dữ liệu đổi

Nếu query cache lưu danh sách IDs `[10, 11, 12]` cho trạng thái ACTIVE, nhưng Product 12 vừa chuyển sang DRAFT, một kết quả cache cũ sẽ sai nếu được dùng vô hạn.

Hibernate dùng cơ chế theo dõi thời điểm cập nhật của các query spaces/tables phụ thuộc để quyết định một cached query result còn hợp lệ hay không. Khi Hibernate quản lý thay đổi phù hợp, query cache có thể bị đánh dấu stale hoặc invalidated.

Điều cần nhớ:

- Query result cache **không phải snapshot vĩnh viễn**.
- Một UPDATE/INSERT/DELETE liên quan có thể làm cached results không còn hợp lệ.
- Việc cache key giống nhau không đủ để bảo đảm cache hit được dùng.
- Đồng bộ/invalidation có overhead; với tables ghi liên tục, hit rate có thể rất thấp.
- Native SQL hoặc write trực tiếp từ hệ thống bên ngoài cần được xử lý đặc biệt để không làm cache stale.

### 9.1. Vì sao query cache không phải lựa chọn tốt cho mọi bảng?

Giả sử query liệt kê danh sách đơn hàng gần đây trên bảng `orders` thay đổi mỗi giây. Mỗi lần update order, cached query liên quan có thể phải được invalidated. Nếu cache bị invalidated trước lần reuse tiếp theo, nó chỉ tốn memory và chi phí quản lý mà hầu như không giảm query.

Query cache thường đáng cân nhắc với:

- Danh sách tham chiếu ổn định.
- Bộ lọc ít thay đổi và được gọi lặp lại rất nhiều.
- Kết quả query có kích thước vừa phải.
- Tables có tần suất ghi thấp hơn tần suất đọc.
- Có thể đo được hit ratio đáng kể và latency thực giảm.

Không nên bật query cache cho toàn bộ repository chỉ vì một vài query hot.

### 9.2. External updates là rủi ro thực tế

Nếu một ứng dụng khác cập nhật database bằng JDBC, batch job hoặc trực tiếp SQL mà Hibernate không được thông báo, L2/query cache của Hibernate có thể không nhận được invalidation phù hợp. Có thể cần:

- Evict các entity/collection/query regions liên quan.
- Cơ chế event-driven invalidation hoặc cache provider cluster invalidation.
- TTL/hard expiration được thiết kế phù hợp.
- Quản lý write-through/outbox/event consistency theo kiến trúc.
- Tránh cache dữ liệu bị thay đổi thường xuyên bởi hệ thống ngoài.

TTL chỉ giới hạn thời gian dữ liệu có thể cũ trong một số mô hình; TTL **không tạo transaction consistency** hay thay thế DB constraints.

## 10. Query-plan cache khác query result cache

Cùng có chữ “query cache”, nhưng có thể nói tới **hai thứ hoàn toàn khác**:

| Loại | Lưu gì? | Tác dụng | Có làm SELECT biến mất? |
| --- | --- | --- | --- |
| Hibernate **query-plan cache** | Biểu diễn/plan đã xử lý của HQL/JPQL để tái sử dụng | Giảm parse/compile/resolve query | Không |
| Hibernate **query result cache** | Kết quả của query với parameters/context | Có thể bỏ thực thi query result SQL khi cache valid | Có thể, nhưng entity loads vẫn tùy L1/L2 |
| DBMS **execution-plan cache** | Execution plans/statement metadata của DB server | Giảm tối ưu hóa lại cùng SQL | Không |
| JDBC/driver **prepared-statement cache** | Prepared statement handles/metadata theo connection/driver | Giảm prepare overhead | Không |

Ví dụ chạy:

~~~java
em.createQuery(
        "select p from Product p where p.status = :status",
        Product.class
    )
    .setParameter("status", ProductStatus.ACTIVE)
    .getResultList();
~~~

nhiều lần có thể tận dụng query-plan cache dù **query result cache tắt**. Hibernate không phải parse HQL từ đầu cho mỗi lần tương đương nếu plan cache hit, nhưng database vẫn có thể thực thi SELECT và trả rows.

Không dùng metrics “query plan cache hit” để kết luận rằng dữ liệu được lấy từ L2 hay query result cache.

## 11. Bộ kết nối (Connection Pool): không phải bộ nhớ đệm dữ liệu

“Bộ kết nối” trong ngữ cảnh truy cập DB thường là **connection pool**, ví dụ HikariCP. Nó giữ một tập kết nối vật lý tới database để các thao tác JDBC có thể **mượn và trả lại** thay vì liên tục tạo TCP/TLS/session/authentication mới.

### 11.1. Nếu không có pool

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant DB as Database
    App->>DB: Mở connection mới
    DB-->>App: Authentication/session setup
    App->>DB: SELECT Product
    DB-->>App: ResultSet
    App->>DB: Đóng physical connection
    App->>DB: Mở connection mới cho request sau
~~~

Chi phí tạo physical connection có thể đáng kể: socket, handshake, authentication, session setup, driver metadata và các giới hạn connection trên DB server.

### 11.2. Khi dùng pool

~~~mermaid
sequenceDiagram
    participant App as Hibernate / JDBC
    participant Pool as HikariCP Connection Pool
    participant DB as Database
    App->>Pool: getConnection()
    Pool-->>App: Mượn connection hiện có
    App->>DB: SELECT Product
    DB-->>App: ResultSet
    App->>Pool: close() logical handle
    Note over Pool: Connection được trả về pool
    App->>Pool: getConnection() lần sau
    Pool-->>App: Tái sử dụng connection phù hợp
~~~

Khi ứng dụng đóng handle được mượn từ `DataSource`, pool thường giữ physical connection lại cho lần mượn kế tiếp. Đóng `EntityManager`/`Session` không phải lời khẳng định physical DB connection bị hủy; Hibernate có thể đã mượn/trả connection ở nhiều điểm tùy connection handling mode và transaction lifecycle.

**Pool lưu connection objects/resources, không lưu rows, entity state hay tập kết quả của HQL.**

### 11.3. Ví dụ HikariCP trong Spring Boot

~~~properties
spring.datasource.hikari.maximum-pool-size=20
spring.datasource.hikari.minimum-idle=5
spring.datasource.hikari.connection-timeout=30000
~~~

Ý nghĩa khái quát:

- `maximum-pool-size`: giới hạn số connection có thể quản lý cùng lúc trong pool.
- `minimum-idle`: mục tiêu tối thiểu số connection rảnh, tùy mode/cấu hình của pool.
- `connection-timeout`: tối đa thời gian chờ mượn connection trước khi báo timeout (đơn vị milliseconds với HikariCP).

Đây là ví dụ cấu hình HikariCP khi Spring Boot đang sử dụng pool này; không phải property của Hibernate L1/L2. Pool size cần dựa trên concurrency, database connection limit, transaction duration và workload. Tăng pool lên gấp đôi không nhất thiết làm throughput tăng nếu bottleneck là CPU/I/O/locks ở database.

### 11.4. Pool có “hit/miss” tương tự L2 không?

Không nên dùng từ hit/miss của entity cache để diễn giải pool. Các chỉ số pool thường là:

- Active connections.
- Idle connections.
- Total connections.
- Pending/waiting threads.
- Connection acquisition latency.
- Timeout và leak detection.

Một connection được tái sử dụng có thể vẫn thực thi **một SELECT hoàn toàn mới**. Ngược lại, nếu L1 hit khiến không cần SQL, request có thể không phải mượn connection để thực hiện thao tác đó.

### 11.5. Pool và transaction

Transaction giữ connection trong một phần hoặc toàn bộ unit of work tùy Hibernate connection handling và transaction coordinator. Một transaction lâu có thể giữ connection bận, làm pool cạn kiệt dù lượng SQL ít. Vì vậy:

- Giữ transactions ngắn và rõ ràng.
- Tránh I/O mạng/chờ người dùng trong transaction DB.
- Đảm bảo code trả connection qua resource/transaction management.
- Theo dõi acquisition timeouts và pending requests.
- Không nhầm “pool hết connection” với “L2 cache miss”.

Caching tốt có thể gián tiếp giảm SQL workload và áp lực connection pool, nhưng hai cơ chế có **cấu hình, giới hạn và metrics riêng**.

## 12. Database buffer pool là một loại cache khác nữa

DBMS như PostgreSQL, MySQL/InnoDB, SQL Server hoặc Oracle có cơ chế sử dụng bộ nhớ để giữ data/index pages. Ví dụ InnoDB buffer pool lưu database pages để giảm disk reads. PostgreSQL dùng shared buffers và cơ chế OS page cache; từng DBMS có thiết kế khác nhau.

Một SELECT từ Hibernate có thể vẫn đi đủ đường:

~~~text
Hibernate -> JDBC connection -> SQL parse/execute -> DB buffer cache hit
                                                   -> rows trả về ứng dụng
~~~

DB buffer hit nghĩa là database không cần đọc disk page tương ứng, **không có nghĩa Hibernate không phát SQL**.

Vì vậy:

- Hibernate L1 hit: thường không cần SQL để lấy lại managed identity.
- Hibernate L2 hit: có thể không cần SQL để tải entity state.
- Query cache hit: có thể không cần thực thi query result SQL, nhưng entity loads tùy trạng thái.
- Connection pool reuse: SQL vẫn chạy.
- DB buffer hit: SQL vẫn chạy, nhưng ít disk I/O hơn.

Khi đánh giá hiệu năng, cần kết hợp Hibernate metrics, pool metrics và database wait/IO/query plan metrics.

## 13. Một yêu cầu có thể đi qua các cơ chế nào?

### 13.1. Trường hợp A: cùng EntityManager, find cùng ID hai lần

~~~java
Product a = em.find(Product.class, 10L);
Product b = em.find(Product.class, 10L);
~~~

Thông thường:

1. Lần đầu L1 miss, có thể L2 hit/miss.
2. Nếu L2 miss, Hibernate thực thi SQL qua connection pool.
3. Lần hai L1 hit, trả cùng managed instance.
4. Không thể từ kết quả này kết luận L2 đang bật.
5. Query cache không liên quan vì đây là load theo ID, không phải cacheable HQL query result.

### 13.2. Trường hợp B: EntityManager mới, find cùng ID

~~~java
try (EntityManager first = emf.createEntityManager()) {
    first.find(Product.class, 10L);
}

try (EntityManager second = emf.createEntityManager()) {
    second.find(Product.class, 10L);
}
~~~

Ở EntityManager thứ hai, L1 mới rỗng. Nếu Product được cache đúng, L2 có thể hit; nếu L2 tắt/miss, cần SQL. Dù hai lần dùng cùng physical DB connection nhờ pool, điều đó **không giúp tái sử dụng Product row**.

### 13.3. Trường hợp C: chạy cùng HQL query hai lần

~~~java
List<Product> first = em.createQuery(
        "from Product p where p.status = :status",
        Product.class
    )
    .setParameter("status", ProductStatus.ACTIVE)
    .getResultList();

List<Product> second = em.createQuery(
        "from Product p where p.status = :status",
        Product.class
    )
    .setParameter("status", ProductStatus.ACTIVE)
    .getResultList();
~~~

Nếu query cache tắt:

- HQL query plan có thể được tái sử dụng.
- SELECT có thể vẫn chạy lần hai.
- Các Product đã managed có thể là cùng instances nhờ L1.

Nếu query cache bật, query được đánh dấu cacheable và cache entry valid, lần sau có thể lấy logical result từ query cache. Nhưng khi trả entities vẫn cần state của những IDs: L1/L2 có thể đáp ứng, hoặc SQL riêng có thể xảy ra tùy loading path.

### 13.4. Trường hợp D: request có connection pool đang ấm

~~~text
Pool có 10 connections sẵn sàng.
Một request mới mượn connection.
Hibernate chạy SELECT chưa từng chạy.
Database trả 500 rows.
Request trả connection cho pool.
~~~

Connection pool hoạt động hiệu quả, nhưng **không có bằng chứng nào về L1/L2/query cache hit**. Thậm chí request có thể vẫn chậm vì query full scan.

## 14. Bảng tình huống đối chiếu

| Tình huống | L1 | L2 | Query result cache | Connection pool |
| --- | --- | --- | --- | --- |
| `find` cùng ID hai lần trong một EntityManager | Có thể hit ngay lần 2 | Có thể không cần tra lần 2 | Không liên quan | Chỉ cần nếu phát SQL |
| `find` cùng ID ở hai EntityManager khác nhau | L1 mới mỗi lần | Có thể phục vụ lần 2 | Không liên quan | Có thể tái sử dụng connection |
| Cùng HQL query chạy lại, không đánh dấu cacheable | Giữ managed instances | Có thể hỗ trợ entity loads | Không có query cache hit | Tái sử dụng connection nếu cần SQL |
| Cùng HQL query cacheable, parameters giống nhau | Giữ entity instance trong session | Hỗ trợ load entity state | Có thể hit nếu entry hợp lệ | Có thể không cần connection cho query result |
| Query parameter khác | Identity map vẫn theo ID | Entity cache theo ID | Cache key khác, thường cần entry khác | Không liên quan tới query key |
| Update entity managed trong transaction | Theo dõi thay đổi | Có invalidation/update phù hợp strategy | Có thể invalidated | Connection dùng cho UPDATE |
| Native SQL ngoài Hibernate thay đổi DB | Có thể stale | Có thể stale | Có thể stale | Chỉ tái sử dụng connection, không đồng bộ cache |
| Pool bị cạn connections | L1 không tự giải quyết | L2/query hit có thể giảm một phần nhu cầu SQL | Có thể giảm DB calls nếu hit | Cần xử lý capacity/transaction leaks |
| L1 clear | Xóa managed state trong context | Không tự xóa L2 | Không tự xóa query cache | Không đóng toàn bộ pool |
| Evict L2 Product region | Không tự detach entity đã managed | Evict state chung | Không nhất thiết evict mọi query result | Không ảnh hưởng pool |
| Database restart | L1 trong tiến trình vẫn có thể tồn tại | Tùy process/provider | Tùy provider/invalidation | Pool phải khôi phục connections |
| DB buffer cache hit | Không suy ra | Không suy ra | Không suy ra | SQL vẫn đi qua connection |

Những từ “có thể” có chủ ý: cache hit còn phụ thuộc mapping, loading path, provider, cấu hình, transaction và cache entry còn hợp lệ.

## 15. Cache invalidation: ai chịu trách nhiệm?

Một cache chỉ hữu ích khi dữ liệu vừa **được tái sử dụng** vừa **không sai so với hợp đồng nhất quán**. Các cơ chế có trách nhiệm khác nhau.

### 15.1. L1

Hibernate quản lý entity state trong phạm vi persistence context. Khi cập nhật qua chính managed entity, L1 nhìn thấy thay đổi local. Nếu dữ liệu đổi từ bên ngoài, L1 có thể stale. Biện pháp: refresh, clear, transaction scope mới, isolation/locking phù hợp.

### 15.2. L2

Hibernate và cache provider phối hợp theo entity/collection region, cache strategy và transaction. Cập nhật ORM bình thường có cơ chế invalidation/update theo strategy; cập nhật native/bulk/external có thể yêu cầu kiểm tra đồng bộ/eviction riêng. Đừng giả định mọi external write được Hibernate biết.

### 15.3. Query cache

Query result cache phụ thuộc invalidation của những query spaces/tables liên quan. Nếu dữ liệu nguồn thay đổi liên tục, nhiều cached results sớm hết giá trị. Nếu hệ thống ngoài cập nhật DB, có thể cần cơ chế invalidate query cache và L2 liên quan.

### 15.4. Connection pool

Connection pool không cache row values, nên không có “invalidation bản ghi” tương tự. Nó quản lý vòng đời connection, health checks, idle eviction, max lifetime và phục hồi sau lỗi DB/network. Một connection trong pool có thể giữ session-level state tùy driver/DBMS, vì thế pool phải reset trạng thái cần thiết trước khi giao connection cho request khác; không dùng session variables tùy ý mà không đảm bảo cleanup.

## 16. Evict đúng tầng

### 16.1. Evict entity khỏi L2 bằng JPA cache API

~~~java
Cache cache = entityManagerFactory.getCache();

// Loại bỏ cache entry của Product ID 10 nếu được cache.
cache.evict(Product.class, 10L);

// Loại bỏ vùng cache cho toàn bộ Product entity.
cache.evict(Product.class);

// Loại bỏ tất cả entity cache entries do JPA Cache API quản lý.
cache.evictAll();
~~~

Import `jakarta.persistence.Cache`. `EntityManagerFactory.getCache()` truy cập shared cache theo JPA. Cách eviction ảnh hưởng các regions khác (collection/query caches) tùy provider; không nên coi `cache.evictAll()` là một lệnh “reset toàn bộ mọi cache và pool” theo nghĩa đen.

**L1 trong các EntityManager đang mở không tự động bị detach** chỉ vì có một L2 eviction. Những managed objects đó vẫn có thể mang state đã tải trước.

### 16.2. Evict query regions bằng Hibernate

Hibernate `SessionFactory` cung cấp API cache provider-specific/ORM-specific cho các vùng cache, ví dụ truy cập `SessionFactory.getCache()` và các thao tác evict query regions theo version:

~~~java
SessionFactory sf = emf.unwrap(SessionFactory.class);

// Ví dụ API Hibernate; kiểm tra method chính xác theo version.
sf.getCache().evictQueryRegions();
~~~

Snippet yêu cầu import `org.hibernate.SessionFactory`. Khi điều tra tính nhất quán, cần xác định region nào được evict và có query cache/region tương ứng thật hay không. Đừng liên tục evict toàn bộ cache trên mỗi request; như vậy cache không còn tác dụng.

### 16.3. Pool không dùng Cache.evict

Muốn chỉnh connection pool, sử dụng cấu hình/API của `DataSource`/HikariCP (pool sizing, max lifetime, idle timeout, metrics). JPA Cache API không quản lý connection pool.

## 17. Transaction và cache consistency

Cache không thay thế các tính chất ACID của database:

- **Atomicity:** một transaction ghi thành công hoặc rollback theo DB semantics.
- **Isolation:** mức nhìn thấy thay đổi giữa các transactions.
- **Durability:** thay đổi commit được lưu bền vững.
- **Constraints:** PK, FK, UNIQUE, CHECK, v.v. bảo vệ invariants.

### 17.1. Optimistic locking vẫn cần DB version

Product dùng:

~~~java
@Version
private long version;
~~~

Khi Product được cập nhật, Hibernate có thể dùng version để phát hiện lost update. L2 cache `READ_WRITE` hỗ trợ quản lý cache state theo provider semantics, nhưng không tự thay thế `@Version` hay DB lock. Cache có thể bị evict bất kỳ lúc nào; logic chống cập nhật đè nhau phải đúng cả khi cache miss.

### 17.2. Cache và multi-instance deployment

Nếu có ba application instances, mỗi instance có `SessionFactory` và local cache provider riêng:

~~~text
Instance A: L2 cache riêng
Instance B: L2 cache riêng
Instance C: L2 cache riêng
Database: chung
~~~

Việc A cập nhật Product không đương nhiên khiến B/C xóa cache entry nếu provider không có cơ chế đồng bộ cluster/invalidation. Một distributed cache/invalidation channel có thể giải quyết vấn đề phù hợp, nhưng phải kiểm tra network partitions, TTL, update ordering và transaction consistency.

**Không coi L2 local cache là distributed cache chỉ vì tất cả instances dùng chung database.**

### 17.3. Multi-tenancy

Cache keys phải phân biệt đúng tenant/context theo cơ chế multi-tenancy của Hibernate/provider. Query result cache còn phải phân biệt filters/parameters và security scope. Dù Hibernate có cơ chế tenant-aware keys trong cấu hình phù hợp, ứng dụng vẫn phải đảm bảo authorization predicates và không đưa dữ liệu của tenant này sang tenant khác trong DTO/application cache tự viết.

Cache correctness và access control là hai yêu cầu riêng.

## 18. Cấu hình đầy đủ: ví dụ Spring Boot + Hibernate 6 + HikariCP

Một file cấu hình có thể chứa các nhóm properties độc lập:

~~~properties
# 1) JDBC connection pool (Spring Boot / HikariCP)
spring.datasource.hikari.maximum-pool-size=20
spring.datasource.hikari.minimum-idle=5
spring.datasource.hikari.connection-timeout=30000

# 2) Hibernate statistics (quan sát trong dev/test)
spring.jpa.properties.hibernate.generate_statistics=true

# 3) Hibernate L2 cache (cần hibernate-jcache và JCache provider phù hợp)
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.cache.region.factory_class=org.hibernate.cache.jcache.internal.JCacheRegionFactory

# 4) Hibernate query result cache (chỉ bật nếu có use case phù hợp)
spring.jpa.properties.hibernate.cache.use_query_cache=true
~~~

Điều kiện để chạy được thực tế:

- `hibernate-core` và `hibernate-jcache` đồng bộ version.
- Có một JCache provider được Hibernate nhận biết và regions/config tương thích.
- Entity cần cache được khai báo theo JPA/Hibernate shared-cache policy.
- Query muốn cache được đánh dấu cacheable.
- HikariCP là DataSource pool đang sử dụng; nếu project dùng pool khác thì properties sẽ khác.
- Không nhầm stats logger/cấu hình cache với việc bảo đảm DB performance.

### 18.1. Một ví dụ service

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.Session;
import org.hibernate.query.Query;

public class CatalogService {
    private final EntityManagerFactory emf;

    public CatalogService(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public Product loadById(Long productId) {
        try (EntityManager em = emf.createEntityManager()) {
            return em.find(Product.class, productId);
        }
    }

    public List<Product> loadActiveProducts() {
        try (EntityManager em = emf.createEntityManager()) {
            Session session = em.unwrap(Session.class);
            Query<Product> query = session.createQuery(
                    "from Product p where p.status = :status " +
                    "order by p.id",
                    Product.class
            );
            query.setParameter("status", ProductStatus.ACTIVE);
            query.setCacheable(true);
            return query.getResultList();
        }
    }
}
~~~

Các collections/associations LAZY của Product có thể vẫn chưa initialized khi EntityManager đóng; nếu service trả entities ra API, mapper bên ngoài context có thể gặp `LazyInitializationException`. Một API nên trả DTO theo fetch plan rõ thay vì dựa vào cache để vô tình khởi tạo graph.

Trong Spring, ranh giới transaction thường được quản lý bằng `@Transactional` và EntityManager được inject; ví dụ trên chỉ minh họa việc mỗi method có persistence context riêng. Các imports như `java.util.List` cần thêm khi sử dụng.

### 18.2. Query cache trên method loadActiveProducts có phải luôn tốt?

Không. Query đọc tất cả ACTIVE Products có thể trả hàng trăm nghìn IDs; status có thể thay đổi thường xuyên. Query result cache khi đó dễ bị invalidated và tốn memory. Phải đo hit rate/result size/latency. Có thể thay bằng query có pagination và filter ổn định, hoặc chỉ cache các tập dữ liệu tham chiếu nhỏ.

## 19. Đo lường đúng loại cache

### 19.1. Hibernate statistics

Có thể bật:

~~~properties
hibernate.generate_statistics=true
~~~

Lấy statistics:

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
        emf.unwrap(SessionFactory.class);

Statistics stats = sessionFactory.getStatistics();

long secondLevelHits = stats.getSecondLevelCacheHitCount();
long secondLevelMisses = stats.getSecondLevelCacheMissCount();
long queryCacheHits = stats.getQueryCacheHitCount();
long queryCacheMisses = stats.getQueryCacheMissCount();
long queriesExecuted = stats.getQueryExecutionCount();
~~~

Các method này minh họa Hibernate 6.x Statistics API. Tùy version/provider còn có counters riêng cho entity fetch, collection fetch, puts, timestamps và regions. `Statistics` có thể ảnh hưởng overhead; trong production cần cân nhắc collection interval và sampling.

### 19.2. L1 không có cùng loại hit counter như L2

L1 identity lookup là một phần persistence context. Một `find` được phục vụ từ L1 có thể làm **không có SQL và không có L2 hit**, nên không thể xác định hiệu quả L1 chỉ từ L2 statistics.

Cách quan sát:

- Bật SQL logging trong môi trường dev/test.
- So sánh lần `find` thứ nhất và thứ hai trong **cùng EntityManager**.
- Tạo EntityManager mới và lặp lại để phân biệt L1 với L2.
- Kiểm soát cache state và transaction boundaries.
- Đọc statistics trước/sau một kịch bản đơn giản thay vì chỉ xem tổng counters của toàn ứng dụng.

### 19.3. SQL logging

Với Hibernate 6:

~~~properties
# Cấu hình logger qua Logback/Log4j/Spring Boot:
# org.hibernate.SQL = DEBUG
# org.hibernate.orm.jdbc.bind = TRACE
~~~

`org.hibernate.SQL` cho biết SQL thật đã phát; `org.hibernate.orm.jdbc.bind` có thể hiển thị bind parameters khi TRACE. Không bật bind parameter logging tràn lan trong production nếu có thông tin cá nhân hoặc secrets.

### 19.4. HikariCP metrics

Các metrics pool thường đi qua Micrometer/Actuator khi Spring Boot tích hợp phù hợp:

- Active, idle, pending và total connections.
- Thời gian chờ mượn connection.
- Timeout khi pool cạn.
- Tần suất tạo/hủy connection và health state.

Đừng so `queryCacheHitCount` với `hikaricp.connections.active` như hai chỉ số cùng loại: một đo tái sử dụng query result, một đo kết nối bận tại thời điểm quan sát.

### 19.5. Database metrics

Để biết DB buffer cache có giúp không, cần DBMS-specific statistics về buffer hits, disk reads, execution time, rows scanned và query plans. Hibernate không thể thay DBMS đo chi phí disk/index cho query.

## 20. Một cách quan sát riêng từng tầng

Để hiểu logic trước khi test tích hợp, có thể lập bốn kịch bản độc lập.

### 20.1. Kịch bản 1 — Chỉ L1

~~~java
try (EntityManager em = emf.createEntityManager()) {
    Product a = em.find(Product.class, 10L);
    Product b = em.find(Product.class, 10L);
    System.out.println(a == b);
}
~~~

Mong đợi: cùng managed instance; thường không phát SELECT thứ hai. Không kết luận gì về L2 từ đây.

### 20.2. Kịch bản 2 — L2 giữa hai contexts

~~~java
try (EntityManager em1 = emf.createEntityManager()) {
    em1.find(Product.class, 10L);
}

try (EntityManager em2 = emf.createEntityManager()) {
    em2.find(Product.class, 10L);
}
~~~

Nếu Product không được cache, lần thứ hai vẫn có thể phát SQL. Nếu L2 đúng mapping/provider và entry tồn tại, lần thứ hai có thể hit L2; xác nhận bằng statistics và SQL. Tránh chạy test này với EntityManager chung hoặc data context đã “ấm” từ setup trước đó.

### 20.3. Kịch bản 3 — Query cache

~~~java
try (EntityManager em = emf.createEntityManager()) {
    Session s = em.unwrap(Session.class);

    s.createQuery(
            "select p from Product p where p.status = :status",
            Product.class
        )
        .setParameter("status", ProductStatus.ACTIVE)
        .setCacheable(true)
        .getResultList();

    s.createQuery(
            "select p from Product p where p.status = :status",
            Product.class
        )
        .setParameter("status", ProductStatus.ACTIVE)
        .setCacheable(true)
        .getResultList();
}
~~~

Cần bật query cache và provider vùng query cache. Nếu cache key giống và entry vẫn valid, có thể thấy query cache hit. Để loại hiệu ứng L1, thử EntityManager riêng cho hai lần; đồng thời theo dõi entity L2 cache và SQL để không nhầm “query cache hit” với “không có bất kỳ SQL nào”.

### 20.4. Kịch bản 4 — Connection pool

Thực thi nhiều transactions ngắn, mỗi transaction có SELECT hoặc UPDATE riêng, và quan sát active/idle connections. Dù pool reuse rất tốt, SQL vẫn được thực thi; điều cần so là connection creation/acquisition overhead và tình trạng chờ pool.

**Không cố chứng minh hiệu quả từng tầng chỉ qua latency tổng**. Latency còn bị chi phối bởi JIT warm-up, database buffer cache, mạng, contention, query plan và số rows.

## 21. Vì sao bật tất cả các cache cùng lúc có thể phản tác dụng?

Có những chi phí thường bị bỏ qua:

- **Memory:** L2 regions và query result sets giữ dữ liệu; cache quá rộng gây pressure lên heap/off-heap.
- **Serialization:** distributed L2 cache có thể cần chuyển đổi entry và truyền qua network.
- **Invalidation:** mỗi transaction ghi có thể phải cập nhật hoặc vô hiệu hóa nhiều vùng.
- **Cache stampede:** nhiều requests cùng miss một key và đồng loạt truy cập DB.
- **Stale data:** external writers hoặc cluster invalidation thiếu gây kết quả cũ.
- **Khó quan sát:** nhiều cơ chế cùng lúc khiến việc quy lỗi hit/miss phức tạp.
- **Session memory:** L1 giữ managed graph lớn trong batch job dài.
- **Pool saturation:** tăng pool vượt năng lực DB tạo thêm cạnh tranh thay vì throughput.
- **Cache key explosion:** query có quá nhiều combination parameters khiến query cache hiếm khi hit.
- **Độ phức tạp vận hành:** regions, TTL, evictions, provider upgrades và compatibility.

Tối ưu nên được đo theo request/business use case: throughput, p95/p99 latency, DB CPU/IO, cache hit ratio, memory và tính nhất quán. Không xem số cache hits cao là đích cuối nếu user latency không cải thiện hoặc dữ liệu sai.

## 22. Sai lầm thường gặp và cách sửa

| Nhầm lẫn | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “`find()` lần hai không có SQL, chắc L2 hit” | L1 trong cùng persistence context đã đủ | Tạo EntityManager mới để quan sát L2 |
| “L2 bật là query JPQL nào cũng không chạy SQL” | Entity cache theo identity, không tự tính tập result | Query cache hoặc query tối ưu vẫn cần thiết |
| “Query cache chứa mọi entity đầy đủ” | Entity results thường dùng IDs + entity load semantics | Có thể cần L1/L2/DB để hydrate entities |
| “Query plan cache hit nên không SELECT” | Cache plan không cache rows | SQL vẫn có thể được thực thi |
| “Pool có 20 connections nên 20 Product được cache” | Pool không lưu row/POJO | Pool lưu kết nối DB |
| “Database buffer cache hit tức Hibernate cache hit” | DB vẫn xử lý SQL qua JDBC | DB buffer cache giảm disk I/O |
| “L2 dùng chung Java instance giữa mọi Sessions” | Mỗi persistence context có identity map riêng | L2 chia sẻ state, không chia sẻ mutable managed object |
| “Cache có TTL nên luôn nhất quán” | TTL chỉ là một giới hạn độ cũ | Transaction/locking/invalidation quyết định consistency |
| “Bật cache giải quyết N+1” | Cold cache vẫn N+1, cache key có thể miss | Sửa fetch plan, batch và projection trước |
| “Bulk JPQL update tự sửa mọi entity trong L1” | Bulk DML bỏ qua đồng bộ state theo dirty checking | Clear/refresh và transaction boundary phù hợp |
| “External SQL chắc chắn invalidate L2/query cache” | Hibernate có thể không biết thay đổi ngoài | Evict/event invalidation hoặc tránh cache |
| “`@Cacheable` tự tạo provider và cache region” | Mapping cần backing region factory/provider | Cấu hình provider và đo thật |
| “Tăng Hikari pool luôn tăng tốc” | Database có giới hạn CPU/I/O/locks/connections | Sizing theo workload và metrics |
| “JPA Cache.evictAll sẽ clear tất cả Sessions” | L1 riêng vẫn giữ managed entities | Evict L2 và clear/close L1 theo nhu cầu |
| “Query cache phù hợp cho danh sách cập nhật mỗi giây” | Invalidation liên tục làm hit ratio thấp | Đo hit/miss; cân nhắc bỏ query cache |

## 23. Chọn tối ưu theo triệu chứng

### 23.1. Một request gọi `find` cùng ID nhiều lần

Kiểm tra scope persistence context trước. Nếu đã dùng cùng EntityManager, L1 thường giải quyết identity reuse. Không cần bật Redis/L2 chỉ để sửa một đoạn code trong cùng transaction.

### 23.2. Nhiều requests đọc cùng lookup data bằng ID

Xem xét L2 cho các entity ít thay đổi. Kiểm tra provider, region policy, consistency và hiệu quả khi deployment có nhiều instances.

### 23.3. Cùng một query danh sách nhỏ được chạy rất nhiều lần

Query result cache có thể hữu ích nếu parameters và result set lặp lại và tables ít ghi. Nếu query trả entities, cân nhắc thêm L2 để tránh loads theo IDs. Nếu query trả DTO/scalar, xem support của Hibernate và đo overhead.

### 23.4. N+1 khi duyệt associations

Chọn fetch join, batch fetching hoặc DTO projection trước. L2 có thể giúp ở warm cache nhưng không làm query plan an toàn dưới mọi dữ liệu mới.

### 23.5. Request chờ quá lâu để mượn connection

Xem Hikari active/pending, transaction duration, connection leaks và DB load. Vấn đề nằm ở connection pool/transaction boundaries, không nhất thiết cần L2 hoặc query cache.

### 23.6. SQL vẫn chạy nhưng DB disk I/O thấp

Có thể DB buffer cache đang giúp, không phải Hibernate cache. Query có thể vẫn tốn CPU, network và row processing.

### 23.7. Dữ liệu đôi khi cũ dù DB đã cập nhật

Xác định lần đọc lấy từ L1, L2 hay query result cache; kiểm tra stale persistence context, external writers, transaction isolation, TTL và invalidation. Đừng vội `evictAll()` trên mỗi request — cần xử lý đúng nguồn không đồng bộ.

## 24. Quy trình thực tế trước khi bật cache

1. **Xác định read pattern.** Truy cập lặp theo entity ID, theo query parameters, hay truy cập nhiều collection?
2. **Định nghĩa freshness contract.** Dữ liệu được phép cũ bao lâu? Có tác vụ nào cần đọc mới tuyệt đối?
3. **Xác định đơn vị tái sử dụng.** L1 managed object, L2 entity state, query results hay DB connection?
4. **Chọn fetch plan đúng trước.** Không dùng cache để che N+1 hoặc collection fetch không phân trang.
5. **Kiểm soát lifecycle.** EntityManager scope/transactions hợp lý; không giữ L1 vô hạn.
6. **Chọn provider/regions cho L2.** Tương thích Hibernate 6/JCache, memory limits, clustered invalidation.
7. **Chỉ cache dữ liệu thật sự hot và phù hợp consistency.** Dùng policy theo entity/collection.
8. **Chỉ đánh dấu query cacheable khi có khả năng reuse cao.** Xem parameters, result size, write frequency.
9. **Sizing connection pool theo database và concurrency.** Không đặt bằng số HTTP threads theo cảm tính.
10. **Đo đúng metrics.** Hibernate L2/query hits, SQL count, Hikari pending, DB buffer/disk/plan.
11. **Kiểm chứng external writes, bulk DML và failover.** Cache invalidation là một phần correctness.
12. **Theo dõi production và có phương án tắt/evict cache.** Cache là tối ưu có thể thay đổi, database vẫn phải là nguồn đúng.

## 25. Bài tập tự kiểm tra

1. Hai lần `em.find(Product.class, 10L)` trong cùng EntityManager trả cùng Java object. Điều đó chứng minh L2 đang bật chưa? Vì sao?
2. Hai EntityManager đọc cùng Product ID. L2 cache có làm hai biến Product trỏ vào cùng instance không?
3. Vì sao L2 entity cache có thể trúng nhiều Product IDs nhưng một HQL query mới vẫn cần SQL?
4. Query result cache lưu gì khác với cache entity? Vì sao query cache hit có thể vẫn cần SQL để tải entities?
5. Hibernate query-plan cache khác query result cache như thế nào?
6. HikariCP connection pool tái sử dụng tài nguyên gì? Nó có giữ ResultSet của query trước không?
7. Vì sao DB buffer cache hit không đồng nghĩa Hibernate không phát SELECT?
8. Khi Product được cập nhật trực tiếp bằng native SQL ở hệ thống khác, L2/query cache có chắc chắn được invalidated không?
9. Bulk JPQL UPDATE có thể gây state nào bị stale trong EntityManager đang mở?
10. Vì sao một cache region READ_ONLY không phù hợp với entity thường xuyên cập nhật?
11. Khi một query list thay đổi dữ liệu liên tục, tại sao query cache hit ratio có thể thấp dù request giống nhau?
12. Với một ứng dụng ba instances và ba local L2 caches, tại sao cần xem xét cluster invalidation?
13. Tăng `maximum-pool-size` có tự giảm số SQL cần thực thi không?
14. Dữ liệu trong L1 thay đổi chưa flush có phải dữ liệu đã commit mà session khác được phép đọc không?
15. Nếu mapper bị N+1 khi duyệt to-one associations, vì sao nên thử fetch plan/batch fetching thay vì chỉ bật L2?

**Gợi ý:** (1) chưa, L1 đủ; (2) không, mỗi context có managed instance riêng; (3) entity state và tập query results là hai việc khác; (4) kết quả logic/IDs khác với entity state; (5) plan cache giúp parse/compile, result cache giúp tránh query execution khi valid; (6) physical connections, không phải rows; (7) SQL vẫn chạy ở DB; (8) không; (9) managed state cũ; (10) caching strategy không hợp mutation; (11) invalidation liên tục; (12) shared DB không tự đồng bộ local caches; (13) không; (14) không; (15) cold cache vẫn N+1.

## 26. Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): persistence context, second-level cache, query cache, fetching và statistics.
- [Hibernate ORM 6.6 Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/): `SessionFactory`, `Cache`, `Statistics`, `Query.setCacheable` và cache concurrency APIs.
- [Hibernate ORM Documentation](https://hibernate.org/orm/documentation/): tài liệu cấu hình cache provider và migration guide theo version.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): EntityManager lifecycle, shared cache, `Cache` và `@Cacheable`.
- [Spring Boot HikariCP configuration](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource, connection pool và cấu hình Hikari trong ứng dụng Spring.
- [HikariCP project](https://github.com/brettwooldridge/HikariCP): connection pool sizing, connection timeout, metrics và pool lifecycle.

**Ghi nhớ cuối cùng:** **L1 giữ managed entities của một persistence context; L2 giữ entity/collection state chia sẻ; query result cache giữ tập kết quả của query theo tham số; connection pool giữ những kết nối DB để tái sử dụng.** Query-plan cache và DB buffer cache còn thuộc các tầng khác. Khi phân tích hiệu năng, luôn hỏi “đang tái sử dụng cái gì, qua ranh giới nào, ai chịu trách nhiệm invalidation?”, rồi kiểm tra SQL, Hibernate cache statistics, pool metrics và database metrics. Cấu hình cache chỉ có ích khi mang lại hiệu năng tốt hơn **mà vẫn giữ dữ liệu đúng và nhất quán với hợp đồng nghiệp vụ**.
