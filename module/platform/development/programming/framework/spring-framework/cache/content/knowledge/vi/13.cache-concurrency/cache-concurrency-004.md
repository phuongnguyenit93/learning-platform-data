# Phân biệt an toàn đa luồng của kho với tính nguyên tử của chuỗi thao tác trong Spring Cache

## 1. Bài toán: thread-safe không đồng nghĩa atomic

Khi dùng Spring Cache, người học thường gặp hai câu khẳng định tưởng như giống nhau:

- **Kho cache an toàn đa luồng (thread-safe store):** nhiều thread cùng gọi `get`, `put`, `evict` có thể được backend xử lý theo hợp đồng concurrency của từng thao tác mà không làm hỏng cấu trúc dữ liệu nội bộ.
- **Một chuỗi nghiệp vụ nguyên tử (atomic sequence):** toàn bộ quy trình như `get → tải dữ liệu → put`, hoặc `get → tăng giá trị → put`, phải được bảo vệ như một đơn vị logic không bị các thread khác chen vào làm sai kết quả.

Hai bảo đảm này **khác nhau**. Một `ConcurrentHashMap` có những phép toán đơn lẻ thread-safe, nhưng:

```java
int old = map.get("n");
map.put("n", old + 1);
```

không làm hai lệnh trở thành một phép tăng atomic. Hai luồng có thể đọc cùng số cũ rồi ghi cùng số mới. Kho không bị hỏng, nhưng xảy ra *lost update*.

Tương tự trong Spring: `ConcurrentMapCacheManager` cung cấp cache trên cấu trúc dữ liệu concurrent, nhưng không mặc nhiên bảo vệ nguyên tử cả đường đi **cache miss → chạy phương thức @Cacheable → cache put**. Hai request cùng key có thể đồng thời miss và cùng làm phép tải tốn kém.

**Mục tiêu:** phân biệt thread safety, atomicity theo key và transaction xuyên tài nguyên; nhìn được ba loại race (lost update, duplicate load, stale put sau evict); biết khi nào dùng `compute`, `@Cacheable(sync=true)`, locking, versioning và transaction.

## 2. Ba cấp độ bảo đảm

| Cấp độ | Điều được bảo đảm | Ví dụ | Không thể tự suy ra |
| --- | --- | --- | --- |
| **Thread safety của một operation** | Nhiều luồng truy cập cấu trúc mà không phá hợp đồng của thao tác đó | `ConcurrentHashMap.get/put` | Cả chuỗi `get+put` là nguyên tử |
| **Atomicity của một mapping/key** | Một phép cập nhật logic lên key được thực hiện như đơn vị | `ConcurrentHashMap.compute`, provider có synchronized cache load | Mọi key, mọi cache đều nằm trong transaction |
| **Nhất quán toàn nghiệp vụ** | Các cập nhật database, cache và sự kiện có trạng thái phù hợp theo SLA | DB transaction + invalidation được điều phối | Bảo đảm chỉ nhờ tên `Concurrent` hoặc `sync` |

Cần nói rõ **phạm vi**: một thao tác, một key, một JVM, nhiều node, một cache hay nhiều hệ thống. Không có bảo đảm “atomic” tuyệt đối nếu không nêu phạm vi thao tác nào là atomic.

### 2.1. Interleaving gây lost update

Giả sử `map["n"] = 0`, hai luồng đều muốn tăng 1:

| Thời điểm | Thread A | Thread B | Map |
| --- | --- | --- | --- |
| T0 | — | — | `n=0` |
| T1 | `get("n") → 0` | — | `n=0` |
| T2 | — | `get("n") → 0` | `n=0` |
| T3 | `put("n",1)` | — | `n=1` |
| T4 | — | `put("n",1)` | `n=1` |

Mỗi thao tác của `ConcurrentHashMap` vẫn hoạt động hợp lệ. Sai lầm nằm ở việc **hai thao tác đọc và ghi không được bảo vệ thành một chuỗi**.

Với phép tăng trên một key, Java cung cấp thao tác atomic:

```java
map.compute("n", (key, oldValue) -> oldValue + 1);
```

Hai lần `compute` cùng key sẽ tạo kết quả 2 khi giá trị ban đầu 0. Theo JDK, `ConcurrentHashMap.compute` thực hiện phép remapping một cách atomic cho mapping liên quan. Function cần gọn và **không được cập nhật lại chính map** từ bên trong; tác vụ chậm có thể làm các thread khác chờ.

### 2.2. Thread-safe store không đồng bộ đối tượng value

Nếu cache lưu một `ArrayList` mutable, nhiều luồng cùng lấy instance rồi thêm/xóa phần tử vẫn cần bảo vệ việc mutate List. Backend thread-safe không tự biến value mutable thành thread-safe. Hãy dùng value bất biến hoặc bản sao snapshot khi phù hợp.

## 3. Trong Spring Cache: hai request cùng cache miss

Đoạn minh họa trong service Spring:

```java
@Cacheable(cacheNames = "books")
public Book findById(String id) {
    return repository.findById(id);
}
```

Đây là **mảnh code minh họa**, cần `Book` và `repository` thực tế. Khi key `"B1"` chưa được cache, hai request có thể xen kẽ:

```text
Thread A                   Cache                    Thread B
  |                         |                          |
  |--- get("B1") --------->|                          |
  |<-- miss ---------------|                          |
  |                         |<------- get("B1") -------|
  |                         |-------- miss ----------->|
  |--- query DB             |             query DB ----|
  |--- put("B1",v1) ------->|                          |
  |                         |<------- put("B1",v2) -----|
```

Sơ đồ mô tả **một interleaving có thể xảy ra**: mỗi thread đọc miss trước khi thread kia put. Cache không bị hỏng nhưng có *duplicate computation*, chi phí DB tăng và kết quả cuối có thể phụ thuộc thứ tự put.

Nếu giá trị nguồn thay đổi giữa hai lần đọc, các giá trị `v1` và `v2` khác nhau có thể tạo **stale write**. Bảo đảm thread-safe của `get` và `put` không cho phép suy ra các bước ở giữa là nguyên tử.

### 3.1. Tính năng @Cacheable(sync=true)

```java
@Cacheable(cacheNames = "books", sync = true)
public Book findById(String id) {
    return repository.findById(id);
}
```

Trong Spring Cache, `sync=true` yêu cầu provider hỗ trợ **đồng bộ phép tải một entry cùng key khi đồng thời miss**. Trên implementation hỗ trợ, một thread tính dữ liệu; các thread khác đợi và nhận cùng kết quả được cache. Spring có API `Cache.get(key, Callable)` dành cho kiểu tải này.

Nhưng đây là **hint/khả năng phụ thuộc provider**, không phải phân tán transaction:

- Không ngăn mọi update hoặc evict song song của key.
- Không tự đồng bộ các key khác hoặc hai cache khác nhau.
- Không đồng bộ database và cache.
- Không được suy ra có single-flight xuyên nhiều JVM chỉ vì một JVM với `ConcurrentMapCacheManager` hoạt động đúng.
- Nếu provider không hỗ trợ locking theo kỳ vọng, phải kiểm chứng thực tế hoặc dùng cơ chế khác.

Spring `@Cacheable(sync=true)` cũng có các ràng buộc: **không hỗ trợ `unless`**, **chỉ một cache được chỉ định**, và **không kết hợp cache operation khác trên cùng method**. Đừng dùng `@Cacheable(sync=true, unless="...")` rồi kỳ vọng nó tự xử lý theo ý muốn.

## 4. Ví dụ hoàn chỉnh Java 17+: ba cuộc đua có thể tái hiện

Ví dụ dùng JDK 17+ và `spring-boot-starter-cache` để minh họa:

1. Hai luồng thực hiện `ConcurrentHashMap.get+put`: mất một lần tăng; đổi sang `compute` thì đúng.
2. Hai lời gọi `@Cacheable` trên cùng key: mặc định có hai lần chạy body khi ép cùng miss; với `sync=true` và `ConcurrentMapCacheManager`, còn một lần.
3. Loader đọc bản cũ, một luồng khác update và evict, rồi loader cũ put **sau eviction**: cache chứa bản stale.

Để kết quả ít phụ thuộc timing, chương trình dùng `CountDownLatch` bắt các luồng đến điểm cần quan sát. Nó là bài thực hành trong **một JVM**, không mô phỏng đầy đủ backend phân tán.

### 4.1. Tạo dự án Gradle

Cấu trúc:

```text
cache-concurrency/
  settings.gradle
  build.gradle
  src/main/java/demo/cache/ConcurrencyDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'cache-concurrency'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}

application {
    mainClass = 'demo.cache.ConcurrencyDemo'
}
```

### 4.2. File Java hoàn chỉnh

`src/main/java/demo/cache/ConcurrencyDemo.java`:

```java
package demo.cache;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ConcurrencyDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                    "ordinary", "singleFlight", "direct");
        }

        @Bean
        CachedService cachedService() {
            return new CachedService();
        }
    }

    public static class CachedService {
        private final AtomicInteger ordinaryLoads = new AtomicInteger();
        private final AtomicInteger syncedLoads = new AtomicInteger();
        private final CountDownLatch bothInside = new CountDownLatch(2);

        @Cacheable(cacheNames = "ordinary")
        public String ordinary(String key) {
            int n = ordinaryLoads.incrementAndGet();
            bothInside.countDown();
            await(bothInside, "both ordinary calls entered");
            return "ordinary-" + n;
        }

        @Cacheable(cacheNames = "singleFlight", sync = true)
        public String singleFlight(String key) {
            return "sync-" + syncedLoads.incrementAndGet();
        }

        public int ordinaryCount() {
            return ordinaryLoads.get();
        }

        public int syncCount() {
            return syncedLoads.get();
        }
    }

    private static void await(CountDownLatch latch, String step) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("timeout: " + step);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted: " + step, e);
        }
    }

    private static List<String> inParallel(Callable<String> action)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        try {
            Future<String> a = pool.submit(() -> {
                await(start, "start");
                return action.call();
            });
            Future<String> b = pool.submit(() -> {
                await(start, "start");
                return action.call();
            });
            start.countDown();

            List<String> values = new ArrayList<>();
            values.add(a.get(10, TimeUnit.SECONDS));
            values.add(b.get(10, TimeUnit.SECONDS));
            Collections.sort(values);
            return values;
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }

    private static void lostUpdate() throws Exception {
        ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
        map.put("counter", 0);
        CountDownLatch bothRead = new CountDownLatch(2);

        inParallel(() -> {
            int previous = map.get("counter");
            bothRead.countDown();
            await(bothRead, "both threads read zero");
            map.put("counter", previous + 1);
            return "done";
        });
        System.out.println("getThenPut=" + map.get("counter"));

        map.put("counter", 0);
        inParallel(() -> {
            map.compute("counter", (k, previous) -> previous + 1);
            return "done";
        });
        System.out.println("atomicCompute=" + map.get("counter"));
    }

    private static void latePut(Cache cache) throws Exception {
        cache.clear();
        AtomicInteger source = new AtomicInteger(1);
        CountDownLatch tookSnapshot = new CountDownLatch(1);
        CountDownLatch allowPut = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<?> oldLoader = pool.submit(() -> {
                if (cache.get("item") == null) {
                    int snapshot = source.get();
                    tookSnapshot.countDown();
                    await(allowPut, "release old loader");
                    cache.put("item", snapshot);
                }
            });

            await(tookSnapshot, "snapshot ready");
            source.set(2);
            cache.evict("item");
            allowPut.countDown();
            oldLoader.get(10, TimeUnit.SECONDS);

            System.out.println("sourceVersion=" + source.get());
            System.out.println("cacheVersion="
                    + cache.get("item", Integer.class));
        } finally {
            allowPut.countDown();
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        lostUpdate();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {
            CachedService service = context.getBean(CachedService.class);

            System.out.println("ordinaryValues="
                    + inParallel(() -> service.ordinary("A")));
            System.out.println("ordinaryLoads=" + service.ordinaryCount());

            System.out.println("syncValues="
                    + inParallel(() -> service.singleFlight("A")));
            System.out.println("syncLoads=" + service.syncCount());

            Cache direct = context.getBean(CacheManager.class)
                                  .getCache("direct");
            if (direct == null) {
                throw new IllegalStateException("missing direct cache");
            }
            latePut(direct);
        }
    }
}
```

Chạy từ thư mục `cache-concurrency` với JDK 17+ và Gradle tương thích:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper: `./gradlew run --quiet`; Windows: `gradlew.bat run --quiet`. Các dòng chương trình in ra (ngoại trừ log từ Gradle/framework):

```text
getThenPut=1
atomicCompute=2
ordinaryValues=[ordinary-1, ordinary-2]
ordinaryLoads=2
syncValues=[sync-1, sync-1]
syncLoads=1
sourceVersion=2
cacheVersion=1
```

Danh sách từ hai Future được sort để không phụ thuộc thread hoàn thành trước. Trường hợp `ordinary` sử dụng latch bên trong body: body thứ nhất phải chờ body thứ hai tới nơi, nên hai lời gọi chắc chắn đã qua cache miss trước khi bất kỳ body nào có thể trả kết quả.

Ngược lại, **không** đặt latch chờ cả hai thread cùng vào body của `singleFlight`: khi đồng bộ load hoạt động, chỉ một thread được vào body, thread còn lại chờ entry; chờ hai body sẽ deadlock. Ví dụ dùng `sync=true` đúng với một cache và không có `unless`.

### 4.3. Vì sao kết quả có ý nghĩa?

**`getThenPut=1`:** cả hai thread đọc giá trị 0 trước khi được cho phép put. Hai phép put hợp lệ nhưng chỉ ghi số 1.

**`atomicCompute=2`:** hai phép `compute` cập nhật một mapping theo hợp đồng atomic của `ConcurrentHashMap`.

**`ordinaryLoads=2`:** ở `@Cacheable` mặc định, hai miss cùng key có thể cùng chạy method. Đây là **duplicate load**, không có corruption trong cache store.

**`syncLoads=1`:** `ConcurrentMapCacheManager` và `@Cacheable(sync=true)` xử lý cùng key qua đồng bộ loader. Hai lời gọi nhận cùng `sync-1`, một lần tính.

**`sourceVersion=2` và `cacheVersion=1`:** loader chậm đã giữ snapshot 1, trong khi dữ liệu nguồn nâng lên 2 và có eviction. Sau đó loader vẫn put 1 vào cache; đây là **stale put sau eviction**. Các lệnh đơn `Cache.get`, `Cache.evict` và `Cache.put` không bị lỗi — sai là thứ tự liên hệ giữa chúng không được bảo vệ theo tính nhất quán nghiệp vụ.

Tình huống cuối điều khiển trực tiếp `Cache` để phơi bày thứ tự. Trong ứng dụng thực tế, các race tương tự có thể xảy ra khi các loader, invalidation và update nguồn chạy ở nhiều thread hoặc service; phạm vi thực tế phụ thuộc provider.

## 5. Những gì @Cacheable(sync=true) giải quyết — và không giải quyết

Tính năng `sync=true` hữu ích khi:
- Một key trống bị nhiều request đồng thời truy vấn.
- Phép tải tốn nhiều I/O/CPU nên duplicate load gây lãng phí.
- Backend cache đã xác nhận hỗ trợ synchronized loading với phạm vi mong muốn.

Nhưng nó **không** tạo transaction toàn cục. Ngay cả nếu chỉ một thread load mỗi key, vẫn phải xét:
- Một request khác sửa dữ liệu nguồn và evict cache trong lúc load.
- Một cache region khác cần cập nhật đồng thời.
- Hai key phụ thuộc nhau phải nhất quán như một aggregate.
- Những instance khác không chia sẻ cùng cơ chế khóa.
- Một loader bị timeout, bị hủy, trả null hoặc ném exception.
- Provider có caching bất đồng bộ, delayed eviction hoặc khả năng serialization khác.

`Cache.get(key, Callable)` là một API tiện để yêu cầu provider lấy hoặc load. Mức đồng bộ và khả năng atomic cụ thể của provider cần được kiểm tra; không tự coi mọi implementation đều tương đương `ConcurrentHashMap.computeIfAbsent`.

## 6. Những cơ chế thay thế cần chọn theo phạm vi

| Nhu cầu | Lựa chọn | Cần xác minh |
| --- | --- | --- |
| Đọc/ghi các mapping độc lập không hỏng cấu trúc | `ConcurrentHashMap`, cache provider concurrent | Thread safety của từng thao tác |
| Tăng/cập nhật một key trong cùng JVM | `compute`, `merge`, CAS, atomic variable phù hợp | Atomicity của mapping/biến, không phải transaction DB |
| Tránh cùng lúc tải lại một key | `@Cacheable(sync=true)` khi provider hỗ trợ | Scope đồng bộ, single cache, `unless` |
| Cần bảo vệ chuỗi get-check-update trong cùng process | `synchronized`/`ReentrantLock` hoặc keyed lock bao quanh **toàn chuỗi** | Lỗi lock, contention, deadlock, phạm vi JVM |
| Tránh loader cũ ghi đè version mới | Versioned cache keys, generation/epoch, conditional put khi provider hỗ trợ | Version phải được cập nhật/đọc nhất quán |
| Cần nguyên tử giữa nhiều hàng database | Transaction và optimistic/pessimistic locking | Isolation, retry và rollback |
| Cache phân tán nhiều node | Atomic script/CAS/lock phân tán với TTL/fencing nếu thật sự cần | Mất lock, network partition, retry |
| Xóa cache sau database commit | Transaction-aware cache, after-commit event hoặc outbox | Eviction race với loader đang chạy |

### 6.1. Vì sao đặt synchronized lên body không chắc đủ?

Nếu chỉ viết:

```java
@Cacheable("books")
public synchronized Book load(String id) {
    return repository.findById(id);
}
```

Đây là đoạn code minh họa. `synchronized` bao quanh **body method**; nhưng kiểm tra cache miss diễn ra **trước khi** Spring gọi body qua proxy. Hai request vẫn có thể cùng quan sát miss, rồi lần lượt đi vào body `synchronized` và cả hai vẫn thực hiện truy vấn. Muốn bảo vệ cả lookup và tính toán, khóa phải bao quanh **toàn đường cache**, hoặc sử dụng provider hỗ trợ `sync=true` phù hợp.

### 6.2. Dùng compute/merge cho một mapping

```java
// Mảnh code minh họa: counts là ConcurrentHashMap<String, Integer>.
counts.merge("A", 1, Integer::sum);
counts.compute("B", (key, old) -> old == null ? 1 : old + 1);
```

Đây là các phép cập nhật phù hợp khi trạng thái cần bảo vệ **nằm trong một mapping của map**. Tránh đặt truy vấn chậm, cập nhật chính map hoặc gọi đệ quy vào mapping function — có thể gây chặn, lỗi hoặc deadlock.

Nếu cần thay đổi **hai key cùng nhau**, atomicity per-key vẫn chưa đủ; phải thiết kế critical section hoặc transaction cho toàn bộ aggregate liên quan.

### 6.3. Key có version/generation

Giả sử trước update, cache key là `product:42:v7`; sau update, phiên bản nguồn tăng thành `v8` và request mới dùng key `product:42:v8`. Loader cũ chỉ có thể ghi vào namespace phiên bản 7, không làm nhiễm giá trị của key phiên bản 8.

Chiến lược này giảm race giữa load cũ và invalidation, nhưng cần bảo đảm việc xác định version hiện tại đúng và có chính sách TTL/xóa entry cũ. Versioning không tự giải quyết mọi vấn đề consistency ở database.

## 7. Race giữa cache và database

Trường hợp cập nhật dữ liệu rồi evict cache vẫn có thể gặp:

```text
T1: cache miss K
T1: đọc dữ liệu nguồn V1, bắt đầu tính chậm
T2: cập nhật nguồn thành V2
T2: evict K
T1: put K = V1 sau eviction
T3: cache hit K = V1  (stale)
```

Evict “sau commit” giúp tránh một số trạng thái không nhất quán, nhưng nếu cần freshness mạnh **với mọi interleaving**, phải xét cả loader đang chạy, version, thứ tự ghi và provider.

Có thể dùng versioned key, kiểm tra generation trước khi put, điều phối critical section chung giữa read/update hoặc cơ chế consistency của data store. Với cache có TTL ngắn và dữ liệu chỉ phục vụ gợi ý, hệ thống có thể chấp nhận một khoảng stale; với giá/tồn kho/quyền truy cập, SLA phải được định nghĩa chặt chẽ.

Không biến cache thành nguồn phân quyền duy nhất. Cache hit vẫn cần đúng phạm vi tenant/user và kiểm tra quyền phù hợp.

## 8. Các hiểu lầm thường gặp

| Kết luận sai | Thực tế |
| --- | --- |
| “Map thread-safe nên get+put atomic.” | Hai thao tác riêng có thể bị xen ngang. |
| “@Cacheable mặc định chỉ cho một thread load mỗi key.” | Hai request miss cùng key có thể chạy body hai lần. |
| “sync=true là một distributed lock.” | Phụ thuộc provider và phạm vi; không tự bảo đảm nhiều node. |
| “AtomicInteger làm mọi transaction atomic.” | Chỉ thao tác trên biến atomic theo hợp đồng. |
| “Evict đã xong nên loader cũ không thể put.” | Loader đang chạy vẫn có thể hoàn tất và ghi stale. |
| “Cache thread-safe nên value mutable cũng thread-safe.” | Mutation của object có cơ chế đồng bộ riêng. |
| “Đã dùng DB transaction thì cache luôn đồng bộ.” | Cần phối hợp commit, invalidation, race và provider. |
| “Thread.sleep khiến test race chắc chắn xảy ra.” | Sleep không ép được thứ tự; dùng barrier/latch có timeout. |

## 9. Checklist kiểm thử thực tế

1. **Xác định phạm vi bảo đảm:** một mapping, một key, một process hay nhiều node?
2. **Hai miss một key:** ép đồng thời bằng latch; đo số lần body chạy khi `sync=false` và `sync=true`.
3. **Hai key khác nhau:** kiểm tra đồng bộ một key không biến thành khóa toàn cục không cần thiết.
4. **Read-modify-write:** buộc hai thread đọc cùng giá trị trước khi put; so sánh với `compute/merge`.
5. **In-flight loader:** chặn sau khi đọc nguồn, cập nhật nguồn + evict, cho loader put và kiểm tra stale.
6. **Timeout/exception:** loader lỗi có để lại entry không? Thread chờ có được giải phóng hoặc retry không?
7. **Nhiều vùng cache:** cập nhật một vùng có làm các vùng phụ thuộc stale không?
8. **Transaction:** commit/rollback cùng eviction có thời điểm và visibility thế nào?
9. **Nhiều JVM:** thử trên cùng backend thật, không chỉ in-memory cache trên một instance.
10. **Giám sát:** tỷ lệ hit/miss, duplicate DB load, contention, p95/p99 latency, lỗi backend và TTL.

Trong integration test, luôn gọi service qua **Spring bean/proxy**. Gọi `new CachedService()` hoặc tự gọi `this.ordinary(...)` bên trong target sẽ không chứng minh annotation cache hoạt động ở chế độ proxy mặc định.

## 10. Câu hỏi tự kiểm tra

**Q1.** Hai thread cùng `ConcurrentHashMap.get("n")` rồi `put("n",old+1)`; map có hỏng cấu trúc và kết quả có chắc tăng 2 không?

**Đáp:** Không hỏng do truy cập hợp lệ; nhưng không chắc tăng 2 vì có thể lost update.

**Q2.** `compute` giải quyết được gì?

**Đáp:** Atomic remapping cho mapping trong `ConcurrentHashMap`; không tự transaction với database hay hai cache.

**Q3.** Vì sao hai request cùng `@Cacheable` có thể tải một key hai lần?

**Đáp:** Cả hai có thể cache miss trước khi có cache put; Spring không mặc định khóa toàn chuỗi load.

**Q4.** `sync=true` có đảm bảo single-flight ở mọi pod và mọi cache không?

**Đáp:** Không. Phải xác minh provider, phạm vi và giới hạn của tính năng.

**Q5.** Có thể stale sau khi vừa evict không?

**Đáp:** Có. Loader cũ có thể put sau evict; cần điều phối hoặc versioning nếu yêu cầu nhất quán chặt.

**Q6.** Có nên đặt `synchronized` trên body rồi kết luận đã bảo vệ cache lookup không?

**Đáp:** Không. Cache lookup thường diễn ra ở proxy trước body, nên hai request có thể cùng miss.

## 11. Ghi nhớ

- **Thread-safe store ≠ atomic sequence ≠ transaction toàn nghiệp vụ.**
- `ConcurrentHashMap.get+put` có thể mất cập nhật; `compute/merge` thích hợp cho phép cập nhật atomic theo key.
- `@Cacheable` mặc định có thể duplicate load; `sync=true` giúp khi provider hỗ trợ, nhưng không phải bảo đảm nhất quán phân tán.
- Eviction không làm mất khả năng loader cũ ghi stale sau đó.
- Hãy chứng minh bằng interleaving có điều khiển, và thiết kế tính nhất quán theo yêu cầu dữ liệu thực tế.

### Tài liệu chính thức

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — @Cacheable.sync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Framework — Cache API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework — ConcurrentMapCache](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html)
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
