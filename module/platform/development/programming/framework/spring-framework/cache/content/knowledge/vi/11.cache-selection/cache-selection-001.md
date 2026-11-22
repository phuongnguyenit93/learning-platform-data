# Chọn CacheManager bằng tên bean trên thao tác trong Spring Cache

> **Ngữ cảnh:** Spring Framework – Cache · **Nhóm:** Chọn vùng cache.  
> **Mục tiêu:** phân biệt `CacheManager` với `Cache`; chỉ định đúng bean `CacheManager` trên `@Cacheable`, `@CachePut`, `@CacheEvict`; hiểu ưu tiên của cấu hình cấp method, cấp class và toàn cục; tự triển khai, chạy và kiểm tra ứng dụng có nhiều manager.

## 1. Chọn manager khác với chọn vùng cache

Spring Cache abstraction dùng hai đối tượng có trách nhiệm khác nhau:

- **`CacheManager`:** thành phần quản lý các vùng cache, cung cấp API `Cache getCache(String name)` và danh sách cache names. Manager có thể là `ConcurrentMapCacheManager`, `CaffeineCacheManager`, `RedisCacheManager` hoặc implementation riêng.
- **`Cache`:** vùng cụ thể chứa dữ liệu theo từng key. Ví dụ vùng tên `products` có entry với key `"P42"` và value tương ứng.

Với annotation:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product getProduct(String id) {
    return repository.find(id);
}
```

Spring lấy vùng `products` thông qua **manager/resolver mặc định**. Nếu ApplicationContext có một manager phù hợp thì cách viết này thường đủ. Tuy nhiên, khi ứng dụng có **hai hoặc nhiều manager**, phải biết thao tác sẽ lấy `products` từ manager nào.

Cách chỉ định tường minh:

```java
@Cacheable(
    cacheNames = "products",
    cacheManager = "redisCacheManager",
    key = "#p0"
)
public Product getProduct(String id) {
    return repository.find(id);
}
```

Đây là snippet trong một Spring-managed service có `Product` và repository, **không phải file Java độc lập**.

Ba giá trị trong annotation có ý nghĩa riêng:

| Thuộc tính | Trả lời câu hỏi | Giá trị minh họa |
|---|---|---|
| `cacheManager` | Dùng **bean manager nào** trong Spring context? | `"redisCacheManager"` |
| `cacheNames` (alias: `value`) | Trong manager đã chọn, dùng **vùng nào**? | `"products"` |
| `key` | Trong vùng đó, truy cập **entry nào**? | `#p0`, ví dụ `"P42"` |

**`cacheManager` là một chuỗi tên bean, không phải SpEL.** `cacheManager="#p0"` không được Spring hiểu là chọn manager theo argument. Nếu cần chọn động theo request, dùng `CacheResolver` (mục 7).

Tên bean cũng không bảo đảm loại backend. Một bean đặt tên `redisCacheManager` nhưng được khai báo từ `ConcurrentMapCacheManager` vẫn là in-memory manager; hãy xác minh implementation và cấu hình thực tế.

### Hai cache cùng tên không nhất thiết chung dữ liệu

Hai bean manager có thể đều cung cấp vùng `products` nhưng mỗi vùng hoàn toàn độc lập:

```text
Spring ApplicationContext
├── fastCacheManager    (Caffeine hoặc ConcurrentMap)
│   └── products
│       └── key=P42 → value=A
└── sharedCacheManager  (Redis hoặc backend khác)
    └── products
        └── key=P42 → value=B
```

Nếu method A dùng `cacheManager="fastCacheManager"` còn method B dùng `cacheManager="sharedCacheManager"`, hai method không tự đọc chéo cache. **Trùng `cacheNames` không nối hai backend**; chỉ khi implementation của hai bean thật sự cùng trỏ về một store/namespace thì dữ liệu mới có thể giao nhau.

## 2. `cacheManager` có trên những annotation nào?

Cả ba thao tác chính của Spring Cache đều cho phép chọn manager bằng tên bean:

**`@Cacheable` — tìm cache trước, tính rồi lưu nếu miss:**

```java
@Cacheable(cacheNames = "books", cacheManager = "fastCacheManager",
           key = "#p0")
public Book findBook(String isbn) {
    return repository.findByIsbn(isbn);
}
```

**`@CachePut` — luôn gọi method, sau đó đưa kết quả vào cache:**

```java
@CachePut(cacheNames = "books", cacheManager = "fastCacheManager",
          key = "#p0")
public Book reloadBook(String isbn) {
    return repository.reload(isbn);
}
```

**`@CacheEvict` — yêu cầu xóa entry hoặc vùng cache:**

```java
@CacheEvict(cacheNames = "books", cacheManager = "fastCacheManager",
            key = "#p0")
public void deleteBook(String isbn) {
    repository.delete(isbn);
}
```

Các đoạn này minh họa trên service đã có repository; chúng không phải một chương trình biên dịch riêng. Khi xóa, mặc định `@CacheEvict` thực thi **sau khi method hoàn thành thành công**, trừ khi dùng `beforeInvocation=true`.

Điểm chung là **manager được chọn tại từng cache operation**, không phải dựa trên return type hay tự suy đoán từ method name. Vì thế, cùng một class có thể có method đọc cache local và method đọc Redis bằng cách đặt hai bean names khác nhau.

### Cú pháp hợp lệ và không hợp lệ

Hợp lệ:

```java
@Cacheable(cacheNames = "books", cacheManager = "fastCacheManager",
           key = "#p0")
public Book find(String isbn) { /* ... */ }
```

Không hợp lệ vì chỉ định **hai cách resolve cache trên cùng operation**:

```java
@Cacheable(
    cacheNames = "books",
    cacheManager = "fastCacheManager",
    cacheResolver = "dynamicCacheResolver")
public Book find(String isbn) { /* ... */ }
```

`cacheManager` và `cacheResolver` là **mutually exclusive**. Một `CacheResolver` tùy chỉnh đã tự quyết định vùng cache cần dùng; Spring không cho phép đồng thời gắn manager riêng trên cùng operation vì dễ tạo kỳ vọng sai.

Tương tự, `key` và `keyGenerator` không được khai báo cùng nhau trên một operation. Việc chọn manager không tự làm thay đổi cách Spring sinh key.

## 3. Khai báo đúng bean `CacheManager` trong cấu hình Spring

### 3.1. Đặt tên bean tường minh

Khi dùng Java configuration, khai báo `@Bean("...")` giúp tên được dùng trong annotation rõ ràng và ổn định:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
class CacheConfiguration {

    @Bean("fastCacheManager")
    CacheManager fastCacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean("archiveCacheManager")
    CacheManager archiveCacheManager() {
        return new ConcurrentMapCacheManager("books");
    }
}
```

Đây là cấu hình minh họa cần các import Spring tương ứng; ví dụ runnable đầy đủ có ở mục 5.

Ý nghĩa:

- Có **hai bean `CacheManager`**: `fastCacheManager` và `archiveCacheManager`.
- Cả hai manager tạo vùng có tên `books`, nhưng dữ liệu độc lập vì `ConcurrentMapCacheManager` dùng cache trong bộ nhớ của riêng instance.
- Method khai báo `cacheManager="archiveCacheManager"` phải chọn bean archive, dù vùng cũng có tên `books` ở fast.
- Để dùng annotation caching, phải bật `@EnableCaching` và gọi method qua Spring proxy theo cấu hình mặc định.

Nếu không chỉ định tên ở `@Bean`, Spring thường sử dụng tên method làm bean name. Tuy nhiên, khi rename method hoặc khai báo alias, annotation phụ thuộc vào đúng **bean name đã đăng ký**, không phải tên class Java.

### 3.2. Nhiều CacheManager và lựa chọn mặc định

Khi có nhiều manager nhưng một số operation không khai báo `cacheManager`, cấu hình **default manager/default CacheResolver** phải rõ ràng. Các cách phổ biến:

- Đặt một bean là `@Primary` để giải quyết injection theo type trong hạ tầng mặc định.
- Triển khai `CachingConfigurer`, cung cấp `cacheManager()` hoặc `cacheResolver()` mặc định.
- Định danh manager trên từng operation hoặc đặt mặc định tại `@CacheConfig` của class khi phù hợp.

Ví dụ:

```java
@Bean("fastCacheManager")
@Primary
CacheManager fastCacheManager() {
    return new ConcurrentMapCacheManager("books", "defaults");
}

@Bean("archiveCacheManager")
CacheManager archiveCacheManager() {
    return new ConcurrentMapCacheManager("books");
}
```

Hai method này là snippet nằm trong class cấu hình, không phải file độc lập. `@Primary` **không chặn** method chỉ định `cacheManager="archiveCacheManager"`. Nó chỉ làm rõ lựa chọn mặc định khi Spring cần một bean `CacheManager` phù hợp mà không có lựa chọn cụ thể hơn.

Khi ứng dụng có nhiều cấu hình cache hoặc `CachingConfigurer`, không nên giả định mọi thao tác không chỉ rõ manager đều chọn `@Primary` theo một cách bất biến; hãy kiểm tra default resolver thực tế bằng integration test.

### 3.3. Lỗi thường gặp với tên bean

`"fastCacheManager"` trong annotation phải khớp **chính xác** tên hoặc alias bean có thể nhìn thấy từ context. Nếu bean đã đổi thành `caffeineManager` nhưng annotation vẫn trỏ `fastCacheManager`, Spring có thể ném lỗi tra cứu bean khi cache operation được khởi tạo/thực thi.

Không thể tự sửa lỗi bằng việc tạo vùng cùng tên ở manager còn lại: tên manager sai là **vấn đề định tuyến** trước cả bước tìm cache name. Dùng tìm kiếm references trong source, kiểm tra `@Bean`/`@Profile`, và kiểm tra beans thực tế trong context.

## 4. Thứ tự ưu tiên giữa cấu hình toàn cục, `@CacheConfig` và method

Spring cho phép tùy biến ở ba tầng:

1. **Tầng toàn cục:** cấu hình hạ tầng `@EnableCaching` với manager/resolver mặc định; có thể dùng `CachingConfigurer`.
2. **Tầng class:** `@CacheConfig(cacheNames=..., cacheManager=..., keyGenerator=..., cacheResolver=...)` cung cấp giá trị mặc định cho các method cache trong class.
3. **Tầng method:** `@Cacheable`/`@CachePut`/`@CacheEvict` ghi đè những mặc định tương ứng nếu có thuộc tính riêng.

Ví dụ:

```java
@Service
@CacheConfig(cacheNames = "books", cacheManager = "fastCacheManager")
class BookService {

    @Cacheable(key = "#p0")
    public Book findFast(String isbn) {
        return repository.findByIsbn(isbn);
    }

    @Cacheable(key = "#p0", cacheManager = "archiveCacheManager")
    public Book findArchive(String isbn) {
        return repository.findByIsbn(isbn);
    }

    @CacheEvict(key = "#p0", cacheManager = "archiveCacheManager")
    public void clearArchive(String isbn) {
        // Không can thiệp vùng books của fastCacheManager.
    }
}
```

Đây là snippet giải thích độ ưu tiên, chưa phải class độc lập (cần `repository` và `Book`).

- `findFast` không có `cacheNames` hoặc `cacheManager` riêng, nên dùng vùng `books` trên `fastCacheManager` từ `@CacheConfig`.
- `findArchive` **ghi đè riêng manager** lên `archiveCacheManager` nhưng vẫn dùng tên cache `books` do class cung cấp.
- `clearArchive` cũng chọn archive để xóa đúng entry mà `findArchive` đã tạo.
- Nếu thêm method `@Cacheable(cacheNames="editions")` trong class mà không khai báo manager, nó dùng manager cấp class `fastCacheManager` với cache name đã được ghi đè là `editions`; manager đó phải có/cho phép tạo vùng tương ứng.

**`@CacheConfig` không kích hoạt caching**, không tạo bean CacheManager, không gắn `@Cacheable` cho tất cả method; nó chỉ chứa *mặc định*. Khi cần định tuyến riêng cho một method, dùng thuộc tính ngay trên operation.

### So sánh ba tầng

| Cấu hình | Phạm vi áp dụng | Ví dụ |
|---|---|---|
| Default toàn ứng dụng | Những operation không có lựa chọn khác | `CachingConfigurer.cacheManager()` |
| `@CacheConfig(cacheManager="fastCacheManager")` | Các cache operation trong class không override | Hầu hết method của `BookService` |
| `@Cacheable(cacheManager="archiveCacheManager")` | Chỉ operation đó | Một method đọc archive đặc biệt |

Tính năng class-level giúp tránh lặp tên bean, nhưng **không thay thế `@Primary`** và không làm mặc định cho các class khác.

## 5. Demo Java 17+ chạy độc lập: hai manager cùng vùng, giá trị độc lập

Ví dụ sử dụng **Java 17**, **Maven**, **Spring Framework 6.2.12**, không cần Spring Boot hay Redis server. Hai `ConcurrentMapCacheManager` tách biệt nhằm chứng minh chính xác cách lựa chọn theo tên bean.

**Các đối tượng:**

- `fastCacheManager`: manager mặc định `@Primary`, có vùng `books` và `defaults`.
- `archiveCacheManager`: manager phụ, có vùng `books`.
- `Books`: dùng `@CacheConfig` chọn fast mặc định, rồi override manager trên method archive và evict.
- `DefaultBooks`: method không chọn manager, để kiểm chứng default.

### 5.1. Cấu trúc thư mục

```text
cache-manager-routing/
├── pom.xml
└── src/main/java/dev/example/routing/CacheManagerRoutingDemo.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>cache-manager-routing</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>dev.example.routing.CacheManagerRoutingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/dev/example/routing/CacheManagerRoutingDemo.java`**

```java
package dev.example.routing;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

public class CacheManagerRoutingDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            Books books = context.getBean(Books.class);
            DefaultBooks defaults = context.getBean(DefaultBooks.class);

            CacheManager fast =
                    context.getBean("fastCacheManager", CacheManager.class);
            CacheManager archive =
                    context.getBean("archiveCacheManager", CacheManager.class);

            System.out.println("separateBooks=" +
                    (fast.getCache("books") != archive.getCache("books")));

            System.out.println("fast1=" + books.fast("42"));
            System.out.println("fast2=" + books.fast("42"));

            System.out.println("archive1=" + books.archive("42"));
            System.out.println("archive2=" + books.archive("42"));

            System.out.println("default1=" + defaults.read("42"));
            System.out.println("default2=" + defaults.read("42"));

            System.out.println("putFast=" + books.updateFast("42"));
            System.out.println("fastAfterPut=" + books.fast("42"));
            System.out.println("archiveStill=" + books.archive("42"));

            books.evictArchive("42");
            System.out.println("archiveAfterEvict=" + books.archive("42"));
            System.out.println("fastStill=" + books.fast("42"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class AppConfig {
        @Bean("fastCacheManager")
        @Primary
        public CacheManager fastCacheManager() {
            return new ConcurrentMapCacheManager("books", "defaults");
        }

        @Bean("archiveCacheManager")
        public CacheManager archiveCacheManager() {
            return new ConcurrentMapCacheManager("books");
        }

        @Bean
        public Books books() {
            return new Books();
        }

        @Bean
        public DefaultBooks defaultBooks() {
            return new DefaultBooks();
        }
    }

    @CacheConfig(cacheNames = "books", cacheManager = "fastCacheManager")
    public static class Books {
        private final AtomicInteger fastLoads = new AtomicInteger();
        private final AtomicInteger archiveLoads = new AtomicInteger();

        @Cacheable(key = "#p0")
        public String fast(String id) {
            return "fast-" + id + "#" + fastLoads.incrementAndGet();
        }

        @Cacheable(key = "#p0", cacheManager = "archiveCacheManager")
        public String archive(String id) {
            return "archive-" + id + "#" + archiveLoads.incrementAndGet();
        }

        @CachePut(key = "#p0")
        public String updateFast(String id) {
            return "new-" + id;
        }

        @CacheEvict(key = "#p0", cacheManager = "archiveCacheManager")
        public void evictArchive(String id) {
            // Không tự xóa cache khác: chỉ method kết thúc thành công.
        }
    }

    public static class DefaultBooks {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "defaults", key = "#p0")
        public String read(String id) {
            return "default-" + id + "#" + loads.incrementAndGet();
        }
    }
}
```

Để chạy, mở terminal tại thư mục `cache-manager-routing`:

```bash
mvn -q compile exec:java
```

Các dòng `System.out.println` trong một lần chạy mới, **không tính log phụ của Maven/môi trường**:

```text
separateBooks=true
fast1=fast-42#1
fast2=fast-42#1
archive1=archive-42#1
archive2=archive-42#1
default1=default-42#1
default2=default-42#1
putFast=new-42
fastAfterPut=new-42
archiveStill=archive-42#1
archiveAfterEvict=archive-42#2
fastStill=new-42
```

### 5.2. Diễn giải kết quả

1. `separateBooks=true`: hai manager có hai đối tượng `Cache("books")` khác nhau.
2. `fast1/fast2`: `@Cacheable` trên method `fast` kế thừa `cacheManager="fastCacheManager"` từ `@CacheConfig`, nên lần sau hit.
3. `archive1/archive2`: method `archive` ghi đè manager bằng tên bean `archiveCacheManager`, vẫn dùng vùng `books`, nhưng không chia sẻ entry với fast.
4. `default1/default2`: class `DefaultBooks` không có `@CacheConfig`; cấu hình default trong context chọn fast manager, có vùng `defaults`.
5. `putFast=new-42`: `@CachePut` luôn chạy method, ghi lại value mới vào `books` của fast manager vì kế thừa default cấp class.
6. `fastAfterPut=new-42`: `@Cacheable` hit value vừa được `@CachePut` cập nhật.
7. `archiveStill=archive-42#1`: cập nhật fast không tác động đến archive dù cùng cache name và key.
8. Sau `evictArchive("42")`, `archiveAfterEvict=archive-42#2` vì entry archive đã bị xóa rồi loader chạy lại.
9. `fastStill=new-42`: xóa archive không xóa fast.

**Proxy là điều kiện quan trọng.** Method phải được gọi qua bean từ `AnnotationConfigApplicationContext`. Nếu trực tiếp `new Books()` hoặc dùng `this.fast("42")` từ bên trong cùng class trong proxy mode mặc định, interceptor có thể không được gọi; lúc đó demo không còn chứng minh định tuyến cache theo annotation.

## 6. Spring Boot: nhiều manager và tên bean

Spring Boot cũng dùng Spring Framework Cache Abstraction. Boot có khả năng auto-configure `CacheManager` mặc định từ dependencies và `spring.cache.*`, nhưng khi tự tạo một hay nhiều bean manager, nhánh auto-configuration liên quan thường **lùi lại**. Vì vậy, đừng kỳ vọng `spring.cache.type=redis` tự thay đổi lựa chọn đã viết rõ `cacheManager="localCacheManager"`.

Ví dụ cấu hình **minh họa riêng trong dự án Spring Boot có Caffeine và Spring Data Redis**:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
class MultiCacheConfig {

    @Bean("localCacheManager")
    @Primary
    CacheManager localCacheManager() {
        return new CaffeineCacheManager("products");
    }

    @Bean("sharedCacheManager")
    CacheManager sharedCacheManager(RedisConnectionFactory connectionFactory) {
        return RedisCacheManager.builder(connectionFactory).build();
    }
}
```

Cần import từ `org.springframework.cache.CacheManager`, `org.springframework.cache.caffeine.CaffeineCacheManager`, `org.springframework.data.redis.cache.RedisCacheManager`, `org.springframework.data.redis.connection.RedisConnectionFactory` và các Spring annotations. Đây **không phải chương trình chạy độc lập**, vì cần dependencies, Redis server, properties kết nối, serialization, TTL/namespace phù hợp.

Trên service:

```java
@Cacheable(cacheNames = "products", cacheManager = "localCacheManager",
           key = "#p0")
public Product readLocal(String id) {
    return repository.find(id);
}

@Cacheable(cacheNames = "products", cacheManager = "sharedCacheManager",
           key = "#p0")
public Product readShared(String id) {
    return repository.find(id);
}
```

Hai lời gọi có thể trả cùng dữ liệu nghiệp vụ khi cache mới, nhưng một vùng local tồn tại trong JVM và một vùng shared ở Redis. Khi một node cập nhật dữ liệu, **chúng không tự invalidated lẫn nhau**; người viết phải tổ chức luồng xóa/invalidation hoặc chiến lược nhất quán thích hợp.

Nên kiểm tra trong runtime:

- Bean names thật của `CacheManager` là gì?
- Caffeine local có TTL, size limit, null policy đúng chưa?
- Redis có key prefix riêng, serializer và connection hợp lệ chưa?
- Method đọc/ghi/xóa có chọn **cùng** manager khi chúng phải thao tác một entry?
- Cache adapter có auto-create vùng theo tên hay chỉ cho phép danh sách tĩnh?

## 7. Khi nào dùng `CacheResolver` thay vì `cacheManager`?

`cacheManager="sharedCacheManager"` là chọn manager **cố định** cho annotation. Nếu logic cần thay đổi theo tenant, region, feature flag hoặc arguments tại mỗi lời gọi, dùng `CacheResolver`.

Ví dụ (snippet nâng cao, không phải phần source runnable mục 5):

```java
@Bean("tenantCacheResolver")
CacheResolver tenantCacheResolver(
        @Qualifier("localCacheManager") CacheManager local,
        @Qualifier("sharedCacheManager") CacheManager shared) {
    return context -> {
        String tenant = (String) context.getArgs()[0];
        CacheManager selected =
                tenant.startsWith("LOCAL-") ? local : shared;
        Cache cache = selected.getCache("profiles");
        return java.util.List.of(
                java.util.Objects.requireNonNull(
                        cache, "profiles cache missing"));
    };
}
```

Đoạn này cần import `CacheResolver`, `Cache`, `CacheManager`, `@Qualifier` và `@Bean`. Demo giả định argument đầu tiên là String tenant hợp lệ; production phải xử lý input null, quyền truy cập và chính sách phân vùng dữ liệu.

Sử dụng:

```java
@Cacheable(cacheNames = "profiles", cacheResolver = "tenantCacheResolver")
public Profile findProfile(String tenantId, String userId) {
    return repository.load(tenantId, userId);
}
```

Lúc này không được thêm `cacheManager="localCacheManager"` vào cùng annotation. Resolver là đối tượng chịu trách nhiệm trả về `Cache` thích hợp; cần kiểm soát kết quả nó trả về và viết test cho các branch. Đừng để các tenant có thể trỏ về cùng cache với cùng key `userId` nếu kết quả bị cô lập theo tenant.

**Phân biệt:** `cacheResolver` chọn **tập các Cache** dựa vào invocation; `cacheManager` chỉ định **một bean manager tĩnh** và Spring dùng resolver mặc định để lấy cache names từ manager đó.

## 8. Read, put và evict phải thống nhất cả manager, cache name, key

### 8.1. Lỗi xóa sai manager

Giả sử đọc từ shared manager:

```java
@Cacheable(cacheNames = "products", cacheManager = "sharedCacheManager",
           key = "#p0")
public Product read(String productId) {
    return repository.find(productId);
}
```

Nhưng method cập nhật quên chỉ định manager:

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void update(String productId, ProductPatch patch) {
    repository.update(productId, patch);
}
```

Nếu default manager là local, thao tác update sẽ xóa local, **không xóa entry đang nằm trong shared manager**. Hệ thống có thể tiếp tục trả dữ liệu stale dù method update đã thành công.

Cách sửa:

```java
@CacheEvict(cacheNames = "products", cacheManager = "sharedCacheManager",
            key = "#p0")
public void update(String productId, ProductPatch patch) {
    repository.update(productId, patch);
}
```

Đây đều là các method minh họa, cần repository và types nghiệp vụ thực. Khi dùng `@CachePut` để cập nhật value, cũng phải trỏ đến cùng manager nếu mục tiêu là cập nhật entry được method đọc sử dụng.

### 8.2. Evict trên nhiều manager

Nếu cùng một thực thể được cache ở local và shared, có thể dùng `@Caching` với hai thao tác `@CacheEvict`:

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "products",
                cacheManager = "localCacheManager", key = "#p0"),
    @CacheEvict(cacheNames = "products",
                cacheManager = "sharedCacheManager", key = "#p0")
})
public void update(String productId, ProductPatch patch) {
    repository.update(productId, patch);
}
```

Các eviction này vẫn **không được gộp thành một transaction nguyên tử giữa hai cache backends**. Một eviction có thể thất bại sau khi eviction khác đã thành công; nên thiết kế retry, event after-commit, versioned keys hoặc TTL theo nhu cầu nhất quán.

Đừng hiểu `@Cacheable(cacheNames={"local","shared"},cacheManager="someManager")` là chỉ định hai manager: trong annotation đó, cả hai cache names được resolver theo **manager đã chọn**, trừ khi bạn chủ động dùng resolver tùy biến có semantics khác.

### 8.3. Tránh cache collision và dữ liệu chéo quyền truy cập

Khi định tuyến đến Redis/shared cache:

- Đưa `tenantId`, region, permission scope vào key nếu ảnh hưởng kết quả. Chọn manager đúng nhưng key thiếu tenant vẫn có thể gây false hit nghiêm trọng.
- Key từ `SimpleKeyGenerator` hoặc object tùy chỉnh có thể cần converter/serializer riêng trong Redis; đừng suy rằng dùng tốt ở local Map thì sẽ giống hệt ở remote cache.
- TTL/eviction/null/serialization được cấu hình ở từng backend. `cacheManager` chỉ chọn đường truy cập, không tự đặt TTL.
- Nếu các bean manager cùng trỏ một Redis namespace với serializer khác nhau, việc “khác bean” **không bảo đảm cách ly dữ liệu**.

## 9. Cách xác minh cấu hình và khắc phục lỗi

### 9.1. Xem các bean `CacheManager` thực tế

Trong code có sẵn `ApplicationContext context`:

```java
String[] names = context.getBeanNamesForType(CacheManager.class);
System.out.println(java.util.Arrays.toString(names));
```

Lệnh trên là snippet cần import `CacheManager`, không phải class độc lập. Khi cần:

```java
CacheManager selected =
        context.getBean("sharedCacheManager", CacheManager.class);
System.out.println(selected.getClass().getName());
System.out.println(selected.getCacheNames());
```

Việc class manager có mặt không chắc chắn một vùng `Cache` có dữ liệu; muốn kiểm tra cụ thể, dùng `getCache("products")` và quan sát hit/miss.

### 9.2. Bảng lỗi hay gặp

| Hiện tượng | Khả năng | Hướng kiểm tra |
|---|---|---|
| Lỗi không tìm được bean manager | `cacheManager` sai tên, bean không được đăng ký, profile không bật | Liệt kê bean names, kiểm tra `@Bean("...")` và context |
| “Cannot find cache named ...” | Manager đã chọn không quản lý tên cache đó, không tạo động | Kiểm tra `getCache(name)` và cacheNames từng manager |
| Method luôn chạy dù có `@Cacheable` | `@EnableCaching` thiếu, self-invocation, method gọi ngoài proxy, key khác | Kiểm tra proxy path, key/condition, hit/miss |
| Thêm một manager thì method không chỉ rõ manager lỗi | Default CacheResolver/CacheManager trở nên mơ hồ | Khai báo `@Primary` hoặc `CachingConfigurer`, test default |
| Thêm `@CacheConfig` nhưng không có hiệu lực | Method không được intercept hoặc có override cấp method | Kiểm tra proxy và annotation trực tiếp |
| Cùng `cacheNames` mà kết quả khác nhau | Hai manager có hai stores/namespace khác nhau | Đọc tên bean, backend, prefix và cache value thực |
| `@CacheEvict` không xóa entry được `@Cacheable` đọc | Hai annotation chọn manager/cache/key khác nhau | So sánh đủ cả ba thông tin |
| `cacheManager="#p0"` không chọn theo argument | Thuộc tính nhận literal bean name | Dùng `CacheResolver` nếu cần runtime routing |
| Lỗi khi kết hợp `cacheManager` và `cacheResolver` | Hai lựa chọn loại trừ nhau | Chỉ định một lựa chọn |
| Đổi `spring.cache.type` nhưng manager vẫn cũ | Có bean CacheManager thủ công làm Boot auto-config lùi lại | Kiểm tra bean definitions/condition report |
| Local cache vẫn hit sau khi xóa Redis | Hai manager độc lập, local chưa invalidated | Thiết kế multi-cache invalidation thực sự |
| Shared cache trả dữ liệu giữa tenant | Key không chứa tenant/permission scope | Partition namespace và key theo quyền |

### 9.3. Kiểm thử nên có

1. Test method có `cacheManager="fastCacheManager"` trả hit lần hai từ đúng manager.
2. Test cùng key và cache name nhưng `archiveCacheManager` giữ entry độc lập.
3. Test `@CachePut` chỉ cập nhật manager được chọn.
4. Test `@CacheEvict` xóa đúng backend và không xóa nhầm backend khác.
5. Test `@CacheConfig` default và override trên một method trong cùng class.
6. Test operation không khai báo manager có default rõ ràng.
7. Test không có manager bean được tham chiếu, thiếu cache name, và kết hợp `cacheManager`/`cacheResolver`.
8. Với production Redis/Caffeine, test provider thật, cấu hình TTL, serializer, key prefix, exception, xóa sau commit.
9. Với nhiều instance, test invalidation liên node và các rủi ro stale data khi read/update cạnh tranh.
10. Kiểm tra metrics hit/miss và tên bean trong runtime; không chỉ dựa vào việc ứng dụng start không báo lỗi.

## 10. Nên chọn cách cấu hình nào?

| Bài toán | Lựa chọn đơn giản | Cần lưu ý |
|---|---|---|
| Chỉ một backend cache | Default manager + cache names | `@EnableCaching` và key đúng |
| Nhiều backend, mỗi method dùng một backend cố định | `cacheManager="beanName"` trên operation | Read/put/evict phải thống nhất |
| Một service chủ yếu dùng một manager | `@CacheConfig(cacheManager=...)` | Method có ngoại lệ thì override |
| Nhiều manager và một default | `@Primary` hoặc `CachingConfigurer` | Test operation không ghi rõ manager |
| Chọn backend theo tenant/argument mỗi invocation | `CacheResolver` | Không kết hợp với `cacheManager` trên cùng operation |
| Cần xóa nhiều backend khi update | `@Caching` với các `@CacheEvict` riêng | Không có atomicity cross-backend |
| Dùng Boot và tự tạo nhiều manager | Định nghĩa rõ các `@Bean` và cache settings | Không kỳ vọng mọi property auto-config áp dụng vào bean thủ công |

**Ghi nhớ:** tên bean là cách *định tuyến* thao tác. Nó không tự đảm bảo tính đúng của key, consistency, TTL, serializer, transaction hoặc hỗ trợ distributed locking. Khi kiến trúc phức tạp, một configuration bean chuẩn và integration tests rõ ràng có giá trị hơn việc rải literal tên bean không kiểm soát khắp source code.

## 11. Checklist trước khi hoàn thiện

1. Có `@EnableCaching` và method được gọi qua Spring-managed proxy?
2. Các tên bean manager có đúng với tên khai báo `@Bean`/alias và có mặt trong context?
3. Operation dùng manager cố định hay cần `CacheResolver` động?
4. `cacheNames` có tồn tại trong manager được chọn (hoặc được phép tạo động)?
5. `key` có đầy đủ các trường ảnh hưởng kết quả, đặc biệt tenant và permission scope?
6. Có default manager rõ ràng cho các operation không chỉ định `cacheManager`?
7. Có `@CacheConfig` ở class và sự override trên method đã đúng ý đồ?
8. `@CachePut`/`@CacheEvict` có dùng **cùng manager, cache name và key** với đường đọc cần cập nhật?
9. Có xử lý lỗi cache backend, transaction, invalidation và đa node?
10. Có test chứng minh lựa chọn manager thật chứ không chỉ kiểm tra tên trong annotation?

### Tóm tắt một câu

`@Cacheable(cacheNames="books", cacheManager="archiveCacheManager", key="#p0")` có nghĩa: **lấy bean `archiveCacheManager`, tìm vùng `books` bên trong nó, rồi truy cập entry theo key của tham số đầu tiên**. Nếu muốn chọn manager theo từng lời gọi, hãy dùng `CacheResolver` chứ không truyền SpEL vào `cacheManager`.

### Tài liệu tham khảo chính thức

- Spring Framework 6.2 — Declarative annotation-based caching; Custom Cache Resolution và `@CacheConfig`: https://www.springframework.org/spring/reference/6.2/integration/cache/annotations.html
- Spring Framework — `CacheConfig` Javadoc: https://www.springframework.org/spring/docs/6.2.x/javadoc-api/org/springframework/cache/annotation/CacheConfig.html
- Spring Framework — `Cacheable` Javadoc: https://www.springframework.org/spring/docs/6.2.x/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework — `CacheManager` Javadoc: https://www.springframework.org/spring/docs/6.2.x/javadoc-api/org/springframework/cache/CacheManager.html
- Spring Framework — `CachingConfigurer` Javadoc: https://www.springframework.org/spring/docs/6.2.x/javadoc-api/org/springframework/cache/annotation/CachingConfigurer.html
- Spring Boot — Cache auto-configuration: https://docs.spring.io/spring-boot/reference/io/caching.html
