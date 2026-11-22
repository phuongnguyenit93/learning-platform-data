# Phạm vi đồng bộ trong một tiến trình so với nhiều máy với Spring Cache

## Mục tiêu học tập

Trong hệ thống có nhiều request đồng thời, hai hoặc nhiều thread có thể cùng gặp **cache miss** và cùng chạy một tác vụ tốn kém. Spring cung cấp `@Cacheable(sync = true)` để đề nghị cache provider phối hợp các lời gọi cho cùng key. Tuy nhiên, một khóa hoặc bộ nhớ cache **cục bộ JVM** không tự biến thành cơ chế đồng bộ giữa nhiều máy, container hay replica.

Sau bài này, bạn sẽ có thể:

1. Phân biệt đồng thời trong một thread, nhiều thread cùng JVM và nhiều tiến trình/máy.
2. Giải thích cache stampede, cache-aside, điều kiện cạnh tranh và ý nghĩa thật của `@Cacheable(sync = true)`.
3. Phân biệt **cùng cache data store** với **cùng cơ chế khóa phân tán**.
4. Viết, chạy và kiểm thử ví dụ Java 17 + Spring Boot cho các lời gọi cùng key trong một JVM.
5. Đánh giá Redis, Caffeine, `ConcurrentMapCacheManager` và khả năng đồng bộ phụ thuộc provider.
6. Chọn chiến lược thực tế: local single-flight, distributed coordination, expiration jitter, stale-while-revalidate hoặc thiết kế chấp nhận tính lại.
7. Nhận diện race về hết hạn khóa, lỗi tiến trình, dữ liệu stale, transaction và những giới hạn của tuyên bố "chỉ tính một lần".

**Nguyên tắc cốt lõi:** `sync=true` là một *gợi ý* dành cho cache implementation, **không phải hợp đồng bảo đảm exactly-once toàn cụm**. Luôn xác định ranh giới nơi các bên thực sự chia sẻ trạng thái đồng bộ.

## 1. Vấn đề bắt đầu từ cache miss đồng thời

Giả sử dịch vụ có phương thức tính báo cáo:

~~~java
// Minh họa trên một Spring-managed service.
@Cacheable(cacheNames = "reports", key = "#p0")
public Report generate(String reportId) {
    return expensiveCalculation(reportId);
}
~~~

Khi cache đã có `reportId="R1"`, nhiều request có thể nhanh chóng lấy cùng giá trị. Nhưng khi cache vừa khởi động, bị xóa hoặc entry vừa hết hạn, một nhóm request cùng thấy miss.

~~~text
10:00:00.000  Thread A: GET reports/R1 -> MISS
10:00:00.001  Thread B: GET reports/R1 -> MISS
10:00:00.002  Thread C: GET reports/R1 -> MISS

Thread A -> generate(R1) -> DB/CPU
Thread B -> generate(R1) -> DB/CPU
Thread C -> generate(R1) -> DB/CPU

A/B/C đều có thể tính cùng một báo cáo, rồi put cùng key.
~~~

Hiện tượng nhiều request cùng tái tạo một giá trị hết hạn được gọi là **cache stampede**, cũng thường được gọi là *dogpile effect*. Nếu việc tạo giá trị mất vài giây hoặc làm nhiều truy vấn DB, backend có thể tăng tải đột biến đúng lúc cache lẽ ra phải giảm tải.

Một cách mô hình hóa:

~~~text
N request đồng thời, cache miss cùng một key
       |
       +-- Không phối hợp: có thể N lần chạy loader
       |
       +-- Có single-flight đúng phạm vi: 1 lần loader,
                                      N-1 lời gọi đợi rồi dùng kết quả
~~~

"Single-flight" là ý tưởng gộp các lời gọi đang diễn ra cho **cùng key** để chỉ một lời gọi tính; các lời gọi còn lại dùng kết quả. Nó khác với việc khóa toàn bộ cache: hai key độc lập như `R1` và `R2` lý tưởng vẫn có thể được tính song song.

## 2. Ba ranh giới đồng thời phải phân biệt

| Phạm vi | Các bên chia sẻ gì? | Khóa cục bộ có tác dụng tới đâu? |
| --- | --- | --- |
| Một thread | Stack và luồng điều khiển hiện tại | Thông thường không cần khóa để chống tranh chấp với chính nó |
| Nhiều thread trong **một JVM/application context** | Heap, cache object, Java monitor/lock | Có thể phối hợp nếu cùng cache instance và cùng key |
| Nhiều **JVM/process/container/máy** | Không chia sẻ Java heap/monitor; có thể cùng dùng DB/Redis | Khóa Java ở tiến trình A không chặn loader ở tiến trình B |

Đừng đánh đồng "hai request trên cùng một máy" với "cùng tiến trình": một máy có thể chạy nhiều JVM riêng biệt. Ngược lại, hai thread xử lý hai request trong **cùng** JVM có thể cùng truy cập một đối tượng cache.

### Hình dung hai replica

~~~text
                        Load balancer
                           /      \
                          v        v
                    App A (JVM)  App B (JVM)
                       |            |
                 Local cache A  Local cache B
                       |            |
                       +----- DB ---+
~~~

Giả sử cả hai local cache chưa có `R1`. `@Cacheable(sync=true)` trên App A có thể khiến các thread **trong App A** phối hợp; App B cũng có một nhóm thread phối hợp độc lập. Kết quả vẫn có thể là **hai lần** gọi `expensiveCalculation("R1")` tới DB, một lần cho mỗi tiến trình.

Không có một Java monitor hoặc biến `static` nào tự chạy xuyên qua hai JVM. Hai host thậm chí có thể dùng cùng source code và cùng tên bean/cache nhưng đó vẫn là những đối tượng riêng.

## 3. `@Cacheable(sync = true)` hoạt động ra sao?

Trong Spring Cache, thông thường `@Cacheable` tra cứu key trước. Khi `sync=false` (mặc định), trên miss nhiều caller có thể đều đi vào thân method, rồi put kết quả.

~~~java
@Cacheable(cacheNames = "reports", key = "#p0", sync = true)
public Report generate(String reportId) {
    return expensiveCalculation(reportId);
}
~~~

Với `sync=true`, Spring yêu cầu cache provider thực hiện thao tác kết hợp **lấy hoặc tính giá trị** thông qua contract kiểu `Cache.get(key, Callable)`. Nếu provider hỗ trợ việc phối hợp, chỉ một thread cho cùng key trên **phạm vi provider đang điều phối** chạy loader, còn các thread khác đợi và dùng kết quả được ghi.

~~~text
Thread A: getOrLoad(R1) -> MISS -> acquire/load R1
                                -> generate(R1)
                                -> store R1
Thread B: getOrLoad(R1) -> wait/read R1 -> same result
Thread C: getOrLoad(R1) -> wait/read R1 -> same result
~~~

**Đọc chính xác về semantics:**

- `sync=true` là **hint** cho provider. Tài liệu Javadoc nêu rõ nhà cung cấp cache có thể không hỗ trợ đồng bộ theo cách được kỳ vọng.
- Bản thân annotation không phân biệt "một máy" hay "nhiều máy"; phạm vi phụ thuộc implementation và topology của backend.
- Các `CacheManager` thuộc core Spring Framework hỗ trợ chế độ synchronized caching theo hợp đồng của chúng; điều đó không có nghĩa các cache instance của chúng liên thông giữa JVM.
- Các lời gọi phải thực sự dùng **cùng `cacheName`, cùng key, cùng cache instance/coordination domain**. Key khác nhau hoặc cache manager khác nhau không phối hợp.
- `sync=true` không thay thế transaction, không loại bỏ race đọc/ghi giữa các loại operation và không chứng minh exactly-once khi có lỗi hoặc retry.

### Các hạn chế của `sync=true`

Theo hợp đồng `@Cacheable`:

1. Không hỗ trợ kết hợp với `unless` (veto kết quả sau khi gọi method).
2. Chỉ được chỉ định **một cache** cho synchronized operation.
3. Không kết hợp operation cache khác trên cùng method với operation synchronized đó.

~~~java
// Không hợp lệ: synchronized caching không hỗ trợ unless.
@Cacheable(
        cacheNames = "reports",
        key = "#p0",
        sync = true,
        unless = "#result == null"
)
public Report generate(String id) {
    return expensiveCalculation(id);
}
~~~

Nếu cần **vừa gộp các lời gọi cùng key, vừa bỏ lưu một số kết quả**, hãy thiết kế chiến lược khác (ví dụ single-flight ở service, loader/provider tùy biến với chính sách kết quả); đừng chỉ gắn cả `sync` và `unless` lên annotation rồi trông đợi Spring tự xử lý.

Một điểm khác biệt khi xử lý lỗi cache: `sync=true` dùng callback kết hợp để load qua provider; nếu thao tác đó lỗi, không còn một pha `put` độc lập để thử lại theo đúng cách `sync=false` có thể thực hiện. Chính sách `CacheErrorHandler` và fail-open cần kiểm thử trên provider thực tế.

## 4. Khóa cục bộ JVM: đủ cho vấn đề nào?

Các primitive như `synchronized`, `ReentrantLock`, `ConcurrentHashMap.computeIfAbsent` hoặc cơ chế single-flight trong một bean đều chỉ phối hợp trong **không gian bộ nhớ của JVM đó**.

~~~java
// Đoạn minh họa Java thuần, không phải một cache provider hoàn chỉnh.
private final java.util.concurrent.ConcurrentMap<String, Object> locks =
        new java.util.concurrent.ConcurrentHashMap<>();

public Object localLockFor(String key) {
    return locks.computeIfAbsent(key, unused -> new Object());
}
~~~

Một monitor lấy từ `localLockFor("R1")` chỉ có nghĩa với các thread dùng **cùng** map `locks`. Một tiến trình khác có map khác, nên cùng chuỗi `"R1"` không tạo thành khóa chung. Đoạn minh họa cũng có vấn đề vòng đời: map khóa có thể lớn mãi nếu không có cleanup an toàn; không nên sao chép nó thành giải pháp production mà không xử lý memory/eviction.

Nếu dùng `synchronized` trực tiếp trên method:

~~~java
public synchronized Report generate(String id) {
    return expensiveCalculation(id);
}
~~~

thì mọi lời gọi vào **cùng object instance** phải chờ nhau, kể cả `R1` và `R2` có thể tính độc lập. Đây có thể là nút cổ chai. Nếu method được gọi trên nhiều service instance/JVM thì khóa monitor cũng độc lập. `synchronized` không tự giúp cache hit và không giải quyết phân tán.

### Khi local single-flight đã đủ

Nó phù hợp khi:

- Ứng dụng chỉ có một instance.
- Mỗi replica có cache local, bạn chấp nhận tối đa một lần tính **mỗi replica** trên miss.
- Loader không quá đắt; lặp vài lần khi có nhiều replica vẫn trong ngân sách tài nguyên.
- Cần giảm tranh chấp trong quá trình warm-up, không cần một bảo đảm toàn cụm.

Nếu có 8 replica với cache local, đồng bộ tốt bên trong từng replica vẫn có thể dẫn đến **tối đa khoảng 8 loader** đồng thời cho cùng key vào lúc cả tám đều miss. Con số thực phụ thuộc traffic, tải và timing, không phải một hằng số chắc chắn.

## 5. Ví dụ Java 17 chạy được: nhiều thread, một cache instance

Ví dụ này sử dụng **Spring Boot 3.3.5, Java 17, Maven**, `@EnableCaching` và `ConcurrentMapCacheManager`. Tám task cùng chờ một `CountDownLatch` rồi đồng thời gọi bean service với **cùng key `"X"`**. Với manager in-memory này và `sync=true`, chúng nhận một giá trị, trong khi loader chạy một lần trong cùng application context.

Để minh họa sự cô lập, chương trình tạo thêm **một `ConcurrentMapCacheManager` khác** và kiểm tra nó không nhìn thấy mục của manager đầu tiên. Đây là **hai manager trong cùng JVM** dùng để minh họa sự độc lập bộ nhớ; đó không phải bài test hai máy. Hai máy còn tách biệt mạnh hơn, trừ khi dùng backend/coordination chung.

### Cấu trúc dự án

~~~text
cache-sync-scope-demo/
├── pom.xml
└── src/main/java/example/sync/
    ├── DemoApplication.java
    └── ExpensiveService.java
~~~

### `pom.xml`

~~~xml
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
    <artifactId>cache-sync-scope-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
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
~~~

### `src/main/java/example/sync/ExpensiveService.java`

~~~java
package example.sync;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ExpensiveService {
    private final AtomicInteger loads = new AtomicInteger();

    @Cacheable(cacheNames = "expensive", key = "#p0", sync = true)
    public String load(String id) {
        int generation = loads.incrementAndGet();
        try {
            Thread.sleep(150);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Loader interrupted", interrupted);
        }
        return "value:" + id + ":load#" + generation;
    }

    public int loadCount() {
        return loads.get();
    }
}
~~~

`Thread.sleep(150)` chỉ tạo một chút độ trễ có thể quan sát; đây không phải công thức bảo đảm tranh chấp. Kết quả demo không phụ thuộc các task bắt đầu đúng cùng một nano giây: nếu task đến sau khi entry đã có, chúng vẫn hit cùng giá trị.

### `src/main/java/example/sync/DemoApplication.java`

~~~java
package example.sync;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("expensive");
    }

    @Bean
    CommandLineRunner demo(ExpensiveService service) {
        return args -> {
            ExecutorService workers = Executors.newFixedThreadPool(8);
            CountDownLatch start = new CountDownLatch(1);

            try {
                List<Future<String>> futures = new ArrayList<>();
                for (int i = 0; i < 8; i++) {
                    futures.add(workers.submit(() -> {
                        start.await();
                        return service.load("X");
                    }));
                }

                start.countDown();
                Set<String> uniqueValues = new HashSet<>();
                for (Future<String> future : futures) {
                    uniqueValues.add(future.get());
                }

                System.out.println("unique-results-X=" + uniqueValues.size());
                System.out.println("loads-after-X=" + service.loadCount());
                System.out.println("X-hit=" + service.load("X"));
                System.out.println("loads-after-hit=" + service.loadCount());

                System.out.println("Y-first=" + service.load("Y"));
                System.out.println("loads-after-Y=" + service.loadCount());

                CacheManager independent =
                        new ConcurrentMapCacheManager("expensive");
                boolean otherHasX =
                        independent.getCache("expensive").get("X") != null;
                System.out.println("independent-manager-has-X=" + otherHasX);
            } finally {
                workers.shutdownNow();
            }
        };
    }
}
~~~

### Chạy

Tại thư mục `cache-sync-scope-demo`, cài JDK 17+ và Maven rồi chạy:

~~~bash
mvn -q spring-boot:run
~~~

Ngoài log khởi động Spring, các dòng in từ `CommandLineRunner` có nội dung chính xác như sau trong demo:

~~~text
unique-results-X=1
loads-after-X=1
X-hit=value:X:load#1
loads-after-hit=1
Y-first=value:Y:load#2
loads-after-Y=2
independent-manager-has-X=false
~~~

Giải thích:

1. Tám task gọi `service.load("X")` thông qua Spring-managed bean. `sync=true` phối hợp việc lấy hoặc tính cùng key `"X"` trên cache instance hiện tại; chỉ một lần method thật sự chạy, nên `loads-after-X=1`.
2. Mọi task nhận giá trị `value:X:load#1`, vì thế tập kết quả có kích thước `1`.
3. Lần gọi lại `"X"` hit: bộ đếm không đổi.
4. `"Y"` là key khác, chưa được cache; loader chạy lần thứ hai và trả `value:Y:load#2`.
5. `independent` là một manager **khác**, tuy cũng có cache tên `"expensive"` nhưng chưa hề lưu `"X"`. Nó không tự thấy entry của manager dùng trong ứng dụng. Điều này cho thấy "cùng cache name" **không đồng nghĩa chia sẻ cache instance**.

Nếu chạy ứng dụng tương tự trong hai process JVM tách biệt, mỗi process có một cache in-memory và một `AtomicInteger` riêng. Kể cả code và cache name giống nhau, mỗi process đều có thể tính `"X"` một lần. Demo này **chỉ kiểm chứng local coordination**; nó không tuyên bố đã đo cross-machine synchronization.

### Tại sao ví dụ không gọi `this.load("X")`?

Spring Cache trong proxy mode mặc định intercept lời gọi đi qua proxy. Khi cùng bean gọi `this.load("X")`, lời gọi nội bộ thường bỏ qua cache advice; `@Cacheable(sync=true)` có thể không có hiệu lực. `CommandLineRunner` nhận `ExpensiveService` dưới dạng Spring bean, nên đi qua cơ chế proxy.

Không dùng ví dụ này để khẳng định mọi provider đều có cùng hành vi. Phải chạy lại test trên provider và cấu hình triển khai thực tế.

## 6. Một kho Redis chung có bảo đảm chỉ một loader toàn cụm không?

**Không nhất thiết.** Redis dùng chung cho phép App A và App B đọc/ghi **cùng dữ liệu cache**. Nhưng việc chia sẻ storage không mặc nhiên tạo thành một cơ chế khóa bảo vệ toàn bộ đoạn:

~~~text
read cache -> nếu miss thì chạy tác vụ chậm -> put cache
~~~

Hai tiến trình có thể cùng đọc miss **trước khi** một bên ghi, sau đó cùng tính. Ngay cả khi kết quả cuối cùng chỉ là một Redis entry, số lần đánh DB/CPU có thể vẫn là hai.

~~~text
App A                   Redis                    App B
  | GET R1 -------------->|<-------------- GET R1 |
  |<--- MISS ------------ | ------------ MISS --->|
  | compute R1            |            compute R1 |
  | SET R1 -------------->|<-------------- SET R1 |
~~~

Hình trên minh họa tình huống không có coordination đủ mạnh. `@Cacheable(sync=true)` yêu cầu hành vi load qua provider, nhưng hiệu lực **toàn cụm** phải được xác minh từ cache implementation, writer/loader path và cách triển khai. Đừng suy ra chỉ từ việc cấu hình `RedisCacheManager`.

### Spring Data Redis: locking và non-locking writer

Theo tài liệu Spring Data Redis, `RedisCacheManager` thường dùng **non-locking `RedisCacheWriter` theo mặc định**. Lựa chọn này giảm độ trễ/round-trip nhưng một số thao tác có thể không nguyên tử xuyên nhiều Redis command. Spring Data Redis cũng có **locking writer** có thể dùng explicit lock key để tránh chồng lấn một số thao tác.

Một chi tiết đặc biệt quan trọng: cơ chế locking writer trong tài liệu được mô tả ở **mức cache**, không phải mỗi entry. Điều đó có thể gây chờ rộng hơn một key đơn lẻ và thêm chi phí request. Ngoài ra, các phiên bản API và provider có ngữ nghĩa khác nhau với value loader; không nên tuyên bố bật locking writer là chắc chắn đạt single-flight tuyệt đối cho mọi phương thức và mọi phiên bản.

Đây là **minh họa API cấu hình Redis**, không phải chương trình chạy độc lập:

~~~java
// Trong lớp @Configuration có RedisConnectionFactory và các import phù hợp.
@Bean
RedisCacheManager redisCacheManager(
        RedisConnectionFactory connectionFactory) {
    return RedisCacheManager
            .builder(RedisCacheWriter.lockingRedisCacheWriter(connectionFactory))
            .cacheDefaults(RedisCacheConfiguration.defaultCacheConfig())
            .build();
}
~~~

Trước khi áp dụng cần kiểm tra tương thích phiên bản Spring Data Redis, semantics của `RedisCache.get(key, Callable)` trong backend ấy, mức contention giữa các key, chi phí locking, expiry, failure recovery và timeout. Việc bật locking trên mọi cache có thể giảm throughput không cần thiết.

**Kết luận thực hành:** Redis có thể là **shared cache storage**, nhưng chỉ được gọi là giải pháp **phối hợp loader xuyên JVM** sau khi đã xác minh và kiểm thử đúng code path, cấu hình writer và topology đang chạy.

## 7. Ba chiến lược khi có nhiều máy

### A. Chấp nhận mỗi replica tính một lần

Đây là lựa chọn hợp lý nếu phép tính không quá đắt, số replica nhỏ và không yêu cầu phối hợp chính xác toàn cụm.

~~~text
Replica A: local single-flight cho R1 -> 1 phép tính
Replica B: local single-flight cho R1 -> 1 phép tính
Replica C: local single-flight cho R1 -> 1 phép tính
~~~

Ưu điểm: đơn giản, không cần distributed lock, ít điểm lỗi mới. Nhược điểm: số lần tính có thể tăng theo số replica và các đợt miss. Nếu dùng shared Redis, một lần put của A có thể giúp các request đến sau ở B hit; nhưng **hai request đang miss đồng thời** vẫn có thể cùng load.

### B. Dùng cơ chế phối hợp phân tán cho cùng key

Khi tác vụ rất đắt hoặc DB không chịu nổi stampede, bạn có thể thiết kế một điều phối chung:

~~~text
App A/B/C request R1
       |
       v
Shared cache GET R1
       |
    HIT? -- yes --> return
       |
       no
       v
Acquire coordination for "R1" in shared system
       |                         |
    Owner                      Not owner
       |                         |
  Recheck cache             Wait/poll with limits
       |                         |
  Compute once               Retry cache read
       |
  Put result
       |
  Release ownership safely
~~~

Với khóa phân tán, chỉ gọi `SETNX lock:R1` rồi `DEL lock:R1` một cách ngây thơ là **chưa đủ**. Cần ít nhất:

1. Định danh khóa có namespace, tenant và key đúng ngữ nghĩa.
2. Token owner duy nhất cho mỗi lần giữ khóa.
3. TTL/lease để khóa không kẹt mãi khi process chết.
4. Release có kiểm tra **chủ sở hữu** (thực hiện atomically), không xóa khóa của owner mới khi lease cũ đã hết.
5. Chờ có timeout/backoff/jitter; không polling vô hạn hoặc gây quá tải Redis.
6. **Đọc lại cache sau khi giành được khóa**, vì một tiến trình khác có thể đã tính xong trong lúc bạn chờ.
7. Chính sách khi loader hoặc cache backend lỗi: trả lỗi, fallback, stale value hay tính lại; phải công bố rõ.
8. Cân nhắc **fencing token/version** khi lease có thể hết trong lúc tác vụ vẫn chạy.

Đặc biệt, một khóa có TTL **không đảm bảo đúng một lần tính**. Nếu App A giữ khóa 5 giây nhưng tính 10 giây, khóa có thể hết hạn, App B trở thành owner mới và cả hai cùng tính. Khi ấy phải có cơ chế để kết quả **cũ** không ghi đè dữ liệu mới, ví dụ version check hoặc fencing do tầng lưu trữ thực thi.

Đoạn sau là **pseudocode**, không phải Java chạy độc lập:

~~~text
value = cache.get(key)
if value exists:
    return value

lease = coordinator.tryAcquire(lockKey(key), ownerToken, boundedLease)
if lease acquired:
    try:
        value = cache.get(key)       # recheck sau khi có lease
        if value exists:
            return value

        fresh = loadFromSource()
        writeWithVersionRules(key, fresh)
        return fresh
    finally:
        coordinator.releaseOnlyIfOwner(lockKey(key), ownerToken)
else:
    boundedWaitWithJitter()
    value = cache.get(key)
    if value exists:
        return value
    followExplicitFailureOrFallbackPolicy()
~~~

Trên thực tế, lock, cache, DB và kết quả được ghi có thể ở các hệ thống khác nhau; phải xét crash/restart, partition mạng, lease expiry, timeout và thứ tự ghi. Nếu yêu cầu **đúng một lần thực thi side effect**, chỉ một distributed cache lock thường không đủ; cần idempotency hoặc transactional coordination ở tầng ghi nghiệp vụ.

### C. Giảm stampede mà không cần distributed lock chặt

Một số kỹ thuật chủ động giảm đỉnh tải:

- **TTL jitter:** thay vì mọi entry hết hạn đúng sau 60 giây, dùng biến thiên ngẫu nhiên có giới hạn để tránh rất nhiều key hết hạn cùng lúc.
- **Stale-while-revalidate:** có thể trả kết quả cũ trong cửa sổ cho phép và làm mới có kiểm soát; chỉ áp dụng nếu nghiệp vụ chấp nhận stale.
- **Refresh-ahead/prefetch:** làm mới key nóng trước khi hết hạn, có giới hạn công suất.
- **Warm-up có kiểm soát:** chỉ nạp các key quan trọng khi deploy hoặc scale-out, tránh mọi replica cùng warm một tập lớn.
- **Rate limit/bulkhead:** giới hạn số loader đồng thời nhằm bảo vệ DB khi cache bị lỗi hoặc mất dữ liệu.
- **Tách TTL theo loại dữ liệu:** key hiếm không cần chiến lược phức tạp; key cực nóng có thể cần refresh riêng.
- **Dedupe tại tầng tác vụ:** đồng nhất một công việc nền theo ID nếu loader vốn là job có thể chạy dài.

Mỗi cách có trade-off. Nếu dữ liệu liên quan số dư, quyền truy cập hay quyết định giao dịch cần nhất quán cao, không được tùy tiện trả stale chỉ để giảm latency.

## 8. So sánh các phương án theo phạm vi thật

| Phương án | Đồng bộ các thread cùng JVM | Đồng bộ giữa nhiều JVM | Điều phải xác minh |
| --- | --- | --- | --- |
| `synchronized` trên bean instance | Có cho cùng instance; có thể khóa rộng | **Không** | Số bean instance, phạm vi lock |
| Local per-key lock/`computeIfAbsent` | Có trên cùng map/key | **Không** | Cleanup, key equality, lỗi loader |
| `ConcurrentMapCacheManager` + `sync=true` | Có theo cache instance trong ví dụ | **Không** với các manager độc lập | Đúng bean/cache và proxy |
| Caffeine local cache có loader phối hợp | Có theo cache instance và API phù hợp | **Không** nếu mỗi JVM có cache riêng | Caffeine API/refresh semantics |
| Redis dùng chung, không có coordination thích hợp | Shared values nhưng loader vẫn có thể trùng | **Không bảo đảm** | Redis writer, load callback, race |
| Redis locking writer | Hành vi phụ thuộc implementation | Có thể giúp phối hợp một số thao tác, **không suy diễn** bảo đảm per-key | Lock ở mức cache, phiên bản/provider |
| Distributed per-key coordinator thiết kế đúng | Có | Có thể đạt single-flight trong điều kiện xác định | Lease, token, fencing, failure, version |
| TTL jitter / stale-while-revalidate | Giảm khả năng miss đồng thời | Giảm nhu cầu phối hợp giữa nhiều JVM | Mức stale và refresh capacity |

Không có phương án nào mặc nhiên bảo đảm exactly-once cho mọi lỗi mạng, rollback và retry. "Một kết quả được lưu" cũng khác hoàn toàn với "chỉ một loader chạy": hai loader có thể hoàn thành và một kết quả ghi đè kết quả kia.

## 9. Quy tắc khóa, cache name và dữ liệu multi-tenant

Dù đồng bộ trong một hay nhiều JVM, các lời gọi chỉ nên phối hợp nếu chúng nhắm **cùng một kết quả nghiệp vụ**.

~~~text
Cache identity = backend/manager + cacheName + key
key = (tenantId, reportId, projectionVersion) khi chúng ảnh hưởng kết quả
~~~

Ví dụ `R1` có thể tồn tại trong hai tổ chức khác nhau:

~~~text
(acme, R1) -> báo cáo của Acme
(beta, R1) -> báo cáo của Beta
~~~

Nếu dùng `key="#p1"` chỉ theo report ID trong cache chung, không chỉ đồng bộ nhầm: một tenant còn có thể nhận dữ liệu từ tenant kia. Hãy dùng key theo scope đáng tin, kiểm tra authorization **trước mỗi yêu cầu**, và bảo đảm query DB thực thi tenant filtering. Cache không phải ranh giới bảo mật.

Thêm thông tin ngẫu nhiên như `requestId`/timestamp vào key sẽ khiến mọi lời gọi có key khác nhau; đồng bộ cùng key sẽ **không còn ý nghĩa**. Ngược lại, khóa quá rộng làm những kết quả khác nhau dùng chung entry. Với distributed coordination, key của lock cũng phải được chuẩn hóa theo cache identity để không phối hợp nhầm hoặc bỏ sót.

Dữ liệu trong key có thể hiện trong Redis, tracing, metrics và logs: tránh dùng token, mật khẩu hoặc thông tin nhạy cảm không cần thiết. Khi chuyển record/object key từ in-memory sang Redis, kiểm chứng serializer và cách provider prefix tên cache.

## 10. Đồng bộ loader không có nghĩa dữ liệu luôn mới

`sync=true` chủ yếu giúp phối hợp **cache miss cho cùng key**. Nó không tự giải quyết các vấn đề sau:

### Reader chậm ghi đè writer mới

~~~text
T1: Reader A miss R1, bắt đầu tính dữ liệu nguồn v1.
T2: Writer B cập nhật nguồn lên v2, put cache v2.
T3: Reader A kết thúc và put v1 vào cache.
T4: Người dùng có thể thấy v1 dù nguồn là v2.
~~~

Tùy implementation, read/put và callback load có thể được điều phối khác nhau. Không được giả định `sync=true` khiến `@CachePut`, `@CacheEvict`, database transaction và mọi writer khác tham gia cùng một lock hoặc thứ tự toàn cụm.

Giải pháp có thể yêu cầu versioning, optimistic locking, kiểm tra version trước khi put, invalidation sau commit, hoặc thiết kế cache version theo bản ghi.

### Dữ liệu bị đổi hoặc quyền bị thu hồi

Khi cache hit, thân method `@Cacheable` có thể không chạy. `sync=true` không làm authorization trong thân method chạy lại. Nếu kết quả có phân quyền, cần kiểm tra quyền ở entrypoint/facade chạy trên **mọi request**, và chính sách key/invalidation theo tenant/user/quyền phù hợp.

### Exception, timeout và process crash

Nếu loader ném exception, cơ chế cache thông thường không ghi một giá trị thành công; các caller khác có thể cần tính lại hoặc nhận lỗi. Nếu process chết giữa lúc giữ distributed lease, lock cần expiry hoặc recovery. Nếu callback load quá chậm, phải có timeout, circuit breaker, bulkhead và fallback được thiết kế cẩn thận.

Một "khóa toàn cụm" đặt sai có thể gây hàng loạt request chờ thay vì bảo vệ hệ thống. Hãy giám sát tail latency, số waiter và thời gian lock hold, không chỉ cache hit ratio.

## 11. Đo lường và kiểm thử đồng thời

Để đánh giá một phương án, hãy xác định **đúng mục tiêu đo**:

| Đại lượng | Ý nghĩa |
| --- | --- |
| `loaderInvocationCount` theo key | Bao nhiêu lần tác vụ thật chạy trên cache miss |
| Cache hit/miss | Tỷ lệ có kết quả sẵn; không cho biết loader có bị trùng lúc miss |
| `inflightLoads` | Số loader đang chạy cùng thời điểm |
| `waiterCount` và wait duration | Có bao nhiêu request bị chặn bởi coordination |
| Loader error/timeout rate | Cache stampede có gây áp lực lên DB/API downstream không |
| Distributed lease expiry/reacquire | Có nguy cơ owner cũ và mới cùng làm việc không |
| Stale read/version mismatch | Hệ thống có trả dữ liệu cũ sau update không |
| p95/p99 latency | Lock có tạo hàng chờ lớn và xấu tail latency không |

### Test 1: Nhiều thread trong một JVM

- Chuẩn bị cache sạch.
- Cho 8–100 thread cùng gọi **một key** qua Spring proxy.
- Đo số lần method thật chạy, giá trị kết quả và lỗi/timeout.
- Với `ConcurrentMapCacheManager` và `sync=true` trong demo, kỳ vọng một lần load cho cùng key đã được cache. Đừng coi đây là bằng chứng nhiều máy.

Có thể thêm test key khác nhau để xác minh các key độc lập không bị chặn bởi một khóa toàn cục không chủ ý.

### Test 2: Hai application instance

Triển khai hai process JVM hoặc hai container độc lập. Phải ghi rõ chúng dùng **local caches riêng** hay **shared Redis**. Tạo request đồng thời cho cùng key qua cả hai process, gắn trace ID và đếm loader ở nguồn (DB/API) bằng telemetry dùng chung.

- Nếu mỗi process có local cache, sau cold start có thể thấy ít nhất một loader ở mỗi process.
- Nếu dùng shared Redis, kiểm tra cả số lần compute **và** số lần put, không chỉ entry cuối cùng.
- Nếu dùng distributed coordination, kiểm thử contention, timeouts, crash của owner, hết lease, cache backend chập chờn và retry.
- Lặp lại phép thử khi tăng số replica và khi cache mất dữ liệu hàng loạt.

Không thể chứng minh một cơ chế "đúng toàn cụm" chỉ bằng test một JVM có nhiều thread, ngay cả khi dùng đến hàng nghìn thread.

### Test 3: Thay đổi dữ liệu cùng lúc với cache load

Giữa lúc một loader đang tính, cập nhật DB và evict/put cùng key. Ghi nhận version mà caller nhận sau update. Test này phát hiện race riêng với stale data; nó khác với test chống stampede.

### Test 4: Khi provider lỗi

Giả lập Redis timeout, mất kết nối hoặc cache miss đột ngột, rồi quan sát `CacheErrorHandler`/loader/fallback. Đảm bảo không có trạng thái mọi caller cùng chạy truy vấn nặng không giới hạn, cũng không có deadlock làm hệ thống mất khả năng phục vụ.

## 12. Những hiểu lầm phổ biến

| Hiểu lầm | Thực tế |
| --- | --- |
| "`sync=true` bảo đảm toàn cluster chỉ tính một lần" | Không; đó là hint, phụ thuộc provider và coordination domain |
| "Các node cùng dùng cache name là dùng chung khóa" | Tên giống nhau không làm Java cache/lock objects trở thành shared |
| "Redis chung nghĩa là các loader tự chờ nhau" | Shared storage chưa đủ để bảo đảm gộp các miss đồng thời |
| "Java `synchronized` bảo vệ các pod Kubernetes" | Java monitor chỉ có hiệu lực với object trong JVM đó |
| "Dùng `static Lock` là khóa toàn máy" | Static field tồn tại theo classloader/JVM, không xuyên process |
| "Bật Redis locking writer chắc chắn là khóa riêng từng key" | Tài liệu mô tả locking writer ở mức cache, có trade-off khác |
| "Có TTL là hết stampede" | TTL khiến entry hết hạn; đồng loạt hết hạn còn có thể làm stampede nặng hơn |
| "Lock hết hạn thì owner cũ chắc chắn dừng" | Owner cũ có thể vẫn chạy và ghi stale value |
| "`sync=true` cũng chặn hai update đồng thời" | Nó nhắm load trên cache miss, không phải transaction/locking tổng quát |
| "Có một cache entry nghĩa là chỉ một loader từng chạy" | Nhiều loader có thể cùng put/ghi đè một entry |
| "Thêm `unless` vào `sync=true` để chặn cache null" | Contract `@Cacheable` không hỗ trợ kết hợp này |
| "Chạy một test nhiều thread đủ chứng minh production" | Cần test nhiều process và provider thực tế |

## 13. Bài tập tự kiểm tra

**Bài 1.** Một ứng dụng Spring Boot chạy một JVM, dùng `ConcurrentMapCacheManager`, 20 request cùng gọi `@Cacheable(cacheNames="reports",sync=true)` với key `"R1"` trên cùng proxy. Kỳ vọng nào hợp lý?  
**Đáp án:** manager in-memory có khả năng phối hợp load cùng key trong cùng cache instance; khi loader thành công và cache entry được lưu, kỳ vọng một lần tính cho đợt miss ấy, các caller khác nhận cùng kết quả.

**Bài 2.** Ứng dụng trên scale lên 6 pod, mỗi pod tạo `ConcurrentMapCacheManager` riêng. Có còn bảo đảm toàn hệ thống chỉ một loader cho `"R1"`?  
**Đáp án:** không. Mỗi pod có memory/cache riêng; nếu tất cả cùng miss, có thể mỗi pod chạy loader riêng, dù các thread trong một pod được phối hợp.

**Bài 3.** Hai pod dùng chung Redis. Chúng có nhất định chỉ chạy một loader khi đồng thời GET miss không?  
**Đáp án:** không nhất định. Cần kiểm tra semantics của cache provider/writer và chiến lược coordination; shared Redis storage không mặc nhiên chặn hai phép tính cùng lúc.

**Bài 4.** Vì sao distributed lock cần token owner và release atomically?  
**Đáp án:** lease của owner A có thể hết, B nhận khóa mới; A không được xóa khóa đang thuộc về B. Release cần kiểm tra token với thao tác nguyên tử.

**Bài 5.** A giữ khóa 5 giây nhưng tính mất 12 giây; B giành khóa sau 5 giây. Có thể khẳng định chỉ một loader không?  
**Đáp án:** không. Cần chiến lược lease renewal/fencing/versioning hoặc chính sách tính lại có thể chấp nhận. Lock TTL không tự dừng tác vụ của A.

**Bài 6.** Vì sao `@Cacheable(sync=true, unless="#result == null")` không phù hợp?  
**Đáp án:** `sync=true` không hỗ trợ `unless` theo contract Spring. Muốn vừa single-flight vừa lọc kết quả, cần thiết kế cơ chế khác.

**Bài 7.** Một báo cáo ở Acme và Beta cùng có ID `"R1"`. Có thể dùng key chỉ `"R1"` để cả hai tenant chia sẻ cache và distributed lock không?  
**Đáp án:** không nếu kết quả khác nhau. Cần key theo tenant/scope đã xác thực, không đánh đồng hai dữ liệu khác nhau.

**Bài 8.** Khi nào chọn TTL jitter thay vì distributed lock?  
**Đáp án:** khi mục tiêu chủ yếu là tránh nhiều entry đồng loạt expire, dữ liệu chấp nhận eventual consistency và chi phí lặp loader còn chịu được; TTL jitter đơn giản hơn nhưng không bảo đảm single-flight.

## 14. Tóm tắt quyết định kiến trúc

Nếu cần lựa chọn nhanh, hãy đi theo thứ tự:

1. **Xác định mục tiêu:** giảm trùng tải trên miss, bảo vệ downstream, hay bảo đảm dữ liệu cập nhật không bị stale? Ba mục tiêu không hoàn toàn giống nhau.
2. **Xác định phạm vi thật:** một JVM, nhiều JVM với local cache, hay nhiều JVM cùng shared cache?
3. **Xác nhận provider:** `@Cacheable(sync=true)` có hỗ trợ load synchronized trên đúng `Cache.get(key,Callable)` và phạm vi nào?
4. **Cân chi phí:** một phép tính trùng mỗi replica có nguy hiểm không? Nếu không, local coordination cộng TTL jitter có thể đủ.
5. **Nếu cần cluster coordination:** chọn primitive đúng, thiết kế owner token, lease, fencing/version, timeout, failure và retry.
6. **Kiểm thử hiện trường:** đo số loader toàn hệ thống, waiter/tail latency, stale version, và thử crash/partition/rollout nhiều instance.
7. **Không lẫn sang authorization:** cache hit có thể bỏ qua method; kiểm tra quyền và scope phải luôn đúng trên mọi request.

### Tài liệu tham khảo chính thức

- Spring Framework – **Synchronized Caching** và `@Cacheable(sync=true)`: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – Javadoc `@Cacheable` (hợp đồng `sync`, hạn chế `unless`, một cache và callback): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework – Javadoc `Cache.get(Object, Callable)`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html
- Spring Data Redis – **Redis Cache** (locking/non-locking writer, lock ở mức cache, TTL, prefix): https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
- Spring Data Redis – Javadoc `RedisCacheWriter`: https://docs.spring.io/spring-data/redis/reference/4.0/api/java/org/springframework/data/redis/cache/RedisCacheWriter.html

**Ghi nhớ:** trong một JVM, `@Cacheable(sync=true)` với provider hỗ trợ có thể gộp các lần miss cùng key. Giữa nhiều JVM, local lock không có hiệu lực, còn shared cache chưa chắc cung cấp distributed single-flight. Muốn phối hợp toàn cụm phải xác minh khả năng của provider hoặc xây điều phối phân tán có chính sách lease, failure và version rõ ràng. Đừng suy từ thành công của test nhiều thread trong một tiến trình sang bảo đảm trên nhiều máy.