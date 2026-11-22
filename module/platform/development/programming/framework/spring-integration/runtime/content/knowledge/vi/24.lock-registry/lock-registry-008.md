# Độ trễ lock và ảnh hưởng throughput trong Spring Integration

## 1. Tại sao có nhiều worker mà message flow vẫn chậm?

Trong **SPRING_INTEGRATION_RUNTIME**, message chạy qua `MessageChannel`, endpoint, consumer, poller và executor. Tăng số worker thường giúp các message độc lập chạy song song. Nhưng khi nhiều message phải cập nhật **cùng một trạng thái** — chẳng hạn cùng `MessageGroup` của aggregator — chúng phải đi qua vùng độc quyền do `LockRegistry` kiểm soát. Nhiều thread sẽ **chờ cùng lock**, khiến throughput không tăng tương ứng.

Chủ đề **Lock registry → Độ trễ lock và ảnh hưởng throughput** giúp hiểu:

1. Vì sao một `correlationId` nóng có thể trở thành điểm nghẽn dù executor còn CPU.
2. Cách tách thời gian tra registry, chờ acquire, giữ lock, unlock và xử lý downstream.
3. Cách ước lượng throughput từ critical-section time, số key độc lập và số worker.
4. Sự khác biệt giữa `DefaultLockRegistry` trong một JVM với JDBC/Redis/ZooKeeper distributed lock.
5. Cách đo và tối ưu mà vẫn giữ tính nhất quán, transaction, retry, correlation và recovery.

Ví dụ: 20 message đều có `correlationId = "ORDER-42"` tới aggregator đồng thời. Chỉ một thread được cập nhật state group tại một thời điểm; 19 thread còn lại phải chờ.

~~~mermaid
flowchart LR
    M["20 messages ORDER-42"] --> E["Executor: 20 workers"]
    E --> L{"obtain(ORDER-42) rồi lock()"}
    L -->|Một thread giữ lock| G["Đọc / cập nhật MessageGroup"]
    L -->|Các thread khác| W["Chờ quyền sở hữu"]
    G --> U["unlock()"]
    U --> W
    W --> L
~~~

Một lock là công cụ **đồng bộ truy cập trạng thái**, không tự đảm bảo idempotency, atomic commit hay message được xử lý chính xác một lần.

## 2. LockRegistry và các thời điểm cần đo

Spring Integration định nghĩa `org.springframework.integration.support.locks.LockRegistry`. API cốt lõi là `obtain(Object lockKey)` trả về `java.util.concurrent.locks.Lock`:

~~~java
Lock lock = lockRegistry.obtain("tenant-1:order-42");
lock.lock();
try {
    updateSharedGroup();
}
finally {
    lock.unlock();
}
~~~

**`obtain()` không đồng nghĩa đã lấy được quyền độc quyền.** Lời gọi `lock()`, `lockInterruptibly()` hoặc `tryLock()` mới thực hiện việc acquire.

Từ Spring Integration **6.2**, có API `executeLocked()` giúp quản lý acquire và release:

~~~java
LockRegistry registry = new DefaultLockRegistry();

registry.executeLocked("order:42", () -> {
    updateSharedGroup();
});

// Nếu không thể acquire trong thời gian chờ thì ném TimeoutException.
registry.executeLocked(
        "order:42",
        Duration.ofMillis(250),
        () -> updateSharedGroup());
~~~

Đoạn này minh họa cách dùng API, cần import các class và triển khai `updateSharedGroup()`; caller xử lý `InterruptedException`, `TimeoutException` hay lỗi từ task tùy chữ ký sử dụng. `Duration.ofMillis(250)` giới hạn **thời gian đợi lock**, không giới hạn thời gian chạy bên trong critical section.

| Đại lượng | Bắt đầu và kết thúc | Ý nghĩa |
| --- | --- | --- |
| `T_obtain` | Trước/sau `registry.obtain(key)` | Lookup, cấp lock wrapper, cache/hash stripe |
| `T_wait` | Trước `lock()/tryLock()` đến acquire thành công | Chờ contention, lịch thread, polling/backend network |
| `T_hold` | Ngay sau acquire đến trước unlock | Thời gian chiếm độc quyền |
| `T_unlock` | Trong `unlock()` | Giải phóng local lock hoặc cập nhật distributed backend |
| `T_queue` | Đợi executor/poller/consumer sẵn sàng | Không phải latency của lock dù tăng tổng message latency |
| `T_flow` | Đầu đến cuối một flow | Có cả queue, lock, I/O và downstream |

~~~text
Message enters
  -> executor queue wait (T_queue)
  -> registry.obtain(key) (T_obtain)
  -> lock acquisition wait (T_wait)
  -> critical update / store I/O (T_hold)
  -> unlock (T_unlock)
  -> reply / downstream / ack
~~~

Phân biệt đúng các khoảng này mới biết nên tối ưu SQL, giữ lock, lịch retry, thread pool hay backend distributed lock.

## 3. Critical-section time giới hạn throughput theo key

Giả sử một message giữ lock trung bình `S` giây; mọi message có **cùng key** và luôn cần đi qua vùng đó. Giới hạn lý tưởng của đoạn được bảo vệ là:

\[
\lambda_{\text{1 key}} \le \frac{1}{S}
\]

Nếu `S = 0,010 s` (10 ms), một key tối đa xấp xỉ **100 thao tác/s** trong mô hình đơn giản, chưa kể overhead. Tăng worker từ 4 lên 64 không làm hai thread đồng thời sửa cùng group dưới cùng lock.

Nếu có `K` key thực sự độc lập, `P` workers và các key phân bố đều:

\[
\lambda_{\text{total}} \lesssim \frac{\min(K,P)}{S}
\]

Đây chỉ là **giới hạn tham khảo**; còn phụ thuộc key skew, database/network, hash stripe collision, scheduler và downstream throughput.

| `S` cho mỗi message | Key độc lập | Workers | Giới hạn lý tưởng |
| --- | ---: | ---: | ---: |
| 10 ms | 1 | 16 | ~100 message/s |
| 10 ms | 4 | 16 | ~400 message/s |
| 10 ms | 16 | 16 | ~1.600 message/s |
| 20 ms | 1 | 16 | ~50 message/s |
| 20 ms | 16 | 16 | ~800 message/s |

Điều cốt lõi là **phân bố tần suất theo key**, không chỉ tổng số key duy nhất. Nếu có 1.000 order ID nhưng 80% message rơi vào `"BATCH-ALL"`, một group nóng có thể chi phối p99 latency. Trong khi đó, nếu mỗi order có một correlation key đúng nghiệp vụ, các group khác nhau có cơ hội được cập nhật đồng thời.

Khi arrival rate trên một key vượt năng lực xử lý tuần tự, `T_wait` và executor queue tăng. Worker chờ lock vẫn chiếm slot trong thread pool, làm ảnh hưởng cả các key không tranh lock.

~~~text
Key A: worker-1 [work A] -> worker-2 [work A] -> worker-3 [work A]
       ---------- Chỉ một critical section tại một thời điểm ----------

Key B: worker-4 [work B] có thể chạy đồng thời với key A
Key C: worker-5 [work C] có thể chạy đồng thời với A/B
~~~

## 4. DefaultLockRegistry: lock striping và false contention

`DefaultLockRegistry` dựa trên `ReentrantLock` **trong một JVM**. Javadoc của Spring Integration 6.x nêu rõ implementation dùng một mảng **striped locks**:

- Mask mặc định `0xFF` tạo **256** lock stripes.
- `obtain(key)` chọn stripe dựa vào `key.hashCode() & mask`.
- Hai key **khác nhau** có thể dùng chung lock nếu hash mask trùng.
- Constructor `DefaultLockRegistry(int mask)` cho phép mask dạng `2^n - 1`; ví dụ `0x3FF` tạo 1.024 stripes.

~~~java
LockRegistry registry = new DefaultLockRegistry(0x3FF);

Lock lockA = registry.obtain("order-A");
Lock lockB = registry.obtain("order-B");
~~~

Không được suy ra `lockA != lockB` chỉ vì hai key khác nhau. Stripe collision tạo **false contention**: key khác nhau phải chờ nhau dù state nghiệp vụ độc lập.

| Hiện tượng | Nguyên nhân | Thay đổi nên thử |
| --- | --- | --- |
| Một key nóng, tăng worker vẫn chậm | Các message thật sự cần cùng lock | Giảm `T_hold`, chia work theo key đúng contract |
| Nhiều key độc lập nhưng vẫn bị chặn | Hash mask collision trong `DefaultLockRegistry` | Xem hash distribution, cân nhắc tăng stripes |
| Hai JVM cùng sửa group bị race | `DefaultLockRegistry` chỉ có hiệu lực trong từng JVM | Dùng shared distributed registry cho shared state |
| Tăng stripes không cải thiện | Nút thắt nằm ở một key hoặc database | Đo lại `T_wait` và `T_hold`, không tiếp tục tăng mù |

Tăng stripes có thể giảm collision, nhưng **không giúp** nếu tất cả message vẫn cùng key. Bản thân `DefaultLockRegistry` không cung cấp distributed mutual exclusion hoặc transaction.

## 5. JDBC và Redis lock thêm latency như thế nào?

Khi nhiều Spring Integration instances chia sẻ `MessageGroupStore` hoặc tài nguyên cần khóa, thường cần registry phân tán để cùng xác định ownership. Phần chi phí có thể gồm network RTT, database/Redis operations, polling hoặc notifications, lease renewal và backend load.

| Registry | Phạm vi đồng bộ | Chi phí phổ biến | Lưu ý |
| --- | --- | --- | --- |
| `DefaultLockRegistry` | Trong process/JVM | Scheduling, contention, hash stripes | Không dùng một mình cho state chia sẻ giữa pods |
| `JdbcLockRegistry` | Các instance kết nối đúng lock repository/DB | SQL, connection pool, polling giữa tries | DDL, `region`, TTL/ownership cần đúng |
| `RedisLockRegistry` | Các instance dùng cùng Redis lock namespace | Redis RTT, spin/pub-sub, expiry | Cần kiểm tra topology và release semantics |
| `ZookeeperLockRegistry` | Các instance cùng ZooKeeper ensemble | Phối hợp session/watcher, network | Cần vận hành session/failover |
| Registry tùy biến | Theo implementation | Phụ thuộc backend | Kiểm chứng atomicity và failure handling |

### 5.1. JDBC: `idleBetweenTries` và polling

Từ Spring Integration **5.1.8**, `JdbcLockRegistry` có thuộc tính `idleBetweenTries`. Tài liệu ghi nhận giá trị mặc định **100 ms** trong các phiên bản được mô tả. Khi owner thuộc instance khác release lock, một contender có thể cần chờ tới lượt thử tiếp theo trước khi thấy lock trống.

**100 ms không phải chi phí cố định cho mọi acquire.** Lock đang rảnh có thể lấy nhanh, trong khi database lock contention, connection pool hoặc network làm thời gian thực tế dài hơn. Giảm `idleBetweenTries` đôi khi giảm tail latency nhưng tăng tần suất truy vấn DB.

Cũng cần kiểm tra:

- DDL/primary key của bảng lock, region/key namespace và truy vấn của `DefaultLockRepository`.
- Connection pool: nếu nhiều worker chờ DB connection để acquire lock, tăng worker có thể làm tắc DB nặng hơn.
- TTL: thời gian lease phải đủ so với critical-section time hoặc có renewal. Nếu owner chết, lease hết hạn giúp node khác phục hồi; nếu owner còn chạy quá TTL, hai node có thể cùng sửa state.
- Từ 6.4, `JdbcLock.unlock()` có thể ném `ConcurrentModificationException` khi quyền sở hữu đã hết hạn; đó là lỗi an toàn dữ liệu cần điều tra.
- Các API và DDL liên quan TTL thay đổi ở dòng 7.x; khi nâng cấp cần dùng schema đúng phiên bản.

### 5.2. Redis: SPIN_LOCK, PUB_SUB_LOCK và TTL

Với `RedisLockRegistry`, tài liệu từ Spring Integration **5.5.13** mô tả hai chế độ qua `RedisLockType`:

| Chế độ | Cách chờ lock | Trade-off |
| --- | --- | --- |
| `SPIN_LOCK` | Thử định kỳ, chu kỳ thường khoảng 100 ms | Dễ tương thích hơn nhưng có network polling |
| `PUB_SUB_LOCK` | Nhận notification khi owner unlock | Có thể giảm network chatter và tail wait ở môi trường hỗ trợ |

Tài liệu ghi `SPIN_LOCK` là mặc định ở các phiên bản được đề cập vì một số Redis Master/Replica setup không hỗ trợ cách pub/sub tương ứng. Không tự bật `PUB_SUB_LOCK` khi chưa xác nhận hạ tầng Redis hiện tại.

Redis lock có thời hạn expiry mặc định được tài liệu mô tả là **60 giây** trong các phiên bản đó; thời gian này có thể cấu hình. TTL ngắn giúp recovery nhanh sau khi instance chết nhưng làm tăng nguy cơ **mất ownership** khi handler chậm, GC pause hoặc network partition.

Spring Integration 6.4 hỗ trợ renewal task scheduler có cấu hình cho Redis; Spring Integration 7.0 thêm `DistributedLock` và TTL theo lần acquire cho JDBC/Redis. Khi lock hết hạn rồi gọi `unlock()`, version 6.4+ có thể báo `ConcurrentModificationException`. Đây là tín hiệu rằng resource đã có nguy cơ bị thao tác đồng thời, không nên chỉ bắt exception rồi bỏ qua.

### 5.3. So sánh có cùng yêu cầu correctness

Không thể dùng tốc độ của `DefaultLockRegistry` trong một instance để kết luận shared JDBC/Redis lock là không đáng dùng. Local lock nhanh nhưng **không bảo vệ shared group giữa nhiều JVM** là mô hình sai nếu cùng ghi một store.

Distributed lock cũng **không tự tạo exactly-once**: transaction DB, message ack, broker redelivery, retry và external API vẫn cần idempotency hoặc coordination riêng. Nếu một node mất lease nhưng vẫn tiếp tục viết, có thể cần version check hoặc **fencing token được resource đích kiểm chứng**, không dựa vào mutex đã hết hạn.

## 6. Aggregator, resequencer và correlation key nóng

Aggregator dùng `MessageGroupStore` giữ các message cùng correlation key đến khi release. Việc sửa group phải được đồng bộ; `LockRegistry` lấy lock tương ứng với group ID. Các message cùng `correlationId` vì vậy chạy **tuần tự đối với phần cập nhật group**; các group khác nhau có cơ hội được xử lý đồng thời.

~~~mermaid
flowchart TD
    A["Message #1 / correlationId=G1"] --> L1["Lock G1"]
    B["Message #2 / correlationId=G1"] --> L1
    C["Message #3 / correlationId=G2"] --> L2["Lock G2"]
    L1 --> S1[("Group G1")]
    L2 --> S2[("Group G2")]
    S1 --> R1{"Release strategy"}
    S2 --> R2{"Release strategy"}
~~~

Các điểm quyết định throughput:

- **Correlation strategy** phải tách các công việc độc lập. Dùng một key constant cho mọi batch có thể ép toàn bộ flow chạy gần tuần tự.
- **Group store I/O** trong lock: query chậm, serialization lớn và transaction chờ DB sẽ làm tăng `T_hold`.
- **Release strategy**: phải được tối ưu theo state/metadata cần thiết; tránh scan/rebuild cả group ở mỗi message nếu có giải pháp phù hợp.
- **Gửi output đồng bộ**: nếu aggregator giữ lock khi gửi kết quả qua `DirectChannel` tới downstream chậm, lock có thể bị giữ lâu.
- **Shared store trong cluster**: cần shared distributed registry theo cùng key; mặc định `DefaultLockRegistry` không đủ giữa các instance.

Spring Integration có thuộc tính **`releaseLockBeforeSend`** (từ 5.1.1) để cho phép thả lock trước khi gửi output, giảm nguy cơ deadlock và rút ngắn hold time trong cấu trúc phù hợp. Cần kiểm chứng các hành vi release, ordering và xử lý lỗi trước khi áp dụng. Từ 6.5, `AbstractMessageGroupStore` còn có cơ chế lock cho metadata group và cho phép cấu hình `setLockRegistry(...)`; phải kiểm tra đúng phiên bản và provider.

### Deadlock giữa hai aggregator

~~~text
Thread T1: aggregator A giữ lock A
  -> gọi đồng bộ aggregator B, cần lock B

Thread T2: aggregator B giữ lock B
  -> gọi đồng bộ aggregator A, cần lock A

T1 chờ B, T2 chờ A -> deadlock
~~~

Tài liệu Spring Integration gợi ý các lựa chọn theo cấu trúc flow: dùng registry riêng cho mỗi aggregator khi phù hợp, dùng `ExecutorChannel`/`QueueChannel` giữa các chặng hoặc bật `releaseLockBeforeSend`. Các giải pháp thay đổi boundary và có thể ảnh hưởng transaction/error handling, nên phải xác minh tính đúng đắn sau khi thay.

## 7. Instrumentation: đo wait và hold thay vì đoán

~~~java
Lock lock = registry.obtain(key);
long waitStart = System.nanoTime();

lock.lockInterruptibly();
long acquiredAt = System.nanoTime();

try {
    performGroupUpdate();
}
finally {
    long beforeUnlock = System.nanoTime();
    lock.unlock();
    long afterUnlock = System.nanoTime();

    long waitNs = acquiredAt - waitStart;
    long heldNs = beforeUnlock - acquiredAt;
    long unlockNs = afterUnlock - beforeUnlock;

    metrics.record("lock.wait", waitNs);
    metrics.record("lock.held", heldNs);
    metrics.record("lock.unlock", unlockNs);
}
~~~

Đây là **snippet instrumentation**, các biến `registry`, `key`, `metrics` và method `performGroupUpdate()` do ứng dụng định nghĩa. Với distributed lock, `unlock()` có thể ném exception; khi đó cần ghi lỗi riêng chứ không giả định đã thả lock thành công.

Dùng `System.nanoTime()` cho elapsed time và đổi đơn vị sang milliseconds/seconds khi báo cáo. Không đo chờ lock bằng đồng hồ wall-clock có thể bị điều chỉnh. Metric hữu ích nên có p50, p95, p99 và failure count, không chỉ average.

| Metric gợi ý | Phát hiện |
| --- | --- |
| `lock.obtain.duration` | Wrapper/cache lookup bất thường |
| `lock.acquire.wait` (p50/p95/p99) | Hot key, polling, contention, starvation |
| `lock.held.duration` | Critical section/I/O dài |
| `lock.release.duration` | Backend unlock chậm |
| `lock.timeout.count` và `lock.interrupted.count` | Chờ vượt budget/worker bị hủy |
| `lock.owner_lost.count` | Lease hết hạn hoặc mất ownership |
| `executor.active` và `executor.queue.depth` | Worker bận chờ, backlog |
| `flow.input.rate` và `flow.output.rate` | Arrival vượt completion |
| `message.group.age` và `message.group.size` | Aggregator tích tụ |
| `db.pool.wait`, `redis.command.latency` | Backend lock/store nghẽn |

Những tên trên là **ví dụ instrumentation**, không phải mặc định mọi metric đều được Spring Integration phát ra. Với metrics system, không tag toàn bộ `correlationId`, `orderId` hay raw lock key vì cardinality cao; dùng endpoint, registry type, result và nhóm traffic. Key cụ thể chỉ nên nằm trong trace/log đã kiểm soát thông tin riêng tư.

## 8. Ví dụ chạy được: benchmark local hot key và 16 key

Ví dụ dùng **Java 17+**, dependency `spring-integration-core` tương thích (6.2+/7.x). Đặt toàn bộ nội dung vào file `LockLatencyDemo.java` trong package `demo.integration`. Chương trình tạo 1.600 tác vụ trên 16 worker, mỗi tác vụ giữ lock khoảng 2 ms. Hai lượt chạy chỉ khác cách chọn key.

~~~java
package demo.integration;

import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.LockSupport;
import java.util.function.IntFunction;

import org.springframework.integration.support.locks.DefaultLockRegistry;
import org.springframework.integration.support.locks.LockRegistry;

public final class LockLatencyDemo {

    private static final int WORKERS = 16;
    private static final int OPERATIONS = 1600;
    private static final long HOLD_NANOS =
            TimeUnit.MILLISECONDS.toNanos(2);

    public static void main(String[] args) throws InterruptedException {
        run("ONE HOT KEY", i -> "group-HOT");
        run("SIXTEEN KEYS", i -> "group-" + (i % 16));
    }

    private static void run(String label, IntFunction<String> keyFor)
            throws InterruptedException {

        LockRegistry registry = new DefaultLockRegistry(0x3FF);
        ExecutorService executor = Executors.newFixedThreadPool(WORKERS);

        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(OPERATIONS);
        ConcurrentLinkedQueue<Long> waitNs = new ConcurrentLinkedQueue<>();
        ConcurrentLinkedQueue<Long> heldNs = new ConcurrentLinkedQueue<>();
        AtomicInteger failed = new AtomicInteger();

        try {
            for (int i = 0; i < OPERATIONS; i++) {
                final int index = i;

                executor.execute(() -> {
                    try {
                        start.await();
                        Lock lock = registry.obtain(keyFor.apply(index));

                        long waitStart = System.nanoTime();
                        lock.lockInterruptibly();
                        long acquiredAt = System.nanoTime();

                        try {
                            // Mô phỏng cập nhật state cần đồng bộ.
                            LockSupport.parkNanos(HOLD_NANOS);
                        }
                        finally {
                            long beforeUnlock = System.nanoTime();
                            lock.unlock();

                            waitNs.add(acquiredAt - waitStart);
                            heldNs.add(beforeUnlock - acquiredAt);
                        }
                    }
                    catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        failed.incrementAndGet();
                    }
                    finally {
                        finished.countDown();
                    }
                });
            }

            long startedAt = System.nanoTime();
            start.countDown();
            finished.await();

            double seconds =
                    (System.nanoTime() - startedAt) / 1_000_000_000.0;
            int completed = waitNs.size();

            System.out.printf(
                    "%s completed=%d failed=%d duration=%.3fs "
                    + "throughput=%.1f msg/s waitP95=%.3fms "
                    + "heldP95=%.3fms%n",
                    label, completed, failed.get(), seconds,
                    completed / seconds,
                    percentileMs(waitNs, 95),
                    percentileMs(heldNs, 95));
        }
        finally {
            executor.shutdownNow();
        }
    }

    private static double percentileMs(
            ConcurrentLinkedQueue<Long> samples, int percentile) {

        long[] values = samples.stream()
                .mapToLong(Long::longValue)
                .sorted()
                .toArray();

        if (values.length == 0) {
            return Double.NaN;
        }

        int pos = Math.max(0, Math.min(values.length - 1,
                (int) Math.ceil(
                        percentile / 100.0 * values.length) - 1));
        return values[pos] / 1_000_000.0;
    }
}
~~~

### Đọc kết quả đúng cách

| Workload | Kỳ vọng tương đối | Tại sao |
| --- | --- | --- |
| `ONE HOT KEY` | `waitP95` lớn, throughput bị giới hạn | 16 worker cạnh tranh một lock |
| `SIXTEEN KEYS` | `waitP95` thấp hơn, throughput cao hơn | Có nhiều lock key độc lập |
| Tăng workers với 1 key | Throughput ít đổi, wait tăng | Số thao tác độc quyền không tăng |
| Tăng thời gian giữ lock | Throughput giảm | `1/S` giảm theo mô hình đơn giản |

**Đây là thí nghiệm minh họa, không phải benchmark production chuẩn.** `LockSupport.parkNanos` chịu ảnh hưởng scheduler, CPU throttling và GC; thread pool/queue cũng có overhead. Không lấy con số từ máy phát triển làm SLA JDBC/Redis. Khi đo nghiêm túc, cần warm-up, lặp nhiều lần, đo p95/p99 cùng backlog, chạy đúng backend và tải thực tế.

Bài tập mở rộng: tăng `WORKERS` từ 4 đến 32, tăng `HOLD_NANOS`, thay 16 key thành 2/4/64 key, thử mask mặc định `0xFF` và mask lớn hơn. Quan sát trường hợp throughput không tăng nữa.

## 9. Giảm thời gian giữ lock mà vẫn đúng nghiệp vụ

Một cách thường hiệu quả là đưa thao tác **không cần độc quyền** ra ngoài critical section.

**Không hợp lý nếu có thể tách I/O:**

~~~java
registry.executeLocked(accountKey, () -> {
    Account state = repository.load(accountKey);
    RemoteProfile profile = remoteClient.fetchProfile(accountKey);
    repository.update(state, profile);
});
~~~

Nếu HTTP mất 300 ms thì lock bị giữ trong lúc chờ mạng.

**Phương án tách I/O khi contract cho phép:**

~~~java
RemoteProfile profile = remoteClient.fetchProfile(accountKey);

registry.executeLocked(accountKey, () -> {
    Account state = repository.load(accountKey);
    repository.updateIfVersionMatches(state, profile);
});
~~~

Đoạn thứ hai chỉ an toàn nếu dữ liệu profile có thể lấy trước và bản cập nhật có **version/conditional check** phù hợp. Nếu dữ liệu ngoài phụ thuộc trạng thái vừa đọc trong lock, phải thiết kế read/version/retry rõ. Không rút ngắn critical section bằng cách phá vỡ tính nhất quán.

Các cách tối ưu:

- Giữ scope khóa chỉ gồm read-check-update tối thiểu; dời logging lớn, serialization và HTTP call ra ngoài nếu semantics cho phép.
- Tối ưu DB index và truy vấn của group store; tránh đọc toàn bộ group chỉ để kiểm tra metadata nhỏ.
- Sửa correlation strategy để các công việc **thật sự độc lập** dùng các key khác nhau.
- Dùng `releaseLockBeforeSend` nếu luồng aggregator phù hợp, kiểm tra downstream và lỗi phát sinh sau khi unlock.
- Tránh nested locks; khi cần nhiều lock, áp cùng thứ tự acquire nhất quán.
- Với workload DB có nhiều conflict, so sánh optimistic locking/CAS với mutex; kiểm thử duplicate/rollback trước khi thay.

Đừng cố giảm `T_hold` xuống 0 bằng cách bỏ lock nếu store cần atomic group updates. Mục tiêu là **giảm khoảng độc quyền không cần thiết**.

## 10. LockRequestHandlerAdvice cho endpoint (Spring Integration 6.5+)

Spring Integration 6.5 giới thiệu `LockRequestHandlerAdvice`. Nó đánh giá key từ message và gọi `LockRegistry.executeLocked()` quanh scope của handler; các key khác nhau có thể được xử lý đồng thời theo registry.

~~~java
// Ví dụ cấu hình Java; yêu cầu bean handler/channel ở ứng dụng.
@Configuration
class LockAdviceConfiguration {

    @Bean
    LockRegistry lockRegistry() {
        return new DefaultLockRegistry(0x3FF);
    }

    @Bean("accountLockAdvice")
    LockRequestHandlerAdvice accountLockAdvice(LockRegistry lockRegistry) {
        LockRequestHandlerAdvice advice =
                new LockRequestHandlerAdvice(lockRegistry,
                    message -> {
                        AccountCommand command =
                                (AccountCommand) message.getPayload();
                        return command.tenantId() + ":" + command.accountId();
                    });

        advice.setWaitLockDurationExpressionString("'PT1S'");
        return advice;
    }
}

record AccountCommand(String tenantId, String accountId, long delta) { }

@MessageEndpoint
class AccountEndpoint {

    @ServiceActivator(
        inputChannel = "accountCommands",
        adviceChain = "accountLockAdvice")
    public void handle(AccountCommand command) {
        // Ví dụ: gọi dịch vụ cập nhật tài khoản có transaction riêng.
        accountService.apply(command);
    }
}
~~~

Đây là snippet **không standalone**: cần imports `@Configuration`, `@Bean`, `@MessageEndpoint`, `@ServiceActivator`, `LockRequestHandlerAdvice`, `LockRegistry`, `DefaultLockRegistry` và inject bean `accountService`; cũng cần channel `accountCommands`. Cấu hình minh họa scope lock và thời hạn chờ.

Những giới hạn cần hiểu:

- `waitLockDuration` giới hạn **chờ acquire**, không giới hạn thời gian handler chạy.
- Key trả `null` khiến advice không giữ lock và có thể tiếp tục xử lý; có cơ chế discard channel nếu muốn loại message thiếu key.
- Advice bọc handler tương ứng, không mặc nhiên bao mọi endpoint downstream; với reply-producing handler, phạm vi request-handler advice có thể kết thúc trước việc gửi reply.
- Nếu ứng dụng chạy nhiều instance với shared store, thay local registry bằng distributed registry đúng backend.
- Nếu handler thất bại sau khi đã có side effect, retry/redelivery vẫn có thể gọi lại. Lock không thay thế idempotency.

## 11. Timeout, TTL, renewal, retry và transaction

### Timeout khi chờ lock

~~~java
Lock lock = registry.obtain(key);

if (!lock.tryLock(250, TimeUnit.MILLISECONDS)) {
    throw new TimeoutException("Unable to obtain lock within 250ms");
}

try {
    process();
}
finally {
    lock.unlock();
}
~~~

`tryLock()` có thể ném `InterruptedException`. Caller cần phân loại timeout/interruption, không retry vô hạn. Time-out quá ngắn ở một hot key dễ làm tăng tỷ lệ thất bại và tạo retry storm.

### Lease TTL khác wait timeout

| Tình huống | Hành vi cần xem xét |
| --- | --- |
| `tryLock` chờ quá deadline | Không acquire; handler chưa được gọi |
| Lock đã acquire nhưng TTL hết | Owner có thể mất quyền độc quyền khi vẫn chạy |
| Owner chết khi giữ lock | TTL giúp instance khác phục hồi sau thời gian hết hạn |
| `unlock()` khi đã mất owner | Có thể ném lỗi nghiêm trọng; phải xem tính đúng của state |
| Renew lock không kịp | Lease vẫn có thể hết do GC pause/network |
| Lock thả nhưng broker redeliver | Message có thể được chạy lại; cần idempotency |

Khi external system nhận một update sau khi owner đã mất lease, một lock có TTL đơn thuần có thể không chặn được owner cũ. Cần design **fencing token/conditional version/idempotency** ở resource đích theo requirement.

### Retry advice trước/sau lock advice

~~~text
[retryAdvice, lockAdvice] -> handler
  attempt 1: acquire -> handler throws -> unlock
  backoff ở ngoài lock
  attempt 2: acquire -> handler returns -> unlock

[lockAdvice, retryAdvice] -> handler
  acquire -> attempt 1 throws -> backoff -> attempt 2 -> unlock
  lock được giữ xuyên thời gian retry/backoff
~~~

Cấu hình đầu thường giúp không giữ lock trong lúc backoff, nhưng điều kiện an toàn nghiệp vụ có thể yêu cầu giữ lock cho toàn bộ chuỗi thao tác. Với retry, cần tính cả số lần acquire, timeout và effect đã commit trước lỗi.

### Transaction và async boundary

- `DefaultLockRegistry` không phải database transaction manager.
- `JdbcLockRegistry` dựa trên DB, nhưng không có nghĩa lock ownership tự kết hợp nguyên tử với transaction nghiệp vụ.
- `DirectChannel` thường giữ call stack và transaction thread, `ExecutorChannel`/poller có ranh giới thực thi khác.
- Nếu thread chờ lock trong một transaction đang mở, nó có thể giữ connection/DB lock lâu, làm contention lan sang hệ thống khác.
- Recovery callback có thể nuốt exception và khiến upstream coi message đã xử lý. Phải xác nhận ack/rollback/error channel theo flow cụ thể.

Không dùng distributed lock thay cho outbox/inbox, `MessageStore`, broker ack hay quy tắc retry có giới hạn.

## 12. Chẩn đoán production từ các dấu hiệu

| Dấu hiệu | Nguyên nhân khả dĩ | Kiểm tra |
| --- | --- | --- |
| Thêm executor threads nhưng throughput đứng yên | Hot key hoặc critical section dài | `T_wait`, `T_hold`, key distribution |
| CPU thấp nhưng queue tăng | Workers đang chờ lock/I/O | Thread dump, executor active, DB/Redis |
| p99 wait tăng sau khi scale pod | Distributed lock contention tăng | Wait theo instance, group, polling |
| Key khác nhau vẫn chờ nhau ở một JVM | DefaultLockRegistry striped hash collision | Mask/hash distribution |
| Redis/JDBC wait cao dù `T_hold` nhỏ | Poll interval/network/backend latency | Acquire vs held vs unlock; spin/pub-sub |
| Aggregator giữ group quá lâu | Correlation key quá rộng, release logic/store chậm | Group size/age, store queries |
| Worker treo không tiến | Deadlock nested locks/aggregator | Thread dump, vòng lock order |
| GC pause xong unlock ném lỗi | Lease/TTL hết trước khi xong | TTL, renewal, GC logs |
| Một pod sửa state dù pod khác giữ lock | Local registry trên shared store hoặc mất ownership | Shared registry, TTL, fencing |
| Timeouts làm backlog lớn hơn | Retry ngay cùng hot key | Giới hạn retry, backoff, DLQ |

Các bước debug:

1. Tìm **điểm acquire/release thực tế** và key được dùng bởi aggregator, advice hay code thủ công.
2. Đo riêng `T_obtain`, `T_wait`, `T_hold`, `T_unlock`.
3. Phân tích key distribution theo khoảng 1–5 phút, tìm hot key và mức skew.
4. Đối chiếu arrival/completion rate, queue depth, consumer lag và oldest message age.
5. Kiểm tra pool threads, DB connections, network RTT, Redis/JDBC lock query và GC pause.
6. Thử fault injection: giữ lock lâu, hết TTL, process chết, Redis/DB chậm, contention nhiều node.
7. Thay từng yếu tố: số workers, key cardinality, stripe mask, critical section, polling interval; giữ nguyên business invariant.
8. Kiểm chứng sau tối ưu: không mất group updates, không duplicate side effects, không sai correlation/transaction.

## 13. Những điều phải phân biệt khi tối ưu

- **Contention thực**: nhiều message cần cùng logical key; không thể giải quyết bằng tăng số stripes.
- **False contention**: key khác nhau cùng hash stripe trong local registry; xem xét cấu hình mask.
- **Backend latency**: Redis/JDBC round-trip, polling và connection pool; cần đo bằng distributed setup thật.
- **Lock wait timeout**: giới hạn người chờ, không phải lease TTL.
- **Lock TTL**: thời hạn ownership; nếu hết khi handler đang chạy thì correctness có nguy cơ bị phá.
- **Message latency**: còn bao queue, poller, executor, transaction, store và downstream.
- **Retry**: có thể nhân số lần acquire, hoặc giữ lock xuyên backoff tùy thứ tự advice.
- **Correlation**: quy tắc gom group ảnh hưởng trực tiếp số key có thể tiến hành đồng thời.
- **Transaction/idempotency**: vẫn cần xác định commit/ack/recovery độc lập với mutex.

## 14. Bài thực hành

1. Chạy `LockLatencyDemo` với 1 hot key và 16 key. So sánh throughput, `waitP95` và `heldP95`.
2. Tăng `WORKERS` từ 4 lên 16 rồi 32 khi chỉ có một key, giải thích vì sao throughput ít thay đổi.
3. Giữ số workers, tăng `HOLD_NANOS` từ 2 ms lên 10 ms, đối chiếu giới hạn `1/S`.
4. Tạo nhiều key có cùng hash mask để minh họa false contention; đổi `DefaultLockRegistry(0x3FF)` để kiểm tra.
5. Dựng aggregator với 1.000 message chung `correlationId` và với nhiều group; đo group age và `T_wait`.
6. Thử cấu hình `releaseLockBeforeSend` hoặc ngắt bằng `ExecutorChannel` trong môi trường test; so sánh latency và semantics downstream.
7. Với shared persistent `MessageGroupStore` qua hai application instances, thử local lock rồi distributed lock để kiểm chứng race/consistency.
8. Nếu có JDBC, thay `idleBetweenTries` và đo đồng thời p99 wait **và** query rate; tránh tối ưu wait bằng cách tăng DB tải vô hạn.
9. Nếu có Redis tương thích, so sánh `SPIN_LOCK` với `PUB_SUB_LOCK` theo topology thực; theo dõi network traffic.
10. Cố tình cho handler chạy quá TTL trong môi trường thử nghiệm; xác minh lỗi owner loss không bị nuốt.
11. Đổi thứ tự `retryAdvice`/`lockAdvice`, đo thời gian hold trong backoff và kiểm tra side effect/idempotency.
12. Thu thread dump khi hai aggregator lấy lock theo thứ tự ngược, sau đó sửa để không còn deadlock.

## 15. Tài liệu tham khảo chính thức

- [Spring Integration — Distributed Locks](https://docs.spring.io/spring-integration/reference/distributed-locks.html): `LockRegistry`, `executeLocked()`, distributed providers và TTL.
- [Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation group, lock scope, release và deadlock.
- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): synchronized message group metadata và backend.
- [Spring Integration — JDBC Lock Registry](https://docs.spring.io/spring-integration/reference/jdbc/lock-registry.html): `idleBetweenTries`, TTL, renewal và ownership.
- [Spring Integration — Redis Lock Registry](https://docs.spring.io/spring-integration/reference/redis.html#redis-lock-registry): `SPIN_LOCK`/`PUB_SUB_LOCK`, expiry và renewal.
- [Spring Integration — Lock Request Handler Advice](https://docs.spring.io/spring-integration/reference/handler-advice/lock.html): `LockRequestHandlerAdvice`, wait duration và message key.
- [Javadoc — LockRegistry (6.4)](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/support/locks/LockRegistry.html): chữ ký `executeLocked`.
- [Javadoc — DefaultLockRegistry (6.5)](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/support/locks/DefaultLockRegistry.html): hash mask, striped locks và constructor.
