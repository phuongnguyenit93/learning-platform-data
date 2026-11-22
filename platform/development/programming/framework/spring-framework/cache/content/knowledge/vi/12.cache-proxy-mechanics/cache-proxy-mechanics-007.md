# Thứ tự cache advice so với các advice khác trong Spring AOP

## 1. Vì sao thứ tự advice quan trọng?

Khi một phương thức Spring đồng thời có caching, transaction, logging, metrics, security hoặc retry, lời gọi thường đi qua **chuỗi các interceptor/advice của Spring AOP** trước khi đến thân phương thức. Thứ tự của chúng không chỉ ảnh hưởng việc log hiện ra trước hay sau: nó có thể quyết định **một advice có được chạy ở cache hit không**, transaction bắt đầu lúc nào, thao tác cache có xảy ra trước hay sau commit, và một lỗi có được retry hay không.

Ví dụ một service có cả hai annotation:

```java
@Cacheable(cacheNames = "books", key = "#p0")
@Transactional(readOnly = true)
public Book findBook(String id) {
    return repository.findById(id).orElseThrow();
}
```

*Đây là đoạn minh họa; `Book` và `repository` cần định nghĩa. Ví dụ chạy đầy đủ có ở mục 6.*

Từ góc nhìn của Java, lời gọi là `service.findBook("B1")`. Nhưng nếu được Spring proxy intercept, thực tế có thể là:

```text
Caller
  |
  v
Proxy
  |
  +-- Transaction advice
  |      |
  |      '-- Cache advice
  |              |-- cache HIT -> trả kết quả, bỏ qua method
  |              '-- cache MISS -> gọi method -> cache put
  |
  '-- trả về Caller
```

**Hoặc** thứ tự hai advice có thể ngược lại, nếu cấu hình khác:

```text
Caller
  |
  v
Proxy
  |
  +-- Cache advice
         |-- cache HIT -> trả ngay, không đi vào Transaction advice
         '-- cache MISS
                |
                '-- Transaction advice
                        |
                        '-- method -> commit/rollback
                |
                '-- Cache advice hoàn tất put nếu phù hợp
```

Hai cấu trúc không tương đương: ở cấu trúc thứ nhất, cache hit vẫn đi qua transaction advice bên ngoài; ở cấu trúc thứ hai, cache hit có thể **không đi qua transaction advice nằm bên trong**. Với các side effect/kiểm tra phải thực hiện mọi lượt, sự khác biệt này rất quan trọng.

**Kết luận đầu bài:** cần xác định rõ **advice nào bao ngoài (outer)**, **advice nào nằm trong (inner)**, và **advice nào có thể không gọi `proceed()`**. `@Cacheable` là ví dụ tiêu biểu của advice có thể dừng chuỗi ở cache hit.

## 2. “Outer” và “inner” có nghĩa là gì?

Với hai around advice A và B, giả sử A có độ ưu tiên cao hơn B, cấu trúc logic là:

```text
Caller
  |
  v
A: trước proceed()
    |
    v
  B: trước proceed()
      |
      v
    method body
      |
      v
  B: sau proceed()
    |
    v
A: sau proceed()
  |
  v
Caller
```

Log thông thường:

```text
A before
B before
BODY
B after
A after
```

Đây là thứ tự **lồng nhau**, không phải một danh sách các thao tác chạy nối tiếp một chiều.

Đối với `@Around`, `ProceedingJoinPoint.proceed()` quyết định có gọi phần còn lại của chuỗi hay không. Một advice có thể:

- gọi `proceed()` **một lần** rồi trả kết quả;
- không gọi `proceed()` và trả kết quả sẵn có (như cache hit);
- ném exception trước khi gọi `proceed()`;
- thực thi logic trước/sau lời gọi; hoặc, nếu thiết kế cho phép, gọi lại phần tiếp theo (retry).

Khi A ở ngoài B, A luôn được gọi nếu lời gọi đã tới A, **nhưng B không chắc được gọi**: A có quyền dừng chuỗi. Ngược lại, nếu B chạy rồi method ném exception, A có thể thấy exception đi lên và ghi log ở nhánh `catch`/`finally`.

Một ví dụ mã minh họa:

```java
@Around("execution(* example.service.BookService.findBook(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("before");
    try {
        Object result = pjp.proceed();
        System.out.println("after");
        return result;
    } catch (Throwable ex) {
        System.out.println("failed");
        throw ex;
    }
}
```

*Đây là nội dung một phương thức trong class `@Aspect`, chưa phải chương trình Java độc lập.*

Vị trí của lời khuyên quanh cache interceptor quyết định log `before/after` có xuất hiện trên cache hit không. **Không thể suy luận chỉ từ annotation trên method rằng tất cả advice đều chạy mỗi lần.**

## 3. Quy tắc thứ tự `@Order` và `@EnableCaching(order = ...)`

Spring AOP tuân theo quy tắc ưu tiên: **giá trị order nhỏ hơn có độ ưu tiên cao hơn**.

Ví dụ:

- `@Order(0)`: ưu tiên cao hơn `@Order(200)`.
- `@Order(200)`: ưu tiên thấp hơn `@Order(0)`.
- Trên đường **đi vào** method, advice có ưu tiên cao chạy **trước** và bọc bên ngoài.
- Trên đường **đi ra** (return hoặc exception unwind), advice có ưu tiên cao kết thúc **sau**.

Với cache advice, Spring cung cấp thuộc tính:

```java
@Configuration
@EnableCaching(order = 100)
public class CacheConfiguration {
}
```

*Đoạn trên minh họa cấu hình. Ví dụ đầy đủ ở mục 6 có cấu hình, bean cache và các aspect hoàn chỉnh.*

Ý nghĩa của `order = 100`: đặt mức ưu tiên của **cache advisor** tại các join point có nhiều advice, để có thể so sánh với những advisor/aspect khác. Nó **không** phải TTL, không phải thứ tự các cache key, không phải độ ưu tiên giữa các instance cache, và không thay đổi hành vi nội tại hit/miss của `@Cacheable`.

Mặc định, thuộc tính `order` của `@EnableCaching` là `Ordered.LOWEST_PRECEDENCE` (giá trị số `Integer.MAX_VALUE`). Nếu các advice liên quan cùng mức ưu tiên hoặc không xác định thứ tự, **không nên dựa vào thứ tự tình cờ** của quá trình khởi tạo, scan bean hay tên method.

Trong ví dụ cụ thể:

| Advice | Cách khai báo | Order | Vai trò |
| --- | --- | ---: | --- |
| Outer tracing | `@Aspect @Order(0)` | 0 | Chạy bên ngoài |
| Cache advice | `@EnableCaching(order = 100)` | 100 | Tra cache và có thể short-circuit |
| Inner tracing | `@Aspect @Order(200)` | 200 | Chạy bên trong cache advice |
| Target method | Method Java | Không phải advisor | Chạy nếu chuỗi đi tới thân method |

Luồng **khi cache miss**:

```text
OUTER before -> CACHE lookup miss
    -> INNER before -> METHOD -> INNER after
    -> CACHE put (nếu phù hợp) -> OUTER after
```

Luồng **khi cache hit**:

```text
OUTER before -> CACHE lookup hit -> OUTER after
```

Không có `INNER before`, `INNER after` và không chạy method ở cache hit. Cache advice đã lấy được kết quả và **không gọi tới phần chuỗi phía trong**.

Lưu ý: order được áp dụng cho các advisor phù hợp tại **cùng một join point**. `@Order` trên một aspect không tự tạo cache operation; method vẫn cần `@Cacheable`/`@CachePut`/`@CacheEvict` và cache infrastructure phù hợp.

## 4. Cache advice có “nuốt” các advice khác không?

Cách nói chính xác là **cache advice có thể short-circuit phần advice nằm *bên trong*** trên một cache hit, chứ không phải xóa toàn bộ AOP.

Khi cache advice được chạy:

- `@Cacheable`: với hit hợp lệ, có thể trả dữ liệu luôn mà **không thực thi target method** và **không đi vào advice phía trong**.
- `@Cacheable`: với miss hoặc bypass do `condition=false`, phương thức có thể chạy (và các advice phía trong có thể chạy theo chuỗi).
- `@CachePut`: trong luồng đồng bộ thông thường, method được gọi rồi có thể ghi kết quả; **không dùng cache hit để bỏ qua method**.
- `@CacheEvict`: thực hiện xóa entry trước hoặc sau invocation tùy `beforeInvocation`; method thường vẫn chạy.
- `@Caching`: tập hợp nhiều operation có thể tạo chuỗi xử lý phức tạp; cần xem các operation cụ thể.

Điều cần quan sát là **lời gọi có đi qua điểm advice đó không?** Nếu cache advice nằm ngoài một aspect ghi metric thời gian thực thi thân method, metric đó có thể chỉ xuất hiện ở miss. Nếu muốn đo **cả cache hit lẫn miss**, đặt metric advisor ở ngoài cache advice hoặc thu metrics ngay tại cache subsystem.

### 4.1. Một sơ đồ so sánh trực quan

```text
Order 0:  AUDIT (outer)
           |
Order 100: CACHE
           |
Order 200: DB_TIMER (inner)
           |
         TARGET METHOD
```

| Sự kiện | AUDIT order 0 | CACHE order 100 | DB_TIMER order 200 | Method |
| --- | --- | --- | --- | --- |
| Lần đầu, miss | Có | Lookup và lưu | Có | Có |
| Lần sau, hit | Có | Hit, trả dữ liệu | **Không** | **Không** |
| `condition=false` | Có | Bypass | Có | Có |
| Target ném exception khi miss | Có, thấy lỗi khi unwind | Không ghi kết quả bình thường | Có, thấy lỗi | Throw |
| Advice ngoài cache từ chối trước `proceed()` | Có | **Không đến** | Không | Không |

**Lưu ý:** đây là một **ví dụ với thứ tự cấu hình rõ ràng**, không phải phát biểu rằng mọi ứng dụng Spring luôn đặt audit ở 0 và cache ở 100.

## 5. Vì sao thứ tự mặc định không đủ để đoán?

Hai annotation thường gặp có mặc định order riêng:

- `@EnableCaching(order = Ordered.LOWEST_PRECEDENCE)`.
- `@EnableTransactionManagement(order = Ordered.LOWEST_PRECEDENCE)` trong cấu hình transaction proxy thông thường.

Khi cả hai đều giữ cùng giá trị mặc định, ta **không nên coi cache luôn ngoài transaction hoặc transaction luôn ngoài cache**. Thứ tự thực tế có thể phụ thuộc cách các advisor được xây dựng và đăng ký. Nếu cần thứ tự cho một invariant cụ thể, **hãy cấu hình order rõ ràng và viết integration test**.

Ví dụ minh họa thứ tự tường minh:

```java
@EnableTransactionManagement(order = 50)
@EnableCaching(order = 100)
@Configuration
public class AdviceConfig {
}
```

Ở cùng join point:

```text
Transaction advice (50, outer)
    |
    '-- Cache advice (100, inner)
            |
            '-- target
```

Cache hit vẫn nằm **bên trong** transaction advice. Đổi lại:

```java
@EnableCaching(order = 50)
@EnableTransactionManagement(order = 100)
@Configuration
public class AdviceConfig {
}
```

thì cache advice nằm **ngoài** transaction advice; `@Cacheable` hit có thể trả ngay mà **không đi vào** transaction advice ở phần trong.

*Hai đoạn là cấu hình minh họa, cần dependency transaction, transaction manager và môi trường giao dịch phù hợp; không sử dụng đồng thời hai cấu hình trong cùng ứng dụng.*

Không nên thay thứ tự chỉ để “thấy cache nhanh hơn” mà không xét invariant: caching có thể bỏ qua một số instrumentation, auditing, transaction context hoặc kiểm tra quyền nếu chúng nằm phía trong.

## 6. Ví dụ hoàn chỉnh chạy được: chứng minh thứ tự bằng stdout

Dự án dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5**, **Spring AOP** và cache in-memory. Ví dụ không dùng database hay transaction thực để minh họa rõ **thứ tự advice**, tránh lẫn với thời điểm commit.

Mục tiêu:

1. `@EnableCaching(order = 100)` đặt cache advice ở giữa hai aspect.
2. `OuterTraceAspect` có `@Order(0)`, nằm ngoài cache.
3. `InnerTraceAspect` có `@Order(200)`, nằm trong cache.
4. Method `BookService.load("A")` có `@Cacheable`.
5. Gọi cùng tham số hai lần; chỉ lượt đầu chạy method và inner aspect, trong khi outer aspect chạy cả hai lần.

### 6.1. Cấu trúc dự án

```text
cache-advice-order-demo/
├── pom.xml
└── src/main/java/example/adviceorder/
    ├── AdviceOrderApplication.java
    ├── BookService.java
    ├── OuterTraceAspect.java
    └── InnerTraceAspect.java
```

### 6.2. File `pom.xml`

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
    <artifactId>cache-advice-order-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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

### 6.3. File `src/main/java/example/adviceorder/BookService.java`

```java
package example.adviceorder;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final AtomicInteger bodyRuns = new AtomicInteger();

    @Cacheable(cacheNames = "books", key = "#p0")
    public String load(String id) {
        int run = bodyRuns.incrementAndGet();
        System.out.println("BODY load #" + run + " " + id);
        return "book:" + id;
    }
}
```

### 6.4. File `src/main/java/example/adviceorder/OuterTraceAspect.java`

```java
package example.adviceorder;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(0)
public class OuterTraceAspect {
    @Around("execution(* example.adviceorder.BookService.load(..))")
    public Object trace(ProceedingJoinPoint joinPoint) throws Throwable {
        System.out.println("OUTER before");
        try {
            Object result = joinPoint.proceed();
            System.out.println("OUTER after");
            return result;
        } catch (Throwable ex) {
            System.out.println("OUTER error");
            throw ex;
        }
    }
}
```

### 6.5. File `src/main/java/example/adviceorder/InnerTraceAspect.java`

```java
package example.adviceorder;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(200)
public class InnerTraceAspect {
    @Around("execution(* example.adviceorder.BookService.load(..))")
    public Object trace(ProceedingJoinPoint joinPoint) throws Throwable {
        System.out.println("INNER before");
        try {
            Object result = joinPoint.proceed();
            System.out.println("INNER after");
            return result;
        } catch (Throwable ex) {
            System.out.println("INNER error");
            throw ex;
        }
    }
}
```

### 6.6. File `src/main/java/example/adviceorder/AdviceOrderApplication.java`

```java
package example.adviceorder;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching(order = 100)
public class AdviceOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(AdviceOrderApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    CommandLineRunner demo(BookService service) {
        return args -> {
            System.out.println("RESULT1 => " + service.load("A"));
            System.out.println("RESULT2 => " + service.load("A"));
        };
    }
}
```

### 6.7. Lệnh chạy

Mở terminal ở thư mục chứa `pom.xml`, với JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Các dòng do demo in ra (bỏ qua Spring Boot banner/log khởi động) theo đúng thứ tự:

```text
OUTER before
INNER before
BODY load #1 A
INNER after
OUTER after
RESULT1 => book:A
OUTER before
OUTER after
RESULT2 => book:A
```

**Giải thích:**

- **RESULT1 — miss:** `OuterTraceAspect` (order 0) chạy trước; cache advice (order 100) không tìm thấy key `"A"`; `InnerTraceAspect` (order 200) chạy; sau đó mới đến `BookService.load`. Khi method trả về `book:A`, inner aspect kết thúc, cache advice có thể lưu kết quả và outer aspect kết thúc.
- **RESULT2 — hit:** outer aspect bắt đầu và gọi `proceed()`; cache advice tìm thấy entry, trả `book:A` ngay. Do cache advice không gọi phần advice phía trong, `InnerTraceAspect` và method body **không chạy**. Outer aspect vẫn in `OUTER after` vì nó đang bao ngoài cache advice.

Kết quả chứng minh rõ **thứ tự không chỉ đổi vị trí log: nó quyết định advice nào có cơ hội thực thi ở cache hit**.

*Ghi chú chạy được:* hai aspect nằm trong package được `@SpringBootApplication` scan; dependency AOP cung cấp AspectJ annotation runtime/weaving support cần cho Spring AOP; `@EnableCaching` đăng ký cache advisor; Spring bean `BookService` được inject vào `CommandLineRunner` nên lời gọi đi qua proxy; key `#p0` là tham số `id`. Cache local `ConcurrentMapCacheManager("books")` chỉ tồn tại trong tiến trình demo. Stdout trên đã được rà soát theo thứ tự thực thi dự kiến; log ngoài demo khác nhau tùy môi trường.

### 6.8. Thử thay đổi thứ tự và dự đoán đầu ra

Đổi **chỉ một dòng** trong `AdviceOrderApplication.java`:

```java
@EnableCaching(order = -100)
```

Không đổi `@Order(0)` và `@Order(200)`, khởi động lại ứng dụng để cache ban đầu rỗng. Cache advisor lúc này có ưu tiên **cao hơn** cả hai aspect:

```text
CACHE (-100, outer)
    |
    '-- OUTER (0)
          |
          '-- INNER (200)
                 |
                 '-- BODY
```

Kết quả dự kiến:

```text
OUTER before
INNER before
BODY load #1 A
INNER after
OUTER after
RESULT1 => book:A
RESULT2 => book:A
```

Ở lượt **hit**, cache advisor nằm ngoài cùng nên trả kết quả **trước khi vào cả hai aspect**. Do đó lượt `RESULT2` không in bất kỳ dòng `OUTER` hoặc `INNER` nào. Đây là một phép thử đơn giản để thấy ý nghĩa thực tế của `order`.

**Không dùng đồng thời hai cấu hình:** `@EnableCaching(order=100)` là cấu hình gốc của demo; `order=-100` chỉ là phép thử thay thế. Không thêm một `@EnableCaching` thứ hai để thử giá trị khác trong cùng application context.

## 7. Cache advice so với transaction advice

Khi `@Cacheable`, `@CachePut` hoặc `@CacheEvict` được kết hợp với `@Transactional`, thứ tự có thể ảnh hưởng **thời điểm lookup/put/evict so với begin/commit/rollback**.

### 7.1. Transaction advice ngoài cache

```text
@Transactional advisor (outer)
  |
  |-- begin transaction
  |    |
  |    '-- Cache advisor (inner)
  |           |-- @Cacheable HIT: trả result từ cache
  |           '-- MISS/@CachePut: method chạy, cache có thể put
  |    |
  |-- commit/rollback transaction
  |
  '-- return/throw
```

Hệ quả:

- Một cache hit vẫn có thể làm transaction advice bên ngoài chạy.
- Với method cập nhật, **cache put có thể xảy ra trước khi outer transaction commit**; nếu commit thất bại sau đó, cache có nguy cơ chứa dữ liệu chưa commit khi cache manager không transaction-aware.
- `@Transactional` không mặc nhiên khiến Redis và database trở thành một giao dịch nguyên tử.

### 7.2. Cache advice ngoài transaction

```text
Cache advisor (outer)
  |
  |-- @Cacheable HIT: trả result; transaction advice bên trong bị bỏ qua
  |
  '-- MISS/@CachePut
         |
         '-- Transaction advisor (inner)
               |-- begin
               |-- target method
               '-- commit/rollback
         |
         '-- Cache advisor có thể put theo kết quả bình thường
```

Hệ quả:

- Với cache hit, transaction advice phía trong có thể **không chạy**.
- Với lời gọi thực sự đi vào transaction advice và hoàn tất thành công, việc put hậu xử lý của cache advisor nằm ngoài xảy ra **sau khi transaction advice quay về**. Tuy vậy vẫn phải xét provider, độ bền, concurrency và tình huống lỗi cache.
- Không nên dùng cấu hình thứ tự này như lời hứa tuyệt đối rằng “database và cache luôn nhất quán”.

### 7.3. Cache update sau commit

Nếu nghiệp vụ yêu cầu chỉ publish cache entry khi database đã commit, ngoài order có thể cần:

- `TransactionAwareCacheManagerProxy` hoặc cache decorator transaction-aware phù hợp.
- Đồng bộ sự kiện **sau commit** thay vì cập nhật cache trước commit.
- Chiến lược invalidation/reconciliation đáng tin cậy nếu hệ thống phân tán.
- Integration test kiểm tra tình huống rollback, commit failure và concurrent read.

Đối với `@CacheEvict(beforeInvocation = true)`, eviction có thể xảy ra trước method, nên nó vẫn có thể xóa cache dù method sau đó throw. Thứ tự transaction và cache advice không xóa bỏ ngữ nghĩa `beforeInvocation`.

**Không suy luận máy móc** thứ tự giữa `@Transactional` và `@Cacheable` chỉ bằng việc nhìn vị trí hai annotation trong source. Vị trí các dòng annotation **không phải** thứ tự advice runtime.

## 8. Cache advice so với kiểm tra quyền và audit

Đây là trường hợp quan trọng về tính đúng đắn và bảo mật.

Giả sử một method có `@Cacheable` và một security advice kiểm tra người gọi mỗi lượt:

```text
PHƯƠNG ÁN A — Security outer, Cache inner

SECURITY: kiểm tra quyền
    |
    '-- CACHE: hit/miss
           |
           '-- target khi miss
```

Tại cache hit, kiểm tra quyền vẫn chạy **trước** khi trả dữ liệu (giả sử security advice thực sự nằm ngoài và không có cơ chế bypass khác).

```text
PHƯƠNG ÁN B — Cache outer, Security inner

CACHE: hit? -> return luôn
    |
    '-- SECURITY: chỉ chạy khi cache cho đi tiếp
           |
           '-- target
```

Nếu cache hit và security advice thực sự nằm trong cache interceptor, kiểm tra quyền đó **có thể bị bỏ qua**. Đây là một rủi ro nghiêm trọng nếu kết quả cache phụ thuộc thông tin nhạy cảm và quyền có thể thay đổi.

Không nên kết luận rằng mặc định Spring Security method interceptor luôn nằm ở vị trí này hay vị trí kia nếu chưa kiểm tra phiên bản/config thực tế; Spring Security có cơ chế interceptor và thứ tự riêng. Khi cần bảo đảm phân quyền ở **mọi request**, nên đặt ranh giới authorize tại một điểm không bị cache short-circuit, như filter/web security hoặc service facade được gọi trước bean cacheable, và viết integration test có cả cache hit.

Bên cạnh thứ tự, **cache key và scope** phải phân biệt mọi ngữ cảnh ảnh hưởng kết quả (user, tenant, role, locale...). Nhưng chỉ thêm user ID vào key **không thay thế** việc kiểm tra quyền mỗi request.

### Audit có thể bị mất dù dữ liệu trả đúng

Nếu audit/metering advice nằm trong cache advice, cache hit không vào audit. Hệ quả:

- Có thể **thiếu log** truy cập thực tế trên các lượt hit.
- Có thể **thiếu phép đo** số lần gọi API nếu chỉ đo thân method.
- Có thể khiến logic đếm/giới hạn sử dụng thực thi không đầy đủ nếu đặt sai chỗ.

Hãy tách **truy cập người dùng** khỏi **thao tác truy vấn tốn kém**: đo API/request ở ranh giới ngoài cache; đo database computation ở điểm bên trong cache. Hai loại metric trả lời hai câu hỏi khác nhau.

## 9. Thứ tự với retry và exception

Một retry advice có thể gọi `proceed()` nhiều lần, còn cache advice có thể không gọi `proceed()` khi hit. Cách lồng chúng quyết định hành vi.

### 9.1. Retry ngoài cache

```text
RETRY outer
    '-- CACHE inner
          '-- target
```

Một lỗi từ method hoặc cache layer (tùy loại lỗi được retry) có thể khiến retry advice gọi vào cache advice lần tiếp theo. Nếu lần đầu đã tạo entry thành công trước khi một tầng ngoài báo lỗi, lượt thử lại có thể hit thay vì chạy method. Vì vậy không nên đồng nhất "retry" với "method sẽ chạy lại" trong mọi trường hợp.

### 9.2. Cache ngoài retry

```text
CACHE outer
    '-- RETRY inner
          '-- target
```

Ở cache hit, retry advice hoàn toàn không chạy. Ở miss, retry advice có thể thử method nhiều lần; khi hoàn thành bình thường, cache advice mới có thể ghi kết quả. Nếu tất cả lần thử đều ném exception, `@Cacheable` mặc định không có giá trị trả về thành công để lưu.

### 9.3. Bắt và chuyển exception

Một `@Around` advice có thể bắt exception từ method rồi **trả fallback bình thường**. Nếu fallback được trả cho cache advice nằm ngoài, caching operation có thể xem đó là kết quả thành công và **lưu fallback** (nếu không bị `unless` veto). Nếu caching nằm bên trong advice xử lý fallback, nó có thể chỉ thấy exception và không lưu được fallback theo cách đó.

Do đó, cần kiểm thử cả:

- Lời gọi thành công, miss rồi hit.
- Exception xuất hiện trước khi method trả kết quả.
- Retry sau lỗi transient.
- Fallback trả giá trị bình thường.
- Cache backend lỗi tại `get`/`put`.
- Thao tác có side effect không idempotent.

Không bật retry cho lệnh ghi chỉ vì “cache có thể lỗi”: việc method đã hoàn thành nhưng `cache.put` ném exception có thể khiến retry advice gọi lại toàn bộ thao tác và tạo side effect lặp.

## 10. Cần lưu ý gì với `@Async` và reactive?

`@Async` là một kiểu method interception khác: phần việc có thể chuyển sang thread/executor và trả handle ngay, vì vậy việc quan sát “trước/sau” bằng log phải phân biệt **lúc schedule**, **lúc hoàn tất tác vụ** và **lúc kết quả sẵn sàng**. Thứ tự cache/async advice ảnh hưởng việc chọn thread chạy cache lookup và khi nào kết quả được ghi.

Với `CompletableFuture` và các return type reactive được Spring Cache hỗ trợ từ Spring Framework 6.1+, caching có thể được điều chỉnh theo **giá trị tạo ra khi hoàn tất** thay vì hiểu đơn giản toàn bộ hành vi như một method đồng bộ. Cần kiểm tra phiên bản Spring, cache provider hỗ trợ async retrieval/put và loại return type.

Không dùng sơ đồ synchronous `proceed() -> return value -> cache.put` như một cam kết đầy đủ cho mọi method asynchronous. Với hệ thống có `@Async`, dùng test xác nhận thread, thời điểm interceptor, entry visibility và hành vi khi future thất bại.

## 11. Các ranh giới của order: khi nào `@Order` không giúp?

### 11.1. Self-invocation

Trong proxy mode mặc định:

```java
@Service
public class BookService {
    public String wrapper(String id) {
        return this.load(id); // không đi qua proxy từ lời gọi nội bộ
    }

    @Cacheable("books")
    public String load(String id) {
        return "book:" + id;
    }
}
```

*Đoạn trên minh họa, chưa phải project độc lập.*

Lời gọi `this.load(id)` bỏ qua proxy; **cache advice và các proxy advice khác có thể không được kích hoạt**, bất kể order của chúng. Điều chỉnh `@EnableCaching(order=...)` không giải quyết self-invocation. Cách đơn giản là gọi method cacheable trên một Spring bean khác thông qua injection. Các chế độ AspectJ weaving có quy tắc khác và cần cấu hình riêng.

### 11.2. Method không được intercept

Khi object được tạo bằng `new` ngoài Spring context, hoặc method có visibility/`final`/proxy đặc biệt khiến advice không intercept được, thứ tự cũng không có tác dụng. Hãy kiểm tra bean thực sự được quản lý, proxy mode, cấu hình AOP và method signature.

### 11.3. Pointcut không match

Một aspect `@Around("execution(* ...BookService.load(..))")` không chạy trên method khác dù `@Order` của nó là số nhỏ nhất. `@Order` chỉ so sánh **những advice thực sự áp dụng tại cùng join point**.

### 11.4. Nhiều advice không có thứ tự rõ ràng

Các advice/aspect có cùng mức order hoặc không thể so sánh ưu tiên có thể có thứ tự không ổn định theo kỳ vọng của tác giả. Nếu kết quả phụ thuộc thứ tự, cần ấn định rõ giá trị phân biệt và test; không dùng thứ tự dòng annotation, tên class theo alphabet hay kinh nghiệm từ một lần chạy.

### 11.5. `@Order` không quyết định thứ tự tất cả sự kiện hệ thống

Thứ tự giữa advice trên một lời gọi proxy khác với thứ tự commit transaction, consumer message, callback async, cache backend replication, concurrent request hay distributed lock. `@EnableCaching(order)` **không** bảo đảm tính nguyên tử hoặc đồng bộ xuyên node.

## 12. Kiểm thử để chứng minh thứ tự trong ứng dụng

Chỉ đọc annotation là chưa đủ khi có nhiều auto-configuration, advisor do thư viện tạo hoặc proxy mode khác nhau.

### 12.1. Test hành vi ở cả cache hit và miss

Một integration test tốt nên:

1. Khởi tạo Spring context thật với cùng cấu hình AOP/cache của application.
2. Xóa cache trước từng test để xác định lượt đầu là miss.
3. Gọi một method cacheable từ **bean khác** qua dependency injection.
4. Ghi lại số lượt chạy method, audit aspect, transaction interceptor hoặc metric aspect.
5. Gọi lần thứ hai cùng key và kiểm tra advice nào chạy ở hit.
6. Đổi order có chủ đích trong một cấu hình test khác rồi so sánh, không phụ thuộc thứ tự mặc định.
7. Nếu có transaction, đo trạng thái transaction **thật** trong advisor/method và kiểm tra commit/rollback, không chỉ đọc log.

Ví dụ assertion ý tưởng cho demo ở mục 6:

```text
Config: OuterAspect order=0; Cache order=100; InnerAspect order=200

Miss:
  outerCalls=1, innerCalls=1, methodCalls=1
Hit:
  outerCalls=2, innerCalls=1, methodCalls=1
```

Hai lần gọi cùng key nhưng chỉ một lần chạy inner/method là bằng chứng cache advice nằm bên ngoài inner aspect.

### 12.2. Đọc advisor chain khi cần debug

Khi chạy trong proxy mode, có thể kiểm tra đối tượng có implement `Advised` và in các advisor ở môi trường phát triển:

```java
import org.springframework.aop.framework.Advised;
import org.springframework.aop.Advisor;

if (service instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor);
    }
}
```

*Đoạn này cần đặt trong code đã có biến `service` là một Spring bean; không phải một file Java độc lập.*

Đây là một công cụ **chẩn đoán**, không nên dùng string representation của advisor như hợp đồng API bền vững. Việc proxy có expose `Advised` và cấu trúc cụ thể phụ thuộc chế độ proxy và cấu hình. Hãy ưu tiên **test hành vi** vì nó xác nhận trực tiếp cache hit/miss và các side effect thực tế.

### 12.3. Checklist khi đổi order trong production

- **Mục tiêu thay đổi là gì?** Logging mọi request, giảm mở transaction khi hit, hay bảo đảm authorization?
- **Advice nào phải chạy mọi lần?** Đặt ngoài cache hoặc đưa sang boundary khác không bị cache skip.
- **Advice nào chỉ cần khi miss?** Có thể đặt trong cache khi ngữ nghĩa phù hợp.
- **Có transaction/commit path không?** Xem rủi ro ghi cache trước commit và error handling.
- **Retry có thể nhân side effect không?** Xem cả lỗi method lẫn lỗi cache backend.
- **Có async/reactive không?** Test thời điểm và thread thực tế.
- **Có tự gọi method trong cùng bean không?** Fix proxy boundary trước khi xét order.
- **Các advisor có order trùng nhau không?** Cấu hình tường minh khi thứ tự là yêu cầu đúng đắn.

## 13. Những sai lầm phổ biến

1. **Hiểu số `@Order` lớn hơn nghĩa là chạy trước.** Trong Spring AOP, giá trị thấp hơn có ưu tiên cao hơn và bao ngoài trên đường vào.
2. **Cho rằng advice nào cũng chạy trên cache hit.** `@Cacheable` có thể trả ngay và bỏ qua tất cả advice nằm bên trong.
3. **Cho rằng tất cả @Around chạy song song.** Chúng lồng nhau theo chuỗi `proceed()`, không đồng thời theo mặc định.
4. **Dựa vào vị trí dòng `@Cacheable` trước hay sau `@Transactional`.** Thứ tự nguồn code không quyết định precedence của advisor.
5. **Không cấu hình order nhưng suy ra cache luôn ngoài transaction.** Cả hai thường có default `LOWEST_PRECEDENCE`; khi order quan trọng cần cấu hình tường minh và kiểm chứng.
6. **Đặt phân quyền động phía trong cache rồi dùng cache key duy nhất.** Cache hit có thể bỏ qua kiểm tra quyền; dữ liệu người dùng/tenant cũng có nguy cơ trộn nếu key/scope sai.
7. **Đặt access audit phía trong cache và tưởng mọi lượt truy cập đều được ghi.** Lượt hit có thể không vào audit; đo request ở boundary ngoài cache.
8. **Cho rằng cache order quyết định TTL hoặc freshness.** Order chỉ sắp xếp AOP advisors; TTL/invalidation là vấn đề khác.
9. **Cố sửa self-invocation bằng đổi order.** Lời gọi nội bộ không đi qua proxy nên order không thể cứu.
10. **Retry toàn bộ method ghi sau lỗi cache put.** Method có thể đã commit side effect trước khi cache backend throw.
11. **Bỏ qua khác biệt `@CachePut` và `@Cacheable`.** Put vẫn chạy method; Cacheable hit mới có thể dừng chuỗi.
12. **Sử dụng sơ đồ đồng bộ cho async future/reactive mà không kiểm tra phiên bản.** Cơ chế hoàn tất/lookup và scheduler có thể khác.
13. **Đo advice bằng một lần miss duy nhất.** Phải kiểm tra cả miss, hit, exception và các condition bypass mới thấy hiệu quả order.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Một aspect có `@Order(10)`, một aspect khác có `@Order(100)`. Aspect nào ở ngoài khi cả hai áp dụng cùng join point?

**Đáp án:** Aspect có `@Order(10)` có precedence cao hơn và chạy trước trên đường vào; nếu cả hai gọi `proceed()`, aspect order 100 kết thúc trước trên đường ra.

**Câu 2.** `@EnableCaching(order=50)` và audit `@Order(100)` cùng áp dụng cho method `@Cacheable`. Khi cache hit, audit có chắc chạy?

**Đáp án:** Không. Cache advice order 50 có ưu tiên cao hơn và bao ngoài; tại hit có thể trả luôn, không gọi phần chain chứa audit order 100.

**Câu 3.** `@EnableCaching(order=100)` và audit `@Order(0)`. Khi cache hit audit có chạy không?

**Đáp án:** Trong cấu trúc ví dụ, có: audit bao ngoài cache; lời gọi đã tới audit và audit gọi `proceed()` để cache trả kết quả. Còn các advice nằm phía trong cache có thể bị skip.

**Câu 4.** Method có `@Cacheable` và `@Transactional`, cả hai sử dụng order mặc định. Có thể kết luận transaction luôn chỉ mở khi cache miss không?

**Đáp án:** Không. Phải xác định precedence thực tế của hai advisor; nếu transaction nằm ngoài cache, cache hit vẫn đi qua transaction advice.

**Câu 5.** Một method `@CachePut` ném exception trước khi return. Có cache kết quả mới và chạy mọi advice phía trong hay không?

**Đáp án:** `@CachePut` không có result bình thường để put. Advice phía trong **có thể đã chạy** cho đến điểm exception, nếu invocation thực sự đi qua chúng; khi unwind, nhánh `catch`/`finally` của advice thích hợp sẽ xử lý theo code.

**Câu 6.** Một phương thức cacheable được gọi bằng `this.find(...)` từ method cùng bean. Thêm `@EnableCaching(order=-100)` có sửa được không?

**Đáp án:** Không. Self-invocation bypass proxy trong mode mặc định; cần sửa ranh giới lời gọi hoặc chọn cơ chế interception khác.

**Câu 7.** Nếu cần transaction commit xong mới cập nhật cache, chỉ đặt `@EnableCaching(order=...)` đã đủ bảo đảm consistency mọi tình huống chưa?

**Đáp án:** Chưa. Order có thể thay đổi vị trí cache advice so với transaction advice, nhưng còn timing, rollback, backend failure, concurrency và distributed consistency. Có thể cần transaction-aware cache/invalidation sau commit và integration test.

## Tài liệu tham khảo

- Spring Framework Reference — *Declarative Annotation-based Caching*, cấu hình `order` và cache proxy: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `@EnableCaching`, thuộc tính `order` và mặc định `Ordered.LOWEST_PRECEDENCE`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/EnableCaching.html
- Spring Framework Reference — *Declaring Advice*, phần *Advice Ordering*: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework Reference — *Proxying Mechanisms* và self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Javadoc — `@EnableTransactionManagement`, thuộc tính `order`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html
- Spring Framework Reference — *Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Boot Reference — *Caching*: https://docs.spring.io/spring-boot/reference/io/caching.html
