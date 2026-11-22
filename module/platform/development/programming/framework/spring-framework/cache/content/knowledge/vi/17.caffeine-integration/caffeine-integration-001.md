# CaffeineCache và CaffeineCacheManager trong Spring Framework Cache

## 1. Tổng quan: Caffeine nằm ở đâu trong Spring Cache?

Spring Cache là **lớp trừu tượng hóa** để ứng dụng khai báo hoặc gọi các thao tác đọc/ghi cache mà không gắn chặt vào một thư viện lưu trữ. Caffeine là một thư viện **in-memory caching hiệu năng cao dành cho Java**; Spring có adapter đưa Caffeine vào hợp đồng `org.springframework.cache.Cache`.

Hai lớp cốt lõi:

- `org.springframework.cache.caffeine.CaffeineCache`: **adapter của một vùng cache**; triển khai giao diện `org.springframework.cache.Cache` và bọc một native `com.github.benmanes.caffeine.cache.Cache` (hoặc `AsyncCache` theo cấu hình). Nó trả lời cho một cache name cụ thể, ví dụ `products`.
- `org.springframework.cache.caffeine.CaffeineCacheManager`: **bộ quản lý nhiều vùng cache**; triển khai `CacheManager`, tạo/tìm các đối tượng `CaffeineCache` theo tên và áp dụng cấu hình Caffeine dùng chung.

Hãy xem sơ đồ:

```text
Controller / caller
       |
       v
Spring proxy / CacheInterceptor (khi dùng annotation)
       |
       v
CacheManager.getCache("products")
       |
       v
CaffeineCacheManager -------------------> Quản lý cache names
       |
       v
CaffeineCache(name="products") ----------> Adapter Spring Cache
       |
       v
Native Caffeine Cache<Object, Object> --> Lưu key/value trong JVM
```

**Phân biệt vai trò:** `CacheManager` là nơi **chọn vùng**, `Cache` là nơi **thao tác entry**. Annotation `@Cacheable` dùng abstraction của Spring; bản thân Caffeine không hiểu annotation nếu không có cơ chế Spring Cache được bật.

Caffeine là **local cache**: các instance JVM độc lập thường có bộ nhớ cache độc lập. Nó không tự tạo Redis, cache phân tán, replication hay khóa toàn cluster. Bài này đi từ dependency, cấu hình, các API, lifecycle đến ví dụ chạy được và những giới hạn triển khai.

## 2. Dependency bắt buộc và điều kiện chạy

Với ứng dụng Spring Framework thuần Java, cần cả **Spring context** và **thư viện Caffeine**; chỉ thêm `spring-context` không cung cấp native Caffeine engine.

Ví dụ Maven (JDK 17+):

```xml
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
```

Hai phiên bản trên là một bộ phiên bản **minh họa** có thật. Spring Framework 6.1+ cần Caffeine 3.0 trở lên cho adapter hiện đại. Khi sử dụng Spring Boot, ưu tiên phiên bản dependency do BOM của Boot quản lý nếu có, thay vì cố ghim số phiên bản không tương thích.

Để annotation có tác dụng:

1. Tạo bean `CacheManager`, ví dụ `CaffeineCacheManager`.
2. Bật `@EnableCaching` ở một class `@Configuration`.
3. Đặt `@Cacheable`, `@CachePut` hoặc `@CacheEvict` lên method thích hợp.
4. Gọi method qua **Spring-managed bean/proxy**. Trong proxy mode mặc định, gọi nội bộ `this.find(...)` thường không đi qua caching advice.

Nếu chỉ dùng API `CacheManager.getCache(...)` và `Cache.put(...)` trực tiếp, không nhất thiết phải dùng `@EnableCaching`; đó là cách dùng programmatic.

## 3. CaffeineCache: một adapter cho từng cache name

`CaffeineCache` triển khai `org.springframework.cache.Cache` và chuyển tiếp các thao tác vào vùng Caffeine native tương ứng.

Các API thường sử dụng:

| API Spring `Cache` | Ý nghĩa |
| --- | --- |
| `getName()` | Tên vùng cache, ví dụ `products` |
| `get(key)` | Trả `Cache.ValueWrapper` nếu có entry, hoặc null wrapper khi cache miss |
| `get(key, Product.class)` | Lấy value với kiểu kỳ vọng; không phân biệt được miss và cached-null chỉ từ kết quả null |
| `get(key, Callable<T>)` | Lấy hoặc tải giá trị bằng callback khi key vắng |
| `put(key, value)` | Ghi mới hoặc thay value của key |
| `putIfAbsent(key, value)` | Chèn khi chưa có mapping; trả wrapper của entry có sẵn |
| `evict(key)` | Xóa entry theo key |
| `clear()` | Xóa các entry của vùng |
| `getNativeCache()` | Lấy native Caffeine Cache để truy cập tính năng đặc thù của Caffeine |

Ví dụ làm việc với bean `CacheManager manager` đã có:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.caffeine.CaffeineCache;

Cache cache = manager.getCache("products");
if (!(cache instanceof CaffeineCache caffeineCache)) {
    throw new IllegalStateException("Expected a Caffeine-backed cache");
}
cache.put("P1", "Bút");
System.out.println(cache.get("P1", String.class)); // Bút
System.out.println(caffeineCache.getName());       // products

// API Caffeine gốc, chỉ dùng khi cần khả năng riêng của provider:
var nativeCache = caffeineCache.getNativeCache();
```

Đây là **mảnh minh họa** (đã có `manager`), không phải chương trình độc lập. Cách cast cần guard vì `CacheManager` khác có thể trả adapter Redis, JCache, ConcurrentMap hoặc một decorator.

`CaffeineCache.getNativeCache()` cho phép đo kích thước ước lượng, xem stats (nếu bật), lấy `asMap()`, v.v. Nhưng thao tác trực tiếp trên native cache **đi vòng abstraction Spring**, nên có thể bỏ qua conversion cho `null`, decorators và các chính sách ở tầng Spring. Khi cần read/write nghiệp vụ, ưu tiên `Cache` abstraction; chỉ dùng native API cho cấu hình/quan sát có chủ đích.

### 3.1. Cache miss khác với stored null

`cache.get(key) == null` nghĩa là không có `Cache.ValueWrapper` — key chưa được ánh xạ. Ngược lại, `wrapper != null && wrapper.get() == null` biểu thị có entry lưu null, **nếu cấu hình cho phép**.

Native Caffeine thông thường không nhận null value; Spring có thể chuyển null sang sentinel nội bộ khi `allowNullValues=true`. Vì vậy native map có thể chứa representation không giống đối tượng Java null. Không đọc trực tiếp native rồi suy luận đó là toàn bộ hành vi null của Spring.

Trong ví dụ thực hành bên dưới, `setAllowNullValues(false)` đi cùng `unless="#result == null"` để không yêu cầu cache lưu kết quả null.

## 4. CaffeineCacheManager: tạo và chọn các vùng cache

### 4.1. Chế độ dynamic: tự tạo cache cho tên được hỏi

```java
CaffeineCacheManager manager = new CaffeineCacheManager();
var cache = manager.getCache("products");
```

Constructor không tham số dùng **dynamic mode**: mỗi tên chưa biết có thể được tạo cache một cách lười (lazily). `getCache("products")` tạo vùng cần thiết ở lần dùng đầu; lần sau tìm cùng tên sẽ dùng vùng tương ứng của manager.

Ưu điểm là không phải khai báo mọi tên trước; nhược điểm là typo trong `cacheNames` như `prodcuts` cũng có thể âm thầm tạo một vùng mới thay vì báo sai.

Một manager dynamic đặt trước các manager khác trong `CompositeCacheManager` có thể nhận mọi tên cache và ngăn cơ chế tìm kiếm đi tới delegate đứng sau. Khi cần phân chia backend rõ ràng, hãy cân nhắc static mode.

### 4.2. Chế độ static: chỉ chấp nhận các tên đã biết

```java
CaffeineCacheManager manager =
        new CaffeineCacheManager("products", "productLabels");

System.out.println(manager.getCache("products") != null); // true
System.out.println(manager.getCache("unknown") != null);  // false
```

Constructor có danh sách tên cache tạo manager ở **static mode**. Có thể thay đổi tập tên bằng `setCacheNames(Collection<String>)`. Với static mode, manager không tự tạo vùng mới cho tên lạ; `getCache(name)` trả null nếu không có vùng được chấp nhận.

Cần lưu ý `setCacheNames(...)` có thể thay thế cache đã tạo cho các tên đã nêu; nó không phải thao tác chỉ đổi một danh sách metadata vô hại. Tốt nhất cấu hình tên và policy **trước khi ứng dụng bắt đầu nhận request**. Muốn quay về dynamic mode, API chấp nhận collection null.

### 4.3. Cấu hình chung cho những vùng do manager tạo

```java
CaffeineCacheManager manager =
        new CaffeineCacheManager("products", "productLabels");

manager.setCaffeine(
        com.github.benmanes.caffeine.cache.Caffeine.newBuilder()
            .maximumSize(500)
            .expireAfterWrite(java.time.Duration.ofMinutes(10))
            .recordStats()
);
manager.setAllowNullValues(false);
```

`setCaffeine(...)` nhận Caffeine builder, áp dụng cấu hình chung cho các vùng do manager tạo. Có thể truyền cấu hình dạng spec qua `setCaffeineSpec(...)` hoặc chuỗi thông qua `setCacheSpecification(...)`:

```java
manager.setCacheSpecification(
        "maximumSize=500,expireAfterWrite=10m,recordStats");
```

Đây là **hai lựa chọn thay thế**, không cần gọi cả `setCaffeine(...)` và `setCacheSpecification(...)` cho cùng manager. Lựa chọn builder phù hợp khi cần type-safe và khả năng tùy biến nâng cao; spec thuận tiện cho cấu hình chuỗi.

**Quan trọng:** TTL và giới hạn số entry là chính sách của native Caffeine cache. `@Cacheable` không tự có thuộc tính TTL dùng chung độc lập với provider.

## 5. Những chính sách cache thường dùng

### 5.1. Giới hạn kích thước

```java
Caffeine.newBuilder().maximumSize(500)
```

Caffeine dùng cơ chế eviction theo policy của thư viện nhằm giữ khoảng tối đa số entry được cấu hình. Đây **không** phải ràng buộc nghiệp vụ bảo đảm lúc nào cũng đúng chính xác 500 entry ở mọi thời điểm; một số thao tác bảo trì/eviction có thể được thực hiện theo cơ chế nội bộ của provider.

Nếu dữ liệu có kích thước rất khác nhau, cân nhắc `maximumWeight(...)` và `weigher(...)` của Caffeine thay vì coi mỗi entry đều có chi phí như nhau. Không sử dụng đồng thời `maximumSize` với `maximumWeight` trên cùng builder.

### 5.2. Expire-after-write và expire-after-access

- `expireAfterWrite(Duration)`: hết hạn theo thời gian tính từ lần tạo/thay value; **đọc** không làm mới đồng hồ expire-after-write.
- `expireAfterAccess(Duration)`: hết hạn khi key không được đọc/ghi trong một khoảng thời gian; truy cập thường xuyên có thể giữ entry tồn tại lâu hơn.
- `refreshAfterWrite(Duration)` là cơ chế **refresh** dành cho loading cache và có ngữ nghĩa khác expiration; cần có loader và phải kiểm tra cách phục vụ value cũ trong lúc refresh. Không xem refresh như đồng nghĩa với evict ngay tại hạn.

Ví dụ dùng expire-after-write:

```java
var policy = Caffeine.newBuilder()
        .maximumSize(500)
        .expireAfterWrite(java.time.Duration.ofMinutes(10));
```

Đây là một **mảnh minh họa** cần import `com.github.benmanes.caffeine.cache.Caffeine`. Sau khi hết hạn, lần đọc tiếp theo thường không thấy entry hợp lệ và có thể phải nạp lại. Spring/Caffeine không tự cập nhật dữ liệu gốc nếu method chưa được gọi hoặc không có cơ chế refresh/loader riêng.

### 5.3. Thống kê

`recordStats()` bật ghi nhận số liệu như hit, miss, load, eviction trên native cache. Khi thống kê được bật:

```java
CaffeineCache springCache =
        (CaffeineCache) manager.getCache("products");

var stats = springCache.getNativeCache().stats();
System.out.println(stats.hitCount());
System.out.println(stats.missCount());
```

Các dòng ở trên chỉ minh họa và **không có stdout cố định**: số liệu phụ thuộc vào lượt gọi đã diễn ra. Stats ở đây là native provider metrics; khi dùng Micrometer/Spring Boot Actuator cần cấu hình cơ chế bind/quan sát phù hợp, không coi `recordStats()` là bước xuất metrics lên server tự động.

### 5.4. Thời điểm thực thi eviction

Caffeine có thể tiến hành maintenance trong quá trình truy cập/ghi và có thể cần cleanup để thống kê/size phản ánh trạng thái vừa hết hạn. Native `estimatedSize()` là **ước lượng**, không phải số lượng entry còn hợp lệ được đồng bộ tức thời qua mọi thời điểm.

Đừng viết test phụ thuộc vào việc `estimatedSize()` giảm đúng một đơn vị ngay sau một khoảng `sleep` cố định. Thay vào đó, test hành vi `get` sau expiry bằng nguồn thời gian có kiểm soát, hoặc dùng chính API test của provider.

## 6. Ví dụ chạy được: Spring Framework 6.2.9 + Caffeine 3.1.8

Chương trình Java 17 sau dùng cấu hình Spring thuần và `CaffeineCacheManager`. Nó minh họa:

1. Hai lượt đọc sản phẩm `P1`: một cache miss và một cache hit.
2. `@CachePut` cập nhật giá trị trong vùng `products`, không bắt buộc nạp lại lần nữa.
3. `@CacheEvict` loại bỏ entry khi sản phẩm bị xóa.
4. `unless="#result == null"` tránh lưu cache một kết quả không tìm thấy, để lần truy vấn kế tiếp vẫn đọc nguồn.
5. Static manager chỉ có vùng `products`; một tên không khai báo không được tự tạo.

**Cấu trúc dự án:**

```text
caffeine-spring-demo/
├── pom.xml
└── src/main/java/CaffeineCacheDemo.java
```

**Nội dung `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>caffeine-spring-demo</artifactId>
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

**Nội dung `src/main/java/CaffeineCacheDemo.java`:**

```java
import java.time.Duration;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.Cache;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CaffeineCacheDemo {

    @Bean
    CaffeineCacheManager cacheManager() {
        var manager = new CaffeineCacheManager("products");
        manager.setAllowNullValues(false);
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(100)
                .expireAfterWrite(Duration.ofMinutes(10))
                .recordStats());
        return manager;
    }

    @Bean
    ProductRepository productRepository() {
        return new ProductRepository();
    }

    @Bean
    ProductService productService(ProductRepository repository) {
        return new ProductService(repository);
    }

    public record Product(String id, String name) {}

    public static class ProductRepository {
        private final Map<String, Product> data = new ConcurrentHashMap<>();
        private final AtomicInteger reads = new AtomicInteger();

        public ProductRepository() {
            data.put("P1", new Product("P1", "Bút"));
        }

        public Product find(String id) {
            reads.incrementAndGet();
            return data.get(id);
        }

        public Product save(Product product) {
            data.put(product.id(), product);
            return product;
        }

        public void delete(String id) {
            data.remove(id);
        }

        public int reads() {
            return reads.get();
        }
    }

    public static class ProductService {
        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @Cacheable(
            cacheNames = "products",
            key = "#p0",
            unless = "#result == null"
        )
        public Product find(String id) {
            return repository.find(id);
        }

        @CachePut(cacheNames = "products", key = "#p0.id()")
        public Product update(Product product) {
            return repository.save(product);
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void delete(String id) {
            repository.delete(id);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(CaffeineCacheDemo.class)) {

            ProductService service = context.getBean(ProductService.class);
            ProductRepository repository =
                    context.getBean(ProductRepository.class);
            CaffeineCacheManager manager =
                    context.getBean(CaffeineCacheManager.class);

            System.out.println("first: " + service.find("P1"));
            System.out.println("second: " + service.find("P1"));
            System.out.println("reads after repeat: " + repository.reads());

            service.update(new Product("P1", "Bút xanh"));
            System.out.println("after update: " + service.find("P1"));
            System.out.println("reads after update: " + repository.reads());

            service.delete("P1");
            System.out.println("after delete #1: " + service.find("P1"));
            System.out.println("after delete #2: " + service.find("P1"));
            System.out.println("reads final: " + repository.reads());

            Cache selected = Objects.requireNonNull(
                    manager.getCache("products"));
            System.out.println("Spring Caffeine adapter: "
                    + (selected instanceof CaffeineCache));
            System.out.println("unknown cache available: "
                    + (manager.getCache("missing") != null));
        }
    }
}
```

**Chạy từ thư mục có `pom.xml`:**

```bash
mvn -q compile exec:java -Dexec.mainClass=CaffeineCacheDemo
```

**Các dòng do chương trình in ra** (không tính log Maven/Spring phụ thuộc môi trường):

```text
first: Product[id=P1, name=Bút]
second: Product[id=P1, name=Bút]
reads after repeat: 1
after update: Product[id=P1, name=Bút xanh]
reads after update: 1
after delete #1: null
after delete #2: null
reads final: 3
Spring Caffeine adapter: true
unknown cache available: false
```

### 6.1. Giải thích readback theo từng bước

- `find("P1")` lần đầu miss, gọi repository một lần và lưu value `Product(P1,"Bút")`.
- Lần thứ hai có key giống hệt, hit cache, repository chưa bị gọi lại: `reads = 1`.
- `update(Product("P1","Bút xanh"))` chạy method thật rồi `@CachePut` ghi bản mới vào `products/P1`. `find("P1")` tiếp theo hit bản mới, số lần đọc nguồn vẫn bằng 1.
- `delete("P1")` xóa dữ liệu nguồn và `@CacheEvict` xóa entry `products/P1`. Lần tìm sau miss rồi trả null; `unless` không lưu null. Lần tìm tiếp theo lại miss nên số lần đọc nguồn tăng từ 1 lên 3.
- `manager.getCache("products")` trả `CaffeineCache` adapter. `manager.getCache("missing")` trả null do manager được khởi tạo với tên tĩnh duy nhất `products`.

**Lưu ý:** đây là demo một JVM, in bộ đếm call nguồn và dùng TTL 10 phút nên các bước chạy ngay không có expiry. Không kết luận rằng Caffeine đảm bảo đồng bộ cache qua nhiều process hoặc database transaction nguyên tử.

## 7. CaffeineCacheManager và nhiều policy khác nhau giữa các vùng

`setCaffeine(...)` và `setCacheSpecification(...)` đặt một cấu hình **chung** cho những cache được manager tạo. Nhưng một ứng dụng có thể muốn:

- `products`: maximumSize 1.000, expireAfterWrite 30 phút.
- `labels`: maximumSize 5.000, expireAfterAccess 5 phút.
- `pricing`: thời gian sống ngắn vì giá thay đổi nhanh.

Khi từng vùng cần native builder riêng, Spring hỗ trợ `registerCustomCache(name, nativeCache)`:

```java
CaffeineCacheManager manager = new CaffeineCacheManager("products");

manager.setCaffeine(Caffeine.newBuilder()
        .maximumSize(1_000)
        .expireAfterWrite(Duration.ofMinutes(30)));

manager.registerCustomCache(
        "labels",
        Caffeine.newBuilder()
            .maximumSize(5_000)
            .expireAfterAccess(Duration.ofMinutes(5))
            .build()
);
```

Đây là đoạn cấu hình độc lập minh họa; cần import `Caffeine`, `Duration` và `CaffeineCacheManager`. Một custom native cache được bọc thành adapter và được quản lý bằng tên đã đăng ký; các vùng khác vẫn dùng cấu hình chung của manager. Khi dùng async native cache, API cũng có overload `registerCustomCache(String, AsyncCache<Object,Object>)`.

**Quan trọng:** đăng ký custom cache phải được thực hiện ở giai đoạn cấu hình, không thay cache đang có tùy tiện trong khi request đang truy cập. Từng cache có policy, entry và stats riêng; `CacheManager` không biến mọi cache cùng tên thành một kho lưu trữ thống nhất giữa nhiều manager.

### 7.1. Đổi policy có tác dụng ngay với entry hiện hữu không?

Hãy xem thay đổi builder/spec của manager như **thay đổi cách xây các native cache**, không phải một giao dịch thay đổi TTL/size của tất cả entry hiện hữu ngay lập tức. Tùy API setter và trạng thái manager, cache có thể được tái tạo/reset, làm mất entry đang lưu.

Vì vậy cấu hình policy trước khi đưa ứng dụng vào phục vụ. Nếu bắt buộc thay đổi runtime, dùng cơ chế chính thức của manager/provider, nắm rõ tác động tới entry, và kiểm thử hành vi dưới lưu lượng thật. Đừng tự suy luận `setCaffeine` chỉ chỉnh một field của cache đang chạy.

## 8. Xử lý null và giới hạn khi dùng Caffeine

Native Caffeine `Cache` không lưu Java null làm value như một entry thông thường. Nhưng adapter Spring có cơ chế **null-value adaptation**. `CaffeineCacheManager` expose:

```java
manager.setAllowNullValues(true);  // Có thể biểu diễn null qua sentinel.
manager.setAllowNullValues(false); // Không chấp nhận cache null.
```

Khi `allowNullValues=true`, Spring có thể chuyển Java null thành sentinel để native store chấp nhận; khi đọc qua Spring `Cache`, conversion trả về null cho caller. Native `getIfPresent` không nên được dùng để kết luận có/không có Java null mà không hiểu adapter.

Khi `allowNullValues=false`, một đường caching cố gắng put null có thể gây lỗi. Nếu mục tiêu là **bỏ cache kết quả chưa tìm thấy**, dùng điều kiện dựa vào kết quả như:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    unless = "#result == null"
)
public Product find(String id) {
    return repository.find(id);
}
```

Đoạn này minh họa service có repository. `unless` được đánh giá sau khi method thật trả về và từ chối cache null. Với `Optional.empty()`, Spring Cache có ngữ nghĩa unwrap đối với `Optional` được hỗ trợ; cần kiểm thử null behavior của provider và return type thật.

**Không kết hợp `sync=true` với `unless`:** Spring `@Cacheable(sync=true)` không hỗ trợ `unless`. Nếu muốn single-flight và không cache null đồng thời, cần thiết kế giá trị/cache provider hoặc cơ chế nạp riêng, không lắp ghép hai annotation options không tương thích.

## 9. Loading, đồng thời và `@Cacheable(sync=true)`

`CaffeineCache` hỗ trợ đường `Cache.get(key, Callable)` dùng callback nạp dữ liệu. Native Caffeine có cơ chế tính giá trị kiểu compute-if-absent, giúp giảm tải trùng khi nhiều thread trong cùng JVM cùng yêu cầu key chưa có.

Ví dụ:

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String id) {
    return repository.find(id);
}
```

Đây là đoạn minh họa **thay thế** `find` của chương trình mục 6, không thể chép kèm `unless` lên cùng method.

Những điểm phải phân biệt:

- `sync=true` chuyển yêu cầu nạp theo một contract của cache provider; không tự tạo distributed mutex giữa mọi JVM.
- Caffeine in-memory thường chỉ đồng bộ hóa trong native cache instance của tiến trình hiện tại.
- Hai app instance có hai Caffeine cache khác nhau vẫn có thể cùng truy cập nguồn, vì chúng không chia sẻ vùng lưu.
- `sync=true` không giải quyết race khi một thread tải dữ liệu cũ còn thread khác update DB và evict cache.
- Chọn key phải chứa mọi yếu tố quyết định kết quả; thiếu tenant/locale/currency có thể gây chia sẻ kết quả sai.

Nếu thực sự cần cache L1 local + L2 remote, không thể chỉ đặt `CaffeineCacheManager` cạnh một manager Redis rồi mong Caffeine tự fallback theo key. Cần provider đa tầng hay composite `Cache` implementation có chiến lược nạp, cập nhật và invalidation riêng.

## 10. Async CaffeineCache và Spring Framework 6.1+

Spring Framework 6.1+ hỗ trợ kiểu cache abstraction bất đồng bộ. `CaffeineCacheManager` có:

```java
manager.setAsyncCacheMode(true);
```

Khi bật async mode, các cache mới được xây trên `AsyncCache` của Caffeine; adapter Spring có thể hỗ trợ `Cache.retrieve(key)` và `Cache.retrieve(key, supplier)` trả `CompletableFuture`. `CaffeineCache` expose `getAsyncCache()` khi native async cache sẵn có.

Những điểm cần chú ý:

1. Chỉ gọi `getAsyncCache()` khi thực sự có native `AsyncCache`, nếu không có thể nhận `IllegalStateException`.
2. Cấu hình null cho async được Javadoc Spring khuyến nghị **tắt** qua `setAllowNullValues(false)` để semantics `CompletableFuture` đơn giản và tránh wrapping thừa.
3. `setAsyncCacheMode(true)` điều khiển các cache do manager tạo; custom cache đã đăng ký có kiểu riêng và không tự chuyển sync ↔ async chỉ nhờ flag này.
4. `setAsyncCacheLoader(...)` có thể dựng loading cache bất đồng bộ, nhưng loader dùng chung cho các vùng phải có hợp đồng key/value phù hợp.
5. Method trả `CompletableFuture<T>` hoặc Reactor type cần được test bằng provider đúng; không suy ra hiệu lực chỉ từ việc `@Cacheable` đồng bộ chạy đúng.

Một chữ ký minh họa của service đã có repository:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public java.util.concurrent.CompletableFuture<Product> findAsync(String id) {
    return java.util.concurrent.CompletableFuture.supplyAsync(
            () -> repository.find(id));
}
```

Đoạn này **không thuộc** chương trình `CaffeineCacheDemo.java` độc lập. Caching async cần chính sách executor, timeout và failure handling; Caffeine Cache không thay thế toàn bộ orchestration bất đồng bộ.

## 11. Dùng Caffeine với Spring Boot

Khi ứng dụng dùng Spring Boot có `spring-boot-starter-cache` và dependency Caffeine phù hợp, Boot có thể auto-configure `CaffeineCacheManager` theo tình trạng các provider khác. Ví dụ cấu hình:

```properties
spring.cache.type=caffeine
spring.cache.cache-names=products,productLabels
spring.cache.caffeine.spec=maximumSize=500,expireAfterWrite=10m,recordStats
```

Cú pháp trên là **một phương án cho Boot**, không phải property tự động được Spring Framework thuần `AnnotationConfigApplicationContext` đọc. Boot cho phép cấu hình spec và/hoặc bean `CaffeineSpec`/`Caffeine` theo quy tắc ưu tiên của auto-configuration; cần đọc tài liệu phiên bản Boot đang dùng. Khi có custom `CacheManager` bean do ứng dụng cung cấp, auto-configuration có thể lùi lại.

Vẫn cần bật caching advice, thông thường bằng `@EnableCaching` trong cấu hình Spring. `@Cacheable(cacheNames="products")` chỉ dùng được khi ứng dụng có manager/resolver phù hợp, và không thể tự đặt TTL bằng thuộc tính annotation.

Đặt `spring.cache.type=caffeine` có ích khi nhiều provider cùng nằm trên classpath, nhưng không thể thay thế việc kiểm thử tên vùng, keys, bean thực tế được chọn và hiệu lực của annotation.

## 12. Caffeine local cache trong môi trường production

### 12.1. Lợi ích

- Truy cập rất nhanh trong cùng JVM, không cần network round trip cho cache hit.
- Có policy size/weight, expire, refresh và stats mạnh của Caffeine.
- Thích hợp cache dữ liệu tham chiếu, cấu hình ít thay đổi, kết quả tính toán, DTO đã được kiểm soát về kích thước.
- Tích hợp tự nhiên với `@Cacheable`/`@CachePut`/`@CacheEvict` của Spring.

### 12.2. Hạn chế

- Mỗi JVM có nội dung độc lập; khi scale từ một instance lên nhiều instance, một thay đổi ở node A không tự evict dữ liệu trên node B.
- Cache mất khi restart process; không phải lưu trữ bền vững hay source of truth.
- Chọn `maximumSize`/TTL không đúng có thể làm memory pressure hoặc cache miss quá nhiều.
- Cache mutable object có thể bị sửa ngoài ý muốn nếu giữ cùng tham chiếu trong JVM. Caffeine không tự deep-copy object cho bạn.
- Đặt key chung cho các tenant/quyền/locale khác nhau gây chia sẻ dữ liệu sai, kể cả khi provider chạy đúng kỹ thuật.
- Write vào cache chưa chắc trùng thời điểm transaction database commit. Annotation cache không mặc nhiên cung cấp transaction atomicity.

Một mô hình triển khai nhiều node cần quyết định rõ: dùng local cache với TTL ngắn và chấp nhận nhất quán cuối cùng, phát sự kiện invalidation đến các node, dùng cache phân tán, hoặc thiết kế multi-tier có contract riêng.

### 12.3. Thông số nên quan sát

- Tỷ lệ hit/miss, số lần load nguồn, số entry bị evict, thời gian loader.
- Dung lượng cache và mức chiếm heap; không đồng nhất `estimatedSize()` với bộ nhớ JVM thực tế.
- TTL/refresh có phù hợp tần suất thay đổi dữ liệu hay không.
- Độ trễ phục vụ cache hit, cache miss và tác động khi traffic tăng đột ngột.
- Khả năng invalidation sau update/delete giữa các node, kể cả khi rollback hoặc message bị trễ.

Tránh log key chứa dữ liệu cá nhân hoặc tạo metric tag theo từng key vì nguy cơ lộ thông tin và cardinality cao.

## 13. Lỗi thường gặp và cách sửa

1. **Chỉ thêm `spring-context` mà quên thư viện Caffeine.** Khi cần `CaffeineCacheManager` phải có dependency `com.github.ben-manes.caffeine:caffeine` và phiên bản tương thích.
2. **Nhầm `CaffeineCacheManager` là một vùng cache.** Manager tìm/tạo nhiều vùng; `CaffeineCache` đại diện một vùng theo tên.
3. **Quên `@EnableCaching`.** Annotation trong code không có caching advice nếu infrastructure chưa bật.
4. **Self-invocation hoặc tự tạo service bằng `new`.** Proxy không intercept lời gọi nội bộ trong proxy mode mặc định.
5. **Dùng dynamic mode rồi viết sai tên cache.** `getCache("prodcuts")` có thể tạo vùng mới và che giấu lỗi cấu hình.
6. **Dùng static mode nhưng annotation yêu cầu tên lạ.** `getCache(name)` trả null; operation không thể resolve vùng đúng.
7. **Mong cache local tự đồng bộ nhiều JVM.** Mỗi node có cache riêng trừ khi có cơ chế đồng bộ riêng.
8. **Tưởng expireAfterWrite nghĩa là “tự refresh”.** Expiry làm entry không còn hợp lệ; nạp lại cần request/loader.
9. **Đọc native cache và bỏ qua null adapter.** Spring sentinel có thể không giống dữ liệu app mong đợi.
10. **Bật `allowNullValues(false)` nhưng để method trả null và cache như thường.** Có thể ném lỗi nếu vẫn thực hiện put; dùng `unless` nếu thích hợp.
11. **Kết hợp `sync=true` với `unless`.** Cấu hình không được Spring hỗ trợ trên cùng operation.
12. **Bật `recordStats()` rồi mong metrics tự xuất ra hệ thống.** Cần tích hợp quan sát như Micrometer/Actuator.
13. **Trộn giá trị không cùng kiểu vào một vùng/key.** Một method có thể trả `Product`, method khác trả `String` cùng key, gây lỗi cast hoặc kết quả sai.
14. **Đổi builder/TTL giữa lúc có traffic và mong mọi entry giữ nguyên.** Manager có thể tái tạo vùng; cần kiểm soát thay đổi.
15. **Bỏ qua transaction/invalidation.** `@CachePut`, `@CacheEvict` phải sử dụng key nhất quán và thời điểm phù hợp với database.
16. **Cho rằng async mode luôn được bật mặc định.** Cần `setAsyncCacheMode(true)` hoặc native AsyncCache phù hợp để dùng `retrieve`; kiểm thử riêng đường async.

## 14. Checklist trước khi triển khai

| Cần kiểm tra | Câu hỏi nghiệm thu |
| --- | --- |
| Dependencies | Có Spring Cache API, Caffeine 3.x và JDK phù hợp không? |
| Mode | Manager static hay dynamic? Có tên nào bị typo? |
| Region mapping | Mỗi operation dùng cacheNames và manager/resolver nào? |
| Policy | Có maximumSize/maximumWeight, expiry/refresh, stats đúng nhu cầu? |
| Key | Có phân biệt tenant, currency, locale, quyền và filter ảnh hưởng kết quả? |
| Null | Có cho phép cache null hay loại trừ bằng `unless`? |
| Concurrency | Nhiều thread cùng key và nhiều node có được test riêng? |
| Async | Có dùng `AsyncCache`, `retrieve` đúng provider/mode? |
| Invalidation | Update/delete xóa đúng entry ở mọi nơi phải đồng bộ? |
| Observability | Có đo hit/miss, load, eviction và chi phí heap? |
| Production | TTL và max size có được load-test trên dữ liệu thật? |

Để tự kiểm tra nhanh, thử bốn tình huống:

1. Gọi `find("P1")` hai lần: lần thứ hai có hit cache không?
2. Sau `update(P1)`: entry được put mới hay vẫn stale?
3. Sau `delete(P1)`: entry có bị evict? Các lần đọc null có bị cache lại không?
4. Khi thêm một instance JVM: cache node mới có tự biết dữ liệu node cũ không? Nếu không, yêu cầu consistency đã được đáp ứng bằng cơ chế nào?

**Kết luận:** `CaffeineCacheManager` chịu trách nhiệm quản lý vùng; `CaffeineCache` là lớp cầu nối giữa Spring Cache abstraction và native Caffeine. Chọn đúng vùng, key, null policy, expiry/size và chiến lược invalidation quan trọng hơn việc chỉ thêm dependency và bật cache annotation.

## Tài liệu chính thức

- Spring Framework 6.2.9 — `CaffeineCacheManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework 6.2.9 — `CaffeineCache` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/caffeine/CaffeineCache.html
- Spring Framework — Cache Store Configuration: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — Cache Annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching, Caffeine section: https://docs.spring.io/spring-boot/reference/io/caching.html
- Caffeine project: https://github.com/ben-manes/caffeine
