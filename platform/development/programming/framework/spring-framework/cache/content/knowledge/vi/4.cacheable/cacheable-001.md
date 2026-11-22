# Spring `@Cacheable`: khai báo `cacheNames`, `value` và quan hệ alias

## 1. Mục tiêu và vấn đề cần hiểu

Trong Spring Framework, `@Cacheable` đánh dấu một phương thức có kết quả có thể được lưu trong cache. Khi lời gọi tiếp theo có cùng cache key và entry hợp lệ, Spring có thể trả kết quả đã lưu, bỏ qua việc thực thi thân phương thức. Để Spring biết **cache nào** được sử dụng, ta thường khai báo `cacheNames` hoặc `value`.

Ba cách dưới đây **tương đương về tên cache được khai báo** (đây là ba lựa chọn *thay thế nhau* cho một phương thức, không phải ba annotation đặt cùng lúc):

~~~java
@Cacheable("products")
public Product findById(String id) { /* đọc nguồn dữ liệu */ }

// Hoặc:
@Cacheable(value = "products")
public Product findById(String id) { /* đọc nguồn dữ liệu */ }

// Hoặc:
@Cacheable(cacheNames = "products")
public Product findById(String id) { /* đọc nguồn dữ liệu */ }
~~~

- `"products"` là **tên cache** (vùng cache/region), không phải tên biến, tên Bean service hay giá trị `Product` được trả về.
- `value` ở đây **không có nghĩa là “giá trị cần cache”**. Nó là tên khác của `cacheNames`.
- `@Cacheable("products")` sử dụng cú pháp rút gọn dành cho phần tử annotation tên `value` của Java.
- Dù giá trị được viết là một chuỗi, cả `value()` và `cacheNames()` thực chất đều có kiểu **`String[]`**: có thể khai báo một hoặc nhiều tên cache.
- Không có thuộc tính `cacheName` dạng số ít trên `@Cacheable`. Thuộc tính chính xác là `cacheNames`.

Vì vậy, khi đọc một codebase, đừng kết luận `@Cacheable(value = "products")` hoạt động khác `@Cacheable(cacheNames = "products")`. Hãy kiểm tra **tên cache, cache key, cấu hình cache manager và cách gọi phương thức**.

## 2. Khai báo một cache hoặc nhiều cache

### Một tên cache

~~~java
@Cacheable(cacheNames = "products")
public Product getProduct(String id) { /* ... */ }
~~~

Spring chọn cache được đặt tên `products` thông qua `CacheResolver`, thông thường dựa vào `CacheManager` đang được cấu hình. Nếu không có entry cho key tương ứng, Spring gọi phương thức và lưu kết quả trả về vào cache; nếu có hit, phương thức có thể không chạy.

Các cách tương đương về *khai báo tên* là:

| Cú pháp | Giá trị tên cache |
|---|---|
| `@Cacheable("products")` | `["products"]` |
| `@Cacheable(value = "products")` | `["products"]` |
| `@Cacheable(cacheNames = "products")` | `["products"]` |
| `@Cacheable(value = {"products"})` | `["products"]` |
| `@Cacheable(cacheNames = {"products"})` | `["products"]` |

Phần lớn phương thức chỉ nên khai báo **một** tên cache để việc quản lý TTL, key và invalidation rõ ràng. Việc chọn tên cache không tự cấu hình TTL hoặc eviction; các chính sách đó phụ thuộc cache provider và cấu hình `CacheManager`.

### Nhiều tên cache

~~~java
@Cacheable(cacheNames = {"products", "productsBackup"})
public Product getProduct(String id) { /* ... */ }

// Cách viết tương đương:
@Cacheable(value = {"products", "productsBackup"})
public Product getProduct(String id) { /* ... */ }

// Chỉ có value, có thể dùng cú pháp rút gọn:
@Cacheable({"products", "productsBackup"})
public Product getProduct(String id) { /* ... */ }
~~~

Đây là **hai tên cache**, không phải hai cache key, hai đối số hay hai phiên bản khác nhau của phương thức. Ở đường xử lý cache đồng bộ thông thường, Spring có thể kiểm tra lần lượt các cache; nếu gặp hit, kết quả được sử dụng và những cache còn thiếu entry có thể được cập nhật. Nếu không có hit, kết quả phương thức được lưu vào các cache đã chọn.

**Giới hạn quan trọng:** với cache truy cập bất đồng bộ/reactive và cache provider cho biết miss muộn, Spring có thể không kiểm tra tất cả tên cache theo cách đồng bộ. Chỉ định nhiều tên cache cần được kiểm chứng với provider thực tế. Khi dùng `ConcurrentMapCacheManager("products", "productsBackup")` ở chế độ tên cố định, cả hai tên phải có trong danh sách cấu hình.

Không nên khai báo nhiều tên cache chỉ để “dự phòng” mà chưa xác định rõ mục đích; mỗi tên bổ sung kéo theo chính sách hết hạn, số bản sao và yêu cầu xóa/cập nhật nhất quán.

## 3. Vì sao `cacheNames` và `value` tương đương? Cơ chế `@AliasFor`

Trong annotation `org.springframework.cache.annotation.Cacheable` của Spring, phần khai báo hai thuộc tính có cấu trúc tương đương đoạn Javadoc rút gọn sau:

~~~java
@AliasFor("cacheNames")
String[] value() default {};

@AliasFor("value")
String[] cacheNames() default {};
~~~

Đây là **alias hai chiều (reciprocal aliases)** trong **cùng một annotation**:

- `value()` được khai báo là alias của `cacheNames()`.
- `cacheNames()` được khai báo là alias của `value()`.
- Hai phần tử có **cùng kiểu `String[]` và cùng giá trị mặc định `{}`**.
- Khi Spring xử lý annotation qua cơ chế merged/synthesized annotations, một tên được khai báo sẽ được diễn giải như giá trị của thuộc tính alias còn lại.

Hình dung luồng đọc metadata:

~~~text
@Cacheable(value = "products")
             |
             v
Spring đọc @Cacheable qua MergedAnnotations / annotation metadata
             |
             v
value ↔ cacheNames = ["products"]
             |
             v
CacheResolver / CacheManager chọn cache "products"
             |
             v
Dùng cache key để kiểm tra hit/miss rồi trả hoặc nạp kết quả
~~~

`@AliasFor` là **quan hệ giữa hai phần tử của annotation**, không phải cơ chế sao chép nội dung cache. Nó cũng **không phải** từ khóa Java có hiệu lực tự động với mọi reflection call: Spring cần đọc/synthesize annotation metadata bằng API của framework thì semantics alias mới được áp dụng đúng. Việc gọi reflection Java thuần trên phần tử `value()` và `cacheNames()` không có nghĩa Java VM đã tự đồng bộ chúng.

### Khai báo hai alias cùng lúc

Không cần viết cả hai tên trong một annotation. Hãy chọn một tên theo quy ước của dự án:

~~~java
// Nên dùng một thuộc tính để tránh trùng lặp:
@Cacheable(cacheNames = "products", key = "#p0")
public Product findById(String id) { /* ... */ }

// Dư thừa, dù hai alias mang cùng giá trị:
@Cacheable(value = "products", cacheNames = "products")
public Product findById(String id) { /* ... */ }

// Sai cấu hình alias: hai thuộc tính được đặt các giá trị khác nhau.
@Cacheable(value = "products", cacheNames = "orders")
public Product findById(String id) { /* ... */ }
~~~

**Lưu ý:** ba đoạn trên là các ví dụ **độc lập**, không đặt ba phương thức cùng chữ ký vào một class. Ví dụ cuối có thể qua kiểm tra cú pháp Java vì đây là hai tên thuộc tính hợp lệ, nhưng Spring phát hiện xung đột khi đọc/synthesize annotation và có thể ném `AnnotationConfigurationException` (hoặc lỗi khởi tạo tương ứng). Không có quy tắc “`value` ưu tiên `cacheNames`” hay ngược lại.

### Điểm dễ nhầm: rút gọn annotation của Java

Java chỉ cho phép bỏ `value =` trong cú pháp annotation khi dùng dạng một phần tử phù hợp:

~~~java
@Cacheable("products") // Hợp lệ
@Cacheable(value = "products", key = "#p0") // Hợp lệ
@Cacheable(cacheNames = "products", key = "#p0") // Hợp lệ
~~~

Không viết `@Cacheable("products", key = "#p0")`: đây không phải cách kết hợp cú pháp rút gọn với các phần tử được đặt tên trong Java. Khi cần thêm `key`, `condition`, `unless`, `sync`, hãy viết rõ `value =` hoặc `cacheNames =`.

## 4. Phân biệt tên cache, cache key và giá trị được lưu

Ví dụ:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product getProduct(String productId) {
    return repository.findById(productId).orElseThrow();
}
~~~

Ba khái niệm này có vị trí khác nhau:

| Thành phần | Trong ví dụ | Tác dụng |
|---|---|---|
| Cache name | `products` | Chọn vùng cache để thao tác. |
| Cache key | `#p0` (giá trị `productId`) | Chọn entry bên trong vùng cache đó. |
| Cached value | Đối tượng `Product` trả về | Dữ liệu/kết quả lưu tại entry được chọn. |

Có thể tưởng tượng nội dung:

~~~text
CacheManager
 └─ Cache "products"
     ├─ key "p1" -> Product(id="p1", name="Keyboard")
     └─ key "p2" -> Product(id="p2", name="Mouse")
~~~

- `cacheNames`/**`value`** chỉ chọn vùng cache, **không tạo key**.
- `key` là một biểu thức SpEL cho từng lời gọi. `#p0` hoặc `#a0` là đối số thứ nhất (đánh chỉ số từ 0); `#p0` hữu ích khi không biên dịch Java bằng `-parameters` để giữ tên tham số.
- Nếu không khai báo `key` và không cấu hình `keyGenerator` riêng, `SimpleKeyGenerator` mặc định tạo key từ các tham số: không tham số dùng `SimpleKey.EMPTY`, một tham số thường dùng chính đối số, nhiều tham số tạo `SimpleKey`.
- Nếu dùng chung cache name và key cho hai phương thức trả kết quả khác ý nghĩa, chúng có thể đụng entry. Tên cache đủ rõ và key đủ phân biệt dữ liệu là trách nhiệm thiết kế của ứng dụng.

Ví dụ nguy hiểm: `getPrice(productId, currency)` nhưng `key = "#p0"` sẽ bỏ qua đơn vị tiền tệ. Lần đọc `USD` có thể bị tái sử dụng sai cho `VND`, dù `cacheNames` được khai báo chính xác.

`cacheManager = "..."` là một thuộc tính khác dùng chọn **bean `CacheManager`** cụ thể; nó **không phải** tên cache:

~~~java
@Cacheable(cacheNames = "products", cacheManager = "businessCacheManager",
           key = "#p0")
public Product getProduct(String id) { /* ... */ }
~~~

Ở đây `businessCacheManager` là tên bean quản lý cache; `products` là tên cache do manager/resolver cung cấp.

## 5. Ví dụ chạy thật với Spring Framework và Java 17+

Bài demo dùng `spring-context` của Spring Framework **6.2.16**, Java **17+** và Maven **3.9+**. Nó dùng cache trong RAM của `ConcurrentMapCacheManager`, không cần Spring Boot, HTTP server hoặc database. Mục đích là kiểm chứng **hai tên thuộc tính alias dẫn đến cùng cache**, không phải benchmark hiệu năng.

Cấu trúc tệp:

~~~text
cache-alias-demo/
├── pom.xml
└── src/main/java/demo/Demo.java
~~~

**`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>cache-alias-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/demo/Demo.java`**:

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class Demo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(CacheConfiguration.class)) {
            var service = context.getBean(ProductService.class);
            System.out.println(service.byValue("p1"));
            System.out.println(service.byCacheNames("p1"));
            System.out.println(service.byCacheNames("p2"));
            System.out.println(service.byValue("p2"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfiguration {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        ProductService productService() {
            return new ProductService();
        }
    }

    public static class ProductService {
        private int loads = 0;

        @Cacheable(value = "products", key = "#p0")
        public String byValue(String id) {
            return load(id);
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public String byCacheNames(String id) {
            return load(id);
        }

        private String load(String id) {
            loads++;
            System.out.printf("LOAD %s #%d%n", id, loads);
            return "product:" + id + ":v" + loads;
        }
    }
}
~~~

Tại thư mục `cache-alias-demo`, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.Demo
~~~

**Stdout của demo** (đã kiểm tra với Java có khả năng biên dịch đích `--release 17` qua Maven):

~~~text
LOAD p1 #1
product:p1:v1
product:p1:v1
LOAD p2 #2
product:p2:v2
product:p2:v2
~~~

Diễn giải từng lời gọi:

1. `byValue("p1")`: cache `products` chưa có key `p1` → chạy `load`, in `LOAD p1 #1` và lưu `product:p1:v1`.
2. `byCacheNames("p1")`: vẫn dùng cache `products` và key `p1` → **hit**, trả đúng kết quả cũ; không in thêm `LOAD`.
3. `byCacheNames("p2")`: key khác → **miss**, chạy `load` lần thứ hai.
4. `byValue("p2")`: hit trên entry `p2` do phương thức kia đã nạp.

Ví dụ cố ý cho hai phương thức dùng **cùng cache và cùng key**, cùng trả về một dạng dữ liệu, để minh họa alias. Trong ứng dụng thực tế, **đừng chia sẻ cache name/key giữa hai phương thức trả dữ liệu khác nghĩa**; đây sẽ là va chạm dữ liệu, dù alias hoạt động hoàn toàn đúng.

`@EnableCaching` kích hoạt xử lý annotation cache; `@Bean CacheManager` cung cấp nơi lưu. Đối tượng service được lấy từ Spring context nên lời gọi đi qua **Spring proxy**, cho phép caching advice can thiệp. Nếu tự khởi tạo `new ProductService()` và gọi trực tiếp, annotation sẽ không tự tạo cache. Gọi một phương thức `@Cacheable` bằng `this.method()` từ cùng đối tượng cũng thường bỏ qua proxy trong chế độ mặc định.

`ConcurrentMapCacheManager` phù hợp để học; ví dụ **không cấu hình TTL**, không dùng Redis và không có đồng bộ cache giữa nhiều tiến trình.

## 6. Liên hệ với `@CacheConfig` và cấu hình cấp phương thức

`@CacheConfig` có thể đặt **tên cache mặc định cho các cache operation trong cùng class**. Khi có mặc định này, một phương thức có thể viết `@Cacheable` mà không chỉ định riêng `cacheNames`/`value`.

Đoạn dưới là **minh họa tích hợp**, cần `Product` và `ProductRepository` của ứng dụng; không phải tệp Java độc lập:

~~~java
@CacheConfig(cacheNames = "products")
@Service
public class ProductQueryService {
    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(key = "#p0")
    public Product get(String id) {
        return repository.findById(id).orElseThrow();
    }

    @Cacheable(cacheNames = "featuredProducts", key = "#p0")
    public Product getFeatured(String id) {
        return repository.findFeaturedById(id).orElseThrow();
    }
}
~~~

- `get()` kế thừa tên mặc định `products` từ `@CacheConfig`.
- `getFeatured()` khai báo `cacheNames = "featuredProducts"` tại phương thức, nên **ghi đè tên cache mặc định** của class cho operation đó.
- `@CacheConfig` một mình **không làm phương thức được cache**; vẫn cần `@Cacheable` hoặc cache operation khác.
- Một phương thức có thể không khai báo tên cache nếu cấu hình phù hợp cung cấp tên qua `@CacheConfig` hoặc `CacheResolver` tùy chỉnh. Ngược lại, `@Cacheable` không có tên cache và không có cấu hình nào cung cấp cache là một cấu hình thiếu để Spring thực thi operation.

Đừng suy ra vì `@Cacheable.value` là alias của `@Cacheable.cacheNames` mà **mọi annotation** của Spring cũng có cặp alias giống hệt. Mỗi annotation có khai báo và phiên bản API riêng; đọc Javadoc của chính annotation đó.

### Nếu dự án tạo annotation tổng hợp (composed annotation)

Spring cho phép tạo annotation riêng mang `@Cacheable` làm meta-annotation và ánh xạ thuộc tính sang nó bằng `@AliasFor`. Ví dụ dưới là **mẫu cấu trúc**, cần các import Java annotation và Spring phù hợp; hãy đặt annotation trong tệp riêng `ProductCached.java` nếu dùng thực tế:

~~~java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Cacheable
public @interface ProductCached {
    @AliasFor(annotation = Cacheable.class, attribute = "cacheNames")
    String[] value() default {"products"};
}
~~~

Khi dùng `@ProductCached`, tên cache mặc định là `products`. Có thể ghi `@ProductCached("otherProducts")` để override metadata được ánh xạ tới `Cacheable.cacheNames`. Đây là **alias từ annotation tự tạo đến thuộc tính của meta-annotation**, khác với alias hai chiều *trong chính* `@Cacheable`. Chỉ thêm abstraction này khi nhiều phương thức cần chia sẻ quy ước và đã kiểm tra cách Spring đọc composed annotations.

## 7. Các lỗi phổ biến khi khai báo và cách xử lý

| Dấu hiệu hoặc hiểu nhầm | Nguyên nhân | Hướng kiểm tra |
|---|---|---|
| Nghĩ `value = "products"` là giá trị lưu vào cache | Nhầm tên thuộc tính với cached value | `value` là `String[]` tên cache; cached value là kết quả phương thức. |
| Viết `@Cacheable(cacheName = "products")` | Sai tên thuộc tính | Dùng `cacheNames` (số nhiều) hoặc `value`. |
| Khai báo `value = "a"` và `cacheNames = "b"` | Hai alias xung đột | Chỉ dùng một thuộc tính hoặc bảo đảm cùng giá trị; ưu tiên một tên. |
| Cache không hoạt động dù có annotation | Chưa `@EnableCaching`; không có manager; gọi qua `new`/`this` | Kiểm tra Spring bean, proxy, bật caching và cấu hình manager. |
| Báo không tìm thấy cache tên `products` | Cache manager hiện tại không cung cấp cache đó | Kiểm tra danh sách cache/logic `CacheResolver`, không đổi tên bừa. |
| Kết quả bất ngờ giữa hai phương thức | Chia sẻ cache name và key trong khi kết quả khác nhau | Tách tên cache hoặc thiết kế key có namespace phù hợp. |
| Không gọi được SpEL `#id` | Tên tham số không có trong metadata biên dịch | Dùng `#p0`/`#a0` hoặc cấu hình `-parameters` đúng. |
| Nghĩ tên cache quy định TTL | `@Cacheable` chỉ nêu cache cần dùng | Cấu hình TTL/eviction ở provider (Caffeine, Redis, v.v.). |
| Dùng nhiều tên cache gây hành vi khó hiểu | Nhiều bản sao, provider có đặc tính truy cập khác nhau | Kiểm thử hit/miss, đồng bộ/invalidation và khả năng async. |

**Thứ tự debug đề xuất:** xác nhận annotation nằm trên phương thức Spring bean và caching được bật → xác nhận cache manager/resolver tìm được tên cache → in key/hit/miss → kiểm tra self-invocation → kiểm tra dữ liệu có đổi mà cache chưa evict hay không. Chỉ khác cách viết `value`/`cacheNames` mà tên bằng nhau **không giải thích được khác biệt hit/miss**.

## 8. Câu hỏi tự kiểm tra

1. `@Cacheable("books")` tương đương với hai cách khai báo tường minh nào?
2. `@Cacheable(value = {"a", "b"})` khai báo mấy cache, và có khai báo hai key không?
3. `@Cacheable(value = "a", cacheNames = "b")` có ý nghĩa “đọc từ a, ghi sang b” không?
4. Trong `@Cacheable(cacheNames = "books", key = "#p0")`, đâu là cache name, đâu là cache key, và đâu là cached value?
5. Nếu hai phương thức khác nhau dùng chung tên cache và key nhưng trả dữ liệu khác nghĩa, nguy cơ gì xảy ra?
6. Tại sao phương thức có `@Cacheable` vẫn chạy lại mỗi lần khi gọi bằng `new Service()`?

**Đáp án gợi ý:** (1) `@Cacheable(value = "books")` và `@Cacheable(cacheNames = "books")`. (2) Hai tên cache, không phải hai key. (3) Không; đây là xung đột alias. (4) `books` là tên cache, `#p0` tính key từ tham số đầu tiên, cached value là kết quả phương thức. (5) Va chạm entry và trả sai kết quả. (6) Phương thức không được gọi thông qua Spring caching proxy.

## 9. Tài liệu tham khảo

- Spring Framework Javadoc — `@Cacheable` (xem khai báo `value()` và `cacheNames()`): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework Reference — Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `@AliasFor` và cơ chế annotation aliases: https://docs.spring.io/spring-framework/docs/6.1.22-SNAPSHOT/javadoc-api/org/springframework/core/annotation/AliasFor.html

**Ghi nhớ:** Trong `@Cacheable`, **`value` và `cacheNames` là hai alias hai chiều của cùng một `String[]` tên cache**. Chọn một cách viết nhất quán; phân biệt tên cache với key và kết quả được lưu; sau đó kiểm tra `CacheManager`, `@EnableCaching` và lời gọi qua Spring proxy để cache thực sự hoạt động.