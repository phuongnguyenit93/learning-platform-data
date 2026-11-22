# LongAdder, DoubleAdder và giảm tranh chấp cập nhật trong Java

## 1. Bài toán: nhiều luồng cùng cập nhật một biến

Giả sử hệ thống nhận hàng chục nghìn request mỗi giây, nhiều worker đều cần tăng bộ đếm request. Nếu dùng một biến long thông thường và viết count++, thao tác đọc–cộng–ghi không nguyên tử. Hai thread có thể cùng đọc 10, cùng tính 11 và đều ghi 11: một lần tăng bị mất. Dùng volatile long cũng không biến phép tăng thành nguyên tử.

Một phương án an toàn là **AtomicLong.incrementAndGet()**. Mọi thread cùng cập nhật một giá trị atomic, bảo toàn từng phép tăng và có thể lấy ngay giá trị mới sau khi tăng. Nhưng khi rất nhiều thread liên tục tranh chấp **cùng một vị trí dữ liệu**, việc cập nhật có thể trở thành điểm nóng.

Từ Java 8, **LongAdder** và **DoubleAdder** thuộc java.util.concurrent.atomic cung cấp cách tối ưu hóa cho trường hợp **nhiều thread cập nhật cùng một tổng, nhưng việc đọc tổng ít thường xuyên hơn**. Thay vì bắt mọi update tranh chấp một biến duy nhất, implementation có thể mở rộng thành **nhiều thành phần tích lũy nội bộ** để phân tán tranh chấp. Khi đọc, sum() kết hợp các thành phần thành một giá trị.

Các API này vẫn còn áp dụng trong JDK hiện đại. Chúng thích hợp cho **thống kê, metric, đếm sự kiện, tổng trọng số**, nhưng **không phải** lựa chọn thay thế AtomicLong trong mọi bài toán đồng bộ.

### Mục tiêu của bài

Sau khi học, bạn có thể:

1. Giải thích **lost update**, contention và lý do biến tích lũy được phân tán thành nhiều thành phần.
2. Sử dụng các phương thức của **LongAdder**: add, increment, decrement, sum, longValue, reset, sumThenReset.
3. Sử dụng **DoubleAdder.add(double)** cho tổng số thực và giải thích sai số dấu phẩy động.
4. Hiểu vì sao **sum() không phải atomic snapshot** khi các luồng vẫn cập nhật.
5. Biết khi nào **sumThenReset/reset chỉ an toàn về kết quả khi không có cập nhật đồng thời**.
6. So sánh **AtomicLong** và LongAdder theo yêu cầu đọc/ghi, atomic return, compare-and-set, bộ nhớ và throughput.
7. Đếm nhiều thread đúng bằng ExecutorService, Future.get và điểm đồng bộ rõ.
8. Xây dựng **ConcurrentHashMap<K,LongAdder>** làm bản đồ tần suất/histogram.
9. Phân biệt **LongAdder** và **LongAccumulator**, **DoubleAdder** và **DoubleAccumulator**.
10. Chọn cách làm phù hợp cho metrics đang chạy, thống kê theo cửa sổ thời gian, số tiền, số định danh tăng dần và giới hạn số lượng đang hoạt động.
11. Tránh kết luận hiệu năng không có benchmark; hiểu cơ chế, điều kiện đo JMH và các trade-off thực tế.
12. Kiểm thử 7 chương trình Java 17 độc lập cùng kết quả stdout xác định.

**Special Note và phiên bản:** Nội dung chỉ gồm các API và kỹ thuật vẫn được hỗ trợ trong Java hiện đại. Các class LongAdder, DoubleAdder, LongAccumulator, DoubleAccumulator là API từ Java 8; các ví dụ độc lập biên dịch bằng **javac --release 17**. Không đề xuất những API đã legacy.

## 2. Atomicity và contention: hai vấn đề khác nhau

**Atomicity của phép tăng** là bảo đảm không mất một update khi nhiều thread cùng thực hiện phép tăng. **Contention** là tình trạng nhiều thread đồng thời muốn cập nhật cùng một nguồn lực, khiến throughput giảm do phải điều phối quyền ghi hoặc retry.

Ví dụ phản chứng:

~~~java
// PHẢN VÍ DỤ: count++ không atomic khi nhiều thread cùng dùng biến.
private long count = 0;
void increment() {
    count++;
}
~~~

Với hai thread cùng thực thi, phép tăng không phải một thao tác nguyên tử. Chuyển thành volatile long chỉ cải thiện các đặc tính truy cập/hiển thị giá trị, **không biến read-modify-write thành atomic increment**.

Giải pháp atomic truyền thống:

~~~java
// Mảnh mã, cần import java.util.concurrent.atomic.AtomicLong.
AtomicLong count = new AtomicLong();
count.incrementAndGet(); // trả giá trị mới bằng một thao tác atomic
long current = count.get();
~~~

AtomicLong có các phép cập nhật và đọc atomic trên một giá trị, thích hợp khi cần **đúng trình tự cập nhật, giá trị trả ngay sau phép tăng, compareAndSet, getAndSet** hoặc trạng thái dùng để ra quyết định.

LongAdder cũng bảo toàn các cập nhật tích lũy theo API khi dùng đúng nhưng **không có một giá trị atomic duy nhất để đọc/compareAndSet như AtomicLong**. Vì vậy, hai lớp giải hai bài toán khác nhau: một lớp cung cấp atomic state trên một scalar, lớp kia tối ưu **throughput của cộng dồn nhiều writer**.

## 3. Cơ chế LongAdder giảm tranh chấp như thế nào?

Theo JavaDoc, LongAdder duy trì **một hoặc nhiều thành phần chứa tổng long**, bắt đầu từ 0. Khi nhiều thread tranh chấp cập nhật, tập các biến nội bộ **có thể tăng động** để giảm khả năng mọi update đều phải thao tác trên cùng một vị trí.

Sơ đồ ý tưởng (không phải cam kết về bố cục bộ nhớ hoặc số cells của mọi JDK):

~~~text
Nhiều luồng cùng tăng một bộ đếm:

Mô hình một điểm nóng:
Thread A -----\
Thread B ------> [AtomicLong: một giá trị] -> đọc atomic
Thread C -----/
Thread D ----/

Mô hình phân tán tranh chấp:
Thread A ------> [thành phần tích lũy 1]
Thread B ------> [thành phần tích lũy 2]
Thread C ------> [thành phần tích lũy 3]
Thread D ------> [thành phần tích lũy 4]
                         |
                         v
               sum() kết hợp các thành phần
~~~

Các phiên bản OpenJDK thường có một giá trị nền cùng tập cells để phân tán cập nhật khi cần, sử dụng thao tác atomic nội bộ. Nhưng **base/cells và chiến lược phân bố cụ thể là chi tiết implementation**, không phải điều khoản để code ứng dụng truy cập hoặc giả định số lượng cells luôn bằng số thread.

**Đổi lại:** LongAdder có thể tiêu tốn nhiều bộ nhớ hơn AtomicLong và sum() phải đọc/kết hợp nhiều thành phần. Dưới contention cao và nhiều update hơn read, throughput kỳ vọng có thể tốt hơn. Khi ít contention hoặc đọc tổng cực thường xuyên, lợi ích có thể nhỏ hoặc thua phương án atomic đơn giản. **Không có bảo đảm LongAdder luôn nhanh hơn trong mọi workload.**

### Một phép cập nhật không đồng nghĩa một atomic snapshot toàn bộ

LongAdder.add(1) thực hiện update theo cơ chế phù hợp. Nhưng do số liệu có thể nằm ở nhiều thành phần, sum() phải kết hợp chúng. Khi các thread vẫn cập nhật, việc đọc lần lượt các thành phần **không được JavaDoc bảo đảm là một snapshot atomic tại một thời điểm duy nhất**. Chi tiết này quyết định khi nào bạn nên dùng LongAdder.

## 4. API LongAdder phải nắm chắc

| API | Vai trò | Lưu ý |
|---|---|---|
| new LongAdder() | Tạo biến tổng long ban đầu bằng 0 | Không truyền initial value qua constructor |
| add(long delta) | Cộng một delta có dấu | Có thể dùng delta âm |
| increment() | Tương đương add(1) | Trả void, **không trả tổng mới** |
| decrement() | Tương đương add(-1) | Trả void |
| sum() | Kết hợp các thành phần thành long | Không atomic snapshot khi cập nhật đồng thời |
| longValue() | Tương đương sum() | Không phải đọc atomic như AtomicLong.get |
| intValue() | Ép kết quả sum thành int | Có thể mất dữ liệu khi thu hẹp kiểu |
| reset() | Đưa tổng về 0 | Chỉ có ý nghĩa đáng tin khi **không có writer** |
| sumThenReset() | Lấy tổng rồi reset về 0 về mặt hiệu ứng | Không atomic với writer đang cập nhật |
| toString() | Chuỗi của sum hiện tại | Không làm snapshot atomic |

**Quan trọng:** LongAdder **không có** incrementAndGet(), getAndIncrement(), compareAndSet(), getAndSet() và cũng không có AtomicLong.get() với cùng semantics. Đừng tự tạo một công thức sum() rồi add() để giả lập compare-and-set hay cấp phát số thứ tự.

### Giá trị âm và kiểu số nguyên

LongAdder.add(-4) hợp lệ. Bạn có thể dùng increment/decrement để theo dõi một gauge thống kê, nhưng không thể dùng **sum()+điều kiện rồi add()** để triển khai ràng buộc atomic như “chỉ cho tối đa 10 người dùng đang hoạt động”.

LongAdder dùng **long 64-bit có dấu**, không kiểm tra overflow số nguyên tự động cho mọi phép cộng. Nếu cần tổng chính xác lớn hơn phạm vi long, hãy chọn mô hình số có giới hạn/overflow detection hoặc BigInteger với chiến lược đồng bộ thích hợp. **LongAdder không tự mở rộng độ chính xác ngoài long**.

## 5. Ví dụ đầy đủ 1 — LongAdder cơ bản, add âm và reset khi không có writer

Tạo file **LongAdderBasicsDemo.java**:

~~~java
import java.util.concurrent.atomic.LongAdder;
public class LongAdderBasicsDemo {
    public static void main(String[] args) {
        LongAdder count = new LongAdder();
        System.out.println("initial=" + count.sum());
        count.add(10);
        count.increment();
        count.decrement();
        count.add(-4);
        System.out.println("sum=" + count.sum());
        System.out.println("longValue=" + count.longValue());
        System.out.println("flushed=" + count.sumThenReset());
        System.out.println("afterFlush=" + count.sum());
        count.add(3);
        count.reset();
        System.out.println("afterReset=" + count.sum());
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~text
javac --release 17 LongAdderBasicsDemo.java
java LongAdderBasicsDemo
~~~

Stdout:

~~~text
initial=0
sum=6
longValue=6
flushed=6
afterFlush=0
afterReset=0
~~~

**Diễn giải:**

- Khởi tạo bắt đầu ở 0.
- Sau add(10), increment, decrement, add(-4), tổng = 10 + 1 - 1 - 4 = 6.
- longValue() bằng sum() theo contract.
- sumThenReset() trả 6 rồi đưa bộ cộng về 0.
- Sau add(3) rồi reset(), tổng lại là 0.
- **Trong demo chỉ có main cập nhật**, vì thế các thao tác reset không đua với writer. Không lấy demo này làm bằng chứng rằng sumThenReset là atomic khi nhiều thread cùng add.

## 6. AtomicLong so với LongAdder: chọn theo mục tiêu nghiệp vụ

| Tiêu chí | AtomicLong | LongAdder |
|---|---|---|
| Bản chất | Một giá trị long atomic | Một tổng qua một/nhiều thành phần |
| Cập nhật + trả giá trị mới | incrementAndGet/addAndGet | Không có tương đương atomic |
| Đọc giá trị tại một điểm tuyến tính hóa | get() atomic | sum() **không atomic snapshot** |
| Compare-and-set | compareAndSet | Không hỗ trợ |
| Đổi giá trị và lấy giá trị cũ | getAndSet | Không có |
| Cập nhật số lượng lớn từ nhiều thread | Có, có thể tranh chấp trên cùng scalar | Thiết kế để giảm tranh chấp |
| Chi phí bộ nhớ | Thường gọn hơn | Có thể lớn hơn vì các thành phần mở rộng |
| Đọc rất thường xuyên | get() đơn giản | sum() có thể phải cộng nhiều thành phần |
| Dùng cho metric/tần suất | Có thể dùng | Thường phù hợp khi writer nhiều, read ít |
| Dùng cho sequence ID / CAS control | Phù hợp | **Không phù hợp** |
| Reset đồng thời writer | getAndSet(0) là thao tác atomic trên scalar | sumThenReset không atomic với writer |
| Bảo đảm luôn nhanh hơn | Không | Không |

Các con số throughput cụ thể phụ thuộc CPU, số thread, tỷ lệ đọc/ghi, layout bộ nhớ, JDK và cách benchmark. Với ít contention, hai loại có thể có hiệu năng gần nhau; benchmark thực tế mới cho biết lựa chọn nào phù hợp.

**Ví dụ chọn lựa:**

- Đếm tổng request để biểu đồ metrics mỗi 10 giây: LongAdder thường hợp lý.
- Phát sinh một số sequence phải duy nhất trong tiến trình: AtomicLong.incrementAndGet có semantics phù hợp hơn.
- Giới hạn số task đang chạy không vượt N với quyết định atomic: AtomicLong CAS hoặc semaphore; không lấy LongAdder.sum() làm khóa kiểm soát.
- Chốt chính xác tổng giao dịch khi writer vẫn hoạt động: cần giao thức đồng bộ/snapshot nhất quán, không chỉ gọi LongAdder.sum().

## 7. Ví dụ đầy đủ 2 — nhiều thread cập nhật LongAdder và AtomicLong

Tạo file **ConcurrentAdderDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class ConcurrentAdderDemo {
    public static void main(String[] args) throws Exception {
        final int workers = 4;
        final int perWorker = 10_000;
        LongAdder striped = new LongAdder();
        AtomicLong atomic = new AtomicLong();
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch start = new CountDownLatch(1);
        try {
            List<Future<?>> results = new ArrayList<>();
            for (int w = 0; w < workers; w++) {
                results.add(pool.submit(() -> {
                    start.await();
                    for (int i = 0; i < perWorker; i++) {
                        striped.increment();
                        atomic.incrementAndGet();
                    }
                    return null;
                }));
            }
            start.countDown();
            for (Future<?> result : results) result.get();
            System.out.println("expected=" + workers * perWorker);
            System.out.println("longAdder=" + striped.sum());
            System.out.println("atomicLong=" + atomic.get());
            System.out.println("matches=" + (striped.sum() == atomic.get()));
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 ConcurrentAdderDemo.java
java ConcurrentAdderDemo
~~~

Stdout:

~~~text
expected=40000
longAdder=40000
atomicLong=40000
matches=true
~~~

**Giải thích:**

1. Bốn worker cùng đợi start latch rồi mỗi worker tăng **10.000 lần**.
2. Mỗi lần lặp cập nhật cả LongAdder và AtomicLong để so kết quả. Đây **không phải benchmark throughput**, vì cùng một vòng lặp thực hiện cả hai update.
3. Future.get() đợi đủ cả bốn worker. Sau khi các writer kết thúc, việc gọi LongAdder.sum() không còn cạnh tranh với update, vì vậy kết quả phản ánh 4 × 10.000 = 40.000.
4. Việc có cùng kết quả sau khi quiescent **không** có nghĩa LongAdder.sum() là atomic snapshot trong khi có writer.
5. shutdownNow ở finally giúp đóng pool nếu tác vụ lỗi; trong service thật nên dùng lifecycle do owner quản lý, xử lý interrupted tasks và shutdown theo policy.

**Đừng kết luận** “LongAdder nhanh hơn AtomicLong” chỉ từ demo: chương trình không đo thời gian, JIT warmup hoặc độ phân bố tranh chấp. Mục tiêu của nó là kiểm thử **tính đúng của phép cộng sau khi tất cả updates đã hoàn tất**.
## 8. DoubleAdder: cộng dồn số thực dưới tranh chấp

**DoubleAdder** có mục đích tương tự LongAdder nhưng giữ **double**:

- new DoubleAdder() bắt đầu từ 0.0.
- **add(double)** cộng một số thực, kể cả số âm.
- **sum()** và **doubleValue()** trả tổng double hiện tại.
- **sumThenReset()** trả tổng rồi đặt bộ cộng về 0.0 về mặt hiệu ứng, **chỉ đáng tin khi không có cập nhật đồng thời**.
- **reset()** đưa tổng về 0.0, cũng chỉ dùng ở trạng thái quiescent.
- DoubleAdder **không có increment/decrement** tiện ích như LongAdder; muốn tăng 1.0 dùng add(1.0).

DoubleAdder thích hợp khi nhiều worker cộng dồn các số đo như tổng thời lượng dưới dạng double, trọng số và dữ liệu thống kê. Nếu cần **đếm số sự kiện nguyên**, LongAdder thường đơn giản hơn vì không vướng sai số dấu phẩy động.

### Tốc độ cập nhật không đồng nghĩa độ chính xác decimal

DoubleAdder không phải “BigDecimal chạy nhanh”. Nó vẫn dùng **IEEE 754 double**. Phép cộng dấu phẩy động **không có tính kết hợp tuyệt đối** do các số bị làm tròn khi biểu diễn:

~~~text
Trong toán học: (a+b)+c = a+(b+c)

Trong floating-point:
(1e16 + 1.0) + (-1e16) có thể khác
1e16 + (1.0 + -1e16)
~~~

Khi nhiều thread cập nhật, thứ tự cộng trong từng thành phần và khi kết hợp các thành phần **không được JavaDoc bảo đảm**. Hai lần chạy có thể cho số double hơi khác nhau. Hiệu năng concurrency không giải quyết sai số số học.

**Nếu cần số thập phân chính xác**, chẳng hạn tiền thanh toán, thuế, quyết toán hoặc ledger phải kiểm toán, DoubleAdder không phù hợp chỉ vì nó thread-safe. Cân nhắc BigDecimal cùng cơ chế đồng bộ/tổng hợp có thể kiểm toán, hoặc số nguyên của đơn vị tiền nhỏ nhất với kiểm soát overflow và quy tắc làm tròn.

### Giá trị double đặc biệt

DoubleAdder nhận double, không tự loại trừ **NaN** hay **Infinity**. Nếu nguồn có giá trị đặc biệt, tổng có thể trở thành NaN/Infinity theo toán học dấu phẩy động. Với metrics, phải có chính sách validate:

~~~java
// Mảnh mã, sample là double, measurements là DoubleAdder.
if (Double.isFinite(sample)) {
    measurements.add(sample);
} else {
    // Ghi nhận hoặc loại mẫu theo chính sách dữ liệu.
}
~~~

Cần chuẩn hóa **đơn vị đo** trước khi cộng. DoubleAdder không biết 500 milliseconds và 0.5 seconds có cùng đơn vị hay chưa.

### DoubleAdder.sum cũng không atomic snapshot

Giống LongAdder, DoubleAdder.sum() không bảo đảm kết quả như một snapshot tại một thời điểm nếu còn updates. Ngoài ra, do floating-point không associative, **ngay cả khi toàn bộ writers đã dừng**, kết quả có thể không giống một thứ tự cập nhật tuần tự cố định.

Không test concurrent floating-point bằng cách đòi bit-for-bit bằng tổng từ một thứ tự tuần tự duy nhất. Dùng epsilon/tolerance phù hợp hoặc chọn thuật toán tổng hợp deterministic và chính xác hơn nếu domain đòi hỏi.

## 9. Ví dụ đầy đủ 3 — DoubleAdder và precision decimal

Tạo file **DoubleAdderDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.concurrent.atomic.DoubleAdder;

public class DoubleAdderDemo {
    public static void main(String[] args) {
        DoubleAdder total = new DoubleAdder();
        total.add(1.25);
        total.add(2.5);
        total.add(-0.5);
        System.out.println("sum=" + total.sum());
        System.out.println("flushed=" + total.sumThenReset());
        System.out.println("afterFlush=" + total.sum());
        total.add(0.1);
        total.add(0.2);
        System.out.println("fraction=" + total.sum());
        System.out.println("exactDecimal="
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));
    }
}
~~~

Chạy:

~~~text
javac --release 17 DoubleAdderDemo.java
java DoubleAdderDemo
~~~

Stdout:

~~~text
sum=3.25
flushed=3.25
afterFlush=0.0
fraction=0.30000000000000004
exactDecimal=0.3
~~~

**Diễn giải:**

1. Các số 1.25, 2.5 và -0.5 được biểu diễn chính xác bằng double nên tổng là 3.25.
2. Trong ví dụ single-thread, sumThenReset() trả 3.25; sau đó sum() là 0.0.
3. Cộng 0.1 và 0.2 gây sai số biểu diễn nhị phân, nên tổng in 0.30000000000000004.
4. BigDecimal tạo từ **chuỗi thập phân** "0.1" và "0.2" cho tổng chính xác 0.3.
5. Phép thử một thread cho stdout xác định; trong ứng dụng concurrent, DoubleAdder không hứa mọi lịch chạy cho cùng bit pattern của double.

BigDecimal là immutable và có semantics số thập phân phù hợp nhưng **không tự biến cập nhật vào một reference shared thành atomic**. Với nhiều worker, cần đồng bộ hoặc gom kết quả per-worker rồi reduce ở điểm nhất quán.

## 10. Thống kê nhiều write, ít read

Một workload phù hợp với LongAdder:

~~~text
Worker 1 -> increment() \
Worker 2 -> increment()  \
Worker 3 -> increment()  --> [LongAdder: requestCount]
Worker 4 -> increment()  /             |
Worker 5 -> increment() /              v
                                  metrics exporter
                                  đọc sum() định kỳ
~~~

Bộ đếm được ghi liên tục ở nhiều thread, còn exporter chỉ cần đọc vài giây/lần. Tỷ lệ **write-heavy/read-light** cho phép LongAdder đánh đổi chi phí đọc và bộ nhớ để có throughput update tốt hơn dưới tranh chấp.

### Từ metric quan sát tới điều khiển nghiệp vụ

Số như “đã xử lý bao nhiêu request” có thể dùng cho dashboard nếu chấp nhận tính không-atomic của snapshot. Ngược lại, số dùng để **ra quyết định đồng bộ** như “không cho vượt 100 nhiệm vụ đang chạy” phải có thao tác kiểm tra và cập nhật nguyên tử hoặc cơ chế permit.

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ: không atomic dù activeUsers là LongAdder.
if (activeUsers.sum() < 100) {
    activeUsers.increment();
    allowLogin();
}
~~~

Hai thread có thể cùng thấy 99 rồi cùng tăng, vượt ngưỡng 100. Đó là **check-then-act race**; ngay cả khi từng sum được đọc chính xác, sum+increment vẫn không tạo transaction atomic.

**Cách phù hợp hơn:** Dùng Semaphore để quản lý permit, hoặc AtomicInteger/AtomicLong với CAS và policy release, tùy yêu cầu. LongAdder có thể tiếp tục làm metric quan sát song song, không đóng vai trò khóa kiểm soát.

## 11. Frequency map: mỗi key có một bộ cộng

JavaDoc LongAdder và ConcurrentHashMap đưa ra pattern:

~~~java
// Mảnh mã, freqs là ConcurrentHashMap<String, LongAdder>.
freqs.computeIfAbsent(key, k -> new LongAdder()).increment();
~~~

Trong đó:

1. **ConcurrentHashMap** cho phép nhiều thread truy cập map an toàn và tạo value cho key khi cần.
2. **LongAdder** cho phép nhiều thread cùng tăng một **hot key** với khả năng giảm tranh chấp.

computeIfAbsent chỉ bảo đảm việc xử lý map theo contract; lời gọi **increment() xảy ra sau đó**, không phải cùng transaction atomic với mọi thao tác remove/replace. Ví dụ đơn giản không xóa key nên ổn.

**Nếu remove/replace/clear key đồng thời với updates**, một worker có thể đã giữ reference đến LongAdder cũ, sau đó tăng nó khi value trong map đã thay; số trong map mới sẽ không có update đó. Cần thiết kế lifecycle key/epoch và đồng bộ phù hợp.

### Cardinality và memory

Một key cho mỗi user ID, trace ID hoặc URL chứa giá trị động dễ tạo cardinality cực lớn. Mỗi entry giữ object LongAdder, có thể còn nhiều thành phần nội bộ khi tranh chấp. Trước khi tạo metrics:

- Chuẩn hóa route (ví dụ /users/{id} thay vì một key cho mỗi id).
- Giới hạn nhãn động không kiểm soát.
- Có chính sách lifecycle/retention.
- Khi publish số liệu, chuyển về giá trị long hoặc DTO thay vì chia sẻ tham chiếu adder.
- Không dùng LongAdder làm **key** của map: nó mutable và không có equals/hashCode theo tổng.

## 12. Ví dụ đầy đủ 4 — ConcurrentHashMap<String, LongAdder>

Tạo file **FrequencyMapDemo.java**:

~~~java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.LongAdder;

public class FrequencyMapDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, LongAdder> counts = new ConcurrentHashMap<>();
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> jobs = new ArrayList<>();
            for (int w = 0; w < 4; w++) {
                jobs.add(pool.submit(() -> {
                    for (int i = 0; i < 1_000; i++) {
                        counts.computeIfAbsent("api", key -> new LongAdder())
                              .increment();
                        if ((i & 1) == 0) {
                            counts.computeIfAbsent("db", key -> new LongAdder())
                                  .increment();
                        }
                    }
                }));
            }
            for (Future<?> job : jobs) job.get();
            Map<String, Long> snapshot = new TreeMap<>();
            counts.forEach((key, adder) -> snapshot.put(key, adder.sum()));
            System.out.println("frequency=" + snapshot);
            System.out.println("api=" + counts.get("api").sum());
            System.out.println("db=" + counts.get("db").sum());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 FrequencyMapDemo.java
java FrequencyMapDemo
~~~

Stdout:

~~~text
frequency={api=4000, db=2000}
api=4000
db=2000
~~~

**Phân tích:**

- Bốn worker, mỗi worker tăng api 1.000 lần: api = 4.000.
- Mỗi worker tăng db ở 500 chỉ số i chẵn: db = 2.000.
- computeIfAbsent cấp phát LongAdder cho key mới khi cần; các lần sau dùng object đó.
- Future.get đợi các worker hoàn tất **trước khi** tạo snapshot. Vì vậy sum không cạnh tranh với writer và cho kết quả xác định.
- TreeMap sắp xếp key để stdout không phụ thuộc thứ tự duyệt ConcurrentHashMap.
- Nếu exporter duyệt map **khi writers vẫn hoạt động**, kết quả chỉ là tổng quan sát, không phải một snapshot atomic của tất cả key.

### Histogram có phải chỉ thêm LongAdder là đủ?

Bạn có thể đếm số mẫu vào từng bucket histogram bằng LongAdder. Nhưng nếu hệ thống cập nhật nhiều bucket hoặc các metric liên quan trong nhiều thao tác, **không có transaction atomic đa-counter**. Để có ảnh chụp toàn bộ nhất quán phải thiết kế thời điểm quiescent hoặc giao thức snapshot phù hợp với exporter và người tiêu thụ dữ liệu.

## 13. sum() là một phép đọc, không phải một atomic snapshot

Đây là điểm dễ hiểu nhầm nhất của LongAdder:

- **Khi không có thread nào đang cập nhật** lúc sum chạy, sum trả kết quả tích lũy chính xác theo trạng thái hiện tại.
- **Khi các thread còn đang cập nhật**, JavaDoc không bảo đảm sum là **atomic snapshot**. Các update xảy ra trong quá trình tính sum có thể không được kết hợp vào kết quả.
- Nếu tổng trải trên nhiều thành phần, sum đọc từng thành phần, nên không có **một thời điểm duy nhất** tương ứng với toàn bộ phần được đọc.
- Không dùng sum để thay một thao tác atomic read-modify-write hoặc lấy một “điểm chốt” mà mọi update trước nó phải được đưa vào và mọi update sau nó phải bị loại trừ.

### Ví dụ tưởng tượng

~~~text
Ban đầu: cellA=10, cellB=20  -> tổng 30

Thread X: bắt đầu sum(), đọc cellA=10
Thread Y: tăng cellA thành 11
Thread Z: tăng cellB thành 21
Thread X: đọc cellB=21 -> sum trả 31

Trong khi đó tổng sau cả hai update là 32.
~~~

Đây là sơ đồ minh họa tính không-atomic, **không phải mô phỏng bố cục thực tế của JDK**. Chỉ cần hiểu sum không khóa mọi writer trong lúc nó đọc các thành phần.

Nếu chỉ dùng các update dương, sau khi toàn bộ worker đã hoàn tất và quiescent, tổng sẽ phản ánh các phép cập nhật (trừ bài toán overflow); nhưng đọc trong lúc đang có writer thì không thể coi là một điểm nhất quán. Với delta âm và dương xen kẽ, kết quả quan sát có thể biến động theo hướng khó dự đoán hơn.

### Từ “thread-safe” không có nghĩa “atomic getAndSet”

LongAdder là một class thread-safe để cộng dồn theo mục đích API. Tuy nhiên, **thread-safe update** không suy ra mọi phương thức đọc phải cung cấp linearizable snapshot, và không có nghĩa tổ hợp sum()+add() thành một thao tác atomic. Phải tách rõ hai hợp đồng:

1. **Cập nhật**: nhiều thread được phép gọi add/increment an toàn.
2. **Quan sát tổng**: sum cho giá trị tổng, nhưng khi cập nhật đồng thời có giới hạn snapshot.

Nếu nghiệp vụ đòi kết quả đúng tại một **ranh giới giao dịch** trong lúc writer hoạt động, cần thêm cơ chế đồng bộ toàn bộ pipeline cập nhật/snapshot, hoặc chọn state atomic khác.

### Tại sao ta không dùng Thread.sleep để kiểm thử sum đang cập nhật?

Với nhiều thread chạy tự do, kết quả sum trong một thời điểm cạnh tranh có thể khác nhau giữa hai lần chạy. Không nên đưa “sum=1234” làm stdout hứa hẹn cho một race chưa điều khiển; nó vừa giòn trên CI vừa dạy sai rằng đây là snapshot.

Để minh họa kết quả xác định, chương trình tiếp theo dùng CountDownLatch **tạm dừng writers giữa hai pha**, rồi đọc sum khi không có writer thực sự cập nhật.

## 14. Ví dụ đầy đủ 5 — điều khiển hai pha cập nhật và đọc tổng

Tạo file **PhaseSnapshotDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.LongAdder;

public class PhaseSnapshotDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        LongAdder count = new LongAdder();
        CountDownLatch firstPhase = new CountDownLatch(3);
        CountDownLatch resume = new CountDownLatch(1);
        try {
            List<Future<?>> jobs = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                jobs.add(pool.submit(() -> {
                    count.increment();
                    firstPhase.countDown();
                    resume.await();
                    count.increment();
                    return null;
                }));
            }
            firstPhase.await();
            System.out.println("pausedSum=" + count.sum());
            resume.countDown();
            for (Future<?> job : jobs) job.get();
            System.out.println("finalSum=" + count.sum());
        } finally {
            resume.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 PhaseSnapshotDemo.java
java PhaseSnapshotDemo
~~~

Stdout:

~~~text
pausedSum=3
finalSum=6
~~~

**Diễn giải kỹ:**

1. Ba worker mỗi người tăng count **một lần**, sau đó countDown firstPhase và chờ resume.
2. Main đợi firstPhase về 0, nghĩa là cả ba lần increment của pha đầu đã xảy ra trước khi main đọc; đồng thời các worker đang chờ release, không thực hiện increment pha thứ hai.
3. pausedSum = 3 được đọc khi các writer đang **tạm dừng**. Đây là thời điểm không có cập nhật đang chạy, chứ không phải minh chứng sum atomic dưới race.
4. Main release resume; mỗi worker tăng lần hai.
5. Main đợi tất cả Future.get, sau đó finalSum = 6.
6. finally release latch nếu xảy ra exception để tránh giữ worker chờ vô hạn.

**Trong sản phẩm thật:** Việc tạm dừng writer đồng loạt để đọc metric có thể không phù hợp hiệu năng. Nếu số liệu chỉ phục vụ dashboard, thường chấp nhận snapshot quan sát gần đúng khi update đang diễn ra. Nếu cần ranh giới chính xác, hãy thiết kế cơ chế chốt/giao tiếp giữa producer và consumer có semantics rõ ràng.

## 15. reset() và sumThenReset(): không dùng bừa khi writer đang hoạt động

LongAdder cung cấp:

~~~java
// Mảnh mã:
long snapshot = count.sumThenReset();
count.reset();
~~~

Trong một chuỗi thao tác single-thread hoặc khi bạn **biết chắc không có thread nào đang cập nhật**:

- sumThenReset trả tổng trước khi reset và đặt tổng mới về 0.
- reset chỉ đưa các thành phần về 0, không trả tổng cũ.
- Có thể tái sử dụng object giữa hai đợt tính toán.

Nhưng JavaDoc nói rõ: reset là **intrinsically racy**, chỉ hiệu quả khi không có cập nhật đồng thời; sumThenReset chỉ tương đương về hiệu ứng với sum theo sau reset, **không phải atomic getAndSet**.

### Vì sao concurrent sumThenReset có thể gây mất số liệu?

Giả sử một thread bắt đầu cộng vào thành phần A trong lúc thread exporter đọc A, B rồi reset. Một update nằm giữa việc đọc và xóa có thể bị xóa mà **chưa được đưa vào giá trị trả về**; hoặc tổng quan sát không tương ứng cửa sổ thời gian mà bạn định chốt. Khi update và reset chồng lấn, API **không đảm bảo** mọi update thuộc đúng một trong hai cửa sổ, dù mỗi update được thực thi bằng add() hợp lệ.

**Không nên dùng sumThenReset cho rate per second live** nếu yêu cầu phải có một ledger không mất/không đếm trùng sự kiện. Đối với telemetry best-effort, có thể chấp nhận dữ liệu tổng quan sát tùy yêu cầu; nhưng phải document rõ sai số và không coi đó là bộ đếm giao dịch.

### AtomicLong.getAndSet(0) khác gì?

AtomicLong có getAndSet(0) là một thao tác atomic trên một scalar. Nó có thể cung cấp ranh giới tuyến tính hóa cho giá trị đã tích lũy tại thời điểm swap, khi **chính mọi writer đều cập nhật vào AtomicLong đó** theo hợp đồng. LongAdder.sumThenReset không có cam kết tương đương trong khi writer đang chạy.

Đổi lại, AtomicLong có thể có contention cao hơn nếu nhiều thread tranh nhau tăng. Đây là trade-off về **semantics trước, hiệu năng sau**: nếu yêu cầu atomic window handoff, đừng thay nó bằng LongAdder chỉ để đẩy throughput.

### Khi hệ thống cần “mỗi event thuộc đúng một cửa sổ”

Các phương án có thể gồm:

- Đồng bộ hóa phase: tạm dừng nhận update, chờ tất cả writer hoàn tất, chốt tổng, reset rồi mở phase sau.
- Producer gắn epoch/window ID cho sự kiện và gửi tới queue; consumer của window cũ phải **drain** đủ trước khi chốt.
- Sử dụng một primitive atomic có semantics phù hợp nếu một scalar đủ để mô hình hóa.
- Tách các bộ tích lũy per worker/partition, chốt đồng bộ sau khi worker kết thúc và tổng hợp tại barrier.

**Đừng giả định việc thay AtomicReference<LongAdder> sang object mới đã an toàn tuyệt đối**. Writer có thể giữ tham chiếu adder cũ từ trước khi swap và cập nhật nó sau khi bạn chốt/loại bỏ, gây update rơi khỏi window. Nếu dùng rotation, phải có cơ chế kiểm soát **in-flight writers** và epoch ownership rõ ràng.

## 16. Ví dụ đầy đủ 6 — hai window có barrier quiescent

Tạo file **QuiescentWindowDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.LongAdder;

public class QuiescentWindowDemo {
    static void runPhase(ExecutorService pool, LongAdder adder,
                         int workers, int iterations) throws Exception {
        List<Future<?>> jobs = new ArrayList<>();
        for (int w = 0; w < workers; w++) {
            jobs.add(pool.submit(() -> {
                for (int i = 0; i < iterations; i++) adder.increment();
            }));
        }
        for (Future<?> job : jobs) job.get();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        LongAdder count = new LongAdder();
        try {
            runPhase(pool, count, 3, 1_000);
            long first = count.sumThenReset();
            System.out.println("phase1=" + first);
            System.out.println("afterFirstReset=" + count.sum());

            runPhase(pool, count, 2, 1_000);
            long second = count.sumThenReset();
            System.out.println("phase2=" + second);
            System.out.println("afterSecondReset=" + count.sum());
            System.out.println("total=" + (first + second));
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 QuiescentWindowDemo.java
java QuiescentWindowDemo
~~~

Stdout:

~~~text
phase1=3000
afterFirstReset=0
phase2=2000
afterSecondReset=0
total=5000
~~~

**Giải thích:**

- Pha 1 tạo ba task, mỗi task tăng 1.000 lần. runPhase chỉ trả khi các Future đã hoàn tất, nên không còn writer của pha đó.
- Main gọi sumThenReset khi không có writer: 3.000 là kết quả chính xác của pha 1.
- Pha 2 bắt đầu **sau** khi reset pha 1 đã xong; hai task tăng 1.000 lần, cho 2.000.
- Tổng hai pha = 5.000, không thất lạc cập nhật.
- **Quan trọng:** Ví dụ là hai pha **không chồng lấn** có barrier do code chủ động tạo. Nó không chứng minh sumThenReset an toàn với cập nhật concurrent ở production.

## 17. Dùng sum() đọc thường xuyên có phá hỏng throughput không?

LongAdder tối ưu cho tỷ lệ **rất nhiều update so với số lần đọc tổng**. Nhưng sum() vẫn phải kết hợp các thành phần nội bộ; khi contention cao, tập thành phần có thể mở rộng và việc đọc tốn thêm công.

Nếu đọc sum() ngay **sau mỗi increment()** trong mọi thread, bạn có thể:

1. Tăng chi phí đọc quá nhiều, làm giảm lợi ích phân tán writer.
2. Vẫn không có một atomic value của riêng lần increment đó.
3. Tạo code ngầm đòi linearizable sequence mặc dù API không cung cấp.
4. Làm giảm throughput khi tổng nhiều thành phần.

Nếu mỗi update cần trả giá trị mới cho caller, **AtomicLong.addAndGet/incrementAndGet** là API phù hợp hơn. Nếu chỉ cần thống kê định kỳ, hãy tách đường update và đường export.

### Số lượng writer không phải yếu tố duy nhất

Một LongAdder không có nhiều contention nếu mỗi thread cập nhật **key khác nhau**; map với nhiều hot key cũng có dạng tải khác với một adder chung. Kỳ vọng hiệu năng còn phụ thuộc:

- Độ dài và tần suất update.
- Số core vật lý và số thread đang chạy thật.
- Tần suất sum/đọc.
- Sự phân bố keys trong frequency map.
- Giới hạn cache/bộ nhớ/GC.
- Runtime JDK/OS và chính sách thread scheduling.

Đừng lấy một phép đo một lần trên laptop làm bằng chứng cho production.

## 18. Counter, gauge và metric types

Cần phân biệt **ý nghĩa số liệu** với kiểu dữ liệu:

- **Counter tích lũy:** tăng theo số event. LongAdder phù hợp để đếm request, lỗi, số lần truy cập, nếu không cần atomic snapshot.
- **Gauge có thể tăng/giảm:** LongAdder.add(delta âm/dương) có thể cho giá trị quan sát; nhưng nếu gauge dùng cho kiểm soát ràng buộc, sum không đủ.
- **Tổng trọng số double:** DoubleAdder có thể phù hợp nếu số đo được chấp nhận sai số floating-point.
- **Histogram:** Map<bucket,LongAdder> đếm số mẫu trong bucket; phải kiểm soát cardinality.
- **Số sequence/ID:** cần giá trị riêng cho mỗi phép tăng, thường dùng AtomicLong hoặc hệ cấp phát ID phân tán phù hợp.
- **Số tiền/ledger:** yêu cầu chính xác, audit và chốt transaction; không chỉ dùng DoubleAdder.

Những tên như requestsTotal, activeSessions hoặc sumLatencySeconds nên mô tả rõ đơn vị và semantics. Đừng chỉ đổi kiểu từ AtomicLong sang LongAdder mà không kiểm tra cách downstream dùng số liệu; một đoạn code đang dựa trên compareAndSet hay atomic read-after-write có thể không còn đúng.

## 19. Khi nào dùng AtomicLong và khi nào dùng LongAccumulator?

LongAdder không thay AtomicLong trong mọi trường hợp; cũng không phải cách tích lũy tùy ý cho mọi phép toán.

### AtomicLong: một scalar với phép cập nhật atomic

Nếu bạn cần **phát số thứ tự**, atomic increment có thể trả về số ngay trong thao tác:

~~~java
// Mảnh mã, cần import java.util.concurrent.atomic.AtomicLong.
AtomicLong id = new AtomicLong(100);
long nextId = id.incrementAndGet(); // 101
~~~

Nếu cần một điều kiện atomic:

~~~java
// Mảnh mã minh họa: thay đổi nếu current = 5.
boolean changed = id.compareAndSet(5, 6);
~~~

LongAdder **không cung cấp** thao tác tương đương có linearization point cho toàn bộ tổng. Viết if (adder.sum() == 5) adder.add(1) không phải compareAndSet.

### LongAccumulator: biến thể tổng quát hóa phép tích lũy

Khi cần **giá trị lớn nhất** thay vì tổng, dùng LongAccumulator với phép toán phù hợp:

~~~java
// Mảnh mã:
LongAccumulator maximum =
        new LongAccumulator(Long::max, Long.MIN_VALUE);
maximum.accumulate(-3);
maximum.accumulate(12);
maximum.accumulate(7);
long result = maximum.get(); // 12
~~~

LongAccumulator có thể phân tán contention cho một phép tích lũy; nhưng function được cung cấp phải **không có side effects**, và để có kết quả dự đoán được khi thứ tự khác nhau nên **associative và commutative**. Function có thể được áp dụng lại khi update tranh chấp. Với phép cộng thông thường, LongAdder là lựa chọn chuyên biệt tiện lợi; với max/min hoặc phép gộp có identity phù hợp, LongAccumulator đáng xem xét.

Tương tự, **DoubleAccumulator** dùng phép tích lũy double tổng quát. Các vấn đề floating-point associativity, thứ tự, numerical stability và atomic snapshot vẫn phải được cân nhắc.

### Phân biệt loại kết quả

| Nhu cầu | API phù hợp |
|---|---|
| Một dãy số atomic, mỗi thread nhận số mới | AtomicLong.incrementAndGet |
| Atomic kiểm tra-và-thay đổi | AtomicLong.compareAndSet |
| Đếm event write-heavy, đọc định kỳ | LongAdder.increment |
| Tổng integer có delta có dấu | LongAdder.add |
| Tổng số đo floating-point, chấp nhận precision double | DoubleAdder.add |
| Giá trị max/min dưới contention cao | LongAccumulator hoặc DoubleAccumulator với function đúng |
| Bộ đếm window cần atomic handoff | AtomicLong.getAndSet hoặc giao thức barrier/queue đúng |
| Tổng doanh thu yêu cầu decimal exact | BigDecimal hoặc số nguyên đơn vị nhỏ nhất, cộng với đồng bộ phù hợp |

**Không thay AtomicLong bằng LongAdder chỉ vì benchmark increment nhanh hơn.** Đầu tiên xác nhận bài toán chỉ cần tổng, không cần atomic read-modify-write.

## 20. Ví dụ đầy đủ 7 — sequence, CAS, metrics và LongAccumulator

Tạo file **AtomicVsAdderDemo.java**:

~~~java
import java.util.concurrent.atomic.*;

public class AtomicVsAdderDemo {
    public static void main(String[] args) {
        AtomicLong sequence = new AtomicLong(40);
        LongAdder metrics = new LongAdder();
        metrics.add(40);
        System.out.println("allocated=" + sequence.incrementAndGet());
        System.out.println("old=" + sequence.getAndIncrement());
        System.out.println("current=" + sequence.get());
        System.out.println("cas=" + sequence.compareAndSet(42, 100));
        System.out.println("atomicNow=" + sequence.get());
        metrics.increment();
        System.out.println("metricTotal=" + metrics.sum());
        LongAccumulator maximum = new LongAccumulator(Long::max, Long.MIN_VALUE);
        maximum.accumulate(-3);
        maximum.accumulate(12);
        maximum.accumulate(7);
        System.out.println("max=" + maximum.get());
    }
}
~~~

Chạy:

~~~text
javac --release 17 AtomicVsAdderDemo.java
java AtomicVsAdderDemo
~~~

Stdout:

~~~text
allocated=41
old=41
current=42
cas=true
atomicNow=100
metricTotal=41
max=12
~~~

**Phân tích:**

1. AtomicLong bắt đầu ở 40. incrementAndGet tăng lên 41 và **trả 41** cho caller.
2. getAndIncrement trả số cũ 41, sau đó current thành 42.
3. compareAndSet(42,100) thành công, đặt giá trị mới thành 100 một cách atomic.
4. LongAdder bắt đầu ở 0, add(40), increment thành 41 nhưng **không có phương thức trả 41 ngay trong phép tăng**. sum lúc không có writer cho 41, không thay được atomic sequence allocator.
5. LongAccumulator sử dụng Long::max và identity Long.MIN_VALUE, thu được giá trị tối đa 12.
6. Demo chạy một thread để stdout xác định; điểm chính là **khác biệt về API và hợp đồng**, không phải hiệu năng của một loại khi không tranh chấp.

## 21. Benchmark đúng cách: LongAdder có nhanh hơn bao nhiêu?

Không đưa số throughput cố định kiểu “LongAdder nhanh gấp X lần” vì không có giá trị phổ quát. JavaDoc nói rằng **khi contention thấp, LongAdder và AtomicLong có thể tương tự**; khi contention cao, throughput kỳ vọng của LongAdder có thể lớn hơn đáng kể, nhưng cần nhiều bộ nhớ hơn.

Để đánh giá có ý nghĩa, dùng một harness benchmark Java được bảo trì như **JMH** và thiết kế các biến thể tương ứng. Đây là hướng dẫn thử nghiệm, không phải mã chạy đầy đủ trong bài:

- So sánh cùng loại công việc: tăng đúng một counter, không trộn I/O, logging hoặc truy cập DB.
- Thử số worker khác nhau: 1, 2, 4, 8, 16... theo số core và môi trường.
- Thử tỷ lệ read/write khác nhau: chỉ increment, rồi có một exporter sum định kỳ, rồi read-heavy.
- Xét một hot key và nhiều key phân tán trong frequency map.
- Có warmup đủ để JIT ổn định, đo đủ iteration/fork để giảm nhiễu.
- Tránh dead-code elimination: benchmark phải tiêu thụ hoặc publish kết quả đúng theo JMH.
- Kiểm tra correctness bằng tổng kỳ vọng **sau khi mọi worker hoàn tất**, tách riêng bài benchmark throughput.
- Quan sát allocation, memory footprint, garbage collection và cache contention.
- Không chạy AtomicLong và LongAdder trong cùng một vòng lặp rồi dùng thời gian tổng để suy ra riêng tốc độ của từng loại.
- Không dùng System.currentTimeMillis để đo một vài phép tăng nanosecond; chọn benchmark harness thích hợp.

**Kết luận benchmark phải nói rõ workload.** Một API tối ưu cho nhiều writer, ít reader không nhất thiết phù hợp với workload đọc tổng sau mỗi lần ghi. Việc nhiều cells cải thiện contention có thể làm sum() chậm hơn do kết hợp các thành phần.

## 22. Memory footprint và object lifecycle

LongAdder không tạo một object mới cho mỗi increment. Nó duy trì state nội bộ và có thể mở rộng số thành phần khi tranh chấp tăng, vì vậy không nên lo mỗi lần tăng đều cấp phát object; nhưng cũng không được khẳng định footprint luôn như một long đơn.

Các lưu ý trong sản xuất:

1. **Tái sử dụng counter** cho một metric/key ổn định; không tạo new LongAdder mỗi lần ghi.
2. **Tránh cardinality bùng nổ** nếu có Map<String,LongAdder>.
3. Không expose trực tiếp reference LongAdder cho code không đáng tin cậy có thể gọi reset hoặc add(-delta).
4. Cần lifecycle khi xóa metric/tenant/key; writer đang giữ reference cũ có thể vẫn cập nhật nó sau khi map thay đổi.
5. Nếu cần export snapshot định kỳ, việc tạo DTO giữ **giá trị long/double** có thể giúp tách các consumer khỏi bộ cộng mutable.
6. Đừng dùng adder mutable như key mà kỳ vọng equals/hashCode so nội dung số; theo JavaDoc chúng không định nghĩa value-based comparison.
7. Khi serialization hoặc lưu trữ cần nhất quán, hãy lưu **giá trị đã chốt tại điểm không cập nhật**, chứ không mặc định việc serialize object đang hot là một atomic snapshot toàn hệ thống.

## 23. Các lỗi phổ biến cần tránh

### 23.1. Dùng count++ trên biến chung

count++ không atomic và có thể mất update; volatile không tự sửa được read-modify-write.

### 23.2. Cho rằng LongAdder luôn hơn AtomicLong

Không. LongAdder tối ưu under contention, nhiều updates/ít reads, đánh đổi bộ nhớ và chi phí sum. Khi cần CAS hoặc số sequence, AtomicLong đúng hơn.

### 23.3. Dùng sum() để cấp ID hoặc giới hạn tài nguyên

sum không atomic snapshot trong lúc writer cập nhật; tổ hợp sum + add không atomic. Dùng AtomicLong/CAS hoặc Semaphore khi cần tính đúng.

### 23.4. Coi sum() là giá trị cuối cùng dù writer còn chạy

Một update xảy ra trong lúc sum có thể không được tính. Chờ writer hoàn tất hoặc dùng cơ chế đồng bộ ranh giới khi cần kết quả chính xác.

### 23.5. Gọi sumThenReset mỗi giây trong khi producer đang add, rồi coi đó là tổng exact window

sumThenReset không atomic với cập nhật đồng thời; update có thể thuộc sai window hoặc bị bỏ khi reset. Nếu exactness quan trọng, phải có phase barrier/queue draining hoặc atomic handoff với primitive phù hợp.

### 23.6. Nghĩ reset() là atomic exchange

reset không trả số cũ và không có cam kết atomic dưới concurrent updates. Đừng dùng nó để chuyển cửa sổ thống kê mà chưa dừng writers.

### 23.7. Tự hoán đổi AtomicReference<LongAdder> mà không xử lý in-flight update

Writer đã lấy adder cũ có thể tăng sau khi chốt. Cần epoch handoff/quiescence, không chỉ thay reference.

### 23.8. Dùng DoubleAdder cho số tiền chính xác

double bị làm tròn nhị phân và thứ tự cộng không bảo đảm. Cần số thập phân chính xác + giao thức đồng bộ/audit phù hợp.

### 23.9. So sánh double concurrent bằng dấu == với kết quả tuần tự

Thứ tự cộng floating-point ảnh hưởng precision. Dùng tolerance có ý nghĩa hoặc thuật toán tổng hợp xác định khi cần.

### 23.10. Cho rằng DoubleAdder có increment()/decrement()

DoubleAdder có add(double), sum, reset, sumThenReset; dùng add(1.0) hoặc add(-1.0).

### 23.11. Giả định mọi sample đều hữu hạn

NaN/Infinity có thể làm kết quả thống kê vô nghĩa; validate dữ liệu vào trước khi add nếu domain yêu cầu.

### 23.12. Đọc sum sau mỗi increment để lấy số mới

LongAdder.increment trả void và sum không phải atomic return cho chính lần tăng. Việc đọc quá thường xuyên còn làm giảm lợi ích throughput update.

### 23.13. Không chờ các worker xong trước khi assert số cuối

Test concurrency không được dựa vào Thread.sleep. Dùng Future.get, CountDownLatch hoặc một điểm đồng bộ xác định.

### 23.14. Xem ConcurrentHashMap + LongAdder là một transaction xuyên nhiều keys

Map và adder thread-safe, nhưng snapshot tất cả key không atomic. Exporter có thể thấy các key ở các thời điểm khác nhau.

### 23.15. Remove key khi writer đang dùng adder của key đó

Worker có thể increment trên object cũ không còn trong map. Định nghĩa lifecycle và chính sách map update/eviction an toàn.

### 23.16. Không kiểm soát số key trong metrics

Một key cho từng user ID/path ID gây tiêu tốn bộ nhớ rất lớn. Chuẩn hóa và giới hạn nhãn để tránh high-cardinality.

### 23.17. Giả định LongAdder tự phát hiện overflow

LongAdder duy trì long, không tự chuyển thành BigInteger. Với miền lớn, xác định quy tắc overflow và biên dữ liệu.

### 23.18. Dùng LongAccumulator với function có side effects

Function có thể bị áp dụng lại, thứ tự không bảo đảm. Chọn hàm thuần, associative, commutative cho kết quả dự đoán được.

### 23.19. Quên rằng LongAdder là mutable khi chia sẻ

Có thể an toàn cho cập nhật đồng thời theo contract nhưng không có nghĩa code tùy ý được quyền reset hoặc sửa tổng. Bảo vệ reference hoặc expose chỉ một interface ghi/đọc được kiểm soát.

### 23.20. Đo một lần và kết luận kiến trúc

Độ dài task, JIT, core count, GC, tỷ lệ đọc/ghi và môi trường ảnh hưởng hiệu năng; đo đúng workload bằng JMH trước khi ra quyết định.

## 24. Checklist trước khi sử dụng trong production

1. Giá trị cần là **metric/tổng** hay **atomic state dùng để ra quyết định**?
2. Có nhiều writer cùng tranh chấp một key/counter không?
3. Tỷ lệ cập nhật và đọc tổng là bao nhiêu?
4. Có cần giá trị ngay sau từng increment cho caller không?
5. Có cần compareAndSet hoặc getAndSet atomic không?
6. Có chấp nhận sum không atomic khi writer đang chạy không?
7. Nếu cần chốt số liệu exact, đã có barrier, epoch ownership hoặc primitive đúng chưa?
8. Nếu gọi reset/sumThenReset, đã chắc chắn không có update đồng thời chưa?
9. Với DoubleAdder, đã xem xét floating-point stability, thứ tự và NaN/Infinity chưa?
10. Dữ liệu monetary đã tránh dùng double nếu cần decimal exact chưa?
11. Frequency map có dùng ConcurrentHashMap và computeIfAbsent đúng không?
12. Map có thay/xóa key đồng thời; nếu có đã xử lý writer giữ reference cũ chưa?
13. Có giới hạn cardinality label, tránh key không kiểm soát chưa?
14. Đã kiểm thử final sum sau khi workers hoàn tất bằng Future.get/barrier chưa?
15. Đã benchmark trên workload mục tiêu và quan sát memory/read cost chưa?
16. Lifecycle của executor và metric registry có rõ ràng chưa?
17. Đã phân biệt counter, gauge, histogram, sequence và ledger theo semantics chưa?

## 25. Bài tập tự kiểm tra

**Câu 1.** Vì sao count++ trên long chung không an toàn?

*Đáp án:* Nó là read-modify-write không atomic; hai thread có thể ghi cùng kết quả và mất một update.

**Câu 2.** LongAdder giải quyết contention như thế nào?

*Đáp án:* Nó có thể mở rộng các thành phần tích lũy khi tranh chấp tăng để không buộc mọi writer cùng cập nhật một vị trí; sum kết hợp các thành phần.

**Câu 3.** LongAdder.increment() trả giá trị mới như AtomicLong.incrementAndGet() không?

*Đáp án:* Không. increment() trả void; không có atomic return-value tương đương.

**Câu 4.** sum() có atomic snapshot trong lúc writer đang add không?

*Đáp án:* Không. JavaDoc không bảo đảm; update đồng thời có thể không được tính vào kết quả.

**Câu 5.** Khi nào sumThenReset() phù hợp?

*Đáp án:* Khi hệ thống đã có điểm quiescent và biết chắc không có writer nào đồng thời cập nhật; ví dụ sau khi Future.get chờ toàn bộ task của một phase.

**Câu 6.** Có thể dùng LongAdder để giới hạn tối đa 100 active users không?

*Đáp án:* Không nên dùng sum + increment như điều kiện atomic; hãy dùng Semaphore hoặc primitive atomic/CAS đúng.

**Câu 7.** DoubleAdder có bảo đảm tổng thập phân 0.1+0.2 bằng chính xác 0.3 không?

*Đáp án:* Không. double có sai số biểu diễn nhị phân; cần BigDecimal hoặc mô hình số chính xác hơn nếu nghiệp vụ đòi.

**Câu 8.** Vì sao DoubleAdder concurrent có thể khác phép cộng tuần tự cố định?

*Đáp án:* Do floating-point không associative tuyệt đối và thứ tự cộng trong/các thành phần không được bảo đảm.

**Câu 9.** Tạo map đếm tần suất theo key thế nào?

*Đáp án:* ConcurrentHashMap<K,LongAdder> và computeIfAbsent(key, ...).increment(), với lifecycle map/key được quản lý.

**Câu 10.** Có được xóa một key khỏi frequency map trong lúc writer đã giữ reference tới adder không?

*Đáp án:* Cần phối hợp. Nếu xóa/replace mà writer vẫn tăng object cũ, map hiện tại có thể không ghi nhận update.

**Câu 11.** AtomicLong.getAndSet(0) khác LongAdder.sumThenReset() ở đâu?

*Đáp án:* getAndSet là atomic exchange của một scalar; sumThenReset không atomic với concurrent writer.

**Câu 12.** LongAccumulator phù hợp cho phép toán nào ngoài cộng?

*Đáp án:* Ví dụ Long::max với identity Long.MIN_VALUE, miễn function thuần và thỏa yêu cầu kết hợp/trật tự phù hợp.

**Câu 13.** Có cần đo tốc độ của LongAdder không?

*Đáp án:* Có nếu mục tiêu là hiệu năng. Dùng JMH, nhiều worker, tỷ lệ read/write và môi trường thực tế thay vì một phép đo đơn lẻ.

**Câu 14.** Khi nào sum trả kết quả cuối cùng đáng tin?

*Đáp án:* Khi writer đã hoàn tất/không có cập nhật đồng thời trong lúc sum; nếu không có overflow và logic input đúng thì tổng phản ánh các update đã thực hiện.

**Câu 15.** Khi nào không nên dùng DoubleAdder cho telemetry?

*Đáp án:* Khi yêu cầu precision/determinism rất cao, dữ liệu có NaN/Infinity chưa được kiểm soát hoặc order-of-magnitude khác nhau gây sai số quá lớn.

**Câu 16.** Có nên đặt LongAdder làm key của HashMap không?

*Đáp án:* Không phù hợp làm khóa theo giá trị tổng; LongAdder mutable và không định nghĩa equals/hashCode dựa trên sum.

**Câu 17.** Vì sao quiescent window không giống live window?

*Đáp án:* Quiescent window chờ mọi writer xong trước khi sumThenReset; live window reset khi writer còn add sẽ không có bảo đảm phân chia cập nhật chính xác.

**Câu 18.** Cần làm gì với bộ đếm metrics có hàng triệu key?

*Đáp án:* Thiết kế label/cardinality giới hạn, lifecycle/eviction an toàn và chính sách aggregation phù hợp.

## 26. Tài liệu chính thức còn được duy trì

- Oracle Java SE 25 — **LongAdder**, thiết kế giảm contention và hợp đồng sum/reset: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- Oracle Java SE 25 — **DoubleAdder**, thứ tự cộng và numerical stability: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/DoubleAdder.html
- Oracle Java SE 25 — **AtomicLong**, incrementAndGet, compareAndSet, getAndSet: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html
- Oracle Java SE 25 — **LongAccumulator**, function tùy biến: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/LongAccumulator.html
- Oracle Java SE 25 — **DoubleAccumulator**, accumulator cho double: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/DoubleAccumulator.html
- Oracle Java SE 25 — **ConcurrentHashMap**, ví dụ frequency map: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- Oracle Java SE 25 — **CountDownLatch**, điểm chờ xác định: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Oracle Java SE 25 — **Future**, Future.get dùng để chờ tác vụ: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html
- OpenJDK Java Microbenchmark Harness — JMH: https://github.com/openjdk/jmh

**Kết luận:** LongAdder và DoubleAdder được thiết kế để giảm tranh chấp khi nhiều thread cập nhật một tổng, đặc biệt với workload nhiều write, ít read. Sự đánh đổi là chi phí bộ nhớ và việc **sum không phải atomic snapshot dưới concurrent updates**. reset/sumThenReset chỉ nên chốt tại điểm không có writer nếu kết quả phải chính xác. AtomicLong dùng cho ID/CAS/atomic exchange; DoubleAdder không thay được số học decimal chính xác. Hãy chọn theo semantics nghiệp vụ, đo trên workload thật và kiểm thử với ranh giới concurrency được xác định rõ.