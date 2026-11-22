# KeyGenerator và ánh xạ lời gọi thành khóa trong Spring Cache

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích vì sao mỗi lời gọi được cache cần một khóa ổn định; dự đoán khóa mà Spring tạo mặc định; chọn giữa `key` (SpEL) và `keyGenerator`; viết `KeyGenerator` dùng lại được; và bảo đảm thao tác đọc, cập nhật, xóa cache cùng trỏ đến một mục dữ liệu. Trọng tâm là **ánh xạ một lời gọi phương thức thành khóa** trong kiến trúc Spring Cache, không phải cấu hình TTL hay lựa chọn nhà cung cấp cache.

## 1. Một lời gọi trở thành một mục cache như thế nào?

Một mục cache có thể hình dung bằng cặp `(tên cache, khóa) → giá trị`. Tên cache xác định không gian lưu trữ, còn khóa phân biệt các kết quả bên trong không gian đó. Chẳng hạn, các lời gọi `find("tenant-A", "P1")` và `find("tenant-B", "P1")` phải khác khóa nếu mỗi tenant có dữ liệu riêng. Hai phương thức cùng dùng cache `"catalog"` cũng có thể vô tình trùng khóa; **Spring không tự thêm tên phương thức vào khóa mặc định**.

Với lời gọi được Spring AOP chặn qua proxy, luồng `@Cacheable` có thể đọc như sau:

1. Spring nhận phương thức đích, đối số và cấu hình cache; kiểm tra `condition` nếu có.
2. Spring xác định các cache theo `cacheNames`/`CacheResolver`, sau đó tính khóa bằng biểu thức `key` hoặc một `KeyGenerator`.
3. Cache **hit**: Spring trả kết quả đã lưu mà không gọi thân phương thức (đối với trường hợp `@Cacheable` thông thường).
4. Cache **miss**: Spring chạy phương thức; nếu điều kiện ghi sau khi chạy (`unless`) cho phép, lưu giá trị dưới chính khóa đó.

Đây là mô hình logic để hiểu trách nhiệm của các thành phần; thứ tự chi tiết và cách xử lý không đồng bộ còn phụ thuộc loại operation và phiên bản/provider. Đặc biệt, `@CachePut` **luôn gọi phương thức** rồi cập nhật cache; `@CacheEvict` loại bỏ mục theo khóa hoặc xóa cả cache khi `allEntries=true`.

~~~text
Lời gọi find(tenantId, productId)
          |
          v
  Cache interceptor / annotation
          |
          +-- Chọn cache: "catalog"
          +-- Tạo khóa: (tenantId, productId)
                      |
                cache.get(key)
                 +----+----+
               HIT        MISS
                |           |
           Trả giá trị   Gọi phương thức
                            |
                       cache.put(key, value)
                            |
                        Trả giá trị
~~~

`KeyGenerator` chỉ chịu trách nhiệm **chọn khóa**. `CacheResolver`/`CacheManager` quyết định **cache nào** được sử dụng; provider (ConcurrentMap, Caffeine, Redis...) đảm nhiệm lưu trữ và chính sách hết hạn. Một khóa tốt không tự tạo TTL, đồng bộ dữ liệu hay tránh stale data.

## 2. Khóa mặc định: `SimpleKeyGenerator`

Khi operation không khai báo `key` hoặc `keyGenerator`, Spring dùng `org.springframework.cache.interceptor.SimpleKeyGenerator`. Các trường hợp chính:

| Đối số của lời gọi | Dạng khóa mặc định | Ý nghĩa |
| --- | --- | --- |
| Không có đối số | `SimpleKey.EMPTY` | Mọi lời gọi cùng phương thức/cache không đối số dùng chung một khóa. |
| Một đối số khác `null`, không phải mảng | Chính đối tượng đối số | Cần `equals()` và `hashCode()` phù hợp. |
| Hai đối số trở lên | `SimpleKey` chứa toàn bộ đối số | Thứ tự và giá trị đối số tham gia so sánh. |
| Một đối số là `null` hoặc mảng | Một `SimpleKey` | Trường hợp đặc biệt, tránh dùng trực tiếp `null`/mảng làm khóa. |

Ví dụ `lookup("P1")` có khóa `"P1"`; `lookup("A", "P1")` có khóa ghép tương đương `SimpleKey("A", "P1")`. Đây là mô tả **cấu trúc khóa**, không phải cam kết chuỗi `toString()` dùng làm khóa lưu trữ.

Cách mặc định thuận tiện khi **mọi đối số thực sự xác định kết quả**, đều có tính bình đẳng ổn định và backend chấp nhận kiểu khóa ấy. Nó có thể gây ra các vấn đề:

- `findById("42")` và `findBySku("42")` dùng chung `cacheNames="products"`: mặc định đều ra `"42"` dù hai phương thức có ý nghĩa khác nhau.
- Tham số `tenantId` bị bỏ khỏi khóa tùy biến: hai tenant có thể đọc nhầm kết quả.
- Khóa dựa trên đối tượng thay đổi trạng thái, mảng/collection có thể bị sửa, hoặc lớp không định nghĩa `equals/hashCode` theo định danh nghiệp vụ: hành vi hit/miss không ổn định.
- Tham số là DTO phức tạp vẫn có thể làm khóa trong cache nội bộ, nhưng backend phân tán có thể yêu cầu chuyển đổi/serializer riêng.

Đừng chỉ tính `hashCode()` rồi dùng số nguyên đó làm khóa: các đối tượng khác nhau có thể trùng hash. Khóa vẫn phải có quy tắc `equals()` nhất quán. `SimpleKey` hiện đại so sánh các thành phần, thay vì chỉ lấy một hash tổng hợp như chiến lược cũ trước Spring 4.

## 3. Chọn khóa bằng SpEL khi chỉ một operation cần tùy biến

Thuộc tính `key` trên `@Cacheable`, `@CachePut`, `@CacheEvict` nhận một biểu thức Spring Expression Language (SpEL). Bạn có thể chọn đúng đối số ảnh hưởng tới kết quả mà không cần tạo bean mới:

~~~java
// Minh họa khai báo; các kiểu Product/Report thuộc ứng dụng, không chạy độc lập.
@Cacheable(cacheNames = "products", key = "#p0")
public Product findById(String id) { return loadProduct(id); }

@Cacheable(cacheNames = "productsByTenant", key = "#p0 + ':' + #p1")
public Product find(String tenantId, String id) { return loadProduct(tenantId, id); }

@Cacheable(cacheNames = "reports", key = "#root.methodName + ':' + #p0")
public Report report(String id) { return generateReport(id); }
~~~

`#p0` hoặc `#a0` là đối số thứ nhất, `#p1` là đối số thứ hai; `#root.args[0]` cũng truy cập được đối số đầu. `#root.methodName`, `#root.method`, `#root.targetClass` cung cấp metadata lời gọi. Tên như `#tenantId` chỉ dùng được nếu Spring nhận diện tên tham số (chẳng hạn biên dịch với `-parameters`); cú pháp vị trí `#p0` thường ít phụ thuộc cấu hình biên dịch hơn.

Biểu thức nối chuỗi ở trên ngắn gọn để minh họa, nhưng có thể gây **va chạm do dấu phân cách**: `("a:b","c")` và `("a","b:c")` tạo cùng một chuỗi. Với định danh có thể chứa `:`, hãy chọn cách mã hóa không nhập nhằng hoặc khóa cấu trúc bất biến (ví dụ `record` ở phần sau). Nếu chuỗi được dùng cho Redis, hãy xem xét chuẩn hóa và cách serialize tương ứng.

`key` và `keyGenerator` **loại trừ nhau trên cùng một annotation**. Khai báo đồng thời sẽ gây lỗi cấu hình; không có cơ chế “ưu tiên cái này rồi thử cái kia”. Một biểu thức `key` cho `@Cacheable` được tính trước khi chạy phương thức nên không thể phụ thuộc `#result`; `#result` thích hợp ở những biểu thức được đánh giá sau khi có kết quả, chẳng hạn `unless`.

## 4. Khi nào tự viết `KeyGenerator`?

Chọn `KeyGenerator` khi nhiều operation cần cùng một quy tắc khóa, khi phải chuẩn hóa đối số, hoặc khi muốn dùng đối tượng khóa có `equals/hashCode` rõ ràng. Hợp đồng của Spring là:

~~~java
package org.springframework.cache.interceptor;

public interface KeyGenerator {
    Object generate(Object target, java.lang.reflect.Method method, Object... params);
}
~~~

Đây là **chữ ký API minh họa**, không phải tệp cần tạo trong ứng dụng. `target` là đối tượng đích, `method` là phương thức được gọi, `params` là các đối số; giá trị trả về chính là khóa dùng với cache. Có thể đọc `method` để phân biệt operation, nhưng chỉ nên làm vậy nếu tất cả đường đọc/ghi/xóa thực sự áp dụng **cùng quy tắc định danh**.

Một generator đáng tin cậy nên:

1. Dựa vào những dữ liệu **quyết định kết quả**: tenant, id, phiên bản, ngôn ngữ, tùy chọn lọc hoặc phân trang nếu chúng thay đổi kết quả.
2. Trả cùng khóa cho các lời gọi tương đương, không phụ thuộc thời gian hiện tại, số ngẫu nhiên, địa chỉ đối tượng hay trạng thái thay đổi ngoài ý muốn.
3. Dùng kiểu bất biến có `equals/hashCode` rõ ràng; không dùng một hash trần thay định danh.
4. Có chi phí thấp, không gọi mạng/DB và không gây side effect.
5. Được dùng thống nhất cho `@Cacheable`, `@CachePut` và `@CacheEvict` khi chúng thao tác trên **cùng một mục**.

Quan trọng: generator cố tình gắn `method.getName()` vào khóa của `find(...)` sẽ tạo khóa khác khi chạy `evict(...)`; lúc đó lệnh xóa không đụng đến mục đã lưu, trừ khi có cơ chế ánh xạ chung được thiết kế riêng. Tên phương thức chỉ là thành phần khóa khi yêu cầu nghiệp vụ thực sự cần phân tách các tập kết quả.

## 5. Ví dụ chạy được: khóa ghép tenant + sản phẩm và xóa đúng mục

Ví dụ dưới đây dùng **Java 17, Spring Boot 3.3.5, Spring Cache** và `ConcurrentMapCacheManager` để quan sát hit/miss mà không cần Redis. Cấu trúc Maven:

~~~text
cache-key-demo/
|-- pom.xml
+-- src/main/java/example/cache/
    |-- DemoApplication.java
    +-- CatalogService.java
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
    <artifactId>cache-key-demo</artifactId>
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

import java.util.Objects;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }

    // Không thêm tên method: find và evict phải dùng cùng khóa.
    @Bean("catalogKeyGenerator")
    KeyGenerator catalogKeyGenerator() {
        return (target, method, params) -> {
            if (params.length != 2
                    || !(params[0] instanceof String)
                    || !(params[1] instanceof String)) {
                throw new IllegalArgumentException(
                        "Expected tenantId and productId as Strings");
            }
            return new ProductKey(
                    Objects.requireNonNull((String) params[0]),
                    Objects.requireNonNull((String) params[1]));
        };
    }

    // Record Java 17: bất biến, equals/hashCode theo hai thành phần.
    private record ProductKey(String tenantId, String productId) {}

    @Bean
    CommandLineRunner showCacheBehavior(CatalogService catalog) {
        return args -> {
            System.out.println(catalog.find("A", "P1"));
            System.out.println(catalog.find("A", "P1"));
            System.out.println(catalog.find("B", "P1"));
            catalog.evict("A", "P1");
            System.out.println(catalog.find("A", "P1"));
        };
    }
}
~~~

**`src/main/java/example/cache/CatalogService.java`**

~~~java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger databaseCalls = new AtomicInteger();

    @Cacheable(cacheNames = "catalog", keyGenerator = "catalogKeyGenerator")
    public String find(String tenantId, String productId) {
        int call = databaseCalls.incrementAndGet();
        return tenantId + "/" + productId + " -> load#" + call;
    }

    @CacheEvict(cacheNames = "catalog", keyGenerator = "catalogKeyGenerator")
    public void evict(String tenantId, String productId) {
        // Ở ứng dụng thực, thao tác thay đổi dữ liệu thuộc tầng nghiệp vụ.
    }
}
~~~

Chạy từ thư mục `cache-key-demo` với JDK 17+ và Maven:

~~~bash
mvn -q spring-boot:run
~~~

Bốn dòng do `CommandLineRunner` in ra (log khởi động Spring có thể xuất hiện thêm):

~~~text
A/P1 -> load#1
A/P1 -> load#1
B/P1 -> load#2
A/P1 -> load#3
~~~

**Giải thích từng lần:** lời gọi đầu cho `(A,P1)` bị miss và chạy phương thức (`load#1`); lần thứ hai hit nên vẫn trả `load#1`. `(B,P1)` tạo khóa khác dù cùng mã sản phẩm (`load#2`). `evict(A,P1)` xóa đúng khóa do cùng `KeyGenerator` và cache `"catalog"`; đọc lại `(A,P1)` chạy thân phương thức lần ba (`load#3`). `AtomicInteger` chỉ giúp quan sát số lần đọc, không phải thành phần khóa.

`ConcurrentMapCacheManager` ở đây lưu trong bộ nhớ JVM, phù hợp minh họa. Khi chuyển sang Redis hoặc provider phân tán, cần kiểm tra cách chuyển đổi/serialize khóa `ProductKey`: không mặc định cho rằng một `record` bất kỳ dùng được nguyên dạng ở mọi backend. Có thể chọn dạng chuỗi chuẩn hóa, có định dạng không nhập nhằng, hoặc cấu hình serializer/converter rõ ràng.

## 6. Cấu hình generator ở phạm vi nào?

Có ba mức cấu hình quan trọng:

| Nơi khai báo | Ví dụ | Phạm vi áp dụng |
| --- | --- | --- |
| Trên operation | `@Cacheable(cacheNames="catalog", keyGenerator="catalogKeyGenerator")` | Chỉ operation đó; ưu tiên cao nhất. |
| Trên class | `@CacheConfig(cacheNames="catalog", keyGenerator="catalogKeyGenerator")` | Giá trị mặc định cho các operation cache trong class; không tự bật caching. |
| Toàn cục | Bean được trả về từ `CachingConfigurer#keyGenerator()` | Mặc định cho các operation không cấu hình riêng. |

Ví dụ khi nhiều phương thức của một service sử dụng cùng định danh:

~~~java
// Minh họa cấu hình; các method trả về dữ liệu giả lập.
@CacheConfig(cacheNames = "catalog", keyGenerator = "catalogKeyGenerator")
@Service
public class AnotherCatalogService {
    @Cacheable
    public String find(String tenantId, String productId) {
        return "value";
    }

    @CacheEvict
    public void evict(String tenantId, String productId) {
    }
}
~~~

Các method vẫn cần annotation như `@Cacheable`/`@CacheEvict`; `@CacheConfig` một mình không tạo cache operation. Cần bật hỗ trợ annotation bằng `@EnableCaching` và gọi qua Spring-managed bean/proxy. Với cấu hình proxy mặc định, `this.find(...)` gọi từ chính object (self-invocation) bỏ qua cache interceptor, cho dù `KeyGenerator` hoàn toàn đúng.

## 7. Đồng bộ quy tắc khóa giữa đọc, cập nhật và vô hiệu hóa

Giả sử `find(tenantId, id)` lưu dưới `(tenantId, id)`, còn `update(tenantId, id, data)` dùng mặc định cả ba đối số làm khóa. `@CachePut` của `update` sẽ ghi vào **mục khác**; `find` vẫn đọc dữ liệu cũ. Tương tự, `@CacheEvict` dùng chỉ `id` sẽ không xóa được khóa ghép `(tenantId, id)`. Thiết kế nên xác định một **cache identity** trước, rồi dùng nó nhất quán cho mọi operation.

Cách dùng SpEL thống nhất có thể là:

~~~java
// Các chữ ký minh họa trong một service; không phải chương trình độc lập.
@Cacheable(cacheNames = "catalog", key = "#p0 + ':' + #p1")
public Product find(String tenantId, String id) {
    return loadProduct(tenantId, id);
}

@CachePut(cacheNames = "catalog", key = "#p0 + ':' + #p1")
public Product update(String tenantId, String id, UpdateRequest request) {
    return persistChanges(tenantId, id, request);
}

@CacheEvict(cacheNames = "catalog", key = "#p0 + ':' + #p1")
public void delete(String tenantId, String id) {
    deleteProduct(tenantId, id);
}
~~~

Biểu thức cần dựa trên **đúng hai đối số đầu** cho cả ba phương thức; `UpdateRequest` không tham gia khóa định danh. Với hệ thống nhiều tenant hoặc chuỗi chứa dấu phân cách, ưu tiên generator tạo khóa cấu trúc như ví dụ chạy được. Nếu phương thức cập nhật có thứ tự tham số khác, `#p0`/`#p1` phải được chỉnh tương ứng; viết giống nhau về cú pháp chưa chắc giống nhau về ý nghĩa.

`@CacheEvict(allEntries=true)` xóa toàn bộ cache được chỉ định, vì vậy không dùng khóa từng mục. Mặc định eviction chạy sau khi phương thức hoàn thành thành công; `beforeInvocation=true` đổi thời điểm thành trước khi gọi method. Chọn thời điểm theo tính nhất quán nghiệp vụ, không dùng nó để chữa lỗi sai khóa.

## 8. Những tiêu chí thiết kế khóa trong dự án thực

- **Đủ dữ liệu:** mọi tham số có thể thay đổi kết quả phải được xét; ví dụ `(tenantId, locale, filter, page, size)` nếu một trong số đó thay đổi nội dung trả về. Ngược lại, trace ID hay đối tượng logger thường không phải định danh kết quả.
- **Cô lập tenant/quyền truy cập:** nếu dữ liệu phụ thuộc tenant, account, role hoặc phạm vi quyền, khóa/cache phải phân tách phù hợp. Lỗi bỏ sót thành phần này có thể dẫn đến trả sai dữ liệu cho người dùng khác.
- **Bất biến và chuẩn hóa:** ưu tiên ID bất biến; quyết định rõ về chữ hoa/thường, khoảng trắng, timezone, locale, thứ tự danh sách. Chỉ chuẩn hóa hai input thành cùng khóa khi nghiệp vụ bảo đảm kết quả của chúng tương đương.
- **Không lộ bí mật:** tránh đưa token, mật khẩu, dữ liệu cá nhân nhạy cảm hoặc payload lớn vào chuỗi khóa có thể xuất hiện trong log/metrics/dashboard của provider.
- **Chi phí thấp:** tránh serialize toàn bộ object graph hoặc gọi service khác chỉ để tạo khóa; khóa cần rẻ và có thể xác định trước khi chạy logic nghiệp vụ.
- **Tương thích backend:** in-memory cache có thể dùng object có `equals/hashCode`; cache phân tán cần khóa serialize được và duy trì ngữ nghĩa ổn định qua các tiến trình/phiên bản.
- **Chiến lược invalidation:** khi đổi thuật toán khóa, các mục cũ có thể không còn truy cập/xóa được bằng khóa mới. Có thể cần version prefix, xóa cache hoặc migration theo chính sách vận hành.

Độ đúng của cache phụ thuộc vào cả **hàm ánh xạ khóa** và **quy tắc cập nhật/invalidation**. Khóa khớp chưa đủ nếu dữ liệu thay đổi ở đường đi không có eviction hoặc TTL thích hợp.

## 9. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách kiểm chứng/khắc phục |
| --- | --- | --- |
| Luôn miss dù đối số trông giống nhau | Đối số mutable, `equals/hashCode` khác mong đợi, cache khác tên, hoặc gọi `this.method()` bỏ qua proxy | Log có kiểm soát định danh khóa; thử gọi qua Spring bean như ví dụ; kiểm tra `equals` của key. |
| Hit nhưng trả dữ liệu của tenant/phương thức khác | Bỏ `tenantId`, hai method dùng cùng cache và cùng khóa mặc định | Liệt kê các thành phần của cache identity; tách cache hoặc bổ sung định danh. |
| `@CacheEvict` chạy nhưng vẫn còn giá trị cũ | Khác cache name, thứ tự tham số, generator, prefix hoặc method name | Tính khóa của `find` và `evict` cho **cùng thực thể**, so sánh cả cache name và key. |
| Báo lỗi cấu hình annotation | Khai báo đồng thời `key` và `keyGenerator`, hoặc tên bean generator không đúng | Dùng một cơ chế trên mỗi operation; kiểm tra bean được quản lý bởi Spring. |
| Khóa chạy trong RAM nhưng lỗi với Redis | Backend không chuyển đổi/serialize được kiểu khóa custom | Xem cấu hình key serializer/converter, dùng kiểu khóa hỗ trợ và kiểm thử tích hợp. |
| `KeyGenerator` không được gọi | Chưa bật `@EnableCaching`, method không qua proxy, bean không do Spring tạo | Gọi từ bean khác; kiểm tra cấu hình caching và các public method được chặn. |
| Xóa nhầm toàn bộ mục | Dùng `allEntries=true` khi chỉ muốn xóa một key | Thay bằng eviction theo khóa; chỉ clear toàn cache khi đó là yêu cầu. |

Khi debug, chỉ log dạng key an toàn/đã ẩn nhạy cảm. Log hash không đủ để kết luận hai key bằng nhau; nên kiểm tra trực tiếp cấu trúc và `equals()` trong một bài test.

## 10. Tự kiểm tra kiến thức

**Tình huống A.** Hai phương thức cùng `@Cacheable("products")`: `findBySku(String sku)` và `findById(String id)`. Khi cả hai nhận chuỗi `"42"`, có rủi ro gì?  
**Đáp án:** mặc định cả hai có khóa `"42"` trong cùng cache nên có thể dùng nhầm kết quả. Dùng hai tên cache khác nhau hoặc một chiến lược khóa phân biệt ngữ nghĩa phương thức; nếu cần evict, bảo đảm evict tạo lại đúng định danh đó.

**Tình huống B.** `renderReport(String tenant, String reportId, Locale locale)` cho kết quả khác theo locale. Có thể chỉ lấy `reportId` làm khóa không?  
**Đáp án:** không, trừ khi business contract bảo đảm `tenant` và `locale` không ảnh hưởng kết quả. Thông thường cần đủ `(tenant, reportId, locale)` và chính sách chuẩn hóa locale rõ ràng.

**Tình huống C.** Dùng một generator thêm tên method vào khóa cho cả `find(a,b)` và `evict(a,b)`. Evict có xóa mục của find không?  
**Đáp án:** thường không, vì tên hai method khác nhau. Hãy dùng một định danh thực thể chung hoặc một cơ chế ánh xạ riêng được thiết kế và kiểm thử nhất quán.

## Tài liệu tham khảo

- Spring Framework — Cache annotations, default/custom key generation, `@CacheConfig`, proxy semantics: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Boot — Caching và cache providers: https://docs.spring.io/spring-boot/reference/io/caching.html

**Ghi nhớ:** `KeyGenerator` biến `(đích, phương thức, đối số)` thành một khóa cache. Hãy bắt đầu từ định danh **kết quả nghiệp vụ**, rồi bảo đảm mọi operation liên quan tạo ra đúng cùng khóa khi chúng nhắm cùng một mục.