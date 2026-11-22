# Kiểm thử tần suất cập nhật, tranh chấp và khả năng mở rộng của ConcurrentHashMap

`java.util.concurrent.ConcurrentHashMap<K,V>` là một cấu trúc map hỗ trợ truy cập đồng thời, vẫn được sử dụng trong những phiên bản Java hiện hành. Nó hữu ích để lưu cache, trạng thái theo khóa, thống kê và bộ đếm sự kiện. Tuy nhiên, **map thread-safe không làm mọi chuỗi thao tác của ứng dụng trở thành atomic**, và **đúng dưới concurrency không có nghĩa tự động mở rộng tuyến tính khi tăng số luồng**.

Một hệ thống đếm lượt truy cập có thể đúng khi một thread nhưng làm mất hàng nghìn update khi nhiều thread dùng `get` rồi `put`. Một phương pháp khác có thể giữ đúng tổng nhưng nghẽn khi mọi worker cập nhật cùng một key nóng. Vì vậy phải kiểm thử đồng thời ba khía cạnh:

1. **Correctness:** tổng update, số lượng key và các bất biến sau khi tất cả worker hoàn tất có chính xác không?
2. **Contention:** mức độ các thread tranh chấp khi cùng cập nhật một key, nhiều key hay các giá trị mutable?
3. **Scalability:** throughput, latency, CPU, memory và allocation thay đổi như thế nào khi tăng số thread và thay phân bố key?

Bài này sử dụng `ConcurrentHashMap.merge`, `computeIfAbsent`, `AtomicLong`, `LongAdder`, `CountDownLatch` và `ExecutorService`, kết hợp phương pháp đo bằng OpenJDK JMH. Các API đều hiện còn áp dụng. Ví dụ độc lập chạy trên **JDK 17+**, có stdout đã được kiểm tra thực tế.

## 1. Định nghĩa workload cần kiểm

Giả sử ứng dụng đếm sự kiện theo mã sản phẩm. Mỗi request thực hiện một update có nghĩa là tăng count của đúng một key. Ta cần biết **số update thật sự hoàn tất**, chứ không chỉ số task đã được tạo.

| Tham số | Ý nghĩa | Ví dụ |
|---|---|---|
| `threads` | Số worker đồng thời | 1, 2, 4, 8 |
| `iterations` | Số update mỗi worker | 10.000 |
| `keySpace` | Số khóa khác nhau | 1, 16, 1.024 |
| `hotKeyRatio` | Phần update tập trung vào key nổi bật | 0%, 50%, 99% |
| `readWriteRatio` | Tỷ lệ đọc và cập nhật | 90/10 hoặc 10/90 |
| `prePopulated` | Các key có trước khi đo hay không | Có hoặc không |
| `updateAlgorithm` | Chiến lược cập nhật | merge, AtomicLong, LongAdder |
| `completedUpdates` | Số update hoàn thành không lỗi | Cần bằng tổng mong đợi |
| `elapsedNanos` | Thời gian đo trong JVM | Không in cứng một con số |
| `allocatedBytes` | Bộ nhớ cấp phát trong workload | Phụ thuộc thuật toán/VM |

**Tổng số update mong đợi** khi mỗi worker chạy cùng số vòng và không có update thất bại:

~~~text
expectedTotal = threadCount * iterationsPerThread
~~~

Ví dụ 8 worker × 10.000 update = 80.000 update. Sau khi tất cả worker xong, tổng count trên mọi key phải bằng 80.000. Nếu mỗi worker cập nhật key riêng, từng key phải có đúng 10.000.

Lưu ý **size của map không phải tổng số update**: map có thể chứa đúng một key nhưng value bị sai vì mất cập nhật.

## 2. ConcurrentHashMap bảo đảm gì?

`ConcurrentHashMap` hỗ trợ các thao tác riêng lẻ như `get`, `put`, `putIfAbsent`, `replace`, `compute`, `merge` theo hợp đồng concurrency. Nó không có một lock toàn map buộc mọi reader và writer cùng tuần tự hóa.

Các tính chất cần nhớ:

- `get(key)` và `put(key,value)` là những thao tác riêng an toàn khi dùng đồng thời.
- `compute` và `merge` có tính atomic **cho việc cập nhật mapping theo key** của một lời gọi, không phải transaction nhiều key.
- Không cho phép `null` key hoặc value.
- Iterator và phép traversal là **weakly consistent**, không đồng nghĩa snapshot atomic khi writer còn chạy.
- `size()`, `mappingCount()` và kết quả duyệt/tổng hợp khi đang update có thể là một trạng thái tạm thời, không thích hợp kiểm invariant cuối của mọi thread.
- Nếu value là một đối tượng mutable, map không tự biến mọi thao tác trên **bên trong value** thành thread-safe.

### 2.1. Lỗi read-modify-write không atomic

Đoạn dưới đây **không đủ an toàn** cho một bộ đếm được nhiều thread cập nhật:

~~~java
int old = counts.getOrDefault("hot", 0);
counts.put("hot", old + 1);
~~~

Đây là mảnh code với `counts` giả định là `ConcurrentHashMap<String,Integer>`. Hai thao tác an toàn đứng riêng, nhưng giữa `get` và `put` một worker khác có thể đã đọc cùng giá trị. Ví dụ cả bốn worker đều đọc 0 rồi cùng ghi 1: dự kiến 4, thực tế 1.

Cách đơn giản hơn:

~~~java
counts.merge("hot", 1, Integer::sum);
~~~

`merge` thực hiện phần cập nhật một mapping atomically theo hợp đồng ConcurrentHashMap. Không có khoảng trống giữa đọc và ghi do ứng dụng tự chia thành hai lời gọi.

### 2.2. Không có transaction trên hai khóa

Giả sử chuyển 5 đơn vị từ `A` sang `B`. Dù mỗi `compute` atomic với khóa riêng, hai lời gọi `compute(A,...)` và `compute(B,...)` không trở thành một transaction duy nhất trên cả map. Một reader có thể thấy một thay đổi trước thay đổi kia.

Nếu yêu cầu nghiệp vụ là invariant trên nhiều key (số dư hoặc quota chính xác), cần một protocol synchronization/transaction phù hợp. Đừng cố dùng ConcurrentHashMap như thay thế mặc định cho database transaction.

## 3. Chọn chiến lược cập nhật phù hợp

### 3.1. merge: tăng bộ đếm bằng giá trị bất biến

~~~java
ConcurrentHashMap<String, Long> counts =
        new ConcurrentHashMap<>();

counts.merge("click", 1L, Long::sum);
~~~

Với một key vắng mặt, `merge` có thể đưa giá trị khởi tạo vào map. Khi key đã tồn tại, nó áp dụng remapping function và cập nhật mapping atomically. Giá trị `Long` immutable và thường có boxing/allocation liên quan; cần đo khi update frequency cao.

`Long` rộng hơn `Integer` nhưng vẫn có giới hạn 64-bit, và `Long::sum` không tự kiểm overflow. Nếu miền nghiệp vụ có nguy cơ tràn, xây chính sách cụ thể hoặc dùng phép kiểm số học phù hợp.

### 3.2. LongAdder: giảm contention cho phép cộng thống kê

~~~java
ConcurrentHashMap<String, LongAdder> counts =
        new ConcurrentHashMap<>();

counts.computeIfAbsent(
        "click", key -> new LongAdder()).increment();

long now = counts.get("click").sum();
~~~

Đây là mẫu frequency map được tài liệu `LongAdder` chính thức đề cập. `computeIfAbsent` tạo counter khi key chưa có; `LongAdder.increment` thread-safe và có thể phân tán cập nhật nội bộ khi tranh chấp lớn.

**Đổi lại:** `LongAdder.sum()` **không phải atomic snapshot** trong lúc các thread khác đang ghi; tài nguyên bộ nhớ có thể cao hơn một biến atomic. Nó phù hợp số đếm thống kê khi một phép đọc tức thời không cần linearizability mạnh.

### 3.3. AtomicLong: một counter có phép đọc/cập nhật atomic

~~~java
ConcurrentHashMap<String, AtomicLong> counts =
        new ConcurrentHashMap<>();

long after = counts.computeIfAbsent(
        "click", key -> new AtomicLong()).incrementAndGet();
~~~

`AtomicLong` có một giá trị long atomic và những phép read/compare-and-set thích hợp cho logic cần cập nhật một biến nguyên tử. Với rất nhiều worker cùng tăng **một counter**, contention trên một biến có thể lớn; `LongAdder` thường được cân nhắc cho thống kê ghi dày hơn.

### 3.4. Bảng quyết định

| Chiến lược | Tăng count có atomic? | Lưu ý kiểm thử |
|---|---|---|
| `get` rồi `put` | Không cho cả chuỗi | Cố ý tái hiện lost update |
| `merge(key,1L,Long::sum)` | Có cho mapping | Kiểm hot key và boxing/GC |
| `compute(key, fn)` | Có cho mapping | Hàm cần ngắn, không tự sửa map |
| `computeIfAbsent` + `LongAdder.increment` | Có cho tạo mapping và tăng counter tương ứng | `sum()` không snapshot atomic khi writer còn chạy |
| `computeIfAbsent` + `AtomicLong.incrementAndGet` | Có cho tạo mapping và tăng counter tương ứng | Một biến atomic có thể tranh chấp |
| `HashMap` chia sẻ không sync | Không an toàn | Không dùng làm baseline correctness |
| `Collections.synchronizedMap` | Các method wrapper có synchronization | Compound action vẫn cần sync ngoài |

Không kết luận `LongAdder` luôn nhanh nhất: với ít thread hoặc key trải đều, overhead và footprint có thể đảo kết quả. Lựa chọn phải đáp ứng cả **semantics** và profile traffic thật.

## 4. Những điều kiện đặc biệt của compute/merge

Các remapping function của ConcurrentHashMap nên **ngắn và đơn giản**. Theo hợp đồng hiện hành, một số attempted updates trên map bởi thread khác có thể bị chặn trong khi function đang tính.

~~~java
cache.computeIfAbsent(
        key, k -> blockingRemoteServiceCall(k));
~~~

Đây là **mảnh phản ví dụ** với hàm ứng dụng giả định: không nên mặc định gọi HTTP/DB có thể kéo dài trong mapping function. Nếu cần load cache từ một nguồn chậm, cân nhắc lưu future, quản lý single-flight, lỗi và timeout bằng thiết kế riêng.

**Không sửa chính map bên trong mapping/remapping function**; thao tác recursive có thể bị từ chối theo hợp đồng. Không đưa side effect khó rollback (chuyển tiền, gửi email) vào callback rồi coi atomic mapping tương đương transaction với dịch vụ ngoài.

`computeIfAbsent` có thể gọi mapping function khi key vắng mặt, nhưng một key có thể được tạo lại về sau nếu bị remove hoặc function trả null. Nó không hứa một factory chỉ chạy một lần **vĩnh viễn** trong vòng đời hệ thống.

`ConcurrentHashMap` không lưu null key/value. Với những phương thức remapping có hợp đồng trả null, kết quả null có thể có nghĩa không tạo hoặc loại bỏ mapping. Hãy định nghĩa rõ khác biệt giữa “chưa từng có count”, “count bằng 0” và “key đã bị xóa”.

## 5. Kiểm đúng trước khi đo nhanh

Một test concurrency tốt phải assert những điều không phụ thuộc may rủi scheduler:

~~~text
expected = threads * loops
sumAfterWorkersDone == expected

hot key:
  map.size() == 1
  map["hot"] == expected

spread keys:
  map.size() == threads
  map["worker-i"] == loops cho mỗi i
~~~

Các kiểm tra khác có giá trị:

- Chỉ tăng thì count không âm (với giả định không tràn số).
- Không update nhầm key.
- Mọi worker thật sự chạy đủ số vòng.
- Mọi lỗi trong worker phải được truyền về coordinator.
- Không còn task chạy khi đọc tổng cuối.
- Future có timeout hợp lý để test không treo khi có deadlock.
- Sau cleanup, executor không rò thread qua test sau.

Không assert `LongAdder.sum()` trên một map đang được cập nhật như một invariant cuối. `sum()` đọc nhiều ô nội bộ không phải atomic snapshot; đọc sau quiescence mới phù hợp để kiểm tổng.

### 5.1. Vì sao map.size chưa đủ?

Một map có `size()==1` dù có 100.000 lần tăng trên cùng key. Nếu 3.000 lần cập nhật bị mất, size vẫn là 1. Phải kiểm **giá trị count** tương ứng với tổng update.

Nếu mỗi worker cập nhật key riêng, kiểm cả số key và count từng key để bắt lỗi phân phối sai. Tổng đúng vẫn có thể che trường hợp update nhầm từ key A sang B.

## 6. Tái hiện lỗi lost update bằng interleaving bắt buộc

Một test chỉ chạy `get`/`put` rất nhanh một triệu lần **có thể không gặp race** ở lần chạy đó. Dùng `CountDownLatch` để tạo tình huống xác định:

~~~text
map["hot"] = 0

worker 1 đọc 0 ─┐
worker 2 đọc 0 ─┼── tất cả đều đọc xong ──► mở cổng ghi
worker 3 đọc 0 ─┤                         tất cả ghi giá trị 1
worker 4 đọc 0 ─┘                         kết quả cuối: 1
                                              mong đợi: 4
~~~

Phần `showLostUpdate` trong chương trình hoàn chỉnh sử dụng `allRead` và `allowWrite`. Khi đủ bốn worker đọc 0, coordinator mới mở cổng ghi. Kết quả cuối **chắc chắn sai theo định nghĩa phép tăng**, không phải lỗi nội bộ của ConcurrentHashMap.

**Đừng thay latch bằng `Thread.sleep`**: sleep chỉ ảnh hưởng lịch chạy, không bảo đảm từng worker đã đến điểm cụ thể. Với bài test cần tái hiện lỗi chính xác, điều phối bước là cách có căn cứ hơn.

## 7. Tạo cạnh tranh cập nhật thật trong test

`Executors.newFixedThreadPool(threads)` cung cấp số worker cho thí nghiệm. Để tránh chạy gần như tuần tự, dùng hai latch:

~~~java
CountDownLatch ready = new CountDownLatch(threads);
CountDownLatch start = new CountDownLatch(1);

for (int t = 0; t < threads; t++) {
    executor.submit(() -> {
        ready.countDown();
        start.await();
        // Thực hiện số update được định nghĩa.
        return null;
    });
}
if (!ready.await(10, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Not ready");
}
long begun = System.nanoTime();
start.countDown();
~~~

Đây là **mảnh minh họa**, với `threads` và `executor` đã có trước. Callback submit theo Callable có thể ném InterruptedException, được phản ánh trong Future.

**Lưu ý deadlock:** nếu pool có 2 worker nhưng 8 task đều phải chờ `ready` của 8 worker trước khi mở cổng, 2 worker đầu có thể chiếm hết pool, làm 6 task còn lại không được chạy. Demo tạo số thread bằng số worker yêu cầu. Thêm timeout để fail thay vì treo vô hạn.

Sau khi mở cổng, coordinator phải lưu `Future<?>` của từng task rồi gọi `get(timeout)` để:

- Đợi **cả vòng update** hoàn tất.
- Nhận exception của worker, tránh pass giả.
- Thiết lập một ranh giới có thể kiểm đo và đọc tổng đúng.
- Không để task của lần chạy cũ xen vào lần chạy mới.

`get` tại **test coordinator** là phép chờ có chủ đích; điều cần tránh là gọi `get` giữa hot path của một tác vụ khi có thể chain kết quả hoặc tổ chức việc khác.

## 8. Phân bố khóa và tình huống thực tế

Không thể đánh giá contention chỉ qua số worker. Cần so ít nhất hai case:

**Hot key:** mọi worker tăng `"hot"`. Đây là trường hợp bất lợi cho một mapping/counter chung, ví dụ một sản phẩm nhận phần lớn event.

**Spread keys:** mỗi worker tăng `"worker-i"` riêng. Tranh chấp trực tiếp trên counter giảm nhưng map vẫn có overhead hash, cache, allocation.

Nên mở rộng ma trận:

| Phân bố | Tình huống mô phỏng | Mục đích |
|---|---|---|
| 1 hot key | 100% update cùng key | Tranh chấp một counter |
| Uniform 16 keys | Phân bố khá đều | Nhiều key với contention vừa |
| Uniform 1.024 keys | Ít trùng key | Throughput khi cạnh tranh thấp |
| Zipf/skew | 80–99% dồn vào một nhóm hot | Workload giống traffic lệch |
| Nhiều key mới | Insert/cold cache | Allocation/resizing |
| Key đã tồn tại | Steady-state update | Tách update khỏi tạo mapping |
| 90% read, 10% write | Read-heavy cache | Đọc khi writer đang hoạt động |
| Remove/reinsert | Eviction và vòng đời | Semantics của counter và race |
| Hash collision | Nhiều key khác nhau cùng hash | Tác động phân phối hash |
| Key cardinality rất lớn | Nhiều ID ít update | Heap và GC |

Các hệ thống thực tế thường có **skew**: một ít key rất nóng, nhiều key hiếm được chạm. Một phép đo uniform không phản ánh đầy đủ trường hợp này. Hãy đo phân bố traffic thật (nếu được phép), rồi tạo tham số test đại diện.

### 8.1. Chuẩn bị key ngoài hot path

Nếu muốn đo riêng chi phí cập nhật map, không tạo chuỗi key, không sinh số ngẫu nhiên phức tạp, không log stdout bên trong vòng lặp đo; những công việc ấy có thể áp đảo chi phí của `merge`. Hãy pre-generate key hoặc một mảng index trong `setup`.

Tuy nhiên, nếu mục tiêu là **đo end-to-end pipeline** và production thực sự phải parse/generate key, hãy ghi rõ rằng bạn đang đo cả chi phí đó. Hai phép đo không thay thế nhau.

## 9. Đo throughput và tính khả năng mở rộng

Chọn đồng hồ monotonic `System.nanoTime()` để đo khoảng trong một JVM:

~~~text
opsPerSec = completedOps / (elapsedNanos / 1_000_000_000.0)

speedup(p) = throughput(p) / throughput(1)

efficiency(p) = speedup(p) / p
~~~

Số nano giây của một lần chạy **không cố định**. JIT, GC, nhiệt độ CPU, scheduling, hoạt động của hệ điều hành và kích thước heap có thể tác động mạnh. Không lấy lần chạy nhanh nhất rồi tuyên bố một phương pháp “nhanh hơn X lần” nếu không có nhiều phép đo.

### 9.1. Strong scaling và weak scaling

- **Strong scaling:** giữ **tổng công việc** cố định, thay số worker. Hỏi thêm worker có rút ngắn thời gian hoàn thành cùng một lượng update không.
- **Weak scaling:** giữ **số update mỗi worker** cố định; tổng công việc tăng cùng số worker. Hỏi throughput hệ thống tăng thế nào khi tải và tài nguyên cùng tăng.

Trong chương trình demo, mỗi worker làm 10.000 vòng nên đây là **scaled workload**. Khi kết luận về speedup, phải dùng throughput đã chuẩn hóa và ghi rõ tải chứ không so thời gian chạy thô khi tổng work khác nhau.

### 9.2. Ví dụ số học minh họa, không phải benchmark

Giả sử throughput một thread là 100.000 ops/s, bốn thread là 300.000 ops/s:

~~~text
speedup(4) = 300000 / 100000 = 3
efficiency(4) = 3 / 4 = 0.75
~~~

Đây là **ví dụ công thức**, không phải kết quả thực nghiệm của ConcurrentHashMap. Thêm worker không đảm bảo throughput tăng tuyến tính, đặc biệt khi contention, memory bandwidth hoặc GC đã trở thành bottleneck.

### 9.3. Các thông tin cần công bố kèm kết quả

| Nhóm | Thông tin |
|---|---|
| Runtime | JDK vendor, version/build, GC và JVM flags |
| Phần cứng | CPU model, số core và thread logic, RAM |
| Giới hạn | Container quota, CPU affinity, heap |
| Input | Keyspace, tỷ lệ hot, map size, read/write ratio |
| Thuật toán | merge/compute/LongAdder/AtomicLong, kiểu key/value |
| Work | Threads, iterations, tổng update |
| Phương pháp | Warmup, measurement, forks, dữ liệu khởi tạo |
| Kết quả | Throughput, variation, latency, allocation/GC |
| Correctness | Tổng, phân bố từng key, worker exceptions |
| Reproducibility | Lệnh chạy và phiên bản benchmark |

Phải có thông tin này mới so sánh được hai lần chạy trên các JDK hoặc máy khác. Nếu CI có workload nền không ổn định, xem số như xu hướng và lặp lại ở môi trường kiểm soát.

## 10. Ví dụ Java hoàn chỉnh đã được kiểm thử

Tạo file **`ConcurrentMapLoadDemo.java`**. Chương trình chạy trên **JDK 17+** không cần thư viện ngoài. Nó kết hợp một test mất cập nhật có chủ đích và nhiều scenario cập nhật đúng.

- `MERGE` dùng `ConcurrentHashMap.merge`.
- `LONG_ADDER` dùng `computeIfAbsent(..., new LongAdder()).increment()`.
- `ATOMIC_LONG` dùng `computeIfAbsent(..., new AtomicLong()).incrementAndGet()`.
- `hot` có một key chung; `spread` có một key cho mỗi worker.
- `ready` và `start` tạo thời điểm khởi đầu phối hợp.
- `Future.get` có timeout và chuyển exception worker về test.
- Mỗi run đọc tổng **chỉ sau khi tất cả task kết thúc**.
- Thời lượng lưu trong `Result.elapsedNanos` và có phương thức tính ops/s, nhưng không in con số thiếu ổn định vào expected stdout.

~~~java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class ConcurrentMapLoadDemo {
    enum Algorithm { MERGE, LONG_ADDER, ATOMIC_LONG }

    record Result(Algorithm algorithm, int workers, String distribution,
                  long expected, long actual, int distinctKeys, long elapsedNanos) {
        boolean valid() {
            return expected == actual && elapsedNanos > 0;
        }
        double operationsPerSecond() {
            return expected * 1_000_000_000.0 / elapsedNanos;
        }
    }

    static int showLostUpdate(int workers) throws Exception {
        ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
        map.put("hot", 0);
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch allRead = new CountDownLatch(workers);
        CountDownLatch allowWrite = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();
        try {
            for (int t = 0; t < workers; t++) {
                futures.add(pool.submit(() -> {
                    int stale = map.get("hot");
                    allRead.countDown();
                    allowWrite.await();
                    map.put("hot", stale + 1);
                    return null;
                }));
            }
            if (!allRead.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not read");
            }
            allowWrite.countDown();
            for (Future<?> f : futures) f.get(10, TimeUnit.SECONDS);
            return map.get("hot");
        } finally {
            allowWrite.countDown();
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }

    static Result exercise(Algorithm algorithm, int workers,
                           int iterations, boolean hot) throws Exception {
        ConcurrentHashMap<String, Integer> merge = new ConcurrentHashMap<>();
        ConcurrentHashMap<String, LongAdder> adders = new ConcurrentHashMap<>();
        ConcurrentHashMap<String, AtomicLong> atomics = new ConcurrentHashMap<>();
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();
        try {
            for (int t = 0; t < workers; t++) {
                final String key = hot ? "hot" : "worker-" + t;
                tasks.add(pool.submit(() -> {
                    ready.countDown();
                    start.await();
                    for (int i = 0; i < iterations; i++) {
                        switch (algorithm) {
                            case MERGE -> merge.merge(key, 1, Integer::sum);
                            case LONG_ADDER -> adders.computeIfAbsent(
                                    key, k -> new LongAdder()).increment();
                            case ATOMIC_LONG -> atomics.computeIfAbsent(
                                    key, k -> new AtomicLong()).incrementAndGet();
                        }
                    }
                    return null;
                }));
            }
            if (!ready.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not start");
            }
            long tick = System.nanoTime();
            start.countDown();
            for (Future<?> task : tasks) task.get(10, TimeUnit.SECONDS);
            long elapsed = Math.max(1L, System.nanoTime() - tick);
            long actual = switch (algorithm) {
                case MERGE -> merge.values().stream()
                        .mapToLong(Integer::longValue).sum();
                case LONG_ADDER -> adders.values().stream()
                        .mapToLong(LongAdder::sum).sum();
                case ATOMIC_LONG -> atomics.values().stream()
                        .mapToLong(AtomicLong::get).sum();
            };
            int keys = switch (algorithm) {
                case MERGE -> merge.size();
                case LONG_ADDER -> adders.size();
                case ATOMIC_LONG -> atomics.size();
            };
            long expected = (long) workers * iterations;
            int expectedKeys = hot ? 1 : workers;
            if (actual != expected || keys != expectedKeys) {
                throw new AssertionError("Incorrect total or key count");
            }
            return new Result(algorithm, workers,
                    hot ? "hot" : "spread", expected, actual, keys, elapsed);
        } finally {
            start.countDown();
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }

    static void print(Result value) {
        if (!value.valid()) throw new AssertionError("Bad sample");
        System.out.printf("%s %s t=%d total=%d valid=true%n",
                value.algorithm(), value.distribution(),
                value.workers(), value.actual());
        if (!Double.isFinite(value.operationsPerSecond())) {
            throw new AssertionError("Invalid throughput");
        }
    }

    public static void main(String[] args) throws Exception {
        int wrong = showLostUpdate(4);
        if (wrong != 1) throw new AssertionError("Expected lost update");
        System.out.println("Non-atomic read-then-put: 1 of 4");

        int loops = 10_000;
        print(exercise(Algorithm.MERGE, 1, loops, true));
        print(exercise(Algorithm.MERGE, 4, loops, true));
        print(exercise(Algorithm.ATOMIC_LONG, 4, loops, true));
        print(exercise(Algorithm.LONG_ADDER, 4, loops, true));
        print(exercise(Algorithm.MERGE, 4, loops, false));
        print(exercise(Algorithm.LONG_ADDER, 4, loops, false));
        print(exercise(Algorithm.MERGE, 8, loops, true));
        print(exercise(Algorithm.LONG_ADDER, 8, loops, true));
        System.out.println("All completed counts exact");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ConcurrentMapLoadDemo.java
java ConcurrentMapLoadDemo
~~~

Kết quả đầu ra đã kiểm chứng:

~~~text
Non-atomic read-then-put: 1 of 4
MERGE hot t=1 total=10000 valid=true
MERGE hot t=4 total=40000 valid=true
ATOMIC_LONG hot t=4 total=40000 valid=true
LONG_ADDER hot t=4 total=40000 valid=true
MERGE spread t=4 total=40000 valid=true
LONG_ADDER spread t=4 total=40000 valid=true
MERGE hot t=8 total=80000 valid=true
LONG_ADDER hot t=8 total=80000 valid=true
All completed counts exact
~~~

### 10.1. Giải thích các dòng

`Non-atomic read-then-put: 1 of 4` là race cố ý được điều phối: bốn worker đều đọc 0 và cùng ghi 1. Đây là lỗi vì **phép ghép get/put thiếu atomicity**, không phải bug của map.

Các scenario `MERGE`, `ATOMIC_LONG`, `LONG_ADDER` đều xuất `valid=true` vì số cập nhật được ghi đúng sau khi worker xong. Case `hot t=4` có 40.000 cập nhật tại cùng key, case `spread t=4` có tổng 40.000 cập nhật chia ra 4 key. Với 8 worker và hot key, tổng cần là 80.000.

Dòng cuối `All completed counts exact` khẳng định tất cả bất biến đã được assert. **Không** có tuyên bố LongAdder nhanh hơn merge trong stdout; thứ tự tốc độ phụ thuộc môi trường và cần JMH để đo.

### 10.2. Tại sao không in elapsedNanos?

Thời gian thực tế khác ở mỗi lần chạy, nên nếu in con số cụ thể sẽ không thể cung cấp stdout cố định. Demo lưu và kiểm `operationsPerSecond()` hợp lệ để minh họa đo; kết quả có thể được thu thập thành báo cáo riêng trên máy thực.

Đây là **sanity test correctness và demo cách điều phối**, không phải benchmark chuẩn. Nó chưa có warmup nhiều iteration hay fork JVM độc lập.

### 10.3. Về cleanup

Trong mỗi scenario, khối `finally` mở cổng start nếu cần để worker không bị mắc kẹt khi có lỗi, gọi shutdownNow và chờ kết thúc có timeout. Trong ứng dụng thật, có thể chọn lifecycle executor dài hạn; không tạo một fixed pool mới cho mỗi request production.

### 10.4. LongAdder.sum được kiểm khi nào?

`LongAdder.sum` có thể bỏ sót thay đổi đang xảy ra trong khi nó đọc nhiều cell nội bộ. Demo **đợi tất cả futures thành công** trước khi duyệt values và cộng sum, do đó các update của scenario không còn in-flight. Nếu đọc giữa vòng update, kết quả là giá trị tạm thời, không phải một snapshot atomic.

## 11. Đo đáng tin cậy hơn với OpenJDK JMH

**JMH (Java Microbenchmark Harness)** là công cụ OpenJDK chuyên đo hiệu năng JVM. Nó giúp cấu hình warmup, measurement, fork JVM, nhiều thread và state scope. Đây là lựa chọn phù hợp hơn một lần tự bấm `System.nanoTime()` quanh loop rất ngắn.

**Mã sau cần dự án có JMH, không thuộc JDK tiêu chuẩn**; nó tách khỏi chương trình runnable không dependency ở trên. Trong dự án JMH, tạo `FrequencyBenchmark.java`:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;
import org.openjdk.jmh.annotations.*;

@State(Scope.Benchmark)
public class FrequencyBenchmark {
    @Param({"1", "16", "1024"})
    public int keySpace;

    private ConcurrentHashMap<Integer, Long> merged;
    private ConcurrentHashMap<Integer, LongAdder> added;

    @Setup(Level.Iteration)
    public void setup() {
        merged = new ConcurrentHashMap<>();
        added = new ConcurrentHashMap<>();
    }

    @State(Scope.Thread)
    public static class Worker {
        int cursor;
    }

    @Benchmark
    public void merge(Worker worker) {
        int key = ++worker.cursor & (keySpace - 1);
        merged.merge(key, 1L, Long::sum);
    }

    @Benchmark
    public void longAdder(Worker worker) {
        int key = ++worker.cursor & (keySpace - 1);
        added.computeIfAbsent(
                key, k -> new LongAdder()).increment();
    }
}
~~~

`@State(Scope.Benchmark)` làm map **được chia sẻ giữa benchmark threads**, cần thiết để đo contention. `@State(Scope.Thread) Worker` chứa cursor riêng để không tạo một global counter làm bottleneck khác. `@Param` chọn keySpace 1, 16 hoặc 1.024, đều là lũy thừa 2 nên phép `& (keySpace - 1)` chọn index đúng; không áp công thức này cho keyspace tùy ý.

`@Setup(Level.Iteration)` khởi tạo map trước mỗi iteration. Nếu chỉ muốn benchmark cập nhật key đã tồn tại, cần **pre-populate map trong setup** và không lẫn chi phí cold-insert. Với input nhiều key mới, cần test riêng.

Theo README OpenJDK JMH, nên khởi tạo project Maven với archetype của JMH và build benchmark code đã được annotation processor xử lý.

~~~bash
mvn clean verify
java -jar target/benchmarks.jar FrequencyBenchmark -t 1 -wi 5 -i 5 -f 3
java -jar target/benchmarks.jar FrequencyBenchmark -t 4 -wi 5 -i 5 -f 3
java -jar target/benchmarks.jar FrequencyBenchmark -t 8 -wi 5 -i 5 -f 3
~~~

Đây là **lệnh JMH minh họa**, không phải benchmark đã được chạy trong nhiệm vụ này. `-t` là threads; `-wi` warmup iterations; `-i` measurement iterations; `-f` số forks. Cấu hình là điểm khởi đầu, cần điều chỉnh theo mục đích, thời lượng và tài nguyên.

### 11.1. Chỉ so những gì tương đương về ý nghĩa

`LongAdder` không cung cấp snapshot atomic khi sum đang cạnh tranh, `merge` cập nhật một mapping có value kiểu Long. Đây là hai cách lưu có trade-off khác nhau. Không nên chỉ dựa benchmark throughput để khuyên dùng LongAdder cho nghiệp vụ cần atomic value trên từng lần đọc.

Nếu update count và đọc count thường xuyên, benchmark cần thêm tỷ lệ read/write, không chỉ phép increment.

### 11.2. Những sai sót microbenchmark thường gặp

1. Map mới trong từng lần `@Benchmark` thay vì trước iteration.
2. Mỗi worker có map riêng khiến không có contention chung.
3. Benchmark có một key nhưng production có hàng triệu key.
4. Đo lẫn phép sinh random/chuỗi key khi muốn đo map update thuần.
5. Không warmup khiến JIT compilation chen vào số liệu.
6. Chỉ một fork, một lần đo và báo kết quả nhanh nhất.
7. Không kiểm heap/GC/allocation.
8. Dùng debugger/IDE có tải nền làm môi trường benchmark.
9. Không ghi CPU quota và số core thực tế.
10. Chạy test sai nghĩa: keyspace rất cao nhưng chỉ có 1 worker và cursor không thay.
11. Không kiểm correctness bằng test riêng.
12. Suy từ nanobenchmark ra latency end-to-end dù service còn I/O, queue và serialization.

### 11.3. Read-heavy và hot-key là hai câu hỏi khác nhau

Khi 99% phép truy cập là `get` trên key đã tồn tại, chi phí update có thể không phải bottleneck. Với hệ thống telemetry 99% write vào một key, vấn đề lại là contention rất cao. Tách hai workload và đo cả throughput/latency theo operations có ý nghĩa nghiệp vụ.

## 12. Khi nào cần OpenJDK jcstress?

JMH chủ yếu trả lời **chậm hay nhanh**. Nếu bạn đang tự xây thuật toán gồm nhiều thao tác hoặc ràng buộc visibility phức tạp, **OpenJDK jcstress** là công cụ chuyên quan sát những kết quả được phép/không được phép của concurrency interleaving trong JVM.

| Công cụ | Mục đích | Không nên dùng để kết luận |
|---|---|---|
| Unit test/JUnit | Một kịch bản correctness cụ thể | Mọi interleaving đã được chứng minh |
| Deterministic latch test | Ép một lịch chạy nguy hiểm cụ thể | Performance production |
| jcstress | Thu thập outcome của các actor concurrent | Thông lượng ứng dụng |
| JMH | Benchmark thời gian/throughput | Tính đúng của business invariant |
| Integration/load test | SLA toàn dịch vụ với traffic | Chi phí riêng của một method nhỏ |

Đừng coi một lần test vượt 100.000 iteration là bằng chứng thuật toán custom linearizable. Test race có yếu tố lịch chạy; jcstress giúp tăng coverage cho nhiều outcome, nhưng bản thân nó cũng cần mô hình đúng và nhiều mẫu.

## 13. Đọc trong lúc ghi không phải snapshot transaction

### 13.1. LongAdder.sum

~~~java
long observed = counts.get("hot").sum();
~~~

Trong lúc các thread khác `increment()`, `sum()` không phải atomic snapshot. Nó có giá trị như **telemetry gần hiện tại**, không phải quyết định quota/tiền tệ cần đọc chính xác tại một điểm duy nhất.

`sumThenReset()` cũng không atomic với các cập nhật đang diễn ra. Nếu cần đếm chính xác theo khoảng thời gian, hãy thiết kế cơ chế đổi epoch hoặc dừng/chuyển writers trước khi snapshot; không chỉ gọi reset giữa luồng ghi và cho rằng mọi sự kiện được gán đúng một kỳ.

### 13.2. size và iterator

`ConcurrentHashMap` cung cấp weakly consistent traversal. Khi còn update, không chắc một vòng `forEach` đã thấy mọi mapping mới tại cùng một snapshot; giá trị `mappingCount` dùng cho giám sát số key cũng có thể là trạng thái tạm thời.

Nếu business invariant cần snapshot trên toàn map, phải có protocol bên ngoài. Nếu mục tiêu là metric gần thời gian thực, dùng phương pháp đo phù hợp và công bố nó là approximate khi writer còn chạy.

### 13.3. AtomicLong cần hiểu phạm vi atomic

`AtomicLong.get` cung cấp một phép đọc atomic của **một counter**, nhưng đọc lần lượt 100 AtomicLong từ 100 key không tự tạo snapshot atomically nhất quán trên cả 100 key. Phân biệt atomic per counter với atomic aggregate toàn bản đồ.

## 14. Những yếu tố làm hiệu năng thay đổi

### 14.1. Hash collision

Nếu nhiều key khác nhau cùng `hashCode()`, lookup và update có thể tốn thêm công việc. Key nên có `equals` và `hashCode` đúng hợp đồng, nhất quán. Đừng thay giá trị một key mutable sau khi đã dùng làm khóa map.

Ví dụ key tạo hash collision có chủ đích để test trường hợp xấu:

~~~java
record BadHash(int id) {
    @Override
    public int hashCode() {
        return 1;
    }
}
~~~

Đây là mảnh code Java 17+; `equals` của record vẫn phân biệt theo id. Test collisions riêng, không coi nó là phân bố bình thường của mọi ứng dụng.

### 14.2. Resize và initial capacity

`ConcurrentHashMap(initialCapacity)` cho phép gợi ý sức chứa ban đầu. Nếu ứng dụng sẽ lưu nhiều key ngay từ đầu, sizing phù hợp có thể giảm chi phí resize ở pha insert. Nếu set quá lớn, có thể tăng footprint không cần thiết.

Constructor có `concurrencyLevel` vẫn tồn tại theo API hiện hành như một **sizing hint**. Đừng dùng mô hình cũ “concurrencyLevel bằng số segment lock cố định” để lý giải chi tiết hiện thực JDK hiện nay.

### 14.3. Allocation và GC

`merge(key,1L,Long::sum)` có thể tạo nhiều giá trị Long mới. `AtomicLong` và `LongAdder` giữ object theo key, nhưng LongAdder có thể dùng thêm các cell bên trong khi contention tăng. Đo **bytes allocated/op, GC pauses, heap footprint**, không chỉ ops/s.

Nếu có hàng triệu key ít khi được cập nhật, bộ nhớ của map các LongAdder có thể lớn đáng kể dù mỗi key chỉ được tăng một lần. Nếu có một key cực nóng, việc phân tán update của LongAdder có thể đáng giá hơn chi phí đó.

### 14.4. Hardware và JVM

CPU core vật lý, hyper-threading, memory bandwidth, cache coherence, GC, tiered compilation và CPU quota ảnh hưởng kết quả. Nếu tăng thread từ 8 lên 64 trên máy ít core mà throughput giảm, chưa thể khẳng định lỗi do thuật toán; cần profiler và kiểm saturation.

## 15. Ma trận test được đề xuất

| Ca thử | Điều kiện | Bất biến/câu hỏi |
|---|---|---|
| Một worker, một key | 10.000 update | Tổng 10.000 |
| Bốn worker, một key | 40.000 update | Không lost update |
| Tám worker, một key | 80.000 update | Không lost update |
| Bốn worker, bốn key | Mỗi worker một key | Mỗi key đúng 10.000 |
| Nhiều key uniform | 1.024 key | Tổng và phân bố đúng |
| 99% hot key | Skew mạnh | Throughput thay đổi thế nào? |
| 90% read | Reader + writer | Đọc hợp đồng, không snapshot giả |
| Cold insert | Key chưa tồn tại | Allocation/resize và correctness |
| Pre-populated | Key có sẵn | Chi phí steady-state |
| Colliding hash | Nhiều key chung hash | Suy giảm tra cứu/update |
| Worker ném exception | Fault injection | Coordinator fail thay vì pass |
| Task treo | Không tới latch/không xong | Timeout, cleanup an toàn |
| Remove/reinsert | Update và eviction | Lifecycle count được định nghĩa |
| Nhiều lần fork | JMH | Số liệu ổn định hay nhiễu |
| JDK khác nhau | Cùng workload | Khác biệt implementation/VM |
| Memory pressure | Keyspace rất lớn | GC, OOM và giới hạn hệ thống |

### 15.1. Không benchmark khi test correctness chưa pass

Một thuật toán `get+put` có thể nhanh hơn `merge` nhưng **sai tổng**. Kết quả throughput của phép tính sai không phải phương án tối ưu hợp lệ. Chỉ so những implementation có ngữ nghĩa đáp ứng yêu cầu; nêu rõ trade-off đọc snapshot của LongAdder so với AtomicLong.

### 15.2. Cách diễn giải thống kê

Sau nhiều benchmark run, xem mean và độ biến thiên/interval, không cherry-pick best run. Khi JMH báo throughput cao hơn nhưng độ bất định chồng lấn lớn, có thể chưa đủ căn cứ kết luận khác biệt. Nên bổ sung GC/memory profiling và workload gần production.

### 15.3. Khả năng mở rộng không thay thế hiệu năng toàn hệ thống

Một counter rất nhanh không giúp service đạt SLA nếu phần lớn thời gian ở network, DB hoặc serialization. Với hệ thống phân tán nhiều JVM, `ConcurrentHashMap` chỉ quản lý trạng thái **trong một process**, không phải bộ đếm global transactional. Nếu cần quota hoặc số dư trên nhiều node, chọn cơ chế dữ liệu có consistency phù hợp.

## 16. Lỗi thường gặp

**1. Dùng `get` rồi `put` để tăng count.** Hai thao tác không tạo atomic RMW; dùng merge/compute hoặc counter atomic.

**2. Chỉ kiểm `size()`.** Size đếm key, không đếm tần suất; kiểm tổng và từng key.

**3. Chỉ chạy một thread.** Không tạo contention thực sự.

**4. Dùng sleep để ép race.** Không bảo đảm interleaving; dùng latch và kiểm điều kiện.

**5. Tạo quá ít worker cho latch.** Worker đầu chiếm hết pool và chờ worker chưa chạy; khớp pool size/ready logic.

**6. Không lấy exception từ `Future.get`.** Worker lỗi nhưng test vẫn báo pass.

**7. Không đợi worker xong trước khi sum.** Đọc tạm thời rồi coi là sai data.

**8. Coi `LongAdder.sum` là atomic snapshot khi writer đang tăng.** Không có bảo đảm ấy.

**9. Dùng `sumThenReset` như giao dịch cắt kỳ.** Không atomic khi có writer.

**10. Cho mapping callback làm HTTP/DB blocking.** Có thể giữ các update khác chờ và tăng contention.

**11. Sửa map từ callback compute.** Vi phạm hướng dẫn/hợp đồng, dễ gặp recursion lỗi.

**12. Không hiểu `null`.** ConcurrentHashMap không lưu null key/value.

**13. Cho rằng LongAdder luôn nhanh hơn AtomicLong.** Phụ thuộc contention và memory.

**14. Chọn LongAdder cho quota cần counter atomic tức thời.** Sum không phù hợp yêu cầu ấy.

**15. Dùng HashMap chia sẻ không sync làm baseline.** Dữ liệu và kết quả benchmark không hợp lệ.

**16. Benchmark hot key rồi áp cho key phân tán.** Hai loại contention khác hẳn.

**17. Không tách cold insert và steady update.** Allocation/resize làm kết quả không tương đương.

**18. Không warmup/fork khi đo loop rất ngắn.** JIT/GC/scheduler gây nhiễu.

**19. Dùng System.nanoTime một lần để công bố winner.** Cần benchmark lặp lại, điều kiện máy rõ.

**20. So thời gian khi tổng lượng việc khác.** Phân biệt strong scaling và scaled workload.

**21. Không ghi JDK và CPU.** Không thể tái lập.

**22. Chỉ xem throughput.** Bỏ quên tail latency, allocation và heap.

**23. Coi concurrencyLevel là số segment lock cố định hiện đại.** API hiện hành không hứa giả định đó.

**24. Dùng iterator/size đang cập nhật như snapshot nhất quán.** CHM cho weak consistency.

**25. Không tính integer overflow.** Tần suất cập nhật cao và thời gian dài có thể tràn.

**26. Không cleanup executor.** Test rò thread có thể phá các phép đo sau.

## 17. Câu hỏi tự luyện

1. Vì sao ConcurrentHashMap thread-safe nhưng `get+put` có thể mất update?
2. Với bốn worker đều đọc 0 rồi ghi giá trị tăng một, kết quả cuối bằng bao nhiêu?
3. `merge` giúp giải quyết vấn đề gì?
4. LongAdder tốt cho mục đích nào và có hạn chế gì với `sum`?
5. AtomicLong khác LongAdder khi cần đọc counter chính xác giữa các update như thế nào?
6. Với 8 worker, mỗi worker tăng cùng key 10.000 lần, tổng mong đợi là bao nhiêu?
7. Vì sao map size bằng 1 chưa chứng minh số update đúng?
8. CountDownLatch ready/start giúp test contention ra sao?
9. Tại sao phải kiểm Future.get và timeout?
10. Hot key khác spread keys về contention thế nào?
11. Tại sao cần test Zipf/skew?
12. Strong scaling và weak scaling khác nhau ra sao?
13. Nếu throughput 1 worker = 100k và 4 worker = 300k, efficiency tại 4 là bao nhiêu?
14. Vì sao nên đo bằng JMH thay vì một lần System.nanoTime?
15. `@State(Scope.Benchmark)` và `@State(Scope.Thread)` khác gì trong benchmark?
16. JMH và jcstress giải quyết những câu hỏi khác nhau nào?
17. Vì sao LongAdder.sumThenReset không phù hợp làm atomic snapshot giữa lúc ghi?
18. Vì sao `merge` không tạo transaction khi thay đổi hai key?
19. Khi key cardinality tăng rất lớn, tài nguyên nào cần theo dõi?
20. Vì sao ConcurrentHashMap trong một JVM không làm được global counter nhất quán trên nhiều node?

**Gợi ý đáp án:** (1) Compound read-modify-write không atomic. (2) 1, vì cả bốn ghi từ giá trị cũ. (3) Atomic update của mapping. (4) Thống kê ghi dày; sum không atomic snapshot đang cập nhật. (5) AtomicLong có một giá trị atomic, LongAdder phân tán cập nhật. (6) 80.000. (7) Size đếm key. (8) Bảo đảm worker sẵn sàng trước khi cùng bắt đầu. (9) Không bỏ qua lỗi/treo của task. (10) Hot cùng counter, spread tách key. (11) Traffic thực có thể không đều. (12) Tổng work cố định so với work tăng cùng worker. (13) 0,75. (14) JMH có warmup, forks, nhiều iteration. (15) Map chung so với state riêng thread. (16) Hiệu năng so với interleaving/correctness. (17) Không atomic khi writer đang chạy. (18) Atomic per key không atomic across keys. (19) Heap, allocation, GC, cache. (20) Dữ liệu chỉ thuộc một process, thiếu coordination và transaction phân tán.

## Tóm tắt

**Correctness trước, performance sau.** `ConcurrentHashMap` bảo vệ các thao tác riêng lẻ nhưng không tự biến `get+put` thành một phép tăng atomic. Dùng `merge`/`compute` cho cập nhật mapping; `LongAdder` cho thống kê ghi dày khi chấp nhận tổng không snapshot atomic trong lúc ghi; `AtomicLong` khi cần thao tác atomic trên một counter. Trong test, dùng latch, lấy exception và đợi tất cả futures rồi kiểm tổng. Trong benchmark, phân biệt hot/spread/skew, warmup/fork, throughput và tài nguyên. Không hứa tốc độ tuyến tính hoặc một implementation tốt nhất cho mọi workload.

### Tài liệu chính thức, hiện còn áp dụng

- [Oracle Java SE 26 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Oracle Java SE 26 — LongAdder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [Oracle Java SE 26 — AtomicLong](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html)
- [Oracle Java SE 26 — CountDownLatch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Oracle Java SE 26 — ExecutorService](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)
- [OpenJDK — Java Concurrency Stress (jcstress)](https://github.com/openjdk/jcstress)
