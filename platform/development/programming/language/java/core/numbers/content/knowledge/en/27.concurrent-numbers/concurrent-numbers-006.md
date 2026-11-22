# `LongAdder`, `DoubleAdder` và bài toán thống kê có tranh chấp trong Java

## 1. Bài toán: rất nhiều luồng cùng tăng một bộ đếm

Trong một máy chủ Java, nhiều luồng có thể cùng thống kê lượt request, số lỗi, cache hit hoặc tổng thời gian xử lý. Nếu dùng biến `long` và lệnh `count++`, nhiều cập nhật có thể bị **mất** vì `++` thực chất gồm đọc, tính, ghi. Hai luồng cùng đọc 10, tính 11 và ghi 11, trong khi kết quả đúng sau hai lần tăng phải là 12.

`volatile long count` không giải quyết được phép cộng: `volatile` cung cấp bảo đảm về hiển thị và thứ tự bộ nhớ, **không làm read-modify-write trở thành nguyên tử**. Khi cần đếm đồng thời, các cách tiếp cận thường là `synchronized`/`Lock`, `AtomicLong` hoặc `LongAdder`.

`LongAdder` và `DoubleAdder` (gói `java.util.concurrent.atomic`, có từ Java 8) được thiết kế cho kiểu công việc **nhiều luồng liên tục cộng vào một đại lượng thống kê**, đặc biệt khi có tranh chấp (*contention*) trên cùng một biến.

Sau bài này, bạn sẽ biết:

- Vì sao một bộ đếm `AtomicLong` có thể trở thành điểm nóng khi nhiều luồng cùng cập nhật.
- `LongAdder` và `DoubleAdder` giảm tranh chấp bằng cách phân tán phép cộng như thế nào.
- Chạy ví dụ nhiều luồng và đọc kết quả đáng tin sau `join()`.
- Phân biệt thread-safe updates với **đọc snapshot nguyên tử**.
- Dùng `ConcurrentHashMap<K, LongAdder>` để đếm theo nhãn.
- Chọn cách xử lý đúng cho reset thống kê, quota nghiêm ngặt và giá trị `double` xấp xỉ.

## 2. Cơ chế: phân tán phép ghi để giảm cạnh tranh

`AtomicLong` giữ một trạng thái nguyên tử dùng chung; nhiều luồng thường thử cập nhật trạng thái đó bằng CAS (*compare-and-set*) hoặc các primitive nguyên tử tương đương. Khi cùng tranh một điểm nóng, các lần thử có thể bị thất bại và phải thử lại.

`LongAdder` được tối ưu cho tình huống một lượng lớn thao tác `add`/`increment` cạnh tranh. Về mặt ý tưởng, nó có tổng cơ sở và có thể mở rộng các ô (*cells*) để trải phép ghi:

```text
Worker A ---> [cell A] --+
Worker B ---> [cell B] --+---> sum() = base + tổng cell
Worker C ---> [cell C] --+
Worker D ---> [base] ----+
```

Sơ đồ chỉ minh họa cơ chế: **không đảm bảo mỗi luồng sở hữu riêng một cell**, cũng không đảm bảo số ô cố định. Việc phân phối và mở rộng là chi tiết triển khai JDK. Điểm đánh đổi là cộng vào các phần độc lập có thể giảm contention khi ghi, nhưng `sum()` phải đọc/gộp các phần, có thể tốn công hơn so với `AtomicLong.get()`.

`DoubleAdder` áp dụng ý tưởng tương tự cho tổng `double`. Cả hai không phải lựa chọn nhanh nhất trong mọi hoàn cảnh: với rất ít tranh chấp, cập nhật thưa, bộ nhớ hạn chế hoặc đọc thường xuyên, `AtomicLong` có thể đơn giản và phù hợp hơn. Hiệu năng thực tế cần đo trên workload cụ thể.

### Ba yêu cầu cần phân biệt

1. **Mọi lần cộng hoàn thành đều được ghi nhận** theo hợp đồng đồng thời của adder, miễn không có reset cạnh tranh và không có vấn đề tràn/precision liên quan.
2. **Đọc tổng sau khi đã ngừng cập nhật**: `sum()` phản ánh số lần cộng đã hoàn tất, phù hợp để nghiệm thu kết quả các worker.
3. **Đọc snapshot nguyên tử trong lúc các worker vẫn cộng**: `sum()` **không cam kết điều này**; có thể lấy trạng thái của các cell ở những thời điểm khác nhau.

## 3. API và khác biệt quan trọng

| Thao tác | `LongAdder` | `DoubleAdder` |
|---|---|---|
| Khởi tạo | `new LongAdder()` | `new DoubleAdder()` |
| Cộng một lượng | `add(long delta)` | `add(double delta)` |
| Cộng/trừ 1 | `increment()`, `decrement()` | `add(1.0)`, `add(-1.0)` |
| Đọc tổng | `sum(): long` | `sum(): double` |
| Đọc rồi reset | `sumThenReset()` | `sumThenReset()` |
| Reset không lấy tổng | `reset()` | `reset()` |
| Lấy qua `Number` | `longValue()` tương ứng với tổng | `doubleValue()` tương ứng với tổng |
| Có `get()`, `compareAndSet()`? | Không | Không |

Các thao tác `add` có thể nhận giá trị âm; adder không chỉ đếm số dương. Giá trị khởi đầu của cả hai là 0. `LongAdder.sum()` trả về `long`, nên vẫn có khả năng **tràn số nguyên 64 bit**, không tự kiểm tra `Math.addExact`.

Cần lưu ý: `LongAdder` **không có phương thức `get()`** giống `AtomicLong`; muốn lấy tổng dùng `sum()`. `LongAdder.longValue()` cũng không làm snapshot trở nên nguyên tử.

## 4. Ví dụ hoàn chỉnh: bốn luồng cùng tăng `LongAdder`

**Tệp `LongAdderDemo.java`**, chạy Java 17+:

```java
import java.util.concurrent.atomic.LongAdder;

public class LongAdderDemo {
    public static void main(String[] args) throws InterruptedException {
        int workersCount = 4;
        int updatesPerWorker = 100_000;
        LongAdder requests = new LongAdder();

        Thread[] workers = new Thread[workersCount];

        for (int i = 0; i < workersCount; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < updatesPerWorker; j++) {
                    requests.increment();
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("expected=" + workersCount * updatesPerWorker);
        System.out.println("actual=" + requests.sum());
    }
}
```

Chạy:

```bash
javac LongAdderDemo.java
java LongAdderDemo
```

Kết quả:

```text
expected=400000
actual=400000
```

`join()` ở đây rất quan trọng. Nó bảo đảm tác vụ của các worker đã kết thúc trước khi main đọc tổng, đồng thời cung cấp quan hệ *happens-before* cho hành động của worker. Vì không còn ghi đồng thời, `sum()` lúc này cung cấp tổng của 400.000 lần `increment()` theo ví dụ.

Nếu đọc `sum()` ngay sau khi gọi `start()`, kết quả có thể nhỏ hơn 400.000 vì các worker chưa xong. Đó không tự chứng minh có lỗi mất cập nhật; khác biệt có thể chỉ do thời điểm quan sát.

Ví dụ thao tác cơ bản (đặt trong một phương thức khi chạy):

```java
LongAdder pending = new LongAdder();
pending.increment(); // +1
pending.add(5);       // +5
pending.decrement(); // -1
System.out.println(pending.sum()); // 5
```

Với biến đã chia sẻ cho nhiều luồng, `increment()`, `decrement()` và `add(long)` hỗ trợ cập nhật đồng thời. Nhưng việc đọc tổng trong khi vẫn đang ghi vẫn mang tính thống kê.

## 5. Ví dụ `DoubleAdder`: tổng thời gian xử lý và số mẫu

`DoubleAdder` dùng `double` để cộng dồn những đại lượng **chấp nhận độ chính xác dấu phẩy động**, ví dụ tổng latency hoặc phép đo. Muốn tính trung bình, thường dùng thêm một `LongAdder` đếm mẫu.

**Tệp `DoubleAdderDemo.java`:**

```java
import java.util.concurrent.atomic.DoubleAdder;
import java.util.concurrent.atomic.LongAdder;

public class DoubleAdderDemo {
    public static void main(String[] args) throws InterruptedException {
        int workersCount = 4;
        int samplesPerWorker = 10_000;

        DoubleAdder total = new DoubleAdder();
        LongAdder count = new LongAdder();
        Thread[] workers = new Thread[workersCount];

        for (int i = 0; i < workersCount; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < samplesPerWorker; j++) {
                    total.add(0.75);
                    count.increment();
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        long n = count.sum();
        double totalTime = total.sum();
        System.out.println("count=" + n);
        System.out.println("total=" + totalTime);
        System.out.println("average=" + totalTime / n);
    }
}
```

```bash
javac DoubleAdderDemo.java
java DoubleAdderDemo
```

```text
count=40000
total=30000.0
average=0.75
```

Ví dụ chọn `0.75`, một số biểu diễn chính xác trong nhị phân, để giá trị hiển thị không bị nhiễu do làm tròn. Với `0.1`, không nên giả định tổng được biểu diễn thập phân chính xác.

**Lưu ý về tính nhất quán:** Mỗi worker gọi `total.add(0.75)` rồi `count.increment()`. Nếu dashboard đọc `count.sum()` và `total.sum()` giữa lúc các worker chạy, hai kết quả có thể tương ứng những thời điểm khác nhau. Tính trung bình như vậy chỉ là một quan sát best effort. Sau khi `join()` tất cả worker, hai tổng mới ổn định theo giới hạn số học ví dụ.

Một trung bình có `n == 0` phải được xử lý riêng. Nếu tính `totalTime / n` với `double` và `n == 0`, kết quả có thể là `NaN` hoặc vô cực, không phải giá trị trung bình hợp lệ. Trong ứng dụng thực, chỉ chia khi có mẫu.

## 6. `sum()` thread-safe nhưng không phải snapshot nguyên tử

Một số tài liệu dùng từ “thread-safe” khiến người đọc suy ra rằng **mọi lần đọc đều nhìn thấy một trạng thái toàn cục nhất quán**. Điều đó không đúng với `LongAdder.sum()`/`DoubleAdder.sum()`.

Khi đang ghi đồng thời, một lời gọi `sum()` có thể cộng phần base và từng cell ở những thời điểm khác nhau. Kết quả hữu ích cho thống kê gần thời điểm đọc, nhưng không có bảo đảm nó đại diện cho một khoảnh khắc đơn nhất theo mô hình linearizable.

Ví dụ dashboard hiển thị “khoảng 10.000 request đã xử lý” có thể chấp nhận độ trễ quan sát. Nhưng tính toán **quota cứng** như giới hạn phát hành tối đa 100 mã phải dùng cơ chế có atomic check-then-update.

Đoạn mã sai về mặt quota:

```java
// Minh họa, quota là LongAdder dùng chung.
if (quota.sum() < 100) {
    quota.increment();
    // Cấp quyền cho request này.
}
```

Hai luồng có thể cùng thấy `99` rồi cùng cấp quyền và tăng, làm vượt 100. Thay `LongAdder` bằng `AtomicLong` rồi vẫn thực hiện `get() < 100` và `incrementAndGet()` riêng lẻ **cũng chưa đủ**: cặp kiểm tra và cập nhật phải được gắn thành một giao thức nguyên tử, chẳng hạn vòng CAS hoặc lock/transaction thích hợp.

`AtomicLong.get()` cung cấp phép đọc nguyên tử trên **một biến**; `AtomicLong.compareAndSet()` giúp triển khai phép cập nhật có điều kiện. `LongAdder` thiếu CAS trên toàn tổng, nên không dùng làm sequencer tạo số thứ tự duy nhất hoặc cơ chế quota chính xác.

## 7. `reset()` và `sumThenReset()`: thận trọng với cập nhật đang diễn ra

Cả hai adder có hai phương thức đáng chú ý:

- `reset()`: đặt bộ cộng dồn về zero.
- `sumThenReset()`: trả tổng đang quan sát rồi đặt lại về zero.

Chúng **không cung cấp phép cắt một cửa sổ thống kê nguyên tử** trong khi nhiều luồng đang `add()`. Theo hợp đồng API, dùng chúng phù hợp nhất khi **không có cập nhật đồng thời**. Nếu cạnh tranh với lần reset, các cập nhật có thể bị quan sát lệch cửa sổ hoặc không được bảo toàn theo yêu cầu thống kê chính xác.

**Tệp `AdderResetDemo.java`** (không có ghi đồng thời):

```java
import java.util.concurrent.atomic.LongAdder;

public class AdderResetDemo {
    public static void main(String[] args) {
        LongAdder requests = new LongAdder();
        requests.add(8);
        requests.increment();

        System.out.println("before=" + requests.sum());
        System.out.println("drained=" + requests.sumThenReset());
        System.out.println("after=" + requests.sum());

        requests.add(3);
        requests.reset();
        System.out.println("afterReset=" + requests.sum());
    }
}
```

```bash
javac AdderResetDemo.java
java AdderResetDemo
```

```text
before=9
drained=9
after=0
afterReset=0
```

Ứng dụng muốn thống kê theo từng phút có thể dùng reset best effort nếu chấp nhận sai số; nếu phải đảm bảo **không mất sự kiện**, cần điều phối worker dừng ghi vào bộ đếm cũ, thiết kế epoch hoặc dùng hệ thống event/metric có cơ chế cắt cửa sổ theo hợp đồng.

Hoán đổi `AtomicReference<LongAdder>` **không tự động giải quyết toàn bộ**: worker có thể đọc tham chiếu adder cũ trước thời điểm hoán đổi, sau đó cập nhật adder cũ khi luồng thu thập đã lấy tổng. Vì vậy hệ thống vẫn cần quy tắc phối hợp và trạng thái kết thúc ghi.

## 8. Thống kê theo nhãn bằng `ConcurrentHashMap` và `LongAdder`

Khi một ứng dụng ghi nhận nhiều loại sự kiện, một cách dùng phổ biến là mỗi khóa map giữ một adder riêng:

```text
"ok"     ---> LongAdder (số request thành công)
"retry"  ---> LongAdder (số request thử lại)
"failed" ---> LongAdder (số request thất bại)
```

**Tệp `ConcurrentMetricsDemo.java`:**

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class ConcurrentMetricsDemo {
    private static final ConcurrentHashMap<String, LongAdder> COUNTS =
            new ConcurrentHashMap<>();

    private static void record(String event) {
        COUNTS.computeIfAbsent(event, key -> new LongAdder())
                .increment();
    }

    public static void main(String[] args) throws InterruptedException {
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            final int index = i;
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 10_000; j++) {
                    record("ok");
                    if (index % 2 == 0) {
                        record("retry");
                    }
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("ok=" + COUNTS.get("ok").sum());
        System.out.println("retry=" + COUNTS.get("retry").sum());
    }
}
```

```bash
javac ConcurrentMetricsDemo.java
java ConcurrentMetricsDemo
```

```text
ok=40000
retry=20000
```

`ConcurrentHashMap.computeIfAbsent()` phối hợp việc tạo giá trị cho **khóa chưa có**; các luồng sau đó tăng cùng đối tượng `LongAdder`. Dùng `if (!map.containsKey(key)) { map.put(key, new LongAdder()); }` là không an toàn nếu có cạnh tranh vì hai luồng có thể tạo ra hai bộ đếm rồi ghi đè tham chiếu của nhau.

Tuy vậy, `computeIfAbsent(...).increment()` là hai bước, **không phải một transaction nguyên tử cho cả map và bộ đếm**. Nếu một luồng đồng thời `remove` hoặc thay giá trị của khóa, worker đang giữ adder cũ vẫn có thể cộng vào một đối tượng không còn nằm trong map. Khi reset/đổi thế hệ metrics, cần quy tắc sở hữu và đồng bộ riêng.

Đồng thời, đừng cho phép tên nhãn là chuỗi vô hạn sinh từ input tùy ý của người dùng; mỗi nhãn tạo ít nhất một counter và có thể tiêu hao nhiều bộ nhớ. Thiết kế nên giới hạn số nhãn (*cardinality*).

## 9. `DoubleAdder` và sai số dấu phẩy động

`DoubleAdder` không làm phép cộng `double` trở nên chính xác thập phân. Hai vấn đề chính là:

### 9.1. `0.1` không được biểu diễn chính xác bằng `double`

Các số như `0.1` có biểu diễn nhị phân vô hạn, nên cộng dồn có thể tạo sai lệch so với phép tính thập phân lý tưởng. Với phép đo thống kê, có thể chấp nhận sai số theo dung sai đã định. Với tiền, khối lượng phải khớp tuyệt đối hoặc đối soát kế toán, `DoubleAdder` không phù hợp làm nguồn dữ liệu chính xác.

### 9.2. Thứ tự cộng ảnh hưởng kết quả

Phép cộng floating-point không kết hợp (*non-associative*) khi có làm tròn. Ví dụ mảnh mã sau có thể đặt trong `main`:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

Số `1.0` có thể bị mất khi cộng vào `-1e16` do hạn chế chữ số hữu hiệu. Trong `DoubleAdder`, việc các luồng cập nhật các cell khác nhau có thể làm thay đổi thứ tự gom tổng, nên không nên đòi hỏi kết quả **giống nhau đến bit cuối** giữa mọi lần chạy đối với dữ liệu nhạy cảm với thứ tự cộng.

### 9.3. Xử lý dữ liệu không hữu hạn

`DoubleAdder` có thể nhận `Double.NaN`, `Double.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY`; các giá trị này có thể khiến tổng trở thành `NaN` hoặc vô cực. Nếu yêu cầu thống kê là tổng số đo hữu hạn, cần xác thực đầu vào trước khi cộng:

```java
// Mảnh mã bên trong phương thức; sample là double,
// total là DoubleAdder đã khởi tạo.
if (!Double.isFinite(sample)) {
    throw new IllegalArgumentException("Non-finite sample");
}
total.add(sample);
```

Nếu số đo không được âm, kiểm tra thêm `sample >= 0.0`.

### 9.4. Chọn biểu diễn cho tiền

Khi cần lưu tiền một cách chính xác, có thể dùng `BigDecimal` kết hợp transaction/đồng bộ hoặc biểu diễn bằng số nguyên của **đơn vị tiền nhỏ nhất** (với chính sách quy đổi, kiểm tra tràn số và phần lẻ rõ ràng). Chỉ dùng `LongAdder` cộng tiền nguyên đơn vị cho thống kê khi chấp nhận kiểu snapshot của nó; nó không thay thế cơ chế giao dịch kế toán.

## 10. So sánh chọn công cụ

| Nhu cầu | Lựa chọn thường phù hợp | Ghi chú |
|---|---|---|
| Nhiều luồng ghi một bộ đếm metrics | `LongAdder` | Giảm điểm tranh chấp trong một số tải |
| Nhiều luồng cộng `double` cho số đo xấp xỉ | `DoubleAdder` | Có giới hạn precision, rounding |
| Cần `get()`, `compareAndSet()`, cấp sequence | `AtomicLong` | Thao tác nguyên tử trên một biến |
| Cần check-then-update quota hoặc nhiều trường nhất quán | CAS/lock/transaction | Thiết kế toàn bộ thao tác nguyên tử |
| Cần thống kê theo khóa | `ConcurrentHashMap<K,LongAdder>` | Giới hạn cardinality, chú ý xóa/thay counter |
| Cần phân cửa sổ mà không mất sự kiện | Giao thức đồng bộ hoặc metric hệ thống hỗ trợ bucket | `sumThenReset` không đủ khi cạnh tranh |
| Ít contention, đọc nhiều, tài nguyên giới hạn | Cân nhắc `AtomicLong` | Đơn giản, có thể ít overhead |
| Tiền hoặc thập phân cần đúng tuyệt đối | `BigDecimal`/đơn vị nguyên + giao dịch | Thread safety không đảm bảo độ chính xác thập phân |

Không tuyên bố adder luôn nhanh hơn atomics: benchmark cần dùng JMH, warm-up JIT, số luồng, tỷ lệ đọc/ghi, kích thước khóa và môi trường đại diện. `System.nanoTime()` quanh một vòng lặp đơn giản thường chưa đủ bằng chứng để lựa chọn cơ chế đồng thời.

## 11. Lỗi thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| `long++` hoặc `volatile long++` giữa nhiều worker | Lost update | Adder, atomic hoặc lock |
| Gọi `adder.get()` | Không có API này | Dùng `sum()` |
| Cho rằng `sum()` nguyên tử | Snapshot nhiều cell thiếu tính nhất quán | Chỉ dùng cho metrics best effort, hoặc đợi writer |
| Dùng `sum() < limit` rồi `increment()` để giữ quota | Hai worker có thể cùng được cấp | CAS/lock/transaction |
| Gọi `sumThenReset()` khi worker vẫn cộng | Sai lệch cửa sổ, có thể không giữ mọi cập nhật | Điều phối cập nhật và reset |
| Xem `DoubleAdder` là `BigDecimal` đa luồng | `double` có sai số | Chọn biểu diễn phù hợp |
| Kỳ vọng kết quả floating-point luôn giống bit | Thứ tự cộng không cố định | Kiểm tra sai số phù hợp |
| Thay map counter đang được worker dùng | Worker có thể ghi vào counter cũ | Quy tắc ownership/epoch |
| Không giới hạn nhãn map | Tăng bộ nhớ vô hạn | Giới hạn miền nhãn |
| Cho rằng `LongAdder` không tràn | Vẫn là `long` | Đánh giá miền giá trị và điều kiện tràn |

## 12. Bài tập tự kiểm tra kèm lời giải

1. **8 worker gọi `LongAdder.increment()` mỗi worker 10.000 lần. Khi nào `sum()` chắc chắn đạt 80.000?**  
   Sau khi tất cả worker hoàn tất và không có cập nhật/reset nào khác, với điều kiện không tràn số.

2. **`LongAdder` có trả số thứ tự duy nhất trong lần `increment()` không?**  
   Không. `increment()` không trả giá trị; `sum()` không phải số thứ tự gắn với chính phép cập nhật. Có thể cân nhắc `AtomicLong.incrementAndGet()` cho cấp sequence.

3. **Vì sao `LongAdder.sum()` không thích hợp để kiểm tra quota chính xác?**  
   Không có snapshot nguyên tử, và riêng thao tác kiểm tra rồi cập nhật cũng cần được đồng bộ chung.

4. **`DoubleAdder` có `increment()` không?**  
   Không. Dùng `add(1.0)`.

5. **Sau khi worker kết thúc, `DoubleAdder` nhận 100 lần `0.75` cho tổng bao nhiêu?**  
   `75.0`. Đây là dữ liệu nhị phân biểu diễn chính xác và phép cộng trong miền không làm mất phần lẻ theo ví dụ.

6. **Tại sao gọi `sumThenReset()` trong lúc writer hoạt động không phù hợp để thống kê bắt buộc chính xác?**  
   Vì đọc và reset không phải thao tác nguyên tử trên toàn cấu trúc; cập nhật cạnh tranh có thể không được gắn đúng vào một kỳ thống kê.

7. **Vì sao kết hợp `ConcurrentHashMap.computeIfAbsent(k, ...)` với `LongAdder` thường được dùng?**  
   Nó tạo/tra cứu counter dùng chung theo khóa an toàn ở cấp map, rồi mỗi lần `increment()` có thể thực hiện đồng thời.

8. **Nếu `DoubleAdder` tính tiền, điều gì sai về mặt số học?**  
   `double` không biểu diễn chính xác mọi số thập phân và thứ tự cộng có thể thay đổi kết quả. Dùng mô hình số thập phân/chia đơn vị chính xác hơn.

## 13. Ghi nhớ và tài liệu

`LongAdder` và `DoubleAdder` giúp các luồng **cộng dồn số liệu thống kê** khi có contention. Lợi ích chủ yếu là giảm áp lực cập nhật trên một vị trí nguyên tử. Đổi lại, `sum()` không cam kết một snapshot nguyên tử khi đang ghi; `sumThenReset()` không tạo ranh giới kỳ thống kê chính xác khi cạnh tranh; `DoubleAdder` vẫn tuân theo giới hạn IEEE 754.

Tài liệu API chính thức:

- [Java 21 — `LongAdder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [Java 21 — `DoubleAdder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/DoubleAdder.html)
- [Java 21 — `AtomicLong`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html)
- [Java 21 — `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
