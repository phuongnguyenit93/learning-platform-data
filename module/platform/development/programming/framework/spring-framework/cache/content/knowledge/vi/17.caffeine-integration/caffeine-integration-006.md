# Chính sách null khi dùng bộ chuyển đổi Spring với Caffeine

## 1. Vấn đề: Caffeine không nhận null, nhưng Spring Cache có thể hỗ trợ

Caffeine là thư viện cache Java hiệu năng cao. Native Caffeine cache **không cho phép lưu giá trị null**. Nếu gọi trực tiếp native API với một giá trị null, Caffeine sẽ từ chối thao tác.

Tuy nhiên, ứng dụng Spring thường không thao tác trực tiếp native cache. Nó dùng adapter `org.springframework.cache.caffeine.CaffeineCache` thông qua `CaffeineCacheManager`. Adapter này có thể chuyển đổi giá trị null của ứng dụng thành một **đối tượng giữ chỗ nội bộ (sentinel/holder)** trước khi lưu vào Caffeine, rồi chuyển ngược về null khi đọc qua Spring Cache API.

Vì thế có hai lớp chính sách cần phân biệt:

- **Native Caffeine:** chỉ lưu giá trị khác null.
- **Spring Caffeine adapter:** có thể nhận null ở API Spring và lưu một holder thay thế nếu cấu hình cho phép.

Trong Spring Framework 6.1, `CaffeineCacheManager` mặc định **cho phép null** (`allowNullValues = true`), dù Caffeine native không hỗ trợ null. Có thể tắt bằng `setAllowNullValues(false)`. Khi tắt, adapter từ chối một thao tác ghi có giá trị null thay vì chuyển nó thành holder.

Điểm quan trọng: `allowNullValues` là chính sách của **Spring adapter**, không thay đổi bản thân quy tắc của thư viện Caffeine.

## 2. Hai chế độ của `CaffeineCacheManager`

### 2.1. Chế độ mặc định: cho phép null

```java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    // Mặc định allowNullValues = true.
    return manager;
}
```

Với cấu hình trên, khi method `@Cacheable` trả null:

1. Spring cache interceptor nhận kết quả null từ method.
2. `CaffeineCache` kiểm tra chính sách `allowNullValues`.
3. Vì cho phép null, adapter chuyển null thành holder nội bộ.
4. Holder được lưu trong native Caffeine cache như một giá trị khác null.
5. Khi đọc qua `Cache.get(key)`, adapter chuyển holder về giá trị nghiệp vụ null.

Native Caffeine vẫn không hề lưu một giá trị null thực sự. Nó lưu holder do Spring tạo ra.

### 2.2. Tắt null: `setAllowNullValues(false)`

```java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    manager.setAllowNullValues(false);
    return manager;
}
```

Khi tắt chính sách null:

- `CaffeineCache` không chuyển null thành holder.
- Gọi `Cache.put(key, null)` sẽ bị adapter từ chối bằng `IllegalArgumentException`.
- Nếu một method `@Cacheable` trả null và Spring cố ghi kết quả đó vào cache, lời gọi có thể ném exception từ thao tác put.
- Nếu dùng `unless = "#result == null"`, Spring bỏ qua thao tác put, vì thế method vẫn có thể trả null bình thường mà không gặp lỗi do cache.

Đây là lựa chọn hữu ích khi ứng dụng muốn **không cache kết quả rỗng**, hoặc khi dùng chế độ Caffeine async và muốn tránh bọc các giá trị null trong future.

### 2.3. Bảng so sánh

| Hành vi | `allowNullValues=true` | `allowNullValues=false` |
| --- | --- | --- |
| Native Caffeine lưu null trực tiếp | Không | Không |
| Spring adapter nhận null khi put | Có | Không |
| Cách xử lý | Chuyển null thành holder nội bộ | Ném lỗi khi thực sự yêu cầu put null |
| `@Cacheable` trả null, không có `unless` | Có thể lưu negative entry | Thường lỗi tại thao tác put |
| `@Cacheable(unless="#result == null")` | Không lưu null | Không lưu null, không phát sinh lỗi put null |
| `Cache.get(key)` sau một null đã cache | Có `ValueWrapper`, `wrapper.get() == null` | Không có entry nếu put đã bị veto |
| Native Caffeine có giá trị tại key | Có holder khác null | Không có entry |

**Không nhầm “cho phép null” với “luôn phải cache null”.** `allowNullValues=true` chỉ cho adapter khả năng biểu diễn null; annotation, điều kiện `unless` và luồng thực thi vẫn quyết định kết quả có được đưa vào cache hay không.

## 3. Holder nội bộ và cách đọc đúng

### 3.1. Vì sao cần holder?

`ConcurrentHashMap` và native Caffeine đều không cho phép lưu null như một value thông thường. Spring dùng một holder nội bộ để phân biệt:

- cache không có key;
- cache có key và giá trị nghiệp vụ là null.

Hình dung:

```text
Spring Cache API
    |
    | cache.put("B42", null)
    v
CaffeineCache adapter
    |
    | allowNullValues = true
    | null -> internal holder
    v
Native Caffeine
    |
    '-- "B42" -> InternalNullHolder

Khi đọc qua Spring Cache:
    InternalNullHolder -> null
```

Tên và cấu trúc của holder là chi tiết nội bộ của Spring. Không nên cast nó, lưu nó vào domain object hoặc phụ thuộc vào class nội bộ đó trong code nghiệp vụ.

### 3.2. Phân biệt cache miss với cache hit chứa null

Dùng `Cache.ValueWrapper`:

```java
Cache.ValueWrapper wrapper = cache.get("B42");

if (wrapper == null) {
    System.out.println("MISS");
} else if (wrapper.get() == null) {
    System.out.println("HIT_NULL");
} else {
    System.out.println("HIT_VALUE");
}
```

Ba trường hợp:

| Kết quả `cache.get(key)` | Ý nghĩa |
| --- | --- |
| `null` | Không có mapping cho key (cache miss) |
| `ValueWrapper` tồn tại, `wrapper.get() == null` | Có mapping; giá trị nghiệp vụ là null (negative cache hit) |
| `ValueWrapper` tồn tại, `wrapper.get() != null` | Có mapping với dữ liệu bình thường |

Nếu chỉ gọi `cache.get(key, Book.class)` và nhận null, caller có thể không phân biệt được cache miss với entry chứa null. Khi cần phân biệt, dùng `ValueWrapper`.

### 3.3. Native cache có thể chứa holder dù Spring trả null

Nếu cần chẩn đoán implementation Caffeine cụ thể:

```java
CaffeineCache caffeineCache = (CaffeineCache) cache;

Object nativeValue =
        caffeineCache.getNativeCache().getIfPresent("B42");

System.out.println(nativeValue != null);
```

*Đoạn này chỉ phù hợp khi `cache` thực sự là `CaffeineCache` và cache đang cho phép null. Nó minh họa quan sát native storage, không phải cách đọc dữ liệu nghiệp vụ.*

Khi null được cho phép và đã cache, native Caffeine có thể trả một holder khác null. **Không cast native value thành `Book`** và không dùng việc raw value khác null để kết luận dữ liệu nghiệp vụ tồn tại.

Khi dùng wrapper hoặc decorator quanh `CaffeineCache`, kiểm tra `cache instanceof CaffeineCache` có thể không còn đúng. Hãy xem đúng object mà `CacheManager` trả về trước khi dùng API riêng của adapter.

## 4. Chính sách null trong `@Cacheable`

### 4.1. Cho phép null và cache kết quả âm

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(String id) {
    return repository.findById(id).orElse(null);
}
```

*Đoạn minh họa; `Book` và `repository` cần được định nghĩa.*

Nếu `CaffeineCacheManager` cho phép null, lần đầu không tìm thấy sách có thể lưu holder đại diện null. Lần gọi tiếp theo cùng key sẽ hit và không truy vấn repository.

Ưu điểm:

- giảm tải khi cùng một ID không tồn tại bị hỏi nhiều lần;
- hạn chế lặp truy vấn cho các ID âm;
- có thể hữu ích khi not-found tương đối ổn định.

Đổi lại, nếu bản ghi được tạo sau lần tìm kiếm âm, cache có thể tiếp tục trả null cũ cho đến khi entry hết hạn hoặc bị xóa/cập nhật. Đây là **negative caching**, không phải dữ liệu tự đồng bộ.

### 4.2. Không cache null bằng `unless`

`unless` được đánh giá **sau khi method chạy**, khi đã có kết quả:

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public Book findBook(String id) {
    return repository.findById(id).orElse(null);
}
```

Nếu kết quả là null, `unless` trả true và Spring không put giá trị đó. Caller vẫn nhận null; lần gọi sau tiếp tục chạy method vì không có entry âm.

Cách này phù hợp với manager đã tắt null:

```java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    manager.setAllowNullValues(false);
    return manager;
}
```

**Điểm quan trọng:** `unless` không thay đổi kết quả trả về. Nó chỉ ngăn thao tác cache put. Nếu method trả null, caller vẫn nhận null.

### 4.3. Không dùng `condition` để kiểm tra kết quả

`condition` được đánh giá **trước khi gọi method**, nên không thể dùng `#result` để biết method có trả null hay không.

```java
// SAI về thời điểm: #result chưa tồn tại trong condition.
@Cacheable(cacheNames = "books",
           condition = "#result == null")
public Book findBook(String id) {
    return repository.findById(id).orElse(null);
}
```

Dùng `unless` khi quyết định lưu phụ thuộc kết quả trả về. Dùng `condition` khi quyết định có áp dụng cache phụ thuộc đối số đầu vào hoặc metadata đã có trước lời gọi.

### 4.4. Method trả Optional

Spring Cache hỗ trợ `Optional`:

- `Optional.of(book)` được unwrap và lưu đối tượng `Book`.
- `Optional.empty()` được xem như kết quả null ở tầng cache.
- `#result` trong biểu thức `unless` tham chiếu đối tượng nghiệp vụ, không phải wrapper `Optional`.

Ví dụ:

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public Optional<Book> findOptional(String id) {
    return repository.findById(id);
}
```

Nếu repository trả `Optional.empty()`, Spring xem `#result` là null và veto cache put. Không viết `#result.isEmpty()` với giả định `#result` luôn là Optional trong cache SpEL; supported wrapper được unwrap.

### 4.5. Exception khác null

Method trả null là một lần hoàn thành bình thường. Method ném exception thì không có kết quả return bình thường để `@Cacheable` lưu. `unless` không phải exception handler và không chuyển exception thành null.

Nếu muốn trả fallback, method hoặc tầng ngoài phải thực sự trả một giá trị bình thường; khi đó chính sách cache sẽ áp dụng lên fallback ấy, trừ khi điều kiện từ chối lưu.

## 5. Hành vi khi tắt null nhưng quên `unless`

Đây là lỗi cấu hình thường gặp:

```java
@Bean
CacheManager strictCacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    manager.setAllowNullValues(false);
    return manager;
}

@Cacheable(cacheNames = "books",
           cacheManager = "strictCacheManager")
public Book find(String id) {
    return null;
}
```

Khi method được gọi:

1. Cache lookup miss.
2. Method chạy và trả null.
3. Spring cố đưa kết quả vào cache.
4. `CaffeineCache` không chấp nhận null vì `allowNullValues=false`.
5. Adapter ném `IllegalArgumentException`.
6. Caller có thể nhận exception từ cache operation dù thân method đã hoàn thành và trả null.

Do đó, nếu hợp đồng method cho phép “không tìm thấy” và bạn tắt null support, phải thiết kế cách xử lý kết quả rỗng rõ ràng. Với synchronous `@Cacheable`, `unless="#result == null"` là lựa chọn phổ biến.

### 5.1. Không nên bắt mọi exception để giả lập null

Không viết một cache error handler tổng quát chỉ để bỏ qua mọi lỗi put. Điều đó có thể che cả lỗi serialization, backend unavailable, sai key hoặc cấu hình sai. Hãy xác định rõ trường hợp cần bỏ qua là **kết quả null**, rồi veto ngay từ `unless`.

Nếu cache provider lỗi vì mạng, timeout hoặc lỗi vận hành, chính sách `CacheErrorHandler` phải được thiết kế riêng theo yêu cầu availability; đừng đánh đồng lỗi provider với chính sách null.

## 6. Cấu hình Caffeine theo nhu cầu

### 6.1. Cho phép null có kiểm soát

```java
@Bean("nullableCacheManager")
CaffeineCacheManager nullableCacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    manager.setAllowNullValues(true);
    manager.setCaffeine(
        Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(Duration.ofMinutes(5))
    );
    return manager;
}
```

Cấu hình này:

- cho phép Spring adapter biểu diễn null bằng holder;
- giới hạn dung lượng cache theo cấu hình Caffeine;
- đặt thời gian hết hạn sau khi ghi;
- vẫn không làm native Caffeine chấp nhận null trực tiếp.

Nếu dùng negative caching, TTL nên được chọn theo mức stale mà nghiệp vụ chấp nhận. Có thể cần TTL âm ngắn hơn TTL của kết quả dương, hoặc tách cache âm/dương để cấu hình riêng.

### 6.2. Từ chối null

```java
@Bean("strictCacheManager")
CaffeineCacheManager strictCacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    manager.setAllowNullValues(false);
    manager.setCaffeine(
        Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(Duration.ofMinutes(5))
    );
    return manager;
}
```

Cấu hình này buộc các method cacheable phải tránh put null, ví dụ bằng `unless`. Nó phù hợp khi ứng dụng không muốn giữ negative entry và muốn lỗi xuất hiện rõ nếu code vô tình cố lưu null.

### 6.3. Thiết lập trước khi cache được sử dụng

Nên cấu hình `allowNullValues` ngay khi tạo manager, trước khi cache được sử dụng trong application context. Tránh thay đổi chính sách null tùy tiện khi cache đang chứa dữ liệu, vì các entry cũ có thể đã được lưu dưới representation khác.

Nếu đăng ký custom native Caffeine caches qua `registerCustomCache`, cần xem overload và cấu hình adapter được dùng khi đăng ký; không giả định một native cache tự biết chính sách null của Spring.

## 7. Chế độ async của Caffeine trong Spring Framework 6.1+

Spring Framework 6.1 bổ sung hỗ trợ Caffeine `AsyncCache` thông qua `CaffeineCacheManager.setAsyncCacheMode(true)`. Chế độ này hỗ trợ API `Cache.retrieve(...)` và cách cache kết quả bất đồng bộ.

```java
@Bean
CaffeineCacheManager asyncCacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    manager.setAsyncCacheMode(true);
    manager.setAllowNullValues(false);
    return manager;
}
```

Tài liệu Spring khuyến nghị **tắt null values trong async cache mode**, dù null vẫn được hỗ trợ. Lý do là future handle do Caffeine cung cấp có thể được dùng trực tiếp hơn, tránh phải bọc future để biểu diễn null và giúp semantics của kết quả bất đồng bộ đơn giản hơn.

Một số điểm cần phân biệt:

- `setAsyncCacheMode(true)` không làm mọi method Java tự động bất đồng bộ; nó cấu hình loại cache native mà manager tạo.
- `CompletableFuture`/reactive caching còn phụ thuộc return type, phiên bản Spring và provider.
- Khi dùng async mode, hãy kiểm tra cách biểu diễn cache miss, null và lỗi qua `Cache.retrieve`; không áp dụng máy móc ví dụ synchronous `ValueWrapper` cho mọi future result.
- Nếu ứng dụng không cần async cache, dùng synchronous mode mặc định sẽ đơn giản hơn.

## 8. Ví dụ Java 17+ chạy được: so sánh ba chính sách null

Ví dụ dùng Java 17+, Maven, Spring Boot 3.3.5, Spring Cache và Caffeine. Ba manager/cache minh họa:

1. `nullableManager`: cho phép null, Spring adapter cache null bằng holder.
2. `strictManager`: từ chối null; một method không có `unless` sẽ gặp lỗi khi put null.
3. Cùng `strictManager`: method có `unless` không ghi null; method trả `Optional.empty()` cũng không ghi null.

### 8.1. Cấu trúc dự án

```text
caffeine-null-policy/
├── pom.xml
└── src/main/java/example/caffeinenull/
    ├── CaffeineNullApplication.java
    └── BookService.java
```

### 8.2. File `pom.xml`

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
    <artifactId>caffeine-null-policy</artifactId>
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
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
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

Spring Boot parent quản lý phiên bản dependency tương thích; không cần tự đặt version Caffeine trong ví dụ này.

### 8.3. File `src/main/java/example/caffeinenull/BookService.java`

```java
package example.caffeinenull;

import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final AtomicInteger nullableCalls = new AtomicInteger();
    private final AtomicInteger strictCalls = new AtomicInteger();
    private final AtomicInteger skipNullCalls = new AtomicInteger();
    private final AtomicInteger optionalCalls = new AtomicInteger();

    @Cacheable(
        cacheNames = "nullableBooks",
        cacheManager = "nullableManager",
        key = "#p0"
    )
    public Book findWithNullableAdapter(String id) {
        int n = nullableCalls.incrementAndGet();
        System.out.println("LOAD nullable #" + n + " " + id);
        return null;
    }

    @Cacheable(
        cacheNames = "strictBooks",
        cacheManager = "strictManager",
        key = "#p0"
    )
    public Book findWithStrictAdapter(String id) {
        int n = strictCalls.incrementAndGet();
        System.out.println("LOAD strict #" + n + " " + id);
        return null;
    }

    @Cacheable(
        cacheNames = "strictBooks",
        cacheManager = "strictManager",
        key = "#p0",
        unless = "#result == null"
    )
    public Book findWithoutCachingNull(String id) {
        int n = skipNullCalls.incrementAndGet();
        System.out.println("LOAD skip #" + n + " " + id);
        return null;
    }

    @Cacheable(
        cacheNames = "optionalBooks",
        cacheManager = "strictManager",
        key = "#p0",
        unless = "#result == null"
    )
    public Optional<Book> findOptional(String id) {
        int n = optionalCalls.incrementAndGet();
        System.out.println("LOAD optional #" + n + " " + id);
        return Optional.empty();
    }

    public int skipNullCalls() {
        return skipNullCalls.get();
    }

    public int optionalCalls() {
        return optionalCalls.get();
    }
}
```

### 8.4. File `src/main/java/example/caffeinenull/CaffeineNullApplication.java`

```java
package example.caffeinenull;

import java.time.Duration;
import java.util.Objects;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import com.github.benmanes.caffeine.cache.Caffeine;

@SpringBootApplication
@EnableCaching
public class CaffeineNullApplication {
    public static void main(String[] args) {
        SpringApplication.run(CaffeineNullApplication.class, args);
    }

    @Bean("nullableManager")
    CaffeineCacheManager nullableManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("nullableBooks");
        manager.setAllowNullValues(true);
        manager.setCaffeine(
            Caffeine.newBuilder()
                .maximumSize(1_000)
                .expireAfterWrite(Duration.ofMinutes(5))
        );
        return manager;
    }

    @Bean("strictManager")
    CaffeineCacheManager strictManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("strictBooks", "optionalBooks");
        manager.setAllowNullValues(false);
        manager.setCaffeine(
            Caffeine.newBuilder()
                .maximumSize(1_000)
                .expireAfterWrite(Duration.ofMinutes(5))
        );
        return manager;
    }

    @Bean
    CommandLineRunner demo(
        BookService service,
        @Qualifier("nullableManager") CacheManager nullableManager,
        @Qualifier("strictManager") CacheManager strictManager
    ) {
        return args -> {
            Cache nullable = Objects.requireNonNull(
                nullableManager.getCache("nullableBooks")
            );

            System.out.println(
                "NULLABLE1 => " +
                service.findWithNullableAdapter("MISSING")
            );
            System.out.println(
                "NULLABLE2 => " +
                service.findWithNullableAdapter("MISSING")
            );

            Cache.ValueWrapper wrapper = nullable.get("MISSING");
            System.out.println(
                "NULLABLE_HIT_NULL => " +
                (wrapper != null && wrapper.get() == null)
            );

            CaffeineCache nativeCache = (CaffeineCache) nullable;
            System.out.println(
                "NATIVE_HOLDER_PRESENT => " +
                (nativeCache.getNativeCache().getIfPresent("MISSING") != null)
            );

            Cache strict = Objects.requireNonNull(
                strictManager.getCache("strictBooks")
            );

            try {
                service.findWithStrictAdapter("STRICT_MISSING");
            } catch (IllegalArgumentException ex) {
                System.out.println(
                    "STRICT_ERROR => " + ex.getClass().getSimpleName()
                );
            }
            System.out.println(
                "STRICT_ENTRY_PRESENT => " +
                (strict.get("STRICT_MISSING") != null)
            );

            System.out.println(
                "SKIP1 => " + service.findWithoutCachingNull("SKIP_MISSING")
            );
            System.out.println(
                "SKIP2 => " + service.findWithoutCachingNull("SKIP_MISSING")
            );
            System.out.println("SKIP_CALLS => " + service.skipNullCalls());
            System.out.println(
                "SKIP_ENTRY_PRESENT => " +
                (strict.get("SKIP_MISSING") != null)
            );

            Cache optional = Objects.requireNonNull(
                strictManager.getCache("optionalBooks")
            );
            System.out.println(
                "OPTIONAL1 => " + service.findOptional("OPTIONAL_MISSING")
            );
            System.out.println(
                "OPTIONAL2 => " + service.findOptional("OPTIONAL_MISSING")
            );
            System.out.println(
                "OPTIONAL_CALLS => " + service.optionalCalls()
            );
            System.out.println(
                "OPTIONAL_ENTRY_PRESENT => " +
                (optional.get("OPTIONAL_MISSING") != null)
            );
        };
    }
}
```

### 8.5. Dọn import trước khi chạy

Trong file `CaffeineNullApplication.java`, bỏ import không dùng sau đây:

```java
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
```

Import này không cần thiết trong demo. Các import còn lại được dùng trong cấu hình, inspection hoặc dependency injection.

### 8.6. Lệnh chạy

Tại thư mục `caffeine-null-policy`, cần JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Các dòng do demo tự in theo thứ tự sau (bỏ qua banner và log khởi động Spring Boot):

```text
LOAD nullable #1 MISSING
NULLABLE1 => null
NULLABLE2 => null
NULLABLE_HIT_NULL => true
NATIVE_HOLDER_PRESENT => true
LOAD strict #1 STRICT_MISSING
STRICT_ERROR => IllegalArgumentException
STRICT_ENTRY_PRESENT => false
LOAD skip #1 SKIP_MISSING
SKIP1 => null
LOAD skip #2 SKIP_MISSING
SKIP2 => null
SKIP_CALLS => 2
SKIP_ENTRY_PRESENT => false
LOAD optional #1 OPTIONAL_MISSING
OPTIONAL1 => Optional.empty
LOAD optional #2 OPTIONAL_MISSING
OPTIONAL2 => Optional.empty
OPTIONAL_CALLS => 2
OPTIONAL_ENTRY_PRESENT => false
```

### 8.7. Giải thích kết quả

**Nhóm 1 — Adapter cho phép null:**

- Lần đầu `findWithNullableAdapter("MISSING")` miss, method chạy và trả null. Adapter lưu holder vào native Caffeine.
- Lần hai hit holder; method không chạy lại, nên chỉ có một dòng `LOAD nullable`.
- `NULLABLE_HIT_NULL=true` chứng minh Spring `ValueWrapper` tồn tại nhưng giá trị nghiệp vụ là null.
- `NATIVE_HOLDER_PRESENT=true` chứng minh native Caffeine có một value khác null tại key. Đó là holder do adapter dùng, không phải một null native.

**Nhóm 2 — Adapter từ chối null:**

- `findWithStrictAdapter` chạy và trả null.
- Cache interceptor cố put kết quả; strict adapter từ chối null và phát `IllegalArgumentException`.
- Không có entry tại key `STRICT_MISSING`.

**Nhóm 3 — Strict adapter kết hợp `unless`:**

- Method chạy ở cả hai lượt vì `unless` veto put null.
- Không phát sinh lỗi do adapter không bao giờ nhận lệnh put null.
- Không có entry tại key `SKIP_MISSING`.

**Nhóm 4 — `Optional.empty()`:**

- Spring unwrap Optional; `#result` đại diện giá trị nghiệp vụ null.
- `unless="#result == null"` veto put.
- Caller vẫn nhận `Optional.empty()`; hai lượt đều chạy method và không có entry trong `optionalBooks`.

Chương trình dùng cache Caffeine local trong một JVM và gọi tuần tự để stdout có thể dự đoán. Ví dụ không kiểm tra transaction, nhiều node hoặc race condition. Mã và output đã được rà soát theo luồng thực thi; để xác nhận runtime cần chạy Maven với JDK 17+.

## 9. Những lỗi thường gặp

1. **Nghĩ native Caffeine lưu null trực tiếp.** Native cache không chấp nhận null; Spring adapter dùng holder nếu được cấu hình cho phép.
2. **Cho rằng CaffeineCacheManager mặc định từ chối null.** Mặc định của Spring adapter là `allowNullValues=true`, dù native Caffeine không hỗ trợ null.
3. **Tắt null support nhưng quên `unless`.** Method trả null có thể khiến thao tác put ném `IllegalArgumentException`.
4. **Nhầm `unless` với `condition`.** `condition` chạy trước method; `unless` chạy sau khi có result.
5. **Cho rằng `unless=true` làm caller nhận exception hoặc giá trị khác.** Caller vẫn nhận kết quả method; chỉ thao tác put bị bỏ qua.
6. **Nhầm cache miss với hit null.** Dùng `Cache.ValueWrapper` để phân biệt; không chỉ nhìn giá trị đã unwrap.
7. **Đọc native cache rồi cast holder thành domain object.** Native value có thể là sentinel nội bộ; chỉ dùng Spring abstraction cho logic nghiệp vụ.
8. **Dùng raw Caffeine API để put null.** Caffeine native từ chối null; hãy dùng adapter Spring và chính sách null phù hợp.
9. **Coi `Optional.empty()` là một wrapper không liên quan đến null.** Spring unwrap supported Optional khi cache và trong `#result`.
10. **Dùng `@Cacheable(sync=true, unless="#result == null")`.** Spring không hỗ trợ kết hợp `sync=true` với `unless` trong cùng operation; cần chọn cơ chế concurrency khác nếu cần.
11. **Dùng chung cache manager cho các cache cần chính sách null khác nhau.** `allowNullValues` là cấu hình manager; nếu cần hai chính sách, có thể tạo manager/cache adapter riêng hoặc thiết kế cache riêng có cấu hình tương ứng.
12. **Cho rằng tắt null support tự giải quyết negative caching.** Nó chỉ từ chối put null; phải xác định method trả null, Optional.empty hay exception và chọn chính sách phù hợp.
13. **Bỏ qua thay đổi async mode.** Với Spring 6.1+ Caffeine async cache, tài liệu khuyến nghị tắt null để đơn giản hóa semantics future.
14. **Dùng null như trạng thái nghiệp vụ duy nhất.** Với domain phức tạp, một result type rõ ràng (found/not-found/error) có thể dễ bảo trì hơn; biểu thức `unless` cần phản ánh đúng hợp đồng đó.
15. **Không test trên đúng provider.** Một cache local cho phép null không chứng minh Redis, JCache hoặc native Caffeine trực tiếp có semantics tương tự.

## 10. Cách chọn chính sách

| Yêu cầu | Cấu hình/hành vi phù hợp |
| --- | --- |
| Muốn nhớ kết quả không tìm thấy để giảm tải | Cho phép null ở adapter; đặt TTL âm ngắn và invalidation khi dữ liệu được tạo |
| Muốn mỗi lần null đều truy vấn lại nguồn | `setAllowNullValues(false)` kết hợp `unless="#result == null"` |
| Muốn tắt null trên toàn manager | `setAllowNullValues(false)`; rà soát mọi method có thể trả null |
| Dùng `Optional.empty()` và không muốn cache âm | `unless="#result == null"` |
| Dùng async Caffeine cache Spring 6.1+ | Cân nhắc `setAllowNullValues(false)` theo khuyến nghị Spring |
| Chỉ cần kiểm tra có entry hay không | Dùng `Cache.get(key)` và `ValueWrapper`; không đọc raw native holder |
| Cần TTL hoặc size policy | Cấu hình Caffeine builder/manager, không dùng null policy để thay thế |

Một cấu hình strict chỉ an toàn khi các operation đã được rà soát. Nếu một method có thể trả null mà không có `unless`, lỗi sẽ chỉ lộ ra ở runtime khi cache put được thực hiện.

## 11. Checklist kiểm thử

- [ ] Cache miss với kết quả khác null: method chạy và kết quả được cache.
- [ ] Cache hit với kết quả khác null: method không chạy lại.
- [ ] Cache hit chứa null khi `allowNullValues=true`: `ValueWrapper` tồn tại và `wrapper.get()==null`.
- [ ] Native Caffeine có holder khác null sau khi Spring cache null.
- [ ] `allowNullValues=false` và method trả null không có `unless`: cache put bị từ chối.
- [ ] `allowNullValues=false` và `unless="#result == null"`: caller nhận null, không có entry và không có lỗi put.
- [ ] Method trả `Optional.empty()`: kiểm tra `#result` được unwrap và entry không được lưu khi dùng unless.
- [ ] Method ném exception: phân biệt với method trả null.
- [ ] Kiểm tra cache key, cache name và manager được dùng thực tế.
- [ ] Nếu dùng async mode, kiểm thử future/retrieve và null semantics riêng.
- [ ] Nếu dùng negative caching, kiểm tra TTL, invalidation và trường hợp bản ghi được tạo sau lần miss.
- [ ] Chạy integration test với đúng phiên bản Spring và Caffeine đang dùng trong dự án.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Caffeine native không hỗ trợ null. Vì sao Spring Caffeine adapter vẫn có thể cache null?

**Đáp án:** `CaffeineCache` có thể chuyển null thành holder nội bộ khi `allowNullValues=true`; native Caffeine lưu holder khác null, còn adapter unwrap thành null khi đọc.

**Câu 2.** `CaffeineCacheManager` mặc định cho phép null hay không?

**Đáp án:** Có. Trong Spring Framework 6.1, mặc định `allowNullValues=true` dù native Caffeine không lưu null trực tiếp.

**Câu 3.** Điều gì xảy ra nếu manager dùng `setAllowNullValues(false)` và một `@Cacheable` trả null nhưng không có `unless`?

**Đáp án:** Cache interceptor cố put null; adapter từ chối bằng `IllegalArgumentException`. Caller có thể nhận exception phát sinh ở cache operation dù thân method đã trả null.

**Câu 4.** Dùng `unless="#result == null"` với strict manager có trả lỗi không?

**Đáp án:** Không do thao tác put null, vì `unless` veto thao tác put. Caller vẫn nhận null.

**Câu 5.** Vì sao `Cache.get(key)` có thể trả wrapper dù giá trị bên trong là null?

**Đáp án:** Wrapper biểu thị entry tồn tại. Giá trị nghiệp vụ null được lưu bằng holder nội bộ nên cần phân biệt hit-null với miss.

**Câu 6.** Method trả `Optional.empty()`, `#result` trong `unless` là gì?

**Đáp án:** Spring Cache unwrap supported Optional; `#result` là null, không phải wrapper Optional. Do đó `unless="#result == null"` có thể veto việc cache empty result.

**Câu 7.** Có thể dùng `@Cacheable(sync=true, unless="#result == null")` không?

**Đáp án:** Không. Spring không hỗ trợ tổ hợp `sync=true` và `unless` trong cùng operation.

**Câu 8.** Muốn cache negative result trong 5 giây nhưng cache kết quả dương trong 5 phút, chỉ gọi `setAllowNullValues(true)` có đủ không?

**Đáp án:** Không. Chính sách này chỉ cho phép biểu diễn null. Cần cấu hình TTL khác nhau cho entry âm/dương bằng cache riêng, provider policy hoặc cơ chế phù hợp.

## Tài liệu tham khảo chính thức

- Spring Framework Javadoc — `CaffeineCacheManager`, mặc định `allowNullValues=true` và `setAllowNullValues`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework Javadoc — `CaffeineCache`, adapter trên native Caffeine và tham số `allowNullValues`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/caffeine/CaffeineCache.html
- Spring Framework Javadoc — `AbstractValueAdaptingCache`, chuyển đổi null/holder: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/support/AbstractValueAdaptingCache.html
- Spring Framework Reference — Declarative Annotation-based Caching, `unless` và Optional: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `Cache` và `Cache.ValueWrapper`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/Cache.html
- Caffeine documentation — native cache API and null-value constraints: https://github.com/ben-manes/caffeine/wiki
