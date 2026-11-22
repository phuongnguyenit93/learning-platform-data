# @Cacheable(sync=true) và hợp đồng hỗ trợ của nhà cung cấp trong Spring Cache

## 1. Vấn đề cần giải quyết: nhiều thread cùng cache miss

Khi hệ thống có nhiều request đồng thời, các request có thể cùng tra một key chưa tồn tại trong cache. Nếu cả nhóm đều đọc cache trước khi kết quả đầu tiên được lưu, chúng có thể cùng truy vấn database hoặc gọi API tốn kém. Hiện tượng này thường gọi là **cache stampede** hoặc **thundering herd**.

Ví dụ service bình thường:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) {
    return repository.load(sku);
}
```

Nếu có tám thread cùng gọi `find("P1")` vào lúc key `P1` chưa có, chỉ riêng `@Cacheable` mặc định **không cam kết** phương thức thật sẽ chạy đúng một lần. Cache vẫn giúp các lượt gọi sau lấy dữ liệu nhanh hơn khi entry đã có, nhưng bước tải đầu tiên có thể bị trùng.

Để yêu cầu cache provider phối hợp các lời gọi cùng key, Spring hỗ trợ:

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String sku) {
    return repository.load(sku);
}
```

`sync = true` yêu cầu cơ chế synchronized loading: nếu provider hỗ trợ, một caller có thể chịu trách nhiệm nạp value của key chưa có, còn các caller khác nhận lại giá trị sau khi quá trình nạp hoàn thành.

**Nguyên tắc cốt lõi:** `sync=true` là **gợi ý/hợp đồng được chuyển xuống implementation cache**; mức đồng bộ thật, phạm vi khóa và hành vi khi có lỗi **phụ thuộc provider**. Spring không tự biến mọi cache backend thành khóa phân tán trên nhiều server.

Bài học tập trung vào cách hoạt động, hợp đồng `Cache.get(key, Callable)`, ba giới hạn annotation, kiểm thử provider, ví dụ Java 17 chạy được và những tình huống dễ hiểu sai.

## 2. Luồng xử lý khi không bật và khi bật `sync`

### 2.1. Không bật đồng bộ: get rồi tính rồi put

Với `sync=false` (giá trị mặc định), cơ chế có thể hình dung:

```text
Thread A                        Thread B
   |                               |
   +-- get("P1") -> MISS           +-- get("P1") -> MISS
   |                               |
   +-- load("P1")                   +-- load("P1")
   |                               |
   +-- put("P1", value)             +-- put("P1", value)
   |                               |
   +-- trả value                    +-- trả value
```

Cả hai thread có thể trả kết quả đúng, nhưng đã gọi nguồn hai lần. Khi nguồn rất tốn chi phí hoặc bị giới hạn tần suất, việc tải trùng làm tăng độ trễ và tải hệ thống.

### 2.2. Bật đồng bộ: thao tác lấy hoặc tải theo key

Trong đường đồng bộ, Spring có thể nhờ API của `Cache` làm thao tác lấy-or-tải:

```java
// Pseudocode diễn giải cơ chế, không phải source Spring.
return cache.get(key, () -> invokeTargetMethod());
```

Nếu provider thực hiện nguyên tử cho cùng key:

```text
Caller A                  Caller B                  Caller C
   |                         |                         |
   +-- getOrLoad("P1")       +-- getOrLoad("P1")       +-- getOrLoad("P1")
          |                         |                         |
          +-- MISS, tải nguồn      +-- chờ                  +-- chờ
          |                         |                         |
          +-- ghi value             |                         |
          |                         |                         |
          +-- trả value             +-- nhận value            +-- nhận value
```

Đây là mô hình **single-flight theo key** của một cache provider có hỗ trợ. Nó không có nghĩa toàn bộ method chạy tuần tự cho mọi request: `P1` và `P2` là hai key khác nhau nên có thể được nạp đồng thời. Tên cache khác, cache instance khác hoặc JVM khác có thể có phạm vi đồng bộ riêng.

Việc chọn key rất quan trọng. Nếu key chứa request ID ngẫu nhiên, mỗi request trở thành key khác nhau nên `sync=true` không còn giúp gộp chúng. Nếu key bỏ qua tenant, locale hoặc quyền truy cập trong khi kết quả phụ thuộc các thông tin này, các lời gọi có thể bị gộp nhầm và trả dữ liệu sai.

## 3. Hợp đồng giữa Spring Cache và nhà cung cấp

### 3.1. Điểm giao tiếp: `Cache.get(Object, Callable<T>)`

Spring Cache có các API:

| API | Tác dụng | Liên quan đến đồng bộ |
| --- | --- | --- |
| `get(Object key)` | Tra value/wrapper của key | Không bao gồm cơ chế tải |
| `get(Object key, Class<T> type)` | Lấy value với kiểu mong đợi | Không loại trừ hai thread cùng cache miss |
| `put(key, value)` | Ghi kết quả vào cache | Là thao tác ghi độc lập |
| `get(key, Callable<T> loader)` | Lấy value; nếu thiếu, dùng callback nạp value | API chủ chốt của synchronized caching đồng bộ |
| `retrieve(...)` | Truy xuất theo `CompletableFuture` | Liên quan các phương thức async/reactive; cần kiểm tra riêng |

Chữ ký Java quan trọng:

```java
<T> T get(Object key, java.util.concurrent.Callable<T> valueLoader);
```

Hợp đồng yêu cầu implementation trả về value nếu đã có hoặc gọi `valueLoader` để tạo/lưu kết quả khi chưa có. Javadoc khuyến nghị nếu khả thi, việc nạp **nên được đồng bộ** để callback chỉ được gọi một lần dưới truy cập cạnh tranh cho cùng key.

Đó là điểm khác biệt quan trọng giữa **khuyến nghị có điều kiện của interface** và **bảo đảm kỹ thuật của implementation**. Provider có thể triển khai bằng `computeIfAbsent`, khóa cục bộ, khóa trên remote backend hoặc cách khác. Thậm chí có implementation không bảo đảm gộp loader, nên việc gọi `@Cacheable(sync=true)` không đủ để khẳng định số lần thực thi.

### 3.2. Hợp đồng cần xác minh khi chọn provider

Hãy hỏi các câu cụ thể:

1. `get(key, Callable)` có được triển khai thực sự không, và có đồng bộ loader cho cùng key không?
2. Phạm vi đồng bộ là **một cache object**, một JVM hay toàn cluster?
3. Với nhiều key khác nhau, provider cho phép tải song song hay khóa cả vùng?
4. Khi loader thất bại, callback có được gọi lại ở lượt tiếp theo? Caller khác nhận lỗi gì?
5. Khi một node chết trong lúc tải, node khác có thể tiếp quản hay có nguy cơ chờ lâu?
6. Khi cache entry hết TTL hoặc bị evict trong lúc load, có khả năng ghi đè dữ liệu mới bằng dữ liệu cũ không?
7. Backend hỗ trợ synchronous `get(key, Callable)` có hỗ trợ **asynchronous** `retrieve(key, supplier)` theo hợp đồng cần dùng không?

Ví dụ, `ConcurrentMapCacheManager` thuộc Spring core dùng cache trong JVM và phù hợp kiểm thử concurrent loading trong **một tiến trình**. Điều này không suy ra hai instance của ứng dụng chạy ở hai server sẽ cùng dùng một khóa. Với Redis hoặc cache remote, cần kiểm tra chính xác implementation và phiên bản adapter; việc lưu value ở Redis không tự chứng minh synchronized load trên mọi node.

## 4. Giới hạn của `@Cacheable(sync=true)`

Theo Javadoc `@Cacheable` của Spring Framework, synchronized caching có **ba giới hạn**. Đây không phải khuyến nghị tùy ý mà là hợp đồng cấu hình annotation.

| Giới hạn | Điều cần tránh |
| --- | --- |
| `unless` không được hỗ trợ | Không dùng `unless="#result == null"` cùng `sync=true` |
| Chỉ một cache cho operation | Không chỉ định nhiều tên cache cho một synchronized cacheable |
| Không kết hợp thêm cache operation | Không ghép `@CachePut`/`@CacheEvict`/`@Cacheable` khác trên cùng method synchronized |

### 4.1. `unless` không được hỗ trợ

**Không hợp lệ:**

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true,
    unless = "#result == null"
)
public Product find(String sku) {
    return repository.load(sku);
}
```

`unless` cần quan sát kết quả sau khi method chạy rồi quyết định có ghi hay không. Với synchronized path, Spring giao callback tải và thao tác cache kết hợp cho provider; không thể tùy tiện chèn thêm cơ chế veto kết quả của `unless`.

Khi sản phẩm yêu cầu **không cache null** đồng thời tránh tải trùng, cân nhắc thiết kế value wrapper không-null kèm chiến lược xử lý “không tìm thấy”, hoặc tách cơ chế single-flight ra khỏi annotation caching. Không giả định backend từ chối null sẽ tự bỏ qua việc lưu một cách êm thấm: có backend sẽ ném exception.

### 4.2. Một cache duy nhất

**Không hợp lệ:**

```java
@Cacheable(
    cacheNames = {"productsLocal", "productsShared"},
    key = "#p0",
    sync = true
)
public Product find(String sku) {
    return repository.load(sku);
}
```

Ngay cả nếu `@Cacheable` bình thường cho phép nhiều vùng cache, synchronized loading chỉ hỗ trợ **một vùng** được resolve cho cache operation đó. Khi dùng `CacheResolver` tùy biến, cần chắc chắn resolver trả về đúng một đối tượng `Cache`.

Điều này không có nghĩa phải có đúng một `CacheManager` trong toàn bộ ứng dụng. Có thể có nhiều manager nhưng operation synchronized chỉ nên chọn một cache cuối cùng.

### 4.3. Không ghép operation khác trên cùng method

**Không hợp lệ:**

```java
@Caching(
    cacheable = @Cacheable(cacheNames = "products", sync = true),
    evict = @CacheEvict(cacheNames = "productLists", allEntries = true)
)
public Product find(String sku) {
    return repository.load(sku);
}
```

Hãy đặt thao tác thay đổi dữ liệu, `@CachePut` hoặc `@CacheEvict` trên **method riêng**. Không cố “vừa synchronized-load, vừa evict” trong cùng một method.

**Hợp lệ:**

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String sku) {
    return repository.load(sku);
}
```

`condition` dựa trên tham số là một lựa chọn khác với `unless`. Khi `condition` trả false, caching bị bỏ qua; method vẫn được gọi và không được single-flight thông qua cache cho lần gọi đó.

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null",
    sync = true
)
public Product find(String sku) {
    return repository.load(sku);
}
```

Đoạn này chỉ minh họa cách lọc input. Nó không thay thế validation nghiệp vụ, và method vẫn phải xử lý hợp lệ khi `sku == null`.

## 5. Ví dụ chạy được với Spring Framework 6.2 và Java 17

Ví dụ có 8 thread cùng gọi một SKU khi cache rỗng. Chúng được khởi động với `CountDownLatch` để cùng bắt đầu, rồi so sánh kết quả và bộ đếm nạp thật.

**Mục tiêu:**

- Lượt truy cập đồng thời cùng key `P1` chỉ nạp nguồn một lần với `ConcurrentMapCacheManager` trong một JVM.
- Gọi lại `P1` là hit, không tăng bộ đếm.
- Gọi `P2` có key riêng, phải nạp thêm.
- Evict `P1` rồi gọi lại dẫn đến nạp mới.

**Cấu trúc thư mục:**

```text
sync-cache-demo/
├── pom.xml
└── src/main/java/SyncCacheDemo.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>sync-cache-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tệp `src/main/java/SyncCacheDemo.java`:**

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class SyncCacheDemo {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    ProductService productService() {
        return new ProductService();
    }

    public static class ProductService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0", sync = true)
        public String find(String sku) {
            int loadId = loads.incrementAndGet();
            try {
                Thread.sleep(120);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Interrupted during load", e);
            }
            return sku + "#load" + loadId;
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void evict(String sku) {
            // Spring caching interceptor xóa entry sau method.
        }

        public int loads() {
            return loads.get();
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(SyncCacheDemo.class)) {
            ProductService service = context.getBean(ProductService.class);

            int callers = 8;
            ExecutorService pool = Executors.newFixedThreadPool(callers);
            CountDownLatch ready = new CountDownLatch(callers);
            CountDownLatch start = new CountDownLatch(1);

            try {
                List<Future<String>> futures = new ArrayList<>();

                for (int i = 0; i < callers; i++) {
                    Callable<String> task = () -> {
                        ready.countDown();
                        start.await();
                        return service.find("P1");
                    };
                    futures.add(pool.submit(task));
                }

                ready.await();
                start.countDown();

                Set<String> distinct = new HashSet<>();
                for (Future<String> f : futures) {
                    distinct.add(f.get());
                }

                System.out.println("distinct same-key results: "
                        + distinct.size());
                System.out.println("same-key value: "
                        + distinct.iterator().next());
                System.out.println("loads after 8 callers: "
                        + service.loads());

                System.out.println("repeat P1: " + service.find("P1"));
                System.out.println("loads after repeat: "
                        + service.loads());

                System.out.println("different P2: " + service.find("P2"));
                System.out.println("loads after P2: " + service.loads());

                service.evict("P1");
                System.out.println("P1 after evict: " + service.find("P1"));
                System.out.println("loads final: " + service.loads());
            } finally {
                start.countDown();
                pool.shutdownNow();
            }
        }
    }
}
```

**Chạy bằng Maven với JDK 17+:**

```bash
mvn -q compile exec:java -Dexec.mainClass=SyncCacheDemo
```

**Các dòng do chương trình in ra** (không tính log Maven/Spring nếu có):

```text
distinct same-key results: 1
same-key value: P1#load1
loads after 8 callers: 1
repeat P1: P1#load1
loads after repeat: 1
different P2: P2#load2
loads after P2: 2
P1 after evict: P1#load3
loads final: 3
```

### 5.1. Vì sao có thể tin kết quả trong ví dụ này?

`ready` giúp đảm bảo tám task sẵn sàng trước khi mở latch `start`. `Thread.sleep(120)` kéo dài việc nạp để dễ quan sát truy cập trùng. Kết quả và `AtomicInteger` thể hiện số lần phương thức nguồn thực sự chạy.

`ProductService` là Spring bean, `@EnableCaching` đã bật và `main` gọi thông qua bean lấy từ context; tránh lỗi **self-invocation** trong proxy mode. `ConcurrentMapCacheManager` tạo vùng `products` cục bộ. Cơ chế `ConcurrentMapCache` hỗ trợ synchronized loading theo key trong JVM của ví dụ.

Vì giá trị nạp đầu tiên là `"P1#load1"`, các `Future` nhận cùng kết quả; tập hợp `distinct` chỉ có một phần tử. Gọi lại `P1` là hit nên số lần nạp giữ nguyên ở 1; `P2` là key mới nên bộ đếm tăng thành 2. `evict("P1")` xóa đúng entry trong method riêng, lần nạp kế tiếp tăng thành 3.

Điểm giới hạn: kết quả này **không** chứng minh khả năng đồng bộ nhiều JVM. Những hệ thống cùng chia sẻ một Redis backend vẫn có thể thực hiện nhiều lần tải đồng thời ở các instance nếu adapter không có khóa phân tán.

## 6. Phạm vi hỗ trợ của cache provider

Spring Framework mô tả `sync` là tính năng tùy chọn theo provider; các `CacheManager` thuộc core Spring được tài liệu mô tả là hỗ trợ cơ chế này. Không nên đánh đồng “provider hỗ trợ phương thức gọi” với “provider có single-flight trên mọi node”.

| Nhóm triển khai | Có thể suy ra | Cần xác nhận |
| --- | --- | --- |
| `ConcurrentMapCacheManager` | Hỗ trợ synchronized load trong cache local JVM | Không có khóa cluster; lifecycle không chia sẻ giữa instance |
| `CaffeineCacheManager` | Provider có khả năng quản lý nạp đồng thời theo cơ chế riêng | Hợp đồng sync mode, expiry/refresh, cấu hình async mode |
| Redis/remote cache | Dữ liệu có thể chia sẻ qua network | `get(key, Callable)` có khóa phân tán hay chỉ khóa local? |
| Custom `Cache` adapter | Có thể cài đặt API theo ý tác giả | Bắt buộc đọc implementation và stress test |
| `NoOpCache` | Không giữ entry giữa các lượt gọi | Không mong đợi giảm tải lâu dài bằng caching |

**Quy tắc thiết kế:** trước khi bật `sync=true` trong production, kiểm tra API `Cache.get(key, Callable)` của provider và test với đúng bản build, cấu hình, backend, số node đang chạy. Nếu provider ném exception do không hỗ trợ hoặc không khóa loader, phải giải quyết bằng cấu hình/provider phù hợp; Spring không tự tạo một mutex toàn cục.

Trong một số implementation, đồng bộ theo key có thể bị mở rộng thành khóa cả vùng, làm các key khác nhau cùng chờ nhau. Vì vậy test không chỉ “một key nhiều thread”, mà cả “nhiều key cùng lúc” để đo thông lượng.

## 7. Những vấn đề `sync=true` không giải quyết

### 7.1. Load–update race và dữ liệu cũ

`sync=true` điều phối các loader trên cache miss, nhưng không tự đồng bộ hóa thao tác ghi database/`@CacheEvict`. Ví dụ race:

```text
T1: miss -> bắt đầu tải Product P1 phiên bản cũ
T2: cập nhật P1 thành phiên bản mới, evict P1
T1: tải xong và put giá trị cũ vào cache
T3: hit -> nhận dữ liệu cũ
```

Đây là vấn đề thứ tự cập nhật/invalidation, không phải chỉ của loader duplication. Có thể cần versioning, invalidation sau commit, điều phối giao dịch hoặc chiến lược cache có bảo đảm consistency phù hợp.

### 7.2. Không phải khóa toàn bộ service

`sync=true` không biến các method khác của service thành synchronized method, không tạo transaction giữa cache và DB, không tự serialize `@CachePut`/`@CacheEvict`, không bảo đảm fairness và không đóng vai trò distributed lock đa node.

### 7.3. Cache hit bỏ qua method body

Khi cache hit, `@Cacheable` không chạy thân method. Nếu method có side effect bắt buộc như gửi event, tính phí, ghi audit theo request, chúng có thể không xảy ra cho cache hit. Đừng đặt side effect thiết yếu trong method cacheable; `sync=true` không thay đổi nguyên tắc này.

### 7.4. Key phải ổn định và phân biệt đúng dữ liệu

Không nên đưa biến động ngẫu nhiên như trace ID vào key nếu nó không ảnh hưởng kết quả: mỗi request sẽ thành key riêng. Ngược lại, nếu giá phụ thuộc SKU + currency + tenant, chọn key chỉ có SKU là sai, có nguy cơ trả giá của tenant khác. Đảm bảo cache key phù hợp ngữ nghĩa nghiệp vụ trước khi tối ưu đồng thời.

## 8. Null, Optional, exception và chịu lỗi

Với `@Cacheable(sync=true)`, không thể dùng `unless = "#result == null"` để chặn việc lưu null. Hành vi khi loader trả null phụ thuộc provider:

- Provider cho phép cached-null có thể lưu trạng thái null, nên các lượt gọi sau không chạy nguồn.
- Provider không cho phép null có thể ném lỗi trong đường callback.
- `Optional.empty()` được Spring xử lý theo hợp đồng unwrap wrapper hỗ trợ; cần test provider và kiểu trả về thực tế.
- Nếu nghiệp vụ không muốn cache “chưa tìm thấy”, có thể bỏ `sync=true` và dùng `unless`, hoặc thiết kế value wrapper/chiến lược negative caching có TTL, invalidation minh bạch.

Khi loader ném exception, API `Cache.get(key, Callable)` có thể bọc nguyên nhân trong `Cache.ValueRetrievalException`. Cần test exception propagate thế nào qua interceptor, cấu hình lỗi và provider. Khi cache backend lỗi, đường combined get-or-load của `sync=true` không giống đường get rồi put của `sync=false`; một số chính sách `CacheErrorHandler` có thể không cho hành vi fallback tương đương.

`sync=true` cũng không thay thế retry với backoff, timeout, circuit breaker, bulkhead và giới hạn tải vào database. Khi nguồn down, các đợt retry nhiều caller có thể gây stampede ngay sau lần tải thất bại.

## 9. CompletableFuture và các kiểu reactive

Spring Framework 6.1+ tích hợp cache annotation với `CompletableFuture` và một số reactive return types. Chữ ký minh họa:

```java
@Cacheable(cacheNames = "productFutures", key = "#p0", sync = true)
public java.util.concurrent.CompletableFuture<Product> findAsync(String sku) {
    return java.util.concurrent.CompletableFuture.supplyAsync(
            () -> repository.load(sku));
}
```

Đây chỉ là mảnh minh họa, không phải một phần của `SyncCacheDemo.java` độc lập ở mục 5.

Đối với synchronized caching async, provider cần hỗ trợ retrieval kiểu `CompletableFuture`, không chỉ `get(key, Callable)` đồng bộ. Tài liệu Spring mô tả `ConcurrentMapCacheManager` có cách thích ứng bất đồng bộ; `CaffeineCacheManager` hỗ trợ async cache mode khi cấu hình `setAsyncCacheMode(true)`. Với Reactor `Mono`/`Flux`, cơ chế cache của abstraction thu thập kết quả tương ứng, không phải cơ chế backpressure/stream orchestration chuyên dụng.

Khi dùng reactive hoặc future, hãy kiểm tra provider có khả năng hoàn thành `retrieve(key, supplier)` phù hợp hay không, và test concurrency trên chính kiểu trả về đó.

## 10. Kiểm thử hợp đồng đồng thời trong thực tế

| Tình huống | Kỳ vọng cần đo |
| --- | --- |
| 8–20 thread cùng key chưa có | Số lần loader thực thi, số kết quả khác nhau |
| Cùng key sau khi nạp xong | Cache hit, loader không tăng |
| Hai key khác nhau | Có thể tải độc lập; không dùng chung value |
| Evict rồi gọi lại | Loader chạy lại |
| Cache entry hết TTL | Bao nhiêu loader sau expiry? |
| Loader ném exception | Caller nhận lỗi nào? Có kẹt khóa không? |
| Provider lỗi/mất mạng | Có fail fast, retry, hay fallback? |
| Nhiều JVM cùng key | Có single-flight toàn cluster thật không? |
| Loader chạy cùng lúc update DB | Có ghi đè kết quả mới bằng stale value không? |
| Null/`Optional.empty()` | Có cache null, từ chối hay lỗi? |
| Không đi qua Spring proxy | Method chạy lại; annotation có thực sự áp dụng? |

Cần đo **số lần gọi nguồn**, không chỉ so sánh kết quả trả về. Nếu cả 20 thread cùng trả chuỗi `"P1"`, có thể cả 20 đã nạp cùng chuỗi. Test hiệu quả đồng bộ phải có bộ đếm, log hoặc metric ở lớp repository/API.

Theo dõi số request chờ, độ trễ cache hit/miss, độ trễ loader, timeout, lỗi provider, tỉ lệ evict/expiry và lượng traffic đỉnh. Không dùng raw key nhạy cảm làm label metric vì rủi ro lộ thông tin và cardinality quá cao.

### Quy trình nghiệm thu khi đổi provider

1. Xác định manager và cache instance thực sự được operation resolve.
2. Đọc documentation/implementation `get(key, Callable)`, không chỉ tên cache provider.
3. Test một JVM với nhiều thread cùng key và nhiều key khác nhau.
4. Nếu triển khai cluster, chạy cùng test trên ít nhất hai instance.
5. Test null, lỗi nguồn, lỗi backend, TTL/eviction và load–update race.
6. Định nghĩa đường fallback và hành vi khi timeout.
7. Chạy lại test sau khi nâng phiên bản provider hoặc đổi cấu hình async/sync.

## 11. Các lỗi phổ biến

1. **Nghĩ rằng `sync=true` luôn khóa toàn cluster.** Không có bảo đảm đó trong hợp đồng annotation.
2. **Bỏ qua API provider.** Nếu `get(key, Callable)` không đồng bộ thực sự, annotation không tạo single-flight mong đợi.
3. **Kết hợp `unless`.** `@Cacheable(sync=true, unless="...")` không được hỗ trợ.
4. **Đưa nhiều cache names vào synchronized operation.** Vi phạm giới hạn một cache.
5. **Ghép `@CachePut` hoặc `@CacheEvict` cùng method.** Không tương thích với synchronized cacheable.
6. **Đặt key theo request ID.** Không thể gộp những request thực sự truy vấn cùng dữ liệu.
7. **Bỏ tenant hoặc yếu tố phân quyền khỏi key.** Có nguy cơ chia sẻ dữ liệu sai.
8. **Test bằng self-invocation.** `this.find(...)` trong cùng bean có thể bỏ qua Spring proxy và cơ chế cache.
9. **Thấy cùng kết quả rồi khẳng định chỉ có một loader.** Kết quả giống nhau chưa nói số lần gọi nguồn.
10. **Tin rằng sync bảo đảm dữ liệu mới khi update.** Race giữa load và cập nhật vẫn cần giải quyết.
11. **Không có timeout và error policy.** Một loader chậm có thể làm nhiều caller chờ.
12. **Lấy kết quả method đồng bộ để suy ra async support.** Hai nhánh retrieval khác nhau cần kiểm tra.
13. **Nghĩ rằng sync làm lần tải đầu tiên nhanh hơn.** Lợi ích chính là giảm tải trùng, không giảm thời gian chạy loader đơn lẻ.
14. **Không kiểm tra cache của từng môi trường.** Provider có thể dùng local lock ở dev nhưng khác hành vi khi chạy nhiều node.

## 12. Tóm tắt áp dụng

Cách khai báo ngắn gọn:

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String sku) {
    return repository.load(sku);
}
```

Ba câu hỏi phải trả lời trước khi dùng production:

1. Key có mô tả đúng kết quả để các request cùng dữ liệu được gộp, nhưng khác tenant/filter/quyền không bị gộp nhầm?
2. Provider có thật sự bảo đảm synchronized loading qua `Cache.get(key, Callable)` ở phạm vi cần thiết, một JVM hay toàn cluster?
3. Có test các giới hạn `unless`/một cache/không ghép operation, đồng thời xử lý lỗi, null, invalidation và tải đồng thời với cập nhật chưa?

**Kết luận:** `sync=true` có thể giúp giảm cache stampede theo key **khi provider hỗ trợ**. Nó không phải distributed mutex, không thay thế nhất quán dữ liệu và không tự giải quyết lỗi hoặc race giữa read và write.

## Tài liệu chính thức

- Spring Framework 6.2 — Synchronized Caching: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework 6.2 — `@Cacheable` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework 6.2 — `Cache.get(key, Callable)` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework 6.2 — `ConcurrentMapCache` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework — Async/Reactive Cache Annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
