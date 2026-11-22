# Thiết kế xử lý để việc tính toán lặp không gây sai nghiệp vụ — Spring Cache và đồng thời

## 1. Tình huống gốc: cùng cache key nhưng nhiều request cùng miss

Trong Spring Framework, `@Cacheable` giúp bỏ qua thân phương thức nếu đã có giá trị cache cho key được yêu cầu. Nhưng khi **hai hoặc nhiều request đồng thời** cùng nhìn thấy cache miss, Spring Cache abstraction **mặc định không khóa toàn bộ chuỗi get → compute → put**. Các request có thể đều chạy cùng một loader:

~~~text
             Thread A                 Thread B                 Cache
t0       get("sku-7")              get("sku-7")               miss
t1       cache miss                cache miss                 trống
t2       compute("sku-7")          compute("sku-7")           trống
t3       trả kết quả 100          trả kết quả 100            trống
t4       put("sku-7",100)          put("sku-7",100)           100
~~~

Đây là **duplicate computation** trên concurrent cache miss, thường liên quan *cache stampede*. Một entry cuối cùng có thể đúng nhưng **không chứng minh method chỉ chạy một lần**.

Phân biệt hai lớp hậu quả:

- **Trùng tính toán mà không sai nghiệp vụ:** hai lần chuyển đổi, tổng hợp dữ liệu hoặc đọc một snapshot bất biến, không gây side effect; chủ yếu tốn tài nguyên.
- **Trùng tính toán gây sai nghiệp vụ:** method trừ hàng tồn, charge thanh toán, tạo voucher, phát điểm, gửi notification hoặc gọi dịch vụ có side effect. Hai lần thực thi có thể làm tăng hiệu ứng nghiệp vụ thành hai lần, bất kể cache cuối cùng chứa một kết quả.

**Nguyên tắc thiết kế:** làm cho **việc thực thi lặp không gây sai**, sau đó mới giảm số lần tính vì mục tiêu hiệu năng. Đừng đảo ngược hai nhiệm vụ.

## 2. Cache không bảo đảm exactly-once

Ví dụ không nên dùng:

~~~java
// SAI: cache miss/retry có thể làm giao dịch thanh toán xảy ra nhiều lần.
@Cacheable(cacheNames = "payments", key = "#p0")
public Receipt charge(String orderId) {
    return paymentGateway.charge(orderId);
}
~~~

Đây là mã minh họa ứng dụng Spring, chưa đầy đủ kiểu/bean. Nếu hai node cùng miss, entry hết TTL, cache provider gián đoạn hoặc request được retry, `charge()` có thể được gọi lại. `@Cacheable` không phải cơ chế chống double payment.

Thiết kế phù hợp hơn:

~~~text
POST /orders/{id}/pay
 → PaymentCommandService.pay(orderId, idempotencyKey)
 → authorization + kiểm tra trạng thái
 → idempotency record/unique constraint trong store bền vững
 → gọi payment provider theo idempotency contract
 → lưu kết quả nghiệp vụ, reconciliation khi lỗi
 → invalidation cache đọc sau commit theo policy

GET /orders/{id}
 → OrderQueryService.findById(id)
 → @Cacheable chỉ cho truy vấn đọc có thể tính lại
~~~

Cache là bản sao tăng tốc, **không phải bằng chứng có bao nhiêu giao dịch đã thực hiện**.

## 3. Pure, idempotent và single-flight khác nhau

| Cơ chế | Ý nghĩa | Bảo vệ điều gì |
|---|---|---|
| **Pure computation** | Cùng input và snapshot cho cùng output, không có side effect quan sát được | Chạy lặp không tự tạo thêm nghiệp vụ |
| **Idempotent command** | Cùng logical request thực hiện lại không nhân đôi hiệu ứng cuối cùng | Retry, duplicate delivery, gửi trùng |
| **Atomic update** | Update và điều kiện có phạm vi nguyên tử đúng | Tránh read-modify-write race |
| **Single-flight** | Chia sẻ một phép tính đang diễn ra cho cùng key | Giảm tính trùng trong một phạm vi phối hợp |
| **`@Cacheable(sync=true)`** | Nhờ cache provider đồng bộ việc load key | Giảm duplicate cache load nếu provider hỗ trợ |
| **Exactly-once effect** | Hiệu ứng business chỉ có một lần cho một operation | Cần contract/state/constraint bền vững, không do cache quyết định |

Ví dụ phép toán chỉ tính giá trị:

~~~java
public long calculateVat(long amountVnd, int rateBasisPoints) {
    return Math.multiplyExact(amountVnd, rateBasisPoints) / 10_000L;
}
~~~

Chạy hai lần không tạo đơn, trừ tồn kho hay gửi thanh toán. Đây là ví dụ thuần Java; quy tắc làm tròn/giới hạn vẫn cần theo yêu cầu nghiệp vụ thật.

Ngược lại, `repository.incrementRewardPoints(userId, 10)` có side effect. Dù hai request trả về cùng số điểm từ cache, ledger có thể đã bị cộng hai lần.

**Một loader chỉ đọc vẫn có rủi ro stale result:** nếu nguồn dữ liệu đổi giữa hai lần tính, kết quả cũ có thể được put sau kết quả mới. Cần versioning/invalidation/TTL khi freshness là yêu cầu.

## 4. Lỗi check-then-act không được sửa bằng cache

Giả sử stock có một đơn vị:

~~~text
Request A: SELECT quantity → 1
Request B: SELECT quantity → 1
A: if quantity > 0 → tiếp tục
B: if quantity > 0 → tiếp tục
A: trừ một đơn vị
B: trừ một đơn vị
=> có thể xác nhận hai đơn hàng cho một đơn vị tồn kho
~~~

Nếu lấy stock từ cache, hai request càng dễ cùng nhìn bản dương đã cũ. **Invariant phải được thực thi ở nguồn dữ liệu có thẩm quyền**, chẳng hạn cập nhật có điều kiện:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = :sku
  AND quantity >= 1;
~~~

Trong transaction phù hợp, kiểm tra **số dòng bị update**; chỉ xem là giữ được một đơn vị khi kết quả bằng 1. Nếu tạo đơn và trừ hàng liên quan nhiều bảng/service, cần thiết kế transaction/workflow cùng constraint hoặc saga/bù phù hợp.

Các cơ chế khác: optimistic locking với cột version, row lock, unique constraint, state transition có điều kiện. `@Transactional` tự nó không làm mọi kiểu `SELECT` rồi `UPDATE` an toàn; `synchronized` Java chỉ khóa trong một JVM/object, không chặn các node khác.

## 5. @Cacheable bình thường không khóa loader

~~~java
@Cacheable(cacheNames = "reports", key = "#p0")
public Report buildReport(String reportId) {
    return reportRepository.calculate(reportId);
}
~~~

Đây là mã minh họa tích hợp Spring, cần `@EnableCaching`, `CacheManager` và các domain bean. Trên cache miss, Spring chạy method và lưu kết quả. Khi hai luồng cùng miss, **cả hai có thể gọi `calculate`**.

Cách đó vẫn hợp lệ nếu loader:
- chỉ đọc hoặc tính toán không side effect;
- đúng với snapshot được dùng;
- không tạo resource duy nhất;
- không phụ thuộc vào việc chỉ gọi một lần;
- xử lý được retry sau lỗi.

Không gắn business command như payment/stock/redeem ở đây rồi dựa vào cache để tránh gọi trùng.

## 6. @Cacheable(sync=true): giảm tính trùng nhưng không bảo đảm nghiệp vụ

Có thể yêu cầu đồng bộ tải cache:

~~~java
@Cacheable(cacheNames = "reports",
           key = "#p0",
           sync = true)
public Report buildReport(String reportId) {
    return reportRepository.calculate(reportId);
}
~~~

Khi provider hỗ trợ, Spring có thể dùng contract `Cache.get(key, Callable)` để phối hợp các luồng tải cùng key, giảm số lần loader chạy. Đây là **gợi ý cho cache provider**, không phải distributed lock hoặc exactly-once command.

Theo Javadoc Spring, `@Cacheable(sync=true)` có **ba giới hạn**:

1. **Không hỗ trợ `unless`**.
2. Chỉ được khai báo **một vùng cache** cho operation đồng bộ.
3. Không được kết hợp một cache-related operation khác trên cùng method.

Ví dụ **không hợp lệ**:

~~~java
// Không hợp lệ: sync=true kết hợp unless.
@Cacheable(cacheNames = "reports",
           sync = true,
           unless = "#result == null")
public Report invalidExample(String reportId) {
    return reportRepository.calculate(reportId);
}
~~~

Phạm vi đồng bộ cần được kiểm chứng:

- Các luồng trong **một JVM** với provider hỗ trợ có thể được phối hợp theo key.
- Hai JVM với **cache cục bộ riêng** không chia sẻ lock; hai loader vẫn có thể chạy.
- Có Redis hoặc cache phân tán **không mặc nhiên đồng nghĩa** có distributed locking cho loader. Kiểm tra provider cụ thể.
- TTL, eviction, loader throw exception, backend unavailable hoặc các lần miss về sau vẫn có thể làm loader chạy lại.

**`sync=true` là tối ưu hóa cho một loader vốn đã an toàn chạy lặp**, không phải cách sửa một command thiếu idempotency.

## 7. Java 17 độc lập: chứng minh duplicate side effect

Ví dụ sau **mô phỏng** cache bằng `ConcurrentHashMap`; không dùng Spring annotation thật, không gọi hệ thống thanh toán hay database. `CountDownLatch` buộc hai thread đều thấy cache miss trước khi tiếp tục, để kết quả không phụ thuộc may rủi scheduler.

Tạo file **`ConcurrentCacheSafetyDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentCacheSafetyDemo {
    record Stats(int loads, int sideEffects, int cachedValue) {}

    private static Stats race(boolean withSideEffect) throws Exception {
        ConcurrentMap<String, Integer> cache = new ConcurrentHashMap<>();
        AtomicInteger loads = new AtomicInteger();
        AtomicInteger sideEffects = new AtomicInteger();
        CountDownLatch bothSawMiss = new CountDownLatch(2);

        Callable<Integer> job = () -> {
            Integer hit = cache.get("sku-7");
            if (hit != null) {
                return hit;
            }
            bothSawMiss.countDown();
            bothSawMiss.await();
            loads.incrementAndGet();
            if (withSideEffect) {
                sideEffects.incrementAndGet();
            }
            cache.putIfAbsent("sku-7", 100);
            return cache.get("sku-7");
        };

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> first = pool.submit(job);
            Future<Integer> second = pool.submit(job);
            if (first.get() != 100 || second.get() != 100) {
                throw new IllegalStateException("unexpected result");
            }
            return new Stats(loads.get(), sideEffects.get(), cache.get("sku-7"));
        } finally {
            pool.shutdownNow();
        }
    }

    private static Stats singleFlight() throws Exception {
        ConcurrentMap<String, Integer> cache = new ConcurrentHashMap<>();
        AtomicInteger loads = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);

        Callable<Integer> job = () -> {
            start.await();
            return cache.computeIfAbsent("sku-7", key -> {
                loads.incrementAndGet();
                return 100;
            });
        };

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> first = pool.submit(job);
            Future<Integer> second = pool.submit(job);
            start.countDown();
            if (first.get() != 100 || second.get() != 100) {
                throw new IllegalStateException("unexpected result");
            }
            return new Stats(loads.get(), 0, cache.get("sku-7"));
        } finally {
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        Stats unsafe = race(true);
        Stats pure = race(false);
        Stats guarded = singleFlight();

        System.out.printf("unsafe: loads=%d, sideEffects=%d, cached=%d%n",
                unsafe.loads(), unsafe.sideEffects(), unsafe.cachedValue());
        System.out.printf("pure: loads=%d, sideEffects=%d, cached=%d%n",
                pure.loads(), pure.sideEffects(), pure.cachedValue());
        System.out.printf("singleFlight: loads=%d, sideEffects=%d, cached=%d%n",
                guarded.loads(), guarded.sideEffects(), guarded.cachedValue());
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac --release 17 ConcurrentCacheSafetyDemo.java
java ConcurrentCacheSafetyDemo
~~~

Stdout **chính xác**:

~~~text
unsafe: loads=2, sideEffects=2, cached=100
pure: loads=2, sideEffects=0, cached=100
singleFlight: loads=1, sideEffects=0, cached=100
~~~

Kết luận từ chương trình:

- Trường hợp `unsafe`: cả hai luồng đều miss và thực hiện side effect mô phỏng **2 lần**, mặc dù `putIfAbsent` chỉ duy trì một entry.
- Trường hợp `pure`: cũng tính hai lần nhưng **không** có side effect, nên chỉ lãng phí công tính.
- Trường hợp `singleFlight`: `computeIfAbsent` của **cùng ConcurrentHashMap trong một JVM** phối hợp tạo mapping; loader thành công chỉ thực thi một lần.
- Không nên đưa logic business side effect vào mapping function rồi giả định nó thành exactly-once. Map trong Java không cung cấp persistent transaction hay distributed lock.

## 8. Thiết kế loader an toàn khi chạy lại

~~~java
@Service
public class PriceQueryService {
    private final PriceRepository repository;

    public PriceQueryService(PriceRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "priceSnapshots",
               key = "#p0",
               sync = true)
    public PriceSnapshot getSnapshot(String sku) {
        return repository.fetchSnapshot(sku);
    }
}
~~~

Đây là mã minh họa Spring, cần `PriceSnapshot`, `PriceRepository` và imports theo project.

Checklist loader:

1. **Không mutate state nghiệp vụ.** Không tạo invoice, charge payment hoặc cấp voucher trong phương thức đọc cache.
2. **Key bao hàm đủ ngữ cảnh**: tenant, currency, locale, ngày hiệu lực, role, filter và version nếu ảnh hưởng kết quả.
3. **Freshness policy rõ ràng**: TTL, invalidation sau commit, versioned key hoặc snapshot phù hợp.
4. **Trả về dữ liệu không bị caller sửa chung**: dùng immutable DTO/record hoặc defensive copy.
5. **Chạy lại được sau lỗi**: cache backend timeout hoặc loader throw có thể khiến lần sau tính lại.
6. **Không lẫn metrics với business state**: số lần loader chạy không phải số lần thực hiện giao dịch.
7. **Giới hạn tài nguyên** khi cache stampede xảy ra: timeout, rate-limit, bulkhead và query budget.

Một method tên `getSomething()` chưa chắc pure: nó có thể gọi API có phí, làm thay đổi quota hoặc gửi event có ý nghĩa nghiệp vụ. Phải xem contract thật của dependency.

## 9. Side effect cần idempotency key và trạng thái bền vững

Với payment/redeem/command, dùng khóa định danh **logical operation** thay vì cache key để chống duplicate:

~~~text
Client → POST /orders/O-7/pay
             idempotencyKey=PAY-7
        |
        v
     Auth + validate payload
        |
        v
     DB UNIQUE(tenant_id, idempotency_key)
        |
        +-- COMPLETED cùng payload → trả kết quả đã lưu
        +-- PROCESSING            → trả trạng thái/chờ theo chính sách
        +-- key khác payload      → từ chối rõ
        +-- key mới               → reserve operation bền vững
                                        |
                                        v
                               gọi payment provider theo
                               idempotency contract của họ
                                        |
                                        v
                               lưu result/status + reconcile
                                        |
                                        v
                               invalidate cache truy vấn
~~~

**Không có transaction DB đơn lẻ nào có thể tự atomic cùng một HTTP call tới payment provider.** Nếu service crash sau khi provider đã xử lý nhưng trước khi lưu `COMPLETED`, cần đối soát hoặc retry theo idempotency contract của provider, không gửi lại một charge mới vô điều kiện.

Chi tiết phải thiết kế:
- **Uniqueness** ở DB hoặc nguồn trạng thái bền vững; `SELECT` rồi `INSERT` không có unique constraint vẫn race.
- Key có **phạm vi tenant và operation**; cùng key nhưng payload khác phải báo lỗi hoặc chính sách xác định.
- Lưu kết quả cho retry, xử lý trạng thái đang chạy, timeout, crash và reconciliation.
- TTL của idempotency record theo hợp đồng retry; **khác** TTL của cache kết quả đọc.
- Provider hỗ trợ idempotency thế nào, có trả result cũ hay không, thời gian giữ key bao lâu.

Cache có thể tăng tốc đọc trạng thái operation nhưng **không thay thế hàng rào duy nhất bền vững**.

## 10. Database bảo vệ invariant nào?

| Bất biến | Cơ chế phù hợp | Vì sao cache không đủ |
|---|---|---|
| Mỗi idempotency key chỉ có một operation | Unique constraint + trạng thái bền vững | Miss, expire, eviction, multi-node |
| Stock không âm | Atomic conditional UPDATE/lock/isolation | Hai request có thể cùng thấy stock dương |
| Một voucher chỉ redeem một lần | Unique redemption record/compare-and-swap | Cache put không atomic với DB |
| Không ghi đè bản mới bằng dữ liệu cũ | Optimistic version/conditional write | Last writer wins có thể stale |
| Message không gây side effect trùng | Transactional outbox + consumer idempotency | Message có thể được gửi lại |
| Chỉ cấp một mã định danh duy nhất | Sequence/unique key | Cache có thể mất hoặc bị rebuild |

`@Transactional` giúp xác định transaction boundary, nhưng không tự áp đặt mọi invariant. Thiết kế isolation, constraint, conditional update hoặc row lock theo hợp đồng nghiệp vụ.

Không xem `synchronized` hoặc `ReentrantLock` trong một service instance là hàng rào toàn cụm; server khác vẫn có thể ghi cùng DB.

## 11. Distributed lock không đồng nghĩa exactly-once

Distributed lock/lease có thể giảm contention, nhưng vẫn có các sự cố:

- Worker A giữ lease rồi bị pause; lease hết hạn, B giành được lock.
- A tỉnh lại và ghi kết quả trễ dù không còn quyền.
- A gọi external API thành công rồi crash trước khi lưu local state.
- Retry không biết thao tác trước đã hoàn tất hay chưa.

Với update nghiêm ngặt, cần **fencing token hoặc monotonic version** kiểm soát write tại nguồn, cộng idempotency state và reconciliation. Distributed lock là công cụ hỗ trợ, không nên là điểm bảo vệ business invariant duy nhất.

## 12. Tối ưu cache stampede sau khi đúng nghiệp vụ

| Kỹ thuật | Tác dụng | Giới hạn |
|---|---|---|
| `@Cacheable(sync=true)` | Phối hợp loader cùng key khi provider hỗ trợ | Không bảo đảm liên JVM, giới hạn annotation |
| Single-flight per key | Chia sẻ `Future` đang tính | Thường local; xử lý timeout/cleanup |
| TTL jitter | Tránh nhiều key hết hạn đồng loạt | Không triệt tiêu race trên một key |
| Cache warming | Nạp dữ liệu trước đỉnh tải | Có thể lãng phí và nạp stale |
| Stale-while-revalidate | Tạm trả bản cũ, refresh trong nền | Chỉ khi nghiệp vụ chấp nhận stale |
| Bulkhead/rate limit | Bảo vệ DB/API khỏi burst | Tăng latency hoặc từ chối request |
| Versioned key | Tách phiên bản dữ liệu | Cần chính sách tiến version/cleanup |

**Lỗi loader và null:** loader throw có thể được gọi lại, không nên giả định exception được cache như giá trị thành công. `sync=true` không cho `unless` nên cách lưu null/empty phụ thuộc CacheManager/provider; phải test rõ negative caching. Cache miss liên tục khi “không tìm thấy” cũng có thể gây stampede.

## 13. Key sai gây trả nhầm dữ liệu ngay cả khi đã sync

Ví dụ giá theo tenant, SKU và currency:

~~~java
@Cacheable(cacheNames = "prices", sync = true)
public PriceSnapshot getPrice(String tenant, String sku, String currency) {
    return repository.fetchPrice(tenant, sku, currency);
}
~~~

Mặc định với nhiều tham số, Spring dùng `SimpleKey` chứa các tham số. Nếu thay bằng `key="#p1"` (chỉ SKU), hai tenant có cùng SKU nhưng khác giá có thể dùng chung entry sai; `sync=true` còn khiến các luồng chờ và dùng chung kết quả sai đó.

Key tự nối chuỗi như `tenant + ":" + sku` cần tránh collision nếu input có thể chứa dấu phân cách; cân nhắc key object bất biến hoặc generator chuẩn hóa và serializer phù hợp. Authorization vẫn phải xử lý riêng, không dùng cache name/key để thay thế kiểm tra quyền truy cập.

## 14. Pure loader vẫn có thể ghi bản cũ sau bản mới

~~~text
t0  Request A cache miss, đọc snapshot version 10
t1  Request B cập nhật DB thành version 11, commit
t2  Request B evict cache
t3  A hoàn thành chậm và put version 10
t4  Request C cache hit nhưng thấy version 10 đã cũ
~~~

`sync=true` chủ yếu phối hợp loader của một key, **không kết nối nguyên tử với database transaction**. Khi correctness đòi freshness:

- Invalidate sau commit với thứ tự rõ ràng.
- Dùng versioned cache key/generation hoặc compare version trước khi put nếu hệ thống hỗ trợ.
- Có TTL và reconciliation nếu chấp nhận stale giới hạn.
- Test race giữa writer và slow loader; không chỉ test hai reader đồng thời.

`@CacheEvict` mặc định xóa sau khi method được cache interceptor gọi hoàn tất thành công, **không mặc nhiên bảo đảm DB đã commit** trong mọi cấu hình advice. `@CachePut` luôn chạy method rồi cache kết quả, **không** bảo vệ command khỏi chạy nhiều lần.

## 15. Hai JVM và khóa cục bộ

~~~text
Client A → Pod A → local cache miss → loader chạy
Client B → Pod B → local cache miss → loader chạy
                                 |
                             shared DB
~~~

Hai JVM dùng `ConcurrentMapCacheManager` riêng vẫn có thể mỗi node tính một lần dù `sync=true`. Cache phân tán không mặc nhiên cung cấp distributed single-flight; kiểm tra contract thực tế của provider. Unit test hai thread cùng JVM **không chứng minh** an toàn production multi-node.

## 16. Kiểm thử đồng thời theo bốn lớp

**Tính trùng an toàn:** dùng `CountDownLatch`/barrier tạo hai cache miss cùng key, kiểm tra hai kết quả, số lần loader và không có side effect.

**Spring sync:** test bằng Spring bean đi qua proxy, provider thật, `@Cacheable(sync=true)`, đo loader invocation count. Thử exception, null, TTL, eviction. Một provider pass không chứng minh mọi provider đều giống nhau.

**Business command:** hai request đồng thời cùng idempotency key và payload, xác minh chỉ một business effect và một logical operation ở nguồn bền vững. **Xóa cache rồi thử lại**: invariant vẫn phải đúng. Thử retry sau timeout, crash sau external call, payload khác cùng key.

**Stale và multi-node:** cho A giữ version cũ, B commit bản mới và evict, A put trễ. Test nhiều pod, cache backend lỗi, transaction rollback, message replay và distributed lease expired.

Quan sát metrics riêng: cache hit/miss, loader invocation, business side-effect count, constraint violation/deduplication, stale reads. **Số cache put không phải số payment đã tạo**.

## 17. Những lỗi phổ biến

- “`@Cacheable` làm method chỉ chạy một lần.” **Sai** khi miss đồng thời, TTL, eviction, retry và restart.
- “`sync=true` là distributed mutex.” **Sai** nếu provider không cam kết.
- “`putIfAbsent` ngăn side effect.” **Sai** nếu side effect xảy ra trước cache put.
- “Hai kết quả bằng nhau nghĩa là không có double charge.” **Sai** nếu bên ngoài đã thực thi hai lần.
- “`synchronized` bảo vệ nhiều pod.” **Sai**: chỉ trong cùng JVM/object.
- “`@Transactional` mặc nhiên chặn double-sell.” **Sai** khi thiếu isolation/constraint/conditional update đúng.
- “Pure loader làm cache luôn mới.” **Sai** khi dữ liệu nguồn đổi hoặc put trễ.
- “Chỉ SKU là key đủ cho multi-tenant.” **Sai** nếu còn khác giá/quyền/locale.
- “Unit test hai thread pass là an toàn cluster.” **Sai**.
- “Cache unavailable được phép phá invariant nghiệp vụ.” **Sai**: correctness phải độc lập cache.

## 18. Checklist trước khi đưa vào production

1. Nếu method chạy lại 10 lần, **business state có bị thay đổi nhiều lần** không?
2. Nếu có side effect, đã tách command và bảo vệ idempotency bằng record bền vững chưa?
3. Invariant đã được mã hóa bởi DB constraint, conditional write hay lock/transaction phù hợp chưa?
4. Key có đầy đủ tenant, currency, role, version và các input ảnh hưởng output không?
5. Provider có hỗ trợ `sync=true` theo phạm vi JVM hay cluster nào?
6. Có vi phạm giới hạn `sync=true`: nhiều cache, `unless`, kết hợp operation không?
7. Có xử lý null/exception/retry, hết TTL và cache provider down không?
8. Có chiến lược chống stale put sau commit/invalidation không?
9. Test có chạy hai luồng và hai instance, có fault injection không?
10. Metrics có phân biệt loader count với **business effect thực** không?

**Quy tắc ngắn:** *Thiết kế chạy lặp vẫn đúng nghiệp vụ; sau đó mới thiết kế chạy ít lần hơn.*

## 19. Tự kiểm tra

**Câu 1.** Hai cache miss cùng chạy một phép tính pure và ra cùng kết quả. Vấn đề chính là gì?

**Câu 2.** `sync=true` có bảo đảm charge payment đúng một lần ở nhiều JVM không?

**Câu 3.** Dùng `@Cacheable(sync=true, unless="#result == null")` có hợp lệ không?

**Câu 4.** Với hai pod dùng local cache riêng, `sync=true` có bảo đảm một loader cho cả cụm?

**Câu 5.** Vì sao `putIfAbsent` sau khi trừ tồn kho không thể ngăn trừ hai lần?

**Câu 6.** Hai transaction cùng thấy stock=1. Làm sao bảo vệ invariant?

**Câu 7.** Vì sao idempotency record phải bền vững hơn cache?

**Câu 8.** Pure loader đọc version 10 nhưng put sau khi version 11 đã commit có thể gây gì?

**Đáp án:**

1. **Lãng phí compute/DB**, không nhất thiết sai nghiệp vụ.
2. **Không**. Cần idempotency state, provider contract và DB constraint.
3. **Không**, `sync=true` không hỗ trợ `unless`.
4. **Không**, mỗi JVM sở hữu cache/lock riêng.
5. Vì side effect xảy ra trước put; cache chỉ kiểm soát entry.
6. Dùng atomic conditional update, isolation/lock hoặc versioning/constraint phù hợp.
7. Cache có thể expire/miss/evict và chạy trên nhiều node; invariant không được phụ thuộc cache.
8. **Stale cache**; cần versioned key, invalidation/validation và policy freshness.

## 20. Tài liệu tham khảo

- Spring Framework Reference — *Synchronized Caching*, *Default Key Generation*: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Javadoc — `Cacheable.sync` và các giới hạn: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Javadoc — `Cache.get(Object, Callable)`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html
- Java 17 Javadoc — `ConcurrentHashMap.computeIfAbsent`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html

**Kết luận:** Việc tính toán lặp trên cache miss là bình thường. **Không nên để tính đúng nghiệp vụ phụ thuộc cache hit.** Tách query pure khỏi command idempotent, bảo vệ invariant tại nguồn bền vững, và sử dụng `@Cacheable(sync=true)` hoặc single-flight như tối ưu có kiểm chứng.