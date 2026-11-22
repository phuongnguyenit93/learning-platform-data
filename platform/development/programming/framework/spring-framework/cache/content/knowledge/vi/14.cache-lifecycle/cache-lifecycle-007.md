# Vì sao annotation Spring Cache không khai báo TTL chuẩn?

## Mục tiêu bài học

Khi mới dùng Spring Cache, chúng ta thường viết `@Cacheable(cacheNames = "products")` rồi hỏi: **“Kết quả được lưu trong bao lâu, và tại sao không có `ttl = 300` ngay trên annotation?”** Đây không phải một thuộc tính bị bỏ quên. Spring Cache cố ý đóng vai trò **abstraction** để thống nhất cách chương trình gọi và sử dụng cache, trong khi chính sách hết hạn (expiration) thuộc về **công nghệ cache lưu trữ thực tế**.

Sau bài học, bạn sẽ:

- Giải thích chính xác vì sao `@Cacheable`, `@CachePut`, `@CacheEvict` và `@CacheConfig` không có thuộc tính TTL tiêu chuẩn.
- Phân biệt **TTL**, **TTI**, **expire-after-write**, **expire-after-access**, **refresh** và **invalidation**.
- Nhận biết lớp nào quyết định dữ liệu có hết hạn: annotation, `CacheManager`, đối tượng `Cache` hay native cache provider.
- Cấu hình TTL qua **Caffeine**, **Redis**, Spring Boot properties hoặc cấu hình riêng theo từng cache name.
- Chạy một chương trình **Java 17 + Spring Framework + Caffeine** có đồng hồ giả lập, kiểm chứng cache hết hạn một cách xác định, không dùng `Thread.sleep()`.
- Thiết kế chính sách vòng đời cho các vùng cache khác nhau, tránh lẫn TTL với yêu cầu nhất quán tức thời.

> **Kết luận trước:** Annotation `@Cacheable` mô tả **phương thức nào có thể được cache và key/cache name nào được dùng**. Nó không mô tả một hợp đồng TTL dùng chung vì Spring Cache không phải một cache engine. Nếu provider không hỗ trợ hết hạn theo thời gian (ví dụ `ConcurrentMapCache` đơn giản), một tham số TTL phổ quát sẽ không có cách thực thi đồng nhất.

## 1. Spring Cache abstraction làm gì và không làm gì?

### 1.1. Luồng `@Cacheable` thường gặp

Giả sử:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto getProduct(long productId) {
    return repository.findDto(productId);
}
~~~

Đây là **mã minh họa**; `ProductDto` và repository cần được định nghĩa trong dự án thật.

Nếu lời gọi đi qua Spring caching proxy (hoặc AspectJ advice đã cấu hình), luồng tổng quát là:

~~~text
Gọi getProduct(42)
          |
    Spring cache advice
          |
    chọn cache "products"
          |
       tạo key 42
          |
       Cache.get(42)
          |
      +---+----------------+
      |                    |
    HIT                  MISS
      |                    |
trả kết quả cũ      gọi getProduct(42)
không chạy thân            |
phương thức          nhận kết quả mới
                            |
                       Cache.put(42, result)
                            |
                      trả kết quả mới
~~~

Spring cần biết **cache nào**, **key nào**, **khi nào đọc/ghi/xóa**. Nhưng việc entry có tự biến mất sau 5 phút, sau lần đọc cuối, do đạt giới hạn bộ nhớ hay không bao giờ tự hết hạn là trách nhiệm của implementation được chọn.

### 1.2. Vai trò của các lớp

| Thành phần | Chịu trách nhiệm chính | Có khai báo TTL chung không? |
| --- | --- | --- |
| `@Cacheable` | Quy tắc tra cứu, cache hit/miss, lựa chọn cache, key và điều kiện | **Không** |
| `@CachePut` | Chạy phương thức, đưa kết quả vào cache | **Không** |
| `@CacheEvict` | Yêu cầu xóa entry hoặc xóa vùng cache ở thời điểm được chỉ định | **Không**; đây là invalidation theo sự kiện |
| `@CacheConfig` | Chia sẻ tên cache/key generator/resolver/manager cho class | **Không** |
| `CacheManager` | Cung cấp đối tượng `Cache` theo tên | Phụ thuộc implementation và cấu hình |
| `Cache` | `get`, `put`, `evict`, `clear` và một số thao tác khác | Không có API TTL per-entry phổ quát |
| Native provider | Lưu dữ liệu và áp dụng chính sách expiration/eviction | **Thường ở đây**, nếu provider hỗ trợ |

Các implementation Spring khác nhau có thể sử dụng Redis, Caffeine, JCache, Couchbase, Hazelcast hoặc `ConcurrentMapCache`. Có provider hết hạn theo từng entry, có provider hết hạn theo access, có provider chỉ hỗ trợ expiry lúc tạo vùng, có provider không tự động hết hạn theo thời gian.

### 1.3. Câu trả lời chính thức của Spring

Tài liệu Spring Framework, mục **“How can I Set the TTL/TTI/Eviction policy/XXX feature?”**, giải thích rằng những chính sách đó được cấu hình **trực tiếp qua cache provider**, vì Spring Cache chỉ là abstraction, không phải một implementation cache cụ thể.

Ví dụ `ConcurrentHashMap` của JDK không có cơ chế TTL bản địa. Nếu Spring bắt tất cả cache phải hiểu cùng một annotation `ttl`, việc áp dụng nó lên `ConcurrentHashMap` sẽ cần một engine phụ để theo dõi thời gian và xóa entry. Spring không cam kết thêm cơ chế ấy cho mọi provider.

Nguồn: https://docs.spring.io/spring/reference/6.2/integration/cache/specific-config.html

## 2. Không có TTL chuẩn nghĩa là không thể dùng TTL?

**Không.** Spring Cache không có thuộc tính annotation chuẩn, nhưng provider có thể hỗ trợ TTL rất tốt.

Ví dụ có thể thiết lập:

- **Caffeine:** `expireAfterWrite(Duration.ofMinutes(5))`, `expireAfterAccess(...)`, hoặc chính sách hết hạn biến đổi bằng API của Caffeine.
- **RedisCacheManager:** `RedisCacheConfiguration.entryTtl(Duration.ofMinutes(5))`, có thể tùy chỉnh theo từng cache name; phiên bản Spring Data Redis phù hợp còn hỗ trợ TTL function.
- **Spring Boot + Redis:** `spring.cache.redis.time-to-live=5m` khi Redis cache được Boot tự cấu hình.
- **Spring Boot + Caffeine:** `spring.cache.caffeine.spec=maximumSize=1000,expireAfterWrite=300s` khi Caffeine manager được Boot tự cấu hình.
- **ConcurrentMapCacheManager:** không có cơ chế TTL tích hợp trong cache lưu bằng `ConcurrentHashMap`; phải đổi provider hoặc xây dựng chính sách vòng đời khác.

Ví dụ trên là **những cách cấu hình khác nhau**, không phải các thuộc tính có thể sao chép lên `@Cacheable`.

Đặc biệt, `@Cacheable(cacheNames = "products", ttl = 300)` là **cú pháp Java không hợp lệ** với annotation Spring Cache chuẩn. Trong IDE/compiler, bạn sẽ gặp lỗi thuộc tính `ttl` không tồn tại.

## 3. TTL, TTI, refresh và eviction khác nhau ở đâu?

### 3.1. TTL: Time To Live

Trong cache nhiều nơi gọi là TTL, nhưng phải xem **thời điểm bắt đầu tính**. Một chính sách phổ biến là `expireAfterWrite`:

- Tại thời điểm `t = 0`, entry `products[42]` được ghi.
- TTL sau ghi là 5 phút.
- Các lần đọc ở `t = 1`, `t = 2`, `t = 4` phút **không kéo dài** hạn hết hiệu lực.
- Tại hoặc sau mốc hết hạn theo semantics provider, một lượt đọc không còn thấy giá trị hợp lệ; nếu dùng `@Cacheable`, nó có thể thành miss và gọi lại phương thức nguồn.

~~~text
expire-after-write = 5 phút

t=0         t=2           t=4           t=5+
 |-----------|-------------|--------------|
 PUT         GET hit       GET hit      expired -> MISS
                ^             ^
         không reset TTL  không reset TTL
~~~

Một lần **ghi lại/replace** entry có thể khởi động lại thời hạn theo chính sách expire-after-write. Tuy nhiên, **không phải mọi hệ thống gọi TTL đều giống hoàn toàn expire-after-write**; cần đọc tài liệu backend cụ thể.

### 3.2. TTI: Time To Idle

TTI (time to idle) là thời gian entry được phép **không có truy cập**. Trong Caffeine, chính sách `expireAfterAccess` được áp dụng theo thời gian kể từ một lần truy cập đọc/ghi gần nhất.

~~~text
expire-after-access = 5 phút

t=0         t=3            t=7            t=12+
 |-----------|--------------|---------------|
 PUT       GET hit        GET hit       có thể expired
             |               |
        hạn trượt đến    hạn trượt đến
          t~8             t~12
~~~

Khác biệt: **read hit có thể kéo dài thời hạn sống**. Đây là hành vi không giống `expireAfterWrite`.

Với Redis, hỗ trợ idle expiration có thể dựa vào các lệnh cụ thể như `GETEX` hoặc thiết kế backend; không mặc định `GET` làm mới TTL. Spring Data Redis có `enableTimeToIdle()` ở các phiên bản hỗ trợ, nhưng yêu cầu Redis tương thích và các đường đọc được thực hiện nhất quán.

### 3.3. Refresh không giống expiration

`refreshAfterWrite` trong Caffeine là một policy để entry **đủ điều kiện làm mới**, không tương đương tự biến entry thành miss ngay lập tức. Với cache có loader/refresh semantics, hệ thống có thể trả giá trị cũ trong khi refresh diễn ra. Việc refresh thực sự và cung cấp dữ liệu mới phụ thuộc thiết kế cache/loader.

Không nên diễn đạt `refreshAfterWrite(5m)` thành “xóa entry sau 5 phút” vì hai cơ chế có hành vi khác nhau, đặc biệt dưới tải cao.

### 3.4. Expiration không giống explicit eviction

- **Expiration:** backend quyết định entry hết hiệu lực theo chính sách thời gian.
- **Eviction:** có thể diễn ra vì dung lượng, thuật toán quản lý bộ nhớ hoặc một yêu cầu `@CacheEvict`/API rõ ràng.
- **Invalidation:** thay đổi dữ liệu nguồn hoặc sự kiện nghiệp vụ làm một entry không còn đúng, nên ứng dụng chủ động xóa hoặc làm mới entry.

Một TTL dài không làm dữ liệu đúng khi database đã thay đổi giữa chừng. Nếu yêu cầu “đổi tên xong thì lần đọc tiếp theo phải thấy tên mới”, hãy dùng `@CacheEvict`/`@CachePut` hoặc một chiến lược invalidation nhất quán, **không chỉ dựa vào TTL**.

## 4. Vì sao Spring không đưa TTL vào @Cacheable?

### 4.1. Khác biệt năng lực giữa các provider

`@Cacheable` được thiết kế để làm việc với rất nhiều engine. `ConcurrentMapCache` đơn giản không có TTL, trong khi Redis có expiration ở cấp key, Caffeine có các chính sách theo write/access và khả năng tùy biến sâu. Một thuộc tính TTL trên method không biết phải xử lý thế nào nếu provider không hỗ trợ hoặc hiểu thời gian theo mô hình khác.

Đưa vào annotation một tùy chọn mà nhiều backend không thực thi được sẽ buộc Spring phải lựa chọn giữa **bỏ qua lặng lẽ**, **ném lỗi** hoặc **xây thêm engine**; cả ba đều làm mất tính đơn giản và nhất quán của abstraction.

### 4.2. Chính sách thường thuộc vùng cache, không thuộc phương thức

Nhiều phương thức có thể sử dụng cùng vùng:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto findById(long id) { /* ... */ }

@CachePut(cacheNames = "products", key = "#p0")
public ProductDto update(long id, ProductDto input) { /* ... */ }
~~~

Các phương thức này **chia sẻ các entry trong một cache name**. Nếu `findById` khai báo TTL 10 phút còn `update` khai báo TTL 15 giây, policy nào được áp dụng khi cả hai ghi cùng một key? Spring không áp đặt một cách giải quyết chung cho tất cả provider.

Một cách dễ kiểm soát là **cấu hình policy ở cache region**: ví dụ vùng `products` là 5 phút; cả `@Cacheable` và `@CachePut` sử dụng region này. Với provider hỗ trợ expiry theo entry, một chính sách phức tạp có thể quyết định hạn lưu từ dữ liệu cụ thể.

### 4.3. TTL theo method dễ tạo kỳ vọng sai về tính nhất quán

Đọc dữ liệu tồn kho, số dư, danh sách khuyến mãi và dữ liệu cấu hình có yêu cầu độ mới khác nhau. TTL là **giới hạn tuổi dữ liệu** chứ không đảm bảo dữ liệu luôn phản ánh transaction vừa commit. Nếu thay đổi nguồn xảy ra ở `t = 1` nhưng TTL là 5 phút, một entry cũ vẫn có thể được trả trong khoảng còn lại nếu không có invalidation.

Do đó TTL phải được thiết kế cùng:

- mức độ chấp nhận stale của nghiệp vụ;
- chiến lược `@CacheEvict`/`@CachePut`;
- transaction/commit order;
- invalidation đa instance;
- thời gian và chi phí truy vấn nguồn;
- quan sát hit/miss, load, memory và sự cố cache backend.

### 4.4. TTL động có thể cần ngữ cảnh không sẵn có ở annotation

Một sản phẩm có thể cache 1 phút, token hết hạn theo thời điểm tuyệt đối, còn kết quả lỗi chỉ cache vài giây. Các chính sách biến đổi theo giá trị, response metadata, thời điểm phát hành hoặc độ nhạy dữ liệu không thể luôn được diễn đạt bằng một số giây cố định trên method.

Một số backend hỗ trợ **expiry per-entry** hoặc **TTL function**. Spring cho phép ứng dụng tùy chỉnh chính backend đó mà không ép mọi implementation phải có cùng API.

### 4.5. Tách code nghiệp vụ khỏi hạ tầng

Thay một cache local bằng cache phân tán thường yêu cầu điều chỉnh TTL, serializer, kích thước, eviction và topology. Nếu các chính sách native này nằm trong từng annotation ở hàng trăm service methods, thay đổi hạ tầng trở nên khó kiểm soát. Với abstraction, annotation tập trung vào **ngữ nghĩa cache của lời gọi**, còn hạ tầng cấu hình vòng đời.

## 5. Cấu hình TTL đúng cách với Caffeine

### 5.1. Java Config cho một vùng cache

Caffeine là một thư viện cache **local in-memory**. Ví dụ cấu hình này dành cho ứng dụng đã có Spring context và Caffeine dependency:

~~~java
import java.time.Duration;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager =
            new CaffeineCacheManager("products");

        manager.setCaffeine(
            Caffeine.newBuilder()
                .maximumSize(1_000)
                .expireAfterWrite(Duration.ofMinutes(5))
        );
        return manager;
    }
}
~~~

Đoạn trên là **Java Config tích hợp**, không phải ứng dụng độc lập. Cần `spring-context-support` và `com.github.ben-manes.caffeine:caffeine`; cấu hình `@EnableCaching` phải có trong ứng dụng.

Một service sử dụng như sau:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto getProduct(long id) {
    return repository.findDtoById(id);
}
~~~

Không có `ttl` trên annotation. Entry hết hạn vì **CaffeineCacheManager tạo một Caffeine cache có policy expireAfterWrite 5 phút**.

### 5.2. Cache local và cache phân tán

Nếu có ba instance của service dùng Caffeine, mỗi instance có một bộ nhớ cache riêng và tự quản lý expiration. TTL 5 phút trên instance A **không đồng bộ hóa** giá trị với instance B hoặc C. Nếu nghiệp vụ cần đồng bộ invalidation toàn hệ thống, hãy cân nhắc shared cache (Redis, v.v.) hoặc phát sự kiện xóa tại các instance.

### 5.3. Kích thước cache và dọn bộ nhớ

`expireAfterWrite` giới hạn tuổi entry nhưng không thay thế `maximumSize` và quản lý tài nguyên. Với Caffeine, expired entry có thể bị coi là không còn dùng được khi tra cứu, trong khi **việc dọn vật lý/notification có thể diễn ra trong các đợt maintenance**, không nhất thiết đúng từng nano-giây theo đồng hồ thực. Nếu cần cleanup kịp thời khi ít request, provider có tùy chọn scheduler.

Đừng viết test khẳng định kích thước map vật lý hoặc removal listener luôn cập nhật ngay tức khắc khi vừa qua mốc TTL. Nên test **giá trị truy xuất sau expiration** bằng đồng hồ giả lập hoặc API provider thích hợp.

## 6. Ví dụ Java 17 chạy được: TTL được quyết định bởi provider

Ví dụ dưới đây chạy bằng **Spring Framework 6.2.10**, **Caffeine 3.1.8**, Java 17 và Maven. Nó đặc biệt chứng minh:

1. Annotation `@Cacheable` không chứa TTL.
2. TTL 5 giây được cấu hình trong `CaffeineCacheManager` bằng `expireAfterWrite`.
3. Gọi lại cùng key trước TTL tạo cache hit, không chạy thân phương thức.
4. Sau khi giả lập thời gian vượt TTL, lần đọc kế tiếp thành cache miss và tải lại dữ liệu.
5. Các lần đọc trước TTL **không kéo dài** hạn trong chế độ expire-after-write.

Không dùng `Thread.sleep()`, nên bài thử không phụ thuộc độ trễ CPU hoặc scheduler của máy.

### 6.1. Cấu trúc thư mục

~~~text
spring-cache-ttl/
├── pom.xml
└── src/main/java/demo/TtlDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-cache-ttl</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context-support</artifactId>
      <version>6.2.10</version>
    </dependency>
    <dependency>
      <groupId>com.github.ben-manes.caffeine</groupId>
      <artifactId>caffeine</artifactId>
      <version>3.1.8</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 6.3. src/main/java/demo/TtlDemo.java

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.Ticker;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class TtlDemo {

    // Đồng hồ giả lập: tính thời gian bằng nano-giây.
    public static final class ManualTicker implements Ticker {
        private final AtomicLong nanos = new AtomicLong();

        @Override
        public long read() {
            return nanos.get();
        }

        public void advance(Duration duration) {
            nanos.addAndGet(duration.toNanos());
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {

        @Bean
        public ManualTicker manualTicker() {
            return new ManualTicker();
        }

        @Bean
        public CacheManager cacheManager(ManualTicker ticker) {
            CaffeineCacheManager manager =
                new CaffeineCacheManager("products");

            manager.setCaffeine(
                Caffeine.newBuilder()
                    .maximumSize(100)
                    .expireAfterWrite(Duration.ofSeconds(5))
                    .ticker(ticker)
            );
            return manager;
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    public static class ProductService {
        private final AtomicInteger sourceCalls = new AtomicInteger();

        // Không hề khai báo ttl trên @Cacheable.
        @Cacheable(cacheNames = "products", key = "#p0")
        public String getProduct(String sku) {
            int count = sourceCalls.incrementAndGet();
            return "Product-" + sku + " (load=" + count + ")";
        }

        public int sourceCalls() {
            return sourceCalls.get();
        }
    }

    public static void main(String[] args) {
        try (var ctx =
                new AnnotationConfigApplicationContext(Config.class)) {

            ProductService service =
                ctx.getBean(ProductService.class);
            ManualTicker ticker = ctx.getBean(ManualTicker.class);

            System.out.println("t=0: " + service.getProduct("A"));
            System.out.println("t=0 again: " + service.getProduct("A"));
            ticker.advance(Duration.ofSeconds(4));
            System.out.println("t=4: " + service.getProduct("A"));

            ticker.advance(Duration.ofSeconds(2));
            System.out.println("t=6: " + service.getProduct("A"));

            ticker.advance(Duration.ofSeconds(4));
            System.out.println("t=10: " + service.getProduct("A"));

            ticker.advance(Duration.ofSeconds(2));
            System.out.println("t=12: " + service.getProduct("A"));
            System.out.println(
                "Source calls: " + service.sourceCalls());
        }
    }
}
~~~

**Vì sao ví dụ này hoạt động?** `@EnableCaching` cho phép Spring áp dụng cache advice lên các lời gọi qua bean. `ProductService` được lấy từ `ApplicationContext`, không được tạo thủ công bằng `new` trong phương thức `main`. Đồng hồ `ManualTicker` được truyền cho Caffeine builder; khi tăng thời gian giả lập, Caffeine xem các entry như đã trôi qua một khoảng tương ứng.

### 6.4. Chạy

Từ thư mục chứa `pom.xml`, cần JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.TtlDemo
~~~

Kết quả **do chương trình in ra** (không tính log Maven):

~~~text
t=0: Product-A (load=1)
t=0 again: Product-A (load=1)
t=4: Product-A (load=1)
t=6: Product-A (load=2)
t=10: Product-A (load=2)
t=12: Product-A (load=3)
Source calls: 3
~~~

### 6.5. Giải thích chính xác theo từng thời điểm

| Thời điểm giả lập | Tình trạng key `A` | Thân `getProduct` có chạy? | Giá trị |
| --- | --- | --- | --- |
| t = 0 | Miss, ghi lần đầu | Có | `load=1` |
| t = 0, gọi lại | Hit | Không | `load=1` |
| t = 4 | Chưa hết 5 giây kể từ write tại t=0 | Không | `load=1` |
| t = 6 | Quá hạn của entry ghi tại t=0 | Có | `load=2`, ghi lại tại t=6 |
| t = 10 | Chưa hết hạn của entry ghi tại t=6 | Không | `load=2` |
| t = 12 | Quá hạn của entry ghi tại t=6 | Có | `load=3` |

Quan trọng: đọc ở t=4 **không reset** mốc hết hạn t=5. Nếu cấu hình là `expireAfterAccess(Duration.ofSeconds(5))` thì việc hit tại t=4 có thể kéo dài thời gian cho phép truy cập, dẫn đến kết quả khác. Đây là lựa chọn của Caffeine, **không phải** của `@Cacheable`.

**Lưu ý kiểm chứng:** chương trình dùng một JVM, không có sự cập nhật dữ liệu bên ngoài hay transaction; nó chỉ xác minh expiration của local Caffeine cache. Để dùng production, hãy thay nguồn mô phỏng bằng repository thật và kiểm tra cơ chế invalidation khi dữ liệu nguồn thay đổi.

## 7. Cấu hình TTL trong Spring Boot

Spring Boot có các properties thuận tiện cho nhiều provider. Nhưng các properties này chỉ có hiệu lực khi **Boot thực sự auto-configure CacheManager tương ứng**; nếu ứng dụng tự đăng ký bean quản lý cache, phải xem cách bean riêng được cấu hình.

### 7.1. Redis cache với TTL 10 phút

Ví dụ `application.properties` cho một ứng dụng có Redis được Boot auto-configure:

~~~properties
spring.cache.type=redis
spring.cache.cache-names=products,productSummaries
spring.cache.redis.time-to-live=10m
~~~

Ở đây, TTL 10 phút được đưa vào cấu hình **RedisCacheManager**, không được truyền vào từng `@Cacheable`.

Với provider Redis, cần cả kết nối Redis, driver, serializer, key prefix, cấu hình lỗi và chính sách deployment hợp lệ. Ví dụ trên chỉ mô tả TTL, không phải cấu hình Redis hoàn chỉnh.

### 7.2. Caffeine cache với expire-after-write 10 phút

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=products,productSummaries
spring.cache.caffeine.spec=maximumSize=1000,expireAfterWrite=600s
~~~

Caffeine là local cache; property này không đồng bộ expiration giữa các instance. Lưu ý tên option **`expireAfterWrite`**, không phải `ttl` như một thuộc tính annotation.

Nếu muốn **expire-after-access**, thay bằng cấu hình kiểu `expireAfterAccess=600s`; hai policy khác nhau về việc read có kéo dài thời hạn hay không.

### 7.3. Vì sao không có một property chung `spring.cache.ttl`?

Spring Boot cung cấp các property **provider-specific** như `spring.cache.redis.time-to-live` và `spring.cache.caffeine.spec`. Chúng không có cùng tên, vì các backend không có cùng mô hình expiry.

Cấu hình property trong Spring Boot là tiện ích auto-configuration, không có nghĩa Spring Framework Cache abstraction đã bổ sung một thuộc tính TTL chuẩn cho `@Cacheable`.

Tham khảo: https://docs.spring.io/spring-boot/reference/io/caching.html

## 8. TTL khác nhau cho nhiều vùng cache

Một ứng dụng có thể cần:

- `productDetails`: 10 phút.
- `inventoryCounts`: 15 giây.
- `referenceData`: 1 giờ.

Việc dùng một TTL duy nhất cho tất cả có thể gây dữ liệu tồn kho stale quá lâu hoặc dữ liệu danh mục bị nạp lại quá thường xuyên.

### 8.1. Redis: cấu hình theo cache name

Spring Data Redis hỗ trợ `RedisCacheConfiguration`. Đoạn Java sau là **mã cấu hình minh họa**, cần Spring Data Redis và `RedisConnectionFactory` thật:

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

public class RedisCacheFactory {

    public RedisCacheManager build(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaultConfig =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10));

        RedisCacheConfiguration inventoryConfig =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofSeconds(15));

        RedisCacheConfiguration referenceConfig =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofHours(1));

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaultConfig)
            .withInitialCacheConfigurations(Map.of(
                "inventoryCounts", inventoryConfig,
                "referenceData", referenceConfig
            ))
            .build();
    }
}
~~~

Những cache names không có cấu hình riêng có thể dùng default, tùy chính sách tạo cache của manager. Đây là một cách quản lý TTL **theo vùng**, không theo annotation.

Với Spring Data Redis 3.2+ có thể có tính năng TTL function để tính thời hạn theo giá trị/đối số của thao tác ghi; phải kiểm tra version và ngữ nghĩa của provider trước khi sử dụng. Không mặc định rằng mọi backend đều cho phép TTL khác nhau trên từng entry.

### 8.2. Caffeine: nhiều manager hoặc cache cấu hình riêng

Một `CaffeineCacheManager` thông thường có thể được cấu hình một `Caffeine` builder dùng chung cho các cache do manager tạo. Nếu các vùng cần TTL rất khác nhau, lựa chọn gồm:

- **Nhiều CacheManager** được cấu hình riêng và lựa chọn bằng tên bean qua `cacheManager` hoặc `CacheResolver`.
- **Đăng ký native cache tùy biến** cho từng tên qua những API được version đang dùng hỗ trợ.
- **Tách nhóm vùng cache** có cùng chính sách expiration/size, thay vì cố ép tất cả dùng cùng builder.

Mã minh họa để chọn manager theo tên bean đã được ứng dụng đăng ký:

~~~java
@Cacheable(
    cacheNames = "inventoryCounts",
    cacheManager = "fastExpiringCacheManager",
    key = "#p0"
)
public long inventoryCount(String sku) {
    return repository.countBySku(sku);
}
~~~

Đoạn này **không phải runnable độc lập**; bean `fastExpiringCacheManager` và repository cần được cấu hình. Nó minh họa cách method chọn vùng/provider được cấu hình TTL ngắn.

### 8.3. TTL theo kết quả hoặc theo từng key

Nếu một mục có expiry riêng do dữ liệu nghiệp vụ quyết định, bạn có thể cần API native:

- Caffeine cung cấp expiry biến đổi qua `Expiry` khi một entry cần hạn sử dụng riêng.
- Redis có thể hỗ trợ TTL function trong `RedisCacheConfiguration` ở phiên bản Spring Data Redis tương ứng.
- Một thao tác dùng `RedisTemplate` có thể gọi API Redis với expiry explicit, nhưng đó là **một mô hình truy cập khác** với annotation cache chuẩn.

Không giả định một custom `@MyCacheable(ttl=...)` chỉ cần meta-annotate `@Cacheable` là tự thực thi TTL. Meta-annotation chỉ mô tả Spring cache operation được kế thừa; muốn kiểm soát expiry native phải có logic tích hợp riêng, và giải pháp đó không còn hoàn toàn portable.

## 9. Các nhầm lẫn thường gặp về annotation và vòng đời

### 9.1. `@CacheEvict` không tự động kích hoạt sau N giây

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void updateProduct(long id) {
    repository.update(id);
}
~~~

Đây là **mã minh họa**. Annotation này được xử lý theo một **lời gọi phương thức/sự kiện nghiệp vụ**, không tự đếm ngược 300 giây rồi evict. Mặc định, sau khi method hoàn tất thành công, Spring yêu cầu xóa entry tương ứng.

Nếu cần hết hạn tự động theo thời gian, cấu hình provider.

### 9.2. `unless` và `condition` không định nghĩa TTL

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 > 0",
    unless = "#result == null"
)
public ProductDto getProduct(long id) {
    return repository.findDto(id);
}
~~~

Đây là **mã minh họa**. `condition` quyết định lời gọi có tham gia caching hay không; `unless` từ chối ghi một kết quả vừa tạo. Chúng không có nghĩa “xóa entry sau 5 phút”.

Một SpEL so sánh thời gian trong `condition` cũng không tự làm cho **entry đã tồn tại** hết hạn vào thời điểm tương ứng. Nếu muốn dùng dữ liệu thời gian để xây key phiên bản, phải quản lý key cũ, memory và tính đồng bộ; đó là **thiết kế versioned cache**, không phải TTL native.

### 9.3. `sync = true` không có nghĩa refresh theo TTL

`@Cacheable(sync = true)` gợi ý provider phối hợp những lời gọi cùng key khi cache miss, giúp giảm tải nạp trùng nếu provider hỗ trợ. Nó **không thêm TTL** và không tự lập lịch refresh. Cần xét các giới hạn khác của `sync` khi thiết kế cache operation.

### 9.4. `@CachePut` có thể đặt lại vòng đời theo chính sách provider

`@CachePut` luôn chạy phương thức đích và cân nhắc lưu kết quả vào cache. Nếu provider dùng expire-after-write, việc ghi lại entry thường **khởi động lại thời hạn tính từ lúc write**. Nhưng Spring Cache không tự biết TTL là bao nhiêu; provider quyết định.

### 9.5. Cache null hoặc kết quả lỗi vẫn cần policy

Nếu phương thức trả `null` và provider cho phép lưu null, kết quả “không tìm thấy” có thể được cache. Việc cache null 10 giây hay không cache null là quyết định ứng dụng/provider. Tương tự, khi method bắt ngoại lệ rồi trả một DTO lỗi bình thường, DTO ấy có thể đi vào cache nếu không có `unless` hoặc điều kiện phù hợp.

Negative caching nên có TTL phù hợp và tránh biến lỗi tạm thời thành kết quả bị lưu quá lâu.

### 9.6. Không có TTL không đồng nghĩa dữ liệu tồn tại mãi mãi

Entry vẫn có thể biến mất vì:

- ứng dụng restart (với local cache);
- `@CacheEvict` hoặc một thao tác `Cache.evict/clear`;
- provider eviction khi vượt maximum size/memory;
- failover và chính sách lưu trữ;
- administrator hoặc tác vụ housekeeping xóa entry;
- cách cụ thể provider cấu hình retention.

Do đó “không cấu hình TTL” và “entry mãi mãi không mất” là hai mệnh đề khác nhau.

## 10. TTL không đảm bảo dữ liệu luôn mới hoặc hệ thống luôn nhanh

### 10.1. Stale data trước thời điểm hết hạn

Giả sử cache `inventoryCounts[SKU-1]` chứa 10 và có TTL 1 giờ. Tại phút 3 kho xuất 2 hàng, giá trị đúng còn 8. Nếu không xóa/cập nhật entry, các lượt đọc cache trong thời gian còn hạn có thể tiếp tục thấy 10.

Muốn mức độ nhất quán tốt hơn, kết hợp:

- xóa bằng `@CacheEvict` sau khi cập nhật nguồn;
- cập nhật giá trị mới đúng bằng `@CachePut`;
- invalidation event đến các instance;
- giảm TTL ở vùng nhạy cảm;
- chọn không cache một số phép đọc quan trọng.

TTL là **giới hạn tuổi**, không phải cơ chế đồng bộ transaction.

### 10.2. Cache stampede sau hết hạn đồng loạt

Nếu hàng nghìn key hết hạn cùng một thời điểm (hoặc một key rất hot hết hạn khi có nhiều request), nhiều request có thể đồng thời đọc nguồn. Có thể xem xét:

- `@Cacheable(sync = true)` khi provider hỗ trợ semantics phù hợp;
- single-flight/locking theo key ở cấp provider;
- TTL jitter để phân tán thời điểm hết hạn;
- refresh-ahead/stale-while-revalidate có thiết kế rõ;
- monitoring tải nguồn khi cache miss tăng.

Không mặc định rằng mọi `CacheManager` hỗ trợ lock liên instance. Cache local Caffeine trên nhiều node có thể vẫn cùng miss vào nguồn ở những node khác nhau.

### 10.3. Thời gian TTL tính ở đâu?

- **Caffeine:** chính sách dùng time source/ticker của cache trong process.
- **Redis:** expiration được quản lý trong Redis, với semantics và thời gian của backend.
- **Cache phân tán:** các instance cần thống nhất key, serialization và invalidation nhưng không nhất thiết dùng chung cách đo thời gian như cache local.

Đừng lấy `System.currentTimeMillis()` ở từng service instance rồi tự suy ra provider chắc chắn hết hạn đúng vào cùng một millis giữa các node. Đối với thời gian tuyệt đối nghiệp vụ (token expiration, legal deadline), phải thiết kế theo yêu cầu hệ thống và đảm bảo clock skew phù hợp.

### 10.4. Transaction và expire/evict

Một lần `@CachePut` hoặc `@CacheEvict` kết hợp cập nhật database có thể xảy ra ở mốc khác với transaction commit tùy advice ordering và transaction-aware cache. TTL không sửa được vấn đề cập nhật cache trước commit, hoặc race giữa reader nạp dữ liệu cũ và writer xóa cache.

Khi tính đúng quan trọng hơn latency, kiểm thử rollback/commit và concurrent reads, đồng thời dùng chính sách after-commit phù hợp.

## 11. Cách chọn TTL và thiết kế theo vùng cache

Không có một giá trị TTL “chuẩn Spring”. Bắt đầu từ độ mới mà nghiệp vụ cho phép, tần suất thay đổi, chi phí nguồn, đặc tính truy cập và mức độ tác động của dữ liệu sai.

| Dữ liệu | Điểm cần cân nhắc | Chính sách tham khảo để bắt đầu thử nghiệm |
| --- | --- | --- |
| Danh mục tĩnh | Ít cập nhật, có cơ chế phát hành rõ | TTL tương đối dài và invalidation khi triển khai cập nhật |
| Giá sản phẩm | Có thể thay đổi theo chiến dịch | TTL ngắn hơn, xóa cache theo event đổi giá |
| Tồn kho | Nhạy với giao dịch bán hàng | TTL rất ngắn hoặc tránh cache trên đường quyết định bán; cần invalidation có kiểm chứng |
| Quy tắc cấu hình | Theo version hoặc deployment | Key có version/config generation; có thể TTL dài |
| Kết quả “không tìm thấy” | Dữ liệu có thể được tạo ngay sau đó | TTL ngắn hoặc không cache null |
| Dữ liệu cá nhân/quyền | Cần phân quyền và tránh rò rỉ | Xem xét không cache hoặc key/scope được kiểm soát nghiêm ngặt |

Đây là **hướng đánh giá**, không phải cam kết rằng mọi hệ thống phải dùng một số phút cố định. TTL đúng cần được đo đạc và thương lượng với yêu cầu nghiệp vụ.

### Checklist thiết kế

- [ ] Xác định rõ dữ liệu nào được phép stale trong bao lâu.
- [ ] Phân biệt TTL tính từ write hay TTI tính từ access.
- [ ] Chọn provider có năng lực expiration phù hợp.
- [ ] Đặt TTL ở nơi được provider áp dụng thật, không ở annotation không tồn tại.
- [ ] Biết cách chia cache names theo nhóm dữ liệu và chính sách thời gian.
- [ ] Có chiến lược `@CacheEvict`/`@CachePut` cho những cập nhật cần thấy ngay.
- [ ] Có giới hạn dung lượng/maximum size và theo dõi eviction.
- [ ] Test expiry bằng fake clock/ticker hoặc phương pháp deterministic tương đương.
- [ ] Test cả cache hit, miss, hết hạn, reload và lỗi provider.
- [ ] Test multi-instance, transaction và concurrency nếu ứng dụng dùng.
- [ ] Giám sát hit rate, load latency, stale data, memory, Redis connections và cache errors.
- [ ] Không dựa vào TTL để thay thế kiểm tra authorization hoặc idempotency.

## 12. Câu hỏi tự kiểm tra

**1.** Vì sao `@Cacheable` không khai báo `ttl` chung?  
**Đáp án:** Spring Cache trừu tượng hóa thao tác đọc/ghi/xóa cache trên nhiều provider có khả năng expiration khác nhau; TTL thuộc chính sách backend.

**2.** Có thể dùng `@Cacheable(cacheNames="x", ttl=60)` trong Spring Framework cache annotation chuẩn không?  
**Đáp án:** Không, `ttl` không phải thuộc tính của `@Cacheable`.

**3.** `ConcurrentMapCacheManager` mặc định có tự làm entry hết hạn sau 5 phút không?  
**Đáp án:** Không có TTL tích hợp. Entry có thể bị xóa thủ công hoặc biến mất khi cache/process bị hủy, nhưng không có expire-after-write chuẩn.

**4.** `expireAfterWrite(5m)` và `expireAfterAccess(5m)` khác gì?  
**Đáp án:** Cái đầu tính từ write/replace; cái sau tính từ truy cập gần nhất, nên cache hit có thể làm trượt hạn.

**5.** Trong demo, vì sao `getProduct("A")` ở t=4 hit nhưng ở t=6 miss?  
**Đáp án:** TTL 5 giây tính từ lần write tại t=0; read ở t=4 không reset hạn.

**6.** Spring Boot có thuộc tính chung `spring.cache.ttl=5m` cho mọi provider không?  
**Đáp án:** Không. Có các tùy chọn riêng như `spring.cache.redis.time-to-live` và `spring.cache.caffeine.spec`.

**7.** Nếu DB đổi trước khi TTL kết thúc, cache có tự nhận biết không?  
**Đáp án:** Không. Cần evict/put hoặc cơ chế đồng bộ/invalidation khác nếu yêu cầu dữ liệu mới ngay.

**8.** `@CacheEvict` có tự chạy sau 60 giây không?  
**Đáp án:** Không; nó gắn với một cache operation được kích hoạt theo lời gọi method.

**9.** Nếu hai loại dữ liệu cần TTL rất khác nhau, nên làm gì?  
**Đáp án:** Tách cache names/provider configuration theo từng vùng hoặc dùng chính sách expiry riêng được provider hỗ trợ.

**10.** Vì sao không dùng `Thread.sleep(5000)` trong unit test TTL?  
**Đáp án:** Test sẽ chậm, dễ phụ thuộc scheduler và bị flake. Với Caffeine có thể dùng `Ticker` giả lập như ví dụ.

**11.** Khi Caffeine báo một entry expired, nó có nhất thiết bị dọn khỏi cấu trúc nội bộ ngay tại cùng thời điểm không?  
**Đáp án:** Không. Entry không hợp lệ khi truy xuất, nhưng cleanup vật lý/notification có thể diễn ra khi maintenance hoạt động.

**12.** TTL có giải quyết cache stampede khi một key hot hết hạn không?  
**Đáp án:** Không. Có thể cần đồng bộ miss, refresh, jitter hoặc các kỹ thuật khác ngoài TTL.

## Tài liệu tham khảo

- Spring Framework 6.2 — How can I Set the TTL/TTI/Eviction policy/XXX feature?: https://docs.spring.io/spring/reference/6.2/integration/cache/specific-config.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework 6.2 — CaffeineCacheManager API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Boot — Caching and provider-specific properties: https://docs.spring.io/spring-boot/reference/io/caching.html
- Spring Data Redis — RedisCacheConfiguration API: https://docs.spring.io/spring-data/redis/docs/3.4.1/api/org/springframework/data/redis/cache/RedisCacheConfiguration.html
- Caffeine documentation — Eviction/expiration and ticker: https://github.com/ben-manes/caffeine/wiki/Eviction
- Caffeine documentation — Cleanup of expired entries: https://github.com/ben-manes/caffeine/wiki/Cleanup
