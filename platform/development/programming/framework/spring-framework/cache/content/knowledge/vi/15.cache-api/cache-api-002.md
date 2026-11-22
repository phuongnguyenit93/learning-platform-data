# Cache.get: phân biệt cache miss với giá trị null trong Spring Framework

## 1. Tại sao hai trạng thái này khác nhau?

Khi thao tác trực tiếp với Spring Cache, câu hỏi quan trọng không chỉ là **giá trị được lưu là gì**, mà còn là **cache có entry ứng với key đó hay chưa**.

Hãy phân biệt ba trạng thái:

1. **MISS — không có mapping cho key**: chưa từng cache, đã hết hạn, hoặc đã bị evict.
2. **HIT_NULL — key tồn tại, giá trị nghiệp vụ được cache là `null`**: method từng tìm nhưng không thấy dữ liệu; cache ghi lại kết quả đó nếu provider cho phép.
3. **HIT_VALUE — key tồn tại, giá trị khác null**: ví dụ `"Alice"`, một DTO, hoặc một số nguyên.

Hai trạng thái đầu dễ bị nhầm, vì phương thức Java trả về `null` có thể mang hai ý nghĩa: “không tìm thấy entry trong cache” hoặc “đã có entry nhưng giá trị business là null”. Nếu không phân biệt, ứng dụng có thể truy vấn database lặp vô ích hoặc bỏ qua một kết quả cần tải lại.

Trong Spring Framework, API `org.springframework.cache.Cache` giải quyết vấn đề bằng **`Cache.ValueWrapper`** đối với overload `get(Object key)`:

- `cache.get(key) == null` nghĩa là **cache không có mapping** cho key.
- `cache.get(key) != null` nhưng `cache.get(key).get() == null` nghĩa là **có mapping chứa giá trị nghiệp vụ null**, nếu cache implementation hỗ trợ null.
- `cache.get(key).get() != null` là cache hit với giá trị thông thường.

Điểm cốt lõi: **wrapper có tồn tại hay không** mới cho biết cache hit/miss; **giá trị bên trong wrapper** mới là kết quả business.

## 2. Ba overload của Cache.get và ý nghĩa

Spring Cache cung cấp các cách đọc phổ biến:

| API | Kiểu trả về | Thế mạnh | Có phân biệt hit-null với miss từ kết quả không? |
| --- | --- | --- | --- |
| `get(Object key)` | `Cache.ValueWrapper` hoặc null | Kiểm tra mapping tồn tại và lấy giá trị | **Có**, nhờ kiểm tra wrapper |
| `get(Object key, Class<T> type)` | `T` hoặc null | Lấy trực tiếp giá trị mong đợi kèm kiểm tra type | **Không**, cả hai trường hợp đều ra null |
| `get(Object key, Callable<T> loader)` | `T` | Tự tính và cache giá trị khi thiếu entry | Giá trị trả về đơn thuần không phân biệt, vì cả cached-null và loader trả null đều có thể cho null |

Ba phương thức không nên bị đánh đồng:

### 2.1. `get(Object)`: dùng khi cần biết key có tồn tại

```java
Cache.ValueWrapper wrapper = cache.get("user:42");

if (wrapper == null) {
    System.out.println("Cache MISS: không có key user:42");
} else if (wrapper.get() == null) {
    System.out.println("Cache HIT: đã lưu null cho user:42");
} else {
    System.out.println("Cache HIT: " + wrapper.get());
}
```

Đây là **đoạn mã minh họa trong method đã có biến `cache` hợp lệ**; phần 4 có chương trình Java đầy đủ.

Không viết `cache.get("user:42").get()` mà không kiểm tra wrapper trước, bởi cache miss khiến `cache.get(...)` trả null và lời gọi `.get()` sẽ gây `NullPointerException`.

Nếu provider không hỗ trợ lưu null thì nhánh hit-null không xuất hiện từ một thao tác `put` thành công của provider đó. Tuy nhiên logic đọc thông qua `Cache.ValueWrapper` vẫn là cách biểu diễn đúng hợp đồng Spring Cache, không phụ thuộc vào chi tiết lưu trữ native.

### 2.2. `get(key, Class<T>)`: ngắn gọn nhưng mơ hồ với null

```java
String a = cache.get("neverStored", String.class);
String b = cache.get("storedNull", String.class);

// a == null và b == null: không thể kết luận cả hai key đều chưa có.
```

Overload này **trả về dữ liệu business trực tiếp**, không trả wrapper. Theo Javadoc Spring, nó **không thể phân biệt cached null và missing entry**. Nếu có giá trị cache nhưng kiểu không phù hợp, nó có thể ném `IllegalStateException` (ví dụ cache lưu String nhưng yêu cầu Integer).

Khi chỉ cần nhận value và chấp nhận `null` mang cả hai nghĩa, overload typed là tiện lợi. Khi logic đòi hỏi phân biệt “chưa tải” và “đã tải nhưng không tìm thấy”, **hãy dùng `get(key)`**.

### 2.3. `get(key, Callable<T>)`: load nếu thiếu

```java
String result = cache.get("sku:A1", () -> repository.load("A1"));
```

Đây là mảnh mã cần `repository` của ứng dụng. Ý nghĩa: nếu key có entry phù hợp, trả giá trị đã cache; nếu key chưa có, chạy `Callable` để tính, lưu theo semantics của provider, rồi trả lại.

**Quan trọng:** nếu entry chứa cached null, provider hỗ trợ null sẽ coi đó là cache **hit**, nên loader không nên chạy chỉ vì giá trị business là null. Với `ConcurrentMapCache` cho phép null (ví dụ hoàn chỉnh bên dưới), điều này được xác nhận bằng bộ đếm loader.

Nếu loader ném exception, API `Cache.get(key, Callable)` quy định lỗi được bọc bởi `Cache.ValueRetrievalException`. Về đồng thời, Javadoc khuyến khích provider đồng bộ loading cho cùng key **nếu có thể**, nhưng không đảm bảo mọi implementation hoặc mọi node chỉ tải đúng một lần. Cần kiểm tra backend thực tế nếu yêu cầu single-flight.

## 3. Bảng trạng thái: wrapper và giá trị

Ví dụ cache `users`:

| Trạng thái của key | `cache.get(key)` | `wrapper.get()` nếu wrapper tồn tại | `cache.get(key, String.class)` |
| --- | --- | --- | --- |
| Chưa lưu key `"u1"` | `null` | Không được gọi `get()` | `null` |
| Đã `put("u1", null)` trên cache hỗ trợ null | Wrapper **khác null** | `null` | `null` |
| Đã `put("u1", "Alice")` | Wrapper **khác null** | `"Alice"` | `"Alice"` |
| Key vừa được `evict("u1")` và không có ghi lại | `null` trên cache đồng bộ đơn giản | Không được gọi `get()` | `null` |

**Đừng nhầm hai khái niệm “null”:**
- **Null key**: key được truyền vào API bằng null, ví dụ `cache.get(null)`. Cache backend có thể không cho phép. Đây là vấn đề hợp lệ của key và **không phải** nội dung bài về cached-null.
- **Null value**: key hợp lệ (ví dụ `"u1"`) nhưng kết quả nghiệp vụ được lưu là null. Có provider chấp nhận, có provider từ chối.

Cũng không nhầm `CacheManager.getCache("users") == null` — **không có cache region với tên đó** — với `cache.get("u1") == null` — **cache region có nhưng không có mapping cho key**.

## 4. Vì sao ConcurrentMapCache có thể cache null dù ConcurrentHashMap không cho phép?

`ConcurrentHashMap` của JDK không hỗ trợ `null` làm value. Tuy nhiên, `ConcurrentMapCacheManager` của Spring mặc định cho phép cache null (**`allowNullValues = true`**), bởi Spring chuyển null nghiệp vụ thành một **marker/sentinel nội bộ** trước khi lưu xuống native map và chuyển ngược về null khi đọc qua abstraction.

```java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("manual", "annotated");
manager.setAllowNullValues(true);
```

Đoạn trên minh họa cấu hình manager, cần import `org.springframework.cache.concurrent.ConcurrentMapCacheManager`. Trong các ví dụ chạy thực tế, ta đặt cấu hình trước khi sử dụng cache. Thiết lập `allowNullValues=false` sẽ làm cache không nhận null; hành vi của cách ghi null (lỗi hoặc chính sách khác) cần xem implementation. Không tự suy ra mọi provider như Redis, Caffeine, JCache hoặc custom cache đều có cùng hỗ trợ null.

**Đừng can thiệp vào sentinel bằng `getNativeCache()` để kiểm tra null nghiệp vụ.** Sentinel là chi tiết nội bộ; giá trị ở lớp native store có thể khác `cache.get(key).get()`. Nếu dùng `Cache` API, Spring đã cung cấp wrapper để giữ semantics ổn định.

### 4.1. Negative caching: cache kết quả “không tìm thấy”

Cached-null còn được gọi là một dạng **negative caching**: ghi nhớ một lần tìm kiếm không có kết quả.

Ví dụ, service gọi database tra mã khách hàng không tồn tại. Nếu provider cho phép cache null, lời gọi lặp lại với mã đó có thể cache hit và **không phải truy vấn lại** trong thời gian entry còn hiệu lực.

Ưu điểm:
- Giảm tải database khi nhiều request hỏi cùng một ID chưa tồn tại.
- Giảm hiện tượng truy vấn lặp do dữ liệu vắng mặt.

Rủi ro:
- Nếu bản ghi xuất hiện sau đó, cached-null có thể khiến service tiếp tục trả “không tìm thấy” cho đến khi entry hết TTL hoặc bị evict.
- Cache một null do lỗi tạm thời (thay vì “thật sự không tồn tại”) là nguy hiểm. Nên phân biệt exception/timeout với kết quả không tìm thấy; không biến lỗi hệ thống thành null để cache vô thời hạn.
- Cần policy TTL riêng hoặc eviction khi tạo bản ghi mới nếu backend và thiết kế cho phép.

Đối với dữ liệu có yêu cầu consistency cao, hãy cân nhắc có nên cache null hay không thay vì mặc định rằng “null luôn là cache miss”.

## 5. Ví dụ chạy được: phân biệt đủ ba trạng thái

Ví dụ dùng Java 17+, Spring Boot BOM 3.3.13 để cố định phụ thuộc Spring Cache, và `ConcurrentMapCacheManager` bộ nhớ. Không cần HTTP server, Redis hay database.

### 5.1. Cấu trúc thư mục

```text
cache-get-null-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/cache/CacheGetDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'cache-get-null-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}

application {
    mainClass = 'demo.cache.CacheGetDemo'
}
```

### 5.2. File Java đầy đủ

`src/main/java/demo/cache/CacheGetDemo.java`:

```java
package demo.cache;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheGetDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        CacheManager cacheManager() {
            ConcurrentMapCacheManager manager =
                    new ConcurrentMapCacheManager("manual", "annotated");
            manager.setAllowNullValues(true);
            return manager;
        }

        @Bean
        LookupService lookupService() {
            return new LookupService();
        }
    }

    public static class LookupService {
        private final AtomicInteger calls = new AtomicInteger();

        @Cacheable(cacheNames = "annotated", key = "#p0")
        public String query(String code) {
            calls.incrementAndGet();
            return null; // Mô phỏng truy vấn không tìm thấy bản ghi.
        }

        public int callCount() {
            return calls.get();
        }
    }

    private static String state(Cache cache, String key) {
        Cache.ValueWrapper wrapper = cache.get(key);
        if (wrapper == null) {
            return "MISS";
        }
        Object value = wrapper.get();
        return value == null ? "CACHED_NULL" : "VALUE:" + value;
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(CacheConfig.class)) {

            CacheManager manager = context.getBean(CacheManager.class);
            Cache manual = Objects.requireNonNull(manager.getCache("manual"));
            Cache annotated = Objects.requireNonNull(manager.getCache("annotated"));

            // Cache region vắng mặt là chuyện khác cache key vắng mặt.
            System.out.println("regionMissing="
                    + (manager.getCache("other") == null));

            // Trạng thái 1: key chưa hề có trong cache.
            System.out.println("missing=" + state(manual, "missing"));

            // Trạng thái 2: đã lưu chính giá trị nghiệp vụ null.
            manual.put("storedNull", null);
            System.out.println("storedNull=" + state(manual, "storedNull"));

            // Trạng thái 3: key có value bình thường.
            manual.put("present", "alpha");
            System.out.println("present=" + state(manual, "present"));

            // Typed get trả null trong cả hai tình huống.
            System.out.println("typedMissing="
                    + manual.get("missing", String.class));
            System.out.println("typedStoredNull="
                    + manual.get("storedNull", String.class));

            AtomicInteger loaderCalls = new AtomicInteger();

            // Stored null là hit: loader không chạy.
            String cachedNull = manual.get("storedNull", () -> {
                loaderCalls.incrementAndGet();
                return "should-not-run";
            });
            System.out.println("nullLoaderResult=" + cachedNull);
            System.out.println("nullLoaderCalls=" + loaderCalls.get());

            // Missing key mới chạy loader và ghi kết quả.
            String created = manual.get("fresh", () -> {
                loaderCalls.incrementAndGet();
                return "generated";
            });
            String createdAgain = manual.get("fresh", () -> {
                loaderCalls.incrementAndGet();
                return "unexpected";
            });
            System.out.println("created=" + created);
            System.out.println("createdAgain=" + createdAgain);
            System.out.println("loaderCalls=" + loaderCalls.get());

            // putIfAbsent thấy mapping null đã tồn tại.
            Cache.ValueWrapper previous =
                    manual.putIfAbsent("storedNull", "overwrite");
            System.out.println("putIfAbsentSawNull="
                    + (previous != null && previous.get() == null));
            System.out.println("nullStillStored="
                    + state(manual, "storedNull"));

            // Evict làm mất mapping; không giữ một wrapper null.
            manual.evict("storedNull");
            System.out.println("afterEvict=" + state(manual, "storedNull"));

            // @Cacheable trên bean Spring cũng cache một kết quả null.
            LookupService service = context.getBean(LookupService.class);
            System.out.println("firstQuery=" + service.query("X"));
            System.out.println("secondQuery=" + service.query("X"));
            System.out.println("queryCalls=" + service.callCount());
            System.out.println("annotatedState="
                    + state(annotated, "X"));
        }
    }
}
```

Chạy trong thư mục dự án bằng JDK 17+ và Gradle phù hợp:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper, thay bằng `./gradlew run --quiet` (Windows: `gradlew.bat run --quiet`).

Đầu ra dự kiến từ `System.out.println`, không tính log công cụ build/framework:

```text
regionMissing=true
missing=MISS
storedNull=CACHED_NULL
present=VALUE:alpha
typedMissing=null
typedStoredNull=null
nullLoaderResult=null
nullLoaderCalls=0
created=generated
createdAgain=generated
loaderCalls=1
putIfAbsentSawNull=true
nullStillStored=CACHED_NULL
afterEvict=MISS
firstQuery=null
secondQuery=null
queryCalls=1
annotatedState=CACHED_NULL
```

### 5.3. Đọc kết quả đúng cách

1. `regionMissing=true`: manager đang ở chế độ danh sách tên cache cố định chỉ có `manual` và `annotated`, nên region `other` không có. Điều này độc lập với các key trong `manual`.
2. `missing=MISS`: `cache.get("missing")` trả **wrapper null**.
3. `storedNull=CACHED_NULL`: gọi `put("storedNull", null)` với provider hỗ trợ null; `get("storedNull")` trả wrapper **khác null** nhưng `wrapper.get() == null`.
4. `present=VALUE:alpha`: wrapper khác null và giá trị bên trong là chuỗi.
5. `typedMissing=null` và `typedStoredNull=null`: typed overload không có cờ cho biết có entry hay không.
6. `nullLoaderCalls=0`: `get("storedNull", Callable)` không chạy loader vì cached-null là **hit**.
7. `loaderCalls=1`: key `fresh` miss một lần, loader tạo `generated`, lần đọc tiếp theo hit.
8. `putIfAbsentSawNull=true`: existing cached-null **vẫn là mapping tồn tại**. Không nên put đè chỉ vì giá trị bên trong wrapper là null.
9. `afterEvict=MISS`: entry được xóa, nên không còn wrapper; ví dụ in-memory đồng bộ thể hiện ngay.
10. `queryCalls=1` sau hai lần gọi `@Cacheable` trả null: method chỉ chạy một lần; cache annotation đã lưu negative result. `annotatedState=CACHED_NULL` cho thấy entry đã tồn tại.

**Vì sao phải gọi qua Spring context?** `@EnableCaching` kích hoạt interceptor cho bean `LookupService`. Nếu tự tạo `new LookupService()` hoặc tự gọi nội bộ `this.query(...)` trong cùng target ở chế độ proxy mặc định, lời gọi annotation không được chặn; bộ đếm có thể tăng cả hai lần và sẽ không chứng minh được caching.

## 6. Mẫu code an toàn khi cần kết quả có ba trạng thái

Nếu logic ứng dụng cần giữ khác biệt giữa “chưa có cache”, “đã có null” và “đã có value”, đừng trả `null` cho hai trạng thái đầu. Có thể dùng một kiểu dữ liệu biểu diễn rõ:

```java
record CacheRead(boolean hit, Object value) {}

static CacheRead read(Cache cache, Object key) {
    Cache.ValueWrapper wrapper = cache.get(key);
    return (wrapper == null)
            ? new CacheRead(false, null)
            : new CacheRead(true, wrapper.get());
}
```

Đây là **mảnh code minh họa Java 17 trong một class** có import `org.springframework.cache.Cache`. Với kết quả `new CacheRead(false, null)`, đó là miss. Với `new CacheRead(true, null)`, đó là hit-null. Với `new CacheRead(true, "Alice")`, đó là hit-value.

Một biến thể dùng enum `MISS`/`HIT_NULL`/`HIT_VALUE` và object result còn giúp log, metrics, hoặc API điều phối truy vấn nguồn không nhầm hai khái niệm.

Tránh sử dụng biểu thức:

```java
// Sai khi null là giá trị có thể cache:
if (cache.get("key", String.class) == null) {
    // Kết luận "không có key" không được bảo đảm!
}
```

Nếu cache key tồn tại với null, biểu thức `== null` vẫn đúng. **Đây không phải cách kiểm tra cache miss**.

## 7. Kiểm soát chính sách cache null với @Cacheable

Nếu method trả null khi không tìm thấy, có hai lựa chọn thiết kế:

**Chủ động cache null (negative caching):**

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) {
    return repository.find(id); // Có thể trả null.
}
```

Trong cache provider cho phép null, lần đầu trả null có thể được lưu, lần sau là hit. Đoạn này là method minh họa cần `Product`/`repository` của ứng dụng.

**Không lưu null:**

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    unless = "#result == null"
)
public Product find(String id) {
    return repository.find(id);
}
```

`unless` được đánh giá **sau khi method chạy khi miss**, nên có thể dùng `#result` để từ chối ghi null. Khi đó nếu ID vẫn không tồn tại, những lời gọi sau lại miss và chạy method theo chính sách provider.

Không dùng `condition="#result != null"` thay `unless`: `condition` cho `@Cacheable` được đánh giá trước khi có kết quả method, dùng để quyết định có lookup hay không.

### 7.1. Optional.empty() cũng cần chú ý

Spring hỗ trợ return type `Optional<T>` cho annotation-based caching. Theo tài liệu Spring, `Optional.of(value)` được xử lý theo value bên trong; `Optional.empty()` có thể được cache như **giá trị nghiệp vụ null** khi provider cho phép.

```java
@Cacheable(cacheNames = "customers", key = "#p0")
public java.util.Optional<Customer> find(String id) {
    return repository.findOptional(id);
}
```

Đoạn này chỉ minh họa class `Customer` và repository có sẵn. Nếu muốn không cache trường hợp rỗng, có thể dùng `unless="#result == null"` theo semantics Spring SpEL với supported wrapper; `#result` là dữ liệu business được unwrapped, không phải chính `Optional`.

**Phân biệt API:** `java.util.Optional.empty()` là **một đối tượng trả về ở ranh giới nghiệp vụ**; khi vào cache abstraction, Spring có thể lưu null tương ứng, chứ không nhất thiết lưu nguyên đối tượng Optional.

## 8. get(key, Callable): thêm hai tình huống cần kiểm tra

### 8.1. Loader trả null

Nếu key chưa có và loader thực sự trả null:

```java
String result = cache.get("notFound", () -> (String) null);
```

Với cache cho phép null, nhà cung cấp có thể lưu kết quả null như một entry, nên lần `get("notFound")` tiếp theo sẽ trả **ValueWrapper khác null chứa null**. Với cache không cho phép null, thao tác có thể thất bại hoặc theo quy tắc provider riêng.

Vì vậy **đừng suy từ chính biến `result == null` rằng loader có được gọi hay không**; nếu phải biết, đo loader call hoặc dùng `get(key)` để kiểm tra mapping sau đó theo semantics provider.

### 8.2. Loader ném exception

```java
try {
    cache.get("slowLookup", () -> {
        throw new IllegalArgumentException("upstream failed");
    });
} catch (Cache.ValueRetrievalException ex) {
    System.err.println("Cannot load cache key: " + ex.getKey());
}
```

Đây là mảnh mã minh họa cần biến `cache` và import `Cache`. Spring dùng `Cache.ValueRetrievalException` để bọc exception do loader ném. Không được biến lỗi upstream thành một entry null bền vững nếu nghiệp vụ cần retry hoặc fail-fast.

### 8.3. Concurrent load và atomicity phụ thuộc provider

`get(key, Callable)` được thiết kế để gộp mẫu “lookup, nếu thiếu thì tính và lưu”. Javadoc Spring khuyến khích backend bảo đảm loader chỉ chạy một lần dưới concurrent miss **nếu có thể**. Nhưng đây không phải cam kết cho tất cả provider hoặc cho nhiều JVM/nút ứng dụng.

Nếu cần single-flight, hãy kiểm thử với backend thật và nêu rõ phạm vi đồng bộ. Trong Spring annotation, `@Cacheable(sync=true)` cũng dựa trên khả năng synchronized loading của cache provider, không tạo distributed transaction giữa cache và database.

## 9. Các lỗi dễ gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `NullPointerException` tại `cache.get(key).get()` | Key miss nên wrapper null | Kiểm tra wrapper trước |
| Null trả về bị hiểu là luôn cache miss | Dùng typed `get(key, String.class)` | Dùng `get(key)` để phân biệt |
| DB không được gọi lại dù bản ghi mới xuất hiện | Đã cache null từ trước | TTL hợp lý, evict khi tạo bản ghi, hoặc `unless` |
| Null không được lưu và code ném lỗi | Provider/tùy chọn không hỗ trợ null | Xác minh `allowNullValues` và chính sách backend |
| Đọc native map thấy một object “lạ” thay vì null | Spring dùng sentinel để biểu diễn cached-null | Đọc qua `Cache.ValueWrapper` |
| `getCache("missing") == null` bị hiểu là key miss | CacheManager không có region | Phân biệt cache region với mapping trong cache |
| Dùng `get(key, Callable)` vẫn gọi loader nhiều lần khi đồng thời | Provider không đảm bảo synchronized load như kỳ vọng | Đo số lần gọi, kiểm tra backend hoặc cơ chế khóa |
| `putIfAbsent` ghi đè null đã cache | Code kiểm tra value thay vì wrapper/presence | Coi wrapper chứa null là existing entry |
| Nạp cùng key vẫn gọi body hai lần | Gọi service qua `new`/self-invocation, hoặc cache không bật | Kiểm tra Spring proxy và `@EnableCaching` |
| Dữ liệu sai tenant bị trả từ cache | Key không mang đủ scope, không liên quan bản chất null | Thiết kế key/authorization đúng |

### 9.1. Evict/clear có thể trì hoãn

Ví dụ dùng `ConcurrentMapCache` in-memory thường cho thấy eviction ngay, nhưng abstraction `Cache.evict(key)` hoặc `Cache.clear()` cho phép backend có thể trì hoãn hoặc thực hiện bất đồng bộ, đặc biệt qua transaction-aware decorator. Vì vậy code cần visibility mạnh phải đọc hợp đồng provider và cân nhắc API như `evictIfPresent` hoặc `invalidate` khi thích hợp, không mặc định mọi `get` ngay sau eviction đều miss trên mọi backend.

### 9.2. Cache put trực tiếp không nguyên tử với chuỗi get-then-put

`get(key)` cho biết trạng thái hiện tại, nhưng giữa kiểm tra wrapper và `put`, một luồng khác có thể ghi cùng key. Nếu mục tiêu là **chỉ ghi khi absent**, dùng `Cache.putIfAbsent` khi provider hỗ trợ atomicity phù hợp. Kết quả trả về của `putIfAbsent` cũng là `ValueWrapper`: wrapper khác null có thể chứa giá trị null đã tồn tại.

Không nhầm “biết hit/miss” với “khóa được toàn bộ quy trình nghiệp vụ” — nhất là khi loader truy vấn dữ liệu nguồn song song với cập nhật.

## 10. Checklist kiểm thử

Khi triển khai cache có khả năng chứa null, nên kiểm thử ít nhất:

1. **Missing key:** `get(key) == null`, typed get trả null.
2. **Cached null:** wrapper khác null, `wrapper.get() == null`; typed get vẫn trả null.
3. **Cached value:** wrapper khác null, giá trị đúng type; typed get trả value.
4. **Wrong type:** type yêu cầu không khớp value khác null; xử lý `IllegalStateException`.
5. **Loader trên missing key:** gọi loader và lưu theo hợp đồng provider.
6. **Loader trên cached-null:** không gọi loader, trừ khi backend không hỗ trợ null và không hề có entry.
7. **Eviction và TTL:** sau khi entry bị xóa/hết hạn, wrapper trở lại null.
8. **@Cacheable trả null:** gọi hai lần qua proxy, đếm số lần body chạy với `allowNullValues=true`.
9. **@Cacheable(unless) từ chối null:** gọi lại cùng key vẫn chạy method nếu chưa có entry khác.
10. **Concurrent miss:** kiểm tra tính chất synchronized loader trên backend đang dùng.
11. **Đổi trạng thái nguồn từ “không có bản ghi” sang “có”:** cần cách invalidate negative cache.
12. **Provider khác:** lặp lại test với Redis/Caffeine hoặc manager thực tế, không mặc định behavior của ConcurrentMapCache.

Những trường hợp null cần được xác định theo **nghĩa nghiệp vụ**: null do không tồn tại, thiếu quyền, lỗi truy vấn hay giá trị đang cập nhật. Không gom tất cả các kết quả đó thành negative-cache dài hạn nếu hệ thống cần phân biệt.

## 11. Tóm tắt

- **`Cache.get(key)` trả null wrapper = cache miss**; **wrapper khác null chứa value null = cached-null**, khi backend cho phép.
- **`Cache.get(key, Class<T>)` trả null cho cả missing và cached-null**, nên không dùng nó để xác định key tồn tại.
- `Cache.get(key, Callable<T>)` dùng loader khi thiếu entry; cached-null là một hit đối với cache hỗ trợ null; khả năng đồng bộ load phụ thuộc provider.
- `ConcurrentMapCacheManager` mặc định cho phép null bằng **sentinel nội bộ**, dù `ConcurrentHashMap` không chứa native null.
- Cần chủ động chọn **negative caching hay `unless="#result == null"`**, TTL và eviction khi dữ liệu nguồn thay đổi.
- Đừng nhầm **null key**, **null value**, **không có cache region**, và **cache miss trong một region đang tồn tại**.

### Tài liệu chính thức

- [Spring Framework 6.1 — Cache API, get(Object), get(Object, Class), get(Object, Callable)](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework — Cache.ValueWrapper API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/cache/Cache.ValueWrapper.html)
- [Spring Framework — ConcurrentMapCacheManager, allowNullValues](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
