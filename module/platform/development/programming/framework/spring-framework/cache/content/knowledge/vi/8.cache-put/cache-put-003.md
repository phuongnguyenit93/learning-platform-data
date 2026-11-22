# @CachePut: Chọn khóa theo đối số hoặc kết quả trả về

## Mục tiêu

Sau bài học, bạn sẽ biết khi nào `@CachePut` nên tính cache key từ **đối số đầu vào** và khi nào phải lấy từ **giá trị trả về**. Bạn sẽ hiểu thời điểm Spring đánh giá biểu thức SpEL, biết cách giữ cùng một khóa giữa `@CachePut` và `@Cacheable`, tự chạy một ví dụ Java 17+ và phát hiện các lỗi thường gặp với ID sinh sau khi lưu, kết quả `null`, kiểu khóa và giao dịch.

Đây là bài trong nhóm **`@CachePut`**, tập trung vào lựa chọn khóa cho thao tác **luôn chạy phương thức rồi cập nhật cache**. Không nên nhầm `@CachePut` với `@Cacheable`: `@Cacheable` có thể bỏ qua thân phương thức khi hit, còn `@CachePut` luôn thực thi phương thức và ghi kết quả trả về nếu thỏa điều kiện caching.

## 1. Vì sao phải chọn đúng nguồn tạo key?

Giả sử dịch vụ có hai thao tác:

- `updateBook(42, "Spring Cache")` sửa quyển sách có ID 42. ID đã biết **trước** khi chạy method.
- `createBook("Spring Cache")` tạo sách mới; repository/database cấp ID 101 **trong** lúc thực thi. Trước khi gọi, chưa biết ID chính thức.

Cả hai thao tác đều có thể trả về `Book` và cần cập nhật cache `books`, nơi `findById(42)` sử dụng key chính là ID 42. Nếu muốn bản ghi do `createBook` tạo được tìm thấy ngay bằng `findById(101)`, ta phải ghi cache dưới **key 101**, không phải chuỗi tiêu đề `"Spring Cache"`.

Quy tắc chọn nhanh:

| Dữ liệu để xác định entry | Chọn khóa từ đâu? | Ví dụ |
| --- | --- | --- |
| Đối số đã chứa đúng định danh ổn định của entry sẽ cache | **Đối số** | `key = "#p0"` với `updateBook(Long id, ...)` |
| Đối số là object có ID đã xác định và không đổi | **Thuộc tính đối số** | `key = "#p0.id()"` với `save(Book book)` |
| ID chính thức được sinh hoặc chuẩn hóa trong quá trình xử lý | **Kết quả trả về** | `key = "#result.id()"` với `createBook(String title)` |
| Kết quả có thể không tồn tại, hoặc không chứa khóa hợp lệ | Thiết kế lại quy tắc put; kiểm soát kết quả rỗng/lỗi | Tránh truy cập `#result.id()` khi `#result == null` |
| Đọc và ghi dùng những định danh khác nhau | Cần thống nhất lại key schema hoặc chủ động cập nhật các cache tương ứng | Không để ghi bằng tên và đọc bằng ID trong cùng hợp đồng |

Điểm quyết định **không phải** “chọn cách nào ngắn hơn”. Hãy hỏi: *phương thức đọc mà ta muốn cập nhật sẽ tra cache bằng đúng key nào?*

## 2. Thời điểm Spring đánh giá khóa trong @CachePut

Đối với phương thức đồng bộ trả kết quả thông thường, luồng điển hình là:

```text
Lời gọi qua Spring proxy
    │
    ├── Kiểm tra điều kiện áp dụng cache nếu có (condition)
    │
    ├── Thực thi phương thức thật (LUÔN chạy với @CachePut)
    │        └── Có thể lưu database, tạo ID, chuẩn hóa dữ liệu...
    │
    ├── Nhận kết quả và xét unless nếu có
    │
    ├── Tính cache key theo biểu thức (có thể dùng #result)
    │
    └── Ghi kết quả trả về vào cache dưới key đó
```

`@CachePut` có thể dùng `#result` trong biểu thức `key` **vì dữ liệu trả về đã có khi thực hiện cache put**. Điều này là đặc điểm quan trọng của annotation.

Ví dụ chọn từ đối số:

```java
@CachePut(cacheNames = "books", key = "#p0")
public Book rename(Long id, String newTitle) {
    return repository.updateTitle(id, newTitle);
}
```

Ví dụ chọn từ kết quả:

```java
@CachePut(cacheNames = "books", key = "#result.id()")
public Book create(String title) {
    return repository.insertAndReturnBook(title);
}
```

Hai đoạn trên là **mẫu minh họa**, cần có `Book` và `repository` trong ứng dụng thực tế. Các `key` SpEL được hiểu như sau:

- `#p0` / `#a0`: tham số tại vị trí 0; `#p1` là tham số tiếp theo.
- `#root.args[0]`: một cách khác để truy cập đối số thứ nhất.
- `#result`: giá trị trả về của method (đối tượng nghiệp vụ sau khi Spring xử lý wrapper được hỗ trợ).
- `#result.id()`: gọi accessor của đối tượng được trả về, ví dụ accessor của Java `record Book`.

**Cẩn thận với `@Cacheable`:** không dùng `key = "#result.id()"` để tra cache trong `@Cacheable`, vì key tra cứu phải biết *trước* khi quyết định có gọi method hay không. `#result` hợp lệ cho `@Cacheable(unless = "...")` sau khi chạy, nhưng không dành cho biểu thức `key` của `@Cacheable`.

## 3. Nguyên tắc nhất quán giữa @CachePut và @Cacheable

Giả sử:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findById(Long id) { /* đọc nguồn */ }
```

Cache đó phân biệt entry theo `Long id`. Mọi đường ghi cache muốn phục vụ `findById` phải tạo **cùng cache name, cùng giá trị key và cùng kiểu key phù hợp backend**.

Ví dụ đúng:

```text
findById(101L)         → books[Long(101)]
rename(101L, "New")    → books[Long(101)]
create(...) trả Book(id=101) → books[Long(101)]
```

Một số kết hợp dễ sai:

| Đường ghi cache | Đường đọc cache | Vấn đề |
| --- | --- | --- |
| `@CachePut(key="#p0")` ở `create(String title)` | `@Cacheable(key="#p0")` ở `findById(Long id)` | Ghi theo title nhưng đọc theo ID; entry tạo ra không được dùng cho lần đọc ID. |
| `key="#result.id()"` nhưng kết quả trả ID là `String "101"` | Đọc với `Long 101L` | Key khác kiểu; nhiều backend xem là hai key khác nhau. |
| Ghi `cacheNames="bookDetails"` | Đọc `cacheNames="books"` | Khác cache namespace. |
| Ghi với ID cũ dù thao tác chuyển định danh | Đọc bằng ID mới | Entry có thể cũ/sai; cần chuyển khóa và xóa entry cũ nếu hợp đồng cho phép đổi ID. |
| Dùng mặc định tất cả tham số `(id, title)` cho update | Đọc chỉ có `id` | Update tạo `SimpleKey(id,title)`, không khớp key chỉ là `id`. |

Mọi method nên có một **hợp đồng key** rõ ràng, ví dụ `books: Book.id (Long)`. Thay đổi hợp đồng phải xem cả phương thức đọc, put, evict, cách serialize và mọi instance sử dụng cùng cache.

## 4. Demo chạy được: ID trả về cho create, ID đầu vào cho rename

Ví dụ dùng Java 17+, Spring Boot với Gradle và một cache trong bộ nhớ. Nó minh họa cả hai cách tính khóa và xác nhận các lệnh đọc sau `@CachePut` là cache hit. Backend `ConcurrentMapCacheManager` không có TTL hay giới hạn kích thước mặc định; mục đích ở đây chỉ để quan sát cách chọn key.

Trong dự án Spring Boot Gradle hiện có (cấu hình plugin và phiên bản Spring Boot tương thích với Java 17+), cần dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
```

Tạo **`src/main/java/example/cacheput/Book.java`**:

```java
package example.cacheput;

public record Book(Long id, String title) {
}
```

`record` giúp kết quả bất biến; accessor `id()` và `title()` có thể được gọi trong Java hoặc SpEL.

Tạo **`src/main/java/example/cacheput/CacheConfiguration.java`**:

```java
package example.cacheput;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }
}
```

Tạo **`src/main/java/example/cacheput/BookService.java`**:

```java
package example.cacheput;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {

    // Mô phỏng database và bộ sinh ID, chỉ phục vụ bài học.
    private final Map<Long, Book> database = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(100);
    private final AtomicInteger sourceReads = new AtomicInteger();

    // Chưa biết ID đầu vào. Sau khi create() trả về,
    // Spring lấy ID từ Book được trả về để đặt cache.
    @CachePut(cacheNames = "books", key = "#result.id()")
    public Book create(String title) {
        Long id = nextId.incrementAndGet();
        Book book = new Book(id, title);
        database.put(id, book);
        return book;
    }

    // Đã biết đúng ID entry trước khi method chạy.
    // Cả title mới lẫn số lần gọi đều không thuộc key của books.
    @CachePut(cacheNames = "books", key = "#p0")
    public Book rename(Long id, String newTitle) {
        Book updated = new Book(id, newTitle);
        if (database.replace(id, updated) == null) {
            throw new IllegalArgumentException("Unknown book: " + id);
        }
        return updated;
    }

    // Đường đọc dùng đúng schema key mà hai đường put dùng.
    @Cacheable(cacheNames = "books", key = "#p0")
    public Book findById(Long id) {
        System.out.println("SOURCE_READ " + sourceReads.incrementAndGet());
        return database.get(id);
    }

    // Chỉ để chứng minh lần đọc tiếp theo là miss sau eviction.
    @CacheEvict(cacheNames = "books", key = "#p0")
    public void evictCachedBook(Long id) {
    }

    public int sourceReadCount() {
        return sourceReads.get();
    }
}
```

Tạo **`src/main/java/example/cacheput/CachePutKeyDemoApplication.java`**:

```java
package example.cacheput;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CachePutKeyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CachePutKeyDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner runExample(BookService books) {
        return args -> {
            Book created = books.create("Java 17");
            System.out.println("created = " + created);
            System.out.println("read1 = " + books.findById(created.id()));

            Book updated = books.rename(created.id(), "Spring Cache");
            System.out.println("renamed = " + updated);
            System.out.println("read2 = " + books.findById(created.id()));

            books.evictCachedBook(created.id());
            System.out.println("read3 = " + books.findById(created.id()));
            System.out.println("sourceReads = " + books.sourceReadCount());
        };
    }
}
```

Chạy từ thư mục dự án:

```bash
./gradlew bootRun
# Trên Windows PowerShell: .\gradlew.bat bootRun
```

**Các dòng `System.out` do chương trình này tạo ra**, theo đúng thứ tự, không kể log của Spring Boot:

```text
created = Book[id=101, title=Java 17]
read1 = Book[id=101, title=Java 17]
renamed = Book[id=101, title=Spring Cache]
read2 = Book[id=101, title=Spring Cache]
SOURCE_READ 1
read3 = Book[id=101, title=Spring Cache]
sourceReads = 1
```

Đối chiếu từng hành động:

1. `create("Java 17")` sinh ID 101, trả `Book`. `@CachePut(key="#result.id()")` ghi `books[101L]`.
2. `findById(101L)` lấy cache hit; không in `SOURCE_READ`.
3. `rename(101L, "Spring Cache")` **vẫn chạy** và cập nhật database, sau đó `@CachePut(key="#p0")` thay `books[101L]` bằng kết quả mới.
4. `findById(101L)` lại hit, thấy tên mới mà chưa đọc database.
5. `evictCachedBook(101L)` xóa entry, nên `findById(101L)` tiếp theo in `SOURCE_READ 1` rồi trả nội dung từ database.
6. Bộ đếm nguồn bằng 1 minh chứng: hai lần đọc đầu không chạy thân `findById`, lần đọc sau eviction mới chạy.

**Tại sao stdout có thể dự đoán?** Chạy mới một process, `nextId` khởi tạo bằng 100 và không có request đồng thời; `Book` record có `toString()` chuẩn của Java; `CommandLineRunner` gọi từng thao tác theo thứ tự. Demo không phụ thuộc database thật.

Đây là **bốn class trong một dự án Spring Boot**, không phải chương trình một file độc lập chạy trực tiếp bằng `javac`: cần Spring và build dependencies. Nếu dự án có các runner khác hoặc cache manager khác, log/hành vi ngoài ví dụ có thể khác.

## 5. Khi nào nên lấy key từ đối số?

Dùng **đối số** khi tham số đã mô tả đúng khóa của cache mà các đường đọc sử dụng.

Ví dụ sửa người dùng có định danh đã biết:

```java
@CachePut(cacheNames = "usersById", key = "#p0")
public User updateProfile(Long userId, UpdateProfileCommand command) {
    return repository.updateAndFetch(userId, command);
}
```

Ở đây `User`, `UpdateProfileCommand` và `repository` là các kiểu/biến minh họa. `userId` luôn là ID của entry được cập nhật, nên không cần đợi kết quả để xác định key. Nếu dùng key mặc định, hai tham số `userId` và `command` cùng tham gia khóa; như vậy có thể lệch với `getById(userId)`.

Một số biến thể hợp lý:

- `key = "#p0"`: tham số đầu tiên là ID, ví dụ `Long id`.
- `key = "#p0.id()"`: tham số đầu tiên là object có ID ổn định.
- `key = "#p0.tenantId() + ':' + #p0.bookId()"`: chỉ là ví dụ ghép chuỗi khi các thành phần đã được chuẩn hóa và thoát ký tự phù hợp. Với nhiều thành phần, ưu tiên value object/key generator tránh va chạm chuỗi.
- `key = "#p1"`: ID nằm ở tham số thứ hai, với điều kiện nó thật sự là key của đường đọc.

**Vấn đề cần tự kiểm tra:** nếu ID được thay đổi/chuẩn hóa trong thân phương thức hoặc có nhiều tenant dùng cùng ID, chọn một đối số đơn lẻ có thể không đủ. Key phải phản ánh đủ những thành phần làm thay đổi kết quả và quyền truy cập.

## 6. Khi nào nên lấy key từ kết quả trả về?

Dùng **`#result`** khi định danh cuối cùng chỉ xuất hiện sau khi chạy method hoặc khi hệ thống muốn lấy giá trị đã được chuẩn hóa/thực tế lưu từ đối tượng trả về.

Ví dụ tạo sản phẩm với ID do database cấp:

```java
@CachePut(cacheNames = "productsById", key = "#result.id()")
public Product createProduct(CreateProductRequest request) {
    return repository.insertAndFetch(request);
}
```

Với ví dụ này, `Product`, `CreateProductRequest` và `repository` là các kiểu minh họa. Phương thức phải trả **đối tượng có ID cuối cùng ổn định**; nếu repository chỉ trả boolean thành công hay `void`, Spring không thể suy ra ID bằng `#result.id()`. Khi đó cần đổi hợp đồng trả về, lấy ID bằng cơ chế khác, hoặc evict/đọc lại theo một key đã biết.

Các trường hợp thực tế:

- Database tự sinh ID sau `INSERT`.
- Phía server gán public ID/slug khác với giá trị khách hàng gửi.
- Service đổi ID tạm sang ID chính thức.
- Dữ liệu sau lưu được chuẩn hóa, và đường đọc dùng định danh đã chuẩn hóa.

**Điều kiện bắt buộc:** giá trị mà `#result` chỉ tới phải có mặt khi put và thành phần tạo key phải hợp lệ. Nếu method có thể trả `null` hay `Optional.empty()`, đừng mặc định `#result.id()` an toàn. Có thể chọn hợp đồng fail-fast khi không tạo được đối tượng, hoặc cấu hình từ chối cache kết quả rỗng (chẳng hạn `unless = "#result == null"`) và kiểm thử trên phiên bản Spring/provider đang dùng.

Với return type wrapper được Spring hỗ trợ như `Optional<Book>`, `#result` trong caching SpEL chỉ **Book thực tế**, không phải `Optional<Book>`; trường hợp empty có thể đưa tới `null`. Với future/reactive return type, thời điểm hoàn thành bất đồng bộ và hành vi cache còn phụ thuộc phiên bản Spring và backend; cần kiểm chứng riêng thay vì suy ra từ demo đồng bộ.

## 7. Những biểu thức không được dùng nhầm

| Tình huống | Cách đúng | Vì sao |
| --- | --- | --- |
| Put sau khi method sinh ID | `@CachePut(key="#result.id()")` | Tại thời điểm put, đã có kết quả. |
| Put cập nhật bản ghi ID đã có | `@CachePut(key="#p0")` | Cùng key với read-by-ID. |
| Tra cứu trước khi chạy method | `@Cacheable(key="#p0")` | Phải biết key trước khi quyết định hit/miss. |
| Tránh cache kết quả không phù hợp | `@CachePut(unless="#result == null")` nếu hợp đồng cho phép | `unless` được xét sau invocation. |
| Chỉ cache khi đầu vào thỏa điều kiện | `@CachePut(condition="#p0 != null")` khi phù hợp chữ ký | `condition` dựa trên thông tin sẵn có trước invocation. |
| Xóa entry sau thành công bằng kết quả trả về | Có thể dùng `@CacheEvict(key="#result.id()")` khi `beforeInvocation=false` | Chỉ có result sau invocation; cần hợp đồng trả về phù hợp. |

Không đặt `@Cacheable` và `@CachePut` tùy tiện trên cùng method: một annotation có mục tiêu tránh thực thi khi hit, annotation kia luôn cần thực thi để cập nhật cache. Tránh các điều kiện loại trừ giữa chúng dựa trên `#result` vì việc lựa chọn cache operation có bước đánh giá trước invocation.

## 8. Những lỗi khó phát hiện trong môi trường thật

### 8.1. Key của write khác key của read

`@CachePut(key="#result.id()")` sẽ không giúp `getByCode(String code)` nếu method đọc cache theo code. Giải pháp là thống nhất một cache theo ID, hoặc duy trì cache riêng theo code và cập nhật/evict đúng từng cache. Đừng giả định hai cache tự đồng bộ.

### 8.2. Cùng ID nhưng khác tenant hoặc quyền

Nếu `books` có dữ liệu riêng theo tenant, `key="#result.id()"` vẫn có thể thiếu tenant. Ví dụ tenant A và B cùng có book ID 101, entry có thể bị ghi đè. Key cần đủ phạm vi, chẳng hạn value object `(tenantId, bookId)`, hoặc cache namespace tách tenant. Cần kiểm tra quyền *trước cached method* vì khi hit, thân `@Cacheable` có thể không chạy.

### 8.3. Đối số và kết quả có ID không khớp

`updateBook(requestedId, ...)` có thể trả một entity có `canonicalId` khác requested ID. Chọn `#p0` hay `#result.id()` phải dựa trên định danh mà **đường đọc** tra cứu. Nếu thay đổi ID hợp lệ, đồng thời xử lý entry cũ (evict/chuyển key) và cập nhật index cache có liên quan. Một lần put tự nó không xóa mọi alias cũ.

### 8.4. Kết quả lỗi, null hoặc side effect

`@CachePut` luôn gọi method, nên lỗi từ repository vẫn xảy ra. Khi method ném exception, put thông thường không diễn ra theo luồng thành công. Khi method trả `null` hoặc một kiểu không chứa ID, biểu thức `#result.id()` không thể coi là hợp lệ. Định nghĩa rõ hành vi thất bại, trả về entity/ID cần thiết và chính sách bỏ qua giá trị rỗng.

### 8.5. Thời điểm commit và request đồng thời

`@CachePut` cập nhật cache theo kết quả method; điều đó **không tự bảo đảm** dữ liệu cache và database đã commit atomically. Nếu transaction rollback sau khi cache đã put, hoặc có request khác ghi đồng thời, cache có thể sai hoặc cũ. Với yêu cầu nhất quán nghiêm ngặt, xem xét transaction boundary, cập nhật cache sau commit, TTL/invalidation và kiểm thử cạnh tranh.

### 8.6. Self-invocation và backend

Annotation hoạt động qua Spring proxy theo cấu hình mặc định. Gọi `this.rename(...)` trong cùng bean hoặc tạo object bằng `new BookService()` có thể bỏ qua advice. Đồng thời key `Long(101)`, key string `"101"` và serialization key Redis có thể khác nhau; test cần dùng cùng backend/key generator thực tế ở deployment.

## 9. Kiểm thử để biết mình đã chọn đúng

Dựa trên demo, thêm test hoặc chạy quan sát các trường hợp:

1. **Create mới:** gọi `create` trả ID mới, ngay sau đó gọi `findById(id)`. Nếu đặt cache đúng từ `#result.id()` thì không đọc nguồn.
2. **Update có ID:** gọi `rename(id, newTitle)`, sau đó `findById(id)` phải hit và trả title mới. Giá trị title không thuộc key.
3. **Evict:** xóa entry cùng ID, gọi lại `findById(id)` phải đọc nguồn một lần.
4. **Sai key có chủ đích:** thử `@CachePut(key="#p0")` trên `create(String title)`; đường đọc bằng Long ID sẽ miss. Chỉ làm trong môi trường test, không giữ cấu hình sai.
5. **Hai tenant trùng ID:** mô phỏng hai bản ghi có cùng numeric ID nhưng khác tenant. Nếu cache chia sẻ, đảm bảo key đủ tenant để không trả nhầm.
6. **Null/exception:** thử create thất bại/không trả entity. Xác nhận không có put lỗi hoặc entry không hợp lệ.
7. **Biên transaction:** với service thật, kiểm tra cập nhật thành công, rollback và nhiều request đồng thời.
8. **Type và namespace:** so sánh Long ID với String ID; xác nhận cache name và key generator trên cả read/put/evict.

Chỉ kết luận “khóa đã đúng” khi có bằng chứng **cả nội dung trả về đúng lẫn hit/miss đúng**. Một giá trị trả về đúng do lần nào cũng đọc database chưa chứng minh `@CachePut` đã cập nhật đúng cache.

## 10. Checklist quyết định khi code review

- [ ] Đã xác định **phương thức đọc** và key của nó trước khi chọn key cho `@CachePut`.
- [ ] Biết rõ ID/giá trị khóa có trước invocation hay chỉ có sau khi method trả về.
- [ ] Nếu lấy từ đối số, dùng đúng `#p0`/`#p1` hoặc thuộc tính tương ứng, không vô tình tạo `SimpleKey` gồm cả dữ liệu không liên quan.
- [ ] Nếu lấy từ kết quả, return type luôn có định danh hợp lệ hoặc có chính sách xử lý kết quả rỗng.
- [ ] Cache name, kiểu key, namespace, tenant/scope và serializer tương thích giữa read/put/evict.
- [ ] Không dùng `#result` để tính lookup key của `@Cacheable`.
- [ ] Cập nhật database, cache và giao dịch có chiến lược nhất quán; xử lý entry cũ khi ID/alias đổi.
- [ ] Test bằng số lần truy cập nguồn và dữ liệu nhận được, bao gồm trường hợp thất bại và concurrency nếu có.

## Tài liệu tham khảo

- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — `@CachePut` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html
