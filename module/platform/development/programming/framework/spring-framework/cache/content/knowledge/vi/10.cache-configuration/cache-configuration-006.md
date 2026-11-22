# Annotation tổng hợp tùy chỉnh cho quy ước dùng chung trong Spring Cache

## 1. Mục tiêu và bối cảnh

Spring Framework hỗ trợ các annotation `@Cacheable`, `@CachePut`, `@CacheEvict`, `@Caching` và `@CacheConfig`. Khi nhiều service sử dụng những quy tắc giống nhau, việc lặp đi lặp lại tên cache, biểu thức key và điều kiện có thể tạo ra lỗi không nhất quán. **Annotation tổng hợp tùy chỉnh** (*custom composed annotation*) giúp định nghĩa một quy ước có tên rõ nghĩa rồi dùng lại trên nhiều phương thức.

Sau bài học, bạn sẽ biết cách:

1. Tạo annotation riêng dựa trên meta-annotation `@Cacheable`, `@CachePut` và `@CacheEvict`.
2. Dùng `@Target` và `@Retention(RUNTIME)` chính xác để Spring nhận diện metadata.
3. Quy định thống nhất cache name, key, `unless` và lựa chọn manager/resolver khi phù hợp.
4. Sử dụng `@AliasFor` để cho phép override một số thuộc tính có kiểm soát.
5. Phân biệt composed annotation với `@CacheConfig` và cấu hình `@EnableCaching`.
6. Viết ví dụ Java 17/Spring Boot chạy được, cùng bộ kiểm thử để phát hiện proxy, key và cache invalidation sai.

Ví dụ xuyên suốt là dịch vụ đọc, đổi tên và xóa sản phẩm. Các thao tác phải dùng **cùng cache identity** để việc cập nhật có hiệu lực với lần đọc tiếp theo.

## 2. Vấn đề khi khai báo lặp lại

Giả sử các method đọc sản phẩm đều khai báo:

~~~java
// Minh họa trong một Spring-managed service.
@Cacheable(
        cacheNames = "productsById",
        key = "#p0",
        unless = "#result == null"
)
public Product findById(String id) {
    return repository.findById(id).orElse(null);
}
~~~

Một service mới có thể bỏ `unless`, đổi nhầm `"productsById"` thành `"products"`, hoặc dùng tất cả đối số làm key. Một update có thể dùng `@CachePut` nhưng tính thêm đối số `newName` vào key, khiến dữ liệu cũ còn được đọc. Khi hệ thống phát triển, việc tìm và sửa mọi annotation thủ công rất dễ thiếu sót.

Hãy định nghĩa một annotation có tên mang nghĩa nghiệp vụ:

~~~java
@CachedProduct
public Product findById(String id) {
    return repository.findById(id).orElse(null);
}
~~~

`@CachedProduct` là cú pháp ngắn của **một quy ước cụ thể**: dùng cache tên `"productsById"`, lấy đối số đầu làm key và không lưu kết quả null. Khi quy tắc được tập trung hóa, tên annotation giúp reviewer hiểu chính sách ngay tại nơi dùng.

Tuy nhiên, tính đúng đắn của quy ước vẫn phụ thuộc chữ ký và dữ liệu: `#p0` chỉ đúng nếu đối số đầu là định danh sản phẩm và đủ phân biệt mọi kết quả trong cùng cache. Annotation không tự suy ra tenant, locale, user, kiểu projection hay quyền truy cập.

## 3. Meta-annotation được Spring diễn giải như thế nào?

Java cho phép annotation được đặt trên một annotation khác. Spring Cache nhận diện `@Cacheable`, `@CachePut`, `@CacheEvict` và `@CacheConfig` làm **meta-annotation** trong cơ chế caching có hỗ trợ.

Một định nghĩa tối thiểu:

~~~java
package example.cache;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.cache.annotation.Cacheable;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Cacheable(
        cacheNames = "productsById",
        key = "#p0",
        unless = "#result == null"
)
public @interface CachedProduct {}
~~~

Giải thích:

| Thành phần | Chức năng |
| --- | --- |
| `public @interface CachedProduct` | Định nghĩa annotation Java có tên riêng |
| `@Target(ElementType.METHOD)` | Quy định annotation được đặt trên phương thức |
| `@Retention(RetentionPolicy.RUNTIME)` | Giữ metadata ở runtime để Spring nhận diện |
| `@Documented` | Hiển thị annotation trong Javadoc; không tự kích hoạt cache |
| `@Cacheable(...)` | Chính cache operation mà Spring thực thi |
| `cacheNames = "productsById"` | Tên vùng cache dùng chung |
| `key = "#p0"` | SpEL lấy đối số đầu của method làm key |
| `unless = "#result == null"` | Không put kết quả null mới tính vào cache |

**Quan trọng:** tự tạo annotation chưa đủ. Ứng dụng phải bật caching, có `CacheManager` phù hợp và đi qua Spring proxy/interceptor. Composed annotation không thay đổi nguyên tắc đánh giá cache hit/miss của `@Cacheable`.

### Luồng thực thi

~~~text
Caller gọi bean có @CachedProduct
                 |
                 v
             Spring proxy
                 |
                 v
Đọc metadata @CachedProduct
  -> meta @Cacheable(cacheNames="productsById",
                     key="#p0", unless="#result == null")
                 |
                 v
CacheManager tra cache "productsById", key theo ID
             /             \
           HIT             MISS
            |                |
       Trả dữ liệu        Chạy method
        từ cache             |
                              v
                      Kiểm tra unless
                         /       \
                      true       false
                       |           |
                   Không put       Put cache
                       \           /
                        Trả kết quả
~~~

Nếu cache hit, method có thể không chạy. `unless` được dùng để quyết định lưu **kết quả mới** trên đường miss; nó không tự kiểm tra lại một entry đã cache. Nếu nguồn dữ liệu thay đổi, cần `@CachePut`, `@CacheEvict`, TTL hoặc cơ chế đồng bộ riêng.

## 4. Quy ước cần có hợp đồng rõ ràng

Một annotation dùng chung nên có tài liệu mô tả các giả định:

~~~text
Tên: @CachedProduct
Hành vi: @Cacheable
Cache: productsById
Key: đối số đầu, kiểu String, là productId duy nhất toàn hệ thống
Giá trị: Product hoặc null
Không lưu: null
Chỉ dùng: method đọc Product theo productId
Không dùng: query danh sách, method multi-tenant thiếu scope, DTO khác kiểu
~~~

Bảng quyết định:

| Method | Có nên dùng `@CachedProduct` này? | Giải thích |
| --- | --- | --- |
| `find(String productId)` | Có, nếu ID duy nhất | Đối số đầu đúng là cache identity |
| `find(String productId, String traceId)` | Có thể | Bỏ traceId nếu nó không ảnh hưởng nội dung |
| `find(String tenantId, String productId)` | **Không** | `#p0` chỉ là tenantId, nhiều sản phẩm trùng key |
| `findSummary(String productId)` | Không mặc định | Summary và Detail có projection khác |
| `search(String category, int page)` | Không | Kết quả danh sách cần key riêng |
| `rename(String id, String name)` | Dùng annotation put tương ứng | Update phải luôn chạy và trả Product mới |
| `delete(String id)` | Dùng annotation evict tương ứng | Xóa entry sau khi xóa nguồn |

Nếu sản phẩm chỉ duy nhất trong từng tenant, cache identity cần bao gồm **`tenantId` và `productId`** hoặc cache name phải được phân vùng đúng. Nếu kết quả khác theo người xem hay locale, key cũng cần xét yếu tố đó. **Không** mặc định dùng một annotation theo ID cho mọi phương thức chỉ vì chúng cùng đọc một entity.

## 5. Ví dụ hoàn chỉnh: ba annotation cho read/put/evict

Ví dụ dùng **Java 17, Spring Boot 3.3.5, Maven** và `ConcurrentMapCacheManager`. Để minh họa rõ, `productId` ở đây duy nhất toàn ứng dụng; `ConcurrentHashMap` chỉ giả lập nguồn dữ liệu. Chúng ta tạo ba annotation tùy chỉnh:

- `@CachedProduct` dùng meta `@Cacheable` để đọc và cache kết quả.
- `@PutProductCache` dùng meta `@CachePut` để cập nhật entry sau method.
- `@EvictProductCache` dùng meta `@CacheEvict` để xóa entry.

Cả ba cùng **cache name** và **key**. Nhờ đó `rename(id,newName)` sẽ thay đúng mục mà `find(id)` sử dụng, dù chữ ký update có hai đối số.

### Cấu trúc thư mục

~~~text
composed-cache-demo/
├── pom.xml
└── src/main/java/example/cache/
    ├── DemoApplication.java
    ├── CachedProduct.java
    ├── PutProductCache.java
    ├── EvictProductCache.java
    └── ProductService.java
~~~

### `pom.xml`

~~~xml
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
    <artifactId>composed-cache-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
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
~~~

### `src/main/java/example/cache/CachedProduct.java`

~~~java
package example.cache;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.cache.annotation.Cacheable;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Cacheable(
        cacheNames = "productsById",
        key = "#p0",
        unless = "#result == null"
)
public @interface CachedProduct {}
~~~

### `src/main/java/example/cache/PutProductCache.java`

~~~java
package example.cache;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.cache.annotation.CachePut;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@CachePut(
        cacheNames = "productsById",
        key = "#p0"
)
public @interface PutProductCache {}
~~~

`@CachePut` luôn chạy method rồi cache **giá trị trả về**. Nó không lấy tham số `newName` làm giá trị cache và cũng không bỏ qua method khi cache đã có dữ liệu.

### `src/main/java/example/cache/EvictProductCache.java`

~~~java
package example.cache;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.cache.annotation.CacheEvict;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@CacheEvict(
        cacheNames = "productsById",
        key = "#p0"
)
public @interface EvictProductCache {}
~~~

`@CacheEvict` mặc định xóa sau khi method thực hiện thành công. Trong demo, đây là lúc loại bỏ mục cache của một sản phẩm đã bị xóa khỏi nguồn.

### `src/main/java/example/cache/ProductService.java`

~~~java
package example.cache;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ConcurrentMap<String, Product> store =
            new ConcurrentHashMap<>();
    private final AtomicInteger sourceLoads = new AtomicInteger();

    public record Product(String id, String name, int version) {}

    public ProductService() {
        store.put("P1", new Product("P1", "Pen", 1));
    }

    @CachedProduct
    public Product find(String id) {
        sourceLoads.incrementAndGet();
        return store.get(id);
    }

    @PutProductCache
    public Product rename(String id, String newName) {
        return store.compute(id, (key, oldValue) -> {
            if (oldValue == null) {
                throw new IllegalArgumentException("Unknown product");
            }
            return new Product(id, newName, oldValue.version() + 1);
        });
    }

    @EvictProductCache
    public void delete(String id) {
        store.remove(id);
    }

    public int sourceLoads() {
        return sourceLoads.get();
    }
}
~~~

### `src/main/java/example/cache/DemoApplication.java`

~~~java
package example.cache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("productsById");
    }

    @Bean
    CommandLineRunner demo(ProductService products) {
        return args -> {
            System.out.println(products.find("P1"));
            System.out.println(products.find("P1"));
            System.out.println("loads=" + products.sourceLoads());

            System.out.println(products.rename("P1", "Blue Pen"));
            System.out.println(products.find("P1"));
            System.out.println("loads=" + products.sourceLoads());

            products.delete("P1");
            System.out.println(products.find("P1"));
            System.out.println("loads=" + products.sourceLoads());
        };
    }
}
~~~

### Chạy và kiểm chứng

Chạy từ thư mục `composed-cache-demo`, với Java 17+ và Maven:

~~~bash
mvn -q spring-boot:run
~~~

Ngoài log khởi động Spring, `CommandLineRunner` in:

~~~text
Product[id=P1, name=Pen, version=1]
Product[id=P1, name=Pen, version=1]
loads=1
Product[id=P1, name=Blue Pen, version=2]
Product[id=P1, name=Blue Pen, version=2]
loads=1
null
loads=2
~~~

Giải thích:

1. `find("P1")` đầu tiên miss, chạy method và cache `Pen/v1`; lần thứ hai hit, nên `loads=1`.
2. `rename("P1","Blue Pen")` vẫn chạy ngay cả khi cache đang có `"P1"`. Annotation meta `@CachePut` ghi `Blue Pen/v2` lên chính key `"P1"`; lần đọc sau hit v2, `loads` vẫn là 1.
3. `delete("P1")` xóa nguồn và meta `@CacheEvict` loại entry `"P1"`. Lần đọc sau miss, chạy method và trả `null`, tăng `loads=2`.
4. Do composed `@CachedProduct` có `unless="#result == null"`, lần đọc trả `null` này **không** lưu entry mới.

**Phạm vi demo:** cache là nội bộ JVM, không có TTL, phân quyền tenant, transaction database hay cơ chế đồng bộ giữa các instance. Khi đổi sang Redis/Caffeine, cần kiểm chứng cách định nghĩa cache, serializer và chính sách thời hạn sống.

## 6. `@AliasFor`: tạo annotation vừa chuẩn hóa vừa linh hoạt

Annotation cố định giúp governance rõ ràng. Nhưng một nhóm method có thể dùng chung **cache name**, còn **key** và **unless** khác nhau. Spring cung cấp `@AliasFor` để tùy biến có kiểm soát các thuộc tính của meta-annotation.

Ví dụ tạo `@CachedReport`:

~~~java
package example.reports;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.core.annotation.AliasFor;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Cacheable(cacheNames = "reportViews")
public @interface CachedReport {

    @AliasFor(annotation = Cacheable.class, attribute = "key")
    String key() default "";

    @AliasFor(annotation = Cacheable.class, attribute = "unless")
    String unless() default "";
}
~~~

Sử dụng trong method đọc báo cáo:

~~~java
// Đoạn minh họa: Report và repository do ứng dụng cung cấp.
@CachedReport(
        key = "T(java.util.List).of(#p0, #p1)",
        unless = "#result == null"
)
public Report find(String tenantId, String reportId) {
    return repository.find(tenantId, reportId);
}
~~~

Spring đọc meta `@Cacheable(cacheNames="reportViews")` và sử dụng các thuộc tính được override từ `@CachedReport`. Tên vùng được giữ cố định; biểu thức key dùng `(tenantId, reportId)` để tránh va chạm hai tenant có cùng reportId. `List.of(...)` không chấp nhận null và là key cấu trúc phù hợp cho minh họa in-memory; với backend như Redis cần xác định serializer/key codec.

### Những nguyên tắc khi dùng `@AliasFor`

- Thuộc tính được alias phải thực sự có ở meta-annotation. Ví dụ `Cacheable.key` và `Cacheable.unless` đều là `String` với mặc định rỗng.
- Khai báo `@AliasFor(annotation = Cacheable.class, attribute = "key")` nghĩa là `key()` trong annotation tùy chỉnh override `key` của meta `@Cacheable`.
- Kiểu dữ liệu phải khớp. `cacheNames` là `String[]`, `sync` là `boolean`, `key` là `String`; không tạo alias khác kiểu.
- Mặc định của thuộc tính alias/override phải tuân thủ hợp đồng Spring; dùng `""` cho các thuộc tính chuỗi trong ví dụ là phù hợp.
- Không expose mọi thuộc tính chỉ vì có thể. Nếu tên cache được quyết định trong quy ước chung, giữ cố định `cacheNames` thay vì cho phép caller tùy tiện đổi.
- Một operation không được khai báo đồng thời `key` và `keyGenerator`; tương tự `cacheManager` và `cacheResolver` là cặp lựa chọn loại trừ nhau.
- Tránh các alias trùng lặp hoặc xung đột giá trị. Kiểm thử Spring tạo đúng merged annotation metadata và đọc đúng cache entry.

`@AliasFor` không tự làm key an toàn, không tự phân quyền và không thay thế `CacheResolver`. Nếu ngữ nghĩa key phức tạp, bạn có thể dùng một `KeyGenerator` có hợp đồng rõ hoặc một annotation riêng cho nhóm phương thức đó.

### Khi nào annotation không có thuộc tính tốt hơn?

Nếu cả tên vùng và quy tắc key luôn cố định, `@CachedProduct` từ ví dụ đầu dễ review hơn `@CachedProduct(key="...")` trên mọi method. Tính linh hoạt nên được thêm vì có nhu cầu thực, không phải nhằm tránh tạo nhiều tên annotation.

## 7. So sánh annotation tổng hợp và `@CacheConfig`

`@CacheConfig` giúp chia sẻ **mặc định cấp class** như cache name, `KeyGenerator`, `CacheManager` hoặc `CacheResolver`. Nó **không tự đánh dấu method nào sẽ được cache**.

~~~java
// Minh họa trong một service; repository và Product thuộc ứng dụng.
@Service
@CacheConfig(cacheNames = "productsById")
public class ProductLookup {
    @Cacheable(key = "#p0")
    public Product find(String id) {
        return repository.find(id);
    }
}
~~~

Ngược lại, `@CachedProduct` chứa meta `@Cacheable` nên khi gắn lên một method, chính nó **đánh dấu cache operation**.

| Công cụ | Cấp áp dụng | Mục đích |
| --- | --- | --- |
| `@EnableCaching` | Application context/configuration | Kích hoạt caching annotation |
| `CacheManager`/`CachingConfigurer` | Application context | Định nghĩa backend và mặc định toàn cục |
| `@CacheConfig` | Class | Chia sẻ cấu hình mặc định cho các method trong class |
| `@Cacheable`/`@CachePut`/`@CacheEvict` | Operation | Đánh dấu hoạt động đọc, ghi, xóa cache |
| Composed annotation | Nhiều operation ở nhiều class | Đóng gói operation và quy ước dùng chung |
| `@AliasFor` | Định nghĩa composed annotation | Cho phép override thuộc tính meta có chọn lọc |

Khi composed annotation đã chỉ rõ `cacheNames`, đó là cấu hình ở cấp operation; đừng kỳ vọng `@CacheConfig(cacheNames="other")` trên class thay đổi tên đó. Thứ tự khái quát của Spring là cấu hình operation cụ thể có ưu tiên so với mặc định class và toàn cục.

`@CacheConfig` cũng có thể dùng làm meta-annotation theo tài liệu Spring, nhưng cần phân biệt **cấu hình mặc định** với **đánh dấu operation**. Hãy bắt đầu bằng cách đơn giản nhất đáp ứng nhu cầu.

## 8. Duy trì đồng nhất giữa đọc, cập nhật và vô hiệu hóa

Nếu bạn tạo các annotation riêng cho read, update và evict, phải bảo đảm chúng cùng nhắm:

~~~text
CacheManager: cùng backend
cacheName:    productsById
cacheKey:     productId
cachedValue:  Product đúng projection
~~~

Dù annotation giúp tái sử dụng, khi chữ ký đổi từ:

~~~java
public Product rename(String id, String newName)
~~~

thành:

~~~java
public Product rename(UpdateRequest request, String id)
~~~

thì quy ước `key="#p0"` **không còn lấy ID**. `@PutProductCache` lúc đó ghi theo đối tượng request, và `@CachedProduct` theo ID vẫn hit mục cũ.

Với nhiều loại chữ ký, có thể chọn một factory/`KeyGenerator` chung được kiểm thử hoặc xây annotation riêng có key phù hợp. Đừng viết một composed annotation quá tổng quát rồi bắt các method không tương thích dùng nó.

Một `@CachePut` chỉ nên dùng khi method trả về **đúng giá trị** mà reader mong đợi. Nếu method update trả `boolean`, `void` hay ID, hãy cân nhắc `@CacheEvict`, để lần đọc sau tự tải lại DTO chuẩn. Với kết quả `null`, một `unless` trên put có thể từ chối ghi nhưng **không xóa entry cũ**; nghiệp vụ cần xác định khi nào phải evict.

Nếu một update làm ảnh hưởng cache danh sách/search/report, put theo ID không tự làm mới các vùng ấy. Có thể dùng `@Caching` để gom nhiều evict/put khi biết key liên quan, hoặc dùng invalidation theo event, version và TTL phù hợp.

## 9. Giới hạn proxy, AspectJ và method visibility

Spring nhận diện composed cache annotation trong chế độ **proxy** có hỗ trợ. Điều đó không có nghĩa annotation làm mọi lời gọi đều được intercept:

- Phải bật `@EnableCaching` trên cấu hình Spring, và có `CacheManager`/provider phù hợp.
- Gắn annotation lên method `public` của concrete Spring-managed bean là trường hợp ít bất ngờ nhất.
- Lời gọi từ bean khác đi qua proxy có thể được intercept. Gọi `this.find(id)` ngay trong cùng bean thường **không** đi qua proxy.
- Không phụ thuộc caching advice khi gọi method trong constructor hoặc `@PostConstruct`, lúc proxy chưa hoạt động đầy đủ.
- Khi annotation đặt lên interface hoặc method không public, hành vi phụ thuộc cơ chế proxy/weaving; hãy kiểm thử trên cấu hình thực tế.
- Với **AspectJ weaving**, những aspect cache chuẩn trong `spring-aspects` hỗ trợ annotation chuẩn. Custom annotation cần cấu hình/viết aspect phù hợp nếu muốn được nhận diện ở chế độ đó; đừng mặc định giống proxy mode.
- Đừng gắn thêm `@Cacheable` trực tiếp lên method đã dùng composed `@Cacheable` chỉ để “chắc ăn”: nhiều operation cùng tác dụng có thể gây trùng lặp hoặc ngữ nghĩa khó dự đoán.

Nếu một annotation cần dùng ở class, đừng tự mở rộng `@Target(TYPE)` mà không kiểm tra cách cache operation được áp dụng lên các method. Ví dụ này chủ đích chỉ cho phép `METHOD`.

## 10. Phạm vi dữ liệu, bảo mật và tính nhất quán

**Composed annotation không phải ranh giới cấp quyền.** Nếu result thay đổi theo user, tenant, role, locale hoặc quyền, cache key phải phản ánh các yếu tố ảnh hưởng kết quả; đồng thời mỗi yêu cầu cần được authorization đúng chỗ.

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ: không đặt kiểm tra quyền duy nhất trong thân cached method.
@CachedProduct
public Product find(String id) {
    authorizeCurrentUser(id);
    return repository.find(id);
}
~~~

Khi hit cache, Spring có thể bỏ qua thân method nên `authorizeCurrentUser` không chạy. Hãy kiểm tra quyền ở facade/entrypoint luôn chạy trước cached service, hoặc tổ chức interceptor với thứ tự đã kiểm thử. Định danh scope phải đến từ principal/ngữ cảnh tin cậy, không chỉ dựa vào chuỗi gửi từ client.

**Composed annotation cũng không đảm bảo nhất quán giao dịch.** Một `@CachePut` có thể ghi cache theo thời điểm khác với database commit; nếu rollback hoặc có read/write race, entry cũ/mới có thể không phù hợp nguồn dữ liệu. Cần chính sách after-commit, transaction-aware cache, version, locking hoặc event invalidation theo yêu cầu. Cache trong JVM không tự đồng bộ với các replica khác.

Đổi quy ước key hoặc tên cache khi deploy có thể khiến entry cũ không còn được tìm thấy, hoặc nhiều instance dùng hai cách mã hóa khác nhau. Phải có kế hoạch rollout, version và xóa entry cũ, đặc biệt khi dùng Redis.

## 11. Kiểm thử composed annotation

Đừng chỉ dùng reflection kiểm tra rằng Java annotation có `@Cacheable`. Điều cần chứng minh là **hành vi thực tế qua Spring container**.

| Ca kiểm thử | Cách thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Cache hit | Gọi `find("P1")` hai lần qua injected bean | Source chỉ chạy một lần |
| Update cùng key | `rename("P1","Blue Pen")`, rồi `find("P1")` | Đọc ngay bản mới; source không tăng |
| Evict | `delete("P1")`, rồi `find("P1")` | Không trả entry cũ |
| `unless` | Gọi `find("missing")` hai lần | Kết quả null không được cache, source chạy lại |
| `@AliasFor` | Dùng `@CachedReport(key=...)` | Key dùng đúng expression được override |
| Sai chữ ký | ID ở vị trí khác `#p0` | Test phát hiện định danh sai |
| Sai cacheName | Put và read khác vùng | Test phát hiện read vẫn stale |
| Multi-tenant | Hai tenant có cùng product ID | Không trộn dữ liệu nếu kết quả khác scope |
| Self-invocation | Gọi `this.find(...)` trong cùng bean | Nhận biết proxy bị bỏ qua |
| Cấu hình | Không bật `@EnableCaching` | Không kỳ vọng cache advice chạy |
| Provider thực | Redis/Caffeine | Serializer, TTL, key và invalidation tương thích |

Có thể triển khai test bằng `@SpringBootTest`, inject service và `CacheManager`, assert trực tiếp counter hoặc số lần mock repository được gọi. Một unit test chỉ `new ProductService()` không có Spring proxy nên không chứng minh caching hoạt động.

### Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Annotation tự viết không kích hoạt caching | Chưa bật `@EnableCaching`, sai bean/proxy | Kiểm tra cấu hình và đường gọi |
| Runtime không nhận ra annotation | Retention/target hoặc meta-annotation sai | Dùng `RUNTIME`, `METHOD`, kiểm thử hợp đồng |
| `@AliasFor` không override như dự tính | Sai tên kiểu thuộc tính hoặc metadata meta | Kiểm tra Javadoc và integration test |
| `@CachedProduct` làm trộn sản phẩm | Đối số đầu không phải productId duy nhất | Thiết kế identity theo toàn bộ scope |
| Put không sửa entry read | Khác key, cache name hoặc manager | So sánh cache identity của hai operation |
| Cache chứa Boolean thay Product | Gắn `@CachePut` lên method trả status | Dùng `@CacheEvict` hoặc trả Product đầy đủ |
| Hit sau khi nguồn đã thay đổi | Thiếu invalidation | Dùng put/evict/TTL hoặc versioning |
| Cùng annotation chạy khác ở AspectJ | Aspect chuẩn không nhận custom annotation | Cấu hình aspect riêng hoặc dùng proxy |
| Test không thấy cache hit | Tạo service bằng `new`, gọi nội bộ | Test qua injected Spring bean |
| Cache không thống nhất giữa replica | Dùng `ConcurrentMapCacheManager` cục bộ | Chọn backend dùng chung nếu nghiệp vụ cần |

## 12. Tổ chức quy ước cache thành API dùng chung

Trong codebase nhiều module, có thể đặt annotation trong package như `com.example.shared.cache`. Mỗi annotation cần JavaDoc mô tả:

- Phạm vi dữ liệu và điều kiện sử dụng: product ID toàn cục, theo tenant, theo user hay theo projection.
- Phần nào của chữ ký dùng tạo key; có xử lý `null`, `Optional` hay không.
- Method trả kiểu gì để `@CachePut` có thể ghi an toàn.
- Tên cache do annotation ấn định hay được override; nếu override, giới hạn hợp lệ là gì.
- Có phụ thuộc bean `KeyGenerator`, `CacheResolver`, `CacheManager` tên nào không.
- Chính sách invalidation liên quan; nhất là những danh sách, search, thống kê phụ thuộc dữ liệu đã cập nhật.
- Bộ kiểm thử và kế hoạch version khi đổi schema key/namespace.

Tên annotation nên nêu ý nghĩa nghiệp vụ như `@CachedProductById` hoặc `@EvictProductById`, tránh tên mơ hồ như `@Fast` hoặc `@Cached` khi chúng che giấu quá nhiều hành vi. Một annotation có thể giảm lặp mã nhưng cũng có thể lan rộng lỗi cấu hình; vì thế API càng dùng nhiều nơi càng cần test hợp đồng rõ ràng.

## 13. Bài tập thực hành

**Bài 1.** Có nhiều service cùng dùng `@Cacheable(cacheNames="productsById", key="#p0", unless="#result == null")`. Nên làm gì?  
**Đáp án:** tạo composed `@CachedProduct` với meta-annotation chứa các thuộc tính ấy; ghi rõ hợp đồng rằng `#p0` là product ID duy nhất.

**Bài 2.** `find(String tenantId, String productId)` có dùng được `@CachedProduct` ở ví dụ không?  
**Đáp án:** không an toàn. Key `#p0` là tenant ID, khiến nhiều sản phẩm trong một tenant trùng nhau. Cần key gồm `(tenantId,productId)` hoặc vùng cache tách theo tenant với quy tắc đáng tin.

**Bài 3.** Tại sao `@Retention(RUNTIME)` là cần thiết?  
**Đáp án:** để metadata annotation được giữ ở runtime, cho phép Spring phát hiện và diễn giải thành cache operation.

**Bài 4.** `@CachedProduct` có tự kích hoạt caching thay `@EnableCaching` không?  
**Đáp án:** không. Annotation là metadata; Spring cần cấu hình kích hoạt cache interception và manager tương ứng.

**Bài 5.** Khi nào nên cho `@AliasFor` override `key`?  
**Đáp án:** khi một nhóm phương thức cần cùng cache name/quy tắc chung nhưng có cách xây key khác nhau có kiểm soát. Nếu toàn bộ method dùng một key cố định, annotation không có thuộc tính thường đơn giản hơn.

**Bài 6.** Nếu `rename(String id,String name)` đổi sang trả `boolean`, `@PutProductCache` còn phù hợp không?  
**Đáp án:** không nếu vùng đọc chứa `Product`. `@CachePut` sẽ put `Boolean`; nên đổi trả về `Product` mới hoặc dùng eviction.

**Bài 7.** Một method trong cùng bean gọi `this.find("P1")`; composed annotation có bảo đảm cache hoạt động không?  
**Đáp án:** không trong proxy mode mặc định, vì self-invocation thường bỏ qua proxy. Hãy test qua Spring-managed bean và tổ chức lời gọi phù hợp.

**Bài 8.** Có thể dùng composed annotation với AspectJ weaving mà không cần đổi gì không?  
**Đáp án:** không nên giả định. Aspect chuẩn nhận annotation cache chuẩn; custom annotation có thể cần aspect riêng hoặc chọn proxy mode.

## Tài liệu chính thức

- Spring Framework, Declarative Annotation-based Caching, phần **Using Custom Annotations**: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework, Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Annotation Programming Model, `@AliasFor`: https://github.com/spring-projects/spring-framework/wiki/Spring-Annotation-Programming-Model
- Javadoc `@AliasFor`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/AliasFor.html
- Spring Boot, Caching providers: https://docs.spring.io/spring-boot/reference/io/caching.html

**Ghi nhớ:** annotation tổng hợp giúp chuyển các cache operation và quy tắc lặp lại thành **một API thống nhất**. Nó chuẩn hóa cache name/key/điều kiện nhưng không tự mở caching, không thay thế kiểm tra quyền, không xử lý thay đổi dữ liệu nguồn và không vượt qua giới hạn của Spring proxy. Thiết kế hợp đồng dùng chung rõ ràng và kiểm thử hành vi thực tế trước khi sử dụng rộng rãi.