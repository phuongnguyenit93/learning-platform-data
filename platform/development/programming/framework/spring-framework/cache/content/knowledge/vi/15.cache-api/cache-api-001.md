# Lấy cache qua CacheManager.getCache trong Spring Framework

## Mục tiêu

Trong Spring Cache, `CacheManager` là điểm truy cập các **vùng cache có tên** (*named cache regions*). API cơ bản nhất là:

~~~java
Cache cache = cacheManager.getCache("products");
~~~

Lệnh này yêu cầu một đối tượng `Cache` có tên `products`. Nó **không phải** thao tác lấy giá trị của một sản phẩm trong cache. Muốn lấy entry theo key, cần gọi tiếp `cache.get(key)`. Quan trọng hơn, `getCache(name)` **có thể trả về `null`** nếu cache không tồn tại hoặc provider không thể tạo ra cache đó.

Sau bài này, bạn có thể:

- Giải thích vai trò của `CacheManager`, `Cache`, tên cache và key.
- Sử dụng `getCache(String name)`, kiểm tra `null` và hiểu lúc nào manager có thể tự tạo vùng cache.
- Phân biệt cache không tồn tại, cache tồn tại nhưng entry bị miss, và entry được cache với giá trị `null`.
- Thao tác `get`, `put`, `evict`, `clear`, và biết khi nào nên dùng `get(key, Callable)`.
- Dùng API lập trình cùng vùng cache với `@Cacheable`/`@CacheEvict`.
- Tổ chức injection, lỗi cấu hình, multi-tenant, kiểm thử và theo dõi hiệu năng đúng cách.
- Chạy demo Java 17 + Spring Framework và đối chiếu stdout.

## 1. Hai cấp định danh: cache name và entry key

Hãy xem cache như một tập hợp các vùng lưu trữ:

~~~text
                CacheManager
                     |
          +----------+-----------+
          |                      |
          v                      v
 Cache "products"          Cache "prices"
    |        |                |        |
    v        v                v        v
 key "A"   key "B"          key "A"   key "B"
    |        |                |        |
    v        v                v        v
 ProductA ProductB             100      200
~~~

Có hai bước riêng biệt:

1. **Chọn cache:** `Cache cache = manager.getCache("products");`
2. **Chọn entry:** `Cache.ValueWrapper wrapped = cache.get("A");`

Tên `products` không phải key `A`. Nếu nhầm hai cấp này, người học dễ viết code truy cập sai vùng cache mà vẫn không thấy lỗi biên dịch.

| API | Câu hỏi được trả lời | Kết quả |
| --- | --- | --- |
| `cacheManager.getCache("products")` | Manager có cung cấp cache `products` không? | Một `Cache` hoặc `null` |
| `cacheManager.getCacheNames()` | Manager hiện biết các tên cache nào? | `Collection<String>` |
| `cache.get("A")` | Cache này có mapping của key `A` không? | `Cache.ValueWrapper` hoặc `null` |
| `cache.get("A", Product.class)` | Có thể lấy giá trị kiểu `Product` của key `A` không? | `Product` hoặc `null` theo hợp đồng API |
| `cache.put("A", product)` | Lưu/thay mapping của `A` | Không trả giá trị |
| `cache.evict("A")` | Yêu cầu loại bỏ mapping của `A` | Không trả giá trị |
| `cache.clear()` | Yêu cầu xóa mọi entry trong vùng cache này | Không trả giá trị |

`CacheManager` không phải một database repository và không tự đọc dữ liệu gốc. Nó chỉ tìm hoặc cung cấp vùng cache dựa trên `name`. Lệnh `getCache` cũng không tự tải entry, không đảm bảo đã có dữ liệu trong vùng được trả về và không tự gắn TTL.

## 2. Hợp đồng API: getCache có thể trả về null

Giao diện Spring Framework, viết dưới dạng rút gọn:

~~~java
public interface CacheManager {
    Cache getCache(String name);
    Collection<String> getCacheNames();
}
~~~

Đây là **chữ ký khái niệm** đã lược annotation và import, không phải tệp Java độc lập. Trong API chính thức, `getCache(String name)` được đánh dấu nullable:

- `name` là định danh cache, **không được truyền `null`**.
- Trả về đối tượng `Cache` tương ứng nếu manager có thể cung cấp.
- Trả về `null` nếu cache không tồn tại hoặc không thể tạo được.
- Tùy provider, cache có thể được **tạo lazy ngay trong lời gọi `getCache`**.

Vì vậy không nên viết:

~~~java
cacheManager.getCache("products").put("A", value);
~~~

nếu chưa chắc chắn cache luôn tồn tại. Đây là snippet minh họa; biến `value` do ứng dụng cung cấp. Nếu cache không tồn tại, dereference sẽ gây `NullPointerException`.

Cách rõ ràng hơn cho cache **bắt buộc phải được cấu hình**:

~~~java
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("products"),
        "Missing required cache: products");
cache.put("A", value);
~~~

Snippet trên cần `import java.util.Objects;`, `import org.springframework.cache.Cache;` và dependency Spring. `Objects.requireNonNull` không giúp tự tạo cache: nó chỉ phát hiện lỗi cấu hình sớm, có thông báo dễ chẩn đoán.

### Hai chiến lược khi không tìm thấy cache

**Fail fast:** Với một vùng cache bắt buộc, ném exception có ý nghĩa. Việc silently fallback về một cache khác có thể phá vỡ cô lập tenant, key namespace hoặc consistency.

**Graceful degradation:** Khi cache thật sự là tính năng không bắt buộc, có thể chọn đường đọc trực tiếp nguồn dữ liệu nếu không có cache. Phải thiết kế đường đi này rõ ràng, thay vì bất ngờ bỏ qua exception trên mọi lỗi backend; không tìm thấy cache và lỗi truy cập Redis là hai tình huống khác nhau.

Ví dụ minh họa:

~~~java
Cache cache = cacheManager.getCache("optional-lookup");
if (cache == null) {
    return repository.load(id); // chủ động chạy không cache
}
Cache.ValueWrapper wrapped = cache.get(id);
if (wrapped != null) {
    return (Product) wrapped.get();
}
Product product = repository.load(id);
if (product != null) {
    cache.put(id, product);
}
return product;
~~~

Đoạn trên **không độc lập** vì `repository`, `id`, `Product` thuộc ứng dụng. Nó chỉ diễn đạt một chính sách bypass; khi thực tế, cần xử lý type, null, concurrency, serialization và lifecycle nhất quán. Không nên tự viết toàn bộ cache-aside logic nếu `@Cacheable` đã đáp ứng tốt.

## 3. getCache phụ thuộc CacheManager cụ thể

Không có quy tắc chung rằng gọi `getCache("anything")` luôn trả cache mới. Đặc tính **dynamic** hay **static** do implementation và cấu hình quyết định.

### 3.1. ConcurrentMapCacheManager ở chế độ dynamic

~~~java
CacheManager manager = new ConcurrentMapCacheManager();
Cache alpha = manager.getCache("alpha");
Cache beta = manager.getCache("beta");
~~~

Đoạn mã này là snippet minh họa. Constructor không truyền tên tạo manager ở chế độ **dynamic**: provider có thể tạo `ConcurrentMapCache` cho tên được yêu cầu lần đầu. Trong trường hợp này, `getCache("alpha")` có thể trả non-null dù trước đó chưa có vùng `alpha`.

Điều đó **không** có nghĩa entry `"A"` đã tồn tại. Vùng mới vẫn có thể rỗng.

### 3.2. ConcurrentMapCacheManager ở chế độ static

~~~java
CacheManager manager = new ConcurrentMapCacheManager(
        "products", "prices");

Cache products = manager.getCache("products"); // non-null
Cache unknown = manager.getCache("unknown");   // null
~~~

Khi truyền danh sách tên cache cho constructor, `ConcurrentMapCacheManager` ở chế độ **static**, chỉ quản lý những vùng đã được chỉ định. Đây là cách hữu ích trong demo/test vì phát hiện tên gõ sai:

~~~text
"products" -> được cấu hình
"prices"   -> được cấu hình
"produts"  -> không được cấu hình (lỗi chính tả)
~~~

Với manager dynamic, lỗi chính tả `produts` có thể tạo **một vùng mới ngoài ý muốn** và khiến người dùng tưởng rằng `products` bị miss vĩnh viễn. Với static manager, lỗi có thể lộ rõ qua kết quả `null`.

### 3.3. getCacheNames không phải luôn là danh mục đóng

`getCacheNames()` cho biết các tên cache manager **đang biết**. Ở manager dynamic, danh sách có thể tăng khi các cache mới được tạo lazy; ở static manager, bộ tên thường được giới hạn theo cấu hình. Đừng dựa vào `getCacheNames()` để chứng minh tất cả tên có thể tồn tại trong tương lai hoặc để triển khai authorization.

### 3.4. Provider thật có thể khác

Trong môi trường production, `CacheManager` có thể là `CaffeineCacheManager`, `RedisCacheManager`, `JCacheCacheManager`, `CompositeCacheManager` hoặc implementation riêng. Chính sách tạo cache, cấu hình TTL, serialization, null, eviction, distributed consistency và ngoại lệ phụ thuộc implementation. Hãy đọc hợp đồng provider tương ứng; **không lấy kết quả của `ConcurrentMapCacheManager` làm đảm bảo cho mọi cache provider**.

## 4. Lấy vùng cache khác với lấy giá trị theo key

Một nhầm lẫn quan trọng là hai dạng `null`:

~~~java
Cache cache = cacheManager.getCache("products");
~~~

- Nếu `cache == null`: **không lấy được vùng cache**.
- Nếu `cache != null` nhưng `cache.get("A") == null`: **vùng cache có tồn tại**, nhưng không có mapping được tìm thấy cho key `A`.

Cần kiểm tra hai bước:

~~~java
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("products"));

Cache.ValueWrapper wrapper = cache.get("A");
if (wrapper == null) {
    System.out.println("MISS: key A");
} else {
    System.out.println("HIT: " + wrapper.get());
}
~~~

Đây là đoạn minh họa, không phải file Java độc lập. Chỉ `wrapper == null` mới biểu thị cache miss trong biến thể `get(Object)`. `wrapper.get()` **có thể trả về `null`** nếu cache implementation có hỗ trợ lưu giá trị null.

### 4.1. Entry chứa null khác entry vắng mặt

Ví dụ một cache provider cho phép lưu `null` (như `ConcurrentMapCache` với `allowNullValues=true`):

~~~java
cache.put("A", null);
Cache.ValueWrapper wrapper = cache.get("A");

System.out.println(wrapper == null);   // false: có mapping
System.out.println(wrapper.get() == null); // true: giá trị là null
~~~

Snippet trên giả định cache được cấu hình cho phép cached-null. Không được mặc định mọi backend chấp nhận null. Nếu backend không hỗ trợ, `put(key, null)` có thể bị từ chối hoặc có semantics riêng.

So sánh:

| Trạng thái | `cache.get(key)` | `wrapper.get()` |
| --- | --- | --- |
| Entry không tồn tại | `null` | Không được gọi vì không có wrapper |
| Entry có giá trị `"x"` | Non-null wrapper | `"x"` |
| Entry chứa giá trị `null` được provider hỗ trợ | Non-null wrapper | `null` |

### 4.2. Typed get

~~~java
String value = cache.get("A", String.class);
~~~

Variant typed tiện lợi nhưng **`null` có thể là miss hoặc cached-null**; nó không phân biệt hai trạng thái như `ValueWrapper`. Nếu kiểu thực tế không tương thích với `String.class`, API có thể ném exception. Không nên dùng typed lookup một cách mù quáng khi dữ liệu cache được dùng chung giữa nhiều kiểu object hoặc sau khi đổi schema.

## 5. Thao tác lập trình sau khi đã có Cache

### 5.1. Ghi: put

~~~java
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("products"));
cache.put("A", "product-A-v1");
~~~

`put` tạo hoặc thay mapping trong **vùng cache** hiện tại. Nó không ghi vào database. Một hệ thống có thể trở nên stale nếu dữ liệu cache được put mà không đồng bộ với dữ liệu gốc. Một số implementation có thể thực hiện operation theo cơ chế bất đồng bộ hoặc có độ trễ; kiểm tra hợp đồng của provider.

### 5.2. Đọc: get

~~~java
Cache.ValueWrapper result = cache.get("A");
if (result != null) {
    Object value = result.get();
    // xử lý value
}
~~~

`get` tra đúng cache/key. Việc có mặt entry không đảm bảo đó là dữ liệu mới nhất trong database. TTL, cập nhật nguồn và invalidation là các quyết định ngoài bước lookup này.

### 5.3. Xóa một entry: evict

~~~java
cache.evict("A");
~~~

Chỉ yêu cầu loại bỏ mapping ứng với key `"A"`. Việc API trả về `void` không có nghĩa entry đã ngay lập tức vô hình trên mọi provider hoặc mọi node. `evictIfPresent(key)` là lựa chọn có hợp đồng yêu cầu entry trở nên không thấy được ngay đối với các lookup tiếp theo **nếu implementation hỗ trợ semantics đó**; vẫn cần xem consistency của backend.

### 5.4. Xóa tất cả entry: clear

~~~java
cache.clear();
~~~

`clear` yêu cầu loại bỏ **toàn bộ mapping của vùng cache đó**, không phải toàn bộ database hay tất cả các vùng do manager quản lý. Không nên dùng tùy tiện cho cache nhiều key vì có thể gây burst miss và tăng tải lên backend.

Tương tự `evict`, `clear` có thể không bảo đảm nhìn thấy tác dụng ngay trong mọi implementation. `invalidate()` có semantics yêu cầu làm cho mọi mapping hiện tại không còn nhìn thấy ngay, với hợp đồng riêng của API/implementation.

### 5.5. Truy xuất hoặc tính toán khi miss: get(key, Callable)

~~~java
String value = cache.get(
        "A",
        () -> repository.load("A"));
~~~

Đây là snippet minh họa; `repository` thuộc ứng dụng. Tác dụng: khi key chưa có, cung cấp một callback để tải dữ liệu và có thể cache kết quả. Lỗi trong `Callable` có thể được bọc thành `Cache.ValueRetrievalException`.

Cần lưu ý: lời gọi này **không** có nghĩa Spring đã tự chạy annotation `@Cacheable` hay tự bảo đảm chỉ có một lần tải trên mọi backend/cluster. Khả năng đồng bộ và tính nguyên tử phụ thuộc `Cache` implementation; hãy kiểm tra under load nếu đây là đường truy cập quan trọng.

## 6. Demo hoàn chỉnh Java 17 + Maven

Demo dùng Spring Framework 6.2.16 và `ConcurrentMapCacheManager` ở chế độ **static** với cache tên `products`. Một Spring bean có method `@Cacheable` để chứng minh rằng:

1. `manager.getCache("products")` trả về vùng cache.
2. `manager.getCache("unknown")` trả `null`.
3. `cache.get("A")` ban đầu là miss.
4. Lần đầu gọi method có `@Cacheable` thông qua Spring proxy sẽ chạy thân method và put vào cache; lần thứ hai sẽ hit.
5. `cache.put` trực tiếp thay entry; method `@Cacheable` sẽ đọc chính entry đó.
6. Khi nguồn dữ liệu thay đổi mà chưa invalidate, cache vẫn có thể trả giá trị cũ.
7. `cache.evict("A")` làm lần đọc tiếp theo miss và nạp lại dữ liệu.
8. `cache.clear()` làm vùng cache rỗng trở lại.

### 6.1. Cấu trúc tệp

~~~text
get-cache-demo/
├── pom.xml
└── src/main/java/demo/GetCacheDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>get-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
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

### 6.3. src/main/java/demo/GetCacheDemo.java

~~~java
package demo;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class GetCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class AppConfig {
        @Bean
        public CacheManager cacheManager() {
            // Static mode: chỉ hỗ trợ tên "products".
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        // Giả lập nguồn dữ liệu, khác với cache.
        private final AtomicInteger sourceVersion =
                new AtomicInteger(1);
        private final AtomicInteger readCount =
                new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public String find(String sku) {
            int n = readCount.incrementAndGet();
            System.out.println("DB_READ " + sku + " #" + n);
            return "item-" + sku + "-v" + sourceVersion.get();
        }

        public void changeSourceVersion(int newVersion) {
            sourceVersion.set(newVersion);
            System.out.println("SOURCE_VERSION=" + newVersion);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             AppConfig.class)) {

            CacheManager manager =
                    context.getBean(CacheManager.class);
            CatalogService service =
                    context.getBean(CatalogService.class);

            Cache products = Objects.requireNonNull(
                    manager.getCache("products"),
                    "products cache is missing");

            System.out.println("unknownIsNull="
                    + (manager.getCache("unknown") == null));
            System.out.println("initialEntry="
                    + (products.get("A") != null));

            System.out.println("first=" + service.find("A"));
            System.out.println("second=" + service.find("A"));

            Cache.ValueWrapper wrapper = products.get("A");
            System.out.println("cachedValue="
                    + (wrapper == null ? "MISS" : wrapper.get()));

            // Cùng cache/key với @Cacheable, nhưng thao tác thủ công.
            products.put("A", "manual-A");
            System.out.println("afterPut=" + service.find("A"));

            // Đổi nguồn mà không evict: entry cũ vẫn hit.
            service.changeSourceVersion(2);
            System.out.println("beforeEvict=" + service.find("A"));

            products.evict("A");
            System.out.println("entryAfterEvict="
                    + (products.get("A") != null));
            System.out.println("afterEvict=" + service.find("A"));

            products.clear();
            System.out.println("entryAfterClear="
                    + (products.get("A") != null));
        }
    }
}
~~~

### 6.4. Chạy và stdout

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.GetCacheDemo
~~~

Các dòng do chương trình chủ động in, không tính log riêng từ Maven/JVM:

~~~text
unknownIsNull=true
initialEntry=false
DB_READ A #1
first=item-A-v1
second=item-A-v1
cachedValue=item-A-v1
afterPut=manual-A
SOURCE_VERSION=2
beforeEvict=manual-A
entryAfterEvict=false
DB_READ A #2
afterEvict=item-A-v2
entryAfterClear=false
~~~

Giải thích từng đoạn:

- **`unknownIsNull=true`:** vì `ConcurrentMapCacheManager("products")` đang chạy static mode; tên `unknown` không tồn tại.
- **`initialEntry=false`:** đã lấy được **vùng** `products`, nhưng entry key `A` chưa có.
- **`DB_READ A #1` rồi `first=item-A-v1`:** lần đầu `@Cacheable` gọi body, Spring put kết quả vào `products`.
- **`second=item-A-v1` không kèm DB_READ:** lời gọi cùng key hit, không chạy body.
- **`cachedValue=item-A-v1`:** một thao tác `Cache.get` lập trình thấy chính entry annotation đã lưu.
- **`afterPut=manual-A`:** `Cache.put` lập trình thay giá trị entry; `@Cacheable` dùng chung cache/key nên trả giá trị mới từ cache mà không chạy body.
- **`SOURCE_VERSION=2` nhưng `beforeEvict=manual-A`:** nguồn dữ liệu đổi chưa làm cache tự cập nhật.
- **`entryAfterEvict=false`:** `evict("A")` loại entry cũ trong provider đồng bộ của demo.
- **`DB_READ A #2` và `afterEvict=item-A-v2`:** lần đọc kế tiếp miss thật, body chạy và cache được nạp lại từ nguồn phiên bản 2.
- **`entryAfterClear=false`:** `clear()` loại mọi entry còn lại trong vùng `products`.

### 6.5. Điểm cần nhớ về runnable demo

`CatalogService` được lấy bằng `context.getBean(...)`, không được tạo trực tiếp bằng `new` trong `main`. Vì vậy các lời gọi `service.find(...)` đi qua Spring-managed bean và caching advice. Nếu tạo `new CatalogService()` ngoài Spring, `@Cacheable` không tự có hiệu lực.

Ví dụ dùng in-memory cache trên một JVM, không có database thật, không có TTL và không chứng minh khả năng đồng bộ đa node. Nó minh họa đúng sự khác biệt giữa **lấy vùng bằng `CacheManager.getCache`** và **truy cập entry bằng `Cache.get`**.

## 7. Kết hợp CacheManager API và caching annotation

Một lợi ích quan trọng của API lập trình là quản lý cache thủ công khi có yêu cầu cụ thể, trong khi các hoạt động thông thường vẫn dùng annotation.

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) {
    return repository.find(sku);
}
~~~

Sau một sự kiện đổi giá, một bean khác có thể invalidate:

~~~java
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("products"));
cache.evict(sku);
~~~

Hai đoạn là snippet minh họa, không độc lập. Chúng tương thích khi:

1. Cùng `CacheManager` thực sự được Spring dùng bởi method annotated.
2. Cùng tên vùng `products`.
3. Cùng key: trong getter là `#p0` (SKU), trong API là `sku`.
4. Backend có đặc tính consistent phù hợp với hệ thống.

**Không đủ** nếu chỉ cùng tên `products` nhưng hai manager khác nhau: một là Redis, một là Caffeine local. Chúng có thể hoàn toàn không chia sẻ entry. Với nhiều `CacheManager` bean, nên dùng `@Qualifier` hoặc tên bean rõ ràng thay vì injection mơ hồ.

### 7.1. Cẩn trọng khi key do Spring tạo mặc định

Nếu getter không chỉ định `key`, Spring thường dùng `SimpleKeyGenerator`:

| Số tham số method | Key mặc định thường dùng |
| --- | --- |
| Không có tham số | `SimpleKey.EMPTY` |
| Một tham số khác `null` | Chính tham số đó |
| Nhiều tham số | `SimpleKey` chứa các tham số |

Nếu method có hai tham số (`tenant`, `sku`) và bạn evict thủ công bằng riêng `sku`, entry cũ có thể **không bị xóa** do key thực tế khác. Cách an toàn là chủ động chỉ định cùng key expression, hoặc dùng một `KeyGenerator` dùng chung/thiết kế một key class có semantics ổn định.

Ví dụ một getter có:

~~~java
@Cacheable(cacheNames = "products", key = "#p0 + ':' + #p1")
public Product find(String tenant, String sku) {
    return repository.find(tenant, sku);
}
~~~

Đây là snippet minh họa; code evict programmatically cần dùng **đúng chuỗi `tenant + ":" + sku`** và đúng manager. Phải cân nhắc va chạm ký tự phân cách, khả năng chuẩn hóa, tenant isolation và serializer của provider.

### 7.2. Có nên luôn gọi API trực tiếp thay @Cacheable?

Không. Nếu logic đơn giản là cache kết quả khi cùng method được gọi nhiều lần, `@Cacheable` thường dễ đọc, dễ kiểm thử và tránh trùng lặp boilerplate. API lập trình hữu ích khi muốn:

- Kiểm tra/truy cập entry tại thời điểm tùy chọn.
- Chủ động warm-up một tập key đã biết.
- Xóa một key do event handler nhận được.
- Quản trị cache hoặc tích hợp luồng không đi qua annotation.
- Tạo cơ chế cache-aside cụ thể có kiểm soát.

Không nên **vừa** thao tác cache thủ công trong chính thân phương thức `@Cacheable`, **vừa** để interceptor tự put cùng entry nếu không có lý do rõ ràng: dễ tạo hai lần ghi, thời điểm không nhất quán hoặc kết quả bị overwrite.

## 8. Dùng getCache trong một Spring service thật

Cách inject đơn giản khi ứng dụng chỉ có một cache manager:

~~~java
@Service
public class ProductCacheMaintenance {
    private final CacheManager cacheManager;

    public ProductCacheMaintenance(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    public void invalidateProduct(String sku) {
        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("products"),
                "products cache is not configured");
        cache.evict(sku);
    }
}
~~~

Đây là snippet tích hợp, **không phải file độc lập**: cần import `@Service`, `CacheManager`, `Cache`, `Objects` và cấu hình Spring. Constructor injection giúp dependency tường minh, test thuận tiện và tránh lookup ở lúc object chưa sẵn sàng.

Nếu có hai manager:

~~~java
public ProductCacheMaintenance(
        @Qualifier("redisCacheManager") CacheManager cacheManager) {
    this.cacheManager = cacheManager;
}
~~~

Snippet này mô tả cách chọn đúng bean khi có `redisCacheManager` được cấu hình. Cần giữ annotation `@Cacheable(cacheManager = "redisCacheManager", ...)` và đường lập trình nhất quán nếu cùng làm việc với vùng đó.

### Có cần gọi getCache một lần rồi giữ Cache mãi?

Không có câu trả lời chung cho mọi provider. Một số manager cung cấp đối tượng `Cache` ổn định; một số có thể reconfigure/reset/swap wrapper theo lifecycle. Nếu muốn giữ field `Cache` để tối ưu lookup, phải hiểu hợp đồng manager/provider và vòng đời của ứng dụng. Trong code quản trị bình thường, gọi `getCache(name)` lúc thao tác thường đơn giản hơn, và chi phí lookup tên cache thường nhỏ so với I/O backend.

### Dùng ApplicationContext.getBean thay CacheManager.getCache?

Đó là hai API khác nhau: `ApplicationContext.getBean(CacheManager.class)` lấy **bean cache manager** từ Spring; `cacheManager.getCache("products")` lấy **vùng cache** bên trong manager. Đừng nhầm hai mức này.

## 9. Các trường hợp dễ sai khi truy cập cache bằng lập trình

### 9.1. Tên cache gõ sai hoặc dynamic creation không kiểm soát

Một manager cho phép tạo vùng theo tên bất kỳ có thể vô tình biến typo thành vùng cache mới. Khi cache name xuất phát từ input request, có thể gây phình số vùng cache, tốn bộ nhớ/connection và làm khó vận hành.

**Giải pháp:** dùng tên hằng, cấu hình allowlist, validate đầu vào hoặc định tuyến bằng `CacheResolver` có kiểm soát. Không dùng input tenant chưa xác thực ghép thẳng thành tên cache.

### 9.2. Không phân biệt miss và cached-null

Code kiểu:

~~~java
if (cache.get("A", String.class) == null) {
    // Kết luận chắc chắn không có mapping: SAI.
}
~~~

có thể sai khi provider cho phép lưu cached-null. Nếu cần phân biệt, dùng `Cache.ValueWrapper` hoặc một kết quả typed mô hình hóa trạng thái absent/present rõ ràng.

### 9.3. Dùng sai key so với @Cacheable

Các annotation cache có thể dùng SpEL, `KeyGenerator` hoặc default `SimpleKeyGenerator`. API trực tiếp không tự áp dụng `key = "... "` của một method khác. **Bạn tự chịu trách nhiệm** tạo chính xác object key khi gọi `cache.get/evict/put`.

### 9.4. Tự tin rằng getCache() luôn trả non-null

Javadoc cho phép `null`. Trong static manager hoặc manager thiếu cấu hình, `getCache` có thể trả `null`. Đừng để exception `NullPointerException` che lấp lỗi thiếu cache. Fail fast với thông báo cụ thể.

### 9.5. Tưởng lấy Cache là đã có dữ liệu

`CacheManager.getCache("products")` trả cache object; nó không có nghĩa `products.get("A")` hit. Hai thao tác dùng hai cấp namespace riêng.

### 9.6. Gọi clear làm ảnh hưởng quá rộng

`cache.clear()` xóa mọi entry của vùng đó. Nếu cache chứa dữ liệu của nhiều tenant mà không tách namespace, thao tác này có thể tạo miss hàng loạt. Ưu tiên `evict(key)` khi biết chính xác key bị thay đổi.

### 9.7. Bỏ qua transaction và concurrency

Nếu DB transaction chưa commit, một request đọc có thể miss sau eviction rồi nạp lại giá cũ vào cache. Bản thân `getCache` không cung cấp transaction hoặc locking. Cần thiết kế invalidation sau commit nếu ứng dụng yêu cầu; đồng thời cân nhắc cache provider, race giữa readers/writers và TTL.

### 9.8. Bỏ qua tính chất đa instance

`ConcurrentMapCacheManager` trên hai JVM tạo **hai cache local riêng**. Instance A gọi `cache.evict("A")` không tự loại entry tương ứng trên instance B. Muốn chia sẻ hoặc phân phối eviction, cần thiết kế backend chung/đồng bộ phù hợp.

### 9.9. Không xử lý lỗi backend

Không tìm được vùng cache (`getCache == null`) khác với lấy được cache nhưng backend Redis mất kết nối khi `get/put/evict`. Hãy phân biệt lỗi cấu hình, lỗi nghiệp vụ, lỗi timeout và lỗi provider. Tùy nhu cầu, có chính sách degrade/retry/alert rõ ràng; không âm thầm bỏ qua eviction lỗi nếu stale data gây hại.

## 10. Bài kiểm tra hành vi

Dưới đây là checklist test có giá trị hơn việc chỉ so sánh chuỗi trả về:

| Tình huống | Thiết lập | Điều cần xác minh |
| --- | --- | --- |
| Vùng đã cấu hình | Manager static chứa `products` | `getCache("products") != null` |
| Vùng không có | Manager static không chứa `unknown` | `getCache("unknown") == null` |
| Tên cache dynamic | Manager dynamic trống | Có thể tạo vùng mới khi `getCache(name)` |
| Entry miss | Cache tồn tại, key `A` vắng mặt | `cache.get("A") == null` |
| Entry chứa null | Provider cho phép cached-null | Non-null `ValueWrapper`, nhưng `wrapper.get()==null` |
| Ghi thủ công | `cache.put("A","v1")` | Lookup entry A trả `v1` |
| Evict | A và B đang có | `evict("A")` chỉ loại A; B còn |
| Clear | A và B đang có | `clear()` loại các entry của cache đó |
| Kết hợp annotation | `@Cacheable` và API cùng manager/key | Hai đường nhìn thấy cùng entry |
| Khác manager | Annotation dùng Redis, API dùng local | Không mặc định chia sẻ entry |
| Concurrency | Nhiều thread cùng miss | Kiểm chứng tải backend, race và provider semantics |

Có thể dùng `ConcurrentMapCacheManager("products")` trong integration test để nhận biết typo nhờ static mode. Với test lỗi nhất quán/phân tán, cần chạy với provider gần production, vì in-memory manager không thể chứng minh behavior đa node/TTL/transaction của Redis.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `cacheManager.getCache("products")` có trả dữ liệu sản phẩm A không?

**Trả lời:** Không. Nó trả về vùng `Cache` có tên `products` hoặc `null`. Muốn lấy entry A, dùng `cache.get("A")`.

**Câu 2.** Nếu `getCache("products")` trả `null`, có thể kết luận sản phẩm A không có trong cache không?

**Trả lời:** Không nên mô tả như vậy. Vấn đề trước mắt là **không lấy được vùng cache**; chưa có object để tra entry A. Phải xử lý lỗi cấu hình/vùng không tồn tại trước.

**Câu 3.** Một manager không khai báo trước tên `temp` có luôn trả `null` khi `getCache("temp")` không?

**Trả lời:** Không. Với dynamic `ConcurrentMapCacheManager()`, vùng `temp` có thể được tạo lazy. Với static `ConcurrentMapCacheManager("products")`, tên ngoài danh sách trả `null`.

**Câu 4.** Khi `cache.get("A", String.class)` trả `null`, chắc chắn entry A vắng mặt không?

**Trả lời:** Chưa chắc. Typed get có thể trả `null` cả khi entry vắng mặt và khi cached-null được hỗ trợ; muốn phân biệt dùng `ValueWrapper`.

**Câu 5.** Khi `@Cacheable` dùng `key="#p0"`, API `cache.evict(sku)` có xóa cùng entry không?

**Trả lời:** Có **nếu** hai đường thao tác dùng cùng manager, cùng tên cache và cùng object key `sku`. Nếu khác manager, namespace hoặc cách sinh key, không có bảo đảm.

**Câu 6.** Gọi `cache.put` bằng API có cập nhật database không?

**Trả lời:** Không. `Cache.put` chỉ ghi mapping trong cache. Muốn sửa dữ liệu gốc, cần gọi repository/service nghiệp vụ.

**Câu 7.** `getCacheNames()` có thể dùng để ủy quyền một user truy cập tenant khác không?

**Trả lời:** Không. Đây là API liệt kê tên cache manager biết, không phải cơ chế xác thực/phân quyền. Isolation phải được thiết kế ở boundary dữ liệu/tenant và quyền truy cập.

## 12. Kết luận

`CacheManager.getCache(name)` là cửa vào **vùng cache** trong Spring Cache. Cách suy luận đúng luôn là:

~~~text
CacheManager
    |
    +-- getCache(cacheName)
              |
              +-- null -> vùng cache không tồn tại/không tạo được
              |
              +-- Cache object
                    |
                    +-- get(key)   -> tìm entry, có thể miss
                    +-- put(key)   -> ghi/thay entry
                    +-- evict(key) -> loại một entry
                    +-- clear()    -> yêu cầu xóa mọi entry
~~~

Hãy kiểm tra `null` ở cấp **cache**, phân biệt `ValueWrapper` và cached-null ở cấp **entry**, chọn đúng manager/cache/key, và hiểu provider có thể tự tạo cache theo tên hay không. Khi kết hợp API lập trình với `@Cacheable`, các thao tác chỉ tác động tới nhau khi cùng tham chiếu một vùng cache thực tế và cùng quy tắc key.

## Tài liệu chính thức

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Cache Annotation Configuration: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- `CacheManager` Javadoc (Spring 6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/CacheManager.html
- `Cache` Javadoc (Spring 6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/Cache.html
- `ConcurrentMapCacheManager` Javadoc (Spring 6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
