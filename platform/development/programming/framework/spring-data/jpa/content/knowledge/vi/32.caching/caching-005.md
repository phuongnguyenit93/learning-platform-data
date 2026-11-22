# Làm mất hiệu lực cache khi cập nhật từ JPA và hệ thống khác

## 1. Bài toán: dữ liệu đã đổi nhưng ứng dụng vẫn đọc giá trị cũ

Trong Spring Data JPA, một bản ghi có thể được đọc qua nhiều tầng cache. Khi dữ liệu được sửa bằng Hibernate/JPA, bằng truy vấn bulk, bằng JDBC trực tiếp hoặc bởi một ứng dụng khác cùng truy cập database, **không có một lệnh xóa cache duy nhất tự động bao phủ mọi tầng**. Nếu không xác định đúng tầng cần làm mất hiệu lực (*invalidate/evict*), API có thể trả về giá, trạng thái hoặc tồn kho đã lỗi thời.

Ví dụ một dịch vụ catalog có sản phẩm `Product(id=42, priceCents=100000)`:

1. API đọc giá qua Spring Cache và lưu `productViews[42] = 100000`. Nếu bật second-level cache của Hibernate, trạng thái entity `Product#42` cũng có thể được lưu ở đó.
2. Hệ thống quản trị hoặc một tiến trình đồng bộ bên ngoài đổi giá trong database thành `120000`.
3. API gọi lại `getProduct(42)`. Nếu Spring Cache còn key `42`, hàm đọc JPA thậm chí **không được gọi**. Xóa Spring Cache mà Hibernate vẫn giữ entity cũ ở L2 cũng có thể tiếp tục trả lại `100000`.
4. Chỉ khi các cache chịu ảnh hưởng được làm mất hiệu lực hoặc hết hạn, lần đọc mới có cơ hội nạp `120000` từ nguồn dữ liệu hiện hành.

Cần phân biệt hai vấn đề: **bảo đảm giao dịch ghi đã commit thành công** và **đảm bảo mọi đường đọc không còn dữ liệu cũ**. Một sự kiện cập nhật có thể đến muộn, thất lạc hoặc đến trong lúc người khác đang nạp cache. Vì vậy, thiết kế phải nêu rõ mức nhất quán cần đạt: đồng bộ nghiêm ngặt, gần thời gian thực, hay chấp nhận cũ trong một TTL ngắn.

## 2. Xác định chính xác cache đang dùng

| Tầng | Phạm vi | Nơi có thể có dữ liệu cũ | Cơ chế xử lý chính |
| --- | --- | --- | --- |
| **JPA first-level cache (L1/persistence context)** | Mỗi `EntityManager`/transaction | Entity đã managed trong một persistence context đang mở | `refresh(entity)`, `clear()` hoặc kết thúc context và tạo context mới |
| **JPA/Hibernate second-level cache (L2)** | `EntityManagerFactory`/`SessionFactory` và nhà cung cấp cache cấu hình | Entity hoặc collection được phép cache qua nhiều context | `EntityManagerFactory.getCache().evict(...)` cho entity; API provider cho collection/region |
| **Hibernate query result cache** | Query được đánh dấu cacheable và các cache region | Danh sách ID/kết quả truy vấn theo tham số | Cơ chế invalidation của Hibernate hoặc chủ động evict query region khi thay đổi ngoài tầm Hibernate |
| **Spring Cache** | Tầng method qua `@Cacheable`, có thể in-memory/Caffeine/Redis | DTO, kết quả service, trang tìm kiếm, thống kê | `@CacheEvict`/`CacheManager`, đúng tên cache và đúng key |
| **Cache hoặc bản sao bên ngoài** | Redis do dịch vụ khác quản lý, CDN, search index, client | Kết quả API/index/giá trị sao chép | Quy ước sự kiện, API invalidation/reindex hoặc TTL riêng |

Các điểm dễ nhầm:

- **L1 luôn gắn với một persistence context**, nên `entityManager.clear()` chỉ tách các managed entity của context đó; không xóa Spring Cache, L2, query cache hay dữ liệu trên node khác. `clear()` còn làm mất các thay đổi chưa flush của context đó.
- **L2 không mặc nhiên bật cho mọi entity.** Hiệu lực thực tế của `jakarta.persistence.Cacheable` phụ thuộc shared-cache mode, cấu hình Hibernate và cache provider. Chỉ gọi `getCache().evict()` không có nghĩa trước đó L2 đang hoạt động.
- **Query cache khác cache câu SQL/query plan.** Hibernate query result cache thường cần bật riêng và opt-in cho từng truy vấn; cache query plan không phải kho chứa kết quả dữ liệu nghiệp vụ.
- **`@Cacheable` có hai nghĩa tùy import:** `org.springframework.cache.annotation.Cacheable` cache kết quả phương thức; `jakarta.persistence.Cacheable` đánh dấu entity đủ điều kiện tham gia L2. Một annotation không tự điều khiển cache của tầng kia.
- **Spring Cache key phụ thuộc phương thức và cấu hình key generator.** Key ID `42L` trong `productViews` khác chuỗi `"42"`, khác key tìm kiếm theo bộ lọc, và khác key mà một dịch vụ bên ngoài tự đặt.

Trong bài này, *invalidate* là đánh dấu/xóa bản cache cũ để lần đọc sau tải lại; *evict* là thao tác loại entry/region cụ thể. *Refresh* là tải lại dữ liệu và thường chỉ có tác dụng đối với entity/đường đọc liên quan.

## 3. Khi nguồn ghi là JPA, ORM tự lo được gì?

Với cập nhật entity managed thông thường:

```java
@Transactional
public void changePrice(Long id, long priceCents) {
    Product p = repository.findById(id).orElseThrow();
    p.changePrice(priceCents);
    // Hibernate dirty checking; transaction manager flush/commit khi kết thúc.
}
```

Đây là đoạn method minh họa bên trong một Spring service; các class hoàn chỉnh xuất hiện ở phần sau. Hibernate biết entity bị thay đổi và xử lý đồng bộ cache mà **chính Hibernate quản lý**, theo cấu hình concurrency/cache region. Với truy vấn Hibernate cacheable, cơ chế update timestamp có thể làm kết quả truy vấn cũ không còn hợp lệ khi Hibernate nhận biết các bảng đã sửa.

Nhưng Hibernate **không thể tự cập nhật mọi cache Spring** có chứa DTO được tạo từ entity. Chẳng hạn `@Cacheable("productViews")` đặt ở service có thể tiếp tục trả giá cũ dù bản ghi JPA đã commit. Tương tự, Hibernate không tự hiểu cache của gateway, hệ thống tìm kiếm, hay HTTP client.

Lưu ý quan trọng về thời điểm: thay đổi entity trong transaction chưa đồng nghĩa database đã commit. Nếu loại bỏ cache quá sớm, một luồng đọc khác có thể nạp lại giá trị **cũ** trước commit và lưu lại trong cache. Nếu transaction rollback, việc loại bỏ cache trước đó cũng là thao tác thừa và có thể gây tải lại không cần thiết.

### 3.1. Vì sao `@CacheEvict` trên method `@Transactional` chưa chắc là “sau commit”?

Mẫu sau trông hợp lý:

```java
@Transactional
@CacheEvict(cacheNames = "productViews", key = "#p0")
public void changePrice(Long id, long priceCents) {
    // Ghi entity...
}
```

`@CacheEvict` mặc định chạy **sau khi method hoàn thành thành công** theo cache advice. Thời điểm đó **không tự bảo đảm database đã commit**, vì thứ tự và phạm vi các AOP advice, transaction lồng nhau hoặc transaction do tầng gọi quản lý có thể khác nhau. `beforeInvocation = true` còn loại key trước khi phương thức thực thi. Không dùng những cơ chế này như cam kết nhất quán sau commit nếu chưa kiểm chứng chính xác cấu hình giao dịch.

Cách rõ ràng cho cập nhật JPA nội bộ là phát sự kiện trong transaction và xử lý invalidation tại `TransactionPhase.AFTER_COMMIT`; với độ tin cậy cao hơn hoặc liên dịch vụ, dùng transactional outbox hay một cơ chế giao nhận có khả năng retry.

## 4. Ví dụ Spring Data JPA: làm mất hiệu lực sau khi commit

Mẫu dưới đây dùng **Java 17+, Spring Boot 3.x, Spring Data JPA, Spring Cache và một database quan hệ**. Các file nằm trong cùng package `demo.cache` của **dự án đã cấu hình Spring Boot**. `spring-boot-starter-data-jpa`, `spring-boot-starter-cache`, JDBC driver và một `CacheManager` phù hợp cần có trong classpath; với test tích hợp dùng thêm `spring-boot-starter-test` và H2. Đây là mã dự án nhiều file, không phải chương trình Java SE chạy độc lập bằng `javac`.

Mục tiêu:

1. `ProductQueryService` đọc JPA và cache DTO theo ID.
2. `ProductCommandService` sửa entity managed trong transaction, phát `ProductChanged`.
3. `ProductCommittedListener` chỉ gọi invalidation sau commit thành công.
4. `ProductCacheInvalidator` xóa **Spring Cache** và entry **JPA L2** liên quan. Nếu L2 không bật, lời gọi JPA cache eviction không có tác dụng phụ.

**`Product.java`**

```java
package demo.cache;

import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(name = "price_cents", nullable = false)
    private long priceCents;

    @Version
    private long version;

    protected Product() {}

    public Product(String name, long priceCents) {
        this.name = name;
        this.priceCents = priceCents;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public long getPriceCents() { return priceCents; }

    public void changePrice(long newPriceCents) {
        if (newPriceCents < 0) {
            throw new IllegalArgumentException("Price must be non-negative");
        }
        this.priceCents = newPriceCents;
    }
}
```

`@Version` giúp phát hiện một số cập nhật cạnh tranh **khi mọi đường ghi tuân thủ cơ chế phiên bản**. Ghi SQL từ hệ thống khác bỏ qua cột `version` có thể phá vỡ bảo vệ đó; phần dưới sẽ xử lý riêng.

**`ProductRepository.java`**

```java
package demo.cache;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
}
```

**`ProductView.java`**

```java
package demo.cache;

public record ProductView(Long id, String name, long priceCents) {
}
```

**`ProductQueryService.java`**

```java
package demo.cache;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductQueryService {
    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productViews", key = "#p0")
    @Transactional(readOnly = true)
    public ProductView byId(Long id) {
        Product p = repository.findById(id).orElseThrow();
        return new ProductView(p.getId(), p.getName(), p.getPriceCents());
    }
}
```

`#p0` là đối số thứ nhất (ID), tránh lệ thuộc tên parameter có được giữ lại sau biên dịch hay không. Phương thức phải được gọi **qua Spring proxy** để `@Cacheable` hoạt động; gọi `this.byId(...)` từ chính class đó thường bỏ qua cache advice trong chế độ proxy mặc định.

**`ProductChanged.java`**

```java
package demo.cache;

public record ProductChanged(Long id) {
}
```

**`ProductCommandService.java`**

```java
package demo.cache;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {
    private final ProductRepository repository;
    private final ApplicationEventPublisher events;

    public ProductCommandService(
            ProductRepository repository,
            ApplicationEventPublisher events
    ) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void changePrice(Long id, long newPriceCents) {
        Product product = repository.findById(id).orElseThrow();
        product.changePrice(newPriceCents);
        events.publishEvent(new ProductChanged(id));
    }
}
```

Sự kiện được phát **bên trong transaction**, lúc này dữ liệu có thể chưa flush/commit. Listener sẽ đăng ký callback theo vòng đời transaction. Nếu transaction rollback, callback `AFTER_COMMIT` sẽ không chạy. Nếu không có transaction đang hoạt động, `@TransactionalEventListener` mặc định không chạy (trừ khi dùng `fallbackExecution = true`, vốn không phù hợp với hợp đồng ví dụ này).

**`ProductCacheInvalidator.java`**

```java
package demo.cache;

import jakarta.persistence.EntityManagerFactory;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;

@Component
public class ProductCacheInvalidator {
    private final CacheManager cacheManager;
    private final EntityManagerFactory entityManagerFactory;

    public ProductCacheInvalidator(
            CacheManager cacheManager,
            EntityManagerFactory entityManagerFactory
    ) {
        this.cacheManager = cacheManager;
        this.entityManagerFactory = entityManagerFactory;
    }

    public void invalidate(Long productId) {
        Cache cache = cacheManager.getCache("productViews");
        if (cache != null) {
            cache.evict(productId);
        }
        entityManagerFactory.getCache().evict(Product.class, productId);
    }
}
```

Lệnh `cache.evict(productId)` chỉ xử lý entry trong Spring Cache `productViews` với key đó. Lệnh `entityManagerFactory.getCache().evict(Product.class, productId)` chỉ nhắm đến **L2 entity cache**. Nó không tự xóa L1 của mọi transaction, query cache của Hibernate, cache collection, hay kết quả tìm kiếm theo nhiều tham số.

**`ProductCommittedListener.java`**

```java
package demo.cache;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductCommittedListener {
    private final ProductCacheInvalidator invalidator;

    public ProductCommittedListener(ProductCacheInvalidator invalidator) {
        this.invalidator = invalidator;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(ProductChanged event) {
        invalidator.invalidate(event.id());
    }
}
```

**`CacheConfiguration.java`**

```java
package demo.cache;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {
}
```

Các class ở trên được Spring quét trong package `demo.cache` hoặc các package con của `@SpringBootApplication`. Với một `CacheManager` in-memory để học/test, cache có hiệu lực trong một JVM. Với Redis hoặc provider khác, cần cấu hình serializer, TTL và phạm vi chia sẻ thích hợp; những lựa chọn đó **không xuất hiện tự động** chỉ nhờ `@EnableCaching`. Nếu tên cache `productViews` bị cấu hình sai, đoạn `cache != null` tránh lỗi null nhưng không đảm bảo invalidation; trong production nên coi cache dự kiến vắng mặt là lỗi cấu hình có thể quan sát.

### 4.1. Dòng thời gian commit

```text
T0  API byId(42) -> cache miss -> JPA load Product#42 -> cache DTO cũ.
T1  CommandService.changePrice(42, 120000) mở transaction.
T2  Entity được sửa, event ProductChanged(42) được publish.
T3  JPA flush; database COMMIT thành công.
T4  AFTER_COMMIT listener gọi invalidator.invalidate(42).
T5  Spring Cache productViews[42] và L2 Product#42 bị evict.
T6  API byId(42) ở lần cache miss tiếp theo nạp lại giá hiện hành.
```

Chuỗi trên giả định callback và eviction thực thi thành công, đúng node/cache, không có đua tranh đặc biệt. **`AFTER_COMMIT` giúp tránh invalidation trước commit nhưng không phải cơ chế gửi sự kiện bền vững**. Nếu process chết ngay sau commit và trước callback, hoặc Redis lỗi trong listener, database vẫn đã commit mà cache có thể còn cũ. Với nhu cầu bắt buộc không mất thông báo, dùng outbox và retry; khi listener thực hiện ghi database sau commit, thường cần một transaction mới (`REQUIRES_NEW`), vì tài nguyên transaction cũ có thể còn gắn với luồng nhưng sẽ không có commit tiếp theo.

## 5. Khi thay đổi đến từ hệ thống ngoài JPA

Giả sử một ứng dụng kho, batch ETL hoặc DBA chạy:

```sql
UPDATE products
SET price_cents = 120000,
    version = version + 1
WHERE id = 42;
```

Đây là SQL minh họa. Hibernate trong ứng dụng catalog không tham gia lệnh SQL này. Vì vậy:

- Persistence context đã nạp `Product#42` vẫn có thể trả entity managed cũ trong vòng đời của nó.
- L2 của Hibernate trên một hay nhiều node có thể tiếp tục giữ bản cũ.
- Hibernate query cache có thể không biết bảng vừa đổi vì update không đi qua Hibernate.
- Spring Cache trả DTO cũ nếu key chưa hết hạn.
- `@Version` có thể giúp phát hiện ghi cạnh tranh nếu mọi writer cập nhật version đúng quy ước, nhưng **không tự phát broadcast invalidation**.

### 5.1. Các cách thông báo đã có thay đổi

| Cách | Dùng khi | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **Đọc/ghi qua một service sở hữu dữ liệu** | Có thể bắt buộc mọi writer đi qua một API chung | Dễ tập trung giao dịch và hợp đồng sự kiện | Các writer truy cập DB trực tiếp vẫn có thể bỏ qua |
| **Transactional outbox** | Chính service ghi DB phát sự kiện nghiệp vụ | Bản ghi dữ liệu và bản ghi outbox commit trong **cùng transaction**; worker chuyển phát lại được | Chỉ bao phủ writer có triển khai outbox; cần relay, retry và dọn dẹp |
| **CDC từ transaction log** | Có nhiều chương trình/legacy job sửa cùng DB | Nhận biết cả thay đổi không qua JPA nếu connector theo dõi đúng bảng và sự kiện commit | Có độ trễ, vận hành phức tạp, cần phân biệt loại thay đổi và xử lý sự kiện trùng/lệch thứ tự |
| **Polling version/timestamp** | Không có broker/CDC, yêu cầu chấp nhận độ trễ | Đơn giản hơn khi tần suất thay đổi thấp | Độ trễ theo chu kỳ; dễ bỏ sót nếu timestamp không được cập nhật tin cậy |
| **TTL ngắn và cache bypass** | Có thể chấp nhận stale trong giới hạn, hoặc trường dữ liệu cần nhất quán mạnh | Giới hạn thời gian tồn tại của entry, có thể tránh cache cho đường đọc quan trọng | TTL không đảm bảo phát hiện ngay; bypass tăng tải DB |

**Outbox không tự bao phủ SQL của một ứng dụng khác** nếu ứng dụng đó không ghi outbox. Khi không kiểm soát writer, lựa chọn thường là CDC trên DB hoặc cơ chế trigger/change stream được quản trị. Event nên xác định rõ entity type, ID, kiểu thay đổi, commit/version khi có, event ID, và nguồn phát; không chuyển bản entity JPA managed làm payload hệ thống.

Một luồng CDC hợp lý:

```text
Writer A (JPA) ----\
                    -> Database commit -> transaction log -> CDC
Writer B (SQL) ----/                            |
                                                v
                                     product-changed event
                                                |
                                                v
                                      invalidate Spring cache
                                      + L2 trên các node phù hợp
                                      + query/list cache phụ thuộc
```

**Sự kiện phải phản ánh trạng thái đã commit**. Xóa cache khi writer mới bắt đầu sửa hoặc khi transaction còn có thể rollback sẽ mở cửa cho cache bị nạp lại bằng dữ liệu cũ.

### 5.2. Bộ tiếp nhận sự kiện bên ngoài nên gọi lại một hàm invalidation

`ProductCacheInvalidator` ở phần 4 cũng là điểm dùng chung cho sự kiện nhận từ broker/CDC:

```java
package demo.cache;

import org.springframework.stereotype.Component;

@Component
public class ExternalProductChangeHandler {
    private final ProductCacheInvalidator invalidator;

    public ExternalProductChangeHandler(ProductCacheInvalidator invalidator) {
        this.invalidator = invalidator;
    }

    public void onCommittedExternalUpdate(Long productId) {
        invalidator.invalidate(productId);
    }
}
```

Đây là **handler được gọi sau khi adapter nhận sự kiện đã commit**, **không phải** một consumer Kafka/RabbitMQ hoàn chỉnh. Việc đăng ký topic, deserialize schema, xác thực nguồn, ack/retry, dead-letter queue và quy tắc phát đến từng node phải được cấu hình ở adapter thực tế. Không có câu lệnh Java nào trong ví dụ tự nhận biết SQL từ ứng dụng khác nếu chưa có kênh thông báo.

Nếu dùng Redis làm cache **chia sẻ** của Spring, việc xóa key Redis là xóa trên namespace chung. Nhưng một event được consumer group giao cho **một** instance chỉ xóa L2 cục bộ của instance đó nếu L2 là cache local. Các instance khác vẫn có thể cũ. Muốn các node cùng invalidate L2 local, cần broadcast/fan-out tới mỗi node, sử dụng provider L2 có cơ chế coherence cluster, hoặc tắt L2 cho thực thể thường bị update bên ngoài. Cấu hình broker consumer group bình thường **không tự đồng nghĩa broadcast cho mọi instance**.

## 6. Phân biệt các API invalidation theo phạm vi

### 6.1. L1: `refresh`, `clear` và transaction mới

```java
// Minh họa bên trong một transaction có EntityManager:
entityManager.refresh(product); // Tải lại trạng thái entity hiện tại.
entityManager.clear();          // Detach toàn bộ entity của context này.
```

`refresh` áp dụng cho entity đang managed và có thể ghi đè thay đổi chưa flush của entity đó. `clear` detach mọi entity của context, nên nếu còn thay đổi chưa flush, chúng có thể bị bỏ lại; không dùng `clear` như một lệnh “sửa cache toàn hệ thống”. Transaction dài và extended persistence context cần chiến lược refresh rõ ràng khi thay đổi từ hệ thống ngoài.

Đối với truy vấn sau sự kiện cập nhật, tạo persistence context/transaction mới giúp loại khả năng L1 đang giữ instance cũ, **nhưng không loại được L2 hay Spring Cache cũ**.

### 6.2. JPA L2: `EntityManagerFactory.getCache()`

```java
entityManagerFactory.getCache().evict(Product.class, 42L);
entityManagerFactory.getCache().evict(Product.class);
entityManagerFactory.getCache().evictAll();
```

Ba lệnh lần lượt nhắm **một entity**, **mọi entity cùng lớp**, **mọi entity trong JPA L2**. `evictAll()` theo hợp đồng Jakarta Persistence chỉ xử lý dữ liệu entity được cache; **không nên coi đây là “xóa mọi cache từ DB đến Redis và query”**. Thường chọn eviction theo ID để giảm tác động lên cache hit rate.

Nếu hệ thống dùng L2 phân tán, kiểm chứng nhà cung cấp cache có đồng bộ trên các node không. `getCache()` từ một instance ứng dụng không thể mặc nhiên làm sạch mọi JVM khác nếu provider sử dụng bộ nhớ local.

### 6.3. Hibernate query cache và collection cache

Jakarta Persistence chỉ cung cấp API cơ bản cho L2 entity. Khi Hibernate có bật query result cache hoặc collection cache, có thể cần API đặc thù:

```java
// Hibernate-specific, chỉ dùng nếu dự án triển khai bằng Hibernate.
org.hibernate.SessionFactory sessionFactory =
        entityManagerFactory.unwrap(org.hibernate.SessionFactory.class);

sessionFactory.getCache().evictQueryRegions(); // Query result regions.
sessionFactory.getCache().evictCollectionData(); // Collection regions.
```

Đoạn trên **cố ý minh họa eviction diện rộng**, không nên gọi cho mỗi thay đổi nhỏ nếu đã xác định được query region hoặc collection role. Hibernate cũng cung cấp `evictQueryRegion("...")` và `evictCollectionData("Entity.collection", ownerId)` khi xác định chính xác mapping. Cache query Hibernate sử dụng metadata cập nhật của các bảng; khi DB đổi bên ngoài mà timestamp nội bộ không được cập nhật, cần cơ chế evict phù hợp. Không dùng `EntityManager.clear()` để thay thế.

Nếu truy vấn không cacheable hoặc query cache không bật, các thao tác query-region không đem lại lợi ích. Cần quan sát thống kê Hibernate và cấu hình thực tế thay vì giả định query cache tồn tại.

### 6.4. Spring Cache: key đơn hay toàn region?

```java
// Đúng khi đã biết khóa của một product:
cacheManager.getCache("productViews").evict(42L);

// Khi không biết các kết quả tìm kiếm nào phụ thuộc vào product,
// có thể buộc tái tạo cả region tìm kiếm:
cacheManager.getCache("productSearch").clear();
```

Đoạn minh họa giả định tên cache tồn tại; mã production nên kiểm tra `getCache(...)` trả null và xử lý cấu hình bất thường. Lựa chọn theo ID hiệu quả khi dữ liệu không có các phụ thuộc phức tạp. Với cache kết quả `search(category, page, sort)`, một sản phẩm thay giá/trạng thái có thể làm thay đổi **nhiều key**, nên xóa mỗi `productViews[42]` là chưa đủ.

Giải pháp cho danh sách/query: ghi rõ dependency của cache, dùng region generation/version, invalidation theo tag/index nếu provider hỗ trợ, hoặc xóa region có chọn lọc. `clear()` toàn region có thể gây cache stampede, phải cân nhắc lưu lượng và cách warm-up. `@CacheEvict(allEntries = true)` cũng theo ngữ nghĩa tương tự đối với một region Spring Cache.

### 6.5. Bảng hành động theo nguồn thay đổi

| Đường ghi | L1 cũ | L2/query Hibernate | Spring Cache/Redis DTO |
| --- | --- | --- | --- |
| Entity managed + commit qua JPA | Context hiện tại quản lý entity; context khác có thể đang giữ instance cũ | Hibernate xử lý những region nó quản lý theo cấu hình; cần xác minh query/collection cụ thể | **Ứng dụng phải chủ động invalidate/refresh** sau commit |
| JPQL/HQL bulk `UPDATE` hoặc `DELETE` | Có thể stale; clear hoặc dùng context mới | Tùy provider/loại query; Hibernate thường có cơ chế xử lý bulk nhưng không thay cho kiểm thử cache liên quan | **Chủ động invalidate** |
| Native SQL/JDBC trong cùng service | Có thể stale | Không nên giả định ORM nhận biết đầy đủ các bảng/region bị sửa | **Chủ động invalidate** |
| SQL do hệ thống khác ghi | Các context đang mở có thể stale | **Không tự nhận biết thay đổi ngoài Hibernate** | **Không tự nhận biết** nếu không có event, polling hoặc TTL |
| Thay đổi data import nhiều bản ghi | Context đang mở có thể stale | Cân nhắc eviction theo region hoặc tái tạo khi số lượng lớn | Cân nhắc region-generation / batch invalidation |

Không biến cột “Hibernate xử lý” thành bảo đảm cho mọi provider và mọi kiểu mapping. Hành vi chính xác còn phụ thuộc phiên bản, second-level cache strategy và cách query được thực thi.

## 7. Update bulk, native SQL và `@Modifying`: điểm dễ bỏ sót

Với Spring Data JPA, có thể viết method cập nhật trực tiếp:

```java
// Thêm method vào interface ProductRepository của phần 4:
@org.springframework.data.jpa.repository.Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@org.springframework.data.jpa.repository.Query(
    "update Product p set p.priceCents = :price where p.id = :id"
)
int updatePriceBulk(
    @org.springframework.data.repository.query.Param("id") Long id,
    @org.springframework.data.repository.query.Param("price") long price
);
```

- `@Modifying` giúp Spring Data xử lý `@Query` như modifying query.
- `flushAutomatically = true` yêu cầu flush persistence context trước khi thực hiện bulk update.
- `clearAutomatically = true` giúp clear persistence context sau query, tránh giữ managed entities đã stale; nó **không xóa Spring Cache hay L2 trên các instance khác**.
- JPQL bulk update thường **bỏ qua cơ chế dirty checking, lifecycle callbacks và optimistic version check của entity trên từng bản ghi**. Ví dụ vừa nêu không tự tăng `@Version`. Nếu cần optimistic locking, phải thiết kế điều kiện/logic cập nhật phiên bản đúng; với một entity đơn lẻ, sửa managed entity thường đơn giản và an toàn hơn.
- Cần gọi method này trong transaction ghi, sau đó invalidate các cache của ứng dụng **khi commit thành công** như với cập nhật managed; không dựa vào `clearAutomatically` như giải pháp toàn bộ.

Với `nativeQuery = true`, JDBC template, stored procedure hoặc ORM session khác, có thể không có đủ thông tin để Hibernate loại mọi cache liên quan. Nếu dùng API đồng bộ query space của Hibernate cho native query, hãy kiểm thử đúng provider/version; cách di động và rõ ràng hơn là chủ động định nghĩa sự kiện thay đổi các aggregate bị ảnh hưởng.

**Ví dụ việc cần tránh:** chạy `UPDATE products SET price_cents = ...` ngoài Hibernate, rồi gọi mỗi `entityManager.clear()` và kỳ vọng API khác thấy giá mới. L1 của một context đã trống, nhưng Spring Cache và L2 có thể vẫn cũ.

## 8. Thứ tự thao tác và lỗi trong môi trường phân tán

### 8.1. Evict trước commit có thể nạp lại dữ liệu cũ

```text
Writer cập nhật product nhưng chưa COMMIT.
Writer EVIC T cache (quá sớm).
Reader thấy cache miss -> đọc giá cũ từ DB -> cache lại.
Writer COMMIT giá mới.
Không có invalidation tiếp -> cache tiếp tục cũ.
```

Vì thế ưu tiên trigger sau commit. Nhưng ngay cả invalidation sau commit vẫn **không loại bỏ hoàn toàn race** giữa những lần đọc đang diễn ra.

### 8.2. Race “stale repopulation” ngay cả khi evict sau commit

```text
Reader R: cache miss, bắt đầu đọc giá 100.
Writer W: commit giá 120.
Writer W: evict key product 42.
Reader R: hoàn tất và đưa giá 100 vừa đọc vào cache.
Đọc tiếp theo: cache có thể lại trả 100.
```

Đây là một rủi ro của mô hình *cache-aside* khi read/write cạnh tranh. TTL rút ngắn thời gian tồn tại của dữ liệu cũ nhưng không tạo nhất quán tức thời. Nếu nghiệp vụ không cho phép đọc cũ (ví dụ quyết định thanh toán/tồn kho có khóa), cân nhắc **bỏ qua cache ở đường đọc/ghi quan trọng**, kiểm tra phiên bản, phối hợp theo key, hoặc thiết kế transaction/locking phù hợp. Tránh tuyên bố “evict sau commit là luôn strong consistency”.

### 8.3. Thông báo đến trễ, trùng hoặc mất

Một hệ thống sự kiện đáng tin cậy cần tối thiểu:

1. **Định danh sự kiện** (`eventId`) và entity/aggregate ID; kèm version/commit sequence nếu có để xử lý thứ tự.
2. **Idempotency:** xóa cùng key nhiều lần về cơ bản an toàn; nếu consumer **ghi đè cache bằng payload sự kiện**, chỉ áp dụng phiên bản mới hơn để tránh sự kiện cũ đảo ngược dữ liệu mới.
3. **Ack sau xử lý thành công** và retry khi cache/broker lỗi; theo dõi dead-letter queue, lag và số lần retry.
4. **Phát sự kiện sau commit** hoặc thông qua outbox/CDC có ranh giới transaction rõ ràng.
5. **Fan-out đúng phạm vi:** cache local của mỗi instance cần thông báo riêng hoặc cluster coherence; consumer group chia việc một-bản-tin-một-worker không tự đạt yêu cầu đó.
6. **Cơ chế giới hạn stale:** TTL, phiên bản key, hoặc disable cache nơi dữ liệu cần tươi hơn khả năng hệ thống truyền sự kiện.
7. **Dễ quan sát:** log có `productId`, event ID, nguồn thay đổi, thời điểm commit/nhận/evict, region và lỗi xử lý, tránh log thông tin nhạy cảm không cần thiết.

Khi callback `AFTER_COMMIT` lỗi, **database đã commit rồi**. Đừng tùy tiện coi exception trả ra là giao dịch đã rollback để tự thử gửi lại lệnh ghi, bởi có thể tạo cập nhật trùng. Outbox tách độ bền của sự kiện khỏi tính sẵn sàng của cache, cho phép worker retry độc lập.

### 8.4. Mô hình versioned cache key

Một phương án chống ghi giá trị cũ vào cùng một key là đưa generation/version vào khóa:

```text
product:42:v17
product:42:v18
```

Khi phiên bản dùng để chọn key tăng lên một cách đáng tin cậy, truy vấn mới không đọc entry của phiên bản trước. Tuy nhiên **bộ xác định “phiên bản mới nhất” cũng phải nhất quán** (database, một generation store được cập nhật có thứ tự, hoặc token phiên bản có hợp đồng rõ). Chỉ đổi key theo timestamp của mỗi instance mà không chia sẻ version không giải quyết được vấn đề. Cần TTL/cleanup để không tích lũy vô hạn các key cũ.

## 9. Kịch bản tích hợp và kiểm thử thực tế

Trước khi chọn chiến lược invalidate, lập **bản đồ dữ liệu và cache**. Ví dụ:

| Dữ liệu thay đổi | Key/region cần xem xét | Writer có thể gây thay đổi |
| --- | --- | --- |
| Giá `Product#42` | Spring `productViews[42]`; JPA L2 `Product#42` | Product service, admin batch, ETL |
| Giá làm thay đổi kết quả tìm kiếm hoặc sort | Spring `productSearch[...]`; query cache đã bật | Cả ba nguồn trên |
| Trạng thái active ảnh hưởng danh sách category | `categoryListings[categoryId]`, query result caches | Catalog service, tích hợp ngoài |
| Dòng order và tổng số lượng | Cache order aggregate/collection và summary DTO | Order service, import SQL |

Không nhất thiết xóa tất cả cache mỗi khi product thay đổi. Xác định **phụ thuộc dữ liệu nào bị tác động**, sau đó chọn ID eviction, region eviction hoặc generation hợp lý. Nếu bảng mapping cập nhật quá rộng và không có đủ dữ liệu để tính key, nên ưu tiên tính đúng trước, sau đó tối ưu phạm vi.

### 9.1. Integration test cho JPA update và external SQL

Với các class `demo.cache` ở phần 4, có thể viết test sau khi cấu hình Spring Boot + H2 + `CacheManager`. Đặt file test trong `src/test/java/demo/cache/ProductCacheIntegrationTest.java`. Mục đích của test là kiểm chứng dữ liệu đã ghi thực sự được nạp lại, không chỉ kiểm tra một Java object trong RAM.

```java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ProductCacheIntegrationTest {
    @Autowired ProductRepository repository;
    @Autowired ProductQueryService reads;
    @Autowired ProductCommandService writes;
    @Autowired ProductCacheInvalidator invalidator;
    @Autowired JdbcTemplate jdbc;

    @Test
    void jpaUpdateInvalidatesAfterCommit() {
        Product p = repository.saveAndFlush(
                new Product("Sản phẩm A", 100_000));
        Long id = p.getId();

        assertThat(reads.byId(id).priceCents()).isEqualTo(100_000);

        writes.changePrice(id, 120_000); // Service @Transactional.
        assertThat(reads.byId(id).priceCents()).isEqualTo(120_000);
    }

    @Test
    void externalSqlNeedsNotificationAndEviction() {
        Product p = repository.saveAndFlush(
                new Product("Sản phẩm B", 100_000));
        Long id = p.getId();

        assertThat(reads.byId(id).priceCents()).isEqualTo(100_000);

        // Mô phỏng writer ngoài JPA, đã commit qua JDBC.
        jdbc.update("""
            UPDATE products
            SET price_cents = ?, version = version + 1
            WHERE id = ?
            """, 150_000, id);

        // Khi cache hit, lời gọi JPA thậm chí không chạy.
        assertThat(reads.byId(id).priceCents()).isEqualTo(100_000);

        // Đây là bước do consumer CDC/outbox/broker thực hiện.
        invalidator.invalidate(id);

        assertThat(reads.byId(id).priceCents()).isEqualTo(150_000);
    }
}
```

Điều kiện để kiểm thử có ý nghĩa: Spring Cache thật sự được bật và phương thức `reads.byId` được gọi qua bean proxy; test **không** đặt `@Transactional` bao quanh cả phương thức kiểm thử khiến transaction rollback mặc định và `AFTER_COMMIT` không kích hoạt; các lệnh ghi dùng một database test; `JdbcTemplate.update` ở test này thực thi ngoài transaction test và được driver/transaction manager commit theo cấu hình mặc định. Nếu dự án cấu hình connection/transaction đặc biệt, cần đảm bảo bước SQL đã commit trước khi gọi invalidation.

Chạy bằng Maven Wrapper nếu dự án cung cấp:

```bash
./mvnw -Dtest=ProductCacheIntegrationTest test
```

Trên Windows dùng `mvnw.cmd -Dtest=ProductCacheIntegrationTest test`; với Gradle dùng task test tương ứng của dự án. Các assertion trên **không xác nhận** query cache Hibernate hoặc cache local của nhiều node, vì cấu hình test cơ bản có thể chỉ bật Spring Cache. Muốn kiểm thử L2, phải thực sự bật provider/region, làm nóng cache, kiểm tra hit/miss rồi đổi DB ngoài ORM và xác nhận eviction. Muốn kiểm thử multi-node, phải chạy hai instance thật với đúng mô hình Redis/L2/event bus.

### 9.2. Các ca kiểm thử nên có khi triển khai production

| Ca | Thực hiện | Kết quả cần quan sát |
| --- | --- | --- |
| Commit qua JPA | Đọc để tạo cache, cập nhật giá rồi commit | Cache cũ bị loại và lần đọc sau nhìn thấy giá mới |
| Rollback | Sửa giá rồi ném lỗi khiến transaction rollback | Không phát invalidation `AFTER_COMMIT`; DB không đổi |
| Bulk JPQL | Làm nóng cache, bulk update và commit | Không còn L1 cũ; Spring Cache và region liên quan được xử lý |
| Writer ngoài | SQL trực tiếp commit rồi gửi change event | Các cache phụ thuộc được evict trên đúng node/namespace |
| Không có event | Cố ý dừng consumer hoặc CDC | TTL/alert/reconciliation hoạt động theo chính sách chấp nhận stale |
| Gửi trùng | Phát lại cùng `eventId` nhiều lần | Consumer idempotent, không xuất hiện lỗi nghiệp vụ |
| Event đảo thứ tự | Vận chuyển phiên bản mới trước phiên bản cũ | Không ghi payload cũ đè dữ liệu mới |
| Hai instance | Cache miss/ấm ở A và B, sửa DB và broadcast | Cả A và B nhìn dữ liệu mới theo SLA |
| Race read/commit | Đọc cache miss chạy đồng thời với ghi + evict | Phát hiện và xử lý stale repopulation đúng mức nhất quán yêu cầu |
| Sửa list/query | Thêm hoặc xóa entity làm thay đổi trang kết quả | Các query/list cache liên quan được cập nhật hoặc loại bỏ |

**Phương pháp kiểm chứng:** quan sát DB riêng, lần đọc qua endpoint/service riêng, số cache hit/miss, log SQL, version/timestamp và thời gian trễ từ commit đến evict. Đừng chỉ nhìn response ở một request vừa sửa entity trong cùng persistence context.

## 10. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Gọi `entityManager.clear()` nhưng API vẫn trả giá cũ | Còn Spring Cache, L2 hoặc query cache | Lập danh sách tầng cache; evict đúng key và đúng region |
| `@CacheEvict` chạy nhưng sau rollback lại nạp giá cũ | Eviction xảy ra trước commit, trong phạm vi advice khác | Dời invalidation sang `AFTER_COMMIT` và thử rollback |
| Xóa `productViews[42]` nhưng tìm kiếm vẫn cũ | Kết quả search được cache theo filter/page khác | Invalidate region phụ thuộc hoặc dùng generation |
| Một node thấy giá mới, node khác thấy cũ | L2/Caffeine local; sự kiện chỉ tới một consumer trong group | Cấu hình broadcast hoặc shared/coherent cache |
| Hibernate không biết thay đổi từ SQL ngoài | Writer không đi qua Hibernate | CDC/outbox/event, TTL, hoặc bypass cache |
| `@Modifying(clearAutomatically=true)` không sửa lỗi | Nó chỉ clear persistence context của query đó | Kiểm tra L2 và các application caches riêng |
| Nạp lại cache ngay sau evict vẫn thấy cũ | Evict quá sớm, context cũ, replica lag, race stale repopulation | Xem timeline commit/read, replica consistency, version |
| Sau commit DB đã đổi nhưng cache vẫn cũ | Event mất, listener lỗi, pub/sub rớt, key sai | Log event ID, retry, DLQ, monitoring, TTL |
| `@Cacheable` không cache hoặc `@CacheEvict` không chạy | Chưa `@EnableCaching`, self-invocation, sai key, advice chưa qua proxy | Kiểm tra cấu hình và gọi qua Spring bean |
| Evict mọi region mỗi lần cập nhật làm hệ thống chậm | Cache miss hàng loạt và stampede | Xác định key phụ thuộc, batch evict, generation, giới hạn tải |
| Sau native SQL bị optimistic-lock conflict hoặc lost update | Writer ngoài không giữ quy ước `@Version` | Thống nhất writer/version/lock; kiểm thử cạnh tranh |

### Đặc biệt: có thể có nhiều “nguồn sự thật” nếu không quy định writer

Khi dịch vụ A và B có thể ghi cùng bảng, phải thống nhất schema, transaction, quy tắc tăng `version` và dữ liệu phát sự kiện. Cache invalidation tốt không sửa được lỗi mất cập nhật trong database. Với các trường cần độ chính xác cao như số dư, tồn kho khả dụng ở bước chốt đơn, quyền truy cập, không giả định cache TTL là cơ chế khóa giao dịch; hãy chọn đường đọc và cập nhật có nhất quán phù hợp.

## 11. Quy trình thiết kế và quyết định triển khai

1. **Liệt kê mọi đường ghi** vào bảng/aggregate: JPA managed, bulk JPQL, JDBC, SQL batch, ETL, hệ thống ngoài, admin scripts.
2. **Vẽ bản đồ cache**: L1, L2 entity/collection, Hibernate query, Spring Cache/Redis, API/search/CDN; ghi rõ cache name, key, TTL và instance ownership.
3. **Xác định SLA tươi dữ liệu**: cần chính xác ngay lúc giao dịch, vài giây hoặc có thể cũ vài phút; dữ liệu nào buộc phải bypass cache.
4. **Thiết kế invalidation sau commit**: nội bộ có thể dùng `@TransactionalEventListener(AFTER_COMMIT)`; cần độ bền thì dùng outbox. Writer không kiểm soát nên xem CDC hoặc trigger/stream được quản lý.
5. **Quy định hợp đồng event**: entity ID, loại thay đổi, phiên bản, event ID, nguồn, thời điểm; idempotency, retry, thứ tự, DLQ và quyền truy cập event.
6. **Quyết định phạm vi evict**: entry theo ID, region/query/list phụ thuộc, hoặc generation; không xóa rộng bừa bãi và không bỏ sót kết quả tổng hợp.
7. **Đánh giá multi-node**: Redis chung không đồng nghĩa L2 local đồng bộ; mỗi cache phải có kênh coherence/broadcast hợp lệ.
8. **Kiểm thử commit, rollback, writer ngoài, lỗi consumer, hai node và race read/commit**. Đo kết quả bằng lần đọc mới từ DB và từng tầng cache.
9. **Đặt cơ chế phòng vệ**: TTL phù hợp, monitoring lag/event failure, reconciliation/rebuild và hướng xử lý khi cache unavailable.

### Câu hỏi tự kiểm tra

**1.** Tại sao ứng dụng cập nhật `Product` bằng Spring Data JPA rồi vẫn đọc giá cũ từ `@Cacheable`? **Đáp án:** Hibernate biết entity changed nhưng không tự loại DTO trong Spring Cache. Cần invalidation đúng key sau commit hoặc chiến lược cache khác.

**2.** `entityManagerFactory.getCache().evict(Product.class, 42L)` có xóa Spring Redis cache `productViews[42]` không? **Không.** API này chỉ nhắm JPA L2 entity cache, không phải Spring Cache.

**3.** Một batch SQL ngoài ORM update sản phẩm nhưng service đã dùng `@Modifying(clearAutomatically=true)` ở một repository khác. Vì sao vẫn có dữ liệu cũ? **Đáp án:** `clearAutomatically` chỉ clear persistence context khi method modifying query đó chạy; nó không tự nghe batch SQL và không evict L2/Spring Cache.

**4.** Có thể dùng `AFTER_COMMIT` thay cho outbox trong mọi trường hợp không? **Không.** Callback phù hợp để canh thời điểm, nhưng có thể bị mất nếu process chết/lỗi sau commit. Outbox hoặc CDC có checkpoint/retry cần thiết khi yêu cầu độ bền thông báo.

**5.** Với cache local trên ba instance và broker dùng một consumer group, chỉ một instance nhận event thì có đủ không? **Không**, nếu mỗi instance có L2 local cần evict. Phải fan-out tới các instance, dùng provider có cluster coherence, hoặc không cache loại entity đó ở L2.

## 12. Kết luận và tài liệu đối chiếu

- **L1** chỉ nằm trong persistence context; `refresh/clear` có phạm vi cục bộ.
- **L2/JPA cache** lưu entity giữa các context, có thể stale khi hệ thống ngoài sửa DB; `EntityManagerFactory.getCache().evict(...)` nhắm entity entry, không đồng nghĩa xóa mọi cache.
- **Hibernate query/collection cache** cần được nhận diện riêng và dùng API provider khi cần.
- **Spring Cache** là cache kết quả method; DTO và list/query phải được invalidate theo đúng key/region phụ thuộc.
- Với **JPA update**, tránh evict sớm; dùng callback sau commit để tránh cache nạp lại giá trị chưa commit. Với **writer bên ngoài**, xây dựng luồng sự kiện từ commit qua outbox/CDC hoặc áp dụng TTL/bypass theo yêu cầu nhất quán.
- Với **multi-node và race**, cần thiết kế phân phối sự kiện, xử lý retry, phiên bản và quan sát; một lệnh evict đơn lẻ không bảo đảm strong consistency.

Tài liệu tham khảo chính thức:

- Spring Framework — Cache annotations (`@Cacheable`, `@CacheEvict`): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Transaction-bound events (`@TransactionalEventListener`): https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Data JPA — Modifying queries: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Jakarta Persistence 3.2 — `Cache` API: https://javadoc.io/static/jakarta.persistence/jakarta.persistence-api/3.2.0/jakarta.persistence/jakarta/persistence/Cache.html
- Hibernate ORM User Guide — Caching và quản lý cached data: https://docs.hibernate.org/orm/7.2/userguide/html_single/#caching
- Hibernate ORM — `org.hibernate.Cache` API: https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Cache.html
