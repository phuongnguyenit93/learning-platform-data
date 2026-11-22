# Yêu cầu kho hỗ trợ truy xuất bằng CompletableFuture trong Spring Cache

## 1. Tại sao bài toán này quan trọng?

Trong Spring Cache, một phương thức nghiệp vụ có thể trả về `CompletableFuture<T>`, nhưng **điều đó không có nghĩa mọi kho cache đều hỗ trợ truy xuất bất đồng bộ**. Kể từ Spring Framework **6.1**, cache abstraction có API truy xuất bằng `CompletableFuture`. Để tận dụng đúng cơ chế này, `Cache` implementation phải hỗ trợ các phương thức `retrieve(...)` tương ứng, thay vì chỉ triển khai các phương thức đồng bộ `get(...)`.

Hai nhu cầu cần phân biệt:

1. **Ứng dụng trả kết quả bất đồng bộ:** một service trả `CompletableFuture<String>`; Spring có thể cache **giá trị hoàn thành** của future và dựng lại future khi cache hit.
2. **Kho cache cung cấp API truy xuất bất đồng bộ:** `cache.retrieve(key)` trả một `CompletableFuture` đại diện cho thao tác tra cache; dạng `cache.retrieve(key, valueLoader)` còn hỗ trợ nạp giá trị khi miss.

Một provider hỗ trợ `Cache.get(key)` đồng bộ **không tự động** hỗ trợ cả hai biến thể `Cache.retrieve(...)`. Có provider hỗ trợ ngay; có provider cần bật chế độ async; có provider không triển khai và ném `UnsupportedOperationException`.

### Bạn sẽ học được

- Vai trò của `CacheManager`, `Cache`, `@Cacheable` và `CompletableFuture`.
- Hợp đồng `Cache.retrieve(Object)` và `Cache.retrieve(Object, Supplier<CompletableFuture<T>>)`.
- Cách hiểu `null` trả về ngay, future hoàn thành với `null` và cached-null.
- Điều kiện thực tế để `@Cacheable` hoạt động với `CompletableFuture<T>` trong Spring 6.1+.
- Các provider ví dụ: `ConcurrentMapCacheManager` hỗ trợ truy xuất kiểu future và `CaffeineCacheManager` cần cấu hình async cache mode thích hợp.
- Giới hạn của `@Cacheable(sync = true)`, concurrency, exception, null, transaction và reactive types.
- Cách viết chương trình Java 17 chạy được, dùng Spring Framework, để **kiểm tra provider** và đối chiếu cache hit/miss.
- Cách chẩn đoán và kiểm thử trước khi thay cache provider trong production.

## 2. Nhìn đúng ba lớp bất đồng bộ

Hãy xét ba đối tượng khác nhau:

~~~text
                          Caller
                            |
                            v
               Spring-managed proxy
                            |
                            v
              @Cacheable / CacheInterceptor
                            |
                            v
                       CacheManager
                            |
                  getCache("names")
                            |
                            v
                      Cache object
                            |
                +-----------+-----------+
                |                       |
                v                       v
       get(key) đồng bộ       retrieve(key) async API
        -> ValueWrapper       -> CompletableFuture<?>
                |                       |
                +-----------+-----------+
                            |
                      Entry value
                            |
                            v
               String / DTO / kết quả thực
~~~

Các lớp:

**Lớp 1 — Phương thức nghiệp vụ:** `CompletableFuture<String> find(String id)` biểu thị tính toán có thể hoàn thành trong tương lai. Giá trị nghiệp vụ cuối cùng là `String`.

**Lớp 2 — Cache abstraction:** `@Cacheable` được Spring xử lý. Với Spring 6.1+, nó nhận biết future return type, có thể đặt **kết quả khi future hoàn thành** vào cache và trả lại một future phù hợp trên cache hit. Không nên mặc định cache luôn lưu chính instance `CompletableFuture` của lời gọi đầu tiên.

**Lớp 3 — Cache provider:** `Cache.retrieve(key)` hỗ trợ truy cập entry qua một future. Chỉ một số provider hoặc cấu hình có hợp đồng này. Tính bất đồng bộ của service không thay thế tính năng của cache implementation.

### So sánh get và retrieve

| API | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `cache.get(key)` | `Cache.ValueWrapper` hoặc `null` | Tra entry qua API đồng bộ |
| `cache.get(key, String.class)` | `String` hoặc `null` | Tra entry và chuyển kiểu qua API đồng bộ |
| `cache.get(key, Callable<T>)` | `T` | Đồng bộ tra hoặc nạp qua loader |
| `cache.retrieve(key)` | `CompletableFuture<?>` hoặc có thể `null` | Tra entry qua API dựa trên future |
| `cache.retrieve(key, Supplier<CompletableFuture<T>>)` | `CompletableFuture<T>` | Tra/nạp value bất đồng bộ khi cần |

**Đừng nhầm:** `CacheManager.getCache("names")` lấy **vùng cache**, còn `Cache.retrieve("A")` lấy **entry** trong vùng đó. Tên cache và key là hai cấp khác nhau.

## 3. Hợp đồng của Cache.retrieve(Object key)

Trong Spring Framework 6.1+, `org.springframework.cache.Cache` có phương thức dạng:

~~~java
@Nullable
CompletableFuture<?> retrieve(Object key);
~~~

Đây là **chữ ký API đã giản lược**, không phải file Java độc lập. Ý nghĩa:

- Đầu vào `key` là key entry bạn muốn tìm.
- Nếu provider hỗ trợ, kết quả có thể là `CompletableFuture<?>` sẽ hoàn thành khi kết quả tra cứu sẵn sàng.
- **Giá trị return của chính `retrieve` có thể là `null`:** provider biết ngay tại thời điểm gọi rằng key không có mapping (*immediate miss*).
- Nếu return là một future, future có thể hoàn thành với `null` khi tra cứu không tìm thấy mapping (*late miss*).
- Một cached-null (khi provider cho phép cache kết quả nghiệp vụ null) có thể được biểu diễn bằng một `ValueWrapper` chứa null để phân biệt với miss; chi tiết phải theo hợp đồng provider.
- Nếu implementation không hỗ trợ retrieval dạng future, nó có thể ném `UnsupportedOperationException`, vì phương thức default của interface không bắt buộc provider cũ phải triển khai tính năng này.

### Quy tắc xử lý miss chuẩn

Không được viết ngay:

~~~java
Object value = cache.retrieve("A").join();
~~~

vì nếu `retrieve("A")` trả `null` ngay, bạn sẽ gặp `NullPointerException`. Một cách kiểm tra căn bản:

~~~java
CompletableFuture<?> future = cache.retrieve("A");

if (future == null) {
    System.out.println("MISS known immediately");
} else {
    Object result = future.join();
    if (result == null) {
        System.out.println("MISS determined asynchronously");
    } else {
        System.out.println("An entry was returned");
    }
}
~~~

Đoạn này **minh họa** và giả định `cache` là một `Cache` đã lấy được, chưa phải file độc lập. Khi provider có cached-null và trả `Cache.ValueWrapper`, cần unwrap rồi kiểm tra wrapper/value đúng API; **không ép mọi result non-null đều là DTO nghiệp vụ**.

### Ba loại null quan trọng

~~~text
CacheManager.getCache("names") == null
    -> không lấy được vùng cache.

Cache.retrieve("A") == null
    -> provider xác định ngay key A không có mapping.

Cache.retrieve("A") != null
    và returnedFuture.join() == null
    -> lookup hoàn tất nhưng không có giá trị trực tiếp;
       thường là miss được xác định sau,
       cần chú ý provider và cached-null contract.

Returned future hoàn thành với ValueWrapper(null)
    -> một cách biểu diễn cached-null (HIT).
~~~

Dạng đồng bộ `cache.get(key)` có `ValueWrapper` để phân biệt miss và hit với null. Với dạng async, hãy đọc Javadoc phiên bản/provider và kiểm thử null policy thay vì suy diễn hoàn toàn từ typed get hoặc `join()`.

### join() có làm lời gọi “non-blocking” không?

Không. `CompletableFuture.join()` **có thể chặn thread hiện tại** cho tới khi future hoàn thành. Trong ví dụ học tập có thể dùng `join()` để in kết quả quyết định; trong ứng dụng bất đồng bộ thực tế nên ưu tiên `thenApply`, `thenCompose`, `whenComplete` hoặc integration với reactive pipeline thay vì chặn thread yêu cầu.

## 4. Hợp đồng retrieve(key, valueLoader)

Spring còn hỗ trợ biến thể:

~~~java
<T> CompletableFuture<T> retrieve(
        Object key,
        Supplier<CompletableFuture<T>> valueLoader);
~~~

Đây là **chữ ký rút gọn**, không phải file Java độc lập.

Điểm khác biệt:

- `retrieve(key)` chỉ tra cache, caller tự quyết định nếu miss.
- `retrieve(key, valueLoader)` cho cache quyền điều phối **tra + tải giá trị khi miss**.
- `valueLoader` là một `Supplier` trả về `CompletableFuture<T>`, **không** phải `Supplier<T>`; loader phải tạo/tra kết quả theo hợp đồng async.
- Kết quả trả về là `CompletableFuture<T>`, có thể được compose với phần còn lại của xử lý.
- Implementation/provider quyết định khả năng phối hợp các request cùng key, độ nguyên tử và thời điểm thực hiện loader; **không được hứa rằng mọi provider sẽ chỉ gọi loader đúng một lần ở toàn bộ cluster**.
- Lỗi từ loader hoặc backend có thể làm future hoàn thành exceptionally (hoặc phương thức ném exception); code gọi cần xử lý thất bại có chủ đích.

Ví dụ:

~~~java
CompletableFuture<String> result = cache.retrieve(
    "A",
    () -> remoteClient.fetchNameAsync("A")
);
~~~

Snippet minh họa: `cache` và `remoteClient` phải được ứng dụng định nghĩa; `fetchNameAsync` trả `CompletableFuture<String>`. Đừng bọc một tác vụ đồng bộ chặn I/O vào `CompletableFuture.completedFuture(...)` rồi tuyên bố đã có non-blocking I/O.

### Nguyên tắc phân biệt cache hit và loader

~~~text
retrieve("A", asyncLoader)
             |
             v
       Kiểm tra entry
         /       \
       HIT       MISS
        |          |
        v          v
     future     asyncLoader.get()
       value       |
                   v
                future T
                   |
                   v
               cache value
~~~

Đây là **mô hình logic**. Provider thực tế có thể thực hiện lookup/loader trên executor hoặc cơ chế futures riêng; cần kiểm thử thời điểm và concurrency. Với một số implementation, quá trình lấy dữ liệu có thể chạy trên worker thread dù API trả về future.

## 5. Provider cần thực sự hỗ trợ hai API này

Một provider có thể implement các phương thức đồng bộ và hoàn toàn hoạt động với `@Cacheable` trả `String`, nhưng khi bạn đổi method sang `CompletableFuture<String>`, yêu cầu về async retrieval trở nên khác.

### 5.1. ConcurrentMapCacheManager

`ConcurrentMapCacheManager` của Spring Framework quản lý các `ConcurrentMapCache` và hỗ trợ retrieval theo `CompletableFuture`. Đây là lựa chọn tốt để làm demo/test vì không cần Redis, Caffeine, network hay cấu hình nhiều dependency.

Tuy nhiên:

- Cache vẫn lưu dữ liệu **trong bộ nhớ JVM hiện tại**.
- API trả `CompletableFuture` **không biến bộ nhớ local thành distributed/asynchronous network store**.
- Nó không tự có TTL, size-based eviction hay persistence.
- Không dùng hành vi của ConcurrentMapCache để suy ra tính năng của tất cả provider khác.

### 5.2. CaffeineCacheManager

`CaffeineCacheManager` có **async cache mode**. Với Spring Framework hỗ trợ `setAsyncCacheMode(true)`, khi muốn truy xuất `CompletableFuture` qua provider Caffeine, cần cấu hình chế độ phù hợp.

Snippet cấu hình (cần `spring-context-support`, Caffeine dependency và imports):

~~~java
@Bean
public CaffeineCacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("names");
    manager.setAsyncCacheMode(true);
    manager.setCaffeine(
            Caffeine.newBuilder()
                    .maximumSize(1000)
                    .expireAfterWrite(Duration.ofMinutes(10))
    );
    return manager;
}
~~~

Đoạn này **không tự chạy độc lập**, vì cần:
- `org.springframework.cache.caffeine.CaffeineCacheManager`.
- `com.github.benmanes.caffeine.cache.Caffeine`.
- `java.time.Duration`.
- `@Bean` và dependencies Spring/Caffeine tương thích.

Chỉ tạo `CaffeineCacheManager` rồi mặc định rằng async mode đã bật có thể dẫn đến lỗi hoặc behavior không mong muốn. Một số cách đăng ký custom `AsyncCache` cũng có hợp đồng riêng; xem Javadoc của phiên bản đang dùng.

### 5.3. Những provider khác

Với Redis/JCache/provider nội bộ hoặc wrapper nhiều tầng, **không suy luận từ tên provider** rằng `retrieve` luôn sẵn sàng. Hỗ trợ có thể phụ thuộc:

- Phiên bản Spring Framework và thư viện tích hợp.
- Khả năng bất đồng bộ của client/backend thực tế.
- Cách cấu hình `CacheManager` và `Cache`.
- Provider có triển khai **cả** `retrieve(key)` và `retrieve(key, valueLoader)` hay chỉ một phần.
- Decorator bên ngoài có delegate đúng API hay không.
- Chính sách serializing cached-null, lỗi backend và timeout.

Một check chính xác thường là **integration test trên chính bean `Cache` của ứng dụng**, không phải danh sách tên cache của manager.

### Bảng quyết định

| Tình huống | Nên làm |
| --- | --- |
| Dùng `ConcurrentMapCacheManager` cho học tập | Thử trực tiếp `retrieve(...)`, kiểm tra hit/miss |
| Dùng Caffeine | Bật async cache mode và test với cấu hình manager cụ thể |
| Dùng Redis hoặc provider khác | Đọc Javadoc/version, kiểm thử method `retrieve` trên provider đang chạy |
| Có lớp wrapper/decorator | Kiểm tra wrapper có hỗ trợ/delegate cả hai overload hay không |
| Chỉ cần method đồng bộ | `@Cacheable` trả `T` và `Cache.get` thường đơn giản hơn |
| Cần future end-to-end | `CompletableFuture<T>` + provider async-compatible, tránh block thread |

## 6. @Cacheable với phương thức trả CompletableFuture<T>

Từ Spring Framework 6.1, cache abstraction biết cách xử lý một số return type bất đồng bộ.

~~~java
@Cacheable(cacheNames = "names", key = "#p0")
public CompletableFuture<String> findName(String id) {
    return gateway.fetchNameAsync(id);
}
~~~

Đoạn này minh họa; `gateway` thuộc ứng dụng.

Khi **cache miss**, phương thức có thể trả một `CompletableFuture<String>` chưa hoàn thành. Spring theo dõi sự hoàn thành và cache **giá trị `String` đã tính được** khi future hoàn tất thành công. Khi **cache hit**, Spring có thể trả lại một `CompletableFuture<String>` đại diện cho value đã cache.

Không nên hiểu rằng:
- Cache luôn giữ nguyên **object `CompletableFuture`** và identity của future ban đầu.
- Cache put được thực hiện trước khi phần tính toán bên trong future hoàn thành.
- Provider bất kỳ hỗ trợ được Spring 6.1 async cache operation.
- CompletableFuture return type tự tạo executor hoặc tự bảo đảm non-blocking.

### Timeline

~~~text
Caller gọi findName("A") qua Spring proxy
                  |
                  v
          Cache lookup theo key
             /              \
           HIT              MISS
            |                 |
            v                 v
      Value đã cache     Gọi target method
            |                 |
            v                 v
   Trả CompletableFuture  CompletableFuture<String>
        phù hợp                |
                               v
                      Hoàn thành thành công
                               |
                               v
                      Put "A" -> String value
                               |
                               v
                         Caller nhận value
~~~

Với future hoàn thành exceptionally, ứng dụng phải xử lý lỗi; không nên xem thất bại như một giá trị bình thường để lưu. Nếu service trả `CompletableFuture.completedFuture(null)`, null policy của cache và `unless` cần được thiết kế rõ ràng.

### Khi dùng @CachePut và @CacheEvict

Các annotation khác có thể thích ứng với return type bất đồng bộ trong Spring Framework 6.1+, nhưng thời điểm put/evict và lỗi phụ thuộc operation/implementation. Đặc biệt, không nên giả định một `void` method với tác vụ async fire-and-forget sẽ làm Spring biết tác vụ đó hoàn thành. Nếu nghiệp vụ trả future, cần làm rõ lifecycle và kiểm thử invalidation sau khi future hoàn tất, cũng như transaction boundary.

## 7. @Cacheable(sync = true) cần gì hơn?

~~~java
@Cacheable(
    cacheNames = "names",
    key = "#p0",
    sync = true
)
public CompletableFuture<String> findName(String id) {
    return gateway.fetchNameAsync(id);
}
~~~

Đây là snippet minh họa.

Mục tiêu của `sync = true` là phối hợp các lời gọi cùng miss/key để tránh nhiều loader cùng tính một giá trị. Với kết quả async, provider thường cần triển khai biến thể **`retrieve(key, valueLoader)`** có khả năng điều phối nạp dữ liệu.

Điểm cần nhớ:

- `sync=true` là gợi ý/hợp đồng với cache provider; khả năng đồng bộ hóa cụ thể do implementation hỗ trợ.
- Không có bảo đảm single-flight xuyên mọi node của cluster chỉ vì annotation này xuất hiện.
- Spring áp đặt các giới hạn với `sync=true`, chẳng hạn chỉ dùng một vùng cache cho operation, không kết hợp `unless` và không gộp nhiều operation cache trong cùng annotation setup.
- Nếu provider không hỗ trợ truy xuất/nạp theo future, `sync=true` không sửa được điều đó; ngược lại có thể khiến lỗi lộ rõ hơn.
- Không nhầm `sync=true` với `@Async`, transaction isolation hay distributed lock.

### Vì sao test chỉ với một thread chưa đủ?

Một unit test tuần tự có thể chứng minh cache hit lần hai, nhưng **không** chứng minh loader chỉ chạy một lần khi 20 request đồng thời cùng miss. Cần integration/concurrency test với `CountDownLatch` hoặc barrier, đo số invocation và xác nhận chính sách của provider thật.

## 8. Demo Java 17 chạy được: kiểm tra truy xuất CompletableFuture

Ví dụ dùng **Java 17**, **Maven**, **Spring Framework 6.2.16** và `ConcurrentMapCacheManager`. Không cần Spring Boot, Caffeine hay database.

Demo kiểm chứng:

1. `retrieve("A")` khi chưa có entry được xử lý theo cả hai khả năng: return null ngay hoặc future hoàn thành với null.
2. `@Cacheable` trên method trả `CompletableFuture<String>` hoạt động với manager hỗ trợ API async.
3. Lần gọi thứ hai cùng key hit cache nên không chạy lại thân method.
4. `Cache.get("A", String.class)` thấy **String resolved**, không phải giữ nguyên `CompletableFuture`.
5. `Cache.retrieve("A")` trả future chứa giá trị đã cache.
6. `retrieve(key, valueLoader)` tự nạp khi miss và không gọi lại loader khi hit trong ví dụ tuần tự.
7. `Cache.evict("A")` làm lời gọi sau phải tải lại.

### 8.1. Cấu trúc thư mục

~~~text
future-cache-demo/
├── pom.xml
└── src/main/java/demo/FutureCacheDemo.java
~~~

### 8.2. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>future-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. File src/main/java/demo/FutureCacheDemo.java

~~~java
package demo;

import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class FutureCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("names");
        }

        @Bean
        public NamesService namesService() {
            return new NamesService();
        }
    }

    public static class NamesService {
        private final AtomicInteger calls = new AtomicInteger();

        @Cacheable(cacheNames = "names", key = "#p0")
        public CompletableFuture<String> name(String id) {
            int n = calls.incrementAndGet();
            System.out.println("LOAD " + id + " #" + n);
            return CompletableFuture.completedFuture(
                    "name-" + id + "-v" + n);
        }

        public int calls() {
            return calls.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            CacheManager manager =
                    context.getBean(CacheManager.class);
            NamesService service =
                    context.getBean(NamesService.class);
            Cache cache = Objects.requireNonNull(
                    manager.getCache("names"));

            // Cho phép cả immediate miss và late miss.
            CompletableFuture<?> before = cache.retrieve("A");
            System.out.println("startMiss="
                    + (before == null || before.join() == null));

            System.out.println("first="
                    + service.name("A").join());
            System.out.println("second="
                    + service.name("A").join());
            System.out.println("stored="
                    + cache.get("A", String.class));

            CompletableFuture<?> hit = cache.retrieve("A");
            System.out.println("retrieved="
                    + Objects.requireNonNull(hit).join());

            AtomicInteger supplierCalls = new AtomicInteger();
            CompletableFuture<String> manual1 = cache.retrieve(
                    "manual",
                    () -> {
                        int n = supplierCalls.incrementAndGet();
                        System.out.println("SUPPLIER #" + n);
                        return CompletableFuture.completedFuture(
                                "manual-value");
                    });
            System.out.println("manual1=" + manual1.join());

            CompletableFuture<String> manual2 = cache.retrieve(
                    "manual",
                    () -> {
                        int n = supplierCalls.incrementAndGet();
                        System.out.println("UNEXPECTED SUPPLIER #" + n);
                        return CompletableFuture.completedFuture(
                                "wrong-value");
                    });
            System.out.println("manual2=" + manual2.join());
            System.out.println("supplierCalls="
                    + supplierCalls.get());

            cache.evict("A");
            System.out.println("afterEvictMissing="
                    + (cache.get("A") == null));
            System.out.println("third="
                    + service.name("A").join());
            System.out.println("serviceCalls=" + service.calls());
        }
    }
}
~~~

### 8.4. Chạy chương trình

Cần JDK 17+ và Maven; từ thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.FutureCacheDemo
~~~

Stdout dự kiến **do chương trình chủ động in**, không tính log riêng của Maven:

~~~text
startMiss=true
LOAD A #1
first=name-A-v1
second=name-A-v1
stored=name-A-v1
retrieved=name-A-v1
SUPPLIER #1
manual1=manual-value
manual2=manual-value
supplierCalls=1
afterEvictMissing=true
LOAD A #2
third=name-A-v2
serviceCalls=2
~~~

### 8.5. Tại sao các dòng output này quan trọng?

**`startMiss=true`:** code không giả định `retrieve("A")` luôn trả non-null future; nó xử lý đúng cả immediate và late miss.

**`LOAD A #1` chỉ xuất hiện trước `first`:** lần đầu chưa có entry, target chạy. `second` trả lại `name-A-v1` nhưng không in `LOAD` — dấu hiệu cache hit.

**`stored=name-A-v1`:** truy xuất đồng bộ kiểu `String.class` thấy giá trị hoàn thành `String`. Bài học: không xem future return type đồng nghĩa cache giữ chính future object ban đầu.

**`retrieved=name-A-v1`:** provider trả `CompletableFuture<?>` cho entry đã có, và lời gọi `join()` lấy được giá trị.

**`SUPPLIER #1` đúng một lần trong nhánh `manual`:** biến thể `retrieve(key, loader)` chạy callback khi miss; lần sau cùng key trả từ cache và không thực thi callback thứ hai. Điều này chứng minh behavior **tuần tự trong demo**; không thay thế concurrency test.

**`afterEvictMissing=true` rồi `LOAD A #2`:** evict xóa mapping; lần sau service phải tải lại, trả version mới.

### 8.6. Vì sao demo dùng completedFuture?

`CompletableFuture.completedFuture(...)` giúp stdout **quyết định, dễ kiểm chứng**, không tạo race phụ thuộc thread pool. Nó chứng minh Spring biết xử lý return type `CompletableFuture` và cache provider triển khai API `retrieve`. Demo **không** chứng minh gọi database/network của bạn là non-blocking. Trong ứng dụng thực tế, future có thể do async database driver/client hoặc executor tạo ra, và test phải kiểm chứng timeout/error/cancellation cụ thể.

### 8.7. Spring proxy vẫn là điều kiện bắt buộc

`@EnableCaching` bật annotation-based caching. `NamesService` được lấy từ Spring `ApplicationContext`; lời gọi đi qua proxy/interceptor. Nếu làm:

~~~java
NamesService service = new NamesService();
service.name("A");
service.name("A");
~~~

đây là **snippet minh họa bên ngoài Spring**; hai lời gọi trực tiếp không được cache chỉ vì method có `@Cacheable`. Tương tự, `this.name("A")` trong chính bean có thể bypass proxy trong proxy mode.

## 9. Lỗi provider không hỗ trợ async retrieval

Triệu chứng có thể gặp khi thay provider hoặc cấu hình sai:

~~~text
java.lang.UnsupportedOperationException
  ...
  Cache.retrieve(...)
~~~

Đoạn trên minh họa triệu chứng, **không khẳng định mọi provider luôn ném đúng cùng một stack trace**. Nguyên nhân thường là implementation cache chỉ hỗ trợ các API `get`/`put` đồng bộ hoặc wrapper không delegate `retrieve`.

### Phải kiểm tra cái gì?

1. Spring Framework version có hỗ trợ `Cache.retrieve` và cache annotation future return type không? (từ 6.1).
2. Bean `CacheManager` thực tế là implementation gì?
3. `getCache(cacheName)` trả `Cache` loại gì? Nó có thể bị wrapper bởi decorator.
4. Provider có hỗ trợ `retrieve(key)`?
5. Provider có hỗ trợ `retrieve(key, loader)`, nhất là khi dùng `sync=true`?
6. Cấu hình Caffeine đã bật `setAsyncCacheMode(true)` chưa?
7. Cache name, key, value type và serialization có hợp lệ không?
8. Có dùng `CompletableFuture.join()` quá sớm khiến thread bị block hoặc deadlock không?
9. Có vấn đề exception/timeout/cancel/null policy khiến future không hoàn thành như mong đợi không?

### Một đoạn kiểm tra API trực tiếp

~~~java
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("names"));

try {
    CompletableFuture<?> test = cache.retrieve("probe-key");
    // test có thể null nếu provider biết ngay key chưa có.
    System.out.println("Async retrieval method supported");
} catch (UnsupportedOperationException ex) {
    System.out.println("Async retrieval is not supported");
}
~~~

Snippet này **không chạy độc lập**: cần `CacheManager`, `Cache`, `Objects` và `CompletableFuture` từ application. Nó chỉ kiểm tra overload `retrieve(key)` tại thời điểm probe; chưa kiểm tra loader overload hoặc backend thật khi có entry. Không nên dùng probe ngẫu nhiên trong production làm bài test duy nhất, và không tự phát sinh tên cache từ input người dùng.

### Fallback có an toàn không?

Không nên catch mọi exception rồi chặn I/O đồng bộ để “chữa” lỗi async. Nếu provider không đáp ứng hợp đồng, các lựa chọn đúng hơn:

- Cấu hình hoặc nâng cấp provider có hỗ trợ.
- Sử dụng manager khác đã được kiểm chứng.
- Thiết kế service đồng bộ với cache đồng bộ nếu yêu cầu nghiệp vụ cho phép.
- Dùng một cache adapter được thiết kế, kiểm thử rõ timeout/concurrency và policy lỗi.

Bọc `Cache.get` đồng bộ trong `CompletableFuture.completedFuture(...)` **không làm thao tác cache trở thành non-blocking**; nó chỉ đổi kiểu trả về sau khi đã làm việc đồng bộ.

## 10. Null, exception và cancellation trong future

### 10.1. Future hoàn thành với null

~~~java
return CompletableFuture.completedFuture(null);
~~~

Nếu trả từ method có `@Cacheable`, việc có lưu cached-null hay không phụ thuộc `Cache` provider và cấu hình `unless`. Ví dụ:

~~~java
@Cacheable(
    cacheNames = "names",
    key = "#p0",
    unless = "#result == null"
)
public CompletableFuture<String> maybeFind(String id) {
    return CompletableFuture.completedFuture(null);
}
~~~

Snippet minh họa; khi kết quả cuối cùng null, `unless` được thiết kế để không cache null. Tùy provider, `null` được biểu diễn bằng marker hoặc bị từ chối. Không dùng `retrieve(key).join()==null` làm chứng cứ duy nhất để kết luận không có entry khi cached-null được bật.

### 10.2. Exception và future exceptionally

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("backend unavailable"));
~~~

Nếu loader/future kết thúc lỗi, caller phải xử lý `CompletionException`/nguyên nhân theo contract. Không được kỳ vọng một cache hit sẽ chữa lỗi nghiệp vụ đang xảy ra, và cũng không nên cache exception như giá trị bình thường trừ khi có thiết kế cụ thể.

Ví dụ xử lý:

~~~java
service.name("A")
    .whenComplete((value, error) -> {
        if (error != null) {
            logFailure(error);
        } else {
            useValue(value);
        }
    });
~~~

Snippet trên cần `service`, `logFailure` và `useValue` trong ứng dụng. Không phải tệp độc lập. Với `join()`, exception thường được bọc `CompletionException`.

### 10.3. Cancellation

`CompletableFuture.cancel(...)` là trạng thái hủy phía future; không mặc nhiên dừng I/O backend hoặc xóa entry cache. Phải thiết kế semantics huỷ và cleanup theo client/provider. Không nên giả định việc cancel một future từ cache cũng xóa cache entry hoặc cancel cùng một future dùng bởi tất cả caller.

### 10.4. Timeout

Với backend từ xa, cần timeout ở client/cache và policy fallback cụ thể. Khi callback supplier hoặc backend treo, future cũng có thể treo nếu không có timeout. Dùng cơ chế như `orTimeout` (khi thích hợp) và giám sát số future pending, latency, exception rate. Timeout một future ở tầng ứng dụng không thay thế timeout I/O của driver.

## 11. Reactive Mono và Flux có liên quan gì?

Spring Framework 6.1+ cũng thích ứng với các return type reactive được hỗ trợ, thường thông qua khả năng truy xuất tương ứng bằng `CompletableFuture` ở cache provider. Tuy nhiên, người học cần nhớ:

- `Mono<T>` đại diện một kết quả bất đồng bộ; Spring có thể cache giá trị khi Mono hoàn thành và dựng publisher tương ứng khi hit.
- `Flux<T>` có thể được **thu thập thành một danh sách** để cache rồi dựng lại stream từ danh sách đó; đây không phải là caching từng phần tử như một streaming buffer.
- Không nên xem Spring Cache annotation là giải pháp universal cho các streaming workload lớn hoặc vô hạn.
- Nếu kho cache không đáp ứng cách retrieval bất đồng bộ mà Spring yêu cầu, việc method trả Mono/Flux không tự khắc phục.
- Không chặn event-loop bằng `join()` hoặc thao tác cache đồng bộ tốn thời gian. Dùng kiến trúc provider và execution model phù hợp.

Nếu ứng dụng có Reactor, hãy kiểm thử với Reactor version và Spring version cụ thể. Demo Java 17 ở mục 8 chỉ tập trung vào `CompletableFuture` để tránh thêm dependency không cần thiết.

## 12. Transaction, context và đa instance

### 12.1. Transaction chưa commit

Future có thể hoàn thành sau khi transaction database kết thúc. Cache put theo future result vì thế có thể xảy ra **ở thời điểm khác** với lúc method ban đầu trả future. Nếu dữ liệu có thể bị rollback hoặc transaction ở layer khác, cần test data consistency và có chiến lược after-commit/invalidation phù hợp. Không giả định `@Transactional` tự đồng bộ mọi cache put với database.

### 12.2. Thread-local context

Một `CompletableFuture` có thể hoàn thành trên thread khác. Tenant, security principal, MDC hoặc transaction context gắn với ThreadLocal không tự động được chuyển qua mọi executor. Nếu định tuyến cache/key phụ thuộc context, phải thiết kế capture/propagation đáng tin và tránh rò dữ liệu cross-tenant.

### 12.3. Cache local khác distributed cache

`ConcurrentMapCacheManager` chỉ chia sẻ dữ liệu trong cùng JVM. Truy xuất bằng `CompletableFuture` **không** khiến hai instance ứng dụng dùng chung vùng cache. Nếu cần consistency nhiều replica, phải chọn backend, partitioning, eviction propagation và transaction/invalidation phù hợp.

### 12.4. Backend có thật sự non-blocking không?

Một method trả `CompletableFuture` có thể vẫn làm việc đồng bộ trước khi future được trả về. Một provider có thể tạo completed future từ bộ nhớ rất nhanh. Dấu hiệu có future là **hợp đồng API**, không phải chứng minh về I/O non-blocking, throughput hoặc latency. Cần đo thread usage, blocking time và I/O profile riêng.

## 13. Kiểm thử provider và concurrency

Kiểm thử tối thiểu:

| Kịch bản | Thiết lập | Kết quả cần chứng minh |
| --- | --- | --- |
| Async retrieval hỗ trợ | `Cache.retrieve("absent")` | Không ném UnsupportedOperationException; xử lý immediate/late miss |
| Loader overload | `retrieve("A", loader)` | Future hoàn thành giá trị và entry được cache theo contract |
| Hit | Hai lần cùng key | Loader/body không chạy thêm trong case tuần tự |
| @Cacheable future | Method trả `CompletableFuture<String>` | Cache chứa value sau completion; hit dựng future mới/phù hợp |
| Delayed completion | Loader trả future pending | Không suy ra value đã cache trước completion |
| Failed completion | Future kết thúc exceptionally | Không trả nhầm stale/partial value; xử lý lỗi |
| Cached-null | Provider cho lưu null | Phân biệt miss và null hit đúng API |
| Eviction | Evict key rồi gọi lại | Tải lại đúng key |
| sync=true | Nhiều caller cùng miss | Kiểm chứng semantics single-flight thực tế của provider |
| Caffeine async mode | Bật/tắt async mode | Xác định cấu hình và behavior của cache thật |
| Multi-node | Nhiều instance | Không suy ra local future retrieval là distributed |
| Transaction | Loader trong transaction rollback | Không cache dữ liệu chưa commit theo thiết kế |
| Timeout | Backend chậm/treo | Future timeout đúng policy; không giữ thread vô hạn |

### Test concurrency phải tránh flaky

Để kiểm tra hai caller cùng key, dùng barrier hoặc `CountDownLatch` để điều khiển thời điểm bắt đầu. Đếm số lần loader thực hiện, không đoán dựa vào thời gian chạy. Nếu provider chỉ điều phối theo local JVM, không khẳng định single-flight giữa các instance.

### Đừng chỉ test get đồng bộ

Một provider có thể qua toàn bộ test `Cache.get(key)` và `@Cacheable` trả `String`, nhưng fail khi sử dụng `retrieve(key, loader)` hoặc method trả `CompletableFuture<String>`. Thêm **test riêng cho async API** khi nâng Spring/provider hoặc thay cache manager.

## 14. Lỗi thường gặp

**Lỗi 1 — “Method trả CompletableFuture nên cache cũng tự async”.** Không. Provider cần hỗ trợ retrieval dựa trên future theo API Spring 6.1+.

**Lỗi 2 — “Cache.get(key) chạy được nên Cache.retrieve(key) chắc chắn chạy được”.** Không. Cache implementation có thể chưa triển khai API async.

**Lỗi 3 — “retrieve(key) luôn trả CompletableFuture khác null”.** Sai. Hợp đồng cho phép return `null` khi provider biết ngay miss.

**Lỗi 4 — “Future hoàn thành null luôn có nghĩa cache miss”.** Chưa chắc: cached-null có thể cần `ValueWrapper`, và representation phụ thuộc provider.

**Lỗi 5 — “Gọi join() thì vẫn là non-blocking”.** Sai; `join()` có thể chặn thread hiện tại.

**Lỗi 6 — “sync=true đảm bảo chỉ một request toàn cluster chạy loader”.** Không có bảo đảm chung; phụ thuộc provider và phạm vi phối hợp.

**Lỗi 7 — “Đổi sang CaffeineCacheManager là xong”.** Chưa đủ nếu cần async retrieval; hãy bật async cache mode theo Spring/Caffeine version tương ứng và test.

**Lỗi 8 — “Cache lưu object CompletableFuture và lần sau trả đúng instance cũ”.** Spring cache adaptation hướng tới **giá trị hoàn thành**, không có cam kết giữ identity future.

**Lỗi 9 — “Bọc get đồng bộ trong completedFuture làm backend non-blocking”.** Sai; backend đã truy vấn đồng bộ trước khi future được tạo.

**Lỗi 10 — “Provider nào cũng hỗ trợ cả retrieve và retrieve-with-loader”.** Không được giả định; phải kiểm thử cả overload, đặc biệt với `sync=true`.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao `@Cacheable` trả CompletableFuture đòi hỏi nhiều hơn `@Cacheable` trả String?**

Vì framework cần làm việc với giá trị hoàn thành và cache retrieval kiểu future; provider phải đáp ứng API hỗ trợ hoặc cấu hình async phù hợp.

**2. `Cache.retrieve(key)` khác `Cache.get(key)` ra sao?**

`retrieve` trả future (hoặc có thể null khi miss biết ngay) để thể hiện truy xuất async; `get` trả `ValueWrapper` hoặc null trực tiếp.

**3. Tại sao cần kiểm tra return null trước khi gọi `join()`?**

Vì hợp đồng cho phép immediate miss khiến chính `retrieve(key)` trả null, không có future để join.

**4. Khi nào `retrieve(key, valueLoader)` hữu ích?**

Khi muốn cache provider điều phối tra entry và nạp từ một loader trả `CompletableFuture<T>` lúc miss; có thể giảm boilerplate và hỗ trợ phối hợp concurrency theo provider.

**5. Spring lưu một CompletableFuture object hay giá trị cuối?**

Với cache annotation hỗ trợ async trong Spring 6.1+, nó thích ứng với **giá trị hoàn thành**; không nên phụ thuộc identity của original future.

**6. Caffeine cần chú ý gì?**

Dùng cấu hình async cache mode (`setAsyncCacheMode(true)`) và đúng dependencies/versions; sau đó test behavior của cache thật.

**7. Tại sao `sync=true` không phải distributed lock?**

Vì coalescing/atomic lookup thuộc năng lực provider; annotation không tự tạo cơ chế lock xuyên cluster.

**8. Vì sao không nên dùng `join()` trên event loop?**

Vì có thể block thread, giảm throughput và gây nghẽn. Nên compose asynchronously.

**9. Nếu provider ném UnsupportedOperationException khi gọi retrieve thì phải làm gì?**

Xác định provider/version/configuration, kiểm tra cả hai overload, chọn backend hỗ trợ hoặc thiết kế đường đồng bộ có chủ đích. Đừng tự fallback blocking ngầm.

**10. Nếu cùng key được gọi trước khi future đầu tiên hoàn thành thì luôn chỉ chạy loader một lần không?**

Không mặc nhiên. Cần xem `sync=true` và provider semantics, đồng thời test concurrency thực tế.

## 16. Kết luận

Trong Spring Cache hiện đại, **async service return type** và **async cache retrieval support** là hai yêu cầu khác nhau. `CompletableFuture<T>` ở service thể hiện kết quả nghiệp vụ sẽ có trong tương lai; `Cache.retrieve(...)` là năng lực của kho cache để tra/nạp giá trị qua future.

Khi xây ứng dụng:

1. Xác nhận Spring Framework 6.1+ và provider có hỗ trợ `Cache.retrieve(key)`, đặc biệt `retrieve(key, valueLoader)` khi cần đồng bộ nạp.
2. Xử lý đúng immediate miss, late miss, cached-null và future exceptional.
3. Dùng `ConcurrentMapCacheManager` để học/test, cấu hình `CaffeineCacheManager.setAsyncCacheMode(true)` khi muốn async caching trên Caffeine.
4. Không nhầm `join()`, completed future hoặc cache local với non-blocking I/O và distributed consistency.
5. Kiểm tra cache hit, số lần loader, lỗi, concurrency, context và transaction trên **provider thực tế**.

**Quy tắc nhớ:** *Một phương thức trả CompletableFuture không làm cache provider tự có CompletableFuture-based retrieval. Hãy kiểm chứng hợp đồng của Cache implementation.*

## Tài liệu tham khảo chính thức

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Annotation-based caching, CompletableFuture và reactive return types: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache API Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework — ConcurrentMapCache Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework — CaffeineCacheManager Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework — Cacheable annotation Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html
