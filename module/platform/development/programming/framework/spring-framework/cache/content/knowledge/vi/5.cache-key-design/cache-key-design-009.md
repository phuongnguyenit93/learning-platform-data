# Viết KeyGenerator dùng chung và đăng ký bean trong Spring Cache

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Hiểu vai trò của \`KeyGenerator\` trong Spring Cache và khi nào nên viết bộ sinh khóa dùng chung.
- Triển khai phương thức \`generate(Object target, Method method, Object... params)\` để tạo khóa đúng ngữ nghĩa nghiệp vụ.
- Đăng ký một \`KeyGenerator\` thành Spring bean, tham chiếu bằng \`@Cacheable(keyGenerator = "...")\`, dùng chung qua \`@CacheConfig\`, và hiểu cách cấu hình mặc định toàn ứng dụng.
- Thiết kế cùng quy tắc khóa cho đọc, cập nhật, xóa cache; tránh collision, lẫn tenant, khóa không ổn định và lỗi serialization.
- Chạy ví dụ Java 17 để quan sát cache hit, cách ly tenant, hai vùng cache và việc \`@CacheEvict\` dùng lại cùng khóa.

## 1. KeyGenerator nằm ở đâu trong cơ chế Spring Cache?

Spring Cache quản lý các thao tác lưu kết quả phương thức theo cặp **cache name + cache key**. Khi lời gọi đi qua Spring caching proxy, framework xác định cache cần truy cập, tạo key rồi tra cứu entry. Với \`@Cacheable\`, cache hit có thể trả kết quả mà không chạy thân phương thức. Với cache miss, phương thức được thực thi và kết quả có thể được lưu.

\`org.springframework.cache.interceptor.KeyGenerator\` là một interface cho phép bạn **biến ngữ cảnh của một lời gọi Java thành một đối tượng key**. Đây là điểm mở rộng khi cách chọn key mặc định chưa diễn đạt chính xác bản sắc của dữ liệu cần cache.

Luồng cơ bản:

~~~text
Gọi phương thức qua Spring proxy
            |
   xác định cacheNames
            |
     KeyGenerator.generate(...)
            |
     tạo key cho lời gọi
            |
    Cache.get(key) / Cache.put(key, result)
~~~

Ví dụ, giả sử ứng dụng có phương thức:

~~~java
String getTitle(String tenantId, String productId, String traceId);
~~~

Nếu cùng \`tenantId\` và \`productId\` luôn tạo cùng tiêu đề, còn \`traceId\` chỉ là metadata theo request và **không ảnh hưởng giá trị**, việc đưa traceId vào key mặc định sẽ tạo entry mới theo mỗi request. Một KeyGenerator dùng chung có thể chỉ chọn \`tenantId\` và \`productId\`.

Lưu ý: nếu traceId **thực sự ảnh hưởng dữ liệu** hoặc tác dụng phụ bắt buộc của phương thức thì không được loại nó khỏi chiến lược cache một cách tùy tiện. Caching chỉ thích hợp khi bỏ qua thân phương thức trên hit là an toàn.

## 2. So sánh sinh khóa mặc định, SpEL và KeyGenerator

### 2.1. Mặc định: SimpleKeyGenerator

Nếu không chỉ định \`key\` hoặc \`keyGenerator\`, Spring thường sử dụng \`SimpleKeyGenerator\`:

| Tham số phương thức | Khóa mặc định |
| --- | --- |
| Không có tham số | \`SimpleKey.EMPTY\` |
| Một tham số | Chính đối tượng tham số đó |
| Từ hai tham số trở lên | \`SimpleKey\` chứa toàn bộ tham số |

Điều này phù hợp nếu **tất cả tham số đều ảnh hưởng kết quả** và đối tượng làm key có \`equals()\`/\`hashCode()\` ổn định. Với \`getTitle(tenantId, productId, traceId)\`, \`traceId\` cũng đi vào key, dù chỉ là thông tin theo dõi yêu cầu.

### 2.2. SpEL: tốt cho một phương thức có quy tắc đơn giản

~~~java
@Cacheable(
    cacheNames = "productTitles",
    key = "T(org.springframework.cache.interceptor.SimpleKey).class"
)
~~~

Đoạn trên **không phải ví dụ khóa nên sử dụng**: nó minh họa rằng không thể suy ra một key đúng bằng cách lấy một giá trị cố định, vì các sản phẩm sẽ collision. Để chọn hai tham số, có thể dùng một biểu thức SpEL hoặc gọi một hàm tạo key được kiểm soát. Ví dụ ngắn hơn với một tham số nghiệp vụ:

~~~java
@Cacheable(cacheNames = "productTitles", key = "#p0")
public String titleByProductId(String productId) {
    return repository.findTitle(productId);
}
~~~

Đây là mã minh họa có repository bên ngoài. Với một vài phương thức, SpEL thường dễ đọc hơn việc tạo thêm lớp Java. Khi **nhiều phương thức cần cùng một thuật toán** (chuẩn hóa ID có quy tắc, tổ hợp tenant + mã dữ liệu, kiểm soát phiên bản key, xác thực kiểu tham số), \`KeyGenerator\` dùng chung dễ kiểm thử và ít lặp logic hơn.

### 2.3. KeyGenerator: thuật toán tái sử dụng

Ví dụ sử dụng bean theo tên:

~~~java
@Cacheable(
    cacheNames = "productTitles",
    keyGenerator = "tenantProductKeyGenerator"
)
public String getTitle(String tenantId, String productId, String traceId) {
    return repository.findTitle(tenantId, productId);
}
~~~

Mã minh họa này yêu cầu một bean tên \`tenantProductKeyGenerator\`. **\`key\` và \`keyGenerator\` loại trừ lẫn nhau trên cùng một thao tác cache**: không đặt cả hai trong một \`@Cacheable\`, \`@CachePut\` hoặc \`@CacheEvict\`.

## 3. Hợp đồng của interface KeyGenerator

Interface có một phương thức chính:

~~~java
public interface KeyGenerator {
    Object generate(Object target, Method method, Object... params);
}
~~~

- **\`target\`**: đối tượng đích được gọi. Có thể dùng khi cần xác định namespace, nhưng không nên biến identity của instance, địa chỉ bộ nhớ hoặc proxy ngẫu nhiên thành key.
- **\`method\`**: thông tin phương thức \`java.lang.reflect.Method\`. Dùng khi thuật toán cần phân biệt các phương thức, nhưng hãy xét cách những thao tác đọc/evict/put phải dùng **cùng key**.
- **\`params\`**: các đối số đã truyền vào, theo thứ tự chữ ký Java; tham số kiểu nguyên thủy đã được boxing.
- **Giá trị trả về**: object đại diện key. Với cache local, \`equals()\` và \`hashCode()\` có ý nghĩa đặc biệt quan trọng; với cache phân tán, còn phải bảo đảm định dạng serialize ổn định.

KeyGenerator **không thực thi truy vấn dữ liệu** và không quyết định TTL, eviction, cache manager hay thời gian lưu. Những việc đó thuộc policy và provider khác.

### 3.1. Điều kiện của một key tốt

Một key nên:

1. **Nhất quán:** cùng danh tính dữ liệu tạo key bằng nhau qua các lần gọi.
2. **Phân biệt đúng:** hai kết quả nghiệp vụ khác nhau không dùng cùng key trong một cache name.
3. **Bền vững:** không chứa mutable object, ID của request tạm thời, hash dựa trên memory address hoặc chuỗi phụ thuộc định dạng máy.
4. **Cách ly:** nếu kết quả phụ thuộc tenant/user/locale/quyền/phiên bản thì key và chiến lược bảo mật phải phản ánh những yếu tố đó.
5. **Tương thích đọc và xóa:** một thao tác evict muốn xóa entry vừa được \`@Cacheable\` tạo phải sinh cùng key và nhắm đúng cache name.
6. **Kiểm soát được cardinality:** tránh nhét timestamp hoặc traceId không liên quan vào key làm cache chỉ miss.

**Không nên chỉ dùng \`Objects.hash(tenantId, productId)\` làm key duy nhất.** Hash 32-bit có thể trùng cho hai bộ dữ liệu khác nhau. \`record\` chứa nguyên các thành phần, hoặc một kiểu key có \`equals/hashCode\` đúng, giúp các thành phần vẫn được so sánh khi phát sinh hash collision trong cấu trúc map.

### 3.2. Tại sao dùng record trong Java 17?

~~~java
public record ProductKey(String tenantId, String productId) {}
~~~

\`record\` tự sinh \`equals()\`, \`hashCode()\`, \`toString()\` dựa trên thành phần; không cần tự nối chuỗi với ký tự phân tách. Ví dụ nối \`tenant + ":" + id\` có thể collision nếu \`tenant\` hoặc \`id\` chứa \`:\` mà không có escaping rõ ràng. Với Redis hoặc provider có serializer riêng, vẫn cần kiểm chứng cách record được mã hóa thành key thực tế, không mặc định rằng mọi serializer đều hỗ trợ record.

## 4. Ví dụ Java 17: dùng chung một bean KeyGenerator qua @CacheConfig

Ví dụ này dùng Spring Framework 6.2.10 và cache in-memory. Hai phương thức đọc \`getTitle\` và \`getCategory\` dùng chung một thuật toán tạo key; mỗi phương thức có **cacheNames riêng** để tránh collision giữa hai loại dữ liệu. \`invalidateTitle\` dùng lại cùng KeyGenerator để xóa đúng entry.

\`traceId\` được truyền vào như metadata; trong bài demo, nó không ảnh hưởng nội dung trả về. Mọi phương thức áp dụng generator đều nhận ba tham số kiểu \`String\` theo thứ tự \`(tenantId, productId, traceId)\`. Trong dự án thật, nên cân nhắc tách trace context khỏi chữ ký nghiệp vụ nếu có thể.

### 4.1. Cấu trúc dự án

~~~text
spring-custom-key/
├── pom.xml
└── src/main/java/demo/CacheKeyExample.java
~~~

### 4.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-custom-key</artifactId>
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

### 4.3. src/main/java/demo/CacheKeyExample.java

~~~java
package demo;

import java.lang.reflect.Method;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheKeyExample {

    // Một value object bất biến làm key cho cache trong RAM.
    public record ProductKey(String tenantId, String productId) {}

    // Hợp đồng: (tenantId, productId, traceId), tất cả là String.
    public static class TenantProductKeyGenerator implements KeyGenerator {
        @Override
        public Object generate(Object target, Method method, Object... params) {
            if (params.length != 3
                    || !(params[0] instanceof String)
                    || !(params[1] instanceof String)
                    || !(params[2] instanceof String)) {
                throw new IllegalArgumentException(
                    "Invalid parameters for " + method.getName());
            }
            String tenantId = (String) params[0];
            String productId = (String) params[1];
            // params[2] là traceId, KHÔNG ảnh hưởng kết quả nghiệp vụ.
            return new ProductKey(tenantId, productId);
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {

        // Bean name phải trùng chính xác với keyGenerator bên dưới.
        @Bean("tenantProductKeyGenerator")
        public KeyGenerator tenantProductKeyGenerator() {
            return new TenantProductKeyGenerator();
        }

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                "productTitles", "productCategories");
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    // Một chính sách key áp dụng cho các cache operation của class.
    @CacheConfig(keyGenerator = "tenantProductKeyGenerator")
    public static class ProductService {
        private final AtomicInteger titleLoads = new AtomicInteger();
        private final AtomicInteger categoryLoads = new AtomicInteger();

        @Cacheable(cacheNames = "productTitles")
        public String getTitle(
                String tenantId, String productId, String traceId) {
            titleLoads.incrementAndGet();
            return "Title@" + tenantId + "/" + productId;
        }

        @Cacheable(cacheNames = "productCategories")
        public String getCategory(
                String tenantId, String productId, String traceId) {
            categoryLoads.incrementAndGet();
            return "Category@" + tenantId + "/" + productId;
        }

        @CacheEvict(cacheNames = "productTitles")
        public void invalidateTitle(
                String tenantId, String productId, String traceId) {
            // Giả lập sự kiện dữ liệu nguồn đã thay đổi.
            // @CacheEvict xóa entry sau khi method hoàn tất thành công.
        }

        public int titleLoadCount() {
            return titleLoads.get();
        }

        public int categoryLoadCount() {
            return categoryLoads.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            ProductService service = context.getBean(ProductService.class);
            Cache titles = Objects.requireNonNull(
                context.getBean(CacheManager.class)
                       .getCache("productTitles"));

            System.out.println(service.getTitle("t1", "P-7", "req-1"));
            System.out.println(service.getTitle("t1", "P-7", "req-2"));
            System.out.println("Title loads: " + service.titleLoadCount());

            System.out.println(service.getTitle("t2", "P-7", "req-3"));
            System.out.println("Title loads: " + service.titleLoadCount());

            System.out.println(service.getCategory("t1", "P-7", "req-4"));
            System.out.println(
                "Category loads: " + service.categoryLoadCount());

            service.invalidateTitle("t1", "P-7", "admin");
            System.out.println(
                "Title entry after evict: "
                    + (titles.get(new ProductKey("t1", "P-7")) != null));

            System.out.println(service.getTitle("t1", "P-7", "req-5"));
            System.out.println("Title loads: " + service.titleLoadCount());
        }
    }
}
~~~

### 4.4. Chạy từ thư mục chứa pom.xml

Cần JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheKeyExample
~~~

Những dòng **chương trình tự in** (không tính log Maven) là:

~~~text
Title@t1/P-7
Title@t1/P-7
Title loads: 1
Title@t2/P-7
Title loads: 2
Category@t1/P-7
Category loads: 1
Title entry after evict: false
Title@t1/P-7
Title loads: 3
~~~

### 4.5. Vì sao output như vậy?

1. \`getTitle("t1", "P-7", "req-1")\` tạo khóa \`ProductKey("t1", "P-7")\`, miss nên chạy thân phương thức.
2. \`getTitle("t1", "P-7", "req-2")\` dùng **cùng khóa** dù traceId khác, vì traceId không ảnh hưởng kết quả; cache hit nên \`titleLoads\` vẫn là 1.
3. \`getTitle("t2", "P-7", "req-3")\` có tenant khác, nên key khác; cache miss, \`titleLoads\` tăng thành 2.
4. \`getCategory("t1", "P-7", "req-4")\` dùng cùng cấu trúc key nhưng **vùng cache khác** (\`productCategories\`), vì vậy không đọc nhầm giá trị title.
5. \`invalidateTitle("t1", "P-7", "admin")\` thừa hưởng cùng generator từ \`@CacheConfig\`, tạo cùng key với \`getTitle\`, rồi \`@CacheEvict\` xóa đúng entry khỏi \`productTitles\`.
6. Lần gọi \`getTitle("t1", "P-7", "req-5")\` lại miss và chạy nguồn, nên bộ đếm title thành 3.

**Điều kiện để quan sát đúng:** lời gọi cần đi qua bean do Spring quản lý. \`@EnableCaching\` cho phép Spring tạo cache advice, còn \`context.getBean(ProductService.class)\` lấy bean được proxy. Nếu trong chính \`ProductService\` gọi trực tiếp \`this.getTitle(...)\`, self-invocation trong proxy mode mặc định sẽ không đi qua cache interceptor.

**Phân biệt demo với hệ thống thật:** \`ConcurrentMapCacheManager\` lưu trong RAM tiến trình, thích hợp để học và test. Một môi trường nhiều instance cần xem xét hạ tầng cache dùng chung, TTL, max-size, eviction, serializer, error handling và chính sách đồng bộ dữ liệu.

## 5. Ba cách đăng ký và sử dụng KeyGenerator

### 5.1. Cách 1: chọn tường minh cho từng method

Định nghĩa bean:

~~~java
@Bean("tenantProductKeyGenerator")
public KeyGenerator tenantProductKeyGenerator() {
    return new TenantProductKeyGenerator();
}
~~~

Và chọn bằng tên:

~~~java
@Cacheable(
    cacheNames = "productTitles",
    keyGenerator = "tenantProductKeyGenerator"
)
public String getTitle(String tenantId, String productId, String traceId) {
    return repository.findTitle(tenantId, productId);
}
~~~

Các đoạn trong mục này là **mã minh họa khi tích hợp vào Spring project**, với lớp generator và repository đã được định nghĩa. Tên bean phải khớp, ví dụ \`tenantProductKeyGenerator\` **không giống** \`tenantProductKeysGenerator\`.

Cách này phù hợp khi chỉ một số phương thức tuân theo hợp đồng key đặc biệt. Có thể dùng lại cùng tên bean trong nhiều \`@Cacheable\`, \`@CachePut\` và \`@CacheEvict\`.

### 5.2. Cách 2: chia sẻ quy tắc cho cả class bằng @CacheConfig

~~~java
@CacheConfig(keyGenerator = "tenantProductKeyGenerator")
public class ProductService {

    @Cacheable(cacheNames = "productTitles")
    public String getTitle(String tenantId, String productId,
                           String traceId) {
        // ...
        return "example";
    }

    @CacheEvict(cacheNames = "productTitles")
    public void invalidateTitle(String tenantId, String productId,
                                String traceId) {
        // ...
    }
}
~~~

\`@CacheConfig\` chỉ **chia sẻ mặc định** giữa các cache operation của class; nó không tự làm cho tất cả phương thức trong class được cache. Mỗi phương thức cần \`@Cacheable\`, \`@CachePut\`, \`@CacheEvict\` hoặc tổ hợp phù hợp.

Một \`keyGenerator\` chỉ định ở **method-level** sẽ ưu tiên hơn giá trị trong \`@CacheConfig\`. Vì thế bạn có thể đặt chính sách mặc định ở class và ghi đè có chủ đích cho một phương thức khác cấu trúc tham số.

### 5.3. Cách 3: đặt key generator mặc định toàn ứng dụng

Spring hỗ trợ \`CachingConfigurer\` khi cần cấu hình mặc định cho hạ tầng cache. Đây là **phương án cấu hình thay thế**, không nên đồng thời thêm class dưới đây vào project demo ở trên:

~~~java
import org.springframework.cache.annotation.CachingConfigurer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
class GlobalCachingConfig implements CachingConfigurer {

    @Bean
    @Override
    public KeyGenerator keyGenerator() {
        return new CacheKeyExample.TenantProductKeyGenerator();
    }
}
~~~

Trong ví dụ, \`CacheKeyExample.TenantProductKeyGenerator\` là lớp từ chương trình demo; đoạn cấu hình này **chỉ thích hợp toàn ứng dụng nếu mọi method sử dụng mặc định đó có hợp đồng 3 tham số tương ứng**. Một generator toàn cục dùng trong ứng dụng thực tế cần xử lý đầy đủ các chữ ký mà nó sẽ gặp; nếu không, các thao tác cache ngoài nhóm sản phẩm sẽ ném lỗi vì generator quá đặc thù.

Thứ tự ưu tiên thực tế để lựa chọn key generator là:

~~~text
keyGenerator chỉ định trực tiếp trên cache operation
                  |
          @CacheConfig cấp class
                  |
       mặc định qua CachingConfigurer
                  |
          SimpleKeyGenerator
~~~

Nếu muốn chỉ dùng một chính sách cho một nhóm service, \`@CacheConfig\` thường rõ ràng hơn việc đổi mặc định của toàn bộ ứng dụng.

## 6. Các lỗi thiết kế khóa thường gặp

### 6.1. Loại bỏ tham số thật sự ảnh hưởng kết quả

Giả sử \`getPrice(productId, currency)\` có kết quả khác nhau cho USD và VND; key chỉ dùng productId sẽ khiến giá trị của hai currency va nhau trong cùng vùng cache. Cần đưa currency vào key hoặc tách vùng theo ngữ nghĩa. Chỉ loại bỏ tham số khi có thể chứng minh nó không ảnh hưởng kết quả và không mang side effect bắt buộc.

### 6.2. Thiếu tenant, user hoặc quyền truy cập

Trong hệ thống nhiều tenant, cùng \`productId\` có thể đại diện những dữ liệu khác nhau. Key phải phân biệt tenant khi dữ liệu thuộc tenant, đồng thời kiểm soát quyền truy cập bên ngoài cache. Không dùng cache hit như một lần “bỏ qua authorization” nếu quyền cần được kiểm tra ở mọi request.

### 6.3. Đưa method name vào key mà không xét việc xóa

Một generator có thể tạo \`method.getName() + ":" + id\` để tách \`getTitle\` và \`getCategory\` trong cùng vùng cache. Tuy nhiên, nếu \`invalidateTitle\` dùng tên method của chính nó, key để xóa **không giống** key tạo bởi \`getTitle\`. Việc dùng chung KeyGenerator **không tự bảo đảm** key giống nhau: phải thiết kế cùng *cache name + identity key* cho read/evict/put.

Trong demo, hai method đọc dùng vùng cache khác nhau nên không cần method name trong key; \`invalidateTitle\` dùng lại đúng \`ProductKey(tenantId, productId)\`.

### 6.4. Nối chuỗi thiếu phân tách và versioning

Nối \`tenantId + productId\` có thể collision, ví dụ \`("ab", "c")\` và \`("a", "bc")\`. Nối có dấu \`:\` vẫn có rủi ro nếu dữ liệu có dấu đó. Có thể dùng record, \`SimpleKey\`, kiểu key riêng hoặc encoding có length-prefix/escaping chuẩn. Nếu cache provider yêu cầu chuỗi (đặc biệt Redis), hãy thiết kế quy ước tuần tự hóa rõ ràng và có version khi schema thay đổi.

### 6.5. Key chứa đối tượng mutable hoặc không ổn định

Không lấy một đối tượng DTO có trường thay đổi làm key nếu \`equals/hashCode\` dựa vào các trường đó. Không dùng \`target.toString()\` hoặc địa chỉ đối tượng để tạo key, vì key có thể khác giữa lần gọi và instance. Với cache phân tán, kiểm tra key serializer, tên vùng và định dạng được các instance chia sẻ.

### 6.6. Coi KeyGenerator là nơi giải quyết mọi vấn đề

KeyGenerator chỉ chọn key. Nó không cấu hình TTL, không chống cache stampede, không tự xóa khi database đổi, không cung cấp khóa phân tán, không đảm bảo transaction commit rồi mới put. Những nhu cầu đó thuộc CacheManager/provider, luồng invalidation, transaction-aware cache và kiểm thử concurrency.

### 6.7. Dùng cùng cache name cho các kết quả không cùng kiểu

Nếu cả \`getTitle\` và \`getCategory\` cùng dùng \`cacheNames="products"\` và key \`ProductKey(tenant, id)\`, một lời gọi có thể đọc sai giá trị của lời gọi khác. Dùng cache name riêng hoặc cố ý đưa phân loại dữ liệu vào key. Không dựa vào kiểu return để Spring tự tách key.

## 7. Khi nào không cần tạo KeyGenerator dùng chung?

Không phải mọi chỗ dùng \`@Cacheable\` đều cần custom generator.

- Một hàm chỉ nhận \`productId\` và cache đúng theo ID thường dùng khóa mặc định là đủ.
- Một hoặc hai phương thức có quy tắc đơn giản có thể dùng \`key = "#p0"\` hoặc SpEL tương đương, giúp người đọc thấy ngay key.
- Nếu các phương thức có ý nghĩa và chữ ký rất khác nhau, cố dùng một generator đặc thù toàn cục có thể tạo coupling và lỗi runtime.
- Nếu phương thức không nên cache vì kết quả thay đổi quá nhanh hoặc có side effect, custom key cũng không biến nó thành ứng viên cache đúng.

Nên tạo KeyGenerator dùng chung khi có **một quy tắc dữ liệu ổn định và thực sự được chia sẻ**: ví dụ các service cùng truy vấn tài nguyên theo cặp tenant + resourceId, cần cách cách ly thống nhất và tái sử dụng trong \`@Cacheable\` lẫn \`@CacheEvict\`.

## 8. Kiểm thử và kiểm tra vận hành

### 8.1. Test trực tiếp lớp generator

Vì \`KeyGenerator\` chỉ là Java code, có thể gọi \`generate(...)\` trực tiếp trong unit test, không cần mở Spring context. Các assertion thiết yếu:

1. Cùng \`tenantId\` + \`productId\` nhưng traceId khác → **key bằng nhau**.
2. Tenant khác nhưng productId giống → **key khác nhau**.
3. productId khác nhưng tenant giống → **key khác nhau**.
4. Sai số lượng/kiểu tham số → **lỗi rõ ràng**, không silently fallback về một key chung.
5. Record key phải có \`equals/hashCode\` phù hợp; nếu dùng serializer, kiểm thử round-trip.

### 8.2. Test tích hợp Spring Cache

Cần gọi method qua Spring bean/proxy và kiểm tra cả nguồn dữ liệu:

1. Miss đầu tiên gọi thân hàm và tạo cache entry.
2. Cùng key nhưng traceId khác hit, không gọi lại nguồn.
3. Tenant khác miss, không dùng dữ liệu của tenant trước.
4. Cùng key ở **hai cacheNames khác nhau** không lẫn giá trị.
5. Thao tác \`@CacheEvict\` sinh **đúng key** và lần đọc sau miss.
6. Nếu thay đổi một phương thức sang chữ ký mới, generator phải có lỗi có thể phát hiện thay vì lặng lẽ tạo key sai.
7. Nếu dùng Redis hoặc nhiều instance, kiểm chứng khóa sau serialization và hành vi invalidation giữa các instance.

Theo dõi hit ratio, cache cardinality, sự kiện eviction và mức tăng bộ nhớ để phát hiện khóa có quá nhiều thành phần không ổn định.

### 8.3. Checklist trước khi áp dụng production

- [ ] Bean \`KeyGenerator\` có tên chính xác và được Spring quản lý.
- [ ] \`@EnableCaching\` được bật trong context chứa các service cần intercept.
- [ ] Mọi phương thức áp dụng generator đáp ứng hợp đồng tham số.
- [ ] Key gồm đủ thành phần định danh kết quả; các tham số bị bỏ qua thật sự không ảnh hưởng kết quả.
- [ ] Phân biệt tenant/user/locale/version khi nghiệp vụ yêu cầu.
- [ ] Thao tác đọc, put và evict sử dụng cùng cache name và cùng quy tắc key.
- [ ] \`equals/hashCode\` ổn định; có chiến lược serialize phù hợp provider.
- [ ] Không đặt \`key\` và \`keyGenerator\` đồng thời trên cùng annotation.
- [ ] Unit test generator và integration test cache hit/miss/evict đều đạt.
- [ ] Có chiến lược TTL/invalidation/metrics riêng với chính sách sinh key.

## 9. Câu hỏi tự kiểm tra

**1.** Có bean tên \`tenantProductKeyGenerator\`. Cách nào chọn nó cho riêng một \`@Cacheable\`?  
**Đáp án:** \`@Cacheable(cacheNames = "productTitles", keyGenerator = "tenantProductKeyGenerator")\`.

**2.** Một KeyGenerator tạo khóa theo \`(tenantId, productId)\`; hai request chỉ khác traceId có nên tạo key khác nhau?  
**Đáp án:** Không nếu traceId chỉ là metadata và không ảnh hưởng kết quả hay side effect bắt buộc.

**3.** Vì sao \`record ProductKey(String tenantId, String productId)\` có lợi hơn chuỗi nối tùy tiện?  
**Đáp án:** Các thành phần được so sánh cấu trúc bằng equals/hashCode; không phải tự phát minh quy tắc escaping dấu phân tách cho cache local.

**4.** \`@CacheConfig(keyGenerator="...")\` tự bật cache cho mọi method trong class không?  
**Đáp án:** Không. Cần cache annotation trên method.

**5.** Nếu generator thêm \`method.getName()\` vào key, điều gì cần kiểm tra khi dùng \`@CacheEvict\`?  
**Đáp án:** Evict phải tạo đúng key mà lời gọi đọc đã dùng, dù tên method thường khác nhau.

**6.** Có thể đặt \`key="#p0"\` và \`keyGenerator="customKeyGenerator"\` trên cùng một \`@Cacheable\`?  
**Đáp án:** Không; hai thuộc tính loại trừ lẫn nhau.

**7.** Đổi KeyGenerator có tự xóa các entry cũ trong Redis không?  
**Đáp án:** Không. Phải có kế hoạch migration, versioning, TTL hoặc xóa vùng cache tương ứng.

## Tài liệu tham khảo

- Spring Framework Reference — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- KeyGenerator Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/KeyGenerator.html
- Spring Framework Reference — Configuring Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
