# NoOpCacheManager khi cần chủ động bỏ qua lưu trữ

> **Bối cảnh:** Spring Framework Cache — nhóm **Chọn vùng cache**. `NoOpCacheManager` là một triển khai `CacheManager` có chủ đích **không lưu dữ liệu cache**. Nó hữu ích khi muốn giữ nguyên cấu trúc Spring Cache và các annotation nhưng tạm thời không tái sử dụng kết quả của những lần gọi trước.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cơ chế của `NoOpCacheManager` và `NoOpCache` trong Spring Cache.
2. Phân biệt **không lưu cache**, **không bật Spring Cache**, và **dùng cache trong bộ nhớ**.
3. Dự đoán số lần thân phương thức `@Cacheable` được thực thi khi dùng no-op manager so với `ConcurrentMapCacheManager`.
4. Chọn đúng cách cấu hình trên Spring Boot (`spring.cache.type=none`) hoặc Spring Framework thuần (khai báo bean `NoOpCacheManager`).
5. Viết thí nghiệm Java 17 và kiểm thử JUnit xác nhận no-op luôn miss, không giữ giá trị vừa put, đồng thời nhận diện những rủi ro nếu vô tình dùng no-op ở production.

## 2. CacheManager có nhiệm vụ gì?

Spring Cache là lớp trừu tượng (cache abstraction), không gắn chặt với Redis, Caffeine hay một bộ lưu trữ cụ thể.

```text
Client → Spring-managed bean
             |
             v
       Cache interceptor
             |
             v
         CacheManager
             |
             +-- ConcurrentMapCacheManager → lưu map trong JVM
             +-- CaffeineCacheManager -----→ cache trong JVM
             +-- RedisCacheManager --------→ Redis server
             +-- NoOpCacheManager ---------→ không lưu giá trị nào
```

- `CacheManager` cung cấp các `Cache` theo tên qua `getCache(name)` và báo những tên cache đã biết qua `getCacheNames()`.
- `Cache` cung cấp các thao tác như `get(key)`, `put(key, value)`, `evict(key)` và `clear()`.
- Spring Cache interceptor quyết định khi nào tra cache, thực thi phương thức, lưu hoặc xóa mục dựa trên các annotation `@Cacheable`, `@CachePut` và `@CacheEvict`.
- Provider/adapter quyết định **hành vi lưu trữ thực tế**. Hai manager có cùng API nhưng tác động hoàn toàn khác nhau.

**Ý chính:** không nên suy luận một annotation đồng nghĩa dữ liệu chắc chắn được giữ lại. Muốn biết dữ liệu có được tái sử dụng hay không phải xem `CacheManager` thực tế.

## 3. NoOpCacheManager hoạt động ra sao?

`NoOpCacheManager` nằm trong package:

```java
import org.springframework.cache.support.NoOpCacheManager;
```

Nó cung cấp các đối tượng `NoOpCache` có tên, nhưng không có bộ lưu trữ dữ liệu bên dưới. Với một cache no-op:

- `get(key)` trả về trạng thái không tìm thấy mục — **cache miss**.
- `put(key, value)` không giữ lại giá trị được đưa vào.
- `evict(key)` và `clear()` không có dữ liệu thực sự để xóa.
- Mỗi lần dùng `@Cacheable` với cùng key, interceptor không có kết quả cũ để trả, nên bình thường **thân phương thức chạy lại**.
- `NoOpCacheManager` vẫn đáp ứng hợp đồng cung cấp cache, nên việc sử dụng tên cache không đồng nghĩa một cache dữ liệu thực được tạo.

Tương tác điển hình:

```text
Lần gọi đầu: service.load("A")
  NoOpCache.get("A") → miss
  thực thi service.load → kết quả A-1
  NoOpCache.put("A", A-1) → bỏ qua
  trả A-1

Lần gọi sau: service.load("A")
  NoOpCache.get("A") → miss (vẫn không có A-1)
  thực thi service.load → kết quả A-2
  NoOpCache.put("A", A-2) → bỏ qua
  trả A-2
```

Trong sơ đồ này, `A-1` và `A-2` được dùng để làm rõ hai lần tính toán, **không phải** biểu hiện lỗi dữ liệu. Trong một hàm đọc bất biến thực tế, hai lần xử lý có thể trả cùng giá trị nhưng vẫn tốn hai lần CPU, I/O hoặc truy vấn nguồn.

### Phân biệt “không lưu” với “không có bean cache”

Dùng `NoOpCacheManager` **không giống** việc không cấu hình `CacheManager`. Khi Spring Cache đã được bật, framework vẫn có một manager hợp lệ và một đối tượng cache tương ứng để xử lý đường đi annotation. Nếu thay bằng một manager cấu hình sai hoặc không biết cache name, ứng dụng có thể ném lỗi không resolve được cache. No-op tránh việc cần một kho lưu trữ nhưng **không loại bỏ toàn bộ cơ chế interception**.

## 4. Khi nào nên chủ động chọn NoOpCacheManager?

### 4.1. Môi trường kiểm thử cần chạy logic thật

Một test cần đo số lần gọi repository hoặc xác minh business logic ở **mỗi lần gọi** có thể bị cache hit che bớt lần chạy. No-op giúp mọi lần gọi `@Cacheable` được tính lại để test nhìn thấy logic thực tế.

Ví dụ: nếu kiểm thử chỉ muốn xác minh service gọi downstream đúng hai lần khi client gọi hai lần, dùng no-op sẽ tránh cache hit khiến downstream chỉ bị gọi một lần. Tuy nhiên **đừng dùng no-op trong test có mục tiêu chứng minh cache hit, TTL, eviction hoặc concurrency**; các test đó cần provider phù hợp và kết quả kỳ vọng khác.

### 4.2. Môi trường dev hoặc điều tra lỗi

Khi cần tách ảnh hưởng của cache khỏi hành vi nguồn dữ liệu, no-op tạo một đối chứng hữu ích: nếu lỗi chỉ xuất hiện khi bật cache thực, có thể cần xem lại key, invalidation, serialization hoặc TTL. Đây là công cụ chẩn đoán, không phải cách giải quyết vĩnh viễn.

### 4.3. Vô hiệu hóa tính năng cache theo môi trường

Ứng dụng có thể chọn no-op cho một môi trường đặc biệt trong khi giữ annotation và code nghiệp vụ giống nhau. Điều này giúp thay cấu hình mà không sửa từng `@Cacheable`; trong Spring Boot, cách tiện nhất thường là đặt `spring.cache.type=none` khi cache được auto-configure.

### 4.4. Fallback khi chủ ý chấp nhận không cache

Nếu chi phí tính toán thấp và việc không lưu được xem là hành vi chấp nhận được, no-op có thể là lựa chọn tạm thời. Nhưng nó **không phải** cơ chế tự chuyển đổi cache hỏng sang nguồn dữ liệu an toàn với bất kỳ provider nào; muốn có fail-open/fail-closed khi Redis lỗi còn cần thiết kế `CacheErrorHandler`, timeout và kiểm soát tác động lên backend.

## 5. So sánh với các cách quản lý cache khác

| Cách triển khai | Lưu giá trị? | Lần gọi cùng key thứ hai | Phù hợp |
| --- | --- | --- | --- |
| `NoOpCacheManager` | Không | Miss; thường chạy lại thân `@Cacheable` | Test không muốn cache, chẩn đoán, cấu hình có chủ đích |
| `ConcurrentMapCacheManager` | Có, trong map của JVM | Hit nếu mục vẫn còn | Demo, test hit/miss đơn giản |
| `CaffeineCacheManager` | Có, trong JVM; hỗ trợ eviction/expiration | Hit nếu mục còn hợp lệ | Cache local với chính sách dung lượng và TTL |
| `RedisCacheManager` | Có, trong Redis server | Hit nếu mục tồn tại và kết nối thành công | Dùng chung cache giữa nhiều instance |
| Không bật `@EnableCaching` | Không có annotation caching được áp dụng | Phương thức gọi trực tiếp theo luồng Java thông thường | Hệ thống không cần xử lý annotation cache |

**Chú ý:** một cache miss không nhất thiết là “không có caching trong ứng dụng”. Với no-op, Spring vẫn thực hiện một phần đường đi của cache abstraction; nó chỉ **không lưu giá trị để hit ở lần sau**.

`NoOpCacheManager` cũng **không giống** `NullValue` hoặc negative caching. Null-value caching có thể chủ ý lưu kết quả “không tìm thấy” để tránh gọi nguồn lặp lại. No-op không giữ cả giá trị bình thường lẫn trạng thái “không tìm thấy”.

## 6. Spring Boot: cấu hình không lưu cache bằng property

Trong ứng dụng Spring Boot đã có hạ tầng Spring Cache, đặt:

```properties
spring.cache.type=none
```

Hoặc YAML:

```yaml
spring:
  cache:
    type: none
```

Khi **Spring Boot được phép auto-configure `CacheManager`**, lựa chọn `none` khiến Boot dùng no-op cache manager thay vì provider lưu trữ được nhận diện tự động. Tài liệu Spring Boot chính thức giới thiệu cách này cho môi trường cần vô hiệu hóa lưu cache và cho các bài kiểm thử.

Ví dụ một service vẫn có annotation:

```java
@Service
public class PriceService {
    @Cacheable(cacheNames = "prices", key = "#p0")
    public int calculatePrice(String sku) {
        return expensiveCalculation(sku);
    }
}
```

Đây là **đoạn mã minh họa**, thiếu triển khai `expensiveCalculation` nên chưa phải chương trình độc lập. Khi `spring.cache.type=none` có hiệu lực và caching được bật, cùng một `sku` gọi nhiều lần sẽ không lấy kết quả đã lưu trước đó; logic tính giá vẫn được gọi lại.

### Điều kiện quan trọng của cấu hình Boot

- `spring-boot-starter-cache` cung cấp các thành phần tích hợp cần thiết; `@EnableCaching` kích hoạt annotation caching.
- Thuộc tính `spring.cache.type=none` có tác dụng theo **nhánh auto-configuration của Boot**. Nếu ứng dụng đã tự khai báo bean `CacheManager` hoặc `CacheResolver` phù hợp, auto-config có thể lùi lại; chỉ thêm property **không tự thay thế** bean người dùng.
- Nếu đang dùng nhiều provider, đừng đoán từ classpath; kiểm tra bean `CacheManager` thực tế bằng type.
- Đừng coi `spring.cache.type=none` như switch loại bỏ mọi hoạt động proxy/AOP hay tất cả code liên quan đến key/SpEL. Nó chọn một provider không lưu; các kiểm tra annotation và expression vẫn có thể được thực hiện.
- Nếu muốn dùng no-op chỉ trong test, có thể đặt property ở cấu hình test riêng, ví dụ `src/test/resources/application.properties`, hoặc truyền qua `@SpringBootTest(properties = "spring.cache.type=none")` trong test toàn context. Các auto-configuration hỗ trợ kiểm thử khác có thể thay manager theo phiên bản Boot, vì vậy nên kiểm tra type thực tế.

Một cấu hình không nên được công bố là đã vô hiệu hóa lưu cache trước khi kiểm chứng rằng bean đang dùng là `NoOpCacheManager`.

## 7. Spring Framework thuần: tạo bean NoOpCacheManager

Nếu không dùng Spring Boot auto-configuration, tạo trực tiếp bean `CacheManager`:

```java
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.support.NoOpCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfig {

    @Bean
    public CacheManager cacheManager() {
        return new NoOpCacheManager();
    }
}
```

Đây là **class cấu hình để đặt trong một dự án có Spring ApplicationContext**, không có `main`. `NoOpCacheManager` thuộc module `spring-context`.

Với Spring Framework thuần, Spring không đọc `spring.cache.type` để tự chuyển bean; muốn đổi provider phải thay bean, dùng một profile phù hợp hoặc một cấu hình có điều kiện do ứng dụng tự định nghĩa.

### Chọn bean theo Spring profile

Một ví dụ minh họa:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheProfiles {

    @Bean
    @Profile("no-cache")
    CacheManager noOpCacheManager() {
        return new NoOpCacheManager();
    }

    @Bean
    @Profile("!no-cache")
    CacheManager normalCacheManager() {
        return new ConcurrentMapCacheManager("prices");
    }
}
```

Đây là **đoạn cấu hình minh họa**, cần import `CacheManager`, `NoOpCacheManager`, `ConcurrentMapCacheManager`, `Bean`, `Configuration`, `Profile` và `EnableCaching`. Chỉ một trong hai bean được đăng ký theo profile. Khi triển khai thật, provider bình thường có thể là Redis/Caffeine thay vì Simple. Đừng vô tình để cả hai `CacheManager` cùng active mà không có quy tắc chọn bean rõ ràng.

**Cảnh báo vận hành:** đặt no-op profile ở production chỉ khi đã đánh giá tải tăng lên database, API, I/O và CPU. Không có cache hit nghĩa là mọi lời gọi lặp có thể phải truy cập lại nguồn.

## 8. Ví dụ hoàn chỉnh chạy được bằng Java 17

Thí nghiệm dưới đây tạo **hai ApplicationContext độc lập** với cùng một service:

1. Một context dùng `NoOpCacheManager`.
2. Một context dùng `ConcurrentMapCacheManager`.

Cả hai đều bật `@EnableCaching`; chỉ provider khác nhau. Nhờ vậy có thể quan sát sự khác biệt của no-op bằng số lần thân method thực thi thay vì chỉ đo thời gian.

### 8.1. Cấu trúc dự án

```text
noop-cache-demo/
├── pom.xml
└── src/
    ├── main/java/demo/cache/NoOpCacheDemo.java
    └── test/java/demo/cache/NoOpCacheDemoTest.java
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>noop-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.1</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.cache.NoOpCacheDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` có các lớp Spring Cache và bộ quản lý cache Simple/no-op; nó cũng kéo các module Spring cần thiết theo dependency. Ví dụ dùng Spring Framework 6.2.1 tương thích Java 17 để dễ tái tạo. Trong ứng dụng Spring Boot thật, nên quản lý phiên bản Spring qua BOM/parent thay vì ép từng module độc lập.

### 8.3. `src/main/java/demo/cache/NoOpCacheDemo.java`

```java
package demo.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.support.NoOpCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class NoOpCacheDemo {

    public static class CalculationService {
        private final AtomicInteger executions = new AtomicInteger();

        @Cacheable(cacheNames = "calculations", key = "#p0")
        public String calculate(String key) {
            int count = executions.incrementAndGet();
            return key + "-run" + count;
        }

        public int executionCount() {
            return executions.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class NoOpConfig {
        @Bean
        public CacheManager cacheManager() {
            return new NoOpCacheManager();
        }

        @Bean
        public CalculationService calculationService() {
            return new CalculationService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class SimpleConfig {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("calculations");
        }

        @Bean
        public CalculationService calculationService() {
            return new CalculationService();
        }
    }

    private static void scenario(String label, Class<?> configType) {
        try (var context =
                     new AnnotationConfigApplicationContext(configType)) {

            CacheManager manager = context.getBean(CacheManager.class);
            CalculationService service =
                    context.getBean(CalculationService.class);

            System.out.println(label + " manager="
                    + manager.getClass().getSimpleName());
            System.out.println(label + " first="
                    + service.calculate("A"));
            System.out.println(label + " second="
                    + service.calculate("A"));
            System.out.println(label + " executions="
                    + service.executionCount());
        }
    }

    public static void main(String[] args) {
        scenario("no-op", NoOpConfig.class);
        scenario("simple", SimpleConfig.class);
    }
}
```

**Tại sao đây là phép so sánh công bằng?**

- Cùng một method `CalculationService.calculate("A")` và cùng key `A`.
- Hai context đều có `@EnableCaching`, nên chỉ **lựa chọn CacheManager** là khác.
- `@Cacheable` đặt trên public method của bean Spring; client lấy bean qua `context.getBean(...)` để lời gọi đi qua proxy.
- Bộ đếm `AtomicInteger` đặt **bên trong** thân method, nên không tăng ở lần cache hit.
- Mỗi context có service mới, bộ đếm bắt đầu từ 0, cache ban đầu trống.
- Chuỗi kết quả chứa số lần chạy để không thể nhầm lượt client gọi với lượt thực thi thật.

### 8.4. Lệnh chạy

Tại thư mục `noop-cache-demo`, cần Java 17+, Maven 3.9+ và truy cập Maven Central ở lần tải dependency đầu:

```bash
java -version
mvn -q compile exec:java
```

Các dòng **do chính chương trình in ra**, không tính log Maven hoặc thông báo khởi tạo của Spring:

```text
no-op manager=NoOpCacheManager
no-op first=A-run1
no-op second=A-run2
no-op executions=2
simple manager=ConcurrentMapCacheManager
simple first=A-run1
simple second=A-run1
simple executions=1
```

Giải thích:

1. **No-op:** lần thứ nhất miss, tính `A-run1` nhưng `put` không lưu. Lần thứ hai vẫn miss, tính `A-run2`. Hai lần client gọi dẫn đến hai lần thân method chạy.
2. **Simple:** lần thứ nhất miss, tính `A-run1` và lưu vào `ConcurrentMapCache`. Lần thứ hai hit, nhận lại `A-run1` mà không chạy thêm thân method.
3. Cùng một mã Java, chỉ đổi CacheManager đã tạo hành vi khác nhau. Đây là bằng chứng trực tiếp về **bỏ qua lưu trữ**, không phải chỉ suy luận từ tên lớp.

Lệnh `mvn -q compile exec:java` chạy ứng dụng qua Maven plugin. Nếu chỉ dùng `javac`/`java` trực tiếp, bạn cần cung cấp đầy đủ các JAR Spring trong classpath; Maven ở đây quản lý việc đó.

## 9. Kiểm thử JUnit: xác nhận no-op không giữ giá trị

Tạo `src/test/java/demo/cache/NoOpCacheDemoTest.java`:

```java
package demo.cache;

import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class NoOpCacheDemoTest {

    @Test
    void noOpAlwaysRecalculatesAndDoesNotStore() {
        try (var context = new AnnotationConfigApplicationContext(
                NoOpCacheDemo.NoOpConfig.class)) {

            var service = context.getBean(
                    NoOpCacheDemo.CalculationService.class);

            Cache cache = Objects.requireNonNull(
                    context.getBean(CacheManager.class)
                            .getCache("calculations")
            );

            assertEquals("A-run1", service.calculate("A"));
            assertNull(cache.get("A"));

            assertEquals("A-run2", service.calculate("A"));
            assertEquals(2, service.executionCount());
            assertNull(cache.get("A"));
        }
    }

    @Test
    void simpleCacheSkipsSecondExecution() {
        try (var context = new AnnotationConfigApplicationContext(
                NoOpCacheDemo.SimpleConfig.class)) {

            var service = context.getBean(
                    NoOpCacheDemo.CalculationService.class);

            assertEquals("A-run1", service.calculate("A"));
            assertEquals("A-run1", service.calculate("A"));
            assertEquals(1, service.executionCount());
        }
    }
}
```

Chạy:

```bash
mvn -q test
```

Kết quả mong đợi: JUnit tests thành công, Maven trả exit code 0. Với tùy chọn `-q`, không bắt buộc có dòng “BUILD SUCCESS” trên console. Lệnh chạy không dùng Redis hay database.

**Vì sao test này có giá trị?**

- `assertNull(cache.get("A"))` xác nhận no-op vẫn miss **sau khi `@Cacheable` đã chạy và cố đưa kết quả vào cache**.
- `executionCount() == 2` xác nhận thân phương thức chạy lại dù client gọi cùng key.
- Test so sánh với Simple cache xác nhận hành vi hit thực sự khi provider có lưu dữ liệu.
- Mỗi test tạo context riêng, tránh phụ thuộc trạng thái cache trong test khác.

Nếu mục tiêu của test là xác minh TTL, invalidation hoặc hit/miss trên Redis/Caffeine, không nên thay provider cần kiểm thử bằng no-op rồi coi kết quả là tương đương.

## 10. Các annotation khác khi dùng NoOpCacheManager

### 10.1. @Cacheable

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) {
    return repository.find(id);
}
```

Đây là phương thức minh họa trong một bean có repository. Khi manager no-op có hiệu lực, các lần gọi cùng key không tìm thấy kết quả cũ, nên body vẫn được thực thi theo đường miss. Nếu phương thức trả object mutable, no-op cũng không bảo tồn bản sao hay trạng thái của object đó.

### 10.2. @CachePut

```java
@CachePut(cacheNames = "products", key = "#p0")
public Product refresh(String id) {
    return repository.loadFresh(id);
}
```

Theo ngữ nghĩa của `@CachePut`, method được chạy và framework yêu cầu put kết quả vào cache. Với `NoOpCache`, thao tác put không lưu gì; lần đọc sau qua `@Cacheable` vẫn miss. Không dùng no-op để kiểm thử rằng một kết quả được lưu thành công.

### 10.3. @CacheEvict

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void remove(String id) {
    repository.delete(id);
}
```

Nghiệp vụ `repository.delete(id)` vẫn phải chạy nếu method được gọi bình thường; eviction lên no-op cache không có mục thực để xóa. Do đó việc có `@CacheEvict` không tự bảo đảm một cache ở provider khác hoặc instance khác cũng đã bị xóa.

Ba đoạn trên là **các ví dụ annotation trong một ứng dụng đã có repository và các domain class tương ứng**, không phải tệp Java độc lập có thể copy chạy.

## 11. No-op không đồng nghĩa vô hiệu hóa hoàn toàn cache interception

Đây là một hiểu nhầm quan trọng:

- **Dùng NoOpCacheManager:** ứng dụng vẫn có bean `CacheManager` và có thể vẫn đi qua advice của Spring Cache. Những biểu thức `key`, `condition`, `unless` và các thao tác annotation có thể vẫn được đánh giá theo đường xử lý; vì vậy no-op không bảo đảm loại bỏ mọi overhead hoặc mọi lỗi SpEL.
- **Không bật `@EnableCaching`:** annotation `@Cacheable` không được Spring tự động áp dụng trong một context không cấu hình caching. Method được gọi theo cơ chế Java thông thường. Điều này không đồng nghĩa mọi thư viện cache hoặc lời gọi cache thủ công khác cũng tự tắt.
- **Gọi method qua `this.method()` trong cùng bean (self-invocation):** ở proxy mode mặc định, lời gọi nội bộ có thể bỏ qua interceptor dù manager thực tế là Redis/Caffeine. Nó không phải bằng chứng manager no-op.

Nếu cần đo đúng tình huống, log class của `CacheManager` và kiểm tra số lần body chạy. Đừng kết luận “cache đã tắt” chỉ từ một lần miss.

### Rủi ro của fallback no-op trong CompositeCacheManager

`CompositeCacheManager` có thể tìm cache qua nhiều manager; tùy cấu hình, `setFallbackToNoOpCache(true)` cung cấp cache no-op cho **những tên cache không được manager trước đó xử lý**.

Điều này khác với việc chọn `NoOpCacheManager` cho **toàn bộ** ứng dụng. Fallback có thể làm lỗi cấu hình cache name bị che: thay vì fail khi viết sai tên cache, hệ thống âm thầm luôn miss và tải lại nguồn. Chỉ bật fallback khi việc không lưu cho cache chưa biết là chính sách thực sự mong muốn.

## 12. Rủi ro sản xuất và cách kiểm soát

### 12.1. Tăng lưu lượng tới nguồn dữ liệu

Giả sử 1.000 lời gọi giống nhau, tác vụ gốc 50 ms, và provider lưu cache cho tỷ lệ hit 90%:

- Cache thực có thể tránh phần lớn lượt xử lý nguồn nếu dữ liệu và khóa phù hợp.
- No-op không tránh được các lượt xử lý lặp; tải có thể tăng mạnh ở database, hệ thống downstream và CPU.

Đây là lập luận về số lượt xử lý; không nên lấy con số 50 ms hay 90% làm cam kết hiệu năng của một hệ thống cụ thể. Phải đo số lần tải nguồn và độ trễ thực tế trước khi quyết định dùng no-op trên production.

### 12.2. Thay đổi hành vi test so với production

Test dùng no-op sẽ không phát hiện các lỗi chỉ xuất hiện khi cache thực: key collisions, stale entries, TTL, serialization, cache stampede, dữ liệu bị share giữa user/tenant, eviction sai hoặc concurrent writes. Nên có **hai nhóm kiểm thử**: business logic với no-op nếu hợp lý, và cache behavior với provider thật hoặc provider tương đương.

### 12.3. Bất ngờ khi dùng @Cacheable trên method có side effect

No-op khiến body thường chạy mọi lần nên một method vừa đọc vừa có side effect có thể trông như hoạt động trong test. Khi chuyển sang cache thực, cache hit có thể bỏ qua side effect đó, gây lỗi nghiệp vụ. Thiết kế method `@Cacheable` nên không phụ thuộc vào việc luôn thực thi.

### 12.4. Khởi tạo bean và thứ tự ưu tiên cấu hình

Nếu tồn tại `@Primary`, nhiều bean `CacheManager`, `CacheResolver` tùy chỉnh hoặc cấu hình Boot auto-config khác, provider thực tế có thể không phải no-op như kỳ vọng. Đầu tiên hãy lấy `context.getBean(CacheManager.class).getClass().getName()` khi type duy nhất; nếu nhiều manager, kiểm tra resolver/qualifier thực tế.

### 12.5. Không biến no-op thành cơ chế xử lý sự cố Redis một cách tùy tiện

Nếu Redis gián đoạn, thay provider bằng no-op có thể làm số lượng request chạy xuống database tăng đột ngột. Cần tính capacity, timeout, rate limit, circuit breaker và phương án degrade cho nguồn. Việc “không lưu” là quyết định kiến trúc có chi phí, không phải lựa chọn luôn an toàn.

## 13. Checklist triển khai

1. **Mục đích:** thật sự muốn bỏ qua lưu trữ, hay muốn tắt cả annotation interception?
2. **Môi trường:** chỉ test/dev hay có production? Nếu production, tải nguồn khi hit rate xuống 0 có chấp nhận được không?
3. **Cấu hình:** ứng dụng Boot dùng `spring.cache.type=none` dưới auto-config, hay Spring Framework thuần dùng `@Bean NoOpCacheManager`?
4. **Quyền chọn provider:** có bean `CacheManager` tùy chỉnh hoặc `CacheResolver` nào lấn át cấu hình không?
5. **Xác minh:** log type manager, gọi cùng key hai lần và assert số lần thực thi body.
6. **Bảo vệ nghiệp vụ:** method đọc không phụ thuộc side effect; method ghi vẫn phải cập nhật nguồn.
7. **Kiểm thử:** dùng real cache cho test hit, TTL và eviction; no-op cho test không muốn kết quả bị tái sử dụng.
8. **Quan sát vận hành:** đo số request tới DB/API và độ trễ, tránh vô tình dùng no-op cho workload lớn.
9. **Phạm vi:** tránh `CompositeCacheManager` fallback no-op che lỗi thiếu tên cache.
10. **Chuyển môi trường:** đảm bảo profile, config map và biến môi trường chọn đúng manager khi deploy.

## 14. Câu hỏi tự luyện

**Câu 1:** Dùng `NoOpCacheManager`, gọi `@Cacheable find("A")` ba lần tuần tự, không có lớp cache nào khác. Thân method thường chạy mấy lần?  
**Đáp án:** **3 lần**, vì không có mục nào được lưu để tạo cache hit.

**Câu 2:** Trong Boot, đặt `spring.cache.type=none` nhưng đã có `@Bean CacheManager` do ứng dụng tự tạo. Có chắc provider đổi thành no-op không?  
**Đáp án:** **Không.** Cần kiểm tra điều kiện auto-configuration và bean/resolver thực tế.

**Câu 3:** No-op có phù hợp để kiểm thử rằng `@CacheEvict` xóa đúng key không?  
**Đáp án:** **Không**, vì không có mục cache thật để xóa. Hãy dùng provider có lưu và kiểm chứng trước/sau eviction.

**Câu 4:** Vì sao no-op không giống việc bỏ `@EnableCaching`?  
**Đáp án:** No-op vẫn cung cấp cache qua API và có thể tiếp tục đi qua Spring Cache interceptor; bỏ kích hoạt annotation caching khiến advice không được áp dụng trong context đó.

**Câu 5:** Tại sao test với no-op có thể bỏ sót bug của `@Cacheable` trong production?  
**Đáp án:** No-op không tạo cache hit; các bug do hit bỏ qua side effect, key sai, dữ liệu cũ hoặc invalidation thất bại chỉ lộ khi dùng provider lưu dữ liệu.

## Tài liệu chính thức

- [Spring Framework — NoOpCacheManager JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/NoOpCacheManager.html)
- [Spring Framework — NoOpCache JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/NoOpCache.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Boot — Caching, provider None và Testing](https://docs.spring.io/spring-boot/reference/io/caching.html)

**Ghi nhớ:** `NoOpCacheManager` giúp **chủ động không lưu bất kỳ mục cache nào** trong khi vẫn giữ giao diện Spring Cache. Nó là công cụ cấu hình và kiểm thử có giá trị, nhưng không tự loại bỏ annotation interception và cũng không thể dùng để xác nhận caching thực sự có hit. Muốn an toàn, hãy kiểm tra `CacheManager` được chọn và số lần thân phương thức thực thi với cùng key.