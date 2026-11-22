# Lưu giá trị do `CompletableFuture` hoàn tất trong Spring Cache

## 1. Mục tiêu và bối cảnh

Trong một ứng dụng Spring, nhiều service không trả kết quả ngay mà trả về `CompletableFuture<T>` để biểu diễn một công việc sẽ hoàn thành sau. Nếu áp dụng cache không đúng cách, ta có thể vô tình cache **đối tượng future chưa hoàn tất**, trả dữ liệu cũ, chạy lặp lại nhiều tác vụ đắt tiền hoặc không xử lý được future hoàn tất bằng exception.

Từ **Spring Framework 6.1**, cache abstraction hỗ trợ các method trả về `CompletableFuture` theo cách nhận biết kết quả bất đồng bộ: khi future hoàn tất thành công, **giá trị `T` do nó tạo ra** mới là kết quả có ý nghĩa đối với cache. Khi cache hit, Spring có thể chuyển giá trị đã cache về hình thức `CompletableFuture<T>` mà phương thức khai báo. Hành vi cụ thể và khả năng non-blocking phụ thuộc cache provider.

Bài này giúp bạn:

1. Phân biệt `CompletableFuture<T>` (đại diện cho công việc) và `T` (giá trị nhận được khi công việc hoàn tất).
2. Hiểu miss, load bất đồng bộ, hoàn tất thành công, hoàn tất lỗi và cache hit.
3. Cấu hình `@Cacheable` đúng cho phương thức trả `CompletableFuture<T>` với Spring 6.1+.
4. Biết vì sao provider phải hỗ trợ truy xuất bất đồng bộ; cấu hình **Caffeine async cache mode**.
5. Hiểu `sync=true` khi nhiều request cùng miss một key và giới hạn của cơ chế này.
6. Xử lý invalidation, TTL, transaction, exception và kết quả null.
7. Chạy ví dụ Java 17 + Spring Boot 3.3.5 và kiểm thử dữ liệu được cache sau khi future hoàn tất.

**Điểm cốt lõi:** `@Cacheable` trên method trả future không phải lời hứa rằng cache sẽ lưu một `CompletableFuture` chưa hoàn tất như dữ liệu nghiệp vụ. Với tích hợp Spring 6.1+ thích hợp, kết quả thành công của future được dùng làm cache value; backend có thể lưu một future nội bộ để phối hợp việc load, nhưng contract mà caller cần hiểu vẫn là giá trị `T`.

## 2. Nhắc lại `CompletableFuture<T>` là gì?

Một `CompletableFuture<T>` là đối tượng biểu diễn một phép tính có thể hoàn tất trong tương lai. Nó có ba trạng thái khái quát:

~~~text
               CompletableFuture<T>
                        |
                 NOT_COMPLETED
                    /      \
                   v        v
           COMPLETED(T)   COMPLETED_EXCEPTIONALLY
                   |        |
                result    Throwable
~~~

Ví dụ Java thuần:

~~~java
CompletableFuture<String> task =
        CompletableFuture.supplyAsync(() -> "Hello");

String value = task.join();
System.out.println(value);
~~~

Output:

~~~text
Hello
~~~

`task` là đại diện cho công việc; `"Hello"` là kết quả đã hoàn tất. `join()` chờ kết quả và ném `CompletionException` nếu future thất bại. Trong ứng dụng phục vụ request bất đồng bộ, không nên tùy tiện `join()` ở thread xử lý request vì sẽ chặn thread; ví dụ console trong bài dùng `join()` để xác nhận kết quả dễ quan sát.

### Tại sao phải phân biệt hai đối tượng?

Giả sử method sau tải một sản phẩm:

~~~java
// Minh họa trong một Spring-managed service.
public CompletableFuture<Product> load(String productId) {
    return CompletableFuture.supplyAsync(
            () -> repository.findById(productId));
}
~~~

Có hai thứ:

- Đối tượng `CompletableFuture<Product>` được trả gần như ngay lập tức.
- Đối tượng `Product` được tạo sau khi truy vấn hoàn tất.

Nếu cache lưu nhầm future chưa hoàn tất như một giá trị nghiệp vụ thông thường, cache có thể gắn với trạng thái sống của tác vụ, exception/cancellation hoặc `Executor` thay vì một snapshot `Product` dùng lại được. Spring 6.1+ đưa ra cơ chế cache-aware để làm việc với các kết quả kiểu này.

## 3. Cơ chế `@Cacheable` với future hoàn tất

~~~java
// Ví dụ ý tưởng; Product và repository do ứng dụng định nghĩa.
@Cacheable(cacheNames = "products", key = "#p0")
public CompletableFuture<Product> find(String id) {
    return CompletableFuture.supplyAsync(
            () -> repository.findById(id));
}
~~~

Trong Spring 6.1+, khi provider hỗ trợ đường truy cập bất đồng bộ, luồng logic có thể hiểu như sau:

~~~text
Caller: find("P1")
        |
        v
Spring Cache interceptor
        |
        +--> cache HIT
        |       |
        |       +--> tạo/trả CompletableFuture chứa giá trị đã cache
        |
        +--> cache MISS
                |
                v
         chạy method find("P1")
                |
                v
         CompletableFuture<Product> đang chạy
                |
          +-----+------+
          |            |
       thành công     thất bại
          |            |
          v            v
     Product mới    Exception
          |            |
          v            +--> không phải giá trị Product thành công
     hoàn tất và          để cache như hit bình thường
     cập nhật cache
          |
          v
     Caller nhận Product qua future
~~~

Đối với future hoàn tất thành công, cache entry đại diện cho kết quả tải được. Với future hoàn tất lỗi, không nên suy rằng một `Product` hợp lệ đã được cache; cách cleanup/retry exception phụ thuộc provider và đường tích hợp, cần test trên backend thực tế.

### Thời điểm nào cache có dữ liệu?

Không nên suy rằng **ngay khi method vừa trả về** future thì cache đã có `Product`. Có thể future còn pending và loader chưa tạo giá trị. Đặc biệt, nếu method trả future từ network hoặc DB client, quãng thời gian từ lúc tạo future đến khi hoàn tất có thể đáng kể.

Đối với provider dùng `AsyncCache`, nó có thể lưu một pending future nội bộ nhằm chia sẻ tác vụ đang thực hiện. Vì vậy phát biểu chính xác là: **giá trị hoàn tất thành công là kết quả cache có ý nghĩa**, còn representation nội bộ của provider có thể là một future.

### Phân biệt hai cách tiếp cận

| Cách | Ý nghĩa |
| --- | --- |
| Cache-aware Spring 6.1+ | Hỗ trợ method `CompletableFuture<T>` và chuyển đổi kết quả bất đồng bộ theo provider |
| Tự `Map<String, CompletableFuture<T>>` | Lưu trực tiếp future; cần tự xử lý exception, hủy, xóa future lỗi và vòng đời |
| Tự `Map<String, T>` sau `thenAccept` | Tự ghi value khi hoàn tất; phải tự xử lý race, miss đồng thời, invalidate, lỗi |
| `@Cacheable` trên method đồng bộ trả `T` | Hợp đồng truyền thống, không có future |

Đừng tự cài `Map<String, CompletableFuture<T>>` chỉ để tránh đọc kỹ tính năng của Spring Cache; một cache future thủ công rất dễ giữ mãi future đã fail hoặc trả kết quả stale sau update.

## 4. Điều kiện kỹ thuật: Spring Framework và cache provider

Khả năng xử lý future-returning cache methods được giới thiệu trong **Spring Framework 6.1**. Đối với Spring Boot, cần một phiên bản quản lý Spring Framework tương thích, chẳng hạn Spring Boot 3.2 trở lên. Ví dụ trong bài dùng **Spring Boot 3.3.5**, chạy trên **Java 17**.

Không chỉ version của Spring mới quan trọng: cache provider cần hỗ trợ thao tác truy xuất phù hợp với return type bất đồng bộ. Hợp đồng `org.springframework.cache.Cache` có các phương thức như:

~~~java
// Chữ ký API được đơn giản hóa để giải thích, không phải class tự tạo.
CompletableFuture<?> retrieve(Object key);

<T> CompletableFuture<T> retrieve(
        Object key,
        Supplier<CompletableFuture<T>> valueLoader);
~~~

Các phương thức này giúp cache backend lấy value hoặc phối hợp load dưới dạng future. Provider có thể không hỗ trợ đầy đủ non-blocking retrieval. Không nên mặc định mọi bản Redis, Ehcache, JCache hoặc custom `Cache` implementation đều có cùng behavior chỉ vì hỗ trợ `Cache.get()` đồng bộ.

### Caffeine async cache mode

`CaffeineCacheManager` hỗ trợ `setAsyncCacheMode(true)` từ Spring Framework 6.1 để tạo các vùng cache có khả năng truy cập bất đồng bộ. Đây là một lựa chọn phù hợp cho `@Cacheable` trả `CompletableFuture<T>`:

~~~java
@Bean
CaffeineCacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("products");

    manager.setAsyncCacheMode(true);
    return manager;
}
~~~

`CaffeineCacheManager` còn có thể cấu hình `maximumSize`, `expireAfterWrite`, `recordStats` và các chính sách khác để tránh cache tăng không giới hạn. `setAsyncCacheMode(true)` **không tự đặt TTL hoặc capacity**.

Khi không bật async cache mode, đừng suy rằng `CompletableFuture` luôn được lưu/tải không chặn với đúng ngữ nghĩa mong muốn. Hãy kiểm tra đường xử lý trên provider, phiên bản và bài test thực tế.

### `@EnableCaching` vẫn cần thiết

~~~java
@SpringBootApplication
@EnableCaching
public class Application {
    // Spring Boot application
}
~~~

`@EnableCaching` kích hoạt caching interceptor. Một dependency Caffeine hoặc một future trả về từ method **không tự kích hoạt** caching.

## 5. `sync=true` và nhiều request cùng miss

Nếu mười request đồng thời gọi `find("P1")` khi cache trống, `@Cacheable(sync = false)` (mặc định) có thể cho nhiều lời gọi cùng chạy loader. Điều đó gây cache stampede nếu loader đắt tiền.

~~~java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public CompletableFuture<Product> find(String id) {
    return repository.findAsync(id);
}
~~~

`sync = true` đề nghị cache provider điều phối **cùng key** trên đường cache miss. Với provider có hỗ trợ `retrieve(key, valueLoader)` phù hợp, các caller có thể dùng chung một lần tính đang diễn ra thay vì gọi loader nhiều lần.

~~~text
Caller A: find(P1) -> MISS -> bắt đầu future load P1
Caller B: find(P1) -> đợi/chia sẻ computation P1
Caller C: find(P1) -> đợi/chia sẻ computation P1

Future hoàn tất Product(P1)
       |
       +--> A nhận Product
       +--> B nhận Product
       +--> C nhận Product
~~~

**Không được đánh đồng** `sync=true` với distributed lock trên nhiều JVM. Nếu mỗi application instance có cache Caffeine local riêng, App A và App B vẫn có thể mỗi bên chạy một loader. Khả năng phối hợp phụ thuộc backend và topology.

### Hạn chế của synchronized caching

Theo hợp đồng `@Cacheable`, khi bật `sync=true`:

- Chỉ một vùng cache được chỉ định cho operation.
- Không hỗ trợ kết hợp với `unless`.
- Không kết hợp với nhiều cache operation khác trên cùng method được đồng bộ.
- Provider cần hỗ trợ việc tải đồng bộ; `sync=true` là gợi ý chứ không tự bảo đảm exactly-once toàn cụm.

Ví dụ không nên dùng:

~~~java
// Không hợp lệ theo hợp đồng sync=true + unless.
@Cacheable(
        cacheNames = "products",
        key = "#p0",
        sync = true,
        unless = "#result == null"
)
public CompletableFuture<Product> find(String id) {
    return repository.findAsync(id);
}
~~~

Nếu cần vừa single-flight vừa loại trừ một số kết quả khỏi cache, phải thiết kế theo provider và chính sách dữ liệu thực tế; không thể chỉ gắn `unless` vào `sync=true`.

## 6. Ví dụ chạy được: Java 17 + Spring Boot + Caffeine

Ta tạo ứng dụng console nhỏ chứng minh:

1. Hai caller có thể xin cùng một key trước khi loader hoàn tất.
2. `@Cacheable(sync=true)` kết hợp Caffeine async mode dùng lại cùng kết quả.
3. Future hoàn tất thành công trả `Book` thực; lần gọi sau cache hit.
4. `@CacheEvict` loại entry sau khi source thay đổi.
5. Lần đọc kế tiếp nạp `Book` mới thay vì giữ giá trị cũ.

Sử dụng Spring Boot 3.3.5 và Maven, không cần web server hay database ngoài.

### Cấu trúc thư mục

~~~text
future-cache-demo/
├── pom.xml
└── src/main/java/example/futurecache/
    ├── DemoApplication.java
    └── BookService.java
~~~

### `pom.xml`

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
    <artifactId>future-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
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

Spring Boot parent quản lý phiên bản các dependency tương thích. Thư viện Caffeine được thêm riêng vì `spring-boot-starter-cache` không tự cài mọi provider.

### `src/main/java/example/futurecache/BookService.java`

~~~java
package example.futurecache;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    public record Book(String id, String title, int version) {}

    private final ConcurrentMap<String, Book> source =
            new ConcurrentHashMap<>();
    private final AtomicInteger loads = new AtomicInteger();

    public BookService() {
        source.put("B1", new Book("B1", "First Edition", 1));
    }

    @Cacheable(cacheNames = "books", key = "#p0", sync = true)
    public CompletableFuture<Book> find(String id) {
        return CompletableFuture.supplyAsync(() -> {
            loads.incrementAndGet();

            Book book = source.get(id);
            if (book == null) {
                throw new IllegalArgumentException("Unknown book: " + id);
            }

            return book;
        });
    }

    @CacheEvict(cacheNames = "books", key = "#p0")
    public void rename(String id, String newTitle) {
        source.compute(id, (key, oldValue) -> {
            if (oldValue == null) {
                throw new IllegalArgumentException("Unknown book: " + id);
            }

            return new Book(
                    id,
                    newTitle,
                    oldValue.version() + 1);
        });
    }

    public int loads() {
        return loads.get();
    }
}
~~~

Giải thích:

- `find` **trả ngay một future**; phép đọc nguồn chạy bằng `CompletableFuture.supplyAsync` trên common pool.
- `loads.incrementAndGet()` nằm **bên trong** tác vụ nên đếm lần loader thật chạy, không đếm số lần caller chỉ nhận future.
- `@Cacheable(sync=true)` để cache provider phối hợp lời gọi cùng key khi miss.
- `rename` thay source rồi `@CacheEvict` xóa cache entry theo cùng ID sau khi method hoàn thành bình thường.
- `Book` là record bất biến; đó là kiểu value phù hợp để cache hơn một object mutable đang bị các thread chỉnh sửa.

`CompletableFuture.supplyAsync` dùng common pool trong ví dụ, không đại diện cho cấu hình executor production. Ứng dụng thật nên dùng executor có giới hạn thread/queue, theo dõi tải và tránh đặt blocking I/O không kiểm soát lên common pool.

### `src/main/java/example/futurecache/DemoApplication.java`

~~~java
package example.futurecache;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CaffeineCacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager("books");
        manager.setAsyncCacheMode(true);
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(1000)
                .expireAfterWrite(Duration.ofMinutes(5)));
        return manager;
    }

    @Bean
    CommandLineRunner demo(BookService books) {
        return args -> {
            CompletableFuture<BookService.Book> first = books.find("B1");
            CompletableFuture<BookService.Book> second = books.find("B1");

            System.out.println("first=" + first.join());
            System.out.println("second=" + second.join());
            System.out.println("loads-after-two=" + books.loads());

            System.out.println("hit=" + books.find("B1").join());
            System.out.println("loads-after-hit=" + books.loads());

            books.rename("B1", "Revised Edition");
            System.out.println("after-evict=" + books.find("B1").join());
            System.out.println("loads-after-evict=" + books.loads());
        };
    }
}
~~~

### Chạy chương trình

Đặt đúng tên/package của hai file Java như cấu trúc ở trên. Với JDK 17+ và Maven:

~~~bash
cd future-cache-demo
mvn -q spring-boot:run
~~~

Ngoài log khởi động của Spring Boot, những dòng do `CommandLineRunner` in là:

~~~text
first=Book[id=B1, title=First Edition, version=1]
second=Book[id=B1, title=First Edition, version=1]
loads-after-two=1
hit=Book[id=B1, title=First Edition, version=1]
loads-after-hit=1
after-evict=Book[id=B1, title=Revised Edition, version=2]
loads-after-evict=2
~~~

Giải thích:

1. Hai lời gọi `find("B1")` dùng cùng cache name/key. Với Caffeine async mode và `sync=true`, chúng dùng chung computation cho cùng entry trong cache instance hiện tại.
2. Cả hai future hoàn tất với `Book(B1, First Edition, v1)`. `loads-after-two=1` cho biết loader thật chạy một lần.
3. Lần `find` kế tiếp hit, không tăng `loads`.
4. `rename` sửa source thành `Revised Edition/v2`, sau đó evict `"B1"`; lần tìm kế tiếp miss, chạy loader và trả bản mới. Bộ đếm thành 2.

**Lưu ý giới hạn:** demo chạy trong một JVM với cache Caffeine local; không chứng minh single-flight giữa nhiều máy. Nó cũng không kiểm chứng transaction DB, TTL thật sau 5 phút hoặc thao tác lỗi. Đó là những trường hợp cần test riêng. Kết quả ở trên dựa trên đường hỗ trợ Spring 6.1+/Caffeine async mode đã nêu.

## 7. Vì sao `join()` không nên có trong method cache?

Một cách viết có thể làm mất ích lợi của bất đồng bộ:

~~~java
// PHẢN VÍ DỤ: thực tế chặn thread để đợi tác vụ hoàn tất.
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBlocking(String id) {
    return repository.findAsync(id).join();
}
~~~

Về mặt khai báo, method này trả `Book` đồng bộ, không phải `CompletableFuture<Book>`. Thread gọi phải chờ; cache vẫn có thể lưu `Book`, nhưng API không còn biểu diễn một thao tác bất đồng bộ.

Một phản ví dụ khác:

~~~java
// PHẢN VÍ DỤ: future được tạo rồi đợi ngay, vẫn không non-blocking.
public CompletableFuture<Book> find(String id) {
    Book value = repository.findAsync(id).join();
    return CompletableFuture.completedFuture(value);
}
~~~

Method trả future nhưng thân đã chặn thread trước khi return. `@Cacheable` không thể tự biến synchronous blocking work thành I/O không chặn.

Cách phù hợp là trả future của tác vụ thật:

~~~java
// Minh họa; repository có API bất đồng bộ thực sự.
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> find(String id) {
    return repository.findAsync(id);
}
~~~

Ứng dụng ở tầng caller có thể dùng `thenApply`, `thenCompose`, `handle` hoặc API HTTP có hỗ trợ `CompletableFuture`, thay vì chặn bằng `get()`/`join()`.

## 8. `CompletableFuture` hoàn tất lỗi: cache gì?

Một tác vụ có thể kết thúc bằng exception:

~~~java
public CompletableFuture<Book> load(String id) {
    return CompletableFuture.supplyAsync(() -> {
        throw new IllegalStateException("Database unavailable");
    });
}
~~~

Future này **không tạo ra một `Book` thành công**. Spring không thể xem exception như một kết quả `Book` bình thường để dùng lại. Với cache implementation hỗ trợ future, các entry load thất bại cần được xử lý phù hợp để lần gọi sau có thể thử lại; behavior cụ thể phải được xác minh trên provider và phiên bản đang chạy.

### Những lỗi thực tế

- **Timeout**: loader có thể hoàn tất lỗi sau khi cache đang giữ trạng thái in-flight.
- **Cancellation**: một caller hủy future; không được mặc định hủy một caller tương đương hủy toàn bộ shared load.
- **RejectedExecutionException**: executor quá tải, không nhận thêm task.
- **Network/database failure**: lỗi tạm thời có thể phục hồi; cache exception lâu dài thường không phù hợp.
- **Circuit breaker**: cần xác định lỗi nào được trả và khi nào retry.
- **Partial side effect**: future lỗi nhưng source có thể đã đổi; cache và DB cần quy tắc consistency riêng.

Chẳng hạn:

~~~java
CompletableFuture<Book> future = books.find("missing-id");

future.whenComplete((book, error) -> {
    if (error != null) {
        // Ghi nhận lỗi và trả trạng thái phù hợp cho caller.
    } else {
        // Chỉ sử dụng book khi future hoàn tất thành công.
    }
});
~~~

Đoạn trên là cách xử lý ở caller; `books` thuộc ví dụ. Đừng cache trực tiếp `error.getMessage()` vào cache `Book` để tránh trả sai kiểu và giữ thông tin lỗi không phù hợp.

### Có nên cache kết quả "không tìm thấy"?

Nếu method trả null hoặc `Optional.empty()`, chính sách negative caching phải được cân nhắc. Caffeine async cache và Spring Cache có thể có quy tắc riêng về null/placeholder và cache hit. Với `sync=true`, không thể dùng `unless` để bỏ cache null. Có thể chọn một kết quả biểu diễn rõ ràng `NotFound`, TTL ngắn và key theo scope, hoặc thiết kế loader ném một exception phù hợp rồi test policy retry. Không dựa vào giả định mọi provider xử lý null giống nhau.

## 9. Giá trị bất biến, mutation và cache consistency

Sau khi future hoàn tất, cache có thể giữ tham chiếu tới đối tượng `Book` hoặc một bản copy theo provider. Nếu value là object mutable, những thread khác có thể thấy thay đổi mà không có một cache put rõ ràng.

~~~java
// DTO mutable có thể khiến việc cache dữ liệu khó kiểm soát.
public class MutableBook {
    public String title;
}
~~~

Ưu tiên immutable value:

~~~java
public record Book(String id, String title, int version) {}
~~~

Trong demo, mỗi lần đổi tên tạo record mới. Điều này giúp tránh trường hợp một thread trực tiếp sửa object đã được cache.

### Khi future hoàn tất sau khi dữ liệu đã bị cập nhật

Một race cần đặc biệt cẩn thận:

~~~text
T1  find(P1) miss, future A tải version 1 và đang pending
T2  update(P1) ghi version 2, evict/put cache
T3  future A hoàn tất với version 1
T4  nếu thứ tự ghi không được kiểm soát, cache có thể stale
~~~

`sync=true` chủ yếu phối hợp load cùng key trên miss. Nó **không tự tạo transaction nguyên tử** giữa future, DB, `@CachePut`/`@CacheEvict` và mọi writer khác. Provider có thể bảo vệ một số race cụ thể, nhưng cần test các tình huống pending load và invalidation trên backend thực tế.

Biện pháp thường gặp:

- Kèm version/update timestamp có ngữ nghĩa rõ, từ nguồn tin cậy.
- Tránh put kết quả có version cũ hơn entry đang có.
- Invalidation sau transaction commit hoặc sử dụng transaction-aware cache khi phù hợp.
- Thiết kế event invalidation và retry khi nhiều instance cùng đọc/ghi.
- Chấp nhận TTL ngắn hoặc stale window nếu nghiệp vụ cho phép, nhưng công bố rõ SLA độ mới.

Một cache hit cũng có thể bỏ qua thân method `find`. Vì vậy **không chỉ kiểm tra quyền trong thân method được cache**. Đặt authorization tại ranh giới luôn chạy trước truy xuất dữ liệu và tạo key theo tenant/user/role/projection nếu kết quả phụ thuộc scope.

## 10. `@CachePut` với kết quả bất đồng bộ

Spring Cache có operation riêng `@CachePut`: method luôn được thực thi, và cache được cập nhật theo giá trị trả về. Trong mô hình Spring 6.1+ hỗ trợ `CompletableFuture`, giá trị thành công do future hoàn tất mới là kết quả cần put, không phải phép tính pending được caller nhìn thấy.

~~~java
// Minh họa trong một service có repository bất đồng bộ.
@CachePut(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> renameAsync(String id, String title) {
    return repository.renameAsync(id, title);
}
~~~

Khi `renameAsync` hoàn tất với `Book` mới, cache được cập nhật cho key `id`. Nếu method trả `CompletableFuture<Void>` hoặc `CompletableFuture<Boolean>`, đừng gắn `@CachePut` vào cache vốn chứa `Book`: kiểu kết quả không đúng với reader. Trong trường hợp chỉ biết update thành công/thất bại, một lộ trình evict để đọc lại từ source thường dễ kiểm soát hơn.

**Lưu ý:** `@CachePut` và `@Cacheable` không nên tùy tiện cùng đặt trên một method, nhất là future-returning method; một bên đòi chạy method, một bên có thể bỏ qua method khi hit. Hãy tách read và write, có key contract thống nhất.

### `@CacheEvict` và thời điểm xóa

Với method cập nhật đồng bộ như demo:

~~~java
@CacheEvict(cacheNames = "books", key = "#p0")
public void rename(String id, String title) {
    source.update(id, title);
}
~~~

Spring xóa entry theo ngữ nghĩa `@CacheEvict` sau khi method hoàn thành thành công, nếu dùng mặc định `beforeInvocation=false`. Ở đây `source.update` chỉ là minh họa. Khi method cập nhật tự trả future, đừng giả định thời điểm xóa trùng hoàn toàn với database commit: cần kiểm tra hành vi async của framework/provider/transaction trên phiên bản triển khai và tốt nhất có integration test.

## 11. TTL, số entry và lỗi stampede

Future hoàn tất không có nghĩa kết quả được lưu vĩnh viễn hoặc sẽ tự hết hạn. TTL, capacity và eviction là chính sách **cache provider**, không phải thuộc tính mặc định của `CompletableFuture`.

Ví dụ cấu hình trong demo:

~~~java
manager.setCaffeine(Caffeine.newBuilder()
        .maximumSize(1000)
        .expireAfterWrite(Duration.ofMinutes(5)));
~~~

- `maximumSize(1000)` đặt giới hạn số entry mục tiêu cho từng cache instance, **không phải byte heap**.
- `expireAfterWrite(5 phút)` làm value hết hạn tính từ lần ghi; các lần hit không tự kéo dài thời hạn theo chính sách này.
- Khi entry hết hạn, lần truy cập tiếp theo có thể khởi tạo future load mới.
- Nếu nhiều key nóng hết hạn cùng lúc, nhiều backend calls có thể tăng đột biến.

`sync=true` giúp điều phối cùng key trên phạm vi provider; nó không bảo đảm phối hợp giữa các application instance có cache local riêng. Với nhiều JVM dùng shared Redis, lưu chung entry không tự chứng minh loader được khóa phân tán.

### Đừng dùng raw future làm cache key

~~~java
// PHẢN VÍ DỤ: key phụ thuộc một object trạng thái động.
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> find(CompletableFuture<String> idFuture) {
    // Không phù hợp: idFuture không phải business ID ổn định.
}
~~~

Nên cache theo định danh nghiệp vụ bất biến, ví dụ `String id`, đồng thời xét tenant, projection và locale nếu ảnh hưởng kết quả. Key có timestamp hoặc UUID mới mỗi request có thể khiến cache vô dụng và tăng cardinality.

## 12. Kiểm thử: chứng minh kết quả được cache sau completion

Kiểm thử đơn vị chỉ `new BookService()` không kích hoạt proxy của Spring. Với caching annotation, hãy test qua **Spring-managed bean**.

### Những trường hợp cần bao phủ

| Tình huống | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Cache miss | Key chưa có entry | Method trả future và loader chạy |
| Completion thành công | Future hoàn tất `Book` | Các lần đọc tiếp theo dùng kết quả cache |
| Cache hit | Gọi lại cùng key sau completion | Không tăng số lần loader |
| Hai miss đồng thời | Hai caller cùng key, `sync=true` | Một lần loader nếu provider hỗ trợ |
| Hai key khác nhau | Gọi `"B1"` và `"B2"` | Hai entry độc lập |
| Eviction sau update | Update source rồi evict | Lần đọc sau tải version mới |
| Lỗi loader | Future hoàn tất exceptionally | Caller nhận lỗi, không trả `Book` giả |
| Cancellation | Hủy future của một caller | Quan sát semantics của shared load/provider |
| TTL | Expire entry bằng ticker/test clock | Lần đọc sau phải load lại |
| Self-invocation | Gọi `this.find` trong cùng bean | Có thể bypass proxy |
| Multi-instance | Chạy hai JVM, local Caffeine | Không mặc định chia sẻ entry/coordination |
| Rollback/race | Update khi future cũ pending | Không trả version sai theo SLA |

### Dùng một future có thể hoàn tất thủ công

Để test thời điểm completion mà không cần `Thread.sleep`, có thể tạo `CompletableFuture<Book>` chưa hoàn tất, trả nó từ một loader được gọi qua Spring proxy, rồi trong test gọi `complete(book)`:

~~~java
// Pseudocode mô tả ý tưởng kiểm thử, không phải test class hoàn chỉnh.
CompletableFuture<Book> pending = new CompletableFuture<>();
loader.setNextFuture(pending);

CompletableFuture<Book> first = service.find("B1");
assertFalse(first.isDone());

pending.complete(new Book("B1", "New Book", 1));
assertEquals("New Book", first.join().title());

Book again = service.find("B1").join();
assertEquals("New Book", again.title());
assertEquals(1, loader.invocations());
~~~

Đoạn trên là pseudocode vì `loader`, `service` và các assert/test setup chưa được khai báo. Trong test thật, đảm bảo phần cache đã quan sát completion và việc put đã được hoàn tất trước khi khẳng định hit, tránh race kiểm thử. Kiểm soát executor/ticker khi có thể để test xác định.

### Test hai JVM khác gì test nhiều thread?

Hai thread cùng dùng một `CaffeineCacheManager` có thể phối hợp các lần miss. Hai process JVM có cache instance riêng nên có thể cùng load key `"B1"`. Nếu cần chứng minh coordination toàn cluster, hãy chạy hai process/container và đo loader count ở nguồn dùng chung; không suy từ unit test một JVM.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `@Cacheable` không có hiệu lực | Thiếu `@EnableCaching`, gọi nội bộ bean hoặc bean tạo bằng `new` | Bật caching, gọi qua Spring proxy |
| Hit trả sai kiểu | Tự lưu `CompletableFuture` như business value hoặc custom provider cũ | Dùng Spring 6.1+ và kiểm tra async cache contract |
| Future đã hoàn tất nhưng lần sau vẫn miss | Provider không hỗ trợ async retrieval/put phù hợp, key khác nhau | Kiểm tra `Cache.retrieve`, config và integration test |
| Hai request cùng chạy loader | `sync=false` hoặc provider không phối hợp in-flight | Dùng `sync=true` với provider hỗ trợ |
| `sync=true` gây lỗi cấu hình | Kết hợp nhiều cache hoặc `unless` | Tuân thủ giới hạn của synchronized caching |
| Cache giữ dữ liệu stale | Không invalidation sau update | Put/evict theo key và transaction |
| Future lỗi lặp đi lặp lại | Lỗi source/executor chưa phục hồi | Có retry/backoff, bulkhead/circuit breaker theo nghiệp vụ |
| Cache giữ future lỗi mãi | Cache future thủ công không cleanup | Xóa entry lỗi, dùng provider phù hợp |
| `join()` khiến API chậm | Block thread request ngay trong method | Trả future và compose bất đồng bộ |
| `@CachePut` ghi `Boolean` thay `Book` | Method update trả status | Dùng eviction hoặc trả `Book` mới |
| Lẫn tenant | Key chỉ gồm ID không duy nhất toàn bộ scope | Dùng key bao gồm tenant/scope đáng tin |
| Giá trị cache thay đổi bất ngờ | Cached object mutable, store-by-reference | Dùng immutable DTO/version |
| Tưởng cache tự đồng bộ giữa pod | Caffeine local từng JVM | Dùng shared cache/invalidation nếu cần |

## 14. Bài tập tự kiểm tra

**Bài 1.** Method `@Cacheable` trả `CompletableFuture<Book>` trong Spring 6.1+. Sau khi future hoàn tất thành công, cache đại diện cho dữ liệu gì?  
**Đáp án:** giá trị `Book` được tạo khi future hoàn tất, với representation nội bộ tùy provider; không phải business contract lưu một future pending mãi mãi.

**Bài 2.** `CompletableFuture<Book>` chưa hoàn tất thì có chắc cache đã có `Book` dùng lại không?  
**Đáp án:** không. Provider có thể giữ future đang chạy để chia sẻ tải, nhưng giá trị `Book` hoàn chỉnh chưa tồn tại cho tới khi completion thành công.

**Bài 3.** Có thể bật `@Cacheable(sync=true, unless="#result == null")` không?  
**Đáp án:** không. `sync=true` không hỗ trợ `unless` theo hợp đồng của Spring.

**Bài 4.** Hai replica cùng dùng Caffeine local, có bảo đảm chỉ một loader cho cùng ID trên toàn cụm không?  
**Đáp án:** không. Chúng có các cache instance riêng; đồng bộ trong một instance không tự lan qua JVM khác.

**Bài 5.** Future hoàn tất exceptionally. Có nên cache exception như `Book` thành công không?  
**Đáp án:** không. Cần xử lý lỗi và chính sách retry/fallback riêng; kiểm thử cleanup của provider.

**Bài 6.** `@CachePut` trên method trả `CompletableFuture<Boolean>` có phù hợp với cache chứa `Book` không?  
**Đáp án:** không. Giá trị hoàn tất là `Boolean`; nên trả `Book` phù hợp hoặc dùng eviction.

**Bài 7.** Vì sao ví dụ dùng `Book` record bất biến?  
**Đáp án:** tránh một caller sửa object đang được nhiều caller khác đọc từ cache; giá trị mới thể hiện bằng record mới/version mới.

**Bài 8.** `setAsyncCacheMode(true)` có tự đặt TTL năm phút không?  
**Đáp án:** không. Nó bật chế độ truy xuất Caffeine bất đồng bộ; TTL cần cấu hình riêng trên Caffeine builder.

**Bài 9.** Một test gọi `service.find("B1").join()` ngay khi source đang trả future lỗi, và thấy exception. Điều này chứng minh cache không hoạt động không?  
**Đáp án:** không. Nó có thể chứng minh loader lỗi; cần tách bài test thành công, lỗi, hit, retry và provider behavior.

**Bài 10.** Khi nào nên tránh dùng cache bất đồng bộ?  
**Đáp án:** khi kết quả không ổn định, rất nhạy cảm với authorization/version/transaction, cache miss không có lợi hoặc backend không có hỗ trợ phù hợp. Cân nhắc thiết kế nhất quán trước khi tối ưu.

## Tài liệu tham khảo

- Spring Framework – **Declarative Annotation-based Caching** (phần synchronized caching, CompletableFuture và reactive return types): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – **Cache Abstraction**: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework – Javadoc `org.springframework.cache.Cache`, các phương thức `retrieve`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework – Javadoc `CaffeineCacheManager`, `setAsyncCacheMode`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Boot – **Caching**: https://docs.spring.io/spring-boot/reference/io/caching.html
- Java 17 – `CompletableFuture` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Caffeine – **Eviction** và expiration: https://github.com/ben-manes/caffeine/wiki/Eviction

**Ghi nhớ:** với Spring Framework 6.1+ và provider hỗ trợ async retrieval, `@Cacheable` có thể xử lý method trả `CompletableFuture<T>` và cache **giá trị `T` khi future hoàn tất thành công**. Caffeine async mode giúp sử dụng đường truy cập phù hợp; `sync=true` giảm tải trùng cho cùng key trong phạm vi provider, không phải distributed lock. Hoàn tất bất đồng bộ không loại bỏ nhu cầu xử lý exception, invalidation, TTL, transaction, bảo mật và kiểm thử race.