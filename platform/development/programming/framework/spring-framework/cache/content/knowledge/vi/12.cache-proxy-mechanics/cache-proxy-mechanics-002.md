# Tự gọi trong cùng đối tượng và vì sao annotation cache bị bỏ qua

> **Spring Framework Cache Abstraction · Chủ đề: Cơ chế proxy.** Bài học giải thích *self-invocation* — một phương thức gọi phương thức khác trên chính đối tượng — và lý do `@Cacheable`, `@CacheEvict` hoặc `@CachePut` đôi khi không hoạt động dù annotation đã được khai báo đúng.

## 1. Hiện tượng: cùng phương thức nhưng có lúc cache hit, có lúc không

Hãy tưởng tượng `BookService.findByIsbn(String isbn)` được đánh dấu `@Cacheable`. Controller gọi trực tiếp qua bean Spring hai lần cùng ISBN; lần đầu đọc dữ liệu nguồn, lần hai thường trả từ cache. Nhưng một phương thức khác trong `BookService` gọi `this.findByIsbn(isbn)` lại khiến logic đọc dữ liệu nguồn chạy mỗi lần.

Ví dụ cấu trúc:

~~~java
public class BookService {

    @Cacheable(cacheNames = "books", key = "#p0")
    public String findByIsbn(String isbn) {
        return "book:" + isbn;
    }

    public String findFromSameObject(String isbn) {
        return this.findByIsbn(isbn);
    }
}
~~~

Đây là đoạn minh họa **nội dung của class**, cần import `Cacheable`, tạo bean và bật caching trong ứng dụng thực. Phần 5 có chương trình đầy đủ với bộ đếm để chứng minh số lần method thực thi.

**Nguyên nhân:** Spring Cache Abstraction mặc định hoạt động qua **Spring AOP proxy**. Cache interceptor chỉ được kích hoạt khi lời gọi đi qua proxy. Lời gọi `this.findByIsbn(isbn)` xảy ra *bên trong target object*, vì vậy không đi qua interceptor và annotation không điều khiển cache ở lời gọi ấy.

Annotation không biến mất khỏi source hay bytecode; chỉ có **đường đi của lời gọi** là khác nhau.

## 2. Proxy và target có vai trò khác nhau

Khi bật `@EnableCaching` với chế độ `AdviceMode.PROXY` mặc định, Spring thiết lập hạ tầng AOP để bao bean có caching operations bằng một **proxy**. Có thể hình dung:

- **Client**: controller, service khác hoặc mã lấy bean từ `ApplicationContext`.
- **Proxy**: đối tượng đứng trước target, nơi advice/interceptor có cơ hội chạy.
- **CacheInterceptor**: xử lý các annotation cache, tra key, đọc/ghi/xóa entry.
- **Target**: đối tượng thực chứa phần thân phương thức nghiệp vụ.
- **CacheManager**: cung cấp vùng cache theo tên cho interceptor.

### Lời gọi bên ngoài đi qua proxy

~~~text
Controller hoặc bean khác
          |
          | bookService.findByIsbn("ISBN-A")
          v
    [Spring Proxy]
          |
          v
   [CacheInterceptor]
          |
          +-- hit --------------> trả entry, không chạy thân method
          |
          +-- miss --> Target.findByIsbn("ISBN-A")
                                 |
                                 v
                          tải dữ liệu nguồn
                                 |
                          ghi giá trị cache
                                 |
                                 v
                              trả về
~~~

Trong trường hợp `@Cacheable`, cache hit cho phép trả giá trị lưu sẵn mà không thực thi method đích. Với `@CacheEvict` hoặc `@CachePut`, interceptor thực hiện hành động tương ứng theo annotation.

### Lời gọi bên trong đối tượng bỏ qua proxy

~~~text
Controller gọi bookService.findFromSameObject("ISBN-A")
          |
          v
    [Spring Proxy]
          |
          v
    [Target BookService]
          |
          | this.findByIsbn("ISBN-A")
          v
    [Target.findByIsbn]
          |
          v
    Chạy thân method trực tiếp
    (không có CacheInterceptor cho findByIsbn ở lời gọi này)
~~~

Điểm dễ nhầm là lời gọi ban đầu vào `findFromSameObject` **có thể đi qua proxy**, nhưng khi đã ở trong target, `this` vẫn là tham chiếu đến target. Nó không tự chuyển thành tham chiếu đến proxy.

Viết `findByIsbn(isbn)` mà bỏ `this.` cũng là **self-invocation ngầm**; kết quả vẫn giống lời gọi `this.findByIsbn(isbn)`.

## 3. Những annotation nào chịu ảnh hưởng?

Self-invocation có thể tác động lên nhiều cache annotation, vì chúng dùng chung cơ chế interception trong proxy mode:

| Annotation trên method được gọi nội bộ | Khi đi qua proxy | Khi target gọi bằng `this` |
| --- | --- | --- |
| `@Cacheable` | Có thể hit và bỏ qua method, hoặc miss rồi nạp/cache | Chạy method trực tiếp, không có bước tra/ghi cache cho lời gọi nội bộ |
| `@CacheEvict` | Evict đúng key hoặc toàn vùng theo cấu hình | Không kích hoạt thao tác evict từ annotation |
| `@CachePut` | Chạy method rồi cập nhật cache theo kết quả | Method vẫn chạy, nhưng annotation không put kết quả |
| `@Caching` | Các caching operations được áp dụng | Các operations gắn trên method bị bỏ qua ở lời gọi nội bộ |

Một lỗi nguy hiểm là **cập nhật nguồn thành công nhưng cache không bị xóa**: phương thức cập nhật gọi nội bộ một method có `@CacheEvict`, khiến entry cũ vẫn tồn tại. Người dùng sau đó có thể tiếp tục đọc dữ liệu stale.

Hành vi này không phụ thuộc vào việc dùng `ConcurrentMapCacheManager`, Caffeine hay Redis. Thay backend hoặc TTL không làm cho lời gọi nội bộ tự động qua proxy.

## 4. Điều kiện để cache annotation có hiệu lực

Khi annotation không chạy, kiểm tra đồng thời các điều kiện:

1. Ứng dụng đã bật `@EnableCaching` hoặc khai báo caching trong XML chưa?
2. Method thuộc **bean được Spring quản lý**, hay object do code tự `new`?
3. Caller có gọi qua **proxy của bean**, hay đang dùng `this.findByIsbn(isbn)`?
4. Method có thể được proxy advice hay không? Với proxy mode, **public method** là cách dùng được Spring khuyến nghị.
5. Method/class có `private` hoặc `final` ngăn lớp proxy can thiệp không?
6. Cache name/key có khớp và provider có thật sự lưu entry không? `condition`, `unless`, TTL có làm thay đổi kết quả không?

`@EnableCaching` là điều kiện kích hoạt hạ tầng, nhưng **không sửa self-invocation**. Ngược lại, nếu chưa bật caching hoặc dùng đối tượng tạo bằng `new`, cả lời gọi bên ngoài cũng không được cache, nên không thể kết luận lỗi do self-invocation.

### JDK dynamic proxy và CGLIB

Spring AOP có thể tạo **JDK dynamic proxy** khi bean có interface phù hợp, hoặc **CGLIB class-based proxy** (subclass của target) trong tình huống class không có interface, hay khi cấu hình yêu cầu class-based proxy.

Hai loại proxy đều có đặc điểm: **self-invocation trong target bỏ qua advice**. Cấu hình `@EnableCaching(proxyTargetClass = true)` ép class-based proxy nhưng **không làm `this.findByIsbn` đi qua proxy**.

CGLIB còn có giới hạn riêng: class `final` không thể được subclass để tạo proxy; method `final` và `private` không thể được override để advice. Để tránh nhầm lỗi visibility với lỗi self-invocation, ví dụ bên dưới dùng class và method `public` không final.

## 5. Ví dụ Java 17+ chạy được: so sánh hai đường gọi

Ví dụ không cần cơ sở dữ liệu hay Redis. `ConcurrentMapCacheManager` giữ entry trong JVM; số đếm `loads` đại diện số lần method thật sự tải dữ liệu.

**Tệp `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.SelfCallCacheDemo'
}
~~~

**Tệp `src/main/java/demo/SelfCallCacheDemo.java`:**

~~~java
package demo;

import java.util.Objects;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SelfCallCacheDemo {
    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("books");
        }

        @Bean
        public BookService bookService() {
            return new BookService();
        }
    }

    public static class BookService {
        private int loads;

        @Cacheable(cacheNames = "books", key = "#p0")
        public String findBook(String isbn) {
            loads++;
            return "book-" + isbn + "-load-" + loads;
        }

        public String findInside(String isbn) {
            return this.findBook(isbn);
        }

        public int getLoads() {
            return loads;
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            BookService service = context.getBean(BookService.class);
            CacheManager manager = context.getBean(CacheManager.class);
            Cache cache = Objects.requireNonNull(manager.getCache("books"));

            System.out.println("self 1: " + service.findInside("self"));
            System.out.println("self 2: " + service.findInside("self"));

            System.out.println("proxy 1: " + service.findBook("proxy"));
            System.out.println("proxy 2: " + service.findBook("proxy"));

            System.out.println("loads: " + service.getLoads());
            System.out.println("self cached: " + (cache.get("self") != null));
            System.out.println("proxy cached: " + (cache.get("proxy") != null));
        }
    }
}
~~~

Chạy trong thư mục chứa `build.gradle` với JDK 17+ và Gradle tương thích:

~~~bash
gradle run --quiet
~~~

**Stdout dự kiến theo luồng thực thi của chương trình:**

~~~text
self 1: book-self-load-1
self 2: book-self-load-2
proxy 1: book-proxy-load-3
proxy 2: book-proxy-load-3
loads: 3
self cached: false
proxy cached: true
~~~

**Giải thích kết quả:**

- Hai lời gọi `service.findInside("self")` ban đầu đi vào bean proxy, sau đó mỗi lần gọi `this.findBook("self")` trực tiếp trên target. `loads` tăng từ 1 lên 2 và **không có cache entry "self"**.
- Lời gọi `service.findBook("proxy")` từ `main` đi vào method annotated qua proxy. Lần đầu miss, chạy thân method và sinh giá trị kết thúc bằng `load-3`; lần hai hit, trả cùng giá trị, không tăng bộ đếm.
- `cache.get("self") == null` thể hiện không tồn tại entry self; `cache.get("proxy") != null` xác nhận proxy invocation đã tạo entry.
- Hai key khác nhau được cố ý sử dụng để kiểm tra hai đường đi độc lập, không để entry của đường này che kết quả đường kia.

Mã có class được Spring quản lý, `@EnableCaching`, cache name tồn tại, method public và không final. Vì `BookService` không implement interface, Spring có thể tạo class-based proxy. Đầu ra trên được **suy luận từ code và hành vi API**, không khẳng định đã chạy trực tiếp trong môi trường người đọc.

## 6. Cách khắc phục nên ưu tiên: gọi sang bean khác

Thiết kế phổ biến là **đưa method có annotation sang một service riêng**, rồi inject service đó vào lớp điều phối. Khi lớp điều phối gọi một bean khác, lời gọi có thể đi qua proxy của bean đích.

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
class CachedBookReader {
    @Cacheable(cacheNames = "books", key = "#p0")
    public String findBook(String isbn) {
        return "book:" + isbn;
    }
}

@Service
class BookFacade {
    private final CachedBookReader reader;

    BookFacade(CachedBookReader reader) {
        this.reader = reader;
    }

    public String readTwice(String isbn) {
        String first = reader.findBook(isbn);
        String second = reader.findBook(isbn);
        return first + " | " + second;
    }
}
~~~

Đây là **đoạn minh họa hai service**, cần được component-scan và cung cấp `@EnableCaching` cùng một `CacheManager` phù hợp. `BookFacade` nhận proxy `CachedBookReader` do Spring inject; lần gọi thứ hai với cùng key có thể dùng cache. Đối với ví dụ truy cập dữ liệu thật, phần thân `findBook` sẽ đọc repository rồi trả giá trị.

Tách bean làm rõ hai trách nhiệm: **điều phối workflow** và **truy xuất cacheable**. Nó tránh circular dependency và làm cách kiểm tra caching dễ hơn. Không dùng `new CachedBookReader()` trong facade, vì object tự tạo không đi qua Spring proxy.

## 7. Những lựa chọn khác và giới hạn

### Tự inject proxy của chính bean

Về mặt kỹ thuật, có thể để bean nhận một tham chiếu proxy đến chính nó, hoặc tra cứu proxy qua `ObjectProvider`. Sau đó lời gọi được thực hiện qua proxy sẽ được advice. Tuy nhiên, self-injection có thể gây phụ thuộc vòng, làm lifecycle và unit test phức tạp. Không nên dùng làm cách sửa mặc định khi có thể tách service.

### `AopContext.currentProxy()`

Spring AOP có API lấy proxy hiện tại, nhưng cần cấu hình **exposeProxy** và chỉ hoạt động khi đang ở một invocation có proxy phù hợp. Cách này khiến code nghiệp vụ phụ thuộc trực tiếp hạ tầng AOP, khó tái sử dụng và khó test. Spring không khuyến nghị dùng rộng rãi.

### `AdviceMode.ASPECTJ`: weaving thay vì proxy

Khi cần advice chạy cả với self-invocation, Spring hỗ trợ cấu hình AspectJ caching mode:

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching(mode = AdviceMode.ASPECTJ)
class CachingConfig {
}
~~~

Đoạn cấu hình này **chưa đủ** để dự án hoạt động ở AspectJ mode: cần `spring-aspects` trong classpath và **compile-time hoặc load-time weaving** đúng cách. Weaving áp dụng advice lên bytecode, vì vậy không phụ thuộc đường đi qua proxy như chế độ mặc định.

Đừng nhầm `proxyTargetClass = true` với AspectJ. Cấu hình đầu vẫn là proxy mode và vẫn chịu self-invocation; cấu hình sau đổi cơ chế interception và tăng chi phí cấu hình.

## 8. Phân biệt self-invocation với nguyên nhân khác

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Gọi qua bean khác thì cache hit, tự gọi thì không | Self-invocation bypass proxy | So sánh hai đường gọi cùng key ở môi trường tách biệt |
| Mọi lời gọi đều không cache | Thiếu `@EnableCaching`, không phải Spring bean, sai manager | Kiểm tra cấu hình và bean thực tế |
| Method annotate không được advice | Method không public, final/private hoặc ngoài khả năng proxy | Kiểm tra visibility và proxy type |
| Bật CGLIB nhưng tự gọi vẫn không cache | CGLIB vẫn là proxy | Tách bean hoặc dùng AspectJ nếu cần |
| Dữ liệu cũ sau update | `@CacheEvict` bị tự gọi bỏ qua; hoặc sai key | Kiểm tra đường gọi updater và cache entry |
| Method chạy lặp dù gọi qua proxy | Cache key khác, `condition` false, `unless` veto, TTL hoặc no-op | Kiểm tra key, điều kiện và provider |
| Annotation không hoạt động trong `@PostConstruct` | Proxy chưa được khởi tạo đầy đủ | Không trông chờ cache advice trong initialization code |

Một công cụ hỗ trợ là `org.springframework.aop.support.AopUtils.isAopProxy(bean)`. Nếu true, đối tượng có Spring AOP proxy; nhưng vẫn phải xem **method được gọi qua proxy hay gọi nội bộ**. Có proxy không có nghĩa mọi invocation đều được advice.

## 9. Các bước debug thực tế

1. Xác nhận có `@EnableCaching` trong application context chứa service.
2. Tìm nơi tạo object. Nếu dùng `new`, đưa object về Spring-managed bean.
3. Xác định caller: bean khác gọi qua proxy, hay cùng class gọi `this.findBook(isbn)`?
4. Với proxy mode, ưu tiên public method, không final và class có thể proxy.
5. Kiểm tra cache manager, `cacheNames`, key SpEL, điều kiện và TTL. Tránh kết luận sai về self-invocation khi key thay đổi.
6. Thêm bộ đếm lời gọi nguồn và so hai đường gọi như trong phần 5.
7. Nếu còn dữ liệu stale sau update, kiểm tra riêng `@CacheEvict` có được gọi qua proxy và xóa đúng key hay không.

Hành vi chẩn đoán đặc trưng của self-invocation là: **cùng phương thức annotated có cache hit khi gọi bên ngoài qua proxy, nhưng không cache khi được gọi trực tiếp trên target**.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** `OrderService.process(id)` gọi `this.loadOrder(id)` trong cùng class; `loadOrder` có `@Cacheable`. Proxy mode mặc định có cache `loadOrder` không?

**Đáp án:** Không cho lời gọi nội bộ đó, vì target gọi trực tiếp method mà không qua cache interceptor.

**Câu 2.** Bỏ `this.` khỏi lời gọi có thay đổi không?

**Đáp án:** Không. `loadOrder(id)` vẫn là self-invocation ngầm.

**Câu 3.** Bật `@EnableCaching(proxyTargetClass = true)` có sửa được không?

**Đáp án:** Không. Chuyển sang CGLIB chỉ đổi kiểu proxy, không chuyển lời gọi nội bộ sang proxy.

**Câu 4.** Vì sao một method `@CacheEvict` được tự gọi có thể gây dữ liệu cũ?

**Đáp án:** Logic sửa nguồn vẫn chạy nhưng eviction advice không chạy, khiến bản cache cũ có thể còn.

**Câu 5.** Giải pháp thường được ưu tiên?

**Đáp án:** Tách method cacheable sang bean riêng, inject bean đó để caller đi qua proxy của bean được advice.

## 11. Ghi nhớ và tài liệu tham khảo

- Spring Cache mặc định dùng **proxy mode**: chỉ lời gọi đi qua proxy mới được cache interceptor xử lý.
- `this.findBook(isbn)` hay `findBook(isbn)` trong cùng target là **self-invocation**, bỏ qua proxy.
- Không chỉ `@Cacheable` mà `@CacheEvict`, `@CachePut` cũng chịu ảnh hưởng khi gọi nội bộ.
- Đổi JDK proxy sang CGLIB **không** sửa self-invocation.
- Ưu tiên **tách bean và inject qua Spring**; AspectJ là lựa chọn khi thật sự cần interception bên trong object và có weaving đầy đủ.
- Khi tìm nguyên nhân, phân biệt self-invocation với thiếu caching configuration, sai key, private/final method và cache provider.

**Tài liệu chính thức:**

- [Spring Framework 6.2 — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — @EnableCaching](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/annotation/EnableCaching.html)
