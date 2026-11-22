# Đăng ký cache tùy chỉnh với cấu hình riêng — Spring Cache và Caffeine

## Mục tiêu

Bài học thuộc nhóm **Tích hợp Caffeine** trong Spring Framework Cache. Sau bài này, bạn sẽ:

1. Giải thích vì sao mỗi **cache region** có thể cần chính sách khác nhau về TTL, dung lượng và thống kê.
2. Đăng ký các cache Caffeine riêng bằng `CaffeineCacheManager.registerCustomCache(name, nativeCache)`, kết hợp với cache dùng **cấu hình chung** của manager.
3. Phân biệt `setCaffeine(...)`, `setCacheNames(...)`, `registerCustomCache(...)`, tên vùng trong `@Cacheable` và key bên trong vùng.
4. Chạy ví dụ Spring Boot Java 17+ có ba cache với TTL lần lượt **5 giây, 40 giây và 30 giây**; kiểm chứng kết quả bằng đồng hồ mô phỏng thay vì `Thread.sleep`.
5. Biết các bẫy về việc tạo vùng động, thứ tự cấu hình, null, key, concurrency, memory bounds, transaction và nhiều replica.

**Ý tưởng chính:** `CaffeineCacheManager` có **cấu hình mặc định** dùng để tạo những cache thông thường. Khi một số vùng cần chính sách riêng, bạn **đăng ký chính những Caffeine cache instances được build theo cấu hình riêng** cho từng tên bằng `registerCustomCache`. Không cần nhân bản toàn bộ `CacheManager` chỉ vì hai vùng có TTL khác nhau.

## 1. Vì sao một ứng dụng cần nhiều chính sách cache?

Ví dụ hệ thống thương mại điện tử có những loại dữ liệu:

| Cache region | Loại dữ liệu | Nhu cầu minh họa |
| --- | --- | --- |
| `prices` | Giá hiển thị thường đổi | TTL ngắn, giới hạn số entry vừa phải |
| `productDetails` | Thông tin sản phẩm ít đổi | TTL dài hơn, nhiều entry hơn |
| `categories` | Danh mục nhỏ, ít thay đổi | Dùng chính sách chung, invalidation khi cập nhật |
| `searchResults` | Kết quả theo filter/sort/page | Key nhiều thành phần, giới hạn dung lượng và TTL riêng |

Nếu mọi cache đều dùng một builder `expireAfterWrite(10 phút).maximumSize(1_000)`, có thể tồn tại hai vấn đề: giá quá cũ vì TTL dài, và thông tin sản phẩm bị load quá thường xuyên vì TTL quá ngắn. Việc cấu hình riêng theo vùng giúp xác định **hợp đồng độ mới và ngân sách bộ nhớ** phù hợp cho mỗi loại dữ liệu.

Về mặt cấu trúc:

~~~text
                   Spring Cache annotations
                              |
                         CacheManager
                              |
                   CaffeineCacheManager
              /---------------+----------------\
             /                |                 \
       prices            productDetails        categories
       custom Cache      custom Cache          default Cache
       TTL = 5 s         TTL = 40 s            TTL = 30 s
       max = 100         max = 1,000           max = 500
             |                |                 |
       key -> value      key -> value         key -> value
~~~

Các con số chỉ phục vụ demo, không phải khuyến nghị TTL cho sản phẩm thực tế. **Từng vùng** có namespace riêng: cùng key `"42"` trong `prices` và `productDetails` không phải cùng entry.

## 2. API cần nắm

`org.springframework.cache.caffeine.CaffeineCacheManager` là adapter từ **Spring Cache abstraction** sang Caffeine. Ba phương thức thường được kết hợp:

### 2.1. Cấu hình chung: setCaffeine

~~~java
manager.setCaffeine(
        Caffeine.newBuilder()
                .maximumSize(500)
                .expireAfterWrite(Duration.ofSeconds(30)));
~~~

Mã trên chỉ minh họa khi đã có biến `manager`, các import `Caffeine` và `Duration`. Những cache được manager **tự tạo theo cơ chế chung** sẽ sử dụng builder này. Cấu hình ở `setCaffeine` không có nghĩa sẽ **ghi đè builder của các native Caffeine cache tự đăng ký**.

Các phương thức khác cùng mục đích chung gồm `setCacheSpecification(...)` và `setCaffeineSpec(...)`; lựa chọn một phương thức cấu hình thống nhất, tránh giẫm lên nhau bằng nhiều nguồn cài đặt.

### 2.2. Khai báo danh sách vùng mặc định: setCacheNames

~~~java
manager.setCacheNames(List.of("categories"));
~~~

Khi cung cấp collection tên vùng, `CaffeineCacheManager` chuyển sang chế độ **static** cho các vùng do manager thông thường tạo; việc gọi `getCache("typo")` cho một tên chưa tồn tại và chưa được custom-register sẽ trả `null` thay vì tự tạo thêm cache. Đây là cách phát hiện lỗi chính tả cache name.

**Đừng nhầm:** `setCacheNames` nhận **tên vùng**, không nhận `Caffeine Cache` instances. Đây không phải API đặt TTL riêng cho từng tên.

### 2.3. Đăng ký cache riêng: registerCustomCache

~~~java
com.github.benmanes.caffeine.cache.Cache<Object, Object> fast =
        Caffeine.newBuilder()
                .expireAfterWrite(Duration.ofSeconds(5))
                .maximumSize(100)
                .build();

manager.registerCustomCache("prices", fast);
~~~

Ở đây, bạn **build một native `com.github.benmanes.caffeine.cache.Cache`** rồi đưa vào manager dưới tên `prices`. Spring sẽ expose nó qua `CacheManager.getCache("prices")` dưới dạng Spring `Cache` adapter. Có thể đăng ký nhiều vùng custom, mỗi vùng có builder riêng.

API này có trên Spring Framework từ **5.2.8** với native synchronous Caffeine `Cache<Object,Object>`. Các Spring Framework phiên bản mới còn có overload nhận Caffeine `AsyncCache<Object,Object>` (từ Spring 6.1), nhưng demo này dùng đường **synchronous** để tránh nhập nhằng semantics async.

Tài liệu API nêu rõ: cache custom hoạt động song song với cache được tạo theo cấu hình chung; cache được tạo theo tên thường hoặc tạo động về sau vẫn dùng cấu hình chung của manager.

### 2.4. Ba tầng cần phân biệt

| Thành phần | Ví dụ | Chức năng |
| --- | --- | --- |
| Spring `CacheManager` | `CaffeineCacheManager` | Tìm/cache region theo tên |
| Spring `Cache` adapter | `manager.getCache("prices")` | API thống nhất `get/put/evict/clear` |
| Native Caffeine `Cache` | `Caffeine.newBuilder()...build()` | Thực hiện TTL/size/eviction/concurrency theo backend |

Khi gọi `@Cacheable(cacheNames = "prices", key = "#p0")`, annotation **không tự tạo builder riêng**. Spring tìm cache region `prices` trên manager; region này đã được liên kết với native cache mà bạn đăng ký.

## 3. Khi nào cần custom cache thay vì một cấu hình toàn cục?

Có ba tình huống thường gặp:

- **Freshness khác nhau:** giá có thể được giữ trong 5–30 giây, thông tin sản phẩm ổn định lâu hơn.
- **Kích thước khác nhau:** cache tìm kiếm nhiều key dễ phình to cần `maximumSize` chặt hơn danh mục nhỏ.
- **Chính sách eviction/expiry khác nhau:** một vùng phù hợp `expireAfterWrite`, vùng khác cần `expireAfterAccess` hoặc `Expiry` riêng từng entry, hoặc chỉ một số vùng cần `recordStats()`.

Cần chú ý: `maximumSize(n)` giới hạn gần theo **số entry**, không bảo đảm mỗi cache dùng ít hơn một lượng RAM tính bằng byte cố định. Nếu kích thước từng value rất khác, xem xét `maximumWeight` với `weigher`. Từ “TTL” trong bài chủ yếu chỉ `expireAfterWrite`; `expireAfterAccess` là *time-to-idle*, sẽ được gia hạn khi có truy cập phù hợp.

Không chọn TTL chỉ vì số liệu “đẹp”. TTL phải được quyết định từ mức độ cũ chấp nhận được, tần suất update, chi phí tải dữ liệu, tốc độ tạo keys, số replica và giới hạn bộ nhớ.

## 4. Ví dụ Spring Boot chạy được: ba vùng, ba TTL

Ví dụ dùng Java 17+, Spring Boot với Gradle; không có database thật. Để **kiểm chứng chính xác TTL** mà không đợi thời gian thực, ta tạo `ManualTicker`. Caffeine hỗ trợ thay nguồn thời gian bằng `Ticker`, nên một lần “tăng 6 giây” trong demo sẽ khiến Caffeine nhận thấy thời gian đã trôi qua.

Cấu hình mong muốn:

| Tên vùng | Cách tạo | TTL theo write | maximumSize |
| --- | --- | --- | --- |
| `shortItems` | `registerCustomCache` | 5 giây | 100 |
| `longItems` | `registerCustomCache` | 40 giây | 1.000 |
| `defaultItems` | `setCacheNames` + `setCaffeine` | 30 giây | 500 |

Trong dự án Spring Boot Gradle có sẵn và đã có plugin/version hỗ trợ Java 17+, cần hai dependency này (để Spring Boot dependency management quản lý phiên bản):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

Bốn file Java nằm cùng package `example.caffeinecustom`.

### 4.1. ManualTicker.java — đồng hồ mô phỏng

Tạo `src/main/java/example/caffeinecustom/ManualTicker.java`:

~~~java
package example.caffeinecustom;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;

import com.github.benmanes.caffeine.cache.Ticker;

public final class ManualTicker implements Ticker {
    private final AtomicLong nanos = new AtomicLong();

    @Override
    public long read() {
        return nanos.get();
    }

    public void advance(Duration duration) {
        if (duration.isNegative()) {
            throw new IllegalArgumentException(
                    "duration must not be negative");
        }
        nanos.addAndGet(duration.toNanos());
    }
}
~~~

Caffeine dùng `Ticker.read()` (đơn vị nanosecond) để so sánh với TTL. Ở đây `nanos` bắt đầu từ 0, thay đổi theo ý muốn test. Trong production, **không dùng ticker thủ công**; để Caffeine sử dụng monotonic clock mặc định.

### 4.2. CacheConfiguration.java — đăng ký custom caches

Tạo `src/main/java/example/caffeinecustom/CacheConfiguration.java`:

~~~java
package example.caffeinecustom;

import java.time.Duration;
import java.util.List;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    ManualTicker manualTicker() {
        return new ManualTicker();
    }

    @Bean
    CacheManager cacheManager(ManualTicker ticker) {
        CaffeineCacheManager manager = new CaffeineCacheManager();

        // Cấu hình CHUNG cho những vùng do manager tự tạo.
        manager.setAllowNullValues(false);
        manager.setCaffeine(Caffeine.newBuilder()
                .ticker(ticker)
                .maximumSize(500)
                .expireAfterWrite(Duration.ofSeconds(30)));

        // Static mode cho vùng chung; cache name khác chưa đăng ký
        // sẽ không được tạo tự động khi gọi getCache(name).
        manager.setCacheNames(List.of("defaultItems"));

        // Custom #1: TTL ngắn và số entry tối đa riêng.
        com.github.benmanes.caffeine.cache.Cache<Object, Object> fast =
                Caffeine.newBuilder()
                        .ticker(ticker)
                        .maximumSize(100)
                        .expireAfterWrite(Duration.ofSeconds(5))
                        .build();
        manager.registerCustomCache("shortItems", fast);

        // Custom #2: TTL dài và capacity lớn hơn.
        com.github.benmanes.caffeine.cache.Cache<Object, Object> longLived =
                Caffeine.newBuilder()
                        .ticker(ticker)
                        .maximumSize(1_000)
                        .expireAfterWrite(Duration.ofSeconds(40))
                        .build();
        manager.registerCustomCache("longItems", longLived);

        return manager;
    }
}
~~~

**Vì sao thứ tự cấu hình như vậy?**

1. Tạo manager.
2. `setCaffeine` khai báo builder mặc định; khi manager tạo `defaultItems`, nó sẽ dùng chính sách mặc định.
3. `setCacheNames` công bố vùng chung và khóa việc tự sinh tên mới ngoài danh sách. Đây là hợp đồng tên vùng **không thay thế** các custom cache đăng ký sau đó.
4. `registerCustomCache` nhận hai native cache **đã build**, áp dụng riêng 5 giây và 40 giây. Hai vùng này không bị ép theo TTL 30 giây của default builder.

Tất cả cache cùng dùng một `ManualTicker` để output demo nhất quán. Để tránh nhầm type, ví dụ dùng tên đầy đủ `com.github.benmanes.caffeine.cache.Cache<Object,Object>` cho native cache và kiểu `org.springframework.cache.CacheManager` cho Spring manager.

**Điều cần kiểm tra:** khi gọi `manager.getCache("shortItems")` hay `"longItems"`, Spring tìm đúng cache custom đã đăng ký; `getCache("defaultItems")` tìm vùng mặc định; `getCache("unknown")` là `null` trong cấu hình static mode này.

### 4.3. CatalogService.java — ba phương thức dùng cùng một key

Tạo `src/main/java/example/caffeinecustom/CatalogService.java`:

~~~java
package example.caffeinecustom;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger shortLoads = new AtomicInteger();
    private final AtomicInteger longLoads = new AtomicInteger();
    private final AtomicInteger defaultLoads = new AtomicInteger();

    @Cacheable(cacheNames = "shortItems", key = "#p0")
    public String shortItem(String id) {
        int n = shortLoads.incrementAndGet();
        System.out.println("LOAD short #" + n);
        return "S-" + n;
    }

    @Cacheable(cacheNames = "longItems", key = "#p0")
    public String longItem(String id) {
        int n = longLoads.incrementAndGet();
        System.out.println("LOAD long #" + n);
        return "L-" + n;
    }

    @Cacheable(cacheNames = "defaultItems", key = "#p0")
    public String defaultItem(String id) {
        int n = defaultLoads.incrementAndGet();
        System.out.println("LOAD default #" + n);
        return "D-" + n;
    }
}
~~~

Cả ba method đều dùng key `"K1"` trong demo, nhưng **ba vùng khác nhau** nên việc nạp và TTL độc lập. Các chuỗi `S-1`, `L-1`, `D-1` thể hiện **lần chạy thân method**, không phải dữ liệu database.

`@Cacheable` sẽ dùng Spring proxy: khi hit, thân method không chạy và bộ đếm không tăng. Khi miss vì TTL, method chạy và đặt một giá trị mới. Các phương thức được gọi từ một Spring bean khác (`CommandLineRunner`), tránh self-invocation.

### 4.4. CustomCacheDemoApplication.java — kiểm tra bằng thời gian giả

Tạo `src/main/java/example/caffeinecustom/CustomCacheDemoApplication.java`:

~~~java
package example.caffeinecustom;

import java.time.Duration;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CustomCacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomCacheDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            CatalogService catalog,
            CacheManager manager,
            ManualTicker ticker) {

        return args -> {
            System.out.println("known = " +
                    (manager.getCache("shortItems") != null
                     && manager.getCache("longItems") != null
                     && manager.getCache("defaultItems") != null));
            System.out.println("unknown = " +
                    (manager.getCache("notRegistered") == null));

            // T = 0 giây; lần đầu cả ba vùng đều miss.
            System.out.println("short@0 = " +
                    catalog.shortItem("K1"));
            System.out.println("long@0 = " +
                    catalog.longItem("K1"));
            System.out.println("default@0 = " +
                    catalog.defaultItem("K1"));
            System.out.println("short@0 again = " +
                    catalog.shortItem("K1"));

            // T = 6 giây: chỉ shortItems (TTL 5 giây) đã hết hạn.
            ticker.advance(Duration.ofSeconds(6));
            System.out.println("short@6 = " +
                    catalog.shortItem("K1"));
            System.out.println("long@6 = " +
                    catalog.longItem("K1"));
            System.out.println("default@6 = " +
                    catalog.defaultItem("K1"));

            // T = 31 giây: default đã hết hạn; long chưa.
            ticker.advance(Duration.ofSeconds(25));
            System.out.println("short@31 = " +
                    catalog.shortItem("K1"));
            System.out.println("long@31 = " +
                    catalog.longItem("K1"));
            System.out.println("default@31 = " +
                    catalog.defaultItem("K1"));

            // T = 41 giây: long (40 giây từ T=0) đã hết hạn;
            // default mới nạp ở T=31 nên vẫn còn hiệu lực.
            ticker.advance(Duration.ofSeconds(10));
            System.out.println("long@41 = " +
                    catalog.longItem("K1"));
            System.out.println("default@41 = " +
                    catalog.defaultItem("K1"));
        };
    }
}
~~~

Chạy tại thư mục dự án:

~~~bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
~~~

**Những dòng do `System.out` in ra, theo đúng thứ tự**, không tính log Spring Boot/Gradle:

~~~text
known = true
unknown = true
LOAD short #1
short@0 = S-1
LOAD long #1
long@0 = L-1
LOAD default #1
default@0 = D-1
short@0 again = S-1
LOAD short #2
short@6 = S-2
long@6 = L-1
default@6 = D-1
LOAD short #3
short@31 = S-3
long@31 = L-1
LOAD default #2
default@31 = D-2
LOAD long #2
long@41 = L-2
default@41 = D-2
~~~

**Diễn giải từng giai đoạn:**

- **T = 0:** mỗi vùng đều miss key `K1` một lần; lần `shortItem("K1")` thứ hai hit nên không in thêm `LOAD short`.
- **T = 6:** entry `shortItems["K1"]` sinh ở T=0 đã quá hạn 5 giây, nạp thành `S-2`. `longItems` (40 giây) và `defaultItems` (30 giây) vẫn hit, giữ `L-1` và `D-1`.
- **T = 31:** entry `shortItems` vừa tạo tại T=6 cũng đã quá hạn 5 giây, nạp `S-3`; `longItems` giữ `L-1` vì từ T=0 mới qua 31 giây; `defaultItems` quá hạn 30 giây nên nạp `D-2`.
- **T = 41:** entry `longItems` tạo ở T=0 đã quá hạn 40 giây, nạp `L-2`. `defaultItems` vừa được nạp ở T=31, tuổi 10 giây nhỏ hơn TTL 30 giây nên hit, vẫn `D-2`.

**Vì sao output có thể kiểm chứng chính xác?** Các cache dùng chung `ManualTicker` và các lời gọi chạy tuần tự trong `CommandLineRunner`. Khi khởi động mới, bộ đếm và ticker đều bắt đầu từ 0. Provider kiểm tra expiry lúc lookup: entry đã hết hạn không được trả lại dù cleanup vật lý có thể diễn ra trễ. Đây là demo có **bốn class Java trong một ứng dụng Spring Boot**, cần Gradle/Spring dependencies; không phải một file có thể chạy với `javac` trần.

## 5. Custom cache thực sự khác default cache ở đâu?

Trong code trên:

~~~java
manager.setCaffeine(Caffeine.newBuilder()
        .maximumSize(500)
        .expireAfterWrite(Duration.ofSeconds(30)));

manager.setCacheNames(List.of("defaultItems"));

manager.registerCustomCache("shortItems",
        Caffeine.newBuilder()
                .maximumSize(100)
                .expireAfterWrite(Duration.ofSeconds(5))
                .build());
~~~

Đây là **đoạn minh họa rút gọn**, không bao gồm `Ticker`; trong chương trình ở mục 4, tất cả builder được cấp cùng ticker để test.

Điều xảy ra:

1. `defaultItems` được tạo bởi manager theo builder chung; TTL 30 giây, max 500.
2. `shortItems` được đưa vào manager như **một native Caffeine cache có builder riêng**; TTL 5 giây, max 100.
3. Nếu cấu hình manager ở chế độ **dynamic** thay vì static, một tên mới không custom có thể được tạo khi lookup, nhưng nó vẫn dùng builder **chung**, không tự suy ra TTL riêng theo tên. 
4. Nếu để `setCacheNames` ở static mode, tên không đăng ký không được tạo ngẫu nhiên; giúp phát hiện lỗi cấu hình.
5. Mọi annotation dùng `cacheNames` phải trùng chính xác với tên đã đăng ký, ví dụ `"shortItems"` khác `"shortItem"`.

Cách cấu hình này phù hợp khi phần lớn cache có một policy mặc định và chỉ một số vùng cần điều chỉnh. Nếu **tất cả** vùng có chính sách riêng, vẫn có thể đăng ký từng cache, nhưng cần tổ chức danh sách chính sách tập trung để tránh copy/paste cấu hình lung tung.

## 6. Các tình huống cấu hình nâng cao

### 6.1. expireAfterWrite và expireAfterAccess

~~~java
Caffeine.newBuilder()
        .expireAfterWrite(Duration.ofMinutes(5));
~~~

Entry hết hạn dựa trên thời gian kể từ lần tạo hoặc lần **ghi/thay thế** giá trị gần nhất. Lookup hit thông thường không tự kéo dài thời hạn này.

~~~java
Caffeine.newBuilder()
        .expireAfterAccess(Duration.ofMinutes(5));
~~~

Entry hết hạn khi đã lâu không được truy cập; các truy cập phù hợp có thể kéo dài thời gian sống (*time-to-idle*). Đừng dùng `expireAfterAccess` cho dữ liệu cần có **tuổi tối đa** cố định mà request liên tục không được phép kéo dài.

Khi cần TTL riêng **cho từng entry**, Caffeine còn hỗ trợ `expireAfter(Expiry<K,V>)`. Đây là logic ở builder/implementation Caffeine, không phải một tham số `ttl=...` chung của `@Cacheable`.

### 6.2. Size eviction không giống TTL

~~~java
Caffeine.newBuilder()
        .maximumSize(1_000)
        .recordStats();
~~~

`maximumSize` giúp hạn chế số entry trong vùng, nhưng không quy định thời gian sống của entry. Backend có thể loại entry để giữ mức dung lượng, ngay cả khi TTL chưa hết. Thực tế cơ chế chọn entry bị loại là chính sách Caffeine, không đơn giản “xóa key lâu không đọc nhất” trong mọi trường hợp.

`recordStats` hữu ích để đo hit/miss/eviction; để đọc số liệu từ native cache, cần giữ reference đến instance hoặc dùng hệ thống metrics có tích hợp thích hợp (ví dụ Micrometer/Actuator khi được cấu hình). **Manager không tự xuất histogram hay dashboard chỉ vì gọi `recordStats()`**.

### 6.3. Caching null

Native Caffeine `Cache` không nhận `null` value. Spring `CaffeineCacheManager` thường hỗ trợ chuyển null sang sentinel theo `allowNullValues`; nếu đặt `setAllowNullValues(false)` như demo, một method trả `null` có thể gây lỗi khi muốn cache. Điều đó là chủ đích của demo vì cả ba loader luôn trả non-null strings.

Nếu nghiệp vụ cho phép “không tìm thấy”, xác định **negative caching** rõ ràng: có lưu null không, trong bao lâu, và có evict khi bản ghi được tạo không. Không mặc định mọi vùng sẽ có chính sách null như nhau khi custom adapter khác nhau, và không dùng null policy như một biện pháp xác thực.

### 6.4. Đồng bộ và cache stampede

`@Cacheable(sync = true)` có thể phối hợp việc load cùng key nếu implementation hỗ trợ. Nhưng điều đó không tự trở thành khóa **phân tán** xuyên các replica/JVM. Một cache Caffeine trong bộ nhớ là **local**; ba ứng dụng chạy trên ba JVM có ba bản cache độc lập, dù tên vùng và TTL giống nhau.

Khi quá nhiều entry hết hạn cùng lúc, backend có thể chịu nhiều miss và truy vấn nguồn đột biến. Giải pháp có thể bao gồm jitter TTL, request coalescing, warmup, giới hạn concurrency hoặc distributed cache, tùy nhu cầu.

### 6.5. Sửa dữ liệu và nhất quán

Custom TTL không tự biết database vừa đổi. Sau update/delete, ứng dụng vẫn có thể cần `@CacheEvict(cacheNames="...", key="...")`, `@CachePut` hoặc event-based invalidation. Một phương thức update có thể ảnh hưởng **nhiều vùng**; chỉ xóa `shortItems` không tự xóa `longItems`.

Nếu eviction thực thi trước database commit, một request khác có thể nạp lại giá trị cũ. Không có transaction atomic giữa database và bộ nhớ Caffeine mặc định. Với yêu cầu nghiêm ngặt, thiết kế after-commit invalidation, versioned values hoặc kiểm tra nhất quán theo nghiệp vụ.

### 6.6. Key và mutability

TTL riêng không sửa được lỗi key. Nếu hai tenant có cùng item ID nhưng dữ liệu khác nhau, `key="#p0"` có thể thiếu tenant. Đưa đủ yếu tố ảnh hưởng kết quả vào key, ví dụ record `(tenantId, itemId)` hoặc một key generator nhất quán. Đảm bảo authorization hoạt động **cả khi cache hit**.

Caffeine local thường lưu Java object theo **tham chiếu**. Nếu value là mutable DTO hoặc list, caller sửa sau khi nhận có thể ảnh hưởng entry được phục vụ cho request khác. Ưu tiên immutable DTO, defensive copy ở boundary và tránh cache entity ORM đang được quản lý trực tiếp.

## 7. Sai lầm thường gặp khi đăng ký custom caches

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ `setCaffeine` một TTL rồi mong từng cache name khác nhau có TTL riêng | Tất cả vùng tạo theo builder chung có cùng expiry | Dùng `registerCustomCache` với native cache được build riêng |
| Truyền `List<String>` vào `registerCustomCache` | Sai API/kiểu; method nhận native Cache instance | `registerCustomCache(name, Caffeine.newBuilder().build())` |
| Nhầm native Caffeine `Cache` với Spring `Cache` | Compile type mismatch hoặc dùng sai API | Phân biệt fully qualified type; manager adapt native cache cho Spring |
| Gọi `getCache("shortItem")` thay vì `"shortItems"` | Missing region trong static mode hoặc sinh vùng sai trong dynamic mode | Centralize tên vùng; test `getCacheNames()` |
| Tạo custom cache nhưng annotation trỏ vùng default khác | TTL riêng không có tác dụng cho method đó | Kiểm tra `cacheNames`, key và manager được resolve |
| Gắn TTL của provider vào `@Cacheable` như một attribute | Spring Cache annotation không có thuộc tính TTL chuẩn | Cấu hình native builder/provider |
| Không giới hạn số entry | Dùng bộ nhớ ngày càng lớn theo workload | Đặt `maximumSize`/`maximumWeight` và đo metrics |
| Coi TTL là exact event đúng mili giây | Logic phụ thuộc sai vào cleanup vật lý | Test tính hợp lệ ở lookup; đừng giả định callback chạy đúng TTL |
| Dùng `Thread.sleep` để test expiry | Test chậm/flaky | Dùng Caffeine `Ticker` giả lập như demo |
| Giữ `ManualTicker` ở production | TTL phụ thuộc thời gian nhân tạo không tiến nếu không advance | Chỉ sử dụng clock giả trong môi trường test |
| Nạp dữ liệu bằng self-invocation | Caching proxy có thể bị bỏ qua | Gọi qua Spring proxy/bean khác |
| Mong một local cache đồng bộ nhiều JVM | Dữ liệu stale khác nhau theo replica | Dùng event invalidation/distributed cache hoặc TTL/SLA phù hợp |
| Đăng ký lại tên cache với cấu hình khác ngoài ý muốn | Entry có thể mất hoặc chính sách thay đổi bất ngờ | Coi cache name/policy là contract, quản lý khi startup và test |

## 8. Cách xác minh cấu hình và hành vi

Một số câu hỏi kiểm tra tại startup:

~~~java
// Minh họa trong bean đã có CacheManager manager:
boolean shortExists =
        manager.getCache("shortItems") != null;
boolean longExists =
        manager.getCache("longItems") != null;
boolean defaultExists =
        manager.getCache("defaultItems") != null;
boolean unknownMissing =
        manager.getCache("typo") == null;
~~~

**Cần phân biệt hai loại test:**

- **Cấu hình:** tên cache có được đăng ký, đúng `CacheManager`, custom cache có TTL/size mong đợi. `getCache(name) != null` chỉ xác nhận region tồn tại.
- **Hành vi:** cùng key đọc lần đầu miss, lần thứ hai hit, sau TTL riêng trở thành miss; eviction do source update cũng hoạt động. Demo `ManualTicker` ở trên đo bằng số lần thực thi thân method.

Nếu muốn kiểm tra giá trị native policy mà không phụ thuộc API nội bộ, có thể giữ chính các biến native cache đã truyền vào `registerCustomCache` để viết integration tests hoặc dùng `CaffeineCache.getNativeCache()` từ adapter khi loại adapter phù hợp. Không dùng thủ thuật reflection để thay đổi cacheMap nội bộ của Spring.

### Các test nên có

1. **Độc lập theo tên:** gọi cùng key `K1` ở `shortItems` và `longItems`; lần đầu mỗi vùng đều miss.
2. **TTL khác nhau:** tại T=6, chỉ short đã expire; tại T=31, default đã expire nhưng long vẫn chưa; tại T=41, long đã expire.
3. **Key khác:** trong một vùng, key `K2` tạo miss riêng so với `K1`.
4. **Chính sách mặc định:** thêm một vùng qua `setCacheNames` mà không custom-register; xác minh nó dùng builder chung chứ không tự thừa hưởng TTL của short.
5. **Sai tên ở static mode:** `getCache("notRegistered") == null`; khi annotation dùng tên sai, phải xuất hiện lỗi resolve thay vì âm thầm tạo vùng.
6. **Maximum size:** đưa nhiều hơn số entry tối đa, đo số entry/hit rate và eviction; không đòi đúng một entry cụ thể bị loại nếu policy không bảo đảm thứ tự.
7. **Null:** cho loader trả `null` và quan sát chính sách `allowNullValues=false`.
8. **Update source:** thử thay source dữ liệu khi cache vẫn còn hiệu lực; sau đó evict key và quan sát kết quả mới.
9. **Nhiều replica:** kiểm chứng một JVM evict không tự tác động local cache ở JVM còn lại.
10. **Metrics:** bật `recordStats()`, xác nhận dữ liệu hit/miss/eviction được quan sát đúng.

## 9. Checklist khi code review

- [ ] Mọi cache region có tên nhất quán và hợp đồng dữ liệu/key rõ ràng.
- [ ] Chính sách chung do `setCaffeine` xác định; chỉ các vùng cần ngoại lệ dùng `registerCustomCache`.
- [ ] Custom caches được build **trước** khi đăng ký, với TTL/size phù hợp từng loại dữ liệu.
- [ ] Tên trong `@Cacheable`/`@CachePut`/`@CacheEvict` khớp với những tên manager cung cấp.
- [ ] Không nhầm `setCacheNames` với cấu hình per-cache; xác định rõ static hoặc dynamic mode.
- [ ] Test expiry bằng ticker và test miss/hit bằng bộ đếm/metrics, không dựa trên giá trị hiển thị giống nhau.
- [ ] Hiểu `expireAfterWrite`, `expireAfterAccess`, `maximumSize` và negative caching/allowNullValues.
- [ ] Có chiến lược xử lý update, giao dịch, nhiều instance và quá nhiều miss đồng thời.
- [ ] Không dùng fake ticker hoặc các tham số demo (5 giây/100 entries) như cấu hình production mặc định.
- [ ] Có integration test với phiên bản Spring và Caffeine thực tế đang triển khai.

## Tài liệu tham khảo

- Spring Framework — CaffeineCacheManager API (`registerCustomCache`, `setCacheNames`, `setCaffeine`): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework — Configuring the Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
- Caffeine — Eviction and Expiration (builder policies, Ticker): https://github.com/ben-manes/caffeine/wiki/Eviction
