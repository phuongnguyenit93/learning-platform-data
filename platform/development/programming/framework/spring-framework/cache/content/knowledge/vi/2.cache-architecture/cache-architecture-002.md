# CacheManager và việc tìm hoặc tạo cache theo tên

> **Ngữ cảnh:** Spring Framework Cache Abstraction · **Nhóm:** Kiến trúc. Bài này tập trung vào cách Spring xác định một *vùng cache* theo tên, vì sao một tên có thể được tạo theo nhu cầu ở một implementation nhưng trả về `null` ở implementation khác, và cách dùng hành vi đó an toàn.

## 1. `CacheManager` giải quyết vấn đề gì?

Ứng dụng thường có nhiều nhóm dữ liệu cần cache riêng: `products`, `users`, `exchangeRates`… Mỗi nhóm là một **cache region**: một không gian ánh xạ *key → value* với cấu hình và vòng đời của riêng nó. Khi mã nghiệp vụ hoặc cơ chế `@Cacheable` yêu cầu vùng `products`, cần có một thành phần tìm đúng vùng đó mà không phụ thuộc vào bộ nhớ, Caffeine, Redis hay JCache.

Spring định nghĩa giao diện `org.springframework.cache.CacheManager` làm đầu mối truy xuất **cache theo tên**. Nó **không trực tiếp quyết định** cách lưu dữ liệu, thời gian hết hạn (TTL), chính sách loại bỏ, mức chia sẻ giữa máy chủ hay khả năng tạo cache mới; các việc này thuộc implementation và nhà cung cấp cache.

Phân biệt ba cấp:

| Cấp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `CacheManager` | Bean `cacheManager` | Tìm/điều phối các vùng cache đã đặt tên |
| `Cache` (vùng) | `products` | Vùng lưu trữ có nhiều entry; được xác định bằng *cache name* |
| Entry trong `Cache` | `key = sku-42`, `value = Product` | Một phần tử bên trong vùng, được xác định bằng *cache key* |

Vì thế, `getCache("products")` là thao tác lấy **vùng** `products`, không phải thao tác lấy một sản phẩm. Sau khi nhận `Cache`, gọi `cache.get("sku-42")` mới tìm **entry** theo key.

## 2. Hợp đồng tối thiểu của API

Giao diện `CacheManager` có hai phương thức chính:

~~~java
public interface CacheManager {
    Cache getCache(String name);           // có thể trả về null
    Collection<String> getCacheNames();
}
~~~

Đây là **chữ ký rút gọn để học**: mã giao diện thật có thể kèm annotation nullability và import.

- **`getCache(String name)`**: trả về một `Cache` mang tên yêu cầu, hoặc `null` nếu không có và không thể/không được tạo. Spring cho phép một số implementation **tạo cache trễ (lazy creation)** ngay khi phương thức này được gọi. Giao diện không bảo đảm tất cả implementation đều tạo mới.
- **`getCacheNames()`**: trả về tập tên cache *manager hiện biết*. Với manager tạo động, danh sách có thể thay đổi sau những lần gọi `getCache(name)`. Không suy ra đây là danh sách đầy đủ mọi tên có thể tạo trong tương lai.
- **Không có `createCache(name)` trong `CacheManager` SPI chung.** Việc khởi tạo vùng cache được cấu hình trước, được xử lý nội bộ lúc `getCache`, hoặc được thực hiện qua API riêng của provider.

Tên cache là một phần cấu hình/contract. `products` và `product` là hai chuỗi khác nhau; viết sai tên ở manager động có thể vô tình tạo một vùng cache mới. Đừng nhầm `CacheManager` của Spring với các giao diện cùng tên thuộc thư viện cache bên dưới.

Đối tượng `Cache` mà manager trả về cung cấp các thao tác như `get(key)`, `put(key, value)`, `evict(key)`, `clear()` và `getName()`. `Cache.get(key)` trả `Cache.ValueWrapper` hoặc `null` (miss); với implementation hỗ trợ cache giá trị null, `ValueWrapper` giúp phân biệt *cache hit có giá trị null* với *cache miss*.

## 3. Diễn tiến của một yêu cầu theo tên

Ví dụ: `CacheManager.getCache("products")`.

1. Thành phần gọi (mã Java hoặc `CacheResolver` của Spring caching interceptor) yêu cầu tên `products`.
2. `CacheManager` tìm trong tập vùng đã biết hoặc hỏi provider tương ứng.
3. **Nếu đã có vùng:** trả về đối tượng `Cache` thích hợp.
4. **Nếu chưa có vùng:** implementation *có thể* tạo vùng mới (dynamic/lazy), hoặc từ chối và trả `null` (static/preconfigured).
5. Chỉ sau khi có `Cache` mới có truy xuất entry theo key (`get`, `put`, `evict`...). Tạo vùng rỗng **không có nghĩa** đã tải dữ liệu nghiệp vụ vào cache.

~~~text
Ứng dụng / @Cacheable
         |
         | yêu cầu cache name = "products"
         v
      CacheResolver (mặc định)
         |
         v
      CacheManager.getCache("products")
         |
         +-- vùng đã tồn tại ---------> Cache("products")
         |
         +-- chưa tồn tại
                |-- manager cho tạo động --> tạo vùng --> Cache("products")
                |
                +-- manager chỉ cho tên có sẵn -------> null
                                                        |
                                                      xử lý lỗi / chọn cấu hình đúng
~~~

Sơ đồ trên mô tả *cache resolution*, chưa mô tả toàn bộ vòng đời `@Cacheable`. Khi dùng annotation, Spring còn tạo key, kiểm tra hit/miss, chạy method khi miss và đưa kết quả vào cache.

## 4. Hành vi phụ thuộc implementation

| Implementation | Khi yêu cầu tên chưa được cấu hình/biết tới | Điểm cần nhớ |
| --- | --- | --- |
| `new ConcurrentMapCacheManager()` | **Tạo động** `ConcurrentMapCache` khi `getCache(name)` được gọi | Phù hợp demo/test hoặc cache bộ nhớ đơn giản; mỗi tên mới có thể sinh vùng mới |
| `new ConcurrentMapCacheManager("products", "users")` | **Trả `null`** với tên khác hai tên đã khai báo | Chế độ static giúp phát hiện lỗi chính tả, bảo vệ tập tên |
| `SimpleCacheManager` với các `Cache` được đăng ký trước | Chỉ trả các vùng đã được cấu hình | Quản lý danh sách cache được chuẩn bị từ trước |
| `CaffeineCacheManager` | Mặc định có thể tạo theo tên; khi đặt `setCacheNames(...)` thì chỉ dùng danh sách đó | Chính sách TTL/size nằm ở cấu hình Caffeine, không ở SPI chung |
| `JCacheCacheManager` / manager dựa provider ngoài | Phụ thuộc vùng mà JCache/provider đã cấu hình và khả năng lookup | Không giả định `getCache` luôn tự tạo cache ở backend |
| `CompositeCacheManager` | Thử lần lượt các manager và trả về cache đầu tiên không `null` | Nếu manager động đứng đầu, nó có thể nhận mọi tên; thứ tự rất quan trọng |

**Lưu ý:** `NoOpCacheManager` cung cấp cache không lưu dữ liệu thực; bật fallback không lưu trữ trong `CompositeCacheManager` có thể làm tên thiếu trở nên khó phát hiện. Không dùng hành vi đó để coi cache thật đã được tạo.

Với `ConcurrentMapCacheManager` và `CaffeineCacheManager`, constructor không truyền tên hoặc `setCacheNames(null)` chọn chế độ động; chỉ định danh sách tên qua constructor/setter chọn chế độ tĩnh. Không suy rộng quy tắc này sang mọi loại manager, nhất là vùng Redis/JCache hoặc cache phân tán.

## 5. Ví dụ Java 17+ chạy được: động so với tĩnh

Ví dụ dùng **Spring Framework 6.2.x**, chỉ cần thư viện `spring-context`; không khởi động Spring Boot hay cơ sở dữ liệu. Tạo dự án Gradle đơn giản với hai tệp sau.

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.CacheManagerLookupDemo'
}
~~~

**`src/main/java/demo/CacheManagerLookupDemo.java`:**

~~~java
package demo;

import java.util.Objects;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;

public class CacheManagerLookupDemo {
    public static void main(String[] args) {
        CacheManager dynamic = new ConcurrentMapCacheManager();

        // Ban đầu chưa có vùng "products".
        System.out.println(dynamic.getCacheNames().contains("products"));

        // Lookup lần đầu tạo vùng "products" trong chế độ dynamic.
        Cache products = Objects.requireNonNull(dynamic.getCache("products"));
        products.put("sku-42", "Keyboard");

        System.out.println(dynamic.getCacheNames().contains("products"));
        System.out.println(products.get("sku-42", String.class));
        System.out.println(products == dynamic.getCache("products"));

        // Chế độ static chỉ cho phép các tên đã khai báo.
        CacheManager fixed = new ConcurrentMapCacheManager("products");
        System.out.println(fixed.getCache("unknown") == null);
    }
}
~~~

Trong thư mục dự án có Gradle (hoặc wrapper tương ứng), chạy:

~~~bash
gradle run --quiet
~~~

**Năm dòng stdout của chương trình** (không tính thông báo Gradle ngoài stdout ứng dụng):

~~~text
false
true
Keyboard
true
true
~~~

Giải thích lần lượt:

1. Manager động ban đầu chưa biết `products`.
2. Lần `getCache("products")` tạo và đăng ký vùng mới.
3. Entry có key `sku-42` đọc lại được giá trị vừa `put`.
4. Lấy lại cùng tên trả chính vùng `ConcurrentMapCache` đã tạo trong **implementation của ví dụ này**; không suy ra mọi provider phải bảo đảm so sánh tham chiếu `==` như vậy.
5. Manager tĩnh trả `null` cho `unknown`. Nó **không** tạo vùng mới theo tên sai.

Ví dụ cố ý thao tác trực tiếp qua API. Không cần `@EnableCaching` để gọi `CacheManager.getCache(...)` hoặc `Cache.put(...)` theo cách này.

## 6. Khi dùng `@Cacheable`, manager tham gia ở đâu?

Với cơ chế annotation, người viết thường khai báo tên cache mà không tự gọi `getCache`:

~~~java
// Các đoạn sau minh họa phần tích hợp trong một ứng dụng Spring,
// chưa phải chương trình độc lập để biên dịch riêng.

@Configuration
@EnableCaching
class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}

@Service
class ProductService {
    @Cacheable(cacheNames = "products", key = "#p0")
    public String loadProduct(String sku) {
        // Trong ứng dụng thật, đây có thể là truy vấn kho dữ liệu.
        return "product:" + sku;
    }
}
~~~

Các import tương ứng nằm trong `org.springframework.context.annotation.*`, `org.springframework.stereotype.Service`, `org.springframework.cache.annotation.*`, `org.springframework.cache.CacheManager` và `org.springframework.cache.concurrent.ConcurrentMapCacheManager`.

Khi một bean khác gọi `ProductService.loadProduct("sku-42")` **qua Spring proxy**:

1. Cache interceptor nhận metadata `@Cacheable(cacheNames = "products")`.
2. `CacheResolver` mặc định dùng `CacheManager` được cấu hình để tìm vùng `products`.
3. `KeyGenerator` hoặc biểu thức `key` tạo key; ở đây `#p0` chính là đối số đầu tiên `"sku-42"`.
4. Nếu entry đã có, Spring trả giá trị cache; nếu miss, Spring gọi method rồi lưu kết quả theo key.
5. Nếu manager tĩnh không biết tên đã khai báo, việc resolve cache không hoàn tất và thao tác caching sẽ báo lỗi theo ngữ cảnh, thay vì âm thầm tạo vùng như manager động.

Để annotation hoạt động, phải bật `@EnableCaching` (hoặc cấu hình tương đương). Ở proxy mode mặc định, **self-invocation** trong cùng bean không đi qua proxy nên có thể bỏ qua `@Cacheable`. Trường hợp có nhiều `CacheManager`, chọn rõ bằng `@Cacheable(cacheManager = "beanName")` hoặc thiết lập `CacheResolver` phù hợp; không tùy tiện để Spring chọn nhầm backend.

## 7. Lookup an toàn trong mã ứng dụng

Nếu yêu cầu bắt buộc tồn tại một vùng, **xử lý khả năng `null`** ngay tại ranh giới:

~~~java
Cache products = Objects.requireNonNull(
    cacheManager.getCache("products"),
    "Missing configured cache: products"
);
products.put("sku-42", productName);
~~~

Đây là **đoạn minh họa**, cần biến `cacheManager` và `productName` từ ứng dụng. Với provider không tạo động, thiếu tên sẽ gây lỗi rõ ràng tại vị trí sử dụng, thay vì `NullPointerException` ở dòng sau.

Khi một ứng dụng có tập cache tên hữu hạn, nên dùng hằng số tên và cấu hình tĩnh tập hợp đó; lập danh mục tên, chủ sở hữu, mục đích và backend. Chỉ bật dynamic naming khi có yêu cầu và kiểm soát được số lượng tên. **Không** nối trực tiếp input người dùng (user ID, tenant ID, URL...) vào tên cache nếu việc đó tạo vô hạn cache region; hãy cân nhắc giữ một cache cố định và dùng các giá trị này trong *key*, cùng giới hạn kích thước/TTL phù hợp.

Ví dụ phân biệt đúng:

- `getCache("products").get("sku-42")`: vùng **products**, key **sku-42**.
- `getCache("products-sku-42")`: yêu cầu một **vùng khác**; ở chế độ động có thể tạo cache riêng cho từng SKU, dễ gây tăng số vùng ngoài ý muốn.

Cấu hình provider cần được kiểm tra riêng: giới hạn số entry, TTL/TTI, serialization, null handling, eviction, khả năng chia sẻ giữa node và metrics. `CacheManager` SPI không tự cung cấp tất cả các bảo đảm này.

## 8. Những lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể | Kiểm tra / hướng xử lý |
| --- | --- | --- |
| `getCache(name) == null` | Tên chưa khai báo ở static manager; sai tên; provider chưa khởi tạo vùng | So khớp tên với cấu hình; xem `getCacheNames()`; tạo/cấu hình vùng qua cơ chế đúng của provider |
| Tên cache lạ xuất hiện trong `getCacheNames()` | Manager động tự tạo vùng do gõ sai hoặc sinh tên từ dữ liệu | Dùng tên chuẩn/hằng số, chặn tên không hợp lệ, xem log nơi gọi `getCache` |
| `@Cacheable` vẫn chạy method mỗi lần | Chưa bật caching; self-invocation; key thay đổi; cache bị evict; provider/no-op không giữ entry | Kiểm tra proxy, `@EnableCaching`, cache name/key, provider và chính sách lưu trữ |
| Có nhiều manager, lookup dùng sai vùng | Chọn nhầm bean hoặc `CompositeCacheManager` trả cache ở manager đứng trước | Chỉ định `cacheManager`/`cacheResolver` rõ; rà lại thứ tự và chế độ dynamic |
| Dùng cùng tên nhưng ứng dụng ở node khác không thấy dữ liệu | Provider cục bộ như `ConcurrentMapCacheManager` chỉ lưu trong tiến trình JVM | Dùng backend chia sẻ nếu cần cache phân tán; không đồng nhất tên cache với dữ liệu chung |
| Kết quả trả `null` nhưng không biết miss hay hit với giá trị null | Dùng `get(key, Type)` hoặc không xét `ValueWrapper` | Khi cần phân biệt, dùng `Cache.get(key)` và kiểm tra wrapper; kiểm tra chính sách cache giá trị null |

**Chẩn đoán theo thứ tự:** xác nhận Spring bean `CacheManager` thực tế → tên vùng được yêu cầu → `getCache(name)` trả `Cache` hay `null` → key tạo ra → provider có lưu/evict entry như dự kiến không. Mốc này giúp tránh đổ lỗi cho “cache không hoạt động” khi thực ra lỗi nằm ở *cache resolution*.

## 9. Câu hỏi tự kiểm tra

1. Tại sao `getCache("users")` không có nghĩa là đã lấy được một user? Vì nó lấy **cache region**, còn `get(userId)` mới lấy entry.
2. Với `new ConcurrentMapCacheManager()`, hai lần gọi `getCache("metrics")` sẽ thế nào? Lần đầu có thể tạo vùng; lần sau tìm lại vùng đó. `getCacheNames()` sẽ biết `metrics` sau lookup.
3. Với `new ConcurrentMapCacheManager("products")`, `getCache("product")` trả gì? `null` vì khác chuỗi tên đã cấu hình.
4. Nếu `CompositeCacheManager` có manager động đứng trước manager Redis, có thể xảy ra điều gì? Manager đầu nhận tên và trả `Cache` nên manager Redis không được thử; cần kiểm soát thứ tự/chiến lược.
5. Nếu có một triệu SKU, nên tạo một triệu cache name không? Thường **không**; tạo một vùng `products` và một triệu key (kèm giới hạn tài nguyên) thường đúng mô hình hơn.

## 10. Ghi nhớ và tài liệu chính thức

- `CacheManager` quản lý **vùng cache theo tên**; `Cache` quản lý **entry theo key**.
- `getCache(name)` có thể **lookup hoặc tạo trễ**, nhưng **phụ thuộc implementation**; không bao giờ mặc định cho rằng cache bị thiếu sẽ luôn được tạo.
- `getCacheNames()` trả về những tên manager đang biết, không phải lời hứa về mọi tên có thể tồn tại.
- Static naming giúp phát hiện tên sai sớm; dynamic naming tăng linh hoạt nhưng cần giới hạn tên và tài nguyên.
- Khi dùng annotation, resolution đi qua `CacheResolver`/`CacheManager`; nó vẫn tuân theo chính sách của provider.

Tài liệu đối chiếu:

- [Spring Framework — CacheManager API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/CacheManager.html)
- [Spring Framework — ConcurrentMapCacheManager API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html)
- [Spring Framework — Declarative annotation-based caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
