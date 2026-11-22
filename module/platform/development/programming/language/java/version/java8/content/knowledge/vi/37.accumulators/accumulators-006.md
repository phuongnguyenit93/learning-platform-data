# `reset`, `sumThenReset`, `getThenReset` và điều kiện sử dụng (Java 8+)

> **Chủ đề:** Biến tích lũy. Bài học giải thích bốn lớp hiện hành thuộc `java.util.concurrent.atomic`: `LongAdder`, `DoubleAdder`, `LongAccumulator` và `DoubleAccumulator`. Các method `reset`, `sumThenReset`, `getThenReset` rất hữu ích khi kết thúc một batch thống kê. **Ràng buộc quan trọng nhất:** chúng **không phải atomic read-and-clear trong lúc thread khác vẫn cập nhật**. Các API đã có từ Java 8 và tiếp tục áp dụng trên các JDK hiện đại.

## 1. Mục tiêu

Sau bài, bạn có thể:

1. Chọn đúng lớp hỗ trợ `reset`, `sumThenReset` hoặc `getThenReset` và hiểu kiểu trả về.
2. Phân biệt cộng dồn bằng `LongAdder/DoubleAdder` với gộp theo hàm tùy chọn bằng `LongAccumulator/DoubleAccumulator`.
3. Hiểu `sum/get` (chỉ đọc), `reset` (bỏ số liệu), `sumThenReset/getThenReset` (đọc rồi reset).
4. Giải thích tại sao `sum/get` không phải atomic snapshot, còn các method reset không phải atomic exchange khi có concurrent updates.
5. Sắp xếp *quiescent point*: chặn writer mới, đợi mọi writer đang chạy kết thúc rồi mới đọc-reset.
6. So sánh `LongAdder.sumThenReset()` với `AtomicLong.getAndSet(0L)` nếu cần một điểm trao đổi chính xác.
7. Viết ví dụ Java 8 tự chạy và kiểm thử được tất cả bốn loại, kể cả identity không phải 0.
8. Tránh sai lầm về identity, tính associative/commutative, floating-point precision và dữ liệu metrics theo khoảng.

## 2. Bốn lớp: method nào có sẵn?

| Class | Cập nhật | Đọc giá trị | Bỏ giá trị cũ | Lấy rồi reset | Giá trị sau reset |
| --- | --- | --- | --- | --- | --- |
| `LongAdder` | `add(long)`, `increment`, `decrement` | `sum(): long` | `reset(): void` | `sumThenReset(): long` | `0L` |
| `DoubleAdder` | `add(double)` | `sum(): double` | `reset(): void` | `sumThenReset(): double` | `0.0` |
| `LongAccumulator` | `accumulate(long)` | `get(): long` | `reset(): void` | `getThenReset(): long` | identity của constructor |
| `DoubleAccumulator` | `accumulate(double)` | `get(): double` | `reset(): void` | `getThenReset(): double` | identity của constructor |

Không hoán đổi các tên: `LongAdder` **không có** `getThenReset` và `LongAccumulator` **không có** `sumThenReset`. `reset` có ở cả bốn lớp và **không trả lại giá trị cũ**.

Các lớp Adder chuyên dùng để đếm/tính tổng; lớp Accumulator nhận một hàm gộp (chẳng hạn max/min) và identity khi tạo object. Chúng tối ưu cho **nhiều thread cập nhật thường xuyên, đọc ít hơn**, nhất là khi contention cao. Chúng không được thiết kế để thay một biến atomic dùng đồng bộ hóa trạng thái hay để cung cấp snapshot chính xác mọi lúc.

## 3. `reset()`: xóa trạng thái và tái sử dụng object

```java
LongAdder count = new LongAdder();
count.add(5);
count.increment();
long before = count.sum(); // 6.

count.reset();
long after = count.sum();  // 0.
```

Với Accumulator, reset về **identity**, không nhất thiết là zero:

```java
LongAccumulator maximum =
        new LongAccumulator(Long::max, Long.MIN_VALUE);
maximum.accumulate(42);
maximum.accumulate(105);
long peak = maximum.get(); // 105.

maximum.reset();
long now = maximum.get(); // Long.MIN_VALUE.
```

`DoubleAdder.reset()` đặt tổng về `0.0`; `DoubleAccumulator.reset()` đặt về identity cung cấp trong constructor. Ví dụ min double có identity `Double.POSITIVE_INFINITY`; khi reset, `get()` trả Infinity cho đến khi có một phép accumulate phù hợp.

**Dùng reset khi nào?** Khi kết thúc một batch và **chắc chắn không còn writer** đang cập nhật object, hoặc setup/teardown của test hoàn toàn đơn luồng. Nếu chỉ muốn hiển thị số liệu hiện tại, dùng `sum()`/`get()` mà không reset. Nếu cần lấy tổng batch trước khi xóa, dùng `sumThenReset` / `getThenReset` đúng kiểu.

## 4. `sumThenReset()` dành cho LongAdder và DoubleAdder

```java
LongAdder clicks = new LongAdder();
clicks.add(10L);
clicks.increment();

long previous = clicks.sumThenReset(); // 11.
long next = clicks.sum();               // 0.
```

Tương tự với double:

```java
DoubleAdder durations = new DoubleAdder();
durations.add(1.25);
durations.add(2.50);

double previous = durations.sumThenReset(); // 3.75.
double next = durations.sum();               // 0.0.
```

`sumThenReset` tương đương **về hiệu ứng** với `sum()` rồi `reset()`, nhưng **không có bảo đảm atomic như getAndSet**. Nếu có update xảy ra cùng lúc, kết quả trả về **không được đảm bảo là tổng cuối cùng ngay trước reset**; không được khẳng định giá trị ấy và các giá trị sau reset tự động tạo hai khoảng không chồng lấn/mất dữ liệu.

Hai số 1.25 và 2.50 có biểu diễn nhị phân chính xác, nên ví dụ trên cho 3.75. Với số như 0.1 và nhiều cập nhật double, việc cộng floating-point có thể có sai số làm tròn và kết quả thay đổi nhẹ theo thứ tự cộng. `DoubleAdder` phù hợp metrics thống kê có tolerance, **không** phù hợp để thay số tiền cần chính xác tuyệt đối.

## 5. `getThenReset()` dành cho LongAccumulator và DoubleAccumulator

```java
LongAccumulator maximum =
        new LongAccumulator(Long::max, Long.MIN_VALUE);

maximum.accumulate(-8L);
maximum.accumulate(4L);

long oldMax = maximum.getThenReset(); // 4.
long emptyMax = maximum.get();        // Long.MIN_VALUE.
```

Accumulator giữ nguyên hàm gộp và identity sau reset, chỉ làm mới trạng thái đã tích lũy. Với double min:

```java
DoubleAccumulator minimum = new DoubleAccumulator(
        Double::min, Double.POSITIVE_INFINITY);

minimum.accumulate(2.25);
minimum.accumulate(1.50);

double oldMin = minimum.getThenReset(); // 1.5.
double emptyMin = minimum.get();        // +Infinity.
```

Một identity như `Long.MIN_VALUE` hoặc Infinity **không phải một phép đo thật**. UI nên hiển thị “chưa có dữ liệu” thay vì trả `Long.MIN_VALUE` như latency cao nhất của kỳ mới.

### 5.1. Hàm gộp và identity phải hợp lệ

Đối với tính toán có contention, thứ tự áp dụng hàm không được đảm bảo; hàm cần **associative**, **commutative** và **không có side effect**.

- Associative: `f(f(a,b),c) == f(a,f(b,c))`.
- Commutative: `f(a,b) == f(b,a)`.
- Identity `e`: `f(e,x) == f(x,e) == x`.

| Phép gộp | Hàm | Identity |
| --- | --- | --- |
| Sum long | `Long::sum` | `0L` |
| Max long | `Long::max` | `Long.MIN_VALUE` |
| Min long | `Long::min` | `Long.MAX_VALUE` |
| Max double | `Double::max` | `Double.NEGATIVE_INFINITY` |
| Min double | `Double::min` | `Double.POSITIVE_INFINITY` |

Accumulator function có thể bị áp dụng **nhiều lần** khi nội bộ thử cập nhật lại do contention. Không trừ tiền, ghi database hoặc đếm sự kiện sang một counter khác trong hàm gộp. Phép trừ, chia, nối chuỗi theo thứ tự không phù hợp để gộp độc lập thứ tự; với floating-point, yêu cầu associative/commutative chỉ nên được hiểu trong tolerance số học chấp nhận được, vì phép cộng double không hoàn toàn associative theo từng bit.

## 6. `sum()` và `get()` cũng không phải atomic snapshot

Để giảm contention, các lớp tích lũy có thể duy trì **nhiều biến nội bộ** thay vì một biến duy nhất. `LongAdder.sum()` và `LongAccumulator.get()` phải gộp trạng thái ấy để trả kết quả. Nếu thread khác còn cập nhật trong lúc đọc, kết quả có thể chưa bao gồm các cập nhật mới nhất; nó **không phải một atomic snapshot tại thời điểm duy nhất**. `DoubleAdder.sum()` và `DoubleAccumulator.get()` có cùng lưu ý.

```java
LongAdder requests = new LongAdder();
// Các thread khác đang gọi requests.increment().
long approximateNow = requests.sum();
```

Giá trị này hợp lý cho dashboard thống kê gần hiện tại, nhưng **không** nên dùng làm điểm đồng bộ chuyển tiền, giới hạn hàng tồn bắt buộc chính xác hay snapshot kiểm toán.

**Khi toàn bộ writer đã hoàn tất và không có writer mới**, đọc kết quả có thể phản ánh đủ các phép cập nhật đã hoàn thành (ngoài các giới hạn về overflow/precision của kiểu số). Đây là điều kiện cần khi muốn dùng `sumThenReset/getThenReset` chính xác cho một batch.

## 7. Vì sao reset đồng thời với update nguy hiểm?

Giả sử thread A chạy:

```java
long oldMinute = requests.sumThenReset();
```

trong khi thread B chạy:

```java
requests.increment();
```

Không có hợp đồng quy định increment của B sẽ nằm chắc chắn trong `oldMinute` hay trong `requests.sum()` sau reset. Cập nhật có thể đan xen việc đọc/xóa trạng thái từ nhiều vị trí. JavaDoc nói rõ `reset()` chỉ nên được dùng **khi biết chắc không có thread nào đang cập nhật**; `sumThenReset()` / `getThenReset()` cũng chỉ đáng tin tại *quiescent point*.

Tên “get then reset” có thể giống `AtomicLong.getAndSet(0)` nhưng **không có nghĩa atomic**. Với các lớp accumulator, không thể giả định một ranh giới chính xác “mọi update trước thời điểm T được ghi vào kỳ trước, mọi update sau T vào kỳ sau”.

### 7.1. Quiescent point là gì?

*Quiescence* là giai đoạn **không còn update đang chạy và không có update mới được bắt đầu** trên accumulator chuẩn bị reset. Quy trình:

1. Ngừng tiếp nhận update vào accumulator của batch hiện tại, hoặc chuyển producer sang một cơ chế tạm giữ với giao thức rõ ràng.
2. Chờ mọi worker đã nhận update của batch kết thúc (ví dụ `Future.get()`/`join`/lifecycle barrier).
3. Chỉ khi không còn writer, gọi `sumThenReset()` hoặc `getThenReset()`.
4. Bắt đầu batch mới.

**Chờ một danh sách Future không đủ nếu thread khác vẫn được phép bắt đầu cập nhật.** Phải quản lý tất cả nguồn writer, kể cả callback, scheduler, queue consumer và retry.

### 7.2. “Hai lần sum bằng nhau” không chứng minh đã yên

Đọc `sum()` hai lần ra cùng số không chứng minh rằng không còn thread nào sẽ cập nhật ngay sau đó. Một biến `activeWriters` tạm bằng 0 cũng không đủ nếu writer mới có thể gia nhập mà không phối hợp với thread reset. Cần giao thức đóng/mở batch, lock/barrier hoặc epoch có theo dõi in-flight updates.

### 7.3. Đếm theo phút trên hệ thống có traffic liên tục

Đọc-reset LongAdder mỗi phút trong lúc writer vẫn chạy **không tạo bộ đếm phút atomic**. Nếu telemetry chấp nhận sai số gần đúng, đôi khi có thể đọc `sum()` định kỳ trên một bộ đếm cumulative không reset rồi lấy hiệu giữa hai lần đọc, nhưng hiệu cũng không phải snapshot atomic. Nếu cần hạch toán chính xác từng sự kiện vào một khoảng, cần một thiết kế phối hợp dữ liệu/sổ cái/atomic exchange hoặc xử lý event theo cửa sổ có đồng bộ rõ ràng.

## 8. So sánh với AtomicLong.getAndSet(0)

```java
AtomicLong exactCounter = new AtomicLong();
exactCounter.addAndGet(3L);

long old = exactCounter.getAndSet(0L); // 3.
long now = exactCounter.get();          // 0.
```

`AtomicLong.getAndSet(0L)` là **atomic exchange của một biến long**. Các update atomic trên cùng biến được sắp thứ tự logic trước hoặc sau điểm exchange. Đó là sự khác biệt với `LongAdder.sumThenReset()`, vốn có thể nhanh hơn dưới contention nhưng không cho một exchange tuyến tính hóa duy nhất.

**Giới hạn cần nhớ:** Nhiều `AtomicLong` không tự tạo snapshot atomic của **toàn bộ hệ thống hoặc cả nhóm counters**. Nếu phải đồng bộ nhiều metric, cần cơ chế snapshot/transaction hoặc thiết kế protocol riêng.

| Nhu cầu | Công cụ gợi ý |
| --- | --- |
| Counter có nhiều writer, đọc thỉnh thoảng, telemetry gần đúng | `LongAdder.sum()` |
| Tổng double cho thống kê chấp nhận sai số số thực | `DoubleAdder.sum()` |
| Max/min của một batch đa luồng | `LongAccumulator/DoubleAccumulator` |
| Kết thúc batch không còn writer, muốn giữ giá trị trước khi xóa | `sumThenReset/getThenReset` |
| Chỉ xóa số liệu batch đã hoàn tất | `reset()` |
| Một counter long đòi hỏi atomic cutover | `AtomicLong.getAndSet(0L)` + atomic updates |
| Nhiều counters đòi hỏi snapshot chính xác cùng lúc | Phối hợp/transaction ở tầng nghiệp vụ |

## 9. Hiệu năng, precision và sử dụng production

Adder/Accumulator thường hữu ích khi **nhiều thread cập nhật cùng một đại lượng thường xuyên** và ít cần đọc: phân tán contention giúp throughput tốt hơn ở một số workload so với một biến `AtomicLong` duy nhất, đổi lại tốn thêm bộ nhớ và thiếu snapshot atomic. Không tự khẳng định lúc nào cũng nhanh hơn; benchmark với số threads, tần suất đọc và kích thước dữ liệu thực, bằng JMH khi cần.

`LongAdder` là long, có thể overflow theo arithmetic Java; `DoubleAdder` dùng số thực binary, có rounding và những trường hợp NaN/Infinity; lựa chọn kiểu biểu diễn và giới hạn nghiệp vụ phải được xác định trước. Với tiền tệ, sử dụng kiểu biểu diễn chính xác và kiến trúc nhất quán, không chọn accumulator floating-point chỉ vì tiện.

**Đừng thay reset bằng tạo object mới mà không nghĩ đến writer cũ.** Đổi một reference tới LongAdder mới trong lúc thread khác vẫn giữ reference cũ có thể làm các update dồn vào bộ cũ; để có interval thật sự không mất sự kiện, cần giao thức chuyển epoch/đóng và đợi in-flight updates, không đơn thuần swap reference.

## 10. Ví dụ về vòng đời một batch

```java
LongAdder batchTotal = new LongAdder();
ExecutorService pool = Executors.newFixedThreadPool(4);
try {
    List<Future<?>> writers = new ArrayList<>();
    for (int worker = 0; worker < 4; worker++) {
        writers.add(pool.submit(() -> {
            for (int i = 0; i < 1_000; i++) {
                batchTotal.increment();
            }
        }));
    }
    // Trong ví dụ không còn producer nào khác.
    for (Future<?> writer : writers) {
        writer.get();
    }
    long completedBatch = batchTotal.sumThenReset(); // 4000.
} finally {
    pool.shutdown();
}
```

Đây là **snippet nằm trong phương thức có thể throws Exception**, cần các import thích hợp. Nếu không có nguồn writer khác, `Future.get()` cho phép đợi tất cả tác vụ batch kết thúc trước khi reset; đây mới là phần đảm bảo quiescence. `pool.shutdown()` ở cuối không thay thế việc `get` để chờ các task đã hoàn tất. Chương trình đầy đủ dưới đây còn dùng `CountDownLatch` để các worker bắt đầu gần nhau.

## 11. Chương trình Java 8 hoàn chỉnh, có kiểm tra kết quả

Lưu thành file **`AccumulatorResetDemo.java`**. Chương trình tạo bốn writer, đợi toàn bộ task kết thúc, sau đó `sumThenReset` mà **không có race với writer**. Các phần khác kiểm tra `DoubleAdder`, `LongAccumulator` max, `DoubleAccumulator` min, reset thủ công và `AtomicLong.getAndSet(0)`. Không đo thời gian hệ thống, không dùng sleep, nên output lặp lại.


```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.DoubleAccumulator;
import java.util.concurrent.atomic.DoubleAdder;
import java.util.concurrent.atomic.LongAccumulator;
import java.util.concurrent.atomic.LongAdder;

public class AccumulatorResetDemo {
    public static void main(String[] args) throws Exception {
        LongAdder requests = new LongAdder();
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            CountDownLatch start = new CountDownLatch(1);
            List<Future<?>> writers = new ArrayList<>();
            for (int worker = 0; worker < 4; worker++) {
                writers.add(pool.submit(() -> {
                    try {
                        start.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(ex);
                    }
                    for (int i = 0; i < 1_000; i++) {
                        requests.increment();
                    }
                }));
            }
            start.countDown();
            for (Future<?> future : writers) {
                future.get();
            }
            long before = requests.sum();
            long drained = requests.sumThenReset();
            long after = requests.sum();
            requests.add(7L);
            long reused = requests.sum();
            requests.reset();
            long afterManualReset = requests.sum();

            DoubleAdder duration = new DoubleAdder();
            duration.add(1.25);
            duration.add(2.50);
            double doubleBefore = duration.sum();
            double doubleDrained = duration.sumThenReset();
            double doubleAfter = duration.sum();
            duration.add(0.5);
            duration.reset();
            double doubleAfterManualReset = duration.sum();

            LongAccumulator maximum =
                    new LongAccumulator(Long::max, Long.MIN_VALUE);
            long longIdentity = maximum.get();
            maximum.accumulate(-8L);
            maximum.accumulate(4L);
            long longBefore = maximum.get();
            long longDrained = maximum.getThenReset();
            long longAfter = maximum.get();
            maximum.accumulate(12L);
            maximum.reset();
            long longAfterManualReset = maximum.get();

            DoubleAccumulator minimum = new DoubleAccumulator(
                    Double::min, Double.POSITIVE_INFINITY);
            double doubleIdentity = minimum.get();
            minimum.accumulate(2.25);
            minimum.accumulate(1.50);
            double minBefore = minimum.get();
            double minDrained = minimum.getThenReset();
            double minAfter = minimum.get();
            minimum.accumulate(-3.0);
            minimum.reset();
            double minAfterManualReset = minimum.get();

            AtomicLong precise = new AtomicLong();
            precise.addAndGet(3L);
            long preciseDrained = precise.getAndSet(0L);
            long preciseAfter = precise.get();

            System.out.println("LongAdder before cutoff: " + before);
            System.out.println("LongAdder sumThenReset: " + drained);
            System.out.println("LongAdder after cutoff: " + after);
            System.out.println("LongAdder after reuse: " + reused);
            System.out.println("LongAdder reset: " + afterManualReset);
            System.out.println("DoubleAdder before cutoff: " + doubleBefore);
            System.out.println("DoubleAdder sumThenReset: " + doubleDrained);
            System.out.println("DoubleAdder after cutoff: " + doubleAfter);
            System.out.println("DoubleAdder reset: " + doubleAfterManualReset);
            System.out.println("LongAccumulator identity: " + longIdentity);
            System.out.println("LongAccumulator max: " + longBefore);
            System.out.println("LongAccumulator getThenReset: " + longDrained);
            System.out.println("LongAccumulator after reset: " + longAfter);
            System.out.println("LongAccumulator manual reset: " + longAfterManualReset);
            System.out.println("DoubleAccumulator identity: " + doubleIdentity);
            System.out.println("DoubleAccumulator min: " + minBefore);
            System.out.println("DoubleAccumulator getThenReset: " + minDrained);
            System.out.println("DoubleAccumulator after reset: " + minAfter);
            System.out.println("DoubleAccumulator manual reset: " + minAfterManualReset);
            System.out.println("AtomicLong getAndSet: " + preciseDrained);
            System.out.println("AtomicLong after exchange: " + preciseAfter);

            if (before != 4_000 || drained != 4_000 || after != 0
                    || reused != 7 || afterManualReset != 0
                    || doubleBefore != 3.75 || doubleDrained != 3.75
                    || doubleAfter != 0.0 || doubleAfterManualReset != 0.0
                    || longIdentity != Long.MIN_VALUE
                    || longBefore != 4 || longDrained != 4
                    || longAfter != Long.MIN_VALUE
                    || longAfterManualReset != Long.MIN_VALUE
                    || doubleIdentity != Double.POSITIVE_INFINITY
                    || minBefore != 1.5 || minDrained != 1.5
                    || minAfter != Double.POSITIVE_INFINITY
                    || minAfterManualReset != Double.POSITIVE_INFINITY
                    || preciseDrained != 3 || preciseAfter != 0) {
                throw new AssertionError("Accumulator reset demo mismatch");
            }
            System.out.println("Checks passed.");
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch với JDK 17+ ở chế độ tương thích Java 8 (hoặc dùng compiler JDK 8):

```bash
javac --release 8 AccumulatorResetDemo.java
java AccumulatorResetDemo
```

**Stdout đã kiểm chứng trên OpenJDK 24:**


```text
LongAdder before cutoff: 4000
LongAdder sumThenReset: 4000
LongAdder after cutoff: 0
LongAdder after reuse: 7
LongAdder reset: 0
DoubleAdder before cutoff: 3.75
DoubleAdder sumThenReset: 3.75
DoubleAdder after cutoff: 0.0
DoubleAdder reset: 0.0
LongAccumulator identity: -9223372036854775808
LongAccumulator max: 4
LongAccumulator getThenReset: 4
LongAccumulator after reset: -9223372036854775808
LongAccumulator manual reset: -9223372036854775808
DoubleAccumulator identity: Infinity
DoubleAccumulator min: 1.5
DoubleAccumulator getThenReset: 1.5
DoubleAccumulator after reset: Infinity
DoubleAccumulator manual reset: Infinity
AtomicLong getAndSet: 3
AtomicLong after exchange: 0
Checks passed.
```

### Phân tích output

1. Bốn writer cùng tăng `LongAdder` mỗi người 1.000 lần; vòng `Future.get()` đợi tất cả kết thúc. Vì không còn writer, `sum()` và `sumThenReset()` đều trả **4.000**, sau reset trả 0. Khi add thêm 7 rồi reset thủ công, kết quả lại 0.
2. `DoubleAdder` cộng 1.25 và 2.50 thành 3.75, `sumThenReset()` trả 3.75 rồi tổng về 0.0; reset thủ công cũng về 0.0.
3. `LongAccumulator(Long::max, Long.MIN_VALUE)` bắt đầu tại `Long.MIN_VALUE`, nhận -8 và 4 nên max là 4; `getThenReset()` trả 4 rồi `get()` lại là `Long.MIN_VALUE`. Reset thủ công sau update 12 cũng trở về identity.
4. `DoubleAccumulator(Double::min, Double.POSITIVE_INFINITY)` bắt đầu tại Infinity, nhận 2.25 và 1.5 nên min là 1.5; `getThenReset()` trả 1.5 rồi về Infinity.
5. `AtomicLong.getAndSet(0L)` trả 3 và đặt atomically một biến long về 0. Phần demo này đối chiếu **hợp đồng của phương thức**, không dùng một race ngẫu nhiên để “chứng minh” atomicity bằng một lần chạy.

Chương trình kiểm tra mọi giá trị bằng `AssertionError` khi sai và không dựa vào Java `assert` (có thể bị tắt nếu JVM không dùng `-ea`). `CountDownLatch` chỉ giúp writer bắt đầu gần đồng thời; bảo đảm **không còn writer khi reset** đến từ việc đợi toàn bộ `Future.get()` và không có nguồn update nào khác.

## 12. Những lỗi phổ biến

| Sai lầm | Vấn đề | Giải pháp |
| --- | --- | --- |
| Gọi `sumThenReset` trên LongAccumulator | Không có method đó | Dùng `getThenReset` |
| Gọi `getThenReset` trên LongAdder | Không có method đó | Dùng `sumThenReset` |
| Coi `reset` trả giá trị cũ | Nó trả `void` | Đọc riêng hoặc dùng method đọc-reset phù hợp |
| Coi reset Accumulator luôn về 0 | Về identity, có thể là MIN_VALUE/Infinity | Thiết kế identity đúng |
| Reset trong lúc nhiều writer còn cập nhật | Dữ liệu interval không đáng tin, có thể bị bỏ sót | Phối hợp quiescence |
| Coi `sumThenReset` là atomic `getAndSet` | Không có một exchange tuyến tính hóa chung | `AtomicLong.getAndSet` cho một counter |
| Đợi vài writer nhưng bỏ qua callback/producer khác | Vẫn có concurrent updates | Đóng intake và đợi toàn bộ in-flight |
| Đọc `sum` hai lần bằng nhau rồi kết luận yên | Writer mới có thể bắt đầu | Dùng lifecycle/barrier thực sự |
| Dùng identity 0 cho max với dữ liệu âm | Trả sai max | `Long.MIN_VALUE` |
| Hiển thị `Long.MIN_VALUE` như một phép đo thực | Nó chỉ là identity của batch chưa có dữ liệu | Theo dõi có dữ liệu hay không |
| Dùng reducer có side effect | Hàm có thể được thử lại dưới contention | Pure function, associative/commutative |
| Dùng phép trừ hoặc chia trong accumulator đa luồng | Phụ thuộc thứ tự áp dụng | Hàm gộp độc lập thứ tự |
| Đếm tiền bằng DoubleAdder | Sai số floating point | Kiểu số chính xác và transaction thích hợp |
| Dùng `sumThenReset` để hạch toán mỗi phút trong traffic liên tục | Không bảo đảm interval exact | Atomic exchange hoặc phối hợp batch |
| Swap reference sang Adder mới mà không quản lý writer cũ | Update có thể vẫn đến object cũ | Epoch/rotation với in-flight protocol |

## 13. Bài tập có đáp án

**1.** Trên `LongAdder` đã cộng 3 và 5, cần lấy 8 rồi đưa về 0, không có writer. — `long x = adder.sumThenReset();`; sau đó `adder.sum()==0`.

**2.** Đã đếm 100 sự kiện nhưng chỉ muốn bỏ số liệu, không cần giá trị. — `adder.reset()` ở điểm quiescent.

**3.** Trên `LongAccumulator(Long::max, Long.MIN_VALUE)` đã có các giá trị -7, 4 và 2, cần lấy max rồi mở batch mới. — `getThenReset()` trả 4; `get()` sau đó bằng `Long.MIN_VALUE`.

**4.** Trên `DoubleAccumulator(Double::min, Double.POSITIVE_INFINITY)` không có quan sát nào, `get()` trả gì? — `Double.POSITIVE_INFINITY`, biểu thị identity chưa có đóng góp.

**5.** Thread A chạy `sumThenReset`, thread B vẫn `increment`. Tổng kỳ trước có bảo đảm bao gồm mọi increment trước mốc reset? — **Không**, đây là thao tác intrinsically racy.

**6.** `LongAdder.sum()` khi đang cập nhật có phải snapshot atomically tại một Instant không? — **Không**, chỉ là quan sát tổng đang tích lũy.

**7.** Muốn atomic exchange một bộ đếm long cùng với các lần increment atomic thì chọn gì? — `AtomicLong.getAndSet(0L)` với `AtomicLong.incrementAndGet/addAndGet`.

**8.** Ba bộ đếm `AtomicLong` riêng có bảo đảm snapshot nhất quán đồng thời khi đọc từng cái không? — **Không**, cần cơ chế phối hợp ở cấp nhiều biến.

**9.** Vì sao hàm truyền vào `LongAccumulator` không được ghi log/thay đổi trạng thái ngoài? — Hàm có thể bị áp dụng lại trong contention, nên side effect có thể lặp.

**10.** Một counter đã tích lũy theo giờ nhưng muốn xem requests/s trong dashboard. Có nên reset liên tục không? — Thường dùng counter cumulative và đọc định kỳ để lấy hiệu gần đúng nếu telemetry chấp nhận, hoặc thiết kế khoảng có cutover atomic nếu cần số chính xác.

## 14. Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — LongAdder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): `sum`, `reset`, `sumThenReset`; cảnh báo non-atomic snapshot và concurrent reset.
- [Oracle Java SE 26 — DoubleAdder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/DoubleAdder.html): `sumThenReset`, rounding floating point và điều kiện sử dụng.
- [Oracle Java SE 26 — LongAccumulator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAccumulator.html): identity, function, `get`, `reset`, `getThenReset`, yêu cầu pure reducer.
- [Oracle Java SE 26 — DoubleAccumulator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/DoubleAccumulator.html): identity và quy tắc tích lũy double.
- [Oracle Java SE 26 — AtomicLong](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): `getAndSet`, cập nhật nguyên tử một biến long.
- [Oracle Java SE 8 — java.util.concurrent.atomic](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/atomic/package-summary.html): đối chiếu các API này đã có từ Java 8.

**Kết luận:** `reset` xóa số liệu không trả kết quả; `sumThenReset` lấy tổng rồi xóa trên **Adder**; `getThenReset` lấy giá trị gộp rồi về identity trên **Accumulator**. Chỉ dùng chúng để cắt batch khi **không có cập nhật đồng thời**. Khi cần atomic cutover của một bộ đếm long đang chạy, `AtomicLong.getAndSet(0)` có hợp đồng mạnh hơn; đừng suy luận atomicity từ chữ “ThenReset”.
