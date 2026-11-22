# LongAdder và LongAccumulator khi cập nhật cạnh tranh trong Java

Khi hàng chục hoặc hàng trăm thread liên tục cộng vào **một bộ đếm dùng chung**, mỗi lần cập nhật cùng một biến nguyên tử có thể tranh chấp. Trong Java, `AtomicLong` cung cấp các phép đọc–sửa–ghi nguyên tử rất phù hợp nếu ta cần **một giá trị có thể đọc ngay tại từng thời điểm** và các thao tác như `getAndIncrement()`. Nhưng với các số liệu **thống kê được cộng dồn liên tục** (lượt truy cập, số sự kiện, số byte), việc mọi thread cùng tranh một điểm cập nhật có thể trở thành nút nghẽn.

`LongAdder` và `LongAccumulator` trong package `java.util.concurrent.atomic` là hai công cụ chuyên dụng của JDK: thay vì bắt mọi cập nhật tranh chấp trên một ô lưu trữ duy nhất, implementation có thể **phân tán cập nhật qua nhiều ô nội bộ**, rồi gộp lại khi cần đọc. Chúng thường cải thiện throughput dưới cạnh tranh cao, đổi lại **chi phí bộ nhớ lớn hơn và phép đọc tổng không phải snapshot nguyên tử**.

Bài này thuộc **Atomic & CAS**, tập trung vào **Java concurrency nói chung, Java 17+**. Không sử dụng tính năng đồng thời riêng của Spring.

Mục tiêu:
- Phân biệt chính xác `AtomicLong`, `LongAdder` và `LongAccumulator` theo semantics chứ không chỉ tốc độ.
- Dùng `LongAdder.increment()`, `add()`, `sum()`, `reset()`, `sumThenReset()` đúng ngữ cảnh.
- Thiết kế hàm và identity cho `LongAccumulator`; hiểu vì sao **associative, commutative, side-effect-free** là điều kiện quan trọng.
- Giải thích tại sao đọc một tổng hoặc reset trong lúc cập nhật **không cho kết quả snapshot/ranh giới thời gian chính xác**.
- Chọn công cụ cho metrics, đếm theo key, phép max/min, và nhận ra khi nào cần một cập nhật tuyến tính hóa của `AtomicLong` hay khóa.

## 1. Vấn đề: một điểm cập nhật chung dưới contention

Giả sử nhiều thread cùng tăng số sự kiện đã xử lý:

~~~java
// Minh họa logic, chưa phải file chạy độc lập.
private final AtomicLong events = new AtomicLong();

void onEvent() {
    events.incrementAndGet();
}
~~~

`AtomicLong.incrementAndGet()` đảm bảo mỗi lần tăng là một phép **read–modify–write nguyên tử** trên cùng một giá trị. Đó là ưu điểm lớn: nếu caller cần **giá trị mới của chính lần tăng**, API trả về ngay con số ấy. Tuy nhiên, khi có nhiều thread liên tục cập nhật cùng một điểm, việc đồng bộ cạnh tranh quanh giá trị này có thể làm tăng số lần retry/chi phí cache-coherence trên phần cứng.

Thường ta có hai nhóm nhu cầu khác nhau:

1. **Trạng thái điều khiển / quyết định chính xác:** cấp số thứ tự duy nhất, kiểm tra giới hạn rồi tăng, thay đổi trạng thái theo một giao thức. Cần atomicity của **một thời điểm cập nhật**; `AtomicLong` hoặc một primitive/khóa phù hợp.
2. **Số liệu thống kê:** mỗi thread chỉ muốn thông báo “thêm 1”, “thêm 64 byte” hoặc “cập nhật max”. Caller không cần biết số mới sau từng lần cập nhật; một giá trị đọc trong khi các thread vẫn ghi có thể là **số đo nhất thời**. `LongAdder`/`LongAccumulator` thích hợp để cân nhắc.

**Không phải cứ có nhiều thread thì LongAdder luôn nhanh hơn AtomicLong.** Trong tranh chấp thấp, khác biệt có thể nhỏ; với workload ít ghi, đọc rất nhiều hoặc cần bộ nhớ nhỏ, `AtomicLong` có thể phù hợp hơn. Hãy chọn theo **đúng semantics trước**, rồi benchmark thực tế.

## 2. LongAdder: cộng dồn long với nhiều thread

`java.util.concurrent.atomic.LongAdder` duy trì một tổng kiểu `long`, khởi đầu từ **0**. Những phương thức chính:

| Phương thức | Ý nghĩa | Trả về |
| --- | --- | --- |
| `add(long x)` | Cộng `x` (được phép âm) | `void` |
| `increment()` | Tương đương `add(1)` | `void` |
| `decrement()` | Tương đương `add(-1)` | `void` |
| `sum()` | Cộng các giá trị nội bộ để trả tổng hiện quan sát được | `long` |
| `longValue()` | Tương đương `sum()` | `long` |
| `reset()` | Đặt các ô nội bộ về 0 | `void` |
| `sumThenReset()` | Lấy tổng và reset, hữu ích giữa các giai đoạn khi đã hết writer | `long` |

Mỗi `add`/`increment` đóng góp vào tổng được duy trì bằng cơ chế đồng thời của class. Dưới contention, implementation có thể phân tán cập nhật qua một **base** và các **cell** (ô phụ). Khi đọc `sum()`, nó tổng hợp các thành phần này.

~~~text
Mô hình ý tưởng (không phải layout cố định của mọi JVM):

             LongAdder
       +--------------------+
       | base: một phần tổng |
       | cells khi cần:      |
       |  cell[0]: +8        |
       |  cell[1]: +6        |
       |  cell[2]: +9        |
       +--------------------+
             |
             v
       sum() -> tổng hợp

Các thread có thể cập nhật những cell khác nhau để giảm tranh chấp.
~~~

Một thread cụ thể **không được API bảo đảm gắn mãi với một cell**, số lượng cell không phải thông số API cố định, và số cell có thể tăng khi tranh chấp. Đây là giải thích thiết kế, không phải lời hứa về representation/hashing bên trong mọi phiên bản JDK.

### 2.1. Ví dụ Java 17+: bốn thread cập nhật 40.000 lần

~~~java
// LongAdderContentionDemo.java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.LongAdder;

public class LongAdderContentionDemo {
    public static void main(String[] args) throws InterruptedException {
        int workers = 4;
        int perWorker = 10_000;

        LongAdder total = new LongAdder();
        CountDownLatch begin = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(workers);

        for (int i = 0; i < workers; i++) {
            Thread t = new Thread(() -> {
                try {
                    begin.await();
                    for (int n = 0; n < perWorker; n++) {
                        total.increment();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    done.countDown();
                }
            });
            t.start();
        }

        begin.countDown();
        done.await();
        System.out.println("Total: " + total.sum());
    }
}
~~~

~~~bash
javac LongAdderContentionDemo.java
java LongAdderContentionDemo
~~~

Trong lần chạy bình thường, không có interrupt bất ngờ, stdout:

~~~text
Total: 40000
~~~

**Giải thích:** Bốn worker mỗi worker đóng góp 10.000. Main chỉ gọi `sum()` **sau** khi `done.await()` đã xác nhận cả bốn task hoàn tất. Các hành động trước `countDown()` được công bố theo memory-consistency của `CountDownLatch`; không còn cập nhật đồng thời khi main tính tổng. Vì vậy `sum()` cho kết quả chính xác trong ví dụ này.

Nếu main gọi `total.sum()` **trong lúc worker còn cập nhật**, nó chỉ nhận một giá trị nhất thời, **không phải snapshot nguyên tử**.

### 2.2. Tăng, giảm, cộng lượng âm

~~~java
// LongAdderOperationsDemo.java
import java.util.concurrent.atomic.LongAdder;

public class LongAdderOperationsDemo {
    public static void main(String[] args) {
        LongAdder value = new LongAdder();

        value.add(10);
        value.increment();
        value.decrement();
        value.add(-3);
        System.out.println("Sum: " + value.sum());

        long finished = value.sumThenReset();
        System.out.println("Finished: " + finished);
        System.out.println("After reset: " + value.sum());
    }
}
~~~

~~~bash
javac LongAdderOperationsDemo.java
java LongAdderOperationsDemo
~~~

Stdout:

~~~text
Sum: 7
Finished: 7
After reset: 0
~~~

`sumThenReset()` được gọi lúc **không có writer**, nên không gây tranh chấp với reset; vì thế các con số trên xác định. `LongAdder` không giới hạn ở phép tăng dương; `add(-3)` hợp lệ. Tuy nhiên, một cặp `sum()` rồi `add(-amount)` không tự tạo giao dịch nghiệp vụ “kiểm tra hạn mức rồi trừ”, vì `sum` không phải điểm đồng bộ cho invariant đó.

## 3. LongAccumulator: tích lũy theo phép toán tự chọn

`java.util.concurrent.atomic.LongAccumulator` tổng hợp giá trị `long` bằng một phép toán do caller cung cấp:

~~~java
new LongAccumulator(accumulatorFunction, identity);
~~~

- `accumulatorFunction` là `java.util.function.LongBinaryOperator`, có signature `long applyAsLong(long left, long right)`.
- `identity` là phần tử đơn vị của phép toán, tức một giá trị e thỏa mãn `f(e, x) = x` (và nên thỏa `f(x, e) = x` cho quy tắc kết hợp đối xứng).
- `accumulate(x)` đưa một quan sát x vào bộ tích lũy.
- `get()` (hoặc `longValue()`) trả kết quả tổng hợp các phần lưu nội bộ.
- `reset()` trở về identity; `getThenReset()` đọc rồi reset, nhưng không phải một phép chốt kỳ nguyên tử đối với concurrent updates.

Vì không có thứ tự tích lũy được bảo đảm giữa các thread, phép toán **phải phù hợp với việc gộp lại theo những thứ tự và nhóm khác nhau**. Theo tài liệu JDK, để có kết quả có thể dự đoán, operator nên **associative, commutative và side-effect-free**.

| Phép tích lũy | Operator | Identity phù hợp | Diễn giải |
| --- | --- | --- | --- |
| Tổng | `Long::sum` | `0L` | Tổng các lượng cập nhật |
| Cực đại | `Long::max` | `Long.MIN_VALUE` | Giá trị lớn nhất quan sát được |
| Cực tiểu | `Long::min` | `Long.MAX_VALUE` | Giá trị nhỏ nhất quan sát được |
| Phép OR từng bit | `(a, b) -> a \| b` | `0L` | Hợp nhất bit flags |
| Phép XOR từng bit | `(a, b) -> a ^ b` | `0L` | XOR các giá trị |
| Trừ dần | `(a, b) -> a - b` | Không thích hợp cho kiểu tổng hợp này | Không associative/commutative |
| Trung bình cập nhật `(a+b)/2` | Không thích hợp | Không đáp ứng tính kết hợp | Phụ thuộc thứ tự và làm tròn |

**Cảnh báo với identity cực đại:** Nếu dùng `Long::max` nhưng cho identity `0L`, một tập quan sát chỉ chứa số âm (ví dụ -12, -4, -7) sẽ cho kết quả **0**, sai. Phải chọn `Long.MIN_VALUE` để mọi `long` đều hợp lệ. Ngược lại, `Long::min` nên chọn `Long.MAX_VALUE`.

### 3.1. Ví dụ Java 17+: tìm cực đại của các giá trị âm

~~~java
// LongAccumulatorMaxDemo.java
import java.util.concurrent.atomic.LongAccumulator;

public class LongAccumulatorMaxDemo {
    public static void main(String[] args) throws InterruptedException {
        LongAccumulator maximum =
            new LongAccumulator(Long::max, Long.MIN_VALUE);

        Thread a = new Thread(() -> {
            maximum.accumulate(-9);
            maximum.accumulate(-4);
        });
        Thread b = new Thread(() -> {
            maximum.accumulate(-12);
            maximum.accumulate(-7);
        });
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Maximum: " + maximum.get());
        System.out.println("Saved: " + maximum.getThenReset());
        System.out.println("After reset: " + maximum.get());
    }
}
~~~

~~~bash
javac LongAccumulatorMaxDemo.java
java LongAccumulatorMaxDemo
~~~

Stdout:

~~~text
Maximum: -4
Saved: -4
After reset: -9223372036854775808
~~~

Vì `Long::max` **associative/commutative**, kết quả không phụ thuộc thread nào cập nhật trước. Sau `join()` không còn writer, nên `getThenReset()` trả đúng -4 và `get()` sau reset trở về identity `Long.MIN_VALUE`, không phải 0.

**Cần phân biệt giá trị rỗng:** Với max dùng `Long.MIN_VALUE`, nếu chưa có mẫu nào, `get()` cũng trả `Long.MIN_VALUE`. Nếu hệ thống cần phân biệt “chưa quan sát” với “đã quan sát chính Long.MIN_VALUE”, phải có thiết kế bổ sung (ví dụ một cấu trúc trạng thái có cờ hiện diện), và phải tính tới tính nhất quán khi đọc nhiều biến.

### 3.2. Ví dụ phép toán khác: GCD (ước chung lớn nhất)

GCD của số nguyên dương có tính kết hợp và giao hoán, identity phù hợp là `0` vì `gcd(0,x)=x` với x dương.

~~~java
// LongAccumulatorGcdDemo.java
import java.util.concurrent.atomic.LongAccumulator;

public class LongAccumulatorGcdDemo {
    private static long gcd(long a, long b) {
        while (b != 0) {
            long remainder = a % b;
            a = b;
            b = remainder;
        }
        return a;
    }

    public static void main(String[] args) {
        // Ví dụ chỉ truyền số nguyên dương.
        LongAccumulator gcdAccumulator =
            new LongAccumulator(LongAccumulatorGcdDemo::gcd, 0L);

        gcdAccumulator.accumulate(18);
        gcdAccumulator.accumulate(24);
        gcdAccumulator.accumulate(30);
        System.out.println("GCD: " + gcdAccumulator.get());
    }
}
~~~

~~~bash
javac LongAccumulatorGcdDemo.java
java LongAccumulatorGcdDemo
~~~

Stdout:

~~~text
GCD: 6
~~~

Hàm `gcd` ở đây **thuần**, không thay đổi state bên ngoài và chỉ nhận số dương trong ví dụ. Nếu muốn hỗ trợ mọi giá trị `long`, cần thiết kế kỹ cho số âm và `Long.MIN_VALUE` vì `Math.abs(Long.MIN_VALUE)` tràn trong kiểu long; ví dụ chỉ minh họa tính kết hợp/giao hoán trên miền số dương.

### 3.3. Hàm accumulator có thể được thực hiện lại

Không dùng updater để gây side effect không thể lặp lại:

~~~java
// MÃ NÊN TRÁNH: minh họa logic, không phải chương trình độc lập.
LongAccumulator wrong = new LongAccumulator((current, x) -> {
    sendEmail(x); // Side effect có thể lặp lại trong quá trình retry.
    return current + x;
}, 0L);
~~~

Vì implementation có thể thử lại việc cập nhật khi tranh chấp, hàm có thể được áp dụng **nhiều lần cho một lời gọi `accumulate`**. Mã đúng chỉ thực hiện phép tính thuần từ `current` và `x` rồi trả kết quả; gửi email, ghi DB, ghi log nghiệp vụ một lần... phải tách khỏi hàm gộp.

Chọn operator không associative/commutative như phép trừ cũng là lỗi: kết quả phụ thuộc thứ tự và cách chia ô, trong khi API không bảo đảm một thứ tự duy nhất.

## 4. Vì sao giảm contention được?

### 4.1. AtomicLong: một điểm cập nhật

`AtomicLong` giữ một trạng thái `long` đơn mà các phép atomic update cùng cạnh tranh. Điều này rất thích hợp nếu cần:

- `incrementAndGet()` trả về ngay giá trị mới.
- `getAndIncrement()` cấp **số thứ tự duy nhất** tại điểm tăng.
- `compareAndSet(expected, update)` cho một chuyển trạng thái có điều kiện.
- `get()` đọc **một giá trị nguyên tử hiện tại** của field theo ngữ nghĩa API.

### 4.2. LongAdder/Accumulator: phân tán cập nhật khi cần

Khi tranh chấp, implementation có thể tăng số biến nội bộ chứa các phần tổng. Thread cập nhật phần nội bộ tương ứng, và lúc đọc kết quả thì code phải gộp các phần đó lại. Điểm được tối ưu là **throughput cập nhật** dưới contention, nhưng có những đánh đổi:

- Tốn **nhiều bộ nhớ hơn**, nhất là với nhiều instance LongAdder/LongAccumulator và nhiều writer.
- `sum()`/`get()` phải tổng hợp nhiều thành phần, nên chi phí **đọc** có thể tăng.
- `sum()`/`get()` **không phải atomic snapshot** khi writer vẫn đang cập nhật.
- Không có một kết quả **trả về từ từng lần update** giống `AtomicLong.incrementAndGet()`; `LongAdder.increment()` trả `void`.
- Các thao tác reset phải được dùng ở giai đoạn **không có concurrent updates**, nếu cần kết quả ranh giới kỳ chính xác.

Phân tán cập nhật không có nghĩa là dùng khóa lớn bảo vệ mỗi update. Cả hai class tận dụng cơ chế nguyên tử và điều phối bên trong JDK, nhưng không cung cấp khóa cho caller để bọc một giao dịch nhiều bước.

## 5. sum() / get(): số liệu đọc được không phải snapshot nguyên tử

Tài liệu JDK 17 nêu rõ:

- `LongAdder.sum()` trả tổng hiện được tổng hợp, **không phải một snapshot nguyên tử**. Những cập nhật xảy ra trong lúc tổng hợp có thể chưa được đưa vào kết quả.
- `LongAccumulator.get()` cũng **không phải snapshot nguyên tử** đối với concurrent updates.
- Khi **không có concurrent updates**, phép lấy tổng/kết quả cho giá trị chính xác của những cập nhật đã hoàn tất và được công bố theo giao thức đồng bộ thích hợp.

Hãy hình dung phép đọc đang cộng nhiều cell:

~~~text
Thời gian →
Reader:   đọc cell A = 10 ─────── đọc cell B = 20 ─── trả 30
Writer:             cập nhật A thành 11 ─── cập nhật B thành 21

Có thể không tồn tại một thời điểm duy nhất mà tổng của cả A và B đúng
bằng giá trị Reader vừa tính từ các phiên bản cell khác nhau.
~~~

Đây là **sơ đồ khái niệm** về sự thiếu atomic snapshot, không phải mô tả chính xác cơ chế từng cell của JDK. Cần tránh kết luận “mỗi lần `sum()` trả về là tổng **tại thời điểm gọi**” nếu vẫn có writers đang chạy.

### 5.1. Đọc thống kê và quyết định nghiệp vụ là hai chuyện

Trường hợp hợp lý:
- Hiển thị một metric xấp xỉ khi request vẫn đang được xử lý.
- Đếm số tác vụ/hit được tích lũy trong worker pool, đọc theo chu kỳ để giám sát.
- Gộp max độ trễ đã quan sát, không yêu cầu một snapshot tuyến tính hóa cho thuật toán điều khiển.

Trường hợp **không nên** chỉ dựa vào `sum()`:
- `if (adder.sum() < limit) adder.increment()` để đặt **giới hạn cứng**.
- `sum()` để cấp số vé/ID duy nhất.
- Quyết định đặt chỗ khi `available == 1` rồi decrement, cần bảo đảm không oversell.
- Chốt một số liệu thanh toán tuyệt đối tại đúng thời điểm trong khi các thread vẫn cập nhật.

Ngay cả `AtomicLong` cũng không tự biến **chuỗi `get()` rồi `incrementAndGet()`** thành một giao dịch điều kiện. Khi có ràng buộc “nếu chưa vượt giới hạn mới tăng”, hãy dùng **CAS loop**, một đoạn khóa hoặc primitive chuyên dụng để kiểm tra và cập nhật tại cùng điểm nguyên tử.

### 5.2. Muốn tổng chính xác sau một đợt: đợi writers kết thúc

Ví dụ LongAdderContentionDemo đã dùng `CountDownLatch` để chờ đầy đủ tasks trước khi gọi `sum()`. Một chương trình dùng executor có thể:
1. `submit` tất cả tác vụ;
2. đợi tất cả `Future.get()` hoàn tất thành công (xử lý exception/hủy đúng cách);
3. chắc chắn không còn producer mới vào cùng counter;
4. đọc `sum()` sau điểm đồng bộ ấy.

**Không đủ** nếu chỉ thấy `ExecutorService.shutdown()` đã được gọi: shutdown dừng nhận task mới nhưng **không đợi** những task đã được nhận hoàn tất. Nếu việc chờ bị interrupt, timeout hoặc một task tiếp tục chạy sau khi caller bỏ chờ, không thể tuyên bố không còn concurrent updates.

## 6. reset(), sumThenReset(), getThenReset() và ranh giới kỳ

`LongAdder.reset()` đặt các phần lưu tổng về 0. `LongAdder.sumThenReset()` đọc tổng rồi reset; `LongAccumulator.reset()` đặt các phần về **identity**; `LongAccumulator.getThenReset()` đọc kết quả rồi reset về identity.

Các thao tác này **không được bảo đảm atomic với những writer đang cập nhật**. JDK mô tả reset là thao tác có tính cạnh tranh nội tại; chỉ dùng an toàn cho mục tiêu số liệu chính xác khi **biết không có concurrent updates**.

| API | Sau reset | Điều kiện để chốt số liệu chính xác |
| --- | --- | --- |
| `LongAdder.reset()` | 0 | Không có writer concurrent |
| `LongAdder.sumThenReset()` | 0 | Không có writer concurrent |
| `LongAccumulator.reset()` | Identity được cấp lúc tạo | Không có writer concurrent |
| `LongAccumulator.getThenReset()` | Identity được cấp lúc tạo | Không có writer concurrent |

### 6.1. Vì sao reset đồng thời có thể mất cập nhật?

Phép tổng hợp rồi xóa các ô nội bộ **không phải một giao dịch** với tất cả cập nhật đang xảy ra. Một update có thể nằm trong khoảng đọc/xóa của một ô và cuối cùng không được phân loại vào kỳ vừa chốt hoặc kỳ mới theo cách mong muốn. Do đó kết quả `sumThenReset()` trong lúc producer đang ghi **không có bảo đảm** bằng “tất cả sự kiện trước thời điểm reset” và kỳ sau cũng không chắc phục hồi một ranh giới logic chính xác.

Đừng đọc tên `sumThenReset` thành “atomic getAndSet(0)”. Với `AtomicLong`, `getAndSet(0)` là một thao tác nguyên tử trên **một biến duy nhất** và có semantics khác.

### 6.2. Chiến lược khi cần báo cáo theo kỳ

**Cách A — Có điểm nghỉ (quiescence):** dừng hoặc chặn các producer mới, đợi toàn bộ producer hiện tại hoàn tất, sau đó gọi `sumThenReset`/`getThenReset`, rồi cho producer tiếp tục. Đây là cách trực tiếp để xác định ranh giới.

**Cách B — Thống kê xấp xỉ:** liên tục gọi `sum()`/`get()` mà không reset, chấp nhận giá trị tức thời và tính delta giữa những lần quan sát cho dashboard. Delta này **không phải** một số đo transactionally exact nếu writers còn hoạt động; có thể dùng cho metrics giám sát phù hợp.

**Cách C — Đổi thế hệ counter có phối hợp:** có thể quản lý nhiều counter/snapshot theo epoch, nhưng việc thay reference `AtomicReference<LongAdder>` bằng `getAndSet` **chưa đủ** để tạo ranh giới tuyệt đối: một writer đã giữ reference counter cũ có thể cập nhật nó **sau** lúc reference mới được công bố. Muốn không bỏ sót/đếm sai kỳ, cần giao thức phối hợp với những writer đang chạy (drain/in-flight tracking, khóa, barrier hoặc cơ chế khác), không chỉ hoán đổi reference.

Khi nghiệp vụ cần chính xác từng giao dịch hoặc số dư, dùng primitive giao dịch thích hợp thay vì dựa vào thống kê kiểu LongAdder.

## 7. LongAdder so với AtomicLong: chọn theo mục tiêu

| Tiêu chí | `AtomicLong` | `LongAdder` |
| --- | --- | --- |
| Trạng thái | Một giá trị `long` nguyên tử | Tổng phân tán qua các giá trị nội bộ khi contention |
| Thao tác tăng | `incrementAndGet()` / `getAndIncrement()` trả giá trị | `increment()` trả `void` |
| Đọc | `get()` là phép đọc nguyên tử một giá trị | `sum()` không phải atomic snapshot |
| CAS điều kiện | Có `compareAndSet` | Không cung cấp CAS trên tổng |
| Dưới contention cao | Có thể tốn chi phí tại một điểm cập nhật | Thường có throughput cập nhật cao hơn |
| Dưới contention thấp | Đơn giản, overhead nhỏ | Lợi ích có thể ít, chi phí quản lý tổng vẫn tồn tại |
| Bộ nhớ | Thường nhỏ hơn | Có thể lớn hơn khi mở rộng nội bộ |
| Mục đích | Điều khiển/chuyển trạng thái, ID, chính xác tức thời trên một biến | Metrics, counters, throughput updates |
| Reset | `getAndSet(0L)` là atomic RMW | `sumThenReset()` không atomic với concurrent updates |

**Ví dụ quyết định đúng:**
- Số lượt truy cập trang được các worker tăng liên tục, đọc để hiển thị dashboard → `LongAdder` phù hợp để thử.
- Cấp số thứ tự tăng dần không trùng cho mỗi request → dùng `AtomicLong.getAndIncrement()`.
- Giới hạn cứng “chỉ tối đa 100 tác vụ cùng hoạt động” → dùng giao thức đồng bộ cho **check và cập nhật** (ví dụ CAS/semaphore), không phải `if (adder.sum() < 100)`.
- Ghi số liệu cho đợt xử lý batch có `join()` đầy đủ trước khi chốt → `LongAdder.sum()` chính xác ở điểm sau batch.

### Tại sao không dùng volatile long++?

`volatile long count` có visibility/ordering cho lần đọc/ghi field, nhưng `count++` vẫn là **read–modify–write không nguyên tử**. Hai thread có thể cùng đọc một giá trị rồi cùng ghi kết quả mới, gây lost update. `AtomicLong.incrementAndGet()` và `LongAdder.increment()` giải quyết việc cộng dồn đồng thời theo hợp đồng của từng API, nhưng mang semantics đọc khác nhau.

## 8. LongAccumulator so với LongAdder và AtomicLong

| Tiêu chí | `LongAdder` | `LongAccumulator` | `AtomicLong` |
| --- | --- | --- | --- |
| Phép kết hợp | Cộng dồn `long` | `LongBinaryOperator` tùy chọn | Atomic update trên một `long` |
| Identity | Luôn 0 | Do caller cấp | Giá trị khởi tạo do caller cấp |
| Cập nhật | `add`, `increment`, `decrement` | `accumulate(x)` | `addAndGet`, `updateAndGet`, `accumulateAndGet`... |
| Đọc | `sum()` | `get()` | `get()` |
| Atomic snapshot khi đang ghi | Không | Không | Có cho một `long` |
| Mức tranh chấp | Có thể phân tán các cập nhật | Có thể phân tán các cập nhật | Cùng tranh một giá trị |
| Phù hợp | Lượt truy cập, bytes, đếm sự kiện | Max/min hoặc phép reduction tùy chọn | Số thứ tự, CAS, cập nhật điều kiện |

`LongAdder` là trường hợp phổ biến của phép cộng, có thể hiểu gần với `new LongAccumulator(Long::sum, 0L)` về ý nghĩa tổng hợp, dù API riêng của `LongAdder` tiện hơn và implementation/performance cần được đo theo workload.

**Không dùng `LongAccumulator` với operator tùy tiện.** Operator cần có identity và không phụ thuộc thứ tự gộp. Chẳng hạn phép “giữ average hiện tại” `(old + sample) / 2` không associative và không cho average tổng thể đúng. Nếu muốn average, nên theo dõi **sum + count**, rồi chia khi tổng hợp; nếu cần một snapshot chính xác đồng thời của cả hai, phải phối hợp việc đọc cả hai theo giao thức phù hợp.

**Long overflow:** cả `LongAdder` lẫn `LongAccumulator` trả kiểu `long`; các phép cộng trên long có thể **tràn** theo quy tắc số nguyên Java. Nếu nghiệp vụ cần tổng vượt phạm vi long với độ chính xác tuyệt đối, chọn biểu diễn khác và cơ chế đồng bộ phù hợp; không giả định phân tán counters giúp tránh overflow.

## 9. Mẫu đếm theo key với ConcurrentHashMap

Tình huống phổ biến: số lượt xuất hiện của từng mã sự kiện. Ta có thể dùng `ConcurrentHashMap<String, LongAdder>` để mỗi key có một bộ đếm đồng thời riêng. `computeIfAbsent` đảm nhiệm việc tạo/bắt lại bộ đếm cho key một cách an toàn theo hợp đồng của map; `increment()` cộng giá trị trên instance được lấy.

~~~java
// LongAdderFrequencyDemo.java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class LongAdderFrequencyDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, LongAdder> frequency =
            new ConcurrentHashMap<>();

        Runnable record = () -> {
            frequency
                .computeIfAbsent("ok", key -> new LongAdder())
                .increment();
            frequency
                .computeIfAbsent("error", key -> new LongAdder())
                .increment();
            frequency
                .computeIfAbsent("ok", key -> new LongAdder())
                .increment();
        };

        Thread a = new Thread(record);
        Thread b = new Thread(record);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("ok: " + frequency.get("ok").sum());
        System.out.println("error: " + frequency.get("error").sum());
    }
}
~~~

~~~bash
javac LongAdderFrequencyDemo.java
java LongAdderFrequencyDemo
~~~

Stdout:

~~~text
ok: 4
error: 2
~~~

**Vì sao đúng?** Hai thread đều cộng vào adder gắn với key tương ứng; việc tạo value qua `computeIfAbsent` là thao tác của concurrent map, không phải `if (map.get(key) == null) map.put(key,new LongAdder())` tự viết. Main `join()` hai worker rồi mới đọc; kết quả không phụ thuộc vào thứ tự lập lịch.

**Giới hạn cần nhớ:**
- Nếu có code **remove/replace** value của key khi writer khác đã giữ reference tới adder cũ, có thể có cập nhật vào object không còn được map tham chiếu. Cần thiết kế lifecycle của key/counter, không kết luận mỗi `increment` chắc chắn được tính vào value hiện đang nằm trong map.
- Việc `sum()` trên nhiều key trong khi writer hoạt động **không cho một snapshot nguyên tử của toàn map**.
- Mỗi key có một adder: với nhiều key ít được cập nhật, chi phí object/metadata có thể lớn. Cần cân nhắc retention/eviction và benchmark.

## 10. Sai lầm phổ biến khi dùng LongAdder/LongAccumulator

1. **Xem `sum()` là một lần đọc atomic của tổng.** Không đúng khi writer vẫn đang cập nhật. Kết quả là tổng hợp nhất thời, không phải linearizable snapshot.
2. **Dùng `sum()` để điều khiển hard limit.** Mẫu `if (counter.sum() < limit) counter.increment()` bị check–then–act race và còn đọc non-atomic snapshot.
3. **Dùng `sumThenReset()` để chốt số chính xác trong lúc producers vẫn ghi.** Reset cạnh tranh có thể bỏ sót/đếm sai kỳ. Phải có quiescence hoặc giao thức epoch đồng bộ đầy đủ.
4. **Chọn sai identity của LongAccumulator.** Với `Long::max` dùng 0 sẽ sai khi mọi mẫu âm; dùng `Long.MIN_VALUE`.
5. **Dùng operator không associative/commutative.** Kết quả có thể phụ thuộc thứ tự và cách gộp, vốn không được bảo đảm.
6. **Đặt side effect trong operator.** Operator có thể chạy lại khi retry, gây gửi thông báo/thực hiện thanh toán trùng.
7. **Nhầm `increment()` với `incrementAndGet()`.** `LongAdder.increment()` trả `void`, không cấp sequence ID.
8. **Giả định LongAdder luôn nhanh hơn.** Mức contention, read frequency, GC, số instance và kiến trúc CPU ảnh hưởng kết quả.
9. **Nghĩ LongAdder là một counter có giá trị không bao giờ giảm.** `add(-x)` và `decrement()` hợp lệ, và phép tổng của nhiều cell được đọc cạnh tranh không bảo đảm một tiến trình đơn giản như một AtomicLong.
10. **Quên xử lý overflow.** Kết quả `long` có giới hạn; cần xem miền giá trị và thời gian tồn tại của counter.
11. **Tưởng `reset()` giúp thread-safe giữa các kỳ.** `reset()` không phải atomic epoch transition; cần ngăn writer cập nhật trong thời gian reset nếu đòi exactness.
12. **Dùng map frequency mà xóa key không kiểm soát.** Writer có thể đã giữ reference tới value cũ; thay map entry không tự chặn update đang bay vào value đó.

## 11. Cách benchmark trước khi chọn

Để so `AtomicLong` với `LongAdder` hoặc `LongAccumulator`, cần dùng workload đại diện, không chỉ đo một vòng lặp ngắn trong `main`.

- **Số writer:** một thread, vài thread, số thread lớn hơn số core? Cần thử nhiều mức.
- **Tần suất đọc:** dashboard mỗi giây hay đọc liên tục sau từng update? `sum()` có chi phí gộp khi có nhiều cell.
- **Hình thức tác vụ:** có tính toán khác giữa hai lần cập nhật hay tất cả thread cùng tranh một điểm?
- **Số instance:** một bộ đếm nóng khác nhiều nghìn bộ đếm lạnh trong map.
- **Bộ nhớ và GC:** adder có thể tiêu thụ nhiều bộ nhớ hơn; đo heap/allocations nếu quan trọng.
- **Warmup/JIT/CPU:** dùng công cụ microbenchmark đáng tin như **JMH** cho đo lường nghiêm túc; tránh kết luận từ `System.nanoTime()` quanh một loop tối ưu khó kiểm soát.
- **Correctness trước:** bảo đảm kết quả sau khi mọi writer hoàn tất là đúng; đừng thay atomicity bắt buộc bằng số liệu throughput.

Thông thường hãy đo **operations/second**, **latency** và **memory** theo các mức contention. Một kết quả benchmark trong một máy không phải bảo đảm trên mọi workload.

## 12. Quy trình thiết kế an toàn

1. **Xác định tính chất của số liệu:** metric thống kê hay trạng thái điều khiển? Có cần giá trị **trả về ngay từ mỗi update** hay không?
2. **Viết ràng buộc tính đúng:** chỉ cần tổng chính xác khi kết thúc batch, hay cần quyết định ở mọi thời điểm?
3. **Chọn primitive:** `AtomicLong` cho ID/conditional CAS; `LongAdder` cho tổng/counter nóng; `LongAccumulator` cho reduction như max/min với operator đúng.
4. **Kiểm tra operator:** có identity thật, associative, commutative, side-effect-free không? Có overflow/giá trị âm/miền đầu vào đặc biệt không?
5. **Xác định điểm đọc:** nếu `sum()/get()` khi writers đang chạy, chấp nhận đây không phải atomic snapshot; nếu cần exact, phối hợp dừng và đợi writers.
6. **Thiết kế kỳ reset:** tuyệt đối không mặc định `sumThenReset()/getThenReset()` là atomic với producer. Xây dựng quiescence/epoch protocol nếu đòi chốt kỳ chính xác.
7. **Đánh giá lifecycle của counter:** trong map, ai tạo/xóa/replace? Có writer cầm reference cũ không?
8. **Stress test và benchmark:** thử nhiều mức contention, assertion số liệu cuối, theo dõi throughput và memory trước khi tối ưu.

## 13. Tự kiểm tra

**1.** Bốn thread mỗi thread tăng `LongAdder` 10.000 lần, main đợi đủ bốn thread rồi gọi `sum()`. Giá trị mong đợi là bao nhiêu?  
**Đáp án:** 40.000 nếu mọi worker hoàn tất các cập nhật; sau điểm đợi không còn concurrent updates nên tổng chính xác.

**2.** Có thể dùng `LongAdder.increment()` để trả về một ID duy nhất cho mỗi request không?  
**Đáp án:** Không. Phương thức trả `void` và `sum()` không phải atomic snapshot. Nếu cần ID, dùng `AtomicLong.getAndIncrement()` hoặc primitive tương đương.

**3.** Với `LongAccumulator(Long::max, 0L)`, thêm -5 và -2. Kết quả đúng phải là -2 nhưng `get()` có thể trả gì?  
**Đáp án:** 0, vì chọn identity sai. Sửa thành `Long.MIN_VALUE`.

**4.** Tại sao `LongAccumulator((a,b)->a-b, 0)` không thích hợp?  
**Đáp án:** Phép trừ không associative/commutative; kết quả phụ thuộc thứ tự và cách gộp cập nhật.

**5.** `sumThenReset()` có phải một thao tác atomic tương đương `AtomicLong.getAndSet(0)` không?  
**Đáp án:** Không. Với writer đồng thời, các phép tổng hợp và reset ô nội bộ không tạo một ranh giới kỳ atomic.

**6.** Nếu muốn đếm tần suất theo key trong `ConcurrentHashMap`, mẫu nào hợp lý?  
**Đáp án:** `map.computeIfAbsent(key, k -> new LongAdder()).increment()`. Cần phối hợp thêm nếu key có thể bị remove/replace cùng lúc.

**7.** Khi nào `LongAdder` có thể kém lợi thế hơn `AtomicLong`?  
**Đáp án:** Khi contention thấp, đọc tổng liên tục, có nhiều bộ đếm ít cập nhật, hay việc dùng thêm bộ nhớ/đọc gộp không phù hợp.

**8.** Với `LongAccumulator(Long::max, Long.MIN_VALUE)` chưa có mẫu nào, `get()` trả gì?  
**Đáp án:** Trả identity là `Long.MIN_VALUE`, không thể tự biết “chưa có mẫu” nếu ứng dụng không thêm mô hình biểu thị sự hiện diện.

**9.** Việc swap `AtomicReference<LongAdder>` sang adder mới có đủ để chốt cứng kỳ trước không?  
**Đáp án:** Chưa đủ. Worker đã đọc reference cũ có thể cập nhật vào nó sau swap; cần phối hợp writer đang chạy để có ranh giới exact.

**10.** LongAccumulator có nên dùng operator có tác dụng phụ ghi database không?  
**Đáp án:** Không. Hàm có thể bị áp dụng lại khi retry. Hãy giữ operator thuần và tách I/O khỏi phép reduction.

**Ghi nhớ:** `LongAdder` là lựa chọn mạnh cho **counter/sum được nhiều thread cập nhật** khi một snapshot đọc trong lúc ghi không cần tuyến tính hóa. `LongAccumulator` mở rộng ý tưởng sang phép reduction có identity đúng và operator kết hợp/giao hoán, thuần. `AtomicLong` vẫn quan trọng khi cần **một điểm cập nhật/đọc nguyên tử hoặc CAS điều kiện**. Chọn theo tính đúng của giao thức, rồi mới tối ưu throughput.

### Tài liệu tham khảo chính thức

- Java SE 17, `LongAdder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- Java SE 17, `LongAccumulator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAccumulator.html
- Java SE 17, `AtomicLong`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html
- Java SE 17, `ConcurrentHashMap`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html