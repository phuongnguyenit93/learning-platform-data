# Phân biệt JPA cache với Spring Cache

## 1. Tại sao cùng gọi là “cache” nhưng không cùng nhiệm vụ?

Trong ứng dụng dùng Spring Data JPA, ít nhất ba cơ chế dễ bị gọi chung là “cache”:

1. **JPA first-level cache (L1, persistence context):** vùng lưu các entity *đang được quản lý* bởi một `EntityManager`. Đây là một phần thiết yếu của vòng đời entity và dirty checking.
2. **JPA second-level cache (L2):** bộ nhớ đệm entity/collection *tùy chọn*, có thể được chia sẻ giữa nhiều `EntityManager` thuộc cùng một `EntityManagerFactory`, tùy JPA provider và cấu hình.
3. **Spring Cache:** abstraction cấp ứng dụng, chủ yếu cache **kết quả phương thức** bằng `@Cacheable`, `@CachePut`, `@CacheEvict` thông qua `CacheManager` và backend như Caffeine hoặc Redis.

Với Hibernate (JPA provider phổ biến trong Spring Boot), còn có **query cache** tùy chọn. Query cache không đồng nghĩa với L2 entity cache và không biến mọi truy vấn JPA thành cache hit.

Điểm mấu chốt: **JPA cache quản lý entity và trạng thái persistence; Spring Cache quản lý giá trị do ứng dụng quyết định cache.** Chúng có thể cùng xuất hiện trong một luồng đọc, nhưng không tự quản lý hoặc vô hiệu hóa dữ liệu cho nhau.

### Sơ đồ một lần đọc

```text
Client
  │
  ▼
ProductReadService.get(id)
  │
  ├── Spring Cache HIT ───────────────────────────────► Trả ProductView đã cache
  │                                                     (không chạy thân method)
  └── Spring Cache MISS
        │
        ▼
      Repository / EntityManager
        │
        ├── Entity đã managed trong L1? ─────────────► Dùng entity trong persistence context
        │
        └── Chưa có trong L1
              │
              ├── L2 bật, có entry phù hợp? ─────────► Nạp trạng thái entity từ L2
              │
              └── Không có/hit không hợp lệ ─────────► Đọc database
        │
        ▼
      Tạo DTO ProductView
        │
        └── Đưa kết quả vào Spring Cache, trả client
```

Đây là sơ đồ khái niệm cho **tra cứu entity theo khóa chính**. Một truy vấn JPQL/Criteria tùy ý có thể vẫn phát sinh SQL để xác định tập kết quả, ngay cả khi một số entity tương ứng đã có trong L1. Quyết định truy vấn, fetch và cache phụ thuộc đường gọi thực tế cùng JPA provider.

## 2. JPA L1: “cache” gắn với EntityManager và transaction

Mỗi `EntityManager` có một **persistence context**, thường được gọi là first-level cache. Với entity có cùng kiểu và khóa chính, JPA bảo đảm chỉ có một instance managed trong cùng persistence context. L1 phục vụ các đặc tính quan trọng:

- **Identity map:** `find` hai lần với cùng id trong cùng persistence context có thể trả về cùng tham chiếu Java.
- **Dirty checking:** thay đổi trên managed entity được phát hiện và đồng bộ khi `flush`/commit theo quy tắc JPA.
- **Repeatable identity trong phạm vi context:** các phần code cùng dùng một entity managed, không tạo ra hai instance managed khác nhau cho cùng database identity.
- **Write-behind:** JPA có thể hoãn SQL cho đến `flush`; L1 không chỉ là nơi giữ bản sao dữ liệu đã truy vấn.

Ví dụ đặt trong một Spring bean với `EntityManager` được inject:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JpaIdentityDemo {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public boolean sameManagedObject(Long existingProductId) {
        Product first = entityManager.find(Product.class, existingProductId);
        Product second = entityManager.find(Product.class, existingProductId);
        return first == second; // true nếu bản ghi tồn tại và cùng persistence context
    }
}
```

Trong Spring, `EntityManager` thường gắn với transaction hiện tại; phạm vi cụ thể phụ thuộc cách cấu hình, ví dụ Open EntityManager in View hoặc extended persistence context. **Không mặc định suy ra L1 dùng chung giữa mọi HTTP request hoặc transaction.**

- `entityManager.flush()`: yêu cầu đồng bộ các thay đổi đang chờ xuống database; **không xóa L1**.
- `entityManager.clear()`: detach toàn bộ managed entities khỏi persistence context; **không tự xóa L2 hoặc Spring Cache**.
- `entityManager.detach(entity)`: detach một entity cụ thể.
- `entityManager.refresh(entity)`: đọc lại trạng thái của một entity managed theo cơ chế provider, phù hợp khi cần làm mới object; **không phải lệnh xóa tất cả cache**.
- Kết thúc persistence context sẽ chấm dứt phạm vi L1, nhưng dữ liệu có thể vẫn còn trong L2 hoặc Spring Cache nếu các lớp ấy được bật.

L1 **không cần `@EnableCaching`** và không bật/tắt bằng `org.springframework.cache.annotation.Cacheable`. Nó tồn tại như một phần bình thường của JPA.

**Giới hạn:** Câu bulk JPQL `UPDATE`/`DELETE` hoặc SQL từ tiến trình ngoài JPA có thể thay đổi database mà entity managed trong L1 vẫn giữ giá trị cũ. Khi đó cần xác định thời điểm `flush`, `clear`, `refresh` hoặc tạo context mới. Không dùng cache như lý do bỏ qua transaction và vấn đề nhất quán.

## 3. JPA L2: cache entity chia sẻ, tùy chọn và phụ thuộc provider

Second-level cache nằm ở phạm vi `EntityManagerFactory`/Hibernate `SessionFactory`, nên entity có thể được sử dụng lại qua nhiều persistence context **nếu** entity được phép cache, provider có cache backend và cấu hình đúng.

Các đặc trưng:

- **Tùy chọn:** ứng dụng JPA không mặc định có một L2 cache hiệu quả cho mọi entity. Nhiều cấu hình Hibernate yêu cầu region factory và backend phù hợp.
- **Thường cache trạng thái entity theo loại + id:** các association/collection có chính sách cache riêng; **không mặc định cache mọi collection hoặc kết quả truy vấn**.
- **Không bảo đảm dùng chung giữa các node:** nếu cache nằm trong bộ nhớ của từng process thì mỗi node giữ một bản riêng. Chia sẻ/cluster phụ thuộc cache provider.
- **Consistency và eviction do provider/quy tắc truy cập quyết định:** cần chọn concurrency strategy, expiry, khóa, invalidation và hành vi khi ghi đồng thời.
- **Cập nhật bên ngoài JPA:** SQL script, dịch vụ khác và một số loại native/bulk DML có thể khiến entry cũ tồn tại. Hibernate có cơ chế invalidation cho một số thao tác nó nhận biết, nhưng không thể suy ra mọi writer ngoài ORM đều được đồng bộ tự động.

Trong JPA có annotation `jakarta.persistence.Cacheable` và API `EntityManagerFactory.getCache()`. Với Hibernate, có thể gặp thêm annotation/provider config như:

```java
// Minh họa mapping entity khi Hibernate L2 đã được cấu hình đầy đủ:
@jakarta.persistence.Cacheable(true)
@org.hibernate.annotations.Cache(
    usage = org.hibernate.annotations.CacheConcurrencyStrategy.READ_WRITE
)
@Entity
public class Product {
    // ... id và các thuộc tính đã mapping ...
}
```

Đoạn trên **chỉ minh họa annotation**, không phải file Java độc lập và chưa đủ để chạy L2: cần dependency/cache backend, region factory, chính sách region và cấu hình Hibernate/JPA tương ứng. Không thêm mapping này chỉ vì thấy truy vấn chậm; phải đo hit rate và đặc tính cập nhật.

JPA cung cấp thao tác cấp factory (khi provider hỗ trợ cache đó):

```java
import jakarta.persistence.Cache;
import jakarta.persistence.EntityManagerFactory;

Cache cache = entityManagerFactory.getCache();
boolean cached = cache.contains(Product.class, productId);
cache.evict(Product.class, productId); // evict entity L2 theo id
// cache.evictAll();                 // xóa toàn bộ dữ liệu cache L2 được quản lý
```

Đây là mã minh họa bên trong một method đã có `entityManagerFactory` và `productId`. Nó **không xóa Spring Cache**. Đặc biệt, `EntityManager.clear()` chỉ tác động tới L1, còn `EntityManagerFactory.getCache().evict(...)` tác động tới L2; hai lệnh giải quyết hai phạm vi khác nhau.

### Query cache của Hibernate khác L2 entity cache

Hibernate query cache là tính năng riêng, phải bật và đánh dấu truy vấn muốn cache theo API/hint phù hợp. Nó thường lưu thông tin tập kết quả truy vấn (chẳng hạn danh sách khóa định danh cùng metadata), trong khi cache trạng thái entity thuộc về L2. Với truy vấn trả entity, **query cache hit không nhất thiết loại bỏ mọi lần truy cập database** nếu các entity/collection cần thiết không có trong cache thích hợp.

Không nên coi `repository.findAll()` hay JPQL `select` mặc định là “được cache” chỉ vì L2 bật. Query cache có chi phí invalidation và dễ kém hiệu quả trên bảng cập nhật liên tục; chỉ bật khi có dữ liệu đo đạc hỗ trợ.

## 4. Spring Cache: cache kết quả method, độc lập vòng đời JPA

Spring Cache là abstraction đặt tại **ranh giới phương thức**. Khi được bật và lời gọi đi qua Spring AOP proxy:

- `@Cacheable(cacheNames = "...", key = "...")`: kiểm tra cache; hit thì trả kết quả đã lưu và **bỏ qua thân method**, miss thì thực thi method rồi cache kết quả theo chính sách.
- `@CachePut`: **vẫn thực thi** method và cập nhật giá trị cache từ kết quả; không thay thế tùy tiện cho `@Cacheable`.
- `@CacheEvict`: xóa một key hoặc cả region; mặc định thực hiện sau khi method thành công (khi đi qua proxy). **Thời điểm này không mặc nhiên đồng nghĩa với sau database commit.**
- `@EnableCaching`: kích hoạt xử lý cache annotation; cần `CacheManager` cung cấp cache backend.
- `CacheManager`: quản lý các Spring cache theo tên; có thể dùng `ConcurrentMapCacheManager` (đơn giản, trong memory), Caffeine (in-process) hoặc Redis (chia sẻ nếu thiết kế phù hợp).

Khác biệt tên dễ gây nhầm:

| Annotation | Package | Ý nghĩa |
| --- | --- | --- |
| `@Cacheable` | `jakarta.persistence.Cacheable` | Metadata cho cơ chế shared cache của JPA |
| `@Cacheable` | `org.springframework.cache.annotation.Cacheable` | Cache **kết quả method** do Spring quản lý |
| `@Cache` | `org.hibernate.annotations.Cache` | Mapping/chính sách cache theo Hibernate provider |
| `@CacheEvict` | `org.springframework.cache.annotation.CacheEvict` | Xóa entry trong **Spring Cache** |

**Lỗi AOP phổ biến:** gọi `this.getProduct(id)` từ một method khác trong **cùng bean** thường bỏ qua Spring proxy, vì vậy `@Cacheable` không hoạt động trong proxy mode mặc định. Đặt read method vào bean riêng và gọi thông qua bean được inject, hoặc thiết kế lại ranh giới service. Cache annotation không biến private method tự động thành cached method.

Spring Data JPA repository cũng **không tự có cache kết quả toàn cục** chỉ vì `JpaRepository` tồn tại. Nếu dùng Spring Cache ở service/repository method, đó là hành vi cache cấp ứng dụng do mình cấu hình.

## 5. Bảng so sánh nhanh

| Tiêu chí | JPA L1 | JPA L2 | Spring Cache |
| --- | --- | --- | --- |
| Mục đích | Quản lý entity và persistence context | Giảm nạp lại trạng thái entity giữa các context | Giảm tính toán, gọi service hoặc truy vấn trả kết quả |
| Phạm vi | Một persistence context / `EntityManager` | `EntityManagerFactory` và provider; liên node tùy backend | CacheManager + backend; một node hay nhiều node tùy chọn |
| Mặc định | Có theo cơ chế JPA | Tùy chọn/cấu hình provider | Phải bật và cấu hình annotation/backend |
| Đối tượng | Managed entity và trạng thái cần dirty checking | Entity state/collection theo mapping | Bất kỳ kết quả method phù hợp: DTO, record, list, dữ liệu tổng hợp... |
| Khóa thường gặp | Entity type + primary key trong context | Entity/region + primary key | Cache name + key sinh từ method args hoặc SpEL |
| Truy vấn bất kỳ | Không bảo đảm bỏ qua SQL | Không tự cache mọi JPQL result | Hit bỏ qua toàn bộ thân method được annotate |
| Xóa/chỉnh | `clear`, `detach`, `refresh` | `EntityManagerFactory.getCache().evict`, provider API | `@CacheEvict`, `Cache.evict`/`clear` |
| Đồng bộ ghi | Theo managed entity/flush; bulk DML có thể làm stale | Theo cơ chế provider; writer ngoài JPA cần kế hoạch rõ | **Ứng dụng chịu trách nhiệm** invalidation/expiry |
| TTL/size | Do vòng đời context; không cấu hình như generic TTL | Tùy provider/region | Tùy backend (Caffeine/Redis...), không do `@Cacheable` tự định nghĩa |

**Thứ tự tra cứu thường gặp:** Spring Cache ở service có thể chặn lời gọi trước khi đi xuống JPA; nếu miss, L1 có thể phục vụ entity managed; nếu L1 chưa có, L2 có thể phục vụ trạng thái; cuối cùng provider mới đọc DB. Đây là mô hình giải thích, không phải lời hứa về số câu SQL của mọi query.

## 6. Ví dụ Java 17+ / Spring Boot 3: cache DTO và xóa cache sau commit

Ví dụ dưới đây dùng:
- Spring Boot 3.x, Java 17+, `spring-boot-starter-data-jpa`, `spring-boot-starter-cache` và H2 runtime.
- Spring Cache backend `ConcurrentMapCacheManager` **chỉ để học/kiểm thử**; không có TTL, giới hạn dung lượng hoặc đồng bộ giữa nhiều process.
- Entity được JPA quản lý; Spring Cache **chỉ lưu record DTO `ProductView`**, tránh cache trực tiếp managed entity và rủi ro proxy/lazy-loading/detached state.
- Khi sửa entity, phát sự kiện trong transaction, sau **commit thành công** mới evict Spring Cache.

Đây là **các file của một ứng dụng Spring Boot**, không phải một file Java độc lập có thể chạy chỉ bằng `javac`. Tạo project Spring Boot 3.x có các dependency kể trên, đặt các file dưới `src/main/java/example/cache/` và cấu hình H2 như bên dưới.

### 6.1. Entity và repository

**`Product.java`**

```java
package example.cache;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {
    }

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void rename(String newName) {
        this.name = newName;
    }
}
```

**`ProductRepository.java`**

```java
package example.cache;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
}
```

`@Version` hỗ trợ optimistic locking khi JPA cập nhật managed entity. L1 dùng tự nhiên qua các lời gọi repository/JPA; chưa cần bật L2.

### 6.2. DTO và service đọc có Spring Cache

**`ProductView.java`**

```java
package example.cache;

import java.math.BigDecimal;

public record ProductView(
        Long id,
        String name,
        BigDecimal price,
        Long version) {
}
```

**`ProductReadService.java`**

```java
package example.cache;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductReadService {
    private final ProductRepository repository;

    public ProductReadService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productViews", key = "#p0")
    @Transactional(readOnly = true)
    public ProductView get(Long id) {
        Product p = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));

        return new ProductView(
                p.getId(), p.getName(), p.getPrice(), p.getVersion());
    }
}
```

`#p0` dùng tham số đầu tiên làm cache key (ở đây là product id), tránh phụ thuộc tên parameter được giữ trong bytecode. Lần đầu miss, repository nạp entity; lần sau hit, bản `ProductView` đã lưu được trả trực tiếp. Điều này **không có nghĩa** `Product` đã được lưu trong JPA L2.

### 6.3. Sửa dữ liệu rồi vô hiệu hóa cache sau commit

**`ProductChanged.java`**

```java
package example.cache;

public record ProductChanged(Long productId) {
}
```

**`ProductWriteService.java`**

```java
package example.cache;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductWriteService {
    private final ProductRepository repository;
    private final ApplicationEventPublisher events;

    public ProductWriteService(
            ProductRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void rename(Long id, String newName) {
        Product product = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));

        product.rename(newName);
        events.publishEvent(new ProductChanged(id));
    }
}
```

Entity đang managed nên JPA flush thay đổi tại thời điểm thích hợp trong transaction. Event được đăng ký trong transaction này; nếu commit thất bại, listener `AFTER_COMMIT` sẽ không chạy.

**`ProductCacheInvalidator.java`**

```java
package example.cache;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductCacheInvalidator {
    private final CacheManager cacheManager;

    public ProductCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(ProductChanged event) {
        Cache cache = cacheManager.getCache("productViews");
        if (cache != null) {
            cache.evict(event.productId());
        }
    }
}
```

`@TransactionalEventListener(AFTER_COMMIT)` chỉ xử lý khi transaction liên quan đã commit thành công; mặc định event không có transaction phù hợp sẽ không được gọi. Nó làm thứ tự invalidate rõ ràng hơn so với mặc định `@CacheEvict` trên method `@Transactional`, nhưng **không phải sự kiện bền vững**: nếu tiến trình chết đúng sau DB commit và trước eviction, cache có thể vẫn cũ. Khi yêu cầu nhất quán cao hoặc nhiều node, cân nhắc outbox/CDC, invalidation phân tán và versioned cache key.

### 6.4. Kích hoạt Spring Cache và chạy ví dụ

**`CacheDemoApplication.java`**

```java
package example.cache;

import java.math.BigDecimal;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CacheDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("productViews");
    }

    @Bean
    CommandLineRunner demo(
            ProductRepository repository,
            ProductReadService reads,
            ProductWriteService writes) {
        return args -> {
            Product product = repository.save(
                    new Product("Before", new BigDecimal("19.00")));
            Long id = product.getId();

            System.out.println("first = " + reads.get(id).name());
            System.out.println("second = " + reads.get(id).name());

            writes.rename(id, "After");

            System.out.println("after change = " + reads.get(id).name());
        };
    }
}
```

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:cache_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

Chạy bằng Maven/Gradle của project Spring Boot đã tạo (ví dụ `./mvnw spring-boot:run` nếu project có Maven Wrapper). Các dòng `System.out.println` mong đợi là:

```text
first = Before
second = Before
after change = After
```

Các log khởi động của Spring Boot có thể xuất hiện thêm. Câu đọc thứ hai có thể phục vụ từ **Spring Cache**. Sau `writes.rename(...)`, JPA ghi thay đổi vào database, listener sau commit evict key, rồi lần đọc cuối phải lấy lại dữ liệu mới.

Ví dụ này **không cấu hình JPA L2**. Việc dữ liệu đọc lần hai được cache không chứng minh L2 đang hoạt động.

## 7. Khi dữ liệu thay đổi, cần xóa cache nào?

Giả sử `Product#7` có tên “Old”; service đã cache `ProductView(7, "Old", ...)`. Transaction khác đổi tên thành “New”. Tùy nơi dữ liệu đang được giữ:

| Thao tác | Tác động chính | Những lớp không được bảo đảm đồng bộ |
| --- | --- | --- |
| `entityManager.clear()` | Detach entity khỏi **L1 hiện tại** | L2, Spring Cache |
| `entityManager.refresh(product)` | Làm mới **entity managed đó** theo provider | Spring Cache; các entity/context khác |
| `entityManagerFactory.getCache().evict(Product.class, 7L)` | Xóa entity khỏi **JPA L2** | L1 đã managed; Spring Cache |
| `cacheManager.getCache("productViews").evict(7L)` | Xóa key khỏi **Spring Cache** | L1, L2 và database |
| `@CacheEvict(cacheNames="productViews", key="#p0")` | Xóa Spring Cache entry khi lời gọi được AOP intercept và đạt điều kiện | JPA L1, JPA L2 |
| Bulk SQL / lệnh của hệ thống khác | Thay đổi **database** | Entity managed trong L1; L2/Spring Cache tùy cơ chế invalidation |

Một ví dụ lỗi logic:

```java
@Cacheable(cacheNames = "productViews", key = "#p0")
public ProductView get(Long id) { /* đọc DB qua repository */ }

// Ở chỗ khác:
entityManager.clear(); // KHÔNG evict productViews
```

Lần gọi `get(id)` tiếp theo vẫn có thể trả `ProductView` cũ từ Spring Cache. Ngược lại, chỉ gọi `@CacheEvict` không làm một entity đang managed trong L1 tự tải lại.

Khi dùng bulk `@Modifying` hoặc native SQL, hãy xử lý **cả persistence context lẫn các cache cấp ứng dụng có liên quan**. Với Hibernate L2/query cache, kiểm tra cơ chế invalidation cụ thể của provider và truy vấn; với writer ở ngoài hệ thống, cần hợp đồng phát sự kiện/evict hoặc một chính sách độ cũ chấp nhận được.

## 8. Rủi ro nhất quán, transaction và nhiều instance

**Eviction sau commit:** Dùng `@CacheEvict` mặc định trên method `@Transactional` có thể gây sai kỳ vọng về thứ tự interceptor/commit, nhất là khi method được gọi trong transaction lớn hơn. Thiết kế rõ việc evict ở thời điểm DB commit thành công, dùng transaction-aware cache manager hoặc transaction event như ví dụ.

**Cache stampede/race:** Một đọc chậm có thể lấy dữ liệu cũ trước commit, rồi cập nhật cache sau khi event đã evict. Vì thế `AFTER_COMMIT` chưa bảo đảm linearizable consistency. Với dữ liệu quan trọng, cân nhắc key chứa version, invalidation liên node, cơ chế lock/CAS hoặc bỏ cache một số loại đọc.

**Nhiều node:** `ConcurrentMapCacheManager` và cache Caffeine in-process thường chỉ tồn tại trong mỗi instance. Evict ở node A không tự xóa dữ liệu ở node B. Redis chia sẻ một cache backend nhưng vẫn cần quy tắc key, TTL và eviction từ mọi đường ghi; chỉ thay backend không tự giải quyết logic invalidation.

**TTL không đồng nghĩa dữ liệu luôn mới:** TTL giới hạn khoảng thời gian entry có thể tồn tại (theo backend), nhưng trong thời gian ấy người dùng vẫn có thể nhận dữ liệu cũ.

**Multi-tenant và dữ liệu cá nhân:** Nếu kết quả phụ thuộc tenant, quyền truy cập, locale hoặc bộ lọc, cache key phải bao gồm các chiều này. Dùng chỉ `#id` cho một kết quả theo user/tenant có thể trả dữ liệu của người khác.

**Entity trong Spring Cache:** Cache trực tiếp JPA entity dễ dẫn đến detached entity, proxy không còn session, lazy-loading exception, mutation ngoài transaction và dữ liệu không đồng bộ. Thông thường nên cache DTO/record bất biến, có phiên bản hóa/expiry hợp lý.

**Hibernate L2 với dữ liệu thay đổi thường xuyên:** Phân tích tỷ lệ hit, vùng cache, strategy nhất quán và chi phí invalidation. Cache một entity cập nhật liên tục có thể ít lợi hơn cache danh mục đọc nhiều, ghi ít.

## 9. Cách kiểm tra mình đang cache ở tầng nào

Để không suy luận bằng cảm giác, hãy đo riêng:

1. **L1:** Trong một transaction, gọi `entityManager.find` hai lần cùng id và kiểm tra đồng nhất tham chiếu; dùng SQL log/statement metrics để quan sát lần đọc thứ hai. Đổi transaction hoặc `clear` để không nhầm phạm vi.
2. **L2:** Bật thống kê Hibernate nếu được hỗ trợ (ví dụ `hibernate.generate_statistics=true`), đọc counters `secondLevelCacheHitCount`/miss/put qua `SessionFactory`; tạo hai persistence context độc lập để kiểm tra hit thực tế. Cache hit L2 không đồng nghĩa Spring Cache hit.
3. **Query cache:** Kiểm tra query cache được bật và từng query được chỉ định cache; đo `queryCacheHitCount` và số SQL thực tế thay vì kết luận từ `findAll()`.
4. **Spring Cache:** Dùng provider metrics hoặc log/counter trong thân method `@Cacheable`; gọi hai lần qua **Spring bean proxy**. Trong ví dụ, method body chỉ được gọi khi miss. Dùng Actuator/metrics nếu stack hỗ trợ.
5. **Invalidation:** Đọc → ghi trong transaction khác → đọc lại; lặp lại với bulk update, SQL ngoài JPA, các node khác, rollback và race cạnh tranh. Kiểm tra nội dung thật, không chỉ số lượng entry.

Dùng test tích hợp để chứng minh hai điều riêng: “cache hit giúp giảm truy cập DB” và “khi dữ liệu đổi, kết quả trả về vẫn tuân thủ yêu cầu nhất quán”. Một bài test chỉ chứng minh hit không chứng minh eviction đúng.

## 10. Chọn giải pháp trong thực tế

| Trường hợp | Lựa chọn thường hợp lý |
| --- | --- |
| Đọc/sửa entity trong một transaction JPA | Dùng **L1 có sẵn** và dirty checking; không cố cache managed entity bằng Spring Cache |
| Entity ít đổi, được đọc thường xuyên qua nhiều transaction | Cân nhắc **Hibernate/JPA L2** sau khi benchmark, chọn concurrency strategy |
| Kết quả service là DTO, cấu hình, báo cáo hoặc dữ liệu tổng hợp tốn tài nguyên | Cân nhắc **Spring Cache** với cache key, TTL, backend và eviction rõ |
| Một JPQL query có tập kết quả lặp đi lặp lại | Chỉ cân nhắc **Hibernate query cache** khi profile chứng minh lợi ích |
| Nhiều ứng dụng/SQL writer và nhiều node cùng sửa dữ liệu | Xác định **invalidation liên hệ thống**, event/outbox/CDC/TTL, giới hạn độ cũ được phép |
| Cần dữ liệu gần thời gian thực hoặc tính đúng đắn cao | Ưu tiên cơ chế nhất quán và transaction; có thể **không cache** đường đọc nhạy cảm |

**Ghi nhớ:** `EntityManager.clear()`, `EntityManagerFactory.getCache().evict(...)` và `@CacheEvict` là ba thao tác trên ba phạm vi khác nhau. Chọn cache theo dữ liệu và vòng đời cần phục vụ, rồi thiết kế cách vô hiệu hóa khi database đổi. “Đã bật cache” không phải bằng chứng rằng dữ liệu luôn chính xác.

### Tài liệu chính thức

- [Jakarta Persistence — Specification](https://jakarta.ee/specifications/persistence/)
- [Hibernate ORM User Guide — Caching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#caching)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Cache Annotations và Proxy Mode](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Configuring Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
