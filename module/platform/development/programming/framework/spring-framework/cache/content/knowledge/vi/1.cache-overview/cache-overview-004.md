# Vì sao Spring Cache là lớp trừu tượng chứ không phải kho lưu trữ

## Mục tiêu

Sau bài này, bạn sẽ hiểu Spring Cache thực sự xử lý những gì trong một lời gọi `@Cacheable`, nơi nào giữ dữ liệu cache, vì sao có thể thay đổi provider mà ít đổi mã nghiệp vụ, và các trách nhiệm về TTL, consistency, concurrency, phân tán mà ứng dụng vẫn phải thiết kế.

## 1. Câu trả lời ngắn gọn nhưng chính xác

**Spring Cache là lớp trừu tượng (abstraction) dành cho hành vi cache ở mức phương thức Java.** Nó cung cấp hợp đồng và cơ chế điều phối để tái sử dụng kết quả tính toán: xác định phương thức nào có cache, tạo key từ tham số, tìm kết quả đã lưu, bỏ qua thân phương thức nếu hit, thực thi rồi đưa kết quả vào cache khi miss.

**Kho lưu trữ thực tế (backing store/provider)** là thành phần giữ key/value ở RAM, trong một tiến trình hoặc ở dịch vụ từ xa; nó quyết định eviction, thời gian tồn tại, serialization, dung lượng, tính bền vững và khả năng chia sẻ giữa các instance.

Điểm dễ nhầm: Spring Framework cũng có triển khai lưu trữ đơn giản `ConcurrentMapCache`/`ConcurrentMapCacheManager`. Khi cấu hình manager này, cache *thực sự* chứa dữ liệu trong map của JVM. Nhưng điều đó chỉ chứng minh Spring cung cấp **một implementation** của hợp đồng, không có nghĩa bản thân các annotation hay giao diện Spring Cache là cơ sở dữ liệu.

~~~text
Chính sách: @Cacheable -> CacheInterceptor -> Cache / CacheManager (hợp đồng)
                                                  |
                                                  v
Hiện thực: ConcurrentMap, Caffeine, Redis, JCache provider... (nơi giữ dữ liệu)
~~~

Ví dụ minh họa chính sách:

~~~java
@Cacheable(cacheNames = "prices", key = "#p0")
public Price findPrice(String sku) {
    return repository.loadPrice(sku);
}
~~~

Annotation mô tả rằng kết quả `findPrice(sku)` có thể tái sử dụng theo key `sku` trong cache tên `prices`. Nó **không cho biết** dữ liệu nằm tại Redis hay RAM, không chỉ định TTL, và không tạo storage vĩnh viễn. `Price` và `repository` là kiểu/phụ thuộc nghiệp vụ giả định: snippet trên dùng để giải thích, chưa phải chương trình độc lập.

### Ranh giới trách nhiệm

| Câu hỏi | Spring Cache abstraction | Provider / ứng dụng |
| --- | --- | --- |
| Cache phương thức nào? | Annotation như `@Cacheable`, `@CacheEvict` | Không tự quyết định |
| Key tạo từ tham số nào? | SpEL `key` hoặc `KeyGenerator` | Nhận key đã tạo/chuyển đổi |
| Gọi các thao tác nào? | Giao diện `Cache`: get/put/evict/clear | Thực hiện trên storage |
| Vùng cache tên gì? | `CacheManager`, `CacheResolver` | Ánh xạ tới vùng/bộ nhớ thực |
| RAM hay cache phân tán? | Không ràng buộc | Implementation quyết định |
| TTL, maximum size, LRU, replication? | Không cam kết chung | Provider/config riêng |
| Dữ liệu database có thay đổi chưa? | Không tự theo dõi | Nghiệp vụ thiết kế invalidation |
| Dữ liệu nào là nguồn chuẩn? | Không thay thế nguồn chuẩn | Database / service / nguồn nghiệp vụ |

**Cache không phải source of truth.** Nếu mọi entry biến mất, hệ thống hợp lệ cần nạp/tính lại từ nguồn dữ liệu gốc. Lưu duy nhất thông tin quan trọng vào cache làm mất khả năng phục hồi khi cache bị xóa hay hết hạn.

## 2. Thành phần của abstraction và vai trò mỗi bên

- `org.springframework.cache.Cache`: giao diện biểu diễn một cache có tên, hỗ trợ lấy, ghi, xóa một entry hoặc xóa toàn bộ. Nó không chỉ định map, kết nối mạng, eviction hay độ bền.
- `org.springframework.cache.CacheManager`: trả về một đối tượng `Cache` theo tên, ví dụ `cacheManager.getCache("prices")`. Một manager có thể quản lý nhiều cache; tên `prices` không mặc định là một bảng database hoặc Redis server riêng.
- `CacheResolver`: tùy chọn định tuyến operation tới các cache thích hợp, thay vì luôn giải quyết bằng manager mặc định.
- `KeyGenerator`: tạo key mặc định hoặc tùy biến. Annotation có thể ghi SpEL `key = "#p0"` để chọn tham số đầu tiên.
- `CacheInterceptor` và Spring AOP: áp dụng chính sách cho lời gọi đi qua Spring proxy. Interceptor không cần biết Redis lưu byte hay Caffeine lưu object.
- Adapter/provider thực tế: `ConcurrentMapCacheManager` (bộ nhớ JVM), `CaffeineCacheManager` (cache bộ nhớ có chính sách eviction), `RedisCacheManager` của Spring Data Redis (Redis ngoài JVM), `JCacheCacheManager` (JSR-107).

~~~text
Caller -> Spring proxy / CacheInterceptor
            |
            +-- chính sách annotation / điều kiện / cache key
            |
            +-- CacheManager hoặc CacheResolver
            |       |
            |       +-- Cache interface -> provider -> bộ nhớ/Redis/...
            |
            +-- cache miss -> phương thức gốc -> repository/API/tính toán
                                            |
                                            +-- kết quả có thể được put vào cache
~~~

Vì mã nghiệp vụ phụ thuộc vào **hợp đồng**, ứng dụng có thể chọn backend qua cấu hình. Tuy vậy, khác biệt provider về TTL, serialization, chia sẻ giữa node và độ trễ vẫn có ý nghĩa vận hành.

## 3. Luồng cache hit và miss thực sự

Giả sử một Spring bean có `@Cacheable(cacheNames = "prices", key = "#p0")`, được bean khác gọi **qua Spring proxy**:

1. Interceptor đọc metadata annotation và tính `condition` nếu có. Nếu condition sai, lời gọi không được cache.
2. Spring giải quyết cache `prices` thông qua resolver/manager, tạo key cho lời gọi.
3. **Hit:** provider trả entry cho key; interceptor trả giá trị đã lưu và **không chạy thân phương thức**.
4. **Miss:** interceptor chạy phương thức gốc. Khi thành công, nếu `unless` không cấm ghi, kết quả được lưu qua giao diện cache và trả về.
5. Lần gọi cùng key sau đó có thể hit, miễn provider còn giữ entry và hỗ trợ kiểu dữ liệu tương ứng.

Pseudocode mang tính khái niệm, không phải code nguồn Spring:

~~~text
if condition không thỏa:
    return invokeTarget()
cache = resolve(cacheName)
key = generateKey(args)
if cache chứa key:
    return cache.get(key)
result = invokeTarget()
if unless không veto:
    cache.put(key, result)
return result
~~~

Spring Cache **không tự khóa toàn bộ lần miss**. Nếu hai thread miss cùng key đồng thời, cả hai có thể chạy phương thức tốn kém. `@Cacheable(sync = true)` là tín hiệu đề nghị provider phối hợp một lần tải cho một key; hiệu lực phụ thuộc provider và có các giới hạn (không dùng `unless`, chỉ một cache). Nó không phải distributed lock cho nghiệp vụ.

Hit cũng bỏ qua mọi side effect trong body: logging, gọi HTTP, ghi database, trừ tiền, gửi email... Vì thế cache phù hợp với phép tính/đọc dữ liệu mà kết quả lặp lại theo key là hợp lý; không gắn bừa lên phương thức bắt buộc thực thi ở mỗi lần gọi.

## 4. Ví dụ runnable với Java 17 và Spring Framework

Ví dụ tối giản dùng Spring Framework 6.2.19, Java 17, Maven và `ConcurrentMapCacheManager`; không cần Spring Boot, Redis hoặc database. “Nguồn chậm” được mô phỏng bằng một bộ đếm để nhìn thấy cache hit/miss.

Cấu trúc:

~~~text
spring-cache-demo/
├── pom.xml
└── src/main/java/demo/Demo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cache-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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

File `src/main/java/demo/Demo.java`:

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class Demo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            var service = context.getBean(PriceService.class);

            System.out.println("Lần 1: " + service.getPrice("A"));
            System.out.println("Lần 2: " + service.getPrice("A"));
            service.invalidate("A");
            System.out.println("Sau xóa: " + service.getPrice("A"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("prices");
        }

        @Bean
        public PriceService priceService() {
            return new PriceService();
        }
    }

    public static class PriceService {
        private int loads;

        @Cacheable(cacheNames = "prices", key = "#p0")
        public int getPrice(String sku) {
            System.out.println("Nạp từ nguồn chậm #" + ++loads + ": " + sku);
            return 100;
        }

        @CacheEvict(cacheNames = "prices", key = "#p0")
        public void invalidate(String sku) {
            System.out.println("Xóa khóa " + sku);
        }
    }
}
~~~

Chạy tại thư mục `spring-cache-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.Demo
~~~

Phần stdout từ chương trình:

~~~text
Nạp từ nguồn chậm #1: A
Lần 1: 100
Lần 2: 100
Xóa khóa A
Nạp từ nguồn chậm #2: A
Sau xóa: 100
~~~

**Diễn giải:** lần đầu chưa có key `"A"` nên body chạy; lần thứ hai hit và body bị bỏ qua; `invalidate("A")` xóa entry; lần ba phải nạp lại. `@EnableCaching` kích hoạt hạ tầng annotation. `getBean(PriceService.class)` đảm bảo lời gọi đi qua Spring bean/proxy, trong khi `new PriceService()` bên ngoài container sẽ không được intercept.

Map lưu entry thuộc implementation `ConcurrentMapCache` do manager quản lý. Điều đó chính là minh chứng: annotation và interceptor mô tả **hành vi**, provider lưu **dữ liệu**. Ví dụ này không chứa TTL: entry tồn tại cho đến khi bị xóa/clear hoặc context kết thúc (trừ thay đổi do ứng dụng).

## 5. Đổi cache backend: điều gì giữ nguyên và điều gì thay đổi?

Vẫn là `@Cacheable(cacheNames = "prices", key = "#p0")` ở service, nhưng manager khác nhau tạo ra tính chất khác nhau:

| Backend | Nơi giữ entry | Thuộc tính cần cân nhắc |
| --- | --- | --- |
| `ConcurrentMapCacheManager` | Map trong một JVM | Dễ dùng, không có giới hạn dung lượng/TTL chuyên dụng; mỗi instance giữ bản riêng |
| Caffeine | RAM mỗi JVM | Có thể cấu hình max size, expire-after-write/access, thống kê hit/miss |
| Redis | Dịch vụ ngoài JVM | Cache chia sẻ giữa instance, kết nối/serializer/network, TTL và eviction cấu hình |
| JCache provider | Tùy implementation JSR-107 | Chức năng thực tùy provider, Spring dùng adapter JCache |

Ví dụ **chỉ thay cấu hình manager** bằng Caffeine (snippet cần thêm dependency `spring-context-support` và `com.github.ben-manes.caffeine:caffeine`):

~~~java
@Bean
public CacheManager cacheManager() {
    var manager = new org.springframework.cache.caffeine.CaffeineCacheManager("prices");
    manager.setCaffeine(
        com.github.benmanes.caffeine.cache.Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(java.time.Duration.ofMinutes(5))
    );
    return manager;
}
~~~

Giữ các method ở `PriceService` như cũ và **thay thế**, không tạo hai bean manager cùng mục đích. TTL năm phút ở đây là tính năng của Caffeine, **không phải một thuộc tính TTL chung của `@Cacheable`**. Nếu chọn Redis, ứng dụng vẫn phải cấu hình kết nối, định dạng value, key prefix, TTL, lỗi mạng và vận hành; “không đổi annotation” không đồng nghĩa “hành vi runtime giống hệt”.

Trong Spring Boot, `spring-boot-starter-cache` hỗ trợ dependency; bật `@EnableCaching` rồi Boot có thể tự cấu hình manager theo classpath/cấu hình nếu bạn không tự cung cấp bean. Boot giúp cấu hình provider, nhưng Spring Cache abstraction không vì vậy biến thành một database.

## 6. Các annotation đều nói về policy

- **`@Cacheable`:** đọc cache trước; hit trả dữ liệu, miss gọi body và có thể ghi kết quả.
- **`@CachePut`:** luôn chạy body rồi ghi **giá trị trả về** vào cache khi điều kiện hợp lệ; không bỏ qua body vì cache hit.
- **`@CacheEvict`:** yêu cầu xóa một key hoặc toàn bộ vùng qua `allEntries = true`; mặc định xóa sau lời gọi thành công, hoặc trước với `beforeInvocation = true`.
- **`@Caching`:** nhóm nhiều thao tác cache cho một phương thức.
- **`@CacheConfig`:** gom thiết lập mặc định như cache name tại cấp class.
- **`@EnableCaching`:** bật cơ chế xử lý annotation (proxy mode thường là mặc định).

Ví dụ dùng điều kiện (snippet nghiệp vụ, cần `Price` và `repository` thực tế):

~~~java
@Cacheable(
    cacheNames = "prices",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
public Price load(String sku) {
    return repository.findPrice(sku);
}
~~~

`condition` đánh giá **trước** khi gọi phương thức, `unless` đánh giá **sau** và có thể ngăn lưu kết quả. `#p0` chỉ tham số đầu tiên, tránh phụ thuộc tên parameter trong bytecode. `#result` biểu diễn kết quả mà biểu thức hậu xử lý được phép quan sát.

Key mặc định nếu không ghi `key`: không tham số → `SimpleKey.EMPTY`; một tham số → chính tham số đó; nhiều tham số → `SimpleKey` chứa các tham số. Vì vậy key phải ổn định, `equals/hashCode` hợp lý và tránh va chạm giữa các operation cùng dùng một cache name.

Không nên đặt `@Cacheable` và `@CachePut` đồng thời vô điều kiện trên cùng một method: một cái có thể bỏ qua body, một cái bắt buộc chạy body. Tách rõ đường đọc và đường cập nhật giúp tránh ngữ nghĩa mâu thuẫn.

## 7. Những cam kết Spring Cache không tự đưa ra

### 7.1. TTL, eviction theo bộ nhớ và persistence

Không có `@Cacheable(ttl = "...")` trong API thông thường. `Cache.evict(key)` là yêu cầu **xóa chủ động**, còn “tự hết hạn sau 5 phút”, “chỉ 10.000 entry”, “LRU” hay ghi xuống đĩa là chính sách của provider. Không cấu hình TTL thì không được tự giả định entry sẽ hết hạn an toàn.

### 7.2. Cache giữa nhiều instance

Hai pod JVM cùng cấu hình `ConcurrentMapCacheManager` có **hai bản map**. Pod A evict key không tự xóa bản B. Dùng Redis giúp cùng nhìn vào một nơi lưu, nhưng vẫn phải thiết kế namespace, invalidation, TTL, bảo mật và phản ứng với mạng chậm. Cache shared cũng không làm kết quả database tự nhất quán.

### 7.3. Đồng bộ với nguồn dữ liệu

Nếu database đổi giá 100 thành 120, cache có thể vẫn trả 100 vì Spring không biết ai đã sửa database ngoài luồng. Cần chiến lược write-then-evict, write-through phù hợp, hoặc TTL chấp nhận độ trễ.

Ví dụ quan hệ đọc/ghi (minh họa, thiếu domain/repository cụ thể):

~~~java
@Cacheable(cacheNames = "prices", key = "#p0")
public Price read(String sku) {
    return repository.findPrice(sku);
}

@CacheEvict(cacheNames = "prices", key = "#p0")
public void update(String sku, Price newPrice) {
    repository.savePrice(sku, newPrice);
}
~~~

Ở đây lệnh ghi dữ liệu gốc chạy rồi mới evict theo cấu hình mặc định. Khi có transaction, **thời điểm commit** vẫn cần được xem xét: eviction có thể diễn ra trước commit thực tế, rồi một caller khác nạp lại giá trị cũ. Có thể cần cơ chế sau commit hoặc manager nhận biết transaction. Không coi cache và database mặc nhiên có atomic transaction chung.

### 7.4. Đồng thời, lỗi và null

Nhiều thread có thể cùng miss, tính toán lặp và ghi chồng. `sync = true` còn phụ thuộc hỗ trợ của provider; không hứa exactly-once hoặc khóa xuyên dịch vụ. Cache backend có thể lỗi hoặc timeout: ứng dụng cần chiến lược fallback và quan sát việc tải lại dữ liệu gốc.

Giá trị null, `Optional.empty()` và cách serialize object có khác biệt giữa provider; Spring có hỗ trợ biểu diễn kết quả null ở một số adapter, nhưng không nên giả định mọi store xử lý giống nhau. Exception từ phương thức gốc không phải một kết quả thành công mặc định được lưu vào cache.

### 7.5. Key và bảo mật

Key phải bao gồm đủ yếu tố quyết định kết quả: sản phẩm, ngôn ngữ, tenant, mức giá, quyền truy cập… tùy bài toán. Chỉ key theo `productId` khi dữ liệu thực tế phụ thuộc `tenantId` có thể trả nhầm kết quả của tenant khác. Cần kiểm soát key namespace, dữ liệu nhạy cảm và tránh log giá trị không phù hợp.

## 8. Bốn lỗi phổ biến

**(1) “Gắn `@Cacheable` là Spring tự lưu Redis.”** Sai: annotation không chọn Redis; phải có hạ tầng annotation và manager/provider phù hợp. Manager in-memory thì lưu in-memory.

**(2) “Gọi `this.cachedMethod()` cũng được intercept.”** Với Spring AOP **proxy mode**, lời gọi nội bộ trong cùng object không đi qua proxy nên advice cache không chạy. Tổ chức lời gọi đi qua Spring bean proxy (ví dụ tách service) hoặc xem xét cơ chế weave khác khi cần. Method không đủ điều kiện được proxy cũng có thể bỏ qua advice.

**(3) “Cache hit vẫn chạy mọi logic trong method.”** Sai: hit sẽ bỏ qua body. Không cache một phương thức có side effect bắt buộc như trừ tiền, gửi email, tạo đơn hàng, hoặc kiểm tra quyền cập nhật theo trạng thái thay đổi từng giây.

**(4) “Đổi ConcurrentMap sang Redis sẽ hoàn toàn giống nhau.”** Sai: latency, chia sẻ giữa instance, TTL, serialization, null handling, failure mode và eviction là khác biệt thực. Abstraction chỉ giữ cách **gọi**, không san bằng các đặc tính backend.

## 9. Cách tự kiểm tra trong một ứng dụng thật

1. Xác định có `@EnableCaching`/cấu hình tương đương không và lời gọi tới method có đi qua **Spring proxy** không.
2. Tìm `CacheManager` hoặc `CacheResolver` thực tế, kiểm tra dependency và cấu hình Boot; ghi rõ backend là gì.
3. Xem từng annotation: cache name, key, condition/unless, invalidation, allEntries, đường ghi dữ liệu gốc.
4. Gọi một key hai lần và quan sát số lần method gốc chạy; thử key mới và thử evict rồi gọi lại. Không đánh giá hiệu quả chỉ từ việc annotation có mặt.
5. Kiểm tra nhu cầu nhiều instance, TTL, giới hạn bộ nhớ, dữ liệu stale, lỗi backend, metric hit/miss và cơ chế kiểm tra tính đúng đắn theo nghiệp vụ.

## 10. Câu hỏi ôn tập

**Tại sao Spring Cache không phải kho lưu trữ?** Vì nó định nghĩa API/annotation/interceptor cho hành vi tái sử dụng kết quả phương thức; phần giữ key/value do implementation cung cấp.

**Nếu có hai JVM dùng `ConcurrentMapCacheManager`, một JVM xóa key thì JVM còn lại có mất key không?** Không, map là cục bộ từng tiến trình.

**Đổi manager sang Redis có phải viết lại `@Cacheable`?** Thường không; policy ở service có thể giữ nguyên, nhưng phải cấu hình Redis và đánh giá TTL, serialization, độ trễ và lỗi kết nối.

**Vì sao database đã cập nhật mà method vẫn trả giá trị cũ?** Vì entry cache chưa được invalidated/hết hạn. Spring Cache không theo dõi mọi cập nhật database.

**Vì sao gọi hai lần vẫn thực thi body cả hai?** Kiểm tra proxy/self-invocation, key có thực sự giống nhau không, `condition/unless`, sự tồn tại của cache, TTL và provider.

## Kết luận

**Spring Cache trả lời “khi nào, với key nào, nên tái dùng kết quả phương thức?”; cache provider trả lời “dữ liệu ấy được giữ ở đâu, bao lâu, chia sẻ và vận hành ra sao?”** Sự tách biệt này cho phép áp dụng cùng một mô hình khai báo với nhiều công nghệ lưu trữ, nhưng trách nhiệm đúng đắn dữ liệu, invalidation và lựa chọn backend vẫn thuộc thiết kế ứng dụng.

## Tham khảo chính thức

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Configuring the Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
