# Cache.retrieve và các dạng biểu diễn hit, miss, null trong Spring Cache

## Mục tiêu

Khi gọi `Cache.get(key)` theo cách đồng bộ, ta thường nhận `Cache.ValueWrapper` nếu entry tồn tại và nhận `null` nếu cache miss. Với API bất đồng bộ `Cache.retrieve`, câu chuyện phức tạp hơn: kết quả có thể là **không có future**, **future hoàn tất với null**, hoặc **future chứa wrapper có value null**. Ba hình thức này **không cùng ý nghĩa**.

Bài học tập trung vào hợp đồng `org.springframework.cache.Cache` từ Spring Framework 6.1 trở lên, đặc biệt hai overload:

~~~java
CompletableFuture<?> retrieve(Object key);

<T> CompletableFuture<T> retrieve(
    Object key,
    Supplier<CompletableFuture<T>> valueLoader
);
~~~

Các chữ ký trên được rút gọn để đọc dễ hơn; import và annotation nullability được lược khỏi ví dụ. Sau bài học, bạn sẽ biết khi nào là hit/miss, cách xử lý cached null, cách dùng loader để nạp dữ liệu, cách tránh block và viết chương trình Java 17 kiểm chứng với Spring Caffeine async cache.

> **Kết luận then chốt:** Với overload **không loader**, `retrieve(key) == null` là miss biết ngay; `retrieve(key)` trả future **hoàn tất với null** là miss được xác định bất đồng bộ; còn future chứa `Cache.ValueWrapper` có `get() == null` là **hit với giá trị null đã được cache**.

## 1. Bối cảnh: vì sao cần Cache.retrieve?

Một cache có thể xác định entry ngay lập tức nếu dùng local map, nhưng nếu backend truy xuất qua network hoặc một tầng I/O bất đồng bộ thì lời gọi phải chờ. API `get` đồng bộ có thể buộc thread đợi. API `retrieve` tạo đường truy xuất dựa trên `CompletableFuture`, để caller compose quá trình tiếp theo mà không phải gọi `.join()` hay `.get()` trong đường xử lý.

Luồng:

~~~text
t0: caller gọi cache.retrieve(key)
          |
          +-- Biết miss ngay: trả null
          |
          +-- Có kết quả async: trả CompletableFuture<?>
                                      |
                               ở thời điểm t1
                                      |
                     +----------------+----------------+
                     |                |                |
                   value             null          exception
                     |                |                |
                  HIT             MISS_DEFERRED     ERROR
                     |
           value có thể là ValueWrapper
                     |
             wrapper.get() == null
                     |
                 HIT_CACHED_NULL
~~~

Điểm khác biệt không chỉ nằm ở giá trị kết quả, mà còn nằm ở **thời điểm provider biết có entry hay không**. Không thể đồng nhất “có future” với “có entry”.

### Tương quan với API đồng bộ

~~~java
Cache.ValueWrapper wrapper = cache.get("item-1");
if (wrapper == null) {
    // Miss: không có entry.
} else {
    Object value = wrapper.get();
    // Hit: value có thể null.
}
~~~

Đây là đoạn minh họa, giả định biến `cache` là đối tượng Spring Cache đã được tạo. Với `get(Object)`, chính sự hiện diện của `ValueWrapper` phân biệt cached null và miss. Trong `retrieve`, còn có thêm tầng future.

## 2. Overload không loader: đầy đủ các dạng kết quả

Hợp đồng đầu tiên:

~~~java
CompletableFuture<?> lookup = cache.retrieve(key);
~~~

Mục tiêu là **tìm entry hiện có**, không tự nạp lại từ repository.

| Giá trị trả về từ `retrieve(key)` | Kết quả khi future hoàn tất | Ý nghĩa |
| --- | --- | --- |
| `null` | Không có future | **MISS_IMMEDIATE** |
| Future khác null | `null` | **MISS_DEFERRED** |
| Future khác null | Object khác null | **HIT_VALUE** |
| Future khác null | `Cache.ValueWrapper` chứa object khác null | **HIT_VALUE** |
| Future khác null | `Cache.ValueWrapper` với `get() == null` | **HIT_CACHED_NULL** |
| Future khác null | Hoàn tất exceptionally | **ERROR**, không phải miss |

### 2.1. Immediate miss: null ở tầng ngoài

Nếu provider có thể xác định ngay key không tồn tại, method có thể trả **tham chiếu null** thay vì future:

~~~java
CompletableFuture<?> lookup = cache.retrieve("absent");

if (lookup == null) {
    // MISS_IMMEDIATE: không có future để tiếp tục.
}
~~~

Không được gọi `lookup.join()`, `lookup.thenApply()` hoặc `lookup.get()` trước khi kiểm tra null tầng ngoài, vì sẽ gây `NullPointerException`.

### 2.2. Deferred miss: future chứa null ở tầng trong

Provider cần thời gian tra cứu có thể trả một future khác null; sau khi lookup xong, future hoàn tất với null:

~~~java
CompletableFuture<?> lookup =
    CompletableFuture.completedFuture(null);
~~~

Đây là **MISS_DEFERRED**. Trong đời thực future có thể đang pending chứ không hoàn tất ngay. Khi `lookup != null`, không được khẳng định hit cho đến khi future hoàn tất và kiểm tra kết quả.

Ví dụ:

~~~java
CompletableFuture<?> lookup = cache.retrieve(key);

if (lookup == null) {
    // Immediate miss.
} else {
    lookup.thenAccept(result -> {
        if (result == null) {
            // Deferred miss.
        }
    });
}
~~~

Đây là mã minh họa cần đặt trong một method, không phải file Java chạy độc lập.

### 2.3. Hit với giá trị khác null

Một cache hit thông thường có thể trả:

~~~java
CompletableFuture<?> lookup =
    CompletableFuture.completedFuture("Book-A");
~~~

Future hoàn tất với `"Book-A"` thể hiện entry có giá trị tương ứng. Một số implementation có thể hoàn tất với `Cache.ValueWrapper("Book-A")`; mã tổng quát nên hỗ trợ unwrap wrapper thay vì cast thẳng kết quả về domain type.

### 2.4. Hit với giá trị null đã lưu

Nếu provider cho phép cache null, phải giữ khả năng phân biệt một entry **có tồn tại** nhưng chứa null với một key **không tồn tại**. Spring cho phép `Cache.ValueWrapper` như một tín hiệu:

~~~java
CompletableFuture<?> lookup =
    CompletableFuture.completedFuture(
        new SimpleValueWrapper(null)
    );
~~~

`SimpleValueWrapper` thuộc package `org.springframework.cache.support`.

Giải thích:

~~~text
result = null
    => Cache MISS_DEFERRED

result = ValueWrapper(null)
    => Cache HIT_CACHED_NULL
       (wrapper khác null, value bên trong null)
~~~

**Đừng xóa bỏ wrapper quá sớm.** Nếu adapter tự biến `ValueWrapper(null)` thành `null`, downstream không còn phân biệt được cached null và miss. Khi đó một kết quả “không tìm thấy” đã được cache có thể bị nạp lại từ nguồn không cần thiết.

### 2.5. Khi future thất bại

Future kết thúc bằng exception không có giá trị để phân loại hit/miss. Đây là **đường lỗi**:

~~~java
CompletableFuture<?> failed =
    CompletableFuture.failedFuture(
        new IllegalStateException("cache backend timeout")
    );
~~~

Khi gọi `failed.join()`, Java ném `CompletionException` với nguyên nhân gốc. Không gộp exception thành `null` rồi gọi nó là miss: hành vi đó che giấu lỗi cache provider và có thể tạo tải lớn xuống database.

## 3. Thứ tự xử lý đúng

Một hàm phân loại future không block:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.cache.Cache;

public static CompletableFuture<String> classifyAsync(
        CompletableFuture<?> lookup) {

    if (lookup == null) {
        return CompletableFuture.completedFuture("MISS_IMMEDIATE");
    }

    return lookup.thenApply(result -> {
        if (result == null) {
            return "MISS_DEFERRED";
        }

        if (result instanceof Cache.ValueWrapper wrapper) {
            Object value = wrapper.get();
            return value == null
                ? "HIT_CACHED_NULL"
                : "HIT_VALUE:" + value;
        }

        return "HIT_VALUE:" + result;
    });
}
~~~

Đây là **method minh họa**, phải được đặt trong một class. Ưu điểm:

1. Kiểm tra null **tầng ngoài** trước.
2. Tiếp tục xử lý khi future hoàn tất, không block caller.
3. Kiểm tra null **tầng trong**.
4. Sau đó mới kiểm tra `ValueWrapper`.
5. Chỉ un-wrap wrapper khi result thực sự là wrapper.
6. Không che exception; stage trả về tự hoàn tất exceptionally nếu lookup lỗi.

Sơ đồ:

~~~text
retrieve(key)
     |
     +-- null -----------------------> MISS_IMMEDIATE
     |
     +-- CompletableFuture
                  |
               complete
                  |
          +-------+----------------+
          |                        |
       exception                 normal
          |                        |
         ERROR                 result == null?
                                   |
                              +----+----+
                              |         |
                             yes        no
                              |         |
                         MISS_DEFERRED  ValueWrapper?
                                        |
                                 +------+------+
                                 |             |
                                yes            no
                                 |             |
                             wrapper.get()    HIT_VALUE
                                 |
                            +----+----+
                            |         |
                           null      value
                            |         |
                     HIT_CACHED_NULL HIT_VALUE
~~~

Trong ví dụ console có thể dùng `.join()` để in stdout theo thứ tự. Ở controller/event loop/Reactive pipeline, tránh join nếu mục tiêu là không block.

## 4. Overload có valueLoader hoạt động khác thế nào?

Chữ ký:

~~~java
<T> CompletableFuture<T> retrieve(
    Object key,
    Supplier<CompletableFuture<T>> valueLoader
);
~~~

Ví dụ:

~~~java
CompletableFuture<Book> result = cache.retrieve(
    "book-42",
    () -> remoteRepository.findAsync("book-42")
);
~~~

Đây là **mã minh họa**, giả định `Book` và repository tồn tại.

Ý nghĩa:

- Khi entry đã có, cache có thể trả future của giá trị đã lưu, không gọi loader.
- Khi miss, provider gọi supplier để nạp một `CompletableFuture<T>`, xử lý kết quả và đưa giá trị hợp lệ vào cache.
- Caller nhận `CompletableFuture<T>`, không phải `CompletableFuture<Cache.ValueWrapper>` như một giao diện thông báo cache miss.
- Các concurrent misses cùng key có thể được provider phối hợp, nhưng **không tự là distributed lock giữa các JVM**.
- Future của loader có thể được provider wrap/transform; không kiểm tra `cacheFuture == loaderFuture` như một hợp đồng.

### 4.1. Supplier phải trả future

Đúng:

~~~java
() -> CompletableFuture.completedFuture("Book-A")
~~~

Hoặc:

~~~java
() -> service.loadAsync(id)
~~~

Sai về ý tưởng API:

~~~java
() -> null
~~~

Supplier trả `null` tham chiếu future là một loader không hợp lệ đối với hoạt động thông thường. Điều này **khác** với supplier trả một future hợp lệ nhưng value của future là null:

~~~java
() -> CompletableFuture.completedFuture(null)
~~~

Ở overload **có loader**, tương lai trả null có thể là **giá trị nghiệp vụ T đã được nạp/tra cứu**; có lưu null hay không phụ thuộc `allowNullValues`/provider. Đừng tự áp quy tắc “inner null = deferred miss” của overload không loader sang overload có loader.

### 4.2. Khả năng cache null là chính sách provider

Một provider có thể chấp nhận cached null bằng internal marker, trong khi provider khác từ chối. Vì vậy:

- Không giả định `cache.put(key, null)` luôn hợp lệ.
- Không giả định một `CompletableFuture<T>` hoàn tất null sẽ được cache ở mọi backend.
- Kiểm tra policy null, TTL và invalidation nếu bạn dùng negative caching.
- Với Caffeine async mode, Spring khuyến nghị cân nhắc `setAllowNullValues(false)` để đơn giản hóa future semantics. Ví dụ của bài bật true **có chủ ý** nhằm chứng minh cached null.

### 4.3. Future bị lỗi hoặc bị cancel

Nếu loader trả future hoàn tất exceptionally thì không có một value nghiệp vụ hoàn tất thành công để lưu. Một số cache provider dọn future lỗi khỏi store để lần sau có thể thử lại, nhưng cần test implementation thực tế. Cancellation cũng phải được xem xét, đặc biệt khi nhiều caller đang chờ chung một future.

### 4.4. Không dùng loader cho side effect bắt buộc mỗi lần gọi

Nếu cache hit, loader **không chạy**. Vì vậy không đặt thao tác “ghi audit log mọi request” hoặc “trừ tồn kho” chỉ trong loader. Caching chỉ thích hợp với các phép đọc hoặc kết quả có thể tái sử dụng hợp lệ theo key.

## 5. So sánh các API và lỗi thường mắc

| API | Dữ liệu trả về | Có phân biệt miss/cached null? | Có tự nạp khi miss? |
| --- | --- | --- | --- |
| `get(key)` | `ValueWrapper` hoặc null | Có, nhờ wrapper | Không |
| `get(key, Type.class)` | Value kiểu T hoặc null | Không nhất thiết | Không |
| `retrieve(key)` | Null hoặc `CompletableFuture<?>` | Có, nếu xử lý đủ hai tầng | Không |
| `retrieve(key, loader)` | `CompletableFuture<T>` | Chủ yếu biểu diễn giá trị T; không dùng wrapper hit/miss tương tự overload đầu | Có |
| `@Cacheable` | Kiểu trả về method, có thể là future | Spring cache interceptor xử lý | Có, bằng cách gọi method trên miss |

Một vài anti-pattern:

~~~java
// Sai: future có thể tồn tại nhưng hoàn tất với null.
boolean hit = cache.retrieve(key) != null;

// Sai: có thể NPE nếu retrieve trả null ngay.
Object result = cache.retrieve(key).join();

// Sai: wrapper null có thể là cached null hit.
boolean miss = result == null
    || (result instanceof Cache.ValueWrapper w && w.get() == null);
~~~

Đây là những **phản ví dụ**, không phải code khuyến nghị. Dùng hàm phân loại như ở mục 3 để tránh nhập nhằng.

### get(Object) vs retrieve(Object)

Trước khi tối ưu async, hãy hỏi backend có thực sự hỗ trợ asynchronous retrieval không. Nếu dùng một map local với lookup tức thời, lợi ích có thể rất nhỏ. Nếu cache ở remote/backend khác, non-blocking path có thể hữu ích nhưng cần đo latency và cơ chế thread/connection thực tế.

## 6. Tính tương thích của CacheManager

### 6.1. Không phải mọi Cache đều hỗ trợ retrieve

Interface `Cache` định nghĩa `retrieve`, nhưng một implementation không hỗ trợ có thể ném `UnsupportedOperationException`. Đây **không phải cache miss**. Không được `catch` lỗi này rồi mặc định coi mọi key đều vắng mặt mà không có thiết kế fallback và quan sát lỗi rõ ràng.

### 6.2. ConcurrentMapCache

`ConcurrentMapCacheManager` dùng cache local dựa trên map trong JVM. Spring hỗ trợ đường retrieval dựa trên future ở các phiên bản hiện đại, nhưng việc trả `CompletableFuture` không làm local map thành backend I/O phi đồng bộ. Một future có thể hoàn tất ngay.

### 6.3. CaffeineCacheManager

Để sử dụng native `AsyncCache` của Caffeine trong Spring:

~~~java
CaffeineCacheManager manager =
    new CaffeineCacheManager();

manager.setAsyncCacheMode(true);
manager.setAllowNullValues(false);
manager.setCaffeine(
    Caffeine.newBuilder().maximumSize(1000)
);
manager.setCacheNames(List.of("books"));
~~~

Đây là đoạn Java Config minh họa với imports cần thiết. Yêu cầu Spring Framework 6.1+ và Caffeine 3.0+. `CaffeineCacheManager` nằm trong `spring-context-support`.

`setAsyncCacheMode(true)` **không tự chuyển method đồng bộ thành async**, không tự chạy code nghiệp vụ trên một executor, và cũng không làm cache local được chia sẻ giữa nhiều instance.

### 6.4. Redis, JCache và adapter khác

Không suy luận từ “native client có async API” thành “Spring Cache adapter triển khai `retrieve`”. Kiểm tra Javadoc của phiên bản `Cache` cụ thể, hỗ trợ từng overload và integration test. Nếu backend chỉ có API blocking, bọc `get` bằng `CompletableFuture.supplyAsync` chỉ chuyển việc block sang thread khác; nó không phải native non-blocking I/O.

## 7. Chương trình Java 17 chạy được với Spring và Caffeine

Ví dụ bên dưới kiểm tra **hợp đồng biểu diễn** và **một cache implementation thật**. Nó dùng trực tiếp `Cache.retrieve` để bài học tập trung vào API, không cần `@EnableCaching` khi không sử dụng annotation interceptor.

### 7.1. Cấu trúc file

~~~text
retrieve-demo/
├── pom.xml
└── src/main/java/demo/RetrieveDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>retrieve-demo</artifactId>
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
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context-support</artifactId>
      <version>6.2.10</version>
    </dependency>
    <dependency>
      <groupId>com.github.ben-manes.caffeine</groupId>
      <artifactId>caffeine</artifactId>
      <version>3.1.8</version>
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

### 7.3. src/main/java/demo/RetrieveDemo.java

~~~java
package demo;

import java.util.List;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.Cache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.cache.support.SimpleValueWrapper;

public class RetrieveDemo {

    static String classify(CompletableFuture<?> lookup) {
        if (lookup == null) {
            return "MISS_IMMEDIATE";
        }

        // join chỉ dùng ở biên console demo.
        Object result = lookup.join();

        if (result == null) {
            return "MISS_DEFERRED";
        }

        if (result instanceof Cache.ValueWrapper wrapper) {
            Object value = wrapper.get();
            return value == null
                ? "HIT_CACHED_NULL"
                : "HIT_VALUE:" + value;
        }

        return "HIT_VALUE:" + result;
    }

    public static void main(String[] args) {
        System.out.println("Immediate: " + classify(null));

        System.out.println("Deferred: " + classify(
            CompletableFuture.completedFuture(null)));

        System.out.println("Cached null: " + classify(
            CompletableFuture.completedFuture(
                new SimpleValueWrapper(null))));

        CaffeineCacheManager manager = new CaffeineCacheManager();
        manager.setAsyncCacheMode(true);

        // Cố ý bật true để thử cached null; production thường
        // cân nhắc false nếu không cần negative caching.
        manager.setAllowNullValues(true);
        manager.setCaffeine(
            Caffeine.newBuilder().maximumSize(100));
        manager.setCacheNames(List.of("catalog"));

        Cache cache = Objects.requireNonNull(
            manager.getCache("catalog"));

        cache.put("present", "Book-A");
        cache.put("known-null", null);

        System.out.println("Present: " + classify(
            cache.retrieve("present")));
        System.out.println("Known null: " + classify(
            cache.retrieve("known-null")));

        String absent = classify(cache.retrieve("absent"));
        System.out.println("Absent is miss: " +
            absent.startsWith("MISS_"));

        AtomicInteger loads = new AtomicInteger();
        Supplier<CompletableFuture<String>> loader = () -> {
            int n = loads.incrementAndGet();
            return CompletableFuture.completedFuture(
                "Book-B(load=" + n + ")");
        };

        String first = cache.retrieve("generated", loader).join();
        String second = cache.retrieve("generated", loader).join();
        System.out.println("Loaded first: " + first);
        System.out.println("Loaded second: " + second);
        System.out.println("Source loads: " + loads.get());
    }
}
~~~

Phân tích:

- **Ba kết quả tổng hợp** ở đầu `main` minh họa chính xác immediate miss, deferred miss và cached-null hit, không phụ thuộc một backend cụ thể.
- `CaffeineCacheManager` bật async mode trước khi tạo vùng `catalog`.
- `setAllowNullValues(true)` là lựa chọn **cố ý cho bài thử**, để lưu một cached null.
- Entry `present` chứa `"Book-A"` nên là hit bình thường.
- Entry `known-null` thực sự tồn tại, do đó là hit với null, không phải miss.
- Với `absent`, code chỉ kiểm tra kết quả bắt đầu bằng `MISS_`, vì có hơn một biểu diễn miss hợp lệ theo hợp đồng.
- Loader của key `generated` trả một future hoàn tất với `Book-B(load=1)`. Hai lời gọi **tuần tự** có cùng key nên lần sau là hit và counter không tăng.

### 7.4. Chạy từ thư mục có pom.xml

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.RetrieveDemo
~~~

Dự kiến chương trình in ra:

~~~text
Immediate: MISS_IMMEDIATE
Deferred: MISS_DEFERRED
Cached null: HIT_CACHED_NULL
Present: HIT_VALUE:Book-A
Known null: HIT_CACHED_NULL
Absent is miss: true
Loaded first: Book-B(load=1)
Loaded second: Book-B(load=1)
Source loads: 1
~~~

Đây là stdout được suy ra từ luồng code và hợp đồng Spring/Caffeine; việc biên dịch Maven và chạy trên JVM thực **chưa được thực hiện trong bài viết**.

### 7.5. Nếu thay đổi cấu hình allowNullValues

Nếu đổi:

~~~java
manager.setAllowNullValues(false);
~~~

thì không tiếp tục `cache.put("known-null", null)` như ví dụ, vì policy không cho phép cached null. Trong một ứng dụng thực, dùng `Optional<T>`, kết quả DTO riêng hoặc không cache “không tìm thấy” là các lựa chọn cần đánh giá theo semantics nghiệp vụ.

## 8. Tích hợp với @Cacheable và reactive return types

Từ Spring Framework 6.1, annotation caching có thể thích nghi với `CompletableFuture<T>`, Reactor `Mono<T>` và `Flux<T>`.

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> loadAsync(String isbn) {
    return repository.findByIsbnAsync(isbn);
}
~~~

Đây là **mã minh họa**, cần repository và cấu hình `@EnableCaching`/cache manager. Spring lưu kết quả `Book` khi future thành công và trả future cho caller.

Với `Flux<T>`, Spring thu thập phần tử thành một `List<T>` để cache sau khi publisher hoàn tất rồi tái phát list khi hit. Đây không phải cache từng phần tử theo stream. Với `Mono.empty()`, cần kiểm tra adaptation và chính sách null/empty theo provider. Không tự suy ra `Mono.empty()` luôn tương đương cached null trong mọi trường hợp.

### @Async không phải Cache.retrieve

`@Async` điều khiển thực thi method qua `TaskExecutor`; `Cache.retrieve` mô tả cache lookup dùng future. Bật Caffeine async mode không tự chạy business method trên background thread, và bật `@Async` không thêm support `retrieve` cho một backend chưa triển khai.

### sync = true

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    sync = true
)
public CompletableFuture<Book> findBook(String id) {
    return repository.findAsync(id);
}
~~~

Đoạn trên minh họa cách yêu cầu Spring phối hợp nhiều miss cùng key nếu cache provider hỗ trợ. `sync=true` có ràng buộc với `unless`, số cache trong operation và khả năng load atomic. Cache Caffeine local không biến nó thành distributed lock giữa các instance.

## 9. Khi nào cần xử lý miss bằng tay?

Nếu chỉ tra cứu:

~~~java
CompletableFuture<?> lookup = cache.retrieve(key);
~~~

và cần tải dữ liệu ở miss, hãy nhớ rằng:

- Nhánh `lookup == null` giải quyết **chỉ immediate miss**.
- Nhánh future kết thúc bằng null giải quyết **deferred miss**.
- Nhánh `ValueWrapper(null)` là **hit**, không gọi loader.
- Nhánh exception là lỗi riêng.
- Nếu tự tải qua `repository.fetchAsync`, bạn còn cần **ghi kết quả vào cache**. Chỉ tải và trả không tự bảo đảm cached value cho lần sau.

Vì vậy, khi provider hỗ trợ, overload `retrieve(key, loader)` thường đơn giản hơn việc tự hiện thực tất cả nhánh, locking và cache put.

## 10. Race, concurrency, cancellation và stale data

### 10.1. Hai request cùng key

Hai request có thể gọi `retrieve(key, loader)` khi future đầu còn pending. Một số implementation có cơ chế dùng chung future/nạp một lần theo key; một số backend hoặc cấu hình không có semantics giống vậy. Hãy kiểm tra bằng test đồng thời, không chỉ từ kiểu trả về `CompletableFuture`.

### 10.2. Future hoàn tất sau eviction

~~~text
t0: Load A đang pending, chờ dữ liệu nguồn.
t1: Nguồn được cập nhật.
t2: cache.evict(key).
t3: Load A hoàn tất với dữ liệu cũ.
~~~

Cần kiểm tra provider có ngăn kết quả cũ ghi lại sau evict hay không. Async cache không tự đảm bảo ordering/transaction/versioning cho mọi backend. Với dữ liệu yêu cầu nhất quán cao, có thể dùng versioned key, invalidation after-commit hoặc fencing token.

### 10.3. Exception và cancellation

Nếu future hoàn tất exceptionally, giữ nguyên thông tin lỗi để caller/metrics xử lý. Đừng biến nó thành miss bằng `catch (Exception) { return null; }` mà không có chính sách rõ ràng. Khi nhiều caller cùng chờ một future, một caller cancel có thể ảnh hưởng đến người khác tùy cách provider chia sẻ handle; kiểm thử cancellation riêng.

### 10.4. Cache hit không đồng nghĩa dữ liệu mới

Kể cả mọi nhánh hit/miss/null được xử lý chính xác, entry vẫn có thể stale sau database update. Cần `@CacheEvict`, `@CachePut`, TTL hoặc invalidation phù hợp. Async retrieval không tự giải quyết freshness.

## 11. Kiểm thử đúng hợp đồng

| Kịch bản | Dữ liệu thử | Kết quả đúng |
| --- | --- | --- |
| Immediate miss | `retrieve` trả `null` | Không gọi method trên future; MISS |
| Deferred miss | Future hoàn tất với `null` | MISS sau completion |
| Hit raw | Future hoàn tất `"A"` | HIT_VALUE |
| Hit wrapper | Future hoàn tất `ValueWrapper("A")` | HIT_VALUE sau unwrap |
| Cached null | Future hoàn tất `ValueWrapper(null)` | **HIT_CACHED_NULL**, không là MISS |
| Future exceptional | `failedFuture(ex)` | ERROR, giữ exception |
| Loader miss | Key chưa có | Loader được gọi, trả value |
| Loader hit | Key đã nạp | Loader không gọi lại |
| Loader trả null | Future hợp lệ chứa null | Hành vi theo null policy |
| Backend không hỗ trợ `retrieve` | Ném `UnsupportedOperationException` | Lỗi capability, không phải miss |
| Concurrent miss | Hai request với future pending | Kiểm tra single-flight theo provider |
| Eviction race | Evict khi load chưa xong | Kiểm tra stale write |

Để tránh test flaky, dùng `CompletableFuture` được test điều khiển hoặc `CountDownLatch` thay cho `Thread.sleep` tùy tiện. Với test không blocking, dùng `thenApply`/`thenCompose` và assertion trên stage hoàn tất. Dùng bộ đếm loader để chứng minh hit/miss, không chỉ đo thời gian.

### Những dấu hiệu cần kiểm tra khi gặp lỗi

- Bất ngờ NPE: có gọi method trên future khi `retrieve` trả null không?
- “Có future nhưng không có dữ liệu”: future có hoàn tất null do deferred miss không?
- Negative cache không hiệu lực: có un-wrap `ValueWrapper(null)` thành miss không?
- Miss luôn nạp lại: cache put bị thiếu, future lỗi hoặc key không ổn định?
- `UnsupportedOperationException`: adapter cache có triển khai `retrieve` không?
- Nhiều request tải cùng key: đã kiểm chứng concurrency/loader atomic chưa?
- Null put bị từ chối: `allowNullValues` có cho phép không?
- Flux lớn gây tăng RAM: Spring có đang gom cả publisher thành list để cache không?

## 12. Checklist triển khai

- [ ] Hiểu hai overload `retrieve(key)` và `retrieve(key, loader)`.
- [ ] Kiểm tra outer null trước khi dùng future của overload không loader.
- [ ] Phân biệt inner null với `ValueWrapper(null)`.
- [ ] Xử lý wrapper cho cả null và non-null cached value.
- [ ] Tách exception/cancellation khỏi cache miss.
- [ ] Không dùng `.join()` trong event-loop hoặc request path nếu mục tiêu là non-blocking.
- [ ] Đảm bảo provider/version có hỗ trợ `Cache.retrieve`.
- [ ] Với Caffeine dùng native async mode khi cần.
- [ ] Có chính sách cho null, `Optional`, negative caching và invalidation.
- [ ] Đảm bảo loader trả `CompletableFuture<T>`, không trả null reference.
- [ ] Đảm bảo loader không chứa side effect cần thực hiện mọi request.
- [ ] Test miss/hit/null, loader, exception và concurrent miss.
- [ ] Kiểm tra race giữa pending future và update/evict.
- [ ] Đo hit ratio, load count, latency, cache errors.
- [ ] Không nhầm async cache mode với `@Async` hoặc distributed cache.

## 13. Câu hỏi tự kiểm tra

**1.** `retrieve(key)` trả null trực tiếp nghĩa là gì?  
**Đáp án:** Cache miss xác định ngay; không có future.

**2.** `retrieve(key)` trả future hoàn tất với null nghĩa là gì?  
**Đáp án:** Deferred miss.

**3.** Future hoàn tất với `SimpleValueWrapper(null)` nghĩa là gì?  
**Đáp án:** Cached null **hit**, không phải miss.

**4.** Tại sao `retrieve(key) != null` chưa chứng minh hit?  
**Đáp án:** Future có thể hoàn tất về sau với null.

**5.** Vì sao `retrieve(key).join()` có thể ném NPE?  
**Đáp án:** Vì `retrieve(key)` được phép trả null ngay.

**6.** Nếu result là `ValueWrapper("Book")`, phải làm gì?  
**Đáp án:** Un-wrap value và phân loại HIT_VALUE.

**7.** Future exceptional có phải miss không?  
**Đáp án:** Không, đó là ERROR.

**8.** Overload `retrieve(key, loader)` trả kiểu gì?  
**Đáp án:** `CompletableFuture<T>` của giá trị được cache hoặc nạp.

**9.** Supplier của overload có loader có được trả null future reference không?  
**Đáp án:** Không nên; nó phải trả một `CompletableFuture<T>` hợp lệ.

**10.** Một future do loader trả ra hoàn tất với null có chắc chắn là deferred miss không?  
**Đáp án:** Không; null có thể là giá trị nghiệp vụ T theo null policy.

**11.** `setAsyncCacheMode(true)` có trên interface `CacheManager` chung không?  
**Đáp án:** Không; đây là API của `CaffeineCacheManager`.

**12.** Chỉ gọi API `Cache.retrieve` trực tiếp có cần `@EnableCaching` không?  
**Đáp án:** Không; `@EnableCaching` dùng cho annotation-driven interception.

**13.** Async retrieval có biến cache Caffeine thành distributed cache không?  
**Đáp án:** Không; Caffeine mặc định là local JVM cache.

**14.** Tại sao không dùng `Thread.sleep` để test future hoàn tất?  
**Đáp án:** Test dễ phụ thuộc scheduler và flaky; dùng future hoặc latch để điều khiển thời điểm.

**15.** Cached null và database không còn record có phải giống nhau mãi không?  
**Đáp án:** Không; cached null là snapshot “không tìm thấy” tại thời điểm cache. Nguồn có thể thay đổi, cần TTL/invalidation.

## Tài liệu tham khảo

- Spring Framework 6.2.10 — Cache Javadoc, `retrieve(Object)`, `retrieve(Object, Supplier)`: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework 6.2.10 — CaffeineCacheManager Javadoc: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework 6.2.10 — SimpleValueWrapper Javadoc: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/support/SimpleValueWrapper.html
- Caffeine — Population and asynchronous loading: https://github.com/ben-manes/caffeine/wiki/Population
