# `getNativeCache` và giới hạn phụ thuộc vào nhà cung cấp

## 1. Mục tiêu và kết luận

Spring Framework cung cấp interface `org.springframework.cache.Cache` để ứng dụng thao tác với cache qua một **API chung**. Interface này có phương thức:

```java
Object getNativeCache();
```

`getNativeCache()` trả về **đối tượng cache gốc hoặc thành phần backend mà implementation sử dụng**, theo cách triển khai của từng `Cache` adapter. Nó là một lối thoát khỏi abstraction khi cần kiểm tra hoặc sử dụng một tính năng chuyên biệt của nhà cung cấp (*provider-specific feature*).

Ba kết luận quan trọng:

1. **`Cache` là hợp đồng chung; đối tượng nhận từ `getNativeCache()` không có hợp đồng kiểu thống nhất.** Kiểu trả về ở interface là `Object`. Với một implementation cụ thể, kiểu thực tế có thể là `ConcurrentMap`, cache của Caffeine hoặc một thành phần Redis. Không thể viết code chung và tự động gọi mọi API native trên các backend khác nhau.
2. **Việc dùng native API tạo ra sự phụ thuộc vào provider, adapter và phiên bản thư viện.** Nếu đổi từ cache in-memory sang Redis hoặc thay adapter/wrapper, một cast hoặc lời gọi method native có thể không còn hợp lệ.
3. **Phần lớn logic ứng dụng nên dùng `Cache`/`CacheManager`, cache annotation và cấu hình provider chính thống.** Chỉ dùng `getNativeCache()` khi thực sự có yêu cầu mà abstraction không cung cấp, và nên cô lập nó trong lớp hạ tầng có kiểm tra kiểu, kiểm thử và đường xử lý không được hỗ trợ.

Ví dụ:

```java
Cache springCache = cacheManager.getCache("books");
Object nativeObject = springCache.getNativeCache();
```

*Đây là đoạn minh họa trong một ứng dụng đã có `cacheManager`, cần kiểm tra `springCache != null` trước khi dùng. Ví dụ runnable đầy đủ ở mục 8.*

**Không thể kết luận** `nativeObject` luôn là `Map`, luôn là kết nối Redis hay luôn có hàm `expireAfterWrite`. Cần xem **implementation cụ thể của bean `Cache` đang được dùng**.

## 2. Spring Cache abstraction nằm ở đâu?

Spring Cache phân biệt các vai trò:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `Cache` | Hợp đồng đọc, ghi, xóa entry, lấy tên và truy cập native cache | `cache.get(key)`, `cache.put(key,value)`, `cache.evict(key)` |
| `CacheManager` | Tra cứu các đối tượng `Cache` bằng tên logic | `manager.getCache("books")` |
| `CacheResolver` | Chọn một hoặc nhiều `Cache` cho một lời gọi/operation | Có thể dựa vào method, đối số hoặc cấu hình |
| Spring cache annotation | Khai báo *khi nào* cache lookup/put/evict xảy ra | `@Cacheable`, `@CachePut`, `@CacheEvict` |
| Native cache/provider | Lưu trữ thật, eviction, TTL, metrics, serialization, cluster | ConcurrentMap, Caffeine, Redis và các adapter khác |

Luồng điển hình:

```text
Business caller
      |
      v
Spring proxy (nếu cache annotation được intercept)
      |
      v
Cache interceptor
      |
      v
CacheResolver / CacheManager
      |
      v
org.springframework.cache.Cache
      |
      +-- get(key) / put(key,value) / evict(key)    <-- API chung
      |
      '-- getNativeCache()                       <-- API escape hatch
              |
              '-- đối tượng khác nhau tùy provider/adapter
```

`getNativeCache()` **không tự kích hoạt** `@Cacheable`, không tìm cache theo tên và không thay thế `@EnableCaching`. Phải có `Cache` instance trước khi gọi nó. Một nơi thường dùng là công cụ chẩn đoán, tích hợp native metrics hoặc một adapter chuyên biệt có yêu cầu rõ.

### 2.1. Hợp đồng của `Cache` có gì?

Những thao tác chung quan trọng gồm:

```java
String name = cache.getName();
Cache.ValueWrapper hit = cache.get(key);
cache.put(key, value);
cache.evict(key);
cache.clear();

Object nativeCache = cache.getNativeCache();
```

*Đây là danh sách API minh họa, không phải một file Java độc lập.*

Các phương thức API chung giúp tránh gắn logic nghiệp vụ vào provider. Tuy nhiên ngay trong abstraction, một số chi tiết như mức đồng bộ khi tải cùng key, thời điểm xóa được quan sát, cache null, TTL và hỗ trợ async vẫn tùy implementation hoặc phiên bản. **API chung không đồng nghĩa mọi backend có cùng toàn bộ đặc tính vận hành.**

### 2.2. `getNativeCache()` không giống `CacheManager.getCache(name)`

Dễ nhầm hai lời gọi có chữ “cache”:

```java
Cache books = cacheManager.getCache("books"); // Spring Cache
Object nativeBooks = books.getNativeCache(); // native object
```

`getCache("books")` là trách nhiệm của **manager**: chọn một vùng cache logic. `getNativeCache()` là trách nhiệm của **adapter Cache**: cho xem đối tượng native bên dưới.

Một cache name có thể được giải quyết tới những implementation khác nhau trong các môi trường khác nhau. Ví dụ cùng tên `"books"` nhưng test chạy `ConcurrentMapCache`, production chạy `RedisCache`. Do đó logic kiểu:

```java
// SAI nếu dùng như mã đa-provider
ConcurrentMap<?, ?> map =
    (ConcurrentMap<?, ?>) cacheManager.getCache("books").getNativeCache();
```

sẽ chỉ phù hợp khi bạn **đã bảo đảm** backend thực sự trả `ConcurrentMap`. Chuyển môi trường sang Redis hoặc Caffeine có thể dẫn đến `ClassCastException`.

## 3. Kiểu native khác nhau giữa các provider

### 3.1. Bảng so sánh

| Spring `Cache` implementation | Ví dụ native object | Ý nghĩa và giới hạn |
| --- | --- | --- |
| `ConcurrentMapCache` | `java.util.concurrent.ConcurrentMap<Object,Object>` | Map cục bộ trong JVM; không tự có TTL, replication hoặc quản trị cluster |
| `CaffeineCache` | `com.github.benmanes.caffeine.cache.Cache<Object,Object>` | Có API native Caffeine như `estimatedSize()`, `stats()`, `policy()`; các tính năng phụ thuộc cấu hình Caffeine |
| `RedisCache` (Spring Data Redis) | `RedisCacheWriter` trong các phiên bản hiện hành của Spring Data Redis | Thành phần ghi/đọc native dưới adapter; **không phải** một `Map`, `RedisTemplate` hay một kết nối Redis có thể cast tùy ý |
| Adapter JCache/JCacheCache | Đối tượng cache theo JCache adapter/provider | Cần xem phiên bản `javax.cache`/provider; không có bảo đảm mọi adapter có cùng kiểu native với Caffeine hay Redis |
| Cache decorator/wrapper | Có thể chuyển tiếp native object hoặc expose implementation riêng | Cần kiểm tra loại wrapper, transaction awareness và `getNativeCache()` của chính lớp đang nhận |

Đây là **ví dụ**, không phải danh sách tất cả provider của Spring. Các thư viện có thể thay đổi API và lớp trả về ở phiên bản khác. Vì thế khi cần native, hãy dùng Javadoc của **đúng phiên bản dependency** trong ứng dụng, thay vì dựa vào tên cache hoặc đoán từ package.

Với Spring Framework 6.1, `ConcurrentMapCache.getNativeCache()` khai báo kiểu trả về cụ thể là `ConcurrentMap<Object,Object>` và `CaffeineCache.getNativeCache()` trả một `com.github.benmanes.caffeine.cache.Cache<Object,Object>` (là native cache đồng bộ, có thể là adapter của async cache tùy cấu hình). Spring Data Redis `RedisCache.getNativeCache()` trả `RedisCacheWriter` ở các phiên bản được tài liệu hóa. Điều đó minh họa rõ **cùng tên phương thức nhưng kiểu native khác nhau**.

### 3.2. “Native” không luôn có nghĩa là “client kết nối datastore”

Ở `ConcurrentMapCache`, native object đúng là một Map lưu trữ trực tiếp.

Ở `RedisCache`, native object có thể là **RedisCacheWriter** — lớp hạ tầng thực hiện các lệnh cache bằng byte arrays và cấu hình liên quan. Nó không tự động cho phép code business thao tác Redis như với `RedisTemplate<String,Book>`, và cũng không trả đối tượng đại diện cho toàn bộ keyspace Redis.

Ở `CaffeineCache`, native object là cache Caffeine bên dưới; nếu Spring wrapper dùng async cache thì có thêm API riêng như `getAsyncCache()` (khi cấu hình hỗ trợ). Không được suy ra từ `getNativeCache()` rằng **mọi** backend đều có cơ chế async tương tự.

Một số adapter còn trang trí cache bằng transaction-aware proxy. Đối tượng `Cache` trả từ manager có thể là wrapper, khiến việc dựa vào exact class hoặc đi xuyên decorator để lấy native trở nên mong manh.

## 4. Cách truy cập native cache an toàn

### 4.1. Tìm đúng cache và kiểm tra null

```java
Cache cache = Objects.requireNonNull(
    cacheManager.getCache("books"),
    "Cache 'books' is not configured"
);
Object nativeStore = cache.getNativeCache();
```

*Đoạn minh họa; phải có import và bean `cacheManager`.*

`CacheManager.getCache(name)` **có thể trả null** nếu không quản lý cache name đó. `Objects.requireNonNull` giúp thất bại rõ ràng thay vì `NullPointerException` mơ hồ ngay ở `getNativeCache()`.

### 4.2. Dùng `instanceof` trước khi cast

```java
Object nativeStore = cache.getNativeCache();

if (nativeStore instanceof ConcurrentMap<?, ?> map) {
    long approximateEntries = map.size();
    System.out.println("Local map entries: " + approximateEntries);
} else {
    System.out.println(
        "Native map inspection unavailable: " +
        nativeStore.getClass().getName()
    );
}
```

*Đoạn minh họa, cần `java.util.concurrent.ConcurrentMap`; muốn xử lý mọi provider thì nên log thông tin loại cache mà không expose dữ liệu.*

Ở đây `instanceof` giúp **không crash do ép kiểu sai**. Nhưng chỉ kiểm tra kiểu **không** làm các tính năng native trở thành portable. Branch này vẫn chỉ dành cho provider trả `ConcurrentMap`.

**Tránh** mã dựa trên tên class:

```java
// MONG MANH: dựa vào tên class hoặc package để suy luận API
if (nativeStore.getClass().getSimpleName().equals("ConcurrentHashMap")) {
    // ...
}
```

Tên class có thể thay đổi do wrapper, subclass, decorator hoặc provider khác. Kiểm tra interface/capability cụ thể đáng tin hơn nếu thật sự cần dùng native API.

### 4.3. Đừng cast thẳng kiểu không kiểm tra

```java
// Không an toàn nếu provider thay đổi:
ConcurrentMap<?, ?> nativeMap =
    (ConcurrentMap<?, ?>) cache.getNativeCache();
```

Đoạn này có thể chạy khi `Cache` là `ConcurrentMapCache`, nhưng fail với cache Redis/Caffeine. Nếu một component phụ thuộc chắc chắn vào Caffeine, có thể khai báo ranh giới của component đó rõ ràng và kiểm tra provider ngay khi khởi động.

### 4.4. Không dùng raw cast để lấy tính năng mà abstraction đã có

Nếu chỉ cần xem entry, ghi entry hoặc xóa key:

```java
Cache.ValueWrapper wrapper = cache.get(bookId);
cache.put(bookId, value);
cache.evict(bookId);
```

hãy dùng **Spring `Cache`**. Dùng native map `put/remove` thay cho `Cache.put/evict` có thể bỏ qua adapter logic và gây khác biệt về điều chỉnh null, key serialization, transaction awareness hay metric.

## 5. Đặc điểm riêng của `ConcurrentMapCache`

`ConcurrentMapCache` là implementation đơn giản dựa trên `ConcurrentMap` trong JVM. Nó hữu ích cho test và ứng dụng nhỏ, nhưng có giới hạn:

- **Local process**: cùng tên cache ở hai JVM khác nhau không bảo đảm chia sẻ entry.
- **Không có hợp đồng TTL/TTI nội tại**: `ConcurrentHashMap` không tự expire key sau N giây.
- **Không có cơ chế distributed replication**: restart JVM làm mất dữ liệu cache in-memory.
- **Không tự cung cấp eviction theo kích thước/chi phí** như cache provider chuyên biệt.
- **Có chuyển đổi giá trị null**: mặc định Spring adapter có thể thay `null` bằng một sentinel nội bộ, vì `ConcurrentHashMap` không lưu `null` trực tiếp.
- **Native map là trạng thái thực**: nếu gọi `map.clear()` hoặc `map.remove(key)`, bạn đang bỏ qua đường `Cache` của Spring.

Đoạn kiểm tra:

```java
Cache cache = Objects.requireNonNull(cacheManager.getCache("books"));

if (cache instanceof ConcurrentMapCache mapCache) {
    ConcurrentMap<Object, Object> nativeMap = mapCache.getNativeCache();
    System.out.println(nativeMap.size());
}
```

*Đoạn minh họa, cần import `org.springframework.cache.concurrent.ConcurrentMapCache`, `ConcurrentMap`, `Objects` và một bean manager thích hợp.*

Cách này biểu lộ rõ dependency vào **Spring ConcurrentMapCache** chứ không còn là code bất biến theo provider.

### 5.1. Vì sao đọc raw value có thể khác `cache.get`?

Khi cho phép cache `null`:

```java
cache.put("missing-book", null);
Cache.ValueWrapper wrapper = cache.get("missing-book");
Object raw = ((ConcurrentMapCache) cache)
    .getNativeCache()
    .get("missing-book");
```

*Đây là minh họa, chỉ hợp lệ với `ConcurrentMapCache` đang cho phép null.*

- `wrapper` **không null**: cache có mapping.
- `wrapper.get()` trả `null`: giá trị nghiệp vụ đã được chuyển ngược lại từ sentinel.
- `raw` có thể là một **đối tượng nội bộ**, không phải `null` như code business kỳ vọng.

Đừng lấy raw value rồi cast thẳng `(Book) raw` khi adapter có khả năng lưu sentinel hoặc dùng store-by-value/serialization. Việc bypass lớp chuyển đổi có thể gây lỗi kiểu, sai null semantics hoặc rò rỉ implementation detail.

### 5.2. Thực hiện thống kê qua `size()` có đáng tin tuyệt đối không?

`ConcurrentMap.size()` là thao tác Java map, nhưng trong hệ thống có ghi đồng thời, con số thu được chỉ phản ánh quan sát tại thời điểm thực hiện; không nên coi đó là snapshot transaction của toàn bộ hệ thống. Nó cũng chỉ đo **một JVM**. Nếu mục tiêu là đo hit/miss hoặc chi phí cache, hãy cân nhắc metrics được provider hỗ trợ thay vì chỉ đếm raw map entries.

## 6. Đặc điểm riêng của Caffeine

Caffeine là thư viện cache local chuyên biệt, có thể hỗ trợ các chính sách như maximum size, TTL/TTI theo thời gian, eviction, statistics và async cache tùy cách xây dựng.

Với Spring `CaffeineCache`, native API trong các phiên bản Spring Framework 6.x có thể lấy như sau:

```java
// Mã minh họa chỉ dành cho Spring CaffeineCache.
if (cache instanceof CaffeineCache caffeineCache) {
    com.github.benmanes.caffeine.cache.Cache<Object, Object> nativeCache =
        caffeineCache.getNativeCache();

    long estimated = nativeCache.estimatedSize();
    System.out.println("Estimated entries: " + estimated);
}
```

*Đoạn này không biên dịch độc lập; cần Spring Caffeine adapter, thư viện Caffeine, các import, và instance `Cache` phù hợp.*

Ví dụ cấu hình backend Caffeine qua `CaffeineCacheManager`:

```java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager = new CaffeineCacheManager("books");
    manager.setCaffeine(
        Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(Duration.ofMinutes(5))
            .recordStats()
    );
    return manager;
}
```

*Đây là một bean minh họa, phải thêm dependency `com.github.ben-manes.caffeine:caffeine` và import `Caffeine`, `CaffeineCacheManager`, `Duration`, `CacheManager`, `Bean`. Không thay thế bean của ví dụ runnable ở mục 8 bằng đoạn này nếu chưa thêm dependency.*

Các lưu ý:

1. `estimatedSize()` là kích thước **ước lượng** của cache Caffeine, không phải một hợp đồng thống kê phổ quát.
2. `nativeCache.stats()` chỉ có ý nghĩa khi provider được cấu hình thu thập statistics (như `recordStats()`); không tự có dữ liệu đầy đủ ở mọi môi trường.
3. `nativeCache.policy()` cho truy cập chính sách native Caffeine, nhưng API và khả năng có sẵn phụ thuộc phiên bản/cấu hình.
4. Đọc/ghi trực tiếp qua native cache có thể bỏ qua các lớp thích ứng của Spring, như xử lý giá trị null.
5. Với cache được xây dựng từ async cache, `CaffeineCache.getAsyncCache()` là API riêng và có thể báo lỗi nếu không có async cache; `getNativeCache()` không đồng nghĩa luôn trả một `AsyncCache`.
6. Caffeine ở cấu hình local không tự trở thành cache phân tán dù dùng tên vùng cache giống nhau trên nhiều node.

Khi cần TTL hoặc maximum size **chỉ ở hạ tầng**, cấu hình provider như trên thường tốt hơn việc truy cập native cache ở từng method nghiệp vụ.

## 7. Đặc điểm riêng của Redis cache

Khi dùng Spring Data Redis, thường sẽ có `RedisCacheManager` và `RedisCache`. API `getNativeCache()` của `RedisCache` ở các phiên bản Spring Data Redis được tài liệu hóa trả **`RedisCacheWriter`**:

```java
// Mã minh họa dành riêng cho Spring Data Redis.
if (cache instanceof RedisCache redisCache) {
    RedisCacheWriter writer = redisCache.getNativeCache();
    System.out.println("Redis writer available: " + (writer != null));
}
```

*Đoạn này không phải demo chạy độc lập; cần dependency Spring Data Redis, các import `RedisCache`, `RedisCacheWriter` và một cache thực sự có loại `RedisCache`.*

Đặc biệt:

- `RedisCacheWriter` là lớp thao tác Redis ở tầng **byte-oriented cache writer**, không phải `RedisTemplate` tổng quát.
- Key trên Redis thường có **prefix theo tên cache**, serializer và conversion riêng; `books::B42` có thể là một cách biểu diễn, không phải một luật tuyệt đối.
- Mã gọi trực tiếp `writer.put(...)` hoặc Redis command cần tự chịu trách nhiệm chuyển đổi key/value, TTL, prefix, lỗi mạng và tương thích định dạng dữ liệu.
- `RedisCacheConfiguration`/`RedisCacheManager` hỗ trợ cấu hình TTL, null caching, key prefix và serializers ở hạ tầng. **Thay vì tự tìm raw client qua `getNativeCache()` để đặt TTL cho mỗi request, hãy ưu tiên đúng API cấu hình.**
- Redis có độ trễ mạng, serialization và vấn đề replication khác hẳn ConcurrentMap/Caffeine. Một cast sang `ConcurrentMap` không có ý nghĩa.
- Một `RedisCache` trong ứng dụng còn có thể nằm dưới transaction-aware decorator, khiến đối tượng Spring `Cache` bên ngoài không nhất thiết có runtime class chính xác là `RedisCache`.

### 7.1. Cấu hình TTL nên ở provider

Ví dụ chỉ mang tính minh họa về Spring Data Redis:

```java
RedisCacheConfiguration config =
    RedisCacheConfiguration.defaultCacheConfig()
        .entryTtl(Duration.ofMinutes(2))
        .disableCachingNullValues();
```

*Đoạn này cần thêm dependency Spring Data Redis, import `RedisCacheConfiguration`/`Duration` và đưa config vào `RedisCacheManager`; một mình nó chưa tạo cache manager.*

Khi cần chính sách khác nhau theo cache name hoặc theo nội dung entry, hãy dùng cấu hình provider/TTL function phù hợp phiên bản thay vì thao tác các byte trên writer trực tiếp trong business service.

### 7.2. Không giả định cùng native API cho mọi Redis client

Ngay cả khi có Redis ở phía sau, đối tượng native từ Spring Cache adapter **không nhất thiết là** một `RedisConnection`, `RedisTemplate`, `Jedis` hoặc `StatefulRedisConnection`. Các abstraction có mục đích khác nhau. Nếu nhu cầu thật là gọi lệnh Redis chuyên biệt, hãy inject công cụ Redis phù hợp ở **adapter hạ tầng riêng**, không lạm dụng `getNativeCache()` như một service locator.

## 8. Demo hoàn chỉnh Java 17+: quan sát native map mà vẫn dùng Spring Cache API

Ví dụ chạy độc lập sử dụng Java 17, Maven, Spring Boot 3.3.5, và `ConcurrentMapCacheManager`. Nó trình diễn:

1. Lấy một `Cache` qua `CacheManager`.
2. Gọi `getNativeCache()` và **kiểm tra kiểu** thay vì ép kiểu mù quáng.
3. Gọi `@Cacheable` từ một Spring-managed bean để tạo một entry.
4. So sánh entry qua Spring `Cache.get` và sự tồn tại key trong native `ConcurrentMap`.
5. Xóa bằng **Spring `Cache.evict`**, rồi quan sát map mất entry.
6. Gọi lại method và thấy body chạy vì cache miss.

### 8.1. Cấu trúc dự án

```text
native-cache-demo/
├── pom.xml
└── src/main/java/example/nativecache/
    ├── NativeCacheApplication.java
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
    <artifactId>native-cache-demo</artifactId>
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

### 8.3. File `src/main/java/example/nativecache/BookService.java`

```java
package example.nativecache;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final AtomicInteger loads = new AtomicInteger();

    @Cacheable(cacheNames = "books", key = "#p0")
    public String findTitle(String bookId) {
        int n = loads.incrementAndGet();
        System.out.println("METHOD_LOAD #" + n + " " + bookId);
        return "TITLE:" + bookId;
    }
}
```

### 8.4. File `src/main/java/example/nativecache/NativeCacheApplication.java`

```java
package example.nativecache;

import java.util.Objects;
import java.util.concurrent.ConcurrentMap;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class NativeCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(NativeCacheApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    CommandLineRunner demo(CacheManager manager, BookService books) {
        return args -> {
            Cache cache = Objects.requireNonNull(
                manager.getCache("books"),
                "Cache books not found"
            );

            System.out.println("SPRING_NAME=" + cache.getName());

            Object nativeObject = cache.getNativeCache();
            System.out.println(
                "NATIVE_IS_CONCURRENT_MAP=" +
                (nativeObject instanceof ConcurrentMap<?, ?>)
            );

            if (!(nativeObject instanceof ConcurrentMap<?, ?> nativeMap)) {
                throw new IllegalStateException("Not a ConcurrentMap cache");
            }

            // Đọc trạng thái entry qua Spring abstraction.
            System.out.println("ENTRY_BEFORE=" + (cache.get("A") != null));

            System.out.println("READ1=" + books.findTitle("A"));
            System.out.println("READ2=" + books.findTitle("A"));

            // Chỉ kiểm tra native map; không mutate nó.
            System.out.println("RAW_HAS_A=" + nativeMap.containsKey("A"));
            System.out.println("RAW_SIZE=" + nativeMap.size());
            System.out.println(
                "ABSTRACTION_VALUE=" +
                Objects.requireNonNull(cache.get("A")).get()
            );

            // Xóa bằng Spring Cache API để giữ ranh giới abstraction.
            cache.evict("A");
            System.out.println(
                "RAW_AFTER_EVICT=" + nativeMap.containsKey("A")
            );

            System.out.println("READ3=" + books.findTitle("A"));
            System.out.println("RAW_END_SIZE=" + nativeMap.size());
        };
    }
}
```

### 8.5. Chạy và kết quả dự kiến

Trong thư mục `native-cache-demo` cần JDK 17+, Maven và khả năng tải dependency lần đầu:

```bash
mvn spring-boot:run
```

Các dòng của ứng dụng demo, **không tính log khởi động Spring Boot**, có thứ tự:

```text
SPRING_NAME=books
NATIVE_IS_CONCURRENT_MAP=true
ENTRY_BEFORE=false
METHOD_LOAD #1 A
READ1=TITLE:A
READ2=TITLE:A
RAW_HAS_A=true
RAW_SIZE=1
ABSTRACTION_VALUE=TITLE:A
RAW_AFTER_EVICT=false
METHOD_LOAD #2 A
READ3=TITLE:A
RAW_END_SIZE=1
```

### 8.6. Phân tích stdout

**Bước 1:** bean `ConcurrentMapCacheManager("books")` tạo cache có tên `books`. `cache.getName()` in `books`. Native object thật của `ConcurrentMapCache` là một `ConcurrentMap` nên `instanceof` trả `true`.

**Bước 2:** trước khi gọi `BookService`, `cache.get("A")` trả `null` (miss), do đó `ENTRY_BEFORE=false`.

**Bước 3:** lần gọi `books.findTitle("A")` đầu tiên đi qua Spring cache proxy, miss, chạy method, in `METHOD_LOAD #1 A` và trả `TITLE:A`. `@Cacheable` lưu value vào key `A` của cache `books`. Lần thứ hai hit, trả cùng value nhưng **không in `METHOD_LOAD #2`**.

**Bước 4:** native map cho thấy key `A` đã có và tổng số entry bằng 1. `Cache.get("A").get()` trả giá trị qua abstraction là `TITLE:A`. Những kết quả này hợp lệ vì demo biết chính xác provider là `ConcurrentMapCache`, không có thread khác hay TTL.

**Bước 5:** `cache.evict("A")` xóa key qua Spring API. Native map phản ánh không còn key đó (`RAW_AFTER_EVICT=false`). Gọi lại `findTitle("A")` miss, chạy method lần thứ hai và ghi lại entry; map kết thúc có một entry.

**Vì sao demo không ném lỗi self-invocation:** `BookService` là Spring bean, được inject vào `CommandLineRunner` và gọi từ bean khác qua proxy. `@EnableCaching` kích hoạt cache infrastructure; `@Cacheable` trên public method là operation cụ thể. Chương trình không tự gọi `this.findTitle()` trong cùng service.

**Đối chiếu với provider khác:** toàn bộ phần nhận `Cache`, `get`, `evict` và annotation vẫn có thể giữ nguyên nếu chuyển sang provider khác, nhưng nhánh `instanceof ConcurrentMap` và các thao tác `containsKey`/`size` **không còn dùng được**. Vì vậy ví dụ có guard rõ và chỉ áp dụng cho manager đã tạo trong demo.

## 9. Những gì `getNativeCache()` không bảo đảm

### 9.1. Không bảo đảm TTL hay expiration portable

Spring `Cache` không có một phương thức chuẩn như:

```java
// API giả định, KHÔNG tồn tại trên org.springframework.cache.Cache:
cache.setTtlForKey("A", Duration.ofSeconds(30));
```

TTL, time-to-idle và eviction policy thuộc về provider. `getNativeCache()` có thể cho tiếp cận cơ chế riêng của một provider, **nhưng không chuẩn hóa cách sử dụng nó**. Cách cấu hình đúng thường là:

- Caffeine: builder với `expireAfterWrite`, `expireAfterAccess`, `maximumSize` và các chính sách phù hợp.
- Redis: `RedisCacheConfiguration`, `RedisCacheManager` và TTL function/config tùy phiên bản.
- `ConcurrentMapCache`: không có TTL tự động; muốn TTL cần một provider có hỗ trợ hoặc xây một abstraction khác.

### 9.2. Không bảo đảm cùng semantics cho null

Spring `Cache` có thể thích ứng `null` qua sentinel. Native store có thể không chứa `null` thực sự, hoặc backend có chính sách null khác. **Đọc raw map hoặc raw Redis bytes là đọc representation ở tầng lưu trữ**, không nhất thiết là giá trị Java logic.

Với `Cache.ValueWrapper`:

```java
Cache.ValueWrapper wrapper = cache.get("A");

if (wrapper == null) {
    System.out.println("MISS");
} else if (wrapper.get() == null) {
    System.out.println("HIT_CACHED_NULL");
} else {
    System.out.println("HIT_VALUE");
}
```

*Đoạn minh họa trong method có biến `cache`; cách phân biệt miss/hit-null dùng API chuẩn của `Cache`, không cần native.*

### 9.3. Không bảo đảm chung key representation

Key do `@Cacheable(key = "#p0")` tạo ra có thể là Java object trong local map, hoặc được chuyển thành byte/string, thêm prefix/cache namespace khi lưu lên Redis. Native API không nhất thiết dùng **key có cùng hình thức** như Spring `Cache.get(Object key)`.

Ví dụ, với Redis cache có prefix theo tên cache, `books::A` có thể là key vật lý tùy cấu hình. Code trực tiếp vào Redis với key `A` không đương nhiên cùng entry. Thay đổi serializer, conversion service hoặc prefix policy còn có thể khiến các key từ hai đường truy xuất không tương thích.

### 9.4. Không bảo đảm atomicity và đồng bộ xuyên process

Mức atomic của `putIfAbsent`, khả năng chống cache stampede, locking, replication delay và consistency đều phụ thuộc implementation. Một `ConcurrentMap` local có đặc tính khác Redis qua mạng. Nếu truy cập native API để tận dụng một operation nguyên tử đặc thù, hãy nêu rõ giả định về concurrency và viết integration test với backend thật.

### 9.5. Không bảo đảm metrics và kích thước chính xác

`Map.size()`, Caffeine `estimatedSize()` và thống kê Redis là các nguồn khác nhau:

- Một số kích thước chỉ là xấp xỉ do concurrent updates/maintenance.
- Một số counters là thống kê của **instance app**, không phải server toàn cục.
- Một số provider cần bật `recordStats()` hoặc tùy chọn thu thập metric riêng.
- Với Redis, cache name thường được ánh xạ sang nhiều key vật lý; không thể coi một native object là container Java của toàn bộ entry.

Đừng xây dashboard đa-provider bằng cách ép mọi native object về `Map`.

### 9.6. Không bảo đảm persistence, eviction và cluster topology

Local map không tự bảo toàn entry qua restart. Caffeine có chính sách local riêng. Redis có topology, memory policy, persistence và replication tùy cấu hình; chúng không “hiện ra” thành một hợp đồng portable qua `getNativeCache()`.

Nếu ứng dụng đổi backend giữa dev/test/prod, hãy xem đó là **thay đổi semantic vận hành**, không đơn thuần là thay class phía sau interface.

### 9.7. Không bảo đảm transaction awareness nếu bypass adapter

Giả sử Spring đang dùng `TransactionAwareCacheManagerProxy` hoặc một decorator trì hoãn `put/evict` đến lúc transaction commit. Nếu code lấy native object và viết trực tiếp, nó có thể **bỏ qua decorator**, khiến cache thay đổi trước khi database commit hoặc ngay cả khi transaction rollback.

Vì vậy không dùng native API để “chữa” các yêu cầu after-commit trong service nghiệp vụ. Hãy thiết kế bằng transaction synchronization, provider configuration hoặc invariant rõ, và kiểm tra với transaction manager thực tế.

## 10. Thao tác native API trực tiếp có những rủi ro gì?

### 10.1. Raw write có thể phá vỡ representation

Một ví dụ **không nên copy vào business code**:

```java
// Ví dụ phản diện: phụ thuộc mạnh vào ConcurrentMapCache.
ConcurrentMap<Object, Object> raw =
    ((ConcurrentMapCache) cache).getNativeCache();

raw.put("A", someRawObject);
```

Tùy cách `someRawObject` được tạo, thao tác đó có thể:

- bypass chuyển đổi `null`/sentinel;
- bypass store-by-value/serialization;
- bypass transaction-aware decorator;
- bypass metrics hoặc callback của cache implementation;
- làm logic Spring đọc dữ liệu sai kiểu hoặc sai cấu trúc.

Nếu mục đích đơn giản là lưu giá trị trả về:

```java
cache.put("A", value);
```

vừa dễ hiểu vừa phù hợp abstraction.

### 10.2. Wrapper và điều kiện `instanceof`

Một lời gọi:

```java
if (cache instanceof ConcurrentMapCache cmc) {
    // ...
}
```

chỉ chạy nếu **Spring `Cache` instance hiện tại** đúng kiểu ấy. Nếu manager đã trả một `TransactionAwareCacheDecorator`, check có thể trả false dù backend thực sự dùng ConcurrentMap. Ngược lại, `cache.getNativeCache()` có thể trả một object native khác tùy wrapper.

**Không nên vòng qua wrapper bằng reflection** để ép lấy field nội bộ. Nếu phải dùng native, nên để một adapter hạ tầng có quyền truy cập thẳng vào đúng provider mà ứng dụng đã cấu hình, với hợp đồng và test rõ.

### 10.3. Security và dữ liệu nhạy cảm

Raw cache có thể chứa dữ liệu đã serialize, token, key định danh khách hàng hoặc payload nội bộ. In ra `nativeCache.toString()` hoặc dump toàn bộ entry trong production dễ làm rò rỉ bí mật. Hãy ưu tiên metrics tổng hợp và ẩn dữ liệu định danh; không expose đối tượng native qua API REST.

### 10.4. Rủi ro dependency và nâng cấp

Nếu business module import `CaffeineCache` hoặc `RedisCacheWriter`, module ấy phải theo các version của provider và Spring adapter. Một nâng cấp lớn có thể đổi return type, serializer, cấu hình hoặc khả năng hỗ trợ async. Cách đặt dependency ít rủi ro hơn là **cô lập mọi code đặc thù trong module hạ tầng**.

## 11. Thiết kế adapter khi bắt buộc dùng native

Thay vì để mọi service biết `getNativeCache()`, có thể tạo một interface theo **năng lực cần dùng**:

```java
public interface CacheDiagnostics {
    String cacheName();
    boolean supportsSizeInspection();
    long estimatedEntryCount();
}
```

*Đây là một interface Java độc lập để minh họa thiết kế; muốn chạy cần implementation.*

Một implementation chỉ dành cho `ConcurrentMapCache`:

```java
public final class ConcurrentMapCacheDiagnostics implements CacheDiagnostics {
    private final ConcurrentMapCache cache;

    public ConcurrentMapCacheDiagnostics(ConcurrentMapCache cache) {
        this.cache = cache;
    }

    @Override
    public String cacheName() {
        return cache.getName();
    }

    @Override
    public boolean supportsSizeInspection() {
        return true;
    }

    @Override
    public long estimatedEntryCount() {
        return cache.getNativeCache().size();
    }
}
```

*Đây là lớp minh họa; cần import interface `CacheDiagnostics` đã định nghĩa ở trên và Spring `ConcurrentMapCache`. Không phải một component tự động có mặt nếu chưa đăng ký bean trong ứng dụng.*

Với Caffeine, có thể có implementation khác gọi `estimatedSize()`; với Redis, có thể chỉ cung cấp metrics thống kê đã được backend hỗ trợ mà không giả vờ biết số lượng entry chính xác.

Thiết kế này giúp:

1. Business code phụ thuộc **năng lực**, không phụ thuộc class provider.
2. Các trường hợp “không hỗ trợ” được diễn đạt tường minh, thay vì `ClassCastException`.
3. Test nhỏ có thể mock `CacheDiagnostics`, còn integration test kiểm tra từng provider.
4. Việc đổi backend không đòi sửa mọi service nghiệp vụ.
5. Có chỗ đặt metric, timeout, phân quyền truy cập, caching policy và cảnh báo riêng.

Trong ví dụ API trên, nên định nghĩa rõ `estimatedEntryCount()` trả số ước lượng trong scope nào và có thể stale đến mức nào; không dùng nó làm điều kiện quyết định bảo mật hoặc giao dịch.

## 12. Cách kiểm thử cho code phụ thuộc provider

### 12.1. Test hợp đồng Spring Cache chung

Với mọi backend mà ứng dụng hỗ trợ, kiểm tra:

- `getCache(name)` trả cache thật khi tên hợp lệ.
- `getName()` đúng tên logic.
- `get(key) == null` khi miss; phân biệt hit chứa null bằng `ValueWrapper` khi provider cho phép.
- `put`/`get`/`evict` hoạt động theo hợp đồng mong đợi.
- Method `@Cacheable` hit thì bỏ qua body khi lời gọi qua proxy.
- Các cache name và key expression giữa `@Cacheable`, `@CachePut`, `@CacheEvict` tương thích.

### 12.2. Test native feature theo từng provider

**ConcurrentMap:**

- Kiểm tra native object là `ConcurrentMap`.
- Kiểm tra size/containsKey sau một put/evict không đồng thời.
- Không suy ra việc cache sẽ expire tự động.

**Caffeine:**

- Kiểm tra cấu hình maximum size, TTL và `recordStats()`.
- Kiểm tra `estimatedSize()`/`stats()` theo tài liệu provider.
- Test đặc điểm async nếu dùng `AsyncCache` thực sự.

**Redis:**

- Kiểm tra TTL/key prefix/serializer trên Redis thật hoặc test container thích hợp.
- Kiểm tra lỗi kết nối và timeout; không assume các thao tác luôn local.
- Kiểm tra việc write-through/invalidation tương thích transaction và nhiều instance.

### 12.3. Test nâng cấp/thay provider

Một bài test chống phụ thuộc đáng có:

```text
Given: business service chỉ dùng org.springframework.cache.Cache
When: thay ConcurrentMapCacheManager bằng provider khác hợp lệ
Then: hành vi nghiệp vụ get/put/evict vẫn đúng

Given: component có native diagnostic cho ConcurrentMap
When: dùng RedisCache
Then: component trả "unsupported" hoặc chọn adapter Redis
      thay vì crash do ClassCastException
```

Không yêu cầu mọi backend hỗ trợ toàn bộ native feature. Quan trọng là **phát hiện capability và phản ứng có chủ đích**.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `Cache.getNativeCache()` có kiểu trả về gì ở interface Spring?

**Đáp án:** `Object`. Các implementation có thể thu hẹp kiểu trả về, nhưng không có một Java interface thống nhất cho tất cả native backends.

**Câu 2.** `ConcurrentMapCache.getNativeCache()` có thể ép về `ConcurrentMap` không?

**Đáp án:** Có với implementation Spring `ConcurrentMapCache` phù hợp: Javadoc trả `ConcurrentMap<Object,Object>`. Không được suy ra mọi Spring `Cache` đều làm vậy.

**Câu 3.** Nếu đổi backend sang Caffeine, có thể tiếp tục gọi `ConcurrentMap.size()` trên native cache không?

**Đáp án:** Không. Native Caffeine cache dùng API khác (như `estimatedSize()`) và cần dependency/configuration phù hợp.

**Câu 4.** `RedisCache.getNativeCache()` có nhất thiết trả `RedisTemplate` hoặc `RedisConnection`?

**Đáp án:** Không. Ở Spring Data Redis theo các phiên bản được tài liệu hóa, nó trả `RedisCacheWriter`. Cần đọc Javadoc đúng phiên bản.

**Câu 5.** Có thể dùng `getNativeCache()` như một cách portable để đặt TTL cho từng entry không?

**Đáp án:** Không. TTL không được chuẩn hóa qua native return type. Hãy cấu hình provider hoặc xây adapter chuyên biệt.

**Câu 6.** Vì sao `cache.get(key)` có thể trả `null` trong khi raw map có entry?

**Đáp án:** `Cache.get(key)` trả `null` khi miss; nếu cache hit chứa giá trị nghiệp vụ `null` thì wrapper có thể tồn tại và `wrapper.get() == null`. Raw map có thể giữ sentinel nội bộ thay cho null.

**Câu 7.** Có nên thay `cache.evict(key)` bằng `((Map) cache.getNativeCache()).remove(key)`?

**Đáp án:** Không nên trong logic chung: vừa không portable, vừa có thể bypass adapter, wrapper, null handling, transaction awareness và provider semantics.

**Câu 8.** Nếu một component chỉ cần ước lượng dung lượng cache, nên thiết kế ra sao?

**Đáp án:** Dùng một interface năng lực/diagnostics, có implementation theo provider và quy tắc fallback rõ. Không giả định mọi provider đều có `size()` với cùng ý nghĩa.

**Câu 9.** Vì sao gọi `getNativeCache()` ở business service dễ gây chi phí nâng cấp?

**Đáp án:** Business service sẽ phụ thuộc vào class và API của provider. Đổi Redis/Caffeine/ConcurrentMap hoặc nâng phiên bản có thể làm gãy cast, methods và các giả định về key/value.

## 14. Tổng kết

- `getNativeCache()` là **escape hatch** để truy cập đối tượng ở tầng dưới `org.springframework.cache.Cache`.
- **Kiểu native phụ thuộc implementation**; không có “native cache chung” có thể dùng API như nhau với ConcurrentMap, Caffeine và Redis.
- `ConcurrentMapCache` → `ConcurrentMap`; `CaffeineCache` → native Caffeine cache; `RedisCache` → trong các phiên bản hiện hành, `RedisCacheWriter`.
- Dùng `Cache.get/put/evict` cho thao tác nghiệp vụ chung. Chỉ dùng native API khi cần **feature provider-specific** và có guard/adapter/test rõ ràng.
- TTL, statistics, serialization, concurrency, replication, null handling và transaction behavior **không được chuẩn hóa hoàn toàn bởi `getNativeCache()`**.
- Khi đổi backend, hãy kiểm thử lại cả hợp đồng abstraction và các nhánh native; không coi thay dependency là thay đổi chỉ về hiệu năng.

## Tài liệu tham khảo

- Spring Framework Javadoc — `Cache`, `getNativeCache` và các API `get/put/evict`: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework Javadoc — `ConcurrentMapCache`, native `ConcurrentMap`: https://docs.spring.io/spring-framework/docs/6.1.0-RC2/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework Javadoc — `CaffeineCache`, `getNativeCache` và `getAsyncCache`: https://docs.spring.io/spring-framework/docs/6.1.0-RC2/javadoc-api/org/springframework/cache/caffeine/CaffeineCache.html
- Spring Framework Reference — *Configuring the Cache Storage*: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework Reference — *TTL/TTI/Eviction policy*: https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html
- Spring Data Redis Reference — `RedisCacheManager` và `RedisCacheConfiguration`: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
- Spring Data Redis Javadoc — `RedisCache`, `getNativeCache()`: https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/cache/RedisCache.html
