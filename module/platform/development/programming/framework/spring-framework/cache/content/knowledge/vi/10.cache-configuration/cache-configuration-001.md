# @CacheConfig và các giá trị mặc định ở cấp lớp trong Spring Framework Cache

## 1. Vì sao một lớp cần cấu hình cache dùng chung?

Giả sử service quản lý sản phẩm có các thao tác đọc, sửa và xóa. Cả ba thao tác đều liên quan vùng cache `products`:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) { /* ... */ }

@CachePut(cacheNames = "products", key = "#p0.id()")
public Product save(Product product) { /* ... */ }

@CacheEvict(cacheNames = "products", key = "#p0")
public void delete(String id) { /* ... */ }
```

Lặp `cacheNames = "products"` trên từng method dễ dẫn đến sai chính tả tên vùng, khó đổi tên và khó nhìn ra hợp đồng cache chung của lớp. Spring cung cấp `@CacheConfig` để khai báo **mặc định ở cấp lớp** cho các thao tác cache nằm trong lớp đó.

```java
@CacheConfig(cacheNames = "products")
public class ProductService {

    @Cacheable(key = "#p0")
    public Product find(String id) { /* ... */ }

    @CachePut(key = "#p0.id()")
    public Product save(Product product) { /* ... */ }

    @CacheEvict(key = "#p0")
    public void delete(String id) { /* ... */ }
}
```

Ba annotation method ở ví dụ thứ hai tự lấy tên vùng `products` từ `@CacheConfig`. Các biểu thức `key` vẫn được khai báo riêng để phù hợp với chữ ký và giá trị từng tham số.

**Bản chất:** `@CacheConfig` cung cấp giá trị mặc định cho các cache operation được khai báo trong cùng lớp. Nó **không tự kích hoạt caching**, không tạo cache entry, không thay thế `@Cacheable`/`@CachePut`/`@CacheEvict` và không định nghĩa chính sách TTL, dung lượng hay nơi lưu vật lý.

Các đoạn Java ngắn ở trên minh họa annotation trên service đã có các kiểu và dependency liên quan. Ví dụ chạy độc lập nằm ở mục 5.

## 2. Các mặc định mà `@CacheConfig` hỗ trợ

Annotation `org.springframework.cache.annotation.CacheConfig` được đặt trên **kiểu/lớp**, cung cấp bốn thuộc tính chính:

| Thuộc tính | Kiểu khai báo | Ý nghĩa mặc định cho các method cache |
| --- | --- | --- |
| `cacheNames` (alias `value`) | `String[]` | Một hoặc nhiều tên cache mà method sử dụng khi method không chỉ định tên riêng |
| `keyGenerator` | `String` | Tên Spring bean triển khai `KeyGenerator` để tính key mặc định |
| `cacheManager` | `String` | Tên Spring bean `CacheManager` dùng khi chưa có resolver/manager được ưu tiên cao hơn |
| `cacheResolver` | `String` | Tên Spring bean `CacheResolver` chọn vùng cache, có thể dựa trên ngữ cảnh gọi method |

Ví dụ đầy đủ về mặt cấu hình (các bean được nêu tên phải tồn tại):

```java
@CacheConfig(
    cacheNames = "products",
    keyGenerator = "productKeyGenerator",
    cacheManager = "catalogCacheManager"
)
public class ProductService {
    @Cacheable
    public Product find(String id) { /* ... */ }
}
```

Ở đây `@Cacheable` không có thuộc tính nào: bộ xử lý cache lấy tên vùng `products`, bean `productKeyGenerator` và bean `catalogCacheManager` làm mặc định cho operation này. Tên trong chuỗi là **tên bean** Spring, không phải tên lớp Java.

Không cần khai báo cả bốn thuộc tính. Thực tế thường chỉ đặt `cacheNames`; các lựa chọn khác nên thêm khi toàn bộ thao tác trong lớp thật sự dùng chung một quy tắc.

### 2.1. `cacheNames` là danh sách các vùng mặc định

Cú pháp tương đương:

```java
@CacheConfig("products")
public class A { /* ... */ }

@CacheConfig(cacheNames = {"products"})
public class B { /* ... */ }
```

Vì `cacheNames` là mảng, có thể truyền nhiều tên cache. Tuy nhiên, nhiều vùng được áp dụng cho một operation không đồng nghĩa với một giao dịch cache nguyên tử. Với thao tác xóa hàng loạt, nó còn làm tăng phạm vi ảnh hưởng. Chọn một vùng chung theo trách nhiệm của lớp là phương án dễ theo dõi hơn trong phần lớn ví dụ.

Một `@Cacheable` không chỉ rõ cache names sẽ kế thừa từ lớp; nếu method ghi `cacheNames = "productLabels"` thì dùng **productLabels thay cho products** ở operation đó. Không có phép “tự cộng” tên vùng cấp lớp và cấp method.

### 2.2. `keyGenerator` chọn cách tạo khóa chung

`KeyGenerator` phù hợp khi nhiều method có cùng quy tắc định danh, chẳng hạn chuẩn hóa một SKU. Nếu method khai báo `key = "#p0"` hoặc `key = "#p0.id()"`, key SpEL ở method được ưu tiên hơn key generator mặc định của lớp.

Phải bảo đảm đọc/ghi/xóa cùng một entry dùng **cùng key logic**. Một generator áp dụng máy móc cho mọi chữ ký có thể tạo key sai, đặc biệt khi `find(String id)` và `save(Product product)` nhận các kiểu đối số khác nhau.

### 2.3. `cacheManager` chọn backend/nhóm cache

`CacheManager` quản lý các cache theo tên. Ví dụ ứng dụng có manager dành cho catalog và manager dành cho số liệu báo cáo. Lớp thao tác catalog có thể dùng mặc định:

```java
@CacheConfig(
    cacheNames = "products",
    cacheManager = "catalogCacheManager"
)
public class CatalogService {
    @Cacheable
    public Product find(String id) { /* ... */ }
}
```

Nếu ứng dụng chỉ có một `CacheManager` phù hợp, thường không cần chỉ định tên manager ở `@CacheConfig`. Tên vùng `products` không tự xác định cache là Redis, Caffeine hay bộ nhớ JVM; điều đó do manager và provider quyết định.

### 2.4. `cacheResolver` chọn cache theo một chiến lược

`CacheResolver` có thể chọn cache từ tên, tham số hoặc ngữ cảnh lời gọi. Một lớp cần chọn cache linh hoạt có thể cấu hình `cacheResolver = "catalogCacheResolver"`, với điều kiện bean tên đó tồn tại và triển khai hợp đồng `CacheResolver`.

Không cấu hình `cacheManager` và `cacheResolver` cùng lúc cho một operation: hai cách chọn nơi lấy cache có vai trò thay thế nhau. Nếu cần logic chọn cache tùy biến, hãy quyết định rõ resolver nào sở hữu logic đó. `@CacheConfig` không tự tạo ra cache resolver mới hay quyết định cách phân tuyến dữ liệu.

## 3. Thứ tự ưu tiên: mặc định toàn cục → lớp → phương thức

Spring Cache có ba tầng cấu hình, trong đó cấu hình **cụ thể hơn** chiếm ưu tiên:

1. **Toàn cục:** ví dụ `CachingConfigurer` và các bean cache mặc định của ứng dụng.
2. **Cấp lớp:** `@CacheConfig` áp dụng cho các operation trong lớp.
3. **Cấp phương thức/operation:** thuộc tính của từng `@Cacheable`, `@CachePut`, `@CacheEvict` hoặc annotation con trong `@Caching`.

Ví dụ:

```java
@CacheConfig(cacheNames = "products")
public class ProductService {

    @Cacheable
    public Product find(String id) { /* ... */ }

    @Cacheable(cacheNames = "productLabels")
    public String label(String id) { /* ... */ }
}
```

| Method | Tên cache thực tế | Vì sao |
| --- | --- | --- |
| `find("P1")` | `products` | `@Cacheable` không chỉ định tên, nên kế thừa `@CacheConfig` |
| `label("P1")` | `productLabels` | Method đã chỉ rõ tên vùng riêng, nên ghi đè mặc định lớp |

Nếu `@CacheConfig(keyGenerator = "productKeyGenerator")` mà method ghi `@Cacheable(key = "#p0")`, biểu thức `#p0` được chọn cho **method đó**. `key` và `keyGenerator` không được khai báo cùng lúc trên **một cache operation**, vì chúng là hai cách xác định key loại trừ nhau.

Tương tự, operation chỉ định `cacheManager = "reportCacheManager"` có thể thay thế lựa chọn manager mặc định ở lớp. Khi operation sử dụng `cacheResolver` riêng, resolver của operation có quyền ưu tiên; kiểm tra bean resolver và cache names mà resolver thực sự trả về.

**Mặc định không phải inheritance nghiệp vụ:** `@CacheConfig` chỉ tập trung các giá trị cấu hình. Nó không biến `@Cacheable` thành `@CachePut`, không thêm cơ chế đồng bộ giao dịch và không buộc các operation đều có cùng chính sách xử lý lỗi.

## 4. Điều gì KHÔNG nằm trong `@CacheConfig`?

| Nhu cầu | Cấu hình phù hợp |
| --- | --- |
| Thực sự bật cơ chế cache annotation | `@EnableCaching` ở cấu hình Spring |
| Quy định method nào được cache | `@Cacheable` trên method |
| Luôn chạy method và cập nhật cache | `@CachePut` |
| Xóa entry hoặc làm trống vùng | `@CacheEvict` |
| Chọn khóa theo SpEL `#p0.id()` | `key` ở từng operation |
| Chỉ cache khi đối số thỏa điều kiện | `condition` ở từng operation |
| Không cache kết quả null | `unless = "#result == null"` trên operation hỗ trợ |
| Đồng bộ tính toán cache miss cùng key | `@Cacheable(sync = true)` khi đáp ứng giới hạn của annotation/provider |
| TTL, size limit, eviction policy, serialization | Cấu hình `CacheManager`/cache provider tương ứng |
| Transaction commit, invalidation nhiều node | Thiết kế giao dịch và cache backend/sự kiện phù hợp |

Dù lớp có `@CacheConfig(cacheNames = "products")`, một method **không có annotation cache operation** vẫn chạy bình thường và không được cache chỉ vì nằm trong lớp đó.

Cũng không thể dùng `@CacheConfig` để mặc định `unless` hay `condition` cho toàn bộ lớp: bốn thuộc tính công khai của nó là `cacheNames`, `keyGenerator`, `cacheManager` và `cacheResolver`.

## 5. Ví dụ chạy được: mặc định lớp và ghi đè ở method

Ví dụ Java 17 + Spring Framework 6.2.x sau minh họa hai vùng:

- `products`: dùng chung cho `find`, phần `@CachePut` của `save`, và phần `@CacheEvict` của `delete` nhờ `@CacheConfig(cacheNames = "products")`.
- `productLabels`: được chọn **riêng ở method** `label` để lưu tên sản phẩm.
- Khi cập nhật/xóa sản phẩm, cả vùng tên sản phẩm cũng phải được invalidation. `@Caching` giúp khai báo đồng thời những operation cần thiết.

Dữ liệu gốc là repository trong bộ nhớ để dễ theo dõi số lần đọc; một ứng dụng thật thay bằng repository/database phù hợp. Dùng JDK 17+ và Maven.

**Cấu trúc tệp:**

```text
cache-config-demo/
├── pom.xml
└── src/main/java/CacheConfigDemo.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-config-demo</artifactId>
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

**`src/main/java/CacheConfigDemo.java`:**

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.Caching;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfigDemo {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products", "productLabels");
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
        private final AtomicInteger loadCount = new AtomicInteger();

        public ProductRepository() {
            data.put("P1", new Product("P1", "Bút"));
        }

        public Product find(String id) {
            loadCount.incrementAndGet();
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
            return loadCount.get();
        }
    }

    @CacheConfig(cacheNames = "products")
    public static class ProductService {
        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        // Dùng region products mặc định của lớp.
        @Cacheable(key = "#p0", unless = "#result == null")
        public Product find(String id) {
            return repository.find(id);
        }

        // Ghi đè cacheNames: lưu tên ở productLabels.
        @Cacheable(
            cacheNames = "productLabels",
            key = "#p0",
            unless = "#result == null"
        )
        public String label(String id) {
            Product product = repository.find(id);
            return product == null ? null : product.name();
        }

        // @CachePut không nêu cacheNames -> lấy products của lớp.
        // Evict riêng productLabels vì tên cũng đã thay đổi.
        @Caching(
            put = @CachePut(key = "#p0.id()"),
            evict = @CacheEvict(
                cacheNames = "productLabels",
                key = "#p0.id()"
            )
        )
        public Product save(Product product) {
            return repository.save(product);
        }

        // Evict hai projection cùng key. Evict đầu tiên
        // kế thừa cacheNames=products từ @CacheConfig.
        @Caching(evict = {
            @CacheEvict(key = "#p0"),
            @CacheEvict(cacheNames = "productLabels", key = "#p0")
        })
        public void delete(String id) {
            repository.delete(id);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(CacheConfigDemo.class)) {
            ProductService service = context.getBean(ProductService.class);
            ProductRepository repo = context.getBean(ProductRepository.class);

            System.out.println("find #1: " + service.find("P1"));
            System.out.println("find #2: " + service.find("P1"));
            System.out.println("reads: " + repo.reads());

            System.out.println("label #1: " + service.label("P1"));
            System.out.println("label #2: " + service.label("P1"));
            System.out.println("reads: " + repo.reads());

            service.save(new Product("P1", "Bút xanh"));
            System.out.println("after save product: " + service.find("P1"));
            System.out.println("after save label: " + service.label("P1"));
            System.out.println("reads: " + repo.reads());

            service.delete("P1");
            System.out.println("after delete product: " + service.find("P1"));
            System.out.println("reads: " + repo.reads());
        }
    }
}
```

**Chạy trong thư mục chứa `pom.xml`:**

```bash
mvn -q compile exec:java -Dexec.mainClass=CacheConfigDemo
```

**Dữ liệu in bởi chương trình** (không tính log Maven/Spring tùy môi trường):

```text
find #1: Product[id=P1, name=Bút]
find #2: Product[id=P1, name=Bút]
reads: 1
label #1: Bút
label #2: Bút
reads: 2
after save product: Product[id=P1, name=Bút xanh]
after save label: Bút xanh
reads: 3
after delete product: null
reads: 4
```

**Giải thích từng giai đoạn:**

1. Lần đầu gọi `find("P1")` miss ở `products/P1`, đọc nguồn một lần; lần hai hit, nên số lượt đọc vẫn bằng 1.
2. `label("P1")` dùng `productLabels/P1` do **method override cacheNames**, lần đầu miss làm số lượt đọc thành 2; lần sau hit trong vùng riêng của nó.
3. `save(P1, "Bút xanh")` chạy nguồn, sau đó thao tác `@CachePut` ghi giá trị product mới vào `products/P1` (kế thừa lớp). Phần `@CacheEvict` xóa `productLabels/P1` vì tên cần được tải lại.
4. `find("P1")` sau save hit product đã cập nhật. `label("P1")` miss rồi đọc tên mới, nên số lượt đọc thành 3.
5. `delete("P1")` xóa nguồn và evict entry cùng key ở cả hai vùng. `find("P1")` sau delete miss, nguồn trả null, `unless` không lưu null, và số lượt đọc thành 4.

Đây là ứng dụng một JVM dùng `ConcurrentMapCacheManager`. Nó minh họa tên vùng, quy tắc key, ưu tiên annotation và invalidation; không thể dùng làm bằng chứng có đồng bộ phân tán hoặc transaction nguyên tử giữa cache và database.

## 6. Thiết kế `keyGenerator` dùng chung: khi nào nên và không nên?

Nếu nhiều method thực sự có cùng quy tắc tạo key, có thể đặt tên generator tại lớp:

```java
@CacheConfig(
    cacheNames = "products",
    keyGenerator = "skuKeyGenerator"
)
public class SkuService {

    @Cacheable
    public Product find(String sku) { /* ... */ }

    @CacheEvict
    public void invalidate(String sku) { /* ... */ }

    // Operation-level key ghi đè keyGenerator của lớp.
    @CachePut(key = "#p0.sku()")
    public Product save(Product product) { /* ... */ }
}
```

Đây là **mảnh minh họa**, các kiểu `Product`, dependency và bean `skuKeyGenerator` cần được định nghĩa ở ứng dụng thật. `find` và `invalidate` nhận cùng kiểu tham số nên generator dùng chung có thể tạo cùng key. `save` lại nhận một đối tượng `Product`, vì vậy biểu thức `#p0.sku()` chọn đúng khóa trên output của phương thức đó.

Một bean generator minh họa (cần import `org.springframework.cache.interceptor.KeyGenerator` và `org.springframework.context.annotation.Bean`):

```java
@Bean("skuKeyGenerator")
KeyGenerator skuKeyGenerator() {
    return (target, method, params) -> {
        if (params.length != 1 || !(params[0] instanceof String sku)) {
            throw new IllegalArgumentException("Expected one String SKU");
        }
        return sku;
    };
}
```

Generator này **chỉ phù hợp với method nhận đúng một `String` SKU**, vì nó kiểm tra kiểu tham số. Không dùng nó trực tiếp cho method nhận `Product`; nếu cần hỗ trợ nhiều chữ ký thì thiết kế key generator đầy đủ hoặc đặt `key` riêng ở method.

**Lưu ý quan trọng:** đặt `keyGenerator` ở `@CacheConfig` không làm cho `@Cacheable` và `@CacheEvict` tự động chọn đúng cùng một key. Đó vẫn là một hợp đồng do người thiết kế quyết định, phải kiểm thử trên các đường đọc/sửa/xóa.

### Phân biệt bean name với biểu thức SpEL

- `keyGenerator = "skuKeyGenerator"` là **tên bean** của thuật toán tạo key.
- `key = "#p0.sku()"` là **biểu thức SpEL** được đánh giá theo tham số lời gọi.
- Hai hình thức đều tạo một giá trị key nhưng chỉ chọn **một** hình thức cho một cache operation; ưu tiên cấu hình theo method hoặc lớp theo quy tắc đã nêu.

## 7. `cacheManager` và `cacheResolver`: ví dụ điều phối backend

Một ứng dụng có thể dùng Caffeine cho dữ liệu catalog và Redis cho dữ liệu chia sẻ. Ví dụ về ý định cấu hình:

```java
@CacheConfig(
    cacheNames = "products",
    cacheManager = "catalogCacheManager"
)
public class CatalogService {

    @Cacheable
    public Product find(String id) { /* ... */ }

    @Cacheable(
        cacheNames = "productPrices",
        cacheManager = "pricingCacheManager"
    )
    public Price price(String id) { /* ... */ }
}
```

Đây cũng là **mảnh minh họa cần các bean thật**. `find` kế thừa manager catalog; `price` chỉ định manager pricing cho operation của nó. Mỗi manager phải có vùng tương ứng hoặc cơ chế tạo vùng theo quy tắc của provider. Hai cache cùng tên ở hai manager có thể là hai không gian vật lý khác nhau; vì vậy khi invalidate dữ liệu hãy chọn đúng manager lẫn key.

Nếu cần cache resolver động:

```java
@CacheConfig(cacheResolver = "dynamicCatalogCacheResolver")
public class DynamicCatalogService {
    @Cacheable
    public Product find(String id) { /* ... */ }
}
```

Bean `dynamicCatalogCacheResolver` chịu trách nhiệm chọn được cache phù hợp. Trong trường hợp dùng resolver động có thể không cần khai báo tên vùng cố định. Không đặt cả `cacheManager` và `cacheResolver` cho cùng một operation, vì resolver đã quyết định cách tìm cache.

### Vòng đời cấu hình và phạm vi ảnh hưởng

`@CacheConfig` chỉ liên quan đến **lớp được đánh dấu** và những cache operation trong lớp đó. Nó không thay đổi cấu hình của các bean Spring khác, không tạo chính sách cache trên toàn ứng dụng và không tự gắn cache vào mọi method của lớp.

`@EnableCaching` phải được khai báo trong một cấu hình Spring phù hợp để kích hoạt cơ chế annotation. Khi dùng proxy mode mặc định, lời gọi từ bean khác qua Spring proxy được interception; tự gọi `this.find(...)` trong cùng instance thường bỏ qua cache advice. Đối với phương thức `private`, `final` hoặc đối tượng tự tạo bằng `new` ngoài Spring context, hành vi proxy có thể không như kỳ vọng.

Nếu chuyển sang Spring Boot, auto-configuration có thể cung cấp manager tương ứng với dependency và properties, nhưng `@CacheConfig` vẫn chỉ là metadata mặc định; không thay vai trò cấu hình provider.

## 8. Hợp đồng nhất quán giữa các operation trong lớp

Dùng chung tên region **không đủ** để đảm bảo đúng dữ liệu. Cần đồng nhất:

| Operation | Đối số | Region | Key | Giá trị/hành vi |
| --- | --- | --- | --- | --- |
| `find("P1")` | `String id` | `products` | `"P1"` | Đọc product |
| `save(Product("P1", ...))` | `Product` | `products` | `product.id()` | Put product mới |
| `delete("P1")` | `String id` | `products` | `"P1"` | Evict đúng entry |
| `label("P1")` | `String id` | `productLabels` | `"P1"` | Đọc projection tên |
| `save/delete` ảnh hưởng tên | Product hoặc id | `productLabels` | `"P1"` | Evict projection để nạp lại |

Nếu `@CachePut` dùng key là toàn bộ object `Product` trong khi `@Cacheable` dùng chuỗi id, hai key sẽ khác nhau. `@CacheConfig(cacheNames="products")` không phát hiện hay sửa sai lệch này.

Tương tự, nếu `find` chỉ phân biệt `id` nhưng kết quả thực tế phụ thuộc `tenantId` hoặc locale, các request khác bối cảnh có thể dùng chung entry sai. Cần key mang đủ yếu tố quyết định kết quả, kể cả khi region được khai báo ở cấp lớp.

Không nhầm **thừa kế cacheNames** với **invalidation của các projection khác**. Nếu catalog có thêm danh sách theo category, tìm kiếm, tổng số và tên, thay đổi một product có thể yêu cầu xóa nhiều vùng có liên quan. Cách xử lý có thể dùng `@Caching` hoặc một cơ chế phối hợp sau commit rõ ràng.

Với các thao tác ghi database trong transaction, thời điểm eviction so với commit cần được thiết kế cụ thể. `@CacheConfig` không đảm bảo cache và database cập nhật nguyên tử. Đặc biệt nhiều instance dùng cache local có thể giữ những bản sao cũ độc lập.

## 9. Lỗi phổ biến khi sử dụng `@CacheConfig`

1. **Nghĩ rằng gắn `@CacheConfig` sẽ cache mọi method.** Sai: annotation này chỉ khai báo mặc định; vẫn cần `@Cacheable`, `@CachePut` hoặc `@CacheEvict` ở operation cần thiết.
2. **Quên `@EnableCaching`.** Annotation trên service không tự kích hoạt bộ xử lý cache.
3. **Hiểu nhầm override thành cộng gộp.** Method ghi `cacheNames = "productLabels"` thì chọn cache đó thay cho mặc định `products` của lớp.
4. **Dùng key generator chung cho chữ ký khác nhau.** Generator nhận `String sku` có thể lỗi khi method nhận `Product` hoặc `DeleteCommand`; xác định hợp đồng key theo mỗi operation.
5. **Đặt `key` và `keyGenerator` đồng thời trên cùng annotation.** Hai cách tạo key loại trừ nhau; lựa chọn cấu hình phù hợp tại một cấp.
6. **Đặt `cacheManager` và `cacheResolver` đồng thời trên cùng operation.** Resolver là cách thay thế việc lấy cache từ manager mặc định; cần ưu tiên cấu hình nhất quán.
7. **Không thống nhất key giữa đọc, ghi và xóa.** Dùng chung cache name nhưng khác key vẫn tạo stale entry và cache miss không cần thiết.
8. **Cho rằng `@CacheConfig` đặt TTL hoặc max size.** Các chính sách này thuộc backend/provider, chẳng hạn Caffeine hay Redis, không phải bốn thuộc tính của `@CacheConfig`.
9. **Áp dụng một cacheNames chung cho các kiểu dữ liệu không tương thích.** Cùng key có thể bị trả về sai kiểu nếu những method khác nhau lưu `Product` và `String` ở cùng region; tách region hoặc thiết kế key namespace rõ ràng.
10. **Bỏ quên proxy và self-invocation.** Lời gọi nội bộ `this.find(id)` có thể không được advice xử lý ở proxy mode mặc định; kiểm thử qua Spring bean.
11. **Dùng nhiều cacheNames trên lớp rồi evict `allEntries=true` thiếu kiểm soát.** Thao tác có thể xóa nhiều vùng được giải quyết cho operation; xem lại phạm vi trước khi triển khai.
12. **Xem class defaults như chính sách của toàn hệ thống.** Lớp khác vẫn có cấu hình riêng, kể cả khi đặt tên manager giống nhau; không nên suy luận từ một lớp ra mọi producer/consumer của cache.

## 10. Checklist kiểm thử và nguyên tắc chọn cấu hình

Khi đưa `@CacheConfig` vào lớp hiện có, hãy kiểm tra:

- **Scope:** những method nào thực sự có cache annotation, cache names thực tế mỗi method là gì?
- **Precedence:** method nào ghi đè tên vùng, key generator, cache manager hoặc resolver?
- **Key equality:** cùng một thực thể qua `find`/`save`/`delete` tạo ra key bằng nhau về `equals()/hashCode()` hoặc representation backend chấp nhận?
- **Hit/miss:** gọi một key hai lần; số lần truy cập nguồn có giảm như mong đợi?
- **Put/evict:** cập nhật/xóa có thay đổi hoặc loại bỏ đúng entry, kể cả cache projection phụ thuộc?
- **Provider:** manager được chọn có tên vùng hợp lệ, TTL/size/serialization đúng yêu cầu? Có nhiều JVM hay không?
- **Proxy:** lời gọi test có đi qua bean Spring và advice được bật?
- **Failure/transaction:** khi nguồn lỗi hoặc rollback, entry cũ có còn đúng? Khi eviction thất bại, ứng dụng xử lý thế nào?

Một quy ước thực tế: nếu nhiều operation của một lớp dùng **cùng tên cache hoặc cùng thuật toán tạo key**, đặt mặc định ở `@CacheConfig` để giảm lặp. Khi một method có dữ liệu hoặc cache backend khác, **ghi đè rõ ràng ngay tại method**, và kiểm thử rằng sự khác biệt ấy có chủ đích.

## Tài liệu tham khảo chính thức

- Spring Framework — Caching Annotations, mục `@CacheConfig`: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — `@CacheConfig` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheConfig.html
- Spring Framework — `@Caching` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Caching.html
- Spring Framework — `KeyGenerator` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/KeyGenerator.html
- Spring Framework — Cache Store Configuration: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
