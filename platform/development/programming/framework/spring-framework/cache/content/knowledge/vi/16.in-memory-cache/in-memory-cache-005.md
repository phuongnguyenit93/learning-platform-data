# SimpleCacheManager với ConcurrentMapCache được khai báo sẵn trong Spring Framework

## 1. Bài toán và mục tiêu

Trong một ứng dụng Spring, bạn muốn dùng cache **trong bộ nhớ của chính JVM**, nhưng chỉ muốn quản lý một số vùng cache xác định từ lúc khởi động, chẳng hạn `catalog` để lưu sản phẩm và `reports` để lưu báo cáo. Những vùng khác không nên vô tình được tạo ra chỉ vì code gõ nhầm tên.

Bộ đôi phù hợp cho nhu cầu đơn giản này là:

- `SimpleCacheManager`: một implementation của `CacheManager` quản lý **tập các đối tượng `Cache` đã được cung cấp sẵn**.
- `ConcurrentMapCache`: một implementation của `Cache` dùng cấu trúc `ConcurrentMap`, mặc định dựa trên `ConcurrentHashMap`, để lưu entry trong bộ nhớ tiến trình.

Điểm quan trọng của bài: **“khai báo sẵn cache” không có nghĩa đã nạp sẵn dữ liệu vào cache**. Ta tạo các **vùng cache** có tên cố định khi khởi tạo, còn các **entry theo key** được thêm khi `@Cacheable` miss, khi gọi `Cache.put`, hoặc bằng một cơ chế nạp dữ liệu chủ động do ứng dụng triển khai.

Sau bài học, bạn sẽ có thể:

1. Tạo bean `SimpleCacheManager` và cung cấp các `ConcurrentMapCache` bằng `setCaches(...)`.
2. Hiểu vòng đời khởi tạo `afterPropertiesSet/initializeCaches` và lý do không được quên khi dùng manager ngoài Spring container.
3. Dùng `@EnableCaching`, `@Cacheable` và `@CacheEvict` với các cache tên cố định.
4. Phân biệt cache **chưa được khai báo** với một **key chưa có entry** trong vùng đã tồn tại.
5. Hiểu sự khác nhau với `ConcurrentMapCacheManager`, chính sách null, phạm vi một JVM, đồng thời và các hạn chế về TTL/giới hạn kích thước.
6. Tự chạy một ví dụ Java 17+ không cần Redis, database hay web server.

## 2. Thành phần và quan hệ giữa các lớp

```text
               Spring ApplicationContext
                         |
                @EnableCaching / AOP
                         |
               CacheInterceptor
                         |
                   CacheManager
                 (SimpleCacheManager)
                         |
             +-----------+------------+
             |                        |
      ConcurrentMapCache       ConcurrentMapCache
        name="catalog"          name="reports"
             |                        |
       ConcurrentMap              ConcurrentMap
         key -> value              key -> value
```

Một số khái niệm cần phân biệt:

| Thành phần | Vai trò | Không có nghĩa là |
| --- | --- | --- |
| `Cache` | API truy cập một vùng cache: `get`, `put`, `evict`, `clear` | Tự định nghĩa toàn bộ cấu hình Spring |
| `CacheManager` | Tìm vùng cache theo tên qua `getCache(name)`, liệt kê tên qua `getCacheNames()` | Tự động lưu mọi kết quả method |
| `SimpleCacheManager` | Quản lý tập instance `Cache` được cấp sẵn qua `setCaches` | Tự sinh region mới cho mọi tên lạ |
| `ConcurrentMapCache` | Cache nội bộ dựa trên concurrent map | Redis, cache nhiều node hoặc database |
| `@EnableCaching` | Bật hạ tầng xử lý annotation cache trong context phù hợp | Tạo sẵn các cache hoặc nạp dữ liệu |
| `@Cacheable` | Đọc cache, bỏ qua method khi hit; gọi method và lưu khi miss | Đảm bảo cơ chế cache hoạt động nếu lời gọi không đi qua Spring proxy |

Khi phương thức `@Cacheable(cacheNames="catalog")` được gọi qua Spring proxy, cache interceptor hỏi `CacheManager` tìm vùng tên `catalog`. `SimpleCacheManager` trả về đúng instance `ConcurrentMapCache` đã đăng ký; sau đó logic cache đọc theo key. Nếu key vắng mặt, body thực thi và kết quả có thể được lưu vào vùng đó.

## 3. Cấu hình SimpleCacheManager với cache khai báo sẵn

Cấu hình Java tối thiểu trong một ứng dụng Spring:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        SimpleCacheManager manager = new SimpleCacheManager();
        manager.setCaches(List.of(
            new ConcurrentMapCache("catalog"),
            new ConcurrentMapCache("reports")
        ));
        return manager;
    }
}
```

Đây là **đoạn cấu hình minh họa**, cần các import của Spring và `java.util.List`. Phần 5 cung cấp **toàn bộ dự án chạy được**.

Ý nghĩa từng bước:

1. `new ConcurrentMapCache("catalog")` tạo một instance cache tên `catalog`, ban đầu chưa có entry nào.
2. `new ConcurrentMapCache("reports")` tạo vùng độc lập với tên `reports`.
3. `manager.setCaches(List.of(...))` cung cấp chính xác các cache instance để manager quản lý. Không phải `setCacheNames`; phương thức đang nhận **đối tượng cache**, không phải danh sách chuỗi tên.
4. Spring container tạo bean `CacheManager`, thực hiện các callback khởi tạo bean và đăng ký các vùng vào lookup của `SimpleCacheManager`.
5. `@EnableCaching` cho phép `@Cacheable`/`@CacheEvict` dùng manager này khi lời gọi đi qua proxy.

Cấu hình này không tạo một bean Spring riêng cho mỗi `ConcurrentMapCache`; chúng là những instance được cấp trực tiếp cho manager. Bạn cũng có thể khai báo các `Cache` thành bean riêng để injection/cấu hình lại, rồi truyền chúng cho `SimpleCacheManager`. Đừng vô tình đăng ký **hai manager** không rõ mặc định hoặc hai cache trùng tên.

### 3.1. Vòng đời khởi tạo là chi tiết bắt buộc

`SimpleCacheManager` kế thừa `AbstractCacheManager` và có `afterPropertiesSet()` thông qua giao diện `InitializingBean`. Khi là một bean Spring thông thường, **Spring tự gọi callback lifecycle** sau khi cấu hình xong thuộc tính; `afterPropertiesSet()` kích hoạt `initializeCaches()` để tạo ánh xạ tên → cache instance.

Vì vậy trong method `@Bean` bên trên, **không cần gọi `afterPropertiesSet()` bằng tay**.

Ngược lại, khi tự khởi tạo ngoài container Spring:

```java
SimpleCacheManager manager = new SimpleCacheManager();
manager.setCaches(List.of(new ConcurrentMapCache("catalog")));
manager.initializeCaches();  // Bắt buộc khởi tạo nếu tự quản lý manager.
Cache cache = manager.getCache("catalog");
```

Đây là **đoạn mã minh họa**, cần import `SimpleCacheManager`, `ConcurrentMapCache`, `Cache` và `List`. Khi dùng trực tiếp, gọi `initializeCaches()` **sau khi đã cung cấp cache instances**; nếu không, `getCache("catalog")` có thể chưa biết vùng cache đó. Không sửa danh sách cache tùy tiện sau khi ứng dụng đã nhận traffic; hãy coi registry là một cấu hình ổn định từ lúc khởi động.

### 3.2. Tên cache cố định: unknown khác cache miss

Ví dụ sau khi khởi tạo đúng:

```java
CacheManager manager = context.getBean(CacheManager.class);
Cache catalog = manager.getCache("catalog");  // Có instance.
Cache unknown = manager.getCache("unknown");  // null.
Cache.ValueWrapper absent = catalog.get("SKU-404"); // null nếu chưa có entry.
```

Đoạn này là mảnh mã minh họa, có biến `context` là Spring context hợp lệ.

- `manager.getCache("unknown") == null`: **không có vùng cache tên đó** trong `SimpleCacheManager`.
- `manager.getCache("catalog") != null` nhưng `catalog.get("SKU-404") == null`: **có vùng cache**, chỉ là **chưa có key đó**.
- Nếu cache hỗ trợ null, wrapper khác null nhưng `wrapper.get() == null` lại mang nghĩa **entry đã lưu giá trị null**.

Đây là ba tình huống khác nhau. Khi annotation tham chiếu cache name không tồn tại, cache resolver thông thường không thể chọn vùng hợp lệ và lời gọi annotated method có thể thất bại ở thời điểm thực thi. Đừng dựa vào việc manager tự sinh vùng mới — `SimpleCacheManager` không vận hành theo kiểu dynamic như một số cache manager khác.

## 4. Cấu trúc ví dụ Java 17+ chạy được

Ví dụ sẽ khai báo trước **hai vùng**: `catalog` và `reports`. Service đọc thông tin qua `@Cacheable` để quan sát cache hit; thao tác cập nhật chỉ evict một key catalog; thao tác làm mới báo cáo clear toàn bộ vùng reports. Hai vùng hoạt động độc lập.

Tạo dự án:

```text
simple-cache-manager-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/cache/SimpleCacheDemo.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'simple-cache-manager-demo'
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
}

application {
    mainClass = 'demo.cache.SimpleCacheDemo'
}
```

Chương trình không dùng `@SpringBootApplication` hay HTTP server. Nó dùng Spring Context trực tiếp và Spring Cache do starter cung cấp; BOM giúp các dependency Spring có phiên bản tương thích. Khi dùng dự án thực tế, hãy chọn phiên bản Spring Boot/Spring Framework được nhóm duy trì hỗ trợ và tương thích với JDK của hệ thống.

## 5. Toàn bộ mã nguồn Java

Tệp `src/main/java/demo/cache/SimpleCacheDemo.java`:

```java
package demo.cache;

import java.util.List;
import java.util.Objects;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.support.SimpleCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SimpleCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {

        @Bean
        CacheManager cacheManager() {
            SimpleCacheManager manager = new SimpleCacheManager();
            manager.setCaches(List.of(
                    new ConcurrentMapCache("catalog"),
                    new ConcurrentMapCache("reports")
            ));
            return manager;
            // Spring tự gọi callback khởi tạo manager khi quản lý bean.
        }

        @Bean
        CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final ConcurrentHashMap<String, Integer> versions =
                new ConcurrentHashMap<>();
        private final AtomicInteger catalogLoads = new AtomicInteger();
        private final AtomicInteger reportLoads = new AtomicInteger();
        private final AtomicInteger reportVersion = new AtomicInteger();

        @Cacheable(cacheNames = "catalog", key = "#p0")
        public String item(String sku) {
            int version = versions.getOrDefault(sku, 0);
            int n = catalogLoads.incrementAndGet();
            return sku + "-v" + version + "-load" + n;
        }

        @Cacheable(cacheNames = "reports", key = "#p0")
        public String report(String region) {
            int version = reportVersion.get();
            int n = reportLoads.incrementAndGet();
            return region + "-report-v" + version + "-load" + n;
        }

        @CacheEvict(cacheNames = "catalog", key = "#p0")
        public void changeItem(String sku) {
            versions.merge(sku, 1, Integer::sum);
        }

        @CacheEvict(cacheNames = "reports", allEntries = true)
        public void rebuildReports() {
            reportVersion.incrementAndGet();
        }

        public String counts() {
            return "catalog:" + catalogLoads.get()
                    + ",reports:" + reportLoads.get();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {

            CacheManager manager = context.getBean(CacheManager.class);
            CatalogService service = context.getBean(CatalogService.class);

            // Sắp xếp chỉ để output không phụ thuộc thứ tự tập tên.
            System.out.println("cacheNames="
                    + new TreeSet<>(manager.getCacheNames()));
            System.out.println("unknownCache="
                    + (manager.getCache("unknown") == null));

            System.out.println("catalog-first=" + service.item("SKU-1"));
            System.out.println("catalog-hit=" + service.item("SKU-1"));
            System.out.println("reports-first=" + service.report("VN"));
            System.out.println("reports-hit=" + service.report("VN"));

            service.changeItem("SKU-1");
            System.out.println("catalog-after-evict="
                    + service.item("SKU-1"));
            System.out.println("reports-still-hit="
                    + service.report("VN"));

            service.rebuildReports();
            System.out.println("reports-after-clear="
                    + service.report("VN"));
            System.out.println("catalog-still-hit="
                    + service.item("SKU-1"));

            System.out.println("loads=" + service.counts());

            Cache catalog = Objects.requireNonNull(
                    manager.getCache("catalog"));
            System.out.println("cacheType="
                    + catalog.getClass().getSimpleName());
            System.out.println("sameInstance="
                    + (catalog == manager.getCache("catalog")));
        }
    }
}
```

Chạy trong thư mục `simple-cache-manager-demo` bằng JDK 17+ và Gradle tương thích Java 17:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, có thể dùng `./gradlew run --quiet` hoặc trên Windows `gradlew.bat run --quiet`.

**Đầu ra dự kiến từ các dòng `System.out.println`**, không tính log build:

```text
cacheNames=[catalog, reports]
unknownCache=true
catalog-first=SKU-1-v0-load1
catalog-hit=SKU-1-v0-load1
reports-first=VN-report-v0-load1
reports-hit=VN-report-v0-load1
catalog-after-evict=SKU-1-v1-load2
reports-still-hit=VN-report-v0-load1
reports-after-clear=VN-report-v1-load2
catalog-still-hit=SKU-1-v1-load2
loads=catalog:2,reports:2
cacheType=ConcurrentMapCache
sameInstance=true
```

### 5.1. Giải thích từng giai đoạn

1. `cacheNames=[catalog, reports]`: `SimpleCacheManager` có đúng hai vùng được đăng ký. Ví dụ dùng `TreeSet` để thứ tự hiển thị ổn định.
2. `unknownCache=true`: tên `unknown` chưa được khai báo nên `getCache("unknown") == null`; manager không tự tạo thêm.
3. Lần đầu `item("SKU-1")`: vùng `catalog` tồn tại nhưng key chưa được lưu, nên method chạy, sinh `SKU-1-v0-load1`. Lần hai cùng key hit, không tăng bộ đếm.
4. Lần đầu `report("VN")` tương tự với vùng `reports`; lần hai hit.
5. `changeItem("SKU-1")` tăng version của sản phẩm và dùng `@CacheEvict(key="#p0")` để xóa **một entry** trong `catalog`. Đọc lại sản phẩm tạo `SKU-1-v1-load2`. Entry báo cáo vẫn là hit.
6. `rebuildReports()` tăng version báo cáo và dùng `allEntries=true` xóa **mọi entry trong vùng `reports` được chỉ định**, không đụng đến `catalog`.
7. Hai bộ đếm cùng bằng 2: có hai lần chạy body item và hai lần body report, bất chấp số lần gọi nhiều hơn. `cacheType` và `sameInstance` chứng minh manager trả về instance `ConcurrentMapCache` đã khởi tạo, không tạo cache mới ở mỗi lần tra cứu.

**Tại sao annotation hoạt động?** `@EnableCaching` được đặt trên configuration trong đúng Spring context. Service được tạo thành bean và các lời gọi trong `main` lấy qua `context.getBean(CatalogService.class)`, tức đi qua Spring proxy. Nếu gọi `new CatalogService().item(...)` hoặc một method trong service tự gọi `this.item(...)`, caching annotation có thể không chạy trong chế độ proxy mặc định.

Ví dụ là bộ nhớ một JVM, đơn luồng ở đoạn demonstration; không dùng để khẳng định mọi thứ atomic khi có nhiều request song song.

## 6. So sánh SimpleCacheManager và ConcurrentMapCacheManager

Tên hai class dễ gây nhầm:

| Khía cạnh | `SimpleCacheManager` + `ConcurrentMapCache` | `ConcurrentMapCacheManager` |
| --- | --- | --- |
| Khởi tạo | Tự tạo các instance `Cache` và truyền bằng `setCaches(...)` | Manager tự tạo `ConcurrentMapCache` theo tên |
| Cache names | Từ chính các `Cache.getName()` được đăng ký | Có thể dynamic mặc định; có thể cấu hình tên cố định |
| Tên chưa đăng ký | Trả null, không tự tạo cache mới | Ở chế độ dynamic có thể tạo cache khi gọi `getCache(name)` |
| Loại cache | Nhận collection các implementation `Cache` | Chuyên tạo `ConcurrentMapCache` |
| Cấu hình null | Đặt trên từng `ConcurrentMapCache` hoặc implementation cụ thể | `setAllowNullValues(...)` ở cấp manager |
| Cấu hình lưu tham chiếu/bản sao | Phụ thuộc cache instance bạn tự cung cấp | Có các tùy chọn của riêng manager |
| Tình huống phù hợp | Muốn kiểm soát chính xác cache instance và tên | Muốn cấu hình JDK concurrent-map cache thuận tiện |

Ví dụ ngắn khi chọn `ConcurrentMapCacheManager` thay cho `SimpleCacheManager`:

```java
// Chế độ tên cố định:
CacheManager manager = new ConcurrentMapCacheManager("catalog", "reports");

// Chế độ dynamic nếu dùng constructor không có tên:
CacheManager dynamic = new ConcurrentMapCacheManager();
```

Hai đoạn trên là **mảnh code minh họa**, cần imports. Chế độ dynamic có thể tạo cache region khi code yêu cầu một tên chưa từng thấy; đó có thể hữu ích trong thử nghiệm nhưng cũng có thể che dấu lỗi gõ sai cache name. Với `SimpleCacheManager`, các cache instance được xác định sẵn và không tự mở rộng tên khi lookup.

Không hiểu nhầm rằng `ConcurrentMapCacheManager("catalog","reports")` là luôn dynamic: constructor nhận các tên được định nghĩa trước tạo chế độ tên cố định. Cả hai lựa chọn đều chỉ là cache in-memory đơn giản, không có TTL/eviction dung lượng mặc định.

## 7. Điều chỉnh từng cache và chính sách null

### 7.1. ConcurrentMapCache mặc định hỗ trợ null nghiệp vụ

Native `ConcurrentHashMap` **không chứa value null**. Tuy nhiên `ConcurrentMapCache` Spring có khả năng chuyển **null nghiệp vụ** thành một marker nội bộ khi cho phép null. Constructor đơn giản `new ConcurrentMapCache("catalog")` mặc định hỗ trợ null.

Để **không cho phép null** trên một vùng cụ thể:

```java
SimpleCacheManager manager = new SimpleCacheManager();
manager.setCaches(List.of(
    new ConcurrentMapCache("catalog", false),
    new ConcurrentMapCache("reports", true)
));
```

Đây là **mảnh cấu hình minh họa**, chưa chạy riêng vì cần imports và vòng đời khởi tạo manager. Constructor `ConcurrentMapCache(String name, boolean allowNullValues)` đặt chính sách cho từng vùng; không có `SimpleCacheManager.setAllowNullValues(...)` áp toàn bộ giống `ConcurrentMapCacheManager`.

Để tránh cache kết quả null của phương thức dù backend cho phép:

```java
@Cacheable(
    cacheNames = "catalog",
    key = "#p0",
    unless = "#result == null"
)
public Product find(String sku) {
    return repository.findProduct(sku);
}
```

Đây là method minh họa có kiểu `Product` và `repository` thật. `unless` được kiểm tra sau khi method trả về khi cache miss và có thể từ chối put kết quả null.

Nếu vẫn muốn cache null (negative caching) thì hãy xác định TTL/eviction khi dữ liệu xuất hiện sau đó. `ConcurrentMapCache` đơn giản không tự xóa entry theo TTL.

### 7.2. Dùng map tự cấp khi cần

Ngoài constructor một hoặc hai đối số, Spring còn hỗ trợ:

```java
ConcurrentMap<Object, Object> nativeMap = new ConcurrentHashMap<>();
ConcurrentMapCache catalog =
        new ConcurrentMapCache("catalog", nativeMap, true);
```

Đây là mảnh code minh họa với `java.util.concurrent.ConcurrentMap` và `ConcurrentHashMap`. Tham số boolean quyết định có cho phép chuyển null nghiệp vụ. Cách này giúp kiểm soát backing map hoặc chia sẻ chính instance đó theo chủ đích, nhưng **không** biến nó thành Redis hay bổ sung tự động TTL/giới hạn dung lượng.

Nếu đọc `cache.getNativeCache()`, nhớ rằng null có thể được biểu diễn bằng marker nội bộ, không nên suy diễn trực tiếp ý nghĩa nghiệp vụ từ value native. Đọc qua `Cache.get(key)`/`ValueWrapper` để tôn trọng semantics của Spring Cache.

### 7.3. Store by reference và đối tượng mutable

Trong cấu hình đơn giản, cache giữ **tham chiếu object** theo mặc định. Nếu cache trả một `ArrayList` hoặc DTO mutable, nhiều lời gọi có thể nhận cùng object và chỉnh sửa nó; tính thread-safe của `ConcurrentHashMap` **không** làm mọi object value trở thành thread-safe.

Nên ưu tiên immutable record/DTO, defensive copy khi thích hợp và thiết kế rõ ràng vòng đời value. Nếu cần store-by-value (bản sao/serialization) hoặc quản lý bộ nhớ, xem cache provider phù hợp hoặc cấu hình sâu hơn thay vì giả định `SimpleCacheManager` tự xử lý.

## 8. Quản lý eviction và tính nhất quán

`ConcurrentMapCache` không có eviction dựa trên TTL, LRU hay giới hạn số lượng entry mặc định. **Tên cache được khai báo trước** không đồng nghĩa **bộ nhớ không thể tăng vô hạn**: một vùng có thể tiếp tục nhận thêm rất nhiều key trong suốt vòng đời JVM.

Với bài học ở phần 5:

- `@CacheEvict(cacheNames="catalog", key="#p0")` xóa entry theo key tương ứng.
- `@CacheEvict(cacheNames="reports", allEntries=true)` yêu cầu clear toàn bộ vùng reports.
- Hai vùng cache là độc lập. Xóa catalog không ngầm xóa reports dù chúng có thể chứa dữ liệu phụ thuộc nhau.

Trong ứng dụng thật, hãy xác định mọi vùng phụ thuộc cùng nguồn dữ liệu. Nếu cập nhật sản phẩm cũng làm thay đổi báo cáo vùng, chỉ evict catalog là **không đủ**; cần evict reports hoặc key liên quan theo logic đúng.

Một số giới hạn hệ thống:

1. **Một JVM:** cache tồn tại trong heap của process. Mỗi pod/JVM có các instance khác nhau; cập nhật hoặc evict ở một process không tự lan truyền tới process khác.
2. **Khởi động lại:** entry bị mất; đây là cache tạm, không phải persistence layer.
3. **Khả năng đồng thời:** concurrent-map đảm bảo các thao tác map theo hợp đồng thread safety, nhưng chuỗi cache miss → tính → put không mặc nhiên nguyên tử; hai request có thể cùng chạy body khi miss đồng thời. Có thể cân nhắc `@Cacheable(sync=true)` khi provider hỗ trợ và đáp ứng ràng buộc, nhưng vẫn không phải distributed lock.
4. **Transaction:** `@CacheEvict` và DB transaction không mặc định tạo một distributed transaction chung. Với dữ liệu quan trọng, xác minh thời điểm commit, eviction và race với phép tải đang chạy.
5. **Hiệu năng:** cache lớn không giới hạn làm tăng heap, chi phí GC và nguy cơ OOM; ứng dụng production thường cần Caffeine hoặc Redis với eviction/TTL/metrics phù hợp.

Việc chọn `SimpleCacheManager` chỉ quyết định **cách quản lý các Cache instance**, không tự tạo thêm tính năng expiration, observability hoặc phân tán.

## 9. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| `getCache("catalog") == null` dù đã setCaches | Tự khởi tạo manager nhưng quên `initializeCaches()` | Khi ngoài Spring container, gọi init sau setCaches; khi là bean, để Spring làm |
| `getCache("reports") == null` | Khai báo tên sai hoặc không đưa instance vào setCaches | Kiểm tra `Cache.getName()` và collection |
| Annotation tham chiếu cache tên lạ | `SimpleCacheManager` không tự tạo cache mới | Thêm cache instance vào cấu hình hoặc sửa tên annotation |
| `@Cacheable` không cache | Chưa `@EnableCaching` đúng context, bean tạo bằng `new` hoặc self-invocation | Kiểm tra proxy, ApplicationContext, service bean |
| Lần đầu method vẫn chạy | Cache miss là hành vi bình thường | Gọi cùng key lần hai và quan sát bộ đếm |
| Xóa một key nhưng entry vẫn hit | Evict và đọc không dùng cùng cache name hoặc key | So sánh chính xác SpEL key và region |
| Xóa reports nhưng catalog vẫn hit | Hai cache độc lập | Nếu dữ liệu phụ thuộc nhau, evict cả vùng liên quan |
| Cached null gây kết quả không cập nhật | Provider cho phép negative caching | Cân nhắc `unless`, TTL hoặc eviction khi dữ liệu nguồn đổi |
| Cache hết RAM sau khi chạy lâu | ConcurrentMapCache không có TTL/max-size mặc định | Dùng cache provider có hạn chế dung lượng và metrics |
| Hệ thống nhiều node có cache khác nhau | Cache trong heap mỗi JVM riêng | Dùng cache phân tán hoặc event invalidation phù hợp |
| Giá trị cache bị sửa ngầm | Store by reference với object mutable | Dùng DTO bất biến hoặc defensive copies |
| Khởi tạo trùng cache name | Nhiều instance mang một tên khiến registry mơ hồ | Đảm bảo tên duy nhất và test danh sách cache |

Khi debug, bắt đầu từ 4 câu hỏi: **Spring có gọi qua proxy không?** → **manager trả đúng instance cache name không?** → **key có đúng không?** → **entry có bị evict/hết hiệu lực hay chưa?** Với `SimpleCacheManager`, danh sách cache names có thể xác minh ngay lúc startup qua `getCacheNames()`.

## 10. Chiến lược test và checklist triển khai

### 10.1. Những kiểm thử nên có

1. **Registry:** sau startup, `getCacheNames()` chứa đúng `catalog` và `reports`; `getCache("unknown")==null`.
2. **Cache instance:** gọi `getCache("catalog")` hai lần được cùng instance khi registry không bị thay đổi.
3. **Cache miss/hit:** gọi `@Cacheable` hai lần cùng key, body chỉ thực thi một lần.
4. **Key khác:** gọi `item("SKU-2")` khi chỉ có entry `SKU-1` phải chạy method cho key mới.
5. **Evict theo key:** thay đổi SKU-1, evict, đọc lại SKU-1 phải được tính mới.
6. **Không xóa vùng khác:** evict catalog không làm mất hit của reports.
7. **Clear toàn vùng:** `allEntries=true` trên reports làm các key reports đều miss, không ảnh hưởng catalog.
8. **Lifecycle:** thử tự tạo manager ngoài Spring, gọi `initializeCaches()` rồi tra cache; tránh phụ thuộc vào callback mà không có container.
9. **Null policy:** xác nhận hành vi khi method trả null, `allowNullValues` và `unless`.
10. **Đa luồng:** kiểm tra hit/miss đồng thời, khả năng double-load và hành vi khi eviction xen kẽ.
11. **Nhiều node:** nếu triển khai đa instance, test từng node để phát hiện cache độc lập không có invalidation cross-node.
12. **Quản trị bộ nhớ:** theo dõi số key, heap/GC, tần suất invalidation; nếu tăng cao, đổi provider.

### 10.2. Checklist trước production

- Số lượng vùng cache đủ ít và đã được định nghĩa rõ ràng?
- Tên cache ở annotation, key SpEL và cấu hình manager đã nhất quán?
- Chỉ có một CacheManager mặc định rõ ràng, hoặc chỉ định manager ở annotation khi có nhiều manager?
- Mọi bean có caching annotation đều đi qua Spring proxy?
- Đã quyết định có cache null, thời điểm evict/clear và TTL cần thiết?
- Heap đủ cho số entry cực đại hay cần provider có cache eviction theo capacity?
- Dữ liệu có thể stale giữa nhiều node không, và yêu cầu consistency cụ thể là gì?
- Có test hit/miss, exception, concurrency, update nguồn và restart?

Đừng đặt `SimpleCacheManager` làm persistence layer hoặc dùng cache nội bộ làm nguồn dữ liệu chuẩn. Nó là công cụ tốt cho ví dụ, test và một số ứng dụng nhỏ, nhưng cần đánh giá lại khi khối lượng dữ liệu, số node hoặc yêu cầu độ tin cậy tăng.

## 11. Câu hỏi tự kiểm tra

**Q1.** `manager.setCaches(List.of(new ConcurrentMapCache("catalog")))` khác gì `manager.getCache("catalog")`?

**Đáp:** `setCaches` cung cấp tập cache instances để manager quản lý **khi khởi tạo**; `getCache` tra cứu instance đã được đăng ký theo tên.

**Q2.** Tại sao trong method `@Bean` không phải gọi `manager.afterPropertiesSet()` bằng tay?

**Đáp:** Spring container xử lý lifecycle của bean, bao gồm callback `InitializingBean`. Nếu tự dùng manager ngoài container, phải khởi tạo cache registry bằng `initializeCaches()` sau khi setCaches.

**Q3.** `getCache("unknown") == null` có nghĩa `catalog` đang cache miss không?

**Đáp:** Không. Nó nghĩa là **vùng unknown không tồn tại**. Cache miss là khi đã có vùng cache và không có mapping cho một key.

**Q4.** Hai cache instances cùng backing JVM có tự chia sẻ entry không?

**Đáp:** Không. `new ConcurrentMapCache("catalog")` và `new ConcurrentMapCache("reports")` có các native stores riêng theo mặc định.

**Q5.** Vì sao cache được khai báo trước vẫn có thể gây thiếu RAM?

**Đáp:** Cố định số vùng không đồng nghĩa giới hạn số entry. `ConcurrentMapCache` không tự cấp TTL hay max-size.

**Q6.** `SimpleCacheManager` có tự sinh cache mới khi một annotation gõ sai tên không?

**Đáp:** Không. Đây là manager được cung cấp một collection cache instances cố định; một tên chưa đăng ký không tự thành vùng mới.

**Q7.** Dùng Spring proxy và `@Cacheable` có đủ để đồng bộ kết quả giữa hai pod không?

**Đáp:** Không. `ConcurrentMapCache` chạy trong bộ nhớ từng JVM; cần giải pháp invalidation/distributed caching theo kiến trúc khi nhiều instance cùng phục vụ dữ liệu.

## 12. Ghi nhớ

- `SimpleCacheManager` quản lý **các đối tượng `Cache` được khai báo sẵn** qua `setCaches(Collection<? extends Cache>)`.
- `ConcurrentMapCache` cung cấp bộ nhớ cache bằng concurrent map cho từng vùng; **khai báo vùng ≠ prefill entry**.
- Khi được Spring tạo như một bean, lifecycle tự chạy `afterPropertiesSet/initializeCaches`; khi tạo bên ngoài container, phải khởi tạo thủ công.
- `getCache(name)` chỉ tra vùng đã đăng ký; tên không tồn tại trả null. Với cache tồn tại, cache miss theo key là một trạng thái khác.
- `@EnableCaching` + Spring proxy mới kích hoạt `@Cacheable` và `@CacheEvict`; cache region name/key phải khớp.
- Thích hợp cho học tập, test, ứng dụng đơn giản; không tự cung cấp TTL, eviction theo kích thước, persistence hay chia sẻ đa JVM.

### Tài liệu tham khảo chính thức

- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — SimpleCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/support/SimpleCacheManager.html)
- [Spring Framework — AbstractCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/support/AbstractCacheManager.html)
- [Spring Framework — ConcurrentMapCache Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html)
- [Spring Framework — ConcurrentMapCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
