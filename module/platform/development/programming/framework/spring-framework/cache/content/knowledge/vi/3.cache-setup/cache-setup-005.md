# Định nghĩa tên cache tường minh hoặc tạo động trong Spring Cache

## Mục tiêu

Sau bài học, bạn có thể xác định **tên cache** được lấy từ đâu, khai báo cache cố định bằng `cacheNames`/`@CacheConfig`, phân biệt **chọn tên cache theo lời gọi** với **tạo vùng cache mới khi tên chưa tồn tại**, và triển khai `CacheResolver` để chọn vùng cache theo dữ liệu runtime. Bạn cũng sẽ biết cách giới hạn số tên cache động, kiểm tra việc đọc/xóa đúng vùng và tránh nhầm lẫn giữa tên cache với khóa của từng phần tử.

Bối cảnh: một hệ thống bán hàng có kết quả `getProduct(tenantId, productId)`. Có hai thiết kế hợp lệ: lưu mọi tenant vào cache tên cố định `"products"` với khóa chứa cả `tenantId` lẫn `productId`, hoặc chuyển từng tenant vào một vùng cache riêng như `"products.north"` và `"products.south"` rồi dùng `productId` làm khóa bên trong vùng đó. Bài này tập trung vào **cách định nghĩa và phân giải tên vùng cache**, cùng điều kiện để lựa chọn ấy có hiệu lực.

## 1. Tên cache khác khóa cache như thế nào?

Một mục cache được xác định về mặt logic bởi bộ `(cacheName, key)`:

~~~text
CacheManager
    |
    +-- Cache "products.north"
    |       +-- key "P1" -> Product north/P1
    |       +-- key "P2" -> Product north/P2
    |
    +-- Cache "products.south"
            +-- key "P1" -> Product south/P1
~~~

- **Cache name** là tên của vùng/namespace, ví dụ `products.north`. `CacheManager` tìm đối tượng `Cache` bằng tên thông qua `getCache(name)`.
- **Cache key** phân biệt từng kết quả trong **một** vùng, ví dụ `"P1"`. `key` (SpEL) hoặc `KeyGenerator` quyết định khóa, không quyết định tên vùng.
- **CacheResolver** trả về tập `Cache` mà một operation sẽ dùng; nó có thể chọn dựa trên tên đã khai báo hoặc đối số của lời gọi.
- **Backend/provider** như `ConcurrentMapCache`, Caffeine hay Redis quyết định cách lưu và quản lý cache thực tế. `CacheManager` và provider có thể hạn chế, tạo động hoặc báo không tìm thấy tên cache.

Bởi vậy `(products.north, P1)` và `(products.south, P1)` là **hai mục khác nhau**, dù khóa đều là `"P1"`. Đổi tên cache cũng giống đổi nơi tìm dữ liệu: các mục ở vùng cũ không tự chuyển sang vùng mới.

### Bản đồ trách nhiệm

| Thành phần | Đầu vào chủ yếu | Kết quả | Có quyết định tên cache không? |
| --- | --- | --- | --- |
| `@Cacheable(cacheNames="products")` | Khai báo annotation | Cung cấp danh sách tên tường minh | Có, khi dùng resolver mặc định |
| `@CacheConfig(cacheNames="products")` | Khai báo trên class | Mặc định chung cho các operation bên trong | Có, theo cấu hình lớp |
| `CacheResolver` | Operation, phương thức, đối số runtime | Một hay nhiều đối tượng `Cache` | **Có**, kể cả động |
| `CacheManager` | `getCache(String name)` | Đối tượng `Cache` hoặc `null` | Quản lý/tra cứu/tạo vùng tùy triển khai |
| `key`/`KeyGenerator` | Đối số và metadata lời gọi | Khóa trong vùng cache | Không |
| `condition`/`unless` | Điều kiện SpEL | Có cache kết quả không | Không thay tên vùng |

Đặt tên tường minh và tạo động là **hai trục riêng**: tên có thể cố định nhưng `CacheManager` tạo vùng chứa khi cần; hoặc resolver chọn tên động nhưng manager chỉ cho phép một danh sách vùng đã được khởi tạo.

## 2. Cách 1: đặt tên cache tường minh ngay tại annotation

Với cách đơn giản nhất, khai báo `cacheNames` (hoặc alias `value`):

~~~java
// Các chữ ký minh họa; Product, repository là thành phần ứng dụng.
@Cacheable(cacheNames = "productsById", key = "#p0")
public Product getById(String productId) {
    return repository.findById(productId).orElseThrow();
}

@CacheEvict(cacheNames = "productsById", key = "#p0")
public void invalidateById(String productId) {
    // Cập nhật/xóa dữ liệu ở nơi thích hợp theo nghiệp vụ.
}
~~~

Mỗi lời gọi `getById("P1")` nhắm cache tên `"productsById"` và khóa `"P1"`; `invalidateById("P1")` có cùng tên và khóa nên nhắm đúng mục. Dấu ngoặc kép quanh tên chỉ là literal Java. Hai cách này tương đương:

~~~java
@Cacheable("productsById")
@Cacheable(cacheNames = "productsById")
~~~

Đây là **hai cách viết thay thế cho cùng một annotation**, không đặt đồng thời lên một phương thức. Tên cố định giúp cấu hình TTL, giới hạn dung lượng, metrics và việc xóa theo vùng dễ dự đoán hơn.

Không chỉ `@Cacheable`, các annotation `@CachePut` và `@CacheEvict` cũng chấp nhận `cacheNames`. Cần thống nhất tên và cách tính khóa giữa các đường **đọc, cập nhật và vô hiệu hóa**. Một lời gọi update có thể chạy thành công mà vẫn để dữ liệu cũ trong cache nếu `@CachePut` và `@Cacheable` trỏ tới hai vùng khác nhau.

### Dùng `@CacheConfig` giảm lặp trong cùng class

~~~java
// Ví dụ định nghĩa lớp minh họa; phụ thuộc repository tùy dự án.
@Service
@CacheConfig(cacheNames = "productsById")
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(key = "#p0")
    public Product find(String id) {
        return repository.findById(id).orElseThrow();
    }

    @CacheEvict(key = "#p0")
    public void invalidate(String id) {
    }
}
~~~

`@CacheConfig` cung cấp mặc định ở cấp lớp cho `cacheNames` (cũng như một số thuộc tính cache khác). Nó **không tự bật caching**: mỗi phương thức vẫn cần annotation như `@Cacheable`, `@CachePut` hoặc `@CacheEvict`; ứng dụng cần `@EnableCaching`. Khai báo cụ thể trên method có thể ghi đè mặc định tương ứng.

Tránh dùng một tên chung mơ hồ như `"data"` cho các kết quả khác loại. Ví dụ, `findBySku("42")` và `findById("42")` nếu cùng cache, cùng quy tắc khóa, có thể trùng mục. Có thể dùng tên `"productsBySku"` và `"productsById"` riêng biệt, hoặc thiết kế định danh khóa phân biệt được ngữ nghĩa.

## 3. Khai báo tên cache không đồng nghĩa với tạo vùng cache

Điểm dễ nhầm: `@Cacheable(cacheNames="productsById")` mô tả **muốn dùng tên nào**, còn vùng cache có tồn tại hoặc được tạo lúc gọi hay không là việc của `CacheManager`/provider.

`org.springframework.cache.CacheManager` có hai phương thức quan trọng:

~~~java
// Trích chữ ký API để giải thích, không phải file cần tạo.
Cache getCache(String name);
Collection<String> getCacheNames();
~~~

`getCache("productsById")` trả một `Cache` phù hợp hoặc `null` nếu manager không hỗ trợ tên này. `getCacheNames()` cho biết các tên manager hiện đang biết; danh sách không nhất thiết là danh mục cố định nếu manager hỗ trợ tạo động.

Với `ConcurrentMapCacheManager` của Spring, có hai chế độ dễ quan sát:

~~~java
// Chế độ tĩnh: chỉ chấp nhận những tên đã khai báo.
CacheManager fixed = new ConcurrentMapCacheManager(
        "productsById", "productsBySku");

// Chế độ động: tạo ConcurrentMapCache khi tên mới được yêu cầu.
CacheManager dynamic = new ConcurrentMapCacheManager();
~~~

`fixed.getCache("unknown")` trả `null`. `dynamic.getCache("unknown")` sẽ tạo vùng tên `"unknown"` ở lần truy vấn đầu. Đây là đặc điểm của **`ConcurrentMapCacheManager`**, không phải cam kết chung cho mọi `CacheManager`. Với manager/provider khác, cơ chế khai báo vùng, cache tự tạo, serializer, TTL và giới hạn tên có thể khác.

Nếu cần ví dụ tĩnh trong ứng dụng:

~~~java
@Configuration
@EnableCaching
class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("productsById", "productsBySku");
    }
}
~~~

Các đoạn trong phần này là minh họa độc lập về cấu hình; ví dụ chạy đầy đủ ở phần 6 dùng chế độ động. `ConcurrentMapCacheManager` phù hợp học tập và tình huống đơn giản trong một JVM, không cung cấp chính sách TTL và giới hạn bộ nhớ phức tạp như cache chuyên dụng.

### So sánh bốn tình huống

| Tên chọn cho mỗi lời gọi | Manager xử lý tên | Kết quả |
| --- | --- | --- |
| Tường minh `"products"` | Đã có `"products"` | Dùng đúng vùng đã có |
| Tường minh `"products"` | Manager tự tạo khi chưa có | Vùng `"products"` được tạo lần đầu dù annotation vẫn tĩnh |
| Resolver trả `"products.north"` hoặc `"products.south"` | Manager nhận tên mới và tạo động | Vùng tương ứng được tạo theo tenant |
| Resolver trả tên mới | Manager chỉ hỗ trợ danh sách tĩnh | `getCache` có thể trả `null`; resolver phải xử lý rõ ràng |

Điều này cho thấy **tên động** và **cache động được khởi tạo** là hai việc khác nhau.

## 4. Vì sao không đặt biểu thức SpEL vào `cacheNames`?

Ví dụ bên dưới **không đạt mục tiêu chọn cache theo đối số**:

~~~java
// Sai ý định: chuỗi dưới đây là tên cache literal, không phải SpEL.
@Cacheable(cacheNames = "'products.' + #p0", key = "#p1")
public Product get(String tenantId, String productId) {
    return load(tenantId, productId);
}
~~~

`cacheNames` là danh sách **tên** lấy từ annotation, không phải thuộc tính biểu thức SpEL như `key`, `condition`, `unless`. Spring không mặc định diễn giải chuỗi `"'products.' + #p0"` thành tên động khi lời gọi chạy. Trong khi đó `key="#p1"` là SpEL và được đánh giá bằng đối số thứ hai. Với nhu cầu phân vùng theo tenant, dùng `CacheResolver` phù hợp hơn.

Nếu **không thực sự cần vùng riêng**, bạn có thể giữ tên tĩnh và đưa tenant vào khóa:

~~~java
// Minh họa: một vùng chung, khóa phải xét cả tenant và productId.
@Cacheable(cacheNames = "products", key = "#p0 + ':' + #p1")
public Product get(String tenantId, String productId) {
    return load(tenantId, productId);
}
~~~

Biểu thức nối chuỗi đơn giản có thể va chạm nếu dữ liệu chứa dấu `:`; khi đó nên dùng khóa cấu trúc, `KeyGenerator` hoặc mã hóa thành phần không nhập nhằng. Thiết kế tên chung với khóa ghép thường tránh phải tạo số vùng tỷ lệ thuận với số tenant.

## 5. Cách 2: chọn tên cache lúc chạy bằng `CacheResolver`

Khi tên vùng phải phụ thuộc yêu cầu đang xử lý, Spring cung cấp interface:

~~~java
package org.springframework.cache.interceptor;

// Chữ ký rút gọn để học, không khai báo lại trong project.
public interface CacheResolver {
    Collection<? extends Cache> resolveCaches(
            CacheOperationInvocationContext<?> context);
}
~~~

`context` chứa `getMethod()`, `getTarget()`, `getArgs()` và `getOperation()`; nhờ đó resolver có thể quyết định vùng cache từ đối số, metadata hoặc một chính sách cấu hình của ứng dụng. Nó trả về **đối tượng `Cache`**, không chỉ một chuỗi tên. Một resolver thực tế thường dùng `cacheManager.getCache(name)` để tìm hoặc tạo vùng.

Khai báo trên method:

~~~java
// Minh họa: bean tenantCatalogResolver sẽ được định nghĩa ở phần 6.
@Cacheable(cacheResolver = "tenantCatalogResolver", key = "#p1")
public String read(String tenantId, String productId) {
    return loadProduct(tenantId, productId);
}
~~~

Không cần `cacheNames` khi resolver tự xác định vùng. Spring gọi resolver cho operation và dùng cache mà nó trả về. Nếu trả `null`, một collection rỗng hoặc cache không tồn tại, operation không có vùng hợp lệ để hoạt động; nên **phát hiện sớm và ném lỗi có ngữ cảnh** khi không hỗ trợ tên yêu cầu.

Lưu ý về cấu hình: **`cacheManager` và `cacheResolver` loại trừ nhau trên cùng một cache annotation**; khai báo cả hai khiến Spring báo lỗi. `cacheManager` chọn manager cho resolver mặc định; `cacheResolver` thay cách phân giải cache. Trong khi đó `key` và `keyGenerator` là một cặp loại trừ nhau khác, dùng cho **khóa mục**.

Một resolver có thể trả nhiều cache; đa số nghiệp vụ chỉ cần một. Với nhiều cache, `@Cacheable` có thể tra cứu lần lượt và ghi giá trị vào các vùng được chỉ định theo hợp đồng của Spring, nhưng hành vi với các cache async/reactive có thể phụ thuộc provider. Không dùng nhiều vùng chỉ để mô phỏng phân vùng tenant nếu một cache là đủ.

## 6. Ví dụ chạy được: mỗi tenant chọn một cache, vùng được tạo động

Ví dụ dùng **JDK 17+, Maven, Spring Boot 3.3.5** và `spring-boot-starter-cache`. Hai tenant hợp lệ là `north` và `south`. Mỗi lần truy vấn, `tenantCatalogResolver` ánh xạ tenant sang một tên cho phép; `ConcurrentMapCacheManager()` tạo vùng khi tên mới xuất hiện. `@Cacheable` và `@CacheEvict` cùng dùng resolver để truy cập đúng vùng.

Cấu trúc dự án:

~~~text
dynamic-cache-name-demo/
|-- pom.xml
+-- src/main/java/example/cache/
    |-- DemoApplication.java
    +-- TenantCatalogService.java
~~~

**`pom.xml`**

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
    <artifactId>dynamic-cache-name-demo</artifactId>
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

**`src/main/java/example/cache/DemoApplication.java`**

~~~java
package example.cache;

import java.util.List;
import java.util.Map;
import java.util.TreeSet;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.CacheResolver;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    // Không truyền sẵn danh sách tên => chế độ tạo cache động.
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager();
    }

    @Bean("tenantCatalogResolver")
    CacheResolver tenantCatalogResolver(CacheManager cacheManager) {
        Map<String, String> allowedNames = Map.of(
                "north", "catalog.north",
                "south", "catalog.south");

        return context -> {
            Object[] args = context.getArgs();
            if (args.length < 2 || !(args[0] instanceof String tenant)) {
                throw new IllegalArgumentException(
                        "Expected tenant and productId");
            }

            String cacheName = allowedNames.get(tenant);
            if (cacheName == null) {
                throw new IllegalArgumentException(
                        "Unsupported tenant: " + tenant);
            }

            Cache selected = cacheManager.getCache(cacheName);
            if (selected == null) {
                throw new IllegalStateException(
                        "Cache is unavailable: " + cacheName);
            }
            return List.of(selected);
        };
    }

    @Bean
    CommandLineRunner demo(TenantCatalogService service,
                           CacheManager cacheManager) {
        return args -> {
            System.out.println(service.read("north", "P1"));
            System.out.println(service.read("north", "P1"));
            System.out.println(service.read("south", "P1"));
            System.out.println("Caches="
                    + new TreeSet<>(cacheManager.getCacheNames()));
            service.invalidate("north", "P1");
            System.out.println(service.read("north", "P1"));
        };
    }
}
~~~

**`src/main/java/example/cache/TenantCatalogService.java`**

~~~java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class TenantCatalogService {
    private final AtomicInteger loads = new AtomicInteger();

    @Cacheable(cacheResolver = "tenantCatalogResolver", key = "#p1")
    public String read(String tenantId, String productId) {
        int attempt = loads.incrementAndGet();
        return tenantId + "/" + productId + " -> load#" + attempt;
    }

    @CacheEvict(cacheResolver = "tenantCatalogResolver", key = "#p1")
    public void invalidate(String tenantId, String productId) {
        // Thực tế thường gọi sau thao tác sửa/xóa dữ liệu nguồn.
    }
}
~~~

Từ thư mục dự án, chạy:

~~~bash
mvn -q spring-boot:run
~~~

Các dòng **do chương trình demo in ra** (ngoài log khởi động Spring):

~~~text
north/P1 -> load#1
north/P1 -> load#1
south/P1 -> load#2
Caches=[catalog.north, catalog.south]
north/P1 -> load#3
~~~

Giải thích theo thứ tự:

1. `read(north, P1)` chọn cache `"catalog.north"`; manager tạo vùng lần đầu; key `"P1"` chưa có nên gọi method (`load#1`).
2. Cùng tenant/id đọc lại trúng cache, không tăng bộ đếm nên vẫn `load#1`.
3. `read(south, P1)` chọn vùng `"catalog.south"`, key `"P1"` ở vùng đó chưa có nên `load#2`.
4. `getCacheNames()` đã có hai vùng, được sắp xếp để in ra theo thứ tự ổn định.
5. `invalidate(north, P1)` chọn lại **đúng vùng** `"catalog.north"` và xóa key `"P1"`; `read(north, P1)` kế tiếp miss nên `load#3`. Giá trị của tenant `south` không bị xóa.

Trong demo, đối số đầu `tenantId` xác định vùng, đối số thứ hai `productId` xác định khóa. `key="#p1"` hoàn toàn hợp lệ ở đây **vì tenant đã được tách bằng tên cache**. Nếu chuyển sang **một vùng dùng chung** mà vẫn chỉ lấy `productId`, các tenant sẽ trùng khóa. Vì vậy, chọn tên vùng và chọn key phải được thiết kế cùng nhau.

`Map.of(...)` là một **allowlist**, chủ động chặn tenant không biết. Chỉ sửa bảng ánh xạ và chính sách cấu hình khi thật sự muốn hỗ trợ tenant mới; không nối trực tiếp input tùy ý thành tên vùng trong một manager tự tạo cache động.

## 7. Nhiều manager và resolver mặc định

Một ứng dụng có thể dùng nhiều cache manager, ví dụ một manager cho danh mục dữ liệu tham chiếu và một manager khác cho kết quả tốn chi phí tính toán. Khi tên cố định và chỉ cần chọn manager cụ thể, khai báo thuộc tính `cacheManager` là đủ:

~~~java
// Phần chữ ký minh họa: catalogCacheManager là tên một bean CacheManager.
@Cacheable(cacheNames = "products", cacheManager = "catalogCacheManager",
           key = "#p0")
public Product getProduct(String id) {
    return loadProduct(id);
}
~~~

Khi sử dụng `cacheManager` như trên, resolver mặc định giải tên `"products"` thông qua manager được chỉ định. Nếu phải **chọn manager hoặc tên cache tùy theo dữ liệu của lời gọi**, có thể viết `CacheResolver` chủ động chọn manager/vùng phù hợp theo chính sách nghiệp vụ. Mọi nhánh phải xác định được nơi cần đọc, ghi và xóa.

Không nên suy luận rằng đổi manager là đổi tên: có thể có **hai CacheManager khác nhau đều chứa cache `"products"`**, nhưng dữ liệu của chúng độc lập. Danh tính logic của một mục còn phụ thuộc manager/provider, cache name và key.

### Nhiều cacheNames trên một operation

~~~java
// Minh họa nhu cầu đặc biệt, không cần dùng cho ví dụ phân vùng tenant.
@Cacheable(cacheNames = {"productsFast", "productsBackup"}, key = "#p0")
public Product getById(String id) {
    return loadProduct(id);
}
~~~

Resolver mặc định trả về nhiều `Cache`, có thể kiểm tra hit theo thứ tự và cập nhật các cache theo ngữ nghĩa annotation. Tuy nhiên với cache bất đồng bộ/reactive và cách phát hiện miss của provider, Spring cảnh báo không phải mọi cache phía sau đều luôn được tham vấn. Chỉ chọn cách này khi có yêu cầu rõ ràng và kiểm thử hành vi của backend thực tế. Không dùng nhiều tên chỉ vì chưa xác định được tên chuẩn của một tập dữ liệu.

## 8. Chọn giữa tên cố định, tên động và khóa có namespace

| Nhu cầu | Phương án thường hợp lý | Lý do |
| --- | --- | --- |
| Mỗi loại dữ liệu có một vùng rõ ràng | `@Cacheable(cacheNames="products")` | Dễ quản trị, cấu hình TTL/metrics, kiểm soát tên |
| Nhiều method cùng dùng một vùng | `@CacheConfig(cacheNames="products")` | Giảm lặp, giữ cấu hình dễ đọc |
| Một vài tenant/region cần chính sách tách biệt | `CacheResolver` + tên chuẩn hóa/allowlist | Chọn cache bằng dữ liệu runtime |
| Rất nhiều tenant không giới hạn | Một tên ổn định + khóa chứa tenant | Tránh tăng số vùng cache theo số tenant |
| Manager có tập tên cố định | Khởi tạo danh sách tên và từ chối tên lạ | Phát hiện sớm lỗi chính tả hoặc cấu hình |
| Cần đổi TTL/serializer theo nhóm | Chọn manager/cache cấu hình trước theo chính sách | Tránh giả định cache tạo động có cấu hình phù hợp |
| Bài toán chỉ cần đổi key trong cùng vùng | `key`/`KeyGenerator` | Không cần `CacheResolver` |

Một cách đặt tên dễ quản trị là `<domain>.<purpose>.<scope>` như `"catalog.byId.north"` nếu vùng thực sự cần tách theo scope. Tên nên nhất quán về chữ hoa/thường, khoảng trắng, ký tự phân cách và phiên bản. Nếu provider dùng prefix hoặc quy tắc biến tên thành key vật lý (ví dụ Redis), tên logic và tên vật lý có thể khác nhau; hãy kiểm tra cấu hình provider trước khi dựa vào công cụ bên ngoài để xóa dữ liệu.

Không nên sinh tên theo timestamp, UUID ngẫu nhiên hay mỗi request; việc đó làm cache luôn miss và có thể tạo quá nhiều vùng. Với scope đến từ người dùng, cần xác minh tenant/account từ danh tính đã xác thực và quy tắc phân quyền; không chỉ tin một chuỗi do client tự gửi.

## 9. Giới hạn và hệ quả vận hành của cache động

### Rủi ro mở rộng số lượng vùng

Nếu tên được ghép trực tiếp từ `tenantId` và `CacheManager` tạo vùng mới với mọi tên, hàng chục nghìn tenant hoặc input sai có thể sinh hàng chục nghìn `Cache`. Với in-memory manager, điều này làm phình cấu trúc trong JVM và khó áp dụng chính sách TTL/giới hạn dung lượng. Thiết kế cần một trong các cách: danh sách tên hợp lệ, registry lifecycle có quản lý, số scope hữu hạn, hoặc một tên cache chung với key phân vùng.

### `CacheManager.getCache(name)` có thể trả `null`

`CacheResolver` nên kiểm tra kết quả trước khi tạo danh sách trả về. Trả `List.of(null)` là lỗi ngay trong Java; trả collection rỗng cũng không tạo vùng hợp lệ để cache operation thực hiện. Ném lỗi mô tả tên mong đợi sẽ giúp debug nhanh hơn việc thấy cache hit/miss bất thường.

### Tên thay đổi làm invalidation không đúng nơi

Nếu `@Cacheable` đọc từ `"catalog.north"` nhưng `@CacheEvict` xóa `"catalog"` thì dữ liệu đã cache vẫn tồn tại. Tương tự, khi chính sách đặt tên thay đổi từ `catalog.north` sang `catalog.tenant.north`, dữ liệu cũ không tự được chuyển/xóa. Cần kế hoạch đổi tên, vô hiệu hóa hoặc migration phù hợp. Với `@CacheEvict(allEntries=true)`, Spring xóa **toàn bộ mục trong những vùng đã được resolver chọn**, không mặc định xóa mọi vùng mà manager quản lý.

### Cấu hình Spring và ứng dụng thực

- `@EnableCaching` bật cơ chế annotation caching; method phải được gọi qua Spring-managed proxy. Lời gọi tự nội bộ `this.read(...)` thường bỏ qua interceptor ở proxy mode mặc định.
- Tên bean trong `cacheResolver = "tenantCatalogResolver"` phải đúng; `cacheManager = "..."` và `cacheResolver = "..."` không được đặt cùng operation.
- Cấu hình `@CacheConfig` chỉ cho mặc định, không tự kích hoạt cache cho mọi method.
- Các giá trị động như `tenantId` nên dùng nguồn tin cậy đã xác thực; nếu dùng ThreadLocal/context thì phải tính đến thread pool, reactive flow và khả năng context không lan truyền.
- Cache tạo tự động trong `ConcurrentMapCacheManager` là cache **cục bộ JVM**. Khi nhiều instance chạy, mỗi instance có bộ nhớ riêng; muốn cache dùng chung cần provider phân tán và cách đồng bộ/xóa phù hợp.
- Với Redis/Caffeine/JCache, cấu hình tạo vùng, bộ nhớ, thời hạn sống, serializer và giới hạn khác nhau. Không chuyển nguyên giả định của demo sang production mà không đọc tài liệu provider đang dùng.

## 10. Kiểm thử lựa chọn tên cache

Test cần chứng minh **cùng key ở hai vùng không xung đột**, resolver trả đúng tên, và eviction chọn đúng vùng. Với ví dụ phần 6, có thể kiểm tra trực tiếp bằng `CacheManager` sau khi các lời gọi thực hiện:

~~~java
// Trích kiểm tra bổ sung ở ngữ cảnh đã có service và cacheManager.
String first = service.read("north", "P1");
String again = service.read("north", "P1");
String other = service.read("south", "P1");

if (!first.equals(again)) {
    throw new AssertionError("Repeated call should hit north cache");
}
if (first.equals(other)) {
    throw new AssertionError("Tenant caches must be independent");
}

Cache north = cacheManager.getCache("catalog.north");
Cache south = cacheManager.getCache("catalog.south");
if (north == null || south == null) {
    throw new AssertionError("Expected cache names not found");
}
if (!first.equals(north.get("P1", String.class))) {
    throw new AssertionError("North cache entry mismatch");
}
if (!other.equals(south.get("P1", String.class))) {
    throw new AssertionError("South cache entry mismatch");
}

service.invalidate("north", "P1");
if (north.get("P1") != null || south.get("P1") == null) {
    throw new AssertionError("Eviction targeted wrong cache");
}
~~~

Đây là mã **kiểm tra minh họa**, đặt trong một method/test có sẵn các biến `service`, `cacheManager`; không phải một tệp Java độc lập. Với ứng dụng thực, dùng kiểm thử tích hợp Spring, stub repository hoặc bộ đếm đọc dữ liệu nguồn. Ngoài cache hit/miss, kiểm thử tên không hợp lệ, quyền tenant, trường hợp cache manager không biết vùng, hành vi đồng thời và chính sách TTL/provider được lựa chọn.

Một bài test cần chứng minh đúng hành vi của **cache provider thực tế**, không chỉ đúng tên trả từ `CacheResolver`. Redis có thể dùng prefix vật lý, serialize key và chính sách cấu hình khác manager trong bộ nhớ.

## 11. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `cacheNames="#p0"` không đổi tên theo đối số | `cacheNames` không đánh giá SpEL | Dùng `CacheResolver` cho tên động; dùng `key` cho khóa |
| Tên cache mới không được dùng | Manager tĩnh trả `null` với tên lạ | Kiểm tra `getCache(name)` và danh sách tên hợp lệ |
| Mỗi request đều miss, nhiều tên lạ xuất hiện | Sinh tên từ giá trị không ổn định/ngẫu nhiên | Chuẩn hóa, giới hạn số vùng hoặc dùng cache chung |
| Hai tenant trả cùng dữ liệu | Dùng cache chung nhưng khóa bỏ qua tenant | Bổ sung tenant trong key hoặc tách vùng với resolver |
| Evict không xóa dữ liệu đang được đọc | Resolver của đọc/xóa tạo tên khác, hoặc key khác | So sánh manager, cacheName, key của cả hai đường |
| Bean resolver không hoạt động | Sai tên bean, thiếu `@EnableCaching`, gọi qua `this` | Kiểm tra cấu hình và gọi method từ bean khác |
| Nhiều vùng làm tăng bộ nhớ | Tạo vô hạn cache trong JVM | Kiểm soát tên/registry, chọn provider có giới hạn rõ |
| Đổi provider khiến cấu hình cache mất tác dụng | Phụ thuộc cơ chế tạo vùng/serializer cũ | Kiểm tra cấu hình tên và chính sách từng provider |
| Lỗi khi khai báo `cacheManager` cùng `cacheResolver` | Hai thuộc tính loại trừ nhau | Chọn một cách phân giải cho một operation |
| `@CacheEvict(allEntries=true)` xóa quá nhiều | Resolver trả nhiều vùng | Giới hạn chính xác các vùng được trả trong operation |

Khi cần điều tra, log **tên cache đã phân giải** và **khóa đã làm sạch thông tin nhạy cảm** ở mức debug phù hợp. Tránh log token, thông tin cá nhân, toàn bộ payload hay tên tenant nhạy cảm công khai.

## 12. Bài tập vận dụng

**Bài 1.** Một ứng dụng có hai phương thức đọc `getProduct(id)` và `getCategory(id)` nhưng cả hai dùng tên `"cache"`. Nên thiết kế ra sao?  
**Gợi ý:** nếu hai tập kết quả có cùng key dạng chuỗi, sẽ có nguy cơ trùng mục. Dùng hai tên tường minh `"products"`/`"categories"` hoặc khóa gồm discriminator có thiết kế rõ.

**Bài 2.** Hệ thống có hàng triệu account; có nên tạo tên `"profile." + accountId` cho mỗi account không?  
**Gợi ý:** thường không hợp lý với manager tạo động vì số vùng tăng theo account. Cân nhắc một vùng `"profiles"` với khóa chứa `accountId`, rồi đặt TTL/giới hạn ở provider.

**Bài 3.** Một resolver chọn `"catalog.north"` cho đọc và `"catalog.south"` cho eviction cùng sản phẩm `"P1"`. Điều gì xảy ra?  
**Đáp án:** eviction không xóa mục đã đọc vì nhắm khác cacheName. Hai operation phải áp dụng cùng chính sách chọn vùng khi cùng thực thể.

**Bài 4.** `new ConcurrentMapCacheManager("a", "b")` nhận yêu cầu `"c"` sẽ ra sao? Còn `new ConcurrentMapCacheManager()`?  
**Đáp án:** biến thể có danh sách cố định trả `null` cho `"c"`; biến thể không đối số cho phép tạo vùng `"c"` khi được hỏi. Đây là quy tắc của manager cụ thể này.

## Tài liệu chính thức

- Spring Framework, Annotation-based caching và Custom Cache Resolution: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework, Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Javadoc `ConcurrentMapCacheManager` và chế độ static/dynamic: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Boot, Caching providers/configuration: https://docs.spring.io/spring-boot/reference/io/caching.html

**Điểm cốt lõi:** `cacheNames`/`@CacheConfig` phù hợp với **tên tường minh**; `CacheResolver` cho phép **chọn vùng theo runtime**; `CacheManager` quyết định **vùng đó có thể được lấy hay tạo ra không**. Tên cache và khóa phải được thiết kế nhất quán ở mọi đường đọc, cập nhật và xóa.