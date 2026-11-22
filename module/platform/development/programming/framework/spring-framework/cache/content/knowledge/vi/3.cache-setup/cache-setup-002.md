# Khai báo bean CacheManager trong Java configuration của Spring

> Ngữ cảnh: **Spring Framework – Cache / Thiết lập**. Bài này hướng dẫn khai báo `CacheManager` bằng `@Bean` trong lớp `@Configuration`, kích hoạt cache annotation bằng `@EnableCaching`, xác nhận cấu hình chạy đúng và tùy chọn bộ lưu cache cho ứng dụng Spring Framework thuần hoặc Spring Boot.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của `CacheManager`, `Cache`, `@Configuration`, `@Bean` và `@EnableCaching`.
2. Tự khai báo một `CacheManager` Java-based configuration mà không cần XML.
3. Sử dụng `ConcurrentMapCacheManager` để thử nghiệm, rồi chuyển sang `CaffeineCacheManager` hoặc `RedisCacheManager` khi yêu cầu thay đổi.
4. Hiểu Spring tìm bean `CacheManager` thế nào khi gọi `@Cacheable`, và xử lý trường hợp có nhiều manager.
5. Chạy một ví dụ Java 17 hoàn chỉnh, kiểm chứng cache hit/miss và nhận diện lỗi cấu hình phổ biến.

## 1. CacheManager là gì, vì sao cần khai báo bean?

Spring Cache định nghĩa một abstraction chung cho nhiều bộ lưu trữ. Hai interface quan trọng:

- `org.springframework.cache.Cache`: đại diện một cache có tên, hỗ trợ các thao tác như `get`, `put`, `evict`, `clear`.
- `org.springframework.cache.CacheManager`: quản lý, tìm một đối tượng `Cache` theo tên bằng `getCache(String name)` và liệt kê các tên qua `getCacheNames()`.

Bản thân `CacheManager` không bắt buộc lưu dữ liệu; hành vi lưu thực sự phụ thuộc implementation. Ví dụ `ConcurrentMapCacheManager` lưu trong bộ nhớ một JVM; `CaffeineCacheManager` thêm nhiều chính sách cache nội bộ; `RedisCacheManager` làm việc với Redis qua Spring Data Redis.

Dòng xử lý khi sử dụng annotation cache:

```text
Client gọi bean service do Spring quản lý
                |
                v
      Spring caching interceptor
                |
      cache name + key từ @Cacheable
                |
                v
     CacheManager.getCache(name)
                |
       +--------+--------+
       |                 |
      HIT               MISS
       |                 |
  Trả giá trị      Chạy phương thức gốc
       |                 |
       |           Đưa kết quả vào cache
       +--------+--------+
                |
           Trả kết quả
```

**Vai trò của Java configuration** là cho Spring biết implementation nào được dùng và cách cấu hình nó. Thay vì để chương trình tự `new CacheManager` trong service, ta khai báo một **Spring bean** để cache interceptor, service khác hoặc các công cụ kiểm tra cùng sử dụng.

Một điều dễ nhầm: **`@Bean` đăng ký manager, còn `@EnableCaching` kích hoạt cơ chế xử lý annotation**. Nếu chỉ có manager mà chưa bật annotation, `@Cacheable` thường không thực hiện caching.

## 2. Cấu hình tối thiểu bằng @Configuration và @Bean

Đối với ví dụ đơn giản, dùng lớp `ConcurrentMapCacheManager` có sẵn trong `spring-context`:

```java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("prices", "products");
    }
}
```

Ở đây:

- `@Configuration` đánh dấu lớp chứa định nghĩa các bean của application context.
- `@Bean` đăng ký kết quả trả về thành bean tên mặc định `cacheManager`, với kiểu công khai `CacheManager`.
- `@EnableCaching` kích hoạt hạ tầng cache annotation trong application context tương ứng.
- Constructor `ConcurrentMapCacheManager("prices", "products")` tạo danh sách cache cố định theo tên; nếu code dùng một cache name chưa khai báo, `getCache(name)` có thể trả `null` và thao tác annotated cache bị lỗi.
- `CacheManager` thường là bean singleton trong application context, được dùng chung giữa nhiều lời gọi và service.

Trong một lớp `@Configuration`, có thể viết `@Bean(name = "priceCacheManager")` để đặt tên rõ ràng. Tên bean khác với tên cache: `priceCacheManager` là tên của **manager**, còn `prices` là tên của **cache được manager quản lý**.

### Không nên nhầm các lớp và cách tạo bean

```text
Tên bean: cacheManager
  Kiểu: org.springframework.cache.CacheManager
  Hiện thực: org.springframework.cache.concurrent.ConcurrentMapCacheManager
  Các cache do bean quản lý: prices, products
```

Một manager có thể chứa nhiều cache. Một cache có thể chứa nhiều mục khác nhau phân biệt bởi key, ví dụ `prices["P42"]` và `prices["P43"]`.

`ConcurrentMapCacheManager` thích hợp cho demo, test và tác vụ nhỏ. Nó **không cung cấp TTL/giới hạn dung lượng/đồng bộ liên JVM như một hệ thống cache chuyên dụng**. Với ứng dụng production, hãy chọn provider theo mục tiêu độ trễ, dung lượng, tính nhất quán và khả năng phân phối.

## 3. Ví dụ Spring Framework thuần có thể chạy với Java 17

Ví dụ này dùng Spring Framework 6.2.0 để minh họa API đã có từ lâu, chạy với JDK 17+. Đây là phiên bản **được cố định để tái lập bài học**, không phải chỉ dẫn chọn phiên bản mới nhất cho production. Một dự án đang có Spring BOM hoặc Spring Boot nên giữ các module Spring cùng dòng phiên bản đã được quản lý.

### 3.1. Cấu trúc tệp

```text
spring-cache-manager-demo/
├── pom.xml
└── src/main/java/demo/
    ├── CacheConfig.java
    ├── PriceService.java
    └── Main.java
```

### 3.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-cache-manager-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp API/cache manager đơn giản và kéo theo các dependency Spring cần thiết cho ví dụ. Không cần Spring Boot, Caffeine, Redis hoặc một máy chủ ngoài để chạy ví dụ này.

### 3.3. src/main/java/demo/CacheConfig.java

```java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("prices");
    }
}
```

**Điểm cần để ý:** tên `prices` trong `ConcurrentMapCacheManager` phải khớp chính xác với `cacheNames = "prices"` trên phương thức nghiệp vụ.

### 3.4. src/main/java/demo/PriceService.java

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class PriceService {

    private final AtomicInteger sourceCalls = new AtomicInteger();

    @Cacheable(cacheNames = "prices", key = "#p0")
    public String getPrice(String productId) {
        int count = sourceCalls.incrementAndGet();
        System.out.println("Doc nguon " + productId + " (lan " + count + ")");
        return "gia-" + productId + "-100";
    }

    public int sourceCalls() {
        return sourceCalls.get();
    }
}
```

Giải thích:

- `@Cacheable` là chỉ dẫn cache kết quả trả về theo tên `prices`.
- `key = "#p0"` dùng đối số đầu tiên làm key; cú pháp này không phụ thuộc tên tham số Java có được giữ lại lúc biên dịch hay không.
- `AtomicInteger` đếm số lần thân phương thức **thực sự** chạy, giúp dễ phân biệt hit và miss.
- Giá trị `"gia-" + productId + "-100"` là kết quả giả lập ổn định; thực tế có thể là truy vấn hoặc tính toán tốn chi phí.

Nếu không chỉ định `key`, Spring sử dụng `KeyGenerator` mặc định dựa trên các đối số. Trong ví dụ một `String` duy nhất, key mặc định cũng có thể dùng trực tiếp đối số đó; dùng `#p0` giúp giải thích cách xác định key một cách tường minh.

### 3.5. src/main/java/demo/Main.java

```java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             CacheConfig.class, PriceService.class)) {

            PriceService service = context.getBean(PriceService.class);

            System.out.println("Lan 1: " + service.getPrice("P42"));
            System.out.println("Lan 2: " + service.getPrice("P42"));
            System.out.println("Lan 3: " + service.getPrice("P43"));
            System.out.println("So lan doc nguon: " + service.sourceCalls());

            CacheManager manager = context.getBean(CacheManager.class);
            System.out.println("Manager: "
                    + manager.getClass().getSimpleName());
            System.out.println("Cache prices ton tai: "
                    + (manager.getCache("prices") != null));
        }
    }
}
```

Dùng `context.getBean(PriceService.class)` để lấy **đúng bean do Spring quản lý**. Nếu thay bằng `new PriceService()`, đối tượng đó nằm ngoài Spring container và không được áp dụng caching interceptor.

### 3.6. Biên dịch, chạy và đối chiếu kết quả

Yêu cầu: JDK 17+, Maven, Internet cho lần đầu tải dependency. Trong thư mục `spring-cache-manager-demo/`:

```bash
mvn -q clean compile exec:java
```

Đoạn sau là **các dòng do mã ứng dụng in ra**, theo đúng thứ tự; các dòng ghi log từ Maven hoặc Spring nếu môi trường hiện ra thêm không thuộc kết quả này:

```text
Doc nguon P42 (lan 1)
Lan 1: gia-P42-100
Lan 2: gia-P42-100
Doc nguon P43 (lan 2)
Lan 3: gia-P43-100
So lan doc nguon: 2
Manager: ConcurrentMapCacheManager
Cache prices ton tai: true
```

Có ba lời gọi `getPrice` nhưng chỉ hai lần thực thi xử lý gốc, vì lần hai với `P42` trúng cache. Lần gọi `P43` dùng key khác nên miss. Việc lấy bean `CacheManager` và kiểm tra `getCache("prices") != null` xác nhận cache name đã được đăng ký.

**Cách nhìn đúng về demo:** Nó minh họa khai báo `@Bean` và cache interception trong một ứng dụng Spring Framework thuần. Nó không tự có HTTP endpoint, cơ sở dữ liệu, TTL hay chia sẻ cache giữa nhiều tiến trình.

## 4. Khi muốn cấu hình CaffeineCacheManager thay cho ConcurrentMap

Với ứng dụng cần giới hạn dung lượng và hết hạn entry trong **một JVM**, có thể tạo bean Caffeine. Cần `spring-context-support` cùng thư viện `caffeine` (khi dùng Spring Boot, starter cache thường cung cấp adapter Spring):

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context-support</artifactId>
    <version>6.2.0</version>
</dependency>
<dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
    <version>3.1.8</version>
</dependency>
```

Ví dụ lớp cấu hình **thay thế toàn bộ bean manager ở ví dụ trước**:

```java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("prices");
        manager.setCacheSpecification(
                "maximumSize=1000,expireAfterWrite=300s");
        return manager;
    }
}
```

- `new CaffeineCacheManager("prices")` cấu hình trước cache `prices` và giới hạn tên cache được manager này tạo.
- `maximumSize=1000` giới hạn xấp xỉ số entry theo chính sách loại bỏ của Caffeine.
- `expireAfterWrite=300s` hết hạn sau 300 giây kể từ khi entry được ghi hoặc cập nhật.
- Trong ví dụ cấu hình Java thủ công, **chính bean này** quyết định TTL và kích thước. Đặt `spring.cache.caffeine.spec` trong `application.properties` của Spring Boot không bảo đảm cấu hình lại một bean manager do bạn tự tạo.

Khi chuyển provider, nên chỉ có **một bean `CacheManager` mặc định rõ ràng**. Đừng thêm đồng thời hai phương thức `@Bean CacheManager cacheManager()` với cùng tên hoặc để nhiều manager mà không có quy tắc chọn.

Mã Caffeine phía trên là một cấu hình Spring để gắn vào dự án đã có dependency phù hợp; ví dụ Maven thuần ở mục 3 phải được cập nhật dependencies trước khi thay lớp này. Nó vẫn là cache **local**, không tự đồng bộ giữa các instance.

## 5. Khi muốn khai báo RedisCacheManager

Với cache dùng chung cho nhiều instance, Spring Data Redis cung cấp `RedisCacheManager`. Cần có module Spring Data Redis/client và một `RedisConnectionFactory` hoạt động. Dưới đây là **mẫu cấu hình bean cho dự án đã tích hợp Redis**, không phải chương trình chạy độc lập:

```java
import java.time.Duration;
import java.util.Set;

import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class RedisCachingConfig {

    @Bean
    public CacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(5));

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .initialCacheNames(Set.of("prices"))
                .build();
    }
}
```

Spring inject `RedisConnectionFactory` từ application context vào phương thức `@Bean`; manager sử dụng kết nối đó để đọc/ghi cache. `entryTtl(Duration.ofMinutes(5))` cài thời hạn 5 phút. Ví dụ giả định đã có kết nối Redis server, serializer phù hợp, dependency và phiên bản Spring Data Redis tương thích.

Trong ứng dụng Spring Boot có thể thêm `spring-boot-starter-data-redis` cùng `spring-boot-starter-cache`, hoặc để Boot tự cấu hình Redis manager khi điều kiện thỏa mãn. Nếu tự tạo `RedisCacheManager` bean, bạn trực tiếp chịu trách nhiệm những thiết lập như TTL, cache names và serialization. Đừng tắt prefix key chỉ để “đơn giản hóa”: prefix mặc định giúp các cache khác tên tránh đụng key trong Redis.

### Lựa chọn manager theo yêu cầu

| Bean implementation | Nơi lưu dữ liệu | Điểm mạnh | Giới hạn chính |
| --- | --- | --- | --- |
| `ConcurrentMapCacheManager` | RAM trong JVM | Thiết lập tối thiểu, phù hợp học và test | Không có TTL/giới hạn entry tích hợp, không chia sẻ nhiều instance |
| `CaffeineCacheManager` | RAM trong JVM | Eviction/expiration và hiệu năng in-memory | Mỗi instance có cache riêng |
| `RedisCacheManager` | Redis server | Chia sẻ dữ liệu giữa các instance | Cần mạng, Redis, serializer và xử lý lỗi hạ tầng |
| `JCacheCacheManager` | Theo JSR-107 provider | Tích hợp chuẩn API với provider tương thích | Phải có provider và cache configuration phù hợp |
| `NoOpCacheManager` | Không lưu | Tắt hiệu lực cache để test/troubleshoot | Mọi lần gọi đều chạy phương thức gốc |

Chỉ chọn và khai báo những manager thực sự cần. Việc biết cách tạo bean cho nhiều provider không đồng nghĩa cài nhiều provider sẽ nhanh hơn.

## 6. Spring Boot: khi nào nên tạo @Bean thủ công?

Spring Boot có khả năng tự cấu hình `CacheManager` dựa vào thư viện có trên classpath khi caching đã bật. Ví dụ, với `spring-boot-starter-cache` và Caffeine trên classpath, Boot có thể tạo `CaffeineCacheManager`.

Khi bạn **tự khai báo bean `CacheManager`**, Spring Boot thường không tạo thêm manager tự động cho cùng nhiệm vụ. Điều này hữu ích khi bạn muốn:

- Kiểm soát chính xác cache name, TTL, kích thước hoặc serializer.
- Có nhiều manager, nhiều provider và quy tắc ánh xạ nghiệp vụ rõ ràng.
- Khởi tạo các cache theo điều kiện hoặc cấu hình Java phức tạp hơn application properties.
- Dùng các chiến lược cache khác nhau giữa môi trường dev/test/prod.

Tuy nhiên, cấu hình thủ công cũng có nghĩa một số tùy chỉnh `spring.cache.*` hoặc `CacheManagerCustomizer` chỉ hoạt động cho manager do Boot tạo, **không mặc nhiên áp dụng cho manager bạn tự xây dựng**. Kiểm tra bean thực tế sẽ đáng tin hơn suy luận từ dependencies.

Gợi ý cấu hình trong một ứng dụng Boot:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("prices");
    }
}
```

Có thể dùng `@Configuration(proxyBeanMethods = false)` khi không cần gọi các `@Bean` method qua CGLIB proxy để tái sử dụng bean. Nó không “tắt” proxy caching cho service: đây là hai cơ chế proxy khác nhau. Với Boot, nên giữ `@EnableCaching` ở class cấu hình riêng để các test slice không vô tình buộc phải bật caching.

## 7. Có nhiều CacheManager bean: chọn đúng manager

Trong hệ thống có nhiều loại cache, có thể cần hai bean, ví dụ một local cache cho danh mục và một distributed cache cho phiên làm việc. Trường hợp đó phải định nghĩa rõ manager nào được dùng:

```java
@Configuration
@EnableCaching
public class MultipleCacheConfig {

    @Bean("localCacheManager")
    CacheManager localCacheManager() {
        return new ConcurrentMapCacheManager("categories");
    }

    @Bean("priceCacheManager")
    CacheManager priceCacheManager() {
        return new ConcurrentMapCacheManager("prices");
    }
}
```

Đây là ví dụ **chỉ minh họa hai manager** cùng implementation; trong thực tế mỗi bean có thể dùng một provider khác. Muốn một phương thức chọn `priceCacheManager`:

```java
@Cacheable(
    cacheNames = "prices",
    cacheManager = "priceCacheManager",
    key = "#p0"
)
public String getPrice(String id) {
    return fetchPriceFromSource(id);
}
```

Đoạn trên là **phương thức minh họa**, giả định có `fetchPriceFromSource` trong service. Nó không chạy độc lập. Nếu một service dùng cache `categories`, có thể khai báo `cacheManager = "localCacheManager"` ở annotation tương ứng.

Các cách chọn khi có nhiều manager:

1. **Chỉ định tên ở annotation**: `@Cacheable(cacheManager = "priceCacheManager")` cho nơi cần manager riêng.
2. **Khai báo mặc định thông qua `CachingConfigurer`** nếu muốn hạ tầng caching biết rõ manager/resolver ưu tiên.
3. **Đảm bảo lựa chọn bằng `@Primary` hoặc cấu hình bean phù hợp** khi injection theo type không còn duy nhất; kiểm tra cả cách cache interceptor tìm manager.
4. **Dùng `CacheResolver`** khi quy tắc định tuyến phức tạp (chọn cache động theo ngữ cảnh), nhưng đây là tầng nâng cao, tránh bổ sung khi chưa cần.

Không nên nghĩ rằng `cacheNames="prices"` sẽ tự động tìm đúng manager giữa hai manager. Nó là tên cache được tra **bên trong manager đã được chọn**. Tên cache trùng nhau ở hai manager có thể dẫn đến hành vi khác nhau hoàn toàn.

### @Bean trả về interface hay implementation?

Cả hai cách sau đều hợp lệ:

```java
@Bean
public CacheManager cacheManager() {
    return new ConcurrentMapCacheManager("prices");
}
```

```java
@Bean
public ConcurrentMapCacheManager cacheManager() {
    return new ConcurrentMapCacheManager("prices");
}
```

Trả về interface làm rõ hợp đồng mà phần còn lại của ứng dụng phụ thuộc. Trả về kiểu cụ thể có thể hữu ích khi cần autowire theo implementation hoặc khi điều kiện auto-configuration phải nhìn thấy type cụ thể. Trong đa số ví dụ Spring Cache đơn giản, trả về `CacheManager` là đủ.

## 8. Những thay đổi thường gặp và hậu quả

### Thêm cache mới

Nếu dùng constructor danh sách tên cố định:

```java
return new ConcurrentMapCacheManager(
        "prices", "products", "categories");
```

Một phương thức `@Cacheable(cacheNames = "categories")` khi đó có nơi lưu phù hợp. Với `new ConcurrentMapCacheManager()` không tham số, manager có thể tạo cache theo tên khi cần; cách này linh hoạt nhưng lỗi chính tả trong `cacheNames` khó bị phát hiện hơn.

### Xóa một entry sau khi cập nhật nguồn

Khi thay đổi giá nguồn, cache cũ có thể không còn hợp lệ. Trong service, một phương thức ghi có thể sử dụng:

```java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updatePrice(String productId, int newPrice) {
    repository.updatePrice(productId, newPrice);
}
```

Đây là **minh họa trong service có repository thật**, không phải mã có thể chạy độc lập. Mặc định, `@CacheEvict` xảy ra sau khi phương thức hoàn tất thành công; với giao dịch database, cần xem xét thời điểm commit và nhất quán cache để tránh đọc lại giá trị cũ hoặc race condition. Cache manager không tự biết dữ liệu gốc đã thay đổi khi bạn ghi database.

### Thay manager khi test

Nếu muốn test đường xử lý nguồn mà không giữ cache, `NoOpCacheManager` có thể được đăng ký trong cấu hình test phù hợp:

```java
@Bean
CacheManager cacheManager() {
    return new org.springframework.cache.support.NoOpCacheManager();
}
```

Manager này đáp ứng interface nhưng không lưu kết quả. Tránh có hai bean cùng tên trong application context nếu dự án không cho phép ghi đè bean; sử dụng test configuration/profiles hợp lý.

## 9. Cách xác minh bean CacheManager và đường đi caching

Khi debug, hãy kiểm tra theo thứ tự:

1. **Bean đã được load chưa?** `CacheConfig` có nằm trong classpath scanning, `@Import`, hoặc đăng ký qua `AnnotationConfigApplicationContext` không?
2. **Có `@EnableCaching` chưa?** Không thể chỉ nhìn thấy `@Cacheable` mà kết luận interceptor đang chạy.
3. **Có một manager phù hợp?** Kiểm tra `context.getBean(CacheManager.class)`; nếu nhiều bean, phải xác định tên hoặc qualifier.
4. **Cache name khớp?** `manager.getCache("prices")` có trả về cache hay `null`?
5. **Lời gọi có qua Spring proxy?** `new Service()` hoặc `this.getPrice()` trong cùng bean không đi qua cache interceptor ở proxy mode mặc định.
6. **Key có ổn định?** `key="#p0"` dùng tham số thứ nhất. Với `key="#productId"`, cần tên tham số được Spring nhận diện (thường biên dịch với `-parameters` trên Java hiện đại).
7. **Có invalidation, TTL hay lỗi backend không?** Một miss không nhất thiết do cấu hình annotation sai.

Đoạn kiểm tra trong thành phần đã có `ApplicationContext context`:

```java
CacheManager cacheManager = context.getBean(CacheManager.class);
System.out.println(cacheManager.getClass().getName());
System.out.println(cacheManager.getCacheNames());
System.out.println(cacheManager.getCache("prices") != null);
```

Đây là snippet để chèn vào ứng dụng đang chạy; `context` cần có sẵn. Với local cache, log đếm số lần thực sự xử lý gốc là cách dễ nhất để kiểm chứng hit/miss. Khi lên production, theo dõi thêm miss rate, latency, TTL, eviction, memory, lỗi backend và dữ liệu stale.

### Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không có bean kiểu `CacheManager` | Config class chưa được nạp hoặc `@Bean` không được khai báo | Kiểm tra component scan, `@Import`, cấu hình context |
| `NoUniqueBeanDefinitionException` khi lấy manager | Có nhiều manager, injection không biết chọn bean nào | Đặt bean name/`@Qualifier`, `@Primary` hoặc cấu hình caching mặc định |
| `Cannot find cache named 'prices'` | Cache name không được manager đã chọn hỗ trợ | Kiểm tra `getCacheNames()`, constructor tên cache và annotation |
| Lần gọi nào cũng chạy thân method | Quên `@EnableCaching`, gọi đối tượng bằng `new`, self-invocation, key thay đổi | Kiểm tra Spring proxy và hành vi hit/miss |
| Dùng Spring Boot nhưng properties cache không có tác dụng | Bean `CacheManager` tự khai báo thay thế auto-configuration | Áp dụng config trực tiếp vào bean hoặc bỏ bean thủ công |
| `ClassNotFoundException` với Caffeine/Redis | Thiếu adapter/provider dependency tương ứng | Kiểm tra Maven/Gradle dependency tree và runtime classpath |
| Cache trả kết quả cũ sau update | Chưa xóa/cập nhật entry, TTL quá dài | Thiết kế invalidation theo thay đổi dữ liệu và giao dịch |
| Demo local hoạt động nhưng các instance trả kết quả khác nhau | Mỗi JVM có cache riêng | Chọn distributed cache hoặc đồng bộ invalidation khi cần |

## 10. Câu hỏi tự kiểm tra

1. Khác biệt giữa bean tên `cacheManager` và cache tên `prices` là gì?
2. Nếu chỉ khai báo `@Bean CacheManager` mà bỏ `@EnableCaching`, điều gì xảy ra với `@Cacheable`?
3. Vì sao trong ví dụ Java có ba lời gọi `getPrice` nhưng chỉ hai lần chạy xử lý gốc?
4. Vì sao `new ConcurrentMapCacheManager("prices")` không thể phục vụ cache `categories` khi chưa cấu hình thêm?
5. Trong Spring Boot, khai báo `CacheManager` thủ công ảnh hưởng thế nào đến auto-configuration và `spring.cache.*`?
6. Nếu có hai `CacheManager`, làm sao chọn đúng manager cho phương thức `@Cacheable`?
7. Vì sao `CaffeineCacheManager` cần thư viện provider trong khi `ConcurrentMapCacheManager` hoạt động với Spring Context cơ bản?
8. Sau khi thay đổi dữ liệu nguồn, vì sao chỉ tạo bean cache manager không bảo đảm dữ liệu trả ra luôn mới?

## 11. Tài liệu chính thức để đào sâu

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Enabling Caching Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)

**Điểm cần nhớ:** `@Bean CacheManager` xác định provider và các cache mà ứng dụng được phép dùng; `@EnableCaching` bật hạ tầng annotation; `@Cacheable` đặt quy tắc tra cache cho từng phương thức. Hãy kiểm tra bean thực tế, cache name và hit/miss qua lời gọi từ Spring container trước khi sử dụng trên môi trường thực tế.