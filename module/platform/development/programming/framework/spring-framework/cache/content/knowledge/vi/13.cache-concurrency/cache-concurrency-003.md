# Giới hạn một cache, không unless và không ghép thao tác khi sync

> **Chủ đề:** Spring Framework Cache — mục **Đồng thời**. Bài học phân tích ba giới hạn bắt buộc khi sử dụng `@Cacheable(sync = true)`: **chỉ một cache cho mỗi thao tác**, **không sử dụng `unless`**, và **không kết hợp với cache operation khác trên cùng phương thức**. Đồng thời, chúng ta sẽ tìm hiểu lý do kỹ thuật, cách viết đúng, phương án thay thế và phép kiểm thử cạnh tranh bằng Java 17.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài, bạn có thể:

1. Giải thích hiện tượng **cache stampede** khi nhiều thread cùng gặp cache miss cho một key.
2. Hiểu `sync = true` tác động đến việc tính kết quả ở đâu và vì sao nó phụ thuộc cache provider.
3. Nêu chính xác ba hạn chế: một cache, không `unless`, không ghép hoạt động cache khác.
4. Phân biệt giới hạn ở **một phương thức** với việc ứng dụng có nhiều cache hoặc nhiều phương thức sử dụng cache.
5. Dự đoán hành vi code hợp lệ và nhận diện code có khả năng bị Spring từ chối.
6. Dùng `ConcurrentMapCacheManager` và hai lời gọi đồng thời để kiểm chứng số lần thân phương thức thực thi.
7. Chọn một giải pháp khác khi thật sự cần lọc kết quả sau khi gọi phương thức, cập nhật nhiều cache hoặc đồng bộ xuyên nhiều instance.

## 2. Tại sao cần synchronized caching?

Một lời gọi đọc thông thường:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String productId) {
    return repository.load(productId);
}
```

Đây là **mã minh họa trong Spring bean**, chưa phải chương trình độc lập. Spring Cache interceptor tra key trước khi gọi thân method:

- **Hit:** trả giá trị cache, thường không chạy method.
- **Miss:** gọi method để tính giá trị và đưa vào cache.

Trong môi trường đồng thời, giả sử 10 request cùng tìm `P42` khi cache còn trống:

```text
Thời điểm      Thread A               Thread B               Thread C
---------      --------               --------               --------
t0             GET(P42) -> miss       GET(P42) -> miss       GET(P42) -> miss
t1             gọi DB/API            gọi DB/API            gọi DB/API
t2             PUT(P42)              PUT(P42)              PUT(P42)
t3             trả kết quả           trả kết quả           trả kết quả
```

Không có phối hợp trên lần tải đầu, nhiều thread có thể cùng chạy công việc tốn kém. Đây là tình huống thường gọi là **cache stampede** hoặc **thundering herd**. Nó thường xảy ra khi cache vừa khởi động, key có nhiều lượt truy cập hết hạn đồng thời, hoặc mục bị invalidation.

Spring hỗ trợ:

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String productId) {
    return repository.load(productId);
}
```

`sync = true` yêu cầu cache provider phối hợp việc **tính giá trị cho một key đang miss**. Với provider có hỗ trợ đồng bộ phù hợp, chỉ một thread chạy loader cho key đó trong lúc các thread khác đợi kết quả. Tuy nhiên đây là **một yêu cầu/hint gửi tới provider**, không phải cam kết độc lập rằng mọi công nghệ cache đều có khóa phân tán hoặc loại bỏ toàn bộ lần chạy lặp.

## 3. Ba giới hạn chính của sync = true

JavaDoc chính thức của `org.springframework.cache.annotation.Cacheable` xác định ba giới hạn của synchronized caching:

| Giới hạn | Điều không được làm | Vì sao cần chú ý |
| --- | --- | --- |
| **Một cache duy nhất** | Khai báo nhiều cache name cho một `@Cacheable(sync = true)` | Cơ chế load đồng bộ cần một cache đích nhất quán cho lần tính |
| **Không có unless** | Đặt `unless = ...`, kể cả kiểm tra `#result` | `unless` cần quyết định từ chối lưu sau khi chạy method, không phù hợp đường load đồng bộ của API cache |
| **Không ghép thao tác cache khác** | Kết hợp synchronized `@Cacheable` với `@CachePut`, `@CacheEvict` hoặc cache operation khác trên **cùng phương thức** | Không hỗ trợ một lần invocation vừa dùng đường load đồng bộ vừa có thêm thao tác cache khác |

Các hạn chế là **quy tắc của Spring Cache annotation**, không chỉ là khuyến nghị về style. Vi phạm có thể dẫn đến cấu hình/operation bị Spring từ chối khi framework kiểm tra; không nên phụ thuộc vào thời điểm hay nguyên văn exception message giữa các phiên bản.

**Không nhầm với chuyện một ứng dụng có nhiều cache:** ứng dụng vẫn có thể có cache `products`, `prices` và `customers`; chỉ **một lời gọi `@Cacheable(sync = true)`** phải hướng tới đúng một cache. Việc một phương thức khác có `@CacheEvict` để xóa key trong cache đó vẫn hợp lệ.

## 4. Giới hạn 1 — mỗi synchronized operation chỉ dùng một cache

### Sai: nhiều cache name trong một annotation

```java
@Cacheable(cacheNames = {"productsLocal", "productsRemote"}, sync = true)
public Product find(String id) {
    return repository.load(id);
}
```

Đây là **ví dụ không hợp lệ khi dùng synchronized caching**, không nên đưa vào ứng dụng đang chạy. Trong mode thông thường, một `@Cacheable` có thể tra nhiều cache name. Nhưng khi `sync = true`, Spring chỉ hỗ trợ **một cache cho mỗi operation**. Cấu hình hai cache name vi phạm giới hạn bất kể chúng đều phục vụ cùng một dữ liệu.

Nếu dùng `CacheResolver` tùy chỉnh, cần bảo đảm resolver thực tế trả về đúng một cache cho synchronized operation; việc không liệt kê tên trong annotation không phải cách lách quy tắc.

### Đúng: một cache cho một method

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String id) {
    return repository.load(id);
}
```

Nếu muốn cache `prices` riêng, hãy sử dụng một phương thức phù hợp khác (hoặc một chiến lược cache đa tầng do provider thực hiện bên trong), thay vì khai báo hai tên cache cho cùng `@Cacheable(sync = true)`.

### Cần cache nhiều tầng thì sao?

Có hai bài toán khác nhau:
- **Một cache operation có hai vùng lưu riêng:** vi phạm giới hạn sync nếu framework nhận hai cache.
- **Một cache logic với nhiều tầng bên trong provider:** có thể khả thi nếu provider triển khai một đối tượng `Cache` với hợp đồng đồng bộ thích hợp, nhưng phải kiểm tra semantics cụ thể.

Đừng coi `CompositeCacheManager` hay `CacheResolver` chọn nhiều cache là “một cache”. Một cache logic của synchronized operation phải được Spring resolve thành **một đối tượng `Cache` duy nhất**.

## 5. Giới hạn 2 — không dùng unless cùng sync

### Sai: từ chối lưu kết quả sau khi method chạy

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true,
    unless = "#result == null"
)
public Product find(String id) {
    return repository.load(id);
}
```

Đây là **ví dụ không hợp lệ**. `unless` được đánh giá **sau khi method đã chạy**, nhằm không đưa một kết quả cụ thể vào cache. `sync = true` dùng đường truy xuất có loader gắn trực tiếp với cache, điển hình qua hợp đồng `Cache.get(key, Callable)`. Spring không hỗ trợ việc ghép `unless` vào đường thực thi synchronized đó.

### Đừng nghĩ đổi biểu thức unless là đủ

Các biến thể sau vẫn không giải quyết được vấn đề:

```java
@Cacheable(cacheNames = "products", sync = true, unless = "false")
@Cacheable(cacheNames = "products", sync = true, unless = "#result.price < 0")
```

Đây là **hai dòng annotation độc lập để minh họa lỗi**, không được ghép cả hai vào một method. Cả hai đều khai báo `unless` không rỗng, dù điều kiện luôn false hay chỉ đúng ở vài kết quả. Muốn dùng `sync = true`, hãy **bỏ hẳn thuộc tính `unless`** chứ không chỉ đổi nội dung SpEL.

### Condition có được dùng không?

**Có**, `condition` và `unless` không giống nhau. `condition` quyết định **trước khi tải** có áp dụng cache hay không, còn `unless` là quyết định **sau khi tính kết quả**.

Ví dụ hợp lệ:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true,
    condition = "#p0 != null && !#p0.isBlank()"
)
public Product find(String id) {
    return repository.load(id);
}
```

Khi `id` không hợp lệ, condition false khiến Spring bỏ qua caching và gọi method trực tiếp; **method vẫn cần tự validate input**. Khi ID hợp lệ, đồng bộ được áp dụng theo provider.

Đừng dùng `condition` thay thế `unless` nếu chính sách phụ thuộc kết quả, ví dụ “chỉ lưu Product có giá dương”: trước khi gọi method, Spring chưa có `#result` để kiểm tra. Đây là hai yêu cầu khác nhau, cần thiết kế lại thay vì biến một biểu thức hậu xử lý thành điều kiện tiền xử lý.

### Nếu cần không cache null result thì sao?

Có thể cân nhắc:
1. **Không dùng sync:** giữ `@Cacheable(unless = "#result == null")` và chấp nhận/giải quyết cache stampede bằng cơ chế riêng ở nơi cần thiết.
2. **Thay đổi hợp đồng đầu ra:** dùng kết quả biểu diễn rõ trạng thái (ví dụ đối tượng kết quả có giá trị phù hợp); xem xét chính sách lưu của provider thay vì kỳ vọng `unless`. Cần tránh cache “không tìm thấy” quá lâu.
3. **Cache thủ công với chính sách có kiểm soát:** viết loader/gate riêng hoặc dùng API provider, bảo đảm đồng bộ và lọc kết quả sau khi tính theo yêu cầu cụ thể.
4. **Áp dụng TTL/invalidation phù hợp:** nếu chấp nhận lưu kết quả âm trong một thời gian ngắn và provider hỗ trợ, cần nêu rõ chính sách nhất quán; không mặc định mọi provider hỗ trợ null value.

`sync = true` không tự cho phép hoặc cấm lưu null ở mọi provider. Việc lưu `null` phụ thuộc implementation và cấu hình. Bỏ `unless` đồng nghĩa bạn **không còn veto result qua annotation này**, chứ không chứng minh rằng mọi null result chắc chắn được lưu.

## 6. Giới hạn 3 — không ghép cache operation khác trên cùng method

### Sai: synchronized cacheable và cache put đồng thời

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
@CachePut(cacheNames = "products", key = "#p0")
public Product loadAndRefresh(String id) {
    return repository.load(id);
}
```

Mẫu này vi phạm giới hạn **không kết hợp operation khác**. Ngoài ra, `@Cacheable` và `@CachePut` tự thân đã có mục tiêu trái nhau: cacheable có thể bỏ qua thân method khi hit, trong khi put thường chạy method để cập nhật cache. Khi thêm `sync = true`, mẫu này lại có thêm ràng buộc không được ghép thao tác.

### Sai: đồng bộ cacheable và eviction cùng invocation

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
@CacheEvict(cacheNames = "products", key = "#p0")
public Product loadAndEvict(String id) {
    return repository.load(id);
}
```

Cũng không hợp lệ; `@CacheEvict` là cache operation khác được áp dụng trên chính method. Cách viết tổng hợp bằng `@Caching` cũng không làm mất giới hạn:

```java
@Caching(
    cacheable = @Cacheable(cacheNames = "products", sync = true),
    put = @CachePut(cacheNames = "products")
)
public Product loadAndPut(String id) {
    return repository.load(id);
}
```

Ba đoạn trên là **anti-pattern có chủ đích**, chỉ dùng để nhận biết lỗi, không copy vào dự án chạy được.

### Đúng: tách đọc và cập nhật/xóa

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String id) {
    return repository.load(id);
}

@CacheEvict(cacheNames = "products", key = "#p0")
public void invalidate(String id) {
    repository.markDirty(id);
}
```

Đây là đoạn minh họa trong một bean có repository. Việc có `@CacheEvict` trên **phương thức khác** không vi phạm hạn chế của synchronized `@Cacheable`. Tương tự, một method cập nhật riêng có thể dùng `@CachePut` khi nó thực sự ghi nguồn và trả giá trị canonical cần lưu; cả hai phải thống nhất key và cache name.

Hãy kiểm tra transaction/commit khi invalidation liên quan database: xóa cache quá sớm có thể khiến request khác nạp lại dữ liệu cũ trước khi giao dịch commit. Đồng bộ cho lần miss không thay thế logic nhất quán dữ liệu.

## 7. Tại sao sync = true phụ thuộc cache provider?

Synchronized caching cần cache có khả năng thực hiện thao tác **lấy hoặc tính giá trị gắn với một key**. Spring Cache API hỗ trợ hợp đồng `Cache.get(Object key, Callable<T> valueLoader)`, cho phép provider phối hợp lần tải. Nhưng đây là **hợp đồng mở rộng**: cách khóa, thời gian chờ, xử lý lỗi, phạm vi JVM và khả năng cache future phụ thuộc implementation.

### Những điều có thể kỳ vọng khi provider hỗ trợ

- Những thread **cùng key, cùng cache, trên cùng phạm vi đồng bộ của provider** không đồng thời chạy loader nếu chưa có kết quả.
- Sau khi loader thành công và value được đưa vào cache, những thread chờ nhận lại value đó theo hợp đồng implementation.
- Hai key khác nhau thường có thể tính độc lập, nhưng mức độ song song phụ thuộc cấu trúc khóa của provider.
- Nếu loader lỗi, mục bị evict, timeout hoặc provider không lưu value, việc tính lại ở lần sau hoàn toàn có thể xảy ra.

### Những điều không nên hứa

- **Không bảo đảm khóa phân tán:** dùng Redis hay một hệ thống phân tán không tự suy ra `sync = true` khóa toàn bộ instance ứng dụng. Phải kiểm tra implementation và nếu cần thì dùng distributed lock/single-flight riêng.
- **Không bảo đảm đúng một lần mãi mãi:** lỗi, expiration, eviction, restart hoặc thay đổi key tạo các lần miss mới.
- **Không thay transaction hoặc idempotency:** đồng bộ trong cache không ngăn hai command nghiệp vụ ghi dữ liệu cùng lúc nếu chúng đi đường khác.
- **Không bảo đảm performance tăng:** contention có thể chuyển từ nhiều truy vấn đồng thời thành các request phải chờ loader lâu; cần đo throughput và độ trễ tail.

Spring Framework ghi rõ synchronized caching là tính năng **tùy chọn** theo cache library và khuyến nghị kiểm tra tài liệu provider. Các `CacheManager` trong Spring Framework core hỗ trợ cơ chế này, nhưng điều đó không mở rộng thành cam kết tương đương cho mọi provider bên ngoài.

## 8. Ví dụ Java 17 chạy được: đối chiếu sync và mặc định

Thí nghiệm chạy **Spring Framework 6.2.16**, `ConcurrentMapCacheManager` và hai luồng client cho cùng key `P1`. Nó không cần database, Redis hay Spring Boot. Hai method có cache **riêng biệt** trong cùng bean: một method có `sync = true`, method còn lại mặc định không sync. Đây là cách sử dụng **hợp lệ** vì mỗi method chỉ có một operation, một cache name và không có `unless`.

### 8.1. Cấu trúc dự án

```text
spring-cache-sync-demo/
├── pom.xml
└── src/
    ├── main/java/demo/cache/CacheSyncDemo.java
    └── test/java/demo/cache/CacheSyncDemoTest.java
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
    <artifactId>spring-cache-sync-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
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
                    <mainClass>demo.cache.CacheSyncDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` mang Spring Cache abstraction và `ConcurrentMapCacheManager`, đồng thời kéo các thư viện Spring liên quan bằng dependency. JUnit được dùng cho test. Trong dự án Spring Boot thật, hãy dùng parent/BOM tương thích thay vì ép phiên bản module Spring riêng lẻ.

### 8.3. `src/main/java/demo/cache/CacheSyncDemo.java`

```java
package demo.cache;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheSyncDemo {

    public static class QueryService {
        private final AtomicInteger syncLoads = new AtomicInteger();
        private final AtomicInteger plainLoads = new AtomicInteger();

        private final CountDownLatch syncEntered = new CountDownLatch(1);
        private final CountDownLatch syncRelease = new CountDownLatch(1);
        private final CountDownLatch plainEntered = new CountDownLatch(2);
        private final CountDownLatch plainRelease = new CountDownLatch(1);

        @Cacheable(cacheNames = "synchronizedProducts",
                   key = "#p0", sync = true)
        public String loadSync(String id) {
            int n = syncLoads.incrementAndGet();
            syncEntered.countDown();
            await(syncRelease);
            return id + ":v" + n;
        }

        @Cacheable(cacheNames = "normalProducts", key = "#p0")
        public String loadPlain(String id) {
            int n = plainLoads.incrementAndGet();
            plainEntered.countDown();
            await(plainRelease);
            return id + ":v" + n;
        }

        public void awaitSyncEntered() {
            await(syncEntered);
        }

        public void awaitPlainEntered() {
            await(plainEntered);
        }

        public void releaseSync() {
            syncRelease.countDown();
        }

        public void releasePlain() {
            plainRelease.countDown();
        }

        public int syncCount() {
            return syncLoads.get();
        }

        public int plainCount() {
            return plainLoads.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                    "synchronizedProducts", "normalProducts");
        }

        @Bean
        public QueryService queryService() {
            return new QueryService();
        }
    }

    static void await(CountDownLatch latch) {
        try {
            if (!latch.await(20, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
    }

    static String runTwo(
            ExecutorService executor,
            Function<String, String> call,
            Runnable waitForLoader,
            Runnable releaseLoader) throws Exception {

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<String> task = () -> {
            ready.countDown();
            await(start);
            return call.apply("P1");
        };

        Future<String> first = executor.submit(task);
        Future<String> second = executor.submit(task);

        await(ready);
        start.countDown();
        waitForLoader.run();
        releaseLoader.run();

        String a = first.get(20, TimeUnit.SECONDS);
        String b = second.get(20, TimeUnit.SECONDS);

        // Sắp xếp để output không phụ thuộc thứ tự thread.
        return a.compareTo(b) <= 0
                ? "[" + a + "," + b + "]"
                : "[" + b + "," + a + "]";
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            var service = context.getBean(QueryService.class);
            var manager = context.getBean(CacheManager.class);
            ExecutorService executor = Executors.newFixedThreadPool(2);
            try {
                System.out.println("manager="
                        + manager.getClass().getSimpleName());

                System.out.println("sync="
                        + runTwo(executor, service::loadSync,
                                service::awaitSyncEntered,
                                service::releaseSync));
                System.out.println("syncExecutions="
                        + service.syncCount());

                System.out.println("plain="
                        + runTwo(executor, service::loadPlain,
                                service::awaitPlainEntered,
                                service::releasePlain));
                System.out.println("plainExecutions="
                        + service.plainCount());
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
```

### 8.4. Chạy ứng dụng

Cần JDK 17+, Maven 3.9+ và truy cập Maven Central khi tải dependency lần đầu. Tại thư mục dự án:

```bash
java -version
mvn -q compile exec:java
```

Các dòng **do chính chương trình in ra** (không tính log do Maven hoặc Spring phát ra):

```text
manager=ConcurrentMapCacheManager
sync=[P1:v1,P1:v1]
syncExecutions=1
plain=[P1:v1,P1:v2]
plainExecutions=2
```

Giải thích:

1. Hai tác vụ đợi tín hiệu `start` rồi cùng gọi một key `P1`.
2. Với `loadSync`, cache provider phối hợp để chỉ một loader phải tính. Cả hai lần đọc nhận `P1:v1`; số lần thân method chạy là 1.
3. Với `loadPlain`, mỗi lần miss có thể chạy loader riêng. `CountDownLatch(2)` trong method **cố ý giữ cả hai lượt thực thi ở bên trong** trước khi cho chúng hoàn tất, do đó bảo đảm thí nghiệm minh họa hai miss chồng lấn của cache mặc định. Hai kết quả khác nhau `v1` và `v2` được sắp xếp trước khi in để không phụ thuộc thứ tự thread.
4. Hai cache là **hai cache name của hai method khác nhau**, không phải hai tên được đưa vào cùng một `@Cacheable(sync = true)`. Vì vậy ví dụ không vi phạm giới hạn một cache.
5. Đây là ví dụ chạy trong **một JVM** với `ConcurrentMapCacheManager`. Nó không chứng minh một Redis cluster hay nhiều ứng dụng trên các máy khác nhau cũng phối hợp loader như vậy.

Một timeout có chủ đích trong demo (20 giây) giúp test không chờ vô hạn nếu worker bị kẹt hoặc provider thay đổi hành vi. Nếu máy bị quá tải, thay đổi timeout phục vụ phép thử; không lấy timeout làm mức cam kết sản xuất.

## 9. Kiểm thử tự động bằng JUnit 5

Tạo `src/test/java/demo/cache/CacheSyncDemoTest.java`:

```java
package demo.cache;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CacheSyncDemoTest {

    @Test
    void syncUsesSingleLoaderForTheSameKey() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                CacheSyncDemo.Config.class)) {

            var service = context.getBean(
                    CacheSyncDemo.QueryService.class);
            ExecutorService pool = Executors.newFixedThreadPool(2);
            try {
                assertEquals(
                        "[P1:v1,P1:v1]",
                        CacheSyncDemo.runTwo(
                                pool,
                                service::loadSync,
                                service::awaitSyncEntered,
                                service::releaseSync)
                );
                assertEquals(1, service.syncCount());
            } finally {
                pool.shutdownNow();
            }
        }
    }

    @Test
    void defaultModeCanComputeSameKeyTwiceConcurrently()
            throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                CacheSyncDemo.Config.class)) {

            var service = context.getBean(
                    CacheSyncDemo.QueryService.class);
            ExecutorService pool = Executors.newFixedThreadPool(2);
            try {
                assertEquals(
                        "[P1:v1,P1:v2]",
                        CacheSyncDemo.runTwo(
                                pool,
                                service::loadPlain,
                                service::awaitPlainEntered,
                                service::releasePlain)
                );
                assertEquals(2, service.plainCount());
            } finally {
                pool.shutdownNow();
            }
        }
    }
}
```

Chạy:

```bash
mvn -q test
```

Kết quả mong đợi: JUnit tests thành công và Maven trả exit code 0. Với `-q` có thể không thấy dòng “BUILD SUCCESS”. Test dùng ApplicationContext và Spring bean thật thay vì tạo `new QueryService()`; như vậy annotation mới có thể được áp dụng. Test chỉ minh họa provider cụ thể và cơ chế đồng thời trong một tiến trình.

**Lưu ý kiểm thử:** bài test thứ hai cố ý đợi cả hai thân method mặc định đã vào loader; đó là phép thử cạnh tranh, **không phải** mẫu code nghiệp vụ sản xuất. Khi viết test ở CI, cần timeout và dọn executor có chủ đích để tránh giữ thread khi một assertion thất bại.

## 10. Hậu quả khi vi phạm từng giới hạn

| Mẫu cấu hình | Đúng/sai | Hướng xử lý |
| --- | --- | --- |
| `@Cacheable(cacheNames = "a", sync = true)` | Hợp lệ về ba giới hạn | Kiểm tra provider support và key |
| `@Cacheable(cacheNames = {"a","b"}, sync = true)` | Sai: hai cache | Chọn một cache logic hoặc thiết kế đa tầng bên trong provider |
| `@Cacheable(cacheNames = "a", sync = true, unless = "#result == null")` | Sai: `unless` | Bỏ `unless` hoặc bỏ `sync`; chọn cơ chế khác nếu cần cả hai |
| `@Cacheable(cacheNames = "a", sync = true, condition = "#p0 != null")` | Hợp lệ về ba giới hạn | Method phải xử lý input null khi condition false |
| `@Cacheable(sync = true)` + `@CachePut` trên cùng method | Sai: ghép operation | Tách lệnh đọc và cập nhật |
| `@Cacheable(sync = true)` + `@CacheEvict` trên cùng method | Sai: ghép operation | Đặt eviction ở method cập nhật riêng |
| `@Caching` gom sync cacheable và put | Sai: `@Caching` không đổi quy tắc | Không ghép cache operation đồng bộ |
| Method `find` sync cacheable; method `update` cache put riêng | Hợp lệ về ba giới hạn | Kiểm soát cùng key, transaction và độ mới |

Dù bảng đánh dấu “hợp lệ”, cấu hình vẫn có thể thất bại do các nguyên nhân khác như provider không hỗ trợ, key null, sai cache name, getter SpEL lỗi hoặc không đi qua Spring proxy.

## 11. Những hiểu lầm thường gặp

### 11.1. “sync = true là khóa của cả phương thức”

Không chính xác. Mục tiêu là **phối hợp tính cho cache key** trong phạm vi provider, chứ không tuyên bố một khóa Java `synchronized` bao trùm tất cả lời gọi cho mọi key. Các key độc lập có thể được tính song song; cùng key mới là trường hợp muốn điều phối. Chính sách locking thực tế tùy implementation.

### 11.2. “sync luôn hoạt động như nhau với Redis, Caffeine và ConcurrentMap”

Không. API có thể giống nhau nhưng khóa của từng provider khác nhau; có thể chỉ trong một process hoặc có đặc điểm atomicity khác. Hãy đọc tài liệu tương ứng, viết test với provider đang triển khai và kiểm tra khi có nhiều ứng dụng chạy đồng thời.

### 11.3. “Có sync rồi thì không cần eviction hoặc TTL”

Sai. Sync xử lý **cạnh tranh khi cùng key đang miss**. Nó không bảo đảm dữ liệu có sẵn luôn mới, không quyết định TTL hay xóa cache sau cập nhật. Một kết quả stale đã hit có thể vẫn được trả nếu không có chính sách invalidation.

### 11.4. “Dùng condition để thay thế unless”

Sai nếu quy tắc phụ thuộc `#result`. `condition` đánh giá trước invocation; `unless` đánh giá sau invocation. Bạn chỉ dùng `condition` để quyết định theo input/metadata có sẵn lúc đó, không để lọc kết quả chưa được tính.

### 11.5. “Chỉ một cache nghĩa là cả ứng dụng chỉ có một cache”

Sai. Một `CacheManager` có thể chứa nhiều cache; mỗi method `@Cacheable(sync = true)` chỉ được resolve **một cache** cho operation của nó.

### 11.6. “Không ghép operation nghĩa là không được có @CacheEvict trong ứng dụng”

Sai. Không được ghép các cache operation khác **trên cùng method** có synchronized cacheable. Một method update riêng `@CacheEvict` hoặc `@CachePut` là phương án bình thường và thường được khuyến nghị.

### 11.7. “Có sync thì tất cả lần truy cập cùng key chỉ chạy method một lần mãi mãi”

Sai. Cache có thể hết hạn, bị evict, bị mất sau restart, loader có thể ném exception hoặc hai node không chia sẻ cơ chế phối hợp. `sync = true` không tương đương exactly-once execution cho toàn hệ thống.

## 12. Checklist chọn sync an toàn

1. **Phạm vi:** method có thật sự đọc giá trị có thể cache, không có side effect bắt buộc?
2. **Một cache:** `cacheNames` chỉ một tên; `CacheResolver` nếu có cũng chỉ resolve một cache cho operation.
3. **Không unless:** không đặt `unless` trong annotation sync, kể cả biểu thức luôn false.
4. **Không ghép operation:** không có `@CachePut`, `@CacheEvict` hay thêm cacheable cùng method; `@Caching` không loại trừ quy tắc.
5. **Key:** cùng dữ liệu phải dùng cùng key; key đủ phân biệt tenant, locale, version và quyền khi ảnh hưởng kết quả.
6. **Condition:** nếu có, chỉ dựa dữ liệu có trước invocation; bản thân method vẫn phải xử lý input không hợp lệ khi caching bị bỏ qua.
7. **Provider:** xác định `CacheManager` và `Cache` thật; đọc hướng dẫn `get(key, Callable)`/synchronization của provider.
8. **Concurrency:** test bằng nhiều thread cùng key, có barrier và số lần thực thi body; kiểm tra cả key khác nhau.
9. **Multi-instance:** không mặc định một JVM test chứng minh khóa phân tán.
10. **Độ mới và lỗi:** có TTL/eviction thích hợp, xử lý loader exception, timeout, transaction và tải sau khi cache vừa hết hạn.

## 13. Bài tập tự kiểm tra

**Câu 1.** `@Cacheable(cacheNames = {"a","b"}, sync = true)` sai gì, dù mỗi cache đều hợp lệ khi dùng riêng?  
**Đáp án:** Một synchronized operation chỉ được resolve một cache; dùng hai cache name vi phạm giới hạn.

**Câu 2.** Muốn tránh cache kết quả `null`, có thể thêm `unless = "#result == null"` khi `sync = true` không?  
**Đáp án:** Không. Phải đổi thiết kế, bỏ sync để dùng unless, hoặc xử lý đồng bộ/lọc kết quả bằng cơ chế khác; hỗ trợ null-value còn tùy provider.

**Câu 3.** `@Cacheable(sync = true, condition = "#p0 != null")` có vi phạm ba giới hạn không?  
**Đáp án:** Không, miễn có một cache và không ghép operation/`unless`; khi condition false thì method vẫn chạy trực tiếp và phải xử lý null.

**Câu 4.** Method `find` có sync cacheable, method `update` riêng có cache put vào cùng cache name. Đó có phải “ghép thao tác” không?  
**Đáp án:** Không. Giới hạn không ghép operation áp dụng cho **cùng method invocation**, không cấm các method độc lập cùng sử dụng cache.

**Câu 5.** Hai instance ứng dụng kết nối Redis. Có thể khẳng định `sync = true` khóa toàn hệ thống không?  
**Đáp án:** Không. Cần xem semantics và cấu hình chính xác của provider; muốn chắc chắn có single-flight xuyên instance có thể phải dùng distributed lock hoặc thiết kế riêng.

## Nguồn chính thức

- [Spring Framework — Cacheable JavaDoc (sync và ba giới hạn)](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Cache interface JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/Cache.html)

**Kết luận:** `@Cacheable(sync = true)` là công cụ giảm tải tính toán đồng thời cho **cùng cache key** khi provider hỗ trợ. Đổi lại, Spring yêu cầu **một cache**, **không `unless`** và **không thêm cache operation khác trên cùng phương thức**. Nếu yêu cầu nghiệp vụ xung đột với ba giới hạn này, phải chọn thiết kế khác thay vì tìm cách lách annotation.