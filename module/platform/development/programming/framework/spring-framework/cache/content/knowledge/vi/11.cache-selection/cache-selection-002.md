# Nhiều CacheManager trong cùng ApplicationContext — lựa chọn vùng cache trong Spring

## 1. Tổng quan

Trong Spring Framework, `CacheManager` là interface quản lý các vùng `Cache`. Mỗi `@Cacheable`, `@CachePut` và `@CacheEvict` phải được gắn với những vùng cache cụ thể. Một ứng dụng có thể có **nhiều bean CacheManager trong cùng một ApplicationContext**: chẳng hạn cache dữ liệu tra cứu sử dụng Caffeine tại mỗi JVM, và cache dữ liệu được chia sẻ sử dụng Redis; hoặc hai manager cùng một provider nhưng có chính sách khác nhau.

**Điểm cốt lõi: `cacheNames = "books"` không tự xác định CacheManager nào sẽ được dùng.** Tên `books` chỉ có nghĩa bên trong manager đã được chọn. Việc sử dụng đúng cache phải xác định bộ ba:

1. **CacheManager** — bean/provider chịu trách nhiệm quản lý vùng cache.
2. **Cache name** — vùng logic, ví dụ `books`, `prices`, `reports`.
3. **Cache key** — entry cụ thể, ví dụ `"ISBN-7"` hoặc `ProductId(7)`.

Với hai manager có vùng cache trùng tên, `managerA.getCache("books")` và `managerB.getCache("books")` có thể là hai kho dữ liệu độc lập. Nếu hai manager cấu hình cùng backend, endpoint, namespace, prefix và serializer, chúng lại có thể dùng chung dữ liệu. **Độc lập hay chia sẻ là kết quả cấu hình provider**, không chỉ dựa trên tên bean.

Bài học tập trung cách chọn manager tĩnh, chọn manager mặc định, `@CacheConfig`, chọn động với `CacheResolver`, `CompositeCacheManager`, Spring Boot và những lỗi nhất quán thường gặp.

## 2. Ba tên khác nhau thường bị nhầm

~~~java
@Cacheable(cacheNames = "books",
           cacheManager = "fastCacheManager",
           key = "#p0")
public Book findByIsbn(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

Đây là **mã minh họa Spring**, không tự chạy với `javac` vì `Book`, `repository` và các cấu hình chưa được cung cấp.

| Thuộc tính/đối tượng | Ý nghĩa | Giá trị trong ví dụ |
|---|---|---|
| `cacheManager` | Tên bean `CacheManager` được đăng ký với Spring | `fastCacheManager` |
| `cacheNames` | Tên `Cache` do manager phân giải | `books` |
| `key` | Biểu thức SpEL để chọn entry | `#p0`, tham số đầu tiên |
| Cache value | Kết quả được lưu | `Book` |

Sơ đồ khái niệm:

~~~text
Spring ApplicationContext
│
├── "fastCacheManager"     : CacheManager A
│   ├── Cache "books"      : {"ISBN-7" → Book A}
│   └── Cache "authors"    : {...}
│
└── "durableCacheManager"  : CacheManager B
    ├── Cache "books"      : {"ISBN-7" → Book B}
    └── Cache "reports"    : {...}
~~~

Tên `durable` chỉ là nhãn minh họa; **không phải mọi bean có tên durable đều có persistence**. Nếu A và B độc lập, gọi evict ở `fastCacheManager/books/ISBN-7` không tự xóa `durableCacheManager/books/ISBN-7`.

Cũng không nên nhầm `@Cacheable(cacheNames = {"books", "authors"})` với việc chọn nhiều manager: danh sách này chỉ nói tới **nhiều vùng cache do cache resolver hiện hành trả về**, thường qua cùng manager.

## 3. Spring chọn CacheManager nào khi không nêu rõ?

`@EnableCaching` kích hoạt annotation-driven caching bằng cache interceptor và proxy/advice. Khi chỉ có một bean `CacheManager`, Spring có thể tìm bean theo type và dùng như default. Khi **nhiều bean** cùng tồn tại, một operation không khai báo manager phải có cơ chế chọn mặc định hợp lệ.

Không thể mặc định rằng Spring sẽ:
- tìm manager có cache name trùng với `cacheNames`;
- chọn bean theo thứ tự khai báo `@Bean` hoặc thứ tự quét package;
- load-balance các cache operation qua nhiều manager;
- chọn manager có dữ liệu cache hit trước.

Một cấu hình mơ hồ có thể làm việc khởi tạo hoặc lời gọi cache phát sinh lỗi (thời điểm tùy phiên bản và cách wiring). Nên **định nghĩa chính sách minh bạch**, thay vì trông cậy vào thứ tự ngẫu nhiên.

| Cấp độ | API | Ý nghĩa |
|---|---|---|
| Trên operation | `@Cacheable(cacheManager = "beanName")` | Chọn manager cố định cho method |
| Trên lớp | `@CacheConfig(cacheManager = "beanName")` | Chia sẻ lựa chọn cho các operation cùng class |
| Mặc định toàn hệ thống annotation cache | `CachingConfigurer.cacheManager()` | Manager mặc định cho operation không override |
| Chọn động tại runtime | `cacheResolver = "beanName"` | Chọn một hoặc nhiều cache theo invocation |
| Fallback theo tên cache | `CompositeCacheManager` | Chọn delegate theo thứ tự, không tự fan-out |

`@Primary` ưu tiên bean khi Spring inject theo type trong một số trường hợp, **không phải bộ điều phối cache theo nghiệp vụ**. Nếu hệ thống có nhiều manager, việc cấu hình mặc định qua `CachingConfigurer` và override rõ ràng bằng tên bean dễ hiểu hơn.

## 4. Đăng ký hai CacheManager và mặc định rõ bằng CachingConfigurer

Trong file `CacheManagersConfiguration.java` của ứng dụng Spring:

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CachingConfigurer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheManagersConfiguration implements CachingConfigurer {

    @Bean("fastCacheManager")
    @Override
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books", "authors");
    }

    @Bean("durableCacheManager")
    public CacheManager durableCacheManager() {
        return new ConcurrentMapCacheManager("books", "reports");
    }
}
~~~

Đây là **đoạn cấu hình cần Spring Framework**, không phải Java thuần. Cả hai manager là `ConcurrentMapCacheManager` với bộ nhớ riêng trong JVM: không chia sẻ đa instance và không tự có TTL. Đừng suy luận rằng `durableCacheManager` trong ví dụ dùng kho lưu trữ bền vững.

Giải thích:

- `@Bean("fastCacheManager")` và `@Bean("durableCacheManager")` đăng ký hai tên bean khác nhau.
- `@EnableCaching` bật cơ chế cache annotation; việc khai báo CacheManager một mình chưa đủ để chắc rằng các lời gọi đều được intercept.
- `CachingConfigurer.cacheManager()` trả về manager mặc định; Spring có thể tạo default cache resolver dựa trên manager này.
- Phương thức `cacheManager()` đồng thời có `@Bean` để manager được container quản lý vòng đời. Đây là mẫu được Spring Javadoc hướng dẫn.
- `ConcurrentMapCacheManager("books", ...)` giúp khai báo tên các vùng cache riêng; hai instance vẫn độc lập dù cùng tồn tại tên `books`.

**Cảnh báo lifecycle:** `CachingConfigurer` được khởi tạo sớm. Tránh phụ thuộc phức tạp thông qua field injection ngay trong configurer; nếu cần dependencies, xem hướng dẫn `ObjectProvider`/lazy access. Với `@Configuration(proxyBeanMethods=false)`, **đừng gọi trực tiếp `cacheManager()` như một method Java để lấy lại bean**: có nguy cơ tạo instance ngoài ý muốn. Hãy inject bean theo tên hoặc để framework tự quản lý.

Trong production, có thể thay bằng Caffeine/Redis/nhà cung cấp khác, nhưng phải cấu hình từng manager về TTL, serializer, key-prefix, dung lượng và kết nối. Tên bean không quy định chính sách của provider.

## 5. Lựa chọn tĩnh trên @Cacheable, @CachePut và @CacheEvict

Hai phương thức đọc dùng cùng tên cache nhưng khác manager:

~~~java
@Cacheable(cacheNames = "books",
           cacheManager = "fastCacheManager",
           key = "#p0")
public Book findFast(String isbn) {
    return repository.findByIsbn(isbn);
}

@Cacheable(cacheNames = "books",
           cacheManager = "durableCacheManager",
           key = "#p0")
public Book findDurable(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

Nếu hai manager thực sự độc lập, lần đầu gọi `findFast("ISBN-7")` là cache miss ở A; lần đầu `findDurable("ISBN-7")` vẫn có thể miss ở B. Cache hit ở A không tạo cache hit tự động ở B.

Để read và eviction nhất quán:

~~~java
@Cacheable(cacheNames = "books",
           cacheManager = "fastCacheManager",
           key = "#p0")
public Book get(String isbn) {
    return repository.findByIsbn(isbn);
}

@CacheEvict(cacheNames = "books",
            cacheManager = "fastCacheManager",
            key = "#p0")
public void delete(String isbn) {
    repository.deleteByIsbn(isbn);
}
~~~

`@CachePut` cũng có thuộc tính `cacheManager`. Tất cả phương thức đọc, ghi và xóa **cùng một entry** cần nhất quán **manager + cacheName + key**; nếu evict ở B nhưng đọc từ A, entry cũ ở A có thể tồn tại.

`#p0` lấy tham số đầu tiên theo vị trí nên không phụ thuộc metadata tên tham số Java `-parameters`. Tuy nhiên, **key cần bao gồm mọi dữ liệu ảnh hưởng kết quả**: tenant, locale, version, phân quyền nếu phù hợp. Manager đúng vẫn không cứu được key thiếu tenant.

**Cẩn thận với key mặc định:** `get(long id)` có một tham số nên key mặc định thường là `id`; `update(long id, String name)` có hai tham số thường tạo `SimpleKey(id, name)`. Nếu `@CachePut` trên update bỏ trống `key`, nó có thể không cập nhật entry cùng key với method get. Đừng chỉ đồng bộ manager mà quên key.

## 6. @CacheConfig — chia sẻ lựa chọn ở mức lớp

Khi phần lớn method của một service dùng một manager:

~~~java
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
@CacheConfig(cacheNames = "books",
             cacheManager = "durableCacheManager")
class DurableBookService {

    @Cacheable(key = "#p0")
    public Book get(String isbn) {
        return repository.findByIsbn(isbn);
    }

    @CacheEvict(key = "#p0")
    public void invalidate(String isbn) {
        repository.invalidate(isbn);
    }

    @Cacheable(cacheManager = "fastCacheManager", key = "#p0")
    public Book preview(String isbn) {
        return repository.findPreview(isbn);
    }
}
~~~

Mã cần `Book`, repository và các bean Spring khác. `@CacheConfig` áp dụng giá trị mặc định cho **cache operations của class**, không tự gắn `@Cacheable` vào tất cả method.

Thứ tự ưu tiên được Spring mô tả:

1. Mặc định toàn cục (ví dụ `CachingConfigurer`).
2. `@CacheConfig` trên class.
3. Tùy chỉnh ngay trên annotation của method — **ưu tiên cao nhất**.

Vì vậy, `get` và `invalidate` ở ví dụ sử dụng `durableCacheManager`; `preview` override thành `fastCacheManager`. Nếu method không nêu `cacheNames` riêng, nó có thể kế thừa `books` từ class.

## 7. CacheResolver — chọn động theo invocation

`cacheManager` trên annotation là lựa chọn **tĩnh**. Nếu cần phân giải cache theo runtime arguments, domain context hay tenant routing, dùng `CacheResolver`.

Hợp đồng:

~~~java
Collection<? extends Cache> resolveCaches(
        CacheOperationInvocationContext<?> context);
~~~

Resolver nhận metadata operation và args, trả về `Collection` các `Cache`. Implementation **phải thread-safe**.

Ví dụ routing theo tham số đầu tiên `channel` (giả định đây là giá trị đáng tin từ nghiệp vụ, đã xác thực/ủy quyền):

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.interceptor.CacheOperationInvocationContext;
import org.springframework.cache.interceptor.CacheResolver;
import org.springframework.stereotype.Component;

@Component("channelCacheResolver")
class ChannelCacheResolver implements CacheResolver {

    private final CacheManager fastManager;
    private final CacheManager internalManager;

    ChannelCacheResolver(
            @Qualifier("fastCacheManager") CacheManager fastManager,
            @Qualifier("durableCacheManager") CacheManager internalManager) {
        this.fastManager = fastManager;
        this.internalManager = internalManager;
    }

    @Override
    public Collection<? extends Cache> resolveCaches(
            CacheOperationInvocationContext<?> context) {

        Object firstArg = context.getArgs()[0];
        if (!(firstArg instanceof String channel)) {
            throw new IllegalStateException("Expected channel argument");
        }
        CacheManager selected = "public".equals(channel)
                ? fastManager : internalManager;

        List<Cache> found = new ArrayList<>();
        for (String name : context.getOperation().getCacheNames()) {
            Cache cache = selected.getCache(name);
            if (cache == null) {
                throw new IllegalStateException(
                        "Missing cache " + name + " in selected manager");
            }
            found.add(cache);
        }
        return found;
    }
}
~~~

Annotation sử dụng resolver:

~~~java
@Cacheable(cacheNames = "books",
           cacheResolver = "channelCacheResolver",
           key = "#p1")
public Book load(String channel, String isbn) {
    return repository.load(channel, isbn);
}
~~~

Resolver chọn manager dựa trên `channel` (đối số thứ nhất), còn `#p1` chọn ISBN (đối số thứ hai). Khi các channel chia sẻ manager hoặc có nhiều tenant khác nhau, cần thiết kế key/name sao cho không lẫn dữ liệu. Ví dụ chọn kênh theo chuỗi chỉ để minh họa; production nên validate enum/domain context và không để chuỗi client tự quyết vùng có dữ liệu nhạy cảm.

**Không khai báo `cacheManager` và `cacheResolver` cùng một operation.** Hai thuộc tính loại trừ nhau; Spring báo lỗi cấu hình vì custom resolver đã quyết định các `Cache` thực sự sẽ được dùng. Tương tự, nếu dùng custom default `CachingConfigurer.cacheResolver()`, resolver là cơ chế ưu tiên khi so với `cacheManager()` ở configurer.

Resolver phải được dùng nhất quán cho method đọc, put và evict có cùng entry. Chỉ định resolver cho đọc nhưng để eviction dùng manager mặc định thường tạo stale data.

## 8. CompositeCacheManager: fallback theo vùng cache, không phải multi-write

`CompositeCacheManager` cho phép khai báo một manager tổng hợp với các delegate:

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.support.CompositeCacheManager;

// managerA, managerB được cấu hình và cung cấp bởi ứng dụng.
CacheManager combined =
        new CompositeCacheManager(managerA, managerB);
~~~

Composite duyệt delegate **theo thứ tự**, chọn manager đầu tiên trả về `Cache` cho tên yêu cầu. **Nó không tự fan-out get/put/evict lên tất cả delegates**, và cũng không dùng manager B khi cache key bị miss ở A: nó đang phân giải **tên vùng cache**, không tìm entry theo key trên mọi backend.

**Bẫy quan trọng:** nhiều implementation CacheManager tự tạo cache nếu gặp tên mới; nếu delegate đầu tiên luôn trả về `Cache` cho bất kỳ tên nào, delegate thứ hai gần như không được chọn. Javadoc yêu cầu delegate trả `null` khi không biết cache name; với provider hỗ trợ, hãy cấu hình static cache names và kiểm tra thứ tự.

Nếu mục tiêu là **routing theo runtime arguments**, dùng `CacheResolver`. Nếu mục tiêu là **xóa hai manager**, dùng hai operation có định danh cụ thể hoặc một tầng orchestration phù hợp, không dựa vào `CompositeCacheManager`.

## 9. Cần xóa dữ liệu ở hai manager sau một lần update?

Khi một thực thể được cache độc lập trong cả hai manager, một lần cập nhật nguồn có thể cần invalidate hai vùng:

~~~java
@Caching(evict = {
    @CacheEvict(cacheNames = "books",
                cacheManager = "fastCacheManager",
                key = "#p0"),
    @CacheEvict(cacheNames = "books",
                cacheManager = "durableCacheManager",
                key = "#p0")
})
public void renameBook(String isbn, String newTitle) {
    repository.renameBook(isbn, newTitle);
}
~~~

Đây là mã minh họa tích hợp Spring; cần import `org.springframework.cache.annotation.Caching` và `CacheEvict`.

Các giới hạn:

- Với `@CacheEvict` mặc định, method ném exception ra ngoài thì eviction-after không diễn ra.
- **Hai eviction không tạo giao dịch phân tán nguyên tử**: một backend có thể xóa thành công, backend còn lại báo lỗi.
- Database transaction commit và cache eviction có thứ tự chịu ảnh hưởng advice, transaction-aware cache và provider; đừng mặc nhiên cho rằng hai cache chỉ xóa sau commit.
- Nếu hai manager chia sẻ cùng một namespace vật lý, xóa hai lần có thể là thao tác thừa.
- `@CacheEvict(cacheNames={"books","authors"}, cacheManager="fastCacheManager")` chỉ xóa các vùng **do fastCacheManager phân giải**, không có nghĩa xóa cả ở manager B.

Với dữ liệu nhất quán nghiêm ngặt, cần thiết kế invalidation after-commit, retry/outbox hoặc cơ chế reconciliation khi provider lỗi.

## 10. Ví dụ Java 17 chạy độc lập — hai manager có cache trùng tên

Ví dụ dưới **mô phỏng** hai CacheManager riêng bằng `Map`, không chạy Spring annotation. Nó chứng minh rằng cùng cache name/key có thể hit/miss độc lập.

Tạo file **`MultipleCacheManagersDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.function.Supplier;

public class MultipleCacheManagersDemo {
    static final class MiniCacheManager {
        final String beanName;
        final Map<String, Map<String, String>> regions = new HashMap<>();

        MiniCacheManager(String beanName) {
            this.beanName = beanName;
        }

        String cached(String cacheName, String key, Supplier<String> loader) {
            Map<String, String> region =
                    regions.computeIfAbsent(cacheName, name -> new HashMap<>());
            if (region.containsKey(key)) {
                System.out.println(beanName + "/" + cacheName + ": HIT");
                return region.get(key);
            }
            System.out.println(beanName + "/" + cacheName + ": MISS");
            String value = loader.get();
            region.put(key, value);
            return value;
        }

        void evict(String cacheName, String key) {
            Map<String, String> region = regions.get(cacheName);
            if (region != null) {
                region.remove(key);
            }
            System.out.println(beanName + "/" + cacheName + ": EVICT");
        }
    }

    public static void main(String[] args) {
        MiniCacheManager fast = new MiniCacheManager("fastCacheManager");
        MiniCacheManager durable = new MiniCacheManager("durableCacheManager");

        System.out.println(fast.cached("books", "7", () -> "fast-v1"));
        System.out.println(fast.cached("books", "7", () -> "unused"));
        System.out.println(durable.cached("books", "7", () -> "durable-v1"));
        fast.evict("books", "7");
        System.out.println(durable.cached("books", "7", () -> "unused"));
        System.out.println(fast.cached("books", "7", () -> "fast-v2"));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac --release 17 MultipleCacheManagersDemo.java
java MultipleCacheManagersDemo
~~~

Stdout **chính xác**:

~~~text
fastCacheManager/books: MISS
fast-v1
fastCacheManager/books: HIT
fast-v1
durableCacheManager/books: MISS
durable-v1
fastCacheManager/books: EVICT
durableCacheManager/books: HIT
durable-v1
fastCacheManager/books: MISS
fast-v2
~~~

Giải thích:

1. Manager fast miss lần đầu, sau đó hit cùng key `7` trong vùng `books`.
2. Durable manager vẫn miss ở lần đầu, dù cache có tên `books` và key `7` giống fast.
3. Xóa key ở fast **không xóa** entry ở durable.
4. Đọc lại fast sau eviction là miss; loader nạp `fast-v2`.
5. Cả hai manager trong chương trình đều là `HashMap` in-memory; tên `durable` **không hàm ý persistence thật**.

Phần Java này đã được kiểm tra biên dịch theo target Java 17. Nó giúp hiểu luồng key, nhưng muốn xác minh Spring `@Cacheable` chạy thật cần test qua Spring proxy.

## 11. Test integration trong cùng ApplicationContext

Để QA cấu hình thực, test phải dùng bean service lấy từ context, không chỉ `new Service()`. Ở proxy mode mặc định, lời gọi `this.cachedMethod()` trong cùng instance thường **bỏ qua proxy**, dù annotation đã ghi đúng manager.

Checklist:

1. Kiểm tra context chứa đúng bean `fastCacheManager`, `durableCacheManager` (không phải hai alias vô tình trỏ cùng một bean).
2. Với `CacheManager fast = context.getBean("fastCacheManager", CacheManager.class)`, kiểm tra `fast.getCache("books")` tồn tại và backend đúng.
3. Đặt baseline và gọi method `findFast` hai lần. Kiểm tra lần hai hit, repository không chạy thêm.
4. Gọi `findDurable` cùng ISBN. Nếu hai manager độc lập, lần đầu ở durable phải không dựa vào entry của fast.
5. Evict ở A rồi đọc lại A/B, so sánh trạng thái.
6. Test method không khai báo manager, xác nhận default `CachingConfigurer` thực sự chọn đúng.
7. Test `@CacheConfig` và method-level override; kiểm tra cache name và key.
8. Test `CacheResolver` ở các nhánh runtime, trường hợp thiếu cache name và tenant không hợp lệ.
9. Test lỗi provider, rollback, concurrency và cluster theo mức độ quan trọng.

Ví dụ assertion **đặt trong Spring/JUnit test** (chưa đủ imports/test fixture để tự chạy một mình):

~~~java
CacheManager fast =
        context.getBean("fastCacheManager", CacheManager.class);
CacheManager durable =
        context.getBean("durableCacheManager", CacheManager.class);

Cache first = fast.getCache("books");
Cache second = durable.getCache("books");

assertNotNull(first);
assertNotNull(second);
assertNotSame(first, second);
~~~

Hai object `Cache` khác identity chưa đủ chứng minh backend không chia sẻ. Nếu dùng Redis, phải kiểm tra endpoint, Redis namespace/key-prefix và dữ liệu thật.

## 12. Lỗi phổ biến

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Có hai CacheManager, method không chọn được manager | Không có default rõ, bean lookup mơ hồ | Dùng `CachingConfigurer`, `@CacheConfig` hoặc `cacheManager` |
| `cacheNames="books"` chạy ở manager không mong đợi | Tên cache không quyết định bean manager | Chỉ rõ tên bean hoặc dùng resolver |
| Đã evict nhưng đọc vẫn thấy cũ | Evict sai manager/cacheName/key | So sánh bộ ba ở method đọc và method xóa |
| Composite không dùng delegate thứ hai | Delegate đầu tự tạo mọi cache name | Static cache names và thứ tự fallback |
| Dùng cả `cacheManager`, `cacheResolver` | Hai thuộc tính loại trừ nhau | Chỉ dùng một cơ chế |
| Đúng manager nhưng tenant nhận nhầm dữ liệu | Key thiếu tenant hoặc resolver routing sai | Thiết kế key và kiểm soát truy cập |
| `@CacheConfig` không tự làm cache hoạt động | Chưa có cache operation hoặc interceptor/proxy không hoạt động | Kiểm tra `@EnableCaching`, annotation, đường gọi |
| Thử ở local đúng, production sai | Auto-config/profile/provider khác nhau | Test đúng context và cấu hình production |
| `@Primary` không làm method phân phối như mong muốn | `@Primary` không routing theo operation | Nêu rõ `cacheManager` hoặc tạo `CacheResolver` |
| Cache provider gặp lỗi serialization | Key/value types, prefix, TTL, serializer không đồng nhất | Test provider thật và log theo manager |
| Manager cùng tên cache nên tưởng cùng dữ liệu | Hai instances/namespace riêng | Kiểm tra backend thực; không chỉ tên |

## 13. Checklist production

- Đặt **bean name** ổn định, mô tả đúng provider và phạm vi dữ liệu.
- Liệt kê từng cache name, key generator/SpEL, tenant, TTL và provider của manager tương ứng.
- Đồng bộ lựa chọn **manager + cacheName + key** giữa đọc, cập nhật và xóa.
- Cấu hình mặc định minh bạch bằng `CachingConfigurer` nếu có các annotation không chỉ rõ manager.
- Dùng `@CacheConfig` để giảm lặp; method override khi thật sự cần.
- Dùng `CacheResolver` khi lựa chọn phụ thuộc ngữ cảnh runtime, bảo đảm thread-safe và validate routing input.
- Xác minh `CompositeCacheManager` có fallback như mong đợi khi provider tự tạo cache name.
- Đừng coi `spring.cache.type` hoặc auto-configuration của Boot là cơ chế phân phối giữa hai bean CacheManager tự khai báo.
- Thiết lập metrics theo **manager và cache name**, không chỉ cache name.
- Test lỗi backend, eviction không toàn bộ, rollback, concurrent read/write và multi-node khi có yêu cầu nhất quán.
- Authorization là logic bảo mật riêng: đừng xem phân vùng manager là sự thay thế kiểm tra quyền truy cập.

## 14. Câu hỏi tự kiểm tra

**1.** Có hai CacheManager cùng cung cấp `"books"`. `@Cacheable("books")` tự biết manager nào đúng chưa?

**2.** Thuộc tính `cacheManager="fastCacheManager"` tham chiếu cache name hay Spring bean name?

**3.** Class dùng `@CacheConfig(cacheManager="durableCacheManager")`, method override `@Cacheable(cacheManager="fastCacheManager")`: manager nào được dùng?

**4.** Khi muốn chọn manager theo tham số runtime, dùng `cacheManager` hay `cacheResolver`?

**5.** Có được khai báo cả hai thuộc tính trên cùng annotation không?

**6.** Vì sao `CompositeCacheManager` có thể không bao giờ hỏi delegate thứ hai?

**7.** Evict `books[7]` ở manager A có bảo đảm xóa `books[7]` ở manager B không?

**Đáp án:**

1. **Chưa.** Phải xét default resolver/`CachingConfigurer` và wiring cụ thể.
2. **Bean name** của `CacheManager`; `"books"` mới là tên vùng cache.
3. **fastCacheManager**, vì method-level override ưu tiên hơn class-level.
4. Dùng **`CacheResolver`** khi routing thực sự phụ thuộc invocation.
5. **Không.** Hai cơ chế loại trừ nhau.
6. Delegate đầu tiên có thể luôn trả về cache (do tự tạo cache mới), nên composite không chuyển sang delegate sau.
7. **Không mặc nhiên**; chỉ khi hai bean trỏ tới vùng vật lý chung mới có khả năng liên thông, cần kiểm tra riêng.

## 15. Tài liệu tham khảo

- Spring Framework — annotation-based caching, cache resolution và `@CacheConfig`: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — `EnableCaching` Javadoc (lựa chọn default, nhiều CacheManager): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/EnableCaching.html
- Spring Framework — `CachingConfigurer`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachingConfigurer.html
- Spring Framework — `CacheResolver`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/CacheResolver.html
- Spring Framework — `CompositeCacheManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/CompositeCacheManager.html
- Spring Boot Reference — caching auto-configuration và cache providers: https://docs.spring.io/spring-boot/reference/io/caching.html

**Ghi nhớ:** Có nhiều CacheManager trong cùng ApplicationContext là bình thường, nhưng **cache name không tự chọn manager**. Chọn rõ mặc định bằng `CachingConfigurer`, chọn tĩnh bằng `cacheManager`, đặt class default bằng `@CacheConfig`, chọn động bằng `CacheResolver` và đừng nhầm `CompositeCacheManager` với thao tác ghi/xóa đồng loạt. Quan trọng nhất là cùng một dữ liệu phải có chính sách nhất quán về **manager, cache name, key, provider, invalidation và quyền truy cập**.