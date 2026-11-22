# Spring Cache trong bộ nhớ: Thiết lập tên cache tĩnh hoặc chế độ tạo động

## 1. Vấn đề: tên vùng cache khác với khóa của một entry

Spring Cache cho phép khai báo cách lưu và đọc dữ liệu qua các annotation như `@Cacheable`, `@CachePut` và `@CacheEvict`. Một thao tác cache có ít nhất hai thông tin cần phân biệt:

- **Tên cache (cache name/cache region):** Chọn vùng lưu trữ, ví dụ `books` hoặc `authors`.
- **Khóa cache (cache key):** Chọn entry trong vùng đó, ví dụ ISBN `"B42"`.

Ví dụ một phương thức truy xuất sách:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public String findBook(String isbn) {
    // Ví dụ minh họa: trả thông tin sách từ nguồn dữ liệu.
    return "Book(" + isbn + ")";
}
~~~

Trong đoạn minh họa, `books` là *tên cache* còn `#p0` lấy đối số đầu tiên làm *key*. Cache `books` có thể chứa rất nhiều key khác nhau. **Danh sách tên cache tĩnh không có nghĩa là danh sách key tĩnh.**

Spring sử dụng `CacheManager` để tìm đối tượng `Cache` theo tên. Với `ConcurrentMapCacheManager` của Spring Framework, người phát triển có thể quyết định **tên vùng cache được khai báo trước** hay **được tạo khi có lời gọi yêu cầu**.

## 2. `ConcurrentMapCacheManager` là gì?

`org.springframework.cache.concurrent.ConcurrentMapCacheManager` cung cấp các vùng cache in-memory dựa trên cấu trúc map đồng thời của Java. Đây là implementation gọn nhẹ, thích hợp cho demo, kiểm thử hoặc ứng dụng ít yêu cầu về chính sách lưu trữ.

Manager cho phép:

- Lấy vùng cache bằng `getCache(String name)`.
- Xem những tên cache đã được quản lý bằng `getCacheNames()`.
- Khai báo tập tên bằng constructor hoặc `setCacheNames(Collection<String>)`.
- Chuyển giữa **static mode** và **dynamic mode** theo cách cấu hình `setCacheNames(...)`.

Nó **không tự cung cấp TTL, giới hạn dung lượng hay cache phân tán** như một số provider chuyên dụng. Dữ liệu nằm trong tiến trình JVM; hai instance ứng dụng khác nhau không có cùng map trừ khi xây dựng cơ chế phối hợp khác.

| Tiêu chí | Static mode | Dynamic mode |
| --- | --- | --- |
| Vùng cache được tạo | Những tên đã khai báo trước. | Được tạo khi có yêu cầu `getCache(name)`. |
| Một tên chưa tồn tại | Trả `null`; không tự tạo thêm. | Có thể tạo vùng cache mới cho tên đó. |
| Khai báo phổ biến | Constructor chứa các tên hoặc `setCacheNames(collection)`. | Constructor không tham số hoặc `setCacheNames(null)`. |
| Lợi ích | Dễ audit, phát hiện tên ngoài danh sách. | Linh hoạt khi phát sinh vùng cache tại runtime. |
| Rủi ro cần kiểm soát | Tên mới cần thay đổi cấu hình. | Tên sai chính tả cũng có thể tạo vùng mới, tăng bộ nhớ. |

## 3. Dynamic mode: tạo tên cache theo yêu cầu

Constructor không tham số tạo `ConcurrentMapCacheManager` ở **dynamic mode**:

~~~java
ConcurrentMapCacheManager manager = new ConcurrentMapCacheManager();

System.out.println(manager.getCacheNames()); // Ban đầu: []
Cache books = manager.getCache("books");      // Tạo mới vùng books
Cache authors = manager.getCache("authors");  // Tạo mới vùng authors
~~~

Đây là đoạn minh họa API; để biên dịch trong chương trình cần import `ConcurrentMapCacheManager` và `Cache`. Ví dụ hoàn chỉnh ở phần 6.

Khi một thành phần gọi `getCache("books")` lần đầu, manager không tìm thấy tên trong map nội bộ nên khởi tạo `ConcurrentMapCache` mới và ghi nhớ nó. Các lần gọi sau với cùng tên dùng vùng đã có.

~~~text
new ConcurrentMapCacheManager()
          |
          v
    dynamic mode
    getCacheNames = []
          |
          v
    getCache("books")
          |
          v
    tạo vùng "books"
          |
          v
    getCacheNames chứa "books"
          |
          v
    getCache("authors")
          |
          v
    tạo thêm vùng "authors"
~~~

Điểm cần nhớ:

1. **Tạo động vùng cache** không có nghĩa là entry key phải thay đổi động. Một vùng `books` duy nhất vẫn chứa được nhiều ISBN.
2. `getCacheNames()` cho biết các vùng manager **đang quản lý**, không phải liệt kê những entry key bên trong vùng.
3. Dynamic mode **không tự suy ra** tên từ đối số của method. Nó chỉ tạo vùng tên mà `CacheResolver`/mã ứng dụng thực sự yêu cầu.
4. Nếu gõ nhầm `boooks` thay vì `books`, manager có thể tạo vùng sai tên và không báo lỗi: điều này là ưu điểm về tính linh hoạt, nhưng cũng làm lỗi cấu hình khó nhận biết.

**Giới hạn vận hành:** Không ghép mỗi request ID hoặc giá trị đầu vào tùy ý thành một cache name mới. Với `ConcurrentMapCacheManager`, số vùng có thể tăng theo số tên khác nhau, và dữ liệu trong mỗi vùng cũng có thể tăng. Giới hạn hoặc kiểm soát nguồn tạo tên; với workload lớn hãy cân nhắc Caffeine/Redis và chính sách eviction phù hợp.

## 4. Static mode: chỉ quản lý tên khai báo trước

Static mode hữu ích khi hệ thống biết rõ các vùng cache, ví dụ `books`, `authors` và `categories`. Có hai cách thiết lập.

### 4.1. Khai báo bằng constructor

~~~java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("books", "authors");
~~~

Constructor có danh sách tên tạo các vùng được yêu cầu và **tắt chế độ tự tạo thêm tên**. Vì vậy:

~~~java
Cache books = manager.getCache("books");       // khác null
Cache unknown = manager.getCache("invoices");   // null
~~~

Hai đoạn trên là minh họa sử dụng cùng manager. `getCache("invoices")` trả `null` thay vì khởi tạo vùng mới. Nếu một method `@Cacheable(cacheNames="invoices")` dùng manager này, Spring không thể resolve vùng mà annotation yêu cầu và có thể phát sinh lỗi cấu hình/thực thi khi chạm vào thao tác. Vì thế danh sách static phải khớp các tên trên annotation.

### 4.2. Thiết lập bằng `setCacheNames(...)`

Một manager không tham số có thể được cấu hình thêm:

~~~java
ConcurrentMapCacheManager manager = new ConcurrentMapCacheManager();
manager.setCacheNames(List.of("books", "authors"));
~~~

Nếu truyền collection **khác `null`**, manager đăng ký các cache với tên tương ứng và hoạt động ở static mode. Không có cache mới ngoài danh sách được tạo theo yêu cầu.

Nếu truyền `null`:

~~~java
manager.setCacheNames(null);
~~~

manager trở lại **dynamic mode** và được phép tạo thêm các vùng theo yêu cầu sau đó.

### 4.3. Không nhầm `setCacheNames(null)` với xóa cache

`setCacheNames(null)` là thao tác **đổi chế độ**, không phải lệnh `clear()` xóa toàn bộ entry. Các cache đã được manager quản lý có thể vẫn tồn tại khi mở lại dynamic mode.

Ngược lại, khi gọi `setCacheNames(collection)`, các cache tương ứng tên trong collection có thể được **tạo lại/thay thế** để áp dụng cấu hình. Các cache cũ khác không nhất thiết bị xóa khỏi map chỉ nhờ lời gọi này. Vì thế không nên điều chỉnh cấu hình khi đang phục vụ traffic rồi giả định dữ liệu cache vẫn giữ nguyên. Hãy cấu hình tại startup; nếu cần đổi khi chạy, thiết kế migration và kiểm thử behavior của phiên bản Spring dùng thực tế.

| Lời gọi | Chế độ/kết quả |
| --- | --- |
| `new ConcurrentMapCacheManager()` | Dynamic mode, chưa tạo sẵn vùng nào. |
| `new ConcurrentMapCacheManager("books","authors")` | Static mode, hai tên được đăng ký. |
| `setCacheNames(List.of("books","authors"))` | Static mode, đăng ký các tên khai báo. |
| `setCacheNames(null)` | Dynamic mode, cho phép tạo thêm region. |
| `getCacheNames()` | Xem tập tên hiện được manager quản lý. |
| `getCache("missing")` | Dynamic: tạo tên mới; static: trả `null` nếu tên chưa được quản lý. |

## 5. Sử dụng trong ứng dụng Spring có `@Cacheable`

Khi bật `@EnableCaching`, Spring chặn lời gọi đi qua proxy và áp dụng annotation. Cấu hình manager static phổ biến:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books", "authors");
    }
}
~~~

Các kiểu trên thuộc Spring Framework (`@Configuration`, `@EnableCaching`, `@Bean`, `CacheManager`, `ConcurrentMapCacheManager`). Đây là trích đoạn cấu hình; ví dụ chạy được có đầy đủ import nằm ở phần 6.

Service có thể dùng:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public String getBook(String isbn) {
    return bookRepository.load(isbn);
}
~~~

Kết quả:

- Lần đầu gọi cùng ISBN: cache miss, thực thi method, lưu entry.
- Lần tiếp theo với cùng ISBN và entry còn hợp lệ: có thể hit và bỏ qua thân method.
- Static mode không hạn chế số lượng ISBN bên trong `books`.
- Nếu annotation ghi một tên chưa khai báo như `booooks`, manager static không tự mở thêm vùng cho lỗi chính tả đó.

**Cần phân biệt:** `@Cacheable` xử lý entry khi gọi method; `CacheManager` điều khiển việc lấy vùng. Nếu gọi trực tiếp `manager.getCache("books")` thì không cần `@EnableCaching`; nếu muốn annotation tự hoạt động, phải bật caching và gọi qua bean Spring-managed proxy đúng cách.

## 6. Demo Spring Boot 3 / Java 17: kiểm tra static và dynamic

Demo sử dụng hai manager độc lập: `dynamicCacheManager` tạo không tham số và `staticCacheManager` tạo với tên `books`, `authors`. Chương trình cũng chuyển một manager từ dynamic sang static rồi chuyển lại, để quan sát bằng `getCacheNames()` và kết quả `getCache(name)`.

**Tạo tệp `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

**Tạo tệp `src/main/java/demo/CacheNamesApplication.java`:**

~~~java
package demo;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CacheNamesApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheNamesApplication.class, args);
    }

    @Bean("dynamicCacheManager")
    ConcurrentMapCacheManager dynamicCacheManager() {
        return new ConcurrentMapCacheManager();
    }

    @Bean("staticCacheManager")
    ConcurrentMapCacheManager staticCacheManager() {
        return new ConcurrentMapCacheManager("books", "authors");
    }

    @Bean
    CommandLineRunner demo(
            @Qualifier("dynamicCacheManager")
            ConcurrentMapCacheManager dynamic,
            @Qualifier("staticCacheManager")
            ConcurrentMapCacheManager fixed) {

        return args -> {
            System.out.println("dynamic initial = " + names(dynamic));
            System.out.println("dynamic books created = "
                    + (dynamic.getCache("books") != null));
            System.out.println("dynamic names = " + names(dynamic));

            System.out.println("static names = " + names(fixed));
            System.out.println("static books exists = "
                    + (fixed.getCache("books") != null));
            System.out.println("static invoices exists = "
                    + (fixed.getCache("invoices") != null));

            dynamic.setCacheNames(List.of("books", "authors"));
            System.out.println("static mode rejects invoices = "
                    + (dynamic.getCache("invoices") == null));

            dynamic.setCacheNames(null);
            System.out.println("dynamic mode creates invoices = "
                    + (dynamic.getCache("invoices") != null));
            System.out.println("dynamic final names = " + names(dynamic));
        };
    }

    private static String names(CacheManager manager) {
        return manager.getCacheNames().stream()
                .sorted()
                .toList()
                .toString();
    }
}
~~~

**Chạy:** trong thư mục dự án đã có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Nếu máy có Gradle tương thích, dùng `gradle bootRun`. JDK 17+ là yêu cầu cho project; lần đầu có thể phải tải dependency từ Maven Central.

Bỏ qua banner và log khởi động của Spring Boot, **những dòng do demo chủ động in ra** sẽ có thứ tự:

~~~text
dynamic initial = []
dynamic books created = true
dynamic names = [books]
static names = [authors, books]
static books exists = true
static invoices exists = false
static mode rejects invoices = true
dynamic mode creates invoices = true
dynamic final names = [authors, books, invoices]
~~~

Giải thích kết quả:

1. Dynamic manager ban đầu chưa có cache nên danh sách rỗng.
2. `getCache("books")` tạo vùng `books` và làm tên này xuất hiện ở danh sách.
3. Manager static có sẵn hai tên; `invoices` chưa được khai báo nên `getCache("invoices")` trả `null`.
4. `setCacheNames(List.of("books", "authors"))` chuyển manager đầu tiên sang static mode, vì vậy không được tự tạo `invoices`.
5. `setCacheNames(null)` trở lại dynamic mode. Lúc này `getCache("invoices")` tạo vùng mới và danh sách cuối có `authors`, `books`, `invoices`.

Hàm `names` cố ý sắp xếp tên để stdout ổn định, không dựa vào thứ tự duyệt của map. Demo gọi trực tiếp `CacheManager` nên không cần `@EnableCaching`; một ứng dụng dùng `@Cacheable` vẫn cần bật annotation processing và gọi method qua bean/proxy.

## 7. Khi nào cần `CacheResolver` để chọn tên tại runtime?

Dynamic mode **cho phép tạo cache theo tên được yêu cầu**, nhưng nó **không tự quyết định tên dựa trên tham số của method**. Muốn định tuyến cache theo tenant, vùng hoặc loại dữ liệu, có thể triển khai `CacheResolver`.

### 7.1. Một tên cố định, key có tenant

Nếu tất cả tenant dùng chung region `tenant-books`, cần đưa tenant vào key để tránh trùng key giữa các tenant:

~~~java
@Cacheable(cacheNames = "tenant-books",
           key = "#p0 + ':' + #p1")
public Book findForTenant(String tenantId, String bookId) {
    return repository.findForTenant(tenantId, bookId);
}
~~~

Đây là minh họa, phụ thuộc `Book`/`repository` của ứng dụng. Tên region vẫn cố định là `tenant-books`; key mới là `tenantId:bookId`. Quy tắc định dạng key cần tránh xung đột khi input có ký tự phân cách và phải đảm bảo tenant đã được xác thực tại tầng nghiệp vụ.

### 7.2. Mỗi tenant dùng một cache region riêng

Nếu nghiệp vụ thực sự cần vùng riêng cho từng tenant, một resolver có thể dùng tham số runtime để chọn tên. **Trích đoạn cấu hình** dưới đây cần import `CacheResolver`, `Cache`, `CacheManager`, `CacheOperationInvocationContext`, `Collection`, `List` và các annotation Spring nếu dùng trực tiếp:

~~~java
@Component("tenantCacheResolver")
public class TenantCacheResolver implements CacheResolver {

    private final CacheManager manager;

    public TenantCacheResolver(
            @Qualifier("dynamicCacheManager") CacheManager manager) {
        this.manager = manager;
    }

    @Override
    public Collection<? extends Cache> resolveCaches(
            CacheOperationInvocationContext<?> context) {
        Object[] args = context.getArgs();
        if (args.length < 2 || !(args[0] instanceof String tenantId)) {
            throw new IllegalArgumentException("Missing tenant id");
        }
        if (!tenantId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("Invalid tenant id");
        }

        Cache cache = manager.getCache("tenant-" + tenantId);
        if (cache == null) {
            throw new IllegalStateException("Cannot resolve tenant cache");
        }
        return List.of(cache);
    }
}
~~~

Với service:

~~~java
@Cacheable(cacheResolver = "tenantCacheResolver", key = "#p1")
public Book findForTenant(String tenantId, String bookId) {
    return repository.findForTenant(tenantId, bookId);
}
~~~

Lúc này:
- `tenantId` quyết định **tên region**, chẳng hạn `tenant-a`.
- `bookId` quyết định **key** trong region của tenant đó.
- Region có thể được tạo khi resolver gọi `getCache` trên manager dynamic.

Resolver là nơi quyết định cache nào dùng cho một invocation. Không khai báo đồng thời `cacheManager` và `cacheResolver` trên cùng thao tác vì hai thuộc tính này là lựa chọn loại trừ nhau. Resolver cũng cần được đăng ký thành Spring bean theo tên tham chiếu. Nếu chỉ có các region `books` và `authors` cố định, giải pháp resolver riêng thường không cần thiết.

**Cảnh báo:** Cache name không phải lớp bảo mật. Phải xác thực phân quyền tenant độc lập, validate tên trước khi tạo, hạn chế số region và theo dõi bộ nhớ. Nếu người dùng có thể tùy ý tạo `tenant-id` mới, local map có thể tăng mãi.

## 8. Chọn static hay dynamic và các bẫy vận hành

| Tình huống | Gợi ý |
| --- | --- |
| Có ba vùng `books`, `authors`, `orders` cố định. | Chọn static mode để kiểm soát tên. |
| Nhiều key ISBN nhưng chỉ một vùng `books`. | Vẫn dùng static mode; key không phải region. |
| Tên vùng phát sinh theo tenant runtime đã kiểm soát. | Dynamic manager + resolver phù hợp; cần giới hạn region. |
| Muốn phát hiện lỗi gõ sai tên cache sớm. | Static mode và integration test với tên annotation. |
| Muốn TTL, max-size hoặc thống kê eviction tốt. | Xem xét provider cache chuyên dụng như Caffeine. |
| Cần chia sẻ cache giữa nhiều JVM. | Dùng backend chia sẻ phù hợp như Redis, không dựa vào local ConcurrentMap. |

### Các lỗi phổ biến

1. **Truy cập tên lạ trả `null`:** Có thể manager static chưa có tên; kiểm tra constructor/`setCacheNames` và `@Cacheable(cacheNames=...)`.
2. **Tên sai chính tả lại trở thành vùng thật:** Dynamic mode tạo vùng mới theo yêu cầu; dùng constants, kiểm thử và static mode nếu thích hợp.
3. **Nhầm tên với key:** Một region cố định vẫn có nhiều entry; chỉ dùng `key`/`KeyGenerator` để thiết kế entry key.
4. **Dùng `setCacheNames(collection)` như lệnh xóa mọi cache:** Đây là cấu hình vùng, không phải API xóa tất cả entry; một số vùng được khởi tạo lại, các vùng khác có thể còn.
5. **Tự tạo vùng theo mọi request ID:** Tên tăng không kiểm soát gây chiếm bộ nhớ, đặc biệt khi dùng map cache không TTL.
6. **Dùng tên vùng để thay cho bảo mật tenant:** Cache chỉ chứa dữ liệu; quyền truy cập phải kiểm tra ở lớp nghiệp vụ.
7. **Cho rằng dynamic mode tạo tên từ method parameters:** Phải có `CacheResolver` hoặc logic quản lý cache quyết định tên; mode của manager chỉ cấp vùng theo tên đã yêu cầu.
8. **Nghĩ cache in-memory tự chia sẻ giữa các instance:** `ConcurrentMapCacheManager` giữ state ở mỗi JVM, không đồng bộ nhiều node.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** `new ConcurrentMapCacheManager()` tạo manager ở chế độ nào?

**Đáp án:** Dynamic mode, có thể tạo vùng cache mới khi `getCache(name)` được gọi.

**Câu 2.** `new ConcurrentMapCacheManager("books", "authors")` xử lý `getCache("invoices")` thế nào?

**Đáp án:** Static mode không tự tạo vùng `invoices` chưa khai báo; phương thức trả `null`.

**Câu 3.** `setCacheNames(null)` có xóa mọi entry trong cache không?

**Đáp án:** Không. Nó chuyển manager sang dynamic mode; việc evict/clear entry là thao tác riêng.

**Câu 4.** Một cache tên `books` có thể có 10.000 entry key khác nhau dù manager ở static mode không?

**Đáp án:** Có. Static mode giới hạn tên vùng cache, không tự giới hạn số key.

**Câu 5.** Muốn tạo region theo tenant ID tại runtime thì chỉ cần `@Cacheable(cacheNames="tenant-" + id)` có đúng không?

**Đáp án:** Không. Annotation không cho ghép tên như biểu thức Java runtime theo cách đó. Dùng một tên cố định và key chứa tenant, hoặc dùng custom `CacheResolver` để chọn region động.

**Câu 6.** Vì sao dynamic mode cần quy tắc giới hạn số tên cache?

**Đáp án:** Mỗi tên mới có thể tạo một cache region in-memory; nếu tên không giới hạn, số region và lượng dữ liệu giữ trong RAM cũng có thể tăng không kiểm soát.

**Ghi nhớ:** Với `ConcurrentMapCacheManager`, constructor không tham số mặc định cho phép **tạo vùng cache động**; constructor có danh sách tên hoặc `setCacheNames(collection)` đặt **danh sách vùng tĩnh**. `setCacheNames(null)` cho phép tạo thêm vùng động. Phải phân biệt tên vùng cache với key, và không sử dụng dynamic mode như một nguồn tạo vô hạn vùng bộ nhớ.

## Tài liệu tham khảo

- [Spring Framework — ConcurrentMapCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html) — constructor, `setCacheNames`, `getCache`, `getCacheNames`.
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html).
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html) — cache names, cache resolver và entry key.
