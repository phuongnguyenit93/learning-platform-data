# `CachingConfigurer`: cấu hình CacheManager, CacheResolver, KeyGenerator và CacheErrorHandler

## 1. `CachingConfigurer` giải quyết vấn đề gì?

Spring Cache cung cấp các annotation như `@Cacheable`, `@CachePut` và `@CacheEvict`. Annotation mô tả **khi nào** cần đọc/ghi/xóa cache, nhưng ứng dụng còn phải xác định **cache nằm ở đâu**, **cache nào được chọn**, **key nào dùng để tra cứu** và **xử lý lỗi backend cache ra sao**.

Giao diện `org.springframework.cache.annotation.CachingConfigurer` là nơi cấu hình mặc định cho cơ chế xử lý annotation cache khi bật `@EnableCaching`. Một lớp `@Configuration` có thể `implements CachingConfigurer` và ghi đè bốn phương thức:

| Phương thức của `CachingConfigurer` | Đối tượng trả về | Trách nhiệm |
| --- | --- | --- |
| `cacheManager()` | `CacheManager` | Quản lý/trả về các vùng cache theo tên, làm nền cho resolver mặc định. |
| `cacheResolver()` | `CacheResolver` | Chọn một hoặc nhiều đối tượng `Cache` cho **mỗi thao tác** dựa trên annotation và ngữ cảnh lời gọi. |
| `keyGenerator()` | `KeyGenerator` | Tạo key từ đối tượng đích, phương thức và các đối số khi annotation không có biểu thức `key` riêng. |
| `errorHandler()` | `CacheErrorHandler` | Xử lý ngoại lệ từ thao tác `Cache.get`, `put`, `evict` hoặc `clear`. |

Trong Spring Framework 6.x, các phương thức trên có triển khai mặc định và có thể chỉ ghi đè những phần cần tùy biến. Khi không tự cung cấp, cách xử lý thông thường là `SimpleCacheResolver` dựa vào manager, `SimpleKeyGenerator` và `SimpleCacheErrorHandler` (ném lại lỗi cache).

**Quan hệ giữa các thành phần:**

~~~text
Lời gọi qua Spring proxy
          |
          v
@Cacheable / @CachePut / @CacheEvict
          |
          +--> CacheResolver --> chọn Cache(s)
          |         |
          |         +--> có thể lấy Cache từ CacheManager
          |
          +--> KeyGenerator --> sinh key (nếu không có key SpEL)
          |
          v
Đọc/ghi/xóa trong Cache
          |
          +--> nếu cache backend ném RuntimeException
                    |
                    v
                CacheErrorHandler
                (ném tiếp hoặc xử lý theo chính sách)
~~~

`CacheManager`, `CacheResolver`, `KeyGenerator` và `CacheErrorHandler` giải quyết **bốn trách nhiệm riêng**. Thêm `CachingConfigurer` không làm caching hoạt động nếu chưa bật xử lý annotation (`@EnableCaching` hoặc cấu hình tương đương) và nếu lời gọi không đi qua cơ chế interception phù hợp.

## 2. `cacheManager()`: khai báo nơi chứa các cache

`CacheManager` là giao diện có các thao tác quan trọng như `getCache(String name)` và `getCacheNames()`. Nó quản lý đối tượng `Cache`, chứ không trực tiếp quyết định key cho một lời gọi.

Ví dụ cơ bản:

~~~java
@Configuration
@EnableCaching
class CacheConfig implements CachingConfigurer {
    @Bean
    @Override
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books", "authors");
    }
}
~~~

Đây là **trích đoạn cấu hình**: khi đưa vào file Java cần import `Configuration`, `EnableCaching`, `CachingConfigurer`, `Bean`, `CacheManager` và `ConcurrentMapCacheManager` từ Spring. Chương trình đầy đủ nằm ở phần 6.

- `books` và `authors` là **tên vùng cache**, không phải key của từng phần tử.
- `ConcurrentMapCacheManager` giữ cache trong bộ nhớ tiến trình, tiện cho ví dụ/ứng dụng đơn giản. Nó không tự cung cấp TTL hoặc đồng bộ nhiều instance.
- Trong ứng dụng thật, có thể dùng manager của Caffeine, Redis hoặc nhà cung cấp khác để có TTL, giới hạn dung lượng, khả năng phân tán và các chính sách riêng.
- `@Bean` trên `cacheManager()` là quan trọng để Spring quản lý bean và vòng đời của manager. Chỉ tạo object tùy tiện rồi để framework không quản lý sẽ gây cấu hình khó kiểm chứng.

Nếu **chỉ** cung cấp `cacheManager()`, Spring có thể dựng resolver mặc định dựa trên manager này. Annotation `@Cacheable(cacheNames = "books")` sau đó được resolve thành cache tên `books` từ manager.

`CacheManager` **không tự chọn key** và không thay thế `KeyGenerator`: hai việc khác nhau.

## 3. `cacheResolver()`: chọn cache theo thao tác và ngữ cảnh

`CacheResolver` quyết định những `Cache` nào phải dùng cho một `@Cacheable`, `@CachePut` hoặc `@CacheEvict`. Phương thức chính của giao diện:

~~~java
Collection<? extends Cache> resolveCaches(
        CacheOperationInvocationContext<?> context);
~~~

Đây là **chữ ký API minh họa**, không phải một chương trình riêng. `context` cung cấp metadata của thao tác cache, method, target và arguments. `SimpleCacheResolver` sử dụng `CacheManager` và tên cache của annotation để trả các đối tượng `Cache`.

**Quy tắc ưu tiên quan trọng:** Nếu cùng một `CachingConfigurer` cung cấp cả `cacheManager()` và `cacheResolver()`, resolver được chọn làm **cơ chế resolve mặc định** cho annotation; manager không được tự động dùng để tạo một resolver thứ hai. Tất nhiên, resolver tùy chỉnh có thể **chủ động sử dụng manager** làm nguồn cache.

Một ví dụ resolver đơn giản:

~~~java
@Bean
@Override
public CacheResolver cacheResolver() {
    return new SimpleCacheResolver(cacheManager());
}
~~~

Trích đoạn trên giả định nằm trong lớp `@Configuration` đã cung cấp `cacheManager()` dưới dạng `@Bean`. Với cấu hình `@Configuration` mặc định (bean-method proxying được bật), lời gọi `cacheManager()` trong cùng class trả về bean do Spring quản lý. Nếu chủ động dùng `proxyBeanMethods = false`, không dựa vào cơ chế gọi bean method này; hãy truyền bean theo cách rõ ràng.

Khi nào cần resolver riêng?

- Nhiều backend cache: phân tuyến theo tenant, vùng địa lý, loại dữ liệu hoặc yêu cầu bảo mật.
- Tên cache cần quyết định tại runtime dựa trên metadata của lời gọi.
- Một thao tác cần truy cập tập hợp cache được tính động, thay vì cố định từ `cacheNames`.

Nếu chỉ một manager và tên cache nằm sẵn trong annotation, **`SimpleCacheResolver` thường đã đủ**. Không tạo lớp resolver tùy chỉnh khi không có quy tắc lựa chọn cụ thể. Resolver phải trả những cache phù hợp, có thể không có cache hoặc sai tên là lỗi cấu hình đối với những thao tác cần cache.

### 3.1. Tránh nhầm `cacheResolver` và `cacheManager` ở annotation

Các thuộc tính trên **một thao tác** có ràng buộc:

~~~java
@Cacheable(cacheNames = "books", cacheManager = "fastManager")
public Book find(String id) { /* ... */ }
~~~

hoặc:

~~~java
@Cacheable(cacheNames = "books", cacheResolver = "tenantCacheResolver")
public Book find(String id) { /* ... */ }
~~~

Hai trích đoạn độc lập trên dùng để minh họa lựa chọn cấu hình. Không khai báo **đồng thời** `cacheManager="fastManager"` và `cacheResolver="tenantCacheResolver"` trên cùng một thao tác: đây là hai cách chọn cache loại trừ nhau và Spring báo lỗi cấu hình.

Độ ưu tiên thường được hiểu như sau: cấu hình **trên method** được ưu tiên so với `@CacheConfig` **trên class**, và cấu hình trên class được ưu tiên so với các mặc định **toàn cục** từ `CachingConfigurer`. Điều này cho phép dùng mặc định chung nhưng có ngoại lệ có chủ đích.

## 4. `keyGenerator()`: tạo khóa nhất quán

Sau khi xác định cache, Spring cần một key để đọc hoặc lưu từng entry. Khi annotation không đặt `key = "..."` hoặc `keyGenerator = "..."` riêng, framework dùng bộ sinh key mặc định.

`KeyGenerator` có chữ ký:

~~~java
Object generate(Object target, Method method, Object... params);
~~~

`SimpleKeyGenerator` thường tạo:

| Đầu vào | Key mặc định |
| --- | --- |
| Không đối số | `SimpleKey.EMPTY` |
| Một đối số khác `null` và không phải mảng | Chính đối số đó |
| Nhiều đối số, một đối số `null` hoặc đối số dạng mảng | Một đối tượng `SimpleKey` chứa tham số |

Những quy tắc trên áp dụng ở tầng Spring và có thể được backend lưu dưới dạng key/serialization khác. Key phải có `equals`/`hashCode` phù hợp với cache đang dùng và nên ổn định giữa các lần gọi tương đương.

Khi cần phân biệt hai method có cùng tham số nhưng dùng chung vùng cache, có thể khai báo generator tùy chỉnh:

~~~java
@Bean
@Override
public KeyGenerator keyGenerator() {
    return (target, method, params) -> {
        String suffix = Arrays.stream(params)
                .map(String::valueOf)
                .collect(Collectors.joining(":"));
        return method.getName() + ":" + suffix;
    };
}
~~~

Đây là **trích đoạn trong `CachingConfigurer`**, cần import `Arrays` và `Collectors` của Java. Ví dụ này cho `find("B42")` key `"find:B42"`, nhưng **không thích hợp nguyên xi cho dữ liệu tổng quát**: overload, tham số chứa dấu `:`, đối tượng có `toString()` thay đổi, dữ liệu nhạy cảm và đổi tên method có thể gây xung đột hoặc đổi key. Với hệ thống thật, xác định rõ contract key, kiểm thử va chạm và cách serialize.

**Lưu ý:** `keyGenerator()` là **mặc định**, nên nếu annotation viết `key="#p0"`, biểu thức SpEL đó được ưu tiên. Không được khai báo cả `key` và `keyGenerator` trên cùng một annotation cache, vì hai cơ chế tạo key là các lựa chọn loại trừ nhau.

Khi `@CacheEvict` dùng generator tùy chỉnh, phải chắc chắn key xóa **giống key mà phương thức đọc đã dùng**. Generator dựa trên `method.getName()` có thể làm `find("B42")` tạo `find:B42`, trong khi `update("B42")` xóa `update:B42` và để lại dữ liệu cũ. Cần dùng key SpEL thống nhất hoặc generator có quy tắc riêng cho các thao tác cùng thực thể.

## 5. `errorHandler()`: khi cache backend phát sinh lỗi

`CacheErrorHandler` nhận ngoại lệ từ **thao tác trên cache** (lỗi đọc/ghi/xóa/xóa toàn bộ cache) và cho phép chọn cách phản ứng. Bốn callback là:

| Callback | Khi được gọi |
| --- | --- |
| `handleCacheGetError(RuntimeException ex, Cache cache, Object key)` | Lỗi đọc key. |
| `handleCachePutError(RuntimeException ex, Cache cache, Object key, Object value)` | Lỗi ghi key/value. |
| `handleCacheEvictError(RuntimeException ex, Cache cache, Object key)` | Lỗi xóa key. |
| `handleCacheClearError(RuntimeException ex, Cache cache)` | Lỗi xóa toàn bộ cache. |

Với `SimpleCacheErrorHandler` mặc định, ngoại lệ được **ném lại** cho caller; lỗi Redis/cache backend có thể làm cả lời gọi nghiệp vụ thất bại:

~~~java
@Bean
@Override
public CacheErrorHandler errorHandler() {
    return new SimpleCacheErrorHandler();
}
~~~

Đây là hành vi *fail-fast* phù hợp khi tính nhất quán quan trọng hoặc ứng dụng cần biết cache backend đang lỗi.

Một lựa chọn khác là **bỏ qua lỗi đọc cache** để tiếp tục lấy dữ liệu gốc. Ví dụ sau chỉ là đoạn thay thế cho nội dung phương thức `errorHandler()` trong lớp cấu hình:

~~~java
@Bean
@Override
public CacheErrorHandler errorHandler() {
    return new SimpleCacheErrorHandler() {
        @Override
        public void handleCacheGetError(RuntimeException ex,
                                        Cache cache, Object key) {
            System.err.println("Cache GET failed: "
                    + cache.getName() + ", key=" + key);
            // Không ném lại: Spring có thể xem như cache miss.
        }
    };
}
~~~

Khi handler cho phép tiếp tục sau lỗi `get`, thân phương thức có thể chạy để lấy kết quả từ nguồn. Tuy nhiên, lỗi `put` vẫn sẽ được ném lại bởi các phương thức còn lại của `SimpleCacheErrorHandler` nếu chúng chưa bị ghi đè. Bỏ qua lỗi `evict`/`clear` nguy hiểm hơn vì **entry cũ có thể tiếp tục tồn tại**; tuyệt đối không mặc định nuốt tất cả exception cho tiện.

`CacheErrorHandler` **không phải** cơ chế xử lý exception của thân phương thức nghiệp vụ, cũng không phải giải pháp cho key SpEL sai, tên cache không resolve được hoặc transaction rollback. Tình huống cụ thể cần quan sát lỗi, độ trễ, freshness và nhu cầu fallback. Với hệ thống phân tán, chính sách "cache lỗi nhưng ứng dụng vẫn chạy" phải được kiểm thử và có giám sát.

## 6. Ví dụ đầy đủ Spring Boot 3.3 / Java 17: cấu hình cả bốn hook

Ta dùng `ConcurrentMapCacheManager` để không phụ thuộc Redis hay Docker. Bài demo cố tình cung cấp cả manager lẫn resolver: **resolver là entry point** cho việc chọn cache và bản thân nó dùng manager đã tạo. Generator in key để dễ thấy, còn handler dùng chế độ mặc định ném lỗi.

Tạo dự án Gradle với `build.gradle`:

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

Tạo tệp `src/main/java/demo/CachingConfigurerDemoApplication.java`:

~~~java
package demo;

import java.util.Arrays;
import java.util.stream.Collectors;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CachingConfigurer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.CacheErrorHandler;
import org.springframework.cache.interceptor.CacheResolver;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.cache.interceptor.SimpleCacheErrorHandler;
import org.springframework.cache.interceptor.SimpleCacheResolver;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CachingConfigurerDemoApplication implements CachingConfigurer {
    public static void main(String[] args) {
        SpringApplication.run(CachingConfigurerDemoApplication.class, args);
    }

    @Bean
    @Override
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    @Override
    public CacheResolver cacheResolver() {
        CacheResolver delegate = new SimpleCacheResolver(cacheManager());
        return context -> {
            System.out.println("RESOLVE "
                    + context.getOperation().getCacheNames());
            return delegate.resolveCaches(context);
        };
    }

    @Bean
    @Override
    public KeyGenerator keyGenerator() {
        return (target, method, params) -> {
            String args = Arrays.stream(params)
                    .map(String::valueOf)
                    .collect(Collectors.joining(":"));
            String key = method.getName() + ":" + args;
            System.out.println("KEY " + key);
            return key;
        };
    }

    @Bean
    @Override
    public CacheErrorHandler errorHandler() {
        return new SimpleCacheErrorHandler();
    }

    @Bean
    BookService bookService() {
        return new BookService();
    }

    @Bean
    CommandLineRunner demo(BookService service, CacheManager manager) {
        return args -> {
            System.out.println("first = " + service.find("B42"));
            System.out.println("second = " + service.find("B42"));
            System.out.println("third = " + service.find("B99"));

            Cache books = manager.getCache("books");
            if (books == null) {
                throw new IllegalStateException("Missing books cache");
            }
            System.out.println("manual = "
                    + books.get("find:B42", String.class));
        };
    }
}

class BookService {
    @Cacheable(cacheNames = "books")
    public String find(String id) {
        System.out.println("LOAD " + id);
        return "Book(" + id + ")";
    }
}
~~~

Chạy từ thư mục dự án bằng `./gradlew bootRun` (Windows: `gradlew.bat bootRun`) nếu có Gradle Wrapper, hoặc `gradle bootRun` với Gradle tương thích đã cài.

Ngoài log khởi động của Spring Boot, những dòng **do demo chủ động in ra** có thứ tự:

~~~text
RESOLVE [books]
KEY find:B42
LOAD B42
first = Book(B42)
RESOLVE [books]
KEY find:B42
second = Book(B42)
RESOLVE [books]
KEY find:B99
LOAD B99
third = Book(B99)
manual = Book(B42)
~~~

Lý giải:

1. `cacheManager()` tạo `ConcurrentMapCacheManager` có cache `books`.
2. `cacheResolver()` tạo resolver gọi `SimpleCacheResolver`, in `RESOLVE [books]` ở mỗi thao tác `@Cacheable` rồi chọn cache thông qua manager.
3. `keyGenerator()` tạo key `find:B42` hay `find:B99` từ tên method và đối số. Vì annotation `@Cacheable` không đặt `key` riêng, generator toàn cục được dùng.
4. Lượt `B42` đầu tiên miss nên method in `LOAD B42`; lượt `B42` thứ hai hit, không có dòng `LOAD`. Lượt `B99` là key khác nên miss.
5. `errorHandler()` thiết lập `SimpleCacheErrorHandler`. Demo không cố tình gây lỗi backend, vì thế không có callback lỗi nào được kích hoạt.
6. `books.get("find:B42", String.class)` đọc lại entry theo key do generator tạo; minh chứng resolver và generator cùng tác động đến một cache cụ thể.

Ví dụ dùng `@SpringBootApplication` cũng là `@Configuration` mặc định có proxy cho các `@Bean` method. Vì thế `cacheResolver()` gọi `cacheManager()` để lấy bean singleton đã đăng ký. Nếu cấu hình theo kiểu `proxyBeanMethods=false`, nên truyền `CacheManager` qua một bean/provider theo cơ chế rõ ràng thay vì giả định lời gọi nội bộ được Spring chặn.

## 7. Cấu hình tối thiểu và thứ tự ưu tiên

**Chỉ cần manager:** Khi các cache được chọn bằng tên ghi trong annotation, chỉ việc định nghĩa `@Bean CacheManager` và bật `@EnableCaching` là đủ; không bắt buộc implement cả bốn hook. `CachingConfigurer` hữu ích khi muốn đặt mặc định toàn cục tường minh.

**Resolver tùy biến:** Khi override `cacheResolver()`, nó trở thành lựa chọn mặc định để tìm cache. Nếu trong cùng configurer cũng override `cacheManager()`, manager không tự động quyết định quá trình resolve; resolver có thể chủ động gọi manager.

**Generator tùy biến:** Chỉ được dùng nếu thao tác không cung cấp biểu thức `key` hoặc generator riêng. `key` và `keyGenerator` trên cùng annotation loại trừ nhau.

**Error handler:** Xác định chính sách lỗi cache trên tầng interceptor. `SimpleCacheErrorHandler` ném lại lỗi; một handler tùy biến có thể log, fallback hoặc cảnh báo, nhưng cần xác định rõ thao tác nào có thể được bỏ qua.

| Cấp cấu hình | Ví dụ | Vai trò |
| --- | --- | --- |
| Toàn cục | `CachingConfigurer` | Mặc định cho các thao tác không chỉ định riêng. |
| Lớp | `@CacheConfig(cacheNames=..., keyGenerator=...)` | Chia sẻ cấu hình cho các method trong cùng class. |
| Phương thức | `@Cacheable(key=..., cacheResolver=...)` | Tùy chỉnh thao tác cụ thể, ưu tiên hơn cấu hình lớp/toàn cục. |

`@CacheConfig` **không tự bật cache**: method vẫn cần annotation tương ứng như `@Cacheable` hoặc `@CacheEvict`.

## 8. Các lỗi phổ biến khi dùng `CachingConfigurer`

| Triệu chứng / nhầm lẫn | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Cấu hình `CacheManager` nhưng resolver tùy chỉnh chọn backend khác. | Khi cung cấp cả hai, `CacheResolver` quyết định cache của thao tác. | Kiểm tra `resolveCaches`, đối tượng manager mà resolver dùng và các annotation override. |
| `keyGenerator()` không được gọi. | Annotation có `key` SpEL riêng hoặc `keyGenerator` được chỉ định trên method/class. | Kiểm tra thứ tự ưu tiên; tránh đặt hai cách tạo key trên cùng method. |
| Cache hit không xảy ra ở lần gọi thứ hai. | Key khác nhau, cache bị evict, backend không lưu, annotation không được intercept. | Log key, tên cache, số lần `LOAD`; kiểm tra proxy và bean. |
| Đặt đồng thời `cacheManager` và `cacheResolver` trong annotation. | Hai lựa chọn này loại trừ nhau. | Chọn một thuộc tính. |
| Sai key khi evict. | Generator ghép tên method, nhưng method ghi có tên khác method đọc. | Thống nhất key giữa `@Cacheable` và `@CacheEvict`. |
| Xóa cache thất bại nhưng handler nuốt exception. | Lỗi `evict/clear` bị bỏ qua. | Với dữ liệu nhạy về độ mới, ưu tiên phát hiện và xử lý lỗi invalidation tường minh. |
| Lỗi của thân method bị tưởng là lỗi cache. | `CacheErrorHandler` chỉ xử lý lỗi thao tác cache. | Xử lý lỗi nghiệp vụ tại tầng phù hợp, không dựa vào cache handler. |
| Injection vào `CachingConfigurer` gây vòng phụ thuộc/khởi tạo sớm. | Infrastructure của caching có thể khởi tạo configurer sớm. | Tránh field injection phụ thuộc bean nặng; cân nhắc lazy `ObjectProvider`, bean method hoặc tách cấu hình. |
| Self-invocation `this.find(...)` không cache. | Chế độ proxy mặc định không intercept lời gọi nội bộ. | Gọi từ bean khác qua proxy Spring, hoặc lựa chọn cơ chế interception thích hợp. |
| Mang cache local lên nhiều instance rồi kỳ vọng trạng thái thống nhất. | `ConcurrentMapCacheManager` chỉ giữ trạng thái trong từng JVM. | Dùng backend chia sẻ/phối hợp invalidation tùy yêu cầu nhất quán. |

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Hai phương thức `cacheManager()` và `cacheResolver()` cùng được override trong một `CachingConfigurer`. Spring dùng thành phần nào để resolve cache mặc định?

**Đáp án:** `CacheResolver`; resolver có thể chủ động dùng `CacheManager` đã khai báo, nhưng manager không tạo một resolver mặc định thay thế resolver tùy chỉnh.

**Câu 2.** `@Cacheable(cacheNames = "books", key = "#p0")` có sử dụng `keyGenerator()` toàn cục không?

**Đáp án:** Không. `key` SpEL đã xác định cách tạo khóa cho thao tác đó.

**Câu 3.** Có nên luôn bỏ qua lỗi `Cache.evict` để ứng dụng tiếp tục chạy không?

**Đáp án:** Không. Nếu eviction thất bại mà vẫn bị bỏ qua, cache có thể trả dữ liệu cũ. Quyết định này cần dựa trên độ mới dữ liệu và cơ chế khôi phục.

**Câu 4.** `CacheManager` khác `CacheResolver` thế nào?

**Đáp án:** Manager biết/trả cache theo tên; resolver chọn cache nào phục vụ một thao tác, có thể dựa vào method, args và nhiều manager.

**Câu 5.** Vì sao key generator dựa trên tên method có thể khiến `@CacheEvict` xóa sai entry?

**Đáp án:** Method đọc và method ghi thường khác tên. Nếu key gắn tên method thì hai thao tác tạo hai key khác nhau dù cùng một đối tượng nghiệp vụ.

**Ghi nhớ:** `CachingConfigurer` là điểm cấu hình mặc định cho annotation cache. `CacheManager` cung cấp cache, `CacheResolver` chọn cache, `KeyGenerator` chọn key, `CacheErrorHandler` chọn cách phản ứng khi cache thất bại. Thiết kế đúng cả bốn sẽ giúp caching có thể quan sát, nhất quán và phù hợp với nhu cầu ứng dụng.

Tài liệu tham khảo:

- [Spring Framework 6.1 — `CachingConfigurer` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/cache/annotation/CachingConfigurer.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
