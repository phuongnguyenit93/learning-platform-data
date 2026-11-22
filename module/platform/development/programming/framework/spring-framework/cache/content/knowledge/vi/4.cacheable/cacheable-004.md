# Trả kết quả từ cache và bỏ qua thân phương thức với `@Cacheable`

## 1. Ý nghĩa chính xác của “bỏ qua thân phương thức”

Khi một phương thức Spring được đánh dấu `@Cacheable`, lời gọi **đi qua bộ chặn cache (cache interceptor)**. Interceptor tìm một giá trị đã lưu bằng **tên cache** và **khóa (key)**. Nếu tìm thấy mục hợp lệ (**cache hit**), nó trả giá trị đó cho bên gọi **ngay tại interceptor**; **không đi vào thân phương thức đích**.

```java
@Cacheable(cacheNames = "books", key = "#p0")
public String findTitle(String isbn) {
    System.out.println("BODY EXECUTED");
    return repository.findTitle(isbn);
}
```

*Đây là đoạn minh họa, `repository` chưa được khai báo; ví dụ chạy đầy đủ ở mục 4.*

Với cache `books` đã có mục tương ứng `isbn = "B-1"`, lời gọi `findTitle("B-1")` có thể trả ngay chuỗi tiêu đề đã lưu. Khi đó, dòng `System.out.println("BODY EXECUTED")` **không được in ra**, `repository.findTitle(isbn)` **không được gọi**, và mọi nhánh `if`, vòng lặp hay thao tác nằm trong thân phương thức **đều không chạy**.

Điều cần phân biệt:

- **Không chạy thân phương thức** không có nghĩa là “không làm gì”: bên gọi vẫn thực hiện lời gọi, Spring vẫn phải xử lý interceptor, tìm cache, tạo/tính key và tra cứu entry.
- **Không chạy thân phương thức** không có nghĩa là dữ liệu nguồn đã được kiểm tra lại. Đúng mục cache vẫn có thể chứa dữ liệu cũ.
- **Không chạy thân phương thức** không có nghĩa là mọi interceptor khác đều bị bỏ qua; việc áp dụng các advice khác phụ thuộc cấu hình và thứ tự advice. Kết luận ở đây chỉ nói về **thân phương thức đích được `@Cacheable` bảo vệ**.
- Nếu lookup **miss** hoặc caching không được áp dụng, phương thức thật sẽ chạy bình thường.

Cache phù hợp khi kết quả của lời gọi có thể dùng lại và việc chạy lại phương thức tốn tài nguyên: truy vấn dữ liệu, tính toán, gọi dịch vụ ngoài. `@Cacheable` khác với việc “lưu log rồi tiếp tục gọi hàm”; ở trạng thái hit, nó **thay thế kết quả của lời gọi**.

## 2. Hai nhánh xử lý: cache hit và cache miss

Với cấu hình đơn giản:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public String findTitle(String isbn) {
    return expensiveLookup(isbn);
}
```

Spring hoạt động theo luồng đồng bộ thông dụng:

```text
Caller -> Spring-managed bean proxy -> CacheInterceptor
                                        |
                                        v
                             cacheName = "books"
                             key = isbn (theo #p0)
                                        |
                                        v
                                cache lookup
                                /          \
                             HIT            MISS
                              |               |
                    lấy cachedValue      gọi findTitle(...)
                              |               |
                              |          chạy expensiveLookup
                              |               |
                              |          nhận kết quả (nếu thành công)
                              |               |
                              |          lưu cache nếu đủ điều kiện
                              |               |
                              v               v
                        return result     return result
```

Ví dụ theo thời gian, giả sử cache ban đầu trống:

| Thời điểm | Lời gọi | Cache tại key | Thân phương thức chạy? | Giá trị trả |
| --- | --- | --- | --- | --- |
| T1 | `findTitle("B-1")` | Miss | Có: truy vấn dữ liệu, tạo `"Java in Action"` | `"Java in Action"` |
| T2 | `findTitle("B-1")` | Hit | Không | `"Java in Action"` từ cache |
| T3 | `findTitle("B-2")` | Miss | Có: xử lý ISBN khác | Giá trị riêng của B-2 |
| T4 | `findTitle("B-1")` | Hit | Không | `"Java in Action"` từ cache |
| T5 | Xóa key `"B-1"` rồi gọi lại | Miss | Có | Giá trị mới đọc từ nguồn |

**Key quyết định có dùng lại được kết quả hay không.** Trong ví dụ, `#p0` trỏ đến đối số thứ nhất (ISBN). Tên cache `books` xác định không gian lưu. Truy vấn cache bằng `("books", "B-1")` là một lookup khác `("books", "B-2")`.

Nếu không chỉ định `key`, Spring dùng chiến lược mặc định dựa trên đối số; ở ví dụ một đối số `String`, key cũng là ISBN. Tuy nhiên, việc thiết kế key rõ ràng đặc biệt hữu ích khi kết quả còn phụ thuộc locale, tenant, bộ lọc hoặc phiên bản dữ liệu. Chỉ cùng tên phương thức chưa đủ để kết luận hai lời gọi có cùng key.

## 3. Vì sao trả được kết quả mà không gọi phương thức?

`@Cacheable` là **cache abstraction** của Spring. Bản thân annotation chỉ khai báo hành vi; cơ chế thực thi do Spring tổ chức qua cache advice, `CacheManager` và `Cache` thực tế:

1. **`@EnableCaching`** (hoặc cấu hình tương đương) bật xử lý cache annotation.
2. **Spring bean proxy** nhận lời gọi từ bean khác và chuyển cho cache interceptor.
3. **`CacheManager`** cung cấp cache mang tên cần dùng, ví dụ `books`.
4. **Key generator hoặc biểu thức SpEL** tạo key, ví dụ `#p0`.
5. **Cache provider** trả trạng thái lookup. Một entry có thể đã có từ lời gọi trước, hoặc đã bị xóa/hết hạn tùy provider.
6. Nếu hit, interceptor **trả cached value** về nơi gọi; nếu miss, nó **gọi target method**, rồi có thể lưu kết quả.

Vì vậy, giá trị được trả từ cache **không phải kết quả của một lần chạy ngầm mới**. Đó là kết quả đã được lưu ở một thời điểm trước (có thể đã được serialize/deserialize hoặc chuyển đổi biểu diễn bởi provider). Với cache local, thường có thể lấy lại đối tượng đang nằm trong bộ nhớ; với cache phân tán, biểu diễn lưu trữ và đặc tính chia sẻ phụ thuộc backend. Không nên suy ra rằng cache hit luôn trả cùng một object reference.

## 4. Ví dụ chạy được với Java 17+ và Spring Boot: nhìn thấy thân phương thức bị bỏ qua

Ví dụ dùng **Spring Boot 3.3.5**, **Java 17+**, Maven và `ConcurrentMapCacheManager` để minh họa lookup trên bộ nhớ của một tiến trình. Chương trình in một dòng `BODY -> ...` **mỗi khi thân phương thức thực sự chạy**, nhờ đó có thể kiểm chứng chính xác thời điểm hit/miss. Sau cùng chương trình xóa một key để chứng minh lần gọi tiếp theo phải chạy lại thân phương thức.

Cấu trúc:

```text
cache-hit-demo/
├── pom.xml
└── src/main/java/example/cachedemo/
    ├── CacheHitDemoApplication.java
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
    <artifactId>cache-hit-demo</artifactId>
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

**`src/main/java/example/cachedemo/BookService.java`**

```java
package example.cachedemo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final AtomicInteger loads = new AtomicInteger();

    @Cacheable(cacheNames = "books", key = "#p0")
    public String findTitle(String isbn) {
        int loadNumber = loads.incrementAndGet();
        System.out.println("BODY -> isbn=" + isbn + ", load=" + loadNumber);
        return "Book[" + isbn + "]@load" + loadNumber;
    }
}
```

**`src/main/java/example/cachedemo/CacheHitDemoApplication.java`**

```java
package example.cachedemo;

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
public class CacheHitDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheHitDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    CommandLineRunner demo(BookService service, CacheManager cacheManager) {
        return args -> {
            System.out.println("CALL 1 -> " + service.findTitle("B-1"));
            System.out.println("CALL 2 -> " + service.findTitle("B-1"));
            System.out.println("CALL 3 -> " + service.findTitle("B-2"));

            Cache books = cacheManager.getCache("books");
            if (books == null) {
                throw new IllegalStateException("Missing cache: books");
            }
            books.evict("B-1");
            System.out.println("EVICT -> B-1");

            System.out.println("CALL 4 -> " + service.findTitle("B-1"));
        };
    }
}
```

Tại thư mục `cache-hit-demo` chạy:

```bash
mvn spring-boot:run
```

Các dòng thuộc ví dụ in ra theo **đúng thứ tự** dưới đây; Spring Boot cũng in log khởi động riêng:

```text
BODY -> isbn=B-1, load=1
CALL 1 -> Book[B-1]@load1
CALL 2 -> Book[B-1]@load1
BODY -> isbn=B-2, load=2
CALL 3 -> Book[B-2]@load2
EVICT -> B-1
BODY -> isbn=B-1, load=3
CALL 4 -> Book[B-1]@load3
```

**Giải thích cơ chế, không chỉ nhìn output:**

- **CALL 1**: key `"B-1"` chưa tồn tại; Spring gọi `findTitle`, in `BODY ... load=1`, nhận chuỗi `Book[B-1]@load1` rồi lưu vào cache `books`.
- **CALL 2**: vẫn là key `"B-1"`. Spring hit, trả đúng `Book[B-1]@load1`. **Không xuất hiện dòng `BODY` mới**, và biến đếm không tăng.
- **CALL 3**: key `"B-2"` chưa tồn tại; thân phương thức chạy lần thứ hai và tạo `Book[B-2]@load2`.
- **EVICT**: xóa riêng key `"B-1"` khỏi `books`. Mục của `"B-2"` vẫn còn.
- **CALL 4**: lại là `"B-1"` nhưng cache vừa bị xóa; Spring miss và chạy thân phương thức lần thứ ba, nên trả `Book[B-1]@load3`.

`AtomicInteger` ở đây là dụng cụ quan sát **số lần phương thức đích chạy**, không phải “version” thực của sách. Ví dụ cố ý tạo kết quả có hậu tố số lần load để nhìn thấy tính tái sử dụng; một phương thức nghiệp vụ thường trả dữ liệu từ repository hay nguồn bên ngoài.

**Điều kiện để kết quả ở trên đúng:** dùng đúng hai file Java và `pom.xml`, lời gọi đến bean `BookService` qua dependency injection, `@EnableCaching` đang bật, `ConcurrentMapCacheManager` chưa có dữ liệu trước lúc chạy và không có thao tác cạnh tranh khác. Đây là ví dụ chạy bằng Maven; không có lệnh `javac BookService.java` đơn lẻ vì lớp cần các dependency của Spring.

## 5. “Thân phương thức bị bỏ qua” ảnh hưởng những gì?

Giả sử method thật có các thao tác:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public BookView readBook(String isbn) {
    validateIsbn(isbn);             // A
    metric.increment();             // B
    BookView book = queryDb(isbn);  // C
    auditRead(isbn);                // D
    return book;                    // E
}
```

*Đoạn này minh họa hành vi, chưa phải chương trình độc lập: `BookView` và các hàm phụ trợ chưa được khai báo.*

Nếu **hit**:

- A, B, C, D, E **không chạy**. Interceptor trả kết quả cache; kể cả biểu thức `return book` trong thân hàm cũng không được đánh giá lần nữa.
- Việc ghi metric/audit bên trong hàm sẽ không thấy các lần hit. Muốn thống kê số lượt gọi hoặc kiểm soát truy cập **mỗi request**, đặt trách nhiệm đó tại một tầng thực thi được với mọi lượt gọi, đồng thời kiểm tra thứ tự advice nếu dùng AOP.
- Tác dụng phụ như gửi email, trừ tồn kho, cập nhật trạng thái hay phát event sẽ bị bỏ qua khi hit. **Không đặt hành vi bắt buộc phải thực thi mỗi lần trong phương thức cacheable**.
- Nếu `validateIsbn` bảo đảm điều kiện bảo mật, không được mặc định tin rằng validation sẽ chạy khi hit. Kiểm tra quyền ở ranh giới phù hợp với từng request; key và dữ liệu trả về phải phân biệt mọi ngữ cảnh có ảnh hưởng đến kết quả/ủy quyền.

Khi miss, toàn bộ logic method chạy theo code bình thường; sau đó Spring mới xét lưu kết quả. Cơ chế này tạo ra một khác biệt cốt lõi giữa **lệnh truy cập cache** và **lệnh thực thi nghiệp vụ**.

## 6. Những trường hợp lời gọi vẫn chạy thân phương thức

`@Cacheable` không hứa “mỗi key chỉ chạy đúng một lần trong suốt đời ứng dụng”. Thân phương thức có thể chạy trong các trường hợp:

| Tình huống | Kết quả |
| --- | --- |
| Key chưa có trong cache | **Miss** → chạy method và cân nhắc lưu |
| Key đã bị evict, cache bị clear, TTL hết hạn hoặc provider không còn entry | **Miss** → chạy method |
| Cache bị vô hiệu hóa, chưa bật caching hoặc lời gọi không đi qua proxy | Annotation không chặn được lời gọi → method chạy |
| `condition` của `@Cacheable` đánh giá thành `false` | Không áp dụng caching cho lần gọi → method chạy |
| Cache miss, nhưng `unless` đánh giá thành `true` sau khi chạy | Method chạy, **không lưu** giá trị mới |
| Hai luồng gần như đồng thời cùng miss một key | Có thể cả hai đều chạy method nếu không có cơ chế phối hợp load |
| Key khác nhau dù đối số nhìn có vẻ tương tự | Mỗi key có lookup riêng; key mới thường miss lần đầu |

Ví dụ về `condition` và `unless`:

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    condition = "#p0 != 'temporary'",
    unless = "#result == null"
)
public String findTitle(String isbn) {
    return loadTitleFromDatabase(isbn);
}
```

*Đoạn trên cần định nghĩa `loadTitleFromDatabase` mới chạy được.*

- `condition` được kiểm tra trước khi Spring quyết định tra cache; khi key `"temporary"`, phương thức vẫn chạy **mỗi lần**, không lookup/put qua `@Cacheable` đó.
- `unless` chỉ có cơ hội đánh giá sau khi phương thức đã được gọi và tạo kết quả ở lần miss. Nếu `#result == null`, Spring từ chối lưu kết quả này.
- Khi hit, phương thức không chạy, `unless` không dùng để xác minh lại cached value; không nên xem nó là bước bảo đảm dữ liệu nguồn luôn mới.
- Nếu phương thức ném exception trong lần miss, Spring không có giá trị trả về bình thường để lưu theo `@Cacheable` mặc định. Lần sau có thể tiếp tục miss và lại thực thi.

**Về giá trị `null`:** việc provider có hỗ trợ cache null hay không, và cách thể hiện giá trị đó, phụ thuộc implementation/cấu hình. Không nên kết luận “trả `null` đồng nghĩa cache miss” nếu chưa kiểm tra khả năng của cache cụ thể.

## 7. Lời gọi nào thật sự đi qua cache interceptor?

Chế độ annotation caching mặc định sử dụng proxy. Hai tình huống dưới đây có kết quả rất khác nhau:

```text
Controller/Runner -> bean proxy -> @Cacheable findTitle(..)
                                  -> HIT: trả cached value, bỏ qua method body

BookService.someOtherMethod()
    -> this.findTitle(..)       -> gọi nội bộ trực tiếp vào target
                                  -> proxy không chặn self-invocation
                                  -> method body vẫn chạy
```

Ví dụ:

```java
@Service
public class BookService {
    @Cacheable("books")
    public String findTitle(String isbn) {
        return expensiveLookup(isbn);
    }

    public String findFromInside(String isbn) {
        return this.findTitle(isbn); // bỏ qua proxy cache mặc định
    }
}
```

*Đây là ví dụ minh họa cơ chế self-invocation; `expensiveLookup` chưa được khai báo.*

Ngay cả khi `books` đã chứa ISBN trên, gọi `findFromInside` rồi gọi `this.findTitle` vẫn thực thi thân `findTitle` trong cấu hình proxy mặc định. Tương tự, tạo object thủ công bằng `new BookService()` sẽ không tự gắn Spring cache interceptor.

Cách viết dễ bảo trì: để một Spring bean khác nhận `BookService` bằng constructor injection và gọi qua bean đó; bảo đảm caching được bật. Tránh phụ thuộc `@Cacheable` trên phương thức private hoặc final khi cơ chế proxy không thể intercept chúng. Một số cấu hình weaving khác proxy có quy tắc khác; ở đây tập trung vào Spring cache annotation theo proxy mặc định.

## 8. Trả dữ liệu cũ là hệ quả cần chủ động xử lý

Vì hit bỏ qua thân phương thức, **database có thể đã thay đổi mà lần đọc sau vẫn trả kết quả cũ**:

```text
10:00  Database: B-1 = "Tên cũ"
10:01  findTitle(B-1) MISS -> load "Tên cũ" -> cache[B-1] = "Tên cũ"
10:02  Database: B-1 = "Tên mới"
10:03  findTitle(B-1) HIT  -> trả "Tên cũ", không vào database
10:04  evict(B-1)
10:05  findTitle(B-1) MISS -> load "Tên mới" -> cache[B-1] = "Tên mới"
```

Để cache phản ánh cập nhật, thường dùng một hoặc nhiều kỹ thuật:

- **`@CacheEvict`** trên thao tác cập nhật thành công để xóa đúng entry, khiến lần đọc sau tải lại dữ liệu.
- **`@CachePut`** nếu thao tác cập nhật trả về chính kết quả cần lưu: phương thức gắn `@CachePut` **luôn được gọi**, sau đó cache được cập nhật.
- **TTL / eviction theo provider** để mục tự hết hạn hoặc bị loại theo chính sách dung lượng.
- **Invalidation giữa các instance** nếu nhiều ứng dụng cùng chia sẻ/nhân bản dữ liệu.

Ví dụ annotation xóa cache sau cập nhật thành công:

```java
@CacheEvict(cacheNames = "books", key = "#p0")
public void renameBook(String isbn, String newTitle) {
    repository.rename(isbn, newTitle);
}
```

*Đây là đoạn minh họa, cần cung cấp `repository`.* Key xóa `#p0` phải khớp key đọc `#p0` trong `@Cacheable`, và cùng cache `books`. Nếu đọc theo `"B-1"` nhưng xóa theo `"B-1:vi"` thì mục cũ sẽ vẫn nằm lại. Với transaction, thời điểm evict/put so với commit cần được thiết kế cẩn thận để tránh đưa dữ liệu chưa commit hoặc dữ liệu cũ trở lại cache.

## 9. Cache hit trong môi trường có nhiều request

Một điểm khó quan sát: **hai request cùng đến khi cache trống có thể đều miss** trước khi một request kịp lưu kết quả. Lúc đó, dù dùng cùng key, thân phương thức có thể chạy hai lần.

```text
Thread A: lookup B-1 -> MISS ---- load() ---- put(B-1)
Thread B: lookup B-1 -> MISS ---- load() ---- put(B-1)
```

`@Cacheable(sync = true)` yêu cầu cache phối hợp nạp giá trị cho cùng key **nếu provider hỗ trợ**:

```java
@Cacheable(cacheNames = "books", key = "#p0", sync = true)
public String findTitle(String isbn) {
    return loadTitleFromDatabase(isbn);
}
```

*Đoạn minh họa, cần định nghĩa `loadTitleFromDatabase`.*

Đừng hiểu `sync = true` là khóa phân tán toàn hệ thống hoặc là cam kết “method chạy đúng một lần mãi mãi”. Hiệu quả phụ thuộc nhà cung cấp cache, phạm vi phối hợp và vòng đời entry; `sync` cũng có các ràng buộc annotation, chẳng hạn không dùng cùng `unless` và chỉ một cache cho operation đồng bộ. Khi giá trị bị evict hoặc hết hạn, một lần load mới vẫn cần xảy ra.

Với method trả về `CompletableFuture` hoặc kiểu reactive, các phiên bản Spring Framework mới có cơ chế cache thích ứng với kết quả bất đồng bộ; không nên suy nguyên xi dòng thời gian đồng bộ của ví dụ `String` sang các kiểu đó nếu chưa xem API/provider tương ứng.

## 10. Các lỗi thường gặp khi phân tích “method có chạy hay không”

1. **Chỉ nhìn return value.** Hai lần trả chuỗi giống nhau chưa chứng minh hit; có thể method thực sự chạy hai lần và trả cùng dữ liệu. Cần quan sát bộ đếm bên trong method, log truy vấn hoặc metrics của cache.
2. **Gọi `this.method()` rồi kết luận annotation không hoạt động.** Trong proxy mode, self-invocation bỏ qua interceptor.
3. **Quên `@EnableCaching` / bean không do Spring quản lý.** Annotation một mình không tạo cache behavior cho đối tượng bình thường.
4. **Nhầm “hit” với “đã tải dữ liệu mới”.** Hit ưu tiên giá trị lưu, nên cập nhật database không tự khiến phương thức chạy lại.
5. **Thiết kế key thiếu ngữ cảnh.** Nếu kết quả phụ thuộc locale/tenant/user filter nhưng key chỉ là ID, phương thức có thể bị bỏ qua ở lúc cần tạo một kết quả khác. Đây là lỗi về correctness và có thể liên quan phân tách dữ liệu.
6. **Đặt nghiệp vụ bắt buộc phải chạy vào method cacheable.** Log nghiệp vụ, side effect, kiểm tra quyền từng lần có thể bị bỏ qua khi hit.
7. **Giả sử các backend có hành vi giống nhau.** Spring chỉ chuẩn hóa abstraction; TTL, cách lưu null, serialize, thống kê hit/miss, chia sẻ cache và cơ chế load đồng thời còn phụ thuộc provider.
8. **Hiểu `@CachePut` là `@Cacheable`.** `@CachePut` thực thi method và ghi cache; `@Cacheable` mới có thể bỏ qua method khi hit.
9. **Dùng chung cache name và key cho hai method khác ý nghĩa.** Giá trị của method này có thể bị trả cho method kia, dẫn đến sai dữ liệu hoặc sai kiểu.

## 11. Tự kiểm tra bằng các tình huống

**Tình huống A:** Cache `books["B-1"]` chứa `"Title A"`. Method `findTitle("B-1")` có `System.out.println("DB query")` trong body. Gọi qua bean proxy với cache enabled, key khớp và entry còn hiệu lực. Điều gì xảy ra?

**Đáp án:** Trả `"Title A"` từ cache; không in `"DB query"`. Interceptor đã cung cấp kết quả trước khi gọi target method.

**Tình huống B:** Database đổi `"Title A"` thành `"Title B"` nhưng entry `"B-1"` chưa evict. Gọi lại thì sao?

**Đáp án:** Có thể vẫn nhận `"Title A"`. Cache hit không thực thi method để kiểm tra database.

**Tình huống C:** `findTitle("B-1")` trả `"Title A"` ba lần liên tục. Có chắc chỉ thực thi một lần không?

**Đáp án:** Không thể kết luận chỉ từ giá trị. Cần xem caching có bật, lời gọi có qua proxy, key có nhất quán, entry có tồn tại và có lần nào bị evict/expire hay không.

**Tình huống D:** Hai thread đồng thời gọi một ISBN chưa có cache. Có bảo đảm method chỉ chạy một lần không?

**Đáp án:** Không có bảo đảm tổng quát với `@Cacheable` thông thường. Cần cơ chế phối hợp phù hợp (ví dụ `sync = true` khi provider hỗ trợ), và vẫn phải xác định phạm vi phối hợp.

**Tình huống E:** Một method đánh dấu `@Cacheable` được gọi qua `this.findTitle(...)` từ method khác trong cùng bean. Vì sao nó vẫn truy vấn database?

**Đáp án:** Self-invocation trên target bỏ qua proxy cache trong cơ chế mặc định; cache interceptor không có cơ hội lookup và trả kết quả.

## Tài liệu tham khảo

- Spring Framework, *Declarative Annotation-based Caching*: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework, *Proxying Mechanisms*, phần self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Boot, *Caching*: https://docs.spring.io/spring-boot/reference/io/caching.html
