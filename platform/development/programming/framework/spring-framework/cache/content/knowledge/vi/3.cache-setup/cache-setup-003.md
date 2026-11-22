# Bật xử lý annotation bằng @EnableCaching

> **Chủ đề:** Spring Framework Cache Abstraction · **Nhóm:** Thiết lập. Mục tiêu là hiểu chính xác `@EnableCaching` kích hoạt gì, điều kiện để caching thực sự xảy ra, giới hạn của proxy và cách kiểm chứng qua mã Java chạy được.

## 1. `@EnableCaching` là gì và vì sao cần dùng?

`@Cacheable`, `@CachePut`, `@CacheEvict` là **annotation khai báo** cách ứng dụng muốn tương tác với cache. Một phương thức có `@Cacheable` nhưng thiếu hạ tầng xử lý annotation vẫn chạy như phương thức Java thông thường: Spring không tự đọc cache hay bỏ qua lời gọi chỉ vì annotation xuất hiện trong source code.

`@EnableCaching` trong `org.springframework.cache.annotation` là annotation cấu hình dùng để **bật xử lý caching annotation** cho các bean thuộc Spring `ApplicationContext` tương ứng:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {
    // Cung cấp CacheManager hoặc CacheResolver thích hợp.
}
~~~

Đây là đoạn minh họa cú pháp, cần Spring configuration hoàn chỉnh để chạy. Sau khi kích hoạt, Spring cấu hình hạ tầng nhận diện các cache operations và áp dụng chúng lên lời gọi method phù hợp, thông thường bằng **Spring AOP proxy**.

Phân biệt rõ:

| Thành phần | Vai trò |
| --- | --- |
| `@EnableCaching` | Kích hoạt annotation-driven caching trong context |
| `@Cacheable` | Tìm entry theo key trước; nếu hit thì trả kết quả cache, nếu miss thì chạy method rồi lưu kết quả |
| `@CachePut` | Luôn thực thi method rồi cập nhật kết quả vào cache |
| `@CacheEvict` | Loại bỏ entry hoặc toàn bộ entry của vùng cache đã chỉ định |
| `@Caching` | Gom nhiều cache operation trên một method |
| `@CacheConfig` | Cung cấp giá trị mặc định cấp lớp như cache name; bản thân nó không thực hiện caching |
| `CacheManager` / `CacheResolver` | Xác định các cache region mà operation sử dụng |
| `Cache` | Đọc, ghi và xóa các entry theo key trong một region cụ thể |

**`@EnableCaching` không phải là cache backend.** Nó không tự đặt TTL, giới hạn dung lượng, serializer, eviction policy hay cơ chế chia sẻ dữ liệu giữa nhiều JVM. Cấu hình các chính sách này nằm ở `CacheManager` và provider (ConcurrentMap, Caffeine, Redis, JCache...).

## 2. Điều kiện để annotation có hiệu lực

Một ứng dụng cần đủ các thành phần:

1. **Dependency Spring:** với ứng dụng Spring Framework thuần, ví dụ dùng `spring-context`; Spring Boot thường dùng `spring-boot-starter-cache`.
2. **Cấu hình được nạp:** `@EnableCaching` đặt trên lớp `@Configuration` được Spring đăng ký/import trong context nơi service được quản lý.
3. **Cache backend:** có `CacheManager` hoặc `CacheResolver` phù hợp. Spring Framework thuần cần người phát triển cấu hình; Spring Boot có thể tự cấu hình provider tùy classpath và properties khi caching được bật.
4. **Method được khai báo cache operation:** ví dụ `@Cacheable(cacheNames="books")` trên phương thức `public` của Spring-managed bean.
5. **Đường gọi được intercept:** proxy mode mặc định chỉ nhận lời gọi qua Spring proxy. Một lời gọi nội bộ `this.method()` không đi qua proxy.

Một cấu hình tối thiểu trong Spring Framework thuần:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books", "authors");
    }
}
~~~

Các import tương ứng là `org.springframework.context.annotation.Configuration`, `org.springframework.context.annotation.Bean`, `org.springframework.cache.annotation.EnableCaching`, `org.springframework.cache.CacheManager`, `org.springframework.cache.concurrent.ConcurrentMapCacheManager`.

Ở ví dụ này manager có danh sách tên tĩnh `books` và `authors`. Tên `book` (khác `books`) sẽ không được tự tạo trong cấu hình đó. `ConcurrentMapCacheManager` hữu ích cho ví dụ và kiểm thử; nó không tự cung cấp các chính sách TTL và giới hạn dung lượng như cache provider chuyên dụng.

Không cần gắn `@EnableCaching` lên từng service, cũng không cần tự gọi `CacheManager.getCache(...)` trong method `@Cacheable`; interceptor và resolver làm việc đó.

## 3. Trước và sau khi bật caching

Giả sử có method thuộc Spring bean:

~~~java
// Mảnh minh họa, Book và repository thuộc ứng dụng thực tế.
@Cacheable(cacheNames = "books", key = "#p0")
public Book findByIsbn(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

**Khi chưa bật `@EnableCaching`:** hai lần gọi `findByIsbn("123")` đều thực thi thân method, vì annotation đơn thuần không tác động đến Java invocation.

**Khi đã bật `@EnableCaching` và caller gọi qua proxy:**

~~~text
Caller
  |
  v
Spring proxy / CacheInterceptor
  |
  +-- đọc metadata @Cacheable(cacheNames="books", key="#p0")
  |
  +-- CacheResolver/CacheManager xác định vùng "books"
  |
  +-- tính key từ tham số thứ nhất ("123")
          |
          +-- Cache HIT  -> trả kết quả đã lưu; không gọi thân method
          |
          +-- Cache MISS -> gọi thân method
                                  |
                                  +-- lưu kết quả vào cache
                                  +-- trả kết quả về caller
~~~

Trong luồng trên, `cacheNames="books"` chỉ **tên vùng cache**, còn `key="#p0"` xác định **entry**. Một vùng chứa nhiều entry khác nhau. `@CachePut` và `@CacheEvict` sử dụng hạ tầng đã bật nhưng có quy tắc thực thi riêng, không có cơ chế “cache hit thì bỏ qua method” giống `@Cacheable`.

Việc tạo bean, cấu hình manager và tạo proxy xảy ra khi Spring xây dựng context; việc tính key, kiểm tra hit/miss và thao tác provider diễn ra khi method được gọi.

## 4. Ví dụ Java 17+ chạy được: so sánh OFF và ON

Ta sẽ tạo **hai Spring context độc lập**. Cả hai có cùng `CacheManager` và bean `Catalog`; context `ON` import thêm cấu hình `@EnableCaching`. Ví dụ cũng quan sát self-invocation ở proxy mode.

Cấu trúc:

~~~text
enable-caching-demo/
├── build.gradle
└── src/main/java/demo/EnableCachingDemo.java
~~~

**`build.gradle`**:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.EnableCachingDemo'
}
~~~

**`src/main/java/demo/EnableCachingDemo.java`**:

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

public class EnableCachingDemo {

    public static void main(String[] args) {
        demonstrate("OFF", BaseConfig.class);
        demonstrate("ON", EnabledConfig.class);
    }

    private static void demonstrate(String label, Class<?> config) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(config)) {

            Catalog catalog = context.getBean(Catalog.class);
            System.out.println(label + " first=" + catalog.find("A"));
            System.out.println(label + " second=" + catalog.find("A"));
            System.out.println(label + " calls=" + catalog.calls());

            if ("ON".equals(label)) {
                System.out.println("ON self1=" + catalog.selfFind("B"));
                System.out.println("ON self2=" + catalog.selfFind("B"));
                System.out.println("ON calls=" + catalog.calls());
            }
        }
    }

    @Configuration
    public static class BaseConfig {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("books");
        }

        @Bean
        public Catalog catalog() {
            return new Catalog();
        }
    }

    @Configuration
    @EnableCaching
    @Import(BaseConfig.class)
    public static class EnabledConfig {
    }

    public static class Catalog {
        private int databaseCalls;

        @Cacheable(cacheNames = "books", key = "#p0")
        public String find(String isbn) {
            databaseCalls++;
            return "database:" + isbn + ":" + databaseCalls;
        }

        public String selfFind(String isbn) {
            // Lời gọi nội bộ: không đi qua caching proxy.
            return find(isbn);
        }

        public int calls() {
            return databaseCalls;
        }
    }
}
~~~

Đứng trong thư mục dự án với Gradle và JDK 17+:

~~~bash
gradle run --quiet
~~~

**Stdout của chương trình**:

~~~text
OFF first=database:A:1
OFF second=database:A:2
OFF calls=2
ON first=database:A:1
ON second=database:A:1
ON calls=1
ON self1=database:B:2
ON self2=database:B:3
ON calls=3
~~~

Giải thích:

- `OFF`: Spring có `CacheManager` nhưng không kích hoạt caching annotations. Hai lần gọi cùng ISBN đều chạy method; bộ đếm là 2.
- `ON`: bean `Catalog` được Spring bọc bằng proxy; lời gọi `find("A")` từ `demonstrate` đi qua proxy. Lần đầu cache miss, lần sau hit; bộ đếm vẫn là 1.
- `ON self1/self2`: `selfFind("B")` chạy trên bean, nhưng lời gọi `find` từ bên trong target không đi qua proxy. Cả hai lần đều thực thi thân method, bộ đếm tăng từ 1 thành 3.
- Các context `OFF` và `ON` độc lập, nên bộ đếm và cache region không chia sẻ state. Cấu hình `books` cũng là cache region, không phải key `A` hay `B`.

Vì `Catalog` không khai báo interface, Spring dùng proxy dựa trên class. Đây là điều có thể xảy ra **ngay cả khi `proxyTargetClass=false`**, vì lựa chọn JDK proxy phụ thuộc vào việc bean có interface phù hợp hay không.

## 5. `@EnableCaching` và cơ chế Spring AOP proxy

Các thuộc tính chính của `@EnableCaching`:

| Thuộc tính | Giá trị mặc định | Tác dụng |
| --- | --- | --- |
| `mode` | `AdviceMode.PROXY` | Áp dụng cache advice lên lời gọi qua Spring proxy |
| `proxyTargetClass` | `false` | Khi ở proxy mode, cho phép dùng proxy dựa trên interface; đặt `true` để yêu cầu class-based proxy |
| `order` | `Ordered.LOWEST_PRECEDENCE` | Quy định thứ tự caching advisor trong chuỗi AOP advice |

Ví dụ cú pháp nâng cao (không phải chương trình độc lập):

~~~java
@Configuration
@EnableCaching(proxyTargetClass = true)
class CachingConfiguration {
}
~~~

**Chọn class-based proxy không sửa được self-invocation.** Dù proxy được tạo bằng JDK interface hay subclass, một lời gọi `this.find(...)` từ bên trong đối tượng gốc không đi qua proxy.

Một số giới hạn thực tiễn:

- Chỉ các **Spring-managed beans** được hạ tầng Spring xử lý. Đối tượng do bạn `new` trực tiếp bên ngoài container không tự được advice.
- Ưu tiên đánh dấu các **phương thức public**. Với proxy, method private không được intercept; `final` method không thể bị class-based proxy override.
- Không trông chờ caching hoạt động trong lời gọi khởi tạo bean như `@PostConstruct`, khi proxy có thể chưa sẵn sàng.
- `@EnableCaching(proxyTargetClass=true)` có thể ảnh hưởng cơ chế proxy của các bean AOP khác cùng context.
- `@EnableCaching` trong context này không bảo đảm xử lý mọi bean nằm ở context con/khác; cần xác minh nơi cấu hình và nơi service được đăng ký.

Nếu cần can thiệp lời gọi nội bộ, `@EnableCaching(mode=AdviceMode.ASPECTJ)` là chế độ nâng cao. Nó cần `spring-aspects` và compile-time hoặc load-time weaving tương ứng. Chỉ đổi thuộc tính `mode` nhưng thiếu weaving thì chưa đủ. Với đa số ứng dụng, giải pháp dễ kiểm soát hơn là tách method cache sang một Spring service khác để caller gọi qua proxy.

## 6. Chọn cache name, key và backend khi annotation được bật

`@EnableCaching` khởi tạo khả năng xử lý; cache interceptor còn cần các quyết định runtime:

- **Cache region:** từ `cacheNames` của `@Cacheable`/`@CachePut`/`@CacheEvict` và cách `CacheResolver` tra cứu các tên đó. `CacheManager` quản lý các cache region; bản thân nó không phải nơi chọn cache key.
- **Cache key:** mặc định dùng `SimpleKeyGenerator`. Với 0 tham số là `SimpleKey.EMPTY`; một tham số thích hợp dùng tham số đó; nhiều tham số gói vào `SimpleKey`. Có thể ghi đè bằng `key="#p0"` hoặc dùng `KeyGenerator` riêng.
- **Cache backend:** `ConcurrentMapCacheManager` lưu tại JVM; Caffeine có thể cấu hình giới hạn kích thước/expiration; Redis có thể chia sẻ dữ liệu giữa instance. TTL/eviction và serialization phụ thuộc provider.
- **Xử lý lỗi cache:** `CacheErrorHandler` mặc định thường ném lỗi truy cập cache về caller; không coi lỗi backend là “cache miss” một cách mặc định.

Để cấu hình mặc định toàn ứng dụng, `CachingConfigurer` có thể cung cấp `CacheManager`, `CacheResolver`, `KeyGenerator`, `CacheErrorHandler`. Trong môi trường có nhiều backend, chọn bean tường minh theo operation khi cần:

~~~java
// Mảnh minh họa bên trong một Spring-managed service:
@Cacheable(cacheNames = "catalog", cacheManager = "localCacheManager")
public String description(String isbn) {
    return "description:" + isbn;
}
~~~

Ở đây `"localCacheManager"` là **tên bean Spring**, còn `"catalog"` là **tên vùng cache** mà manager cung cấp. Nếu dùng `cacheResolver` tùy chỉnh, cấu hình rõ thay vì chỉ định đồng thời các lựa chọn đối nghịch trên một annotation.

## 7. Spring Boot: bật annotation và auto-configuration

`@EnableCaching` vẫn thuộc **Spring Framework**, kể cả khi ứng dụng dùng Spring Boot. Spring Boot giảm công việc cấu hình provider, nhưng phải bật tính năng caching theo tài liệu Boot.

**Dependency trong ứng dụng Boot đã có plugin và dependency management**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

**Lớp cấu hình (minh họa)**:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class AppCachingConfiguration {
}
~~~

Khi `@EnableCaching` đã có hiệu lực, Spring Boot có thể auto-configure `CacheManager` theo provider trên classpath và cấu hình `spring.cache.*`; nếu không tìm thấy provider khác, Boot có thể dùng simple cache lưu bằng concurrent map. Không nên mặc định simple cache là lựa chọn production vì thiếu nhiều kiểm soát lưu trữ.

Một số phân biệt dễ nhầm:

| Chỉ có… | Đủ để `@Cacheable` tự động hoạt động chưa? |
| --- | --- |
| `spring-boot-starter-cache` | Chưa; starter mang dependency, không thay thao tác bật annotation |
| Bean `CacheManager` | Chưa; bean quản lý vùng cache, nhưng bản thân nó không tạo cache advice |
| `@Cacheable` trên service | Chưa; annotation cần caching infrastructure |
| `@EnableCaching` + backend + bean/lời gọi có thể intercept | Đủ các điều kiện cốt lõi; còn phụ thuộc tên vùng/key/provider chính xác |

Các thuộc tính `spring.cache.type`, `spring.cache.cache-names` hay các thiết lập cụ thể của Redis/Caffeine hỗ trợ chọn hoặc cấu hình provider do Boot quản lý, **không** thay thế `@EnableCaching`. Nếu khai báo `CacheManager` tùy chỉnh, Boot có thể không dùng các mặc định auto-configure như trước; hãy kiểm tra bean thực tế.

Nên giữ `@EnableCaching` trong cấu hình độc lập khi hệ thống có test slices hoặc muốn quyết định context nào cần caching. Nếu gắn luôn lên lớp chính mang `@SpringBootApplication`, caching dễ trở thành thành phần bắt buộc trong nhiều bài kiểm thử, đúng điều tài liệu Boot lưu ý.

## 8. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Khả năng cao | Cách kiểm tra |
| --- | --- | --- |
| Method `@Cacheable` vẫn chạy lại với cùng input | Chưa bật caching hoặc config không được nạp | Xác nhận `@EnableCaching` ở đúng Spring context |
| Test gọi `new Service()` không cache | Không dùng bean từ Spring | Lấy service bằng `ApplicationContext.getBean(...)` trong integration test |
| Gọi `this.load(...)` không cache | Self-invocation | Tách method sang Spring bean khác hoặc chuyển luồng gọi qua proxy |
| Private/final method không được cache | Giới hạn AOP proxy | Dùng public non-final method phù hợp; xem loại proxy |
| Không tìm thấy cache name | Cache region chưa tạo/cấu hình, sai tên, dùng manager tĩnh | Đối chiếu `cacheNames`, `CacheManager.getCacheNames()`, cấu hình provider |
| Có nhiều manager, dữ liệu vào sai backend | Chọn sai manager/resolver | Đặt `cacheManager` rõ tại operation hoặc tùy chỉnh `CachingConfigurer` |
| Cache vẫn miss dù đã bật đúng | Key thay đổi, eviction/TTL, provider no-op hoặc không lưu | Kiểm tra key, cache hit, chính sách provider và dữ liệu thực |
| Test slice thiếu bean khi caching bật | Cấu hình bị nạp quá rộng | Tách cấu hình và import theo scope test cần thiết |

Quy trình phân tích hiệu quả: **kiểm tra @EnableCaching → kiểm tra Spring bean/proxy → kiểm tra lời gọi method → kiểm tra CacheManager/CacheResolver → kiểm tra cache name → kiểm tra key và entry**.

Cách kiểm chứng tốt nhất là đo **số lần thực thi method thật**, không chỉ so sánh hai giá trị trả về. Ví dụ OFF/ON dùng `databaseCalls` để chứng minh cache hit đã làm method được bỏ qua.

## 9. Tình huống tự kiểm tra

1. **Tại sao chỉ thêm `@Cacheable` chưa đủ?** Vì annotation cần cơ chế xử lý được kích hoạt bằng `@EnableCaching` hoặc cấu hình tương đương.
2. **Nếu đã có `CacheManager` mà thiếu `@EnableCaching`?** Tra cứu cache trực tiếp bằng API có thể chạy, nhưng caching annotation chưa được áp dụng cho lời gọi method.
3. **Hai lần gọi `find("A")` trong context ON có chạy thân method hai lần?** Không; lần thứ hai hit cache, counter vẫn là 1.
4. **Vì sao `selfFind("B")` vẫn chạy `find` hai lần?** Vì self-invocation không đi qua proxy.
5. **Bật `proxyTargetClass=true` có chữa self-invocation không?** Không, đó chỉ là lựa chọn kiểu proxy.
6. **TTL đặt ở `@EnableCaching` được không?** Không; đặt ở cấu hình provider/backend.
7. **Có nên dùng `@EnableCaching` trên mọi service?** Không; kích hoạt ở Spring configuration được nạp, còn cache operation đặt ở các method thích hợp.
8. **Spring Boot chỉ có starter cache là đủ?** Chưa; cần kích hoạt annotation-driven caching, thường bằng `@EnableCaching`.

## 10. Ghi nhớ và nguồn chính thức

- `@EnableCaching` là điểm **kích hoạt Spring caching annotation infrastructure** cho context.
- `@Cacheable` chỉ giảm số lần chạy method khi **lời gọi được advice thực sự chặn** và có cache hit hợp lệ.
- Proxy mode là mặc định: gọi qua Spring bean/proxy, ưu tiên method public, tránh self-invocation.
- `CacheManager`/`CacheResolver` quyết định cache region; `KeyGenerator`/SpEL quyết định key; backend quyết định chính sách lưu trữ.
- Spring Boot có thể auto-configure cache provider, nhưng `@EnableCaching` vẫn là thao tác bật caching annotations.

Tài liệu để đối chiếu:

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — @EnableCaching API (6.2.19)](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/EnableCaching.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
