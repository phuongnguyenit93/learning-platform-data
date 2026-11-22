# Xóa cache sau khi cập nhật dữ liệu với Spring Application Events

## 1. Bài toán: database đã đổi nhưng người đọc vẫn nhận dữ liệu cũ

Khi ứng dụng triển khai **cache-aside**, một service đọc bản ghi từ database hoặc API, lưu kết quả theo một key và trả lại bản đã lưu ở những lần truy vấn tiếp theo. Điều này cải thiện hiệu năng, nhưng bản sao trong cache trở thành **stale data** nếu nguồn dữ liệu thay đổi mà cache không được làm mới.

Ví dụ, sản phẩm `P-1` có giá 100:

~~~text
t0: Database chứa P-1, price=100
t1: GET P-1 -> CACHE MISS -> DB trả 100 -> cache[P-1]=100
t2: GET P-1 -> CACHE HIT  -> trả 100
t3: UPDATE P-1 -> database price=150
t4: GET P-1 -> CACHE HIT  -> trả 100 (STALE)
~~~

Một mẫu triển khai rõ ràng trong Spring:

1. Service cập nhật **source of truth**.
2. Service phát event `ProductUpdated(productId)` để mô tả bản ghi đã thay đổi.
3. Listener nhận event và gọi phương thức `@CacheEvict` hoặc `Cache.evict(...)` để loại bỏ entry tương ứng.
4. Lần đọc tiếp theo cache miss, truy vấn DB và đưa dữ liệu mới vào cache.

~~~text
ProductApplicationService.updatePrice("P-1", 150)
     |
     +-- repository.updatePrice("P-1", 150)
     |
     +-- publisher.publishEvent(ProductUpdated("P-1"))
                      |
                      v
             @EventListener
             ProductCacheInvalidationListener
                      |
                      v
             ProductCacheService.evict("P-1")
             @CacheEvict(cacheNames="products", key="#p0")
                      |
                      v
             Entry "P-1" bị xóa
                      |
                      v
       GET P-1 -> MISS -> DB price=150
~~~

**Điều cần nhớ:** event nội bộ chỉ **kích hoạt hành động xóa cache**, không thay thế giao dịch database và không tự mang lại đảm bảo message delivery, retry hay đồng bộ xuyên nhiều JVM. Việc quyết định **xóa lúc nào**, **xóa key nào** và **xóa ở những instance nào** là một phần quan trọng của thiết kế.

## 2. Phân biệt đúng loại cache cần xóa

| Loại cache | Lưu dữ liệu gì? | Có cần xử lý khi cập nhật Product? |
| --- | --- | --- |
| **Business/data cache** | Product detail, DTO, kết quả truy vấn, product summary. | Có, nếu entry bị ảnh hưởng. |
| **Listener-selection cache** của `AbstractApplicationEventMulticaster` | Danh sách listener phù hợp cho một event type/source type. | Không; nó không chứa giá sản phẩm. |
| **HTTP/CDN/browser cache** | HTTP response, tài nguyên mạng và frontend state. | Có thể cần, nhưng không tự được Spring Application Events xóa. |
| **ORM first-level cache** | Persistence context của JPA trong một transaction/session. | Được quản lý theo lifecycle ORM; không đồng nhất với Spring Cache. |
| **Local near-cache + distributed cache** | Các bản sao ở mỗi pod và backend shared. | Phải xét toàn bộ các tầng phục vụ read path. |

Khi nói “xóa cache sau khi cập nhật dữ liệu”, bài này chủ yếu nói về **Spring Cache abstraction** và cache-aside cho dữ liệu nghiệp vụ. Đừng cố dùng reflection xóa listener cache của multicaster để giải quyết một entry Product stale.

## 3. Các API Spring liên quan

| API/annotation | Trách nhiệm |
| --- | --- |
| `@EnableCaching` | Kích hoạt xử lý annotation caching, mặc định thông qua AOP proxy. |
| `@Cacheable` | Lấy giá trị từ cache nếu hit; khi miss, gọi method và có thể lưu kết quả. |
| `@CacheEvict` | Xóa entry theo key hoặc toàn bộ cache region. |
| `@CachePut` | Luôn gọi method, sau đó lưu giá trị trả về vào cache. |
| `@Caching` | Kết hợp nhiều `@CacheEvict`/`@CachePut`/`@Cacheable` trên một method. |
| `CacheManager` | Cung cấp cache theo tên, ví dụ `products`. |
| `Cache` | Có `get`, `put`, `evict`, `clear` và các API khác. |
| `ConcurrentMapCacheManager` | Provider in-memory, phù hợp cho demo, không dùng chung giữa JVM. |
| `ApplicationEventPublisher` | Công bố sự kiện nghiệp vụ trong Spring context. |
| `@EventListener` | Nhận event và điều phối một thao tác invalidation. |
| `@TransactionalEventListener` | Cho phép phản ứng theo pha transaction, ví dụ `AFTER_COMMIT`. |

Caching và event dispatch là **hai cơ chế độc lập**. Việc listener chạy không tự chứng minh một key đã biến mất khỏi cache; việc thêm annotation `@CacheEvict` cũng không tự làm listener được đăng ký. Cần test cả hai.

## 4. Chọn cache key chính xác

### 4.1. Đường đọc

Ví dụ:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String productId) {
    return repository.load(productId);
}
~~~

*Đây là đoạn tích hợp minh họa trong Spring bean; `Product`/`repository` cần được định nghĩa. Cần `@EnableCaching` và `CacheManager`.*

`#p0` trong SpEL tham chiếu tham số đầu tiên của method; khi gọi `find("P-1")`, key là chuỗi `"P-1"`.

### 4.2. Đường xóa

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void evict(String productId) {
    // Không cần code xóa cache trong body; Spring advice xử lý.
}
~~~

Hai đường trên dùng **cùng cache name và cùng key**. Nếu `find` dùng `String` nhưng evict dùng object event, thao tác sẽ không khớp.

Ví dụ anti-pattern:

~~~java
@EventListener
@CacheEvict(cacheNames = "products", key = "#p0")
public void onProductUpdated(ProductUpdated event) {
}
~~~

Vì `#p0` ở đây là **toàn bộ ProductUpdated event**, nó không bằng key `String "P-1"` đang lưu từ `find(String)`. Nếu muốn đưa cache annotation trực tiếp lên method nhận event, phải chọn property phù hợp:

~~~java
@CacheEvict(cacheNames = "products", key = "#p0.productId()")
public void onProductUpdated(ProductUpdated event) {
}
~~~

*Các đoạn chỉ minh họa cú pháp; cần kiểm thử lời gọi qua Spring proxy khi kết hợp `@EventListener` và `@CacheEvict` trên cùng method. Ví dụ chạy ở phần 6 tách cache service để tránh phụ thuộc vào chi tiết đó.*

Ngoài product ID, cache key có thể chứa tenant, locale, trang hoặc loại giá. Một entry `tenant-A:P-1` không được xóa bằng key `P-1`. Hãy thống nhất key generator hoặc xây khóa ghép nhất quán ở cả read và invalidation.

### 4.3. Vai trò của eventId

Nếu event chứa `eventId` và `productId`, `eventId` dùng để nhận diện **lần phát sinh sự kiện**, còn `productId` là **định danh bản ghi** và thường là cache key. Dùng event ID để evict product detail cache sẽ không chính xác, trừ khi cache của bạn thực sự được index theo event ID.

## 5. @CacheEvict: trước hay sau method, một key hay toàn bộ region?

### 5.1. Mặc định: sau khi method hoàn thành thành công

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void evict(String id) {
    auditEvictionRequest(id);
}
~~~

Theo contract của Spring, `beforeInvocation=false` là mặc định: eviction được kích hoạt **sau khi method đã thực thi thành công**. Nếu method ném exception trước đó, eviction mặc định không diễn ra. Nó không có nghĩa “sau khi một database transaction khác commit”.

### 5.2. beforeInvocation=true

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    beforeInvocation = true)
public void evictBefore(String id) {
    performSomething(id);
}
~~~

Khi bật `beforeInvocation=true`, cache eviction xảy ra trước khi method được gọi, không phụ thuộc vào kết quả của method. Trường hợp này có thể hữu ích, nhưng với update DB có thể rollback, xóa trước thường không phải cách mặc định để giữ cache nhất quán.

### 5.3. allEntries=true

~~~java
@CacheEvict(cacheNames = "productLists", allEntries = true)
public void clearProductLists() {
}
~~~

`allEntries=true` nhắm tới **toàn bộ region**, không chỉ một product ID. Không kết hợp `key` với `allEntries=true` trên cùng annotation. Xóa cả region mỗi lần cập nhật một sản phẩm có thể gây nhiều cache misses đồng thời, tăng tải DB và giảm hit ratio.

### 5.4. condition và phương thức void

`@CacheEvict` có thể dùng trên method `void` vì giá trị trả về không phải phần được cache. Nó còn hỗ trợ `condition` để chỉ evict khi một điều kiện hợp lệ; nhưng đừng nhầm với `unless` phổ biến ở `@Cacheable`. Hãy đặt business conditions ở nơi rõ ràng và kiểm thử các giá trị biên; một condition luôn false có thể làm entry stale dù listener vẫn chạy.

## 6. Ví dụ Java 17+ chạy được: update phát event, listener xóa cache

Ví dụ dùng **Spring Framework 6.2.9**, JDK 17+ và Maven. Nó dùng một repository in-memory làm **source of truth giả lập**, không có transaction/broker. Cấu trúc này giúp kiểm tra chính xác hành vi của `@Cacheable`, `@EventListener` và `@CacheEvict` mà không lẫn với lỗi kết nối database.

### 6.1. Cấu trúc dự án

~~~text
cache-event-demo/
├── pom.xml
└── src/main/java/CacheInvalidationDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>cache-event-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/CacheInvalidationDemo.java`:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class CacheInvalidationDemo {

    public record Product(String id, int price) {}
    public record ProductUpdated(String productId) {}

    public static class ProductRepository {
        private final Map<String, Product> data = new ConcurrentHashMap<>();
        private final AtomicInteger loads = new AtomicInteger();

        public ProductRepository() {
            data.put("P-1", new Product("P-1", 100));
        }

        public Product load(String id) {
            Product product = data.get(id);
            if (product == null) {
                throw new IllegalArgumentException("Unknown product: " + id);
            }
            loads.incrementAndGet();
            System.out.println("DB_LOAD " + id + "=" + product.price());
            return product;
        }

        public void updatePrice(String id, int price) {
            Product result = data.computeIfPresent(
                    id, (key, oldValue) -> new Product(id, price));
            if (result == null) {
                throw new IllegalArgumentException("Unknown product: " + id);
            }
            System.out.println("DB_UPDATE " + id + "=" + price);
        }

        public int loadCount() {
            return loads.get();
        }
    }

    public static class ProductCacheService {
        private final ProductRepository repository;

        public ProductCacheService(ProductRepository repository) {
            this.repository = repository;
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public Product find(String id) {
            return repository.load(id);
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void evict(String id) {
            // Body chạy trước eviction mặc định (after-invocation).
            System.out.println("EVICT_CALL " + id);
        }
    }

    public static class ProductApplicationService {
        private final ProductRepository repository;
        private final ApplicationEventPublisher publisher;

        public ProductApplicationService(
                ProductRepository repository,
                ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        public void updatePrice(String id, int price) {
            repository.updatePrice(id, price);
            publisher.publishEvent(new ProductUpdated(id));
        }
    }

    public static class ProductInvalidationListener {
        private final ProductCacheService cacheService;

        public ProductInvalidationListener(ProductCacheService cacheService) {
            this.cacheService = cacheService;
        }

        @EventListener
        public void onProductUpdated(ProductUpdated event) {
            System.out.println("EVENT " + event.productId());
            cacheService.evict(event.productId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public ProductRepository productRepository() {
            return new ProductRepository();
        }

        @Bean
        public ProductCacheService productCacheService(
                ProductRepository repository) {
            return new ProductCacheService(repository);
        }

        @Bean
        public ProductApplicationService productApplicationService(
                ProductRepository repository,
                ApplicationEventPublisher publisher) {
            return new ProductApplicationService(repository, publisher);
        }

        @Bean
        public ProductInvalidationListener productInvalidationListener(
                ProductCacheService cacheService) {
            return new ProductInvalidationListener(cacheService);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            ProductCacheService cache =
                    context.getBean(ProductCacheService.class);
            ProductApplicationService app =
                    context.getBean(ProductApplicationService.class);
            ProductRepository repo =
                    context.getBean(ProductRepository.class);

            System.out.println("READ1=" + cache.find("P-1").price());
            System.out.println("READ2=" + cache.find("P-1").price());

            app.updatePrice("P-1", 150);

            System.out.println("READ3=" + cache.find("P-1").price());
            System.out.println("LOAD_COUNT=" + repo.loadCount());
        }
    }
}
~~~

Tại thư mục có `pom.xml`, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=CacheInvalidationDemo
~~~

**Stdout do chương trình tự in ra**, không kể log Maven:

~~~text
DB_LOAD P-1=100
READ1=100
READ2=100
DB_UPDATE P-1=150
EVENT P-1
EVICT_CALL P-1
DB_LOAD P-1=150
READ3=150
LOAD_COUNT=2
~~~

### 6.2. Vì sao kết quả này đúng?

1. `@EnableCaching` kích hoạt cache interceptor; `ConcurrentMapCacheManager("products")` cung cấp region `products`.
2. `cache.find("P-1")` được gọi từ bên ngoài bean qua Spring proxy. Lần đầu miss, repository in `DB_LOAD ... 100`, kết quả được lưu vào cache.
3. Lần thứ hai hit, `READ2=100` nhưng repository không được gọi thêm.
4. `app.updatePrice(...)` ghi 150 vào repository rồi phát `ProductUpdated("P-1")`.
5. Multicaster mặc định gọi `@EventListener` đồng bộ. Listener in `EVENT P-1` và gọi bean `cacheService.evict("P-1")` qua dependency Spring đã inject.
6. Spring cache advice của `@CacheEvict` gọi method body, in `EVICT_CALL P-1`, rồi evict key `"P-1"` sau khi method thành công.
7. Lần đọc tiếp theo miss và load 150. `LOAD_COUNT=2` xác nhận repository chỉ được dùng ở lần đọc đầu và lần đọc sau eviction.

**Giới hạn demo:** repository in-memory không có transaction, không có nhiều server, không có network và không test crash/retry. Chương trình chứng minh cơ chế **in-process event-driven cache invalidation**, không chứng minh consistency mạnh trong hệ thống phân tán.

## 7. Spring proxy và lỗi self-invocation

Cache annotations ở chế độ mặc định dùng AOP proxy. Nếu một method trong cùng bean tự gọi `this.evict(id)`, lời gọi thường **không qua proxy**, nên `@CacheEvict` bị bỏ qua.

~~~java
@Service
class BadProductService {
    @Cacheable(cacheNames = "products", key = "#p0")
    public Product find(String id) {
        return repository.load(id);
    }

    public void update(String id, int price) {
        repository.updatePrice(id, price);
        evict(id); // SELF-INVOCATION: có thể bỏ qua @CacheEvict.
    }

    @CacheEvict(cacheNames = "products", key = "#p0")
    public void evict(String id) {}
}
~~~

*Đoạn anti-pattern tích hợp; `Product`, `repository` và các import phải được ứng dụng định nghĩa.*

**Cách sửa:** tách `ProductCacheService` thành bean độc lập và để listener/application service gọi bean đó từ dependency được inject. Một cách khác là dùng trực tiếp `CacheManager`. Đừng cố “chữa” bằng cách tạo `new ProductCacheService(...)` vì object tự tạo không được Spring proxy quản lý.

Với class-based proxy, đừng đặt caching annotation trên private/final method và giả định interceptor luôn chạy. Hãy dùng public method có lời gọi từ bean khác, kiểm thử ứng dụng trong Spring context thực thay vì gọi trực tiếp Java method rồi kết luận caching hoạt động.

Nếu đặt `@EventListener` và `@CacheEvict` trên cùng một method, phải xác nhận event adapter gọi **proxy phù hợp**. Tách listener và cache service là cách giảm rủi ro và thuận tiện cho kiểm thử, không phải yêu cầu bắt buộc của Spring.

## 8. Khi nào xóa cache: trước commit hay sau commit?

### 8.1. Rủi ro của listener đồng bộ trong transaction

Trong hệ thống có database, `@Transactional` service có thể phát event **trước khi transaction commit**:

~~~text
@Transactional updatePrice(...)
    |
    +-- UPDATE DB P-1=150 (chưa commit)
    |
    +-- publish ProductUpdated("P-1")
    |       |
    |       +-- @EventListener -> evict("P-1") ngay
    |
    +-- một bước khác lỗi -> ROLLBACK
~~~

Về ngữ nghĩa, `ProductUpdated` lúc này có thể bị hiểu sai là “đã cập nhật thành công” dù transaction rollback. Evict sớm còn tạo cache miss không cần thiết và mở rộng cửa sổ race với các reader khác.

### 8.2. Dùng @TransactionalEventListener(AFTER_COMMIT)

Trong Spring-managed transaction, một listener có thể chạy sau commit:

~~~java
@Component
class ProductCacheEvictAfterCommit {
    private final ProductCacheService cache;

    ProductCacheEvictAfterCommit(ProductCacheService cache) {
        this.cache = cache;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onUpdated(ProductUpdated event) {
        cache.evict(event.productId());
    }
}
~~~

*Đây là snippet **tích hợp**, không phải ví dụ chạy ở phần 6; cần Spring transaction infrastructure, `@TransactionalEventListener`, `TransactionPhase`, `@Component` và transaction manager thực tế.*

Sơ đồ:

~~~text
BEGIN TX
  UPDATE products
  publish ProductUpdated
  Spring đăng ký transaction synchronization
COMMIT thành công
  AFTER_COMMIT listener -> evict cache key

Nếu ROLLBACK:
  AFTER_COMMIT listener không thực hiện eviction
~~~

**Lưu ý:** `@TransactionalEventListener` mặc định **không chạy ngoài transaction phù hợp** vì `fallbackExecution=false`. Demo in-memory không có transaction nên dùng `@EventListener`; nếu thay bằng `@TransactionalEventListener` mà không bổ sung transaction manager, event sẽ không kích hoạt invalidation.

Khi xử lý ở pha `AFTER_COMMIT`, transaction gốc đã commit. Nếu listener còn muốn ghi DB bổ sung, cần thiết kế transaction mới phù hợp (ví dụ một service có `REQUIRES_NEW` khi dùng imperative transaction) thay vì giả định nó vẫn ghi vào transaction cũ.

### 8.3. @CacheEvict trên chính method @Transactional

~~~java
@Transactional
@CacheEvict(cacheNames = "products", key = "#p0")
public void updatePrice(String productId, int price) {
    repository.updatePrice(productId, price);
}
~~~

*Đây là đoạn tích hợp minh họa.*

Hai annotation có thể khiến cache eviction xảy ra gần điểm kết thúc method, nhưng **thời điểm so với commit còn tùy thứ tự advice và cấu hình**. Không mặc định nó tương đương `AFTER_COMMIT`. Cần test ranh giới transaction thực tế, hoặc dùng mẫu transactional event rõ nghĩa.

### 8.4. Transaction-aware cache manager

Spring có `TransactionAwareCacheDecorator`/`TransactionAwareCacheManagerProxy`, có thể đồng bộ `put`, `evict` và `clear` với transaction hiện hành, thực hiện các thao tác đó sau commit thành công. Đây là **cơ chế ở tầng cache**, không phải bản thân event listener.

Các API immediate như `evictIfPresent` có semantics khác và không thể trì hoãn như eviction thông thường. Khi kết hợp cache wrapper, transaction listener và custom advice, phải kiểm chứng thứ tự; không mặc định mọi lựa chọn cấu hình tương đương nhau.

**Điều quan trọng:** xóa sau commit giải quyết vấn đề **rollback**, nhưng không tự bảo vệ trước việc process chết ngay sau commit hoặc các reader cập nhật cache đồng thời. Những hạn chế ấy cần giải pháp riêng.

## 9. Nhiều instance: local event không xóa cache của pod khác

`ConcurrentMapCacheManager` trong ví dụ chỉ hoạt động trong một JVM:

~~~text
Pod A: cache[P-1] = 100
Pod B: cache[P-1] = 100
Pod C: cache[P-1] = 100

UPDATE ở Pod A:
  Database = 150
  Pod A phát Spring ApplicationEvent
  Pod A evict(P-1)

Đọc sau update:
  Pod A -> 150
  Pod B -> 100  (STALE)
  Pod C -> 100  (STALE)
~~~

Spring Application Events **không tự truyền qua mạng**. Các chiến lược phổ biến:

- **Shared cache** (ví dụ Redis) để các instance dùng chung key space; vẫn cần xét replication lag và near-cache nếu có.
- **Broadcast invalidation event** qua broker/pub-sub: mỗi instance xóa local cache của nó; cần retry/catch-up nếu instance offline.
- **Transactional outbox** ghi notification cùng database transaction rồi relay lên broker; có thể giảm nguy cơ mất invalidation khi process chết.
- **TTL và phiên bản dữ liệu** để hạn chế thời gian stale; đây là cơ chế dự phòng, không thay thế business consistency policy.
- **Versioned cache key** hoặc CAS/provider-specific behavior khi yêu cầu tính nhất quán cao hơn và có nguồn cấp version đáng tin.

Nếu một application có cả Caffeine local cache và Redis shared cache, xóa key ở Redis chưa có nghĩa mọi near-cache trong pod cũng đã hết bản cũ. Phải lập sơ đồ **đầy đủ read path** trước khi quyết định phạm vi invalidation.

## 10. Race condition: sau commit vẫn có thể trả dữ liệu cũ

### 10.1. Reader cũ làm đầy lại cache

~~~text
Reader                            Writer
--------------------------------  -------------------------------
cache MISS
DB read old=100
                                  COMMIT DB new=150
                                  cache evict(P-1)
cache put(old=100)  [đến muộn]
GET P-1 có thể nhận 100
~~~

Ngay cả khi evict sau commit, một reader concurrent có thể đã lấy snapshot cũ và ghi vào cache sau thời điểm eviction. Đây là **stale repopulation race**; cách xảy ra cụ thể tùy provider và scheduling.

Các biện pháp tùy yêu cầu: version/generation tokens, per-key synchronization, provider atomic operations, TTL, read-through/write-through consistency policy, hoặc bypass cache cho các thao tác yêu cầu dữ liệu cực mới. Không có một annotation Spring đơn lẻ loại bỏ được mọi race.

### 10.2. Event đến trễ, lặp và đảo thứ tự

Evict cùng key nhiều lần thường **idempotent**: xóa entry đã vắng mặt không gây lỗi nghiệp vụ. Tuy nhiên consumer vẫn phải xử lý retry và quan sát lỗi. Nếu thay vì evict bạn dùng `@CachePut` để ghi giá từ payload, event cũ đến sau event mới có thể **ghi đè** cache bằng giá lỗi thời. Khi đó cần version check, ordering hoặc CAS rõ ràng.

### 10.3. Derived caches

Cập nhật giá sản phẩm có thể làm sai không chỉ detail cache:

~~~text
products[P-1]                 -> product detail
productSummaries[P-1]         -> summary
productsByCategory[category]  -> danh sách có giá
searchResults[query]          -> kết quả lọc/tìm kiếm
cartTotals[cartId]            -> tổng giá giỏ hàng
~~~

Nếu chỉ xóa detail key, những cache khác vẫn stale. Hãy lập **cache dependency map** theo loại thay đổi. Không xóa toàn bộ mọi region chỉ vì chưa hiểu key mapping; cân nhắc thiết kế region theo business responsibility, key tags hoặc cache TTL hợp lý.

## 11. Xóa nhiều vùng bằng @Caching

Khi một update ảnh hưởng cả detail và summary, có thể khai báo:

~~~java
@Caching(evict = {
    @CacheEvict(cacheNames = "products", key = "#p0"),
    @CacheEvict(cacheNames = "productSummaries", key = "#p0"),
    @CacheEvict(cacheNames = "productLists", allEntries = true)
})
public void invalidateProduct(String productId) {
}
~~~

*Snippet tích hợp trong bean được Spring quản lý, cần `@Caching` và các cache names đã cấu hình.*

Không có transaction nguyên tử mặc định cho tất cả cache providers trong danh sách: nếu một cache backend lỗi giữa chừng, có thể xuất hiện partial invalidation. Cần metrics, retry và reconciliation khi nghiệp vụ nhạy cảm.

Nếu mỗi update xóa toàn bộ `productLists`, hệ thống có thể gặp cache stampede. Có thể sử dụng versioned list cache, group invalidation hoặc cache lại với TTL ngắn hơn tùy tải thực tế.

## 12. Eviction bằng CacheManager thay cho annotation

Đôi khi listener không muốn phụ thuộc AOP:

~~~java
@Component
class ProductEvictListener {
    private final CacheManager manager;

    ProductEvictListener(CacheManager manager) {
        this.manager = manager;
    }

    @EventListener
    public void onUpdated(ProductUpdated event) {
        Cache cache = manager.getCache("products");
        if (cache != null) {
            cache.evict(event.productId());
        }
    }
}
~~~

*Đoạn tích hợp cần import `CacheManager`, `Cache`, `@Component` và `@EventListener`; không phải file chạy độc lập.*

So sánh:

| Cách làm | Phù hợp khi | Cảnh báo |
| --- | --- | --- |
| Listener gọi bean có `@CacheEvict` | Muốn reuse cache policy, key SpEL và AOP. | Cần proxy, cache name và key khớp. |
| Listener gọi `CacheManager.getCache(...).evict(...)` | Muốn thao tác explicit bằng key đã có. | Cần xử lý cache null/provider semantics. |
| Update method có `@CacheEvict` | Quy trình nhỏ, rõ ràng. | Trật tự advice so với commit không tự rõ. |
| Listener `AFTER_COMMIT` | Yêu cầu không invalidate nếu rollback. | Không durable sau crash. |
| Outbox + broker + listener đa instance | Cần retry và invalidation cross-process. | Eventual consistency, ordering và vận hành phức tạp. |

Theo Spring `Cache` API, `evict(Object key)` có thể được thực hiện deferred/asynchronous tùy cache decorator/provider. `evictIfPresent(key)` kỳ vọng key không còn nhìn thấy ngay trong các lookup tiếp theo, nhưng cũng cần hiểu implementation. Đừng coi mọi cache backend đều có cùng thời điểm visibility hoặc replication guarantee.

## 13. Transactional outbox và đảm bảo gửi invalidation

Khoảng hở nghiêm trọng trong hệ thống nhiều service:

~~~text
DB COMMIT price=150
    |
    X process chết trước khi gửi event sang broker
    |
    +-- Pod khác vẫn cache price=100
~~~

Một `@TransactionalEventListener(AFTER_COMMIT)` chỉ là callback trong memory; nó **không tự lưu event để retry sau JVM crash**.

Transactional outbox tạo một hàng outbox **trong cùng DB transaction** với update:

~~~text
BEGIN TRANSACTION
  UPDATE product price=150
  INSERT outbox(ProductUpdated, eventId, productId, version)
COMMIT
    |
    v
Outbox relay -> durable broker -> consumer
                                   |
                                   +-- evict local/shared cache
                                   +-- retry nếu lỗi
                                   +-- idempotency theo eventId nếu cần
~~~

Outbox giảm rủi ro commit dữ liệu mà mất notification; nhưng relay vẫn có thể phát trùng và consumer vẫn có thể offline. Cần lựa chọn retention, dead-letter/retry, idempotency và đo **thời gian từ commit tới eviction**.

Một event contract production có thể dùng:

~~~java
public record ProductUpdated(
        String eventId,
        String productId,
        long productVersion,
        Instant occurredAt,
        String correlationId) {}
~~~

*Snippet minh họa; cần `java.time.Instant` và chính sách cấp eventId/version rõ ràng.*

`eventId` định danh occurrence, `productId` xác định entry, `productVersion` giúp xử lý ordering nếu thiết kế cache theo version. Không dùng correlation ID làm cache key hoặc dedup key của mọi event vì nhiều event cùng workflow có thể chia sẻ correlation ID.

## 14. Cần làm gì khi xóa cache thất bại?

Lỗi có thể xảy ra ở nhiều ranh giới:

- **Event không được publish** vì service bỏ qua đường update đúng.
- **Listener không đăng ký** do sai event type/context hoặc thiếu bean.
- **Listener chạy nhưng cache advice không chạy** do self-invocation, method không public hoặc bean tự tạo ngoài Spring.
- **Evict dùng sai key/cacheName**, nên xóa không đúng bản ghi.
- **Cache backend lỗi**: timeout, không kết nối, rate limit hoặc provider trả lỗi.
- **Transaction rollback/phase**: listener `AFTER_COMMIT` không chạy do không có commit.
- **Async execution**: exception xảy ra ở executor, publisher không nhìn thấy ngay.
- **Cluster**: một instance xóa local key nhưng các instance khác giữ stale.
- **Concurrent reader**: cache được làm đầy lại bởi dữ liệu cũ.

Để xử lý an toàn:

1. Quan sát eventId/productId/cacheName/hashed key và outcome, tránh log thông tin nhạy cảm.
2. Tách lỗi cấu hình (sai key) khỏi lỗi transient (timeout).
3. Có metric số invalidation thành công/thất bại và tuổi của dữ liệu cache.
4. Nếu yêu cầu không stale, xác định **fail-open hay fail-closed** khi backend cache/invalidation hỏng.
5. Với distributed invalidation, dùng retry/outbox và idempotency; đừng âm thầm nuốt lỗi rồi đánh dấu thành công.
6. TTL là một lớp phòng vệ, không phải guarantee dữ liệu mới tức thì.

Nếu listener bị exception đồng bộ trong một transaction, nó có thể khiến transaction rollback theo quy tắc áp dụng; nhưng khi lỗi trong callback `AFTER_COMMIT`, DB đã commit nên không thể rollback dữ liệu gốc chỉ bằng exception đó. Phải có kế hoạch compensation/reconciliation hoặc retry riêng.

## 15. Kiểm thử mẫu triển khai

Một bộ test thực tế nên bao phủ:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Read đầu tiên | Cache miss, repository load. |
| Read thứ hai cùng key | Cache hit, không load lại. |
| Update thành công + event | Listener evict entry đúng key. |
| Read sau update | Cache miss và trả giá mới. |
| Update product khác | Entry không liên quan giữ nguyên. |
| Event lặp | Evict idempotent, không có side effect ngoài ý muốn. |
| Gọi cache method qua proxy | `@CacheEvict` thực sự có tác dụng. |
| Gọi `this.evict(...)` | Test phát hiện việc bypass proxy nếu code làm vậy. |
| TX rollback | AFTER_COMMIT listener không chạy. |
| Không có TX | AFTER_COMMIT không chạy khi fallback disabled. |
| Multiple pods | Cần notification hoặc shared cache để tránh stale. |
| Cache provider lỗi | Lỗi được theo dõi và có policy retry/fallback. |
| Race giữa reader và writer | Có biện pháp version/consistency khi yêu cầu. |
| Update danh sách/category | Các derived cache regions được invalidated. |

Đừng chỉ assert “listener được gọi”; hãy xác nhận **repository được gọi lại và giá trả về thay đổi**. Ở demo, `LOAD_COUNT=2` chính là phép chứng minh tối thiểu. Với Spring Boot/JPA/Redis thực tế nên thêm integration test có database và cache backend tương ứng.

### Snippet JUnit/Mockito để định hướng

~~~java
@Test
void updateMustInvalidateCachedProduct() {
    Product before = cachedService.find("P-1");
    assertEquals(100, before.price());

    Product again = cachedService.find("P-1");
    assertEquals(before, again);
    verify(repository, times(1)).load("P-1");

    applicationService.updatePrice("P-1", 150);

    assertEquals(150, cachedService.find("P-1").price());
    verify(repository, times(2)).load("P-1");
}
~~~

*Đoạn là mẫu test **không độc lập**: cần JUnit 5, Mockito, setup repository mock với behavior cập nhật phù hợp và Spring test context đã bật caching + listener. Với repository thật của demo, có thể dùng `repo.loadCount()` thay vì Mockito.*

## 16. Quy trình chẩn đoán khi data vẫn stale

~~~text
Source of truth thực sự là giá mới?
 |
 +-- Không -> kiểm tra transaction/update.
 +-- Có
     |
     +-- Event ProductUpdated đã được publish?
     |     |
     |     +-- Không -> sửa mutation flow hoặc outbox
     |     +-- Có
     |
     +-- Listener có nhận event đúng type/context?
     |     |
     |     +-- Không -> kiểm tra bean, annotation, TX phase, async
     |     +-- Có
     |
     +-- @CacheEvict chạy qua proxy / CacheManager?
     |     |
     |     +-- Không -> sửa @EnableCaching, self-invocation, visibility
     |     +-- Có
     |
     +-- CacheName và KEY khớp với @Cacheable?
     |     |
     |     +-- Không -> sửa key generator/cache region
     |     +-- Có
     |
     +-- Còn cache tầng khác hoặc pod khác?
     |     |
     |     +-- Có -> kiểm tra shared cache, pub/sub, near-cache
     |
     +-- Có reader concurrent, delayed event hoặc replication lag?
           |
           +-- Có -> thiết kế version/race handling
           +-- Không -> đo cache provider, TTL và actual reads
~~~

**Không nên chữa tạm bằng `allEntries=true` khắp nơi.** Nó có thể che đi lỗi key, gây thundering herd và vẫn không khắc phục được việc mất event hoặc có cache ở pod khác.

## 17. Những sai lầm phổ biến

1. Nhầm cache của multicaster với cache của dữ liệu nghiệp vụ.
2. Update DB nhưng quên phát event/invalidate cache.
3. `@Cacheable` dùng key `String`, `@CacheEvict` lại nhận toàn bộ event object làm key.
4. Sai cache name hoặc bỏ qua tenant/locale trong composite key.
5. Quên `@EnableCaching`, nên annotation không có tác dụng.
6. Gọi `this.evict(...)` và bỏ qua AOP proxy.
7. Giả định `@CacheEvict` trên method `@Transactional` luôn chạy đúng sau commit.
8. Dùng `@TransactionalEventListener` nhưng không có transaction, khiến callback mặc định không chạy.
9. Xem AFTER_COMMIT là durable delivery hoặc retry tự động sau crash.
10. Chỉ xóa cache của instance đang publish event.
11. Xóa cả region cho một thay đổi nhỏ, gây cache stampede.
12. Quên list/search/summary/derived cache.
13. Ghi cache bằng payload cũ đến muộn qua `@CachePut`.
14. Không xử lý exception từ backend hoặc từ listener async.
15. Dùng TTL như cam kết consistency tức thời.
16. Bỏ qua sự cạnh tranh giữa stale read, update commit và cache refill.
17. Không phân biệt `eventId` với `productId` khi xác định key.
18. Dùng update event đến từ nguồn không đáng tin để xóa key của tenant khác.
19. Không có metrics cho invalidation delay và failure.
20. Kiểm thử mỗi listener riêng lẻ mà không kiểm thử toàn bộ đường đọc trước/sau update.

## 18. Tự kiểm tra

**Câu 1.** Vì sao `READ2=100` không đi kèm dòng `DB_LOAD` thứ hai?

**Đáp án:** `@Cacheable` đã lưu kết quả theo `products["P-1"]`, nên lần đọc sau hit cache.

**Câu 2.** Vì sao không dùng `key="#p0"` trên một method nhận `ProductUpdated event` nếu method đọc cache nhận `String id`?

**Đáp án:** `#p0` ở hai method là hai object khác kiểu; cần `#p0.productId()` hoặc một method `evict(String)`.

**Câu 3.** `beforeInvocation=false` có đồng nghĩa eviction sau DB commit không?

**Đáp án:** Không. Nó chỉ có nghĩa eviction xảy ra sau khi method được advice hoàn thành thành công, không phải transaction commit.

**Câu 4.** Vì sao `@TransactionalEventListener(AFTER_COMMIT)` không phù hợp để thay trực tiếp `@EventListener` trong demo?

**Đáp án:** Demo không có transaction active; transactional listener không chạy khi `fallbackExecution=false` mặc định.

**Câu 5.** Xóa local cache ở Pod A có làm Pod B không còn stale data không?

**Đáp án:** Không. Cần shared cache, cross-instance invalidation hoặc một chính sách nhất quán khác.

**Câu 6.** Khi update giá P-1, vì sao cache danh sách theo category có thể vẫn lỗi?

**Đáp án:** Detail entry và danh sách theo category là các cache keys/regions độc lập; cần lập dependency map.

**Câu 7.** Lý do gì có thể khiến một reader nạp lại bản cũ sau khi writer đã evict?

**Đáp án:** Reader có thể đọc snapshot trước commit nhưng hoàn tất cache put sau eviction. Phải xét concurrency/version.

**Câu 8.** Khi nào `allEntries=true` hợp lý?

**Đáp án:** Khi tất cả entries bị ảnh hưởng hoặc không thể định danh tập key, và tác động tải/latency được chấp nhận.

**Câu 9.** Event bị giao lại cùng ID có nên xem là update mới không?

**Đáp án:** Không. Đó có thể là cùng occurrence được replay; consumer cần semantics idempotency, không mặc định tạo side effect mới.

**Câu 10.** Sau commit, invalidation bị lỗi và process chết. `@TransactionalEventListener` có tự khôi phục sau restart không?

**Đáp án:** Không. Cần cơ chế bền vững như transactional outbox, broker/retry và reconciliation.

## Tài liệu tham khảo

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, `@CacheEvict`, `beforeInvocation`, `allEntries`, `@Caching`, `@EnableCaching` và AOP proxy.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, `AFTER_COMMIT`, `fallbackExecution` và ranh giới commit.
- [Spring Framework 6.2.9 Javadoc — Cache](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/Cache.html): `evict`, `evictIfPresent`, `clear`, `invalidate`.
- [Spring Framework 6.2.9 Javadoc — CacheEvict](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/annotation/CacheEvict.html): cacheName, key, condition, allEntries, beforeInvocation.
- [Spring Framework 6.2.9 Javadoc — TransactionAwareCacheDecorator](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html): transaction-aware `put`/`evict`/`clear`.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher` và `@EventListener`.
