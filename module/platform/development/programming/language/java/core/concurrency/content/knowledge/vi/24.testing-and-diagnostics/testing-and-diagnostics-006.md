# Kiểm tra invariant và lỗi mất dữ liệu trong Java concurrency

## 1. Tại sao cần kiểm tra invariant?

Một chương trình chạy đa luồng có thể không ném exception, không deadlock, vẫn trả kết quả sai: một lần cập nhật biến mất, cùng bản ghi được xử lý hai lần, số lượng phần tử giữa các bước pipeline không khớp, hoặc trạng thái chia sẻ vi phạm quy tắc nghiệp vụ. Lỗi thường chỉ xuất hiện khi nhiều thread xen kẽ vào những thời điểm khó tái hiện.

**Invariant** là điều kiện phải đúng ở các điểm kiểm chứng được xác định rõ. Trong concurrency, điều kiện đó có thể là thuộc tính của **trạng thái** (số dư tổng không đổi), **kết quả** (không mất ID nào), **lịch sử thao tác** (mỗi thao tác thành công có hiệu lực đúng một lần) hoặc **vòng đời** (mọi tác vụ được nhận đều kết thúc, hủy hoặc được ghi nhận là chưa hoàn tất).

Ví dụ:

- Bộ đếm: sau `N` lần tăng thành công, kết quả phải là `initial + N`.
- Chuyển tiền nội bộ: khi chuyển `x` từ A sang B thành công, `A + B` phải được bảo toàn và không số dư nào âm nếu quy tắc không cho phép.
- Pipeline dữ liệu: sau khi tất cả producer/consumer đã dừng, mỗi ID được chấp nhận phải có đúng một kết quả xử lý hoặc một trạng thái loại bỏ có chủ đích, có thể kiểm tra.
- Hàng đợi tác vụ: tác vụ đã được xác nhận nhận vào không được biến mất giữa nhận, xử lý, retry và ghi kết quả.
- Cache hoặc collection concurrent: cấu trúc không bị hỏng và các cập nhật phải tuân theo semantics đã chọn, kể cả khi có tranh chấp.

**Mục tiêu bài học:** xây dựng oracle độc lập với mã cần kiểm thử, gây ra những interleaving khó bằng công cụ đồng bộ, kiểm tra dữ liệu mất/trùng, tránh phép đo sai do snapshot không nhất quán, và biết giới hạn của stress test.

Bài học chỉ sử dụng các API Java 17+ nói chung (`java.util.concurrent`, `AtomicInteger`, lock, queue và test harness). Không phụ thuộc framework.

## 2. Phân loại invariant trước khi viết test

| Loại | Ví dụ điều kiện | Thời điểm kiểm chứng |
| --- | --- | --- |
| Bảo toàn số lượng | `accepted = processed + pending + inFlight + rejectedAfterAccept` | Ở checkpoint nhất quán; các trạng thái phải loại trừ nhau. |
| Bảo toàn giá trị | `balanceA + balanceB = initialTotal` | Bên trong khóa bảo vệ snapshot hoặc khi mọi chuyển tiền đã dừng. |
| Không âm/không vượt giới hạn | `stock >= 0`, `activeTasks <= capacity` | Sau mỗi thao tác nguyên tử hoặc từ snapshot nhất quán. |
| Không mất ID | Mọi ID đầu vào đã nhận đều hiện diện ở tập kết quả hoặc có trạng thái thất bại được ghi nhận. | Sau khi các worker hoàn tất và queue đã drain. |
| Không trùng hiệu ứng | Một ID chỉ được ghi kết quả một lần theo semantics yêu cầu. | Dùng tập ID và bộ đếm lần xuất hiện, hoặc quan sát hệ thống đích. |
| Thứ tự | Các phần tử của một nguồn đến đúng thứ tự nếu contract yêu cầu FIFO theo nguồn. | So lịch sử theo từng key/partition; không áp đặt total order khi API không cam kết. |
| Liveness / progress | Mọi tác vụ hợp lệ cuối cùng hoàn tất trong điều kiện giả định đã nêu. | Có deadline/timeout, số lượng task còn chạy và chính sách hủy. |

Không nên áp một invariant toàn cục vào **mọi thời điểm giữa các lệnh** nếu thao tác chỉ bảo đảm đúng ở ranh giới transaction. Ví dụ chuyển tiền qua hai field cần một lock chung để người đọc thấy snapshot nguyên tử; đọc từng field không đồng bộ có thể nhìn một nửa giao dịch rồi kết luận sai.

### Định nghĩa thế nào là "mất dữ liệu"

Cần chốt chính xác phạm vi của `accepted`:

- **Chưa được nhận:** producer thử `offer` vào queue đầy và nhận `false`; việc từ chối là có thể hợp lệ nếu hợp đồng cho phép và caller biết. Không được lặng lẽ ghi nhận là đã nhận.
- **Đã được nhận nhưng chưa xử lý:** item đang ở queue hoặc ở worker; chưa thể kết luận mất.
- **Đã được xử lý nhưng chưa commit:** kết quả trong bộ nhớ chưa chắc đã bền vững. Nếu ứng dụng restart, có thể phải retry.
- **Đã commit nhưng chưa acknowledge:** retry có thể khiến hiệu ứng bị lặp; đây là vấn đề duplicate bên cạnh data loss.
- **Bị loại bỏ có chủ đích:** phải có lý do, counter hoặc dead-letter record; nếu hợp đồng cho phép thì không tính là mất không giải thích.

Trong một pipeline chỉ chạy trong RAM, test có thể chứng minh các item không mất **trong quá trình chạy được quan sát**. Nó **không** chứng minh tính bền vững sau mất điện, process crash hoặc việc ghi xuống hệ thống ngoài. Các bảo đảm đó đòi hỏi giao thức lưu trữ/commit riêng.

## 3. Nguyên nhân thường gặp: read–modify–write không nguyên tử

Xét:

```java
int current = counter;
counter = current + 1;
```

Hai câu lệnh thực hiện thao tác đọc, tính, ghi. Nếu hai thread cùng đọc `7` trước khi bất kỳ thread nào ghi, cả hai có thể ghi `8`: đã có hai lần tăng được yêu cầu nhưng chỉ tăng thực tế một đơn vị. Đó là **lost update**.

```text
                  Thread A                  Thread B
state = 7
                  read -> 7
                                            read -> 7
                  compute 8
                                            compute 8
                  write 8
                                            write 8
state = 8         (mong đợi 9; đã mất một cập nhật)
```

Biến `volatile` giải quyết một số yêu cầu visibility và ordering, nhưng **không biến `counter++` thành thao tác nguyên tử**. Một số thao tác atomic và lock bảo đảm read–modify–write không bị xen vào nhau; cần chọn theo invariant phải bảo vệ.

Các cách đúng cho counter độc lập:

- `AtomicInteger.incrementAndGet()` hoặc `AtomicLong.incrementAndGet()`: một bước read–modify–write nguyên tử.
- `synchronized` / `ReentrantLock` bao quanh toàn bộ read–modify–write.
- `LongAdder`: phù hợp counter thống kê có contention cao; `sum()` trong lúc còn cập nhật không phải một snapshot nguyên tử. Không dùng thay atomic cho thuật toán đòi hỏi kết quả tăng tuần tự chính xác ở mọi thời điểm.

## 4. Ví dụ Java 17+ tạo lost update có kiểm soát

Một stress test gọi nhiều thread cùng chạy `counter++` có thể vô tình cho kết quả đúng ở vài lần chạy. Để minh họa **chắc chắn** hiện tượng lost update, ví dụ sau dùng `CyclicBarrier` ép bốn thread cùng đọc giá trị cũ trước khi bất kỳ thread nào ghi. Sau mỗi vòng, tất cả cùng ghi `old + 1`. Nhánh an toàn dùng `AtomicInteger.incrementAndGet()`.

Tạo file **`LostUpdateInvariantDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class LostUpdateInvariantDemo {
    private static final int THREADS = 4;
    private static final int ROUNDS = 20;

    private static final class UnsafeCounter {
        volatile int value;
    }

    private static int forcedLostUpdates() throws Exception {
        UnsafeCounter counter = new UnsafeCounter();
        CyclicBarrier allRead = new CyclicBarrier(THREADS);
        CyclicBarrier allWrote = new CyclicBarrier(THREADS);
        ExecutorService pool = Executors.newFixedThreadPool(THREADS);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int t = 0; t < THREADS; t++) {
                tasks.add(pool.submit(() -> {
                    for (int i = 0; i < ROUNDS; i++) {
                        int old = counter.value;  // Bốn thread cùng đọc.
                        allRead.await();          // Chờ tất cả đã đọc.
                        counter.value = old + 1;  // Bốn thread cùng ghi.
                        allWrote.await();         // Chờ hết vòng mới đọc tiếp.
                    }
                    return null;
                }));
            }

            for (Future<?> task : tasks) {
                task.get(10, TimeUnit.SECONDS);
            }
            return counter.value;
        } finally {
            pool.shutdownNow(); // Đề phòng một worker lỗi hoặc bị treo.
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static int atomicUpdates() throws Exception {
        AtomicInteger counter = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(THREADS);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int t = 0; t < THREADS; t++) {
                tasks.add(pool.submit(() -> {
                    for (int i = 0; i < ROUNDS; i++) {
                        counter.incrementAndGet();
                    }
                    return null;
                }));
            }

            for (Future<?> task : tasks) {
                task.get(10, TimeUnit.SECONDS);
            }
            return counter.get();
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        int expected = THREADS * ROUNDS;
        int unsafe = forcedLostUpdates();
        int safe = atomicUpdates();

        System.out.println("expected=" + expected);
        System.out.println("unsafe=" + unsafe);
        System.out.println("atomic=" + safe);
        System.out.println("unsafeInvariant=" + (unsafe == expected));
        System.out.println("atomicInvariant=" + (safe == expected));
    }
}
```

Lệnh chạy:

```bash
javac LostUpdateInvariantDemo.java
java LostUpdateInvariantDemo
```

Output khi hai phần hoàn thành trong thời hạn:

```text
expected=80
unsafe=20
atomic=80
unsafeInvariant=false
atomicInvariant=true
```

**Vì sao `unsafe` luôn bằng 20 trong ví dụ này?** Mỗi vòng, `allRead.await()` không cho thread ghi trước khi tất cả đã đọc giá trị trước vòng. Vì các thread đều ghi cùng một giá trị `old + 1` và `allWrote.await()` đóng vòng, kết quả tăng đúng một đơn vị mỗi vòng thay vì bốn. Đây là **test cố tình tạo interleaving xấu**, không phải tần suất race tự nhiên trong ứng dụng thực.

**Vì sao `atomic` bằng 80?** Có đúng `4 × 20` lần `incrementAndGet()`; mỗi lời gọi thực hiện tăng nguyên tử, và `Future.get(...)` chờ toàn bộ tác vụ hoàn thành. `Future.get` cũng cung cấp quan hệ happens-before giữa hành động trong task và code sau khi `get` thành công.

Một timeout hoặc exception làm bài chạy thất bại; không được diễn giải trường hợp đó là output như trên. `shutdownNow()` chỉ yêu cầu interrupt; task phải hợp tác để dừng. Ví dụ dùng hai barrier đều hỗ trợ interrupt.

## 5. Kiểm tra mất/trùng dữ liệu bằng định danh ổn định

Tăng counter đến đúng số lượng chưa đủ: một item có thể bị xử lý hai lần trong khi item khác biến mất, tổng số vẫn bằng kỳ vọng. Để bắt lỗi đó, mỗi input cần **ID duy nhất** hoặc khóa nghiệp vụ ổn định; kiểm tra ba thuộc tính độc lập:

1. **Coverage:** tất cả ID được chấp nhận có mặt trong tập kết quả hợp lệ.
2. **Multiplicity:** mỗi ID có số lần xử lý/commit đúng theo contract (thường là một lần).
3. **Count:** tổng kết quả, tổng ID distinct và số lượng accepted thống nhất sau khi hệ thống ổn định.

Ví dụ: input là `{1,2,3,4}`, output là `{1,2,2,4}`. `input.size == output.size == 4` nhưng ID `3` đã mất và `2` bị trùng. Chỉ kiểm đếm tổng số sẽ bỏ sót lỗi.

Nên dùng một oracle khác với đường code kiểm thử: producer ghi lại ID thành công ngay khi hợp đồng xác nhận nhận dữ liệu; phía output ghi kết quả thực sự sau khi commit. Nếu dùng chung một counter sai cho cả “expected” lẫn “actual”, test có thể cho kết quả đẹp nhưng vô nghĩa.

## 6. Ví dụ Java 17+: kiểm tra hàng đợi producer–consumer không mất bản ghi

Ví dụ này dùng `ArrayBlockingQueue` có giới hạn dung lượng để tạo backpressure. Ba producer gửi tổng cộng 1.500 ID khác nhau; hai consumer lấy và ghi lại ID. Test đợi **producer kết thúc trước**, sau đó mới gửi mỗi consumer một marker dừng để các item còn tồn trong queue được xử lý. Sau khi consumer hoàn tất, test đo missing, duplicate và số bản ghi được nhận/xử lý.

Tạo file **`PipelineInvariantDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PipelineInvariantDemo {
    private static final int PRODUCERS = 3;
    private static final int CONSUMERS = 2;
    private static final int PER_PRODUCER = 500;
    private static final int TOTAL = PRODUCERS * PER_PRODUCER;

    private record Message(int id, boolean stop) { }

    public static void main(String[] args) throws Exception {
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(64);
        Set<Integer> seen = ConcurrentHashMap.newKeySet();
        AtomicInteger accepted = new AtomicInteger();
        AtomicInteger processed = new AtomicInteger();
        AtomicInteger duplicates = new AtomicInteger();
        ExecutorService pool =
                Executors.newFixedThreadPool(PRODUCERS + CONSUMERS);
        List<Future<?>> consumers = new ArrayList<>();
        List<Future<?>> producers = new ArrayList<>();

        try {
            for (int c = 0; c < CONSUMERS; c++) {
                consumers.add(pool.submit(() -> {
                    while (true) {
                        Message message = queue.take();
                        if (message.stop()) {
                            return null;
                        }
                        if (!seen.add(message.id())) {
                            duplicates.incrementAndGet();
                        }
                        processed.incrementAndGet();
                    }
                }));
            }

            for (int p = 0; p < PRODUCERS; p++) {
                final int producerId = p;
                producers.add(pool.submit(() -> {
                    for (int i = 0; i < PER_PRODUCER; i++) {
                        int id = producerId * PER_PRODUCER + i;
                        queue.put(new Message(id, false));
                        accepted.incrementAndGet();
                    }
                    return null;
                }));
            }

            // Chỉ tiếp tục sau khi tất cả producer hoàn thành.
            for (Future<?> f : producers) {
                f.get(10, TimeUnit.SECONDS);
            }

            // Marker FIFO đứng sau toàn bộ item đã được đặt vào queue.
            for (int c = 0; c < CONSUMERS; c++) {
                if (!queue.offer(new Message(-1, true),
                                 5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Không gửi được marker");
                }
            }

            for (Future<?> f : consumers) {
                f.get(10, TimeUnit.SECONDS);
            }

            int missing = 0;
            for (int id = 0; id < TOTAL; id++) {
                if (!seen.contains(id)) {
                    missing++;
                }
            }

            boolean ok = accepted.get() == TOTAL
                    && processed.get() == TOTAL
                    && seen.size() == TOTAL
                    && duplicates.get() == 0
                    && missing == 0;

            System.out.println("accepted=" + accepted.get());
            System.out.println("processed=" + processed.get());
            System.out.println("distinct=" + seen.size());
            System.out.println("duplicates=" + duplicates.get());
            System.out.println("missing=" + missing);
            System.out.println("INVARIANTS_OK=" + ok);

            if (!ok) {
                throw new AssertionError("Pipeline vi phạm invariant");
            }
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Chạy:

```bash
javac PipelineInvariantDemo.java
java PipelineInvariantDemo
```

Output khi toàn bộ tác vụ hoàn tất bình thường:

```text
accepted=1500
processed=1500
distinct=1500
duplicates=0
missing=0
INVARIANTS_OK=true
```

**Tại sao test có thể kết luận ở cuối?**

- Mỗi producer sở hữu một khoảng ID không chồng lấn; `put` thành công rồi mới tăng `accepted`. `ArrayBlockingQueue.put` chờ khi queue đầy, thay vì lặng lẽ bỏ item.
- Sau `Future.get(...)` của tất cả producer, không còn producer nào thêm bản ghi; chỉ lúc đó test gửi đúng hai marker.
- Queue có thứ tự FIFO ở mức các item thực sự được đưa vào. Mỗi consumer dừng khi gặp một marker; do marker được thêm sau toàn bộ bản ghi nên không còn item dữ liệu nào nằm phía sau marker. Hai consumer vẫn có thể hoàn tất xử lý ở những thời điểm khác nhau.
- `seen.add(id)` dùng tập concurrent để phát hiện ID đã từng xuất hiện; `duplicates` ghi lại việc xử lý lặp. `processed` tính số lần xử lý, còn `seen.size()` tính số ID khác nhau.
- Test chỉ đọc các số cuối **sau khi cả hai consumer đã dừng**, tránh so sánh các counter không được chụp tại cùng thời điểm khi hệ thống vẫn hoạt động.
- `Future.get` có timeout để không chờ mãi nếu producer/consumer lỗi hoặc thiếu tín hiệu dừng. Khối `finally` yêu cầu dừng executor do chính chương trình tạo.

**Giới hạn:** chương trình chứng minh một pipeline Java trong bộ nhớ với đường chạy này. `processed.incrementAndGet()` chỉ là phép đo trong RAM, chưa chứng minh ghi dữ liệu bền vững sang cơ sở dữ liệu hay hệ thống khác. `ConcurrentHashMap.newKeySet()` lưu toàn bộ ID, phù hợp kiểm thử giới hạn, có thể không phù hợp telemetry production rất lớn.

## 7. Tạo test có khả năng bắt lỗi thay vì phụ thuộc may rủi

### 7.1. Dùng công cụ đồng bộ tạo điểm giao tranh

- `CountDownLatch`: đưa nhiều thread đến một vạch xuất phát, chờ một thao tác hoàn tất.
- `CyclicBarrier` / `Phaser`: ép các thread chạm các pha cụ thể để tái hiện xen kẽ bất lợi.
- `Semaphore`: giới hạn số thread được vào pha nhạy cảm.
- `Future.get(timeout, unit)` và `ExecutorService.awaitTermination`: giới hạn thời gian chờ và truyền lỗi từ worker về test.
- `AtomicBoolean` / `AtomicInteger`: ghi nhận event hoặc trạng thái test một cách an toàn.

Đặt đồng bộ theo **sự kiện có ý nghĩa**, như “cả hai thread đã đọc version cũ” hay “consumer đã nhận item nhưng chưa commit”. Một `Thread.sleep(100)` thường chỉ làm tăng khả năng tình cờ có race, không bảo đảm xen kẽ mong muốn và dễ gây flaky test trên CI.

### 7.2. Giữ một negative control

Một test chống lost update nên có ít nhất:

- Nhánh triển khai sai có thể bị test bắt (`unsafeInvariant=false` trong ví dụ).
- Nhánh sửa đúng trả kết quả đạt kỳ vọng.
- Assert hiển thị **expected** được tính từ dữ liệu đầu vào, không dựa vào biến đang được kiểm tra.

Nếu test cũng PASS khi cố ý thay `AtomicInteger.incrementAndGet()` bằng `value++` không đồng bộ, có thể test thiếu contention hoặc oracle không đủ mạnh.

### 7.3. Chạy stress và đổi điều kiện tải

Sau test có barrier, thử nhiều vòng chạy với số thread, queue capacity, kích thước batch, tác vụ CPU/I/O, loại executor và thời điểm hủy khác nhau. Có thể sử dụng seed cố định khi ngẫu nhiên hóa input để tái hiện cùng dữ liệu; tuy nhiên seed cố định **không bảo đảm cùng thread schedule**.

Stress testing có thể **phát hiện** lỗi khi thất bại, nhưng nghìn lượt PASS không chứng minh không còn mọi interleaving sai. Với các thuật toán lock-free, atomic hoặc memory ordering phức tạp, có thể tham khảo **JCStress** (harness thử nghiệm hành vi concurrent/JMM). Với throughput/latency, **JMH** phục vụ benchmark hiệu năng, không phải bằng chứng tính đúng đắn.

## 8. Invariant nhiều biến và snapshot nhất quán

Giả sử `balanceA=100`, `balanceB=100`. Một transfer 30 đơn vị yêu cầu:

```text
Trước: A=100, B=100, total=200
Sau:   A= 70, B=130, total=200
```

Nếu cập nhật A rồi B mà không có cơ chế bảo vệ toàn giao dịch, thread khác có thể đọc giữa hai câu lệnh và nhìn tổng tạm thời chỉ là 170. Dùng `volatile` riêng trên hai field hoặc `AtomicLong` riêng cho từng field vẫn **không** làm cặp giá trị thành một snapshot nguyên tử.

Mẫu bảo vệ trạng thái gắn với nhau (đoạn code minh họa trong một class Java):

```java
private final Object balanceLock = new Object();
private long balanceA = 100;
private long balanceB = 100;

public boolean transferAToB(long amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("amount âm");
    }
    synchronized (balanceLock) {
        if (balanceA < amount) {
            return false;
        }
        balanceA -= amount;
        balanceB += amount;
        return true;
    }
}

public long totalSnapshot() {
    synchronized (balanceLock) {
        return balanceA + balanceB;
    }
}
```

Ở đây cả cập nhật lẫn snapshot đi qua **cùng** monitor. Test có thể gọi `totalSnapshot()` sau mỗi transfer (hoặc đồng thời từ thread khác) và kiểm tra tổng bằng 200, bởi không nhìn được trạng thái chuyển tiền nửa chừng. Với bất kỳ quy tắc invariant khác như “không âm” hoặc “giữ đúng hạn mức”, logic phải kiểm tra **trong cùng ranh giới đồng bộ hóa**.

Tuy nhiên, invariant `A + B = 200` **chưa đủ**: code có thể ghi nhầm A/B nhưng vẫn giữ tổng. Cần kiểm thêm số transfer thành công, biến động từng tài khoản, thông báo lỗi và lịch sử kết quả. Đó là lý do một hệ thống tốt cần **nhiều invariant bổ sung**, mỗi invariant bảo vệ một thuộc tính độc lập.

Khi thao tác trải trên database, dịch vụ mạng hoặc nhiều tiến trình, monitor trong một JVM không thể tạo atomic transaction xuyên hệ thống. Khi đó cần cơ chế commit và nhất quán thích hợp ở lớp lưu trữ/giao tiếp; kiểm thử Java ở mức thread chỉ là một phần.

## 9. Happens-before, visibility và phép quan sát của test

Có hai nguy cơ khác nhau:

1. **Cập nhật không nguyên tử:** `counter++` có thể mất update dù biến là `volatile`.
2. **Đọc không thấy giá trị mới:** một thread không được bảo đảm thấy trạng thái do thread khác ghi nếu thiếu quan hệ happens-before phù hợp.

Những quan hệ thường giúp thiết kế test đúng:

- Giải phóng monitor rồi thread khác lấy **cùng monitor** tạo quan hệ happens-before.
- Ghi `volatile` rồi đọc biến volatile đó phù hợp theo quy tắc JMM; nhưng volatile không bảo vệ transaction gồm nhiều field.
- Một lần gọi `AtomicInteger.incrementAndGet` cung cấp atomic update và ngữ nghĩa bộ nhớ của các thao tác atomic tương ứng.
- Các hành động trong task xảy ra trước `Future.get` trả về thành công theo contract của `java.util.concurrent`.
- Những hành động trước `CountDownLatch.countDown` xảy ra trước những hành động sau khi thread khác `await` thành công trên latch đó.
- `Thread.join` sau khi thread hoàn thành cũng thiết lập visibility tương ứng.

Kết luận thực hành: hãy **đợi task hoàn tất bằng công cụ đồng bộ** trước khi so final state. Nếu chỉ kiểm sau `Thread.sleep`, một phép so có thể đọc lúc xử lý đang dở, hoặc không có quan hệ memory visibility rõ ràng.

### Snapshot đang chạy có thể sai dù từng counter là atomic

Giả sử producer làm:

```java
queue.put(item);
accepted.incrementAndGet();
```

Một thread giám sát chụp `queue.size()`, `accepted.get()` và `processed.get()` riêng rẽ trong lúc các thread khác vẫn làm việc. Các phép đọc không tạo thành một giao dịch nguyên tử, nên phương trình cộng trừ có thể lệch tạm thời.

Giải pháp: dừng/đóng băng tại checkpoint rồi chụp các giá trị; hoặc thiết kế một snapshot/version protocol đúng; hoặc chỉ áp dụng invariant theo **khoảng thời gian với độ lệch đã được định nghĩa**. `size()` của nhiều collection concurrent là số liệu quan sát, không phải giao dịch với những counter ở object khác.

## 10. Lỗi mất dữ liệu ở queue và pipeline

Một số lỗi phổ biến:

| Lỗi | Cơ chế | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| Bỏ qua kết quả `offer` | Queue đầy, `offer` trả `false` nhưng caller tưởng item đã được nhận. | Kiểm `boolean`, ghi rõ reject/drop hoặc dùng `put`/timed `offer` theo contract. |
| Dừng consumer quá sớm | Marker dừng được gửi trước khi producer hoàn tất. | Chờ producer kết thúc, gửi marker theo số consumer, chờ consumer kết thúc. |
| Hai consumer cùng xử lý ID do retry | Side effect hoàn tất nhưng ACK mất; item phát lại. | Deduplicate theo ID và kiểm side effect/commit thực sự, không chỉ count. |
| Bỏ dữ liệu ở exception path | Consumer lấy item rồi exception trước commit; item không quay lại queue. | Ghi trạng thái failure/retry/dead-letter và đưa vào invariant bảo toàn. |
| Dùng cấu trúc không thread-safe | `HashMap`/`ArrayList` bị sửa đồng thời không đồng bộ. | Chọn lock hoặc collection concurrent, và kiểm atomicity của chuỗi thao tác. |
| `check-then-act` race | `if (!map.containsKey(k)) map.put(k,v)` không thành một bước nguyên tử. | `putIfAbsent`, `compute` hoặc lock theo yêu cầu. |
| Shutdown không drain | Executor bị đóng khi queue còn task chưa xử lý. | Có giao thức nhận/ngừng nhận mới, drain, chờ, và kiểm task chưa hoàn tất. |
| Coi timeout là thành công | Worker treo; test chỉ hết thời gian rồi so counter một phần. | Propagate timeout thành lỗi test; hủy/cleanup worker và thu diagnostic. |
| Tính expected từ chính output | Cùng bug ảnh hưởng oracle và kết quả, test PASS giả. | Sinh expected từ input/contract hoặc reference implementation độc lập. |

**Không mất** và **không trùng** là hai mục tiêu riêng. Retry giúp giảm mất dữ liệu khi có lỗi tạm thời, nhưng có thể tăng xử lý lặp. “Exactly once” đối với một side effect bên ngoài thường đòi hỏi kết hợp ID ổn định, transaction/deduplication và giao thức commit/ack phù hợp. Một `ConcurrentHashMap` trong RAM không đủ bảo đảm khi process crash.

## 11. Kiểm tra thứ tự và tính tuyến tính hóa

Khi API hứa thao tác nguyên tử, ta quan tâm **linearizability**: mỗi thao tác hoàn tất dường như có một thời điểm hiệu lực duy nhất nằm giữa lúc gọi và lúc trả về, phù hợp thứ tự thời gian thực của những thao tác không chồng lấn.

Không phải invariant về giá trị cuối có thể chứng minh linearizability. Ví dụ hai thread thực hiện `getAndIncrement`: counter cuối cùng bằng 2 chưa chứng minh mỗi thread đã nhận giá trị trả về khác nhau và đúng lịch sử.

Cách kiểm thử tăng độ tin cậy:

1. Ghi mỗi thao tác với ID, thời điểm bắt đầu, kết thúc, input, output và lỗi.
2. Dùng clock hoặc thứ tự sự kiện đã đồng bộ để xác định quan hệ trước–sau đáng tin; đừng dựa vào việc `println` xen kẽ như một specification.
3. So lịch sử nhỏ với mô hình tuần tự đặc tả, có xét các thao tác chồng lấn có thể đổi thứ tự.
4. Kết hợp invariant về kết quả cuối với invariant về **giá trị trả về** và history. Việc tổng hợp final state không đủ.

Đối với queue FIFO concurrent, hai producer gọi `put` chồng lấn không có thứ tự toàn cục đơn giản từ thứ tự dòng lệnh ở hai thread. Chỉ kiểm những guarantee mà API thật sự đưa ra: ví dụ queue đưa ra theo thứ tự item đã được thêm thành công, trong khi thứ tự giữa các lời gọi producer đang chạy đồng thời cần nhìn vào linearization/order thực tế.

## 12. Kiểm tra đúng các đường kết thúc bất thường

Một bài test pipeline chỉ chạy “happy path” không kiểm được data loss khi có lỗi. Cần bổ sung các tình huống có **kết quả mong đợi rõ ràng**:

- Queue đầy: item bị reject hay chờ? Có bị đánh dấu nhầm accepted không?
- Consumer ném exception sau khi lấy item, trước khi ghi kết quả: item được retry hoặc đưa vào failed bucket? Có mất âm thầm không?
- Timeout/interrupt khi producer đang `put`: chỉ tăng accepted nếu `put` thực sự thành công; xử lý ngoại lệ rõ ràng.
- Retry sau lỗi ACK: một ID có tạo hai side effect không?
- Đóng executor khi còn việc: còn bao nhiêu queued/running; task nào bị hủy; có log trạng thái unresolved không?
- Nhiều consumer: có thể cùng xử lý một ID hay không? Test phải kiểm cả multiplicity.
- Lỗi chậm hiếm gặp: chạy stress nhiều lần, log seed/input/thread dump khi thất bại.
- Restart/process crash: cần test tích hợp phù hợp và trạng thái lưu trữ bền; kiểm thử in-memory không thể thay thế.

Có thể dùng **fault injection**: một hook test cố tình dừng ngay sau “đã lấy item”, trước “commit”, hoặc ngay sau commit, trước ACK. Điều này làm lỗi có thể tái hiện và kiểm được chính sách retry/dedup đúng contract.

## 13. Công cụ hỗ trợ chẩn đoán

**Thread dump và `jcmd`** hỗ trợ tìm thread stuck, deadlock, monitor, thread park hoặc block I/O:

```bash
jcmd <pid> Thread.print -l
```

`<pid>` là PID JVM thực tế. Thread dump chỉ phản ánh thời điểm lấy mẫu. Nhiều thread `WAITING` có thể đang chờ công việc hợp lệ; cần đọc stack và trạng thái hệ thống.

**Java Flight Recorder (JFR)** cho phép phân tích sự kiện lock, park, allocation, thread scheduling, GC. Nó giúp tìm lý do hiệu năng hoặc treo; nó **không tự chứng minh** data integrity, vì vẫn cần oracle và kiểm tra ID/state.

**JCStress** phù hợp để thử một số hành vi đồng thời cấp thấp, memory ordering và các kết quả cho phép/bị cấm theo Java Memory Model; **JMH** phù hợp đo benchmark. Không nên dùng throughput cao thay cho một test invariant.

**Metrics, logs, traces** hỗ trợ quan sát production:

- Đếm accepted/rejected/processed/failed/retried bằng các điểm cập nhật định nghĩa rõ.
- Có histogram thời gian chờ queue, thời gian xử lý, deadline, số task in-flight.
- Gắn correlation ID cho mỗi item để điều tra khi số lượng mất cân đối.
- Chỉ phân tích invariant sau khi xác định checkpoint nhất quán hoặc cách gộp số liệu đã có tính đến độ trễ telemetry.

## 14. Những sai lầm khiến test bỏ sót lỗi

1. **Chỉ kiểm tổng count:** output thiếu một ID nhưng trùng ID khác vẫn PASS.
2. **Tin rằng `volatile` giải quyết `counter++`:** visibility khác atomicity.
3. **Đọc hai biến synchronized khác lock hoặc đọc riêng lẻ:** tạo snapshot không nhất quán và false positive.
4. **Dùng `Thread.sleep` để bảo đảm interleaving:** scheduler không có cam kết theo mili-giây bạn chọn.
5. **Không thu lỗi từ task:** `ExecutorService.submit` giữ exception trong `Future`; không `get` thì test có thể coi là thành công dù worker đã lỗi.
6. **Không timeout khi chờ:** test deadlock có thể treo CI mãi.
7. **Đo performance thay correctness:** benchmark chạy nhanh với data race vẫn là sai.
8. **Dùng collection không thread-safe làm oracle:** bộ đếm/Set kiểm thử có thể tự bị race khiến kết luận không đáng tin.
9. **Gửi shutdown marker trước khi producer kết thúc:** consumer có thể thoát khi vẫn còn dữ liệu mới.
10. **Không kiểm contract của drop/retry:** một lần reject hợp lệ bị coi là loss hoặc một lần loss âm thầm bị ghi nhầm vào reject.
11. **Dùng một lần PASS làm bằng chứng không có race:** stress có thể bỏ qua interleaving xấu.
12. **Giới hạn bài toán ở RAM khi hệ thống cần durability:** phải kiểm đúng ranh giới commit và ACK của nguồn/đích.

## 15. Checklist xây test invariant hoàn chỉnh

Trước khi viết code test, hãy trả lời:

1. **Nguồn sự thật:** tập input accepted, expected state hoặc reference model được xây từ đâu?
2. **Ranh giới:** thao tác được coi là accepted, committed, failed, rejected, acknowledged ở thời điểm nào?
3. **Invariant:** có điều kiện số lượng, giá trị, ID distinct, multiplicity, order, liveness nào phải luôn đúng?
4. **Checkpoint:** test kiểm lúc hệ thống đã quiescent hay dùng snapshot nhất quán khi đang chạy?
5. **Race cần ép:** điểm xen kẽ nào có thể gây lỗi? Có thể tạo bằng latch/barrier/phaser không?
6. **Đường lỗi:** queue full, exception, timeout, retry, interrupt, cancel và shutdown đã được thử chưa?
7. **Dữ liệu chứng cứ:** nếu fail, test có ghi input/ID, kỳ vọng, output, stack trace và metadata tái hiện không?
8. **Kết thúc:** tất cả Future đã được `get`/cancel và executor do test sở hữu đã shutdown chưa?
9. **Kiểm chứng bản sửa:** test đỏ với cách triển khai sai có chủ ý và xanh với bản sửa đúng không?
10. **Giới hạn kết luận:** test chứng minh tính đúng trong một JVM, trên lịch chạy cụ thể hay còn bao gồm crash/restart/remote commit?

### Bài tập thực hành

1. Bỏ `allRead` khỏi `LostUpdateInvariantDemo` và chạy nhiều lần. Giải thích vì sao kết quả unsafe có thể thay đổi hoặc đôi khi đúng: bug vẫn tồn tại dù test may mắn PASS.
2. Sửa `PipelineInvariantDemo`: trong một producer, dùng `queue.offer(...)` không kiểm kết quả khi queue đầy, rồi kiểm oracle nhận vào/được giao. Xác định đúng thời điểm một item bị reject. Sau đó sửa bằng kiểm `boolean` hoặc dùng `put`.
3. Tạo một consumer xử lý trùng ID có chủ đích và một consumer bỏ qua một ID; kiểm tổng count sẽ không đủ, nhưng tập distinct và missing/duplicates phải bắt được.
4. Viết test chuyển tiền giữa hai tài khoản; kiểm `totalSnapshot()` dưới một lock bảo vệ cả hai field, rồi thử bỏ đồng bộ để tái hiện kết quả sai. Kiểm thêm trường hợp số dư âm và transfer thất bại.

## 16. Tổng kết

Trong Java concurrency, **kiểm tra invariant** biến một lỗi “thỉnh thoảng sai” thành câu hỏi có thể chứng minh bằng dữ liệu: có bao nhiêu thao tác được chấp nhận, trạng thái cuối có thỏa điều kiện, ID nào mất, ID nào trùng và việc quan sát được thực hiện tại checkpoint nào.

Muốn bắt lỗi mất cập nhật, hãy cố ý tạo interleaving có ý nghĩa bằng `CyclicBarrier` hoặc `CountDownLatch` và so với oracle độc lập. Muốn bắt mất dữ liệu trong pipeline, hãy kiểm **tập ID, số lần xuất hiện và số lượng** sau khi chờ mọi worker kết thúc. Khi cần độ tin cậy sâu hơn, bổ sung fault injection, stress/JCStress và kiểm tra đường commit/retry ở tầng lưu trữ thực sự.

### Tham khảo Java API

- [`java.util.concurrent` — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html)
- [`CyclicBarrier`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)
- [`CountDownLatch`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [`ArrayBlockingQueue`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)
- [`AtomicInteger`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
- [`Future`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)