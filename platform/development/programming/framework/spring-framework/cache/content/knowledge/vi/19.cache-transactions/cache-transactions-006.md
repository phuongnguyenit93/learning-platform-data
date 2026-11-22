# Thứ tự cache advice với transaction advice trong Spring Framework

## 1. Vì sao thứ tự advice quan trọng?

Một phương thức service có thể đồng thời mang `@Cacheable`, `@CachePut` hoặc `@CacheEvict` và `@Transactional`. Khi ứng dụng bật Spring Cache và Spring Transaction Management, cả hai cơ chế có thể tạo **AOP advice** bao quanh cùng một lời gọi qua Spring proxy.

Ví dụ:

```java
@Transactional
@CacheEvict(cacheNames = "products", key = "#p0")
public void updateProduct(String productId) {
    repository.update(productId);
}
```

Đây là **method minh họa**, không phải chương trình Java độc lập. Có hai thời điểm hoàn toàn khác nhau mà cache eviction có thể xảy ra:
- **Sau khi transaction advice đã commit**: cache được evict khi thay đổi nguồn dữ liệu đã được transaction advice hoàn tất.
- **Trước lúc transaction advice commit**: cache được evict khi method trả về nhưng transaction vẫn chưa commit. Một request đồng thời có thể cache miss, đọc dữ liệu DB cũ rồi ghi lại cache; nếu commit sau đó thất bại, cache cũng đã bị xóa không cần thiết.

**Điểm cốt lõi:** thứ tự annotation trên method không phải cơ chế đáng tin cậy để sắp xếp cache advice và transaction advice. Thứ tự thực thi dựa trên hệ thống AOP advisor, cấu hình `order` và các lớp proxy/interceptor thực tế.

Mục tiêu bài học:
1. Hiểu `@EnableCaching(order = ...)` và `@EnableTransactionManagement(order = ...)`.
2. Nhận diện hai dạng lồng nhau: **Cache ngoài / Transaction trong** và **Transaction ngoài / Cache trong**.
3. Dự đoán cache hit, cache miss, cache put, cache evict, commit và rollback theo từng thứ tự.
4. Phân biệt thứ tự AOP với việc cache được đồng bộ sau commit bằng `TransactionAwareCacheDecorator`.
5. Chạy ví dụ Java 17+ dùng hai cấu hình order và transaction manager ghi vết, rồi xác minh stdout.
6. Thiết kế kiểm thử với transaction thật, nhiều request, outer transaction và cache backend.

## 2. Nhắc lại: AOP advice chạy theo dạng lồng nhau

Một chuỗi interceptor có dạng:

```text
Client
  -> Advice A (outer)
      -> Advice B (inner)
          -> target service method
      <- Advice B thoát
  <- Advice A thoát
Client nhận kết quả
```

Trong Spring AOP, **giá trị order càng nhỏ thì mức ưu tiên càng cao**: advice có order 100 đứng **ngoài** advice có order 200. Nó chạy sớm hơn trên đường vào và muộn hơn trên đường ra. Dạng lồng nhau quyết định lúc cache put/evict và lúc transaction commit diễn ra tương đối với nhau.

Cần phân biệt:
- **Advice order**: thứ tự trong proxy/interceptor chain.
- **Transaction propagation**: `REQUIRED`, `REQUIRES_NEW`, v.v. quyết định transaction thực sự bắt đầu hay tham gia transaction đang có.
- **Thời điểm backend ghi/xóa cache**: cache implementation có thể ghi/xóa tức thời hoặc trì hoãn qua transaction-aware decorator.

Đây là ba vấn đề độc lập; thay `order` không tự biến cache và database thành một transaction ACID chung.

### 2.1. Hai nơi cấu hình order

```java
@Configuration
@EnableCaching(order = 100)
@EnableTransactionManagement(order = 200)
class CacheOutsideConfig {
    // Cache advisor có mức ưu tiên cao hơn -> đứng ngoài.
}
```

Ngược lại:

```java
@Configuration
@EnableCaching(order = 200)
@EnableTransactionManagement(order = 100)
class TransactionOutsideConfig {
    // Transaction advisor có mức ưu tiên cao hơn -> đứng ngoài.
}
```

Đây là **hai đoạn cấu hình minh họa**, chọn một kiểu cho mỗi ApplicationContext; phần 5 có bản chạy được với cả hai context riêng biệt.

Theo tài liệu Spring, `@EnableCaching.order` và `@EnableTransactionManagement.order` đều có mặc định `Ordered.LOWEST_PRECEDENCE`. Khi cùng mức ưu tiên mà không có quy tắc bổ sung, **không nên dựa vào thứ tự quan sát được tình cờ**. Đặt hai giá trị rõ ràng, khác nhau khi yêu cầu nghiệp vụ phụ thuộc vào thứ tự advice.

`@Order` trên class service hoặc việc viết `@Transactional` trước `@CacheEvict` trong source **không thay thế** việc cấu hình order của các infrastructure advisors tương ứng.

## 3. Trường hợp A: Cache advice nằm NGOÀI transaction advice

Thiết lập:

```java
@EnableCaching(order = 100)
@EnableTransactionManagement(order = 200)
```

Luồng logic của `@Cacheable` khi **cache miss**:

```text
Client
  CacheInterceptor (outer): lookup key -> MISS
    TransactionInterceptor (inner): begin/join transaction
      Service method: đọc DB hoặc tính kết quả
    TransactionInterceptor: commit/hoàn tất phạm vi transaction
  CacheInterceptor: put giá trị vào cache
Client nhận kết quả
```

Nếu target thực sự mở một transaction mới và commit thành công trước khi quay về cache advice, cache put thường diễn ra **sau commit** (trên cache thường, không trì hoãn).

Với `@CacheEvict(beforeInvocation=false)` (mặc định):

```text
Cache advice
  Transaction advice: begin
    target: cập nhật DB
  Transaction advice: commit
Cache advice: evict key
```

Một lỗi commit xảy ra trước khi cache advice xử lý after-invocation; vì exception từ transaction advice truyền ra, operation cache after-success thường **không được thực hiện**.

### 3.1. Trên cache HIT thì sao?

Với `@Cacheable`, cache outer kiểm tra key **trước khi đi vào transaction advice**. Nếu hit:

```text
Cache advice: lookup -> HIT -> trả cached value
Transaction advice: KHÔNG ĐƯỢC GỌI
Target method: KHÔNG ĐƯỢC GỌI
```

Điều này có thể giúp tránh mở transaction không cần thiết cho một lần đọc cache hit. Nhưng cũng có nghĩa **mọi logic chỉ được kích hoạt trong transaction advice sẽ không chạy** ở lần hit đó. Không áp dụng cache cho một method mà mỗi lời gọi đều bắt buộc phải thực thi nghiệp vụ hoặc kiểm tra bảo mật/side effect không thể bỏ qua.

### 3.2. Không phải bảo đảm after-commit toàn hệ thống

Nếu method annotated tham gia **transaction bên ngoài đã tồn tại** (`Propagation.REQUIRED`), transaction advice ở method bên trong có thể chỉ hoàn tất **phạm vi tham gia** mà chưa commit transaction gốc. Cache advice bên ngoài đoạn method đó vẫn có thể put/evict **trước commit của transaction lớn**.

Vì vậy câu “cache outer = luôn luôn sau mọi database commit” là **sai**. Cần xét transaction thật đang thuộc call stack nào, có `REQUIRES_NEW` không, có synchronization nào đang hoạt động và cache backend xử lý put/evict lúc nào.

## 4. Trường hợp B: Transaction advice nằm NGOÀI cache advice

Thiết lập:

```java
@EnableCaching(order = 200)
@EnableTransactionManagement(order = 100)
```

Luồng `@Cacheable` khi **cache miss**:

```text
Client
  Transaction advice (outer): begin/join transaction
    Cache advice (inner): lookup key -> MISS
      target: đọc DB hoặc tính kết quả
    Cache advice: put giá trị vào cache
  Transaction advice: commit
Client nhận kết quả
```

Cache put với một cache bình thường có thể xảy ra **trước khi DB commit thành công**. Nếu commit sau đó thất bại, cache có thể đã chứa dữ liệu từ một transaction không được commit.

Với `@CacheEvict(beforeInvocation=false)`:

```text
Transaction advice: begin
  Cache advice
    target: cập nhật DB
  Cache advice: evict key
Transaction advice: commit
```

Tình huống nguy hiểm: một request khác nhìn thấy cache miss giữa eviction và commit, truy vấn một phiên bản cũ của DB, rồi đưa bản cũ trở lại cache. Khi transaction commit, cache vẫn có nguy cơ stale.

### 4.1. Trên cache HIT

Transaction advice đứng ngoài và **đã chạy trước lúc cache lookup**. Dù cache hit khiến target method bị bỏ qua, transaction advice vẫn có thể mở hoặc tham gia transaction:

```text
Transaction advice: begin/join
  Cache advice: HIT -> trả cached value
Transaction advice: commit/complete
```

Đây là khác biệt hiệu năng và semantics với cache outer. Với transaction manager thật, một cache hit có thể vẫn phải chịu chi phí transaction; tùy implementation và propagation, “begin” ở đây không nhất thiết là mở physical DB transaction mới.

### 4.2. Nếu method ném exception?

Với `@CacheEvict` mặc định `beforeInvocation=false`, exception từ target làm after-success eviction **không diễn ra**, bất kể outer advisor là cache hay transaction. Transaction advice thường rollback khi có unchecked exception theo chính sách `@Transactional` mặc định.

Nếu `beforeInvocation=true`, eviction được yêu cầu **trước khi target chạy**, kể cả target sau đó lỗi. Khi không dùng transaction-aware decorator, entry có thể đã bị xóa dù transaction rollback. Với transaction-aware cache, thực tế còn phụ thuộc eviction được defer tới after-commit hay không.

**Lưu ý:** checked exception không tự rollback theo mặc định trong nhiều phiên bản/cấu hình Spring. Hãy kiểm tra `rollbackFor`/`noRollbackFor` và quy tắc toàn ứng dụng, không khẳng định “mọi exception đều rollback”.

## 5. Ví dụ Java 17+ đầy đủ: quan sát hai thứ tự trên cùng một service

Để tách biệt **thứ tự AOP** khỏi chi tiết cơ sở dữ liệu, ví dụ dùng một `PlatformTransactionManager` tối giản chỉ ghi sự kiện `TX_BEGIN`, `TX_COMMIT` và `TX_ROLLBACK`. Nó **không thực hiện transaction DB thật**. Một `ConcurrentMapCache` được mở rộng để ghi sự kiện `CACHE_GET`, `CACHE_PUT`, `CACHE_EVICT`; method service ghi `TARGET_LOAD` hoặc `TARGET_CHANGE`.

Đây là cách kiểm chứng thứ tự interceptor chính xác mà không phụ thuộc cấu hình JDBC, không thể hiện bảo đảm ACID. Hai Spring ApplicationContext được tạo riêng để đảm bảo hai thí nghiệm không dùng chung cache.

### 5.1. Cấu trúc dự án và Gradle

```text
cache-tx-advice-order/
  settings.gradle
  build.gradle
  src/main/java/demo/advice/AdviceOrderDemo.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'cache-tx-advice-order'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework:spring-tx'
}

application {
    mainClass = 'demo.advice.AdviceOrderDemo'
}
```

### 5.2. Toàn bộ chương trình

Tệp `src/main/java/demo/advice/AdviceOrderDemo.java`:

```java
package demo.advice;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.support.SimpleCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.SimpleTransactionStatus;

public class AdviceOrderDemo {

    // Mỗi context có một event log riêng.
    public static class Events {
        private final List<String> entries = new ArrayList<>();

        public void add(String event) {
            entries.add(event);
        }

        public String drain() {
            String trace = String.join(" > ", entries);
            entries.clear();
            return trace;
        }
    }

    // Manager này chỉ mô phỏng begin/commit/rollback để đo thứ tự AOP.
    // Không mở connection và không cấp transaction thật cho database.
    public static class TraceTransactionManager
            implements PlatformTransactionManager {

        private final Events events;

        public TraceTransactionManager(Events events) {
            this.events = events;
        }

        @Override
        public TransactionStatus getTransaction(TransactionDefinition definition) {
            events.add("TX_BEGIN");
            return new SimpleTransactionStatus();
        }

        @Override
        public void commit(TransactionStatus status) {
            events.add("TX_COMMIT");
        }

        @Override
        public void rollback(TransactionStatus status) {
            events.add("TX_ROLLBACK");
        }
    }

    public static class TraceCache extends ConcurrentMapCache {
        private final Events events;

        public TraceCache(Events events) {
            super("items", true);
            this.events = events;
        }

        @Override
        public ValueWrapper get(Object key) {
            events.add("CACHE_GET(" + key + ")");
            return super.get(key);
        }

        @Override
        public void put(Object key, Object value) {
            events.add("CACHE_PUT(" + key + ")");
            super.put(key, value);
        }

        @Override
        public void evict(Object key) {
            events.add("CACHE_EVICT(" + key + ")");
            super.evict(key);
        }
    }

    public static class ItemService {
        private final Events events;
        private final AtomicInteger loadCount = new AtomicInteger();

        public ItemService(Events events) {
            this.events = events;
        }

        @Transactional
        @Cacheable(cacheNames = "items", key = "#p0")
        public String load(String key) {
            events.add("TARGET_LOAD(" + key + ")");
            return key + "-v" + loadCount.incrementAndGet();
        }

        @Transactional
        @CacheEvict(cacheNames = "items", key = "#p0")
        public void change(String key) {
            events.add("TARGET_CHANGE(" + key + ")");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SharedBeans {
        @Bean
        Events events() {
            return new Events();
        }

        @Bean
        PlatformTransactionManager transactionManager(Events events) {
            return new TraceTransactionManager(events);
        }

        @Bean
        CacheManager cacheManager(Events events) {
            SimpleCacheManager manager = new SimpleCacheManager();
            manager.setCaches(List.of(new TraceCache(events)));
            return manager;
        }

        @Bean
        ItemService itemService(Events events) {
            return new ItemService(events);
        }
    }

    // Cache order nhỏ hơn: Cache advice đứng ngoài Transaction advice.
    @Configuration(proxyBeanMethods = false)
    @EnableCaching(order = 100)
    @EnableTransactionManagement(order = 200)
    @Import(SharedBeans.class)
    public static class CacheOuterConfig {
    }

    // Transaction order nhỏ hơn: Transaction advice đứng ngoài Cache advice.
    @Configuration(proxyBeanMethods = false)
    @EnableCaching(order = 200)
    @EnableTransactionManagement(order = 100)
    @Import(SharedBeans.class)
    public static class TransactionOuterConfig {
    }

    private static void runCase(String label, Class<?> config) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(config)) {
            ItemService service = context.getBean(ItemService.class);
            Events events = context.getBean(Events.class);

            System.out.println("== " + label + " ==");
            System.out.println("first=" + service.load("SKU-1"));
            System.out.println("missTrace=" + events.drain());

            System.out.println("second=" + service.load("SKU-1"));
            System.out.println("hitTrace=" + events.drain());

            service.change("SKU-1");
            System.out.println("evictTrace=" + events.drain());
        }
    }

    public static void main(String[] args) {
        runCase("CACHE_OUTER", CacheOuterConfig.class);
        runCase("TX_OUTER", TransactionOuterConfig.class);
    }
}
```

Chạy từ thư mục dự án với JDK 17+ và Gradle tương thích:

```bash
gradle run --quiet
```

Nếu đã có Gradle Wrapper, dùng `./gradlew run --quiet` (Windows: `gradlew.bat run --quiet`).

**Đầu ra dự kiến từ chương trình**, không tính log khởi động/build:

```text
== CACHE_OUTER ==
first=SKU-1-v1
missTrace=CACHE_GET(SKU-1) > TX_BEGIN > TARGET_LOAD(SKU-1) > TX_COMMIT > CACHE_PUT(SKU-1)
second=SKU-1-v1
hitTrace=CACHE_GET(SKU-1)
evictTrace=TX_BEGIN > TARGET_CHANGE(SKU-1) > TX_COMMIT > CACHE_EVICT(SKU-1)
== TX_OUTER ==
first=SKU-1-v1
missTrace=TX_BEGIN > CACHE_GET(SKU-1) > TARGET_LOAD(SKU-1) > CACHE_PUT(SKU-1) > TX_COMMIT
second=SKU-1-v1
hitTrace=TX_BEGIN > CACHE_GET(SKU-1) > TX_COMMIT
evictTrace=TX_BEGIN > TARGET_CHANGE(SKU-1) > CACHE_EVICT(SKU-1) > TX_COMMIT
```

### 5.3. Cách đọc output

**CASE CACHE_OUTER**:
- Ở cache miss, `CACHE_GET` trước `TX_BEGIN`; `CACHE_PUT` sau `TX_COMMIT`.
- Ở cache hit, trace chỉ có `CACHE_GET`. Cache advice trả về value ngay, transaction advice chưa bao giờ được đi vào.
- `CACHE_EVICT` sau `TX_COMMIT` vì `@CacheEvict` mặc định chạy sau method và nằm ngoài transaction advice.

**CASE TX_OUTER**:
- `TX_BEGIN` có trước `CACHE_GET`.
- `CACHE_PUT` và `CACHE_EVICT` xảy ra trước `TX_COMMIT` trên cache in-memory không transaction-aware.
- Ở cache hit, transaction advice vẫn được đi vào, dù method body không chạy.

**Giới hạn quan trọng:** `TraceTransactionManager` chỉ ghi event và trả status; nó không làm việc với JDBC, ORM hoặc transaction synchronization thật. Vì vậy output là **minh họa thứ tự advice**, không phải một bằng chứng về khả năng rollback DB hay việc cache nhất quán sau commit trong dự án production.

## 6. Kết hợp với transaction-aware cache

Thứ tự AOP chỉ cho biết **lúc Spring gọi** thao tác `put/evict/clear`. Nếu bạn cần đồng bộ cache writes/evictions với Spring-managed transaction, có thể dùng `TransactionAwareCacheManagerProxy` hoặc một cache implementation/manager tương thích transaction-aware.

Ví dụ cấu hình minh họa:

```java
@Bean
CacheManager cacheManager() {
    CacheManager underlying =
            new ConcurrentMapCacheManager("items");
    return new TransactionAwareCacheManagerProxy(underlying);
}
```

Cần import:
- `org.springframework.cache.CacheManager`;
- `org.springframework.cache.concurrent.ConcurrentMapCacheManager`;
- `org.springframework.cache.transaction.TransactionAwareCacheManagerProxy`.

Đoạn này chỉ minh họa bean, không nằm trong ví dụ trace ở mục 5.

Theo Spring, `TransactionAwareCacheDecorator` đồng bộ các thao tác **`put`, `evict` và `clear`** với transaction hiện hành thông qua `TransactionSynchronizationManager`. Khi có một Spring-managed transaction phù hợp, hành động thực tế có thể được **trì hoãn tới after-commit của một transaction thành công**. Không có transaction đang hoạt động, hành động có thể được thực thi ngay như bình thường.

Hệ quả:
- Nếu transaction outer gọi `cache.evict(...)` trước commit, decorator có thể **đăng ký yêu cầu xóa** chứ chưa xóa native cache ngay.
- Khi transaction commit thành công, thao tác xóa được thực hiện trong pha after-commit.
- Nếu transaction rollback, thao tác defer không được thực hiện như một thao tác after-commit của transaction thành công.
- Nếu cache advice bên ngoài gọi put/evict sau khi toàn bộ transaction đã hoàn tất, decorator không còn một transaction đang chạy để trì hoãn, nên có thể thao tác ngay.

**Cực kỳ quan trọng:** các thao tác yêu cầu kết quả tức thời như `putIfAbsent` hoặc `evictIfPresent` không thể trì hoãn như `put/evict/clear`. Với `@Cacheable(sync=true)`, Spring có thể dùng đường `Cache.get(key, Callable)` thay cho put thông thường; phải kiểm tra tính chất của provider/decorator thay vì suy ra mọi thứ đều được defer.

### 6.1. Transaction-aware không đồng nghĩa atomic giữa DB và cache

Ngay cả khi cache eviction chạy trong after-commit, database có thể đã commit xong rồi nhưng cache backend lỗi. Spring cache abstraction không biến hai tài nguyên đó thành một distributed two-phase commit.

Với nghiệp vụ yêu cầu không mất invalidation:
- Thiết kế retry hoặc outbox/event bền vững.
- Gắn version vào cache key để loader cũ không làm ô nhiễm version mới.
- Theo dõi failures của backend và có fallback phù hợp.
- Kiểm tra khả năng stale result bị ghi lại bởi request đã miss **trước eviction**.

Transaction-aware giúp sắp xếp thời điểm, không tự bảo đảm mọi reader trên mọi node thấy trạng thái mới ngay lập tức.

## 7. Trường hợp đặc biệt: transaction bên ngoài và propagation

Xét hai service:

```java
@Service
public class OrderService {
    private final ProductService products;

    public OrderService(ProductService products) {
        this.products = products;
    }

    @Transactional
    public void processOrder(String id) {
        products.updateProduct(id);
        // Còn những bước khác; transaction tổng thể chưa commit.
    }
}
```

Đây là đoạn minh họa phụ thuộc `ProductService`. Giả sử `products.updateProduct` cũng dùng `@Transactional` mặc định (`REQUIRED`), và Cache advice nằm ngoài transaction advice của method con. Method con có thể hoàn thành khi transaction **tổng thể** của `processOrder` vẫn còn. Khi đó cache eviction của method con vẫn có thể diễn ra trước commit transaction ngoài.

Không khắc phục hoàn toàn chỉ bằng đổi `@EnableCaching(order=100)`. Cần xác định:
- Transaction được mở ở đâu, advisor nào bao quanh cuộc gọi cấp cao?
- Method con tham gia transaction hiện hữu hay mở transaction riêng (`REQUIRES_NEW`)?
- Eviction cần xảy ra ngay hay sau commit transaction nào?
- Cache manager có transaction-aware decorator không?
- Có gọi qua Spring proxy của cả outer và inner service không?

Một hướng thiết kế là phát sự kiện nghiệp vụ và thực hiện invalidation trong pha after-commit, chẳng hạn `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` cho synchronous transaction-managed event. Khi yêu cầu độ bền cao xuyên service/process, dùng outbox/queue và retry; callback after-commit trong bộ nhớ không thay thế durable messaging.

## 8. Những gì xảy ra khi exception hoặc commit thất bại

### 8.1. Method ném exception

Ví dụ minh họa:

```java
@Transactional
@CacheEvict(cacheNames = "items", key = "#p0")
public void update(String id) {
    repository.change(id);
    throw new IllegalStateException("failed");
}
```

Với `beforeInvocation=false` mặc định và unchecked exception:
- Spring transaction advice thường rollback theo rule mặc định, trừ khi có cấu hình khác.
- After-success cache eviction **không chạy** vì invocation kết thúc bằng exception.
- Điều này đúng trong hai kiểu lồng advice thông thường, nhưng các side effect ngoài transaction, các advisor khác và provider-specific hành vi cần được phân tích riêng.

### 8.2. Method hoàn thành nhưng commit thất bại

Ví dụ cấu hình transaction ngoài:

```text
TX_BEGIN
  CACHE_MISS
  TARGET_METHOD_RETURNS
  CACHE_PUT
TX_COMMIT_FAIL
```

Nếu cache được ghi ngay và transaction commit thất bại, cache có thể giữ một kết quả không phản ánh DB đã commit. Đây là lý do không thể suy rằng method return thành công là đủ để ghi cache đúng với database.

Với cache ngoài và transaction advice trong (transaction mới):
```text
CACHE_MISS
  TX_BEGIN
  TARGET_METHOD_RETURNS
  TX_COMMIT_FAIL
CACHE_PUT không chạy vì inner advice ném exception
```

Nhưng hãy nhớ ngoại lệ transaction tham gia transaction ngoài ở mục 7: cache bên ngoài method con vẫn có thể ghi trước commit transaction gốc. Transaction-aware decorator và việc đặt đúng transaction boundary thường đáng tin hơn việc chỉ đảo order.

### 8.3. beforeInvocation=true thay đổi thời điểm xóa

```java
@Transactional
@CacheEvict(
    cacheNames = "items",
    key = "#p0",
    beforeInvocation = true
)
public void delete(String id) {
    repository.delete(id);
}
```

Trong cấu hình cache outer, eviction trước invocation có thể xảy ra **trước khi transaction advice bắt đầu**. Trong cấu hình transaction outer, eviction được yêu cầu khi transaction đã bắt đầu nhưng trước target. Nếu có transaction-aware decorator, yêu cầu eviction có thể được trì hoãn, tạo ra semantics khác thao tác native tức thời.

Chỉ dùng `beforeInvocation=true` nếu yêu cầu nghiệp vụ chấp nhận việc cache bị xóa dù method sau đó thất bại hoặc đã kiểm soát được behavior transaction-aware. Không coi nó là tùy chọn “an toàn hơn” mặc định.

## 9. Checklist để cấu hình và xác minh thứ tự

1. **Kiểm tra Spring version** và mode của hai annotation: proxy mặc định hay AspectJ weaving; ví dụ này tập trung proxy mode.
2. **Ghi rõ order** của `@EnableCaching` và `@EnableTransactionManagement` khi cần thứ tự ổn định. Số nhỏ hơn -> advice ở ngoài.
3. **Xác minh thứ tự qua log/test**; không suy từ thứ tự decorator annotations trong source hoặc thứ tự khai báo bean.
4. **Test cache miss:** chụp trace Cache GET, transaction begin, target, cache PUT, commit.
5. **Test cache hit:** bảo đảm có/không có transaction theo yêu cầu, và method có được phép bỏ qua không.
6. **Test eviction sau update:** xác minh `@CacheEvict` chạy khi nào so với commit.
7. **Test exception:** kiểm tra checked/unchecked và rollback rules; xem cache entry trước/sau.
8. **Test commit failure:** cố tình tạo transaction rollback/commit failure với DB thật; xác minh entry không chứa dữ liệu chưa commit.
9. **Test outer transaction:** method con `REQUIRED` có thể tham gia transaction lớn; đừng suy “inner advice xong = physical commit”.
10. **Test transaction-aware cache:** xác nhận cache delegate thực sự chỉ put/evict/clear after-commit khi có transaction synchronization.
11. **Test concurrency:** một request miss trong lúc request khác update/evict; kiểm tra stale put.
12. **Test multiple instances/backend:** hiểu provider-specific propagation, consistency, null policy và transaction behavior.
13. **Test proxy/self-invocation:** `this.update(...)` trong cùng class có thể bỏ qua cả cache và transaction advice ở proxy mode; lấy service qua Spring bean.
14. **Theo dõi metrics:** cache hit/miss, số transaction thực, rollback, lỗi cache backend, tình trạng queue/outbox nếu có.

### 9.1. Câu hỏi nhanh khi debug

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Cache hit vẫn mở transaction | Transaction advice ở ngoài cache advice | So sánh order, trace actual advice |
| Cache hit không mở transaction | Cache advice ở ngoài và trả về trước khi tới transaction | Xác định có bước nghiệp vụ bắt buộc cần transaction không |
| Cache evict trước DB commit | Transaction outer, cache thường, không defer | Đặt order có chủ đích hoặc dùng transaction-aware |
| Đã đặt cache outer mà vẫn evict trước commit | Method tham gia outer transaction chưa commit | Kiểm tra propagation và transaction boundary |
| Cache chứa dữ liệu không commit | Cache put xảy ra trước commit thất bại | Test rollback/commit failure, dùng after-commit policy |
| Evict không xảy ra khi method ném exception | `@CacheEvict` mặc định chỉ sau thành công | Xác minh `beforeInvocation` và rules |
| Evict xảy ra dù method lỗi | `beforeInvocation=true` hoặc thao tác cache ngoài transaction | Xem lại intent và decorator |
| Cấu hình order không tác dụng | Sai context, sai annotation mode, self-invocation hoặc advisor khác | Kiểm tra proxy chain, context và advisor ordering |

## 10. Mô hình tư duy để chọn cách làm

**Nếu mục tiêu là tối ưu hiệu năng đọc** và cache hit không cần transaction: cache advisor bên ngoài thường có lý do. Tuy nhiên, chỉ cân nhắc trên method **thuần đọc**, cache key gắn đầy đủ quyền/tenant, và không có side effect bắt buộc mỗi lời gọi.

**Nếu mục tiêu là cache update gắn với commit dữ liệu**: hãy xem transaction-aware cache, event after-commit và những bảo đảm về retry/độ bền thay vì chỉ trông chờ vào thứ tự annotation.

**Nếu hệ thống có transaction lớn hoặc nested calls**: quyết định invalidation phải căn cứ **transaction thực sự commit**, không chỉ method con kết thúc. Trình tự advice là yếu tố cần kiểm soát nhưng không phải toàn bộ giải pháp consistency.

**Nếu có nhiều advisor khác** như retry/security/async: cần đọc chuỗi thực tế. Một `@Retryable` bên ngoài transaction có thể tạo transaction mới theo mỗi lần thử; `@Async` chuyển thread có thể thay đổi transaction context. Đừng áp dụng nguyên xi sơ đồ hai advisor vào chuỗi nhiều lớp mà chưa kiểm tra.

## 11. Câu hỏi tự kiểm tra

**Q1.** Cache advisor order 100, transaction advisor order 200. Advisor nào ở ngoài?

**Đáp:** Cache advisor, vì số order nhỏ hơn có mức ưu tiên cao hơn.

**Q2.** Với `@Cacheable` cache outer, cache hit có đi vào transaction advisor không?

**Đáp:** Không, nếu CacheInterceptor trả cached result mà không gọi tiếp inner chain.

**Q3.** Với transaction outer và cache thường, khi nào `@CacheEvict(beforeInvocation=false)` xảy ra?

**Đáp:** Sau target method thành công nhưng có thể **trước lúc transaction advice commit**.

**Q4.** Cả hai annotation enabling để mặc định order có nên dựa vào thứ tự tình cờ hiện tại không?

**Đáp:** Không. Cả hai mặc định `LOWEST_PRECEDENCE`; nếu thứ tự quan trọng, hãy cấu hình order khác nhau rõ ràng.

**Q5.** Cache outer có bảo đảm eviction luôn sau database commit không?

**Đáp:** Không; khi method tham gia outer transaction đang hoạt động, inner transaction advice hoàn tất chưa chắc là physical commit của transaction gốc.

**Q6.** `TransactionAwareCacheDecorator` defer những thao tác nào?

**Đáp:** Chủ yếu `put`, `evict` và `clear` đến after-commit khi có Spring-managed transaction phù hợp; những API yêu cầu tác động tức thì như `putIfAbsent` và `evictIfPresent` không được defer tương tự.

**Q7.** Tại sao ghi cache trước commit có thể gây lỗi?

**Đáp:** Transaction có thể fail ở commit, hoặc request khác đọc DB cũ trong khoảng eviction-commit và nạp entry stale.

## 12. Ghi nhớ

- **Cache advice và transaction advice là hai AOP interceptors** có thể nằm ngoài hoặc trong nhau; thứ tự quyết định điểm cache lookup/put/evict so với transaction begin/commit.
- `@EnableCaching(order=...)` và `@EnableTransactionManagement(order=...)` là hai nơi đặt order. **Số nhỏ hơn -> advice ngoài -> chạy trước ở đường vào, sau ở đường ra**.
- **Cache outer:** hit có thể tránh transaction; miss/evict after-invocation thường xử lý sau inner transaction advice.
- **Transaction outer:** hit vẫn có transaction advice; cache put/evict thường diễn ra trước outer commit nếu cache không transaction-aware.
- **Outer transaction có thể đổi toàn bộ mốc commit thật.** Đừng suy từ việc method con trả về thành công.
- `TransactionAwareCacheDecorator` giúp defer put/evict/clear đến after-commit phù hợp, nhưng không phải distributed transaction hoặc cách tự động xóa mọi race condition.
- **Luôn test với transaction manager/database/cache provider thật** khi độ nhất quán có ý nghĩa nghiệp vụ.

### Tài liệu chính thức

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework — @EnableCaching Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/annotation/EnableCaching.html)
- [Spring Framework — @EnableTransactionManagement Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html)
- [Spring Framework — TransactionAwareCacheDecorator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html)
- [Spring Framework — TransactionAwareCacheManagerProxy Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
