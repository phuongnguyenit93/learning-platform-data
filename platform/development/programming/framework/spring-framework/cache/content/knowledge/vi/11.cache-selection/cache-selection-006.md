# SimpleCacheManager với danh sách cache có sẵn

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích vai trò của `SimpleCacheManager` trong Spring Cache, tự tạo và đăng ký danh sách `Cache` theo tên cố định, phân biệt **đối tượng cache**, **vùng cache** và **khóa của entry**, hiểu vòng đời khởi tạo manager, sử dụng đúng `@Cacheable`/`@CacheEvict` với các vùng đã đăng ký, và nhận biết khi nào nên chọn manager khác.

Trong nhóm **Chọn vùng cache**, điểm cốt lõi là: `SimpleCacheManager` quản lý **một tập các đối tượng `Cache` được cung cấp sẵn**. Ứng dụng quyết định những vùng nào tồn tại và cách tạo từng vùng. Manager chỉ lập danh mục để các thao tác cache tìm đúng vùng theo tên.

## 1. Ba tầng tên và trách nhiệm dễ nhầm

Giả sử ứng dụng có hai loại dữ liệu là sản phẩm và danh mục:

```text
Spring caching interceptor (@Cacheable / @CacheEvict)
                |
                v
          CacheManager
                |
         getCache("products") -----> Cache "products"
                |                    |-- key "42" -> Product #42
         getCache("categories") --> Cache "categories"
                                     |-- key "42" -> Category #42
```

Các khái niệm:

- **`CacheManager`:** thành phần tìm hoặc quản lý cache theo tên, đặc biệt qua `getCache(String name)` và `getCacheNames()`.
- **`Cache` (vùng/cache region):** kho chứa các cặp **key → value** trong một namespace, có tên xác định bằng `getName()`; ví dụ `products` và `categories`.
- **Cache key:** định danh một entry **bên trong** một vùng, ví dụ `"42"`. Hai vùng khác nhau có thể có cùng key mà không xung đột.
- **Cache value:** nội dung được giữ lại để lần đọc tiếp theo có thể bỏ qua phép tính/truy vấn tốn kém.
- **Backend/provider:** cách dữ liệu thực sự được giữ, hết hạn, loại bỏ, chia sẻ hoặc serialize (ví dụ `ConcurrentMapCache`, Caffeine, Redis).

Ví dụ `products["42"]` và `categories["42"]` không trùng nhau vì khác vùng cache, dù key text giống hệt. Nếu hai service dùng cùng tên vùng và cùng key nhưng kiểu giá trị khác nhau, chúng có thể va chạm về dữ liệu. Do đó **chọn vùng** và **thiết kế key** là hai quyết định riêng phải thống nhất.

## 2. SimpleCacheManager là gì?

`org.springframework.cache.support.SimpleCacheManager` là một triển khai `CacheManager` của Spring Framework, mở rộng `AbstractCacheManager`, làm việc với **collection các đối tượng `Cache` đã được chỉ định** bằng:

```java
SimpleCacheManager manager = new SimpleCacheManager();
manager.setCaches(List.of(productsCache, categoriesCache));
```

Đoạn trên chỉ minh họa: `productsCache` và `categoriesCache` phải là các đối tượng `org.springframework.cache.Cache` được tạo trước đó; cần import `java.util.List`. Điểm khác biệt nằm ở chỗ bạn truyền **Cache instances**, không chỉ truyền tên.

Những hành vi quan trọng:

1. **Danh sách tĩnh khi khởi tạo:** `SimpleCacheManager` tải các cache đã cung cấp và lập ánh xạ tên → đối tượng `Cache`. Nó thích hợp cho tập vùng được biết trước.
2. **Không tự sinh vùng mới theo tên chưa đăng ký:** sau khi khởi tạo, `getCache("unknown")` trả về `null` nếu không có cache đó; việc gọi một phương thức có annotation tham chiếu vùng không tồn tại sẽ khiến quá trình resolve cache thất bại.
3. **Không quyết định chính sách TTL/giới hạn bộ nhớ:** manager không tự thêm expiry, persistence hoặc distributed semantics cho `Cache` mà nó nắm giữ. Hành vi thuộc về từng triển khai `Cache`.
4. **Có thể nhận cache đã là bean:** hai đối tượng `Cache` có thể được cấu hình độc lập rồi đưa vào manager qua DI, giữ đúng tên và cấu hình đã khai báo.
5. **Phù hợp demo, test và ứng dụng có số cache ít, ổn định:** quản lý đơn giản, dễ kiểm chứng những tên hợp lệ.

Tên vùng thực tế là tên của đối tượng `Cache`, chẳng hạn `new ConcurrentMapCache("products").getName()` trả `"products"`. **Tên bean** như `productStore` là để Spring DI phân biệt bean; nó **không tự đổi** tên vùng thành `productStore`.

## 3. Cấu hình đúng: tạo cache trước, đăng ký bằng setCaches

Ví dụ Java config tạo hai vùng bộ nhớ. Nếu dùng trong một ứng dụng Spring Boot đã có Gradle và Java 17+, chỉ cần starter Spring Cache để thực hành.

**File `src/main/java/example/simplecache/CacheConfiguration.java`:**

```java
package example.simplecache;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.support.SimpleCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    // Spring bean name = productStore; actual cache name = products.
    @Bean("productStore")
    Cache productCache() {
        return new ConcurrentMapCache("products");
    }

    @Bean("categoryStore")
    Cache categoryCache() {
        return new ConcurrentMapCache("categories");
    }

    @Bean
    CacheManager cacheManager(
            @Qualifier("productStore") Cache products,
            @Qualifier("categoryStore") Cache categories) {

        SimpleCacheManager manager = new SimpleCacheManager();
        manager.setCaches(List.of(products, categories));
        return manager;
    }
}
```

Giải thích:

- `@EnableCaching` bật việc xử lý các annotation cache, thường qua Spring AOP proxy.
- `@Bean("productStore")` và `@Bean("categoryStore")` tạo **đối tượng `Cache`** do Spring quản lý. Bản thân chúng là hai cache riêng, đã có tên `products` và `categories`.
- `@Qualifier` chọn chính xác hai cache bean cần đưa vào manager, tránh nhập nhằng vì có nhiều bean cùng interface `Cache`.
- `manager.setCaches(List.of(products, categories))` khai báo danh mục vùng mà manager cung cấp. Đối số là collection các cache, không phải collection chuỗi tên.
- `CacheManager` là interface được inject cho các lớp cần truy cập cache qua code; annotation `@Cacheable(cacheNames = "products")` sẽ tìm vùng qua manager này.

**Lưu ý vòng đời:** `SimpleCacheManager` thực thi cơ chế `InitializingBean` từ `AbstractCacheManager`. Khi được trả về làm Spring `@Bean`, container gọi callback khởi tạo thích hợp (trong đó có `afterPropertiesSet()`) để tải danh sách vùng. Không cần tự gọi `afterPropertiesSet()` bên trong `@Bean` trên. Nếu tự tạo manager bằng `new` **ngoài** Spring container, phải tự hoàn tất bước khởi tạo (ví dụ `manager.afterPropertiesSet()`) trước khi mong đợi `getCache(...)` trả về danh mục đã cấu hình.

### Cấu hình nhanh không cần mỗi Cache là một bean

Nếu không cần cấu hình/inject từng cache riêng:

```java
@Bean
CacheManager cacheManager() {
    SimpleCacheManager manager = new SimpleCacheManager();
    manager.setCaches(List.of(
            new ConcurrentMapCache("products"),
            new ConcurrentMapCache("categories")
    ));
    return manager;
}
```

Đây là **biến thể thay thế** cho `cacheManager` ở trên, không sử dụng đồng thời hai `@Bean` cùng tên trong một cấu hình. Đoạn code cần các import `@Bean`, `CacheManager`, `SimpleCacheManager`, `List`, `ConcurrentMapCache` đã thấy ở ví dụ trước. Hai cách có cùng hợp đồng vùng; cách đầu phù hợp khi muốn chủ động tái sử dụng/tiêm các cache instances đã có.

## 4. Ví dụ chạy được trên Spring Boot (Java 17+)

Dùng file `CacheConfiguration.java` ở mục 3 cùng hai class sau. Mọi file nằm trong package `example.simplecache`, để component scanning của `@SpringBootApplication` phát hiện chúng.

Trong dự án Spring Boot Gradle có sẵn, bổ sung dependency sau nếu chưa có (giữ nguyên plugin/version và dependencies khác của dự án):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
```

**File `src/main/java/example/simplecache/CatalogService.java`:**

```java
package example.simplecache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger productLoads = new AtomicInteger();
    private final AtomicInteger categoryLoads = new AtomicInteger();

    @Cacheable(cacheNames = "products", key = "#p0")
    public String product(String id) {
        System.out.println("LOAD_PRODUCT #" + productLoads.incrementAndGet());
        return "Product-" + id;
    }

    @Cacheable(cacheNames = "categories", key = "#p0")
    public String category(String id) {
        System.out.println("LOAD_CATEGORY #" + categoryLoads.incrementAndGet());
        return "Category-" + id;
    }

    @CacheEvict(cacheNames = "products", key = "#p0")
    public void evictProduct(String id) {
        // Chỉ xóa entry trong products, không đụng tới categories.
    }
}
```

Bộ đếm `AtomicInteger` chỉ tăng nếu thân phương thức đọc chạy, tức là khi cache miss hoặc khi caching không được áp dụng. Trả về chuỗi cố định để cô lập vấn đề chọn vùng khỏi phụ thuộc database.

**File `src/main/java/example/simplecache/SimpleCacheDemoApplication.java`:**

```java
package example.simplecache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SimpleCacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SimpleCacheDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CatalogService catalog, CacheManager manager) {
        return args -> {
            System.out.println("products exists = " +
                    (manager.getCache("products") != null));
            System.out.println("categories exists = " +
                    (manager.getCache("categories") != null));
            System.out.println("prices exists = " +
                    (manager.getCache("prices") != null));

            System.out.println("product-1 = " + catalog.product("42"));
            System.out.println("product-2 = " + catalog.product("42"));
            System.out.println("category-1 = " + catalog.category("42"));
            System.out.println("category-2 = " + catalog.category("42"));

            catalog.evictProduct("42");
            System.out.println("product-3 = " + catalog.product("42"));
            System.out.println("category-3 = " + catalog.category("42"));
        };
    }
}
```

Chạy trong thư mục dự án:

```bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
```

Các dòng `System.out` do demo tạo ra theo đúng thứ tự, không tính log khởi động Spring Boot/Gradle:

```text
products exists = true
categories exists = true
prices exists = false
LOAD_PRODUCT #1
product-1 = Product-42
product-2 = Product-42
LOAD_CATEGORY #1
category-1 = Category-42
category-2 = Category-42
LOAD_PRODUCT #2
product-3 = Product-42
category-3 = Category-42
```

Diễn giải:

1. `getCache("products")` và `getCache("categories")` đều tìm thấy đối tượng đã khai báo; `getCache("prices") == null` vì `prices` không có trong danh sách.
2. `catalog.product("42")` lần đầu miss ở vùng `products` nên in `LOAD_PRODUCT #1`; lần hai hit nên không chạy thân method.
3. `catalog.category("42")` cũng dùng key `"42"` nhưng ở **vùng `categories`**. Vì hai vùng độc lập, lần đầu vẫn miss (in `LOAD_CATEGORY #1`); lần hai hit.
4. `catalog.evictProduct("42")` chỉ loại `products["42"]`. Lần đọc sản phẩm sau đó miss và in `LOAD_PRODUCT #2`. Entry `categories["42"]` vẫn còn nên lần gọi category cuối vẫn hit.
5. Việc trả về cùng chuỗi `Product-42` trước và sau eviction là do nguồn giả lập không đổi; **số lần nạp nguồn** mới là bằng chứng phân biệt hit/miss.

**Vì sao đây là demo chạy được?** Hai tên vùng và các key được định nghĩa nhất quán; các method `public` được gọi từ bean `CommandLineRunner` sang Spring bean `CatalogService` nên đi qua caching proxy; không có request đồng thời hay dịch vụ ngoài. Toàn bộ ba file Java phải nằm trong đúng thư mục/package, và `bootRun` cần một dự án Spring Boot có plugin Gradle phù hợp. Đây không phải một file Java độc lập có thể chạy bằng `javac` mà không có Spring.

## 5. Khác biệt với ConcurrentMapCacheManager và CaffeineCacheManager

Cả ba đều triển khai `CacheManager`, nhưng **khác cách tạo và quản lý vùng**.

| Manager | Cách định nghĩa vùng | Đặc điểm |
| --- | --- | --- |
| `SimpleCacheManager` | Truyền collection các **`Cache` instances** bằng `setCaches(...)`. | Hữu ích khi đã có đối tượng cache và muốn lựa chọn chính xác vùng nào được cung cấp. |
| `ConcurrentMapCacheManager` | Có thể quản lý cache theo tên; ở chế độ động, có thể tạo `ConcurrentMapCache` cho tên mới; có thể cấu hình tên cố định. | Gọn khi tất cả vùng đều là `ConcurrentMapCache`. |
| `CaffeineCacheManager` | Có thể khai báo cache names hoặc tạo theo nhu cầu; sử dụng Caffeine làm backend. | Thích hợp khi cần TTL/maximum size/đặc tính Caffeine. |

`SimpleCacheManager` không có ý nghĩa “luôn tốt hơn manager chuyên dụng”. Nếu tất cả cache là local `ConcurrentMapCache` và không cần cấu hình từng instance, `ConcurrentMapCacheManager` có thể ngắn gọn hơn. Nếu cần expiration hoặc size limit, chọn backend có các đặc tính đó, chẳng hạn Caffeine.

### Động hay tĩnh là khác biệt quan trọng

- **Tĩnh:** danh sách vùng do ứng dụng công bố trước; một lỗi chính tả tên vùng sẽ lộ ra khi resolve, thay vì tự tạo vùng có tên sai.
- **Động:** một số manager có thể sinh cache cho tên chưa gặp (nếu cấu hình cho phép), hữu ích với workload phù hợp nhưng cũng có thể che giấu lỗi đặt tên.

Vì vậy, danh sách vùng tĩnh là lựa chọn tốt khi muốn có một **hợp đồng tên cache** rõ ràng, được kiểm soát và kiểm thử. Nó không đồng nghĩa “các entry được sinh sẵn”: vùng `products` có thể tồn tại nhưng **trống**, và chỉ có entry sau một lần put/miss.

### Cache instance có sẵn không bắt buộc là ConcurrentMapCache

`SimpleCacheManager.setCaches(...)` nhận các đối tượng implement `Cache`. Về nguyên tắc, chúng có thể là adapter của các backend khác nhau nếu ứng dụng tự tạo đúng cách; tuy nhiên điều đó không tự mang lại distributed invalidation, cùng TTL hay cùng serializer giữa các backend. Khi kết hợp nhiều backend, cần kiểm tra cách mỗi cache xử lý `null`, đồng thời, expiry và lỗi.

Ví dụ muốn một vùng dùng Caffeine có TTL, cần tạo **Caffeine-backed `Cache`** với cấu hình Caffeine tương ứng rồi mới đưa vào manager. `SimpleCacheManager` sẽ sử dụng instance ấy, chứ không “nâng cấp” một `ConcurrentMapCache` thành Caffeine chỉ vì có thêm dependency.

## 6. Danh sách cache có sẵn và vòng đời khởi tạo

Khi Spring quản lý bean:

```text
@Configuration tạo các @Bean Cache
           ↓
Tạo SimpleCacheManager và setCaches(collection)
           ↓
Spring container khởi tạo bean (InitializingBean)
           ↓
AbstractCacheManager tải danh mục cache và ánh xạ theo getName()
           ↓
@Cacheable / @CachePut / @CacheEvict resolve cache theo tên
```

`SimpleCacheManager` kế thừa cơ chế `loadCaches()`/`afterPropertiesSet()` của `AbstractCacheManager`. **Trong ứng dụng Spring, hãy để container chạy khởi tạo bean**. Với object tạo thủ công ngoài container, cần chủ động gọi `afterPropertiesSet()` sau `setCaches`.

Đừng coi `setCaches(...)` là API để cập nhật danh sách cache ở mỗi request. Nó mô tả **tập cache đầu vào** cho manager; mô hình thông thường là cấu hình xong trong giai đoạn startup. Thay đổi cấu trúc cache runtime cần xác định lại hợp đồng/lifecycle và lựa chọn manager thích hợp.

Hai kiểm tra hữu ích lúc khởi động:

```java
// Ví dụ trong một nơi đã được inject CacheManager:
boolean productsPresent = manager.getCache("products") != null;
boolean categoryPresent = manager.getCacheNames().contains("categories");
```

`manager` ở đây là biến `CacheManager` đã tồn tại từ ví dụ trước. `getCacheNames()` liệt kê **tên vùng**, không liệt kê các entry/key hiện có bên trong từng vùng. Không dựa vào thứ tự tên khi so sánh, nếu ứng dụng không định nghĩa yêu cầu thứ tự rõ ràng.

## 7. Điều gì xảy ra nếu tên cache không tồn tại?

Với demo:

```java
Cache unknown = manager.getCache("prices"); // null
```

`prices` chưa được đăng ký. Nếu một method có `@Cacheable(cacheNames = "prices")` mà chỉ có `SimpleCacheManager` này phục vụ, cache resolution thường thất bại khi method được gọi qua proxy; không có cam kết Spring sẽ tự tạo vùng mới.

Ví dụ lỗi đặt tên:

```java
// Sai với cấu hình demo: "product" khác "products".
@Cacheable(cacheNames = "product", key = "#p0")
public String wrongName(String id) {
    return "Product-" + id;
}
```

Cú pháp Java minh họa nằm trong một Spring bean tương ứng. Đừng sửa manager bằng cách tạo thêm một vùng tên sai chỉ để lỗi biến mất: xác nhận tên nào là hợp đồng chuẩn rồi dùng nhất quán ở annotation, cấu hình và quan sát vận hành.

Có hai lớp lỗi khác:

- **Không có tên vùng:** `getCache(name)` trả `null`; Spring không tìm được vùng để thực hiện operation.
- **Có vùng nhưng không có entry:** `getCache(name)` trả một `Cache` hợp lệ, nhưng `cache.get(key)` miss. Đây là trường hợp bình thường để `@Cacheable` tính rồi put giá trị.

Phân biệt hai trường hợp này sẽ tiết kiệm nhiều thời gian debug: **missing region** là vấn đề cấu hình; **missing entry** là tình trạng dữ liệu/TTL/invalidation.

## 8. Tổ chức vùng cache có chủ đích

Đặt tên theo **hợp đồng dữ liệu**, không theo tên method ngẫu nhiên:

- `productsById`: dữ liệu sản phẩm theo ID.
- `categoriesById`: dữ liệu danh mục theo ID.
- `productSearchResults`: kết quả tìm kiếm, có key phức hợp gồm filter/sort/page.
- `exchangeRates`: bảng tỷ giá, có chính sách expiry phù hợp.

Những điều cần quyết định với mỗi vùng:

| Câu hỏi | Ý nghĩa triển khai |
| --- | --- |
| Vùng này chứa loại dữ liệu nào? | Tránh key giống nhau nhưng value khác kiểu hoặc khác ngữ nghĩa. |
| Key được tạo từ những tham số nào? | Không gộp kết quả khác tenant/locale/quyền; giữ cách tạo key thống nhất. |
| Ai đưa dữ liệu vào? | `@Cacheable` sau miss, `@CachePut` hoặc thao tác `Cache.put(...)` trực tiếp. |
| Khi nào dữ liệu bị xóa? | `@CacheEvict`, tác vụ invalidation, TTL/size policy của backend nếu có. |
| Cần thời hạn sống hay giới hạn bộ nhớ? | `ConcurrentMapCache` không có TTL/maximum size mặc định; cân nhắc Caffeine/Redis hoặc backend phù hợp. |
| Một hay nhiều instance ứng dụng? | Cache local trong từng JVM không tự đồng bộ với instance khác. |
| Có cần chia sẻ dữ liệu theo tenant/user? | Key và kiểm tra quyền cần nhất quán; đừng coi cache là cơ chế phân quyền. |

Thực hành tốt là lưu tên vùng thành hằng số có ý nghĩa nếu nhiều service dùng chung, nhưng annotation và `SimpleCacheManager` vẫn phải resolve đúng **chuỗi tên cuối cùng**. Với `@CacheConfig(cacheNames = "products")` ở cấp class, có thể giảm lặp tên cho các operation của class; nó không tự tạo vùng cache.

## 9. Sai lầm thường gặp

1. **Truyền tên string vào `setCaches`:** API yêu cầu collection các `Cache`, ví dụ `List.of(new ConcurrentMapCache("products"))`, không phải `List.of("products")`.
2. **Nhầm bean name và cache name:** bean `productStore` có thể chứa `ConcurrentMapCache("products")`; annotation phải dùng `products`.
3. **Chưa khởi tạo manager tạo ngoài Spring:** gọi `setCaches` nhưng bỏ qua `afterPropertiesSet` sẽ không có bảo đảm danh mục đã sẵn sàng cho lookup.
4. **Nhầm vùng với entry:** `getCache("products") != null` chỉ xác minh vùng tồn tại; không chứng minh có key `"42"` bên trong.
5. **Sai chính tả cache name:** `products` và `product` là hai tên khác nhau; manager tĩnh không tự tạo tên thiếu.
6. **Quên `@EnableCaching` hoặc gọi nội bộ `this.method()`:** cache annotation không được áp dụng như mong đợi ở chế độ proxy mặc định.
7. **Tưởng có TTL mặc định:** `SimpleCacheManager` chỉ điều phối; `ConcurrentMapCache` không tự hết hạn entry theo thời gian.
8. **Chọn quá nhiều vùng không có hợp đồng:** khó biết nên evict vùng nào khi dữ liệu nguồn đổi, dễ làm stale dữ liệu hoặc tăng tải.
9. **Dùng vùng local trong nhiều replica rồi chờ đồng bộ:** evict ở JVM A không mặc định loại entry của JVM B.
10. **Dùng `@Cacheable` và `@CachePut` không đồng nhất về tên/key:** cập nhật một vùng, đọc một vùng khác thì cache cũ còn tồn tại.

## 10. Bài tập kiểm chứng

Sau khi chạy ví dụ ở mục 4:

1. Gọi `manager.getCacheNames()`, in từng tên để thấy chính xác các vùng do bạn đăng ký. Đừng giả định danh sách này chứa entry keys.
2. Thêm một vùng `"prices"` bằng `new ConcurrentMapCache("prices")` vào danh sách `setCaches(...)`, chạy lại process. Khi đó dòng `prices exists` đổi từ `false` sang `true`.
3. Chuyển annotation `@Cacheable(cacheNames = "products")` sang `"product"` (bỏ chữ `s`) và thử gọi: quan sát lỗi resolve vùng, sau đó khôi phục tên đúng.
4. Dùng cùng key `"42"` cho hai service như ví dụ để chứng minh vùng `products` và `categories` không ảnh hưởng lẫn nhau.
5. Gọi `evictProduct("42")`, chứng minh chỉ `LOAD_PRODUCT` tăng còn `LOAD_CATEGORY` vẫn giữ nguyên; giải thích vì sao.
6. Tạo một `SimpleCacheManager` **ngoài** Spring container, gọi `setCaches(...)` rồi `afterPropertiesSet()` trước khi dùng `getCache`; so sánh với bean Spring được tự khởi tạo.
7. Nếu muốn TTL, thử cấu hình một backend Caffeine riêng rồi đưa cache instance ấy vào danh sách; xác nhận TTL do cache backend xử lý, không phải do `SimpleCacheManager` tự đặt.

### Checklist trước khi đưa vào dự án

- [ ] Biết rõ vùng cache cần quản lý và chọn tên duy nhất, đúng hợp đồng dữ liệu.
- [ ] Đã tạo đầy đủ **`Cache` instances**, đặt tên qua `Cache.getName()`.
- [ ] Gọi `setCaches(...)` với collection các cache đó và để Spring khởi tạo manager.
- [ ] Bật `@EnableCaching`; đảm bảo phương thức được gọi qua proxy của bean.
- [ ] Annotation dùng đúng tên vùng, đúng key schema; put/evict cùng hợp đồng với đọc.
- [ ] Biết rõ provider chịu trách nhiệm TTL/size/serialization và phạm vi local/distributed.
- [ ] Kiểm tra vùng không đăng ký bằng `getCache(name)==null` và test hit/miss độc lập giữa các vùng.

## Tài liệu chính thống

- Spring Framework — Configuring the Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — SimpleCacheManager API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/SimpleCacheManager.html
- Spring Framework — CacheManager API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/CacheManager.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
