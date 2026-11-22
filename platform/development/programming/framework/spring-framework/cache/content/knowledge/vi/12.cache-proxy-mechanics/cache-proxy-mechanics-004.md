# Spring Cache proxy: phạm vi truy cập phương thức và giới hạn `final`, `private`

## 1. Tại sao có `@Cacheable` nhưng cache không hoạt động?

Trong Spring Framework, `@Cacheable`, `@CachePut` và `@CacheEvict` mô tả hành vi cache cho phương thức, nhưng **việc đặt annotation không tự làm Java thay đổi cách gọi method**. Với chế độ thông dụng `@EnableCaching(mode = AdviceMode.PROXY)`, Spring tạo một **proxy** bao quanh bean. Cache interceptor chỉ có cơ hội tra, ghi hoặc xóa cache khi lời gọi **đi qua proxy và có thể được proxy chặn (intercept)**.

Vì vậy, một phương thức có annotation hợp lệ về mặt cú pháp vẫn có thể bị bỏ qua tại runtime nếu nó là `private`, là `final` đối với class-based proxy, không thể truy cập qua proxy phù hợp, hoặc bị gọi bằng `this.method()` từ bên trong cùng bean. Đôi khi ứng dụng chạy hoàn toàn bình thường, nhưng thao tác đắt đỏ vẫn được thực hiện ở mọi lần gọi.

Hai điều kiện cần tách biệt:

1. **Đúng vị trí annotation và đúng khả năng của proxy:** method phải được cơ chế caching tìm thấy và có thể chặn.
2. **Đúng đường đi của lời gọi:** caller sử dụng đối tượng Spring-managed proxy, không gọi trực tiếp target bằng `new`, `this` hoặc trong lúc bean chưa được proxy hoàn chỉnh.

Bài này tập trung vào *method visibility* (quyền truy cập `public`, `protected`, package-private, `private`) và modifier `final` ở **Spring Cache chế độ proxy**. Các kết luận về hạn chế class-based proxy khác với JDK interface proxy và khác với bytecode weaving của AspectJ.

## 2. Cách Spring proxy chặn lời gọi

### 2.1. Lời gọi ngoài bean so với tự gọi trong bean

Giả sử một bean có `@Cacheable(cacheNames = "books")` trên `find("B42")`.

~~~text
Bean A / Controller -> Spring proxy -> CacheInterceptor
                                        |
                              Cache hit? Có -> trả kết quả
                                        |
                                    Không -> gọi target.find()
                                             rồi lưu kết quả


Bên trong target.findViaSelfCall()
      |
      +--> this.find("B42") -> gọi trực tiếp target.find()
                               không qua Spring proxy
                               không chạy CacheInterceptor
~~~

Đường đầu tiên có thể là cache hit. Đường thứ hai không chạy cache advice mặc dù `find` là `public` và có annotation. Đây là **self-invocation**.

Spring AOP proxy không chặn mọi lời gọi Java trong JVM; nó chặn các lời gọi phù hợp đi qua đối tượng proxy. Cách gọi nội bộ (kể cả không viết từ khóa `this` nhưng Java ngầm dùng `this`) vẫn đi trực tiếp đến target.

### 2.2. Hai loại proxy chính

| Loại | Cơ chế | Phạm vi hữu ích | Giới hạn đáng chú ý |
| --- | --- | --- | --- |
| **JDK dynamic proxy** | Tạo object thực thi những interface của bean; intercept lời gọi qua interface. | Các phương thức `public` được khai báo qua interface proxy. | Method chỉ có ở concrete class nhưng không thuộc interface không thể gọi qua kiểu interface của proxy. |
| **Class-based proxy (CGLIB)** | Tạo subclass runtime của concrete class và ghi đè method có thể override. | Phương thức instance phù hợp trên lớp đích, đặc biệt `public` không `final`. | Không thể subclass `final class`, không thể override `final method` hoặc `private method`. |

Spring Framework thuần thường chọn JDK proxy khi bean có interface và class-based proxy khi không có interface; cấu hình của Spring Boot hoặc các processor AOP khác có thể thay đổi lựa chọn mặc định. Vì vậy **không nên suy luận loại proxy chỉ từ việc có/không có interface**. Nếu cần kiểm chứng class-based proxy, có thể dùng `@EnableCaching(proxyTargetClass = true)`; demo phần 5 dùng cài đặt này để kết quả không phụ thuộc mặc định của ứng dụng.

`proxyTargetClass=true` **không khắc phục được** `private`/`final`; ngược lại, nó làm rõ hạn chế không thể override của class-based proxy.

## 3. Phạm vi truy cập: `public`, `protected`, package-private và `private`

### 3.1. `public` là lựa chọn chuẩn cho cache annotations

Tài liệu Spring Cache khuyến nghị đặt các annotation cache trên **phương thức `public` của concrete class** khi sử dụng proxy. Đây là cách rõ ràng và di động nhất giữa JDK proxy và class-based proxy:

~~~java
@Service
public class BookService {
    @Cacheable(cacheNames = "books", key = "#id")
    public Book findById(String id) {
        return repository.findById(id);
    }
}
~~~

Đây là đoạn minh họa có các dependency `Book` và `repository`; ví dụ Java chạy được nằm ở phần 5. Khi một bean khác gọi `bookService.findById("B42")` **qua Spring proxy**, Spring có thể áp dụng cache. Muốn annotation thực sự hoạt động còn phải bật caching, có `CacheManager`, tạo đúng key và không tự bypass proxy.

Một phương thức `public` vẫn có thể **không cache** nếu gọi bằng `this.findById(...)`, tạo đối tượng bằng `new BookService()`, bean chưa được quản lý, hoặc lời gọi xảy ra trước khi proxy hoàn tất.

### 3.2. `protected` và package-private: không nên dựa vào cho Spring Cache

- `protected`: có thể truy cập trong lớp, lớp con và trong cùng package theo quy tắc Java.
- **Package-private**: không khai báo modifier truy cập, chỉ các lớp trong cùng package truy cập trực tiếp.
- Cả hai không phải là API `public` qua JDK interface proxy.

Tài liệu **Spring Cache** ở chế độ proxy hướng dẫn chỉ dùng annotation trên `public` method; annotation trên `protected` hoặc package-visible method có thể không gây lỗi khởi động nhưng **không nên mong đợi cache advice được áp dụng**. Đừng dùng cách gọi qua một public wrapper như bằng chứng annotation trên method nội bộ hoạt động, bởi wrapper thường dẫn đến self-invocation.

Có một sắc thái cần phân biệt: trong **Spring AOP nói chung**, class-based proxy ở một số phiên bản/cấu hình có thể advise vài method `protected` hoặc package-private có thể override. Điều đó **không phải bảo đảm tương đương cho mọi annotation cache, mọi interceptor và mọi loại proxy**. Nếu dự án thật muốn tận dụng hành vi non-public đặc thù, phải kiểm tra tài liệu và chạy integration test với đúng phiên bản Spring, proxy và đường gọi. Quy tắc bài học an toàn nhất là **đặt annotation cache lên public entry point**.

### 3.3. `private`: không thể intercept bằng proxy

`private` method chỉ dùng được bên trong lớp khai báo và **không thể override theo cơ chế subclass Java**. Class-based proxy không chặn được method này. JDK dynamic proxy chỉ expose interface method `public`, nên cũng không cung cấp đường gọi `private`.

~~~java
class PriceService {
    @Cacheable(cacheNames = "prices")
    private String loadPrice(String sku) {
        return "price:" + sku;
    }

    public String price(String sku) {
        return loadPrice(sku);  // Gọi trực tiếp private method.
    }
}
~~~

Đây là đoạn Java minh họa: dù `price(...)` có được gọi từ bên ngoài qua một Spring-managed bean, `loadPrice(...)` vẫn được thực thi trực tiếp. Annotation trên `loadPrice` **không làm xuất hiện caching proxy** cho lời gọi đó.

**Cách sửa đúng:** giữ helper `private` thuần Java, đặt `@Cacheable` lên `public` method do bên ngoài gọi, hoặc chuyển thao tác cần cache sang `public` method của bean khác và gọi qua bean đó. Không đơn thuần đổi `private` sang `public` rồi tiếp tục gọi qua `this`: như vậy vẫn có thể bypass proxy.

### 3.4. Bảng quyết định trong chế độ proxy

| Tình huống | Kỳ vọng an toàn | Lý do |
| --- | --- | --- |
| `public`, không `final`, gọi từ bean khác qua proxy. | **Có thể cache** khi cấu hình hợp lệ. | Proxy có đường intercept. |
| `public`, không `final`, nhưng gọi bằng `this.method()`. | **Không qua cache advice**. | Self-invocation bỏ qua proxy. |
| `protected` hoặc package-private, có `@Cacheable`. | **Không dựa vào**, ưu tiên public API. | Hạn chế visibility và khác biệt proxy/phiên bản. |
| `private`, có `@Cacheable`. | **Không cache qua proxy**. | Method không thể override/intercept. |
| `public final`, class-based proxy. | **Không cache qua proxy** cho method đó. | CGLIB không override được method `final`. |
| `final class`, buộc class-based proxy. | **Không thể tạo subclass proxy**. | Lớp `final` không được kế thừa. |
| `final class` implements interface, dùng JDK interface proxy. | **Có thể proxy interface**. | JDK proxy không subclass target. |

Bảng này nói về **khả năng intercept của proxy**, không bảo đảm kết quả cache luôn đúng: TTL, key, condition, resolver, eviction và loại backend vẫn ảnh hưởng đến hit/miss.

## 4. Modifier `final`: khác biệt giữa class và interface proxy

### 4.1. `final method` với class-based proxy

Với CGLIB, proxy là một subclass runtime. Để cài cache advice, subclass phải ghi đè method tương ứng. Java không cho override `final` method:

~~~java
class CatalogService {
    @Cacheable(cacheNames = "catalog")
    public final String find(String code) {
        return "item:" + code;
    }
}
~~~

Đoạn trên biên dịch hợp lệ nếu đã import `@Cacheable`, nhưng khi truy cập qua **class-based proxy**, `find` không được cache interceptor chặn. Nếu method `final` đọc các trường phụ thuộc vào quá trình khởi tạo, class-based proxy còn có thể gây hành vi khó đoán khi thực hiện trực tiếp trên proxy; **đừng xem việc chạy được một lần là an toàn**.

Lưu ý: `final` trên **method** khác với `final` trên **class**. Một class không final vẫn tạo được proxy CGLIB cho các method khác không final; riêng method final không thể được override. Một `final class` thì CGLIB không thể subclass ngay từ đầu, có thể làm việc tạo proxy thất bại.

### 4.2. Vì sao không được kết luận “cứ `final` là Spring Cache không hoạt động”?

JDK dynamic proxy là object **implements interface**, không phải subclass của target. Vì thế, nếu bean được phơi qua interface `public`, proxy có thể intercept **lời gọi interface** trước khi delegate vào một target method mang `final`. Việc target method có `final` không tự động ngăn JDK proxy thực hiện interception ở ranh giới interface.

Ví dụ thiết kế (minh họa, không phải chương trình độc lập):

~~~java
public interface Reader {
    String read(String id);
}

public final class ReaderImpl implements Reader {
    @Override
    @Cacheable(cacheNames = "books", key = "#p0")
    public final String read(String id) {
        return "Book:" + id;
    }
}
~~~

Để thiết kế này hoạt động theo JDK proxy, phải cấu hình/có hiệu lực proxy interface, gọi qua bean kiểu `Reader` và không ép `proxyTargetClass=true`. Annotation nên đặt trên **concrete implementation** như trên, không chỉ trên interface (đặc biệt nếu sau này đổi sang AspectJ). Với `final class` hoặc `final method`, việc chuyển sang **CGLIB** sẽ không giải quyết được giới hạn `final`.

Nếu không có nhu cầu đặc biệt, cách dễ bảo trì nhất cho Spring Cache vẫn là **public, non-final service method**.

### 4.3. Các nguồn `final` ít được để ý

- Java `record` là class `final`: không thể tạo class-based subclass proxy. Nếu cần cache, nên đưa logic vào service bean thích hợp thay vì kỳ vọng proxy một record.
- Kotlin class và method thường `final` theo mặc định nếu không mở bằng `open` hoặc plugin phù hợp. Khi dùng Spring và class-based proxy, cần hiểu việc class/method đã được mở thực sự hay chưa.
- `static` method không phải instance method được dispatch qua một bean proxy thông thường; đừng dùng static helper như cache entry point của Spring proxy.
- Method `final` do kế thừa cũng không thể được CGLIB override. Với package-private method nằm ở class cha khác package, phương thức có thể không nhìn thấy từ subclass proxy, nên cũng không thể intercept.

## 5. Ví dụ chạy được: public, private, final và self-invocation

Ví dụ dùng **Spring Boot 3.3, Java 17** và `ConcurrentMapCacheManager` (cache trong RAM). Ta cố ý ép class-based proxy bằng `@EnableCaching(proxyTargetClass = true)` để minh họa đúng giới hạn CGLIB, không phụ thuộc cấu hình proxy mặc định của Boot.

Bốn nhóm lời gọi:

1. `publicRead("A")` đi qua proxy: lần thứ nhất miss, lần thứ hai hit.
2. `callPrivate("B")` gọi `privateRead` có annotation: không cache, hai lần đều chạy.
3. `finalRead("C")` là `public final`: class-based proxy không thể intercept, hai lần đều chạy.
4. `selfCall("D")` gọi `this.publicRead("D")` nội bộ: không cache, sau đó gọi `publicRead("D")` từ ngoài mới phát sinh miss rồi hit.

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

Tạo file `src/main/java/demo/CacheProxyVisibilityDemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching(proxyTargetClass = true)
public class CacheProxyVisibilityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheProxyVisibilityDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    LibraryService libraryService() {
        return new LibraryService();
    }

    @Bean
    CommandLineRunner demo(LibraryService service) {
        return args -> {
            System.out.println("external-1 = " + service.publicRead("A"));
            System.out.println("external-2 = " + service.publicRead("A"));

            System.out.println("private-1 = " + service.callPrivate("B"));
            System.out.println("private-2 = " + service.callPrivate("B"));

            System.out.println("final-1 = " + service.finalRead("C"));
            System.out.println("final-2 = " + service.finalRead("C"));

            System.out.println("self-1 = " + service.selfCall("D"));
            System.out.println("self-2 = " + service.selfCall("D"));

            System.out.println("external-3 = " + service.publicRead("D"));
            System.out.println("external-4 = " + service.publicRead("D"));
        };
    }

    public static class LibraryService {
        @Cacheable(cacheNames = "books", key = "#p0")
        public String publicRead(String id) {
            System.out.println("LOAD public " + id);
            return "Book:" + id;
        }

        @Cacheable(cacheNames = "books", key = "#p0")
        private String privateRead(String id) {
            System.out.println("LOAD private " + id);
            return "Book:" + id;
        }

        public String callPrivate(String id) {
            return privateRead(id);
        }

        @Cacheable(cacheNames = "books", key = "#p0")
        public final String finalRead(String id) {
            System.out.println("LOAD final " + id);
            return "Book:" + id;
        }

        public String selfCall(String id) {
            return this.publicRead(id);
        }
    }
}
~~~

Chạy `./gradlew bootRun` nếu dự án có Gradle Wrapper (Windows: `gradlew.bat bootRun`), hoặc `gradle bootRun` với Gradle tương thích đã cài. Ví dụ không có database ngoài; cần tải dependency Maven lần đầu.

**Các dòng do demo in ra**, bỏ qua banner/log khởi động và log cảnh báo của Spring, theo thứ tự:

~~~text
LOAD public A
external-1 = Book:A
external-2 = Book:A
LOAD private B
private-1 = Book:B
LOAD private B
private-2 = Book:B
LOAD final C
final-1 = Book:C
LOAD final C
final-2 = Book:C
LOAD public D
self-1 = Book:D
LOAD public D
self-2 = Book:D
LOAD public D
external-3 = Book:D
external-4 = Book:D
~~~

**Giải thích từng nhóm:**

- **Public/external:** `service.publicRead("A")` đến từ bean `CommandLineRunner`, đi qua proxy. `LOAD public A` chỉ xuất hiện một lần, dù có hai lần gọi cùng key `A`.
- **Private:** `callPrivate` là public wrapper nhưng bên trong gọi `privateRead` trực tiếp. `privateRead` không thể bị proxy override và annotation của nó không áp dụng; `LOAD private B` xuất hiện hai lần.
- **Final:** `finalRead` là `final` và class-based proxy không override được. Vì phương thức demo không phụ thuộc vào field của target, lời gọi chỉ in `LOAD final C` ở cả hai lần. Trong ứng dụng thực tế, không dựa vào cách thức một method `final` chạy trên proxy để tạo logic quan trọng.
- **Self-invocation:** `selfCall` gọi `this.publicRead("D")`, bỏ qua proxy, nên hai lượt `self` đều in `LOAD public D`. Hai lần nội bộ đó **không làm nóng cache** cho key `D`; `external-3` mới là miss tạo entry và `external-4` là hit.

Ví dụ này cố tình không thêm `@Cacheable` lên `callPrivate` hoặc `selfCall` để tránh đánh lạc hướng về annotation nào thực sự được intercept. Không cần đoán Spring đang dùng JDK hay CGLIB: `proxyTargetClass=true` chỉ định rõ class-based proxy.

## 6. Cách sửa thiết kế để caching hoạt động đúng

### 6.1. Đặt annotation trên public entry point

Thay vì annotate private helper, cache public method được bean khác gọi:

~~~java
public class PriceService {
    @Cacheable(cacheNames = "prices", key = "#p0")
    public String price(String sku) {
        return loadPrice(sku);
    }

    private String loadPrice(String sku) {
        return "price:" + sku;
    }
}
~~~

Đây là đoạn class minh họa; cần khai báo bean và bật caching như demo ở phần 5. `loadPrice` vẫn là private helper thuần Java. Khi caller dùng Spring proxy của `PriceService`, cache interceptor áp dụng ở entry point `price`. Đừng dùng `new PriceService()` nếu kỳ vọng Spring interception.

### 6.2. Tách bean khi cần cache lời gọi nội bộ

Nếu method `checkout` phải gọi `price` và muốn dùng cache, tách thao tác đọc sang bean riêng:

~~~java
@Service
class PriceQueryService {
    @Cacheable(cacheNames = "prices", key = "#p0")
    public String price(String sku) {
        return "price:" + sku;
    }
}

@Service
class CheckoutService {
    private final PriceQueryService prices;

    CheckoutService(PriceQueryService prices) {
        this.prices = prices;
    }

    public String checkout(String sku) {
        return "checkout:" + prices.price(sku);
    }
}
~~~

Ví dụ này là trích đoạn các bean, cần import `@Service` và `@Cacheable` khi đặt vào project. Vì `CheckoutService` gọi qua bean `PriceQueryService` do container cung cấp, proxy có cơ hội chặn. Đây thường là giải pháp sáng sủa hơn self-injection hoặc `AopContext.currentProxy()`, vốn làm service phụ thuộc mạnh vào cơ chế AOP.

### 6.3. Không biến `final` thành vấn đề của mọi loại proxy

- Muốn class-based proxy: cho method cần cache là **non-final**, cho class có thể được subclass, và đặt annotation trên public method.
- Muốn dùng JDK proxy: phơi method qua interface, inject bean qua interface; không ép class-based proxy; annotation trên implementation thường là lựa chọn rõ ràng.
- Không đổi `private` sang `protected` chỉ để “hy vọng CGLIB thấy được”; dùng public entry point.
- Với Java `record`/Kotlin class final, cân nhắc tách logic cache vào public service bean thay vì thay đổi model domain chỉ để phục vụ AOP.

### 6.4. Khi nào cân nhắc `AdviceMode.ASPECTJ`?

Spring Cache hỗ trợ chế độ AspectJ thay thế proxy: áp dụng aspect bằng compile-time hoặc load-time weaving để thay đổi bytecode của lớp được weave. Cách này có thể xử lý các tình huống **self-invocation** và các method non-public theo cơ chế khác proxy, nhưng cần `spring-aspects` cùng cấu hình weaving phù hợp và kiểm thử build/deployment.

~~~java
@EnableCaching(mode = AdviceMode.ASPECTJ)
~~~

Dòng trên **không đủ một mình** để chuyển ứng dụng sang AspectJ: phải có dependency/instrumentation weaving và cấu hình tương ứng. Không nên thêm nó chỉ để “vá nhanh” một private method khi có thể thiết kế lại public service API sạch hơn.

## 7. Kiểm tra proxy và chẩn đoán cache miss bất thường

Khi thấy `@Cacheable` nhưng method luôn chạy, kiểm tra có hệ thống:

1. **Bean có thực sự do Spring quản lý?** `new Service()` không qua Spring AOP proxy; caller phải inject bean từ context.
2. **Caching đã được bật?** Kiểm tra `@EnableCaching`, `CacheManager`, cache names và lỗi cấu hình.
3. **Lời gọi có qua proxy?** Từ bean khác là dễ xác nhận nhất. `this.method()`, gọi trong constructor, hoặc trong `@PostConstruct` khi proxy chưa sẵn sàng không phải đường đáng tin.
4. **Method có khả năng được intercept?** Ưu tiên `public`, non-final. Nếu class-based proxy, kiểm tra class không `final`; nếu JDK proxy, kiểm tra method nằm trong interface mà caller đang dùng.
5. **Thực sự miss hay bỏ qua caching?** Tạo hai lần gọi cùng tham số, đếm số dòng `LOAD`; kiểm tra cache backend có entry đúng key hay không. Nếu cache advice chạy nhưng key thay đổi, `condition` false, `unless` true, entry hết hạn hoặc cache bị evict, biểu hiện cũng giống như “không cache”.
6. **Các annotation khác có ảnh hưởng?** `@CachePut` luôn thực thi method và cập nhật cache, khác với `@Cacheable`; `@CacheEvict` xóa entry. Không dùng số lần chạy method của `@CachePut` để kết luận proxy hỏng.
7. **Thử integration test theo đúng cấu hình deploy.** Dùng cùng version Spring, proxy mode, cache provider và cùng kiểu injection như ứng dụng thật. Nếu cần, log `org.springframework.cache`/`org.springframework.aop` ở mức phù hợp để xem đường đi.

Để kiểm tra bean có là proxy, có thể gọi API `AopUtils.isAopProxy(bean)` và `AopUtils.isCglibProxy(bean)` trong một integration test có dependency Spring AOP. **Có proxy không đồng nghĩa mọi method của bean đều được intercept**: vẫn phải kiểm tra visibility, `final`, self-invocation và cache key.

Đặc biệt, trong cấu hình proxy, annotation trên method không phải public thường **không gây lỗi rõ ràng ngay khi khởi động**. Vì vậy test hành vi hit/miss quan trọng hơn việc chỉ thấy ứng dụng khởi động thành công.

## 8. Câu hỏi tự kiểm tra

**Câu 1.** Một service có method `@Cacheable public String find(String id)`. Method khác trong cùng service gọi `this.find(id)`. Caching có chạy không?

**Đáp án:** Không qua cache advice trong chế độ proxy mặc định, vì self-invocation bypass proxy. Đặt lời gọi qua bean proxy ở ngoài, hoặc tách service.

**Câu 2.** Đổi private method có `@Cacheable` thành protected có phải giải pháp chắc chắn không?

**Đáp án:** Không. Tài liệu Spring Cache hướng dẫn dùng public method trong proxy mode; protected/package-private không phải contract an toàn xuyên cấu hình. Hãy cache public entry point.

**Câu 3.** Vì sao `public final` có thể không cache với CGLIB nhưng vẫn có thể tham gia một JDK interface proxy?

**Đáp án:** CGLIB cần subclass và override method, bị `final` ngăn. JDK proxy đứng trước lời gọi qua interface, không subclass target.

**Câu 4.** Bắt buộc dùng `proxyTargetClass=true` có sửa được private/final caching không?

**Đáp án:** Không. Flag này ép class-based proxy, không làm thay đổi quy tắc override của Java.

**Câu 5.** Hai lần gọi một public method đều chạy thân method. Ngoài visibility và self-invocation, còn lý do nào?

**Đáp án:** Chưa bật caching, key khác, `condition` false, `unless` ngăn lưu, cache backend hết hạn/không lưu, hoặc entry bị xóa; kiểm tra proxy và actual cache entry.

**Câu 6.** AspectJ mode có thể tự hoạt động chỉ nhờ thêm `@EnableCaching(mode=ASPECTJ)` không?

**Đáp án:** Không. Phải cấu hình dependency và compile-time/load-time weaving phù hợp, rồi kiểm thử.

**Ghi nhớ:** Trong Spring Cache proxy mode, hãy thiết kế **public, non-final cache entry point**, gọi **qua Spring-managed proxy**. `private` không được intercept; `final` chặn class-based proxy; `protected`/package-private không phải lựa chọn cache annotation an toàn. Chọn JDK hay CGLIB có thể làm thay đổi giới hạn kỹ thuật, nhưng không thay thế việc thiết kế API và đường gọi rõ ràng.

## Tài liệu tham khảo

- [Spring Framework Reference — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html) — mục *Method visibility and cache annotations*, chế độ proxy/AspectJ.
- [Spring Framework Reference — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html) — JDK/CGLIB, giới hạn `final`, `private` và self-invocation.
