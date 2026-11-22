# @CacheEvict: beforeInvocation=false và xóa sau lời gọi thành công

## 1. Mục tiêu

Trong Spring Framework Cache, `@CacheEvict` đánh dấu một phương thức làm vô hiệu hóa dữ liệu đã lưu. Thuộc tính `beforeInvocation` quyết định **thời điểm kích hoạt eviction so với lời gọi mà caching advice chặn**. Giá trị mặc định là `false`: yêu cầu xóa cache được thực hiện **sau khi target method hoàn tất bình thường**, không có exception thoát ra.

~~~java
@CacheEvict(cacheNames = "products", key = "#p0", beforeInvocation = false)
public void rename(long id, String newName) {
    repository.rename(id, newName);
}
~~~

Ví dụ trên là snippet cần một Spring bean và repository thực tế. Khi `rename` hoàn thành bình thường, interceptor xử lý eviction cho key tham số đầu tiên. Khi method ném exception ra ngoài, eviction sau lời gọi của annotation không chạy.

Có ba khái niệm phải tách bạch:

- **Thành công của method invocation**: method được advice quan sát đã return bình thường. Trả `false`, `null` hoặc trạng thái nghiệp vụ `FAILED` vẫn có thể là return bình thường.
- **Thành công của nghiệp vụ**: cơ sở dữ liệu hoặc domain thực sự được cập nhật như dự kiến. Spring không tự suy ra điều này từ trạng thái trong result.
- **Thành công của transaction/commit**: dữ liệu đã commit và có thể được các reader quan sát. `beforeInvocation=false` không tự bảo đảm eviction diễn ra sau DB commit.

Mục tiêu bài học là hiểu chính xác hành vi khi có exception, cách dùng `condition`/`#result`, key hoặc `allEntries`, tác động tới transaction và concurrency, và cách kiểm thử bằng ví dụ Java 17 có thể chạy.

## 2. CacheInterceptor xử lý eviction lúc nào?

Khi ứng dụng có `@EnableCaching` và bean được gọi qua Spring AOP proxy, `CacheInterceptor` nhận lời gọi và dùng `CacheAspectSupport` để điều phối các cache operations được tìm từ annotation metadata. Với `beforeInvocation=false`, luồng đồng bộ đơn giản:

~~~mermaid
flowchart TD
    A[Caller gọi Spring bean qua proxy] --> B[CacheInterceptor]
    B --> C[Thực thi target method]
    C --> D{Kết thúc thế nào?}
    D -- Exception thoát ra --> E[Propagate exception; không after-evict]
    D -- Return bình thường --> F[Đánh giá condition sau lời gọi]
    F --> G{condition true hoặc để trống?}
    G -- Không --> H[Không evict; trả result]
    G -- Có --> I[Resolve cache và key hoặc allEntries]
    I --> J[Cache.evict hoặc Cache.clear]
    J --> K[Trả result]
~~~

Sơ đồ mô tả **một operation đồng bộ**, chưa bao gồm future/reactive, nhiều annotation, transaction-aware decorator hoặc lỗi provider. Một phép xóa được yêu cầu sau khi method return bình thường; thời điểm xóa vật lý có thể được backend/decorator thực hiện muộn hơn.

`CacheInterceptor` không trực tiếp thay đổi database. Nó điều phối `Cache.evict(key)` hoặc `Cache.clear()` sau khi business method hoàn tất. `@CacheEvict` chỉ invalidation, không tính/ghi giá trị mới vào cache. Nếu lần đọc kế tiếp qua `@Cacheable`, cache miss thường dẫn đến đọc lại dữ liệu nguồn.

## 3. Khi nào evict xảy ra và khi nào không?

| Tình huống của method | Eviction với `beforeInvocation=false` | Giải thích |
| --- | --- | --- |
| `void` return bình thường | Có, nếu condition cho phép | Không cần return value |
| Trả object hoặc chuỗi | Có, nếu condition cho phép | Invocation bình thường |
| Trả `false` | Theo mặc định vẫn có | `false` không phải exception |
| Trả `null` | Theo mặc định vẫn có | Không tự coi null là thất bại |
| Trả status `FAILED` mà không ném lỗi | Theo mặc định vẫn có | Spring không hiểu status nghiệp vụ |
| Ném unchecked exception | Không | Target method không hoàn tất bình thường |
| Ném checked exception | Không | Exception thoát khỏi invocation |
| Bắt lỗi bên trong rồi return | Có thể có | Advice chỉ nhìn thấy return bình thường |
| Thay đổi dữ liệu rồi ném exception | Không | Nguy cơ stale cache nếu dữ liệu đã thay đổi bền vững |
| Return bình thường nhưng `condition` false | Không | Operation bị loại bởi điều kiện |
| Gọi nội bộ không qua proxy | Không | Cache advice không được gọi |

**Đáng chú ý:** nếu business method thành công nhưng `Cache.evict` bị lỗi, caller vẫn có thể nhận exception từ tầng cache (theo `CacheErrorHandler` mặc định). Phải tách lỗi target method và lỗi phát sinh **sau** method khi điều phối caching.

## 4. Khác biệt giữa beforeInvocation=false và true

| Đặc điểm | `beforeInvocation=false` (mặc định) | `beforeInvocation=true` |
| --- | --- | --- |
| Advice yêu cầu xóa | Sau khi target return bình thường | Trước khi gọi target |
| Target ném exception | Không xóa theo operation đó | Đã yêu cầu xóa trước |
| Có `#result` cho SpEL `key`/`condition`? | Có | Không, vì chưa có kết quả |
| Method trả false bình thường | Vẫn có thể xóa | Đã yêu cầu xóa trước khi biết kết quả |
| Rủi ro | Không xóa khi đã có side effect rồi exception; transaction commit có thể đến sau | Có thể tạo cache miss và reload dữ liệu cũ trong khi update chưa xong |
| Mục đích thường gặp | Gắn invalidation với lệnh cập nhật hoàn thành bình thường | Muốn xóa bất kể outcome của lệnh cập nhật |

Cả hai đều phụ thuộc khả năng của cache backend. Với transaction-aware cache, hành động vật lý có thể được hoãn; `beforeInvocation` xác định mốc **kích hoạt theo advice**, không phải mọi chi tiết đồng bộ của provider.

## 5. Xóa một key: phải đối xứng với đường đọc

Một hệ thống cache-aside thường dùng `@Cacheable` để cache truy vấn và `@CacheEvict` để xóa entry sau cập nhật:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(long id) {
    return repository.find(id);
}

@CacheEvict(cacheNames = "products", key = "#p0",
            beforeInvocation = false)
public void update(long id, ProductUpdate changes) {
    repository.update(id, changes);
}
~~~

Đây là snippet trong service, chưa phải file Java độc lập. Khi `find(42)` đã cache sản phẩm cũ, `update(42, changes)` return bình thường sẽ evict key `42` trong cache `products`. Lần `find(42)` tiếp theo phải miss và nạp dữ liệu mới.

**Những sai sót quan trọng:**

- Đường đọc dùng `tenantId:productId`, đường evict chỉ dùng `productId`, khiến entry cũ không bị xóa.
- Đường đọc dùng cache `products`, đường xóa dùng cache `product`, hai nơi khác nhau.
- Đường đọc tạo key bằng custom `KeyGenerator`, đường xóa tạo key bằng SpEL khác quy tắc chuẩn hóa.
- Key thiếu tenant, locale, status, permission scope hoặc query filter ảnh hưởng kết quả, có thể trả dữ liệu sai hoặc xóa nhầm phạm vi.
- Tên parameter `#id` không có trong metadata biên dịch: `#p0` hoặc `#a0` có thể thuận tiện hơn khi không chắc có cờ `-parameters`.

`key` và `keyGenerator` **loại trừ nhau** trong cùng operation. `cacheManager` và `cacheResolver` cũng là hai cấu hình lựa chọn cache không dùng đồng thời. Cần test exact key và cache name giữa GET/UPDATE/DELETE.

## 6. condition và #result sau invocation

`@CacheEvict` có `condition` nhưng **không có `unless`**. Với `beforeInvocation=false`, `condition` và `key` có thể tham chiếu `#result`, vì method đã hoàn tất.

Ví dụ: method trả số dòng cập nhật, chỉ evict khi thực sự thay đổi hàng:

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    condition = "#result > 0",
    beforeInvocation = false
)
public int updatePrice(long id, long newPrice) {
    return repository.updatePrice(id, newPrice);
}
~~~

Nếu method trả `0` (không cập nhật), không evict; trả `1` thì evict. Đây là snippet giả định repository trả số dòng thay đổi.

Một ví dụ khác với boolean:

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    condition = "#result == true",
    beforeInvocation = false
)
public boolean changeStatus(long id, String status) {
    return repository.changeStatus(id, status);
}
~~~

Nếu method trả `false` bình thường, `condition` không thỏa nên không evict; không có `condition` thì mặc định vẫn evict. Nếu method ném exception, operation sau lời gọi không được thực thi.

Khi method trả `Optional<T>`, `#result` trong ngữ cảnh hỗ trợ của Spring Cache tham chiếu phần tử bên trong hoặc `null` nếu `Optional.empty()`. Cần kiểm tra null khi expression phụ thuộc result. Thường an toàn hơn khi tính key từ input ổn định, dùng `#result` để quyết định condition:

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    condition = "#result != null",
    beforeInvocation = false
)
public Optional<Product> tryUpdate(long id, String value) {
    return repository.tryUpdate(id, value);
}
~~~

Đây là snippet giả định method trả `Optional<Product>`. Đừng mặc định mọi result wrapper tùy biến được unwrap như Optional.

Với `beforeInvocation=true`, không sử dụng `#result` trong `key`/`condition`: method chưa có kết quả tại lúc evict.

## 7. allEntries=true: xóa toàn cache sau thành công

Nếu một batch thay đổi nhiều key và khó xác định key bị ảnh hưởng:

~~~java
@CacheEvict(cacheNames = "catalog",
            allEntries = true,
            beforeInvocation = false)
public void rebuildCatalog() {
    repository.rebuild();
}
~~~

Sau khi `rebuildCatalog()` return bình thường, Spring yêu cầu clear **toàn bộ cache `catalog`**. Nếu method ném exception, operation clear sau lời gọi không chạy.

**Không khai báo `key` khi `allEntries=true`**. Đây là hai cơ chế loại trừ nhau: xóa một entry theo key so với xóa toàn bộ vùng cache. Với cache nhiều tenant hoặc nhiều node, full clear có thể gây cache stampede và tăng truy cập database. Chỉ chọn khi thật cần.

Đối với nhiều cache với key khác nhau, có thể dùng `@Caching(evict={...})` để khai báo riêng, nhưng nhiều operation không tạo một transaction phân tán giữa các cache provider. Khi một provider lỗi, có thể xảy ra partial invalidation.

## 8. Ví dụ runnable với Java 17, Maven và Spring Framework

Ví dụ này mô tả ba nhánh: lần đọc đầu tiên cache miss, cập nhật ném exception giữ entry cũ, cập nhật thành công xóa entry và lần đọc kế tiếp nạp dữ liệu mới. Sử dụng `ConcurrentMapCacheManager` và store trong RAM để loại bỏ phụ thuộc database thật.

**Tệp `pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>evict-after-success</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.18</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.2</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Tệp `src/main/java/demo/EvictAfterSuccessDemo.java`**

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class EvictAfterSuccessDemo {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    Store store() {
        return new Store();
    }

    @Bean
    ProductService productService(Store store) {
        return new ProductService(store);
    }

    public static class Store {
        private final Map<Long, String> values =
                new ConcurrentHashMap<>(Map.of(7L, "v1"));

        public String get(long id) {
            return values.get(id);
        }

        public void put(long id, String value) {
            values.put(id, value);
        }
    }

    public static class ProductService {
        private final Store store;
        private int loads;

        public ProductService(Store store) {
            this.store = store;
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public String find(long id) {
            System.out.println("read source #" + (++loads));
            return store.get(id);
        }

        @CacheEvict(
            cacheNames = "products",
            key = "#p0",
            beforeInvocation = false
        )
        public void update(long id, String value, boolean fail) {
            System.out.println("update begin: " + value);
            if (fail) {
                throw new IllegalStateException("update rejected");
            }
            store.put(id, value);
            System.out.println("update stored: " + value);
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                EvictAfterSuccessDemo.class)) {
            ProductService service = context.getBean(ProductService.class);

            System.out.println("first = " + service.find(7));
            System.out.println("cached = " + service.find(7));

            try {
                service.update(7, "v2", true);
            } catch (IllegalStateException ex) {
                System.out.println("failed = " + ex.getMessage());
            }
            System.out.println("after failure = " + service.find(7));

            service.update(7, "v2", false);
            System.out.println("after success = " + service.find(7));
            System.out.println("again = " + service.find(7));
        }
    }
}
~~~

**Lệnh chạy** tại thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.EvictAfterSuccessDemo
~~~

**Output do chương trình in theo đúng thứ tự**, bỏ qua log Maven/framework:

~~~text
read source #1
first = v1
cached = v1
update begin: v2
failed = update rejected
after failure = v1
update begin: v2
update stored: v2
read source #2
after success = v2
again = v2
~~~

Giải thích:

1. `find(7)` miss lần đầu, in `read source #1` và cache `v1`. Lần thứ hai hit, không gọi store.
2. `update(7, "v2", true)` ném exception **trước** khi thay đổi store. Eviction không chạy; `find(7)` kế tiếp vẫn hit `v1`.
3. `update(7, "v2", false)` cập nhật store thành `v2`, return bình thường; Spring evict key `7`.
4. `find(7)` tiếp theo miss, in `read source #2`, tải `v2` rồi cache. Lần đọc sau trả `v2` từ cache.

Đây là một ứng dụng chạy độc lập bằng Maven, sử dụng Spring bean từ `ApplicationContext` để lời gọi đi qua proxy. Store giả lập **không có transaction rollback** và ví dụ lỗi cố tình xảy ra trước cập nhật; không suy từ đó rằng mọi lỗi ứng dụng thật đều tự rollback dữ liệu.

## 9. Exception sau khi dữ liệu đã thay đổi

Với `beforeInvocation=false`, nếu method ném exception thì Spring không chạy eviction của annotation. Điều này có thể tạo dữ liệu stale nếu nguồn đã bị thay đổi bền vững trước lỗi:

~~~java
@CacheEvict(cacheNames = "products", key = "#p0",
            beforeInvocation = false)
public void updateAndNotify(long id, String name) {
    repository.update(id, name);  // có thể đã commit
    notifier.notify(id);          // có thể ném exception
}
~~~

Snippet giả định repository/notifier có sẵn. Nếu update đã commit rồi notifier ném lỗi, cache có thể vẫn chứa sản phẩm cũ. Cần transaction rollback thật, thiết kế outbox/event hoặc invalidation độc lập khi mutation đã bền vững.

Nếu method **bắt** exception rồi return bình thường, eviction lại có thể diễn ra. Vì vậy, xác định chính sách trên kết quả cuối cùng mà proxy nhìn thấy, không dựa vào việc “đã từng có lỗi ở sâu bên trong”.

## 10. after invocation không tự đồng nghĩa after commit

Khi kết hợp `@Transactional` và `@CacheEvict`:

~~~java
@Transactional
@CacheEvict(cacheNames = "products", key = "#p0",
            beforeInvocation = false)
public void changePrice(long id, long newPrice) {
    repository.changePrice(id, newPrice);
}
~~~

Đây là snippet, cần transaction manager và repository thật. Do thứ tự transaction advice/cache advice và có thể có outer transaction, eviction có thể được yêu cầu **trước khi DB commit**. Nếu reader khác miss đúng lúc đó, nó có thể đọc bản cũ rồi ghi lại vào cache; sau commit bản cache vẫn stale. Một outer transaction cũng có thể rollback **sau** khi annotated method đã return.

Nếu cần eviction sau commit, xem xét `TransactionAwareCacheManagerProxy` hoặc `TransactionAwareCacheDecorator`. Với Spring transaction đang active, chúng có thể hoãn `put`, `evict` và `clear` đến **after-commit** của giao dịch thành công; nếu không có active transaction thì thực hiện ngay. Những API yêu cầu hiệu ứng tức thì như `evictIfPresent` không được defer theo cùng cách.

Cần test thứ tự advisor, transaction propagation, database commit và cache provider thực tế. Một lựa chọn khác là phát sự kiện và xử lý invalidation ở `@TransactionalEventListener(phase = AFTER_COMMIT)` hoặc outbox khi phải đồng bộ nhiều dịch vụ.

**Điều cần nhớ:** `beforeInvocation=false` chỉ bảo đảm mốc tương đối với invocation mà caching advice quan sát; không tự đồng bộ với giao dịch database.

## 11. Khi cache provider evict lỗi

Nếu business method đã return nhưng `Cache.evict` lỗi (timeout, mạng, permission, serializer), `SimpleCacheErrorHandler` mặc định có thể propagate exception cho caller. Nguồn dữ liệu có thể đã thay đổi dù API trả lỗi.

Có thể cấu hình `CacheErrorHandler` để bỏ qua một số lỗi cache nhằm tiếp tục nghiệp vụ, nhưng khi evict thất bại, entry cũ có thể stale. Phải có TTL, metric, alert và chiến lược retry/invalidation an toàn. Không nên âm thầm nuốt lỗi eviction rồi tuyên bố cache luôn nhất quán.

Phân biệt khi debug:

- **Lỗi của target method**: after-invocation eviction không chạy.
- **Lỗi đánh giá SpEL/cache configuration** sau method: không xóa đúng entry, có thể propagate ra caller.
- **Lỗi do cache provider** khi evict: method đã thành công nhưng xóa thất bại, caller có thể nhận exception.

## 12. Async/reactive và fire-and-forget

Từ Spring Framework 6.1, một số cache operations có hỗ trợ kiểu trả về `CompletableFuture` và reactive publisher. Với `@CacheEvict(beforeInvocation=false)`, eviction có thể được thực hiện khi **xử lý bất đồng bộ hoàn tất**, thay vì ngay khi method mới trả về một future/publisher. Với `Flux`, Spring có thể gom emitted values thành `List` để phục vụ `#result` trong ngữ cảnh thích hợp.

~~~java
@CacheEvict(cacheNames = "products", key = "#p0",
            beforeInvocation = false)
public CompletableFuture<Void> updateAsync(long id) {
    return asyncRepository.update(id);
}
~~~

Đoạn trên là snippet cần repository bất đồng bộ. Phải kiểm tra completion thành công, exceptional completion và cache provider. Nếu method chỉ khởi chạy job nền rồi return `void` ngay (*fire-and-forget*), “sau lời gọi” có thể đến trước khi job kết thúc. Khi đó hãy gắn eviction với mốc completion/commit thật, không chỉ thời điểm method launcher return.

## 13. AOP proxy và self-invocation

Ở proxy mode mặc định, annotation chỉ hoạt động khi lời gọi đi qua proxy:

~~~java
@Service
public class ProductService {
    public void batch(long id) {
        update(id); // self-invocation, có thể bypass caching advice
    }

    @CacheEvict(cacheNames = "products", key = "#p0")
    public void update(long id) {
        // cập nhật dữ liệu
    }
}
~~~

Snippet này cần Spring `@Service` và implementation thực tế. Lời gọi nội bộ từ `batch` sang `update` qua `this` không được proxy chặn; dù `update` return thành công, cache không được evict bởi annotation. Cách sửa thường là chuyển annotated method sang một bean khác, inject và gọi thông qua bean đó.

Những trường hợp khác cần kiểm tra: object được tạo bằng `new`, thiếu `@EnableCaching`, bean ở context khác, method private/final không tương thích loại proxy, pointcut không áp dụng, cache/key không khớp và kết hợp các annotation gây bỏ qua business method. Nên tách query `@Cacheable` và command `@CacheEvict` thành các method rõ ràng.

## 14. Kiểm thử và chẩn đoán

Một bộ kiểm thử đúng phạm vi nên chứng minh:

1. Gọi method `@Cacheable` hai lần: lần đầu miss, lần hai hit.
2. Gọi command annotated `@CacheEvict(beforeInvocation=false)` thành công: lần đọc tiếp theo miss, tải giá trị mới.
3. Command ném exception trước khi thay đổi nguồn: cache vẫn hit giá trị cũ.
4. Method trả false không ném exception: eviction mặc định vẫn diễn ra.
5. Thêm `condition="#result == true"`: kết quả false không evict.
6. Bắt exception rồi return bình thường: eviction vẫn có thể xảy ra.
7. Hai key khác nhau: evict key A không xóa key B.
8. `allEntries=true`: command thành công clear cả cache; command lỗi không clear.
9. Transaction rollback/commit: kiểm tra thứ tự eviction và commit với transaction thật.
10. Concurrent reader và nhiều node: kiểm tra race stale cache giữa update, commit và eviction.
11. Cache backend lỗi: xác minh `CacheErrorHandler` và kết quả business update.
12. Async completion, proxy boundary và self-invocation: test với Spring context thật.

Khi kiểm thử caching, hãy lấy service từ `ApplicationContext` thay vì `new`. Dùng counter số lần business method chạy và giá trị cache giúp phân biệt cache hit/miss. Với cache provider có deferred eviction, cần chờ/quan sát đúng thời điểm backend thực sự xóa entry.

## 15. Những hiểu nhầm phổ biến

- **“`beforeInvocation=false` nghĩa là xóa sau DB commit.”** Sai; thời điểm invocation và commit là hai mốc khác nhau.
- **“Method trả false thì Spring không evict.”** Sai nếu không có `condition`.
- **“Có exception thì database chắc chắn không thay đổi.”** Sai với side effect đã commit hoặc tài nguyên ngoài transaction.
- **“`@CacheEvict` luôn tạo giá trị cache mới.”** Sai; nó invalidation, còn `@CachePut` dùng để ghi kết quả mới.
- **“`@CacheEvict` không dùng được với void.”** Sai; void method rất phổ biến.
- **“`allEntries=true` kết hợp key sẽ xóa một vài entry.”** Sai; full-region eviction là chế độ riêng.
- **“`beforeInvocation=true` luôn an toàn hơn.”** Sai; eviction trước update có thể dẫn tới reader nạp dữ liệu cũ.
- **“Provider luôn xóa vật lý ngay lập tức.”** Không chắc; có transaction-aware/deferred eviction.
- **“Tự gọi method trong cùng bean vẫn được cache advice.”** Không đúng trong proxy mode mặc định.
- **“Bỏ qua lỗi cache không ảnh hưởng tính nhất quán.”** Sai; cache cũ có thể tồn tại đến TTL hoặc invalidation kế tiếp.

## 16. Tài liệu tham khảo chính thức

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@CacheEvict`, `beforeInvocation`, `condition`, `allEntries`, `#result`, async/reactive.
- [Spring Framework — CacheEvict Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html): hợp đồng và các giá trị mặc định của annotation.
- [Spring Framework — CacheAspectSupport Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/CacheAspectSupport.html): xử lý cache operations theo invocation.
- [Spring Framework — TransactionAwareCacheDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html): hoãn put/evict/clear đến after-commit trong transaction phù hợp.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundary và rollback.

**Ghi nhớ:** `@CacheEvict(beforeInvocation=false)` yêu cầu evict sau khi target method hoàn tất bình thường; exception thoát khỏi method ngăn after-invocation eviction. Muốn cache nhất quán, cần đúng cache/key, condition, xử lý side effect, transaction commit và hành vi backend.