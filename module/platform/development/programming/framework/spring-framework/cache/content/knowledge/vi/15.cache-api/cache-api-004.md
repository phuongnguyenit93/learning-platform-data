# get với Callable để nạp dữ liệu khi thiếu — Spring Cache API lập trình

## Mục tiêu

Bài học thuộc nhóm **API lập trình** của Spring Framework Cache. Sau bài này, bạn sẽ:

- Sử dụng đúng `Cache.get(Object key, Callable<T> valueLoader)` cho thao tác **nếu có thì lấy từ cache, nếu thiếu thì nạp từ nguồn và lưu**.
- Phân biệt `get(key)`, `get(key, Class<T>)` và `get(key, Callable<T>)`, đặc biệt khi giá trị trả về có thể là `null`.
- Hiểu khi nào `Callable` chạy, xử lý lỗi bằng `Cache.ValueRetrievalException`, và tránh giả định sai về “chỉ load đúng một lần” dưới nhiều thread/instance.
- Sử dụng `CacheManager`, cache name và key nhất quán; cập nhật source of truth và invalidate đúng entry.
- Chạy ví dụ Spring Boot Java 17+ với stdout dự đoán được, chứng minh cache hit, cache miss, stale value và loader thất bại.

**Ý chính:** đây là cách **dùng Spring Cache trực tiếp qua API**, không phải annotation caching. `Cache.get(key, Callable)` giúp viết ngắn gọn vòng đời *get-or-load*: tra entry; nếu miss mới gọi loader; đưa kết quả vào cache theo chính sách provider; trả kết quả cho caller.

## 1. Bài toán: nạp dữ liệu khi cache miss

Giả sử phương thức đọc tiêu đề sách từ database chậm. Khi nhiều request cùng hỏi sách `B1`, ta muốn:

~~~text
Lần 1:
  cache["B1"] → MISS
  database.findTitle("B1") → "Java 17"
  lưu cache["B1"] = "Java 17"
  trả "Java 17"

Lần 2:
  cache["B1"] → HIT
  trả "Java 17", KHÔNG đọc database
~~~

Có thể tự viết logic:

~~~java
// Minh họa trong một method đã có các biến cache và bookId.
Cache.ValueWrapper wrapper = cache.get(bookId);
if (wrapper != null) {
    return (String) wrapper.get();
}
String title = loadFromDatabase(bookId);
cache.put(bookId, title);
return title;
~~~

Tuy nhiên, đây là thao tác **kiểm tra rồi hành động** (*check-then-act*). Hai thread có thể cùng thấy miss và cùng load, dẫn tới tốn hai lần truy vấn hoặc put lẫn nhau. Trong nhiều trường hợp, API nạp khi thiếu của Spring ngắn gọn và hợp lý hơn:

~~~java
String title = cache.get(
        bookId,
        () -> loadFromDatabase(bookId));
~~~

`() -> loadFromDatabase(bookId)` là một `Callable<String>`. **Callable chỉ được yêu cầu thực thi khi entry chưa có hoặc đã trở nên không hợp lệ theo backend.** Không gọi `loadFromDatabase` trước rồi truyền kết quả vào callback, vì làm vậy đánh mất lợi ích của cache.

Lưu ý: Spring JavaDoc khuyến khích các provider phối hợp loader để một key chỉ phải nạp một lần nếu có thể, nhưng mức độ đồng bộ thực tế phụ thuộc implementation. Không được suy ra bảo đảm exactly-once trên nhiều JVM từ chữ ký API.

## 2. Ba overload quan trọng của Cache.get

Spring Framework định nghĩa `org.springframework.cache.Cache` như API chung cho các vùng cache. Các dạng đọc thường dùng:

| API | Kết quả | Cache miss | Tự load? |
| --- | --- | --- | --- |
| `Cache.ValueWrapper get(Object key)` | Wrapper của value, hoặc `null` nếu không có mapping | `null` | Không |
| `<T> T get(Object key, Class<T> type)` | Value đúng kiểu, hoặc `null` | `null` | Không |
| `<T> T get(Object key, Callable<T> valueLoader)` | Value đã cache hoặc callback vừa nạp | Gọi `valueLoader`, đưa kết quả vào cache theo provider | **Có** |

Đoạn so sánh:

~~~java
// cache là một org.springframework.cache.Cache đã được lấy từ manager.
Cache.ValueWrapper present = cache.get("B1");
String typed = cache.get("B1", String.class);
String onDemand = cache.get("B1", () -> "Java 17");
~~~

**Không nhầm `get(key, Class<T>)` với `get(key, Callable<T>)`.** Một phương thức yêu cầu kiểu dữ liệu khi đọc, phương thức còn lại yêu cầu cách nạp nếu miss.

Một khác biệt tinh tế: `cache.get(key, String.class) == null` có thể mang nghĩa **không có entry** *hoặc* **entry có value bằng null**. `get(key)` với `Cache.ValueWrapper` cho phép phân biệt hai trường hợp nếu backend hỗ trợ cached null. Nếu wrapper không null mà `wrapper.get() == null`, entry tồn tại nhưng giá trị nghiệp vụ là null.

### Callable là gì?

`java.util.concurrent.Callable<V>` có một phương thức:

~~~java
V call() throws Exception;
~~~

Nó giống một hàm không đối số, **trả kết quả** và có thể ném checked exception. Spring chỉ nhận callback; việc chạy callback khi miss được giao cho `Cache`. So với `Runnable`, `Callable` phù hợp với tác vụ đọc dữ liệu vì nó trả lại giá trị để cache.

## 3. Cơ chế nạp: đường đi của một lời gọi

~~~text
Service / Controller
        │
        └── Cache.get(key, Callable<T>)
                    │
               lookup key
                /       \
             HIT        MISS
              │           │
       trả cached T       gọi valueLoader.call()
                          │
                    /-----------\
                thành công      exception
                    │               │
               cache giá trị   ValueRetrievalException
                    │
                trả value
~~~

Trong cache-hit path, callback không chạy. Do đó:

- Không đặt kiểm tra quyền truy cập **chỉ bên trong loader**. Khi hit, loader bị bỏ qua. Authorization phải ở đường luôn được thực thi và key phải chứa đủ ngữ cảnh tenant/user nếu kết quả khác nhau.
- Không đặt side effect bắt buộc mỗi request (như audit request hoặc billing) trong loader.
- Không mặc định dữ liệu được cập nhật ngay khi database thay đổi. Nếu cache còn entry hợp lệ, caller vẫn nhận dữ liệu cũ cho tới lúc evict/expire.
- Nếu cached value là object mutable và provider store-by-reference, các caller có thể cùng tham chiếu đến một object. `get(key, Callable)` không tạo deep copy.
- Nếu cache provider lỗi, không phải mọi exception runtime đều xuất phát từ loader; phân biệt lỗi `Cache.ValueRetrievalException` với lỗi backend/serialization.

## 4. Ví dụ Java 17+ Spring Boot: hit, miss, evict và loader lỗi

Demo dùng **Spring Boot**, `ConcurrentMapCacheManager` và một map giả lập database để không phụ thuộc hệ thống bên ngoài. Mục tiêu là đo số lần thực sự chạy `Callable`.

Trong một dự án Spring Boot Gradle Java 17+ đã cấu hình plugin/versions phù hợp, dùng dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Dùng hai file Java cùng package `example.cacheapi`. Vì ta **tự gọi API `Cache.get`**, demo **không cần `@EnableCaching`**. Nếu dùng `@Cacheable`/`@CacheEvict` theo annotation trong ứng dụng khác, lúc đó cần bật interception phù hợp.

### 4.1. BookCatalog.java — nạp bằng Callable

Tạo `src/main/java/example/cacheapi/BookCatalog.java`:

~~~java
package example.cacheapi;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Service;

@Service
public class BookCatalog {
    private final Cache cache;
    private final Map<String, String> database =
            new ConcurrentHashMap<>(Map.of("B1", "Java 17"));
    private final AtomicInteger sourceReads = new AtomicInteger();

    public BookCatalog(CacheManager manager) {
        this.cache = Objects.requireNonNull(
                manager.getCache("bookTitles"),
                "Cache bookTitles missing");
    }

    public String title(String bookId) {
        return cache.get(bookId, () -> {
            int count = sourceReads.incrementAndGet();
            System.out.println("LOAD #" + count + " " + bookId);

            String result = database.get(bookId);
            if (result == null) {
                throw new IllegalArgumentException(
                        "Unknown book: " + bookId);
            }
            return result;
        });
    }

    // Chỉ để minh họa cache stale: thay nguồn, không evict.
    public void changeSourceOnly(String bookId, String newTitle) {
        database.put(bookId, newTitle);
    }

    // Trong production cần phối hợp invalidation với transaction.
    public void changeAndEvict(String bookId, String newTitle) {
        database.put(bookId, newTitle);
        cache.evict(bookId);
    }

    public int sourceReadCount() {
        return sourceReads.get();
    }
}
~~~

Giải thích:

1. `CacheManager.getCache("bookTitles")` lấy đúng cache region. Nếu cấu hình thiếu cache, constructor fail-fast thay vì âm thầm đọc một vùng sai.
2. Loader là lambda; `sourceReads.incrementAndGet()` nằm **bên trong** loader, nên tăng khi thật sự miss và cần nạp.
3. Nguồn ban đầu có `B1 → Java 17`. Vì map giả lập độc lập với cache, ta có thể thay nguồn mà không tự xóa entry.
4. Không tồn tại ID thì loader ném `IllegalArgumentException`, làm nổi bật cơ chế wrapper exception.
5. `cache.evict(bookId)` là API xóa entry chủ động, dùng cùng key với đường đọc.

### 4.2. CacheApiDemoApplication.java — kịch bản

Tạo `src/main/java/example/cacheapi/CacheApiDemoApplication.java`:

~~~java
package example.cacheapi;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CacheApiDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheApiDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("bookTitles");
    }

    @Bean
    CommandLineRunner demo(BookCatalog books) {
        return args -> {
            System.out.println("first = " + books.title("B1"));
            System.out.println("second = " + books.title("B1"));

            books.changeSourceOnly("B1", "Intermediate");
            System.out.println("stale = " + books.title("B1"));

            books.changeAndEvict("B1", "Spring Cache");
            System.out.println("fresh = " + books.title("B1"));

            for (int attempt = 1; attempt <= 2; attempt++) {
                try {
                    books.title("MISSING");
                } catch (Cache.ValueRetrievalException ex) {
                    System.out.println("missing attempt " + attempt +
                            " = " +
                            ex.getCause().getClass().getSimpleName());
                }
            }

            System.out.println("sourceReads = " +
                    books.sourceReadCount());
        };
    }
}
~~~

Chạy tại thư mục dự án Spring Boot:

~~~bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
~~~

Các dòng do `System.out` in ra, **theo thứ tự** (bỏ qua log Gradle và Spring Boot):

~~~text
LOAD #1 B1
first = Java 17
second = Java 17
stale = Java 17
LOAD #2 B1
fresh = Spring Cache
LOAD #3 MISSING
missing attempt 1 = IllegalArgumentException
LOAD #4 MISSING
missing attempt 2 = IllegalArgumentException
sourceReads = 4
~~~

**Đối chiếu từng hành động:**

- Lần đầu `title("B1")` miss; loader chạy và in `LOAD #1 B1`. Giá trị `Java 17` được lưu dưới `bookTitles["B1"]`.
- Lần hai cùng key hit; loader không chạy, vì vậy không có `LOAD #2` tại đây.
- `changeSourceOnly` sửa map nguồn thành `Intermediate` nhưng **không xóa entry**. `stale = Java 17` chứng minh cache không tự nhận biết thay đổi của nguồn.
- `changeAndEvict` đổi nguồn thành `Spring Cache` và xóa entry `B1`. Lần `title("B1")` sau đó miss, in `LOAD #2 B1` rồi trả `Spring Cache`.
- Lời gọi `title("MISSING")` đầu tiên in `LOAD #3 MISSING` rồi loader ném `IllegalArgumentException`. Spring bọc lỗi đó dưới `Cache.ValueRetrievalException`, và code in tên kiểu `getCause()`.
- Vì lần load bị lỗi không tạo giá trị cache thành công, lần gọi `MISSING` thứ hai tiếp tục miss, in `LOAD #4 MISSING` và bọc cùng loại lỗi.
- `sourceReads = 4` được xác định hoàn toàn theo bốn lần thực thi lambda.

**Tại sao stdout dự đoán được?** Chạy một process mới; `database` chỉ có một entry, tất cả lời gọi diễn ra tuần tự trong một `CommandLineRunner` và không có request khác thay đổi map/cache. Code là **hai file Java trong một dự án Spring Boot có dependencies**, không phải một file độc lập biên dịch bằng `javac` không kèm Spring.

## 5. Giá trị bị thiếu: null, exception và negative caching

**Không tìm thấy** một bản ghi không đồng nghĩa với **lỗi hạ tầng**. Hợp đồng nghiệp vụ cần quyết định callback trả gì.

### 5.1. Loader ném exception

~~~java
cache.get("MISSING", () -> {
    throw new IllegalArgumentException("No such record");
});
~~~

Với API `get(key, Callable)`, lỗi của loader được bọc trong `Cache.ValueRetrievalException`. Lỗi không tạo ra một value thành công để put; lần gọi sau có thể tiếp tục gọi loader. Trường hợp này được demo ở trên.

Để xử lý có nghĩa:

~~~java
try {
    return cache.get(id, () -> repository.load(id));
} catch (Cache.ValueRetrievalException ex) {
    Throwable original = ex.getCause();
    throw new IllegalStateException(
            "Cannot load item " + id, original);
}
~~~

Đoạn này **chỉ minh họa** trong một method có `cache`, `id`, `repository`. Không bắt tất cả lỗi rồi mặc nhiên trả giá trị giả “thành công”; giá trị giả đó có thể bị cache gây sai cho các request tiếp theo.

### 5.2. Loader trả null

~~~java
String notFound = cache.get("UNKNOWN", () -> null);
~~~

Với backend hỗ trợ `null`, ví dụ `ConcurrentMapCache` mặc định, `null` có thể được lưu thành một marker nội bộ: lần sau trả **cached null** và callback không chạy. Với backend được cấu hình không cho phép `null`, thao tác cache có thể thất bại hoặc phải thiết kế khác.

Do vậy không được mặc định “`null` nghĩa là cache miss”. Để xem entry tồn tại ngay cả khi value null:

~~~java
Cache.ValueWrapper wrapper = cache.get("UNKNOWN");
if (wrapper == null) {
    System.out.println("No mapping");
} else {
    System.out.println("Mapped value = " + wrapper.get());
}
~~~

Ví dụ thứ hai cũng chỉ minh họa; cần biến `cache`. Nếu wrapper tồn tại và `get() == null`, entry là cached null. Nếu wrapper `null`, không có mapping.

**Negative caching** (lưu “không tìm thấy” để hạn chế query lặp) có thể hữu ích nhưng cần TTL, invalidation khi có record mới và phân biệt với lỗi network. Nếu không muốn cache null, `Cache.get(key, Callable)` không có tùy chọn `unless` của annotation; hãy thiết kế policy read/put tương ứng, hoặc dùng `@Cacheable(unless = "#result == null")` khi phù hợp.

### 5.3. Optional không giống null

Nếu loader trả `Optional.empty()`, đó là một object không null (một `Optional` rỗng), không phải `null`. Cache backend có thể lưu object ấy theo cấu hình/serializer; với distributed cache cần kiểm tra khả năng serialize. Đừng tự cho rằng Spring sẽ unwrap `Optional` trong mọi lời gọi **API trực tiếp** như một số đường đi của annotation caching.

## 6. Nhiều thread miss cùng key: có phải chỉ load một lần?

Nếu tự làm `get → if missing → load → put`, hai thread có thể cùng thấy cache miss:

~~~text
Thread A                        Thread B
--------                        --------
get(B1) → MISS                  get(B1) → MISS
loadFromSource(B1)              loadFromSource(B1)
put(B1, valueA)                 put(B1, valueB)
~~~

`Cache.get(key, Callable)` cho phép provider xử lý get-or-load trong cùng operation. Spring JavaDoc viết rằng **nếu có thể**, implementation nên bảo đảm callback chỉ được gọi một lần cho các request đồng thời của cùng key.

Với `ConcurrentMapCache` phổ biến, implementation dùng thao tác kiểu `ConcurrentMap.computeIfAbsent` để phối hợp trong **một JVM**. Tuy nhiên:

- Không có bảo đảm các replica khác JVM sẽ cùng chia sẻ một lần load nếu mỗi replica có local cache riêng.
- Với Redis, JCache hoặc provider khác, phải đọc tài liệu/kiểm thử implementation thực tế; không mặc định phân tán sẽ khóa cùng key.
- Nếu callback có side effect không thể lặp lại (tạo thanh toán, phát sự kiện), không dùng cache loader như cơ chế exactly-once.
- Loader quá lâu có thể khiến request khác chờ hoặc tăng latency. Cần timeout, giám sát và policy phù hợp.
- Tránh loader gọi đệ quy lại `cache.get(sameKey, loader)`; nguy cơ recursive update/deadlock/exception tùy provider.
- `@Cacheable(sync=true)` cũng phụ thuộc hỗ trợ của backend, không phải thay thế cho khóa phân tán trong mọi hệ thống.

Để kiểm thử, khởi tạo cache rỗng, cho nhiều thread cùng gọi một key, đếm số lần callback thật chạy. Test trên cả backend và topology production, không chỉ map trong test.

## 7. Cần chọn đúng cache name, key và vòng đời

### Cache region

~~~java
Cache cache = Objects.requireNonNull(
        manager.getCache("bookTitles"));
~~~

Trong demo, manager tạo sẵn vùng `bookTitles`. Đừng nhầm **không có cache region** với **có region nhưng miss entry**. Với manager tĩnh, tên vùng bị gõ sai có thể khiến `getCache(name) == null`; dùng `Objects.requireNonNull` để phát hiện sớm.

### Key và ngữ cảnh

Nếu source trả dữ liệu riêng theo tenant, cùng ID `B1` ở hai tenant có thể khác tiêu đề. Khi đó `cache.get("B1", loader)` là sai nếu hai tenant chia sẻ vùng cache. Một key phù hợp:

~~~java
public record BookKey(String tenantId, String bookId) {}
~~~

Sau đó:

~~~java
BookKey key = new BookKey(tenantId, bookId);
return cache.get(key, () ->
        repository.loadTitle(tenantId, bookId));
~~~

Đoạn trên minh họa với `repository`, `tenantId` và `bookId` có sẵn trong service. Với cache bộ nhớ, Java `record` có equality/hash theo field; khi dùng backend distributed, cần kiểm tra serialization/key conversion.

**Kiểm tra quyền truy cập phải nằm ở đường luôn được gọi**, không chỉ trong loader vì một cache hit sẽ không gọi loader. Không đưa access token, password hay dữ liệu nhạy cảm thô vào key.

### Khi source of truth thay đổi

Trong demo, `changeSourceOnly` cố ý tạo cache stale để học. Với production, phải có một trong các chiến lược:

- `cache.evict(key)` khi update/delete thành công và vùng cần loại đúng.
- `cache.put(key, freshValue)` nếu có kết quả chính xác sau cập nhật.
- TTL/expiry trên provider để giới hạn tuổi entry khi nguồn có thể thay đổi từ nơi khác.
- Versioning hoặc event-driven invalidation khi nhiều service hoặc replica cùng đọc.

Lưu ý: cập nhật database và xóa cache không tự atomic với transaction. Nếu evict trước commit, request khác có thể nạp lại giá trị cũ. Với yêu cầu nhất quán cao, thiết kế invalidation sau commit hoặc cơ chế giao dịch/đồng bộ phù hợp.

## 8. So sánh với @Cacheable(sync=true)

Dạng annotation tương tự về mục tiêu:

~~~java
@Cacheable(cacheNames = "bookTitles", key = "#p0", sync = true)
public String title(String id) {
    return repository.loadTitle(id);
}
~~~

Đây là **minh họa khác**, không phải code để chèn vào demo imperative. `repository` là dependency của ứng dụng thực tế.

| Khía cạnh | `Cache.get(key, Callable)` | `@Cacheable(sync=true)` |
| --- | --- | --- |
| Phương thức triển khai | Gọi trực tiếp trên object `Cache`. | Gọi service method được Spring cache interceptor xử lý. |
| `@EnableCaching` | Không cần nếu chỉ dùng API. | Cần bật caching và lời gọi đi qua proxy/weaving phù hợp. |
| Nguồn key | Caller tự tạo `key`. | Spring key generator hoặc SpEL. |
| Nguồn value | `Callable<T>` chạy lúc miss. | Thân method chạy lúc miss. |
| Vùng cache | Lấy `Cache` qua `CacheManager`. | `cacheNames` và cấu hình annotation. |
| Điều kiện/`unless` | Tự điều khiển bằng Java và chính sách provider. | Có cơ chế annotation, với các hạn chế khi `sync=true`. |
| Self-invocation | API trực tiếp vẫn là lời gọi Java bình thường. | Lời gọi `this.method()` trong cùng bean thường bỏ qua proxy. |
| Đồng thời | Theo semantics của `Cache.get(key, Callable)` do provider hỗ trợ. | Cũng cần provider hỗ trợ đồng bộ nạp key. |

Nếu cần cache tại một đoạn code có nhánh điều kiện linh hoạt, API imperative thường rõ. Nếu muốn caching là concern trên service method, annotation ngắn gọn hơn. Không trộn cả hai lên cùng value/key mà không thiết kế ai chịu trách nhiệm put/evict và chính sách lỗi.

## 9. Các lỗi cần tránh

1. **Tưởng `Callable` luôn chạy:** cache hit không chạy loader; không đặt logic bắt buộc cho mọi request bên trong đó.
2. **Tưởng `get(key, Class<T>)` tự load:** nó chỉ đọc/cast value đã có, không nhận callback.
3. **Key sai hoặc thiếu ngữ cảnh:** gây hit dữ liệu của user/tenant khác, dù loader đúng.
4. **Cache name sai:** `getCache(name)` có thể trả `null`, không phải miss entry.
5. **Không evict sau thay đổi nguồn:** cache tiếp tục giữ dữ liệu cũ.
6. **Không xử lý lỗi loader:** `ValueRetrievalException` có cause, không phải lúc nào cũng là lỗi cấu hình cache.
7. **Tưởng exception được cache như một kết quả:** lỗi loader thông thường không put value thành công; lần đọc sau lại có thể chạy callback.
8. **Không xác định hợp đồng cached null:** có thể tạo negative caching mà không mong muốn.
9. **Dùng mutable key/value:** thay đổi `equals/hashCode` của key sau put, hoặc sửa object cache store-by-reference, có thể phá correctness.
10. **Mong đợi TTL mặc định từ `ConcurrentMapCacheManager`:** TTL phải do provider có hỗ trợ và được cấu hình riêng.
11. **Giả định “một loader trên toàn cluster”:** lời hứa về phối hợp nạp chỉ ở mức provider hỗ trợ, không có distributed exactly-once mặc định.
12. **Không kiểm thử backend production:** serialization, TTL, null và concurrency của Redis/Caffeine/JCache có thể khác map dùng trong demo.

## 10. Bài tập và kế hoạch kiểm thử

| Bài kiểm tra | Thao tác | Kết quả cần xác minh |
| --- | --- | --- |
| Miss đầu tiên | Gọi cùng key khi cache rỗng | Loader chạy, value được lưu. |
| Hit sau miss | Gọi lại key đó | Loader không chạy; số lần đọc nguồn không tăng. |
| Evict rồi đọc | `cache.evict(key)` rồi gọi get | Loader chạy lại, lấy dữ liệu mới. |
| Nguồn đổi nhưng không evict | Update source độc lập | Cache có thể trả value cũ trước khi expire. |
| Loader ném exception | Dùng key `MISSING` như demo | `Cache.ValueRetrievalException` chứa cause ban đầu. |
| Thử lại sau lỗi | Gọi lại cùng key lỗi | Loader được gọi lại, không có value thành công trước đó. |
| Cached null | Dùng backend allowNullValues=true | `ValueWrapper` không null dù value null; lần sau có thể không load. |
| Không cho cache null | Backend allowNullValues=false | Xác minh chính sách lỗi/miss và thiết kế xử lý. |
| Khác key | Gọi `B2` khi có dữ liệu nguồn | Cache miss độc lập, không trả B1. |
| Hai tenant trùng ID | Tạo BookKey gồm tenant và bookId | Không trả nhầm dữ liệu giữa tenant. |
| Concurrent miss | Nhiều thread đồng thời gọi cùng key | Đo số lần loader và điều kiện chờ của backend thực. |
| Production backend | Chạy test với provider đang triển khai | Xác nhận serialization, concurrency, TTL và exception. |

### Checklist trước khi merge

- [ ] `CacheManager` đã có vùng tên đúng, kiểm tra `getCache(name) != null`.
- [ ] Cache key bất biến và chứa đủ thành phần ảnh hưởng kết quả.
- [ ] `Callable<T>` trả giá trị đúng kiểu, không chứa side effect phải chạy mọi request.
- [ ] Có hợp đồng xử lý not found, cached null, lỗi loader và retry.
- [ ] Có chiến lược evict/put/expiry khi nguồn dữ liệu thay đổi.
- [ ] Có xác thực quyền ở đường gọi ngay cả khi cache hit.
- [ ] Đã kiểm tra khả năng load đồng thời của backend, không giả định exactly-once trên cluster.
- [ ] Có test hit/miss, source update, exception và backend thực tế.

## Tài liệu chính thức

- Spring Framework — `Cache` API, `get(Object, Callable)`, `ValueRetrievalException`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework — `ConcurrentMapCache` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
