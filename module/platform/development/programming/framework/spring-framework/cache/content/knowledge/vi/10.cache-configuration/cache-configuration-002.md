# `@CacheConfig` không tự kích hoạt thao tác cache

## 1. Ý chính: cấu hình mặc định khác với hành động cache

Trong Spring Framework, `@CacheConfig` là annotation đặt **ở cấp lớp** để khai báo những giá trị cấu hình dùng chung cho **các cache operation đã được khai báo** trong lớp đó. Bản thân `@CacheConfig` **không** biến mọi phương thức trong lớp thành phương thức có cache, không tự tạo thao tác đọc/ghi/xóa cache và cũng không tự bật cache interception của Spring.

Ví dụ dễ nhầm:

```java
@Service
@CacheConfig(cacheNames = "products")
public class ProductService {
    public String findProduct(String id) {
        System.out.println("QUERY DB");
        return repository.findTitle(id);
    }
}
```

*Đây là đoạn minh họa, `repository` chưa được định nghĩa; ví dụ đầy đủ chạy được ở mục 6.*

Nếu gọi `findProduct("P1")` nhiều lần, **thân phương thức vẫn chạy ở mỗi lần**, dù lớp đã có `@CacheConfig(cacheNames = "products")`. Lý do: Spring chưa được yêu cầu áp dụng thao tác `@Cacheable`, `@CachePut` hoặc `@CacheEvict` cho phương thức đó.

Muốn cache kết quả tìm kiếm, cần khai báo một operation:

```java
@Service
@CacheConfig(cacheNames = "products")
public class ProductService {
    @Cacheable(key = "#p0")
    public String findProduct(String id) {
        System.out.println("QUERY DB");
        return repository.findTitle(id);
    }
}
```

Trong đoạn thứ hai, `@Cacheable` mới là annotation **khai báo hành vi**: trước khi gọi method, tra cache; khi hit, trả dữ liệu cache; khi miss, gọi method rồi lưu kết quả nếu đủ điều kiện. `@CacheConfig` chỉ cung cấp mặc định `cacheNames = "products"` để method không phải nhắc lại.

**Còn một điều kiện độc lập:** cơ chế xử lý cache annotation phải được bật, thường qua `@EnableCaching` trên lớp cấu hình Spring, và phải có `CacheManager`/`CacheResolver` thích hợp. Ngay cả khi method có `@Cacheable`, thiếu hạ tầng xử lý hoặc lời gọi không đi qua Spring proxy thì hiệu ứng cache có thể không xảy ra.

## 2. Ba tầng cần phân biệt

### Tầng A — Khai báo cấu hình chung: `@CacheConfig`

```java
@CacheConfig(cacheNames = "products")
public class ProductService {
    // Chỉ khai báo tên cache dùng chung.
}
```

Nó giống một **bộ giá trị mặc định** cho những method có cache operation. Nó không mang ý nghĩa "mọi method của lớp đều được cache". Annotation này có thể chỉ định:

- `cacheNames` (cũng có alias `value`): tên hoặc danh sách tên cache mặc định.
- `keyGenerator`: tên bean `KeyGenerator` dùng khi operation không tự chọn key hoặc generator khác.
- `cacheManager`: tên bean `CacheManager` dùng cho các operation áp dụng mặc định đó.
- `cacheResolver`: tên bean `CacheResolver` để giải quyết cache động theo operation.

`@CacheConfig` **không có** các thuộc tính `key`, `condition` hay `unless` của một operation đơn lẻ; không có "TTL = 60 seconds", "maximumSize", "sync" hoặc "evict all entries" trực tiếp trên annotation này. Các chính sách như TTL, serialization, dung lượng và eviction policy là chuyện của cache provider/configuration, không phải mặc nhiên do `@CacheConfig` cung cấp.

### Tầng B — Khai báo hành vi: `@Cacheable`, `@CachePut`, `@CacheEvict`

Các operation nói rõ phải làm gì:

| Annotation trên phương thức | Hành vi | Phương thức đích có chạy? |
| --- | --- | --- |
| `@Cacheable` | Tìm key trước; khi miss chạy method và có thể lưu kết quả | **Có khi miss**, **không khi hit** trong trường hợp thường |
| `@CachePut` | Gọi method rồi cập nhật cache bằng kết quả bình thường | **Có** trong trường hợp lời gọi được intercept |
| `@CacheEvict` | Xóa entry/các entry theo cấu hình, trước hoặc sau invocation | Thông thường **có** |
| `@Caching` | Nhóm nhiều operation ở cùng một method | Tùy các operation chứa bên trong |

`@CacheConfig` **không tương đương** `@Caching`: một bên là mặc định cấp lớp, một bên gom các hoạt động cache cụ thể.

### Tầng C — Hạ tầng thực thi: `@EnableCaching` + backend

`@EnableCaching` cấu hình cơ chế xử lý cache annotation qua Spring AOP/cache interceptor trong chế độ proxy mặc định. `CacheManager` cung cấp các cache thật mà operation cần dùng, chẳng hạn một cache trong RAM hoặc một backend Redis được cấu hình phù hợp.

```text
@EnableCaching + CacheManager
           |
           v
Spring cache infrastructure/proxy
           |
           | đọc metadata của method cache operation
           | + giá trị mặc định từ @CacheConfig
           v
@Cacheable / @CachePut / @CacheEvict
           |
           v
Cache lookup/put/evict theo tên, key và policy
```

Nếu chỉ có `@EnableCaching` nhưng **không có method-level cache operations**, không có việc tự động cache mọi method. Nếu chỉ có `@CacheConfig` mà **không có `@EnableCaching`**, cũng không có cache advice được bật theo cách thông thường. Để caching annotation có tác dụng, cần **cả khai báo operation và hạ tầng phù hợp**, đồng thời lời gọi phải đi qua điểm interception.

## 3. Điều xảy ra khi một lớp chỉ có `@CacheConfig`

Xét lớp:

```java
@Service
@CacheConfig(cacheNames = "catalog")
public class CatalogService {
    public String read(String sku) {
        return database.get(sku);
    }

    public String update(String sku, String title) {
        database.put(sku, title);
        return title;
    }
}
```

*Đây là ví dụ minh họa, `database` chưa được khai báo.*

Dù có cache `catalog` trong `CacheManager`, cả hai phương thức trên vẫn chạy như Java method thông thường. Không có automatic lookup trước `read`, không có automatic put sau `update`, và không có automatic eviction. `@CacheConfig` không theo dõi những thao tác ở `database` để suy đoán khi nào cần cache.

Điều này không có nghĩa cache không thể thay đổi: **code khác vẫn có thể tự gọi `Cache.put(...)` hoặc một method khác có annotation cache vẫn có thể ghi cache**. Kết luận chính xác là: **chính `@CacheConfig` không tạo ra bất kỳ cache operation nào cho những method chỉ vì chúng thuộc lớp đó**.

Nếu muốn áp dụng mặc định cho `read` và `update`:

```java
@Service
@CacheConfig(cacheNames = "catalog")
public class CatalogService {
    @Cacheable(key = "#p0")
    public String read(String sku) {
        return database.get(sku);
    }

    @CachePut(key = "#p0")
    public String update(String sku, String title) {
        database.put(sku, title);
        return title;
    }
}
```

Tại đây, hai operation đều sử dụng cache `catalog` do `@CacheConfig` khai báo. Nhưng chúng vẫn có **hành vi khác nhau**: `read` có thể trả từ cache mà không vào method; `update` luôn thực thi method rồi có thể ghi giá trị trả về vào cache. Việc `update` trả đúng dạng dữ liệu mà `read` mong đợi, và hai key có cùng ý nghĩa, là trách nhiệm thiết kế của lập trình viên.

## 4. Cơ chế kế thừa mặc định và độ ưu tiên cấu hình

Spring hỗ trợ ba mức cấu hình cho cache operation, từ tổng quát tới cụ thể:

1. **Mức global:** cấu hình toàn ứng dụng (ví dụ `CachingConfigurer` hoặc cache infrastructure).
2. **Mức lớp:** `@CacheConfig` cung cấp các mặc định cho operation trong lớp đó.
3. **Mức operation:** thuộc tính ngay trên `@Cacheable`, `@CachePut` hoặc `@CacheEvict`.

**Cấu hình cụ thể của operation ưu tiên hơn mặc định cấp lớp** khi cùng thuộc tính được chỉ định. Ví dụ:

```java
@CacheConfig(cacheNames = "catalog")
public class CatalogService {
    @Cacheable(key = "#p0")
    public String readDefault(String id) {
        return loadDefault(id);
    }

    @Cacheable(cacheNames = "catalog-preview", key = "#p0")
    public String readPreview(String id) {
        return loadPreview(id);
    }
}
```

*Đoạn trên minh họa; hai hàm `loadDefault` và `loadPreview` chưa được định nghĩa.*

- `readDefault` lấy cache name từ `@CacheConfig`: `catalog`.
- `readPreview` khai báo cache name riêng ngay trên `@Cacheable`: `catalog-preview`; vì thế không dùng cache name cấp lớp cho operation đó.
- Cả hai có expression `key = "#p0"` do chính method khai báo.
- Việc hai method có cùng đối số không tự làm chúng chung một entry nếu tên cache khác nhau.

### 4.1. `keyGenerator` chỉ là cách tạo khóa, không phải một cache operation

Ví dụ:

```java
@CacheConfig(cacheNames = "catalog", keyGenerator = "myKeyGenerator")
public class CatalogService {
    @Cacheable
    public String find(String sku) {
        return lookup(sku);
    }
}
```

Nếu bean `myKeyGenerator` tồn tại và được cấu hình đúng, `@Cacheable` có thể dùng generator ấy để tạo key. Nhưng nếu bỏ `@Cacheable` khỏi `find`, `@CacheConfig(keyGenerator = ...)` cũng **không khiến Spring tự tính key** trên mỗi lời gọi thường.

Một cache operation không được chỉ định đồng thời `key` (SpEL) **và** `keyGenerator` riêng ở cùng cấp; hai cơ chế lựa chọn khóa thay thế nhau. Nếu cần tính key phụ thuộc nhiều tham số, hãy thiết kế nhất quán giữa read, put và evict.

### 4.2. `cacheManager` / `cacheResolver` là cách tìm cache

`@CacheConfig` có thể chia sẻ tên bean manager/resolver. Chúng không thay thế `@Cacheable`, `@CachePut` hay `@CacheEvict`. `cacheManager` và `cacheResolver` là hai cách giải quyết cache, không nên chỉ định chúng một cách xung đột ở cùng operation. Muốn dùng provider phù hợp, bean được tham chiếu phải thực sự tồn tại trong Spring context.

**Lưu ý quan trọng:** việc chọn `cacheNames = "catalog"` không tự tạo cache vật lý, Redis key namespace, TTL, eviction policy hay transaction. Cache name là một phần metadata để operation tìm cache; sự tồn tại, khởi tạo và cấu hình cache thật do provider/manager quyết định.

## 5. Các trường hợp đủ và chưa đủ để có cache

| `@EnableCaching` | `@CacheConfig` | Annotation cache trên method | Kết quả trong proxy mode thông thường |
| --- | --- | --- | --- |
| Có | Có | **Không có** | Không tạo cache operation từ `@CacheConfig`; method chạy bình thường |
| Có | Có | `@Cacheable` | Có thể cache hit/miss; lấy mặc định từ `@CacheConfig` |
| Có | Có | `@CachePut` | Method chạy, put kết quả nếu thỏa điều kiện |
| Có | Có | `@CacheEvict` | Evict theo cấu hình operation |
| Có | Không | `@Cacheable(cacheNames = "catalog")` | Có thể hoạt động: `@CacheConfig` không bắt buộc |
| Không | Có | `@Cacheable` | Annotation có trong source nhưng thường không có cache advice được kích hoạt |
| Có | Có | Có, nhưng gọi `this.cachedMethod()` từ chính bean | Self-invocation **không được proxy intercept** trong mode mặc định |
| Có | Có | Có, nhưng object được tạo bằng `new` ngoài container | Không có Spring proxy cho object đó, nên không có cache advice |

Bảng giả định `CacheManager`/`CacheResolver` phù hợp và bean được quản lý đúng. Một annotation cache có thể tồn tại nhưng cấu hình sai (cache name không tìm thấy, key expression lỗi, bean manager không có...) thì runtime vẫn báo lỗi; không nên tự động kết luận cache hoạt động.

## 6. Ví dụ Spring Boot chạy được: cùng một lớp, method thường và method có cache

Ví dụ độc lập này dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5**, và `ConcurrentMapCacheManager` làm cache cục bộ. Có một lớp `CatalogService` mang `@CacheConfig(cacheNames = "catalog")` nhưng **không phải mọi method đều được cache**.

Những điều muốn quan sát:

- `plain("P1")` **không** có annotation cache operation: lần nào cũng vào thân method, **không thêm entry** vào cache.
- `read("P1")` có `@Cacheable`: lần đầu miss, lần hai hit.
- `change("P1", "Updated")` có `@CachePut`: method chạy và ghi kết quả mới theo key.
- `evict("P1")` có `@CacheEvict`: xóa entry đúng key.
- Cả ba operation **không phải ghi lại `cacheNames` trên method**, nhờ mặc định class-level.

### 6.1. Cấu trúc thư mục

```text
cache-config-demo/
├── pom.xml
└── src/main/java/example/cacheconfig/
    ├── CacheConfigApplication.java
    └── CatalogService.java
```

### 6.2. File `pom.xml`

```xml
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
    <artifactId>cache-config-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
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
```

### 6.3. File `src/main/java/example/cacheconfig/CatalogService.java`

```java
package example.cacheconfig;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
@CacheConfig(cacheNames = "catalog")
public class CatalogService {
    private final ConcurrentMap<String, String> database =
            new ConcurrentHashMap<>(Map.of("P1", "Original"));

    private final AtomicInteger plainCalls = new AtomicInteger();
    private final AtomicInteger readCalls = new AtomicInteger();
    private final AtomicInteger changeCalls = new AtomicInteger();

    // KHÔNG có operation annotation: @CacheConfig không tự thêm cache.
    public String plain(String sku) {
        System.out.println("BODY plain #" + plainCalls.incrementAndGet());
        return database.get(sku);
    }

    // @Cacheable là operation; cacheNames được kế thừa từ @CacheConfig.
    @Cacheable(key = "#p0")
    public String read(String sku) {
        System.out.println("BODY read #" + readCalls.incrementAndGet());
        return database.get(sku);
    }

    // @CachePut luôn gọi method rồi dùng kết quả để cập nhật cùng key.
    @CachePut(key = "#p0")
    public String change(String sku, String newTitle) {
        System.out.println("BODY change #" + changeCalls.incrementAndGet());
        database.put(sku, newTitle);
        return newTitle;
    }

    // @CacheEvict loại bỏ entry sau khi method hoàn thành bình thường.
    @CacheEvict(key = "#p0")
    public void evict(String sku) {
        System.out.println("BODY evict " + sku);
    }
}
```

### 6.4. File `src/main/java/example/cacheconfig/CacheConfigApplication.java`

```java
package example.cacheconfig;

import java.util.Objects;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CacheConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheConfigApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }

    @Bean
    CommandLineRunner demo(CatalogService service, CacheManager cacheManager) {
        return args -> {
            Cache catalog = Objects.requireNonNull(cacheManager.getCache("catalog"));

            System.out.println("PLAIN1 => " + service.plain("P1"));
            System.out.println("PLAIN2 => " + service.plain("P1"));
            System.out.println(
                "ENTRY_AFTER_PLAIN => " + (catalog.get("P1") != null)
            );

            System.out.println("READ1 => " + service.read("P1"));
            System.out.println("READ2 => " + service.read("P1"));
            System.out.println(
                "ENTRY_AFTER_READ => " +
                Objects.requireNonNull(catalog.get("P1")).get()
            );

            System.out.println("CHANGE => " + service.change("P1", "Updated"));
            System.out.println("READ3 => " + service.read("P1"));

            service.evict("P1");
            System.out.println(
                "ENTRY_AFTER_EVICT => " + (catalog.get("P1") != null)
            );
            System.out.println("READ4 => " + service.read("P1"));
        };
    }
}
```

### 6.5. Chạy chương trình

Cần có JDK **17 trở lên**, Maven, và quyền tải các dependency Maven khi chưa có trong cache cục bộ. Tại thư mục `cache-config-demo` chạy:

```bash
mvn spring-boot:run
```

Những dòng do đoạn demo in ra sẽ theo **đúng thứ tự** dưới đây (Spring Boot còn có log khởi động riêng):

```text
BODY plain #1
PLAIN1 => Original
BODY plain #2
PLAIN2 => Original
ENTRY_AFTER_PLAIN => false
BODY read #1
READ1 => Original
READ2 => Original
ENTRY_AFTER_READ => Original
BODY change #1
CHANGE => Updated
READ3 => Updated
BODY evict P1
ENTRY_AFTER_EVICT => false
BODY read #2
READ4 => Updated
```

### 6.6. Phân tích kết quả

**Lượt PLAIN1 và PLAIN2:** `CatalogService` có `@CacheConfig(cacheNames="catalog")` nhưng `plain` không có cache operation. Vì vậy mỗi lời gọi in `BODY plain`. Sau cả hai lần, `catalog.get("P1") == null`, kết quả `ENTRY_AFTER_PLAIN => false`. Đây là bằng chứng trực tiếp rằng class-level `@CacheConfig` **không tự kích hoạt cache**.

**Lượt READ1:** `@Cacheable` ở method `read` là cache operation. Spring chọn cache `catalog` từ `@CacheConfig`, tính key từ `#p0 = "P1"`, thấy miss rồi chạy method; kết quả `Original` được lưu.

**Lượt READ2:** cùng key `"P1"`, Spring hit, trả `Original` ngay từ cache, nên không in thêm `BODY read`. `ENTRY_AFTER_READ => Original` xác nhận cache có entry.

**Lượt CHANGE:** `@CachePut` **luôn thực thi** `change`, ghi `Updated` vào database giả lập rồi ghi trả về `Updated` vào cache `catalog["P1"]`. Vì `READ3` dùng cùng cache/key, nó hit `Updated`; không in `BODY read`.

**Lượt EVICT:** `@CacheEvict(key="#p0")` xóa entry `P1` sau khi `evict` trả về. Kết quả `ENTRY_AFTER_EVICT => false` cho biết key không còn trong cache.

**Lượt READ4:** key đã bị xóa nên miss; method `read` chạy lần thứ hai, đọc `Updated` từ database giả lập và lưu lại.

**Điều kiện làm demo tái lập được:** `CommandLineRunner` nhận `CatalogService` bằng dependency injection, gọi từ một bean khác đi qua Spring proxy. `@EnableCaching` bật xử lý annotation; `ConcurrentMapCacheManager("catalog")` tạo đúng cache có tên được dùng trong `@CacheConfig`. Các object và biến đếm được khởi tạo trong một tiến trình mới, không có thread khác thao tác. Toàn bộ output trên là luồng nghiệp vụ deterministic của code; không bao gồm log/framework banner.

## 7. Nếu bỏ `@Cacheable` nhưng giữ `@CacheConfig` thì sao?

Hãy tưởng tượng thay:

```java
@Cacheable(key = "#p0")
public String read(String sku) {
    return database.get(sku);
}
```

bằng:

```java
public String read(String sku) {
    return database.get(sku);
}
```

Nếu chỉ xóa `@Cacheable`, không có operation nào được khai báo trên `read`. `@CacheConfig(cacheNames="catalog")` **vẫn còn ở class**, nhưng lời gọi `read` không được cache interceptor xử lý để lookup/put như trước. Với một cache entry đã tồn tại, method không tự động lấy lại entry đó; nó chạy logic của mình.

Đây cũng là lý do không nên đặt kỳ vọng rằng thêm `@CacheConfig` cho toàn bộ repository/service sẽ “tự động tối ưu” tất cả phương thức. Spring Cache là một cơ chế **declarative theo operation**, không phải bộ nhớ tự động ghi lại mọi lần gọi đối tượng trong lớp.

Ngược lại, xóa riêng `@CacheConfig` nhưng vẫn giữ `@Cacheable(cacheNames="catalog")` trên method, cùng `@EnableCaching` và `CacheManager` hợp lệ, cache vẫn hoạt động. `@CacheConfig` giúp tránh lặp thông số, chứ không phải điều kiện bắt buộc để dùng caching.

## 8. Nếu đã gắn `@Cacheable` mà vẫn thấy phương thức chạy mỗi lần?

Không phải cứ thấy method chạy liên tục là `@CacheConfig` “không hoạt động”; cần phân loại nguyên nhân:

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| Class có `@CacheConfig`, method không gắn operation | Không có gì để cache: hoạt động đúng theo thiết kế |
| Method có `@Cacheable` nhưng chưa bật caching annotation | Cần `@EnableCaching` hoặc cấu hình tương đương |
| Method có annotation, nhưng object được tạo bằng `new` | Không được Spring quản lý/proxy |
| Method cacheable được gọi qua `this.method()` cùng bean | Self-invocation bỏ qua proxy trong mode mặc định |
| Method có `@Cacheable(condition=...)` trả `false` | Lời gọi bypass cache và method vẫn chạy |
| Method có `@Cacheable(unless=...)` veto kết quả | Cache không lưu kết quả mới; lần sau có thể miss |
| Cache name ở method khác tên ở class | Method-level override; đang kiểm tra cache khác |
| Key được tạo khác nhau giữa hai lượt | Mỗi key có lookup riêng |
| Cache entry bị evict/expire hoặc cache manager không chia sẻ giữa instance | Có thể miss dù đã từng lưu ở nơi khác |
| Method/annotation không thể được proxy intercept | Cần xem visibility, cấu trúc bean/proxy và mode |

Trong proxy mode mặc định, chỉ các lời gọi **đi qua proxy** mới được cache intercept. Ví dụ:

```java
@Service
@CacheConfig(cacheNames = "catalog")
public class CatalogService {
    @Cacheable(key = "#p0")
    public String read(String sku) {
        return lookup(sku);
    }

    public String callInternally(String sku) {
        return this.read(sku); // self-invocation; bỏ qua cache proxy mặc định
    }
}
```

*Đoạn minh họa chưa độc lập do `lookup` chưa được định nghĩa.*

Giải pháp dễ bảo trì là tách method cacheable sang một Spring bean được bean khác gọi qua dependency injection. Cẩn thận với phương thức private, final, lời gọi từ constructor và việc dựa vào AOP khi bean chưa khởi tạo xong. Có thể có các chế độ weaving khác proxy, nhưng chúng cần cấu hình rõ ràng.

## 9. `@CacheConfig` không định nghĩa TTL và không bảo đảm dữ liệu luôn mới

Một hiểu nhầm thường gặp là dùng `@CacheConfig(cacheNames="catalog")` rồi kỳ vọng:

- cache entry tự hết hạn sau một thời gian cố định;
- kết quả tự đồng bộ khi database đổi;
- các ứng dụng/instance đều chia sẻ một bộ nhớ cache;
- có chính sách hạn chế dung lượng hoặc serialize thích hợp;
- cập nhật database cùng cache theo transaction nguyên tử.

`@CacheConfig` **không chứa** những chính sách này. Chúng được cấu hình ở cache provider, `CacheManager`, cách invalidation, transaction-aware cache và kiến trúc hệ thống.

Ví dụ `ConcurrentMapCacheManager` trong demo là bộ nhớ của **một JVM**, không có TTL mặc định như một số provider có chính sách expiration. Caffeine, Redis hoặc các cache provider khác có cơ chế TTL/size/eviction riêng. Việc đặt cùng tên cache trên nhiều node **không tự tạo bộ nhớ chia sẻ**.

Ngay cả khi `@Cacheable` thực sự hoạt động, key phải phân biệt những giá trị đầu vào ảnh hưởng kết quả (ví dụ tenant, locale, loại giá). Cần evict/put hay version hóa đúng khi dữ liệu thay đổi; `@CacheConfig` không tự nhận biết những phụ thuộc nghiệp vụ đó.

## 10. Lựa chọn dùng `@CacheConfig` trong thực tế

Nên dùng `@CacheConfig` khi **nhiều method trong cùng một class** thực sự có cache operation và chia sẻ cùng mặc định. Ví dụ một lớp có `findById` cacheable, `save` cache-put và `delete` cache-evict, tất cả cùng cache namespace `products`.

Lợi ích:

- **Giảm lặp tên cache:** đổi tên cache chung ở một nơi.
- **Nhất quán key generator/manager/resolver:** tránh method này dùng manager A, method kia vô tình dùng manager B khi đáng lẽ phải chung.
- **Dễ xem cấu hình:** metadata của cả lớp nằm cùng vị trí, nhưng hành vi cụ thể vẫn được khai báo rõ ngay tại từng method.
- **Có thể override có chủ đích:** method đặc biệt khai báo `cacheNames` hoặc config riêng ở operation level.

Không nên dùng `@CacheConfig` chỉ để làm "dấu hiệu đánh dấu lớp có cache" mà bỏ qua việc khai báo operation. Nếu mọi method có behavior khác nhau, ưu tiên annotation cụ thể tại method; không ép chung một default chỉ để tiết kiệm vài dòng.

### Ví dụ thao tác nhiều cache, có override

```java
@CacheConfig(cacheNames = "products")
public class ProductService {
    @Cacheable(key = "#p0")
    public String getById(String id) {
        return loadById(id);
    }

    @Cacheable(cacheNames = "product-search", key = "#p0")
    public String search(String keyword) {
        return searchDatabase(keyword);
    }

    @CacheEvict(key = "#p0")
    public void deleteById(String id) {
        deleteFromDatabase(id);
    }
}
```

*Đoạn này minh họa cấu hình, các phương thức phụ trợ chưa được khai báo.*

Trong ví dụ, `getById` và `deleteById` dùng mặc định `products`, nhưng `search` cố ý dùng `product-search`. Một cập nhật sản phẩm có thể cần invalidation **cả cache tra cứu lẫn cache tìm kiếm**, tùy các kết quả phụ thuộc nhau; `@CacheConfig` không tự suy ra quan hệ này.

## 11. Các lỗi thường gặp

1. **Đặt `@CacheConfig` trên class rồi bỏ qua `@Cacheable`.** Không có hành vi đọc/lưu tự động trên method không được đánh dấu operation.
2. **Cho rằng `@EnableCaching` tự động cache mọi method.** Nó chỉ bật cơ chế xử lý các operation đã khai báo.
3. **Quên bean manager/resolver hoặc khai báo tên cache không tồn tại.** Metadata không thay cho hạ tầng lưu trữ; cấu hình sai có thể gây lỗi ở runtime.
4. **Trộn lẫn cache defaults với cache provider policy.** `@CacheConfig` không cung cấp TTL, max size hoặc Redis serialization.
5. **Cho rằng method-level config sẽ bị class config ghi đè.** Ngược lại: operation level được ưu tiên cho thuộc tính được chỉ định.
6. **Nhầm `@CachePut` với `@Cacheable`.** Put thực thi method rồi có thể ghi kết quả; Cacheable mới có thể bỏ qua method khi hit.
7. **Gọi method cacheable từ cùng bean qua `this.`.** Trong proxy mode mặc định, không qua proxy thì không có cache interception.
8. **Dùng `@CacheConfig(keyGenerator=...)` nhưng đồng thời chỉ định `key` trên method rồi tưởng generator vẫn chạy.** Biểu thức key của operation là lựa chọn cụ thể; phải thiết kế một chiến lược key nhất quán.
9. **Dùng chung tên cache/key cho các method khác kiểu kết quả.** Một operation có thể lấy dữ liệu do operation khác ghi vào và gặp dữ liệu sai kiểu/sai ý nghĩa.
10. **Xem cấu hình class là bảo đảm transaction hoặc freshness.** Data consistency phụ thuộc backend, invalidation và transaction orchestration riêng.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một lớp có `@Service`, `@CacheConfig(cacheNames="books")` và method `findBook` không có annotation khác. Gọi cùng ID hai lần có chắc lần thứ hai cache hit không?

**Đáp án:** Không. `@CacheConfig` không tự tạo cache operation. Method vẫn thực thi thông thường ở cả hai lần, trừ khi có caching được áp dụng theo cơ chế khác ngoài đoạn khai báo đang xét.

**Câu 2.** Đã có `@EnableCaching`, `CacheManager`, và `@CacheConfig(cacheNames="books")`. Đã đủ để cache method không gắn `@Cacheable` chưa?

**Đáp án:** Chưa. Cần operation annotation trên method (hoặc cơ chế declarative tương đương) để Spring biết lời gọi nào cần xử lý cache.

**Câu 3.** Lớp khai báo `@CacheConfig(cacheNames="books")`, method khai báo `@Cacheable(cacheNames="featured")`. Cache nào được method dùng?

**Đáp án:** `featured`, bởi cấu hình operation-level override mặc định cấp lớp.

**Câu 4.** Method có `@Cacheable` nhưng chỉ được gọi qua `this.find(...)`. Vì sao không có hit/miss như mong đợi?

**Đáp án:** Self-invocation trong proxy mode mặc định bỏ qua Spring cache proxy. Cần gọi thông qua Spring bean proxy hoặc cấu hình interception thích hợp.

**Câu 5.** Có thể viết `@CacheConfig(ttl=60)` để mọi cache trong class tự hết hạn không?

**Đáp án:** Không. `@CacheConfig` không có thuộc tính `ttl`. Thiết lập expiration ở cache provider/CacheManager hoặc một chính sách quản lý vòng đời cache phù hợp.

**Câu 6.** Một class có `@CacheConfig` và ba method: không annotation, `@Cacheable`, `@CachePut`. Có phải cả ba đều bị Spring cache interceptor xử lý giống nhau?

**Đáp án:** Không. Method không annotation không có operation tự động; `@Cacheable` có hit/miss và có thể bỏ qua method, còn `@CachePut` thực thi method rồi ghi kết quả.

## Tài liệu tham khảo

- Spring Framework Reference — *Declarative Annotation-based Caching*, mục `@CacheConfig` và *Enabling Caching Annotations*: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `@CacheConfig`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/CacheConfig.html
- Spring Framework Javadoc — `@EnableCaching`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/EnableCaching.html
- Spring Boot Reference — *Caching*: https://docs.spring.io/spring-boot/reference/io/caching.html
