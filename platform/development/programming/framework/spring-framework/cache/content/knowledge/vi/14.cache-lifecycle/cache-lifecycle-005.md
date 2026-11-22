# Cache kết quả không tồn tại và hệ quả khi dữ liệu được tạo sau đó

## 1. Tình huống: hôm qua “không có”, hôm nay đã có

Giả sử một API tìm sách theo mã `bookId`. Lần đầu truy vấn `B42`, cơ sở dữ liệu trả về “không tồn tại”. Một lúc sau, quản trị viên tạo sách `B42`. API tìm kiếm vẫn báo “không tìm thấy” dù database đã có bản ghi. Tại sao?

Một nguyên nhân phổ biến là **negative caching**: hệ thống đã ghi nhớ không chỉ kết quả tìm thấy, mà cả **kết quả không tìm thấy**. Khi phương thức gắn `@Cacheable` lần sau nhận cùng key, Spring có thể trả kết quả “không tồn tại” từ cache mà **không chạy phương thức truy vấn database**.

```text
T0: database không có B42
    getById("B42") -> cache MISS -> DB: not found
    cache["B42"] = <giá trị biểu diễn "không tìm thấy">

T1: một luồng khác tạo B42 trong database
    database["B42"] = Book("B42", "New Book")
    cache["B42"] vẫn là <không tìm thấy> nếu không được invalidated

T2: getById("B42") -> cache HIT
    trả "không tìm thấy" từ cache, KHÔNG đọc database mới

T3: evict/expire/put lại đúng key
    getById("B42") -> cache MISS hoặc HIT giá trị mới
    người gọi mới nhìn thấy Book("B42", "New Book")
```

**Kết luận:** cache không tự quan sát thay đổi từ database. Một nhận định “không tồn tại” ở thời điểm T0 **không phải sự thật vĩnh viễn**. Nếu cache giữ nhận định ấy quá lâu, ứng dụng sẽ gặp tình trạng “bản ghi đã được tạo nhưng vẫn 404”.

Đây là vấn đề **vòng đời dữ liệu và tính nhất quán**, không phải lỗi riêng của annotation `@Cacheable`.

## 2. “Cache miss” khác “cache có giá trị null”

Cần phân biệt hai trạng thái bằng tư duy rõ ràng:

- **Cache miss:** không có mapping tương ứng với key. Spring phải gọi phương thức đích để lấy dữ liệu theo cấu hình operation.
- **Cache hit chứa kết quả không tồn tại:** mapping đã có, nhưng giá trị nghiệp vụ được lưu mang ý nghĩa “không có bản ghi”. Spring có thể **không gọi phương thức đích**, trả lại biểu diễn rỗng.

Một phương thức đơn giản:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book find(String bookId) {
    return repository.find(bookId); // trả null nếu không tìm thấy
}
```

*Đây là đoạn minh họa, chưa phải chương trình độc lập; `Book` và `repository` chưa được định nghĩa.*

Nếu cache provider cho phép lưu giá trị `null` thông qua Spring abstraction, lời gọi đầu trả `null` có thể làm cache lưu **một entry biểu diễn null**. Lần tiếp theo, với cùng key, Spring nhìn thấy entry và trả lại `null` mà không vào `repository.find`.

**Không phải cache provider nào cũng xử lý null giống nhau.** Một số hỗ trợ hoặc chuyển `null` sang sentinel nội bộ; một số cấu hình không cho phép lưu `null`; một số adapter có thể từ chối thao tác put null. Do đó, đừng kết luận “Spring luôn cache null” mà không biết `CacheManager` và provider của ứng dụng.

### 2.1. Cách Spring phân biệt bằng `Cache.ValueWrapper`

Khi dùng API `Cache` trực tiếp:

```java
Cache.ValueWrapper wrapper = cache.get("B42");

if (wrapper == null) {
    System.out.println("MISS: entry không tồn tại");
} else if (wrapper.get() == null) {
    System.out.println("HIT: entry biểu diễn kết quả null");
} else {
    System.out.println("HIT: có đối tượng thực");
}
```

*Đây là ví dụ dùng trong method đã có biến `Cache cache`; các import tương ứng phải được bổ sung.*

Với cache có thể chứa null như `ConcurrentMapCache` mặc định, cả hai biểu thức sau có ý nghĩa **khác nhau**:

- `cache.get(key) == null`: không có entry.
- `cache.get(key) != null && cache.get(key).get() == null`: có entry, **giá trị người dùng là null**.

Không dùng `cache.get(key, Book.class) == null` để khẳng định chắc là miss, vì đường truy xuất trả giá trị đã unwrapped có thể không phân biệt được “không có mapping” và “mapping chứa null”.

### 2.2. `ConcurrentMapCacheManager` và giá trị null

`ConcurrentMapCacheManager` của Spring Framework **mặc định cho phép null** bằng cách chuyển `null` thành một đối tượng đại diện bên trong, dù `ConcurrentHashMap` của Java không hỗ trợ lưu `null` trực tiếp. Cấu hình liên quan:

```java
@Bean
CacheManager cacheManager() {
    ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("books");
    manager.setAllowNullValues(true);
    return manager;
}
```

*Đoạn này chỉ là một bean trong lớp cấu hình, không phải file Java độc lập.*

Nếu thay bằng `manager.setAllowNullValues(false)`, provider này không được phép lưu null. Nhưng **tắt allowNullValues không đồng nghĩa tự động kích hoạt một chính sách fallback hoặc reload hợp lệ**: nếu method thực sự trả null mà operation vẫn cố put, có thể phát sinh lỗi. Khi mục tiêu là “trả null cho caller nhưng không cache null”, cấu hình rõ ràng bằng `unless` là lựa chọn dễ hiểu.

## 3. `Optional.empty()` có thể trở thành một kết quả âm được cache

Không chỉ method trả `null` mới gặp vấn đề. Spring Cache hỗ trợ `java.util.Optional<T>`:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Optional<Book> find(String bookId) {
    return repository.findOptional(bookId);
}
```

*Đây là đoạn minh họa; cần định nghĩa `Book` và repository.*

Trong các phiên bản Spring Framework hỗ trợ `Optional` theo cache abstraction:

- `Optional.of(book)` được **unwrap** để lưu giá trị `book`.
- `Optional.empty()` được coi là kết quả **null** ở tầng cache.
- Khi cache hit chứa dữ liệu, Spring dựng lại dạng trả về phù hợp với method, ví dụ `Optional.of(book)` hoặc `Optional.empty()`.

Vì vậy không nên mặc định “dùng Optional thì không cache kết quả không tồn tại”. `Optional` làm rõ hợp đồng Java của method, **không tự định nghĩa chính sách có lưu kết quả rỗng hay không**.

Với `unless = "#result == null"`, Spring sử dụng `#result` là **đối tượng nghiệp vụ sau khi unwrap Optional**, không phải chính wrapper `Optional`. Khi method trả `Optional.empty()`, biểu thức này có thể veto cache put.

Nếu method ném `NoSuchElementException`, `ResponseStatusException` hoặc ngoại lệ tùy chỉnh thay vì trả `Optional.empty()`, đó là một kịch bản khác: **`@Cacheable` thông thường không cache exception bằng cơ chế lưu kết quả trả về**, vì method chưa hoàn thành bình thường. Một HTTP gateway hoặc cache tầng web có thể cache HTTP 404 theo chính sách riêng; không nên đánh đồng với cache method Spring.

## 4. Hai chính sách: lưu âm hay chỉ lưu kết quả dương?

### 4.1. Chính sách A — Negative caching

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(String id) {
    return repository.find(id);  // có thể trả null
}
```

Nếu provider cho phép null, entry "không tồn tại" được nhớ lại. Lợi ích là những ID không có thật bị truy vấn nhiều lần sẽ **không phải đọc database liên tục**. Tuy nhiên khi một ID được tạo sau đó, cache có thể tiếp tục báo không tồn tại tới khi entry hết hạn hoặc bị xóa/cập nhật.

Thích hợp hơn khi:

- phần lớn key âm thực sự lâu dài không tồn tại;
- các request tìm ID không có thật rất thường xuyên, cần giảm tải database;
- có **TTL âm ngắn**, invalidation khi tạo hoặc cơ chế version hóa đáng tin;
- business chấp nhận một cửa sổ dữ liệu trễ có kiểm soát.

Ví dụ: hệ thống kiểm tra một mã chưa từng cấp phát, có thể cache “không tồn tại” trong **thời gian ngắn**. Không nên chọn một TTL dài cho âm chỉ vì TTL dương dài.

### 4.2. Chính sách B — Không cache kết quả rỗng

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public Book findBook(String id) {
    return repository.find(id);
}
```

`unless` là biểu thức SpEL được đánh giá **sau khi method chạy** ở lượt miss. Khi kết quả là `null`, biểu thức trả `true`, Spring **không ghi entry**. Lần gọi sau sẽ tiếp tục query database; vì thế nếu bản ghi được tạo, lượt đọc tiếp theo có thể thấy ngay bản ghi (giả sử database nhất quán và không có một cache khác nằm bên dưới).

Chính sách này phù hợp khi dữ liệu mới thường được tạo ngay sau lượt tìm không thấy, hoặc yêu cầu phát hiện sự tồn tại mới nhanh hơn quan trọng hơn việc giảm miss load.

**Đổi lại:** một ID không tồn tại nhưng bị hỏi 10.000 lần có thể tạo tới 10.000 lượt load database (trừ khi có các lớp bảo vệ khác). Không cache âm giúp tránh stale negative cache, **không miễn phí**.

### 4.3. So sánh

| Trường hợp | Cache cả null | `unless="#result == null"` |
| --- | --- | --- |
| Lần đầu tìm ID chưa có | Query DB, có thể lưu entry null | Query DB, không lưu |
| Lần hai tìm cùng ID chưa có | Có thể hit, không query DB | Miss và query DB lại |
| Sau khi ID được tạo bên ngoài | Có thể tiếp tục trả null cũ | Lượt đọc mới có cơ hội thấy bản ghi |
| Tải DB do ID không tồn tại lặp lại | Thấp hơn nếu hit | Cao hơn nếu rất nhiều request |
| Cần TTL/invalidation cho dữ liệu âm | **Rất quan trọng** | Không có entry âm từ operation đó |
| Cần bảo đảm dữ liệu sau khi tạo luôn thấy ngay | Không, nếu chưa invalidated | Vẫn phụ thuộc nguồn dữ liệu, cache khác và race |
| Cache provider không hỗ trợ null | Phải cấu hình chính sách phù hợp | Veto put null tránh yêu cầu lưu null |

**Lưu ý về `condition`:** `@Cacheable(condition = "...")` được xét trước method, dựa trên đầu vào; không có `#result` để biết dữ liệu có tồn tại hay không. `unless` mới là nơi thích hợp để xét **kết quả trả về**.

## 5. Dữ liệu được tạo sau đó: ba cách làm cache cập nhật

Cả ba cách đều cần **đúng cache name, đúng key, đúng timing**.

### 5.1. Cách 1 — Không cache giá trị âm

```java
@Cacheable(cacheNames = "books", key = "#p0",
           unless = "#result == null")
public Book findBook(String id) {
    return repository.find(id);
}
```

Đây là cách đơn giản nếu nhu cầu ưu tiên nhìn thấy dữ liệu mới. Tuy nhiên nó vẫn có thể trả dữ liệu cũ cho **entry dương đã cache** khi nội dung bản ghi bị sửa, nên không thay thế cơ chế invalidation chung.

### 5.2. Cách 2 — Xóa entry âm khi tạo thành công

```java
@CacheEvict(cacheNames = "books", key = "#p0")
public Book createBook(String id, String title) {
    return repository.insert(id, title);
}
```

*Đoạn minh họa, chưa có repository.*

Theo mặc định, `@CacheEvict` có `beforeInvocation=false`, nghĩa là eviction được thực hiện **sau khi method hoàn thành bình thường**. Nếu tạo dữ liệu throw, eviction hậu xử lý thông thường không xảy ra. Sau khi entry được xóa, lượt `@Cacheable` kế tiếp miss, query dữ liệu mới rồi có thể cache dương.

Không nên tự động chuyển thành `beforeInvocation=true` mà chưa suy xét: eviction sẽ xảy ra **trước khi phương thức tạo chạy**, kể cả khi tạo thất bại. Trong hệ thống transaction, cần kiểm tra thời điểm evict so với database commit; “method return bình thường” chưa luôn đồng nghĩa transaction bên ngoài đã commit.

### 5.3. Cách 3 — Ghi luôn đối tượng mới bằng `@CachePut`

```java
@CachePut(cacheNames = "books", key = "#result.id()")
public Book createBook(String id, String title) {
    return repository.insert(id, title);
}
```

Khi method trả `Book` mới bình thường, `@CachePut` có thể ghi đè entry âm ở key `book.id()` bằng đối tượng dương. Lần đọc sau cùng cache/key có thể hit ngay. Cách này giảm lượt tải lại nhưng yêu cầu result đúng kiểu, key thống nhất và thời điểm cập nhật cache an toàn.

**Không dùng `@CachePut` để xóa entry nếu trả `null` không có ý nghĩa:** hành vi put null lại có thể tiếp tục duy trì một negative entry. Với thao tác tạo thành công, nên trả đối tượng đã xác nhận và lưu đúng key.

### 5.4. Cách 4 — TTL âm ngắn và giới hạn tài nguyên

Khi không thể đảm bảo mọi writer đều phát event invalidation (vì nhiều dịch vụ ngoài hoặc batch job cùng tạo dữ liệu), TTL âm ngắn là hàng rào giúp lỗi “không tồn tại cũ” không kéo dài vô hạn.

Ví dụ yêu cầu nghiệp vụ: “Kết quả không thấy sách có thể cũ tối đa 10 giây”; khi đó đặt TTL âm khoảng 10 giây, nếu provider hỗ trợ phân loại dương/âm và cơ chế nhất quán phù hợp. **Không có thuộc tính `ttl` trong `@Cacheable` hay `@CacheConfig`** để tự giải quyết việc này; cấu hình cần nằm ở provider, cache riêng hoặc logic ứng dụng.

TTL chỉ đặt một giới hạn thời gian gần đúng trong điều kiện provider hoạt động như mong đợi; nó không loại bỏ race, clock skew, replication delay hay yêu cầu read-your-writes nghiêm ngặt. Kết hợp TTL với event-driven invalidation nếu cần.

## 6. Ví dụ chạy được: null bị cache, tạo mới gây stale, rồi khôi phục

Ví dụ sau dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5** và `ConcurrentMapCacheManager`, không cần Redis hay database ngoài. Một `ConcurrentHashMap` mô phỏng bảng sách. Không có transaction phức tạp để dễ quan sát.

Demo minh họa ba kịch bản:

- **A: negative cache + tạo dữ liệu bên ngoài cache** → vẫn trả null cũ cho tới khi evict.
- **B: `unless` từ chối lưu null** → đọc lại DB và thấy đối tượng sau khi tạo, nhưng tốn thêm lượt query lúc chưa có.
- **C: negative cache + `@CachePut` khi tạo** → entry null được thay bằng đối tượng mới mà không cần đợi miss.

### 6.1. Cấu trúc

```text
negative-cache-demo/
├── pom.xml
└── src/main/java/example/negativecache/
    ├── NegativeCacheApplication.java
    ├── Book.java
    ├── BookStore.java
    └── BookService.java
```

### 6.2. File `pom.xml`

```xml
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
    <artifactId>negative-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
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
```

### 6.3. File `src/main/java/example/negativecache/Book.java`

```java
package example.negativecache;

public record Book(String id, String title) {}
```

Record của Java 17 tự tạo `toString()` dạng `Book[id=A, title=Alpha]`, thuận tiện để đối chiếu stdout.

### 6.4. File `src/main/java/example/negativecache/BookStore.java`

```java
package example.negativecache;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class BookStore {
    private final ConcurrentMap<String, Book> books =
            new ConcurrentHashMap<>();
    private final AtomicInteger reads = new AtomicInteger();

    public Book find(String id) {
        Book book = books.get(id);
        int n = reads.incrementAndGet();
        System.out.println(
            "DB_READ #" + n + " " + id + " -> " +
            (book == null ? "ABSENT" : book.title())
        );
        return book;
    }

    public Book create(String id, String title) {
        Book created = new Book(id, title);
        Book previous = books.putIfAbsent(id, created);
        if (previous != null) {
            throw new IllegalStateException("Book exists: " + id);
        }
        System.out.println("DB_CREATE " + id + " -> " + title);
        return created;
    }
}
```

Đây là kho dữ liệu giả lập bằng `ConcurrentHashMap` trong một JVM. `create` dùng `putIfAbsent` để tránh ghi đè một sách đã tồn tại trong demo, nhưng chưa phải transaction/database thật.

### 6.5. File `src/main/java/example/negativecache/BookService.java`

```java
package example.negativecache;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final BookStore store;

    public BookService(BookStore store) {
        this.store = store;
    }

    // Có thể cache null: negative caching khi provider cho phép.
    @Cacheable(cacheNames = "negative", key = "#p0")
    public Book cachedEvenWhenAbsent(String id) {
        return store.find(id);
    }

    // Chỉ cache kết quả dương, không cache null.
    @Cacheable(
        cacheNames = "positiveOnly",
        key = "#p0",
        unless = "#result == null"
    )
    public Book skipAbsent(String id) {
        return store.find(id);
    }

    // Loại bỏ entry âm hoặc entry dương cùng key sau khi method return.
    @CacheEvict(cacheNames = "negative", key = "#p0")
    public void invalidateNegative(String id) {
        System.out.println("CACHE_EVICT " + id);
    }

    // Tạo sách và đưa kết quả dương vào cùng cache/key với method đọc.
    @CachePut(cacheNames = "negative", key = "#result.id()")
    public Book createAndRefresh(String id, String title) {
        return store.create(id, title);
    }
}
```

Tất cả các cache operation đều nằm trên method public của một Spring-managed bean. `CommandLineRunner` gọi qua bean được inject (không tự gọi qua `this.`), nên proxy cache có cơ hội intercept.

### 6.6. File `src/main/java/example/negativecache/NegativeCacheApplication.java`

```java
package example.negativecache;

import java.util.Objects;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class NegativeCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(NegativeCacheApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        ConcurrentMapCacheManager manager =
                new ConcurrentMapCacheManager("negative", "positiveOnly");
        // Nêu rõ cấu hình để demo negative caching nhất quán.
        manager.setAllowNullValues(true);
        return manager;
    }

    @Bean
    CommandLineRunner demo(
        BookStore store, BookService service, CacheManager manager
    ) {
        return args -> {
            Cache negative = Objects.requireNonNull(
                manager.getCache("negative")
            );
            Cache positiveOnly = Objects.requireNonNull(
                manager.getCache("positiveOnly")
            );

            // A: cache null, tạo ở store không tự invalidation.
            System.out.println("A1 => " + service.cachedEvenWhenAbsent("A"));
            System.out.println("A2 => " + service.cachedEvenWhenAbsent("A"));
            Cache.ValueWrapper aEntry = negative.get("A");
            System.out.println(
                "A_CACHED_NULL => " +
                (aEntry != null && aEntry.get() == null)
            );

            store.create("A", "Alpha"); // mô phỏng writer nằm ngoài cache
            System.out.println(
                "A_STALE => " + service.cachedEvenWhenAbsent("A")
            );
            service.invalidateNegative("A");
            System.out.println(
                "A_REFRESHED => " + service.cachedEvenWhenAbsent("A")
            );

            // B: không lưu null; sau create sẽ query lại store.
            System.out.println("B1 => " + service.skipAbsent("B"));
            System.out.println("B2 => " + service.skipAbsent("B"));
            System.out.println(
                "B_CACHE_PRESENT => " + (positiveOnly.get("B") != null)
            );
            store.create("B", "Bravo");
            System.out.println("B3 => " + service.skipAbsent("B"));
            System.out.println("B4 => " + service.skipAbsent("B"));

            // C: entry âm được thay thế bằng @CachePut khi tạo sách.
            System.out.println("C0 => " + service.cachedEvenWhenAbsent("C"));
            System.out.println(
                "C_PUT => " + service.createAndRefresh("C", "Charlie")
            );
            System.out.println("C1 => " + service.cachedEvenWhenAbsent("C"));
        };
    }
}
```

### 6.7. Chạy chương trình

Trong thư mục `negative-cache-demo`, cần JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Các dòng ứng dụng demo tự in theo **đúng thứ tự** sau (Spring Boot còn có log khởi động, không liệt kê ở đây):

```text
DB_READ #1 A -> ABSENT
A1 => null
A2 => null
A_CACHED_NULL => true
DB_CREATE A -> Alpha
A_STALE => null
CACHE_EVICT A
DB_READ #2 A -> Alpha
A_REFRESHED => Book[id=A, title=Alpha]
DB_READ #3 B -> ABSENT
B1 => null
DB_READ #4 B -> ABSENT
B2 => null
B_CACHE_PRESENT => false
DB_CREATE B -> Bravo
DB_READ #5 B -> Bravo
B3 => Book[id=B, title=Bravo]
B4 => Book[id=B, title=Bravo]
DB_READ #6 C -> ABSENT
C0 => null
DB_CREATE C -> Charlie
C_PUT => Book[id=C, title=Charlie]
C1 => Book[id=C, title=Charlie]
```

### 6.8. Diễn giải từng nhóm kết quả

**Nhóm A — Cache null tạo ra kết quả âm cũ:**

1. `A1`: cache `negative` chưa có key `A`. Spring gọi `BookStore.find`, in `DB_READ #1 A -> ABSENT` và method trả `null`. Manager cho phép giá trị null nên lưu một entry đại diện null.
2. `A2`: cache hit null; method không chạy. Không có dòng `DB_READ #2` ở thời điểm này.
3. `A_CACHED_NULL => true`: `Cache.get("A")` trả về một `ValueWrapper` có `get() == null`. Đây là **hit âm**, không phải miss.
4. `store.create("A", "Alpha")`: map giờ có sách A, nhưng không có annotation cache hay event nào tự động thay entry trong cache.
5. `A_STALE => null`: cache vẫn chứa negative entry. Dù store có Alpha, Spring vẫn trả null cũ.
6. `invalidateNegative("A")`: Spring thực thi `@CacheEvict` xóa key A sau khi method kết thúc bình thường; lần đọc kế tiếp miss, in `DB_READ #2 A -> Alpha` và cache mới nhận đối tượng.

**Nhóm B — `unless` không cache null:**

1. `B1`: lượt đầu không có sách B, query database giả lập (#3), trả `null`, `unless` trả `true` nên không lưu.
2. `B2`: không có negative entry nên lại query (#4), tiếp tục null, không cache.
3. `B_CACHE_PRESENT => false`: không có mapping key B trong cache `positiveOnly`.
4. `store.create("B", "Bravo")`: tạo sách B.
5. `B3`: lượt tiếp theo query (#5) và thấy Bravo; vì kết quả khác null nên được cache.
6. `B4`: cùng key hit, không có thêm `DB_READ`.

**Nhóm C — `@CachePut` ghi thay negative entry:**

1. `C0`: query (#6) không thấy C; cache `negative["C"]` giữ giá trị âm.
2. `createAndRefresh("C", "Charlie")`: method tạo sách trả `Book`, `@CachePut` lấy `#result.id()` là `"C"` và ghi đối tượng vào **cùng cache `negative`, cùng key C**.
3. `C1`: lần đọc sau hit đối tượng mới mà không gọi `BookStore.find`, nên không có `DB_READ #7`.

**Vì sao output tái lập được:** code chạy tuần tự trong `CommandLineRunner`; hai cache là local riêng biệt, mỗi key mới bắt đầu vắng mặt; cache manager được cấu hình rõ `allowNullValues=true`; không có thread khác hoặc TTL tự động; mọi lời gọi tới `BookService` từ `CommandLineRunner` qua Spring-managed proxy. Output Java record theo cú pháp `Book[id=..., title=...]`.

Đây là demo về hành vi, không phải hệ thống production: `BookStore` là map, không có transaction hay nhiều node. Đã rà soát thủ công code, annotation, key và thứ tự stdout; để xác nhận runtime cần chạy Maven trong môi trường có JDK và dependency.

## 7. Nếu API trả 404 thì có phải đã cache lỗi không?

Giả sử controller:

```java
@GetMapping("/books/{id}")
public BookDto read(@PathVariable String id) {
    Book book = bookService.find(id);
    if (book == null) {
        throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }
    return BookDto.from(book);
}
```

*Đoạn trên minh họa tầng web; cần các import và kiểu `BookDto`/service tương ứng.*

Nếu `bookService.find(id)` đã **cache null**, controller có thể ném `ResponseStatusException` mỗi lần mà service không query database lại. Nhìn bên ngoài, người dùng thấy HTTP 404 liên tục và có thể tưởng Spring “đã cache exception 404”. Thực tế, **cache method có thể chỉ đang giữ kết quả null**, còn controller tạo response 404 mới từ null đó.

Ngược lại, nếu chính method `@Cacheable` ném `ResponseStatusException` trước khi trả return value, `@Cacheable` mặc định **không lưu exception như một result bình thường**. Các cache HTTP ở CDN, reverse proxy, browser hoặc API gateway có quy tắc caching 404 riêng; phải kiểm tra đúng tầng.

**Cách chẩn đoán:** log số lần đi vào method đọc dữ liệu, inspect cache entry bằng `Cache.get`, phân biệt cache hit null với cache miss, kiểm tra status code được tạo ở đâu.

## 8. `@Cacheable(unless="#result == null")` và `Optional<Book>`

Khi phương thức trả `Optional<Book>`:

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public Optional<Book> findOptional(String id) {
    return repository.findOptional(id);
}
```

*Đoạn minh họa; repository chưa được định nghĩa.*

Trong caching SpEL, Spring unwrap `Optional`: `#result` tham chiếu tới `Book` khi present, hoặc `null` khi empty. Do đó `unless="#result == null"` là cách diễn đạt phù hợp cho “không lưu khi không tồn tại”, cả khi API method sử dụng `Optional`.

Không viết mặc định `unless="#result.isEmpty()"` rồi giả định `#result` là `Optional`. Với supported Optional wrapper, `#result` là **giá trị bên trong**, không phải wrapper; gọi `isEmpty()` như trên có thể sai kiểu hoặc dereference null.

Khi người dùng dùng một kiểu `Result` tùy chỉnh chứa status `NOT_FOUND`, Spring không tự hiểu nó mang ý nghĩa kết quả âm:

```java
record LookupResult(boolean found, Book book) {}

@Cacheable(cacheNames = "books", key = "#p0",
           unless = "!#result.found()")
public LookupResult findResult(String id) {
    // Trả LookupResult phù hợp theo dữ liệu thực.
    return new LookupResult(false, null);
}
```

*Đoạn minh họa, không phải lời khuyên dùng một kết quả cố định trong ứng dụng thật.*

Với loại result này, `unless` phải tự mã hóa quy tắc “không lưu khi found=false”. Đó là một **hợp đồng nghiệp vụ do bạn định nghĩa**, không phải mặc định của Spring.

## 9. TTL âm, cache stampede và chi phí hiệu năng

### 9.1. Khi nào nên cache “không tồn tại”?

Negative caching hữu ích khi hệ thống phải xử lý nhiều truy vấn đến các key thường xuyên không có thật:

- Bot liên tục hỏi mã sản phẩm chưa được cấp phát.
- Dịch vụ kiểm tra ID không tồn tại với tần suất cao.
- Lookup tới một dịch vụ bên ngoài có độ trễ cao và trả not found thường xuyên.

Nếu mọi lượt miss đều truy vấn database, tải có thể tăng rất mạnh. Một negative entry ngắn hạn giảm tải nhưng đánh đổi độ tươi.

Nên xác định **ngân sách stale chấp nhận được** theo nghiệp vụ. Nếu dữ liệu vừa tạo phải thấy ngay trong cùng phiên làm việc, chỉ dùng negative TTL ngắn vẫn có thể chưa đủ; cần invalidation/refresh hoặc đường đọc đi thẳng tới nguồn sau ghi.

### 9.2. TTL dương và âm nên được xem xét riêng

Một sách đã có có thể tương đối ổn định và cache lâu; nhưng “không có sách” có thể thay đổi chỉ vài giây sau khi tạo. Vì vậy nhiều hệ thống chọn **TTL âm ngắn hơn TTL dương**.

Cách thực hiện phụ thuộc cache provider:

- Tách cache `booksPositive` và `booksNegative` với cấu hình TTL khác nhau.
- Dùng wrapper có trạng thái và logic lưu có phân loại kết quả nếu backend hỗ trợ.
- Dùng cache provider hỗ trợ expiry policy phụ thuộc entry, nếu có.
- Kết hợp event invalidation với một TTL giới hạn thời gian.

Không có annotation chuẩn `@Cacheable(ttl=...)`; thời gian sống được cấu hình qua provider/cache manager hoặc một abstraction riêng.

### 9.3. Vấn đề “hàng nghìn request cùng miss”

Khi không cache null bằng `unless`, hàng nghìn request cùng hỏi một ID chưa tồn tại có thể đều chạy database. Các biện pháp khả thi:

- giới hạn tốc độ, batching hoặc cơ chế request coalescing;
- negative caching TTL ngắn với quy tắc invalidation đúng;
- distributed lock/single-flight ở tầng phù hợp nếu cần;
- cache ở tầng khác có bảo vệ chống stampede.

Spring hỗ trợ `@Cacheable(sync=true)` như một hint đồng bộ load cho cùng key tùy backend, nhưng có giới hạn quan trọng: **không hỗ trợ kết hợp `sync=true` với `unless` trong cùng `@Cacheable`**, chỉ một cache và không kết hợp các operation khác. Không được trình bày `@Cacheable(sync=true, unless="#result == null")` như cấu hình hợp lệ.

Ngay cả khi dùng `sync=true`, không suy ra nó giải quyết mọi đồng thời trên nhiều node: mức đồng bộ và hành vi thất bại phụ thuộc provider.

## 10. Tạo dữ liệu, transaction và sự nhất quán của negative entry

“Evict khi tạo thành công” nghe đơn giản, nhưng cần xét thời điểm database commit.

Ví dụ:

```java
@Transactional
@CacheEvict(cacheNames = "books", key = "#result.id()")
public Book createBook(CreateBookCommand command) {
    return repository.insert(command);
}
```

*Đoạn minh họa, cần transaction manager/repository thích hợp.*

`@CacheEvict(beforeInvocation=false)` thực hiện sau method hoàn thành thành công **theo cache advice**, nhưng nếu transaction advice bao ngoài cache advice, một eviction có thể xảy ra **trước database commit**. Một lượt đọc đồng thời có thể miss, truy vấn dữ liệu cũ chưa thấy bản ghi mới, rồi **cache lại null**; sau đó transaction mới commit, khiến negative entry tiếp tục tồn tại.

Đây là một race đặc biệt nguy hiểm:

```text
Writer tạo B42 trong transaction (chưa commit)
  -> evict cache["B42"]
Reader ngay lập tức:
  -> cache miss
  -> database vẫn chưa nhìn thấy B42
  -> cache lưu "không tồn tại"
Writer commit B42
  -> cache["B42"] vẫn là "không tồn tại" nếu không có invalidation tiếp
```

Các cách giảm rủi ro:

1. Đảm bảo thao tác cache invalidation/put được điều phối **sau commit** khi yêu cầu consistency đòi hỏi.
2. Cân nhắc `TransactionAwareCacheManagerProxy` hoặc cache decorator/transaction synchronization phù hợp với backend và phạm vi transaction.
3. Với hệ thống phân tán, dùng sự kiện sau commit đáng tin cậy (transactional outbox, idempotent consumer) để invalidate/refresh mọi node liên quan.
4. Vẫn có TTL âm đủ ngắn để giới hạn ảnh hưởng của event thất lạc.
5. Test bằng điều kiện concurrent và rollback thật, không chỉ bằng một chuỗi lời gọi tuần tự.

**Không mặc định cache và database chung một atomic transaction:** `@Transactional` không tự biến Redis và database thành một đơn vị commit duy nhất. `@CachePut` cũng không phải transactional write-through trong mọi môi trường.

## 11. Cuộc đua giữa miss và create dù đã dùng evict

Ngay cả khi create evict **sau commit**, vẫn có race:

```text
Reader R1: bắt đầu find("B42"), cache miss
Reader R1: hỏi DB -> chưa thấy B42, chuẩn bị trả null

Writer W: create B42, commit thành công
Writer W: evict key B42

Reader R1: hoàn tất @Cacheable và ghi null vào cache SAU eviction
Reader R2: thấy negative entry cũ, trả "không tìm thấy"
```

Do đó, một eviction đơn lẻ không phải một bảo đảm mạnh trong mọi lịch trình đồng thời. Để xử lý mức nhất quán cao hơn, cần thiết kế có chủ đích:

- Đọc/ghi dưới lock chung hoặc một cơ chế serialization phù hợp.
- Versioned keys hoặc generation token giúp kết quả miss cũ không ghi đè thế hệ cache mới.
- TTL âm rất ngắn nhằm hạn chế tác hại khi race xảy ra.
- Cơ chế invalidate lại hoặc refresh khi phát hiện create event; cân nhắc thứ tự event và retry.
- Kiểm soát những writer không đi qua ứng dụng đang sử dụng annotation.

Nếu dữ liệu quan trọng cần **read-your-writes** chặt chẽ, có thể cần đọc trực tiếp nguồn cho lượt truy vấn sau khi tạo hoặc dùng một invariant đọc/ghi khác, không chỉ hy vọng cache nhất quán tức thì.

## 12. Cache key, tenant và dữ liệu phụ thuộc ngữ cảnh

Ví dụ method:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(String bookId, String tenantId) {
    return repository.find(tenantId, bookId);
}
```

*Đoạn minh họa, chưa có repository.*

Nếu cache key chỉ là `bookId` nhưng dữ liệu tồn tại khác nhau theo `tenantId`, một tenant chưa có sách có thể cache null theo key `B42` và tenant khác **đã có sách** cũng bị trả null. Đây là một kiểu **cross-tenant cache poisoning** gây sai kết quả, thậm chí rủi ro bảo mật.

Key phải bao gồm **mọi chiều dữ liệu ảnh hưởng đầu ra**, ví dụ:

```java
@Cacheable(cacheNames = "books", key = "#p1 + ':' + #p0")
public Book findBook(String bookId, String tenantId) {
    return repository.find(tenantId, bookId);
}
```

Trong ví dụ, `#p1` là tenant và `#p0` là bookId. Khi tạo một bản ghi, `@CacheEvict` hoặc `@CachePut` phải **dùng đúng cùng cách tạo key và đúng cache name/manager**. Có thể chọn key object tổng hợp hoặc `KeyGenerator` thay vì nối chuỗi nếu định dạng đầu vào phức tạp và có nguy cơ collision.

Cache key không thay thế việc **kiểm tra quyền**. Không bao giờ tin tenant ID do client tùy ý cung cấp mà không đối chiếu với ngữ cảnh xác thực.

## 13. Triệu chứng và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm chứng |
| --- | --- | --- |
| Database đã có bản ghi, API vẫn 404 | Method cache null/`Optional.empty` | Kiểm tra `Cache.get(key)`, số lần method chạy, tên cache/key |
| Mất nhiều giây mới thấy bản ghi | TTL âm | Xem expiration, provider metrics, thời gian create |
| Tạo qua API A thấy ngay; tạo qua batch B thấy chậm | API A có `@CacheEvict`/`@CachePut`, batch B không phát invalidation | Trace mọi writer/producer event |
| Xóa cache rồi lại thấy null | Race: reader miss trước commit và ghi null sau evict | Kiểm tra transaction timing và concurrent traces |
| `@CacheEvict` có annotation nhưng không xảy ra | Self-invocation, sai bean/proxy hoặc key không khớp | Log method, kiểm tra proxy, cache name và key |
| Không cache null nhưng database tải cao | `unless` làm mọi kết quả âm đều miss | Đo QPS negative lookup và DB read count |
| Một tenant trả “không có” dù tenant khác có | Key không phân biệt tenant | So sánh cache keys theo tenant và auth context |
| Cache get có `wrapper != null` nhưng `get()==null` | Entry negative thực sự đã được lưu | Phân biệt wrapper hit và miss, xem allowNullValues |
| Method ném exception và request sau vẫn tải lại | Exception không được cache như return value | Kiểm tra nguồn exception và cache layer khác |

Cách thực hành là **đo cả hai nơi**: log/metric khi method thực sự truy vấn database, và trạng thái/cache hit/miss tại provider. Nếu chỉ nhìn HTTP response, không đủ phân biệt cache âm với truy vấn mới trả âm.

### 13.1. Test tối thiểu nên có

1. **Missing đầu tiên:** không có ID, gọi đọc, nhận null/empty hoặc 404.
2. **Missing lặp lại:** xác minh method được gọi lại hay bị cache skip đúng với policy.
3. **Create sau missing:** tạo cùng ID, gọi đọc lại; kết quả phải khớp yêu cầu freshness.
4. **Create thất bại:** không đưa đối tượng giả vào cache; xem eviction có xảy ra ngoài ý muốn không.
5. **Create qua writer bên ngoài:** kiểm tra event/TTL/invalidation.
6. **Concurrent miss/create:** ép xen kẽ giữa database read và cache put/evict, tìm race.
7. **Multi-tenant:** cùng ID ở tenant khác không bị chia sẻ negative entry.
8. **Provider null support:** test `allowNullValues`/serializer/null sentinel thật trên môi trường dùng trong production.
9. **Multi-node:** kiểm tra invalidation/TTL trên mọi node hoặc mọi cache partition liên quan.
10. **Transaction rollback:** dữ liệu và cache có khôi phục đúng sau rollback/commit failure không.

Đừng chỉ test “lần đầu trả null”: bug negative cache thường **chỉ lộ ra ở lượt gọi sau khi dữ liệu đã được tạo**.

## 14. Những sai lầm thường gặp

1. **Nhầm `null` với cache miss.** Nếu provider lưu null bằng sentinel, `Cache.get(key)` có thể trả wrapper dù giá trị bên trong là null.
2. **Cho rằng `Optional.empty()` không bao giờ được cache.** Spring Cache có thể unwrap Optional thành null và lưu nếu cho phép.
3. **Dùng `condition="#result == null"` để tránh cache âm.** `condition` được đánh giá trước method; muốn xét kết quả, dùng `unless`.
4. **Cho rằng `unless=true` trả lỗi.** Nó chỉ từ chối việc lưu kết quả mới; caller vẫn nhận null/empty của lần hiện tại.
5. **Tắt null support mà không thiết kế xử lý method trả null.** Có thể khiến cache put gặp lỗi tùy provider; `unless` thường diễn đạt ý định rõ hơn.
6. **Tạo bản ghi mới nhưng chỉ xóa cache khác namespace.** Key, cache name và cache manager/resolver phải khớp giữa read và write/evict.
7. **Evict quá sớm, trước database commit.** Reader có thể miss, đọc database chưa commit và cache null trở lại.
8. **Tin rằng evict sau commit loại bỏ toàn bộ race.** Reader đã bắt đầu trước create có thể put âm sau eviction; cần chống race nếu yêu cầu consistency cao.
9. **Dùng TTL dương dài cho cả kết quả âm.** Negative entry có thể làm dữ liệu vừa tạo “vô hình” quá lâu.
10. **Thay kết quả âm bằng object lỗi giả cùng cache với object hợp lệ.** Có nguy cơ lỗi kiểu/logic và không phân biệt được trạng thái nghiệp vụ; hãy dùng hợp đồng rõ ràng.
11. **Đặt `@CacheEvict` trên private hoặc tự gọi từ cùng bean rồi kỳ vọng proxy intercept.** Trong proxy mode mặc định, self-invocation bỏ qua advice.
12. **Kết hợp `sync=true` và `unless` trong `@Cacheable`.** Spring không hỗ trợ tổ hợp đó.
13. **Giả định ngoại lệ HTTP 404 mặc định được Spring method cache lưu.** Có thể là null cache ở service hoặc HTTP response cache ở tầng khác.
14. **Dùng key không phân biệt tenant/user/locale.** Negative result của nhóm này có thể gây sai kết quả ở nhóm khác.
15. **Cho rằng cache giải quyết authorization hoặc data validation.** Kiểm tra quyền và quy tắc nghiệp vụ cần được thực hiện ở điểm thích hợp mỗi request.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `@Cacheable` trả `null`, `ConcurrentMapCacheManager` cho phép null. Lượt gọi tiếp theo với cùng key có chắc chạy phương thức đọc database không?

**Đáp án:** Không. Cache có thể đã lưu một negative entry đại diện null; lượt sau hit và bỏ qua thân method.

**Câu 2.** `Cache.get("B42") != null` nhưng `Cache.get("B42").get() == null`. Kết luận gì?

**Đáp án:** Cache có entry cho B42, nhưng giá trị người dùng là null. Đây là “hit null”, khác với `Cache.get("B42") == null` biểu thị miss.

**Câu 3.** Bản ghi B42 được tạo sau khi một lượt tra cứu đã cache null. `@Cacheable` có tự nhận biết database đã thay đổi không?

**Đáp án:** Không. Cần invalidation, `@CachePut`, TTL/expiry, versioned key hoặc chính sách khác phù hợp.

**Câu 4.** `@Cacheable(unless="#result == null")` trả null. Caller nhận gì? Có lưu null vào cache không?

**Đáp án:** Caller vẫn nhận null của lượt gọi đó; Spring từ chối put kết quả null theo điều kiện `unless`.

**Câu 5.** Với method trả `Optional.empty()`, `unless="#result == null"` có tác dụng không?

**Đáp án:** Có, với supported Optional wrapper của Spring Cache, `#result` tham chiếu giá trị bên trong; empty được xem là null để đánh giá điều kiện.

**Câu 6.** Nếu create đã commit nhưng một reader đang miss cũ ghi null sau eviction thì sao?

**Đáp án:** Cache có thể bị tái nhiễm kết quả âm. Eviction một lần không bảo đảm strong consistency trước mọi interleaving; cần thiết kế chống race hoặc giới hạn thời gian sống âm.

**Câu 7.** Có thể dùng `@Cacheable(sync=true, unless="#result == null")` để vừa single-flight vừa veto null?

**Đáp án:** Không. `sync=true` có giới hạn không dùng `unless`. Cần chọn kỹ thuật concurrency/negative caching khác.

**Câu 8.** `BookService.find(id, tenantId)` dùng key chỉ gồm ID. Kết quả “không có” có thể ảnh hưởng tenant khác không?

**Đáp án:** Có. Nếu hai tenant có cùng ID nhưng dữ liệu khác nhau, negative entry của một tenant có thể bị dùng cho tenant kia. Key hoặc cache scope phải phân tách tenant và giữ kiểm tra quyền đúng.

## 16. Ghi nhớ nhanh

- **Negative caching** là cache kết quả “không tồn tại”, thường biểu diễn bằng null, Optional.empty hoặc sentinel nghiệp vụ.
- **Cache miss ≠ cache hit null.** Phân biệt `Cache.get(key) == null` với wrapper tồn tại nhưng `get()==null`.
- **Dữ liệu tạo sau không tự làm mất negative entry.** Có thể thấy 404 cũ dù database đã có bản ghi.
- **`unless="#result == null"`** tránh lưu kết quả rỗng, đổi lại tăng DB load khi key tiếp tục không tồn tại.
- **`@CacheEvict`** xóa entry; **`@CachePut`** ghi dữ liệu mới. Cả hai phải dùng đúng cache/key và thời điểm.
- **TTL âm và invalidation** nên xuất phát từ yêu cầu freshness, không sao chép máy móc TTL dương.
- **Concurrency và transaction** có thể làm null được ghi lại sau eviction; test race nếu cần read-after-create nhất quán.
- **Method ném exception khác với method trả null.** Spring Cache không tự cache exception như một giá trị trả về bình thường.

## Tài liệu tham khảo chính thức

- Spring Framework Reference — Declarative Annotation-based Caching, `@Cacheable`, `unless`, `Optional` và `@CacheEvict`: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `@Cacheable`, giới hạn `sync` và `unless`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework Javadoc — `Cache` và `Cache.ValueWrapper`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework Javadoc — `ConcurrentMapCacheManager` và `setAllowNullValues`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework Reference — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework Reference — Proxying Mechanisms/self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
