# Chọn cache đơn giản cho kiểm thử và môi trường phù hợp trong Spring

## 1. Mục tiêu và các implementation cần phân biệt

Spring Cache cung cấp abstraction để gắn hành vi cache vào phương thức; nơi lưu dữ liệu do `CacheManager` và `Cache` đảm nhiệm. Với kiểm thử, demo, local development hoặc ứng dụng nhỏ chỉ chạy trong một JVM, cache dựa trên `ConcurrentMap` thường dễ cấu hình và quan sát.

Các lớp có tên gần giống nhau nhưng trách nhiệm khác nhau:

- **`ConcurrentMapCache`**: một vùng cache cụ thể, lưu key/value dựa trên `ConcurrentMap`.
- **`ConcurrentMapCacheManager`**: tạo và quản lý các `ConcurrentMapCache` theo tên; hỗ trợ chế độ tạo cache động hoặc khai báo trước danh sách cache.
- **`SimpleCacheManager`**: quản lý collection các `Cache` đã được tạo sẵn. Nó không tự chọn storage hay tự tạo cache theo tên.
- **`NoOpCacheManager`**: cache không lưu dữ liệu; thường dùng để tắt caching trong một số test hoặc môi trường.

| Implementation | Cách quản lý | Phù hợp khi | Giới hạn chính |
|---|---|---|---|
| `ConcurrentMapCacheManager` | Tạo `ConcurrentMapCache` theo tên; dynamic hoặc static | Demo, test hit/miss, local development | Không có TTL/size policy tự động, persistence hay chia sẻ nhiều JVM |
| `SimpleCacheManager` | Nhận collection `Cache` đã tạo sẵn qua `setCaches` | Muốn khai báo chính xác từng cache object | Cần tự tạo từng cache; manager không phải storage engine |
| `NoOpCacheManager` | Trả cache no-op, không lưu entry | Test logic không phụ thuộc caching | Không kiểm tra được hit, eviction hoặc reuse |

**Phân biệt:** Spring Boot gọi provider auto-configured đơn giản là *Simple*; provider đó thường dựa trên `ConcurrentMapCacheManager`. Nó **không đồng nghĩa** với lớp `SimpleCacheManager`. Khi debug, hãy xem class thực tế của bean `CacheManager`.

## 2. ConcurrentMapCacheManager: cách đơn giản nhất để bắt đầu

`ConcurrentMapCacheManager` dùng các `ConcurrentMapCache` và tạo cache khi được yêu cầu. Constructor không đối số chọn chế độ **dynamic**:

~~~java
@Bean
CacheManager cacheManager() {
    return new ConcurrentMapCacheManager();
}
~~~

Khi code yêu cầu `getCache("books")`, manager có thể tạo cache `books` nếu chưa có. Cách này tiện khi demo hoặc khi danh sách cache chưa cố định.

Nếu muốn chỉ cho phép một số cache name đã biết, dùng constructor nhận tên:

~~~java
@Bean
CacheManager cacheManager() {
    return new ConcurrentMapCacheManager("books", "authors");
}
~~~

Đây là **static mode**: manager chỉ quản lý các tên đã khai báo, không tự tạo vùng cache mới cho tên ngoài danh sách. Ví dụ `@Cacheable("book")` bị gõ nhầm trong khi chỉ đăng ký `books` có thể dẫn tới lỗi khi cache operation cần vùng `book`. Cấu hình tĩnh giúp phát hiện lỗi tên cache thay vì vô tình tạo thêm vùng mới.

Hai ví dụ trên là mã cấu hình Spring, cần import `CacheManager`, `ConcurrentMapCacheManager`, đăng ký `@Bean` trong configuration và bật annotation caching bằng `@EnableCaching` nếu dùng `@Cacheable`.

### Dùng @Cacheable với cache in-memory

~~~java
@Service
public class BookService {
    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "books", key = "#p0")
    public Book findByIsbn(String isbn) {
        return repository.findByIsbn(isbn);
    }
}
~~~

Đây là mã minh họa tích hợp Spring; `Book` và `BookRepository` là kiểu nghiệp vụ của ứng dụng. Lần đầu gọi ISBN chưa có trong cache, phương thức chạy và kết quả được lưu. Lần gọi sau với cùng key có thể nhận kết quả từ cache mà không truy vấn repository.

Ứng dụng vẫn cần `@EnableCaching` và method phải được gọi qua cơ chế interception của Spring. Với proxy mode mặc định, self-invocation (method gọi `this.findByIsbn(...)` trong cùng bean) thường không đi qua proxy, nên không kích hoạt cache advice.

## 3. SimpleCacheManager: khai báo từng cache object

Khác với `ConcurrentMapCacheManager`, `SimpleCacheManager` nhận **các đối tượng `Cache` đã có sẵn**:

~~~java
import java.util.List;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.support.SimpleCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SimpleCacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        SimpleCacheManager manager = new SimpleCacheManager();
        manager.setCaches(List.of(
                new ConcurrentMapCache("books"),
                new ConcurrentMapCache("authors")
        ));
        return manager;
    }
}
~~~

Đây là cấu hình Spring, không phải chương trình Java độc lập. Khi bean được Spring quản lý, lifecycle `InitializingBean`/`afterPropertiesSet()` giúp `SimpleCacheManager` khởi tạo danh sách cache đã cung cấp. Nếu tự tạo manager ngoài Spring container, cần gọi cơ chế initialize theo Javadoc trước khi sử dụng.

`SimpleCacheManager` không có map lưu dữ liệu riêng. Trong ví dụ, **`ConcurrentMapCache` mới là cache object thực sự**; manager chỉ quản lý collection đó. Có thể cung cấp các implementation `Cache` khác nhau nếu chúng đáp ứng contract của Spring Cache.

- Chọn `ConcurrentMapCacheManager` khi muốn manager tự tạo cache theo tên, hoặc muốn static mode bằng danh sách tên.
- Chọn `SimpleCacheManager` khi đã có các `Cache` object cụ thể và muốn đăng ký chính xác chúng.
- Nếu cần TTL, giới hạn dung lượng, eviction policy, metrics hoặc persistence, chọn provider có tính năng tương ứng.

## 4. Cache in-memory lưu ở đâu và có giới hạn gì?

`ConcurrentMapCache` dùng `ConcurrentMap` làm cấu trúc lưu trữ; implementation mặc định dựa trên `ConcurrentHashMap`. Cache nằm **trong bộ nhớ của process/JVM đang chạy**:

~~~text
Spring Bean → CacheInterceptor → CacheManager
                                  |
                                  v
                         ConcurrentMapCache
                                  |
                                  v
                         ConcurrentMap<Key, Value>
                                  |
                                  v
                               JVM RAM
~~~

Điều này có các hệ quả:

1. **Restart mất cache:** dữ liệu không tự được lưu xuống database hay file.
2. **Mỗi JVM có cache riêng:** hai instance ứng dụng không tự chia sẻ entry. Pod A nạp `books[7]` không có nghĩa pod B đã có entry.
3. **Không có TTL/size policy nâng cao:** entry không tự hết hạn theo thời gian hoặc bị loại bỏ theo dung lượng như Caffeine nếu không bổ sung cơ chế riêng.
4. **Bộ nhớ có thể tăng:** nếu key phát sinh liên tục và không có invalidation/clear, map có thể giữ nhiều entry trong suốt vòng đời process.
5. **Giá trị mặc định được giữ theo reference:** `ConcurrentMapCacheManager` mặc định `storeByValue=false`. Nếu caller sửa object mutable đã lấy ra, nội dung trong cache có thể bị thay đổi ngoài ý muốn.
6. **Thread-safe map không đồng nghĩa nghiệp vụ atomic:** ConcurrentHashMap hỗ trợ thao tác đồng thời của map; nó không tự bảo vệ transaction nhiều bước, side effect hoặc consistency giữa nhiều service.

Nên ưu tiên DTO/record bất biến hoặc defensive copy khi caller có thể sửa object. Nếu bật store-by-value, giá trị cần đáp ứng yêu cầu serialization của implementation.

`ConcurrentMapCacheManager` mặc định cho phép lưu `null` thông qua wrapper nội bộ vì `ConcurrentHashMap` không cho phép value null trực tiếp. Có thể thay đổi bằng `setAllowNullValues(false)`; khi đổi cấu hình, các cache hiện hữu có thể được reset. Cần phân biệt cache miss với entry đại diện cho null và với NoOp cache không lưu gì.

## 5. Cấu hình cache đơn giản trong Spring Boot

Nếu dùng Spring Boot và không có cache provider/library cụ thể khác trên classpath, Boot có thể auto-configure **Simple provider dùng ConcurrentHashMap trong bộ nhớ**. Có thể khai báo tên cache trong `application.properties`:

~~~properties
spring.cache.cache-names=books,authors
~~~

Hoặc YAML:

~~~yaml
spring:
  cache:
    cache-names:
      - books
      - authors
~~~

Khi đặt danh sách tên tĩnh, nếu ứng dụng yêu cầu cache không được khai báo, lỗi có thể chỉ xuất hiện khi cache operation thực sự cần vùng đó. Vì vậy, nên kiểm tra tên cache trong integration test.

Lưu ý:

- Cần bật caching bằng `@EnableCaching` (hoặc cấu hình tương đương).
- Boot auto-configure manager theo provider detection khi không có bean `CacheManager` hay resolver phù hợp do ứng dụng cung cấp.
- `spring.cache.cache-names` không phải nơi đặt TTL hoặc max-size cho `ConcurrentMapCacheManager`.
- `CacheManagerCustomizer` của Boot áp dụng cho manager mà Boot auto-configure phù hợp; nếu tự khai báo manager khác, đừng giả định customizer tự cấu hình nó.
- `spring.cache.type` có thể ép loại provider cho manager do Boot auto-configure; không xem property này là cách ghi đè mọi cache manager tùy chỉnh.

Simple provider phù hợp để bắt đầu và tìm hiểu cache. Khi cần cache production, hãy chọn provider có tính năng cần thiết và đọc tài liệu cấu hình của provider đó.

## 6. Kiểm thử có cache thật và kiểm thử không cache

Hai mục tiêu test thường bị trộn lẫn:

| Mục tiêu | Nên dùng | Điều muốn xác nhận |
|---|---|---|
| Test logic service mà không phụ thuộc cache | `NoOpCacheManager` hoặc Boot no-op configuration | Method nghiệp vụ vẫn chạy và trả kết quả đúng |
| Test `@Cacheable` hit/miss, `@CacheEvict`, `@CachePut` | `ConcurrentMapCacheManager` hoặc `SimpleCacheManager` thật | Entry được lưu, tái sử dụng, cập nhật và xóa đúng |
| Test provider production | Provider thật hoặc integration environment tương ứng | TTL, serialization, network, cluster và eviction |
| Test chỉ mock repository/service | Mock phù hợp phạm vi | Tập trung contract component; không chứng minh cache proxy hoạt động |

### NoOpCacheManager

`NoOpCacheManager` là implementation không lưu entry. Nó vẫn đáp ứng API cache để code annotation có thể chạy, nhưng `put` không giữ giá trị để lần sau tái sử dụng. Method có `@Cacheable` vì vậy được gọi lại ở mỗi lần invocation.

Đây là lựa chọn hữu ích khi test logic không cần xác minh caching hoặc khi muốn tắt cache trong một cấu hình test cụ thể. **Không dùng NoOpCacheManager để kiểm tra cache hit** vì nó được thiết kế để không lưu entry.

### Spring Boot test có thể tắt cache tự động

Nếu manager do Boot auto-configure, có thể dùng `@AutoConfigureCache` trong test Spring Boot để thay bằng no-op implementation (tùy phiên bản Boot và test starter). Một cách khác là cấu hình:

~~~properties
spring.cache.type=none
~~~

Các cách này nhắm tới **cache auto-configuration của Boot**. Nếu ứng dụng tự định nghĩa `CacheManager`, hãy tách cache configuration thành lớp riêng và cung cấp test configuration thay thế phù hợp; không giả định property no-op tự ghi đè bean tùy chỉnh.

### Test cần xác minh caching phải dùng manager có lưu trữ

~~~java
@SpringBootTest
class BookServiceCacheTest {
    @Autowired
    BookService service;

    @Autowired
    CacheManager cacheManager;

    @BeforeEach
    void clearCache() {
        Cache cache = cacheManager.getCache("books");
        if (cache != null) {
            cache.clear();
        }
    }

    @Test
    void reusesCachedBook() {
        Book first = service.findByIsbn("ISBN-7");
        Book second = service.findByIsbn("ISBN-7");

        assertEquals(first, second);
        assertEquals(1, service.getRepositoryCallCount());
    }
}
~~~

Đây là mã minh họa test cần project cung cấp `BookService`, counter và imports JUnit/Spring. `service` phải là bean lấy từ Spring context để lời gọi đi qua proxy; tự tạo `new BookService(...)` sẽ không tự kích hoạt caching advice. Clear cache giữa test để kết quả không phụ thuộc thứ tự chạy hoặc context được tái sử dụng. Test hit/miss phải kiểm tra số lần repository/loader được gọi, không chỉ kiểm tra hai kết quả bằng nhau.

## 7. Java 17 chạy độc lập: cache in-memory và no-op

Chương trình sau mô phỏng hai chính sách bằng JDK, **không sử dụng Spring annotation hoặc Spring Cache classes**. Nó giúp nhìn thấy khác biệt giữa cache lưu trong map và cache no-op.

Tạo tệp **`SimpleCacheDemo.java`**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class SimpleCacheDemo {
    static final class InMemoryCache {
        private final ConcurrentMap<String, String> values =
                new ConcurrentHashMap<>();

        String getOrLoad(String key, Supplier<String> loader) {
            return values.computeIfAbsent(key, ignored -> loader.get());
        }

        void clear() {
            values.clear();
        }

        int size() {
            return values.size();
        }
    }

    static final class NoOpCache {
        String getOrLoad(String key, Supplier<String> loader) {
            return loader.get();
        }
    }

    public static void main(String[] args) {
        AtomicInteger loads = new AtomicInteger();
        InMemoryCache cache = new InMemoryCache();

        String first = cache.getOrLoad("ISBN-7", () -> {
            loads.incrementAndGet();
            return "Java";
        });
        String second = cache.getOrLoad("ISBN-7", () -> {
            loads.incrementAndGet();
            return "unused";
        });
        System.out.printf(
                "simple: first=%s, second=%s, loaderCalls=%d, entries=%d%n",
                first, second, loads.get(), cache.size());

        cache.clear();
        String afterClear = cache.getOrLoad("ISBN-7", () -> {
            loads.incrementAndGet();
            return "Java";
        });
        System.out.printf(
                "simple after clear: value=%s, loaderCalls=%d, entries=%d%n",
                afterClear, loads.get(), cache.size());

        AtomicInteger noOpLoads = new AtomicInteger();
        NoOpCache noOp = new NoOpCache();
        String noOpFirst = noOp.getOrLoad("ISBN-7", () -> {
            noOpLoads.incrementAndGet();
            return "Java";
        });
        String noOpSecond = noOp.getOrLoad("ISBN-7", () -> {
            noOpLoads.incrementAndGet();
            return "Java";
        });
        System.out.printf(
                "no-op: first=%s, second=%s, loaderCalls=%d%n",
                noOpFirst, noOpSecond, noOpLoads.get());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac --release 17 SimpleCacheDemo.java
java SimpleCacheDemo
~~~

Stdout **chính xác**:

~~~text
simple: first=Java, second=Java, loaderCalls=1, entries=1
simple after clear: value=Java, loaderCalls=2, entries=1
no-op: first=Java, second=Java, loaderCalls=2
~~~

Phân tích:

1. Lần đầu cache trống, loader chạy và lưu `Java` dưới key `ISBN-7`.
2. Lần hai cùng key trả giá trị đã lưu; loader không chạy lại.
3. Sau `clear()`, entry bị xóa; lần tiếp theo loader chạy lại và cache có một entry mới.
4. `NoOpCache` không lưu gì, nên cả hai lần gọi đều thực thi loader.
5. `ConcurrentHashMap.computeIfAbsent` là cơ chế của JDK; **không suy ra mọi CacheManager/provider Spring có cùng locking semantics**.

Đây là demo một process, một key và một luồng gọi tuần tự. Nó không mô phỏng TTL, eviction policy, persistence, cache cluster hoặc Spring proxy.

## 8. Chọn loại cache theo môi trường

| Môi trường/nhu cầu | Lựa chọn gợi ý | Lưu ý |
|---|---|---|
| Unit test không kiểm tra cache | `NoOpCacheManager` | Mỗi invocation chạy method; không assert cache hit |
| Integration test xác minh annotation | `ConcurrentMapCacheManager` hoặc `SimpleCacheManager` | Clear cache giữa test; gọi qua Spring bean |
| Demo, học tập, local development | `ConcurrentMapCacheManager` | Dễ cấu hình; cache mất khi JVM dừng |
| Ứng dụng nội bộ nhỏ, một JVM, dữ liệu có thể tái tạo và không cần TTL | Có thể dùng ConcurrentMap cache | Theo dõi memory; xác nhận yêu cầu vận hành |
| Cache local production cần TTL, max size và eviction | Cân nhắc Caffeine | Cấu hình expiry/size/metrics |
| Nhiều application instance cần chia sẻ cache | Redis hoặc distributed provider phù hợp | Thiết kế serialization, key prefix, network và invalidation |
| Cần persistence hoặc policy đặc thù | Provider có tính năng tương ứng | Kiểm tra failure mode, durability và consistency |

Không có ngưỡng số request chung để kết luận cache in-memory có đủ phù hợp. Hãy xét **số key, kích thước value, tốc độ thay đổi dữ liệu, số instance, mức stale chấp nhận được, RAM và khả năng quan sát**.

Không nên chọn cache đơn giản nếu dữ liệu phải tồn tại sau restart, nhiều instance cần chia sẻ entry, cần TTL/TTI, maximum size, policy loại bỏ tự động, metrics hoặc SLA vận hành. Khi yêu cầu vượt khả năng cache map đơn giản, hãy chuyển sang provider thích hợp.

## 9. Lỗi thường gặp

- **Nhầm `SimpleCacheManager` với provider Boot Simple:** một lớp quản lý cache object có sẵn khác với auto-configured concurrent-map provider.
- **Dùng `NoOpCacheManager` rồi mong cache hit:** no-op không lưu entry; mọi lần gọi đều vào method.
- **Dùng cache đơn giản trong cluster:** mỗi JVM giữ map riêng; node khác không tự thấy entry hoặc eviction.
- **Quên clear cache giữa test:** test phụ thuộc thứ tự, dữ liệu test trước hoặc Spring context được tái sử dụng.
- **Test bằng cách tạo service bằng `new`:** bỏ qua proxy, khiến annotation cache không được thực thi.
- **Gõ sai cache name trong static mode:** tên không đăng ký có thể lỗi lúc operation cần vùng đó.
- **Tưởng `ConcurrentMapCacheManager` có TTL mặc định:** nó không tự đặt thời gian sống hoặc size policy.
- **Trả mutable object cho nhiều caller:** cache mặc định giữ reference; caller có thể vô tình sửa dữ liệu đang nằm trong cache.
- **Cache mọi thứ không đo lường:** key/value tăng liên tục gây áp lực heap và GC.
- **Dùng cache để thay nguồn dữ liệu:** cache in-memory có thể mất khi restart hoặc eviction; dữ liệu nghiệp vụ cần source of truth riêng.
- **Nhầm thread-safe map với transaction-safe business logic:** nhiều thao tác nghiệp vụ vẫn cần transaction, constraint hoặc đồng bộ riêng.

## 10. Checklist trước khi chọn

1. Test cần **tắt cache** hay cần **kiểm tra hit/miss thật**?
2. Có bao nhiêu cache name, cần dynamic creation hay danh sách cố định?
3. Dữ liệu có thể mất khi restart không?
4. Chỉ một JVM hay nhiều instance cần chia sẻ?
5. Cần TTL, maximum size, eviction policy hoặc metrics không?
6. Value có mutable không; có chấp nhận lưu theo reference không?
7. Test có clear cache và gọi service qua Spring proxy không?
8. Boot đang auto-configure manager hay ứng dụng đã tự khai báo bean?
9. Cache provider có được kiểm thử với failure, stale data và concurrency không?
10. Khi cache unavailable hoặc trống, nghiệp vụ vẫn đọc được dữ liệu từ nguồn có thẩm quyền chứ?

**Quy tắc chọn nhanh:** dùng `NoOpCacheManager` khi cần vô hiệu hóa cache; dùng `ConcurrentMapCacheManager` khi muốn cache in-memory tạo theo tên; dùng `SimpleCacheManager` khi muốn cung cấp danh sách `Cache` object tường minh. Khi cần TTL/size/distributed sharing, chọn provider được thiết kế cho các yêu cầu đó.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `ConcurrentMapCacheManager()` không truyền tên cache và `ConcurrentMapCacheManager("books")` khác nhau ở chế độ tạo cache thế nào?

**Câu 2.** `SimpleCacheManager` có tự tạo `ConcurrentMapCache` khi nhận một tên bất kỳ không?

**Câu 3.** Vì sao `NoOpCacheManager` phù hợp cho một số test nhưng không phù hợp để kiểm tra `@Cacheable` hit?

**Câu 4.** Hai pod cùng dùng `ConcurrentMapCacheManager` local có chia sẻ entry không?

**Câu 5.** Trong `ConcurrentMapCacheManager`, tại sao cache value mutable có thể bị thay đổi bởi caller?

**Câu 6.** Khi nào nên chuyển từ concurrent-map cache sang Caffeine hoặc Redis?

**Đáp án:**

1. Không truyền tên là **dynamic mode**, cache được tạo lười khi yêu cầu; truyền tên là **static mode**, chỉ quản lý tên đã khai báo.
2. **Không.** `SimpleCacheManager` nhận collection cache object đã tạo qua `setCaches`.
3. No-op không giữ entry nên method chạy lại mỗi lần; test hit cần manager có lưu trữ thật.
4. **Không.** Mỗi JVM có map riêng, trừ khi cấu hình backend dùng chung.
5. Mặc định `storeByValue=false` nên cache giữ reference; sửa object có thể thay đổi object đang nằm trong cache.
6. Caffeine khi cần cache local có TTL/size/eviction nâng cao; Redis hoặc distributed provider khi cần chia sẻ nhiều instance.

## 12. Tài liệu tham khảo

- Spring Framework Reference — Configuring the Cache Storage, JDK ConcurrentMap-based Cache: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework Javadoc — `SimpleCacheManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/SimpleCacheManager.html
- Spring Framework Javadoc — `ConcurrentMapCacheManager` (dynamic/static mode, null và store-by-value): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework Javadoc — `NoOpCacheManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/NoOpCacheManager.html
- Spring Boot Reference — Caching auto-configuration, Simple provider và Testing: https://docs.spring.io/spring-boot/reference/io/caching.html

**Ghi nhớ:** `ConcurrentMapCacheManager` là lựa chọn dễ bắt đầu cho cache in-memory; `SimpleCacheManager` phù hợp khi muốn đăng ký các cache object có sẵn; `NoOpCacheManager` dùng để tắt lưu cache trong test. Hãy dùng cache map đơn giản khi dữ liệu có thể tái tạo, phạm vi phù hợp và không cần policy nâng cao. Khi có yêu cầu TTL, giới hạn dung lượng, persistence hoặc chia sẻ nhiều instance, chuyển sang provider phù hợp và kiểm thử hành vi của nó.