# Giới hạn dung lượng, số khóa và dữ liệu lưu quá lâu trong Spring Cache

## Mục tiêu học tập

Cache giúp giảm số lần truy vấn nguồn và cải thiện độ trễ, nhưng cache **không được giới hạn** có thể trở thành nguyên nhân làm ứng dụng tốn RAM, gây áp lực GC, tăng chi phí Redis, hoặc tiếp tục trả dữ liệu đã lỗi thời. Trong Spring Framework, các annotation như `@Cacheable`, `@CachePut` và `@CacheEvict` quyết định **khi nào** đọc, ghi, xóa dữ liệu. Chính sách **giới hạn số entry, dung lượng, thời hạn sống và thuật toán eviction** chủ yếu do cache provider hoặc cấu hình hệ thống đảm trách.

Sau bài này, bạn sẽ biết cách:

1. Phân biệt dung lượng bộ nhớ, **số key** (*cardinality*), kích thước mỗi entry và tuổi dữ liệu.
2. Hiểu sự khác nhau giữa **expiration**, **eviction** và **explicit invalidation**.
3. Cấu hình Caffeine có `maximumSize`, `expireAfterWrite`, `expireAfterAccess`, và biết khi nào dùng `maximumWeight`.
4. Hiểu giới hạn Redis như `maxmemory`, `maxmemory-policy`, TTL của Spring Data Redis và các trường hợp Redis không tự xóa dữ liệu đúng như kỳ vọng.
5. Ngăn key tăng vô hạn do tham số quá đa dạng, input không chuẩn hóa hoặc cache name động.
6. Thiết kế chính sách làm mới và thu hồi khi dữ liệu nguồn thay đổi.
7. Đọc metrics, kiểm thử ranh giới bộ nhớ và xây ví dụ Java 17/Spring Boot có thể chạy để chứng minh TTL và giới hạn số entry.

**Nguyên tắc:** một cache tốt luôn có **phạm vi dữ liệu rõ**, **ngân sách tài nguyên** và **hợp đồng độ mới**. Tăng hit rate không phải mục tiêu duy nhất.

## 1. Ba giới hạn khác nhau

Xét một cache tên `"products"`:

~~~text
products
  key1 -> value1 (4 KiB)
  key2 -> value2 (8 KiB)
  key3 -> value3 (120 KiB)
  ...
~~~

Có ba rủi ro tách biệt:

| Rủi ro | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Số khóa quá lớn | Có quá nhiều **entry khác nhau** | Mỗi query string/người dùng/timestamp tạo key mới |
| Kích thước entry quá lớn | Mỗi giá trị giữ nhiều dữ liệu | Cache một file 10 MiB hoặc danh sách hàng trăm nghìn đối tượng |
| Dữ liệu lưu quá lâu | Entry vẫn tồn tại và có thể được trả sau khi nguồn đổi | Giá/stock/quyền truy cập đã thay đổi nhưng cache hit bản cũ |

Các chỉ số liên quan nhưng không thay thế nhau:

~~~text
Estimated retained memory
    ≈ number_of_entries × average_retained_bytes_per_entry
    + metadata, key objects, references, index và overhead provider
~~~

Công thức là một **ước lượng**, không phải phép đo heap chuẩn. Trong JVM, kích thước đối tượng còn chịu ảnh hưởng object header, alignment, references, interned/shared objects, GC và cách provider lưu key/value. Ở Redis, chi phí còn gồm cấu trúc keyspace, encoding, allocator, replication và bộ nhớ phục vụ lệnh.

Một cache 100 entry vẫn có thể rất lớn nếu mỗi entry vài megabyte. Một cache có entry rất nhỏ vẫn có thể ngốn nhiều RAM nếu key phát triển tới hàng triệu. TTL giúp hạn chế tuổi entry, nhưng **không tự bảo đảm** số entry ở một thời điểm luôn thấp: nếu tốc độ sinh key mới cao, hàng triệu key có thể cùng tồn tại trong cửa sổ TTL.

### Cardinality khác với số request

~~~text
1,000,000 request cho cùng key "P1"
    -> có thể chỉ cần 1 entry

1,000,000 request có 1,000,000 key riêng
    -> có thể tạo 1,000,000 entry
~~~

Với key vô hạn như timestamp đến mili giây, random UUID mới mỗi request hoặc query string không chuẩn hóa, cache có thể gần như **không bao giờ hit** nhưng vẫn phải trả giá lưu entry.

## 2. `@Cacheable` không tự ấn định TTL hoặc dung lượng

Ví dụ:

~~~java
// Minh họa trong Spring-managed service, không phải file chạy độc lập.
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) {
    return repository.find(id);
}
~~~

Annotation này không khai báo "giữ tối đa 10.000 entry" hay "hết hạn sau 5 phút". Nó chỉ biểu thị **cache theo key**. Cache abstraction của Spring tương tác với `CacheManager`/`Cache` mà không áp đặt một chính sách bộ nhớ thống nhất cho mọi backend.

Nếu không thêm provider cụ thể, Spring Boot có thể dùng cache **simple** trên `ConcurrentMapCacheManager`. Vùng cache dựa trên concurrent map không được thiết kế để tự áp dụng TTL/giới hạn tối đa tương tự Caffeine/Redis. Trong ứng dụng chạy lâu, cache các ID đa dạng bằng map không giới hạn là một rủi ro thực tế.

Đừng suy rằng "có `@Cacheable` thì chắc Spring tự xóa entry cũ" hoặc "provider nào cũng tự dùng LRU". Phải kiểm tra cấu hình **provider thật** mà application sử dụng và cách mỗi cache được tạo.

### Tên cache không phải số key

~~~text
cache name = "products"
key        = "P1", "P2", "P3", ...
~~~

Một cache name có thể chứa rất nhiều key. Nếu đặt tên cache động theo user/request thay vì key phù hợp, hệ thống còn có thể sinh rất nhiều **cache instance** mới, gây rối việc giới hạn và giám sát. Tên cache thường nên là tập hữu hạn theo loại dữ liệu/nghiệp vụ; key mới thể hiện định danh của từng kết quả. Nếu thật sự phải chia namespace tenant, cần chính sách giới hạn số namespace và vòng đời rõ ràng.

## 3. Ba cơ chế dễ nhầm: expiration, eviction và invalidation

| Cơ chế | Khi xảy ra | Câu hỏi được giải quyết |
| --- | --- | --- |
| **Expiration** | Entry vượt quá thời hạn/thời gian nhàn rỗi đã cấu hình | Giá trị có còn đủ mới để trả từ cache không? |
| **Capacity eviction** | Cache cần giảm số entry/trọng số/bộ nhớ | Cache có vượt ngân sách tài nguyên không? |
| **Explicit invalidation** | Ứng dụng chủ động xóa/ghi entry khi nguồn thay đổi | Entry nào trở nên không hợp lệ về nghiệp vụ? |

Ba cơ chế có thể được dùng cùng lúc:

~~~text
@Cacheable đọc "P1"
       |
       +-- cache hit và entry chưa expired -> trả nhanh
       |
       +-- miss / expired / evicted
                |
                v
           tải dữ liệu nguồn
                |
                v
           put vào cache
                |
                v
           provider có thể evict mục khác khi đầy
~~~

Giới hạn số entry **không bảo đảm dữ liệu mới**. TTL **không bảo đảm dùng ít bộ nhớ** khi traffic và cardinality lớn. `@CacheEvict` chính xác giúp nhất quán sau update, nhưng không tự tạo một giới hạn RAM tổng thể. Cần kết hợp phù hợp.

### TTL: thời gian từ lần ghi

`expireAfterWrite = 5 phút` nghĩa là entry hết hạn khoảng 5 phút sau lần tạo/ghi cuối. Những lần **đọc** không kéo dài tuổi theo chính sách này. Nếu value được ghi lại, mốc thời gian tính từ lần ghi mới, theo semantics của provider.

~~~text
T=00:00 write P1
T=04:59 read P1  -> có thể hit
T=05:01 read P1  -> expired, phải load lại
~~~

### Time-to-idle: thời gian từ lần truy cập

`expireAfterAccess = 5 phút` thường cho phép entry sống tiếp khi được đọc/ghi thường xuyên. Phù hợp với dữ liệu có tính locality nhưng **không phải giới hạn tuổi tuyệt đối**: key cực nóng có thể còn tồn tại rất lâu và vẫn stale nếu nguồn không được invalidation.

~~~text
T=00 write P1
T=04 read P1  -> reset thời gian idle
T=08 read P1  -> vẫn hit nếu chưa idle đủ lâu
T=14 read P1  -> có thể expired nếu không có read/write từ T=08
~~~

Nếu nghiệp vụ yêu cầu "dữ liệu không được cũ quá 5 phút", `expireAfterAccess=5m` **không đáp ứng** điều đó vì các lần đọc có thể kéo dài tuổi mãi. Chọn TTL theo write, refresh/invalidation hoặc kiểm tra version/độ mới phù hợp.

### Eviction khi cache đầy

Với chính sách giới hạn số entry, provider có thể loại một hoặc nhiều mục để chừa chỗ cho mục mới. Đừng mặc định entry bị evict chắc chắn là "ít dùng gần nhất" trừ khi provider và cấu hình cụ thể bảo đảm thuật toán đó. Caffeine dùng chính sách admission/eviction nhằm tối ưu hit rate và có thể trì hoãn một số việc dọn dẹp đến thời điểm maintenance. Kết quả eviction có thể thay đổi theo lịch truy cập, contention và thuật toán.

## 4. Cấu hình Caffeine trong Spring Boot

Caffeine là cache hiệu năng cao **trong bộ nhớ JVM**, tích hợp với Spring qua `CaffeineCacheManager`. Đây là lựa chọn phổ biến để giới hạn **số entry** và tuổi dữ liệu khi cache dùng cục bộ trên mỗi application instance.

Với Spring Boot có dependency Caffeine và `@EnableCaching`, một cấu hình qua properties:

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=products,productSummaries
spring.cache.caffeine.spec=maximumSize=10000,expireAfterWrite=600s,recordStats
~~~

Giải thích:

- `maximumSize=10000`: số entry mục tiêu tối đa **trên từng cache instance** do cấu hình này tạo ra. Đây không phải tổng số entry của tất cả cache/tất cả JVM.
- `expireAfterWrite=600s`: entry quá thời hạn từ lần ghi sẽ không còn được trả như hit hợp lệ.
- `recordStats`: bật thống kê nội bộ Caffeine để theo dõi hit/miss, eviction và load tùy các đường thao tác.
- `spring.cache.cache-names`: khai báo danh sách tên vùng, giúp dễ quản lý hơn so với tạo vô hạn.
- `spring.cache.type=caffeine`: chọn provider Caffeine cho auto-configuration tương thích.

`maximumSize` là **giới hạn số lượng entry**, không phải 10.000 byte hay 10.000 MiB. Nếu mỗi value cực lớn, bạn vẫn có thể dùng quá nhiều heap trước khi đạt 10.000 entry. `maximumSize` cũng không bảo đảm heap ứng dụng có đủ chỗ cho cache.

**Lưu ý:** khi bạn tự khai báo `@Bean CacheManager`, cấu hình builder của bean đó là nguồn cấu hình chính; không giả định các property auto-configuration ở trên sẽ tự ghi đè bean tùy chỉnh.

### `maximumSize` hay `maximumWeight`?

Caffeine có thể giới hạn theo **trọng số** với `maximumWeight(...)` và `weigher(...)`. Trọng số do ứng dụng định nghĩa, không phải phép đo byte heap tự động.

~~~java
// Minh họa Caffeine builder, không phải file chạy độc lập.
// Giả sử Cache<String, byte[]>; dùng độ dài byte[] làm trọng số.
var cache = com.github.benmanes.caffeine.cache.Caffeine.newBuilder()
    .maximumWeight(10L * 1024 * 1024)
    .weigher((String key, byte[] value) -> value.length)
    .build();
~~~

Trong ví dụ, ngân sách trọng số khoảng 10 MiB **payload byte[]**, nhưng còn overhead key/object/index chưa tính. Trọng số được tính khi đưa/cập nhật entry, không tự cập nhật khi đối tượng value bị sửa trực tiếp sau khi lưu. Vì thế nên ưu tiên value bất biến, hoặc bảo đảm cập nhật thông qua cache put.

Không kết hợp `maximumSize` và `maximumWeight` trên cùng Caffeine builder: hãy chọn **một chính sách dung lượng**. Nếu các value gần tương đương kích thước, `maximumSize` dễ hiểu. Nếu value có kích thước chênh lệch lớn và có cách cân trọng số hợp lý, `maximumWeight` có thể sát ngân sách hơn.

### `expireAfterWrite`, `expireAfterAccess`, `refreshAfterWrite`

| Cấu hình | Tác dụng chính | Rủi ro khi dùng sai |
| --- | --- | --- |
| `expireAfterWrite` | Hết hạn sau thời gian từ lần ghi | Nhiều key có thể expire gần nhau, tăng miss |
| `expireAfterAccess` | Hết hạn sau thời gian không truy cập | Entry nóng có thể lưu rất lâu, stale |
| `refreshAfterWrite` | Đánh dấu entry đủ điều kiện refresh sau một thời gian | **Không phải TTL**; có thể tiếp tục trả giá trị cũ trong lúc làm mới |
| `maximumSize` | Giới hạn số entry theo cơ chế eviction | Không hạn chế byte của từng value |
| `maximumWeight` + `weigher` | Giới hạn tổng trọng số do ứng dụng khai báo | Trọng số sai không phản ánh RAM thật |

`refreshAfterWrite` không thay thế `expireAfterWrite`: khi đủ điều kiện, cơ chế refresh thường đòi **loading cache/loader** và lần truy cập để kích hoạt; trong lúc refresh có thể dùng giá trị cũ. Với `@Cacheable` đơn thuần và cache không được cấu hình loader/refresh thích hợp, đừng mặc định bật `refreshAfterWrite` là dữ liệu sẽ tự được làm mới đúng thời hạn. Kiểm thử đường loader của provider đang dùng.

### Expiration có nhất thiết xóa vật lý đúng thời khắc?

Không. Với nhiều local cache, một entry đã expired sẽ không được trả như hit, nhưng việc **dọn vật lý** khỏi các cấu trúc dữ liệu có thể được thực hiện trong lần truy cập/ghi hoặc maintenance. Muốn quản lý RAM nghiêm ngặt cần quan sát heap và chiến lược maintenance, không chỉ xét thời điểm `get()` trả miss. `Cache.cleanUp()` trong Caffeine phục vụ maintenance; nó không phải thao tác để mọi request thường ngày phải gọi.

## 5. Ví dụ chạy được: Caffeine giới hạn hai entry và TTL năm phút

Ví dụ dùng **Java 17, Spring Boot 3.3.5, Maven**. Ta cấu hình `CaffeineCacheManager` với:

- `maximumSize(2)`: cache `"catalog"` bị giới hạn hai entry theo cơ chế eviction.
- `expireAfterWrite(Duration.ofMinutes(5))`: entry quá năm phút từ lần ghi thì hết hạn.
- Một **ticker giả lập** (`ManualTicker`) để tiến thời gian 6 phút ngay lập tức, giúp kiểm chứng TTL **không cần chờ thật**.
- `recordStats()` để có thể xem thống kê từ Caffeine native cache.

Không dùng timestamp hiện tại làm key; `"P1"`, `"P2"`, `"P3"` là các định danh ổn định. `@Cacheable` chỉ chạy phần load khi miss.

### Cấu trúc thư mục

~~~text
bounded-cache-demo/
├── pom.xml
└── src/main/java/example/bounded/
    ├── DemoApplication.java
    ├── ManualTicker.java
    └── CatalogService.java
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
    <artifactId>bounded-cache-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
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

Spring Boot parent quản lý phiên bản của các dependency tương thích; không cần đặt phiên bản Caffeine riêng trong mẫu này.

### `src/main/java/example/bounded/ManualTicker.java`

~~~java
package example.bounded;

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
            throw new IllegalArgumentException("Duration must not be negative");
        }
        nanos.addAndGet(duration.toNanos());
    }
}
~~~

Trong test, `ManualTicker` thay đồng hồ thời gian monotonic của Caffeine. Không dùng ticker này trong production vì thời gian sẽ **đứng yên** nếu không có code gọi `advance`. Production nên dùng ticker thực của Caffeine.

### `src/main/java/example/bounded/CatalogService.java`

~~~java
package example.bounded;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger sourceLoads = new AtomicInteger();

    public record Entry(String productId, int generation) {}

    @Cacheable(
            cacheNames = "catalog",
            key = "#p0",
            unless = "#result == null"
    )
    public Entry find(String productId) {
        int generation = sourceLoads.incrementAndGet();
        return new Entry(productId, generation);
    }

    public int sourceLoads() {
        return sourceLoads.get();
    }
}
~~~

Trong ví dụ này, mỗi lần chạy method tạo một `generation` tăng lên, mô phỏng nguồn dữ liệu có kết quả mới. `generation` **không phải version DB thật**; nó chỉ giúp nhìn thấy cache hit, miss và expiry từ output.

### `src/main/java/example/bounded/DemoApplication.java`

~~~java
package example.bounded;

import java.time.Duration;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ManualTicker manualTicker() {
        return new ManualTicker();
    }

    @Bean
    CaffeineCacheManager cacheManager(ManualTicker ticker) {
        CaffeineCacheManager manager = new CaffeineCacheManager("catalog");
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(2)
                .expireAfterWrite(Duration.ofMinutes(5))
                .ticker(ticker)
                .recordStats());
        return manager;
    }

    @Bean
    CommandLineRunner demo(CatalogService service,
                           ManualTicker ticker,
                           CaffeineCacheManager manager) {
        return args -> {
            System.out.println("first=" + service.find("P1"));
            System.out.println("hit=" + service.find("P1"));
            System.out.println("sourceLoads=" + service.sourceLoads());

            ticker.advance(Duration.ofMinutes(6));
            System.out.println("after-ttl=" + service.find("P1"));
            System.out.println("sourceLoads=" + service.sourceLoads());

            service.find("P2");
            service.find("P3");

            CaffeineCache cache = (CaffeineCache) manager.getCache("catalog");
            cache.getNativeCache().cleanUp();
            System.out.println("size-within-2="
                    + (cache.getNativeCache().estimatedSize() <= 2));
        };
    }
}
~~~

### Chạy và đọc kết quả

Từ thư mục `bounded-cache-demo`, dùng JDK 17+ và Maven:

~~~bash
mvn -q spring-boot:run
~~~

Bên cạnh log khởi động Spring, các dòng do `CommandLineRunner` tự in sẽ là:

~~~text
first=Entry[productId=P1, generation=1]
hit=Entry[productId=P1, generation=1]
sourceLoads=1
after-ttl=Entry[productId=P1, generation=2]
sourceLoads=2
size-within-2=true
~~~

Giải thích từng dòng:

1. `find("P1")` lần đầu miss, method chạy và sinh `generation=1`; cache ghi entry.
2. Lần `find("P1")` tiếp theo chưa có thời gian giả lập trôi qua, nên hit; `sourceLoads` vẫn là 1.
3. `ticker.advance(6 phút)` làm thời gian Caffeine tăng vượt TTL cấu hình là 5 phút. Lần `find("P1")` tiếp theo miss và tạo `generation=2`.
4. `find("P2")` và `find("P3")` có hai key khác. Khi cần, provider loại bớt entry để bảo đảm ngân sách hai mục.
5. Sau `cleanUp()`, `estimatedSize() <= 2` cho kết quả `true`. Demo **cố ý không khẳng định chính xác** P1, P2 hay P3 bị evict: chính sách eviction có thể chọn entry khác nhau.

Như vậy, demo chứng minh **cả tuổi entry lẫn số entry** trên một cache instance. Nó không đo byte heap, không có Redis, không đồng bộ nhiều JVM và chưa xử lý cập nhật database. Những yêu cầu ấy cần chính sách riêng.

### Muốn dùng cấu hình production đơn giản hơn?

Khi không cần ticker giả lập, thường có thể **bỏ `@Bean CaffeineCacheManager` trong demo** và dùng `spring.cache.caffeine.spec` cùng `spring.cache.cache-names` như ở mục 4. Không được vừa giữ custom bean rồi giả định properties auto-config sẽ thay nó. Trong production cần chọn TTL và số entry theo dữ liệu, không sao chép nguyên con số 2 hoặc 5 phút từ bài học.

## 6. Redis: TTL trên từng key và giới hạn bộ nhớ toàn server

Redis là một **kho cache dùng chung qua mạng**, nên ngân sách dung lượng khác Caffeine local:

- Caffeine local: bộ nhớ của **mỗi JVM**, cộng dồn khi triển khai nhiều replica.
- Redis: bộ nhớ trên **Redis node/cluster**, chia sẻ cho nhiều ứng dụng nếu dùng chung instance.
- Spring Data Redis `RedisCacheManager`: quản lý cache theo tên, prefix và serializer; TTL được áp dụng lên các key của cache theo cấu hình.
- Redis server: `maxmemory` và `maxmemory-policy` quyết định hành vi khi đạt ngưỡng bộ nhớ cấu hình.

Đừng nhầm `spring.cache.redis.time-to-live` với `maxmemory`: một bên là tuổi entry; bên kia là ngưỡng bộ nhớ của server Redis.

### Ví dụ cấu hình TTL trong Spring Boot

Khi ứng dụng đã thêm dependency Spring Data Redis, khai báo kết nối và dùng `RedisCacheManager` tương ứng, có thể đặt:

~~~properties
spring.cache.type=redis
spring.cache.cache-names=products,referenceData
spring.cache.redis.time-to-live=10m
spring.cache.redis.cache-null-values=false
spring.cache.redis.use-key-prefix=true
~~~

Các property ở đây là **minh họa cấu hình Redis provider**, không thể chạy trong demo Caffeine ở trên nếu không thêm Redis dependency và server. `time-to-live=10m` là TTL cố định cho entry theo cấu hình Boot; cần kiểm tra cache nào có thể dùng chung chính sách. Dữ liệu tham chiếu ít thay đổi và dữ liệu giá cập nhật thường xuyên có thể cần TTL riêng.

Có thể thiết lập TTL theo tên cache bằng cấu hình Java:

~~~java
// Đoạn cấu hình minh họa, cần dependency Spring Data Redis
// và RedisConnectionFactory trong ứng dụng.
@Bean
RedisCacheManager cacheManager(RedisConnectionFactory factory) {
    RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10))
                .disableCachingNullValues();

    return RedisCacheManager.builder(factory)
            .cacheDefaults(defaults)
            .withCacheConfiguration(
                "referenceData",
                defaults.entryTtl(Duration.ofHours(1)))
            .build();
}
~~~

Để đoạn cấu hình trở thành mã biên dịch, cần import `RedisCacheManager`, `RedisCacheConfiguration`, `RedisConnectionFactory`, `Duration`, `Bean` và dependency tương ứng; đây **không phải file chạy độc lập**. Chính sách ví dụ: mặc định 10 phút, riêng `"referenceData"` là 1 giờ.

Theo Spring Data Redis, cấu hình cache mặc định có **key expiration = none** nếu bạn không đặt TTL; null caching và prefix cũng có defaults riêng. Không nên suy rằng Redis cache entry tự biến mất sau một khoảng thời gian hữu hạn nếu chưa cấu hình.

### TTL không phải TTI

TTL thông thường trên Redis được set/reset khi ghi; một lần đọc bằng `GET` **không** tự gia hạn. Nếu muốn hành vi giống time-to-idle, Spring Data Redis có hỗ trợ lựa chọn `enableTimeToIdle()` trên những phiên bản phù hợp, sử dụng lệnh Redis `GETEX` để đọc và gia hạn TTL.

Cần kiểm tra tối thiểu:

1. Redis server từ **6.2** trở lên có `GETEX`.
2. `RedisCacheConfiguration` có TTL và đã bật TTI theo API phiên bản đang dùng.
3. **Mọi** đường đọc/ghi liên quan phải dùng thao tác có semantics gia hạn; một module dùng `GET` thuần có thể không reset thời gian.
4. TTI giữ key nóng tồn tại lâu, không bảo đảm độ mới tuyệt đối.

Không tự bật TTI cho mọi cache với mong muốn giảm bộ nhớ, vì key nóng có thể sống lâu hơn TTL theo write.

### `maxmemory` và chính sách eviction của Redis

Ví dụ cấu hình **trên Redis server** (không phải annotation Spring):

~~~conf
maxmemory 512mb
maxmemory-policy allkeys-lru
~~~

Ý nghĩa: đặt ngưỡng bộ nhớ Redis và dùng một chính sách chọn key để evict khi cần. `allkeys-lru` là lựa chọn dựa trên xấp xỉ least recently used; Redis còn có các chính sách khác như LFU, random và nhóm `volatile-*` chỉ xét những key có TTL. Đừng khẳng định một policy duy nhất là tốt cho mọi workload.

Một số điểm cần nhớ:

- `maxmemory` là ngưỡng cấu hình **của Redis node**, không phải giới hạn 512 MiB riêng cho cache `"products"`.
- Các policy `allkeys-*` có thể evict cả key không có TTL nếu chúng thuộc vùng dữ liệu Redis chịu chính sách ấy.
- `volatile-*` chỉ có các key có expire để lựa chọn; nếu thiếu key đủ điều kiện, Redis có thể không giải phóng được bộ nhớ cần thiết và thao tác ghi có thể thất bại.
- Với `noeviction`, Redis thường từ chối các lệnh làm tăng bộ nhớ khi đạt ngưỡng, tùy lệnh và cấu hình.
- Redis không tự phân biệt "key của app A quan trọng hơn app B" khi các ứng dụng cùng dùng một instance và policy chung.
- Overhead, replica buffer, fragmentation và memory accounting làm bộ nhớ thực tế khác giá trị payload thuần; theo dõi metrics trên Redis thay vì chỉ ước lượng kích thước từng value.

Trong Redis Cluster, đánh giá giới hạn và áp lực bộ nhớ **theo node/shard**. Một keyspace phân phối không đều có thể làm một node chịu nhiều áp lực hơn dù tổng dung lượng toàn cluster còn dư.

### Prefix và số lượng key

Mặc định Spring Data Redis thường prefix key cache theo tên cache, chẳng hạn:

~~~text
products::P1
referenceData::currency:USD
~~~

Prefix giúp giảm va chạm giữa các cache nhưng không tự giới hạn cardinality. Nếu key được xây từ raw search query, tenant ID, user ID, page, sort và timestamp, số lượng kết hợp vẫn có thể khổng lồ. Đừng bỏ key prefix tùy tiện nếu nhiều cache/application dùng chung Redis.

Trong vận hành, ưu tiên `SCAN` có kiểm soát để lấy mẫu/khảo sát keyspace thay vì dùng `KEYS *` trên một Redis production lớn. Khi `RedisCacheWriter` xóa toàn vùng, cần kiểm tra chiến lược batch; tài liệu Spring Data Redis mô tả mặc định liên quan `KEYS`/`DEL` và tùy chọn `SCAN` theo driver/topology.

## 7. Ngăn số key tăng vô hạn ngay từ thiết kế

Một cấu hình `maximumSize` chỉ là lớp bảo vệ cuối. Để cache có hiệu quả, bản thân key phải có **tỷ lệ tái sử dụng đủ cao**.

### Những mẫu key nguy hiểm

~~~java
// PHẢN VÍ DỤ: mỗi lần gọi sinh một key khác.
@Cacheable(cacheNames = "reports", key = "#p0 + ':' + T(java.util.UUID).randomUUID()")
public Report find(String id) {
    return repository.load(id);
}
~~~

Key UUID mới khiến hầu như không hit. Provider vẫn có thể tốn chi phí insert và eviction cho từng request. Tương tự, thêm `System.currentTimeMillis()`, `traceId`, `requestId`, nonce hoặc access token chưa cần thiết vào key sẽ tạo cardinality lớn và có thể làm lộ thông tin không nên lưu/log.

### Tổ hợp query bị bùng nổ

Một API tìm kiếm có tham số:

~~~text
tenant × keyword × filter × sort × page × pageSize × locale
~~~

Nếu mọi tổ hợp đều cache, hàng trăm nghìn key có thể xuất hiện ngay cả khi mỗi chiều chỉ có ít giá trị. Một số cách kiểm soát:

- Cache những truy vấn nóng với khả năng tái sử dụng cao, không cache tất cả raw query.
- Chuẩn hóa cú pháp có ý nghĩa tương đương, ví dụ filter order không ảnh hưởng truy vấn thì canonicalize trước khi tạo key.
- Giới hạn `pageSize`/`page`, chiều dài từ khóa và số filter theo hợp đồng API; validation độc lập với cache.
- Tách các kết quả cá nhân hóa vào scope đúng, đồng thời cân nhắc không cache kết quả quá đặc thù.
- Giới hạn số entry và TTL của cache query ngắn hơn cache dữ liệu tham chiếu.
- Đừng dùng dynamic cache name tùy người dùng nếu key/partitioning có thể giải quyết đúng hơn.

Khi canonicalize, phải giữ đúng ngữ nghĩa: ví dụ keyword phân biệt hoa/thường trong tìm kiếm thì tự chuyển lowercase có thể tạo nhầm cache hit. Không rút ngắn ID thành một hash code 32-bit duy nhất vì có thể gây collision; nếu dùng hash cho key dài, cân nhắc khả năng collision và cách giữ identity đầy đủ.

### Cache result quá lớn

~~~java
// PHẢN VÍ DỤ: mọi kết quả tìm kiếm đều đưa trọn danh sách vào cache.
@Cacheable(cacheNames = "allOrders", key = "#p0")
public List<Order> findAllOrders(String tenantId) {
    return repository.findEveryOrderForTenant(tenantId);
}
~~~

Một tenant có hàng triệu đơn hàng có thể khiến một entry cực lớn, kéo theo pause GC, serializer CPU, network latency hoặc Redis eviction. Có thể giới hạn query, trả kết quả phân trang, cache một DTO rút gọn hoặc cache từng entity khi hợp lý. Nhưng cache phân trang cũng tăng số key; cần ngân sách số key song song với kích thước entry.

Đừng cache payload nhạy cảm hoặc toàn bộ entity graph gồm các quan hệ lazy-loading nếu không có lý do rõ ràng. Kích thước bị giữ trong heap có thể lớn hơn rất nhiều so với JSON response nhìn thấy.

## 8. Dữ liệu lưu quá lâu gây stale và lỗi nghiệp vụ

Ngay cả khi bộ nhớ đủ, một entry còn tồn tại có thể **không còn đúng**.

~~~text
T0: find("P1") -> price=100; cache P1
T1: DB cập nhật price=120
T2: find("P1") -> cache hit price=100
~~~

Giảm TTL xuống 5 phút chỉ giới hạn *thời gian stale có thể kéo dài* trong một số giả định; không bảo đảm "read ngay sau update thấy dữ liệu mới". Nếu có yêu cầu **read-your-writes**, nên dùng `@CachePut` cùng key và cùng projection hoặc `@CacheEvict` sau update thành công, kết hợp đúng transaction và coordination.

~~~java
// Minh họa: find và update có cùng cacheName và key theo productId.
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String productId) {
    return repository.findById(productId);
}

@CacheEvict(cacheNames = "products", key = "#p0")
public void updatePrice(String productId, long price) {
    repository.updatePrice(productId, price);
}
~~~

Đoạn code chỉ minh họa trong service Spring với repository; không phải chương trình độc lập. `@CacheEvict` mặc định evict sau method hoàn thành thành công. Nếu transaction rollback hoặc cache update xảy ra sai điểm commit, dữ liệu cache có thể không nhất quán. Cần kiểm tra cấu hình transaction-aware, sự kiện after-commit hoặc chiến lược đồng bộ cụ thể.

**Giới hạn TTL không thay thế kiểm tra quyền:** một user bị thu hồi quyền có thể tiếp tục nhận entry cache nếu authorization đặt **chỉ trong thân** phương thức `@Cacheable`, bởi cache hit không chạy thân method. Đặt quyền ở nơi luôn được kiểm tra và phân chia key theo scope đáng tin nếu nội dung thay đổi theo user/tenant.

### `expireAfterAccess` có thể giữ stale vô thời hạn

Một entry được đọc liên tục có thể không idle đủ lâu để expired, dù dữ liệu nguồn đã đổi. Đây là lý do lựa chọn thời hạn cần dựa vào **hợp đồng độ mới**, không chỉ hit ratio. Nếu dữ liệu phải kiểm tra lại tối đa sau một khoảng thời gian, cân nhắc `expireAfterWrite`, refresh/invalidation hoặc xác thực version.

### Eviction không xảy ra vào đúng lúc nghiệp vụ cần

Khi capacity đầy, provider có thể loại bất kỳ entry được chọn theo policy. Nếu không loại entry stale `"P1"` mà lại loại entry còn hợp lệ `"P2"`, việc quản lý stale vẫn chưa giải quyết. Capacity eviction giúp **quản lý tài nguyên**, không phải xác nhận dữ liệu nghiệp vụ mới hay cũ.

## 9. Thiết kế TTL theo loại dữ liệu

Một TTL cho toàn bộ ứng dụng thường không phù hợp.

| Loại dữ liệu | Đặc trưng | Hướng chính sách tham khảo |
| --- | --- | --- |
| Cấu hình tham chiếu ít thay đổi | Được truy cập nhiều, update hiếm | TTL dài hơn, eviction có chủ đích khi đổi |
| Giá, stock, trạng thái workflow | Thay đổi thường xuyên | TTL ngắn, ưu tiên invalidate sau update |
| Kết quả search/pagination | Cardinality cao, tỷ lệ tái sử dụng không đều | TTL ngắn, capacity chặt, chỉ cache hot queries |
| Hồ sơ theo user/tenant | Dữ liệu nhạy cảm/phân mảnh | Key theo scope đáng tin; TTL + authorization/invalidation |
| Negative cache (`not found`) | Tránh truy vấn lặp khi ID không tồn tại | TTL ngắn có cân nhắc, không làm chậm việc thấy dữ liệu mới |
| Báo cáo tính toán đắt | Loader chậm, stale có thể chấp nhận | TTL/refresh theo SLA, bảo vệ stampede |
| Dữ liệu phải chính xác ngay tức thì | Không chấp nhận stale | Cân nhắc không cache hoặc invalidation/consistency nghiêm |

Bảng là **hướng tư duy**, không phải thông số TTL áp dụng ngay. Quyết định dựa vào: tần suất thay đổi, kích thước, mức chịu stale, chi phí load, số key, mức lưu lượng và khả năng invalidation.

Các cache lớn cũng có thể bị **cache stampede** khi nhiều key đồng thời hết hạn. Có thể thêm TTL jitter cho một số loại key nếu provider hoặc chính sách application hỗ trợ, hoặc làm mới nóng theo lịch. `@Cacheable(sync=true)` giúp phối hợp miss cùng key trong phạm vi mà provider hỗ trợ, nhưng không phải cam kết exactly-once trên toàn cluster.

## 10. Quan sát cache trong production

Không thể chọn đúng `maximumSize` và TTL chỉ bằng trực giác. Hãy đo ít nhất:

| Chỉ số | Câu hỏi |
| --- | --- |
| `estimatedSize`/entry count | Cache đang giữ bao nhiêu entry? |
| Hit/miss rate | Có tái sử dụng dữ liệu hay chỉ lưu nhiều key một lần? |
| Eviction count/weight | Cache đầy và phải loại entry thường xuyên không? |
| TTL expiry/miss sau expiry | Có đợt miss đồng loạt làm backend tăng tải không? |
| Load time/errors | Khi miss, truy vấn nguồn đắt hay dễ lỗi không? |
| Heap used/GC pause | Local cache có gây áp lực JVM không? |
| Redis `used_memory`, keyspace, evicted keys | Shared cache có gần ngưỡng bộ nhớ không? |
| Redis latency/network/serialization | Value quá lớn có làm tăng thời gian round trip không? |
| Stale read/age/version | Entry còn tồn tại có còn đúng hợp đồng độ mới không? |
| Cardinality theo cache name/tenant/query class | Loại key nào tăng bất thường? |

Caffeine có thống kê nội bộ khi bật `recordStats()`. Với Spring Boot Actuator và Micrometer, khả năng thu thập metrics còn phụ thuộc dependency, cache manager và cấu hình binding; không mặc định một tên metric tồn tại trong mọi dự án. Redis cũng có metrics server và các snapshot thống kê của Spring Data Redis ở những cấu hình hỗ trợ.

Không gắn **raw key, user ID, access token hoặc query text** làm tag metrics vì làm nổ cardinality của hệ thống giám sát và có thể lộ dữ liệu nhạy cảm. Thay bằng tag giới hạn như `cacheName`, nhóm loại kết quả hoặc tenant tier đã được quy định phù hợp.

### Quy trình kiểm toán dung lượng

1. Liệt kê các **cache name** hợp lệ và owner của chúng; tránh vùng tạo tự do vô hạn.
2. Ghi rõ schema key và những tham số tham gia; ước tính số key duy nhất theo ngày.
3. Đo kích thước giá trị thực khi serialized hoặc retained, gồm các trường hợp lớn nhất.
4. Chọn ngân sách memory/key count theo JVM/Redis node; dành headroom cho GC, traffic peak và các thành phần khác.
5. Đặt TTL/eviction và đo hit rate cùng source load. Tăng `maximumSize` chỉ khi có bằng chứng tăng hit rate đủ bù chi phí.
6. Giám sát alerts khi key growth hoặc memory tăng liên tục, eviction quá mạnh, source miss tăng và p95 latency xấu đi.
7. Thử warm-up/cold start, redeploy nhiều replica, Redis eviction và cache flush, không chỉ traffic bình thường.

### Trade-off: size nhỏ không luôn tốt

Cache quá nhỏ sẽ liên tục evict key hữu ích, khiến miss/thời gian đọc nguồn tăng. Cache quá lớn giữ những key ít dùng và tăng chi phí tài nguyên. Điểm cân bằng thường có thể tìm bằng thử nghiệm: tăng/giảm capacity rồi so sánh hit rate, load rate, p95 latency, GC và chi phí. Một giá trị cấu hình có ý nghĩa khi nó được gắn với **workload đo được**.

## 11. Vận hành Redis và multi-instance

Khi một ứng dụng chạy nhiều pod:

~~~text
App A (local Caffeine: 10k entries)
App B (local Caffeine: 10k entries)
App C (local Caffeine: 10k entries)
            |
            +---- cùng đọc nguồn DB
~~~

Tổng số entry cục bộ có thể lên tới khoảng 30k trên ba cache độc lập, thậm chí các entry trùng nhau. Bộ nhớ được tiêu thụ **trên từng JVM**. Nếu dùng Redis chung, ba app có thể chia sẻ một keyspace và TTL, nhưng phải tính đến serialization, network, Redis memory policy và rủi ro Redis trở thành điểm nghẽn.

Không đặt `maxmemory` Redis quá sát bộ nhớ RAM vật lý; Redis còn cần chỗ cho quá trình hoạt động, buffer, replica/client và fragmentation. Theo dõi metrics và workload thực tế. Nếu Redis dùng cho cả **cache có thể mất** và **dữ liệu có độ bền** như queue/session quan trọng, cấu hình eviction chung cần được thiết kế rất cẩn thận; nhiều kiến trúc nên tách những workload với yêu cầu khác nhau.

Một ứng dụng chạy nhiều phiên bản có thể đổi schema cache value/key. Nếu không version namespace hoặc không có cách dọn key cũ, dữ liệu đã lưu lâu có thể gây deserialization lỗi sau deploy. Hãy có kế hoạch migration/invalidation và TTL để hạn chế tuổi của phiên bản cũ.

### Giới hạn số key Redis theo cache name?

Redis `maxmemory` là giới hạn toàn node, **không phải một quota per cache name** của Spring. Nếu cần quota chặt cho từng ứng dụng/tenant/cache name, có thể cần phân chia instance/cluster, quy tắc admission theo ứng dụng, hoặc một cơ chế quản lý key riêng. Không tự suy rằng prefix `"products::"` làm Redis tính riêng dung lượng cho vùng products.

## 12. Các lỗi phổ biến

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Heap JVM tăng mãi | Simple concurrent-map cache không có TTL/capacity | Chọn provider có bounded size/expiry, đo heap |
| Hit rate thấp dù cache rất lớn | Mỗi request sinh key mới | Rà soát `requestId`, timestamp, raw query, key cardinality |
| Redis tăng key liên tục | Không TTL hoặc TTL quá dài | Đặt TTL phù hợp và kiểm tra keyspace |
| Caffeine bị OOM trước khi đạt `maximumSize` | Entry quá lớn hoặc có đối tượng bị giữ thêm nơi khác | Kiểm soát payload, cân `maximumWeight`/heap profiling |
| Dữ liệu stale dù đọc liên tục | `expireAfterAccess` kéo dài tuổi entry | Dùng write TTL, invalidation/version |
| Cache hit sau khi user bị thu hồi quyền | Authorization chỉ trong thân method | Kiểm tra quyền ở đường gọi luôn chạy, invalidation |
| Tăng TTL giúp hit nhưng trả giá cũ | Không có eviction sau update | Đồng bộ `@CachePut`/`@CacheEvict` và transaction |
| Caffeine eviction không đúng "LRU" kỳ vọng | Provider có chính sách admission/eviction riêng | Test hành vi/budget, không đoán key cụ thể |
| Redis từ chối write dù có `maxmemory` | `noeviction` hoặc không có key phù hợp `volatile-*` | Xem Redis policy/TTL và cấu trúc workload |
| Redis hết chỗ dù TTL ngắn | Sinh key quá nhanh, value lớn hoặc fragmentation | Đo entry count/size, giảm cardinality và memory |
| Dữ liệu cũ gây lỗi sau deploy | Cache value serializer/schema khác phiên bản | Version key namespace, TTL, kế hoạch migrate |
| Metric tags nổ cardinality | Gắn từng raw key vào metric | Dùng tag giới hạn, không dùng ID người dùng/query |

## 13. Bài tập tự kiểm tra

**Bài 1.** API tìm kiếm nhận timestamp tới mili giây rồi dùng toàn bộ timestamp làm cache key. Điều gì có thể xảy ra?  
**Đáp án:** cardinality tăng rất nhanh và hit rate gần 0. Nên loại các yếu tố không ảnh hưởng kết quả, hoặc giảm granularity có cân nhắc đúng ngữ nghĩa; nếu dữ liệu thật sự khác theo timestamp, có thể không phù hợp cache mọi yêu cầu.

**Bài 2.** Caffeine cấu hình `maximumSize=5000` có chắc cache dùng tối đa 5.000 KiB RAM không?  
**Đáp án:** không. Đây là ngưỡng số entry, không phải byte. Kích thước key/value và metadata vẫn quyết định lượng heap.

**Bài 3.** Một entry được đọc mỗi giây, cache có `expireAfterAccess=10m`. Nó có thể sống nhiều ngày không?  
**Đáp án:** có thể, nếu truy cập thường xuyên và không bị capacity eviction/invalidation. Đây không phải TTL tuyệt đối theo write.

**Bài 4.** Redis cache có `time-to-live=5m` nhưng server không đặt `maxmemory`. Có bảo đảm dùng ít RAM không?  
**Đáp án:** không. TTL giúp entry tự hết hạn nhưng tốc độ sinh key/value có thể vượt dung lượng trong cửa sổ TTL; cần ngân sách bộ nhớ ở server và theo dõi.

**Bài 5.** Giá P1 đổi từ 100 lên 120 sau khi đã cache. Nên chỉ giảm TTL hay còn phải làm gì?  
**Đáp án:** nếu yêu cầu đọc ngay đúng giá mới, cần put/evict/invalidation theo update và transaction. TTL đơn thuần chỉ giới hạn tuổi dữ liệu trong điều kiện nhất định.

**Bài 6.** Mỗi pod có Caffeine `maximumSize=10k`; có 8 pod. `maximumSize` có nghĩa 10k entry toàn cụm không?  
**Đáp án:** không. Giới hạn áp dụng **mỗi cache instance**; nhiều pod có các ngân sách và keyspace local độc lập.

**Bài 7.** Có nên cache kết quả cả triệu order trong một entry nếu chỉ 10 key?  
**Đáp án:** vẫn có thể quá lớn. Cần xét kích thước value/heap, giới hạn dữ liệu, DTO và phân trang; ít key không đồng nghĩa rẻ.

**Bài 8.** Vì sao `@Cacheable` không đủ để đặt TTL?  
**Đáp án:** annotation mô tả operation, còn TTL/capacity/eviction được provider và `CacheManager` cấu hình. Các backend có tính năng và defaults khác nhau.

**Bài 9.** Redis `maxmemory-policy=volatile-ttl` nhưng phần lớn key không có expiration. Rủi ro là gì?  
**Đáp án:** những key không TTL không phải ứng viên cho nhóm chính sách `volatile-*`. Khi không đủ key phù hợp để evict, việc ghi có thể thất bại.

**Bài 10.** Vì sao đo hit rate một mình chưa đủ?  
**Đáp án:** cache vẫn có thể quá lớn, trả stale, tăng GC, tạo eviction storm hoặc làm Redis quá tải. Cần cùng đo size, load time, latency, memory, key growth và độ mới.

## 14. Checklist triển khai an toàn

Trước khi đưa một cache vào production, hãy xác nhận:

- [ ] Tên cache có phạm vi hữu hạn, có người phụ trách và mục tiêu sử dụng rõ.
- [ ] Key phản ánh đúng tenant/user/projection nếu kết quả thay đổi theo scope; không chứa dữ liệu nhạy cảm không cần thiết.
- [ ] Có ước lượng số **key khác nhau**, không chỉ số request.
- [ ] Kích thước entry điển hình và lớn nhất đã được đo hoặc giới hạn.
- [ ] Provider thực sự hỗ trợ capacity limit/TTL như mong đợi; không dựa vào defaults ngầm.
- [ ] `maximumSize`/`maximumWeight` hoặc giới hạn Redis được tính theo phạm vi đúng (cache instance hay Redis node).
- [ ] TTL/TTI phù hợp với SLA độ mới; key nóng không vô tình giữ stale vô hạn.
- [ ] Những thao tác cập nhật/xóa nguồn có chiến lược `@CachePut`, `@CacheEvict` hoặc invalidation rõ ràng.
- [ ] Cache miss đột ngột và nhiều request cùng key không làm downstream quá tải.
- [ ] Metrics/alerts theo size, hit/miss, eviction, load time, GC hoặc Redis memory đã có.
- [ ] Có test expiration, capacity, nhiều instance, rollback và thay đổi dữ liệu.
- [ ] Có kế hoạch dọn dữ liệu cũ sau khi đổi key/value serializer và deploy nhiều phiên bản.

## Tài liệu chính thức

- Spring Framework – **Cache Abstraction** và declarative caching: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework – **Cache Annotations** và giới hạn của `@Cacheable`: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot – **Caching**, Caffeine specs và Redis properties: https://docs.spring.io/spring-boot/reference/io/caching.html
- Spring Data Redis – **Redis Cache**, TTL, TTI, prefix, batch strategy: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
- Caffeine – **Eviction** (`maximumSize`, `maximumWeight`, expiration): https://github.com/ben-manes/caffeine/wiki/Eviction
- Redis – **Key eviction** (`maxmemory`, eviction policies): https://redis.io/docs/latest/develop/reference/eviction/

**Kết luận:** kiểm soát cache đòi hỏi đồng thời ba điều: **giới hạn số và kích thước dữ liệu**, **đặt vòng đời/độ mới phù hợp**, và **chủ động invalidation khi nguồn thay đổi**. Spring Cache cung cấp abstraction; provider thực thi chính sách bộ nhớ. Không chỉ tăng TTL để tối ưu hit rate, và không chỉ thêm `maximumSize` để tự tin dữ liệu luôn đúng. Hãy đo chi phí, key cardinality, độ mới và hành vi trên môi trường triển khai thực tế.