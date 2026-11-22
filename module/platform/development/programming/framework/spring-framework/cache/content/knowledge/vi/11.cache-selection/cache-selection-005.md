# Xử lý tên cache không tồn tại hoặc không được cấp phát trong Spring Cache

## Mục tiêu bài học

Khi cấu hình `@Cacheable(cacheNames = "products")`, nhiều lập trình viên cho rằng Spring luôn có một vùng cache tên `products`. Thực tế, annotation chỉ **yêu cầu sử dụng tên cache đó**; khả năng tìm thấy hoặc tạo được cache phụ thuộc vào **`CacheResolver`, `CacheManager` và nhà cung cấp cache**. Một lỗi gõ sai tên có thể dẫn đến exception lúc chạy, hoặc âm thầm tạo một cache ngoài dự định khi manager cho phép tạo động.

Sau bài này, bạn có thể:

- Phân biệt **cache name không tồn tại**, **cache region chưa được cấp phát**, **cache entry chưa tồn tại** và **backend cache không truy cập được**.
- Hiểu hợp đồng `CacheManager.getCache(name)` và khác biệt giữa manager tạo cache động với manager giới hạn danh sách cache.
- Chẩn đoán một lời gọi `@Cacheable` bị lỗi do cache không được cấp phát, thay vì nhầm nó với cache miss.
- Đăng ký trước tên cache, chọn đúng `CacheManager`, kiểm tra cấu hình khi khởi động và viết test cho tên hợp lệ/lỗi.
- Hiểu tùy chọn của Spring Boot, Caffeine, Redis và `CompositeCacheManager` ở mức nguyên tắc mà không mặc định mọi provider có hành vi giống nhau.
- Chạy một ví dụ Java 17 + Spring Framework minh họa chế độ strict và dynamic.

**Thông điệp quan trọng:** Tên cache xuất hiện trong annotation **không đảm bảo cache vật lý đã tồn tại**. Hệ thống có thể tạo cache theo yêu cầu, trả về `null`, hoặc thất bại vì cấu hình/hạ tầng. Hãy xác định rõ chiến lược cấp phát thay vì dựa vào phỏng đoán.

## 1. Phân biệt bốn trạng thái thường bị nhầm

### 1.1. Cache name chưa được manager nhận biết

Ví dụ:

~~~java
@Cacheable(cacheNames = "prodcuts", key = "#p0") // gõ sai "products"
public Product findById(long id) {
    return repository.findById(id);
}
~~~

Đây là mã minh họa có `Product` và `repository` bên ngoài.

Annotation yêu cầu vùng `prodcuts` thay vì `products`. Nếu manager chỉ chấp nhận `products`, lời gọi có thể thất bại khi Spring cố phân giải cache `prodcuts`. Nếu manager tự động tạo vùng theo yêu cầu, nó có thể tạo **một vùng cache mới sai tên**, và lỗi chỉ bộc lộ gián tiếp qua hit ratio, bộ nhớ hoặc dữ liệu không nhất quán.

### 1.2. Cache region hợp lệ nhưng chưa được cấp phát

Một số manager/lớp provider quản lý cache **lazy**: trước lần sử dụng đầu, region chưa tồn tại trong bộ nhớ hoặc danh sách cache đã được tạo; khi `getCache("products")` được gọi, manager có thể khởi tạo một cache rồi trả về nó.

Vì vậy, `getCacheNames()` tại thời điểm ứng dụng vừa chạy có thể không bao gồm mọi tên **được phép tạo về sau**. Không được kết luận mọi tên chưa xuất hiện trong danh sách là tên sai mà không xem chế độ manager.

### 1.3. Region tồn tại, nhưng entry theo key chưa tồn tại (cache miss)

Đây là tình huống bình thường:

~~~text
CacheManager.getCache("products") -> Cache hợp lệ
Cache.get(42)                   -> không có entry
@Cacheable                      -> gọi phương thức nguồn
                                   rồi xét lưu kết quả
~~~

Khác biệt căn bản: **cache miss chỉ liên quan một key trong một vùng cache đã phân giải thành công**. Nó không có nghĩa `CacheManager` trả `null`.

### 1.4. Region có tên đúng nhưng hạ tầng gặp sự cố

Ví dụ Redis không kết nối được, lỗi credentials, timeout mạng hoặc lỗi serialization. Đây không nhất thiết là “cache name không tồn tại”. `CacheManager.getCache(name)` có thể vẫn trả một đối tượng `Cache`, nhưng thao tác `get`, `put` hay `evict` mới ném lỗi.

Khắc phục phải dựa trên **ngoại lệ gốc và loại provider**, không tự động đổi tên cache hoặc xóa ngẫu nhiên dữ liệu.

## 2. CacheManager và CacheResolver phân giải tên cache như thế nào?

### 2.1. Hợp đồng của CacheManager

Spring cung cấp interface `org.springframework.cache.CacheManager`:

~~~java
Cache getCache(String name);
Collection<String> getCacheNames();
~~~

Đây là **trích lược chữ ký để giải thích API**, không phải class Java hoàn chỉnh.

- `getCache(name)`: tìm cache theo tên; tùy implementation, có thể **tạo lazy**; có thể trả `null` nếu cache không tồn tại hoặc không thể được tạo.
- `getCacheNames()`: trả danh sách các cache manager **đang biết**. Với chế độ dynamic, đây không mặc nhiên là danh sách toàn bộ tên có thể có trong tương lai.

Không nên viết `cacheManager.getCache("prodcuts").get(42)` mà không kiểm tra `null`; nếu tên không được hỗ trợ, code này dễ ném `NullPointerException` và che khuất nguyên nhân.

Đối với truy cập programmatic, có thể kiểm tra rõ ràng:

~~~java
Cache cache = Objects.requireNonNull(
    cacheManager.getCache("products"),
    "Cache 'products' is unavailable"
);
~~~

Đây là **đoạn minh họa**; cần import `java.util.Objects`, `org.springframework.cache.Cache` và có `cacheManager` sẵn.

### 2.2. Mặc định của cache annotations

Khi dùng annotation như `@Cacheable`, Spring sử dụng cache resolver để xác định các đối tượng `Cache` tương ứng với cache names. Một cấu hình thường gặp là `SimpleCacheResolver`, dùng `CacheManager` đã cấu hình.

Luồng điển hình:

~~~text
Gọi @Cacheable(cacheNames="products")
                 |
          Spring caching proxy
                 |
       CacheResolver.resolveCaches(...)
                 |
        CacheManager.getCache("products")
                 |
         +-------+--------+
         |                |
     có Cache         trả null
         |                |
  xét key/hit/miss    default resolver
                      báo lỗi phân giải cache
~~~

Với resolver mặc định, nếu một tên cache được yêu cầu nhưng `CacheManager` không trả được cache cho tên đó, lời gọi được chặn thường ném **`IllegalArgumentException` liên quan việc không tìm thấy cache name**. Điều này thường xảy ra **khi phương thức được gọi**, không nhất thiết ngay khi Spring ApplicationContext khởi tạo.

**Ngoại lệ:** một `CacheResolver` tùy biến có thể xử lý khác (ví dụ không trả cache, định tuyến động hoặc báo lỗi riêng). Luôn nhìn cấu hình thực tế trước khi khẳng định một loại exception cho mọi dự án.

### 2.3. Tên có phân biệt chữ hoa/thường và khoảng trắng

Tên vùng cache là định danh dạng chuỗi. Đừng giả định `"products"`, `"Products"` và `"products "` là cùng một cache. Thống nhất cách đặt tên, ưu tiên hằng số hoặc nhóm tên quản lý tập trung trong code, và kiểm thử với chính `CacheManager` thật.

## 3. Dynamic và static: cùng một manager có thể có hai hành vi

`ConcurrentMapCacheManager` là ví dụ dễ kiểm chứng trong Spring Framework.

### 3.1. Chế độ dynamic: khởi tạo không truyền tên

~~~java
@Bean
CacheManager cacheManager() {
    return new ConcurrentMapCacheManager();
}
~~~

Với constructor không tham số, `ConcurrentMapCacheManager` có thể **tạo vùng cache theo yêu cầu** khi `getCache(name)` được gọi. Vì vậy:

- `getCacheNames()` có thể trống ngay sau khi khởi tạo.
- `getCache("products")` có thể tạo và trả về cache tên `products`.
- Nếu annotation viết sai `"prodcuts"`, vùng sai tên cũng có thể được tạo. Không có exception chỉ vì gõ sai tên trong trường hợp này.

Ưu điểm: nhanh chóng khi thử nghiệm, không cần liệt kê mọi vùng ban đầu. Nhược điểm: dễ che giấu lỗi chính tả và sinh cache region ngoài dự kiến.

### 3.2. Chế độ static/strict: khai báo tên được phép

~~~java
@Bean
CacheManager cacheManager() {
    return new ConcurrentMapCacheManager(
        "products", "productSummaries", "categoryLists"
    );
}
~~~

Constructor nhận danh sách tên đưa `ConcurrentMapCacheManager` vào chế độ **chỉ quản lý những cache đã khai báo**. Khi yêu cầu tên khác:

~~~text
getCache("products")  -> Cache
getCache("prodcuts")  -> null
~~~

Với `@Cacheable(cacheNames = "prodcuts")`, resolver mặc định không tìm được vùng nên báo lỗi ở lời gọi cần cache.

Chế độ strict giúp **phát hiện cache name sai** nhanh hơn, nhưng cần cập nhật danh sách khi thêm vùng cache hợp lệ và có test phát hiện sai cấu hình trước khi triển khai.

### 3.3. So sánh

| Kiểm tra | ConcurrentMapCacheManager dynamic | ConcurrentMapCacheManager static |
| --- | --- | --- |
| Khởi tạo | `new ConcurrentMapCacheManager()` | `new ConcurrentMapCacheManager("products")` |
| Tên đúng, lần đầu sử dụng | Tạo cache lazy | Trả cache đã khai báo |
| Tên mới chưa khai báo | Có thể tạo vùng mới | `getCache(name)` trả `null` |
| Rủi ro gõ sai tên | Dễ tạo vùng sai | Lộ lỗi khi resolution |
| Có thể xem `getCacheNames()` là allow-list hoàn chỉnh? | Không | Trong mô hình static, là danh sách khai báo |
| Lựa chọn | Demo/khai báo mở có chủ đích | Hệ thống muốn kiểm soát tên |

**Không suy rộng bảng này cho mọi CacheManager.** Redis, Caffeine, JCache hoặc cache tự viết có chính sách tạo vùng khác nhau và còn phụ thuộc cấu hình của mỗi provider.

## 4. Demo Java 17: một annotation đúng, một annotation sai

Chương trình dưới đây tạo **hai ApplicationContext độc lập** để đối chiếu:

1. **StrictConfig**: chỉ khai báo cache `products`. Lời gọi `@Cacheable(cacheNames = "mistypedProducts")` bị từ chối trước khi thân phương thức thực thi.
2. **DynamicConfig**: dùng manager không có danh sách cố định. Cùng annotation `mistypedProducts` được chấp nhận và tạo cache mới.

Chương trình có thể chạy với Java 17+, Maven và Spring Framework 6.2.10. Không dùng Spring Boot để việc phân biệt chính sách `CacheManager` không bị ảnh hưởng bởi auto-configuration.

### 4.1. Cấu trúc dự án

~~~text
missing-cache-name/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MissingCacheNameDemo.java
~~~

### 4.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>missing-cache-name</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
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

### 4.3. src/main/java/demo/MissingCacheNameDemo.java

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class MissingCacheNameDemo {

    @Configuration
    @EnableCaching
    public static class StrictConfig {
        @Bean
        public CacheManager cacheManager() {
            // Chỉ những tên trong danh sách này được cấp phát.
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    @Configuration
    @EnableCaching
    public static class DynamicConfig {
        @Bean
        public CacheManager cacheManager() {
            // Không có allow-list: cache được tạo theo yêu cầu.
            return new ConcurrentMapCacheManager();
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    public static class ProductService {
        private final AtomicInteger productCalls = new AtomicInteger();
        private final AtomicInteger typoCalls = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public String findProduct(long id) {
            int n = productCalls.incrementAndGet();
            return "Product-" + id + " (load=" + n + ")";
        }

        @Cacheable(cacheNames = "mistypedProducts", key = "#p0")
        public String findWithTypo(long id) {
            int n = typoCalls.incrementAndGet();
            return "Other-" + id + " (load=" + n + ")";
        }

        public int productCalls() {
            return productCalls.get();
        }

        public int typoCalls() {
            return typoCalls.get();
        }
    }

    public static void main(String[] args) {
        try (var ctx =
                new AnnotationConfigApplicationContext(StrictConfig.class)) {
            ProductService service = ctx.getBean(ProductService.class);
            CacheManager manager = ctx.getBean(CacheManager.class);

            System.out.println("STRICT:");
            System.out.println(service.findProduct(7L));
            System.out.println(service.findProduct(7L));
            System.out.println("Product calls: " + service.productCalls());
            System.out.println(
                "Missing region: " +
                (manager.getCache("mistypedProducts") == null));

            try {
                service.findWithTypo(7L);
            } catch (IllegalArgumentException ex) {
                System.out.println(
                    "Rejected missing cache: " +
                    ex.getMessage().contains("mistypedProducts"));
            }
            System.out.println("Typo calls: " + service.typoCalls());
        }

        try (var ctx =
                new AnnotationConfigApplicationContext(DynamicConfig.class)) {
            ProductService service = ctx.getBean(ProductService.class);
            CacheManager manager = ctx.getBean(CacheManager.class);

            System.out.println("DYNAMIC:");
            System.out.println(
                "Known before: " + manager.getCacheNames().size());
            System.out.println(service.findWithTypo(7L));
            System.out.println(service.findWithTypo(7L));
            System.out.println("Typo calls: " + service.typoCalls());
            System.out.println(
                "Missing region was created: " +
                (manager.getCache("mistypedProducts") != null));
            System.out.println(
                "Known after: " + manager.getCacheNames().size());
        }
    }
}
~~~

**Vì sao không cùng một ApplicationContext?** Hai context dùng hai `CacheManager` khác nhau, mỗi context có một `ProductService` và bộ đếm riêng. Điều này giúp kết quả minh bạch và không phụ thuộc vào trạng thái cache từ lần chạy trước.

### 4.4. Cách chạy

Tại thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MissingCacheNameDemo
~~~

Những dòng **do chương trình in ra** (không tính log Maven):

~~~text
STRICT:
Product-7 (load=1)
Product-7 (load=1)
Product calls: 1
Missing region: true
Rejected missing cache: true
Typo calls: 0
DYNAMIC:
Known before: 0
Other-7 (load=1)
Other-7 (load=1)
Typo calls: 1
Missing region was created: true
Known after: 1
~~~

### 4.5. Giải thích output

1. `StrictConfig` cấp phát vùng `products`. Lần gọi `findProduct(7)` đầu là cache miss bình thường, lần hai hit; thân phương thức chỉ chạy **một lần**.
2. `manager.getCache("mistypedProducts") == null` là `true`: không có vùng cache sai tên và manager không tạo thêm vùng này.
3. Lời gọi `findWithTypo(7)` qua proxy bị từ chối trong bước phân giải cache, trước khi phương thức thật chạy. Vì thế `Typo calls: 0`.
4. `DynamicConfig` bắt đầu chưa có vùng cache nào được cấp phát; `getCacheNames().size()` trả 0.
5. Lời gọi `findWithTypo(7)` tạo cache mới tên `mistypedProducts`. Lần thứ hai hit, nên `Typo calls: 1`.
6. Sau khi cấp phát, region đã có và tổng số vùng được biết là 1.

**Ý nghĩa:** Cache name không hợp lệ có thể gây lỗi rõ ràng **hoặc bị tạo như một region hoàn toàn mới**, tùy chính sách manager. Việc chương trình chạy không lỗi **không có nghĩa tên cache đúng với thiết kế**.

## 5. Xử lý thực tế khi tên cache không tồn tại

Hãy đi theo trình tự chẩn đoán, thay vì sửa tên cache một cách mò mẫm.

### Bước 1: Ghi nhận tên trong thông báo lỗi

Kiểm tra exception đầy đủ: tên bị yêu cầu, phương thức có annotation, loại `CacheManager` được sử dụng, và nguyên nhân lồng nhau nếu có.

Một lỗi thường gặp với resolver mặc định khi không tìm thấy cache:

~~~text
IllegalArgumentException: Cannot find cache named 'unknownName' for ...
~~~

Đây là **dạng thông báo minh họa** (phần sau dấu `for` còn chứa thông tin cache operation); không phải contract cho mọi phiên bản/provider.

### Bước 2: Đối chiếu chính xác cacheNames tại nơi khai báo

Kiểm tra:

- `@Cacheable(cacheNames="...")`, `@CachePut`, `@CacheEvict`, `@Caching`.
- `@CacheConfig(cacheNames = {...})` ở cấp class, có thể cấp cache name mặc định.
- `cacheManager` hoặc `cacheResolver` trên annotation/class, nếu ứng dụng dùng nhiều manager.
- Các hằng số tên cache, typo, chữ hoa/thường, số ít/số nhiều, dấu cách và môi trường profile.
- Đúng method có đi qua proxy cache hay không: self-invocation có thể bỏ qua advice và che giấu lỗi.

Không chỉnh bất kỳ tên nào trước khi hiểu cơ chế tạo vùng cache và dữ liệu đã tồn tại trong vùng cũ.

### Bước 3: Kiểm tra CacheManager thực sự được chọn

Một hệ thống có thể có nhiều manager, ví dụ:

- `localCacheManager` cho cache RAM.
- `distributedCacheManager` cho Redis.
- Một `CacheResolver` tùy biến định tuyến theo tenant hoặc method.

Một tên hợp lệ ở manager A không có nghĩa nó tồn tại ở manager B.

Ví dụ **minh họa khi ứng dụng đã đăng ký bean có tên tương ứng**:

~~~java
@Cacheable(
    cacheNames = "products",
    cacheManager = "distributedCacheManager",
    key = "#p0"
)
public Product findProduct(long id) {
    return repository.findById(id);
}
~~~

Nếu không có bean manager tên `distributedCacheManager`, đó lại là vấn đề cấu hình bean/resolver, **không chỉ** thiếu region. `cacheManager` và `cacheResolver` là hai cách lựa chọn cơ chế phân giải khác nhau, không dùng đồng thời trên một cache operation.

### Bước 4: Quyết định có cho phép tạo vùng cache mới không

Nếu vùng cache mới là chủ đích, hãy **khai báo/cấp phát đúng cách** theo provider thay vì đổi toàn hệ thống sang dynamic để tránh một lỗi riêng lẻ.

Nếu ứng dụng cần bảo vệ khỏi typo, ưu tiên danh sách cho phép rõ ràng và test xác minh. Việc dùng dynamic chỉ phù hợp khi tên cache được thiết kế để phát sinh linh hoạt và có kiểm soát số lượng region.

### Bước 5: Xác minh lại bằng integration test

Cần chứng minh cả hai điều:

1. Tên được cho phép có thể phân giải và cache hit thực sự hoạt động.
2. Tên không được cho phép bị từ chối (đối với cấu hình strict), hoặc chỉ được cấp phát theo quy tắc động đã thống nhất.

Nếu chỉ nhìn log khởi động “Application started”, bạn có thể bỏ sót lỗi; nhiều cache name chỉ được resolution **khi phương thức được gọi**.

## 6. Cách đăng ký/cấp phát tên cache đúng

### 6.1. Spring Framework: danh sách cố định trong Java Config

~~~java
@Configuration
@EnableCaching
class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager(
            "products",
            "productSummaries",
            "categoryLists"
        );
    }
}
~~~

Đây là **mã minh họa cấu hình**, giả sử đã import `Configuration`, `EnableCaching`, `Bean`, `CacheManager`, `ConcurrentMapCacheManager`. Khi thêm `@Cacheable(cacheNames = "productSearch")`, phải quyết định khai báo `productSearch` trước hoặc đổi annotation sang tên vùng thực sự muốn sử dụng.

### 6.2. Spring Boot với simple cache provider

Với **Spring Boot dùng simple cache provider** (backed by `ConcurrentMapCacheManager`) và khi Boot là bên auto-configure manager, có thể giới hạn tên bằng cấu hình:

~~~properties
spring.cache.type=simple
spring.cache.cache-names=products,productSummaries,categoryLists
~~~

Đây là **application.properties minh họa**, không phải bước cần áp dụng cho demo Maven ở mục 4. Khi dùng `spring.cache.type=simple`, các vùng nằm ngoài danh sách bị từ chối lúc sử dụng; một typo có thể không lộ ra khi ứng dụng khởi động. Chi tiết auto-configuration khác nhau theo phiên bản Boot, provider và việc ứng dụng đã cung cấp `CacheManager` bean riêng hay chưa.

**Không coi `spring.cache.cache-names` là một phép bảo đảm strict cho mọi provider.** Một số provider có cơ chế tạo vùng động khác nhau; cần xác nhận cách provider được cấu hình ở profile thực tế.

### 6.3. Caffeine

`CaffeineCacheManager` hỗ trợ cả cơ chế tạo vùng cache theo yêu cầu lẫn đăng ký trước tên cache, tùy cách thiết lập manager và các cache đặc biệt. Hãy chọn chế độ phù hợp để loại trừ typo, đồng thời kiểm tra TTL, maximumSize, refresh và các chính sách của từng vùng cache.

Không copy nguyên cấu hình `ConcurrentMapCacheManager` sang Caffeine rồi giả định các tùy chọn backend giống hệt.

### 6.4. Redis

Với Spring Data Redis, `RedisCacheManager` có thể được cấu hình các cache ban đầu và chính sách **cho phép hoặc vô hiệu hóa việc tạo cache chưa khai báo**. Ví dụ API builder `disableCreateOnMissingCache()` dùng để từ chối tạo vùng Redis cache động đối với tên không có trong cấu hình.

Đây là **định hướng cấu hình provider**, không phải một lời khuyên áp dụng mù: cần kiểm tra phiên bản Spring Data Redis, tên cache, key prefix, TTL và khả năng kết nối Redis thực tế. Việc có đối tượng `RedisCache` không chứng minh backend Redis đang sẵn sàng xử lý `GET/SET`.

### 6.5. SimpleCacheManager/JCache và những provider cấp phát tường minh

Một số manager quản lý tập cache được đăng ký hoặc cấp phát từ native provider. Với những manager đó, phải khởi tạo/tạo cache region đúng theo API, không kỳ vọng `getCache(name)` lúc nào cũng tự cấp phát. JCache/Ehcache/Hazelcast/Infinispan có vòng đời và cấu hình riêng. Luôn đối chiếu tài liệu triển khai đang dùng.

## 7. Startup validation: phát hiện thiếu cache sớm hơn runtime

Nhiều lỗi cache name chỉ xuất hiện ở đường code ít được gọi. Trong hệ thống strict, có thể kiểm tra **danh sách cache bắt buộc** ngay sau khi Spring khởi tạo.

Ví dụ **mã Java minh họa tích hợp vào ứng dụng**, không nằm trong demo độc lập:

~~~java
import java.util.List;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;

@Component
public final class RequiredCacheChecker
        implements SmartInitializingSingleton {

    private final CacheManager cacheManager;

    public RequiredCacheChecker(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @Override
    public void afterSingletonsInstantiated() {
        for (String name : List.of(
                "products", "productSummaries", "categoryLists")) {
            if (cacheManager.getCache(name) == null) {
                throw new IllegalStateException(
                    "Required cache is missing: " + name);
            }
        }
    }
}
~~~

Ưu điểm: khi dùng **static/strict manager**, thiếu một cache bắt buộc sẽ làm startup fail rõ ràng trước khi nhận traffic.

**Cảnh báo:** Với dynamic manager, việc gọi `getCache(name)` trong checker **có thể tự tạo cache** rồi cho kết quả “hợp lệ”, ngay cả khi tên bị gõ sai. Vì vậy startup validation cần đi kèm danh sách tên chuẩn, static policy hoặc cơ chế phân giải không tự tạo (nếu provider hỗ trợ). Đừng dùng checker này như bằng chứng rằng dữ liệu đã tồn tại trong cache hay backend Redis sẵn sàng kết nối.

Ngoài ra, checker ở trên xác minh **danh sách cố định do bạn khai báo**, không tự quét được mọi tên trong toàn bộ annotation source. Để phát hiện annotation sai tên, có thể bổ sung integration test gọi các phương thức sử dụng cache và kiểm tra strict resolver, hoặc quy tắc kiểm tra cấu hình bằng test/CI.

## 8. Tùy chọn fallback và khi nào không nên nuốt lỗi

### 8.1. Có nên tự động bỏ qua caching nếu vùng không có?

Một số ứng dụng ưu tiên khả dụng: khi cache chưa sẵn sàng, chúng muốn chạy logic nghiệp vụ mà không sử dụng cache. Đây là một quyết định kiến trúc, **không phải mặc định của `SimpleCacheResolver` khi tên không tìm thấy**.

Spring `CompositeCacheManager` có tùy chọn `fallbackToNoOpCache` để cung cấp cache không lưu dữ liệu khi các manager con không giải quyết được tên. Khi bật có chủ đích, một lời gọi có thể tiếp tục chạy thay vì báo lỗi thiếu cache; đổi lại nó có thể **âm thầm mất toàn bộ lợi ích cache** ở vùng đó. Hãy giới hạn fallback vào môi trường/nhu cầu có lý do và giám sát hoạt động thực tế.

Tránh đưa `NoOpCache` làm giải pháp mặc định cho lỗi typo production: nó có thể che giấu tình trạng cache vô hiệu hóa suốt thời gian dài.

### 8.2. Có nên dùng CacheErrorHandler để bỏ qua?

`CacheErrorHandler` xử lý lỗi phát sinh trong các **thao tác cache get/put/evict/clear**. Việc **không phân giải được tên cache** thông qua resolver không tương đương một lỗi `Cache.get` trên đối tượng `Cache` hợp lệ.

Do đó, đừng coi việc thêm một `CacheErrorHandler` “nuốt exception” là cách chắc chắn sửa lỗi missing cache name. Phải sửa chỗ đăng ký/resolve cache hoặc thay đổi policy fallback có kiểm soát.

### 8.3. Khi cache name là một vấn đề bảo mật và tài nguyên

Trong multi-tenant, tạo vùng cache động từ giá trị không tin cậy có thể tăng số region vô hạn hoặc làm lộ logic phân vùng. Nên dùng **cache name cố định** cùng key có tenantId nếu phù hợp, hoặc áp dụng allow-list/quota cho vùng động thật sự cần thiết. Không sử dụng tên cache động để thay thế mọi kiểm tra phân quyền.

## 9. Các lỗi thường gặp và nguyên nhân thực sự

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Lỗi “Cannot find cache named ...” khi gọi service | Manager strict không có region được yêu cầu | Đối chiếu annotation/cacheNames/manager |
| Không lỗi nhưng cache không hit như dự kiến | Dynamic manager tạo vùng sai tên | Kiểm tra getCacheNames, metrics và tên cache chuẩn |
| `getCache("products") != null` nhưng vẫn timeout | Provider/backend không sẵn sàng | Health, connection, credentials, timeout |
| `cache.get(key) == null` | Entry miss hoặc hết hạn | Kiểm tra key, TTL, eviction; không kết luận thiếu region |
| Có bean CacheManager nhưng injection không rõ | Nhiều manager/chọn nhầm bean | Qualifier, `@Primary`, `cacheManager` trên annotation |
| Không thấy lỗi dù annotation sai | Method chưa được gọi qua proxy; hoặc manager dynamic | Integration test thực sự gọi method qua bean |
| Chỉ production bị lỗi | Profile/CacheManager/provider khác dev | So sánh config theo môi trường |
| `@CacheEvict` không xóa đúng | Key hoặc cache name của đường đọc và đường ghi không khớp | So sánh hai annotation và key generator |
| Cache region xuất hiện nhưng memory tăng mãi | Tạo tên cache động không giới hạn | Chuyển sang allow-list, giám sát cardinality |
| Đổi cache name rồi dữ liệu cũ vẫn chiếm chỗ | Region/key cũ chưa có lifecycle dọn dẹp | Chính sách TTL, migration hoặc clear phù hợp |

## 10. Cách chẩn đoán có hệ thống trong production

1. **Xác nhận từ exception gốc.** Tách lỗi name resolution, lỗi backend và cache miss. Ghi lại class exception cùng phần message có cache name (không log dữ liệu nhạy cảm).
2. **Đối chiếu owner của cache name.** Tìm đúng cache annotation và cache policy của service, kể cả `@CacheConfig`.
3. **Xác minh manager thực tế.** Xem bean/config/profile/provider đang được dùng; không suy ra từ tên biến `cacheManager` trong code.
4. **Kiểm tra danh sách vùng được manager biết.** `getCacheNames()` hữu ích nhưng với dynamic mode không phải danh sách toàn bộ tên hợp lệ trong tương lai.
5. **Kiểm tra policy tạo vùng.** Manager có tạo lazy hay strict không? Provider có yêu cầu cấu hình region trước không?
6. **Chỉ tạo vùng cache hợp lệ.** Khi bổ sung cache mới, thiết kế key, TTL, memory/eviction, serializer, tính nhất quán với các instance.
7. **Test bằng phương thức được Spring quản lý.** Gọi qua bean để cache advice chạy, kiểm tra hit/miss và phản ứng với tên sai.
8. **Giám sát sau thay đổi.** Theo dõi số vùng cache, hit/miss/put, lỗi backend, latency và thay đổi memory.
9. **Phân biệt kiểm tra vùng và dữ liệu.** Một cache region hợp lệ không có nghĩa có entry đúng cho mọi key, cũng không chứng minh dữ liệu cache mới nhất.

### Log/metrics nên có

- Loại `CacheManager` và những cache names được cấu hình khi startup.
- Số lần cache name resolution thất bại, tách khỏi cache backend failures.
- Cache region count theo instance hoặc provider, khi có khả năng thu thập.
- Cache hit ratio, latency của nguồn khi cache miss, dung lượng/eviction.
- Các sự kiện thay đổi cấu hình vùng cache và lỗi tạo vùng trong deploy.

Không log key chứa token, session ID, thông tin định danh cá nhân hoặc bí mật hệ thống khi không có cơ chế làm sạch dữ liệu phù hợp.

## 11. Các tình huống đặc biệt cần lưu ý

### 11.1. Một annotation sử dụng nhiều cacheNames

~~~java
@Cacheable(
    cacheNames = {"products", "productBackup"},
    key = "#p0"
)
public Product findProduct(long id) {
    return repository.findById(id);
}
~~~

Đây là mã minh họa. Nếu resolver không tìm thấy **một tên** trong danh sách và cấu hình không cho phép tạo, việc phân giải có thể thất bại cho **cả cache operation**, không phải mặc định bỏ qua tên sai rồi dùng tên còn lại. Hãy đăng ký tất cả cache names mà operation yêu cầu.

### 11.2. Ứng dụng có nhiều cache manager

`cacheManager="someManager"` trên một annotation có thể chuyển sang hạ tầng khác. Nếu một vùng hợp lệ với manager A nhưng không thuộc manager B, lỗi thường nằm ở **sai manager được chọn**, không phải vùng cache bị xóa khỏi hệ thống.

Với `CacheResolver` tùy biến, cache names có thể được ánh xạ động theo tham số runtime; trong trường hợp đó hãy kiểm thử chính sách resolution của chính resolver.

### 11.3. Cache mất hiệu lực sau deploy hoặc thay đổi cấu hình

Có thể thay đổi cấu hình khiến region không còn được phép cấp phát, dù phiên bản trước đã dùng. Khi rollout nhiều instance, tên vùng và key format cần tương thích hoặc có kế hoạch migration. Đừng tự động tạo lại vùng cũ chỉ để “cho hết lỗi” nếu dữ liệu/serializer của nó không còn phù hợp.

### 11.4. Ứng dụng dùng @EnableCaching nhưng phương thức không bị intercept

Với proxy mode mặc định, lời gọi `this.findProduct(id)` trong chính bean bỏ qua cache advice. Điều này có thể tạo **ảo giác rằng annotation dùng tên cache sai nhưng vẫn chạy được**, vì thực tế chưa có cache resolution. Test nên gọi method từ bên ngoài bean thông qua `ApplicationContext`, không chỉ gọi trực tiếp instance bằng `new`.

## 12. Checklist trước khi phát hành

- [ ] Có một danh sách tên cache chính thức, thống nhất giữa các module.
- [ ] Cache names trong `@Cacheable`, `@CachePut`, `@CacheEvict`, `@CacheConfig` đều khớp.
- [ ] Biết `CacheManager` nào xử lý từng annotation.
- [ ] Biết manager đó cho phép tạo cache động hay chỉ chấp nhận tên đã đăng ký.
- [ ] Nếu strict, mọi tên cần thiết đã được cấp phát/khai báo và được test.
- [ ] Nếu dynamic, có chính sách chặn typo hoặc kiểm soát số lượng region.
- [ ] Không nhầm region thiếu với entry miss hoặc backend outage.
- [ ] Có kiểm thử qua Spring proxy cho cả tên hợp lệ và tên sai.
- [ ] Có kế hoạch cấu hình theo dev/test/prod; không mặc định mọi profile dùng cùng provider.
- [ ] Có metrics và cảnh báo khi phát sinh vùng cache lạ hoặc name resolution thất bại.
- [ ] Có chính sách TTL, memory, serialization và invalidation phù hợp vùng cache mới.
- [ ] Không dùng fallback/no-op để che giấu lỗi tên cache quan trọng.

## 13. Câu hỏi tự kiểm tra

**1.** `@Cacheable(cacheNames="products")` có tự bảo đảm vùng `products` được tạo từ khi ứng dụng khởi động không?  
**Đáp án:** Không. Điều đó phụ thuộc `CacheManager` và chính sách khởi tạo/lazy allocation.

**2.** `CacheManager.getCache("products")` trả về `null` có đồng nghĩa `products[42]` đang miss không?  
**Đáp án:** Không. Chưa phân giải được cache region khác với việc một region hợp lệ không có entry theo key.

**3.** `new ConcurrentMapCacheManager()` với annotation tên chưa khai báo thường xử lý ra sao?  
**Đáp án:** Có thể tạo cache region mới theo yêu cầu.

**4.** `new ConcurrentMapCacheManager("products")` nhưng annotation dùng `"prodcuts"` thường xử lý ra sao?  
**Đáp án:** Manager strict trả `null`; resolver mặc định có thể ném lỗi phân giải cache lúc method được gọi.

**5.** Vì sao `getCacheNames()` trống không luôn chứng minh cache name không hợp lệ?  
**Đáp án:** Với dynamic manager, vùng cache có thể chưa được cấp phát và chỉ được tạo khi có yêu cầu.

**6.** Có thể dùng `CacheErrorHandler` để chắc chắn sửa lỗi thiếu cache name không?  
**Đáp án:** Không. Lỗi name resolution khác lỗi thao tác trên một đối tượng `Cache` hợp lệ.

**7.** Vì sao dùng `CompositeCacheManager` với fallback no-op phải cân nhắc?  
**Đáp án:** Có thể cho nghiệp vụ tiếp tục chạy nhưng âm thầm bỏ caching, che giấu lỗi cấu hình và gây tăng tải.

**8.** Một service sử dụng `cacheManager="redisManager"`, nhưng cache name chỉ có ở `localManager`. Cần kiểm tra gì?  
**Đáp án:** Manager được chọn trên annotation/class và danh sách vùng được manager tương ứng quản lý.

**9.** Khi nào nên kiểm tra cache name trong startup validator?  
**Đáp án:** Khi có danh sách vùng bắt buộc và strict policy; phải lưu ý validator có thể tự cấp phát cache nếu manager ở dynamic mode.

**10.** Nếu `getCache("products")` trả đối tượng Cache nhưng thao tác `get(key)` timeout, loại lỗi nào cần xử lý?  
**Đáp án:** Lỗi backend/provider/network, không mặc định là lỗi tên cache.

## Tài liệu tham khảo

- Spring Framework 6.2 — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework 6.2 — Configuring Cache Storage: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/store-configuration.html
- Spring Framework 6.2 — ConcurrentMapCacheManager API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework 6.2 — CacheManager API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/CacheManager.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
- Spring Data Redis — RedisCacheManagerBuilder: https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/cache/RedisCacheManager.RedisCacheManagerBuilder.html
