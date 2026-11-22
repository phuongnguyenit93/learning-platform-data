# CacheResolver tùy chỉnh theo đối số hoặc ngữ cảnh

## 1. Mục tiêu và bài toán

Spring Cache dùng các annotation như `@Cacheable`, `@CachePut` và `@CacheEvict` để khai báo thao tác cache quanh lời gọi phương thức. Câu hỏi quan trọng không chỉ là **dùng key nào**, mà còn là **dùng vùng cache nào**. Trong ứng dụng đơn giản, một `CacheManager` và một `cacheNames` cố định thường đủ. Nhưng với nhiều tenant, vùng địa lý, loại dữ liệu, nguồn xử lý hoặc nhiều cache manager, việc chọn vùng cache có thể phải diễn ra **ở runtime**, theo tham số hoặc ngữ cảnh thực thi.

`CacheResolver` là điểm mở rộng của Spring Cache để giải quyết bài toán đó. Nó nhận thông tin về operation và lời gọi hiện tại, rồi trả về một hoặc nhiều đối tượng `Cache` mà interceptor sẽ sử dụng.

Sau bài này, bạn sẽ:

- Phân biệt `CacheResolver`, `CacheManager`, `KeyGenerator`, tên cache và cache key.
- Viết resolver chọn cache theo tham số phương thức, ví dụ `region`.
- Viết resolver chọn cache theo ngữ cảnh đáng tin cậy, ví dụ tenant hiện tại.
- Cấu hình `@Cacheable(cacheResolver = "...")` và dùng nhất quán cho `@CacheEvict`.
- Hiểu các rủi ro về tenant isolation, lỗi cấu hình, bộ nhớ, transaction, proxy và concurrency.
- Chạy ví dụ Java 17 có thể quan sát hit/miss, định tuyến và invalidation.

## 2. CacheResolver là gì? Nó đứng ở đâu trong luồng xử lý?

Ba khái niệm thường bị nhầm lẫn:

| Khái niệm | Trả lời câu hỏi nào? | Ví dụ |
| --- | --- | --- |
| `CacheManager` | Làm sao truy xuất một vùng cache có tên? | `manager.getCache("prices-north")` |
| `CacheResolver` | Với lời gọi **này**, phải thao tác trên vùng cache nào? | `region = "north"` → cache `prices-north` |
| `KeyGenerator` hoặc thuộc tính `key` | Trong vùng cache đã chọn, entry nào tương ứng với lời gọi? | `sku = "P1"` → key `"P1"` |

Hãy nghĩ tới hai cấp định vị:

~~~text
CacheResolver quyết định cache nào
           |
           v
      prices-north             prices-south
       |         |             |         |
       v         v             v         v
      "P1"      "P2"          "P1"      "P2"
       |                         |
       v                         v
      100                       200
    (north/P1)                (south/P1)
~~~

Key `"P1"` có thể xuất hiện **ở cả hai cache** mà không xung đột, vì chúng là hai không gian lưu trữ riêng. Một resolver chọn cache `prices-north` cho request miền Bắc; request miền Nam đi tới `prices-south`. Nếu dùng chung cache, cần mã hóa thêm region/tenant trong key để tránh đụng dữ liệu.

### Luồng tổng quát với @Cacheable

~~~text
Caller -> Spring proxy / CacheInterceptor
                  |
                  v
      Đọc @Cacheable + invocation context
                  |
                  v
       CacheResolver.resolveCaches(context)
                  |
                  v
       Collection<? extends Cache>
                  |
                  v
        Tạo key theo cấu hình key
                  |
                  v
        Tra entry trên cache được chọn
             /                \
           HIT                MISS
            |                   |
            v                   v
      Trả kết quả         Gọi method gốc
                                |
                                v
                       Có thể ghi kết quả
                       vào cache được chọn
~~~

Đây là sơ đồ khái niệm cho cách cache hit/miss hoạt động; đường đi chi tiết có thể khác khi `condition`, `unless`, nhiều cache, async/reactive return hay provider có đặc tính riêng. `CacheResolver` **không** tự quyết định giá trị trả về của method, không tự làm database query và cũng không tự định nghĩa TTL.

## 3. Giao diện CacheResolver và thông tin runtime

Giao diện Spring:

~~~java
package org.springframework.cache.interceptor;

public interface CacheResolver {
    Collection<? extends Cache> resolveCaches(
            CacheOperationInvocationContext<?> context);
}
~~~

Đoạn trên mô tả chữ ký API (đã lược các khai báo `import`), **không phải file Java độc lập**. Resolver cần trả về collection các đối tượng `org.springframework.cache.Cache` thực tế.

`CacheOperationInvocationContext<?>` cung cấp những đầu vào hữu ích:

| API | Ý nghĩa | Tình huống sử dụng |
| --- | --- | --- |
| `context.getArgs()` | Mảng đối số của lời gọi hiện tại | Chọn cache theo `region`, `tenantId`, loại tài liệu |
| `context.getMethod()` | `Method` được gọi | Dùng chung resolver cho nhiều operation |
| `context.getTarget()` | Bean đích thực thi | Phân biệt nhóm service nếu thực sự cần |
| `context.getOperation()` | Metadata cache operation | Đọc `cacheNames` được khai báo hoặc các thuộc tính metadata |

Lưu ý: `context.getArgs()` trả đối số **trước lúc method chạy**. Không thể chọn cache dựa vào kết quả trả về cuối cùng từ chính lời gọi này. Khi logic phụ thuộc vào kết quả, cần thiết kế cache operation hoặc luồng nghiệp vụ khác.

Resolver được gọi trong phạm vi cache operation, vì thế nên **nhanh, xác định được**, không gây side effect nghiệp vụ và không truy vấn DB đắt tiền chỉ để quyết định cache. Nếu không tìm được một cache hợp lệ, hãy xử lý rõ ràng (ví dụ ném exception có ý nghĩa) thay vì âm thầm trả nhầm cache chung. Không nên trả collection rỗng hoặc đưa giá trị `null` vào collection để giả lập “không cache”.

## 4. Khi nào dùng resolver tùy chỉnh?

### 4.1. Chọn theo tham số

Ví dụ:

~~~java
public int getPrice(String region, String sku)
~~~

- `region="north"` → `prices-north`.
- `region="south"` → `prices-south`.
- Cùng SKU `"P1"` nhưng ở hai region có mức giá khác nhau.
- Khi cập nhật giá ở `north`, chỉ entry thuộc `prices-north` bị xóa.

Resolver đọc `context.getArgs()[0]` để lấy region. Key của mỗi entry có thể chỉ là `sku`, tức `#p1`.

### 4.2. Chọn theo ngữ cảnh

Một API đa tenant không nhất thiết muốn lặp `tenantId` ở mọi method:

~~~java
public String profile(String userId)
~~~

Tenant hiện tại có thể lấy từ security principal đã xác thực, request scope hoặc một tenant context được thiết lập trước khi vào service. Resolver chọn:

- Tenant `a` → cache `profiles-a`.
- Tenant `b` → cache `profiles-b`.

Method nghiệp vụ có thể nhận cùng `userId="u1"`, nhưng cache của từng tenant vẫn tách biệt. Đây là quyết định **phân vùng và cô lập dữ liệu**; không phải chỉ là tối ưu hiệu năng.

### 4.3. Chọn giữa các CacheManager

Khi một operation cần dùng Caffeine còn operation khác cần Redis, resolver có thể giữ tham chiếu đến cả hai `CacheManager` rồi chọn manager theo loại dữ liệu hoặc yêu cầu thực tế. Dùng cấu hình `cacheManager` trực tiếp nếu lựa chọn là **cố định cho từng method**. Dùng `CacheResolver` khi việc lựa chọn phụ thuộc vào **mỗi lần gọi**.

### Khi không cần custom resolver

Nếu tất cả lời gọi đều dùng cache `"products"`, cách đơn giản và rõ ràng nhất là:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) {
    return repository.load(sku);
}
~~~

Đây là snippet minh họa, chưa độc lập vì `Product` và `repository` thuộc ứng dụng. Không nên thêm resolver riêng chỉ để trả về chính cache `products` ở mọi lần gọi: code phức tạp hơn nhưng không tăng giá trị.

## 5. Gắn resolver với annotation

Khi có bean Spring tên `regionResolver`:

~~~java
@Cacheable(cacheResolver = "regionResolver", key = "#p1")
public int getPrice(String region, String sku) {
    return database.load(region, sku);
}
~~~

`cacheResolver` là **tên bean**, không phải tên class. Spring tìm bean được khai báo phù hợp, ví dụ:

~~~java
@Bean("regionResolver")
public CacheResolver regionResolver(CacheManager manager) {
    return context -> {
        String region = (String) context.getArgs()[0];
        String cacheName = "prices-" + region;
        Cache cache = manager.getCache(cacheName);
        if (cache == null) {
            throw new IllegalArgumentException(
                    "Unsupported cache name: " + cacheName);
        }
        return List.of(cache);
    };
}
~~~

Hai đoạn Java trên là snippet định hướng, không phải chương trình chạy độc lập. Cách nối chuỗi `"prices-" + region` thích hợp để diễn giải nhưng **không nên đưa thẳng input không tin cậy vào tên cache trong production**. Demo hoàn chỉnh ở mục 7 dùng một allowlist `switch` để chọn đúng cache đã cho phép.

### Có cần cacheNames không?

Không bắt buộc nếu custom resolver đã cung cấp các cache. Ví dụ:

~~~java
@Cacheable(cacheResolver = "regionResolver", key = "#p1")
~~~

là cấu hình hợp lệ. Khi tự trả về một collection các `Cache` theo runtime, resolver không nhất thiết phụ thuộc `cacheNames` của annotation. Nếu muốn giữ cache name làm metadata logic, có thể khai báo nó và xử lý có chủ đích trong resolver. Đừng giả định custom resolver luôn tự động tôn trọng `cacheNames`: **chính phần implementation quyết định điều đó**.

### cacheManager và cacheResolver có cùng đặt trên operation được không?

Không. `cacheManager` và `cacheResolver` là hai cách chọn cơ chế phân giải cache mang tính thay thế nhau; khai báo **cả hai trong cùng cache operation** là cấu hình không hợp lệ. Tương tự, `key` và `keyGenerator` không dùng cùng nhau cho một operation.

Ví dụ **không đúng**:

~~~java
@Cacheable(
    cacheNames = "prices",
    cacheManager = "redisManager",
    cacheResolver = "regionResolver"
)
public int getPrice(String region, String sku) {
    return 0;
}
~~~

Đoạn trên cố ý là ví dụ cấu hình sai, không dùng để chạy. Nếu `regionResolver` đã biết phải dùng manager nào, chỉ khai báo `cacheResolver`.

### Cấu hình toàn cục/lớp

Có thể áp dụng `CacheResolver` mặc định qua `CachingConfigurer` hoặc ở mức lớp với `@CacheConfig(cacheResolver = "regionResolver")`. Cấu hình trực tiếp trên method được ưu tiên so với mức lớp, và cấu hình lớp có thể ghi đè mặc định toàn cục. Chỉ dùng phạm vi rộng khi toàn bộ các method trong phạm vi đó thật sự có chung hợp đồng định tuyến.

## 6. Thiết kế nhất quán giữa đọc, ghi và xóa

Một hệ thống có thể đọc qua `@Cacheable`, ghi lại qua `@CachePut` hoặc xóa qua `@CacheEvict`. Ba hoạt động phải nhất quán về **cache được chọn** và **key**.

Ví dụ:

~~~java
@Cacheable(cacheResolver = "regionResolver", key = "#p1")
public int getPrice(String region, String sku) {
    return repository.findPrice(region, sku);
}

@CacheEvict(cacheResolver = "regionResolver", key = "#p1")
public void changePrice(String region, String sku, int newPrice) {
    repository.updatePrice(region, sku, newPrice);
}
~~~

Đây là snippet minh họa; `repository` chưa được định nghĩa. Điều quan trọng:

1. Cùng region thì resolver phải trả cùng cache cho cả getter lẫn updater.
2. Cùng SKU thì cả hai key expression đều tạo ra key `sku`; tham số giá mới không được tham gia key.
3. Sau khi updater chạy thành công, entry cũ bị evict; lần đọc tiếp theo mới nạp dữ liệu mới.
4. Nếu getter dùng cache theo tenant nhưng updater evict ở cache mặc định, entry tenant vẫn tồn tại và có thể stale.

Khi chọn cache theo security/request context, cùng ngữ cảnh tin cậy phải tồn tại trong thời gian update và evict. Không được giả định method nào cũng chạy trên thread chứa context giống nhau, đặc biệt trong `@Async`, queue listener hoặc reactive flow.

## 7. Demo runnable: chọn cache theo đối số và ngữ cảnh

Ví dụ đầy đủ sau dùng **Java 17**, **Spring Framework 6.2.19** và Maven. Không cần Spring Boot hay Redis; provider là `ConcurrentMapCacheManager` lưu trong JVM.

Demo kiểm tra cả hai trường hợp:

- Phương thức `price(region, sku)` chọn cache theo **đối số region**.
- Phương thức `profile(userId)` chọn cache theo **tenant context**.
- `changePrice(region, sku, newValue)` dùng cùng resolver và key với getter để chỉ xóa vùng bị ảnh hưởng.

### 7.1. Cấu trúc thư mục

~~~text
dynamic-cache-resolution/
├── pom.xml
└── src/main/java/demo/CacheRoutingDemo.java
~~~

### 7.2. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>dynamic-cache-resolution</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. File src/main/java/demo/CacheRoutingDemo.java

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.CacheResolver;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheRoutingDemo {

    // Chỉ mô phỏng context trong ví dụ đồng bộ.
    // Production: tenant phải đến từ identity đã xác thực.
    public static final class TenantContext {
        private static final ThreadLocal<String> CURRENT =
                new ThreadLocal<>();

        static String requireTenant() {
            String tenant = CURRENT.get();
            if (tenant == null) {
                throw new IllegalStateException("Tenant is missing");
            }
            return tenant;
        }

        static void runAs(String tenant, Runnable action) {
            String previous = CURRENT.get();
            CURRENT.set(tenant);
            try {
                action.run();
            } finally {
                if (previous == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(previous);
                }
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            // Chỉ cho phép các cache đã khai báo.
            return new ConcurrentMapCacheManager(
                    "prices-north", "prices-south",
                    "profiles-a", "profiles-b");
        }

        @Bean("regionResolver")
        public CacheResolver regionResolver(CacheManager manager) {
            return context -> {
                Object[] args = context.getArgs();
                if (args.length == 0 ||
                        !(args[0] instanceof String region)) {
                    throw new IllegalArgumentException(
                            "Region argument is required");
                }

                String cacheName = switch (region) {
                    case "north" -> "prices-north";
                    case "south" -> "prices-south";
                    default -> throw new IllegalArgumentException(
                            "Unknown region: " + region);
                };

                return List.of(requiredCache(manager, cacheName));
            };
        }

        @Bean("tenantResolver")
        public CacheResolver tenantResolver(CacheManager manager) {
            return context -> {
                String tenant = TenantContext.requireTenant();
                String cacheName = switch (tenant) {
                    case "a" -> "profiles-a";
                    case "b" -> "profiles-b";
                    default -> throw new IllegalArgumentException(
                            "Unknown tenant: " + tenant);
                };

                return List.of(requiredCache(manager, cacheName));
            };
        }

        @Bean
        public DataService dataService() {
            return new DataService();
        }
    }

    private static Cache requiredCache(
            CacheManager manager, String name) {
        Cache cache = manager.getCache(name);
        if (cache == null) {
            throw new IllegalStateException(
                    "Cache not configured: " + name);
        }
        return cache;
    }

    public static class DataService {
        // DB mô phỏng; key "region|sku" độc lập với cache key.
        private final Map<String, Integer> database =
                new ConcurrentHashMap<>();
        private final AtomicInteger priceReads = new AtomicInteger();
        private final AtomicInteger profileReads = new AtomicInteger();

        public DataService() {
            database.put("north|P1", 100);
            database.put("south|P1", 200);
        }

        @Cacheable(cacheResolver = "regionResolver", key = "#p1")
        public int price(String region, String sku) {
            Integer value = database.get(region + "|" + sku);
            if (value == null) {
                throw new IllegalArgumentException("Unknown product");
            }

            int number = priceReads.incrementAndGet();
            System.out.println(
                    "DB price " + region + "/" + sku + " #" + number);
            return value;
        }

        @CacheEvict(cacheResolver = "regionResolver", key = "#p1")
        public void changePrice(
                String region, String sku, int newPrice) {
            database.put(region + "|" + sku, newPrice);
            System.out.println(
                    "WRITE " + region + "/" + sku + "=" + newPrice);
        }

        @Cacheable(cacheResolver = "tenantResolver", key = "#p0")
        public String profile(String userId) {
            String tenant = TenantContext.requireTenant();
            int number = profileReads.incrementAndGet();
            System.out.println(
                    "DB profile " + tenant + "/" + userId
                    + " #" + number);
            return tenant + ":" + userId;
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                Config.class)) {
            DataService service = context.getBean(DataService.class);
            CacheManager manager = context.getBean(CacheManager.class);

            // Định tuyến theo tham số region.
            System.out.println("north1=" + service.price("north", "P1"));
            System.out.println("north2=" + service.price("north", "P1"));
            System.out.println("south1=" + service.price("south", "P1"));

            Cache north = requiredCache(manager, "prices-north");
            Cache south = requiredCache(manager, "prices-south");
            System.out.println("north cached? "
                    + (north.get("P1") != null));
            System.out.println("south cached? "
                    + (south.get("P1") != null));

            service.changePrice("north", "P1", 150);
            System.out.println("north after evict? "
                    + (north.get("P1") != null));
            System.out.println("south after evict? "
                    + (south.get("P1") != null));
            System.out.println("north3=" + service.price("north", "P1"));
            System.out.println("south2=" + service.price("south", "P1"));

            // Định tuyến theo ngữ cảnh tenant hiện tại.
            TenantContext.runAs("a", () -> {
                System.out.println("a1=" + service.profile("u1"));
                System.out.println("a2=" + service.profile("u1"));
            });
            TenantContext.runAs("b", () ->
                    System.out.println(
                            "b1=" + service.profile("u1")));
            TenantContext.runAs("a", () ->
                    System.out.println(
                            "a3=" + service.profile("u1")));
        }
    }
}
~~~

### 7.4. Chạy chương trình

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheRoutingDemo
~~~

Stdout do **chương trình** in ra, không bao gồm thông báo Maven/phụ thuộc theo môi trường:

~~~text
DB price north/P1 #1
north1=100
north2=100
DB price south/P1 #2
south1=200
north cached? true
south cached? true
WRITE north/P1=150
north after evict? false
south after evict? true
DB price north/P1 #3
north3=150
south2=200
DB profile a/u1 #1
a1=a:u1
a2=a:u1
DB profile b/u1 #2
b1=b:u1
a3=a:u1
~~~

### 7.5. Đọc dấu vết và giải thích

**Định tuyến theo đối số:**

- `north1`: resolver lấy `region=north`, trả `prices-north`. Entry `P1` chưa có → method chạy → in `DB price... #1` và lưu 100.
- `north2`: vẫn chọn `prices-north`, cùng key `P1` → hit, không thêm dòng `DB price`.
- `south1`: resolver chọn **cache khác** `prices-south`. Dù key vẫn `P1`, đây là miss riêng → method chạy, nạp 200.
- Sau `changePrice("north","P1",150)`: cùng resolver chọn `prices-north`; `@CacheEvict` xóa riêng entry `P1` tại vùng đó. Cache `prices-south` vẫn giữ 200.
- `north3` miss nên method nạp 150; `south2` hit nên không có lần đọc DB mới.

**Định tuyến theo ngữ cảnh:**

- Với context tenant `a`, `profile("u1")` chọn `profiles-a`. Lần đầu in `DB profile a/u1 #1`; lần thứ hai hit.
- Với context tenant `b`, **cùng key** `u1` vẫn chọn `profiles-b`, nên phải tính lần đầu cho tenant b (counter tăng tới 2).
- Quay lại tenant a, `a3` hit trên `profiles-a`, không in thêm dòng DB.
- `TenantContext.runAs` khôi phục context cũ hoặc `remove()` trong `finally` để không làm rò dữ liệu giữa các lời gọi tuần tự trên thread tái sử dụng.

### 7.6. Vì sao demo phải dùng ApplicationContext?

`@EnableCaching` bật cơ chế annotation; các lời gọi tới `DataService` thông qua bean lấy từ `ApplicationContext` được Spring proxy/interceptor xử lý. Nếu gọi `new DataService().price(...)` ngoài Spring, annotation không tự chạy. Với proxy mode mặc định, self-invocation như `this.price(...)` cũng không đi qua caching advice. Thực tế nên tổ chức ranh giới service để các lời gọi cần cache đi qua Spring-managed proxy.

Demo là in-memory trên **một JVM**, không tự kiểm chứng tính nhất quán giữa nhiều instance hoặc security context của ứng dụng web thật.

## 8. Thiết kế CacheResolver theo ngữ cảnh trong production

Đoạn demo dùng `ThreadLocal` để trình bày ý tưởng. Khi xây hệ thống thật, “tenant hiện tại” phải có nguồn **đáng tin**.

### 8.1. Nguồn lấy ngữ cảnh

| Nguồn | Điểm cần lưu ý |
| --- | --- |
| Tham số đã validate | Truyền minh bạch từ boundary vào service; không tin trực tiếp chuỗi nhập tùy ý |
| Security principal đã xác thực | Ưu tiên tenant thuộc identity/authorization đã kiểm tra |
| Request-scoped object | Chỉ hiện diện trong HTTP request phù hợp; không tự có trong batch/worker |
| ThreadLocal | Phải set/clear hoặc restore đúng; dễ sai khi chạy thread pool/async |
| Reactor context / async context | Cần cơ chế truyền context tương ứng; không giả định ThreadLocal tự đi theo luồng |

**Không dùng header `X-Tenant` chưa xác thực làm căn cứ phân vùng dữ liệu nhạy cảm.** Một resolver chọn cache sai có thể tạo lỗi rò dữ liệu chéo tenant. Cache routing không thay thế authorization ở tầng nghiệp vụ.

### 8.2. Fail closed khi thiếu ngữ cảnh

Giả sử method yêu cầu tenant. Nếu context trống, cách nguy hiểm là:

~~~java
String tenant = currentTenantOrNull();
String name = tenant == null ? "profiles-shared" : "profiles-" + tenant;
~~~

Snippet trên minh họa **anti-pattern** (hàm `currentTenantOrNull` giả định), không được dùng như giải pháp. Cách fallback sang cache shared có thể khiến cùng key `u1` của nhiều tenant va chạm. Thay vào đó, ném lỗi có ý nghĩa hoặc định nghĩa rõ một ngữ cảnh hệ thống độc lập đã được cấp quyền.

### 8.3. Tránh cấp phát cache không giới hạn từ input

Một số `CacheManager` có thể tự tạo cache với tên mới khi `getCache(name)` được gọi. Nếu tên cache được ghép từ đầu vào không kiểm soát, request tạo hàng nghìn tên khác nhau có thể làm tăng bộ nhớ, metadata hoặc số lượng resource ở backend. Cách phòng ngừa:

1. Chuẩn hóa và validate region/tenant từ nguồn đã xác thực.
2. Nếu tập lựa chọn hữu hạn, dùng `switch`/allowlist như demo.
3. Nếu số tenant lớn/biến động, cân nhắc **một cache chung với key có tenant prefix an toàn** thay vì tạo cache riêng cho từng tenant; lựa chọn phụ thuộc backend, quota và yêu cầu cô lập.
4. Giám sát cardinality của cache name/key, memory, eviction, hit ratio và chi phí quản lý.

Phân vùng vật lý theo tenant và namespace hóa key theo tenant là hai thiết kế khác nhau; nên chọn dựa trên bảo mật, vận hành và khả năng mở rộng.

### 8.4. Tính nhất quán với invalidation

Nếu chọn theo tenant, mọi đường cập nhật nên evict/put vào đúng tenant. Với cùng một logical entity, cần bảo đảm:

~~~text
Read request for tenant a:
  resolver -> profiles-a -> key "u1" -> hit/miss

Update request for tenant a:
  resolver -> profiles-a -> key "u1" -> evict/put

Read request for tenant b:
  resolver -> profiles-b -> key "u1"
  -> KHÔNG ảnh hưởng dữ liệu tenant a
~~~

Nếu resolver phụ thuộc vào context nhưng một tác vụ nền không có context, không nên “đoán” tenant. Hãy truyền tenant vào job và thiết lập context tin cậy hoặc dùng một API invalidate rõ tenant ở ranh giới hệ thống.

### 8.5. Transaction và thời điểm xóa

`@CacheEvict` mặc định xử lý sau khi method chạy thành công, **không tự đảm bảo xóa sau database commit** trong mọi tổ hợp AOP/transaction. Nếu cache được xóa trước commit, một reader khác có thể miss rồi nạp lại dữ liệu cũ. Thiết kế cơ chế invalidation sau commit nếu consistency yêu cầu. Resolver chỉ chọn cache; nó không giải quyết thứ tự commit hoặc race condition.

## 9. Chọn cache bằng nhiều CacheManager

Giả sử một service có `localCacheManager` và `remoteCacheManager`. Một resolver có thể định tuyến loại dữ liệu ngắn hạn về local, dữ liệu chia sẻ về remote:

~~~java
@Bean("tierResolver")
public CacheResolver tierResolver(
        CacheManager localCacheManager,
        CacheManager remoteCacheManager) {
    return context -> {
        String kind = (String) context.getArgs()[0];
        CacheManager chosen = switch (kind) {
            case "local" -> localCacheManager;
            case "shared" -> remoteCacheManager;
            default -> throw new IllegalArgumentException(
                    "Unknown storage tier: " + kind);
        };
        Cache cache = chosen.getCache("lookup");
        if (cache == null) {
            throw new IllegalStateException("Cache lookup unavailable");
        }
        return List.of(cache);
    };
}
~~~

Đây là snippet tích hợp vào một cấu hình Spring có **hai bean cache manager đã được xác định rõ**; để inject chính xác trong ứng dụng có nhiều manager, dùng tên bean/`@Qualifier` phù hợp (hoặc chỉ định rõ parameter qualifier). Không phải file Java độc lập.

Lưu ý: dù cùng tên `"lookup"`, cache từ local và remote manager có **semantics khác nhau** (TTL, serialization, phân tán, eviction). Resolver cần bảo đảm loại dữ liệu và key tương thích với từng backend.

Nếu có yêu cầu rõ ràng cho một method cụ thể, cấu hình đơn giản hơn:

~~~java
@Cacheable(cacheNames = "lookup", cacheManager = "remoteCacheManager")
public String find(String id) {
    return service.load(id);
}
~~~

Snippet này chỉ minh họa. Dùng `cacheManager` khi cố định theo method; dùng `cacheResolver` khi lựa chọn **thay đổi theo lời gọi**.

## 10. Trả một hay nhiều cache?

`CacheResolver.resolveCaches` trả về `Collection<? extends Cache>`, vì một operation có thể liên quan nhiều cache. Nhưng không nên lợi dụng điều đó để “cache một cách bừa bãi”.

- Một cache: thường dễ suy luận hit/miss, TTL và invalidation nhất.
- Nhiều cache: cần hiểu trình tự tra và việc ghi/xóa đối với toàn bộ các cache, nhất là khi một bên đã có entry còn bên kia chưa có.
- `@Cacheable(sync = true)` có các hạn chế, trong đó operation đồng bộ không được xử lý đồng thời nhiều cache.
- Một số provider bất đồng bộ hoặc phân tán có chi tiết lookup khác; đừng xem nhiều cache là bảo đảm giao dịch nguyên tử hoặc cơ chế replica nhất quán.

Một resolver có thể chọn các cache từ nhiều manager, nhưng khả năng đọc/ghi ở các cache đó không mặc nhiên là một atomic transaction.

## 11. So sánh công cụ chọn vùng cache

| Nhu cầu | Nên dùng | Lý do |
| --- | --- | --- |
| Tất cả lời gọi dùng một cache cố định | `cacheNames = "products"` | Rõ ràng, ít code |
| Method A dùng Redis, method B dùng Caffeine, cố định | `cacheManager` trên từng method | Không cần routing runtime |
| Cache theo tham số `region` trong cùng method | Custom `CacheResolver` | Chọn theo invocation |
| Cache theo tenant từ security context | Custom `CacheResolver` hoặc cấu trúc key có namespace | Tùy yêu cầu cô lập |
| Chỉ thay đổi cách tạo entry key | `key` / `KeyGenerator` | Không cần đổi cache |
| Muốn đổi TTL theo region | Cấu hình provider/cache tương ứng | Resolver không phải TTL policy engine |
| Chỉ cache khi thỏa điều kiện | `condition` | Bypass logic, không phải chọn cache |

Ví dụ: `key = "#p1"` thay đổi **entry key**, còn `cacheResolver = "regionResolver"` thay đổi **cache object**. Hai lựa chọn có thể kết hợp trong cùng annotation vì giải quyết hai vấn đề khác nhau.

## 12. Lỗi thường gặp và cách debug

### Lỗi 1 — nhầm cacheName và key

Tạo key `"north:P1"` không tự khiến Spring chọn cache `prices-north`. Khi không có resolver tùy chỉnh, cache có thể vẫn là `prices`. Ngược lại, chọn cache `prices-north` mà quên key đúng cũng có thể tạo đụng entry giữa các method dùng cùng cache đó.

**Cách kiểm tra:** log một cách an toàn tên cache được resolver trả về và key thực sự được sử dụng, không log dữ liệu cá nhân/secret.

### Lỗi 2 — @Cacheable và @CacheEvict dùng resolver/key khác nhau

Getter chọn `profiles-a`, updater lại evict `profiles`; kết quả stale. Phải định nghĩa cùng chiến lược định tuyến, bao gồm cả đường cập nhật chạy từ job, event handler và admin API.

### Lỗi 3 — bean name không trùng

Annotation `@Cacheable(cacheResolver = "regionResolver")` yêu cầu đúng bean tên `regionResolver`. Tên class có thể khác. Nếu bean không tồn tại/không đúng kiểu, caching không hoạt động như mong đợi hoặc việc khởi tạo/invocation ném lỗi.

### Lỗi 4 — tự trả về null hoặc collection rỗng

Không nên dùng kết quả rỗng như “cache disabled”. Nếu muốn bỏ qua cache có điều kiện, có thể dùng `condition`; nếu không thể chọn cache, báo lỗi cấu hình hoặc ngữ cảnh rõ ràng.

### Lỗi 5 — lấy tenant từ ngữ cảnh không ổn định

Request HTTP chạy tenant a nhưng tác vụ `@Async` chạy thread khác không mang tenant context. Resolver có thể thiếu context hoặc chọn sai. Truyền context đúng cách, đừng mặc định ThreadLocal đi theo thread pool/reactive flow.

### Lỗi 6 — chọn cache theo dữ liệu không đáng tin

Nếu client tự gửi tenant ID mà không xác minh quyền truy cập, resolver chỉ tạo “khác tên cache” chứ không ngăn truy cập sai. Bảo mật phụ thuộc xác thực, phân quyền và kiểm tra sở hữu dữ liệu gốc.

### Lỗi 7 — self-invocation bỏ qua interceptor

Nếu một method trong class gọi `this.otherCachedMethod()`, proxy mode thường không xử lý annotation trên lời gọi nội bộ đó. Resolver cũng không được gọi. Cần thiết kế method boundary hoặc dùng proxy/aspect thích hợp.

### Lỗi 8 — giả định cache in-memory đồng bộ đa instance

`ConcurrentMapCacheManager` trong demo chỉ chia sẻ cache giữa các bean cùng JVM. Các instance khác nhau có cache khác nhau; cần backend chia sẻ hoặc giao thức invalidation nếu muốn nhất quán xuyên node.

### Checklist chẩn đoán

1. Có `@EnableCaching` và lời gọi đi qua Spring-managed proxy không?
2. Annotation có dùng đúng bean `cacheResolver` không? Có xung đột `cacheManager` không?
3. `context.getArgs()`/ngữ cảnh hiện tại có đúng và đã được xác thực/validate không?
4. Resolver trả về đúng tên cache, đúng manager, collection không trống và không chứa null không?
5. Biểu thức key có đúng với tham số của getter và updater không?
6. `@Cacheable` có `condition`/`unless` làm thay đổi việc cache không?
7. Có expiry, eviction, serialization hoặc backend khác nhau giữa các instance không?
8. Các job/async/transaction có dùng cùng quy tắc routing và thời điểm invalidation không?

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Với cùng key `"P1"`, phương thức `price("north","P1")` và `price("south","P1")` có lấy nhầm giá của nhau không nếu resolver trả hai cache khác nhau? **Không**, nếu mỗi cache là không gian entry riêng và cấu hình provider thực sự tách chúng.

**Câu 2.** Có phải bỏ `cacheNames` thì Spring không thể cache? **Không** khi custom `CacheResolver` được cấu hình đúng và trả về cache phù hợp.

**Câu 3.** Một updater nhận `(region, sku, newPrice)` phải xóa entry getter nhận `(region, sku)` như thế nào? **Chọn cùng cache theo region và dùng cùng key theo sku**, ví dụ cả hai `key = "#p1"`.

**Câu 4.** Có thể khai báo đồng thời `cacheManager` và `cacheResolver` trên một `@Cacheable` không? **Không**; đây là hai cơ chế thay thế nhau để chọn cách phân giải cache.

**Câu 5.** Resolver dùng tenant từ `ThreadLocal` có an toàn với `@Async`/reactive không? **Không mặc định**. Cần cơ chế truyền context đúng với mô hình thực thi, đồng thời phải xác thực nguồn tenant.

**Câu 6.** Chuyển từ cache local sang Redis có thể làm bằng cách sửa mỗi resolver mà không cần kiểm thử gì? **Không**. Vẫn phải đánh giá TTL, key serialization, độ trễ, error handling, memory/connection, multi-node invalidation và consistency.

## Kết luận

`CacheResolver` cung cấp một “bộ định tuyến” cache cho từng lời gọi: **dựa vào đối số hoặc ngữ cảnh → chọn một hay nhiều Cache → Spring áp dụng hit/miss/put/evict với key tương ứng**. Nếu cache cần cố định, chọn `cacheNames` hoặc `cacheManager` để giữ cấu hình đơn giản. Nếu cache phải thay đổi theo runtime, resolver nên có quy tắc rõ ràng, nhanh, xác định, kiểm soát đầu vào và dùng nhất quán giữa các đường đọc–ghi–xóa. Trong ứng dụng nhiều tenant, đây còn là vấn đề cô lập dữ liệu và bảo mật, không chỉ là tối ưu cache.

## Tài liệu chính thức

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Caching / Custom Cache Resolution: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Javadoc `CacheResolver`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/cache/interceptor/CacheResolver.html
- Javadoc `CacheOperationInvocationContext`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/cache/interceptor/CacheOperationInvocationContext.html
- Javadoc `CacheManager`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/cache/CacheManager.html
