# sum(), get() và giới hạn ảnh chụp khi vẫn có ghi

**Chủ đề:** Java 8 → Biến tích lũy → sum, get và giới hạn ảnh chụp khi vẫn có ghi.

**LongAdder**, **DoubleAdder**, **LongAccumulator** và **DoubleAccumulator** thuộc gói **java.util.concurrent.atomic**, xuất hiện từ Java 8 và vẫn được hỗ trợ trong Java hiện đại. Chúng cho phép nhiều thread cập nhật một số liệu chung với khả năng giảm tranh chấp khi contention cao. Tuy vậy, phép đọc **sum()** hoặc **get()** không được bảo đảm là một **ảnh chụp nguyên tử (atomic snapshot)** khi nhiều threads vẫn tiếp tục ghi.

**Điểm quan trọng:** *Cập nhật thread-safe* không đồng nghĩa với *đọc tổng ở một thời điểm tuyến tính hóa duy nhất*. Khi sum/get tính giá trị từ nhiều thành phần, các cập nhật khác có thể diễn ra giữa các lần đọc. Một số cập nhật xảy ra trong lúc tính tổng có thể chưa xuất hiện trong kết quả lần đọc ấy.

Ngược lại, **khi không có concurrent updates và các writers trước đó đã hoàn tất/đồng bộ đúng**, sum/get trả giá trị chính xác theo phép toán và kiểu dữ liệu. Bài tập trung vào ranh giới giữa hai trường hợp này.

Các chương trình độc lập chạy được trên **Java 17+**. Các lớp tích lũy thuộc API Java 8; ví dụ có **record** sử dụng cú pháp Java 17+, được nêu rõ để tránh nhầm với Java 8 gốc.

## 1. Mục tiêu bài học

Bạn sẽ có thể:

1. Chọn đúng **LongAdder.sum()**, **DoubleAdder.sum()**, **LongAccumulator.get()**, **DoubleAccumulator.get()**.
2. Hiểu cơ chế giảm contention nhờ nhiều thành phần lưu trữ.
3. Giải thích chính xác ý nghĩa **NOT an atomic snapshot** trong tài liệu Java.
4. Phân biệt tổng quan sát trong lúc writer chạy với tổng cuối sau **quiescence**.
5. Dùng **Future.get**, **CountDownLatch**, **Thread.join** để kiểm soát khi nào đọc kết quả.
6. Tránh sử dụng sum/get làm phép check-and-update nguyên tử cho quota, sequence hoặc số dư.
7. Hiểu giới hạn **sumThenReset**, **getThenReset**, **reset** khi ghi đồng thời.
8. Áp dụng **ConcurrentHashMap<String, LongAdder>** cho frequency map mà không nhầm với snapshot toàn map.
9. Chọn **AtomicLong** hoặc **AtomicReference** khi cần nhất quán mạnh hơn.
10. Nhận ra sai số floating-point và yêu cầu đối với hàm tích lũy tùy biến.

## 2. Bốn kiểu tích lũy và phương thức đọc

| Kiểu | Cập nhật | Đọc | Dữ liệu |
|---|---|---|---|
| **LongAdder** | add(long), increment(), decrement() | **sum()** | Tổng long |
| **DoubleAdder** | add(double) | **sum()** | Tổng double |
| **LongAccumulator** | accumulate(long) | **get()** | Kết quả của LongBinaryOperator |
| **DoubleAccumulator** | accumulate(double) | **get()** | Kết quả của DoubleBinaryOperator |

**Adder** là loại tích lũy chuyên cho phép cộng. **Accumulator** cho phép một hàm kết hợp, chẳng hạn max/min.

Các phương thức đọc khác:

- **LongAdder.longValue()** tương đương **sum()**.
- **DoubleAdder.doubleValue()** tương đương **sum()**.
- **LongAccumulator.longValue()** tương đương **get()**.
- **DoubleAccumulator.doubleValue()** tương đương **get()**.

Đổi sang các phương thức Number nói trên **không làm kết quả mạnh hơn về tính nguyên tử**.

**Đừng nhầm API:** LongAdder không có get() tương tự AtomicLong.get(); LongAccumulator không có sum() như LongAdder.

## 3. Vì sao có giới hạn atomic snapshot?

Khi nhiều thread tranh chấp cùng một bộ đếm, một AtomicLong thường thực hiện cập nhật nguyên tử trên **một biến logic**. Những lớp Adder/Accumulator có thể mở rộng thành **base và các cells** nhằm chia bớt tranh chấp.

Sơ đồ khái niệm:

~~~text
Thread A ── update ─► cell A
Thread B ── update ─► cell B
Thread C ── update ─► base
Thread D ── update ─► cell C
                            │
                         sum/get
                            │
            đọc base và lần lượt các cells
                            │
                      kết quả tổng hợp
~~~

Không nên dựa vào số lượng cells, thứ tự quét hay cấu trúc nội bộ trong một bản JDK; đó không phải hợp đồng dành cho ứng dụng.

Khi **sum()** đang đọc cell A thì thread khác có thể cập nhật cell A ngay sau đó. Lần đọc này có thể không tính update mới ở A. Ngược lại, nếu cell B được update trước khi reader tới nó, lần đọc có thể ghi nhận giá trị B mới. Vì thế, kết quả có thể kết hợp dữ liệu ở **những thời điểm khác nhau**.

### 3.1. Lịch xen kẽ minh họa

Giả sử trước lúc reader bắt đầu:

~~~text
base = 10
cell = 20
tổng = 30
~~~

Một lịch có thể là:

~~~text
Reader: đọc base = 10
Writer: cộng 5 vào base  -> base = 15
Writer: cộng 7 vào cell  -> cell = 27
Reader: đọc cell = 27
Reader: trả 10 + 27 = 37

Trạng thái cuối: 15 + 27 = 42
~~~

Đây là **mô hình giải thích tính không nguyên tử**, không phải stdout chắc chắn của một JDK cụ thể. Nội dung cần nhớ: không có cam kết kết quả sum/get tương ứng một thời điểm cắt duy nhất khi updates đồng thời.

**Không hiểu sai:** Phương thức vẫn hữu ích để quan sát metrics. Nó không đồng nghĩa có data race không an toàn hoặc tất cả kết quả đều vô nghĩa. Nó chỉ không đủ mạnh để làm một atomic snapshot.

### 3.2. Ba mức nhất quán

| Mức | Ví dụ | Bảo đảm |
|---|---|---|
| **Cập nhật an toàn** | Nhiều threads gọi LongAdder.increment() | Không mất update do race kiểu biến long thường |
| **Đọc khi còn ghi** | Reader gọi sum() trong lúc writer chạy | Giá trị quan sát, **không là atomic snapshot** |
| **Đọc khi writers đã dừng** | Đợi hết Future.get() rồi sum() | Kết quả chính xác theo semantics của class |

Đó là lý do một metric quan sát cho dashboard có thể dùng LongAdder, nhưng **cấp ID**, **giới hạn quota cứng** hoặc **chốt giao dịch** thường cần thiết kế khác.

## 4. Ví dụ cơ bản với bốn lớp

Lưu thành **AccumulatorBasicsDemo.java**:

~~~java
import java.util.concurrent.atomic.DoubleAccumulator;
import java.util.concurrent.atomic.DoubleAdder;
import java.util.concurrent.atomic.LongAccumulator;
import java.util.concurrent.atomic.LongAdder;

public class AccumulatorBasicsDemo {
    public static void main(String[] args) {
        LongAdder hits = new LongAdder();
        hits.increment();
        hits.add(4);
        hits.decrement();

        DoubleAdder amount = new DoubleAdder();
        amount.add(1.25);
        amount.add(2.5);
        amount.add(-0.5);

        LongAccumulator maximum =
                new LongAccumulator(Long::max, Long.MIN_VALUE);

        maximum.accumulate(7);
        maximum.accumulate(2);
        maximum.accumulate(11);

        DoubleAccumulator peak =
                new DoubleAccumulator(
                        Double::max,
                        Double.NEGATIVE_INFINITY);

        peak.accumulate(1.5);
        peak.accumulate(3.25);
        peak.accumulate(-4.0);

        System.out.println("hits=" + hits.sum());
        System.out.println("longValue=" + hits.longValue());
        System.out.println("amount=" + amount.sum());
        System.out.println("doubleValue="
                + amount.doubleValue());
        System.out.println("maximum=" + maximum.get());
        System.out.println("peak=" + peak.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AccumulatorBasicsDemo.java
java AccumulatorBasicsDemo
~~~

**Stdout:**

~~~text
hits=4
longValue=4
amount=3.25
doubleValue=3.25
maximum=11
peak=3.25
~~~

**Giải thích:** 1+4−1=4; 1.25+2.5−0.5=3.25 trong các số đơn giản này. LongAccumulator giữ cực đại 11, DoubleAccumulator giữ cực đại 3.25. Không có concurrent writer khi đọc, vì vậy kết quả xác định.

## 5. LongAdder.sum() cho thống kê được ghi thường xuyên

Mẫu phổ biến:

~~~java
import java.util.concurrent.atomic.LongAdder;

class RequestCounter {
    private final LongAdder counter = new LongAdder();

    void onRequest() {
        counter.increment();
    }

    long observedTotal() {
        return counter.sum();
    }
}
~~~

Đây là class minh họa, không có main(). Các request threads có thể gọi onRequest đồng thời; thread thu thập metrics đọc observedTotal định kỳ.

**Phù hợp cho:** tổng lượt gọi, tổng bytes, số cache hits, số sự kiện xử lý, tần suất theo key.

**Không phù hợp khi dùng một mình cho:** số thứ tự duy nhất, phán quyết "chỉ cho thêm một request nếu đang dưới N", số dư có điều kiện, hoặc một cặp số phải được đọc/cập nhật nguyên tử cùng lúc.

### 5.1. Vì sao LongAdder có thể nhanh hơn AtomicLong?

Khi contention cao, cập nhật trên nhiều cells có thể giảm tranh chấp một vị trí nóng. Đây là mục tiêu thiết kế của lớp.

**Không bảo đảm LongAdder luôn nhanh hơn.** Khi ít threads hoặc đọc rất thường xuyên, việc dùng nhiều cells và tổng hợp khi đọc có thể không tạo lợi thế; phải benchmark trên workload cụ thể.

### 5.2. Đọc khi đang ghi có được phép không?

**Có.** sum() có thể được gọi trong khi threads khác cập nhật. Chỉ cần **không quảng bá nó thành atomic snapshot**. Nếu hệ thống vẽ biểu đồ theo sample mỗi vài giây, semantics quan sát thường phù hợp.

### 5.3. longValue() có giúp nhận snapshot mạnh hơn không?

**Không.** Nó tương đương sum(). Với DoubleAdder, doubleValue cũng tương đương sum. Với Accumulator, longValue/doubleValue tương đương get.

## 6. DoubleAdder.sum() và floating-point

Với DoubleAdder, còn một vấn đề độc lập với snapshot: **phép cộng double không hoàn toàn associative** do rounding.

~~~text
(a + b) + c có thể khác a + (b + c).
~~~

Lưu thành **FloatingPointOrderDemo.java**:

~~~java
public class FloatingPointOrderDemo {
    public static void main(String[] args) {
        double firstOrder =
                (1e16 + 1.0) - 1e16;

        double secondOrder =
                (1e16 - 1e16) + 1.0;

        System.out.println("first=" + firstOrder);
        System.out.println("second=" + secondOrder);
    }
}
~~~

~~~bash
javac -encoding UTF-8 FloatingPointOrderDemo.java
java FloatingPointOrderDemo
~~~

**Stdout:**

~~~text
first=0.0
second=1.0
~~~

Khi giá trị quá lớn, phép cộng một đơn vị nhỏ có thể bị làm tròn. DoubleAdder không bảo đảm thứ tự gộp các updates từ mọi threads, nên kết quả có thể khác việc cộng tuần tự theo một thứ tự tùy chọn.

**Không dùng DoubleAdder để quyết toán tiền.** Nếu cần số tiền tuyệt đối đúng, dùng loại dữ liệu và transaction phù hợp, chẳng hạn long theo đơn vị tiền nhỏ nhất có kiểm soát overflow, hoặc BigDecimal với chính sách làm tròn rõ ràng.

**NaN, Infinity và signed zero** cũng cần chính sách validation khi ứng dụng cho phép những đầu vào này.

## 7. LongAccumulator.get() và DoubleAccumulator.get()

Accumulator có một **hàm kết hợp** và một **identity**.

~~~java
LongAccumulator maximum =
        new LongAccumulator(
                Long::max,
                Long.MIN_VALUE);

maximum.accumulate(7);
maximum.accumulate(11);

long result = maximum.get(); // 11
~~~

~~~java
DoubleAccumulator peak =
        new DoubleAccumulator(
                Double::max,
                Double.NEGATIVE_INFINITY);

peak.accumulate(1.5);
peak.accumulate(3.25);

double result = peak.get(); // 3.25
~~~

Đây là hai đoạn minh họa độc lập; cần import lớp tương ứng.

### 7.1. Identity phải phù hợp với phép toán

**Long::max** trên toàn miền long nên dùng **Long.MIN_VALUE**. Nếu identity là 0 và chỉ cập nhật các số âm, giá trị max có thể thành 0 dù không có input bằng 0.

**Long::min** thường dùng **Long.MAX_VALUE**. Double::max thường dùng **Double.NEGATIVE_INFINITY** nếu domain cho phép. Với double, cần đặc biệt quy định hành vi mong muốn cho NaN/signed zero.

### 7.2. Hàm nên associative, commutative và không có side effects

Oracle nêu rõ thứ tự tích lũy giữa các threads không được bảo đảm. Để có kết quả dự đoán được, function nên associative và commutative theo semantics dữ liệu.

**Hàm phải không có side effects**, vì implementation có thể gọi lại khi một lần cập nhật thất bại vì contention.

~~~java
// Anti-pattern minh họa:
new LongAccumulator((a, b) -> {
    sendEmail(b);  // Không làm side effect trong accumulator.
    return Math.max(a, b);
}, Long.MIN_VALUE);
~~~

Đây là ví dụ ý tưởng, sendEmail là phương thức giả định. Retry có thể khiến email được gửi hơn một lần.

**Không dùng Accumulator để lưu “giá trị update cuối cùng theo thời gian”** nếu hàm phụ thuộc thứ tự; thứ tự liên thread không được bảo đảm. Cần sequence, timestamp và một kiểu state có quy tắc so sánh/cập nhật khác.

## 8. Sau khi writers kết thúc: tính tổng chính xác

Dùng **Future.get** để chờ toàn bộ cập nhật hoàn tất trước lần đọc.

Lưu thành **ConcurrentFinalTotalDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.LongAccumulator;
import java.util.concurrent.atomic.LongAdder;

public class ConcurrentFinalTotalDemo {
    public static void main(String[] args) throws Exception {
        int workers = 4;
        int iterations = 25_000;

        LongAdder visits = new LongAdder();
        LongAccumulator maximum =
                new LongAccumulator(Long::max, Long.MIN_VALUE);

        ExecutorService executor =
                Executors.newFixedThreadPool(workers);

        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int w = 0; w < workers; w++) {
                futures.add(executor.submit(() -> {
                    for (int i = 0; i < iterations; i++) {
                        visits.increment();
                        maximum.accumulate(i);
                    }
                }));
            }

            for (Future<?> f : futures) {
                f.get();
            }

            System.out.println("visits=" + visits.sum());
            System.out.println("max=" + maximum.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConcurrentFinalTotalDemo.java
java ConcurrentFinalTotalDemo
~~~

**Stdout:**

~~~text
visits=100000
max=24999
~~~

**Vì sao có thể xác nhận số cuối?**

- 4×25.000 = 100.000 increments.
- Mỗi thread đưa vào max các giá trị từ 0 tới 24.999.
- **Future.get() của tất cả tasks đã hoàn tất** trước sum/get.
- Không còn worker nào trong danh sách tiếp tục ghi.
- Hợp đồng Future.get cung cấp quan hệ memory consistency, giúp reader thấy kết quả đã hoàn tất.

**Nếu có producer khác đang dùng cùng adder/accumulator mà chưa được dừng hoặc chờ**, giả định quiescence không đúng. Phải kiểm soát tất cả đường ghi liên quan.

## 9. Quiescence: điểm dừng trước khi đọc

**Quiescent point** nghĩa là không có update đồng thời vào đối tượng trong lúc đọc. Có thể đạt được bằng:

- Chờ tất cả Future.get hoặc Thread.join.
- Dùng CountDownLatch/Phaser/CyclicBarrier với quy ước writer đã dừng rõ ràng.
- Khóa bảo vệ cả reader và writers.
- Dừng nhận writers mới, chờ writers đang xử lý kết thúc.

**Không dùng Thread.sleep(10)** rồi khẳng định producer đã dừng. Thời gian nghỉ không tạo quan hệ đồng bộ và scheduler không cam kết task sẽ hoàn thành trong khoảng đó.

**ExecutorService.shutdown()** cũng không có nghĩa tất cả task đã kết thúc ngay. Nó chỉ ngừng nhận task mới. Muốn xác nhận xong phải chờ Future.get/awaitTermination.

### 9.1. Demo điều khiển writer bằng latch

Lưu thành **PausedWriterDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.LongAdder;

public class PausedWriterDemo {
    public static void main(String[] args) throws Exception {
        LongAdder counter = new LongAdder();

        CountDownLatch firstDone = new CountDownLatch(1);
        CountDownLatch proceed = new CountDownLatch(1);

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            Future<?> writer = pool.submit(() -> {
                counter.add(3);
                firstDone.countDown();

                try {
                    proceed.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }

                counter.add(7);
            });

            firstDone.await();

            // Writer đang chờ latch và không cập nhật thêm.
            System.out.println("paused=" + counter.sum());

            proceed.countDown();
            writer.get();

            System.out.println("finished=" + counter.sum());
        } finally {
            proceed.countDown();
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 PausedWriterDemo.java
java PausedWriterDemo
~~~

**Stdout:**

~~~text
paused=3
finished=10
~~~

**Điều ví dụ chứng minh:** sum() chính xác khi writer đã được đưa đến điểm dừng và sau khi writer hoàn tất.

**Điều ví dụ không chứng minh:** sum() có atomic snapshot trong lúc writer thật sự update chồng lên một lần đọc.

## 10. reset(), sumThenReset() và getThenReset()

Các phương thức reset được thiết kế cho những giai đoạn **không có cập nhật đồng thời**:

~~~text
LongAdder.reset()
LongAdder.sumThenReset()
DoubleAdder.reset()
DoubleAdder.sumThenReset()
LongAccumulator.reset()
LongAccumulator.getThenReset()
DoubleAccumulator.reset()
DoubleAccumulator.getThenReset()
~~~

**sumThenReset()/getThenReset() không phải atomic drain khi writers đang ghi.** Chúng tương đương về hiệu ứng với lấy tổng/giá trị rồi reset các biến duy trì trạng thái. Cập nhật concurrent có thể xen kẽ với quá trình đó, nên tổng trả về không được bảo đảm là tổng cuối chính xác trước một ranh giới reset.

### 10.1. Demo reset khi không có writers

Lưu thành **QuiescentResetDemo.java**:

~~~java
import java.util.concurrent.atomic.DoubleAdder;
import java.util.concurrent.atomic.LongAccumulator;
import java.util.concurrent.atomic.LongAdder;

public class QuiescentResetDemo {
    public static void main(String[] args) {
        LongAdder window = new LongAdder();
        window.add(5);

        System.out.println("window="
                + window.sumThenReset());
        System.out.println("afterWindow="
                + window.sum());

        LongAccumulator max =
                new LongAccumulator(
                        Long::max,
                        Long.MIN_VALUE);

        System.out.println("maxBefore="
                + max.get());

        max.accumulate(7);
        max.accumulate(2);
        max.accumulate(11);

        System.out.println("maxWindow="
                + max.getThenReset());
        System.out.println("maxAfter="
                + max.get());

        DoubleAdder measure = new DoubleAdder();
        measure.add(2.75);

        System.out.println("doubleWindow="
                + measure.sumThenReset());
        System.out.println("doubleAfter="
                + measure.sum());
    }
}
~~~

~~~bash
javac -encoding UTF-8 QuiescentResetDemo.java
java QuiescentResetDemo
~~~

**Stdout:**

~~~text
window=5
afterWindow=0
maxBefore=-9223372036854775808
maxWindow=11
maxAfter=-9223372036854775808
doubleWindow=2.75
doubleAfter=0.0
~~~

**LongAccumulator** reset về identity Long.MIN_VALUE, không phải về 0, vì đã được khởi tạo theo phép Long::max.

### 10.2. Nguy cơ khi reset đồng thời với ghi

~~~text
Exporter                      Writer
--------                      ------
Đọc một cell
                              Cập nhật cell vừa đọc
Reset cell đó
                              Cập nhật cell khác
Reset cell tiếp theo
Xuất kết quả
~~~

Không có cam kết rằng mọi event được phân loại chính xác vào kỳ trước hoặc kỳ sau.

**Đừng chốt số liệu tài chính hay event windows exact bằng sumThenReset khi producers vẫn ghi.** Phải phối hợp writer ở điểm quiescence hoặc dùng một cơ chế chốt epoch có quản lý in-flight updates.

Chỉ **AtomicReference.getAndSet(new LongAdder())** cũng chưa đủ để chốt kỳ: một writer đã giữ tham chiếu adder cũ có thể tiếp tục ghi sau khi bạn swap sang đối tượng mới.

## 11. Histogram với ConcurrentHashMap và LongAdder

Một ứng dụng có thể đếm số event theo key bằng:

~~~java
ConcurrentHashMap<String, LongAdder> counts =
        new ConcurrentHashMap<>();

counts.computeIfAbsent(
        key,
        ignored -> new LongAdder()).increment();
~~~

Đây là đoạn minh họa với key đã có giá trị. ConcurrentHashMap quản lý việc truy cập map đồng thời, LongAdder đảm nhiệm số đếm của mỗi key.

### 11.1. Chương trình đầy đủ

Lưu thành **FrequencyMapDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class FrequencyMapDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, LongAdder> freqs =
                new ConcurrentHashMap<>();

        for (String key : List.of(
                "java", "go", "java",
                "rust", "go", "java")) {

            freqs.computeIfAbsent(
                    key,
                    ignored -> new LongAdder())
                    .increment();
        }

        Map<String, Long> snapshot = new TreeMap<>();

        freqs.forEach((key, value) ->
                snapshot.put(key, value.sum()));

        System.out.println("freq=" + snapshot);
    }
}
~~~

~~~bash
javac -encoding UTF-8 FrequencyMapDemo.java
java FrequencyMapDemo
~~~

**Stdout:**

~~~text
freq={go=2, java=3, rust=1}
~~~

Dữ liệu được cập nhật trước bước xuất, nên kết quả chính xác. TreeMap giúp thứ tự key trong output xác định.

**Khi writers còn thêm key hoặc tăng counts:** Duyệt ConcurrentHashMap và gọi sum() nhiều lần **không tạo snapshot nguyên tử của toàn histogram**. Các key khác nhau có thể được quan sát tại các thời điểm khác nhau.

Không thay ConcurrentHashMap bằng HashMap thường cho nhiều concurrent writers mà thiếu đồng bộ.

## 12. Vì sao hai LongAdder không tạo snapshot của một trạng thái hai field?

Giả sử:

~~~java
LongAdder accepted = new LongAdder();
LongAdder completed = new LongAdder();
~~~

Muốn tính **inFlight = accepted − completed**. Nếu một thread đọc accepted.sum() rồi completed.sum(), các updates có thể xảy ra ở giữa. Hai giá trị quan sát không cùng một instant.

**Ngay cả hai AtomicLong riêng biệt cũng không tự cho atomic snapshot của cả cặp.** AtomicLong có atomic operations **trên mỗi object**, không cung cấp transaction cho hai objects rời.

### 12.1. Dùng AtomicReference tới immutable state

Lưu thành **ConsistentCountsDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class ConsistentCountsDemo {
    record Counts(long accepted, long completed) {}

    public static void main(String[] args) {
        AtomicReference<Counts> state =
                new AtomicReference<>(new Counts(0, 0));

        state.updateAndGet(old ->
                new Counts(
                        old.accepted() + 3,
                        old.completed()));

        state.updateAndGet(old ->
                new Counts(
                        old.accepted(),
                        old.completed() + 2));

        Counts snapshot = state.get();

        System.out.println("accepted="
                + snapshot.accepted());
        System.out.println("completed="
                + snapshot.completed());
        System.out.println("inFlight="
                + (snapshot.accepted()
                        - snapshot.completed()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConsistentCountsDemo.java
java ConsistentCountsDemo
~~~

**Stdout:**

~~~text
accepted=3
completed=2
inFlight=1
~~~

**Giải thích:** AtomicReference trỏ tới một Counts immutable. Reader chỉ đọc một tham chiếu nên thấy hai field từ cùng một phiên bản state.

Đây là snapshot nhất quán của **state do AtomicReference quản lý**, không phải transaction toàn database hoặc giữa các dịch vụ. Hàm updateAndGet phải side-effect-free vì có thể bị gọi lại trong CAS retry.

**record là tính năng Java 17+**. Với Java 8 gốc, dùng một immutable final class có các trường final và getters.

### 12.2. Lock cũng phù hợp

Nếu mọi readers và writers đều dùng chung synchronized/ReentrantLock, có thể bảo vệ một nhóm fields. **Chỉ reader khóa còn writers tự cập nhật LongAdder bên ngoài khóa thì không đủ**.

## 13. AtomicLong khi cần thao tác nguyên tử

AtomicLong có các method:

- **get()**.
- **getAndIncrement()**, **incrementAndGet()**.
- **getAndAdd()**, **addAndGet()**.
- **compareAndSet()**.
- **getAndSet()**.
- **updateAndGet()**, **getAndUpdate()**.

Ví dụ:

~~~java
AtomicLong seq = new AtomicLong();
long id = seq.getAndIncrement();
~~~

Đây là một atomic read-modify-write trên seq. Nó khác với:

~~~java
// Không an toàn để cấp ID:
long id = adder.sum();
adder.increment();
~~~

Hai threads có thể cùng lấy cùng một id.

### 13.1. Chương trình cấp sequence

Lưu thành **AtomicSequenceDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public class AtomicSequenceDemo {
    public static void main(String[] args) {
        AtomicLong sequence = new AtomicLong();

        System.out.println("id0="
                + sequence.getAndIncrement());
        System.out.println("id1="
                + sequence.getAndIncrement());
        System.out.println("id2="
                + sequence.getAndIncrement());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicSequenceDemo.java
java AtomicSequenceDemo
~~~

**Stdout:**

~~~text
id0=0
id1=1
id2=2
~~~

**Lưu ý:** Đây là sequence trên một AtomicLong trong một JVM và trong phạm vi chưa overflow. Không tự bảo đảm ID duy nhất giữa nhiều tiến trình hoặc sau restart.

### 13.2. Quota cứng cần nguyên tử check-and-act

Một anti-pattern:

~~~java
if (active.sum() < LIMIT) {
    active.increment();
    allowRequest();
}
~~~

Đoạn minh họa với active là LongAdder. Phép so sánh và increment không cùng một hành động nguyên tử. Khi nhiều thread chạy, quota có thể bị vượt.

Dùng **Semaphore** cho số request active có acquire/release đúng lifecycle, hoặc AtomicInteger/AtomicLong CAS và policy phù hợp. Đối với quota toàn hệ thống phân tán, cần cơ chế phối hợp ở phạm vi tương ứng.

## 14. Tổng hợp theo cửa sổ thời gian

Muốn xuất thống kê từng phút, có các phương án với tính chất khác nhau:

- **Counter tích lũy không reset:** lấy sum() định kỳ và tính hiệu giữa hai samples. Trong lúc ghi, đây là số liệu quan sát và có giới hạn snapshot.
- **Buckets theo epoch/timestamp:** đưa event vào bucket phù hợp, có chính sách cho event tới muộn, quản lý điểm đóng bucket.
- **Quiescent barrier:** dừng hoặc phối hợp writers, đợi các updates in-flight rồi sumThenReset.
- **Event store/transaction authoritative:** tổng hợp dữ liệu đã ghi bền vững khi cần kiểm toán.

**Không có lựa chọn hoàn toàn miễn phí:** tăng độ nhất quán thường yêu cầu đồng bộ, chi phí lưu trữ hoặc latency cao hơn.

Chỉ đổi tham chiếu AtomicReference<LongAdder> sang một LongAdder mới không đủ nếu writer đã lấy tham chiếu cũ mà chưa hoàn tất. Cần protocol để biết có thể chốt adder cũ an toàn.

## 15. Hiệu năng và đánh đổi

LongAdder/DoubleAdder thường được thiết kế cho mô hình **nhiều cập nhật, ít đọc tổng**.

| Nhu cầu | Công cụ thường thích hợp |
|---|---|
| Request count cho monitoring | LongAdder |
| Tổng measurements double | DoubleAdder |
| Maximum/minimum có contention | LongAccumulator/DoubleAccumulator |
| Atomic sequence/quota một biến | AtomicLong/CAS |
| Đọc hai field cùng phiên bản | AtomicReference<immutable state> hoặc lock |
| Tổng cuối sau khi workers dừng | sum()/get() sau quiescence |
| Exact financial/audit records | Transaction/authoritative store |

Khi contention thấp, AtomicLong có thể đủ đơn giản. Khi contention cao, Adder thường có throughput cập nhật tốt hơn, nhưng tốn thêm không gian và phép đọc có thể phải tổng hợp nhiều cells.

**Không khẳng định luôn nhanh hơn**. Benchmark với workload thực bằng JMH, đo số writers/readers, latency, CPU, memory và GC thay vì một vòng lặp rất ngắn tự viết.

## 16. Giới hạn số học và kiểu dữ liệu

**LongAdder** giữ giá trị kiểu long; cộng vượt Long.MAX_VALUE có thể wraparound theo arithmetic long. Nó không tự chuyển sang BigInteger hay ném lỗi overflow.

~~~java
LongAdder adder = new LongAdder();
adder.add(Long.MAX_VALUE);
adder.add(1L);

long total = adder.sum();
// total bằng Long.MIN_VALUE trong ví dụ đơn luồng.
~~~

**DoubleAdder** và **DoubleAccumulator** chịu giới hạn IEEE floating-point: rounding, NaN, infinities và signed zero. Nếu nghiệp vụ cần tính toán tiền hoặc những đại lượng bắt buộc exact, hãy dùng kiểu số/thuật toán phù hợp.

Các phương thức chuyển Number như intValue() và floatValue() có thể mất precision do narrowing và **không cải thiện snapshot semantics**.

## 17. Các lỗi thường gặp

1. **Coi sum() hoặc get() là atomic snapshot khi writer vẫn đang ghi.** Tài liệu Oracle xác định rõ không có bảo đảm đó.
2. **Nhầm cập nhật thread-safe với đọc tổng tuyến tính hóa.** Đó là hai khái niệm khác nhau.
3. **Đổi sum() thành longValue() để “đọc nguyên tử”.** Chúng tương đương.
4. **Dùng sum()+increment để cấp sequence.** Đây không phải một atomic fetch-and-increment.
5. **Dùng sum() kiểm tra quota cứng rồi increment.** Check-and-act không atomic.
6. **Assert tổng cuối trước khi writers hoàn tất.** Cần Future.get/Thread.join hoặc đồng bộ đúng.
7. **Dùng Thread.sleep làm bằng chứng writers đã dừng.** Scheduling không được cam kết.
8. **Chỉ đợi một số workers nhưng còn writers khác.** Quiescence chưa tồn tại.
9. **Gọi sumThenReset trong lúc producers chạy và cần exact windows.** Có thể bị race.
10. **Swap LongAdder mới mà không phối hợp những writers giữ đối tượng cũ.** Chốt epoch không chính xác.
11. **Dùng DoubleAdder cho sổ cái tiền tệ.** Floating-point rounding không phù hợp.
12. **Để side effect trong Accumulator function.** Có thể bị gọi lại do contention.
13. **Chọn hàm không associative hoặc commutative** khi cần kết quả độc lập thứ tự.
14. **Chọn identity sai**, ví dụ Long::max với 0 khi chỉ có số âm.
15. **Dùng HashMap thường thay ConcurrentHashMap** cho histogram nhiều writers.
16. **Coi nhiều lần sum() của nhiều counters là snapshot cùng phiên bản.** Không có bảo đảm đó.
17. **Dùng hai AtomicLong rồi nghĩ cặp fields atomic.** Chỉ mỗi object có atomic access riêng.
18. **Không xem xét overflow của long** hoặc NaN/Infinity của double.
19. **Đo performance trên một trường hợp nhẹ** rồi kết luận LongAdder luôn tốt hơn AtomicLong.
20. **Dựa vào một test race ngẫu nhiên để chứng minh “mỗi lần sum đều bỏ sót”.** Hành vi không dự đoán theo từng lịch chạy.
21. **Sử dụng giá trị metrics tạm để chốt quyết toán authoritative.** Cần nguồn dữ liệu có consistency phù hợp.
22. **Không ghi rõ semantics của API trả metric**, khiến caller hiểu nhầm observed sample thành số exact tại một điểm thời gian.

## 18. Checklist kiểm thử và production

- [ ] Xác định số liệu này là **thống kê quan sát** hay **giá trị chính xác bắt buộc**.
- [ ] Dùng **sum() cho Adder**, **get() cho Accumulator**.
- [ ] Nếu test tổng cuối, đã đợi **toàn bộ writers**.
- [ ] Không assert một giá trị in-progress cụ thể dựa trên Thread.sleep.
- [ ] Mọi phương thức reset được gọi tại quiescent point hoặc chấp nhận rõ rủi ro race.
- [ ] Nếu chốt bucket, đã xử lý writers có tham chiếu epoch cũ.
- [ ] Accumulator function thuần, associative/commutative trong domain, identity phù hợp.
- [ ] Với double, đã quy định rounding, NaN, Infinity và signed zero.
- [ ] Với long, đã xem xét overflow và narrowing conversion.
- [ ] Nếu dùng ConcurrentHashMap, hiểu giới hạn đọc đồng thời toàn map.
- [ ] Nếu cấp ID/quota, có atomic check-and-act hoặc transactional admission.
- [ ] Nếu cần snapshot nhiều field, dùng một state nguyên tử/lock thích hợp.
- [ ] Benchmark theo contention thực, không tự giả định performance.
- [ ] Có cơ chế chờ writers dừng trước khi xuất số chốt kỳ.
- [ ] Dashboard/export có mô tả kết quả là observed sample nếu còn concurrent writes.

## 19. Bài tập tự luyện

**Bài 1.** Dùng 4 workers, mỗi worker tăng LongAdder 10.000 lần, chờ Future.get rồi assert tổng 40.000. Vì sao không assert 40.000 khi tasks đang chạy?

**Bài 2.** Dùng LongAccumulator(Long::max, Long.MIN_VALUE) với -3, -5, -2. Dự đoán get() sau quiescence. Nếu identity là 0 thì chuyện gì xảy ra?

**Bài 3.** Chạy FloatingPointOrderDemo và giải thích vì sao DoubleAdder không hứa tổng tương ứng một thứ tự cộng nhất định.

**Bài 4.** Sau khi dừng writers, gọi sumThenReset và kiểm tra số trước/sau. Hãy mô tả một lịch xen kẽ khiến reset khi đang ghi không thể chốt kỳ chính xác.

**Bài 5.** Đếm frequency bằng ConcurrentHashMap<String,LongAdder>. Tại sao xuất map khi writers vẫn thêm key không là snapshot nguyên tử?

**Bài 6.** Thiết kế quota 100 concurrent requests bằng Semaphore. Cần release lúc nào và tại sao không dùng sum()<100 rồi increment?

**Bài 7.** Tạo hai counters accepted/completed và chuyển sang AtomicReference<Counts> để đọc cùng phiên bản. Giải thích ưu/nhược điểm.

**Bài 8.** Thiết kế bucket theo phút có xử lý writer giữ tham chiếu bucket cũ. Nêu cơ chế barrier hoặc event store.

**Bài 9.** Giải thích vì sao đưa side effect vào LongAccumulator function có thể làm hành động thực thi hơn một lần.

**Bài 10.** Tại sao một benchmark LongAdder vs AtomicLong cần kiểm soát số threads, read/write ratio, JIT và GC?

## 20. Câu hỏi ôn tập

**1. LongAdder đọc bằng gì?** — sum().

**2. LongAccumulator đọc bằng gì?** — get().

**3. sum/get có là atomic snapshot khi concurrent writers active không?** — Không.

**4. Thread-safe increments có làm sum tuyến tính hóa không?** — Không, hai mức bảo đảm khác nhau.

**5. Khi nào sum/get chính xác?** — Khi không có concurrent updates trong lúc tổng hợp, và cập nhật trước đã hoàn tất/đồng bộ đúng.

**6. LongAdder giảm contention bằng cơ chế gì?** — Có thể chia updates ra base và các cells.

**7. longValue của LongAdder có mạnh hơn sum không?** — Không, chúng tương đương.

**8. Vì sao DoubleAdder có sai số phụ thuộc thứ tự gộp?** — Floating-point addition không associative tuyệt đối.

**9. Accumulator function cần tính chất nào?** — Không side effects, và để dự đoán được nên associative/commutative, có identity đúng.

**10. Identity cho Long::max trên long toàn miền?** — Long.MIN_VALUE.

**11. sumThenReset có bảo đảm chốt kỳ exact khi writers vẫn active không?** — Không.

**12. Vì sao cần Future.get của mọi writer trước khi assert sum cuối?** — Để xác nhận hoàn tất và thiết lập visibility/happens-before.

**13. Có thể dùng Thread.sleep để bảo đảm writer đã xong không?** — Không.

**14. Có thể dùng LongAdder.sum()+increment để cấp ID duy nhất không?** — Không.

**15. AtomicLong.getAndIncrement khác gì?** — Atomic read-modify-write trên một biến.

**16. Đọc hai LongAdder liên tiếp có cùng phiên bản không?** — Không được bảo đảm.

**17. AtomicReference<immutable state> giúp gì?** — Reader nhận một object mang cặp fields cùng phiên bản.

**18. Duyệt ConcurrentHashMap và sum các values khi đang ghi có là global snapshot không?** — Không.

**19. LongAdder có tự chống overflow không?** — Không.

**20. DoubleAccumulator với NaN cần gì?** — Domain validation hoặc policy rõ.

**21. Accumulator function có thể được gọi lại khi tranh chấp không?** — Có.

**22. Có thể dùng Accumulator làm “latest value theo thứ tự thread” không?** — Không phù hợp.

**23. LongAdder có hữu ích cho metrics đang chạy không?** — Có, khi chấp nhận semantics observed sample.

**24. Chỉ đợi một trong nhiều writers thì có quiescent chưa?** — Chưa.

**25. Một test race không tái hiện missing update có chứng minh sum atomic không?** — Không; hợp đồng API vẫn giới hạn non-atomic.

## 21. Tổng kết

**LongAdder.sum(), DoubleAdder.sum(), LongAccumulator.get() và DoubleAccumulator.get() là các API an toàn cho việc tích lũy đồng thời, nhưng không phải các thao tác chụp snapshot nguyên tử khi writers tiếp tục cập nhật.**

Ghi nhớ:

- Adder dùng **sum()**, Accumulator dùng **get()**.
- Cập nhật đồng thời được thiết kế an toàn, nhưng phép đọc tổng hợp có thể chưa bao gồm updates diễn ra trong lúc quét.
- **Không còn concurrent writers** sau khi đồng bộ đúng là điều kiện để đọc tổng chính xác.
- **sumThenReset/getThenReset/reset không atomic drain** khi writers chạy; dùng tại quiescent points hoặc có giao thức chốt kỳ riêng.
- Double có rounding phụ thuộc thứ tự và special values; Accumulator cần hàm thuần và identity đúng.
- ConcurrentHashMap + LongAdder phù hợp cho histogram, nhưng đọc toàn map khi có ghi không tạo global snapshot.
- Với ID, quota hoặc một biến cần check-and-update nguyên tử, cân nhắc **AtomicLong/CAS/Semaphore**.
- Với snapshot nhiều field cùng phiên bản, dùng **AtomicReference tới state bất biến** hoặc lock/transaction.
- **Metrics quan sát khác dữ liệu audit và quyết toán chính xác.** Chọn đúng consistency trước khi tối ưu throughput.
- Test bằng Future.get/latch/barrier với protocol rõ ràng, không dựa vào Thread.sleep.

### Tài liệu Oracle chính thức

- [LongAdder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [DoubleAdder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/DoubleAdder.html)
- [LongAccumulator — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAccumulator.html)
- [DoubleAccumulator — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/DoubleAccumulator.html)
- [AtomicLong — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html)
- [AtomicReference — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)
- [ConcurrentHashMap — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Future — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html)
