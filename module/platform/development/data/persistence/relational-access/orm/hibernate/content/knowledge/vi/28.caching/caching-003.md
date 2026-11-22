# Vùng đệm thực thể, tập hợp và khóa tự nhiên

Hibernate có thể giảm số lượt truy cập database bằng cách giữ lại một phần dữ liệu đã đọc trong cache. Tuy nhiên, nói “bật cache cho entity” chưa đủ để hiểu hệ thống sẽ lưu cái gì, dùng khóa nào và cache đó có giúp truy vấn liên quan đến collection hoặc natural ID hay không.

Trong **second-level cache (L2 cache)**, Hibernate phân biệt các nhóm vùng đệm (**cache region**) với trách nhiệm khác nhau:

1. **Entity region:** lưu trạng thái persistent của entity để có thể nạp entity theo **primary key** mà không phải luôn thực hiện SQL SELECT.
2. **Collection region:** lưu trạng thái của một collection association theo **collection role và owner key**; với collection chứa entity, dữ liệu chủ yếu giúp biết **những phần tử nào thuộc collection**.
3. **Natural-id region:** lưu phép ánh xạ từ **natural key** (ví dụ SKU, ISBN) sang **primary key** của entity để tối ưu việc tra cứu bằng business key.

Ví dụ:

~~~text
Product có:
    id  = 42
    sku = "BOOK-001"
    name = "Hibernate Fundamentals"
    category_id = 7

Entity region:
    (Product, 42) -> trạng thái name, sku, category_id, ...

Natural-id region:
    (Product, "BOOK-001") -> 42

Collection region:
    (Category.products, 7) -> [42, 51, 89, ...]
~~~

Ba vùng trên không thay thế nhau. Natural-id region **không chứa toàn bộ Product**, collection region **không nhất thiết chứa mọi thuộc tính Product**, và entity region **không tự cho biết danh sách các Product thuộc Category 7**.

Bài học thuộc chương **Bộ nhớ đệm** trong module *Data Persistence Relational Access ORM Hibernate*. Chúng ta sẽ phân biệt ba loại region, tìm hiểu cách đánh dấu cache bằng annotation, cách cache phối hợp với persistence context, chiến lược nhất quán dữ liệu, tình huống cập nhật, vấn đề hiệu năng và cách quan sát hành vi khi triển khai.

Ví dụ dùng Jakarta Persistence (`jakarta.persistence.*`), Hibernate ORM 6.x/7.x và cú pháp SQL thông dụng. Vài API thuộc riêng Hibernate hoặc phụ thuộc cache provider; những điểm này được nêu rõ.

## 1. Cache giải quyết vấn đề gì?

Giả sử 10.000 request cùng cần thông tin một loại sản phẩm phổ biến. Nếu mỗi request có Session riêng và đều truy vấn:

~~~sql
SELECT id, sku, name, category_id
FROM products
WHERE id = 42;
~~~

database phải phục vụ nhiều lượt đọc gần như giống nhau. Với entity được phép lưu trong L2 cache và backend có dữ liệu hợp lệ, một số request có thể tạo entity từ cached state, giảm round trip.

Nhưng một request khác muốn xem danh sách sản phẩm của Category 7:

~~~sql
SELECT id
FROM products
WHERE category_id = 7;
~~~

Ngay cả khi đã cache từng Product theo ID, Hibernate **không tự suy ra tất cả Product thuộc Category 7** từ những entry Product đã từng được lưu. Đó là bài toán membership của collection, hoặc một query result riêng.

Tương tự, một request biết SKU `BOOK-001` nhưng không biết ID 42:

~~~sql
SELECT id
FROM products
WHERE sku = 'BOOK-001';
~~~

Entity region chỉ được tra theo ID, nên có thể cần thêm bước đổi SKU thành ID. Natural-id region phục vụ chính bước này.

**Ba loại region giải quyết ba dạng tra cứu khác nhau:**

| Câu hỏi | Loại region phù hợp |
| --- | --- |
| “Product ID 42 có những thuộc tính gì?” | Entity region |
| “Category ID 7 có những Product nào?” | Collection region |
| “SKU BOOK-001 ứng với Product ID nào?” | Natural-id region |

## 2. Cache tầng một và cache tầng hai không giống nhau

Trước khi bàn về cache region, cần phân biệt hai cấp:

~~~text
Application code
       |
       v
Hibernate Session / EntityManager
       |
       +── First-level cache (Persistence Context)
       |      Entity ID -> managed Java object
       |
       v
SessionFactory / EntityManagerFactory
       |
       +── Second-level cache (shared backend)
       |      Entity regions
       |      Collection regions
       |      Natural-id regions
       |
       v
Database
~~~

### First-level cache (L1)

L1 là persistence context gắn với một `Session` hoặc `EntityManager`. Nó lưu managed entity instance và thông tin tracking cần thiết cho dirty checking.

~~~java
Product first = session.find(Product.class, 42L);
Product second = session.find(Product.class, 42L);

System.out.println(first == second); // true trong cùng Session.
~~~

Trong cùng persistence context, một entity identity được biểu diễn bởi cùng managed instance. Nếu không có yêu cầu refresh đặc biệt, `find` lần hai thường không cần đọc lại trạng thái entity từ database.

L1 có những đặc điểm:

- Tự tồn tại cùng persistence context, không cần `@Cache`.
- Không được chia sẻ trực tiếp giữa các Session.
- Quản lý Java object, identity, dirty checking và vòng đời entity.
- `clear()`/`detach()` có tác động đến managed state trong L1.
- L1 có thể giữ object đã đọc/cập nhật trong transaction ngay cả khi L2 đã bị evict.

### Second-level cache (L2)

L2 được phối hợp bởi `SessionFactory` và backend cache. Nó có thể chia sẻ cached data giữa nhiều Session cùng SessionFactory. Nếu provider hỗ trợ phân tán, dữ liệu có thể được chia sẻ giữa nhiều node theo cấu hình.

Đặc điểm:

- Không tự động cache mọi entity/collection chỉ vì chúng có mapping.
- Cần cấu hình region factory/provider và đánh dấu những entity/collection đủ điều kiện cache.
- Lưu dữ liệu dạng cache entry, **không lưu và chia sẻ cùng managed Java instance** giữa các Session.
- Cache eviction/TTL/concurrency được điều phối ở vùng đệm và cache provider.
- Có rủi ro stale data nếu dữ liệu bị thay đổi ngoài Hibernate.

**L2 hit không có nghĩa hai Session sử dụng cùng object Java.** Mỗi Session vẫn tạo/quản lý entity instance riêng trong L1 của nó.

## 3. “Region” là gì?

Cache region là một namespace logic trong L2 cache. Hibernate dùng tên region để nhóm các cache entry thuộc cùng entity hierarchy, collection role hoặc natural-id mapping.

Một provider có thể cấu hình riêng cho từng region:

- Dung lượng tối đa và chính sách eviction.
- TTL/time-to-idle.
- Memory/disk tier.
- Local cache hay distributed cache.
- Chính sách replication/invalidation giữa node.
- Serialization và object copy.
- Transaction/concurrency support.
- Monitoring, số lần hit/miss/put.

Ví dụ định danh region trong một catalog:

~~~text
catalog.product            entity region cho Product
catalog.category           entity region cho Category
catalog.category.products  collection region cho Category.products
catalog.product-natural    natural-id region cho Product.sku
~~~

Tên ở đây do ứng dụng lựa chọn. Không phải table name bắt buộc và không phải một schema database.

Nếu không chỉ định tên region, Hibernate có quy tắc đặt tên mặc định theo entity name hoặc collection role. Với natural ID, tên mặc định thường có dạng `EntityName##NaturalId`; nên kiểm tra theo phiên bản/provider thực tế.

**Region là ranh giới cache configuration và lookup, không phải bảng dữ liệu mới trong database.**

## 4. Hình dung nội dung ba loại region

Giả sử dữ liệu:

~~~sql
INSERT INTO categories(id, code, name)
VALUES (7, 'JAVA', 'Sách Java');

INSERT INTO products(id, sku, name, category_id)
VALUES
    (42, 'BOOK-001', 'Hibernate Fundamentals', 7),
    (51, 'BOOK-002', 'JPA Patterns', 7),
    (89, 'BOOK-003', 'SQL Design', 7);
~~~

Lược đồ logical cache:

~~~text
Entity: Product
  cache key: (Product, id=42)
  value:    các thuộc tính persistent của Product 42
            (sku, name, category association key, ...)

Entity: Category
  cache key: (Category, id=7)
  value:    code="JAVA", name="Sách Java", ...

Collection: Category.products
  cache key: (role="Category.products", ownerId=7)
  value:    [42, 51, 89]  // membership theo mapping

Natural ID: Product
  cache key: (Product, sku="BOOK-001")
  value:    id=42
~~~

Đây là **mô hình logic**, không phải định dạng binary/serialization mà mọi provider bắt buộc dùng. Provider/version có thể tối ưu cache entry layout khác nhau.

### Vì sao mỗi region cần được đánh giá riêng?

- Entity Product có thể được đọc theo ID rất thường xuyên.
- Category.products có thể thay đổi khi sản phẩm được thêm/gỡ.
- SKU có thể bất biến; natural-id lookup có thể tiết kiệm thêm một SELECT.
- Nếu catalog cập nhật liên tục, chi phí invalidation có thể lớn hơn lợi ích.
- Nếu chỉ có rất ít request truy cập lại cùng dữ liệu, cache có thể chỉ làm tốn thêm memory.

Không chọn cache strategy chỉ dựa vào việc dữ liệu là “bảng master” hay “bảng transaction”. Hãy xem cả **read/write ratio, cardinality, staleness tolerance và access pattern**.

## 5. Cấu hình L2 cache: annotation chưa đủ

Chỉ thêm:

~~~java
@Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
@Entity
public class Product {
    // ...
}
~~~

không bảo đảm ứng dụng đã có backend L2 cache hoạt động.

Hibernate có cơ chế tích hợp cache provider thông qua `RegionFactory` và những thư viện như Hibernate JCache integration. Trong triển khai thực, cần:

1. Thêm dependency phù hợp của Hibernate cache integration.
2. Cung cấp cache backend/provider (ví dụ nhà cung cấp JCache tương thích).
3. Cấu hình RegionFactory và cache manager/provider.
4. Cấu hình cách tạo region, size/TTL và concurrency policy.
5. Đánh dấu entity/collection cần cache.
6. Xác nhận L2 thực sự bật, không vô tình dùng no-op cache region factory.

Ví dụ định hướng Hibernate JCache:

~~~properties
hibernate.cache.use_second_level_cache=true
hibernate.cache.region.factory_class=org.hibernate.cache.jcache.internal.JCacheRegionFactory
hibernate.generate_statistics=true
~~~

Các thuộc tính trên là **khung minh họa**, chưa phải cấu hình chạy độc lập. Cần dependency `hibernate-jcache` và provider thực tế, cùng file config cho JCache manager/regions.

Tên class, cấu hình bootstrapping và các alias setting có thể khác theo Hibernate version. Không sao chép nguyên vào mọi dự án rồi kỳ vọng cache hoạt động.

### Mặc định có cache hay không?

First-level cache luôn gắn với persistence context. Ngược lại, second-level cache cần backend và opt-in theo entity/collection mapping. Hibernate không tự đem mọi hàng trong database đặt vào một L2 cache mặc định.

JPA có `@Cacheable` cho entity, nhưng Hibernate-specific `@Cache` còn thể hiện region và concurrency usage. Cách `@Cacheable` và shared-cache-mode tương tác phụ thuộc cấu hình JPA/provider. Đừng đánh đồng `@Cacheable(true)` với việc đã cấu hình backend.

## 6. Entity region: lưu trạng thái entity theo primary key

Entity region cho phép Hibernate tìm cached state khi ứng dụng nạp một entity theo ID.

~~~java
Product product = session.find(Product.class, 42L);
~~~

Nếu Session chưa có Product 42 ở L1, Hibernate có thể kiểm tra L2 entity region. Khi cache có entry hợp lệ, provider có thể tạo managed Product cho Session hiện tại mà không cần SQL SELECT entity đó.

Pseudo-flow:

~~~mermaid
flowchart TD
    A["session.find(Product, 42)"] --> B{"L1 có entity ID 42?"}
    B -- "Có" --> C["Trả managed object hiện có"]
    B -- "Không" --> D{"Product entity region có state?"}
    D -- "Có" --> E["Hydrate managed entity trong Session"]
    D -- "Không" --> F["SQL SELECT products WHERE id=42"]
    F --> G["Tạo managed entity; có thể put vào L2"]
    E --> H["Trả managed entity"]
    G --> H
~~~

Đây là lược đồ tư duy, không thể hiện mọi trường hợp: lock mode, cache mode, refresh, trạng thái deleted, version, inheritance và cache provider có thể ảnh hưởng đường đi.

### Entity cache không giữ cùng Java object

L2 thường lưu **dehydrated/disassembled persistent state**, không phải reference tới một object managed được chia sẻ cho mọi Session.

Ví dụ Session A và B:

~~~java
Product a;
Product b;

try (Session sessionA = sessionFactory.openSession()) {
    a = sessionA.find(Product.class, 42L);
}

try (Session sessionB = sessionFactory.openSession()) {
    b = sessionB.find(Product.class, 42L);
}

System.out.println(a == b); // Thường là false.
~~~

Hai object có thể đại diện cùng database row nhưng được tạo trong hai Session khác nhau. Chúng không phải cùng instance, dù việc nạp B có thể dùng cached state từ L2.

**Không thay đổi thuộc tính của một object rồi kỳ vọng object managed ở Session khác tự đổi ngay qua shared reference.** Hibernate đồng bộ state thông qua transaction và cache concurrency policy, không chia sẻ managed Java object theo cách đó.

## 7. Khai báo entity cache với `@Cache`

Giả sử Product được đọc thường xuyên và có cập nhật có kiểm soát:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Table(name = "products")
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog.product"
)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    @Column(name = "name", nullable = false)
    private String name;

    @Version
    private long version;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }
}
~~~

Ở đây:

- `@Entity`: Product là persistent entity.
- `@Cache`: cho phép entity tham gia Hibernate L2 cache với chiến lược `READ_WRITE`.
- `region = "catalog.product"`: tên vùng entity cache được lựa chọn tường minh.
- `@Version`: hỗ trợ optimistic locking ở tầng ORM; tương tác cache update phụ thuộc concurrency strategy.
- `@ManyToOne(fetch=LAZY)`: cách tải Category khi đọc Product, độc lập với việc Product có entity cache.

Không cần Hibernate tạo bảng `catalog.product`; region này tồn tại ở cache provider, không ở database.

### Khi nào entity region có ích?

- Nạp lặp lại entity theo ID.
- Entity có read-heavy access pattern.
- Đọc entity không cần lock mạnh trong mọi request.
- Dữ liệu thay đổi không quá thường xuyên.
- Backend cache đủ memory và có eviction phù hợp.
- Nhiều Session trong cùng SessionFactory truy cập cùng các ID.

### Khi nào không nên cache entity?

- Dữ liệu thay đổi liên tục, invalidation thường xuyên.
- Dữ liệu có tính nhạy cảm về freshness và khó phối hợp multi-node.
- Hầu hết ID chỉ được đọc một lần.
- Region có cardinality rất lớn, chi phí memory vượt lợi ích.
- Dữ liệu bị thay đổi ngoài Hibernate quá nhiều nhưng không có cơ chế invalidation.
- Query chủ yếu cần aggregate/projection và không nạp entity theo ID.

## 8. Entity region trong inheritance hierarchy

Hibernate thường quản lý entity cache region theo **entity hierarchy**, không đơn giản một region cho mỗi subclass tùy ý.

Ví dụ:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "accounts"
)
public abstract class Account {
    @Id
    private Long id;
}

@Entity
public class BusinessAccount extends Account {
    // ...
}
~~~

Tùy mapping và phiên bản, `@Cache` được khai báo trên root của inheritance hierarchy. Không mặc định mỗi subclass có region hoàn toàn độc lập rồi đặt cấu hình xung đột.

Điều quan trọng là hiểu entity hierarchy được Hibernate nhận diện như thế nào, cache key có thông tin entity type/identifier ra sao và region nào thực sự được sử dụng.

**Không lấy tên bảng con làm tên region chỉ vì dùng JOINED inheritance.** Region thuộc metadata của entity hierarchy, không phải từng bảng SQL.

## 9. Collection region: lưu membership của association

Entity region trả lời: “Product 42 có những thuộc tính gì?”

Collection region trả lời: “Category 7 có những phần tử nào trong `Category.products`?”

Ví dụ:

~~~java
@Entity
@Table(name = "categories")
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog.category"
)
public class Category {

    @Id
    private Long id;

    @Column(name = "name", nullable = false)
    private String name;

    @OneToMany(
        mappedBy = "category",
        fetch = FetchType.LAZY
    )
    @Cache(
        usage = CacheConcurrencyStrategy.READ_WRITE,
        region = "catalog.category.products"
    )
    private Set<Product> products = new HashSet<>();

    protected Category() {
    }

    public Set<Product> getProducts() {
        return products;
    }
}
~~~

`@Cache` ở class định nghĩa **entity region cho Category**. `@Cache` ở field `products` định nghĩa **collection region cho role Category.products**.

Đây là hai region khác nhau. Chỉ cache Category entity không tự động cache collection products.

### Collection role là gì?

Collection role thường gắn với tên entity sở hữu mapping và tên collection attribute:

~~~text
com.example.catalog.domain.Category.products
~~~

Hibernate dùng role này để định danh một persistent collection mapping. Tên region tường minh có thể là `catalog.category.products`.

Cache key của collection thường liên quan đến **collection role + owner identifier** (kèm thông tin liên quan như tenant nếu mapping multi-tenant). Ví dụ:

~~~text
(role=Category.products, ownerId=7) -> [Product IDs 42, 51, 89]
~~~

Collection cache không phải một dictionary toàn cục `productId -> ProductState`. Nó tập trung vào **cấu trúc/membership** của collection thuộc owner.

## 10. Vì sao collection cache không thay entity cache?

Giả sử Category 7 có ba Product.

~~~text
Collection region:
  Category.products / ownerId=7
      -> [42, 51, 89]

Entity region:
  Product / 42 -> ("BOOK-001", "Hibernate Fundamentals", ...)
  Product / 51 -> ("BOOK-002", "JPA Patterns", ...)
  Product / 89 -> ("BOOK-003", "SQL Design", ...)
~~~

Khi `category.getProducts()` được khởi tạo, Hibernate có thể:

1. Dùng collection region để biết membership/identifier của phần tử.
2. Tra Product entity region để lấy state cho từng Product chưa có trong L1.
3. Nếu Product entity cache miss, phải lấy state từ database.
4. Dựng các managed Product instances trong Session.

Nếu chỉ cache collection mà không cache Product, có thể giảm SQL để xác định membership nhưng vẫn phát SQL nạp Product state. Tùy batch fetching và cache hit rate, điều này có thể không đáng giá.

Ngược lại, chỉ cache Product mà không cache Category.products thì khi truy cập collection Hibernate vẫn có thể cần truy vấn membership bằng SQL, dù trạng thái từng Product đã có trong entity cache.

**Muốn tăng tỷ lệ cache hit cho toàn bộ truy cập collection entity, thường cần đánh giá cả collection region và entity region của các phần tử.**

## 11. Collection cache với `@ElementCollection`

Không phải mọi collection đều chứa entity có primary key riêng. Một entity có thể chứa collection value types:

~~~java
@Entity
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog.product"
)
public class Product {

    @Id
    private Long id;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "product_tags",
        joinColumns = @JoinColumn(name = "product_id")
    )
    @Column(name = "tag")
    @Cache(
        usage = CacheConcurrencyStrategy.READ_WRITE,
        region = "catalog.product.tags"
    )
    private Set<String> tags = new HashSet<>();
}
~~~

Collection `tags` chứa `String` chứ không phải ProductTag entity. Với collection giá trị, cache có thể lưu các **element values** theo collection owner/role, vì không có entity region riêng cho String element.

So sánh:

| Collection | Collection region thường biểu diễn |
| --- | --- |
| `Category.products` (`OneToMany<Product>`) | Identifiers/membership của Product |
| `Article.tags` (`ManyToMany<Tag>`) | Identifiers của Tag và cấu trúc liên kết |
| `Product.tags` (`ElementCollection<String>`) | Element values của collection |
| `Order.addresses` (`ElementCollection<Embeddable>`) | Trạng thái element values theo mapping |
| `List` có `@OrderColumn` | Thông tin collection cùng vị trí/index cần thiết |
| `Map` được map persistent | Các key/value cần thiết theo cấu trúc mapping |

Định dạng lưu cụ thể phụ thuộc Hibernate version và loại persistent collection. Không nên viết logic ứng dụng dựa vào cache entry binary layout.

### Collection fetch strategy vẫn độc lập

~~~java
@ElementCollection(fetch = FetchType.LAZY)
@Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
private Set<String> tags;
~~~

`LAZY` cho biết Hibernate có thể trì hoãn truy cập collection. `@Cache` cho biết khi collection cần load, có thể tra L2 region.

Cache annotation **không biến LAZY thành EAGER**. Và collection không được cache chỉ vì nó được JOIN FETCH ở một truy vấn khác.

## 12. Collection region có thể giúp giảm những SQL nào?

Giả sử Session A đã tải Category 7 và `products`, backend cache giữ collection entry sau các thao tác hợp lệ.

Session B:

~~~java
try (Session session = sessionFactory.openSession()) {
    Category category =
        session.find(Category.class, 7L);

    int size = category.getProducts().size();

    System.out.println(size);
}
~~~

Nếu collection region có entry hợp lệ, Hibernate có thể dùng cached membership và giảm hoặc tránh SELECT cần thiết để tìm các Product thuộc Category 7. Nhưng số SQL chính xác còn phụ thuộc:

- Product entities đã có ở L1 hay L2 chưa.
- Proxy và fetch strategy.
- Collection mapping, extra-lazy behavior hoặc batch fetching.
- Cache concurrency strategy.
- Transaction/cache mode.
- Hibernate version và cache provider.

Không khẳng định “collection cache hit thì toàn bộ truy cập collection bằng 0 SQL” trong mọi trường hợp. Một entry membership có thể vẫn cần nạp từng Product state từ database.

## 13. Khi collection thay đổi, cache region phải được đồng bộ

Giả sử thêm một Product vào Category 7:

~~~java
category.addProduct(product);
~~~

Nếu Hibernate quản lý đầy đủ hai phía quan hệ và transaction commit thành công, Hibernate có cơ chế cập nhật/invalidate collection cache entry bị ảnh hưởng theo mapping và cache strategy.

Nhưng có hai rủi ro:

**Rủi ro 1 — Chỉ cập nhật phía inverse side**

~~~java
category.getProducts().add(product);
// product.setCategory(category) chưa được gọi.
~~~

Nếu `Category.products` dùng `mappedBy="category"`, `Product.category` thường là owning side chứa foreign key. Chỉ thêm vào collection trong Java không bảo đảm FK thực sự thay đổi như mong đợi.

Nên dùng helper giữ hai phía nhất quán:

~~~java
public void addProduct(Product product) {
    products.add(product);
    product.assignCategory(this);
}
~~~

**Rủi ro 2 — Thay đổi ngoài Hibernate**

Một chương trình khác hoặc JDBC trực tiếp chạy:

~~~sql
UPDATE products
SET category_id = 8
WHERE id = 42;
~~~

Hibernate không tự biết collection region của Category 7 và 8 đã thay đổi. Cache membership có thể cũ nếu không được evict/update qua cơ chế tích hợp.

**Collection region đặc biệt nhạy với các thay đổi quan hệ**, không chỉ với cập nhật các field scalar của Product.

## 14. Collection cache không phải query cache

Hai câu hỏi khác nhau:

- “Các phần tử thuộc `Category.products` cho owner ID 7 là gì?” — collection region.
- “Kết quả của truy vấn `select p from Product p where p.price > :price` là những Product nào?” — query result cache.

Ví dụ query:

~~~java
List<Product> products = session.createQuery(
    "select p from Product p where p.price > :minimum",
    Product.class
)
.setParameter("minimum", new BigDecimal("100000"))
.getResultList();
~~~

Chỉ cache Product entity state không tự lưu danh sách ID phù hợp với mọi giá trị `:minimum`.

Nếu bật query cache và đặt query cacheable, Hibernate có thể lưu result-set representation riêng; đây là **một lớp cache khác** với ba region chính của bài.

~~~java
List<Product> products = session.createQuery(
    "select p from Product p where p.price > :minimum",
    Product.class
)
.setParameter("minimum", new BigDecimal("100000"))
.setCacheable(true)
.setCacheRegion("catalog.query.expensive-products")
.getResultList();
~~~

`setCacheable(true)` là API Hibernate-specific; cần bật query cache và có backend phù hợp.

**Không nên bật query cache chỉ vì đã có entity cache.** Query cache có chi phí invalidation và có thể kém hiệu quả với nhiều điều kiện hoặc dữ liệu thường xuyên cập nhật.

## 15. Natural ID: business key không phải primary key

Primary key là định danh chính trong bảng:

~~~text
Product.id = 42
~~~

Natural ID là giá trị có ý nghĩa từ domain và có thể dùng để nhận diện duy nhất một entity:

~~~text
Product.sku = "BOOK-001"
~~~

Ví dụ khác:

- ISBN + edition của một bản sách.
- Mã quốc gia ISO, nếu domain bảo đảm uniqueness.
- Mã nhân viên duy nhất trong một tổ chức.
- Cặp (tenantId, username) trong ứng dụng nhiều tenant.
- Mã nhà cung cấp hoặc mã nghiệp vụ ổn định.

Natural ID cần được thiết kế theo invariant thực tế. Email không phải lúc nào cũng phù hợp làm natural ID bất biến vì người dùng có thể đổi email. Một trường được gọi là `code` cũng không tự nhiên trở thành unique business key nếu database/domain không bảo đảm uniqueness.

Natural ID Hibernate được khai báo bằng:

~~~java
@NaturalId
@Column(name = "sku", unique = true, nullable = false)
private String sku;
~~~

`@NaturalId` là annotation riêng của Hibernate; khác với JPA `@Id` hoặc `@Column(unique=true)`.

### Vì sao vẫn cần primary key?

Natural ID thường có thể dài, thay đổi theo business rule hoặc gồm nhiều thuộc tính. Database schema có thể dùng numeric/UUID primary key ổn định để tạo FK và quản lý entity identity.

Natural ID phục vụ tra cứu theo business key, còn primary key vẫn phục vụ identity và nhiều cơ chế ORM.

## 16. Natural-id region: ánh xạ business key sang primary key

Nếu lookup Product theo SKU:

~~~java
Product product = session
    .bySimpleNaturalId(Product.class)
    .load("BOOK-001");
~~~

Hibernate phải xác định ID từ natural ID:

~~~text
"BOOK-001" -> Product ID 42
~~~

Nếu natural-id cache được bật và có entry hợp lệ:

~~~text
Natural-id region:
  ("BOOK-001") -> 42
~~~

Sau khi biết ID 42, Hibernate có thể tra L1/Entity region để lấy Product state. Nếu entity state chưa được cache, vẫn có thể cần SQL SELECT để tải Product.

Lược đồ:

~~~mermaid
flowchart TD
    A["bySimpleNaturalId(Product).load(BOOK-001)"] --> B{"Session có natural-id resolution?"}
    B -- "Có" --> C["Lấy primary key 42"]
    B -- "Không" --> D{"Natural-id L2 region có mapping?"}
    D -- "Có" --> C
    D -- "Không" --> E["SQL lookup theo SKU / natural key"]
    E --> F["Nhận Product ID 42; có thể cache resolution"]
    F --> C
    C --> G{"Product 42 có state trong L1/L2?"}
    G -- "Có" --> H["Trả managed Product"]
    G -- "Không" --> I["SQL SELECT Product theo ID"]
    I --> H
~~~

Đây là hình dung khái niệm: thứ tự cache lookup thực tế, cách provider tối ưu hóa SQL, trạng thái managed object và cache mode có thể phức tạp hơn.

**Natural-id cache không phải entity cache.** Nó chỉ giúp một bước giải quyết key; để tránh luôn round trip khi đọc entity bằng SKU, entity state cũng nên có khả năng được cache.

## 17. Khai báo `@NaturalIdCache` cùng entity cache

Ví dụ Product với SKU bất biến:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;
import org.hibernate.annotations.NaturalId;
import org.hibernate.annotations.NaturalIdCache;

@Entity
@Table(name = "products")
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog.product"
)
@NaturalIdCache(region = "catalog.product-natural")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NaturalId
    @Column(
        name = "sku",
        nullable = false,
        unique = true,
        updatable = false
    )
    private String sku;

    @Column(name = "name", nullable = false)
    private String name;

    @Version
    private long version;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }
}
~~~

Ý nghĩa:

- `@NaturalId` đánh dấu SKU là natural key của Product.
- `@NaturalIdCache` cho phép natural-id-to-PK resolution tham gia L2 cache.
- `@Cache` cho phép Product entity state tham gia L2 entity region.
- `region` trên mỗi annotation đặt tên **hai region độc lập**.
- `@Version` giúp Hibernate optimistic locking trong luồng cập nhật entity thông thường.
- `updatable=false` là ràng buộc mapping phù hợp với SKU bất biến; database còn nên có unique constraint thực sự.

Trong Hibernate hiện đại, `@NaturalIdCache` không bắt buộc entity phải có `@Cache` về mặt cú pháp, nhưng natural-id cache sẽ ít mang lại lợi ích nếu sau khi resolve ID lại luôn phải SELECT entity state từ database.

### Natural ID bất biến theo mặc định

Với Hibernate `@NaturalId`, default là natural ID **immutable**. Provider có thể phát hiện thay đổi không hợp lệ ở lúc flush.

Nếu business key thực sự có thể đổi, cần khai báo tường minh:

~~~java
@NaturalId(mutable = true)
private String email;
~~~

Không đánh dấu mutable chỉ vì muốn sửa field trong tương lai; nó tạo thêm chi phí đồng bộ/invalidation và thay đổi hợp đồng domain.

## 18. Dùng `bySimpleNaturalId` và `byNaturalId`

Nếu entity có **một** natural-id attribute:

~~~java
Product product = session
    .bySimpleNaturalId(Product.class)
    .load("BOOK-001");
~~~

Đây là lookup đơn giản bằng natural key.

Nếu entity có **nhiều** natural-id attributes, dùng API `byNaturalId` với từng thuộc tính.

Ví dụ:

~~~java
@Entity
@Table(
    name = "application_users",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_user_tenant_username",
        columnNames = {"tenant_id", "username"}
    )
)
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "identity.user"
)
@NaturalIdCache(region = "identity.user-natural")
public class ApplicationUser {

    @Id
    private Long id;

    @NaturalId
    @Column(name = "tenant_id", nullable = false, updatable = false)
    private String tenantId;

    @NaturalId
    @Column(name = "username", nullable = false, updatable = false)
    private String username;

    // ...
}
~~~

Lookup:

~~~java
ApplicationUser user = session
    .byNaturalId(ApplicationUser.class)
    .using("tenantId", tenantId)
    .using("username", username)
    .load();
~~~

Cặp (tenantId, username) là natural ID tổng hợp trong model này. Database unique constraint phải phù hợp invariant nghiệp vụ.

Nếu chỉ tra `username` mà không có tenantId, giá trị không nhất thiết unique. Natural ID chỉ được định nghĩa đúng khi tập thuộc tính tạo một định danh duy nhất theo domain.

### `load()` và `getReference()`

Hibernate có những API natural-id lookup cho trường hợp cần entity đã nạp hoặc chỉ reference. Quy tắc proxy/initialization có thể khác theo version và trạng thái context. Đừng dựa vào `getReference()` để bảo đảm row tồn tại tại thời điểm lấy reference nếu provider có thể trì hoãn SELECT.

## 19. Natural-id resolution cache trong Session và L2 là hai cấp riêng

Ngay cả khi không bật shared natural-id cache, Hibernate có thể giữ một **cross-reference giữa natural ID và entity ID trong Session**.

Ví dụ:

~~~java
try (Session session = sessionFactory.openSession()) {
    Product a = session
        .bySimpleNaturalId(Product.class)
        .load("BOOK-001");

    Product b = session
        .bySimpleNaturalId(Product.class)
        .load("BOOK-001");

    System.out.println(a == b);
}
~~~

Nếu entity đã được managed và natural-id resolution biết mapping, Session có thể tái sử dụng dữ liệu và object instance. Đây là hành vi persistence context/session-local, không chứng minh L2 natural-id region đã có hiệu quả.

Để quan sát shared cache, cần so sánh **nhiều Session khác nhau** trong điều kiện provider/cache được cấu hình phù hợp.

Không nhầm cache key natural ID với Java `Map<String,Product>` tự tạo trong service. Hibernate quản lý resolution theo metadata entity và scope context; cache provider còn cần xử lý concurrency và invalidation.

## 20. Natural ID có thể thay đổi: vấn đề synchronization

Giả sử email được đánh dấu:

~~~java
@NaturalId(mutable = true)
@Column(name = "email", unique = true)
private String email;
~~~

Trong một Session:

~~~java
ApplicationUser user = session
    .bySimpleNaturalId(ApplicationUser.class)
    .load("old@example.test");

user.changeEmail("new@example.test");
~~~

Trước lúc flush, object Java đã có email mới nhưng database có thể vẫn lưu email cũ. Session còn giữ natural-id cross-reference; nếu không kiểm tra đồng bộ, một lookup theo email cũ/mới có thể dùng mapping chưa cập nhật.

Hibernate có cơ chế synchronization cho mutable natural IDs khi thực hiện natural-id lookup. API thông dụng:

~~~java
ApplicationUser result = session
    .bySimpleNaturalId(ApplicationUser.class)
    .setSynchronizationEnabled(true)
    .load("new@example.test");
~~~

Với mutable natural ID, synchronization thường bật mặc định và có chi phí duyệt/kiểm tra managed entities liên quan.

Có thể tắt:

~~~java
.setSynchronizationEnabled(false)
~~~

nhưng chỉ khi chắc chắn không có mutable natural-id changes chưa được đồng bộ trong Session. Nếu tắt sai, lookup có thể trả kết quả cũ hoặc không tìm thấy entity.

### Vì sao mutable natural ID khó cache?

Khi business key đổi:

~~~text
Trước: old@example.test -> User ID 9
Sau:   new@example.test -> User ID 9
~~~

Natural-id region phải bỏ hoặc cập nhật mapping cũ, tạo mapping mới và phối hợp entity region/invalidation theo transaction.

Nếu email được đổi thường xuyên, natural-id cache có thể có churn lớn và performance kém hơn kỳ vọng. Hãy cân nhắc cache dựa vào access pattern thực thay vì mặc định mọi natural ID đều có lợi.

## 21. Collection role và natural ID khác nhau về key

Một lỗi thiết kế là coi collection region cũng là cache “tra theo business key”.

Không đúng:

~~~text
categoryCode = "JAVA"
    => products collection cache trực tiếp tra theo "JAVA"
~~~

Thông thường collection cache dùng **owner entity ID**:

~~~text
(Category.products, ownerId=7) -> [42, 51, 89]
~~~

Nếu ứng dụng chỉ biết `Category.code = "JAVA"`, cần resolve Category bằng ID hoặc natural-id lookup trước, rồi truy cập collection theo owner ID.

Có thể phối hợp:

~~~text
Category natural ID:
    "JAVA" -> 7

Category entity region:
    7 -> Category state

Category.products collection region:
    7 -> [42, 51, 89]

Product entity region:
    42 -> Product state
    51 -> Product state
    89 -> Product state
~~~

Mỗi tầng làm một việc rõ ràng. Nếu thiếu một region, các tầng khác có thể vẫn hoạt động nhưng có thể phải đi database ở một số bước.

## 22. Kịch bản thực tế: mở trang Category theo mã

Giả sử endpoint:

~~~text
GET /categories/JAVA
~~~

cần trả:

~~~text
Category "JAVA"
  - Product BOOK-001
  - Product BOOK-002
  - Product BOOK-003
~~~

Nếu mapping có natural ID của Category, entity region Category, collection region Category.products và entity region Product:

1. Lookup Category theo code `JAVA`.
2. Natural-id region có thể resolve `JAVA -> 7`.
3. Entity region có thể cung cấp state Category 7.
4. Khi truy cập `Category.products`, collection region có thể cung cấp IDs Product.
5. Entity region Product có thể cung cấp state của Product 42, 51, 89.

Khi tất cả vùng có hit hợp lệ, nhiều SQL SELECT có thể được tránh.

Nhưng nếu một trong số đó miss:

- Natural-id miss: có thể phải query theo code.
- Category entity miss: có thể phải query Category theo ID.
- Collection miss: có thể phải query các Product IDs theo category FK.
- Product entity miss: có thể phải query các Product state tương ứng.

**Cache hit ở một region không bảo đảm không có SQL cho toàn bộ endpoint.** Để đánh giá đúng, xem SQL count và cache hit/miss theo cả workflow.

## 23. Cache concurrency strategy là gì?

Hibernate hỗ trợ những chiến lược dùng L2 region khi concurrent sessions đọc và ghi dữ liệu.

| Strategy | Mục tiêu | Tình huống điển hình | Cảnh báo |
| --- | --- | --- | --- |
| `READ_ONLY` | Dữ liệu không thay đổi qua ORM | Danh mục bất biến | Không phù hợp với dữ liệu cập nhật |
| `NONSTRICT_READ_WRITE` | Cho phép một khoảng dữ liệu có thể stale | Dữ liệu hiếm khi đổi, không yêu cầu nhất quán mạnh | Cần chấp nhận stale reads |
| `READ_WRITE` | Điều phối read/write bằng cơ chế lock/soft lock cache | Entity thay đổi nhưng cần cache | Overhead và giới hạn consistency tùy provider |
| `TRANSACTIONAL` | Tích hợp cache với transaction khi provider hỗ trợ | Cần consistency transaction đặc biệt | Yêu cầu backend/transaction manager phù hợp |

Không phải cache provider nào cũng hỗ trợ mọi strategy với cùng semantics. `READ_WRITE` dùng soft-locking/invalidation ở cache không đồng nghĩa với distributed ACID transaction tuyệt đối giữa database và cache trong mọi cấu hình.

### Ví dụ READ_ONLY

~~~java
@Entity
@org.hibernate.annotations.Immutable
@Cache(
    usage = CacheConcurrencyStrategy.READ_ONLY,
    region = "reference.country"
)
public class Country {
    @Id
    private String isoCode;

    private String displayName;
}
~~~

Dữ liệu Country nên được quản lý theo quy trình bất biến hoặc release migration có invalidation tường minh. Nếu database bị sửa từ bên ngoài, cache READ_ONLY có thể stale mãi cho đến khi evict/TTL theo provider.

`@Immutable` là annotation Hibernate khác với `@Cache(READ_ONLY)`; một cái định nghĩa entity mutation semantics, cái kia là concurrency strategy của cache. Kết hợp chúng thể hiện rõ ý định chỉ đọc.

### Ví dụ READ_WRITE

~~~java
@Entity
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog.product"
)
public class Product {
    @Id
    private Long id;

    @Version
    private long version;

    // ...
}
~~~

Product có thể cập nhật trong transaction bình thường. Strategy `READ_WRITE` được thiết kế để giảm nguy cơ stale cache khi ứng dụng Hibernate update entity, nhưng vẫn cần đánh giá transaction behavior và external writes.

### Chọn strategy theo cách dữ liệu đổi

Nếu một dữ liệu cần cập nhật thường xuyên từng giây và mọi request phải thấy giá trị mới, L2 cache có thể không phù hợp dù có strategy mạnh hơn. Có những workload mà database/index/query tối ưu trực tiếp an toàn và nhanh hơn.

## 24. Natural-id region thường gắn với policy của entity

`@NaturalIdCache` chỉ định region để cache natural-id-to-PK mapping. Nó không có tham số `usage = CacheConcurrencyStrategy...` như `@Cache` trên entity.

Cách Hibernate xử lý concurrency/invalidation cho natural-id region dựa trên metadata và cơ chế region provider. Vì vậy không viết:

~~~java
@NaturalIdCache(
    usage = CacheConcurrencyStrategy.READ_WRITE
)
~~~

vì `usage` không phải thuộc tính của `@NaturalIdCache`.

Ví dụ đúng:

~~~java
@Entity
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "identity.user"
)
@NaturalIdCache(region = "identity.user-natural")
class ApplicationUser {
    @Id
    Long id;

    @NaturalId
    String username;
}
~~~

Khi thay đổi natural ID mutable hoặc xóa entity, phải tin cậy các cơ chế update/invalidation đúng của Hibernate/provider, và kiểm thử behavior trong transaction concurrency tương ứng.

## 25. Những gì entity cache thường lưu — và không lưu

Entity L2 cache lưu state persistent ở dạng tối ưu cho ORM. Nó không phải một phiên bản full object graph được serialize tự động với mọi association đã initialized.

Ví dụ Product:

~~~java
@Entity
@Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
public class Product {
    @Id
    Long id;

    String name;

    @ManyToOne(fetch = FetchType.LAZY)
    Category category;

    @OneToMany(mappedBy = "product")
    List<Review> reviews;
}
~~~

Cache state của Product có thể chứa những field scalar và identifier của Category, nhưng **không tự chứa toàn bộ Category object và tất cả Reviews**.

Lý do:

- Associations có lifecycle, fetch plan và region riêng.
- Collection membership có thể thay đổi độc lập.
- Hibernate không thể coi object graph như một khối nguyên tử không thay đổi.
- Việc cache nguyên graph lớn sẽ tăng memory và làm invalidation khó kiểm soát.

Muốn tối ưu màn hình Product + Category + Reviews, cần đánh giá entity regions liên quan, collection region, query fetch plan và DTO projection. Chỉ đặt `@Cache` trên Product chưa đủ.

## 26. L2 cache không tự giải quyết N+1

Giả sử:

~~~java
List<Product> products = session.createQuery(
    "select p from Product p",
    Product.class
).getResultList();

for (Product p : products) {
    System.out.println(p.getCategory().getName());
}
~~~

Nếu Category là LAZY, mỗi Product có thể kích hoạt lazy lookup khi truy cập `getCategory()`.

L2 entity cache của Category có thể giúp nhiều lookup theo ID được đáp ứng từ cache, giảm SQL. Nhưng:

- Khi cache cold, có thể vẫn phát nhiều SQL.
- Nếu mỗi Product thuộc Category khác nhau, số lookup vẫn lớn.
- Query root và collection membership không tự biến thành một JOIN.
- Tăng hit rate bằng cache không sửa cấu trúc truy vấn thiếu fetch plan.

Một lựa chọn có thể là:

~~~java
List<Product> products = session.createQuery(
    "select p from Product p " +
    "left join fetch p.category",
    Product.class
).getResultList();
~~~

Hoặc dùng Entity Graph, DTO projection, batch fetching.

**Cache là công cụ tối ưu reuse dữ liệu; fetch plan là công cụ tối ưu cách lấy association của một use case cụ thể.** Hai cơ chế bổ sung cho nhau chứ không thay thế hoàn toàn.

## 27. Entity graph, collection cache và query cache có thể cùng tham gia

Giả sử một trang cần Category và Products.

~~~java
Category category = session.createQuery(
    "select distinct c from Category c " +
    "left join fetch c.products " +
    "where c.id = :id",
    Category.class
)
.setParameter("id", 7L)
.getSingleResult();
~~~

Vì query yêu cầu JOIN FETCH, Hibernate có thể nạp collection trong query đó. Nếu các entity/collection đủ điều kiện cache và cache mode cho phép, data được nạp có thể đóng góp cache state theo cơ chế provider. Nhưng không nên suy luận rằng mọi query fetch join đều tạo đúng một cache put cho từng entry như nhau.

Một query khác:

~~~java
Category category = session.find(Category.class, 7L);
int size = category.getProducts().size();
~~~

có thể dùng entity region + collection region. Query thứ nhất tối ưu một fetch plan cụ thể; query thứ hai có thể tận dụng cache membership khi truy cập LAZY collection.

Đừng chuyển mọi association sang EAGER chỉ vì region đã cache. Tải nhiều dữ liệu không cần thiết vẫn tốn CPU, memory và object hydration dù phần lớn data đến từ cache.

## 28. Query result cache: phân biệt với ba vùng chính

Một query cache entry thường gắn với query string/parameters/pagination và các metadata cần kiểm tra invalidation. Trong Hibernate hiện đại, layout có thể lưu identifier/shallow representation hoặc dữ liệu fetched đầy đủ tùy cấu hình và provider.

Vì vậy câu khái quát “query cache chỉ lưu ID” có thể không chính xác cho mọi Hibernate version và query shape. Nhưng điểm cốt lõi không đổi:

- Entity region phục vụ identity lookup.
- Collection region phục vụ persistent collection role.
- Natural-id region phục vụ natural-key-to-PK resolution.
- Query cache phục vụ **kết quả của một query cụ thể**.

Query cache còn cần cơ chế tracking/invalidation khi các bảng liên quan thay đổi. Region cho query results và region timestamps/update information có thể riêng biệt.

Ví dụ:

~~~properties
hibernate.cache.use_query_cache=true
~~~

Bật query cache toàn cục không khiến mọi query tự cache. Query thường cần được đánh dấu cacheable.

### Lựa chọn query cache theo trường hợp

Có thể cân nhắc cho query ít đổi điều kiện, lặp lại thường xuyên, dữ liệu update ít. Tránh dùng bừa bãi với query có vô số tổ hợp parameters, frequently changing data hoặc result set rất lớn.

Trong nhiều ứng dụng, entity/natural-id cache đem lợi ích dễ dự đoán hơn query cache. Nhưng điều này vẫn phụ thuộc workload thực tế.

## 29. Eviction: xóa cache entry không phải xóa database row

Hibernate cung cấp API cache để evict entries khi cần.

~~~java
SessionFactory sessionFactory = // ...

sessionFactory.getCache()
    .evictEntityData(Product.class, 42L);
~~~

Thao tác này làm cache entry cho Product 42 không còn được giữ theo vùng entity tương ứng; nó **không DELETE Product row khỏi database**.

Trong JPA:

~~~java
EntityManagerFactory emf = // ...

emf.getCache().evict(Product.class, 42L);
~~~

JPA cache API cho phép evict entity entry. Nhưng quản lý collection region và natural-id region chi tiết thường cần Hibernate-specific API.

### Evict toàn entity region

~~~java
sessionFactory.getCache()
    .evictEntityData(Product.class);
~~~

Thao tác có phạm vi rộng hơn evict một ID, có thể khiến nhiều request tiếp theo phải đọc lại Product state từ database.

### Evict collection region

Với Hibernate, có các API cho collection region theo role:

~~~java
sessionFactory.getCache()
    .evictCollectionData(
        "com.example.catalog.domain.Category.products"
    );
~~~

Đây là minh họa evict collection region. Role phải khớp mapping thực tế; nếu có thể, dùng API/class mapping được Hibernate version hỗ trợ để tránh sai tên.

### Evict natural-id region

~~~java
sessionFactory.getCache()
    .evictNaturalIdData(Product.class);
~~~

Đây là API Hibernate-specific dùng để làm mất natural-id resolution cached cho loại entity tương ứng; version cụ thể có thể hỗ trợ thêm overload theo key.

**Đừng evict Product entity state rồi mặc định collection membership hoặc natural-id mapping liên quan cũng được evict theo cách mình mong muốn.** Khi sửa dữ liệu ngoài Hibernate, phải xác định vùng nào thực sự đã stale.

## 30. Evict L2 không làm Session đang mở tự quên entity

Giả sử:

~~~java
Product product = session.find(Product.class, 42L);

sessionFactory.getCache()
    .evictEntityData(Product.class, 42L);

Product again = session.find(Product.class, 42L);

System.out.println(product == again); // true trong cùng Session.
~~~

Entity vẫn đang managed trong L1. Eviction khỏi L2 không buộc Session tự refresh object đang có.

Để làm mới một managed entity từ database:

~~~java
session.refresh(product);
~~~

Hoặc kết thúc persistence context hiện tại và load bằng Session mới.

### Cẩn thận với pending changes

`session.clear()` detach toàn bộ entities. Nếu có thay đổi chưa flush, clear có thể khiến thay đổi đó không được đồng bộ như mong muốn. `refresh(product)` có thể ghi đè state Java local chưa lưu.

Không dùng clear/refresh như một cách sửa tất cả vấn đề cache mà không hiểu transaction và dirty checking.

## 31. Dữ liệu thay đổi ngoài Hibernate: nguy cơ lớn nhất

L2 cache không tự nhận notification từ mọi writer của database.

Ví dụ một công cụ ETL:

~~~sql
UPDATE products
SET name = 'New Catalog Name'
WHERE id = 42;
~~~

Nếu Product 42 đã cache ở entity region, Hibernate Session mới có thể nhận name cũ từ cache, tùy TTL/concurrency và trạng thái entry.

Nếu ETL đổi SKU:

~~~sql
UPDATE products
SET sku = 'BOOK-NEW'
WHERE id = 42;
~~~

có thể ảnh hưởng đồng thời:

- Entity region Product 42.
- Natural-id region mapping SKU cũ/mới.
- Query cache có kết quả lọc theo SKU.
- Collection region nếu ETL còn thay đổi category FK hoặc các hàng liên kết.

Các chiến lược có thể dùng:

1. Đưa các mutation qua Hibernate khi phù hợp để provider xử lý cache consistency.
2. Evict những region/entries bị ảnh hưởng sau external write.
3. Thiết kế TTL phù hợp khi chấp nhận dữ liệu stale trong thời gian ngắn.
4. Cung cấp integration/event invalidation khi có nhiều writer.
5. Không cache dữ liệu luôn cần freshness mạnh nếu việc invalidation không đáng tin cậy.

**TTL không phải một transaction consistency guarantee.** Nó chỉ giới hạn thời gian sống theo chính sách cache, có thể vẫn đọc dữ liệu cũ trước khi hết hạn.

## 32. SQL bulk update/delete cũng cần chú ý

Một ứng dụng Hibernate có thể dùng HQL bulk mutation:

~~~java
int changed = session.createMutationQuery(
    "update Product p " +
    "set p.name = :name " +
    "where p.category.id = :categoryId"
)
.setParameter("name", "New Name")
.setParameter("categoryId", 7L)
.executeUpdate();
~~~

Bulk HQL update/delete không đi qua lifecycle callback/dirty checking từng entity như sửa managed instance rồi flush.

Hibernate có các cơ chế invalidation cache liên quan đến bulk operations do ORM biết, nhưng không được coi bulk mutation giống hệt entity-by-entity update. Trong cùng Session, managed Product objects có thể vẫn giữ state cũ; có thể cần clear/refresh tùy workflow.

Native JDBC/SQL từ ngoài Hibernate còn khó hơn vì ORM không tự biết query space, affected tables/rows hoặc natural-id changes.

**Sau một thao tác bulk**, đánh giá riêng L1 state, L2 entity/collection/natural-id regions và query cache; không chỉ hỏi “SQL chạy thành công chưa?”.

## 33. Tính nhất quán nhiều node và cache provider

Một ứng dụng có hai node:

~~~text
Node A ── SessionFactory A ── Cache A
   |
   +--------------------------- Database
   |
Node B ── SessionFactory B ── Cache B
~~~

Nếu Cache A và Cache B là local độc lập, việc Node A cập nhật database và cache của nó không tự bảo đảm Node B biết để invalidate cached entry.

Một distributed cache provider hoặc event-based invalidation có thể giải quyết một phần, nhưng cần thiết kế:

- Topology/replication/invalidation.
- Staleness tolerance.
- Network partitions.
- Transaction coordination.
- Failover và cache warmup.
- Schema/version compatibility của serialized entries.
- Cache region naming nhất quán giữa node.
- Upgrade/rolling deployment compatibility.

`READ_WRITE` trong mapping không tự biến hai backend cache local độc lập thành một hệ thống nhất quán toàn cụm.

### Cache không thay thế isolation/locking

Nếu nghiệp vụ có tranh chấp cập nhật số dư hoặc tồn kho cao, cần database constraint, optimistic/pessimistic locking và transaction isolation phù hợp. Cache không được dùng làm nguồn sự thật duy nhất để quyết định phép cập nhật tài chính quan trọng.

## 34. Kích thước và thời gian sống của từng region

Các loại region có access pattern khác nhau:

| Region | Cardinality thường gặp | Chọn TTL/size |
| --- | --- | --- |
| Entity Country/Reference | Nhỏ, dữ liệu hiếm đổi | Có thể lưu lâu nếu có invalidation/migration rõ |
| Entity Product | Trung bình/lớn, có cập nhật | Giới hạn size; cân nhắc churn |
| Collection Category.products | Một entry mỗi owner được tải; value có thể lớn | Cân nhắc collection size và frequency update |
| Natural-ID Product.sku | Gần một entry mỗi Product được tra theo SKU | Cần memory cho key→ID; lợi ích theo lookup rate |
| Query cache Search | Nhiều tổ hợp parameters | Dễ churn; thường TTL/size chặt chẽ hơn |

Không mặc định collection region luôn nhỏ hơn entity region. Một collection khổng lồ có thể tạo entry rất lớn. Ngược lại, natural-id region lưu mapping gọn nhưng có thể có hàng triệu keys.

Các policy như expiry và eviction được cấu hình **ở cache provider**, không chỉ bằng `@Cache(region=...)`.

### Hot keys và cache pressure

Một Category cực phổ biến có thể được đọc nhiều, có lợi cho caching. Nhưng nếu collection liên tục thay đổi khi sản phẩm được thêm/gỡ, cached membership có thể liên tục bị invalidate/put lại.

Hit rate thấp, churn cao và eviction nhiều có thể khiến cache gây overhead thay vì cải thiện performance.

## 35. Đo cache hit/miss bằng Hibernate Statistics

Hibernate cung cấp statistics khi được bật:

~~~properties
hibernate.generate_statistics=true
~~~

Ví dụ:

~~~java
SessionFactory sf = // ...

Statistics stats = sf.getStatistics();
stats.clear();

long beforeHits =
    stats.getSecondLevelCacheHitCount();

long beforeMisses =
    stats.getSecondLevelCacheMissCount();

long beforePuts =
    stats.getSecondLevelCachePutCount();

// Chạy một workflow đọc dữ liệu trong Session mới.

long hitDelta =
    stats.getSecondLevelCacheHitCount() - beforeHits;

long missDelta =
    stats.getSecondLevelCacheMissCount() - beforeMisses;

long putDelta =
    stats.getSecondLevelCachePutCount() - beforePuts;
~~~

Cần import `org.hibernate.stat.Statistics`. Các statistic counters được tính theo SessionFactory và chịu ảnh hưởng hoạt động đồng thời của toàn ứng dụng; trong test cần cô lập workload để diễn giải chính xác.

### Các chỉ số nên quan sát

| Chỉ số | Ý nghĩa |
| --- | --- |
| L2 cache hit | Truy xuất dữ liệu được đáp ứng từ cache |
| L2 cache miss | Không có entry phù hợp; có thể cần query DB |
| L2 cache put | Hibernate đưa data vào cache |
| Query cache hit/miss | Chỉ áp dụng khi query cache được dùng |
| JDBC SQL count | Bao nhiêu SQL thực sự được chạy |
| Entity load/fetch count | Số entity được nạp/fetch theo statistics |
| Collection load/fetch count | Việc tải collection và lazy fetch |
| Cache provider eviction/expiration | Dữ liệu bị đẩy ra/hết hạn |
| Query latency | Tác động thực tế lên request time |
| Memory/network use | Chi phí của cache ngoài SQL savings |

**Một số cache hit nhiều không tự chứng minh endpoint nhanh hơn.** Cần xem độ trễ, cache lookup overhead và memory footprint.

### Cẩn thận với tỉ lệ hit

Công thức thường dùng:

\[
\text{Hit rate} =
\frac{\text{hits}}{\text{hits}+\text{misses}}
\]

Nếu workload có 1 hit và 0 miss, hit rate 100% nhưng dữ liệu quá ít để kết luận cache hiệu quả. Nếu cache được warmup từ trước hoặc trong cùng Session L1 luôn hit, statistics L2 cũng cần được giải thích đúng scope.

## 36. Một kịch bản quan sát ba region qua nhiều Session

Giả sử mapping:

- `Category` có `@NaturalId(code)` và `@NaturalIdCache`.
- `Category` có entity cache.
- `Category.products` có collection cache.
- `Product` có entity cache.

Pseudo-workflow:

~~~java
void openCategoryPage(SessionFactory sessionFactory) {
    try (Session session = sessionFactory.openSession()) {
        Transaction tx = session.beginTransaction();

        try {
            Category category = session
                .bySimpleNaturalId(Category.class)
                .load("JAVA");

            if (category == null) {
                throw new IllegalArgumentException(
                    "Category không tồn tại"
                );
            }

            for (Product product : category.getProducts()) {
                System.out.println(
                    product.getSku() + " - " +
                    product.getName()
                );
            }

            tx.commit();
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        }
    }
}
~~~

Nếu gọi workflow hai lần ở hai Session khác nhau:

~~~java
openCategoryPage(sessionFactory); // Cache cold hoặc chưa warmup.
openCategoryPage(sessionFactory); // Có thể hit các region nếu đủ điều kiện.
~~~

Ở lượt đầu, Hibernate có thể phải truy vấn Category theo code, lấy Product membership và tải Product state; các entry phù hợp có thể được đưa vào L2.

Ở lượt tiếp theo, nếu entries còn hợp lệ và cache provider hoạt động, Hibernate có thể:

- Resolve `JAVA -> categoryId` từ natural-id region.
- Nạp Category state từ entity region.
- Nạp collection membership từ collection region.
- Nạp Product state từ Product entity region.

Kết quả cụ thể còn tùy loading strategy, cache configuration, transaction handling và trạng thái cache. Đo Statistics/SQL để biết hiệu quả thật.

Đây là **một tình huống minh họa**, không phải một bài kiểm thử được chạy trong giai đoạn viết Markdown.

## 37. Cache key và tenant isolation

Với multi-tenancy, hai tenant có thể cùng có Product ID 42 hoặc SKU `BOOK-001` nhưng biểu diễn hai bản ghi khác nhau.

Cache cần phân biệt tenant để không trộn dữ liệu:

~~~text
Tenant A:
  Product 42 -> "A's Product"
  SKU BOOK-001 -> ID 42

Tenant B:
  Product 42 -> "B's Product"
  SKU BOOK-001 -> ID 42
~~~

Hibernate có cơ chế cache key phù hợp với multi-tenancy khi được cấu hình đúng. Nhưng application code không nên tự tạo vùng cache dùng chung theo `sku` hoặc `id` mà quên tenant dimension.

Điều cần đánh giá:

- Chiến lược multi-tenancy của SessionFactory.
- Entity/collection/natural-id cache keys theo provider.
- Region naming và cache isolation.
- Tenant eviction policies.
- SQL direct access không bypass tenant filter/schema.
- Object/DTO cache do ứng dụng tự xây dựng có tenant scope đúng.

**Không dùng cache tối ưu hiệu năng để làm suy yếu ranh giới bảo mật giữa tenant.**

## 38. Cache region và JPA Entity Graph là hai thứ khác nhau

Một `EntityGraph` chỉ rõ association cần fetch trong use case:

~~~java
EntityGraph<Product> graph =
    em.createEntityGraph(Product.class);

graph.addAttributeNodes("category");

Product product = em.find(
    Product.class,
    42L,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
~~~

Nó không tạo region mới hoặc thay đổi concurrency strategy của cache. Nếu Product/Category đủ điều kiện cache, provider có thể tận dụng L2 cho các bước tải; nhưng graph bản thân nó là **fetch plan**, không phải cache policy.

Tương tự:

~~~jpql
select p
from Product p
join fetch p.category
~~~

là yêu cầu tải Category cùng Product trong query, không phải chỉ thị “hãy đặt cả hai vào cùng một cache entry”.

Ba quyết định phải tách riêng:

1. **Fetch plan:** use case cần dữ liệu liên quan nào?
2. **Cache eligibility:** entity/collection/natural ID có đáng cache không?
3. **Cache consistency:** read/write/TTL/invalidation hoạt động thế nào?

## 39. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Thêm `@Cache` nhưng vẫn SELECT mọi lần | Chưa cấu hình backend, L2 tắt, entry miss | RegionFactory, provider, statistics |
| `find` lần hai trong một Session không có SQL | L1 hit, không nhất thiết L2 | Thử bằng Session khác |
| Cache Product nhưng tải Category.products vẫn SELECT | Entity cache không chứa collection membership | `@Cache` trên collection role |
| Cache collection nhưng vẫn SELECT nhiều Product | Product entity region chưa cache hoặc miss | Caching của phần tử, fetch/batch |
| Natural-id lookup vẫn SELECT theo SKU | Thiếu `@NaturalIdCache`/region miss/provider | Mapping và stats |
| Natural-id hit nhưng vẫn SELECT Product theo ID | Natural-id cache chỉ có key→PK | Entity cache Product |
| Bật `@NaturalIdCache` mà không cache entity | Bước lookup có thể nhanh hơn, state vẫn tải DB | Cân nhắc `@Cache` entity |
| Cache trả Product name cũ sau ETL | External JDBC write không invalidation | Evict/TTL/event strategy |
| Cache collection bị cũ khi đổi FK | Collection membership chưa được invalidated | Owning side và external changes |
| READ_ONLY cache gây lỗi khi update | Entity không thật sự bất biến | Chọn READ_WRITE hoặc bỏ cache |
| Cache hit rate thấp dù nhiều entries | High churn hoặc query ít reuse ID | Xem access pattern, TTL/size |
| L2 hit nhưng API vẫn N+1 | Fetch plan/lazy loading không tối ưu | JOIN FETCH, batch fetching, DTO |
| `session.clear()` rồi mất pending changes | Clear detach các managed entities | Flush trước nếu hợp lệ |
| Evict L2 nhưng `find` vẫn trả object cũ | Object còn trong L1 | Refresh/new Session |
| Mọi node thấy dữ liệu khác nhau | Local caches không đồng bộ | Distributed invalidation/topology |
| Query cache không hoạt động | Chưa bật `use_query_cache` hoặc query không cacheable | Config và query flags |
| Natural ID mutable đổi nhưng lookup sai | Cross-reference chưa đồng bộ hoặc sync disabled | Mutable natural-id synchronization |
| Cache region quá lớn | Không có eviction/TTL/size phù hợp | Cache provider config |
| Data nhiều tenant bị trộn | Cache key hoặc app cache thiếu tenant | Tenant isolation design |
| `@Cacheable` có nhưng không có backend | JPA eligibility không tự tạo provider | SharedCacheMode/RegionFactory |

## 40. Cách chọn region theo domain

### Danh mục Country — dữ liệu gần như bất biến

~~~java
@Entity
@Immutable
@Cache(
    usage = CacheConcurrencyStrategy.READ_ONLY,
    region = "reference.country"
)
public class Country {
    @Id
    String isoCode;

    String name;
}
~~~

READ_ONLY có thể phù hợp khi hệ thống chỉ thay đổi Country theo quy trình deployment/migration và có cách xóa cache đúng lúc.

### Product — được đọc nhiều, đôi lúc cập nhật

~~~java
@Entity
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog.product"
)
@NaturalIdCache(region = "catalog.product-natural")
public class Product {
    @Id
    Long id;

    @NaturalId
    String sku;

    @Version
    long version;
}
~~~

Entity region giúp ID lookup. Natural-id region giúp SKU lookup. Cần xem TTL và invalidation theo tần suất chỉnh sửa.

### Category.products — collection membership

~~~java
@OneToMany(mappedBy = "category")
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog.category.products"
)
private Set<Product> products;
~~~

Nếu collection membership được xem nhiều và thay đổi ít, region có thể hữu ích. Nhưng nếu collection gồm hàng chục nghìn sản phẩm và thường xuyên thay đổi, caching membership có thể làm nặng memory/invalidation.

### InventoryBalance — dữ liệu thay đổi liên tục

Một entity biểu diễn số lượng tồn kho thay đổi từng giây có thể không phù hợp L2 nếu độ tươi dữ liệu quan trọng và invalidation rất thường xuyên.

Thay vì mặc định bật READ_WRITE, hãy xem workload, database locking/versioning, query và consistency requirements.

## 41. Bài tập tình huống

**Bài 1 — Hai Session đọc cùng Product ID.**

Session A đọc Product 42, đóng. Session B đọc Product 42. L2 entity region có thể giúp gì?

**Đáp án:** Nếu Product cacheable và region có entry hợp lệ, Session B có thể hydrate Product state mà không cần SELECT entity đó. Hai Session không dùng cùng Java object.

**Bài 2 — Một Session gọi `find` hai lần.**

Có thể kết luận L2 hit không?

**Đáp án:** Không. L1 persistence context đã có thể phục vụ lần gọi thứ hai; cần nhiều Session để quan sát L2 riêng.

**Bài 3 — Category entity đã cache, nhưng products chưa cache.**

Lần truy cập `category.getProducts()` có thể cần SQL không?

**Đáp án:** Có. Entity region Category không tự chứa collection membership.

**Bài 4 — Collection region chứa Product IDs.**

Nếu Product entity region chưa có state, có chắc không phát SQL khi duyệt collection không?

**Đáp án:** Không. Hibernate có thể vẫn phải load Product attributes theo ID.

**Bài 5 — Lookup Product bằng SKU.**

Region nào xử lý `"BOOK-001" -> 42`?

**Đáp án:** Natural-id region, không phải entity region.

**Bài 6 — Natural-id cache hit nhưng Product entity cache miss.**

Điều gì có thể xảy ra?

**Đáp án:** Hibernate biết primary key nhưng vẫn có thể SELECT Product state từ database.

**Bài 7 — SKU đổi mỗi ngày.**

Có nên cache natural ID bất biến?

**Đáp án:** Nếu SKU thực sự có thể đổi, mapping phải phản ánh mutable natural ID hoặc chọn business key khác. Cache natural ID mutable có thêm chi phí invalidation/synchronization; không mặc định có lợi.

**Bài 8 — External JDBC UPDATE Product.name.**

Hibernate L2 có tự biết không?

**Đáp án:** Không được bảo đảm. Cần cache eviction/invalidation/TTL hoặc đưa mutation qua ORM.

**Bài 9 — Chỉ evict entity L2 nhưng Session đang mở vẫn trả Product cũ.**

Vì sao?

**Đáp án:** Product đang managed trong L1. Evict L2 không làm refresh instance đó.

**Bài 10 — Bật query cache cho mọi query.**

Có phải luôn nhanh hơn không?

**Đáp án:** Không. Query cache có key/invalidations riêng, tốn memory và thường kém hiệu quả với nhiều tổ hợp tham số hoặc data thường cập nhật.

**Bài 11 — READ_ONLY region cho entity được sửa thường xuyên.**

Rủi ro gì?

**Đáp án:** Không đúng concurrency strategy, có thể lỗi hoặc dữ liệu stale. Dùng policy phù hợp hoặc không cache.

**Bài 12 — L2 cache và N+1.**

Có phải entity cache giúp hết N+1 không?

**Đáp án:** Cache có thể giảm SQL khi hit, nhưng query shape vẫn có nhiều lazy lookups; cần fetch plan/batch loading.

**Bài 13 — Product trong Category bị chuyển sang Category khác bằng SQL ngoài ứng dụng.**

Region nào có thể stale?

**Đáp án:** Product entity region và collection memberships của Category cũ/mới; query cache cũng có thể stale nếu đã cache kết quả phụ thuộc.

**Bài 14 — Hai tenant dùng chung SKU.**

Natural-id cache được phép chỉ key theo SKU không?

**Đáp án:** Không nếu vậy làm trộn tenant. Cần cache key/isolation đúng theo multi-tenancy configuration.

**Bài 15 — Cache hit rate 95% nhưng memory gấp đôi và request vẫn chậm.**

Có nên giữ cache chỉ vì hit rate cao?

**Đáp án:** Không. Cần đo latency, cache overhead, GC, DB query count và memory pressure; tối ưu theo tổng chi phí.

## 42. Quy trình quyết định cache region

~~~mermaid
flowchart TD
    A["Ứng dụng muốn giảm database reads"] --> B{"Tầng L1 hay L2?"}
    B -- "Trong một Session" --> C["L1 đã có sẵn; xem entity lifecycle"]
    B -- "Nhiều Session" --> D{"Mẫu truy cập là gì?"}
    D -- "Theo primary key" --> E["Entity region"]
    D -- "Theo collection owner" --> F["Collection region"]
    D -- "Theo business/natural key" --> G["Natural-id region + entity region"]
    D -- "Theo query và parameters" --> H["Cân nhắc query cache riêng"]
    E --> I{"Dữ liệu thường bị update không?"}
    F --> I
    G --> I
    H --> I
    I -- "Ít đổi" --> J["READ_ONLY/READ_WRITE theo domain"]
    I -- "Thường đổi" --> K["Xem churn, consistency và có nên cache"]
    J --> L["Cấu hình backend, TTL, size và region"]
    K --> L
    L --> M["Quan sát SQL, hit/miss/put, latency và memory"]
~~~

Sơ đồ không thay thế phân tích hệ thống thực tế. Nó nhấn mạnh rằng **chọn region theo cách truy cập dữ liệu**, rồi mới quyết định concurrency/expiry/invalidation.

## 43. Checklist trước khi bật cache

- **Có thật sự nhiều Session đọc lại cùng dữ liệu không?** Nếu chỉ lặp trong một Session, L1 đã xử lý identity reuse.
- **Cần lookup theo ID, collection owner hay natural key?** Chọn đúng loại region.
- **Entity có bất biến không?** Có thể cân nhắc READ_ONLY nếu thật sự không update.
- **Region entity và collection có phụ thuộc nhau không?** Membership cache có thể cần entity cache của phần tử để giảm tối đa SQL.
- **Natural ID có unique và stable không?** Bảo đảm bằng mapping và database constraint.
- **Cache provider đã hoạt động chưa?** Annotation không đủ.
- **Có writer ngoài Hibernate không?** Phải có invalidation/TTL hợp lý.
- **Có nhiều application node không?** Cần topology/invalidation giữa node.
- **Có nhiều tenant không?** Cache key và region isolation phải đúng.
- **Có query cache không?** Đừng nhầm cache entity với cache kết quả query.
- **Có update thường xuyên không?** Churn/invalidation có thể làm cache phản tác dụng.
- **Region có quá lớn không?** Thiết kế max size và eviction.
- **Có dùng SQL bulk/direct JDBC không?** Rà soát L1/L2 và query cache stale.
- **Có theo dõi Statistics/metrics không?** Đo trước-sau.
- **Cache có làm giảm SQL nhưng tăng GC/heap không?** Xem tổng chi phí.
- **Phiên bản Hibernate/provider có hỗ trợ policy định dùng không?** Không mặc định mọi provider tương đương.

## 44. Tổng kết

**Second-level cache của Hibernate không phải một bộ nhớ đệm duy nhất cho toàn bộ object graph.** Nó gồm nhiều **region** với những chức năng chuyên biệt:

- **Entity region:** lưu persistent state theo primary key, hỗ trợ nạp entity theo ID giữa nhiều Session.
- **Collection region:** lưu membership hoặc element values của một persistent collection theo collection role và owner key.
- **Natural-id region:** lưu ánh xạ natural ID → primary key, hỗ trợ tra entity theo business key; thường hiệu quả hơn khi entity state cũng được cache.

Các nguyên tắc quan trọng:

1. **L1 khác L2:** L1 thuộc Session và giữ managed objects; L2 thuộc cache backend chia sẻ ở phạm vi SessionFactory/cụm khi được cấu hình.
2. **Entity cache không tự chứa collection:** cache Product theo ID không tự cache danh sách Product thuộc Category.
3. **Collection cache không thay entity cache:** membership hit có thể vẫn cần SELECT để tải entity state.
4. **Natural-id cache chỉ resolve key:** biết SKU → ID chưa bảo đảm entity state có trong cache.
5. **`@Cache` và `@NaturalIdCache` là Hibernate-specific:** cần provider hoạt động và region policy phù hợp.
6. **READ_ONLY/READ_WRITE/NONSTRICT/TRANSACTIONAL khác nhau:** chọn theo mô hình cập nhật và consistency requirement.
7. **L2 không tự phát hiện mọi external write:** JDBC trực tiếp, ETL và ứng dụng khác cần cơ chế invalidation rõ ràng.
8. **Evict L2 không tự refresh L1:** Session đang giữ managed object có thể vẫn đọc state cũ.
9. **Query cache là lớp khác:** không nhầm kết quả query với entity, collection và natural ID regions.
10. **Cache không tự sửa N+1 hoặc fetch plan thiếu tối ưu:** Entity Graph, JOIN FETCH, batch fetching và projection vẫn quan trọng.
11. **Đo hiệu quả bằng cache statistics lẫn SQL/latency/memory:** cache hit rate đơn lẻ chưa đủ.
12. **Natural key và tenant isolation phải đúng:** cache không thay database constraints và authorization.

Một thiết kế tốt không chỉ hỏi **“có bật cache hay không?”** mà hỏi rõ **“mỗi request tra dữ liệu bằng khóa nào, region nào chứa thông tin đó, khi dữ liệu đổi ai làm cache invalidation và nếu cache miss thì hệ thống còn bao nhiêu SQL?”**. Trả lời được những câu hỏi ấy giúp Hibernate cache tăng hiệu năng mà không làm dữ liệu khó kiểm soát.

## Tài liệu tham khảo

- [Hibernate ORM 7.2 User Guide — Caching](https://docs.hibernate.org/orm/7.2/userguide/html_single/)
- [Hibernate ORM 7.2 — A Short Guide: Second-level cache và caching by natural id](https://docs.hibernate.org/orm/7.2/introduction/html_single/)
- [Hibernate ORM 6.6 User Guide — Natural ID, mutable natural IDs và cache](https://docs.hibernate.org/orm/6.6/userguide/html_single/)
- [Hibernate ORM 7.0 Javadocs — NaturalIdCache](https://docs.hibernate.org/orm/7.0/javadocs/org/hibernate/annotations/NaturalIdCache.html)
- [Hibernate ORM 6.6 Javadocs — Cache API](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Cache.html)
