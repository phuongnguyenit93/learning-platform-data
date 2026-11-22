# Dùng giá trị trả về qua `#result` ở những ngữ cảnh cho phép

## 1. `#result` là gì và vì sao không dùng được ở mọi chỗ?

Trong các cache annotation của Spring Framework, Spring Expression Language (**SpEL**) cho phép tham chiếu đối số bằng `#p0`, `#p1` hoặc tên tham số, và tham chiếu **kết quả phương thức** bằng biến đặc biệt `#result` ở **một số giai đoạn nhất định**.

`#result` **không phải biến Java** trong thân phương thức. Nó là một biến trong **evaluation context do Spring Cache cung cấp** khi đánh giá biểu thức annotation. Muốn biết dùng được hay không, phải xác định chính xác: **biểu thức được đánh giá trước hay sau khi phương thức có kết quả?**

```text
Lời gọi -> Spring Cache interceptor
             |
             | Trước khi gọi method:
             |  - biết đối số (#p0, #p1, ...)
             |  - có thể chọn cache, tính key đọc, kiểm tra điều kiện trước gọi
             |  - CHƯA có kết quả từ method => không có #result
             |
             | Nếu cần: gọi method, nhận return value
             |  - lúc này mới có #result
             |
             '-- Đánh giá biểu thức sau gọi: ví dụ unless của @Cacheable,
                 key của @CachePut, key của @CacheEvict sau invocation
```

**Quy tắc cốt lõi:** Biểu thức cần chạy **trước** khi phương thức tạo kết quả thì không thể tham chiếu `#result`. Biểu thức chạy **sau** lời gọi, trong ngữ cảnh Spring hỗ trợ biến này, mới có thể dùng `#result` để xét kết quả hoặc lấy thuộc tính của nó.

Ví dụ, nếu một phương thức trả đối tượng `Book`, biểu thức `#result.id()` có nghĩa là gọi phương thức `id()` trên kết quả; biểu thức `#result == null` kiểm tra kết quả có bằng `null` hay không. Hai biểu thức này chỉ có nghĩa nếu Spring đang cung cấp `#result`.

## 2. Bảng quyết định: lúc nào `#result` khả dụng?

| Annotation / thuộc tính | Thời điểm điển hình | Có thể dùng `#result`? | Lý do |
| --- | --- | --- | --- |
| `@Cacheable(key = "...")` | Trước khi tra cache / gọi method | **Không** | Phải biết key để tìm cache trước khi có kết quả |
| `@Cacheable(condition = "...")` | Trước khi quyết định tra cache | **Không** | Điều kiện chặn việc áp dụng caching trước lời gọi |
| `@Cacheable(unless = "...")` | Sau khi method thực thi ở lượt miss | **Có** | Kết quả đã có để quyết định có lưu hay không |
| `@CachePut(key = "...")` | Sau khi method thực thi | **Có** | Spring luôn gọi method và có thể tạo key từ kết quả |
| `@CachePut(unless = "...")` | Sau khi method thực thi | **Có** | Có thể từ chối đưa kết quả vào cache |
| `@CacheEvict(key = "...", beforeInvocation = false)` | Sau khi method thực thi thành công | **Có** | Có thể chọn key cần xóa dựa vào giá trị trả về |
| `@CacheEvict(key = "...", beforeInvocation = true)` | Trước khi method thực thi | **Không** | Xóa diễn ra khi chưa có giá trị trả về |

Với `@CachePut`, những biểu thức được đánh giá sau lời gọi có thể tham chiếu kết quả theo hợp đồng của annotation; cần phân biệt điều này với `@Cacheable(condition=...)` vốn được kiểm tra trước khi tra cache. Với `@CacheEvict`, việc dùng `#result` ở điều kiện/key hậu xử lý phụ thuộc `beforeInvocation = false`. Hãy xác định evaluation context cụ thể thay vì giả định mọi thuộc tính có cùng biến.

**Không dùng `#result` trong `cacheNames` như thể đó là một biểu thức SpEL:** tên cache trong annotation là cấu hình tên cache, không phải một thuộc tính luôn được Spring đánh giá dưới dạng SpEL.

## 3. `@Cacheable(unless = ...)`: từ chối lưu theo kết quả trả về

`@Cacheable` tìm cache **trước** khi cần chạy phương thức. Nếu hit, Spring trả dữ liệu đã lưu và bỏ qua thân method. Nếu miss, phương thức chạy và tạo kết quả. Khi đó, `unless` có quyền dùng `#result` để **quyết định không lưu** kết quả vừa tạo.

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public Book findBook(String id) {
    return repository.findById(id);
}
```

*Đây là đoạn minh họa; `Book` và `repository` cần được định nghĩa. Ví dụ chạy đầy đủ có ở mục 7.*

- Nếu `findBook("B-1")` trả `Book`, `unless` là `false` và Spring có thể lưu đối tượng.
- Nếu phương thức trả `null`, `unless` là `true` và Spring không cache lần trả `null` đó.
- Nếu có cache hit, thân method không chạy và `unless` **không phải bộ lọc đánh giá lại** dữ liệu đã cache.
- Nếu method ném exception, không có return value bình thường để `unless` xử lý; mặc định `@Cacheable` không cache exception.

Ví dụ chọn không lưu dữ liệu chưa được phát hành:

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null || !#result.published()"
)
public Book findBook(String id) {
    return repository.findById(id);
}
```

Biểu thức có toán tử **OR** ngắn mạch: nếu `#result == null` là đúng, phần `!#result.published()` không bị gọi trên `null`. Nếu kết quả là một Java record với accessor `published()`, cú pháp gọi phương thức có thể dùng trong SpEL.

Phải hiểu đúng chức năng của `unless`: nó **không làm method chạy lại**, **không xóa mục cũ theo mặc định**, và **không áp dụng cho cache hit hiện có**. Nó chỉ veto thao tác **lưu giá trị mới** khi phương thức đã tạo kết quả.

## 4. Vì sao `@Cacheable(key = "#result.id()")` là sai?

Xét đoạn code sau:

```java
// SAI: @Cacheable phải tính key trước khi có kết quả
@Cacheable(cacheNames = "books", key = "#result.id()")
public Book findBook(String id) {
    return repository.findById(id);
}
```

Ở bước tra cache, chưa có `Book` nào được tạo. Spring không thể lấy `#result.id()` để tìm entry trước khi gọi method. Việc truy cập thuộc tính trên giá trị không có sẽ gây lỗi khi biểu thức được đánh giá; đây không phải cách sinh khóa hợp lệ cho `@Cacheable`.

Cách sửa khi phương thức nhận ID:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(String id) {
    return repository.findById(id);
}
```

Tương tự, không thể dùng `@Cacheable(condition = "#result != null")` để quyết định liệu có nên tra cache: thời điểm đó chưa có kết quả. Nếu muốn **không lưu giá trị `null` sau khi chạy**, dùng:

```java
@Cacheable(cacheNames = "books", key = "#p0",
           unless = "#result == null")
public Book findBook(String id) {
    return repository.findById(id);
}
```

**Đừng nhầm `condition` với `unless`:**

| Câu hỏi | Công cụ phù hợp |
| --- | --- |
| Dựa vào *đối số đầu vào* để quyết định có dùng cache không? | `condition` (ví dụ `#p0.length() < 30`) |
| Dựa vào *giá trị trả về* để quyết định có lưu kết quả miss không? | `unless` (ví dụ `#result == null`) |
| Dựa vào *đối số đầu vào* để tạo khóa tìm cache? | `key` của `@Cacheable` |
| Dựa vào *kết quả trả về* để tạo khóa ghi cache? | `key` của `@CachePut` |

## 5. `@CachePut(key = "#result.id()")`: khóa được tạo sau khi có kết quả

Khác với `@Cacheable`, `@CachePut` **luôn thực thi phương thức đích** (khi lời gọi đi qua cache advice), rồi cập nhật cache bằng kết quả. Do đó, phương thức có thể trả về đối tượng mang ID mà ta muốn dùng làm key:

```java
@CachePut(cacheNames = "books", key = "#result.id()")
public Book saveBook(String title) {
    return repository.saveNewBook(title);
}
```

*Đây là đoạn minh họa: `saveNewBook` phải trả một `Book` có `id()` hợp lệ; `repository` cần được triển khai.*

Ở ví dụ này, ID có thể do database sinh ra, nên lúc bắt đầu lời gọi chưa có ID. Sau khi `repository.saveNewBook(title)` trả về `Book`, Spring có thể tính `#result.id()` rồi ghi cache tại key đó.

**Các điểm phải kiểm tra:**

- `@CachePut` **không bỏ qua** method khi entry đã tồn tại; mục đích chính là cập nhật cache bằng kết quả vừa tạo.
- Nếu `#result == null` mà biểu thức truy cập `#result.id()`, việc tính key có thể lỗi. Với kết quả có thể null, thiết kế guard/điều kiện tương thích hoặc trả đối tượng hợp lệ trước khi cache.
- Phương thức đọc `@Cacheable(cacheNames = "books", key = "#p0")` phải được gọi với **cùng loại key/ID** để nhìn thấy entry `@CachePut` đã ghi.
- Không nên phối hợp `@Cacheable` và `@CachePut` trên cùng một phương thức một cách tùy tiện: hai annotation hướng tới hành vi thực thi khác nhau.

## 6. `@CacheEvict`: dùng `#result` khi xóa sau lời gọi

`@CacheEvict` loại bỏ entry khỏi cache. Mặc định `beforeInvocation = false`: Spring xóa cache **sau khi phương thức hoàn thành thành công**, nên có thể dùng kết quả để xác định key cần xóa:

```java
@CacheEvict(
    cacheNames = "books",
    key = "#result.id()",
    beforeInvocation = false
)
public Book archiveBook(String id) {
    return repository.archive(id);
}
```

*Đây là đoạn minh họa; `repository.archive(id)` phải trả `Book` có ID và các lớp liên quan cần được định nghĩa.*

Diễn tiến: method `archiveBook` chạy → nhận `Book` → Spring tính `#result.id()` → evict entry. Cách này hữu ích khi key chỉ biết chính xác từ kết quả xử lý.

Nếu `archiveBook` trả `null`, biểu thức `#result.id()` không an toàn; hãy bảo đảm result hợp lệ hoặc áp dụng một điều kiện hậu xử lý phù hợp. Nếu phương thức ném exception và eviction diễn ra sau invocation, mặc định operation không xóa cache.

**Trường hợp không hợp lệ:**

```java
// SAI: xóa trước thì chưa có #result
@CacheEvict(
    cacheNames = "books",
    key = "#result.id()",
    beforeInvocation = true
)
public Book archiveBook(String id) {
    return repository.archive(id);
}
```

Với `beforeInvocation = true`, thao tác evict xảy ra **trước khi method chạy**, bất kể kết quả method là gì hoặc method có ném exception hay không. Do đó chỉ có thể tạo key bằng dữ liệu **đã biết trước**, chẳng hạn `key = "#p0"`.

`@CacheEvict(allEntries = true)` xóa toàn bộ cache, nên không kết hợp việc chọn một key riêng cho thao tác đó.

## 7. Ví dụ Java 17+ chạy được: quan sát ba kiểu sử dụng `#result`

Ví dụ dưới đây dùng Spring Boot **3.3.5**, Java **17+**, Maven và một cache trong bộ nhớ. Có ba mục đích:

1. `@Cacheable(unless = "#result == null || !#result.published()")`: không cache kết quả thiếu hoặc chưa phát hành.
2. `@CachePut(key = "#result.id()")`: dùng ID **từ đối tượng trả về** để ghi cache sau khi cập nhật.
3. `@CacheEvict(key = "#result.id()")`: dùng ID **từ đối tượng trả về** để xóa cache sau khi xóa dữ liệu.

Cấu trúc:

```text
result-spel-demo/
├── pom.xml
└── src/main/java/example/resultspel/
    ├── Application.java
    ├── Book.java
    └── BookService.java
```

**`pom.xml`**

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
    <artifactId>result-spel-demo</artifactId>
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

**`src/main/java/example/resultspel/Book.java`**

```java
package example.resultspel;

public record Book(String id, String title, boolean published) {}
```

**`src/main/java/example/resultspel/BookService.java`**

```java
package example.resultspel;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final Map<String, Book> database = new ConcurrentHashMap<>();
    private final AtomicInteger reads = new AtomicInteger();

    public BookService() {
        database.put("A", new Book("A", "Alpha", true));
        database.put("D", new Book("D", "Draft", false));
    }

    @Cacheable(
        cacheNames = "books",
        key = "#p0",
        unless = "#result == null || !#result.published()"
    )
    public Book find(String id) {
        int count = reads.incrementAndGet();
        System.out.println("DB READ " + id + " #" + count);
        return database.get(id);
    }

    @CachePut(cacheNames = "books", key = "#result.id()")
    public Book update(String id, String title) {
        Book book = new Book(id, title, true);
        database.put(id, book);
        System.out.println("DB WRITE " + id + "=" + title);
        return book;
    }

    @CacheEvict(
        cacheNames = "books",
        key = "#result.id()",
        beforeInvocation = false
    )
    public Book remove(String id) {
        Book removed = database.remove(id);
        if (removed == null) {
            throw new IllegalArgumentException("Unknown book: " + id);
        }
        System.out.println("DB REMOVE " + id);
        return removed;
    }
}
```

**`src/main/java/example/resultspel/Application.java`**

```java
package example.resultspel;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    CommandLineRunner demo(BookService books) {
        return args -> {
            System.out.println("READ A1 => " + books.find("A"));
            System.out.println("READ A2 => " + books.find("A"));
            System.out.println("READ D1 => " + books.find("D"));
            System.out.println("READ D2 => " + books.find("D"));
            System.out.println("PUT => " + books.update("A", "Beta"));
            System.out.println("READ A3 => " + books.find("A"));
            System.out.println("REMOVE => " + books.remove("A"));
            System.out.println("READ A4 => " + books.find("A"));
            System.out.println("READ A5 => " + books.find("A"));
        };
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Các dòng của chương trình theo đúng thứ tự sau (bỏ qua log khởi động từ Spring Boot):

```text
DB READ A #1
READ A1 => Book[id=A, title=Alpha, published=true]
READ A2 => Book[id=A, title=Alpha, published=true]
DB READ D #2
READ D1 => Book[id=D, title=Draft, published=false]
DB READ D #3
READ D2 => Book[id=D, title=Draft, published=false]
DB WRITE A=Beta
PUT => Book[id=A, title=Beta, published=true]
READ A3 => Book[id=A, title=Beta, published=true]
DB REMOVE A
REMOVE => Book[id=A, title=Beta, published=true]
DB READ A #4
READ A4 => null
DB READ A #5
READ A5 => null
```

Giải thích:

- **READ A1:** lần đầu miss. Method chạy và trả `Book("A", "Alpha", true)`, `unless` đánh giá là `false` nên giá trị được lưu.
- **READ A2:** hit. Method `find` không chạy lần nữa; không có log `DB READ`.
- **READ D1/D2:** mỗi lần đều chạy vì kết quả có `published() == false`; `unless` là `true` và từ chối lưu.
- **PUT:** `update` luôn chạy, ghi database giả lập và trả đối tượng `Book("A", "Beta", true)`. `#result.id()` bằng `"A"` nên ghi đè entry `books["A"]`. **READ A3** hit và trả `Beta` mà không truy vấn database.
- **REMOVE:** `remove` trả đối tượng có ID `"A"` rồi `@CacheEvict` dùng `#result.id()` để xóa entry `books["A"]`.
- **READ A4/A5:** database không còn `A`, method trả `null`; `unless = "#result == null ..."` từ chối cache, nên cả hai lượt đều phải chạy method, làm bộ đếm tăng.

Chương trình dùng `ConcurrentMapCacheManager` nên chỉ mô phỏng cache trong một JVM; không kiểm chứng TTL, cache phân tán, transaction hoặc chiến lược serialization. Giá trị số lần đọc được in để chứng minh **method có chạy hay không**. Để chạy ví dụ cần JDK 17+ và Maven; không thể dùng `javac` riêng lẻ cho file có dependency Spring nếu chưa cấu hình classpath.

## 8. `Optional<T>`: `#result` là giá trị bên trong wrapper

Spring Cache hỗ trợ các kiểu wrapper được nhận diện, đặc biệt là `java.util.Optional`. Khi method trả `Optional<Book>`, biểu thức SpEL `#result` trong ngữ cảnh hậu xử lý **đại diện cho đối tượng `Book` bên trong**, thay vì chính wrapper `Optional<Book>`; với `Optional.empty()`, giá trị đó là `null`.

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null || !#result.published()"
)
public java.util.Optional<Book> findOptional(String id) {
    return repository.findOptionalById(id);
}
```

*Đây là đoạn minh họa, chưa chạy độc lập vì `repository` chưa được khai báo.*

Nếu `Optional.of(new Book("A", "Alpha", true))`, `#result` trong `unless` đại diện `Book`. Nếu `Optional.empty()`, điều kiện `#result == null` là `true`. Đừng viết `#result.isPresent()` khi ngữ cảnh đã unwrap: đó là lời gọi của `Optional`, không phải `Book`.

Dấu hỏi an toàn trong SpEL giúp truy cập thuộc tính khi kết quả có thể null:

```java
// Toán tử safe navigation của SpEL: không dereference null
@Cacheable(cacheNames = "books", key = "#p0",
           unless = "#result?.published() == false || #result == null")
public java.util.Optional<Book> findOptional(String id) {
    return repository.findOptionalById(id);
}
```

Chọn cách diễn đạt ngắn gọn, dễ đọc cho điều kiện; với ví dụ này, `#result == null || !#result.published()` đã đủ rõ. Cần xác nhận ngữ nghĩa unwrap với từng kiểu async/reactive và phiên bản framework thay vì mở rộng quy tắc của `Optional` cho mọi wrapper.

## 9. Bẫy thực tế: chọn key, null và kết quả dùng chung

**Bẫy 1 — Giá trị trả về không cùng danh tính với key đọc.** Giả sử `@CachePut(key="#result.id()")` ghi theo `String id`, nhưng method đọc `@Cacheable(key="#p0")` nhận một đối tượng `BookRequest`. Hai key có thể khác nhau dù cùng ID nghiệp vụ. Cần chủ động quy định kiểu khóa thống nhất, ví dụ `#p0.id()` ở phương thức đọc.

**Bẫy 2 — Result có thể null.** Với `@CachePut(key="#result.id()")` hoặc `@CacheEvict(key="#result.id()")`, cần kiểm tra hợp đồng trả về. Nếu null là hợp lệ, bảo vệ expression bằng điều kiện hậu xử lý phù hợp hoặc chọn key có sẵn từ đối số thay vì đọc thuộc tính null.

**Bẫy 3 — Giá trị chưa ổn định.** Một method trả object mutable rồi dùng `#result.id` có thể gặp vấn đề nếu ID bị thay đổi sau thao tác cache. Nên dùng ID bất biến hoặc một snapshot ổn định.

**Bẫy 4 — Dùng `#result` trước khi có result.** `@Cacheable(key="#result.id")` và `@Cacheable(condition="#result != null")` sai về thời điểm. Không có cách làm cho `#result` khả dụng sớm chỉ bằng đổi dấu ngoặc hoặc cú pháp `#root`.

**Bẫy 5 — Giả định đã dùng `unless` thì cache hit được kiểm tra lại.** `unless` chỉ được đánh giá sau khi method đã thực thi ở lượt cần tính kết quả; nó không đọc lại dữ liệu nguồn và không thay cho cơ chế invalidate/TTL.

**Bẫy 6 — Tưởng `#result` thuộc ngữ cảnh chung của mọi SpEL.** `#root.args`, `#p0` và `#result` phục vụ những vai trò khác nhau. Tên tham số có thể không khả dụng khi biên dịch thiếu metadata `-parameters`; cú pháp chỉ số `#p0`/`#a0` giúp tránh phụ thuộc tên tham số.

**Bẫy 7 — Kết quả không hoàn thành bình thường.** Nếu method ném exception, các cache action thực hiện sau lời gọi thành công không có return value bình thường. Xử lý lỗi cache hay exception nghiệp vụ cần logic riêng, không dựa vào `#result` để “bắt” exception.

## 10. Quy trình chọn biểu thức SpEL

Khi cần viết cache annotation, đi theo thứ tự:

1. **Xác định mục tiêu:** tra cache trước method, veto lưu sau method, ghi lại sau update, hay xóa sau mutation?
2. **Xác định thời điểm:** expression sẽ chạy trước hay sau phương thức? Đây là câu hỏi quyết định tính khả dụng của `#result`.
3. **Chọn dữ liệu có sẵn:** nếu chạy trước, chỉ dùng đối số và metadata tương ứng; nếu chạy sau, có thể dùng `#result` tại thuộc tính hỗ trợ.
4. **Thiết kế null-safety:** kết quả có thể null/empty/throw exception không? Có cần `unless`, điều kiện hậu xử lý hay trả kiểu nhất quán?
5. **Kiểm tra key giữa read, put và evict:** cùng cache name, cùng loại key, cùng ý nghĩa nghiệp vụ.
6. **Kiểm tra lời gọi đi qua Spring proxy:** annotation cache chỉ được intercept khi cấu hình Spring tương ứng thực sự có hiệu lực.
7. **Quan sát thực nghiệm:** in counter trong thân method, kiểm tra hit/miss và đọc lại key để xác nhận hành vi.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `@Cacheable(key = "#result.id()")` không hợp lệ nhưng `@CachePut(key = "#result.id()")` có thể hợp lệ?

Đáp án: `@Cacheable` phải tính key để tra cache **trước** khi gọi method; lúc đó chưa có result. `@CachePut` gọi method trước rồi mới dùng kết quả để ghi cache.

**Câu 2.** `@Cacheable(unless = "#result == null")` có làm cache hit trả `null` phải chạy method lại không?

Đáp án: Không. `unless` kiểm tra kết quả vừa được tạo sau lần miss. Việc provider có cache `null` hay không phụ thuộc cấu hình, nhưng `unless` không phải bộ lọc chạy lại trên hit.

**Câu 3.** Có dùng `#result.id()` trong `@CacheEvict(beforeInvocation = true)` không?

Đáp án: Không. Eviction chạy trước method, nên chưa có result. Dùng key dựa trên đối số, hoặc chuyển sang eviction sau lời gọi nếu hợp đồng nghiệp vụ cho phép.

**Câu 4.** Method trả `Optional<Book>`; trong `unless`, `#result` là `Optional<Book>` hay `Book`?

Đáp án: Với `Optional` được Spring Cache hỗ trợ, đó là `Book` bên trong nếu có giá trị; `Optional.empty()` được biểu diễn bằng `null`.

**Câu 5.** Method cập nhật trả `Book(id="A")`, `@CachePut(key="#result.id()")` ghi cache `books["A"]`. Method đọc dùng `@Cacheable(key="#p0")` và nhận `"A"`. Có thể hit entry vừa cập nhật không?

Đáp án: Có, nếu cùng `cacheNames="books"`, key có cùng kiểu/giá trị và cache provider giữ entry đó. Điều này minh họa việc key đọc và key ghi phải thống nhất.

## Tài liệu tham khảo

- Spring Framework Reference, *Declarative Annotation-based Caching*, phần *Conditional Caching* và *Available Caching SpEL Evaluation Context*: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc, `@Cacheable`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework Javadoc, `@CachePut`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework Javadoc, `@CacheEvict`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
