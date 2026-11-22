# Giới hạn TTL và dung lượng của cài đặt ConcurrentMap cơ bản trong Spring Cache

## Mục tiêu học tập

Spring Cache cung cấp một cách khai báo cache rất thuận tiện bằng `@Cacheable`, `@CachePut`, `@CacheEvict` và `CacheManager`. Với ứng dụng mới, Spring Boot thường có thể dùng nhà cung cấp **Simple**, dựa trên `ConcurrentMapCacheManager` và `ConcurrentMapCache`. Cách này nhanh, ít phụ thuộc, phù hợp để học hoặc kiểm thử. Tuy nhiên, nó **không có TTL, TTI, giới hạn số entry hoặc chính sách loại bỏ vì đầy bộ nhớ** như những cache provider chuyên dụng.

Sau bài học, bạn sẽ:

1. Hiểu cấu trúc và vòng đời của `ConcurrentMapCacheManager`, `ConcurrentMapCache` và `ConcurrentHashMap`.
2. Phân biệt **không có TTL tự động** với **vẫn có thể xóa thủ công** qua cache API hoặc `@CacheEvict`.
3. Hiểu tại sao số key tăng không giới hạn có thể giữ bộ nhớ JVM và gây nguy cơ OOM.
4. Biết những tùy chọn như `setCacheNames`, `setAllowNullValues` không phải TTL hoặc capacity.
5. Chạy ví dụ **Java 17 + Spring Boot 3.3.5** chứng minh cache giữ giá trị cũ sau khi chờ, tăng số entry và được xóa chủ động.
6. Chuyển sang Caffeine khi cần `maximumSize`, `maximumWeight`, `expireAfterWrite` hay `expireAfterAccess`.
7. Kiểm thử, đo lường và quyết định khi nào giữ ConcurrentMap đơn giản, khi nào phải thay provider.

**Ý chính:** Spring Cache abstraction không quy định tuổi thọ hoặc kích thước cache. Chính sách này phải đến từ implementation bên dưới. Đừng xem `@Cacheable` là cam kết rằng một entry sẽ tự hết hạn.

## 1. `ConcurrentMapCacheManager` lưu dữ liệu ở đâu?

`ConcurrentMapCacheManager` là `CacheManager` của Spring Framework, tạo và quản lý các `ConcurrentMapCache`. Mỗi cache có một vùng dữ liệu được hỗ trợ bởi `ConcurrentMap`, thường là `ConcurrentHashMap` trong bộ nhớ của **tiến trình JVM hiện tại**.

~~~text
Spring-managed service
  @Cacheable(cacheNames = "prices", key = "#p0")
               |
               v
        Spring Cache interceptor
               |
               v
       ConcurrentMapCacheManager
               |
               +-- ConcurrentMapCache "prices"
               |       |
               |       +-- "P1" -> 100
               |       +-- "P2" -> 200
               |
               +-- ConcurrentMapCache "products"
                       |
                       +-- "P1" -> Product(...)
~~~

`CacheManager` phân giải **tên cache**. `Cache` phân giải **key**. Hai request chỉ dùng chung entry khi chúng đi qua cùng cache instance với key tương thích. Mỗi tên cache thường có map riêng. Nếu có hai JVM chạy cùng một ứng dụng, mỗi tiến trình tạo `ConcurrentMapCacheManager` và map riêng; đó không phải distributed cache.

### Lợi ích của cách triển khai đơn giản

- Có sẵn trong hệ sinh thái Spring, ít cấu hình.
- `ConcurrentHashMap` hỗ trợ truy cập đồng thời nhiều thread với hiệu năng tốt.
- Phù hợp với demo nhỏ, test, thử nghiệm annotation và tập dữ liệu nhỏ, hữu hạn.
- Không cần chạy Redis hay thêm Caffeine chỉ để học các khái niệm caching.
- Khi context/JVM kết thúc, cache trong bộ nhớ cũng biến mất.

### Giới hạn quan trọng

- **Không có TTL**: một entry không tự hết hạn sau 30 giây, 5 phút hay 1 ngày.
- **Không có TTI**: không có cấu hình tự xóa sau một thời gian không truy cập.
- **Không có `maximumSize`**: map không tự giới hạn ở 1.000 hoặc 10.000 entry.
- **Không có `maximumWeight` hay ngân sách byte**: entry có thể giữ một object graph lớn.
- **Không có chính sách LRU/LFU tự động**: khi số entry tăng, provider không tự loại key cũ để bảo vệ heap.
- **Không có persistence hay chia sẻ giữa JVM**: restart sẽ mất cache; replica khác có cache khác.

`ConcurrentHashMap` hỗ trợ concurrent access; từ “Concurrent” **không có nghĩa** nó cung cấp timeout, eviction hay distributed coordination. Đây là những trục tính năng khác nhau.

## 2. Hai loại giới hạn: tuổi dữ liệu và dung lượng

### TTL: Time To Live

TTL là thời hạn một entry còn được xem là hợp lệ. Trong cache chuyên dụng, ta có thể đặt ví dụ “hết hạn sau 120 giây kể từ lần ghi”.

~~~text
T=00:00:00  put P1=100
T=00:01:00  get P1 -> HIT
T=00:02:10  get P1 -> MISS nếu TTL là 120 giây
~~~

Với `ConcurrentMapCache` cơ bản, **không có bộ đếm TTL tương ứng**. Nếu không có ai chủ động xóa hoặc thay entry, lời gọi tại `T=00:02:10` vẫn có thể hit giá trị cũ. Chờ `Thread.sleep(120_000)` không khiến map tự biết phải expire dữ liệu.

Một số hệ thống đưa timestamp vào **key** để tạo một key mới mỗi khoảng thời gian. Đó **không phải TTL của map**: entry với key cũ vẫn còn trong map, tiếp tục chiếm bộ nhớ cho tới khi bị xóa hoặc tiến trình kết thúc. Đây thường là giải pháp nguy hiểm vì số key có thể phình ra liên tục.

### TTI: Time To Idle

TTI (time-to-idle), còn gọi là expiration sau truy cập, giới hạn thời gian kể từ lần access cuối. Nó khác với TTL sau ghi:

| Chính sách | Mốc đo tuổi | Hành vi |
| --- | --- | --- |
| TTL/expire-after-write | Lần ghi/tạo entry | Đọc nhiều lần không tự kéo dài thời hạn |
| TTI/expire-after-access | Lần truy cập gần nhất | Key nóng có thể sống lâu vì luôn được truy cập |
| Không expiration | Không có mốc | Entry còn tới khi bị evict/clear/overwrite hoặc context kết thúc |

Không có hai chính sách đầu trong `ConcurrentMapCache` cơ bản. Nếu nghiệp vụ yêu cầu “dữ liệu không cũ quá 5 phút”, hãy chọn backend có TTL theo write hoặc triển khai invalidation đáng tin, không dùng TTI để thay thế yêu cầu độ mới tuyệt đối.

### Capacity: giới hạn số entry hoặc trọng số

~~~text
Cache name = "prices"
"P1" -> 100
"P2" -> 200
"P3" -> 300
...
"P1000000" -> 999999
~~~

`ConcurrentMapCache` có thể tiếp tục giữ nhiều key khác nhau. Nó không có `maximumSize(1000)` như Caffeine, cũng không theo dõi tổng trọng số value để tự evict. Khi bộ nhớ không đủ, ứng dụng có thể chịu áp lực GC, thời gian phản hồi xấu đi hoặc gặp `OutOfMemoryError`.

Giới hạn số entry và giới hạn byte là hai điều khác nhau:

~~~text
Ước lượng bộ nhớ giữ lại
    ≈ số entry × (trọng số key + trọng số value + overhead)
~~~

Đây chỉ là ước lượng để tư duy. Kích thước object graph Java còn phụ thuộc object header, references, alignment, collection internals và cách giữ đối tượng ở nơi khác. Chỉ 100 entry có thể chiếm nhiều RAM nếu mỗi value là cả một danh sách lớn.

## 3. Vì sao `@Cacheable` không giải quyết TTL/capacity?

Ví dụ:

~~~java
// Đoạn minh họa trong Spring-managed service.
@Cacheable(cacheNames = "prices", key = "#p0")
public Integer findPrice(String productId) {
    return repository.findPrice(productId);
}
~~~

Spring cache interceptor thực hiện gần như:

~~~text
key = productId
cache = cacheManager.getCache("prices")

if cache có entry(key):
    return entry.value

value = findPrice(productId)
cache.put(key, value)
return value
~~~

Đây là mô hình giản lược, không mô tả hết các đặc tính như `condition`, `unless`, `sync`, null adaptation hay `CacheErrorHandler`.

Với `ConcurrentMapCache`, mục `key -> value` vẫn nằm trong map sau khi `put` cho đến khi có thao tác ghi đè, `evict`, `clear` hoặc vòng đời tiến trình kết thúc. Annotation không ẩn chứa một scheduler để dọn key theo thời gian và cũng không tạo ra một chính sách capacity.

### `@Cacheable(sync = true)` có thêm TTL không?

**Không.** `sync=true` là gợi ý phối hợp tính toán khi nhiều caller cùng miss một key, tùy khả năng provider. Nó không thêm expiration, LRU, quota hoặc đồng bộ giữa nhiều JVM. Cần phân biệt **concurrency control** với **lifecycle/capacity management**.

### `unless = "#result == null"` có TTL không?

**Không.** `unless` có thể từ chối lưu một kết quả mới (ví dụ null) sau khi method chạy. Nó không xóa kết quả cũ đã nằm trong cache, không đặt thời hạn sống và không giới hạn số key.

## 4. Những tùy chọn của `ConcurrentMapCacheManager` thường bị hiểu nhầm

Spring có một số cấu hình cho manager đơn giản, nhưng chúng **không** biến nó thành provider bounded cache.

| Tùy chọn / API | Làm gì? | Có đặt TTL/capacity không? |
| --- | --- | --- |
| `new ConcurrentMapCacheManager("prices")` | Khai báo các vùng cache có tên | **Không** |
| `setCacheNames(...)` | Cố định tập **tên cache** có thể tạo/tra cứu | **Không giới hạn số key bên trong** |
| `setAllowNullValues(boolean)` | Cho phép/không cho phép lưu kết quả null qua adapter | **Không** |
| `setStoreByValue(boolean)` | Cấu hình copy theo serialization khi hỗ trợ, thay vì giữ reference | **Không** |
| `getCache("prices")` | Lấy vùng cache theo tên | **Không** |
| `Cache.evict(key)` | Xóa **một entry được chỉ định** | Chủ động, không theo thời gian |
| `Cache.clear()` | Xóa các entry trong một vùng | Chủ động, không theo dung lượng tự động |
| `@CacheEvict` | Khai báo xóa theo thao tác nghiệp vụ | Chủ động, không phải TTL |

Lưu ý `setStoreByValue` có yêu cầu serialization và đánh đổi hiệu năng; không bật nó chỉ nhằm giảm memory leak. Copy giá trị không tạo eviction. Với cấu hình mặc định kiểu store-by-reference, object mutable được cache có thể bị sửa ngoài ý muốn nếu cùng object được dùng ở nhiều nơi; ưu tiên DTO bất biến khi có thể.

### `setCacheNames` chỉ giới hạn tên cache, không giới hạn key

~~~java
// Minh họa cấu hình tĩnh cho hai tên cache.
@Bean
ConcurrentMapCacheManager cacheManager() {
    return new ConcurrentMapCacheManager("prices", "products");
}
~~~

Điều này giúp tránh việc vô tình tạo **vùng cache có tên mới** theo request. Nhưng `"prices"` vẫn có thể chứa hàng triệu key khác nhau. Hai giới hạn là độc lập:

~~~text
Giới hạn tên cache: prices, products
Giới hạn key trong prices: KHÔNG có ở ConcurrentMap cơ bản
~~~

Nếu tạo cache name động theo tenant hoặc request trong chế độ dynamic, số cache instance cũng có thể tăng. Nên dùng tập tên cache có kiểm soát và thiết kế key theo nghiệp vụ, không dựa vào tạo name không giới hạn.

## 5. Ví dụ chạy được: cache không tự hết hạn và số entry tăng

Ta xây ứng dụng nhỏ với **Java 17, Spring Boot 3.3.5, Maven**. `PriceService` mô phỏng nguồn dữ liệu bằng `ConcurrentHashMap` và đếm số lần method thực sự đọc nguồn. `ConcurrentMapCacheManager` được khai báo tường minh để bảo đảm dùng đúng provider đơn giản dù môi trường có những dependency khác.

Chương trình sẽ:

1. Đọc `P1` lần đầu rồi hit ở lần sau.
2. Sửa giá trong **nguồn dữ liệu** thành 120, chờ hơn 1 giây, nhưng vẫn đọc giá cache 100.
3. Đọc thêm bốn key mới để map chứa năm entry.
4. Gọi `Cache.evict("P1")` để xóa thủ công và đọc lại giá 120.
5. Gọi `Cache.clear()` để xóa toàn vùng.

Đây là demo hành vi, **không phải thử nghiệm đo giới hạn tối đa**: năm entry chỉ minh họa việc key mới được thêm, không tự bị loại. Việc provider thiếu capacity/TTL là đặc tính được mô tả trong tài liệu chính thức.

### Cấu trúc thư mục

~~~text
simple-map-cache-demo/
├── pom.xml
└── src/main/java/example/simplecache/
    ├── DemoApplication.java
    └── PriceService.java
~~~

### `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>simple-map-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### `src/main/java/example/simplecache/PriceService.java`

~~~java
package example.simplecache;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class PriceService {
    private final ConcurrentMap<String, Integer> source =
            new ConcurrentHashMap<>();
    private final AtomicInteger sourceReads = new AtomicInteger();

    public PriceService() {
        for (int i = 1; i <= 5; i++) {
            source.put("P" + i, i * 100);
        }
    }

    @Cacheable(cacheNames = "prices", key = "#p0")
    public Integer findPrice(String productId) {
        sourceReads.incrementAndGet();
        return source.get(productId);
    }

    // Cố tình chỉ sửa nguồn để quan sát một entry cache bị stale.
    public void changeSource(String productId, int newPrice) {
        source.put(productId, newPrice);
    }

    public int sourceReads() {
        return sourceReads.get();
    }
}
~~~

`findPrice()` là method duy nhất có annotation cache. `changeSource()` **không evict** để minh họa rằng sửa DB/nguồn dữ liệu không làm Spring tự phát hiện và xóa entry đã lưu. Trong ứng dụng production, đây sẽ là lỗi nhất quán nếu nghiệp vụ yêu cầu lần đọc tiếp theo thấy ngay giá mới.

### `src/main/java/example/simplecache/DemoApplication.java`

~~~java
package example.simplecache;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("prices");
    }

    @Bean
    CommandLineRunner demo(PriceService prices, CacheManager manager) {
        return args -> {
            System.out.println("first=" + prices.findPrice("P1"));
            System.out.println("hit=" + prices.findPrice("P1"));
            System.out.println("sourceReads=" + prices.sourceReads());

            prices.changeSource("P1", 120);
            Thread.sleep(1200);
            System.out.println("after-wait=" + prices.findPrice("P1"));
            System.out.println("sourceReads=" + prices.sourceReads());

            for (String id : List.of("P2", "P3", "P4", "P5")) {
                prices.findPrice(id);
            }

            ConcurrentMapCache cache =
                    (ConcurrentMapCache) manager.getCache("prices");
            System.out.println(
                    "entry-count=" + cache.getNativeCache().size());

            cache.evict("P1");
            System.out.println(
                    "after-evict=" + prices.findPrice("P1"));
            System.out.println("sourceReads=" + prices.sourceReads());

            cache.clear();
            System.out.println(
                    "after-clear-count=" + cache.getNativeCache().size());
        };
    }
}
~~~

### Chạy và kết quả

Mở terminal ở thư mục `simple-map-cache-demo`:

~~~bash
mvn -q spring-boot:run
~~~

Ngoài log khởi động Spring Boot, các dòng được in bởi `CommandLineRunner` sẽ là:

~~~text
first=100
hit=100
sourceReads=1
after-wait=100
sourceReads=1
entry-count=5
after-evict=120
sourceReads=6
after-clear-count=0
~~~

**Giải thích kết quả:**

- `first=100`: lần đầu `P1` chưa có cache, method đọc nguồn, `sourceReads=1`.
- `hit=100`: lần hai hit cùng key, số lần đọc nguồn vẫn bằng 1.
- Giá nguồn được đổi thành 120 nhưng cache **không có TTL**. Dù `Thread.sleep(1200)` đã chờ hơn một giây, `after-wait=100` vì entry `P1` vẫn tồn tại.
- Chương trình truy vấn thêm P2, P3, P4, P5; cùng với P1, map giữ năm key, do đó `entry-count=5`. Không có cấu hình tự loại P1 khi số key tăng.
- `cache.evict("P1")` xóa mục cũ. Lần đọc sau là miss nên trả `120`; số lần tải nguồn bằng `1 + 4 + 1 = 6`.
- `cache.clear()` xóa các entry trong **vùng `"prices"`**, nên số entry về 0. Nó không tự dọn những cache name khác hoặc cache ở JVM khác.

`Thread.sleep` trong demo chỉ giúp người học thấy khoảng thời gian trôi qua; không phải timer eviction. Nếu bạn thay `1200` bằng một khoảng lớn hơn, bản chất `ConcurrentMapCache` vẫn không tự có TTL. Đừng tăng sleep trong test production chỉ nhằm “ép” cache expire: provider đơn giản không có logic đó.

### Vì sao demo gọi qua `CommandLineRunner`?

Spring Cache ở proxy mode thông thường chỉ intercept lời gọi **qua Spring bean proxy**. Lời gọi `this.findPrice(...)` từ chính bên trong `PriceService` thường bỏ qua proxy. Ví dụ inject bean `PriceService` vào một bean runner khác, bảo đảm annotation được xử lý theo đường gọi Spring hỗ trợ.

### Có thể dùng test thay vì `Thread.sleep` không?

Có. Với bài test không-TTL, có thể dùng đồng hồ giả lập cho **nguồn dữ liệu** hoặc chỉ chứng minh rằng entry vẫn tồn tại sau khi thay đổi dữ liệu nguồn. Nhưng một “manual clock” không tác động được lên TTL của `ConcurrentMapCache`, vì provider vốn **không có** cấu hình TTL. Nếu muốn kiểm thử expiration theo thời gian bằng ticker giả lập, hãy dùng Caffeine với `Ticker` tùy chỉnh trong test.

## 6. Những điều `ConcurrentMapCache` làm được dù không có TTL

### `@CacheEvict` xóa entry theo nghiệp vụ

~~~java
// Ví dụ minh họa trong Spring service có repository thực.
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updatePrice(String productId, int price) {
    repository.updatePrice(productId, price);
}
~~~

Sau khi method hoàn thành bình thường, Spring evict key tương ứng. Lần `@Cacheable` tiếp theo tải lại dữ liệu nguồn. Đây là **invalidation chủ động**, không phải TTL.

Cần dùng cùng tên cache và cùng key giữa read và update. Nếu `@Cacheable` dùng key `productId` còn `@CacheEvict` dùng `SimpleKey(productId, price)`, entry cũ vẫn còn.

Nếu method cập nhật trả đúng giá trị mà reader mong đợi, bạn cũng có thể dùng `@CachePut` để ghi đè entry. Nếu update chỉ trả status/boolean mà cache chứa DTO, dùng `@CachePut` trực tiếp sẽ đưa sai loại giá trị vào cache; eviction an toàn hơn.

### Xóa toàn vùng khi cần

~~~java
// Minh họa: evict tất cả entry của cache "prices" sau thao tác nghiệp vụ.
@CacheEvict(cacheNames = "prices", allEntries = true)
public void invalidateAllPrices() {
    // Thân method thực hiện hoặc ghi nhận sự kiện nghiệp vụ thích hợp.
}
~~~

`allEntries=true` áp dụng trong vùng cache đã chọn; nó không có nghĩa xóa mọi cache name trong ứng dụng. Xóa toàn vùng có thể tạo đỉnh cache miss và tải lại từ nguồn, cần cân nhắc nếu lưu lượng lớn.

### Cache API

~~~java
// Trong lớp đã inject CacheManager; mã minh họa không độc lập.
Cache cache = cacheManager.getCache("prices");
cache.evict("P1");
cache.clear();
~~~

Những thao tác này có tác dụng khi được gọi. `ConcurrentMapCacheManager` không tự lập lịch gọi `evict` hoặc `clear` theo tuổi entry, và không tự biết một product đã thay đổi trong DB.

### Chặn cache null

~~~java
@Cacheable(
        cacheNames = "prices",
        key = "#p0",
        unless = "#result == null"
)
public Integer findPrice(String productId) {
    return repository.findPrice(productId);
}
~~~

Cách này từ chối lưu null **sau một lần tính mới**, không đặt TTL. `ConcurrentMapCache` có cơ chế thích nghi để hỗ trợ null qua một marker khi manager cho phép; bản thân `ConcurrentHashMap` không chấp nhận giá trị null. `setAllowNullValues(false)` là cấu hình khác với `unless` và không nên xem là cơ chế xóa dữ liệu cũ.

## 7. Vì sao tự xây TTL bằng `ConcurrentHashMap` thường không phải lựa chọn tốt?

Một ý tưởng phổ biến là lưu cặp `(value, expiresAt)` trong map và kiểm tra `System.currentTimeMillis()` trước khi trả. Nó có thể hoạt động ở một ví dụ rất nhỏ, nhưng một cache hoàn chỉnh cần giải quyết nhiều vấn đề:

1. **Tính thời gian:** dùng nguồn thời gian monotonic phù hợp cho elapsed time; wall clock có thể bị chỉnh, làm mốc TTL bất ngờ.
2. **Load đồng thời:** hai thread thấy cùng entry expired thì có cùng chạy loader không?
3. **Ghi đè race:** một loader chậm có thể ghi giá trị cũ sau khi một request khác đã update.
4. **Dọn key expired:** kiểm tra TTL khi `get` chỉ loại key được truy cập. Entry hết hạn nhưng không ai đọc có thể vẫn giữ bộ nhớ.
5. **Giới hạn dung lượng:** dọn expired khác với eviction khi số key vượt ngân sách.
6. **Độ chính xác và chi phí:** scheduler chạy thường xuyên có thể tốn CPU; chạy thưa thì retained memory cao.
7. **Tính thread-safe:** iterator, update và eviction phải an toàn khi nhiều thread cùng truy cập.
8. **Metrics:** cần quan sát hit/miss, expiration, capacity eviction và thời gian load.
9. **Quản lý vùng và key:** mỗi cache name, tenant và loại dữ liệu cần chính sách phù hợp.
10. **Failure handling:** loader exception, null, serialization và application shutdown phải có semantics rõ.

Chỉ lưu `expiresAt` trong value **không tự tạo** một cơ chế capacity. Chỉ chạy `@Scheduled(fixedRate=...)` để `clear()` toàn bộ cache **không phải TTL per-entry**; nó làm mọi key mất hiệu lực cùng lúc và có thể gây cache stampede.

Nếu yêu cầu không vượt quá một tập vài chục key cố định và tuổi dữ liệu được quản lý bằng update/evict cụ thể, ConcurrentMap đơn giản có thể đủ. Nếu cần expiration, bounded size, weighted eviction hoặc metrics đáng tin, dùng cache provider có sẵn sẽ ít rủi ro hơn việc tự viết lại những tính năng ấy.

## 8. Chuyển sang Caffeine khi cần TTL và giới hạn thực sự

Caffeine là provider bộ nhớ JVM có các tính năng expiration, maximum size/weight, statistics và nhiều tối ưu cho ứng dụng thực tế. Trong Spring Boot, thường chỉ cần thêm dependency Caffeine và để Boot cấu hình `CaffeineCacheManager`.

### Thêm dependency

Trong `pom.xml`, giữ `spring-boot-starter-cache` và thêm:

~~~xml
<!-- Chỉ là đoạn dependencies bổ sung vào pom.xml có sẵn -->
<dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
</dependency>
~~~

Spring Boot BOM quản lý version phù hợp trong dự án Boot; đoạn XML này không phải một POM đầy đủ.

### Bỏ `CacheManager` tự khai báo của demo

Trong `DemoApplication` ở mục 5, **xóa phương thức `@Bean CacheManager cacheManager()`**. Nếu giữ bean `ConcurrentMapCacheManager` do mình tự tạo, Boot không tự thay nó bằng Caffeine chỉ vì có dependency và properties. Một cấu hình provider cần được lựa chọn rõ ràng.

### `application.properties`

Tạo `src/main/resources/application.properties`:

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=prices
spring.cache.caffeine.spec=maximumSize=1000,expireAfterWrite=120s,recordStats
~~~

Ý nghĩa:

| Cấu hình | Tác dụng |
| --- | --- |
| `spring.cache.type=caffeine` | Chọn Caffeine trong auto-configuration |
| `cache-names=prices` | Chỉ định tên cache mong muốn |
| `maximumSize=1000` | Giới hạn mục tiêu khoảng 1.000 **entry cho cache instance này** |
| `expireAfterWrite=120s` | Entry hết hạn sau 120 giây tính từ lần ghi gần nhất |
| `recordStats` | Ghi nhận thống kê Caffeine khi được truy xuất |

**Lưu ý quan trọng:** `maximumSize` đếm **entry**, không phải byte RAM. Value rất lớn có thể gây áp lực heap dù số entry thấp. Caffeine thực thi chính sách eviction/maintenance của riêng nó; không nên suy ra một key cụ thể nào sẽ bị loại khi chạm ngưỡng.

Sau chuyển provider, logic trong `PriceService` vẫn có thể giữ nguyên `@Cacheable(cacheNames="prices", key="#p0")`: đây là lợi ích của Spring Cache abstraction. Nhưng code demo có ép kiểu `ConcurrentMapCache` và gọi `getNativeCache().size()` sẽ **không còn đúng** với Caffeine; hãy sửa phần đo size qua `CaffeineCache`/native API hoặc Actuator metrics nếu cần. Output demo ở mục 5 chỉ dành cho **ConcurrentMap**, không dùng để khẳng định kết quả của bản đã đổi provider.

### Cấu hình programmatic thay vì properties

Có thể dùng cấu hình Java:

~~~java
// Đoạn minh họa trong class @Configuration, với các import phù hợp.
@Bean
CaffeineCacheManager cacheManager() {
    CaffeineCacheManager manager = new CaffeineCacheManager("prices");
    manager.setCaffeine(
            Caffeine.newBuilder()
                    .maximumSize(1000)
                    .expireAfterWrite(java.time.Duration.ofMinutes(2))
                    .recordStats()
    );
    return manager;
}
~~~

Đoạn này thay cho cấu hình auto bằng properties, không phải thêm một manager thứ hai cùng chức năng. Import cần `Caffeine`, `CaffeineCacheManager` và `Bean`; có Caffeine dependency.

### Nếu cần giới hạn byte thay vì số entry

Caffeine hỗ trợ `maximumWeight(...)` và `weigher(...)` để tính **trọng số do ứng dụng định nghĩa**. Ví dụ payload `byte[]` có thể gán trọng số bằng độ dài mảng:

~~~java
// Mã minh họa builder Caffeine, không độc lập.
var nativeCache = Caffeine.newBuilder()
        .maximumWeight(20L * 1024 * 1024)
        .weigher((String key, byte[] value) -> value.length)
        .build();
~~~

Ở đây giới hạn là tổng **trọng số payload** khoảng 20 MiB, không đo chính xác heap overhead, key objects hay metadata. Không kết hợp `maximumWeight` với `maximumSize` trên cùng builder: chọn chiến lược giới hạn phù hợp. Trọng số được xác định khi entry được tạo/cập nhật; sửa nội dung mảng sau khi lưu không làm provider tự tính lại trọng số, vì vậy ưu tiên value bất biến.

### `expireAfterAccess` có hợp hơn không?

`expireAfterAccess=120s` làm entry hết hạn sau khoảng 120 giây **không truy cập**. Nó phù hợp với dữ liệu mà số key nóng nên giữ lại, nhưng key được truy cập liên tục có thể sống rất lâu. Nếu mục tiêu là giới hạn **độ cũ tối đa**, nên dùng TTL sau ghi hoặc cơ chế refresh/invalidation phù hợp hơn.

`refreshAfterWrite` (khi cấu hình cache có loader hỗ trợ) khác với expiration: nó cho phép làm mới khi đủ điều kiện, trong nhiều trường hợp vẫn có thể trả giá trị cũ trong lúc refresh. Đừng bật refresh rồi mặc định dữ liệu sẽ tự làm mới theo một lịch cứng; cần kiểm tra provider, loader và version đang chạy.

### Khi nào phải dùng cache phân tán?

Caffeine và ConcurrentMap đều chủ yếu nằm trong bộ nhớ **mỗi JVM**. Nếu nhiều replica cần chia sẻ entry hoặc thống nhất invalidation, cân nhắc Redis hoặc provider phân tán phù hợp. Shared storage giúp các replica thấy dữ liệu chung, nhưng lại cần thiết kế TTL, key prefix, serializer, memory policy và xử lý lỗi mạng. Một distributed cache cũng không mặc nhiên bảo đảm "exactly once" khi nhiều loader cùng miss.

## 9. Quản lý dung lượng nếu tạm thời vẫn dùng ConcurrentMap

Có những trường hợp giữ Simple provider là quyết định hợp lý, chẳng hạn tập dữ liệu cấu hình nhỏ được biết trước. Khi đó cần rõ giới hạn **bằng thiết kế nghiệp vụ** thay vì hứa một tính năng provider không có.

### Giới hạn miền key bằng validation nghiệp vụ

~~~text
cache = "countryCodes"
key chỉ có thể là một trong tập ISO country code đã được xác minh
số key có giới hạn miền rõ ràng
~~~

Nếu bạn biết trước số lượng key hữu hạn và mỗi value nhỏ, cache không cần thuật toán eviction phức tạp. Tuy nhiên, đừng nhầm **giới hạn miền key** với **`maximumSize` cấu hình ở provider**: nếu API cho thêm key mới không kiểm soát, lập luận hữu hạn không còn đúng.

### Không đưa request ID hoặc timestamp vào key

~~~java
// PHẢN VÍ DỤ: UUID mới mỗi lần làm cache hầu như không hit.
@Cacheable(
    cacheNames = "prices",
    key = "#p0 + ':' + T(java.util.UUID).randomUUID()"
)
public Integer findPrice(String id) {
    return repository.findPrice(id);
}
~~~

Mỗi request có key mới, các entry cũ có thể giữ mãi trong ConcurrentMap. Cũng tránh dùng raw query string không chuẩn hóa, access token hoặc metadata tracing trong key nếu chúng không ảnh hưởng giá trị trả về. Cần quan tâm cả hiệu năng lẫn nguy cơ lộ thông tin nhạy cảm qua logs/tracing.

### Cẩn trọng với method trả danh sách lớn

Một entry chứa danh sách hàng trăm nghìn phần tử có thể làm heap tăng mạnh dù số key chỉ là 1. Có thể cache DTO gọn hơn, giới hạn kích thước query, phân trang hợp lý hoặc không cache kết quả quá lớn. Cache phân trang lại tạo nhiều key hơn: cả kích thước value lẫn cardinality đều cần đánh giá.

### Evict khi dữ liệu nguồn thay đổi

Nếu `updatePrice("P1")` vừa cập nhật database, cần chính sách invalidation hoặc `@CachePut` tương thích. Nếu không, giá cũ có thể ở trong map **cho đến khi restart**. Một `@CacheEvict` đúng key giúp lần đọc kế tiếp nạp lại giá mới. Khi update nằm trong transaction, cần xác định thời điểm evict/put so với commit; đừng giả định cache và DB tự có giao dịch nguyên tử.

### Clear định kỳ có thay thế TTL không?

Không. Ví dụ cứ mỗi giờ clear một vùng:

~~~text
10:00 clear prices
10:00:01 giá P1 được cache
10:59:59 P1 vẫn có thể còn
11:00 clear toàn vùng
~~~

Tuổi entry sẽ khác nhau tùy lúc nó được tạo so với lịch clear. Một entry mới tạo lúc 10:59:59 bị xóa sau một giây, còn entry tạo lúc 10:00:01 tồn tại gần một giờ. Lịch clear toàn vùng còn dễ khiến tất cả request đồng loạt miss sau khi clear, gây áp lực lên nguồn. Với SLA về TTL, chọn provider hỗ trợ expiration per-entry.

## 10. Một JVM, nhiều JVM và hệ quả của local cache

~~~text
                 Load balancer
                    /      \
                  App A    App B
                   JVM A    JVM B
                    |        |
             Map prices A  Map prices B
                    \        /
                   Database chung
~~~

`ConcurrentMapCacheManager` tại App A không chia sẻ heap với App B. Hai ứng dụng có thể cache **cùng key nhưng hai phiên bản giá khác nhau**. Xóa `"P1"` ở App A không tự xóa `"P1"` ở App B.

Nếu có bốn replica và mỗi replica có 10.000 entry giống nhau, memory dùng cho các bản sao có thể tăng trên cả bốn JVM. Không có công thức chính xác chỉ dựa vào số entry; đo retained heap và GC ở từng replica.

`@Cacheable(sync=true)` có thể phối hợp loader cho cùng key **trong một cache instance** theo hỗ trợ của provider, nhưng không làm local map trở thành cache phân tán. Khi cache warm-up cùng lúc trên nhiều replica, có thể có nhiều phép tính trùng nhau. Tùy ứng dụng, điều này có thể chấp nhận được hoặc cần shared cache / coordination riêng.

### Cache hit không phải cơ chế xác thực quyền

Nếu một method `@Cacheable` chỉ kiểm tra quyền **trong thân method**, lần cache hit có thể bỏ qua kiểm tra ấy. Với dữ liệu nhạy cảm, cần kiểm tra quyền trước lời gọi cache ở nơi luôn chạy và bảo đảm key được phân vùng theo tenant/user/role nếu giá trị thay đổi theo scope. Cài đặt ConcurrentMap cơ bản không tự giải quyết bài toán bảo mật.

## 11. Kiểm thử TTL/capacity và theo dõi vận hành

### Kiểm thử đúng điều gì?

| Thử nghiệm | Provider Simple/ConcurrentMap | Provider có TTL/capacity |
| --- | --- | --- |
| Gọi cùng key hai lần | Có thể hit ở lần hai | Có thể hit nếu chưa expired/evicted |
| Chờ 1 giây khi không có invalidation | Entry không tự hết hạn | Phụ thuộc TTL cấu hình |
| Đổi nguồn khi cache đang có | Entry có thể tiếp tục stale | Vẫn có thể stale cho tới TTL/invalidation |
| Thêm nhiều key khác nhau | Map tiếp tục nhận key | Có thể bị capacity eviction |
| `Cache.evict(key)` | Xóa chủ động | Cũng xóa chủ động |
| `Cache.clear()` | Xóa toàn vùng | Cũng xóa toàn vùng theo provider |
| Restart JVM | Cache local mất | Cache local mất; cache remote có thể còn |
| Nhiều JVM | Không chia sẻ entry | Local provider không chia sẻ; remote tùy backend |

Với Caffeine, nên dùng ticker giả lập trong unit/integration test để kiểm chứng expiration nhanh và đáng tin. Với ConcurrentMap, test có thể chỉ xác minh **không có** behavior TTL tự động và explicit invalidation hoạt động. Không nên làm test đòi chờ nhiều phút khi có API kiểm soát thời gian thích hợp.

### Theo dõi key count và bộ nhớ

Từ `ConcurrentMapCache`, `getNativeCache().size()` cho số entry hiện diện trong map tại thời điểm đọc. Đó không phải số byte heap. Nếu có rất nhiều cache name, phải xem xét tổng entry và memory của mọi vùng, không chỉ một tên.

Một bộ chỉ số nên có:

- Số key per cache, tốc độ tăng key mới theo thời gian.
- Heap used/retained, garbage collection pause và số lần OOM/near-OOM.
- Cache hit/miss, số lần tải nguồn, thời gian tải nguồn và lỗi loader.
- Số lần invalidation, các lần clear toàn vùng và áp lực miss ngay sau clear.
- Kích thước value lớn nhất và trung vị sau serialization (nếu có).
- Số replica JVM và chi phí giữ nhiều bản cache giống nhau.
- Số lần kết quả stale bị phát hiện khi nguồn cập nhật.
- p95/p99 latency của API đang dùng cache.

Simple provider không có đầy đủ thống kê eviction/expiration bởi vì nó không thực thi chính sách ấy. Có thể thêm instrumentation tại lớp service hoặc dùng Actuator/Micrometer tùy cấu hình, nhưng **không** giả định metric được bật sẵn chỉ vì có `@Cacheable`.

**Tránh nổ cardinality của chính metrics:** đừng gắn từng product ID, query string hoặc access token vào nhãn metric. Chỉ dùng tập label hữu hạn như tên cache/nhóm nghiệp vụ/môi trường.

### Hạn chế kiểm tra bằng cách quét toàn bộ map

`ConcurrentHashMap.size()` có thể dùng để quan sát quy mô ở mức cần thiết, nhưng không nên liên tục snapshot và log mọi key/value của cache production; thao tác đó tạo chi phí CPU/GC và rủi ro lộ dữ liệu. Với ứng dụng có nhiều request ghi đồng thời, số `size()` là một snapshot phục vụ giám sát, không phải một ranh giới quota nguyên tử.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Giá vẫn cũ sau nhiều giờ | Không có TTL/invalidation ở ConcurrentMap | Evict/put khi update, hoặc dùng provider có TTL |
| Heap tăng theo thời gian | Key mới tiếp tục được thêm, không tự evict | Giảm key cardinality, giới hạn payload, chuyển bounded cache |
| `spring.cache.cache-names` chỉ có 2 tên mà memory vẫn tăng | Hạn chế tên cache, không hạn chế số key | Kiểm soát key count của từng cache |
| Đặt `@Cacheable(unless=...)` nhưng vẫn stale | `unless` chỉ veto kết quả mới | Chủ động xóa entry cũ khi dữ liệu đổi |
| Thêm `@Cacheable(sync=true)` mà map vẫn lớn | `sync` chống tính trùng khi miss, không có capacity | Dùng `maximumSize`/provider chuyên dụng |
| Đổi source không làm cache đổi | Caching không tự theo dõi DB | Đồng bộ update với `@CacheEvict`/`@CachePut` |
| Clear mỗi giờ nhưng key vẫn có tuổi khó dự đoán | Clear theo lịch khác TTL per-entry | Chọn expire-after-write phù hợp |
| Thêm Caffeine dependency nhưng vẫn không có TTL | Đang có custom `ConcurrentMapCacheManager` bean | Loại bean cũ, chọn đúng provider, kiểm tra runtime |
| Đã dùng Caffeine nhưng ép kiểu `ConcurrentMapCache` lỗi | Native cache class đã thay đổi | Dùng `Cache` abstraction hoặc API provider tương ứng |
| Một replica đã evict, replica khác vẫn stale | Local cache riêng mỗi JVM | Dùng shared cache / broadcast invalidation |
| Lưu DTO mutable rồi thấy dữ liệu đổi bất thường | Store-by-reference và object bị mutate | Dùng giá trị bất biến hoặc cấu hình copy thích hợp |
| Cache null tạo hành vi không mong muốn | `allowNullValues` và annotation policy | Quy định negative caching/`unless` rõ ràng |
| Tưởng `maximumSize` bằng giới hạn byte | Caffeine đếm entry, không đo RAM | Dùng weight ước lượng hoặc đo heap thực |

## 13. Bài tập thực hành

**Bài 1.** Một ứng dụng dùng `ConcurrentMapCacheManager` để cache `findById`. Sau 24 giờ, một key vẫn hit dù nguồn dữ liệu đổi. Đây có phải bug của Java `ConcurrentHashMap` không?  
**Đáp án:** không. Provider cơ bản không có TTL tự động. Nếu cần dữ liệu mới, phải evict/put khi nguồn thay đổi hoặc dùng provider có expiration và chính sách độ mới tương ứng.

**Bài 2.** `new ConcurrentMapCacheManager("users", "products")` có ngăn `"users"` nhận hơn 1 triệu key không?  
**Đáp án:** không. Nó chỉ quy định tên cache, không giới hạn số entry trong mỗi cache.

**Bài 3.** Một cache có 500 key, mỗi value 5 MiB. Có thể coi nó nhỏ vì “chỉ 500 key” không?  
**Đáp án:** không. Payload thuần đã rất lớn, chưa kể overhead. Cần giới hạn kích thước value, dữ liệu được giữ và ngân sách heap.

**Bài 4.** Xóa toàn cache lúc nửa đêm có tương đương TTL 24 giờ không?  
**Đáp án:** không. Entry tạo ngay trước nửa đêm bị xóa sau vài giây, còn entry tạo ngay sau nửa đêm gần 24 giờ sau mới bị xóa.

**Bài 5.** Thêm `spring.cache.caffeine.spec=maximumSize=1000,expireAfterWrite=120s` nhưng dự án vẫn có `@Bean ConcurrentMapCacheManager`. Có chắc properties đã có hiệu lực không?  
**Đáp án:** không. Bean CacheManager tùy chỉnh có thể ngăn Boot auto-config Caffeine. Cần chọn đúng manager, kiểm tra class đang chạy và test hành vi expiration/capacity.

**Bài 6.** `@Cacheable(sync=true)` có làm một entry tự biến mất sau 5 phút không?  
**Đáp án:** không. Nó liên quan phối hợp cache miss, không cung cấp thời hạn sống.

**Bài 7.** App A và App B dùng cùng source DB và cùng tên cache `"prices"` nhưng mỗi app có `ConcurrentMapCacheManager` riêng. App A evict `"P1"` thì App B có tự xóa không?  
**Đáp án:** không. Hai local cache ở hai JVM độc lập.

**Bài 8.** Khi nào có thể tiếp tục dùng ConcurrentMap?  
**Đáp án:** khi tập key nhỏ/hữu hạn được kiểm soát, value nhỏ, không cần expiration tự động, invalidation được quản lý rõ và có số liệu theo dõi bộ nhớ. Đối với keyspace mở hoặc dữ liệu cần giới hạn độ mới, chọn provider phù hợp hơn.

## 14. Checklist lựa chọn và chuyển đổi

Trước khi quyết định dùng Simple provider lâu dài:

- [ ] Đã xác định số **key khác nhau** tối đa hoặc ít nhất tốc độ key growth có thể xảy ra.
- [ ] Đã đo hoặc giới hạn kích thước các object được giữ trong cache.
- [ ] Đã quy định kết quả được phép stale bao lâu và những lần update nào cần evict/put.
- [ ] Đã hiểu rằng ConcurrentMap cơ bản không có TTL/TTI/capacity tự động.
- [ ] Không dùng timestamp/UUID mới mỗi request làm key để giả lập TTL.
- [ ] Không coi `setCacheNames` là quota của entry count.
- [ ] Đã kiểm tra bean CacheManager **thực tế** trong Spring context.
- [ ] Nếu đổi sang Caffeine, đã xác minh `maximumSize`/`maximumWeight`, expiration và hoạt động trên mỗi JVM.
- [ ] Đã rà lại các đoạn code ép kiểu native cache khi đổi provider.
- [ ] Đã test cập nhật nguồn, cache hit, evict, clear, concurrency và restart.
- [ ] Nếu chạy nhiều replica, đã hiểu rằng local eviction không đồng bộ giữa JVM.
- [ ] Có metrics/alerts về heap, key count, miss rate và stale data.

## Tài liệu tham khảo

- Spring Framework – **Configuring the Cache Storage**, phần *JDK ConcurrentMap-based Cache*: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework – **Cache Abstraction**, `@Cacheable`, `@CachePut`, `@CacheEvict`: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework – **How can I Set the TTL/TTI/Eviction policy?**: https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html
- Spring Framework – Javadoc `ConcurrentMapCacheManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework – Javadoc `ConcurrentMapCache`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Boot – **Caching** và Simple/Caffeine providers: https://docs.spring.io/spring-boot/reference/io/caching.html
- Caffeine – **Eviction** và expiration: https://github.com/ben-manes/caffeine/wiki/Eviction

**Ghi nhớ:** `ConcurrentMapCacheManager` là lựa chọn tiện lợi cho demo, test và cache local nhỏ, nhưng **không tự giới hạn tuổi hay dung lượng dữ liệu**. `@CacheEvict`/`Cache.clear()` chỉ xóa khi được gọi; `@Cacheable` không biến chúng thành TTL. Khi cần bounded memory, expiration hoặc thống kê nâng cao, dùng provider chuyên dụng như Caffeine, cấu hình và kiểm thử trên đúng `CacheManager` được ứng dụng sử dụng.