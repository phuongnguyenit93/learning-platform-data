# TTL, TTI và chính sách loại bỏ thuộc cấu hình kho cache

> **Ngữ cảnh:** Spring Framework Cache — mục **Dữ liệu và vòng đời**. Bài học giải thích vì sao `@Cacheable` không tự quy định thời gian sống, thời gian nhàn rỗi hay chiến lược loại bỏ mục cache; những chính sách đó phải được thiết lập trên **cache provider** hoặc cache implementation thực tế. Trọng tâm là phân biệt **TTL**, **TTI**, **size-based eviction**, kiểm soát vòng đời và áp dụng chính xác trên Caffeine/Redis.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **TTL (Time To Live)**, **TTI (Time To Idle)**, eviction theo dung lượng và invalidation theo nghiệp vụ.
2. Giải thích trách nhiệm của Spring Cache abstraction so với trách nhiệm của nhà cung cấp cache.
3. Chọn `expireAfterWrite`, `expireAfterAccess` hoặc `maximumSize` trên Caffeine, và TTL/TTI phù hợp trên Redis.
4. Hiểu vì sao `ConcurrentMapCacheManager` mặc định không tự hết hạn mục cache theo thời gian.
5. Viết một ví dụ Java 17 có **đồng hồ giả** để kiểm chứng chính xác thời điểm hit/miss mà không cần `Thread.sleep()`.
6. Thiết kế kiểm thử cho expiry, eviction, dữ liệu mới sau cập nhật, đa instance và hiệu năng.
7. Tránh những nhầm lẫn: `@Cacheable` không có tham số TTL chuẩn, TTL không bằng TTI, thời điểm hết hạn logic không phải thời điểm bộ nhớ vật lý được thu hồi.

## 2. Spring Cache quyết định điều gì, provider quyết định điều gì?

Ứng dụng Spring sử dụng annotation:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product findProduct(String productId) {
    return repository.find(productId);
}
```

Đây là **đoạn mã minh họa** cho một bean có repository và lớp Product; chưa phải chương trình Java độc lập.

`@Cacheable` yêu cầu: kiểm tra mục cache cho key; nếu hit thì có thể trả kết quả mà không thực thi thân phương thức; nếu miss thì chạy method rồi lưu kết quả theo chính sách. Những phần khác của Spring Cache gồm `@CachePut` để cập nhật mục và `@CacheEvict` để xóa mục.

Tuy vậy, `@Cacheable` **không định nghĩa một chính sách TTL/TTI/size-eviction chuẩn**. Các tính năng này rất khác nhau giữa map trong JVM, Caffeine, Redis, JCache và những provider khác.

```text
Client
  |
  v
Spring proxy / cache interceptor
  |
  +--> Chọn cache theo cacheNames / CacheResolver
  +--> Sinh key
  +--> Cache.get(key) --> HIT? --> trả value
  |                       |
  |                      MISS
  |                       |
  +--> chạy phương thức, Cache.put(key, value)
                            |
                            v
                    Provider / Cache store
                    |                 |
                    |                 +--> TTL / TTI (nếu hỗ trợ)
                    +--> maximumSize / eviction
                    +--> storage, serialization, expiry
```

Spring Cache cung cấp hợp đồng thao tác; **provider quản lý dữ liệu đã lưu, thời điểm mục không còn hợp lệ, tiêu thụ bộ nhớ và kỹ thuật loại bỏ**.

Tài liệu Spring Framework trả lời trực tiếp câu hỏi “How can I set the TTL/TTI/Eviction policy?” bằng cách yêu cầu cấu hình tính năng này **trực tiếp qua cache provider**. Vì vậy sẽ không có một công thức `@Cacheable(ttl = 60)` chuẩn hoạt động nhất quán cho mọi cache manager.

## 3. TTL — Time To Live: sống bao lâu kể từ khi được ghi?

Trong cách dùng phổ biến, TTL quy định khoảng thời gian mục cache còn hợp lệ tính từ lúc **được tạo hoặc ghi/cập nhật**. Trên Caffeine, chính sách tương ứng thường là `expireAfterWrite`.

Giả sử `ttl = 5 giây`, thời gian tính từ lần ghi gần nhất:

| Thời điểm | Sự kiện | Kết quả truy cập key A |
| --- | --- | --- |
| `t = 0s` | Miss, tính A rồi ghi cache | Mục A được tạo |
| `t = 3s` | Đọc A | Hit, nhưng **không kéo dài** tuổi theo `expireAfterWrite` |
| `t = 4s` | Đọc A | Hit, thời điểm hết hạn vẫn tính từ `t = 0` |
| `t = 6s` | Đọc A | Miss do đã quá 5 giây từ lần ghi |
| `t = 6s` | Tính A mới, ghi lại | Bắt đầu khoảng TTL mới |

Ví dụ đó giả định không có eviction hoặc invalidation khác và loader thành công.

**Quan trọng:** tên gọi “TTL” không tự quy định cách provider tính mốc bắt đầu. Một số sản phẩm coi TTL là hạn sau write; có hệ thống đặt TTL trên key ở mỗi lần ghi; có chính sách biến thiên theo entry. Luôn xem API/provider cụ thể. Trong bài này, khi nói TTL theo Caffeine ta đang nói `expireAfterWrite`; còn với Redis nói TTL được gắn vào key và thao tác ghi có thể thiết lập lại hạn.

TTL có ích khi dữ liệu được chấp nhận cũ trong một khoảng **tối đa tương đối kể từ lần tải**, kể cả được đọc thường xuyên.

## 4. TTI — Time To Idle: quá lâu không truy cập thì hết hạn

TTI quy định thời gian nhàn rỗi tối đa. Caffeine có `expireAfterAccess`, thường làm mới “mốc truy cập gần nhất” khi item được **đọc hoặc ghi** qua cache.

Giả sử `tti = 5 giây`, với cùng key A:

| Thời điểm | Sự kiện | Kết quả |
| --- | --- | --- |
| `t = 0s` | Miss, tạo A | Bắt đầu bộ đếm idle |
| `t = 4s` | Đọc A | Hit, làm mới mốc truy cập |
| `t = 8s` | Đọc A | Hit, chỉ 4 giây từ lần truy cập trước |
| `t = 14s` | Đọc A | Miss, đã 6 giây không truy cập |
| `t = 14s` | Tính A mới | Bắt đầu khoảng idle mới |

Khác biệt rõ nhất: nếu key được dùng liên tục với khoảng cách nhỏ hơn TTI, mục có thể sống lâu hơn rất nhiều so với thời gian cấu hình, cho đến khi bị loại bởi chính sách khác.

### TTL và TTI có thể cùng tồn tại không?

Trên Caffeine, bạn có thể kết hợp:

```java
Caffeine.newBuilder()
    .expireAfterWrite(Duration.ofMinutes(10))
    .expireAfterAccess(Duration.ofMinutes(2))
    .maximumSize(10_000);
```

Đây là **đoạn builder minh họa**, không phải chương trình hoàn chỉnh. Ý định là cache item hết hạn nếu **một trong hai** điều kiện expiry xảy ra: sống quá lâu kể từ lần ghi hoặc nhàn rỗi quá lâu. Đặt cả hai không có nghĩa TTI tự “gia hạn” expiry theo write: mỗi cơ chế có mốc thời gian riêng.

Các provider khác có thể không hỗ trợ đồng thời hoặc có cách diễn giải khác. Đừng giả định mọi cache đọc `GET` đều làm mới idle-time.

## 5. Eviction — loại bỏ do dung lượng hoặc chính sách lưu trữ

**Expiration** làm mục không còn hợp lệ khi đạt điều kiện về thời gian. **Eviction** thường là việc loại bỏ một mục để quản lý dung lượng/tài nguyên hoặc theo thuật toán lựa chọn mục.

Ví dụ với Caffeine:

```java
Caffeine.newBuilder()
    .maximumSize(500)
    .expireAfterWrite(Duration.ofMinutes(10));
```

- `maximumSize(500)` đặt **ngưỡng dung lượng** (số entry tối đa theo chính sách thực thi). Provider có thể loại bớt mục trước khi chúng hết TTL.
- `expireAfterWrite(10 phút)` là **expiry theo thời gian**.
- Caffeine sử dụng chính sách lựa chọn ứng viên eviction dựa trên đặc tính truy cập; **không nên khẳng định nó là FIFO hoặc LRU thuần**.
- Tác động chính xác của size eviction còn phụ thuộc access pattern, cấu hình weighted size và việc provider thực hiện bảo trì.

**Kết luận:** một mục có thể miss dù chưa hết TTL vì bị loại theo kích thước; và một mục có thể miss khi còn nhiều chỗ trống vì hết TTL. Hai nguyên nhân không loại trừ nhau.

### Expiration, eviction và invalidation

| Thuật ngữ | Lý do | Ví dụ |
| --- | --- | --- |
| **Expiration** | Không còn hợp lệ theo thời gian | TTL 10 phút, TTI 2 phút |
| **Capacity eviction** | Giới hạn bộ nhớ/dung lượng hoặc chính sách thay thế | Cache đạt `maximumSize` |
| **Explicit invalidation** | Nghiệp vụ yêu cầu bỏ dữ liệu cũ | `@CacheEvict(key = ...)` sau cập nhật |
| **Clear all** | Xóa toàn bộ một vùng cache theo chủ đích | `@CacheEvict(allEntries = true)` |

Với Spring, `@CacheEvict` cho phép **chủ động xóa** khi nghiệp vụ thay đổi. Annotation đó không thiết lập một bộ đếm thời gian tự động; TTL/TTI phải được cấu hình tại provider.

## 6. Cấu hình Caffeine trong Spring Boot

Nếu ứng dụng dùng Spring Boot auto-configuration với dependency cache và Caffeine, có thể đặt:

```properties
spring.cache.type=caffeine
spring.cache.cache-names=products,prices
spring.cache.caffeine.spec=maximumSize=500,expireAfterWrite=600s
```

Cấu hình này tương ứng **giới hạn 500 entry và 600 giây sau write** cho các cache do manager auto-configure, theo Caffeine specification syntax. Nếu muốn **TTI** thay vì TTL theo write:

```properties
spring.cache.type=caffeine
spring.cache.cache-names=products,prices
spring.cache.caffeine.spec=maximumSize=500,expireAfterAccess=600s
```

Đây là **hai phương án thay thế nhau**, không phải hai dòng `spring.cache.caffeine.spec` nên xuất hiện cùng lúc trong một file. Có thể cấu hình cả hai chính sách trong **một** Caffeine spec nếu yêu cầu nghiệp vụ cần cả hai.

### Dependency Maven thường gặp

Trong một dự án Spring Boot có parent/BOM tương thích:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>
    <dependency>
        <groupId>com.github.ben-manes.caffeine</groupId>
        <artifactId>caffeine</artifactId>
    </dependency>
</dependencies>
```

Đây là **mảnh dependency** đặt vào `pom.xml` của dự án Spring Boot, không phải POM độc lập. Parent/BOM quản lý version; để caching annotation hoạt động cần `@EnableCaching`.

### Ví dụ một service

```java
@Service
public class ProductService {
    @Cacheable(cacheNames = "products", key = "#p0")
    public Product find(String id) {
        return repository.find(id);
    }
}
```

Đoạn này cần repository, Product và các import tương ứng; nó chỉ minh họa annotation. Lần gọi qua Spring proxy có thể hit nếu chưa hết hạn và chưa bị eviction.

**Lưu ý cấu hình:**
- Một `spring.cache.caffeine.spec` auto-configured thường áp dụng chung chính sách cho các cache do manager này tạo. Muốn mỗi cache có TTL/TTI khác nhau, có thể tạo cache riêng bằng Caffeine native API và đăng ký chúng thay vì kỳ vọng mọi cache name tự có chính sách khác nhau.
- Boot chỉ cấu hình Caffeine theo cơ chế auto-configuration khi các điều kiện thỏa mãn. Nếu bạn đã cung cấp `CacheManager` hoặc `CacheResolver` riêng, property có thể không được áp dụng như dự tính.
- Hãy kiểm tra `CacheManager` thực tế là `CaffeineCacheManager` (hoặc manager tùy chỉnh đã đăng ký các cache Caffeine) trước khi kết luận chính sách có hiệu lực.
- Không dùng `Thread.sleep(600000)` để test expiry; nên dùng **ticker giả** trên Caffeine để test nhanh và ổn định.

## 7. Caffeine bằng Java: expireAfterWrite, expireAfterAccess và maximumSize

Caffeine hỗ trợ builder:

```java
Caffeine.newBuilder()
    .maximumSize(500)
    .expireAfterWrite(Duration.ofSeconds(30));

Caffeine.newBuilder()
    .maximumSize(500)
    .expireAfterAccess(Duration.ofSeconds(30));
```

Đây là **hai builder độc lập để minh họa**, chưa có `build()` và chưa gắn vào Spring CacheManager.

Điểm cần phân biệt:
- `expireAfterWrite` dựa vào thời điểm tạo hoặc cập nhật entry; đọc hit không reset.
- `expireAfterAccess` dựa vào thời điểm truy cập qua API cache mà Caffeine nhận diện; đọc hit có thể gia hạn.
- `maximumSize` là eviction theo sức chứa, không phải TTL.
- Caffeine có thể thực hiện bảo trì/xóa mục vật lý **lazily**, trong các hoạt động truy cập hoặc các chu kỳ maintenance. Một mục **đã hết hạn về mặt logic** không nhất thiết được giải phóng bộ nhớ đúng tại nano-giây hết hạn.
- `@Cacheable` vẫn chỉ yêu cầu hit/miss; chính sách expiry được thực hiện bởi cache gốc và được Spring nhìn qua adapter.

Đây là lý do nên test bằng việc truy cập và assert **miss/hit/số lần chạy thân method**, thay vì kiểm tra chính xác thời điểm mục biến mất khỏi internal map.

## 8. Redis: TTL đặt trên key; TTI cần opt-in và GETEX

### 8.1. TTL trong Spring Boot với Redis

Khi Spring Boot auto-configure Redis CacheManager, cấu hình ví dụ:

```properties
spring.cache.type=redis
spring.cache.cache-names=products,prices
spring.cache.redis.time-to-live=10m
spring.cache.redis.cache-null-values=false
```

`spring.cache.redis.time-to-live=10m` dùng TTL 10 phút cho các cache mà cấu hình này quản lý. Redis server phải được cấu hình và truy cập được; cần dependency Redis tương ứng, ví dụ `spring-boot-starter-data-redis`, cùng phần tích hợp Spring Cache. Đây không phải cấu hình tự tạo server Redis.

Khi cần TTL khác nhau theo cache name, có thể xây dựng `RedisCacheManager` và dùng cấu hình từng cache bằng `RedisCacheConfiguration`:

```java
RedisCacheConfiguration base =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10));

RedisCacheConfiguration products =
        base.entryTtl(Duration.ofMinutes(2));

RedisCacheConfiguration prices =
        base.entryTtl(Duration.ofMinutes(30));

// Ví dụ minh họa cấu hình; cần kết hợp với RedisCacheManager builder
// và một RedisConnectionFactory trong Spring context.
```

Cần phân biệt TTL áp dụng cho entry và việc làm mới theo truy cập: **Redis lệnh `GET` thông thường không gia hạn TTL** của key. Việc key được đọc thường xuyên không mặc nhiên giữ nó còn sống.

### 8.2. Redis không có TTI gốc giống Caffeine

Spring Data Redis cung cấp cơ chế mô phỏng TTI trong các phiên bản hỗ trợ thông qua:

```java
RedisCacheConfiguration config =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(5))
                .enableTimeToIdle();
```

Đây là **đoạn cấu hình RedisCacheConfiguration**, không phải chương trình độc lập. `enableTimeToIdle()` phải được bật chủ động; kết hợp TTL đã khai báo. Để đạt hành vi TTI giả lập, Spring Data Redis Cache dùng lệnh **`GETEX`** thay vì `GET` khi đọc qua cache API; lệnh `GETEX` có thể đọc và đặt lại hạn của key.

Điều kiện rất quan trọng:
1. **Redis server phiên bản 6.2.0 trở lên** hỗ trợ `GETEX`. Bật TTI trên server cũ hơn sẽ lỗi thực thi lệnh; Spring Data Redis không tự “vá” sự thiếu hụt này.
2. Dùng Spring Data Redis phiên bản có API `enableTimeToIdle()` (từ dòng 3.2 trở đi); tránh sao chép code trên vào phiên bản quá cũ.
3. **Mọi đường truy cập cần thống nhất cách gia hạn expiry.** Một thao tác `RedisTemplate.opsForValue().get(key)` thông thường hoặc repository query dùng `GET` không reset TTL. Khi kết hợp nhiều cách truy cập cùng key, bạn có thể tưởng giá trị vừa được “dùng” nhưng nó vẫn hết hạn theo đồng hồ TTL cũ.
4. Redis TTI theo cơ chế này **là một cách mô phỏng trên nền TTL**; không phải Redis hỗ trợ một kiểu “idle timestamp” server-side riêng cho mọi lệnh.
5. Nếu có nhiều client ngoài Spring cùng đọc key, cần đánh giá toàn bộ luồng truy cập; một provider không thể tự biết mọi kiểu đọc ngoài API của nó.

### Redis kiểm tra TTL trực tiếp

Trong môi trường phát triển có Redis CLI, nếu bạn biết chính xác key thực (bao gồm prefix cache name, serializer và key format), có thể kiểm tra:

```bash
redis-cli TTL 'products::P1'
redis-cli PTTL 'products::P1'
```

Đây là lệnh **minh họa** với prefix/key `products::P1` khi cấu hình mặc định của Redis cache tương ứng; key thực có thể khác theo serializer, prefix hoặc cache key generator.

- `TTL` trả thời gian còn lại tính bằng giây; `PTTL` bằng mili-giây.
- Mã trả về `-2` nghĩa là key không tồn tại; `-1` nghĩa là key tồn tại nhưng không đặt expire.
- Một lệnh `TTL` để **quan sát thời gian còn lại** không tự làm mới TTI.
- Không xóa/điều chỉnh key production chỉ để kiểm tra thí nghiệm; dùng môi trường test riêng.

## 9. ConcurrentMapCacheManager: vì sao ví dụ cơ bản không tự hết hạn?

`ConcurrentMapCacheManager` dùng cache trong bộ nhớ JVM dựa trên cấu trúc map. Nó thích hợp cho demo hoặc test cache hit/miss cơ bản, nhưng **không có chính sách TTL/TTI built-in** tương đương Caffeine.

Ví dụ minh họa:

```java
@Bean
CacheManager cacheManager() {
    return new ConcurrentMapCacheManager("products");
}
```

Chỉ đặt `@Cacheable("products")` trên method không tự làm entry hết hạn sau 5, 10 hay 60 phút. Trừ khi có explicit eviction/clear, làm mới qua put, thay đổi context hoặc một yếu tố khác, entry vẫn có thể được giữ trong map.

Những hậu quả:
- Các test giả định “chờ một chút rồi miss” sẽ sai khi provider không có expiry.
- Số entry và lượng bộ nhớ có thể tăng nếu key tăng mãi mà không có quản lý dung lượng phù hợp.
- Chuyển từ ConcurrentMap sang Redis/Caffeine có thể làm thay đổi thời điểm miss, cách serializable value và concurrency.
- Cần chọn provider phù hợp yêu cầu vòng đời thay vì bổ sung annotation không tồn tại như `@Cacheable(ttl = ...)`.

## 10. Ví dụ Java 17 chạy được: kiểm chứng TTL và TTI bằng đồng hồ giả

Thí nghiệm sử dụng Spring Framework 6.2.x, Caffeine 3.1.x và JUnit 5. Trong cùng một Spring ApplicationContext, chúng ta tạo **hai cache riêng biệt**:
- `byWrite`: hết hạn sau **5 giây kể từ write**.
- `byAccess`: hết hạn sau **5 giây kể từ lần access gần nhất**.

Cả hai cache dùng một đối tượng `Ticker` giả để điều khiển thời gian. Nhờ vậy phép kiểm chứng nhanh và dự đoán chính xác mà **không cần ngủ 5–15 giây**.

### 10.1. Cấu trúc tệp

```text
cache-lifecycle-demo/
├── pom.xml
└── src/
    ├── main/java/demo/cache/CacheLifecycleDemo.java
    └── test/java/demo/cache/CacheLifecycleDemoTest.java
```

### 10.2. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>cache-lifecycle-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.16</version>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
            <version>3.1.8</version>
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
                    <mainClass>demo.cache.CacheLifecycleDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context-support` mang lớp adapter `CaffeineCache` và kéo các module Spring cần thiết; dependency Caffeine cung cấp native builder. JUnit dùng cho assertion. Các phiên bản được nêu cụ thể để dễ tái tạo; khi đưa vào một dự án Spring Boot thật, **dùng BOM/parent quản lý tương thích** thay vì tự đặt phiên bản Spring chồng chéo.

### 10.3. Java hoàn chỉnh — `CacheLifecycleDemo.java`

```java
package demo.cache;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.Ticker;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.support.SimpleCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheLifecycleDemo {

    public static final class FakeTicker implements Ticker {
        private final AtomicLong nanos = new AtomicLong();

        @Override
        public long read() {
            return nanos.get();
        }

        public void advanceSeconds(long seconds) {
            nanos.addAndGet(TimeUnit.SECONDS.toNanos(seconds));
        }
    }

    public static class PriceService {
        private final AtomicInteger writeLoads = new AtomicInteger();
        private final AtomicInteger accessLoads = new AtomicInteger();

        @Cacheable(cacheNames = "byWrite", key = "#p0")
        public String byWrite(String sku) {
            return sku + "-w" + writeLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "byAccess", key = "#p0")
        public String byAccess(String sku) {
            return sku + "-a" + accessLoads.incrementAndGet();
        }

        public int writeLoadCount() {
            return writeLoads.get();
        }

        public int accessLoadCount() {
            return accessLoads.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {

        @Bean
        public FakeTicker ticker() {
            return new FakeTicker();
        }

        @Bean
        public CacheManager cacheManager(FakeTicker ticker) {
            var ttlNative = Caffeine.newBuilder()
                    .ticker(ticker)
                    .expireAfterWrite(Duration.ofSeconds(5))
                    .maximumSize(100)
                    .build();

            var ttiNative = Caffeine.newBuilder()
                    .ticker(ticker)
                    .expireAfterAccess(Duration.ofSeconds(5))
                    .maximumSize(100)
                    .build();

            var manager = new SimpleCacheManager();
            manager.setCaches(List.of(
                    new CaffeineCache("byWrite", ttlNative),
                    new CaffeineCache("byAccess", ttiNative)
            ));
            return manager;
        }

        @Bean
        public PriceService priceService() {
            return new PriceService();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            var clock = context.getBean(FakeTicker.class);
            var service = context.getBean(PriceService.class);

            System.out.println("t0 write=" + service.byWrite("A"));
            System.out.println("t0 access=" + service.byAccess("A"));

            clock.advanceSeconds(4);
            System.out.println("t4 write=" + service.byWrite("A"));
            System.out.println("t4 access=" + service.byAccess("A"));

            clock.advanceSeconds(4);
            System.out.println("t8 write=" + service.byWrite("A"));
            System.out.println("t8 access=" + service.byAccess("A"));

            clock.advanceSeconds(6);
            System.out.println("t14 write=" + service.byWrite("A"));
            System.out.println("t14 access=" + service.byAccess("A"));

            System.out.println("writeLoads=" + service.writeLoadCount());
            System.out.println("accessLoads=" + service.accessLoadCount());
        }
    }
}
```

Giải thích:
- `FakeTicker` là đồng hồ nguồn nano-giây do test điều khiển. Nó triển khai đúng interface `Ticker` của Caffeine.
- Cache `byWrite` hết hạn sau 5 giây kể từ lần load/ghi gần nhất.
- Cache `byAccess` hết hạn sau 5 giây kể từ lần truy cập gần nhất.
- `SimpleCacheManager` ở đây **đăng ký hai đối tượng CaffeineCache có chính sách khác nhau**. Đừng nhầm tên `SimpleCacheManager` với `ConcurrentMapCacheManager`; bộ quản lý này chỉ gom các cache đã cung cấp, còn mỗi cache con thực sự là Caffeine.
- Hai method `@Cacheable` gọi từ bean do Spring quản lý; bộ đếm nằm trong thân method để quan sát miss thật.
- Đọc trúng cache Caffeine có thể làm mới mốc access, nhưng không làm mới mốc write.

### 10.4. Chạy ứng dụng và stdout dự kiến

Cần JDK 17+, Maven và tải được dependency từ Maven Central. Ở thư mục `cache-lifecycle-demo`:

```bash
java -version
mvn -q compile exec:java
```

Các dòng **do chính chương trình in ra** (bỏ qua thông báo riêng của Maven/Spring):

```text
t0 write=A-w1
t0 access=A-a1
t4 write=A-w1
t4 access=A-a1
t8 write=A-w2
t8 access=A-a1
t14 write=A-w3
t14 access=A-a2
writeLoads=3
accessLoads=2
```

Đối chiếu từng bước:

- **t0:** cả hai cache trống, hai method thực thi lần đầu.
- **t4:** chưa quá 5 giây so với t0, cả hai hit. Cache `byAccess` làm mới thời điểm idle tại t4.
- **t8:** cache `byWrite` đã sống 8 giây từ lần ghi t0, nên miss và tải lần hai; cache `byAccess` vừa được đọc tại t4, chỉ idle 4 giây nên vẫn hit.
- **t14:** cache `byWrite` ghi tại t8, đã qua 6 giây nên miss, tải lần ba. Cache `byAccess` lần cuối được đọc tại t8, cũng quá 5 giây nên miss và tải lần hai.
- **Số lần thực thi body:** 3 đối với expiry sau write, 2 đối với expiry sau access; không phải số lần client gọi (mỗi method đều được gọi 4 lần).

Bài này không dùng `Thread.sleep()` nên không phụ thuộc lịch thực thi OS. Tuy nhiên, kết quả là hành vi của **provider Caffeine, chính sách và cấu hình cụ thể trong ví dụ**; nó không chứng minh tất cả provider giống nhau.

## 11. Kiểm thử JUnit 5: xác nhận vòng đời một cách quyết định

Tạo `src/test/java/demo/cache/CacheLifecycleDemoTest.java`:

```java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CacheLifecycleDemoTest {

    @Test
    void writeExpiryAndIdleExpiryBehaveDifferently() {
        try (var context = new AnnotationConfigApplicationContext(
                CacheLifecycleDemo.Config.class)) {

            var clock = context.getBean(CacheLifecycleDemo.FakeTicker.class);
            var service = context.getBean(
                    CacheLifecycleDemo.PriceService.class);

            assertEquals("A-w1", service.byWrite("A"));
            assertEquals("A-a1", service.byAccess("A"));

            clock.advanceSeconds(4);
            assertEquals("A-w1", service.byWrite("A"));
            assertEquals("A-a1", service.byAccess("A"));

            clock.advanceSeconds(4);
            assertEquals("A-w2", service.byWrite("A"));
            assertEquals("A-a1", service.byAccess("A"));

            clock.advanceSeconds(6);
            assertEquals("A-w3", service.byWrite("A"));
            assertEquals("A-a2", service.byAccess("A"));

            assertEquals(3, service.writeLoadCount());
            assertEquals(2, service.accessLoadCount());
        }
    }
}
```

Chạy:

```bash
mvn -q test
```

Nếu test thành công, Maven trả **exit code 0**. Với `-q`, không nhất thiết có dòng “BUILD SUCCESS”; chính các assertion là bằng chứng. Vì test dựng ApplicationContext mới, cache và bộ đếm bắt đầu trống, không phụ thuộc lần chạy `main` trước đó.

Khi mở rộng test cho size eviction, **không nên khẳng định key A chắc chắn bị loại chỉ vì thêm một key khác**: thuật toán chọn entry bị loại phụ thuộc provider và pattern truy cập. Muốn test chính sách sức chứa, đo tổng entry/khả năng bị loại dưới workload được kiểm soát và không hard-code một thứ tự eviction sai.

## 12. Hết hạn logic khác với dọn dẹp bộ nhớ vật lý

Hệ thống cache có thể đánh dấu mục không còn hợp lệ tại t = 5 giây, nhưng không nhất thiết chạy một thread đúng lúc đó để xóa vật lý.

- Caffeine có thể xử lý bảo trì khi cache được đọc/ghi; tùy cấu hình scheduler, việc dọn dẹp có thể được thúc đẩy theo thời gian.
- Redis có cơ chế xóa key hết hạn bằng cả kiểm tra khi truy cập và hoạt động chủ động của server; không nên suy ra mức bộ nhớ giảm chính xác tại mili-giây hết TTL.
- Một mục đã hết hạn **không được trả như một cache hit hợp lệ** khi provider kiểm tra expiry, nhưng dữ liệu có thể vẫn tạm tồn tại bên trong cấu trúc quản lý cho đến đợt maintenance.

Vì vậy nên test hành vi **get/hit/miss**, chứ không kiểm tra đồng hồ thực với độ chính xác nano-giây hoặc soi memory usage để quyết định một mục đã expire.

## 13. Điều gì xảy ra khi cập nhật dữ liệu nguồn trước khi TTL kết thúc?

Giả sử giá sản phẩm trong database từ 100 thành 200 tại t = 1 giây, nhưng TTL cache là 10 phút. Nếu không có invalidation:

```text
t0: GET P1 -> MISS -> tải 100 -> cache P1=100 (TTL 10 phút)
t1: UPDATE DB P1=200
t2: GET P1 -> HIT -> vẫn trả 100 (dữ liệu stale)
t10m+: GET P1 -> MISS -> tải 200 (nếu DB đã commit và cache đã expire)
```

**TTL chỉ đặt giới hạn tuổi của một bản cache, không đồng nghĩa cache luôn mới ngay khi nguồn thay đổi.** Với dữ liệu cần cập nhật nhanh, kết hợp:
- `@CacheEvict` sau lệnh ghi để loại key và đọc lại ở lần truy vấn tiếp theo; hoặc
- `@CachePut` khi lệnh ghi trả về giá trị canonical đã persist và có thể put đúng key; hoặc
- chiến lược cập nhật chủ động/event-based invalidation, phù hợp giao dịch và hệ thống nhiều instance.

TTL dài làm giảm miss và tải lên nguồn nhưng tăng khoảng có thể đọc dữ liệu cũ; TTL ngắn làm dữ liệu nhanh được làm mới hơn nhưng tăng miss và chi phí xử lý. Đây là **trade-off** cần đo bằng yêu cầu nghiệp vụ, không có TTL duy nhất tốt cho mọi dịch vụ.

### Giao dịch và thứ tự xóa/ghi cache

Ngay cả `@CacheEvict`/`@CachePut` cũng cần phối hợp thời điểm commit. Nếu xóa cache trước khi DB commit, request khác có thể nạp lại giá trị cũ; nếu put cache nhưng DB rollback, cache có thể chứa bản cập nhật không tồn tại ở nguồn. Cần kiểm tra transaction advice, after-commit invalidation hoặc chiến lược bù lỗi phù hợp.

## 14. Nhiều JVM, cache local và cache phân tán

- **Caffeine local cache:** mỗi instance ứng dụng có cache, đồng hồ TTL/TTI và vòng đời mục riêng. Evict ở instance A không tự xóa mục ở instance B.
- **Redis cache dùng chung:** nhiều instance truy cập key ở cùng Redis có thể chia sẻ TTL. Tuy nhiên key/serializer, namespace, prefix và transaction vẫn phải được thống nhất.
- **TTI trên Redis:** một request từ instance A qua `GETEX` có thể gia hạn TTL trên key Redis dùng chung; request chỉ dùng `GET` từ instance B không làm mới TTL. Chính vì vậy mọi đường truy cập phải có chính sách nhất quán.
- **Cache stampede:** nhiều request cùng miss sau expiry có thể đồng thời tải nguồn. `@Cacheable(sync = true)` phụ thuộc provider và không tự cam kết đồng bộ xuyên tất cả instance; cần thiết kế riêng nếu yêu cầu tải đúng một lần toàn hệ thống.
- **Clock/TTL precision:** thời gian và cách vận hành do provider quyết định. Không giả định đồng hồ local của một JVM quyết định TTL của Redis server.

Khi dữ liệu quan trọng, một cache phân tán cũng **không thay thế database làm nguồn chuẩn**; nên có idempotency, transaction, version hoặc invalidation phù hợp.

## 15. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Cache không bao giờ hết hạn | Dùng `ConcurrentMapCacheManager` hoặc không cấu hình TTL | Kiểm tra type manager/provider và cấu hình expiry |
| Mục hết hạn dù vừa được đọc | Đang dùng TTL theo write, không phải TTI | Kiểm tra `expireAfterWrite` vs `expireAfterAccess`; Redis GET vs GETEX |
| Cache miss dù chưa tới TTL | Bị capacity eviction, manual evict, key khác hoặc provider restart | Kiểm tra size stats, key, logs, instance |
| Giá trị cũ còn tồn tại sau update DB | Chưa invalidation hoặc update cache sai key | So sánh key read/write và thời điểm transaction commit |
| Boot `spring.cache.caffeine.spec` không có tác dụng | Có CacheManager custom hoặc auto-config không chọn Caffeine | Log bean/provider và điều kiện auto-config |
| Redis bật TTI rồi lỗi lệnh | Server dưới Redis 6.2 hoặc đường truy cập không dùng GETEX | Kiểm tra version Redis, Spring Data Redis và truy cập |
| Test expiry lúc pass lúc fail | Dùng `Thread.sleep()` và phụ thuộc scheduler | Inject fake ticker hoặc clock abstraction của provider |
| Cache lớn bất thường | TTL không tương đương giới hạn số entry, maintenance lười, key không giới hạn | Dùng `maximumSize`/memory budget/metrics phù hợp |
| Nhiều instance thấy giá trị khác nhau | Local cache mỗi process, hoặc invalidation chưa đồng bộ | Kiểm tra topology và chiến lược shared cache |
| `@Cacheable` vẫn chạy method nhiều lần | TTL ngắn, key thay đổi, miss đồng thời, self-invocation hoặc proxy | Đếm số lần method body chạy và kiểm tra key/proxy |

**Lưu ý:** tự tạo đối tượng bằng `new` hoặc gọi `this.find(...)` trong cùng bean có thể bỏ qua Spring proxy cache interceptor ở chế độ mặc định. Khi kiểm tra TTL/TTI của annotation, phải gọi một bean do Spring quản lý qua proxy thực tế.

## 16. Checklist lựa chọn chính sách

1. **Độ mới:** dữ liệu được phép stale tối đa bao lâu? Nguồn thay đổi do batch, sự kiện hay người dùng?
2. **Ý nghĩa thời gian:** cần giới hạn tuổi từ lần ghi (**TTL/write**) hay cần giữ giá trị còn được truy cập (**TTI/access**)?
3. **Giới hạn bộ nhớ:** có cần `maximumSize`, `maximumWeight` hoặc memory quota bên cạnh expiry?
4. **Provider:** cần cache local hay phân tán? Provider đang dùng có hỗ trợ TTI thật, mô phỏng hay không hỗ trợ?
5. **Cấu hình thực:** xác nhận bean `CacheManager`, tên cache và chính sách đang được áp dụng thay vì chỉ nhìn annotation.
6. **Đường đọc:** có nhiều API đọc cùng key? Đặc biệt trên Redis, TTI qua GETEX không giống GET.
7. **Invalidation:** sau khi nguồn thay đổi, có xóa/put mục liên quan để không chờ TTL không?
8. **Null/negative caching:** muốn cache kết quả “không tồn tại” trong bao lâu, provider có hỗ trợ không?
9. **Load:** TTL quá ngắn có gây stampede hoặc làm DB/API bị quá tải khi hàng loạt key hết hạn cùng lúc?
10. **Đo lường:** theo dõi hit rate, miss rate, eviction count, số tải từ nguồn, p95/p99 latency, số entry và heap/Redis memory.
11. **Kiểm thử:** có test với fake ticker/clock, test invalidate sau update và test provider thật không?
12. **Triển khai:** cấu hình theo môi trường có bị override bởi bean custom/profile/env var không?

## 17. Bài tập tự luyện

**Bài 1 — TTL.** Cache TTL 5 giây, ghi tại t = 0, đọc t = 2, t = 4 và t = 6. Không có cập nhật, eviction hoặc reload trước t = 6. Lần đọc t = 6 hit hay miss?  
**Đáp án:** **Miss** theo chính sách `expireAfterWrite(5s)` vì đọc tại t = 2 và t = 4 không đặt lại tuổi kể từ write.

**Bài 2 — TTI.** Cache TTI 5 giây, ghi t = 0, hit t = 4, hit t = 8, đọc t = 14. Lần cuối hit hay miss?  
**Đáp án:** **Miss** vì khoảng idle từ t = 8 đến t = 14 là 6 giây.

**Bài 3 — Capacity.** Cache có `maximumSize(2)` và TTL 30 phút. Thêm ba key khác nhau. Vì sao có thể miss một key dù mới ghi?  
**Đáp án:** Vì capacity eviction có thể loại một mục trước khi nó đạt TTL. Không nên tự phán key cụ thể bị loại nếu không xác nhận thuật toán/pattern.

**Bài 4 — Annotation.** Có thể viết `@Cacheable(cacheNames = "products", ttl = 60)` để tự nhận TTL 60 giây trên mọi provider?  
**Đáp án:** **Không**; `ttl` không phải thuộc tính chuẩn của Spring `@Cacheable`. Cần cấu hình trên provider/cache manager.

**Bài 5 — Redis TTI.** Vì sao dùng `RedisTemplate` để `GET` một key không chắc kéo dài TTI của Spring Data Redis?  
**Đáp án:** Vì mô phỏng TTI dựa trên `GETEX` có thể đặt lại expire, trong khi `GET` thông thường chỉ đọc.

**Bài 6 — Update DB.** Nếu TTL là 60 phút và dữ liệu đổi ngay sau khi cache được ghi, người đọc có thể gặp stale data không?  
**Đáp án:** Có, nếu không có invalidation hoặc put giá trị mới. TTL giới hạn tuổi chứ không đồng bộ tức thời với nguồn.

## Tài liệu tham khảo chính thức

- [Spring Framework — How can I set the TTL/TTI/Eviction policy/XXX feature?](https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Boot — Caching (Caffeine và Redis)](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Data Redis — Redis Cache, TTL và TTI expiration](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Caffeine — Eviction & Expiration Wiki](https://github.com/ben-manes/caffeine/wiki/Eviction)
- [Caffeine — Testing Wiki (Ticker)](https://github.com/ben-manes/caffeine/wiki/Testing)

**Ghi nhớ:** Spring Cache quản lý **cách áp dụng caching cho lời gọi phương thức**, không phải một chính sách hết hạn thống nhất. **TTL, TTI và capacity eviction phải được thiết lập trên provider**, và hành vi thật cần được kiểm chứng bằng hit/miss, số lần thực thi method cùng dữ liệu nguồn. Đặt đúng thời gian sống vẫn chưa đủ: cache có hiệu quả và an toàn cần cả giới hạn dung lượng, invalidation sau update, hiểu đúng topology và kiểm thử với provider đang dùng.