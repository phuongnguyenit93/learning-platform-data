# CompositeCacheManager và thứ tự tìm kiếm trong Spring Framework Cache

## 1. Bài toán: một ứng dụng cần nhiều CacheManager

Một ứng dụng Spring có thể dùng các vùng cache khác nhau cho dữ liệu catalog, báo cáo và dữ liệu dùng chung. Ví dụ, vùng `catalog` có thể nằm trên một provider; vùng `reports` có thể nằm trên provider khác. Nếu mọi annotation đều sử dụng cùng một `CacheManager`, cách phân bổ cache cần được xác định rõ.

`CompositeCacheManager` trong package `org.springframework.cache.support` giải quyết bài toán **tìm đối tượng Cache theo tên từ một danh sách CacheManager**. Nó duyệt danh sách delegate theo đúng thứ tự đã cấu hình và chọn **Cache đầu tiên khác null**.

Ví dụ ý tưởng:

```text
CacheInterceptor / CacheManager.getCache("reports")
                      |
                      v
          CompositeCacheManager
                      |
            [1] catalogManager
                   getCache("reports") = null
                      |
            [2] reportManager
                   getCache("reports") = Cache("reports")
                      |
                      v
              Chọn Cache("reports")
```

Điều kiện cốt lõi: **một manager không quản lý tên cache được hỏi cần trả `null`**, để composite tiếp tục sang delegate sau. Khi manager đầu trả một `Cache` khác null, việc tìm **dừng ngay**; composite không hỏi tiếp các manager còn lại.

Bài này đi vào ngữ nghĩa chọn vùng, thứ tự ưu tiên, static/dynamic cache names, fallback `NoOpCache`, ứng dụng với annotation và kiểm thử những sai lầm thường gặp.

## 2. Vai trò của CompositeCacheManager

Các thành phần cần phân biệt:

| Thành phần | Trách nhiệm |
| --- | --- |
| `CacheManager` | Tra một vùng cache bằng `getCache(String name)`; liệt kê các vùng đã biết qua `getCacheNames()` |
| `Cache` | Là vùng chứa các entry `key → value`; hỗ trợ `get`, `put`, `evict`, `clear`... |
| `CompositeCacheManager` | Duyệt nhiều `CacheManager` theo thứ tự cho đến khi một manager trả về `Cache` khác null |
| `CacheResolver` | Chọn tập Cache cho một cache operation; resolver mặc định thường dựa vào tên cache và một manager |
| `@Cacheable`, `@CachePut`, `@CacheEvict` | Chỉ định operation đọc, ghi hoặc xóa; sử dụng Cache được resolve ở bước trên |

Phương thức tìm cache có thể mô tả bằng thuật toán:

```java
// Pseudocode diễn giải hợp đồng, không phải mã nguồn Spring nguyên văn.
Cache getCache(String name) {
    for (CacheManager manager : delegatesInOrder) {
        Cache cache = manager.getCache(name);
        if (cache != null) {
            return cache;
        }
    }
    return null;
}
```

**Thứ tự lựa chọn là theo tên vùng cache, không theo việc entry key có tồn tại hay không.** Composite không lấy từng key từ manager 1, rồi khi không thấy key mới thử manager 2. Nó chọn một vùng `Cache` trước; việc hit/miss cho từng key được thực hiện **bên trong vùng đó**.

Hệ quả:

- Manager 1 có cache `shared` nhưng `shared/K` chưa có entry: composite vẫn chọn cache `shared` của manager 1.
- Manager 2 cũng có cache `shared` và đã lưu `shared/K`: entry đó **không được thử** qua cơ chế composite.
- `put` hoặc `evict` thông qua cache vừa được chọn không tự sao chép thao tác sang mọi delegate.

Vì thế `CompositeCacheManager` **không phải hệ thống cache hai tầng L1/L2**, không phải write-through giữa hai provider và không tự đồng bộ dữ liệu. Nếu cần L1/L2 với nạp từ L2 về L1, phải triển khai Cache hoặc provider đa tầng có hợp đồng read-through, invalidation và consistency riêng.

## 3. Thứ tự tìm kiếm khi tên cache trùng hoặc khác nhau

Giả sử ba manager được cấu hình:

| Thứ tự | Manager | Các vùng nó quản lý |
| --- | --- | --- |
| 1 | `catalogManager` | `catalog`, `shared` |
| 2 | `reportManager` | `reports`, `shared` |
| 3 | `otherManager` | `audit` |

Khi gọi `composite.getCache(name)`:

| Tên yêu cầu | Manager 1 | Manager 2 | Manager 3 | Kết quả |
| --- | --- | --- | --- | --- |
| `catalog` | Có | Không hỏi | Không hỏi | Cache từ manager 1 |
| `reports` | Trả null | Có | Không hỏi | Cache từ manager 2 |
| `audit` | Trả null | Trả null | Có | Cache từ manager 3 |
| `shared` | Có | Không hỏi | Không hỏi | Cache từ manager 1 |
| `missing` | Trả null | Trả null | Trả null | Composite trả null nếu không bật fallback |

**Nếu hai manager cùng quản lý `shared`, manager xếp trước có ưu tiên tuyệt đối đối với tên đó.** Thứ tự thay đổi có thể khiến dữ liệu được đọc từ provider khác, ngay cả khi code sử dụng annotation vẫn không đổi.

`getCacheNames()` trên composite tổng hợp các tên cache đã biết từ các delegate. Danh sách tên không chứng minh cache nào xử lý một request cụ thể nếu có tên trùng; phải kiểm tra `getCache(name)` và thứ tự cấu hình. Khi có cache được tạo động, các tên trả về cũng có thể thay đổi theo thời gian.

## 4. Vì sao cấu hình manager dạng “dynamic” dễ làm sai thứ tự?

Nhiều CacheManager có chế độ **tự tạo vùng** khi được hỏi một tên chưa tồn tại. Ví dụ `ConcurrentMapCacheManager` của Spring:

```java
// Dynamic: tạo mới cache cho bất kỳ tên chưa được khai báo nào.
CacheManager dynamic = new ConcurrentMapCacheManager();

// Static: chỉ quản lý catalog và shared.
CacheManager staticCatalog =
        new ConcurrentMapCacheManager("catalog", "shared");
```

Cấu hình với constructor nhận danh sách tên cố định đặt `ConcurrentMapCacheManager` vào **static mode**. Trong static mode, `getCache("reports")` sẽ trả null nếu `reports` không nằm trong danh sách khai báo, cho phép composite thử manager tiếp theo.

Nếu dùng dynamic manager ở vị trí đầu:

```java
var first = new ConcurrentMapCacheManager(); // dynamic
var second = new ConcurrentMapCacheManager("reports"); // static
var composite = new CompositeCacheManager(first, second);

// first.getCache("reports") tự tạo Cache("reports").
// Vì khác null nên composite không bao giờ tới second.
Cache selected = composite.getCache("reports");
```

Đoạn trên minh họa cách resolution hoạt động. Dù manager thứ hai có `reports` được cấu hình sẵn, lời gọi vẫn chọn vùng mới tạo ở manager đầu. Code có thể chạy không báo lỗi nhưng dữ liệu lại đi nhầm backend.

Để tránh:

1. Liệt kê rõ cache names do manager đầu sở hữu và cấu hình chế độ chỉ chấp nhận tên đã biết khi provider hỗ trợ.
2. Đặt các manager có phạm vi tên xác định ở trước; nếu thật sự cần một manager hỗ trợ mọi tên, đặt nó cuối danh sách một cách có chủ đích.
3. Kiểm tra cơ chế `getCache(name)` của **từng provider**, không chỉ kiểm tra `getCacheNames()`; một danh sách tên trống không đồng nghĩa với việc `getCache` luôn trả null.
4. Thêm test cho cả tên có trong danh sách, tên trùng và tên không tồn tại để phát hiện việc manager đầu “nuốt” mọi request.

Trong hệ thống dùng Caffeine, Redis, JCache hoặc adapter tùy chỉnh, khả năng tạo cache động và cách xử lý tên lạ phụ thuộc vào từng implementation/cấu hình. Đừng suy diễn rằng mỗi provider đều có constructor hoặc thuộc tính giống `ConcurrentMapCacheManager`.

## 5. Cấu hình CompositeCacheManager trong Java Config

Khi một ứng dụng có hai backend/nhóm cache, có thể tạo composite bằng constructor nhận các delegate theo **thứ tự ưu tiên**:

```java
@Bean
CacheManager cacheManager() {
    var catalog = new ConcurrentMapCacheManager("catalog", "shared");
    var reports = new ConcurrentMapCacheManager("reports", "shared");

    var composite = new CompositeCacheManager(catalog, reports);
    composite.setFallbackToNoOpCache(false);
    return composite;
}
```

Đây là **đoạn cấu hình minh họa**; cần import `CacheManager`, `ConcurrentMapCacheManager`, `CompositeCacheManager`, `@Bean`, và đặt method trong một lớp cấu hình Spring.

Cấu hình này bảo đảm:

- Hỏi `catalog` → chọn manager `catalog` đầu tiên.
- Hỏi `reports` → manager đầu trả null, manager thứ hai được thử.
- Hỏi `shared` → chọn manager đầu vì cả hai cùng quản lý tên đó.
- Hỏi `unknown` → trả null vì cả hai ở static mode và không bật fallback.

**Có thể thay đổi thứ tự** bằng cách đổi vị trí tham số constructor hoặc sử dụng `setCacheManagers(Collection<CacheManager>)`. Nên xem thứ tự đó như một phần của cấu hình có ảnh hưởng trực tiếp tới dữ liệu.

`CompositeCacheManager` cũng hỗ trợ `afterPropertiesSet()` theo `InitializingBean` để hoàn tất cấu hình fallback. Khi nó là một Spring bean, container gọi lifecycle callback. Nếu tự khởi tạo bằng `new` ngoài Spring và muốn dùng tính năng `NoOp` fallback, cần xét việc gọi `afterPropertiesSet()` phù hợp.

### 5.1. Tránh nhiều bean CacheManager gây không rõ lựa chọn mặc định

Nếu đăng ký nhiều bean Spring cùng kiểu `CacheManager` rồi chỉ dùng `@Cacheable` mà không cấu hình manager mặc định, có thể xuất hiện tình huống không xác định bean nào cần dùng. Ví dụ hoàn chỉnh ở phần tiếp theo đăng ký **một bean CacheManager là composite**, các delegate nằm trong một object cấu hình riêng.

Trong ứng dụng thật còn có thể chọn bean mặc định bằng `CachingConfigurer`, `@Primary`, hoặc chỉ định `cacheManager = "..."` ở method/`@CacheConfig` khi phù hợp. Nên thống nhất đường resolution để tránh annotation đi thẳng tới manager khác thay vì qua composite.

## 6. Ví dụ Java 17 chạy được: thấy rõ tìm kiếm theo thứ tự

Ví dụ dưới đây dùng Spring Framework 6.2.x và `ConcurrentMapCacheManager` ở **static mode**. Có hai delegate:

- `first` quản lý `catalog` và `shared`.
- `second` quản lý `reports` và `shared`.

Ứng dụng dùng một `CompositeCacheManager`, đồng thời có một bean `Delegates` giữ tham chiếu tới hai manager để minh họa vùng trùng tên mà không đăng ký thêm nhiều `CacheManager` bean cạnh tranh với composite.

**Cấu trúc thư mục:**

```text
composite-cache-demo/
├── pom.xml
└── src/main/java/CompositeCacheDemo.java
```

**Nội dung `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>composite-cache-demo</artifactId>
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

**Nội dung `src/main/java/CompositeCacheDemo.java`:**

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.support.CompositeCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CompositeCacheDemo {

    // Hai delegate là dữ liệu cấu hình, không phải các bean CacheManager.
    public record Delegates(
            ConcurrentMapCacheManager first,
            ConcurrentMapCacheManager second) {}

    @Bean
    Delegates delegates() {
        return new Delegates(
                new ConcurrentMapCacheManager("catalog", "shared"),
                new ConcurrentMapCacheManager("reports", "shared"));
    }

    @Bean
    CacheManager cacheManager(Delegates delegates) {
        var composite = new CompositeCacheManager(
                delegates.first(), delegates.second());
        composite.setFallbackToNoOpCache(false);
        return composite;
    }

    @Bean
    DataService dataService() {
        return new DataService();
    }

    public static class DataService {
        private final AtomicInteger catalogLoads = new AtomicInteger();
        private final AtomicInteger reportLoads = new AtomicInteger();

        @Cacheable(cacheNames = "catalog", key = "#p0")
        public String catalog(String sku) {
            catalogLoads.incrementAndGet();
            return "Product-" + sku;
        }

        @Cacheable(cacheNames = "reports", key = "#p0")
        public String report(String reportId) {
            reportLoads.incrementAndGet();
            return "Report-" + reportId;
        }

        public int catalogLoads() {
            return catalogLoads.get();
        }

        public int reportLoads() {
            return reportLoads.get();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                CompositeCacheDemo.class)) {

            CacheManager manager = context.getBean(CacheManager.class);
            Delegates delegates = context.getBean(Delegates.class);
            DataService service = context.getBean(DataService.class);

            System.out.println("catalog exists: "
                    + (manager.getCache("catalog") != null));
            System.out.println("reports exists: "
                    + (manager.getCache("reports") != null));
            System.out.println("unknown exists: "
                    + (manager.getCache("unknown") != null));

            Cache firstShared = delegates.first().getCache("shared");
            Cache secondShared = delegates.second().getCache("shared");
            if (firstShared == null || secondShared == null) {
                throw new IllegalStateException("Missing shared cache");
            }

            secondShared.put("K", "SECOND");
            Cache selected = manager.getCache("shared");
            if (selected == null) {
                throw new IllegalStateException("Composite missing shared");
            }
            System.out.println("shared with empty first: "
                    + (selected.get("K") == null ? "MISS" : "HIT"));

            firstShared.put("K", "FIRST");
            System.out.println("shared chosen: "
                    + selected.get("K", String.class));
            System.out.println("second still: "
                    + secondShared.get("K", String.class));

            System.out.println("catalog 1: " + service.catalog("P1"));
            System.out.println("catalog 2: " + service.catalog("P1"));
            System.out.println("catalog loads: " + service.catalogLoads());

            System.out.println("reports 1: " + service.report("R1"));
            System.out.println("reports 2: " + service.report("R1"));
            System.out.println("report loads: " + service.reportLoads());
        }
    }
}
```

**Chạy từ thư mục có `pom.xml`** (yêu cầu JDK 17+ và Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=CompositeCacheDemo
```

**Các dòng do `main` in ra** (không tính log Maven/Spring phụ thuộc môi trường):

```text
catalog exists: true
reports exists: true
unknown exists: false
shared with empty first: MISS
shared chosen: FIRST
second still: SECOND
catalog 1: Product-P1
catalog 2: Product-P1
catalog loads: 1
reports 1: Report-R1
reports 2: Report-R1
report loads: 1
```

Diễn giải kết quả:

1. Vì `catalog` chỉ có ở delegate đầu, `getCache("catalog")` khác null.
2. `reports` không có ở delegate đầu nên được tìm ở delegate thứ hai; `getCache("reports")` khác null.
3. Cả hai delegate đều không quản lý `unknown`, vì thế composite trả null.
4. `second/shared/K` đã có value `"SECOND"`, nhưng `first/shared/K` chưa có. Composite vẫn chọn vùng `shared` của delegate đầu, nên đọc key `K` báo `MISS`: nó **không fallback khi key miss**.
5. Ghi `"FIRST"` vào cache `shared` của delegate đầu làm composite đọc ra `"FIRST"`, còn delegate thứ hai vẫn lưu `"SECOND"`. Đây là bằng chứng hai vùng trùng tên không được hợp nhất.
6. `service.catalog("P1")` và `service.report("R1")` mỗi phương thức chỉ tăng bộ đếm một lần qua hai lượt gọi, thể hiện `@Cacheable` đã sử dụng cache được composite resolve.

Demo không dùng database hay cache phân tán và không tuyên bố bảo đảm TTL, transaction hoặc đồng bộ nhiều instance. Các lời gọi cache annotation từ `main` đi qua Spring bean, nên không bị lỗi self-invocation.

## 7. Fallback NoOpCacheManager: khi không manager nào biết tên

`CompositeCacheManager` có thuộc tính `fallbackToNoOpCache` (mặc định tắt). Khi bật, nó bổ sung `NoOpCacheManager` vào **cuối danh sách delegate** trong giai đoạn khởi tạo. Manager này trả một đối tượng `Cache` cho tên được hỏi nhưng không lưu dữ liệu.

Cấu hình:

```java
@Bean
CacheManager cacheManager() {
    var real = new ConcurrentMapCacheManager("catalog");
    var composite = new CompositeCacheManager(real);
    composite.setFallbackToNoOpCache(true);
    return composite;
}
```

Đây là đoạn cấu hình thay thế để minh họa, không chép thêm vào lớp demo ở mục 6 vì sẽ tạo hai method bean `cacheManager()`.

Với cấu hình này:

- `composite.getCache("catalog")` lấy cache thật ở delegate đầu.
- `composite.getCache("unknown")` cũng khác null, nhưng đó là **NoOpCache**.
- `@Cacheable(cacheNames="unknown")` vẫn chạy method mỗi lần vì NoOp cache luôn không có entry lưu bền qua các lượt gọi.
- Không có exception do tên cache không tìm thấy, nên typo trong `cacheNames` có thể bị che giấu và ứng dụng âm thầm không hưởng lợi từ cache.

Bật fallback phù hợp khi muốn một số vùng có thể cố ý không lưu trong môi trường cụ thể; nếu muốn phát hiện cấu hình cache sai sớm, nên **tắt fallback** và kiểm thử tên vùng. Đừng dùng fallback này như bản sao dự phòng của Redis/Caffeine: `NoOpCache` bỏ qua lưu trữ, không phải cache thật.

### Khi nào fallback được kích hoạt?

`CompositeCacheManager` triển khai `InitializingBean`. Khi là Spring bean, `afterPropertiesSet()` được gọi sau khi cấu hình và thêm `NoOpCacheManager` ở cuối nếu `fallbackToNoOpCache=true`. Nếu tự tạo composite ngoài Spring mà không gọi lifecycle callback, cấu hình fallback có thể chưa được áp dụng. Không đổi fallback liên tục sau khi bean đã khởi tạo rồi suy đoán danh sách delegate được xây lại theo thời gian.

## 8. Chọn manager trong Spring Cache annotation

Một operation `@Cacheable(cacheNames="reports", key="#p0")` sẽ yêu cầu cache có tên `reports` từ manager được chọn (thường thông qua một `CacheResolver`). **Composite chỉ có tác dụng nếu operation đang dùng chính composite**.

Cách chọn manager có thể được cấu hình ở các cấp:

| Cấp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Bean mặc định của caching infrastructure | Một `CacheManager` được cấu hình rõ | Operation không chỉ định manager riêng dùng mặc định |
| Lớp service | `@CacheConfig(cacheManager = "compositeCacheManager")` | Các operation trong lớp kế thừa tên manager |
| Method | `@Cacheable(cacheManager = "compositeCacheManager")` | Operation chỉ định manager của chính nó |
| Resolver | `cacheResolver = "customCacheResolver"` | Cơ chế chọn Cache do resolver thực thi, có thể không đi qua composite |

Nếu ứng dụng có nhiều `CacheManager` bean, cần chọn mặc định rõ ràng theo cấu hình Spring hoặc đặt tên chính xác ở annotation. Nếu một method chỉ định manager khác, nó có thể hoàn toàn bỏ qua composite và dùng thẳng cache của backend đó.

`@CacheConfig(cacheNames = "reports")` hoặc `@Cacheable(cacheNames="reports")` chỉ xác định **tên** vùng cần resolve. Tên vùng không tự mô tả provider, địa điểm lưu hay thứ tự delegate; những điều đó nằm trong cấu hình manager.

Không kết hợp `cacheManager` và `cacheResolver` cùng lúc trên cùng cache operation. Với resolver tùy biến, phải kiểm tra resolver dùng danh sách cache nào, có tôn trọng thứ tự dự kiến hay không và khi không tìm được cache thì xử lý thế nào.

## 9. Khác biệt giữa chọn vùng và cache miss

Đây là một nhầm lẫn phổ biến khi muốn xây dựng “L1 + L2”:

```text
Hợp đồng của CompositeCacheManager:
  Tên cache "shared"
       -> manager 1 có region "shared" ?
          Có -> chọn ngay region đó
          Không -> hỏi manager 2

Hợp đồng cache 2 tầng mà nhiều ứng dụng mong muốn:
  Đọc key K trong L1
       -> L1 miss: đọc key K trong L2
       -> L2 hit: có thể ghi ngược L1
       -> L2 miss: gọi nguồn
```

Hai flow xử lý các **đơn vị khác nhau**:

- Composite giải quyết **tên vùng** một lần cho một operation (và có thể được gọi lại ở các request khác).
- Cache đa tầng giải quyết **từng key**, yêu cầu hợp đồng nhất quán giữa các tầng, chiến lược copy/serialization/TTL và invalidation.

Nếu đặt `ConcurrentMapCacheManager` local đầu tiên, Redis manager sau nhưng cả hai đều trả cache cho cùng tên `products`, composite sẽ luôn dùng local, kể cả local miss. Dữ liệu Redis không được dùng làm fallback theo key. Việc invalidate local cũng không tự lan tới Redis hay các node khác.

Để làm cache hai tầng thực sự, chọn thư viện/provider triển khai multi-tier `Cache` rõ ràng hoặc tự xây một implementation `Cache` phối hợp L1/L2 và kiểm thử race condition, write-through, stale data, TTL và invalidation. Chỉ hoán đổi thứ tự `CompositeCacheManager` không đủ.

## 10. Lỗi phổ biến và cách kiểm chứng

1. **Manager đầu tạo mọi tên cache.** Dynamic manager trả `Cache` khác null cho tên bất kỳ, làm mọi manager đứng sau gần như không bao giờ được hỏi. Kiểm tra static mode hoặc chuyển manager catch-all xuống cuối.
2. **Hiểu sai thứ tự ưu tiên.** Khi hai manager cùng có `shared`, manager đầu thắng; không có round-robin hay load balancing.
3. **Coi miss theo key là tín hiệu thử manager tiếp theo.** Composite không thực hiện key-level lookup, chỉ name-level lookup.
4. **Bật `fallbackToNoOpCache` rồi tưởng có cache dự phòng thật.** Unknown name được NoOp xử lý và không lưu; typo tên vùng có thể khó phát hiện.
5. **Đăng ký nhiều CacheManager bean nhưng không chọn manager mặc định.** Annotation có thể dùng nhầm bean hoặc cấu hình không rõ; xác định default manager một cách tường minh.
6. **Coi cùng tên cache ở các delegate là cùng dữ liệu.** Vùng ở các manager có thể độc lập hoàn toàn; ghi/xóa qua composite chỉ tác động đến vùng được chọn.
7. **Tin rằng `getCacheNames()` cho biết thứ tự hit của entry.** Danh sách tên chỉ nói cache names đã biết, không cho biết key nào tồn tại hay manager nào sẽ được chọn khi trùng tên.
8. **Không quản lý thay đổi cấu hình giữa các môi trường.** Provider A tạo cache động trong môi trường dev, còn production cố định tên; hành vi chọn vùng có thể khác.
9. **Giả định transaction hoặc distributed invalidation tự có.** Composite không tham gia atomic commit chung với database và không đồng bộ cache giữa nhiều JVM.
10. **Viết test chỉ cho tên vùng duy nhất.** Cần test cả region chung, tên không biết và một key chỉ tồn tại ở manager đứng sau.

### Checklist trước khi triển khai

| Tình huống cần test | Hành vi mong đợi |
| --- | --- |
| Manager 1 có cache `catalog` | Composite trả đúng Cache từ manager 1 |
| Manager 1 không có `reports`, manager 2 có | Composite trả Cache từ manager 2 |
| Cả hai có `shared` | Composite chọn manager 1 |
| Manager 1 có `shared` nhưng key `K` miss; manager 2 có `K` | Không thử manager 2; trả miss từ vùng đã chọn |
| Không manager nào có `unknown`, fallback tắt | `getCache("unknown") == null` |
| Không manager nào có `unknown`, fallback bật và bean đã init | Lấy `NoOpCache`, không cache kết quả |
| Manager 1 dynamic | Manager 1 có thể nhận mọi cache name, chặn delegation |
| Annotation trên service dùng manager khác composite | Các quy tắc tìm kiếm của composite không được áp dụng |

Để quan sát trong vận hành, ghi nhận tên region đã chọn và backend xử lý, tỉ lệ hit/miss **trong từng cache thật**, chi phí truy cập nguồn và lỗi từ backend. Cần kiểm thử thêm khi thay đổi danh sách cache names hoặc thứ tự delegate.

## 11. Quy tắc thiết kế để không chọn nhầm backend

Một cấu hình đáng tin có thể được diễn tả bằng bốn câu hỏi:

1. **Manager nào sở hữu từng tên region?** Ghi rõ bảng ánh xạ tên vùng → provider/manager.
2. **Khi gặp tên không biết, manager đó trả null hay tự tạo cache?** Đây là điều kiện kỹ thuật để composite đi tiếp.
3. **Có tên nào trùng giữa các manager?** Nếu có, manager đứng trước được chọn; phải ghi nhận đó là quyết định có chủ đích.
4. **Khi không ai quản lý tên, hệ thống cần báo lỗi hay tạm bỏ cache?** Quyết định này điều khiển `fallbackToNoOpCache`.

Chỉ dùng `CompositeCacheManager` để **điều phối tìm vùng cache theo tên**. Khi cần tái sử dụng dữ liệu theo key giữa nhiều tầng, yêu cầu một cache implementation đa tầng và hợp đồng nhất quán riêng.

## Tài liệu tham khảo chính thức

- Spring Framework — `CompositeCacheManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/cache/support/CompositeCacheManager.html
- Spring Framework — `ConcurrentMapCacheManager` Javadoc (static/dynamic): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Cache Annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — `CacheManager` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/CacheManager.html
