# Chế độ cache bất đồng bộ và setAsyncCacheMode trong Spring Cache

## Mục tiêu bài học

Spring Cache thường được dùng theo luồng đồng bộ: gọi một phương thức, kiểm tra cache, nếu miss thì chạy phương thức, chờ kết quả, ghi cache rồi trả kết quả. Nhưng trong ứng dụng hiện đại, phương thức có thể trả về `CompletableFuture<T>`, `Mono<T>` hoặc `Flux<T>`. Khi đó, **giá trị chưa sẵn sàng ngay tại thời điểm phương thức Java trả về**.

Spring Framework từ phiên bản 6.1 đã hỗ trợ cache các giá trị được tạo ra bởi các kiểu trả về bất đồng bộ và reactive. Với Caffeine, để tận dụng cơ chế truy xuất bất đồng bộ native, cần bật:

~~~java
cacheManager.setAsyncCacheMode(true);
~~~

Bài học này giải thích cơ chế đó, các điều kiện phiên bản, cách cấu hình `CaffeineCacheManager`, thời điểm giá trị thực sự được lưu và cách kiểm thử.

Sau bài học, bạn có thể:

- Phân biệt **phương thức trả về một future** với **giá trị bên trong future đã hoàn tất**.
- Hiểu cách `@Cacheable` làm việc với `CompletableFuture`, Reactor `Mono` và `Flux` từ Spring 6.1.
- Giải thích vì sao `CaffeineCacheManager` cần `setAsyncCacheMode(true)` để hỗ trợ native asynchronous retrieval.
- Cấu hình đúng `spring-context-support`, Caffeine 3.0+ và cache manager.
- Chạy chương trình Java 17 + Spring Framework 6.2.10 + Caffeine để quan sát cache hit/miss với `CompletableFuture`.
- Hiểu ảnh hưởng của `sync = true`, lỗi future, null, concurrency, back-pressure và giới hạn của cache local.
- Biết khi nào nên dùng cache bất đồng bộ và khi nào nên dùng một mô hình reactive chuyên dụng.

> **Quy tắc cốt lõi:** Khi một phương thức `@Cacheable` trả `CompletableFuture<T>`, Spring cache **giá trị T khi future hoàn tất thành công**. Với Caffeine, `setAsyncCacheMode(true)` chuyển manager sang native `AsyncCache`, cho phép thao tác truy xuất qua `CompletableFuture` mà không cần chặn luồng để đợi kết quả.

## 1. Vì sao cần chế độ cache bất đồng bộ?

### 1.1. Cache đồng bộ truyền thống

Với phương thức trả về trực tiếp một object:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

Đây là **mã minh họa**, giả định `Book` và `repository` tồn tại.

Luồng thường gặp:

~~~text
Caller
  |
  v
Spring cache advice
  |
  +--> Cache.get(key)
          |
          +--> HIT  -> trả Book đã lưu
          |
          +--> MISS -> gọi findBook(isbn)
                         |
                         +--> chờ repository trả Book
                         |
                         +--> Cache.put(key, Book)
                         |
                         +--> trả Book cho caller
~~~

Lời gọi method chỉ trả về sau khi có object `Book`. Cache có thể thực hiện `get`/`put` theo API đồng bộ.

### 1.2. Khi method trả CompletableFuture

Một phương thức bất đồng bộ có dạng:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> findBook(String isbn) {
    return repository.findByIsbnAsync(isbn);
}
~~~

Đây cũng là **mã minh họa**. Khi method chạy, nó trả về một handle `CompletableFuture<Book>`; dữ liệu `Book` có thể vẫn đang được tải từ database hoặc dịch vụ từ xa.

Spring cần xử lý hai việc:

1. Trên **cache miss**, nhận future từ method, theo dõi future và đưa giá trị `Book` vào cache khi future hoàn tất thành công.
2. Trên **cache hit**, trả một `CompletableFuture` đại diện cho giá trị cache để caller vẫn sử dụng API bất đồng bộ.

Không nên cache chính object future như một kết quả nghiệp vụ lâu dài. Spring thích nghi để lưu **giá trị được future tạo ra**, còn caller tiếp tục nhận kiểu trả về bất đồng bộ.

~~~text
Cache MISS:

Spring -> gọi findBook("ISBN-1")
                  |
                  +--> trả CompletableFuture<Book>
                                |
                         tác vụ vẫn chạy
                                |
                         future hoàn tất
                                |
                            Book value
                                |
                         cache put Book
                                |
                         hoàn tất future trả caller


Cache HIT:

Spring -> tra cache ISBN-1
                  |
             có Book value
                  |
       trả CompletableFuture<Book>
       đại diện cho giá trị đã cache
                  |
               caller
~~~

**Thời điểm quan trọng:** việc method Java trả về một future chưa đồng nghĩa cache đã chứa giá trị cuối cùng. Giá trị chỉ có sau khi future hoàn tất thành công.

### 1.3. Spring Framework hỗ trợ từ phiên bản nào?

Từ **Spring Framework 6.1**, cache annotations nhận biết `CompletableFuture` và các reactive return type, rồi tự điều chỉnh cách tương tác với cache:

- `CompletableFuture<T>`: cache object `T` khi future hoàn tất; cache hit được trả dưới dạng `CompletableFuture`.
- Reactor `Mono<T>`: cache object được publisher phát ra khi có giá trị; cache hit trả dưới dạng `Mono`.
- Reactor `Flux<T>`: Spring thu thập các phần tử thành một `List<T>`, cache list khi chuỗi hoàn tất; cache hit được chuyển lại thành `Flux<T>`.

Hành vi này khác với cách cũ coi một `Mono` hoặc `Flux` chỉ là một object Java thông thường rồi cache chính publisher đó.

## 2. Async return type không đồng nghĩa async cache provider

Có hai phần độc lập:

1. **Phương thức tạo kết quả bất đồng bộ:** method trả `CompletableFuture` hoặc reactive publisher.
2. **Cache provider hỗ trợ retrieval bất đồng bộ:** cache phải cung cấp cách tra cứu/nạp giá trị không chặn, tương thích với kiểu trả về đó.

Chỉ thay chữ ký method thành `CompletableFuture<T>` không làm mọi `CacheManager` tự nhiên hỗ trợ asynchronous retrieval.

Spring Framework cung cấp hai ví dụ đáng chú ý:

| Cache manager | Hỗ trợ kiểu truy xuất future |
| --- | --- |
| `ConcurrentMapCacheManager` của Spring | Tự thích nghi với kiểu truy xuất dựa trên `CompletableFuture` |
| `CaffeineCacheManager` | Hỗ trợ native khi bật `setAsyncCacheMode(true)` |
| Provider khác | Phải kiểm tra implementation và phiên bản; không suy ra chỉ từ việc có Spring Cache adapter |

Caffeine yêu cầu **Caffeine 3.0 trở lên** cho native asynchronous cache mode mà Spring sử dụng.

### 2.1. Cache API có retrieval bất đồng bộ

Từ Spring Framework 6.1, interface `Cache` có các thao tác như:

~~~java
CompletableFuture<?> retrieve(Object key);

<T> CompletableFuture<T> retrieve(
    Object key,
    Supplier<CompletableFuture<T>> valueLoader
);
~~~

Đây là **chữ ký API rút gọn để giải thích**, không phải đoạn code cần tự triển khai.

- `retrieve(key)`: tra cứu theo key bằng API không chặn; có thể xác định miss ngay, hoặc kết quả miss chỉ rõ sau khi future hoàn tất.
- `retrieve(key, valueLoader)`: tra cứu và nạp bằng future nếu cần.
- Provider tương thích phải giữ semantics của future, giá trị null và lỗi một cách phù hợp.

Spring caching interceptor sử dụng cơ chế này để tránh phải biến mọi thao tác thành một lần `.join()` hoặc `.get()` đồng bộ.

### 2.2. Vì sao Caffeine cần setAsyncCacheMode(true)?

Mặc định `CaffeineCacheManager` tạo các native Caffeine cache **đồng bộ**. Những cache đó phù hợp với các thao tác `get`/`put` đồng bộ thông thường, nhưng không cung cấp native async retrieval mà Spring cần cho luồng `CompletableFuture`/reactive.

Khi gọi:

~~~java
cacheManager.setAsyncCacheMode(true);
~~~

manager chuyển kiểu cache do nó tạo sang **Caffeine AsyncCache**. Các cache này:

- hỗ trợ `Cache.retrieve(...)` dựa trên future;
- vẫn có thể được sử dụng qua synchronous API;
- áp dụng cho cache khai báo qua `setCacheNames(...)` và cache được tạo theo yêu cầu;
- cần Caffeine 3.0+.

Đây là lựa chọn của **CaffeineCacheManager**, không phải thuộc tính của `@Cacheable` hay của interface `CacheManager` chung.

### 2.3. Async cache không tự chạy method trên thread pool

`setAsyncCacheMode(true)` không tự chuyển một method đồng bộ thành bất đồng bộ và cũng không tự tạo executor cho mọi phương thức. Method phải trả kiểu bất đồng bộ hoặc sử dụng API async của chính provider.

Ví dụ:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> findBook(String isbn) {
    return remoteClient.fetchAsync(isbn);
}
~~~

Ở đây, `remoteClient.fetchAsync` chịu trách nhiệm tạo future. Caffeine async mode giúp cache xử lý future theo cách không chặn.

Nếu method trả trực tiếp `Book`, nó vẫn là một method đồng bộ, kể cả khi cache manager đang ở async mode.

## 3. Cấu hình CaffeineCacheManager đúng cách

### 3.1. Dependency cần có

Ví dụ sử dụng:

- Java 17+
- Spring Framework 6.2.10
- Caffeine 3.1.8 (đáp ứng yêu cầu Caffeine 3.0+)
- Maven

Các dependency cần thiết:

~~~xml
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
~~~

`CaffeineCacheManager` nằm trong module Spring hỗ trợ cache provider (`spring-context-support`). Chỉ thêm `spring-context` và `caffeine` có thể chưa đủ để compile class tích hợp của Spring.

### 3.2. Java Config cơ bản

~~~java
import java.util.List;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager();

        manager.setAsyncCacheMode(true);
        manager.setAllowNullValues(false);
        manager.setCaffeine(
            Caffeine.newBuilder().maximumSize(1_000)
        );
        manager.setCacheNames(List.of("books", "authors"));

        return manager;
    }
}
~~~

Đây là **mã cấu hình có thể tích hợp vào ứng dụng Spring**; cần thêm `@EnableCaching` trong cấu hình ứng dụng và các dependency ở mục 3.1.

Giải thích:

- `new CaffeineCacheManager()`: tạo manager có thể quản lý các vùng cache.
- `setAsyncCacheMode(true)`: bật native Caffeine `AsyncCache`.
- `setAllowNullValues(false)`: không cho phép giá trị null; đây là lựa chọn được khuyến nghị khi dùng async mode vì semantics của future đơn giản hơn và giảm wrapping không cần thiết.
- `setCaffeine(...)`: đặt cấu hình Caffeine chung, ở đây giới hạn tối đa 1.000 entries.
- `setCacheNames(...)`: khai báo trước hai vùng cache `books` và `authors`.

Nếu muốn tạo cache theo yêu cầu, có thể dùng manager dynamic không truyền tên ban đầu; nhưng cần kiểm soát chính tả và số lượng region. Khi đã khai báo tên tĩnh, annotation phải dùng đúng cache name trong danh sách.

### 3.3. Bật async mode trước khi sử dụng cache

Nên hoàn tất cấu hình manager trước khi ứng dụng bắt đầu nhận lời gọi cache. Đặc biệt, không nên bật/tắt `asyncCacheMode` tùy tiện sau khi các cache đã được tạo và đang có traffic.

Cấu hình cache manager nên tập trung tại một nơi để tránh những bean khác nhau vô tình tạo cache với chế độ đồng bộ và bất đồng bộ không nhất quán.

### 3.4. Có thể dùng đồng thời API đồng bộ và bất đồng bộ không?

Có. Theo hợp đồng của `CaffeineCacheManager`, cache được tạo trong async mode vẫn có thể được sử dụng qua synchronous API. Tuy nhiên, nên thống nhất cách dùng trong từng service và kiểm tra latency thực tế; việc một cache hỗ trợ cả hai kiểu API không có nghĩa mọi luồng sync/async đều có cùng đặc tính hiệu năng.

## 4. Ví dụ Java 17 chạy được: @Cacheable với CompletableFuture

Ví dụ sau tạo một service trả `CompletableFuture<String>`. Future được chạy trên một `ExecutorService`; khi hoàn tất, Spring đưa giá trị vào Caffeine async cache. Gọi lại cùng key nhận kết quả từ cache và không chạy lại thân method.

### 4.1. Cấu trúc dự án

~~~text
spring-caffeine-async/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AsyncCacheDemo.java
~~~

### 4.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-caffeine-async</artifactId>
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

### 4.3. src/main/java/demo/AsyncCacheDemo.java

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class AsyncCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {

        @Bean
        public CacheManager cacheManager() {
            CaffeineCacheManager manager =
                new CaffeineCacheManager();

            manager.setAsyncCacheMode(true);
            manager.setAllowNullValues(false);
            manager.setCaffeine(
                Caffeine.newBuilder().maximumSize(100)
            );
            manager.setCacheNames(List.of("books"));
            return manager;
        }

        @Bean(destroyMethod = "shutdown")
        public ExecutorService cacheExecutor() {
            return Executors.newFixedThreadPool(2);
        }

        @Bean
        public BookService bookService(ExecutorService cacheExecutor) {
            return new BookService(cacheExecutor);
        }
    }

    public static class BookService {
        private final ExecutorService executor;
        private final AtomicInteger sourceLoads = new AtomicInteger();

        public BookService(ExecutorService executor) {
            this.executor = executor;
        }

        @Cacheable(
            cacheNames = "books",
            key = "#p0",
            sync = true
        )
        public CompletableFuture<String> find(String isbn) {
            int loadNumber = sourceLoads.incrementAndGet();

            return CompletableFuture.supplyAsync(
                () -> "Book-" + isbn + " (load=" + loadNumber + ")",
                executor
            );
        }

        public int sourceLoads() {
            return sourceLoads.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            BookService service = context.getBean(BookService.class);

            CompletableFuture<String> first = service.find("A");
            System.out.println("First: " + first.join());

            CompletableFuture<String> second = service.find("A");
            System.out.println("Second: " + second.join());

            System.out.println(
                "Loads after hit: " + service.sourceLoads());

            CompletableFuture<String> other = service.find("B");
            System.out.println("Other key: " + other.join());

            System.out.println(
                "Final loads: " + service.sourceLoads());
        }
    }
}
~~~

### 4.4. Chạy chương trình

Tại thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.AsyncCacheDemo
~~~

Những dòng **do chương trình in ra** (không tính log Maven):

~~~text
First: Book-A (load=1)
Second: Book-A (load=1)
Loads after hit: 1
Other key: Book-B (load=2)
Final loads: 2
~~~

### 4.5. Phân tích kết quả

1. Lần gọi `find("A")` đầu là cache miss. Thân method tăng `sourceLoads` lên 1 rồi trả một future chạy trên executor.
2. Caller nhận `CompletableFuture` và `.join()` để **chờ trong chương trình demo** lấy kết quả in ra. Spring theo dõi future và lưu giá trị hoàn tất vào cache.
3. Lần gọi `find("A")` thứ hai tra cùng cache name/key. Đây là cache hit; caller vẫn nhận một `CompletableFuture<String>`, nhưng giá trị được lấy từ cache. Thân method không tăng bộ đếm.
4. Gọi `find("B")` tạo key mới nên miss; thân method chạy lần thứ hai và kết quả có `load=2`.

**Không nhầm vai trò của `.join()`:** ví dụ chỉ dùng `.join()` trong `main` để hiển thị output theo thứ tự xác định. Service không tự block để chờ future rồi mới trả về. Trong controller hoặc service bất đồng bộ thật, nên tiếp tục compose future thay vì gọi `.join()`/`.get()` chỉ để ép đồng bộ.

### 4.6. Vì sao dùng sync = true?

Ví dụ khai báo `sync = true` để yêu cầu cache phối hợp khi nhiều lời gọi cùng key đồng thời miss. Spring 6.1+ hỗ trợ cơ chế đồng bộ caching với các kiểu `CompletableFuture` và reactive khi provider có khả năng future-based retrieval.

Với Caffeine async mode, native `AsyncCache` hỗ trợ đường truy xuất phù hợp. Tuy nhiên:

- `sync = true` có những giới hạn của Spring Cache (ví dụ một cache operation cho cache tương ứng, không dùng cùng `unless`).
- Tính đồng bộ phụ thuộc provider thực hiện loading operation ra sao.
- Caffeine là cache local trong một JVM; không biến thành distributed lock giữa nhiều instance.
- Nếu bỏ `sync = true`, không được mặc định rằng mọi provider sẽ bảo đảm chỉ một lần nạp khi nhiều request đồng thời miss.

## 5. Điều gì xảy ra khi future thất bại?

Cache chỉ có thể lưu **giá trị kết quả thành công**. Một future hoàn tất exceptionally không cung cấp object nghiệp vụ thành công để đưa vào cache.

Ví dụ minh họa:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> findBook(String isbn) {
    return remoteClient.fetchAsync(isbn);
}
~~~

Nếu future hoàn tất bằng exception:

- Caller nhận lỗi qua future (ví dụ `CompletionException` khi gọi `.join()`).
- Spring không có một kết quả `Book` thành công để cache.
- Lần gọi sau cùng key có thể cần chạy nguồn lại.
- Không nên cache exception bằng cách biến nó thành một object kết quả lỗi trừ khi nghiệp vụ chủ động thiết kế negative caching.

### 5.1. Phân biệt exception với DTO báo lỗi

Giả sử method bắt lỗi và trả về:

~~~java
public record BookResult(
    boolean success,
    String title,
    String errorCode
) {}
~~~

Nếu future hoàn tất bình thường với `BookResult(success=false, ...)`, dưới góc nhìn caching đó vẫn là **một giá trị thành công về mặt completion**. Nó có thể được cache nếu không có điều kiện từ chối như `unless`.

Nếu không muốn cache kết quả lỗi, cần thiết kế điều kiện dựa trên giá trị trả về, hoặc để future hoàn tất exceptionally theo hợp đồng phù hợp.

### 5.2. Cancellation

Future bị cancel cũng không tạo ra một giá trị hoàn tất thành công để cache. Cần xác định caller nào có quyền cancel công việc dùng chung và việc cancellation có ảnh hưởng các caller đang chờ cùng key hay không; tránh thiết kế để một request tùy ý hủy công việc được nhiều request khác dùng chung.

## 6. Mono và Flux: reactive caching từ Spring 6.1

Spring 6.1 trở lên nhận biết Reactor publisher trong cache annotations. Cần thêm Reactor dependency nếu ứng dụng dùng các kiểu này.

### 6.1. Mono<T>

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Mono<Book> findBook(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

Đây là **mã minh họa**; repository cần trả `Mono<Book>`.

- Khi miss, Spring đợi publisher phát ra giá trị và cache object `Book` khi giá trị sẵn sàng.
- Khi hit, Spring trả một `Mono<Book>` dựa trên giá trị cache.
- `Mono.empty()` cần được cân nhắc cùng chính sách null/empty của cache và provider; không giả định mọi cache manager có cùng semantics lưu giá trị rỗng.

### 6.2. Flux<T>

~~~java
@Cacheable(cacheNames = "booksByAuthor", key = "#p0")
public Flux<Book> findBooksByAuthor(String author) {
    return repository.findByAuthor(author);
}
~~~

Đây là **mã minh họa**; repository cần trả `Flux<Book>`.

Spring thu thập các phần tử của `Flux` thành một `List<Book>` và chỉ cache list khi publisher hoàn tất. Khi hit, cache cung cấp danh sách rồi được chuyển thành `Flux` cho caller.

Điều này có nghĩa:

- Kết quả không được trả từ cache theo từng phần tử độc lập.
- Một `Flux` rất lớn có thể phải gom toàn bộ vào bộ nhớ.
- Một stream vô hạn sẽ không hoàn tất để tạo giá trị list có thể cache.
- Caching dạng này có tính **coarse-grained**; không thay thế thiết kế streaming/back-pressure.

### 6.3. Caffeine async mode với reactive types

Đối với Caffeine, nếu muốn Spring xử lý reactive publisher theo kiểu asynchronous caching native, hãy bật:

~~~java
CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setAsyncCacheMode(true);
~~~

Cần Caffeine 3.0+ và các dependency Reactor phù hợp. Nếu ứng dụng đang dùng cache provider khác, kiểm tra provider có hỗ trợ các thao tác `Cache.retrieve` tương ứng không.

### 6.4. Khi annotation caching không phù hợp với reactive flow phức tạp

Tài liệu Spring lưu ý annotation-driven caching không phù hợp cho các tương tác reactive phức tạp cần composition và back-pressure chi tiết. Annotation cache hoạt động theo kết quả publisher ở mức khá tổng quát:

- `Mono`: một giá trị.
- `Flux`: gom thành một list.

Nếu cần cache từng phần tử, stream có trạng thái, window/batch, TTL riêng theo phần tử, hoặc luồng vô hạn, hãy cân nhắc cơ chế cache reactive chuyên biệt hoặc thiết kế programmatic phù hợp với mô hình dữ liệu.

## 7. Khác biệt giữa setAsyncCacheMode và @Async

Hai khái niệm này dễ bị nhầm:

| Cơ chế | Vai trò |
| --- | --- |
| `CompletableFuture<T>` | Kiểu trả về mô tả kết quả sẽ có trong tương lai |
| `@Async` | Spring gửi lời gọi method qua một `TaskExecutor` theo cấu hình |
| `CaffeineCacheManager.setAsyncCacheMode(true)` | Cho Caffeine manager tạo native async caches và hỗ trợ `Cache.retrieve` |
| `@Cacheable` | Quyết định cache lookup/load/put cho method được gọi |
| `@Cacheable(sync = true)` | Yêu cầu phối hợp cache loading khi concurrent miss, trong giới hạn provider |

### 7.1. Không cần @Async chỉ vì method trả CompletableFuture

Một method có thể tự tạo future từ HTTP client, database client hoặc executor:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> findBook(String isbn) {
    return webClient.get()
        .uri("/books/{isbn}", isbn)
        .retrieve()
        .bodyToMono(Book.class)
        .toFuture();
}
~~~

Đây là **mã minh họa**, yêu cầu cấu hình WebClient/endpoint thật. `@Cacheable` có thể xử lý kiểu future khi cache provider tương thích; không cần thêm `@Async` chỉ để cache nhận biết future.

### 7.2. @Async không tự bật async cache mode

Nếu method có `@Async` và trả future, executor điều khiển việc thực thi method. Nhưng Caffeine vẫn cần được cấu hình `setAsyncCacheMode(true)` nếu muốn native future-based cache retrieval.

Ngược lại, bật Caffeine async mode không tự khiến một method đồng bộ chạy trên background thread. Hai phần cần được cấu hình theo mục tiêu riêng.

### 7.3. Tránh block trong đường bất đồng bộ

Các đoạn như:

~~~java
Book book = service.findBook(isbn).join();
~~~

có thể cần trong code đồng bộ ở biên ứng dụng, test hoặc ví dụ console. Nhưng nếu đặt giữa một pipeline reactive/future, việc block có thể chiếm thread và làm mất lợi ích non-blocking. Hãy compose:

~~~java
return service.findBook(isbn)
    .thenApply(Book::title);
~~~

Đây là **đoạn minh họa**; kiểu return của method bao ngoài phải phù hợp.

## 8. Null values và semantics của async cache

Caffeine async mode chấp nhận một số cơ chế null-value wrapping của Spring, nhưng tài liệu `CaffeineCacheManager` khuyến nghị **`setAllowNullValues(false)`** khi dùng asynchronous cache mode.

Lý do:

- Caffeine async cache sử dụng `CompletableFuture` handle.
- Không cho null giúp semantics của future-based retrieval đơn giản hơn.
- Có thể tránh một tầng wrapping bổ sung cho handle do Caffeine cung cấp.

Nếu nghiệp vụ có kết quả “không tìm thấy”, hãy chọn rõ một cách biểu diễn:

- Future hoàn tất với DTO kết quả có trạng thái `found=false`.
- `Optional<T>` nếu contract phù hợp.
- Exception cho trường hợp thật sự là lỗi.
- Một negative-cache value có TTL riêng nếu provider và thiết kế hỗ trợ.

Không trả null một cách tùy tiện rồi giả định async cache provider nào cũng xử lý giống nhau. Đặc biệt, với `setAllowNullValues(false)`, hãy test nhánh future hoàn tất với null theo đúng phiên bản Spring/Caffeine đang dùng.

## 9. Cache key, cache name và đồng bộ dữ liệu không thay đổi

Chuyển sang async mode không thay đổi quy tắc xác định cache entry:

- `cacheNames` chọn vùng cache.
- `key` hoặc `KeyGenerator` xác định key.
- `condition`/`unless` quyết định có áp dụng hoặc lưu kết quả theo cấu hình.
- `@CachePut` và `@CacheEvict` vẫn phục vụ cập nhật/xóa entry.

Ví dụ hai method có chữ ký khác nhau nhưng cần cùng key:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> find(String isbn) {
    return repository.findAsync(isbn);
}

@CachePut(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> update(String isbn, BookUpdate input) {
    return repository.updateAsync(isbn, input);
}
~~~

Đây là **mã minh họa**. Nếu dùng `@CachePut` để cập nhật kết quả, hãy bảo đảm cả hai method dùng cùng cache name/key và kết quả future của update trả về đúng value cần lưu.

Async mode không giải quyết:

- dữ liệu stale sau khi database thay đổi;
- transaction rollback sau cache put;
- invalidation giữa nhiều instance;
- cache stampede ở nhiều node;
- sai key hoặc thiếu tenant trong key;
- race giữa future cũ hoàn tất muộn và future mới cập nhật cùng key.

Đó vẫn là những vấn đề nhất quán dữ liệu và provider policy cần thiết kế riêng.

## 10. Concurrency và đồng thời nhiều yêu cầu cùng key

Một tình huống thường gặp:

~~~text
Request A ----> cache miss ----> tải ISBN-1
Request B ----> cache miss ----> tải ISBN-1
Request C ----> cache miss ----> tải ISBN-1
~~~

Nếu cache/provider không phối hợp việc nạp, nhiều request có thể cùng gọi nguồn. Với Caffeine async cache, native `AsyncCache` có khả năng quản lý future theo key; Spring cũng hỗ trợ `@Cacheable(sync = true)` cho kiểu future/reactive khi provider hỗ trợ.

### 10.1. Dùng sync = true khi phù hợp

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    sync = true
)
public CompletableFuture<Book> findBook(String isbn) {
    return repository.findAsync(isbn);
}
~~~

Đây là mã minh họa. `sync=true` yêu cầu provider phối hợp load cho cùng key. Cần nhớ những giới hạn của synchronized caching:

- chỉ áp dụng cho một cache operation/cache tương ứng theo hợp đồng Spring;
- không kết hợp `unless` theo cách không được hỗ trợ;
- hành vi phụ thuộc provider hỗ trợ atomic/synchronized loading;
- Caffeine local cache chỉ phối hợp trong một JVM, không là distributed lock.

### 10.2. Future chưa hoàn tất và nhiều caller

Với async cache, giá trị đang được nạp có thể được đại diện bởi một future đang chạy. Khi provider hỗ trợ atomic async loading, các lời gọi cùng key có thể sử dụng cùng tiến trình nạp. Tuy nhiên, không tự suy rộng đặc tính đó cho mọi `CacheManager` hoặc mọi deployment nhiều instance.

Hãy kiểm thử hai tình huống riêng:

1. **Cùng JVM, cùng key, đồng thời miss:** số lần gọi nguồn khi bật/tắt `sync=true`.
2. **Nhiều instance, cùng key, đồng thời miss:** mỗi local Caffeine cache có thể nạp riêng; nếu cần phối hợp toàn cụm phải có shared provider hoặc cơ chế phân tán.

### 10.3. Race khi dữ liệu nguồn được cập nhật

Một future cũ có thể hoàn tất sau một thao tác update/evict mới. Nếu thiết kế không quản lý version hoặc thứ tự cập nhật, kết quả cũ có nguy cơ ghi lại entry sau khi dữ liệu đã thay đổi.

Cách xử lý tùy hệ thống:

- version/fencing token trong value hoặc key;
- invalidation sau commit;
- provider hỗ trợ atomic update/version;
- kiểm tra phiên bản trước khi put;
- tránh để nhiều tác vụ không liên quan cùng ghi một key mà không có quy tắc.

`setAsyncCacheMode(true)` chỉ cung cấp asynchronous cache interaction, **không phải** cơ chế versioning hoặc transaction.

## 11. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `@Cacheable` trả future nhưng Caffeine báo lỗi retrieval | Manager chưa bật async mode | Kiểm tra `setAsyncCacheMode(true)` |
| Không tìm thấy `CaffeineCacheManager` khi compile | Thiếu `spring-context-support` | Bổ sung dependency đúng version |
| Async mode không có hiệu lực | Caffeine version quá cũ | Dùng Caffeine 3.0+ |
| Method vẫn chạy ở lần gọi cùng key | Future trước chưa hoàn tất hoặc key/cache name khác | Chờ future hoàn tất rồi kiểm tra lại key |
| Caller nhận future nhưng cache chưa có value ngay lúc method return | Future vẫn đang pending | Quan sát khi future complete; không kiểm tra cache quá sớm |
| Future lỗi nhưng tưởng exception đã cache | Method trả exceptional future | Xử lý completion failure; không coi exception là value |
| Future hit trả về null bất ngờ | Null policy hoặc empty result chưa rõ | Kiểm tra `setAllowNullValues`, Optional/empty semantics |
| Flux tiêu thụ nhiều bộ nhớ | Spring gom toàn bộ Flux thành List để cache | Không dùng annotation cache cho stream lớn/vô hạn |
| Reactive back-pressure không còn như kỳ vọng | Cache tương tác ở mức toàn bộ giá trị/publisher | Dùng cơ chế reactive cache chuyên biệt |
| `@Async` có nhưng cache vẫn block | Cache manager/provider không hỗ trợ retrieve async | Phân biệt executor và cache async mode |
| Nhiều lần miss cùng key gây nhiều request nguồn | Chưa dùng sync hoặc provider không phối hợp load | Kiểm tra `sync=true` và semantics provider |
| Instance A có cache hit, B vẫn miss | Caffeine là cache local | Dùng shared cache hoặc chấp nhận per-node cache |
| Cache chứa dữ liệu cũ sau update | Thiếu invalidation/versioning | `@CachePut`, `@CacheEvict`, after-commit |
| Method không được cache khi gọi nội bộ | Self-invocation trong proxy mode | Tách bean hoặc cấu hình interception phù hợp |

## 12. Kiểm thử asynchronous caching đúng cách

### 12.1. Không kiểm tra ngay sau khi method trả future

Đoạn sau có thể kiểm tra quá sớm:

~~~java
CompletableFuture<String> result = service.find("A");
// Future có thể chưa hoàn tất và cache chưa chứa String.
assertThat(cache.get("A")).isNotNull();
~~~

Đây là **mã minh họa về một test sai thời điểm**. Future chưa hoàn tất thì giá trị cuối chưa có để cache.

Nên chờ completion trong test:

~~~java
String value = service.find("A").join();
assertThat(value).isEqualTo("expected");
~~~

Sau khi future hoàn tất, kiểm tra lần gọi tiếp theo và bộ đếm nguồn. Trong ứng dụng thực, có thể dùng `CompletableFuture` chain và test framework hỗ trợ async assertion để tránh block tùy tiện.

### 12.2. Bộ test tối thiểu

- **Miss → future success:** thân method chạy một lần, kết quả được cache khi future complete.
- **Hit sau completion:** cùng key trả future chứa kết quả đã lưu, không chạy lại nguồn.
- **Key khác:** tạo một lần nạp độc lập.
- **Future exceptional:** không có kết quả nghiệp vụ thành công để cache; lần gọi sau được kiểm chứng theo chính sách provider.
- **Future cancellation:** xác nhận không ghi value thành công.
- **Concurrent miss cùng key:** so sánh behavior khi `sync=true` và khi không.
- **Null/empty:** xác minh chính sách `setAllowNullValues(false)` hoặc giá trị empty.
- **Provider error:** kiểm tra lỗi kết nối, timeout và `CacheErrorHandler` phù hợp.
- **Invalidation:** update/evict khi future cũ vẫn đang chạy, kiểm tra race.
- **Reactive:** Mono một giá trị, Mono.empty và Flux hoàn tất với list nhỏ; không dùng Flux vô hạn trong test cache annotation.

### 12.3. Quan sát số lần chạy nguồn

Dùng `AtomicInteger` hoặc spy/mock repository để đo số lần thực thi. Đừng chỉ đo thời gian response: thời gian có thể dao động do thread scheduling và không chứng minh được cache hit.

Trong demo, bộ đếm `sourceLoads` là bằng chứng trực tiếp:

- gọi A lần đầu: count 1;
- gọi A lần hai sau completion: count vẫn 1;
- gọi B: count 2.

### 12.4. Kiểm thử provider thật

Một test dùng Caffeine in-memory chứng minh cấu hình Caffeine manager. Nếu production dùng Redis, JCache hoặc provider khác, cần integration test riêng với provider đó. Đừng coi một test với Caffeine là chứng minh mọi backend đều hỗ trợ native async retrieval.

## 13. Khi nào nên dùng Caffeine async mode?

Phù hợp khi:

- service đã dùng `CompletableFuture` hoặc Reactor và muốn cache mà không block luồng;
- Caffeine local cache là lựa chọn phù hợp với deployment;
- các kết quả có thể tái sử dụng theo key và có chính sách invalidation rõ;
- cần tận dụng async cache retrieval/native future handles;
- đội ngũ có test concurrency và quan sát được số lần load nguồn.

Cân nhắc giải pháp khác khi:

- dữ liệu cần chia sẻ giữa nhiều instance và invalidation phải nhất quán;
- Flux rất lớn hoặc vô hạn, không thể gom thành một list;
- reactive flow cần composition/back-pressure phức tạp;
- method có side effect bắt buộc mỗi lần gọi;
- dữ liệu có yêu cầu consistency/transaction nghiêm ngặt mà cache provider không đáp ứng;
- phương thức đồng bộ đơn giản, cache hit/miss đồng bộ đã đủ và không có lợi ích rõ ràng khi chuyển async.

### Bảng chọn nhanh

| Nhu cầu | Hướng tiếp cận |
| --- | --- |
| Method trả object đồng bộ | Cache API đồng bộ; async mode không bắt buộc |
| Method trả `CompletableFuture<T>` + Caffeine | `setAsyncCacheMode(true)` |
| Method trả `Mono<T>` + Caffeine | Spring 6.1+, Caffeine async mode, test empty semantics |
| Method trả `Flux<T>` nhỏ và hữu hạn | Có thể cache toàn bộ list nếu chấp nhận semantics |
| Flux lớn/vô hạn, cần back-pressure | Reactive cache chuyên biệt, không cache nguyên publisher bằng annotation |
| Cần phối hợp concurrent miss cùng key | Cân nhắc `sync=true` và provider support |
| Cần cache dùng chung nhiều instance | Shared provider hoặc cơ chế invalidation phân tán |

## 14. Checklist triển khai

- [ ] Spring Framework từ 6.1 trở lên nếu cần adaptation CompletableFuture/Mono/Flux.
- [ ] Caffeine 3.0+ nếu dùng native async mode.
- [ ] Có dependency `spring-context-support` cùng version Spring Framework.
- [ ] Có dependency Caffeine phù hợp.
- [ ] `@EnableCaching` được bật trong Spring context.
- [ ] Caffeine manager gọi `setAsyncCacheMode(true)` trước khi dùng cache.
- [ ] Xem xét `setAllowNullValues(false)` theo khuyến nghị của async mode.
- [ ] Cache names/key được khai báo đúng; không tạo cache region sai tên ngoài ý muốn.
- [ ] Method trả future/publisher thực sự, không block trước khi trả.
- [ ] Chỉ cache giá trị có thể tái sử dụng theo cùng key.
- [ ] Future failure/cancellation không bị biến thành cache value ngoài chủ đích.
- [ ] Với `sync=true`, kiểm tra giới hạn annotation và khả năng provider.
- [ ] Không coi Caffeine local là distributed cache/lock.
- [ ] Flux có kích thước hữu hạn và list được cache không vượt giới hạn bộ nhớ.
- [ ] Kiểm thử sau future completion, không đọc cache quá sớm.
- [ ] Kiểm thử invalidation, concurrency, provider error và nhiều instance.
- [ ] Theo dõi hit/miss, thời gian load, số future in-flight, exception và memory.

## 15. Câu hỏi tự kiểm tra

**1.** Spring Framework hỗ trợ caching cho `CompletableFuture` từ phiên bản nào?  
**Đáp án:** Từ Spring Framework 6.1.

**2.** Khi method `@Cacheable` trả `CompletableFuture<Book>`, Spring cache object nào?  
**Đáp án:** Giá trị `Book` mà future tạo ra khi hoàn tất thành công; cache hit được trả dưới dạng future.

**3.** Vì sao Caffeine cần `setAsyncCacheMode(true)`?  
**Đáp án:** Để CaffeineCacheManager tạo native Caffeine AsyncCache hỗ trợ các thao tác future-based retrieval như `Cache.retrieve`.

**4.** Caffeine version nào cần cho cơ chế native async này?  
**Đáp án:** Caffeine 3.0 trở lên.

**5.** `setAsyncCacheMode(true)` có tự chạy method đồng bộ trên background thread không?  
**Đáp án:** Không. Nó thay đổi kiểu cache do manager tạo; method phải trả future/publisher hoặc sử dụng API async phù hợp.

**6.** Spring có tự cache một `Flux<T>` theo từng phần tử ngay khi phát ra không?  
**Đáp án:** Không theo annotation adaptation mặc định; Spring thu thập các phần tử thành `List<T>` và cache khi Flux hoàn tất.

**7.** Vì sao không phù hợp cache Flux vô hạn bằng annotation?  
**Đáp án:** Flux không hoàn tất để tạo list cuối cùng; việc gom toàn bộ còn có thể tiêu tốn bộ nhớ lớn.

**8.** Có cần `@Async` để `@Cacheable` hiểu `CompletableFuture` không?  
**Đáp án:** Không. Spring nhận biết kiểu trả về future từ 6.1; `@Async` là cơ chế thực thi qua TaskExecutor riêng.

**9.** Future hoàn tất exceptionally có tạo cache value thành công không?  
**Đáp án:** Không. Không có giá trị nghiệp vụ hoàn tất thành công để lưu.

**10.** Tại sao nên cân nhắc `setAllowNullValues(false)` khi bật async mode?  
**Đáp án:** Spring khuyến nghị để semantics future đơn giản và tránh wrapping handle bổ sung cho null.

**11.** `sync=true` có phải distributed lock giữa nhiều instance Caffeine không?  
**Đáp án:** Không. Caffeine là local cache; đồng bộ loading chỉ trong phạm vi provider/JVM hỗ trợ.

**12.** Vì sao cần đợi future hoàn tất trước khi xác nhận cache đã có value?  
**Đáp án:** Vì giá trị được đưa vào cache khi future hoàn tất, không nhất thiết ngay khi method trả về handle.

**13.** Nếu method trả object đồng bộ, có bắt buộc bật async cache mode không?  
**Đáp án:** Không. Có thể tiếp tục dùng API đồng bộ; async mode chỉ cần khi muốn hỗ trợ native async retrieval.

**14.** Async cache mode có tự xử lý stale data sau khi database update không?  
**Đáp án:** Không. Vẫn cần `@CachePut`, `@CacheEvict`, TTL hoặc cơ chế invalidation phù hợp.

## Tài liệu tham khảo

- Spring Framework 6.2 — Declarative Annotation-based Caching, mục “Caching with CompletableFuture and Reactive Return Types”: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework 6.2.10 — CaffeineCacheManager Javadoc (`setAsyncCacheMode`): https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework 6.2 — Cache Abstraction: https://docs.spring.io/spring-framework/reference/6.2/integration/cache.html
- Spring Framework 6.2 — Cache API (`retrieve`): https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/Cache.html
- Caffeine — Asynchronous computations: https://github.com/ben-manes/caffeine/wiki/Population
- Caffeine — User guide and features: https://github.com/ben-manes/caffeine/wiki
