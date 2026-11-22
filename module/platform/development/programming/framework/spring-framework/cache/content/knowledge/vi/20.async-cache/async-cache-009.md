# Giới hạn nhiều `cacheNames` và chế độ `sync` với truy xuất bất đồng bộ trong Spring Cache

## 1. Tại sao async caching làm thay đổi cách nghĩ về nhiều cache?

Khi học Spring Cache, ta thường viết một annotation ngắn gọn:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) {
    return repository.load(sku);
}
```

Một `cacheName` chỉ định **một vùng cache**. Với `@Cacheable` thông thường, Spring kiểm tra vùng cache trước khi chạy method thật. Nếu key có sẵn, value được trả về; nếu thiếu, method được chạy và kết quả được đưa vào cache theo hợp đồng của provider.

Tuy nhiên, hai câu hỏi khó hơn xuất hiện trong hệ thống dùng `CompletableFuture`, `Mono` hoặc `Flux`:

1. Điều gì xảy ra nếu `@Cacheable` khai báo **nhiều cache names** nhưng cache miss chỉ được biết **sau khi một future hoàn thành**?
2. Có thể bật `sync=true` để gộp nhiều request cùng key **trong khi dùng nhiều cache names** hay không?

Câu trả lời cốt lõi:

- **Nhiều cache names** là cấu hình hợp lệ trong một số đường caching thông thường, nhưng **không bảo đảm** Spring sẽ dò hết mọi cache khi truy xuất bất đồng bộ có **late-determined cache miss**.
- **`@Cacheable(sync=true)` chỉ hỗ trợ một cache** cho operation đó. Không thể dùng `sync=true` để đồng bộ tải trên nhiều vùng cache trong cùng annotation.
- Cơ chế async và synchronized loading chỉ hoạt động đúng khi **cache provider/adapter hỗ trợ API cần thiết**, không phải cứ method trả `CompletableFuture` là có bảo đảm single-flight giữa mọi node.

Bài này diễn giải những giới hạn của Spring Framework 6.1+ (ví dụ dùng 6.2.9), kèm mô hình luồng thực thi, cấu hình đúng/sai, demo Java 17 và checklist kiểm thử.

## 2. `cacheNames` nhiều vùng có nghĩa gì trong đường đồng bộ?

Một annotation có thể khai báo nhiều cache names:

```java
@Cacheable(
    cacheNames = {"productsFast", "productsShared"},
    key = "#p0"
)
public Product find(String sku) {
    return repository.load(sku);
}
```

Trong đường **truy xuất đồng bộ** thông thường, ý nghĩa tổng quát là Spring xem xét các vùng cache được resolve. Nếu một vùng có value thì có thể dùng value ấy thay vì chạy method. Với những cache không chứa entry, Spring còn có thể cập nhật kết quả khi operation hoàn tất. Hành vi chi tiết phụ thuộc `CacheManager`, `CacheResolver` và provider.

Ví dụ mong đợi với hai vùng trả lời cache lookup tức thời:

```text
productsFast          productsShared          repository
     |                       |                      |
     +-- get(P1) -> miss     |                      |
     |                       +-- get(P1) -> hit      |
     |                       |                      |
     +-- có thể nhận value / cập nhật vùng thiếu      |
     |                       |                      |
     +-- trả value --------- +                      |
                                                  (không gọi)
```

Đây là cách dễ dẫn tới kỳ vọng rằng một annotation nhiều vùng tự động là cơ chế **L1 → L2 fallback**. Nhưng điều đó không phải hợp đồng phổ quát của một hệ thống cache nhiều tầng.

Cần phân biệt:

- **Danh sách `cacheNames`**: nhiều vùng được resolve cho **một caching operation**.
- **`CacheResolver`**: quyết định trả về một hoặc nhiều đối tượng Spring `Cache` dựa trên method và tham số.
- **`CompositeCacheManager`**: chọn một manager có thể cung cấp **tên cache** được hỏi; không tự làm `get(key)` ở L1 rồi fallback `get(key)` ở L2.
- **Multi-tier cache đúng nghĩa**: một implementation có logic hit/miss, nạp từ tầng dưới, backfill, eviction và xử lý lỗi giữa các tầng.

Vì vậy, ngay cả trong đường đồng bộ, dùng nhiều `cacheNames` cũng không thay thế việc thiết kế tính nhất quán của L1/L2, nhất là khi một tầng có thể lưu stale value.

## 3. Late-determined cache miss: giới hạn quan trọng nhất của async

### 3.1. Cache miss được biết ngay hoặc biết sau

Giả sử Spring gọi API truy xuất bất đồng bộ:

```java
java.util.concurrent.CompletableFuture<?> result =
        cache.retrieve("P1");
```

Đoạn trên là **mảnh minh họa**, giả định biến `cache` có kiểu `org.springframework.cache.Cache` và provider hỗ trợ `retrieve`.

Có hai kiểu miss cần phân biệt:

- **Early/immediate miss**: adapter biết ngay key không tồn tại và có thể trả `null` từ chính lời gọi `retrieve(key)`.
- **Late-determined miss**: adapter trả một `CompletableFuture` trước; chỉ khi future hoàn thành, Spring mới biết có value hay là cache miss.

Một provider remote có round trip mạng, ví dụ một số cấu hình `RedisCache`, có thể trả về future vì kết quả tra cứu đến sau. Khi ấy, việc quyết định “chuyển qua cache kế tiếp” không còn đơn giản như gọi nhiều `get` nối tiếp trong cùng stack đồng bộ.

### 3.2. Khi nhiều cache names không được duyệt hết

Xét annotation minh họa:

```java
@Cacheable(
    cacheNames = {"productsRemote", "productsBackup"},
    key = "#p0"
)
public CompletableFuture<Product> findAsync(String sku) {
    return CompletableFuture.supplyAsync(
            () -> repository.load(sku));
}
```

Đây **không** phải một chương trình độc lập; giả định có `Product` và `repository`. Cấu hình này không nhất thiết bị từ chối lúc khởi tạo, nhưng **không được bảo đảm** mang ngữ nghĩa fallback qua hai vùng khi cache thứ nhất trả late miss.

Một tình huống đáng chú ý:

```text
T0  Spring bắt đầu lookup key P1 ở productsRemote
T1  Provider trả CompletableFuture (chưa biết hit hay miss)
T2  Future hoàn thành: MISS
T3  Đường xử lý async có thể chuyển sang load thật,
    KHÔNG nhất thiết tra tiếp productsBackup
T4  repository.load(P1) chạy, dù productsBackup có thể đang chứa P1
```

Điều cần nhớ: **late miss của cache trước có thể khiến những cache names sau không được tham vấn**. Tài liệu Spring Cache cảnh báo rõ async/reactive access không nhất thiết hỗ trợ đầy đủ việc tra qua tất cả cache được khai báo; khi gặp late-determined miss, nên dùng **một cache name** cho operation.

Đây là giới hạn về hợp đồng lookup, không nhất thiết là lỗi Redis và cũng không phải mọi provider đều có hành vi giống nhau. Provider local có thể xác định miss sớm; provider remote có thể cần future. Khi đổi provider hoặc phiên bản, đường thực thi phải được kiểm thử lại.

### 3.3. Điều không nên kết luận từ một bài test

Nếu test với local `ConcurrentMapCache` và thấy `productsBackup` được hỏi, không thể suy ra Redis async cũng duyệt vùng thứ hai. Nếu test `productsRemote` đã có cache hit, cũng không chứng minh hệ thống xử lý đúng **late miss**.

Muốn kiểm tra giới hạn, phải dựng đúng tình huống: cache thứ nhất mất key, nhưng hoàn thành lookup **bất đồng bộ**, trong khi cache thứ hai đã có value. Đo số lượt truy xuất từng vùng và số lần loader thực thi, không chỉ so sánh kết quả cuối.

## 4. `sync=true`: synchronized loading và ba giới hạn bắt buộc

### 4.1. `sync=true` thực sự yêu cầu gì?

`@Cacheable(sync=true)` yêu cầu Spring sử dụng cơ chế **synchronized cache loading** nếu implementation hỗ trợ. Mục đích là giảm việc nhiều caller cùng key cache miss rồi tất cả đều chạy nguồn dữ liệu tốn kém (cache stampede).

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public CompletableFuture<Product> findAsync(String sku) {
    return CompletableFuture.supplyAsync(
            () -> repository.load(sku));
}
```

Nếu provider hỗ trợ cơ chế lấy-or-tải atomic theo key, nhiều caller cùng `P1` có thể nhận các future tương ứng với cùng một load. Việc gọi nguồn chỉ một lần được kỳ vọng ở **phạm vi provider bảo đảm**, thường là một cache instance/JVM với local cache.

**Không có cam kết khóa phân tán toàn cluster chỉ vì đặt `sync=true`.** Hai application instance có cache riêng vẫn có thể cùng gọi repository.

### 4.2. Ba giới hạn của `@Cacheable(sync=true)`

Theo hợp đồng `@Cacheable` của Spring Framework:

| Giới hạn | Hệ quả |
| --- | --- |
| Không hỗ trợ `unless` | Không kết hợp synchronized caching với điều kiện veto sau khi method trả kết quả |
| Chỉ một cache được resolve cho operation | Không khai báo nhiều `cacheNames` khi dùng `sync=true` |
| Không kết hợp với caching operations khác trên cùng method | Không ghép `@CachePut`, `@CacheEvict` hoặc `@Cacheable` khác vào method synchronized |

Ba ví dụ **không hợp lệ** (chỉ để nhận diện lỗi; không đưa vào code demo chạy):

**Sai 1 — `sync=true` và nhiều vùng:**

```java
@Cacheable(
    cacheNames = {"productsFast", "productsShared"},
    key = "#p0",
    sync = true
)
public CompletableFuture<Product> findAsync(String id) {
    return serviceLoad(id);
}
```

Spring không thể triển khai đồng bộ hóa nạp trên một tập nhiều cache cho một operation `sync=true` theo contract này.

**Sai 2 — `sync=true` và `unless`:**

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true,
    unless = "#result == null"
)
public CompletableFuture<Product> findAsync(String id) {
    return serviceLoad(id);
}
```

`unless` cần quan sát kết quả sau khi method thực thi rồi quyết định không ghi cache. Đường synchronized loading giao việc phối hợp lookup và load cho provider nên Spring không hỗ trợ kiểu veto này.

**Sai 3 — ghép operation khác vào method synchronized:**

```java
@Caching(
    cacheable = @Cacheable(cacheNames = "products", sync = true),
    evict = @CacheEvict(cacheNames = "lists", allEntries = true)
)
public CompletableFuture<Product> findAsync(String id) {
    return serviceLoad(id);
}
```

Nếu cần evict hay update cache khác, đặt operation đó trên method riêng hoặc giải quyết ở workflow ghi dữ liệu. `@Caching` cũng không biến tổ hợp không hỗ trợ thành hợp lệ.

### 4.3. `condition` khác `unless`

`condition` của `@Cacheable` được đánh giá **trước** khi gọi method, có thể lọc theo input:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null",
    sync = true
)
public CompletableFuture<Product> findAsync(String id) {
    return serviceLoad(id);
}
```

Đây là mảnh minh họa trong một service giả định. Khi `condition` false, caching bị bỏ qua; method có thể chạy ở mỗi lời gọi nên `sync=true` không còn giúp gộp các lời gọi đó. `condition` không thể kiểm tra `#result` vì kết quả chưa tồn tại tại thời điểm đánh giá.

## 5. Ma trận các tổ hợp được phép và giới hạn thực tế

| Cấu hình | Hợp lệ về cấu hình? | Điều cần chú ý |
| --- | --- | --- |
| Một `cacheName`, `sync=false`, method đồng bộ | Có | Lookup và put thông thường; cache miss đồng thời có thể gọi loader trùng |
| Nhiều `cacheNames`, `sync=false`, method đồng bộ | Có | Có thể kiểm tra nhiều cache khi lookup trả ngay; tính nhất quán giữa vùng vẫn do thiết kế |
| Một `cacheName`, `sync=false`, `CompletableFuture<T>` | Có với Spring 6.1+ và provider phù hợp | Future completion được thích ứng; async retrieve có thể miss muộn |
| Nhiều `cacheNames`, `sync=false`, `CompletableFuture<T>` | Có thể khai báo, **không bảo đảm fallback đủ** | Late-determined miss có thể ngăn tham vấn cache sau |
| Một `cacheName`, `sync=true`, method đồng bộ | Có nếu provider hỗ trợ | Synchronized loading được delegate cho provider |
| Một `cacheName`, `sync=true`, `CompletableFuture<T>` | Có khi provider hỗ trợ async loading | Phải test `retrieve(key, supplier)`/single-flight thực tế |
| Nhiều `cacheNames`, `sync=true` | **Không hỗ trợ** | Vi phạm giới hạn một cache của `@Cacheable(sync=true)` |
| Một cache, `sync=true` kèm `unless` | **Không hỗ trợ** | Veto sau khi load không nằm trong đường synchronized |
| Một cache, `sync=true` ghép `@CachePut`/`@CacheEvict` | **Không hỗ trợ** | Cần tách operation ra method khác |

Như vậy, **bỏ `sync=true` không tự sửa mọi vấn đề nhiều cacheNames**; cấu hình nhiều vùng có thể vẫn gặp late miss khi async. Ngược lại, **bật `sync=true` không biến nhiều vùng thành một kho có khóa chung**.

## 6. Spring `Cache.retrieve` và những hợp đồng async cần provider đáp ứng

Spring Framework 6.1 bổ sung phương thức retrieval bất đồng bộ trên `org.springframework.cache.Cache`:

```java
CompletableFuture<?> retrieve(Object key);

<T> CompletableFuture<T> retrieve(
        Object key,
        java.util.function.Supplier<CompletableFuture<T>> valueLoader);
```

Đây là **chữ ký API** để giải thích, không phải chương trình độc lập.

### 6.1. `retrieve(key)` — truy xuất thuần

`retrieve(key)` có thể báo miss ngay bằng cách trả `null` nếu provider biết sớm không có key. Hoặc nó có thể trả một `CompletableFuture` rồi báo hit/miss khi future hoàn thành.

Trong trường hợp cần biểu diễn **cached null**, adapter có thể dùng `Cache.ValueWrapper` thay vì nhầm với “không có entry”; các quy ước unwrap cần theo đúng Javadoc/provider. Không mặc định cả “null wrapper”, “future hoàn thành với null” và “cached null” là một trường hợp.

```text
retrieve(P1)
   |
   +-- null ngay ---------------------> cache miss sớm
   |
   +-- CompletableFuture<?> ---------> kết quả đến sau
            |
            +-- value ----------------> hit
            +-- null -----------------> miss muộn
            +-- ValueWrapper(null) ---> cached-null (nếu hỗ trợ)
```

### 6.2. `retrieve(key, valueLoader)` — lấy hoặc tải

Đường combined retrieve/load nhận callback tạo `CompletableFuture<T>` khi key thiếu. Đối với `@Cacheable(sync=true)` với giá trị bất đồng bộ, Spring cần cache provider thực hiện hợp đồng kết hợp này tương ứng. Kỳ vọng synchronized load/single-flight phải đến từ implementation, không suy ra chỉ từ tên API.

Mảnh minh họa:

```java
CompletableFuture<Product> product =
    cache.retrieve("P1", () -> CompletableFuture.supplyAsync(
        () -> repository.load("P1")
    ));
```

Đây là API gọi trực tiếp khi có biến `cache` và `repository` phù hợp. **Không** đưa nguyên cả callback này vào method đã gắn `@Cacheable` rồi tự gọi lại cùng cache, vì có thể tạo vòng lặp hoặc double caching.

Một số provider/adapter chỉ hỗ trợ retrieval đồng bộ hoặc không hỗ trợ đường `retrieve`; chúng có thể ném `UnsupportedOperationException`. Bật `@Cacheable(sync=true)` không thay thế việc chọn provider đúng và kiểm thử phiên bản cụ thể.

### 6.3. Value đã cache là gì khi method trả Future?

Với async adaptation của Spring Framework 6.1+, ý tưởng là cache **giá trị kết quả sau completion**, không mặc nhiên coi chính object `CompletableFuture` đang pending là data nghiệp vụ để các caller khác đọc và ép kiểu. Adapter/manager chịu trách nhiệm chuyển đổi giữa contract Spring và native cache.

Vì vậy cần tránh nghĩ rằng `CompletableFuture<Product>` và `Product` là hai kiểu có thể tùy ý dùng chung region. Khi nhiều method chia sẻ cache, chúng phải dùng cùng contract key/value và cùng cách unwrap.

## 7. Ví dụ chạy được: Java 17 + Spring 6.2.9 + Caffeine async

Ví dụ sử dụng một vùng `products` và `sync=true`. Tám caller đồng thời gọi một key chưa có; sau đó chương trình kiểm tra hit, key khác và evict.

Dùng **`CaffeineCacheManager#setAsyncCacheMode(true)`** để Spring có native async cache hỗ trợ `retrieve`. Đây là cấu hình của Spring Framework thuần; không cần Spring Boot.

### 7.1. Cấu trúc thư mục

```text
async-sync-cache-demo/
├── pom.xml
└── src/main/java/AsyncSyncCacheDemo.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-sync-cache-demo</artifactId>
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
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
            <version>3.1.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. `src/main/java/AsyncSyncCacheDemo.java`

```java
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class AsyncSyncCacheDemo {

    @Bean
    CaffeineCacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("products");

        manager.setAllowNullValues(false);
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(500)
                .expireAfterWrite(Duration.ofMinutes(5)));
        manager.setAsyncCacheMode(true);
        return manager;
    }

    @Bean
    ProductService productService() {
        return new ProductService();
    }

    public static class ProductService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0", sync = true)
        public CompletableFuture<String> findAsync(String sku) {
            return CompletableFuture.supplyAsync(() -> {
                int loadId = loads.incrementAndGet();

                try {
                    Thread.sleep(150);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                            "Interrupted during cache load", ex);
                }
                return sku + "#load" + loadId;
            });
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void evict(String sku) {
            // Spring interceptor thực hiện eviction.
        }

        public int loads() {
            return loads.get();
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                        AsyncSyncCacheDemo.class)) {

            ProductService service =
                    context.getBean(ProductService.class);

            int callers = 8;
            ExecutorService executor =
                    Executors.newFixedThreadPool(callers);
            CountDownLatch ready = new CountDownLatch(callers);
            CountDownLatch start = new CountDownLatch(1);

            try {
                List<Future<CompletableFuture<String>>> submitted =
                        new ArrayList<>();

                for (int i = 0; i < callers; i++) {
                    submitted.add(executor.submit(() -> {
                        ready.countDown();
                        start.await();
                        return service.findAsync("P1");
                    }));
                }

                ready.await();
                start.countDown();

                List<CompletableFuture<String>> stages =
                        new ArrayList<>();
                for (Future<CompletableFuture<String>> f : submitted) {
                    stages.add(f.get());
                }

                CompletableFuture.allOf(
                        stages.toArray(new CompletableFuture[0]))
                        .join();

                Set<String> distinctValues = new HashSet<>();
                for (CompletableFuture<String> f : stages) {
                    distinctValues.add(f.join());
                }

                System.out.println("distinct values: "
                        + distinctValues.size());
                System.out.println("value: "
                        + distinctValues.iterator().next());
                System.out.println("loads after 8 callers: "
                        + service.loads());

                System.out.println("P1 repeat: "
                        + service.findAsync("P1").join());
                System.out.println("loads after P1 repeat: "
                        + service.loads());

                System.out.println("P2 first: "
                        + service.findAsync("P2").join());
                System.out.println("loads after P2: "
                        + service.loads());

                service.evict("P1");
                System.out.println("P1 after evict: "
                        + service.findAsync("P1").join());
                System.out.println("loads final: "
                        + service.loads());
            } finally {
                start.countDown();
                executor.shutdownNow();
            }
        }
    }
}
```

### 7.4. Chạy Maven

Trong thư mục chứa `pom.xml`, dùng JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=AsyncSyncCacheDemo
```

**Các dòng stdout mong đợi của chính chương trình** với cấu hình provider trong ví dụ (không tính log Maven/Spring nếu có):

```text
distinct values: 1
value: P1#load1
loads after 8 callers: 1
P1 repeat: P1#load1
loads after P1 repeat: 1
P2 first: P2#load2
loads after P2: 2
P1 after evict: P1#load3
loads final: 3
```

### 7.5. Vì sao ví dụ này kiểm chứng đúng điều cần học?

- `@EnableCaching` bật caching advice; service là Spring bean và được lấy từ context, **không** gọi `this.findAsync(...)` trong cùng bean.
- `CaffeineCacheManager("products")` ở static mode tạo một vùng cache duy nhất.
- `setAsyncCacheMode(true)` cho phép adapter sử dụng async cache, còn `setAllowNullValues(false)` tránh cách biểu diễn null khó hiểu trong đường async.
- `CountDownLatch` giúp tám task bắt đầu cùng lúc. `Thread.sleep(150)` làm lần nạp nguồn đủ dài để quan sát các caller cạnh tranh.
- `AtomicInteger` đếm **số lần loader thật chạy**, chứ không chỉ đếm các kết quả trả về. Tập `distinctValues` có một phần tử vì cùng một key nhận cùng kết quả.
- `P2` là key khác, phải được nạp riêng. `@CacheEvict` nằm trên **method khác**, không vi phạm giới hạn không ghép operations với `@Cacheable(sync=true)`.
- Ví dụ chỉ minh họa **một JVM và một provider cụ thể**, không chứng minh single-flight trên nhiều process hoặc Redis cluster.

Nếu chạy trên provider khác mà số lần load lớn hơn một, hãy kiểm tra đúng implementation `Cache.retrieve(key, supplier)`, cách tạo cache instance và cách các request phân chia key; đừng chỉ dựa vào annotation để kết luận.

## 8. CompletableFuture, Mono và Flux: bất đồng bộ không giống streaming

### 8.1. `CompletableFuture<T>`

Spring Framework 6.1+ có thể thích ứng cache abstraction với method trả `CompletableFuture<T>`: cache biết kết quả sau khi future hoàn thành. Khi lưu ý về nhiều `cacheNames`, cần xem xét **cơ chế lookup của provider**, không chỉ kiểu trả về của service.

Lời gọi `findAsync("P1")` có thể trả future rất nhanh, trong khi truy vấn nguồn vẫn chạy. Nếu cache lookup hoàn thành muộn, kế hoạch chuyển sang cache khác có thể không thực hiện như mong đợi.

### 8.2. Reactor `Mono<T>`

Khi có Reactor trên classpath, Spring 6.1+ cũng hỗ trợ các phương thức trả `Mono<T>` bằng cách thích ứng qua future. `Mono` thường đại diện không quá một value; cần kiểm tra empty completion, null policy, lỗi và đúng adapter cache.

Mảnh minh họa (không thuộc chương trình độc lập mục 7):

```java
@Cacheable(cacheNames = "products", key = "#p0")
public reactor.core.publisher.Mono<Product> findReactive(String id) {
    return repository.findReactive(id);
}
```

Không suy ra chỉ vì code reactive là Spring sẽ duyệt mọi `cacheNames` hay tự có distributed lock.

### 8.3. Reactor `Flux<T>`

Với `Flux<T>` hữu hạn, cache abstraction của Spring có thể **thu thập toàn bộ phần tử thành một List** để lưu kết quả rồi phục hồi publisher ở các lượt sau. Điều này khác hoàn toàn caching từng event trong một stream.

Vì thế, không dùng `@Cacheable` kiểu này cho event stream **vô hạn** hoặc quá lớn: bộ nhớ và độ trễ có thể tăng mạnh. Ngoài ra, khi publisher fail hoặc bị cancel giữa chừng, cần test semantics của adapter, không khẳng định các phần tử trung gian đã được lưu.

### 8.4. Không đồng nhất `@Async` với async caching

`@Async` là cơ chế thực thi method trên executor. `@Cacheable` là cơ chế lưu/truy xuất kết quả. Kết hợp cả hai cần xét thứ tự proxy/advisor và kiểu trả về; việc một method dùng `@Async` **không tự** bảo đảm `Cache.retrieve` được provider hỗ trợ.

Đối với mục tiêu chỉ cần `CompletableFuture`, ví dụ ở mục 7 dùng `CompletableFuture.supplyAsync` và không cần `@Async` để tránh chồng hai abstraction.

## 9. Khả năng của provider quyết định kết quả thực tế

| Provider/manager | Đặc điểm cần kiểm tra |
| --- | --- |
| `ConcurrentMapCacheManager` | Local JVM; Spring hỗ trợ cơ chế retrieval thích ứng, nhưng không chia sẻ cache giữa process |
| `CaffeineCacheManager` | Local JVM; dùng `setAsyncCacheMode(true)` cho native Caffeine AsyncCache và các overload `retrieve` |
| `RedisCacheManager` | Remote/network; cache miss có thể được xác định muộn; phải kiểm tra hỗ trợ async retrieval và semantics khóa của **phiên bản adapter** |
| JCache hoặc custom `Cache` adapter | Không mặc định có đầy đủ `retrieve`; đọc code/Javadoc và test chức năng |
| Multi-tier/cache decorator tự viết | Phải định nghĩa rõ thứ tự tầng, cách backfill, stale value, null, exception, TTL và concurrency |

Không phải mọi `CacheManager` đều có cùng sự hỗ trợ cho `retrieve`, `sync=true` và async. Ngay cả khi API tồn tại, synchronized loading là một **hợp đồng phụ thuộc implementation**. Cần biết single-flight có phạm vi một `Cache` object, một JVM, một client hay toàn cluster.

Ví dụ, dùng một vùng Redis làm remote cache không tự thêm khóa phân tán cho method body. Nếu mục tiêu là chặn cache stampede giữa các node, cần chiến lược điều phối phù hợp như provider có atomic loader/lock thực sự hoặc distributed single-flight có timeout và recovery; không coi `sync=true` là một mutex toàn cầu.

### 9.1. Null và future thất bại

Với async caching, có thể có một future hoàn thành với value, null, hoặc hoàn thành **exceptionally**. Cần test:

- Value `null` có được provider cache không và Spring xử lý wrapper ra sao?
- Với `sync=true` không dùng `unless` để loại trừ null; nếu provider không cho null, chọn kiểu giá trị khác hoặc giải pháp phù hợp.
- Khi loader fail, caller chờ cùng key nhận lỗi gì? Entry đang tải có được xóa/cho retry không?
- Khi timeout mạng, liệu lời gọi đã ghi cache nhưng client chưa nhận được response không?
- Khi caller cancel future, provider có làm hỏng shared loading cho các caller khác không?

Đừng dùng future completion thành công/không thành công để tự kết luận rằng cache đã được ghi hoặc xóa trước khi transaction database commit.

## 10. Thiết kế thay thế khi cần nhiều tầng cache và async

Nếu yêu cầu sản phẩm là **L1 Caffeine local, L2 Redis remote, cuối cùng DB/API**, nên thiết kế một hợp đồng rõ ràng hơn là phụ thuộc vào danh sách `cacheNames` bất đồng bộ.

### 10.1. Một logical cache, nhiều tầng bên trong

Một cách là xây **một** Spring `Cache` adapter logical tên `products`; adapter nội bộ thực hiện:

```text
Application
   |
   +-- Spring Cache("products")
           |
           +-- L1 Caffeine get(P1)
           |      |
           |      +-- HIT -> return
           |      +-- MISS
           |
           +-- L2 Redis async get(P1)
           |      |
           |      +-- HIT -> backfill L1 -> return
           |      +-- MISS
           |
           +-- repository load(P1)
                  |
                  +-- put L2 và L1 theo policy
                  +-- return
```

Adapter này phải có logic `retrieve(key)`, `retrieve(key, supplier)`, `put`, `evict` và null/error policy đúng. Với `sync=true`, operation Spring vẫn nhìn thấy **một logical cache**, dù bên trong adapter có nhiều tầng. Nhưng khả năng synchronized loading theo key và phạm vi khóa **phải được adapter cài đặt thực sự**.

Đây là **phương án kiến trúc**, không có nghĩa Spring tự tạo đúng adapter này khi khai báo `CompositeCacheManager` hoặc `cacheNames={"l1","l2"}`.

### 10.2. Chỉ một provider cho mỗi method

Nếu không cần L1/L2, giải pháp đơn giản và dễ kiểm soát hơn là chọn một vùng cache phù hợp:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public CompletableFuture<Product> findAsync(String sku) {
    return repository.findAsync(sku);
}
```

Đoạn trên là mảnh minh họa. Nếu muốn `sync=true`, kiểm tra provider hỗ trợ async retrieve-and-load rồi bật `sync` với **một** cache.

### 10.3. CacheResolver không tự giải quyết late miss

`CacheResolver` chọn những cache nào được dùng cho operation dựa trên context. Nó không mặc nhiên định nghĩa state machine để đợi một future remote hoàn thành rồi tự chuyển qua vùng kế tiếp.

Muốn có fallback thực sự, phải viết logic ở một lớp/service/adapter riêng hoặc sử dụng cache provider có multi-tier contract được kiểm chứng. Khi tự viết, cần test cả hit, early miss, late miss, lỗi, timeout và update/eviction giữa các tầng.

### 10.4. Tính nhất quán và key

Trong mọi thiết kế, key cần bao gồm tất cả yếu tố làm thay đổi kết quả, ví dụ tenant, currency, locale, query filters và authorization context nếu thực sự ảnh hưởng dữ liệu. Nếu hai request cùng SKU nhưng khác tenant, không được gộp vào một load hoặc dùng chung entry.

Nếu L1 và L2 có TTL khác nhau, L1 có thể giữ stale value sau khi DB/L2 thay đổi. Cần chiến lược invalidation hoặc chấp nhận mức nhất quán đã được sản phẩm phê duyệt. `sync=true` chỉ giải quyết tải cạnh tranh trên cache miss, **không** tự giải quyết read–update race.

## 11. Các lỗi thường gặp

1. **Nghĩ nhiều `cacheNames` luôn là L1/L2 fallback.** Với late async miss, cache phía sau có thể không được tham vấn.
2. **Bật `sync=true` trên nhiều cache names.** Vi phạm trực tiếp giới hạn một cache của `@Cacheable`.
3. **Kết hợp `sync=true` với `unless`.** Spring không hỗ trợ veto kết quả trên synchronized cache operation.
4. **Ghép `@CacheEvict` hoặc `@CachePut` vào cùng method `sync=true`.** Tách method và operation riêng.
5. **Tin rằng `sync=true` bảo đảm một loader trên nhiều JVM.** Phạm vi atomicity phụ thuộc provider và topology.
6. **Giả định mọi `Cache` đều hỗ trợ `retrieve`.** Custom adapter có thể không triển khai async retrieval.
7. **Chỉ test cache hit hoặc immediate miss.** Phải có test late-determined miss khi dùng remote async cache.
8. **Không đếm số lần gọi nguồn.** Nhiều caller có thể trả cùng value dù loader bị thực thi nhiều lần.
9. **Nhầm `@Async` với async caching.** Một cái điều phối executor, cái kia quản lý cache lookup/storage.
10. **Lưu publisher thay vì kết quả hữu hạn.** Với `Flux` dài hoặc vô hạn, thu thập thành List có thể gây quá tải.
11. **Sai key giữa các method hoặc các tầng.** Kết quả stale/cross-tenant quan trọng hơn tối ưu hit rate.
12. **Bỏ qua null hoặc exception.** Async future có thể hoàn thành null/exceptionally; loader failures cần retry policy phù hợp.
13. **Trộn Spring Cache với native API provider thiếu kiểm soát.** Có thể bỏ qua null adaptation, decorators và metrics.
14. **Coi `CompositeCacheManager` là cache hai tầng theo key.** Nó xử lý lựa chọn manager, không tự backfill và fallback.
15. **Không test sau nâng cấp Spring/provider.** Async adaptation, retrieval và eviction có thể thay đổi theo version.

## 12. Kiểm thử và checklist trước khi triển khai

| Ca thử | Điều cần quan sát |
| --- | --- |
| Một cache, một key, nhiều caller | Loader chạy bao nhiêu lần với `sync=true`? |
| Một cache, hai key khác nhau | Hai load có thể độc lập, không dùng chung value? |
| Multi-name, cache đầu trả early miss | Các cache phía sau có được hỏi không? |
| Multi-name, cache đầu trả **late miss** | Có bỏ qua cache sau và chạy nguồn không? |
| Multi-name, cache đầu hit | Có tránh gọi nguồn thật không? |
| Cache provider không hỗ trợ `retrieve` | Có lỗi rõ ràng thay vì fallback thầm lặng không? |
| CompletableFuture trả null | Null entry được xử lý theo provider policy nào? |
| Future hoàn thành exceptionally | Caller nhận lỗi gì? Có bị kẹt entry đang load? |
| Evict trong lúc load | Có race đưa stale value trở lại cache không? |
| Request đến từ hai JVM | Single-flight chỉ local hay thực sự cross-node? |
| L1 và L2 khác TTL | Có đọc stale value hoặc sai quy tắc invalidation không? |
| Reactive Flux nhiều phần tử | Có thu thập/tiêu thụ bộ nhớ ngoài dự kiến không? |

### Checklist vận hành

1. Xác định **đúng Spring version** và cache adapter/provider version đang chạy.
2. Với async/reactive method, ưu tiên **một cache name** trên một caching operation.
3. Nếu bật `sync=true`, bảo đảm **một cache**, không `unless`, không ghép caching operation.
4. Kiểm tra `Cache.retrieve(key)` và `retrieve(key, supplier)` của provider; không giả định mọi implementation giống nhau.
5. Tạo test **late-determined miss** thay vì chỉ test local in-memory cache.
6. Đo loader count, cache hit/miss, lookup latency, số caller chờ, timeout và exception.
7. Xác nhận khóa/key có phạm vi đúng đối với tenant/filter/permission.
8. Với multi-node, đo hiệu quả từng process và cross-node riêng.
9. Nếu cần L1/L2, dùng một adapter/strategy có hợp đồng rõ ràng về fallback, backfill và invalidation.
10. Kiểm thử load–update race, eviction, TTL, rollback và các lỗi mạng.

## 13. Kết luận

Bốn nguyên tắc giúp tránh lỗi khi thiết kế Spring Cache bất đồng bộ:

- **Một cache name** là lựa chọn có tính dự đoán cao nhất cho một operation async/reactive.
- **Nhiều cache names với `sync=false`** có thể được khai báo nhưng không bảo đảm mọi vùng được tra cứu khi miss đến muộn.
- **`sync=true` có giới hạn nghiêm ngặt**: chỉ một cache, không `unless` và không ghép operation khác trên cùng method.
- **Single-flight thật là khả năng của provider**; hãy xác minh qua `retrieve`, số lần loader và test đồng thời, đặc biệt khi triển khai nhiều JVM.

Nếu cần cả async, single-flight và L1/L2, hãy xem đó là một **thiết kế cache đa tầng cần cài đặt và kiểm thử rõ ràng**, chứ không chỉ là việc liệt kê nhiều tên trong `cacheNames`.

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 — Cache annotations, `@Cacheable`, Synchronized Caching, async/reactive: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework 6.2.9 — `@Cacheable` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework 6.2.9 — `Cache.retrieve` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework 6.2.9 — `CaffeineCacheManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework — Cache Store Configuration: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
