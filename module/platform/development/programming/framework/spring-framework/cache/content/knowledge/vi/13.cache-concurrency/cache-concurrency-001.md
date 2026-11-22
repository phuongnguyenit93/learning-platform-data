# Nhiều luồng cùng trượt một khóa và tính toán lặp

Trong hệ thống dùng Spring Cache, **cache miss (trượt cache)** xảy ra khi một khóa chưa có kết quả được lưu, hoặc entry đã bị xóa/hết hạn. Khi **nhiều luồng cùng lúc gọi một phương thức với cùng cache name và cache key**, chúng có thể đều thấy cache miss trước khi bất kỳ luồng nào kịp lưu kết quả. Mỗi luồng tự chạy lại cùng phép tính tốn kém. Hiện tượng này thường được gọi là **cache stampede**, **dogpile effect** hoặc **thundering herd** ở mức tải dữ liệu.

**Ví dụ:** 100 request đồng thời hỏi sản phẩm **P01** vừa hết TTL. Nếu mỗi request đều đọc DB trong 150 ms, một cache miss vốn chỉ cần một lượt truy vấn có thể trở thành 100 lượt truy vấn gần như đồng thời. Cache không còn giảm tải đúng như mong đợi ở thời điểm quan trọng nhất.

Bài này giải thích cơ chế, tác hại, cách dùng **@Cacheable(sync = true)** và giới hạn của nó, đồng thời cung cấp một dự án **Java 17 + Spring Framework** tái hiện tình huống có/không đồng bộ với kết quả quan sát được bằng **CountDownLatch**.

## 1. Cùng một khóa, vì sao nhiều luồng đều cache miss?

Cơ chế thông thường của **@Cacheable** khi không dùng đồng bộ nạp dữ liệu:

1. Tính **cache name + cache key** từ method và đối số.
2. Gọi cache để tìm entry.
3. Nếu hit, trả ngay dữ liệu đã lưu, không thực thi method.
4. Nếu miss, **thực thi method** để tạo kết quả.
5. Ghi kết quả vào cache để lời gọi về sau có thể hit.

Điểm đáng chú ý nằm giữa bước 2 và bước 5: hai thao tác **đọc cache** và **nạp/ghi kết quả** không mặc nhiên là một vùng tới hạn duy nhất theo khóa. Nhiều luồng có thể đi qua bước 2 trước khi bất kỳ luồng nào hoàn thành bước 5.

~~~text
Thời gian         Luồng A                    Luồng B
    |        get("P01") -> MISS        get("P01") -> MISS
    |        query DB / HTTP...       query DB / HTTP...
    |        tính kết quả             tính lại cùng kết quả
    |        put("P01", value)         put("P01", value)
    v        trả dữ liệu               trả dữ liệu
~~~

Cache cuối cùng vẫn có thể chứa một entry hợp lệ; nhưng **phép tính đắt đỏ đã chạy nhiều lần**. Nếu dữ liệu được đọc tại những thời điểm khác nhau hoặc phép tính có side effect, kết quả từ các luồng còn có thể khác nhau. Một kết quả hoàn thành muộn hơn có thể ghi cache sau và thay giá trị trước đó, tùy provider và thứ tự thực tế.

**Không nhầm với trùng hash code:** các lời gọi ở đây cố ý cùng **logical key**; vấn đề là nhiều miss đồng thời chứ không phải hai đối tượng khác nghĩa vô tình tạo cùng key.

## 2. Điều kiện tạo ra stampede và những tác hại

Tình huống thường thấy:

- **Cold start / deploy mới:** cache ban đầu rỗng và nhiều request cùng đọc một dữ liệu phổ biến.
- **Một hot key vừa hết TTL:** hàng nghìn người dùng cùng cần một entry sau thời điểm expiration.
- **Invalidation đồng loạt:** một sự kiện xóa entry mà nhiều request đang sử dụng.
- **Cache node restart / evict do thiếu bộ nhớ:** nhiều key bị thiếu cùng lúc.
- **Database/HTTP backend chậm:** khoảng thời gian từ miss tới put càng dài, càng nhiều request có cơ hội cùng miss.
- **Tải burst:** request đến gần như đồng thời sau một sự kiện, chiến dịch hoặc cập nhật nội dung.

| Tác hại | Diễn giải |
| --- | --- |
| Nhiều truy vấn DB/API lặp | Tiêu hao CPU, connection pool, quota và băng thông |
| Độ trễ tăng | Nhiều luồng cùng phải chờ phép tính tốn kém |
| Tăng tải ngược (feedback loop) | Backend chậm → cửa sổ miss kéo dài → càng thêm request trượt |
| Chi phí tăng | Truy cập dịch vụ bên thứ ba có thể tính phí theo số gọi |
| Race/overwrite | Nhiều kết quả tính ở thời điểm khác nhau có thể ghi cùng key |
| Sự cố dây chuyền | Thread pool/DB pool đầy, timeout, retry làm khuếch đại tải |

**Phân biệt:** Một *stampede theo cùng khóa* xảy ra khi nhiều lời gọi cùng chờ một kết quả. Một *cache avalanche* có thể là hàng loạt **khóa khác nhau** hết hạn cùng lúc, gây tổng tải lớn. Giải pháp chỉ khóa theo từng key sẽ giúp giảm việc tính lặp cho *một key* nhưng **không tự giải quyết** việc hàng nghìn key khác nhau đồng thời hết hạn.

## 3. @Cacheable(sync = true): phối hợp nạp cùng khóa

Spring cho phép khai báo:

~~~java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product findById(String productId) {
    return repository.fetch(productId);
}
~~~

Trong môi trường mà Cache implementation hỗ trợ đồng bộ tải dữ liệu, các luồng cùng miss **một cache key** sẽ cùng tham gia một thao tác **get-or-load**: một luồng thực thi phép tính, các luồng còn lại chờ và dùng kết quả đã nạp.

~~~text
                       cache "products", key "P01"
       ┌────────────────────┼────────────────────┐
       │                    │                    │
    Thread A             Thread B             Thread C
       │                    │                    │
       └─────── cùng miss ──┴────────────────────┘
                            │
                    phối hợp per-key load
                            │
                  1 luồng fetch từ DB
                            │
                      ghi 1 entry
                            │
                  các luồng nhận kết quả
~~~

**Cách hiểu đúng:** **sync = true** là yêu cầu/hint để cache provider đồng bộ việc nạp một entry. Nó **không có nghĩa** Spring tự tạo một distributed lock bảo đảm toàn bộ cluster chỉ chạy một lần. Hiệu lực cụ thể phụ thuộc CacheManager và implementation của **Cache.get(key, Callable)** hoặc cơ chế nạp tương đương.

Với **ConcurrentMapCache** trong một JVM, cơ chế get-or-load có thể dùng tính toán nguyên tử theo key của concurrent map để cùng một key chỉ được nạp một lần trong đợt miss đồng thời. Với Caffeine cần xét đúng chế độ/cache configuration. Với Redis hoặc provider phân tán, phải đọc tài liệu về locking/load atomics và kiểm thử nhiều instance: sync ở từng JVM hoặc một thao tác cache không có khóa phân tán **không đủ để khẳng định** chỉ một replica gọi DB.

### Giới hạn annotation sync

Đối với **@Cacheable(sync = true)** trong Spring Framework, cần nhớ:

1. **Chỉ khai báo một cache** trong thao tác cacheable đó.
2. **Không dùng thuộc tính unless** để veto kết quả sau khi tính.
3. **Không kết hợp thêm một cache operation khác trên cùng method** theo cấu hình synchronized caching.
4. Cache provider phải hỗ trợ semantics đồng bộ; đây là một hint, không phải bảo đảm phổ quát.

Ví dụ không nên dùng:

~~~java
// KHÔNG HỢP LỆ theo giới hạn synchronized caching:
// @Cacheable(cacheNames = {"A", "B"}, sync = true)
// public Item load(String id) { ... }

// KHÔNG HỢP LỆ:
// @Cacheable(cacheNames = "A", sync = true,
//            unless = "#result == null")
// public Item load(String id) { ... }
~~~

**sync = true** không tự thêm tenant/locale/currency vào key. Nếu key thiếu thành phần, các request khác nghĩa có thể bị gộp **sai dữ liệu** dù không còn tính lặp. Trước khi tối ưu đồng thời, key phải đúng nghiệp vụ.

## 4. Ví dụ định lượng: tại sao chờ nhau có thể rẻ hơn tính lặp?

Giả sử có 40 request tới cùng key trong khoảng 100 ms, truy vấn nguồn mỗi lần mất 200 ms.

| Không phối hợp nạp | Có phối hợp nạp theo key |
| --- | --- |
| Nhiều request cùng miss và có thể chạy hàng chục truy vấn nguồn | Một truy vấn nguồn phục vụ nhiều request chờ |
| Backend chịu nhiều thao tác trùng lặp | Backend giảm tải cho hot key |
| Nhiều kết quả cùng được put | Một lượt nạp có thể được chia sẻ |
| Có thể gây nghẽn connection pool | Ít truy vấn hơn, nhưng các caller cùng đợi một kết quả |
| CPU/DB tổng cộng lớn | Cần tính chi phí khóa, thời gian chờ và xử lý lỗi |

Không kết luận rằng mọi request sẽ nhanh hơn: những request đến cùng lúc vẫn cần chờ phép tính đầu tiên. Lợi ích chính là **không nhân bản công việc** và tránh phá hủy tài nguyên backend. Khi phép tính rất nhanh, overhead của đồng bộ có thể không đáng kể hoặc có thể lớn hơn lợi ích; phải đo trong tải thực tế.

## 5. Dự án Java 17 + Spring: tái hiện sáu luồng cùng trượt một khóa

Ví dụ dùng **Spring Framework 6.1.14**, **Java 17+**, **ConcurrentMapCacheManager** và Java concurrency primitives. Không dùng sleep để suy đoán thời điểm; **CountDownLatch** buộc sáu luồng trong trường hợp không sync đều đi vào thân method trước khi bất kỳ luồng nào được phép trả kết quả.

Cấu trúc:

~~~text
spring-cache-stampede-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/cache/CacheStampedeDemo.java
└── src/test/java/demo/cache/CacheStampedeDemoTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-cache-stampede-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    testImplementation 'org.springframework:spring-test:6.1.14'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.cache.CacheStampedeDemo'
}

test {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/cache/CacheStampedeDemo.java**

~~~java
package demo.cache;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheStampedeDemo {
    public static final int REQUESTS = 6;

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("plain", "synced");
        }

        @Bean
        public WorkService workService() {
            return new WorkService();
        }
    }

    public static class WorkService {
        private final AtomicInteger plainLoads = new AtomicInteger();
        private final AtomicInteger syncLoads = new AtomicInteger();

        // Không sync: cả sáu lần thực thi sẽ chờ ở đây.
        private final CountDownLatch plainEntered =
                new CountDownLatch(REQUESTS);
        private final CountDownLatch plainRelease = new CountDownLatch(1);

        // Có sync: chỉ một lời gọi được vào thân method khi miss.
        private final CountDownLatch syncEntered = new CountDownLatch(1);
        private final CountDownLatch syncRelease = new CountDownLatch(1);

        @Cacheable(cacheNames = "plain", key = "#p0")
        public String plain(String key) {
            int n = plainLoads.incrementAndGet();
            plainEntered.countDown();
            await(plainRelease);
            return "plain:" + key + ":" + n;
        }

        @Cacheable(cacheNames = "synced", key = "#p0", sync = true)
        public String synced(String key) {
            int n = syncLoads.incrementAndGet();
            syncEntered.countDown();
            await(syncRelease);
            return "synced:" + key + ":" + n;
        }

        public void awaitAllPlainMisses() {
            await(plainEntered);
        }

        public void awaitOneSyncedLoad() {
            await(syncEntered);
        }

        public void releasePlain() {
            plainRelease.countDown();
        }

        public void releaseSynced() {
            syncRelease.countDown();
        }

        public int plainLoads() {
            return plainLoads.get();
        }

        public int syncLoads() {
            return syncLoads.get();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out at latch");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
    }

    static List<Future<String>> submit(
            ExecutorService executor, Callable<String> task) {
        List<Future<String>> pending = new ArrayList<>();
        for (int i = 0; i < REQUESTS; i++) {
            pending.add(executor.submit(task));
        }
        return pending;
    }

    static int countDistinct(List<Future<String>> pending)
            throws Exception {
        Set<String> values = new HashSet<>();
        for (Future<String> future : pending) {
            values.add(future.get(15, TimeUnit.SECONDS));
        }
        return values.size();
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            WorkService service = context.getBean(WorkService.class);
            ExecutorService pool = Executors.newFixedThreadPool(REQUESTS);
            try {
                // Sáu worker đều miss cùng key "K1" trước khi put.
                var plainTasks = submit(pool, () -> service.plain("K1"));
                service.awaitAllPlainMisses();
                service.releasePlain();

                int distinctPlain = countDistinct(plainTasks);
                System.out.println("plainLoads=" + service.plainLoads());
                System.out.println("plainDistinct=" + distinctPlain);

                // Trên vùng khác, sáu worker cùng miss một key.
                var syncedTasks = submit(pool, () -> service.synced("K1"));
                service.awaitOneSyncedLoad();
                service.releaseSynced();

                int distinctSynced = countDistinct(syncedTasks);
                System.out.println("syncLoads=" + service.syncLoads());
                System.out.println("syncDistinct=" + distinctSynced);

                // Cache đã có kết quả: hit không tăng bộ đếm.
                service.synced("K1");
                System.out.println("syncAfterHit=" + service.syncLoads());
            } finally {
                // Nếu có lỗi, không để worker mắc kẹt ở latch.
                service.releasePlain();
                service.releaseSynced();
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy từ thư mục dự án bằng Gradle thích hợp cho Java 17 (hoặc Gradle wrapper của dự án nếu đã tạo):

~~~bash
gradle run --quiet
~~~

Kết quả do **System.out.println** in ra theo thứ tự sau, với **ConcurrentMapCacheManager** và điều kiện sáu luồng được thực thi như trong ví dụ:

~~~text
plainLoads=6
plainDistinct=6
syncLoads=1
syncDistinct=1
syncAfterHit=1
~~~

Giải thích chính xác:

1. **plain** không dùng **sync**. Sáu worker đều miss khóa **"K1"** trong cache **plain** và đi vào thân method; mỗi worker tăng **plainLoads** và chờ. Controller chỉ mở latch khi đã có **6 lượt thực thi**. Vì thế **plainLoads = 6** và các kết quả chứa số thứ tự từ 1 đến 6 nên có **6 kết quả khác nhau**.
2. **synced** dùng **sync = true**. Với ConcurrentMapCache, một worker tính kết quả của **"K1"** cho cache **synced**; các worker khác nhận lại kết quả đó thay vì tính lặp. **syncLoads = 1**, **syncDistinct = 1**.
3. Gọi **synced("K1")** thêm một lần sau đó là cache hit, nên bộ đếm vẫn là 1.

**Vì sao kết quả có thể khẳng định?** Phần plain dùng latch đếm đủ sáu method invocation **trước khi cho phép bất kỳ method nào trả về**, nên không phải thử may rủi dựa vào **Thread.sleep()**. Phần sync cho phép đúng một invocation vào body và những lời gọi khác dùng entry vừa tạo. Không dùng latch đợi sáu invocation *bên trong* method synced: cách đó sẽ deadlock vì cơ chế sync chủ đích chỉ cho một loader đi vào thân method.

**Giới hạn của kết quả:** Dự án dùng cache local của Spring và một JVM. Sự đảm bảo **syncLoads=1** dựa vào provider hỗ trợ đồng bộ get-or-load; không được tự gán kết quả này cho Redis cluster hoặc hai JVM riêng biệt.

### Kiểm thử bằng JUnit 5

**src/test/java/demo/cache/CacheStampedeDemoTest.java**

~~~java
package demo.cache;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(CacheStampedeDemo.Config.class)
class CacheStampedeDemoTest {

    @Autowired
    CacheStampedeDemo.WorkService service;

    @Test
    void sameKeyBurstIsComputedOnceWithSync() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(
                CacheStampedeDemo.REQUESTS);
        try {
            var plain = CacheStampedeDemo.submit(
                    pool, () -> service.plain("K1"));
            service.awaitAllPlainMisses();
            service.releasePlain();

            assertEquals(6, CacheStampedeDemo.countDistinct(plain));
            assertEquals(6, service.plainLoads());

            var synced = CacheStampedeDemo.submit(
                    pool, () -> service.synced("K1"));
            service.awaitOneSyncedLoad();
            service.releaseSynced();

            assertEquals(1, CacheStampedeDemo.countDistinct(synced));
            assertEquals(1, service.syncLoads());

            assertEquals("synced:K1:1", service.synced("K1"));
            assertEquals(1, service.syncLoads());
        } finally {
            service.releasePlain();
            service.releaseSynced();
            pool.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Kỳ vọng: **một test JUnit thành công** trên môi trường Spring và JDK 17 phù hợp. Đây là integration test thực sự lấy bean từ ApplicationContext; gọi **new WorkService()** trực tiếp sẽ không kích hoạt cache interceptor như mong muốn.

Test dùng **timeout trong latch và Future.get** để tránh treo vô hạn nếu cấu hình sai. Nếu timeout, test cần fail rõ, không nên tăng thời gian chờ vô hạn để che lỗi. Các thông báo build chi tiết phụ thuộc Gradle/JDK nên không có stdout cố định cho lệnh test.

## 6. Vì sao không nên tự đồng bộ bằng synchronized toàn method?

Một phương án dễ nghĩ tới:

~~~java
public synchronized Product findById(String id) {
    return repository.fetch(id);
}
~~~

Nhưng **synchronized** trên method dùng chung một instance có thể khiến **mọi key** bị tuần tự hóa trong phạm vi synchronized. Lời gọi cho **P01** cũng chặn lời gọi cho **P02**, dù hai phép tính độc lập. Nếu một phương thức thuộc nhiều bean instance, synchronized ở một object cũng không bảo vệ instance khác, càng không tự bảo vệ nhiều replica.

Khi mục tiêu là tránh **nhiều miss cùng một key**, giải pháp tốt thường là **single-flight/per-key coordination** chứ không khóa toàn bộ service. **@Cacheable(sync = true)** với provider phù hợp là cách đơn giản để yêu cầu hành vi này trong một vùng cache. Một key khác có thể được tải đồng thời thay vì phải chờ hot key.

**Không tự chế Map<key,Lock>** nếu chưa quản lý vòng đời lock, số lượng key, lỗi/timeout và khả năng rò rỉ bộ nhớ. Nếu cần điều phối phức tạp hơn, nên dùng primitive có ngữ nghĩa rõ hoặc thư viện cache hỗ trợ loader.

## 7. Trường hợp sync = true không đủ

### 7.1. Nhiều replica hoặc nhiều process

Giả sử service có ba replica A/B/C; mỗi replica dùng **ConcurrentMapCacheManager** riêng. Khi cùng miss **P01**, có thể xảy ra:

~~~text
Replica A: local miss P01 -> 1 DB query
Replica B: local miss P01 -> 1 DB query
Replica C: local miss P01 -> 1 DB query
~~~

Ngay cả khi **mỗi JVM chỉ tính một lần theo key**, toàn hệ thống vẫn có thể có **3 truy vấn DB**. **sync = true** không tự biến local cache thành distributed cache.

Nếu dùng cache chia sẻ như Redis, vẫn cần kiểm tra **provider và cache writer** có thực hiện locking/load coordination xuyên các replica hay không. Không suy luận chỉ từ việc cùng trỏ tới Redis rằng tất cả process dùng chung một khóa loader.

Các lựa chọn tùy yêu cầu: distributed locking có **lease/timeout và fencing**, request coalescing ở một tầng được chia sẻ, refresh chủ động, hoặc chấp nhận một số truy vấn dư kèm rate limit. Distributed lock không phải giải pháp miễn phí: cần xử lý lock holder chết, timeout, retry, clock/lease và tính nhất quán sau khi hết lock.

### 7.2. Hai khóa khác nhau cùng hết hạn

**sync = true** thường điều phối theo **một key**. Nếu có 10.000 key hết TTL cùng lúc, vẫn có thể có 10.000 loader độc lập chạy. Cân nhắc:

- **TTL jitter:** thêm sai số được kiểm soát vào thời điểm hết hạn để phân tán tải, nếu provider hỗ trợ.
- **Refresh-ahead / prewarming:** nạp những hot key trước khi hết hạn khi có thể.
- **Stale-while-revalidate:** phục vụ kết quả cũ trong khoảng ngắn, cập nhật nền theo cơ chế riêng và chấp nhận độ cũ được xác định rõ.
- **Bulkhead và giới hạn concurrency:** giới hạn tải đồng thời tới DB/API.
- **Circuit breaker và backpressure:** tránh dồn retry vô hạn vào backend đang suy giảm.
- **Sharding hoặc cache phân tầng:** giảm điểm nóng, nhưng phải giải quyết vấn đề nhất quán và invalidation.

Không phải tất cả tính năng trên có sẵn trong annotation **@Cacheable**. Chúng có thể cần provider, thư viện hoặc thiết kế riêng. Chọn theo SLA về độ mới, tài nguyên backend và mức độ phức tạp chấp nhận được.

### 7.3. Loader bị lỗi, chậm hoặc trả null

Nếu một loader **ném exception**, kết quả thường không được lưu như một giá trị thành công; những lời gọi khác hoặc lần sau có thể phải tính lại. Khi nhiều luồng cùng chờ, cần xác định chính xác semantics lan truyền exception/retry của provider; không tự khẳng định mọi caller sẽ thấy cùng một exception.

Nếu loader bị treo hoặc tốn vài giây, các luồng chờ một hot key có thể gây **head-of-line waiting**. Đồng bộ làm giảm số phép tính, không tự đặt timeout cho DB hoặc ngăn queue vô hạn. Cần giới hạn thời gian, giới hạn số caller chờ, cân nhắc fallback và giám sát.

Kết quả **null** có thể được cache hay không tùy implementation và cấu hình; ví dụ ConcurrentMapCache có hỗ trợ lưu null thông qua cơ chế chuyển đổi nội bộ khi được bật. Với dữ liệu “không tìm thấy”, cân nhắc **negative caching** có TTL ngắn nếu business cho phép. Không giả định một kết quả null được lưu mãi hoặc luôn không được lưu.

### 7.4. Invalidation trong khi đang tính toán

Một luồng đang nạp **P01** trong khi một luồng khác cập nhật DB rồi **@CacheEvict** cũng tác động **P01**. Tùy thời điểm, loader có thể trả bản đọc cũ và ghi vào cache **sau eviction**, làm entry stale xuất hiện lại. **sync = true** chủ yếu xử lý việc *nhiều loader cùng một key*; nó **không tự đảm bảo** atomic consistency giữa update nguồn và cache invalidation.

Với dữ liệu cần nhất quán cao, cân nhắc thứ tự commit/evict, versioned keys, optimistic check, cache-aside nhất quán theo phiên bản, hoặc event/outbox sau commit. Phải kiểm thử race giữa nạp và cập nhật, không chỉ kiểm thử đồng thời nhiều lần đọc.

## 8. Thiết kế cache key ảnh hưởng trực tiếp đến phạm vi khóa

Hai lời gọi được xem là “cùng khóa” theo **cache name + key mà Spring/Cache implementation thực sự nhận được**, không phải chỉ theo câu chữ của tham số.

~~~java
@Cacheable(cacheNames = "quotes", key = "#p0", sync = true)
public Quote quote(String sku, String tenant, String currency) {
    return gateway.quote(sku, tenant, currency);
}
~~~

Annotation trên **đồng bộ sai miền dữ liệu** vì cùng sku nhưng khác tenant/currency có thể bị gộp vào cùng entry; **sync = true** không sửa lỗi đó. Nếu output phụ thuộc cả ba chiều, dùng key đủ thành phần:

~~~java
@Cacheable(
    cacheNames = "quotes",
    key = "T(java.util.List).of(#p0, #p1, #p2)",
    sync = true
)
public Quote quote(String sku, String tenant, String currency) {
    return gateway.quote(sku, tenant, currency);
}
~~~

Ví dụ **List.of** yêu cầu tham số không null và phù hợp để minh họa với cache giữ key Java. Với cache phân tán cần kiểm tra key serializer; có thể dùng key có cấu trúc/encoding ổn định theo hợp đồng.

**Quy tắc:** key quá hẹp → cache hit sai dữ liệu; key quá rộng → các lời gọi đáng lẽ được dùng chung không gặp nhau, khiến stampede và cache footprint lớn hơn. Thiết kế key phải dựa vào hợp đồng nghiệp vụ trước khi tối ưu concurrency.

## 9. Phân tích hiệu năng và đo kiểm

Đừng chỉ kiểm tra rằng ứng dụng không ném exception. Đo các chỉ số dưới tải cùng khóa và tải nhiều khóa:

| Chỉ số | Cách diễn giải |
| --- | --- |
| **loader invocations/key** | Số lần tính thật cho một key sau cold miss |
| **cache hit/miss** | Tần suất tra cứu có dữ liệu; chú ý hit ratio có thể bị ảnh hưởng bởi sai key |
| **DB/API requests** | Tổng lượt gọi backend sau một burst |
| **latency p50/p95/p99** | Độ trễ caller, bao gồm thời gian chờ loader |
| **waiting threads/queue** | Số caller chờ một key và độ dài thời gian chờ |
| **timeout/error/retry rate** | Tình trạng nghẽn hoặc lỗi bị retry khuếch đại |
| **TTL/eviction/refresh metrics** | Thời điểm entry hết hạn và tác động tới burst |
| **distributed replication count** | Một key bị nạp bao nhiêu lần trên toàn cluster, không chỉ một JVM |

Test đề xuất:

1. **Cold miss cùng khóa:** n worker khởi phát cùng lúc; không sync thường có thể n loader, sync provider hỗ trợ nên giảm gần 1 loader.
2. **Hit sau khi đã nạp:** gọi thêm 10 lần, xác minh loader count không tăng.
3. **Hai khóa khác nhau:** thử P01 và P02; đừng vô tình khóa toàn bộ service.
4. **Method ném exception:** đo hành vi chờ, retry và cache state sau failure.
5. **Evict giữa lúc load:** kiểm tra stale result có thể quay lại hay không.
6. **Nhiều replica:** chạy load test qua các process trên cùng hoặc khác cache provider.
7. **Timeout và áp lực tài nguyên:** giới hạn pool, backend latency cao, retry và hủy request.

Dùng **CountDownLatch/Barrier** để kiểm soát thứ tự test, tránh dùng **Thread.sleep(100)** rồi coi kết quả lần chạy duy nhất là bằng chứng chắc chắn. Khi test sync, chỉ chờ **một loader vào method**; các caller còn lại không thể cùng vào thân method nếu cơ chế sync hoạt động. Đừng thiết lập barrier chờ n loader bên trong method sync vì sẽ gây deadlock.

## 10. Cách lựa chọn giải pháp theo bối cảnh

| Bối cảnh | Hướng ưu tiên |
| --- | --- |
| Một JVM, cache local, một hot key | **@Cacheable(sync = true)** với provider đã xác nhận hỗ trợ |
| Nhiều JVM với local caches | Phối hợp cấp cluster nếu thực sự cần single-flight toàn hệ thống |
| Shared Redis nhưng không có per-key distributed load lock | Không mặc định sync có hiệu lực toàn cluster; thử provider và cân nhắc locking/coalescing |
| Nhiều key hết hạn cùng lúc | TTL jitter, prewarming/refresh, bulkhead |
| Loader rất chậm hoặc đôi khi lỗi | Timeout, circuit breaker, giới hạn hàng đợi, fallback/negative caching |
| Cache thay đổi trong khi tính | Thiết kế versioning, after-commit invalidation, xử lý race |
| Output phụ thuộc tenant/locale/currency | Key đúng và ranh giới bảo mật trước, rồi mới sync |

Nếu dữ liệu cần cực kỳ nhất quán, đôi khi **không cache**, giảm phạm vi cache hoặc sử dụng một data source đọc nhất quán có kiểm soát sẽ tốt hơn việc thêm hàng loạt lock phức tạp.

## 11. Lỗi phổ biến

- **Tin rằng @Cacheable mặc định chặn các miss cùng khóa:** không có đảm bảo như vậy.
- **Hiểu sync = true thành distributed lock:** mức đồng bộ phụ thuộc Cache implementation, và local cache không phối hợp các process.
- **Cho rằng sync giải quyết avalanche nhiều khóa:** sync chủ yếu gộp công việc theo từng key.
- **Gắn sync=true kèm unless/multiple caches/operation khác:** vi phạm giới hạn synchronized caching.
- **Khóa synchronized toàn method:** có thể tuần tự hóa cả các key độc lập.
- **Test bằng Thread.sleep ngẫu nhiên:** kết quả có thể lúc đạt lúc không; nên điều phối chủ động bằng latch.
- **Đợi đủ n loader trong method sync:** dễ deadlock vì đúng cơ chế mong muốn chỉ cho một loader vào.
- **Thiếu tenant/currency trong key:** giảm số loader nhưng có thể trả dữ liệu sai giữa ngữ cảnh khác nhau.
- **Không xét exception và long-running loader:** nhiều caller chờ một điểm nghẽn; cần timeout/backpressure.
- **Không xét race giữa eviction và load:** dữ liệu cũ có thể bị ghi lại sau invalidation.
- **Tự viết local lock Map không dọn dẹp:** có thể rò rỉ lock và mở thêm race.
- **Nhầm @CacheEvict với single-flight:** xóa entry là nguyên nhân miss mới, không phối hợp loader.

## 12. Câu hỏi tự kiểm tra

1. Vì sao khi 10 luồng cùng cache miss một key, cả 10 có thể cùng gọi DB dù cuối cùng chỉ một entry tồn tại?
2. Khác nhau giữa **cache stampede theo một key** và **cache avalanche nhiều key** là gì?
3. **@Cacheable(sync = true)** muốn thay đổi bước nào trong quy trình cache-aside thông thường?
4. Vì sao **sync=true** trong một JVM có ConcurrentMapCache không bảo đảm toàn cluster chỉ tính một lần?
5. Những giới hạn nào của synchronized caching liên quan **unless**, số cache và các annotation khác?
6. Vì sao dùng barrier yêu cầu sáu worker đều vào thân method **synced** sẽ khiến test bị treo?
7. Nếu đổi một Product trong lúc cache đang nạp bản cũ, rủi ro gì vẫn tồn tại dù đã dùng sync=true?
8. Khi nào cần TTL jitter, refresh-ahead hoặc bulkhead thay vì chỉ sync theo key?
9. Tại sao **key = "#p0"** có thể nguy hiểm với method nhận SKU, tenant và currency?
10. Khi loader lỗi, cần kiểm tra điều gì về retry/timeout và cache state?

**Tổng kết:** Nhiều luồng cùng miss một key có thể dẫn tới tính toán lặp và gây đột biến tải. **@Cacheable(sync = true)** là một công cụ phù hợp để yêu cầu *một loader cho cùng key* khi cache provider hỗ trợ, nhưng không thay thế thiết kế key, consistency, xử lý lỗi, giới hạn tài nguyên hay đồng bộ liên process. Hãy kiểm thử bằng concurrency có điều phối, đo số lần loader thật sự chạy và xác nhận hành vi trên provider đang sử dụng.

### Tài liệu chính thức

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Synchronized Caching và @Cacheable(sync): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — @Cacheable Javadoc (sync constraints): https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework — Cache.get(key, Callable): https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework — ConcurrentMapCache Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework — AOP proxying và self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
