# ConcurrentMapCache và ConcurrentMapCacheManager

> **Ngữ cảnh:** Spring Framework Cache — nhóm **Cache trong bộ nhớ**. Bài này giải thích hai lớp `ConcurrentMapCache` và `ConcurrentMapCacheManager`, cách chúng tạo và quản lý các vùng cache local, cũng như những khác biệt quan trọng về tên cache, null, mutability, tính đồng thời và vòng đời dữ liệu. Ví dụ được viết cho Java 17 và Spring Framework 6.2.x.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:
1. Phân biệt **một vùng cache chứa key/value** với **đối tượng quản lý nhiều vùng cache**.
2. Sử dụng `CacheManager.getCache(name)` và các API `Cache.get`, `put`, `evict`, `clear`.
3. So sánh `ConcurrentMapCacheManager` ở chế độ **dynamic** và **static**.
4. Hiểu vì sao `ConcurrentMapCache` cho phép cached null value dù `ConcurrentHashMap` không chấp nhận null trực tiếp.
5. Nhận ra mặc định **store-by-reference**, tùy chọn **store-by-value**, và hậu quả khi lưu dữ liệu mutable.
6. Chứng minh hit/miss/eviction và cập nhật bằng `@CachePut` qua một ứng dụng Spring thật.
7. Giải thích giới hạn **không có TTL/TTI/size-eviction built-in**, **không chia sẻ cache giữa JVM** và **không tồn tại qua restart**.
8. Biết khi nào Spring Boot dùng Simple provider và khi nào nên lựa chọn Caffeine/Redis.

## 2. Vị trí của hai lớp trong Spring Cache

```text
Client
  |
  v
Spring-managed Service Bean / AOP Proxy
  |
  v
Spring Cache Interceptor (@Cacheable, @CachePut, @CacheEvict)
  |
  v
ConcurrentMapCacheManager
  |                          (một manager có nhiều Cache)
  +--- "books"  ---> ConcurrentMapCache("books")
  |                   B1 --> Book(...)
  |                   B2 --> Book(...)
  |
  +--- "prices" ---> ConcurrentMapCache("prices")
                      P1 --> Price(...)
```

- **`Cache`** là abstraction cho một vùng lưu key/value. Nó có các thao tác như `get`, `put`, `evict`, `clear`.
- **`ConcurrentMapCache`** là implementation `Cache` đơn giản, dựa trên các cấu trúc concurrent của JDK, mặc định dùng `ConcurrentHashMap`.
- **`CacheManager`** là abstraction cấp trên, cung cấp `getCache(String name)` và `getCacheNames()`.
- **`ConcurrentMapCacheManager`** tạo/quản lý các `ConcurrentMapCache` theo tên.
- **`@Cacheable`** áp dụng chính sách dùng lại kết quả cho lời gọi method, nhưng chỉ khi Spring cache interceptor đang được bật và lời gọi đi qua proxy phù hợp.

Một cache có tên `books` trong **JVM A** không tự liên kết với cache `books` trong **JVM B**. Cùng tên là cùng vùng logic **bên trong một manager/context**, không phải kho lưu trữ phân tán.

## 3. ConcurrentMapCache: các thao tác cơ bản

Lớp đầy đủ:

```java
org.springframework.cache.concurrent.ConcurrentMapCache
```

Một đối tượng `ConcurrentMapCache` cung cấp hành vi như:

| API | Hành vi cơ bản |
| --- | --- |
| `get(key)` | Tra entry, trả `Cache.ValueWrapper` nếu có; null khi không có entry |
| `get(key, Class<T>)` | Đọc giá trị với kiểu mong đợi |
| `put(key, value)` | Đặt hoặc thay value của một key |
| `putIfAbsent(key, value)` | Chỉ đặt khi key chưa có theo thao tác atomic của map |
| `evict(key)` | Xóa một key |
| `clear()` | Xóa các entry của cache đó |
| `get(key, Callable<T>)` | Tra hoặc dùng loader để tính khi thiếu; có khả năng phối hợp tính trên cùng key |

Ví dụ **đoạn mã minh họa** trong một method đã có `CacheManager cacheManager`:

```java
Cache cache = cacheManager.getCache("books");
if (cache == null) {
    throw new IllegalStateException("Missing books cache");
}

cache.put("B1", "Spring Framework");
System.out.println(cache.get("B1").get()); // Spring Framework

cache.evict("B1");
System.out.println(cache.get("B1"));       // null
```

Với API cache trực tiếp, ứng dụng tự gọi `put` hoặc `evict`. Với `@Cacheable`, Spring interceptor thay bạn thực hiện việc tra và ghi kết quả dựa trên cache name/key đã cấu hình.

**Không nhầm thread-safe map với thread-safe nghiệp vụ.** Map có các thao tác truy cập đồng thời an toàn nhưng một chuỗi “đọc DB → sửa dữ liệu → ghi cache” không mặc nhiên là transaction atomic. Một object mutable được cache cũng không tự có cơ chế đồng bộ sửa nội dung.

## 4. ConcurrentMapCacheManager: hai chế độ tên cache

Lớp đầy đủ:

```java
org.springframework.cache.concurrent.ConcurrentMapCacheManager
```

### 4.1. Dynamic — tạo vùng cache khi có yêu cầu

```java
ConcurrentMapCacheManager manager = new ConcurrentMapCacheManager();

Cache a = manager.getCache("books");
Cache b = manager.getCache("prices");
```

Constructor **không truyền tên** bật chế độ động. `getCache("books")` lần đầu có thể tạo một `ConcurrentMapCache`, các lần sau sử dụng cache đã tạo. `getCacheNames()` liệt kê các vùng manager đã biết tại thời điểm kiểm tra.

Ưu điểm: tiện cho demo hoặc các tên cache được yêu cầu linh hoạt. Nhược điểm: lỗi chính tả như `"bokos"` có thể **âm thầm tạo vùng cache khác** thay vì báo tên không hợp lệ.

### 4.2. Static — chỉ cho phép các tên đã định nghĩa

```java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("books", "prices");

System.out.println(manager.getCache("books") != null);  // true
System.out.println(manager.getCache("unknown") != null); // false
```

Constructor có các tên chỉ cho phép tập cache đó. Nếu một `@Cacheable(cacheNames = "unknown")` đòi cache không có, lỗi resolve cache có thể phát sinh **lúc method được gọi**, thay vì ngay khi application startup.

Mode tĩnh hữu ích khi tên cache là một hợp đồng cố định và bạn muốn phát hiện lỗi cấu hình.

### 4.3. setCacheNames và reset

```java
ConcurrentMapCacheManager manager = new ConcurrentMapCacheManager();
manager.setCacheNames(java.util.List.of("books", "prices"));
manager.setCacheNames(null); // trở lại dynamic mode
```

Theo JavaDoc, `setCacheNames` có thể thay thế các cache cùng tên và không tự xóa mọi cache tên khác đã tồn tại. `resetCaches()` có hành vi reset tương ứng. Vì thay đổi cấu hình manager có thể ảnh hưởng dữ liệu đang giữ, tốt nhất **chốt mode lúc khởi tạo**, không chuyển mode liên tục trong production.

## 5. Cache hit và cache miss qua @Cacheable

Xét method minh họa:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book find(String isbn) {
    return repository.load(isbn);
}
```

Đoạn code cần một Spring bean, repository và lớp `Book` để chạy. Khi ứng dụng đã bật `@EnableCaching` và gọi method qua Spring proxy:

1. Spring tạo key từ đối số đầu (`#p0`).
2. Interceptor lấy cache `books` từ manager.
3. **Miss:** chạy thân `find`, gọi repository, lưu kết quả nếu chính sách cho phép.
4. **Hit:** trả value đã lưu và **không chạy lại thân method**.
5. Với key khác hoặc sau `evict`, lại có thể miss.

| Lời gọi tuần tự | Key | Dự kiến (cache ban đầu trống) | Tổng lần chạy body |
| --- | --- | --- | --- |
| `find("B1")` | B1 | Miss | 1 |
| `find("B1")` | B1 | Hit | 1 |
| `find("B2")` | B2 | Miss | 2 |
| `find("B1")` | B1 | Hit | 2 |
| `evict("B1"); find("B1")` | B1 | Miss sau xóa | 3 |

Bảng giả định loader thành công, không có `condition`/`unless` loại cache và mọi lời gọi đi qua proxy. Muốn kiểm chứng, đặt `AtomicInteger` trong thân method hoặc repository; đếm ở controller chỉ đo số lần client gọi.

### Cạm bẫy self-invocation

Trong proxy mode mặc định, một method bên trong cùng bean gọi `this.find("B1")` thường bỏ qua cache interceptor. Tương tự, tạo `new BookService()` bên ngoài Spring không kích hoạt annotation. Khi test, lấy service bằng `ApplicationContext.getBean(...)` hoặc inject vào bean khác.

## 6. Null value: khác biệt giữa cached null và cache miss

`ConcurrentHashMap` của Java không cho phép map chứa null value trực tiếp. Nhưng `ConcurrentMapCacheManager` mặc định có `allowNullValues = true`: `ConcurrentMapCache` mã hóa user-level null bằng một **giá trị đại diện nội bộ**.

Ví dụ:

```java
Cache cache = manager.getCache("books");
cache.put("not-found", null);

Cache.ValueWrapper never = cache.get("never-created");
Cache.ValueWrapper noBook = cache.get("not-found");

System.out.println(never == null);          // true: miss
System.out.println(noBook != null);         // true: có entry
System.out.println(noBook.get() == null);   // true: cached null
```

Đây là đoạn minh họa trong method đã có manager và các import. Điểm phân biệt:
- **Miss**: `cache.get(key) == null`, không có `ValueWrapper`.
- **Hit với null**: có `ValueWrapper`, nhưng `wrapper.get() == null`.

`cache.get(key, Book.class)` có thể trả null cả khi miss lẫn khi value được cache là null, nên nếu cần phân biệt tình trạng **có/không có entry**, dùng dạng wrapper.

### Tắt cho phép lưu null

```java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("books");
manager.setAllowNullValues(false);
```

Khi đó `put(key, null)` có thể không được chấp nhận. Nếu muốn **không lưu kết quả null** qua Spring annotation:

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public Book find(String isbn) {
    return repository.load(isbn);
}
```

Đây là phương án khác với việc mặc định lưu null. Lưu ý: `@Cacheable(sync = true)` không hỗ trợ `unless`; đừng ghép chúng để “sửa” null caching. Null **key** cũng là vấn đề khác null **value**; cho phép null value không có nghĩa mọi expression sinh key null sẽ được chấp nhận.

Theo JavaDoc, thay đổi `allowNullValues` có thể reset các cache đã tạo để dùng chính sách mới. Cấu hình nên được quyết định trước khi hệ thống phục vụ request.

## 7. Mặc định store-by-reference và tùy chọn store-by-value

Manager có thuộc tính `storeByValue`:
- `false` (mặc định): lưu **tham chiếu object**, không bắt buộc `Serializable`.
- `true`: lưu bản sao thông qua cơ chế serialization; value phải serializable, có chi phí CPU/bộ nhớ và ràng buộc kiểu dữ liệu.

### Nguy cơ dùng object mutable

```java
List<String> tags = new ArrayList<>(List.of("java"));
cache.put("B1-tags", tags);

tags.add("spring");

@SuppressWarnings("unchecked")
List<String> cached =
        (List<String>) cache.get("B1-tags").get();

System.out.println(cached); // [java, spring]
```

Đoạn minh họa cần import `List` và `ArrayList`, giả định cache mặc định store-by-reference. Caller sửa object sau khi put khiến nội dung cache thay đổi **mà không có thao tác put mới**. Các request khác cùng tham chiếu có thể bị tác động, nhất là khi có thread đồng thời.

**Lựa chọn thực tế:** dùng immutable record/DTO, sao chép phòng vệ cho collection, hoặc store-by-value khi thật sự cần cách ly object và các value đều serializable.

```java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("books");
manager.setStoreByValue(true);
```

**Store-by-value không phải persistence.** Dù dùng serialization để tạo bản sao, cache vẫn ở bộ nhớ của JVM hiện tại. Khi restart, các entry vẫn mất. Thay đổi chế độ trên manager đã có dữ liệu cũng có thể reset cache để tái cấu hình.

## 8. Giới hạn về vòng đời, dung lượng và phân tán

`ConcurrentMapCache` phù hợp cho thử nghiệm hoặc caching đơn giản, nhưng theo Spring Framework nó **không cung cấp sẵn hợp đồng quản lý expiration/eviction** như provider chuyên dụng.

| Nhu cầu | ConcurrentMapCache mặc định |
| --- | --- |
| TTL (hết hạn sau một thời gian kể từ write) | **Không có built-in** |
| TTI (hết hạn do không truy cập) | **Không có built-in** |
| maximumSize/size-based eviction | **Không có built-in** |
| Thủ công xóa một key | Có `evict(key)` |
| Thủ công xóa cả cache | Có `clear()` |
| Persistence qua JVM restart | Không |
| Chia sẻ value giữa nhiều instance JVM | Không |
| Map cho phép truy cập đồng thời | Có |
| Transaction nguyên tử giữa database và cache | Không tự bảo đảm |

Hệ quả quan trọng:
- Một key có thể **giữ lâu không xác định** nếu không bị cập nhật/xóa; đừng kỳ vọng 10 phút sau nó tự hết hạn.
- Bộ nhớ tăng theo số entry, kiểu value và số cache name; key tăng liên tục có thể gây áp lực heap.
- Nguồn dữ liệu được update nhưng cache không được invalidation thì có thể trả **stale value**.
- Hai instance A/B giữ các bản cache khác nhau; evict trên A không tự xóa trên B.
- Cache được tạo động với tên typo có thể tạo thêm vùng không mong muốn.

Nếu cần TTL, giới hạn dung lượng hoặc telemetry, xem xét **Caffeine**. Nếu cần chia sẻ dữ liệu cache giữa nhiều instance, xem xét **Redis** cùng chiến lược invalidation, key và serialization phù hợp.

## 9. Spring Boot và Simple cache

Spring Boot có thể auto-configure **Simple** cache dựa trên `ConcurrentHashMap` khi caching đã được bật và không có provider khác được chọn. Có thể chỉ rõ:

```properties
spring.cache.type=simple
spring.cache.cache-names=books,prices
```

Đây là ví dụ `application.properties`:
- `spring.cache.type=simple` yêu cầu loại Simple trong nhánh Boot cache auto-configuration.
- `spring.cache.cache-names=books,prices` giới hạn các tên cache hợp lệ theo cấu hình đó.
- Khi application dùng tên `unknown` không có trong danh sách, lỗi thường phát sinh **khi cache được yêu cầu**, không nhất thiết ngay lúc startup.
- Nếu có bean `CacheManager`/`CacheResolver` tự khai báo, auto-config của Boot có thể không chọn manager theo property. Luôn xác nhận type thực tế.

Dependency thường dùng trong POM có parent/BOM Spring Boot:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
```

Đây là **đoạn dependency**, không phải POM đầy đủ. Để annotation caching hoạt động, vẫn cần `@EnableCaching`. Với Boot, nên để parent/BOM quản lý phiên bản module Spring.

**Phân biệt:**
- `spring.cache.type=simple` → lưu giá trị bằng Simple cache.
- `spring.cache.type=none` → no-op cache, **không lưu**.
- `SimpleCacheManager` là class có thể quản lý những `Cache` được đăng ký thủ công; nó **không đồng nghĩa** với tên lựa chọn Boot “simple” trong mọi thiết kế.

## 10. Ví dụ Java 17 độc lập: hit, stale, evict, put và cache names

Demo dùng **Spring Framework 6.2.16**, Maven và JDK 17+, không cần database/Redis/Caffeine. Nguồn dữ liệu được mô phỏng bởi một `ConcurrentHashMap` riêng; việc này đủ để chứng minh sự khác nhau giữa **dữ liệu nguồn** và **cache do Spring quản lý**.

### 10.1. Cấu trúc thư mục

```text
concurrent-map-cache-demo/
├── pom.xml
└── src/
    ├── main/java/demo/cache/CacheDemo.java
    └── test/java/demo/cache/CacheDemoTest.java
```

### 10.2. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>concurrent-map-cache-demo</artifactId>
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
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.cache.CacheDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp Spring Cache abstraction, annotation và ConcurrentMap cache implementation; các module phụ thuộc được Maven resolve tự động. JUnit 5 dùng để kiểm chứng trực tiếp. Đây là chương trình Spring Framework thuần, không dựa vào cache auto-configuration của Boot.

### 10.3. `src/main/java/demo/cache/CacheDemo.java`

```java
package demo.cache;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheDemo {

    public record Book(String isbn, String title) {}

    public static class BookRepository {
        private final Map<String, Book> data = new ConcurrentHashMap<>();
        private final AtomicInteger reads = new AtomicInteger();

        public BookRepository() {
            data.put("B1", new Book("B1", "Spring Basics"));
        }

        public Book load(String isbn) {
            reads.incrementAndGet();
            return data.get(isbn);
        }

        public Book save(String isbn, String title) {
            Book book = new Book(isbn, title);
            data.put(isbn, book);
            return book;
        }

        public int readCount() {
            return reads.get();
        }
    }

    public static class BookService {
        private final BookRepository repository;

        public BookService(BookRepository repository) {
            this.repository = repository;
        }

        @Cacheable(cacheNames = "books", key = "#p0")
        public Book find(String isbn) {
            return repository.load(isbn);
        }

        @CachePut(cacheNames = "books", key = "#p0")
        public Book rename(String isbn, String title) {
            return repository.save(isbn, title);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("books");
        }

        @Bean
        public BookRepository bookRepository() {
            return new BookRepository();
        }

        @Bean
        public BookService bookService(BookRepository repository) {
            return new BookService(repository);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            var service = context.getBean(BookService.class);
            var repository = context.getBean(BookRepository.class);
            CacheManager manager = context.getBean(CacheManager.class);

            System.out.println("manager="
                    + manager.getClass().getSimpleName());
            System.out.println("staticBooks="
                    + (manager.getCache("books") != null));
            System.out.println("staticUnknown="
                    + (manager.getCache("unknown") != null));

            System.out.println("first="
                    + service.find("B1").title());
            System.out.println("second="
                    + service.find("B1").title());
            System.out.println("reads1="
                    + repository.readCount());

            // Mô phỏng nguồn được cập nhật bên ngoài cache advice.
            repository.save("B1", "Changed Outside Cache");
            System.out.println("stale="
                    + service.find("B1").title());

            Cache cache = Objects.requireNonNull(
                    manager.getCache("books"));
            cache.evict("B1");

            System.out.println("afterEvict="
                    + service.find("B1").title());
            System.out.println("reads2="
                    + repository.readCount());

            service.rename("B1", "Updated Through Service");
            System.out.println("afterPut="
                    + service.find("B1").title());
            System.out.println("reads3="
                    + repository.readCount());

            // Default allowNullValues=true.
            cache.put("ABSENT", null);
            Cache.ValueWrapper wrapper = cache.get("ABSENT");
            System.out.println("cachedNull="
                    + (wrapper != null && wrapper.get() == null));
            System.out.println("missingNull="
                    + (cache.get("NEVER") == null));

            var dynamic = new ConcurrentMapCacheManager();
            System.out.println("dynamicBefore="
                    + dynamic.getCacheNames().contains("adHoc"));
            dynamic.getCache("adHoc");
            System.out.println("dynamicAfter="
                    + dynamic.getCacheNames().contains("adHoc"));
        }
    }
}
```

### 10.4. Chạy và đối chiếu stdout

Cần Java 17+, Maven 3.9+ và kết nối Maven Central lần đầu. Ở thư mục `concurrent-map-cache-demo` chạy:

```bash
java -version
mvn -q compile exec:java
```

Các dòng **do chương trình in ra**, không tính log riêng của Maven hoặc Spring:

```text
manager=ConcurrentMapCacheManager
staticBooks=true
staticUnknown=false
first=Spring Basics
second=Spring Basics
reads1=1
stale=Spring Basics
afterEvict=Changed Outside Cache
reads2=2
afterPut=Updated Through Service
reads3=2
cachedNull=true
missingNull=true
dynamicBefore=false
dynamicAfter=true
```

Đọc kết quả:
1. Manager tĩnh có `books` nhưng không biết `unknown`.
2. Hai lần `find("B1")` chỉ có **một lượt repository.load**, chứng minh cache hit.
3. Repository bị thay đổi trực tiếp, cache chưa nhận được invalidation nên `stale` vẫn trả title cũ.
4. `cache.evict("B1")` xóa entry, lần đọc tiếp theo miss, tăng `reads2` lên 2.
5. `@CachePut` tại method `rename` làm mới cache bằng Book vừa cập nhật; đọc lại không cần load nguồn, nên `reads3` vẫn 2.
6. Cached null có wrapper, còn key chưa tồn tại thì `get` trả null.
7. Manager động tạo vùng `adHoc` khi được yêu cầu.

Ví dụ chỉ kiểm chứng một JVM đơn luồng. Nó không chứng minh TTL, consistency đa node hoặc giao dịch DB/cache đã được xử lý.

## 11. Kiểm thử JUnit 5

Tạo `src/test/java/demo/cache/CacheDemoTest.java`:

```java
package demo.cache;

import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CacheDemoTest {

    @Test
    void hitEvictionAndPutWorkWithOneCacheKey() {
        try (var context = new AnnotationConfigApplicationContext(
                CacheDemo.Config.class)) {

            var service = context.getBean(CacheDemo.BookService.class);
            var repository = context.getBean(CacheDemo.BookRepository.class);
            CacheManager manager = context.getBean(CacheManager.class);

            assertEquals("Spring Basics", service.find("B1").title());
            assertEquals("Spring Basics", service.find("B1").title());
            assertEquals(1, repository.readCount());

            repository.save("B1", "New Source Title");
            assertEquals("Spring Basics", service.find("B1").title());

            Cache cache = Objects.requireNonNull(
                    manager.getCache("books"));
            cache.evict("B1");

            assertEquals("New Source Title", service.find("B1").title());
            assertEquals(2, repository.readCount());

            service.rename("B1", "Put Title");
            assertEquals("Put Title", service.find("B1").title());
            assertEquals(2, repository.readCount());
        }
    }

    @Test
    void namesAreStaticOrCreatedDynamically() {
        var fixed = new ConcurrentMapCacheManager("books");
        assertNotNull(fixed.getCache("books"));
        assertNull(fixed.getCache("unlisted"));

        var dynamic = new ConcurrentMapCacheManager();
        assertFalse(dynamic.getCacheNames().contains("adHoc"));
        assertNotNull(dynamic.getCache("adHoc"));
        assertTrue(dynamic.getCacheNames().contains("adHoc"));
    }

    @Test
    void cachedNullIsNotTheSameAsCacheMiss() {
        var manager = new ConcurrentMapCacheManager("books");
        Cache cache = Objects.requireNonNull(manager.getCache("books"));

        assertNull(cache.get("NEVER"));
        cache.put("ABSENT", null);

        Cache.ValueWrapper wrapper = cache.get("ABSENT");
        assertNotNull(wrapper);
        assertNull(wrapper.get());
    }
}
```

Chạy:

```bash
mvn -q test
```

Kỳ vọng JUnit thành công với exit code 0. Khi chạy `mvn -q`, Maven có thể không in “BUILD SUCCESS”. Các assertion xác nhận: hit tránh tải nguồn, cache stale khi nguồn đổi, eviction tạo miss, put làm mới đúng key, mode static/dynamic hoạt động khác nhau và cached null có wrapper. Mỗi test có context/manager riêng nên không phụ thuộc thứ tự test.

**Chú ý:** đây là kiểm thử caching với Spring ApplicationContext thật, không phải unit test dùng `new BookService(...)` bỏ qua annotation. Nếu muốn test TTL hoặc distributed cache, phải dùng provider phù hợp và bộ kiểm thử riêng.

## 12. ConcurrentMap, đồng thời và @Cacheable(sync = true)

`ConcurrentMapCache` sử dụng `ConcurrentHashMap` nên thao tác map thread-safe, nhưng **mặc định** nhiều thread cùng thấy miss có thể cùng chạy method body. Không có bảo đảm một lần gọi loader duy nhất chỉ nhờ đặt `@Cacheable`.

Ví dụ minh họa method đọc:

```java
@Cacheable(cacheNames = "books", key = "#p0", sync = true)
public Book findSlowly(String isbn) {
    return repository.load(isbn);
}
```

`sync = true` yêu cầu provider phối hợp loader cho một cache key đang miss. `ConcurrentMapCache` có cơ chế `get(key, Callable)` dùng tính toán atomic theo key trong map, nên phù hợp minh họa trong một JVM. Nhưng đây **không phải distributed lock**. Thêm vào đó, Spring hạn chế `sync=true`: một cache, không dùng `unless`, và không ghép operation cache khác lên cùng method.

Không dùng đoạn minh họa để kết luận mọi provider hoặc môi trường phân tán đảm bảo exactly-once. Với bài test concurrency cần dùng nhiều thread/barrier và đo số lần body thực thi.

## 13. Khi nào nên chuyển sang provider khác?

| Lựa chọn | Dữ liệu được lưu ở đâu? | TTL/size policy | Chia sẻ nhiều JVM | Dùng khi |
| --- | --- | --- | --- | --- |
| `ConcurrentMapCacheManager` | Map local trong JVM | Không có built-in expiry/capacity policy | Không | Demo, test, app nhỏ hoặc caching đơn giản |
| `CaffeineCacheManager` | Local JVM | Có `maximumSize`, `expireAfterWrite`, `expireAfterAccess` | Không | Cache local cần giới hạn tài nguyên và độ mới |
| `RedisCacheManager` | Redis server | Có key TTL, cấu hình riêng | Có nếu dùng chung server | Cần chia sẻ cache giữa nhiều instance |
| `NoOpCacheManager` | Không lưu | Không áp dụng | Không | Cố ý tắt caching value trong một môi trường |
| `SimpleCacheManager` | Các `Cache` được ứng dụng đăng ký | Theo provider của từng cache | Theo provider | Gom các cache được cấu hình thủ công |

Cần lưu ý:
- Caffeine và Redis có những khác biệt về serializer, null handling, TTL, eviction và concurrency. Không chuyển provider rồi mặc nhiên giữ nguyên mọi behavior.
- Dù có TTL, dữ liệu vẫn có thể stale cho tới khi hết hạn nếu không invalidation.
- Distributed cache không tự khiến DB và cache cùng transaction atomic. Xem xét thời điểm commit và race condition.
- Giới hạn số key và đo hit/miss, số lần truy cập nguồn, chi phí heap/Redis memory trước khi chọn chính sách.

## 14. Lỗi thường gặp và checklist

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Hai lần gọi cùng key vẫn chạy body | Không đi qua Spring proxy, `@EnableCaching` thiếu, key khác nhau, cache bị evict | Inject bean Spring, đo số lượt repository |
| Lỗi cache name | Static mode không chứa tên yêu cầu | Kiểm tra `getCacheNames`, spelling `cacheNames` |
| Giá trị cũ sau update | Thiếu `@CacheEvict` hoặc `@CachePut` đúng key | Kiểm tra thời điểm DB commit và entry cache |
| Lưu null không như dự kiến | `allowNullValues` và `unless` khác nhau | Kiểm tra manager thực tế và `Cache.ValueWrapper` |
| Object cached đổi bất ngờ | Lưu object mutable theo reference | Dùng immutable DTO/defensive copy |
| Heap tăng theo thời gian | Không TTL, không maximumSize, nhiều key | Xem xét Caffeine, eviction và metric |
| Các node trả dữ liệu khác nhau | Local cache riêng từng JVM | Dùng shared cache hoặc invalidation liên node |
| Property Boot không hoạt động | User-defined manager/resolver, auto-config không chọn Simple | Log bean thật, kiểm tra classpath |

**Checklist triển khai:** Xác định chính xác cache name và key, chọn dynamic/static, chủ động null policy, ưu tiên immutable value, kiểm tra đường gọi qua proxy, thiết kế invalidation sau update, giới hạn bộ nhớ, hiểu topology nhiều instance và test cả hit/miss. Nếu cần expiry, không cố cấu hình TTL trên `@Cacheable` mà hãy chọn provider có hỗ trợ.

## 15. Câu hỏi tự luyện

**Câu 1.** `new ConcurrentMapCacheManager()` rồi gọi `getCache("new")` có tạo cache không?  
**Đáp án:** Có, trong dynamic mode nó được tạo khi yêu cầu.

**Câu 2.** `new ConcurrentMapCacheManager("books")` trả gì cho `getCache("new")`?  
**Đáp án:** `null` vì đây là static mode chỉ nhận tên được khai báo.

**Câu 3.** Có thể phân biệt cached null và cache miss bằng `get(key)` không?  
**Đáp án:** Có: hit chứa null có `ValueWrapper` với `get() == null`; miss không có wrapper.

**Câu 4.** Vì sao cập nhật DB không làm cache tự có giá trị mới?  
**Đáp án:** ConcurrentMap là kho local độc lập. Cần eviction, put hoặc quy trình invalidation thích hợp.

**Câu 5.** Spring Cache với ConcurrentMap có tự xóa entry sau 5 phút không?  
**Đáp án:** Không, provider này không cung cấp TTL built-in.

**Câu 6.** Vì sao mặc định store-by-reference có thể gây lỗi với object mutable?  
**Đáp án:** Caller sửa chung tham chiếu có thể làm entry cache thay đổi không qua put.

**Câu 7.** Dùng hai server có cache `books` cùng tên. Chúng có tự đồng bộ dữ liệu với nhau không?  
**Đáp án:** Không. Mỗi JVM có map riêng; cần giải pháp cache chung hoặc invalidation liên node.

## Tài liệu chính thức

- [Spring Framework — ConcurrentMapCacheManager JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html)
- [Spring Framework — ConcurrentMapCache JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html)
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)

**Ghi nhớ:** `ConcurrentMapCache` giữ các mục key/value trong JVM; `ConcurrentMapCacheManager` quản lý các cache theo tên, có chế độ động hoặc cố định. Đây là provider đơn giản, tiện cho học và test, nhưng không có TTL, persistence hay cache phân tán. Để ứng dụng đúng, phải kiểm tra key, proxy, null, mutability, invalidation và nhu cầu thay provider khi quy mô tăng.