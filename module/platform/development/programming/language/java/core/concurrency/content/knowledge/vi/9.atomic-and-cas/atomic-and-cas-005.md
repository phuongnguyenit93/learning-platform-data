# getAndUpdate(), updateAndGet() và accumulator trong Java Atomic & CAS

## Mục tiêu học tập

Khi nhiều thread cùng thay đổi một counter, ngưỡng giới hạn, giá trị lớn nhất hoặc một snapshot trạng thái, mẫu đọc–tính–ghi thông thường rất dễ gây **lost update**. Họ API `java.util.concurrent.atomic` hỗ trợ cập nhật dựa trên hàm mà không phải tự viết vòng lặp `compareAndSet` trong mỗi trường hợp. Nhưng tên gần giống nhau có thể gây nhầm giữa **giá trị trước khi cập nhật** và **giá trị sau khi cập nhật**; thêm nữa, thuật ngữ **accumulator** vừa chỉ các phương thức tích lũy trên atomic value, vừa chỉ các lớp như `LongAccumulator` và `DoubleAccumulator` với mục tiêu hiệu năng khác nhau.

Bài học giúp bạn:
- Dùng `getAndUpdate()` và `updateAndGet()` đúng với `UnaryOperator`, `IntUnaryOperator`, `LongUnaryOperator`.
- Phân biệt `getAndAccumulate(x, fn)` và `accumulateAndGet(x, fn)` với `BinaryOperator`; hiểu rõ thứ tự hai đối số.
- Giải thích cập nhật nguyên tử bằng **CAS**, thời điểm cập nhật có hiệu lực và vì sao callback có thể được tính lại nhiều lần.
- Tránh side effect trong callback, đếm sai thành công, overflow, tái sử dụng object mutable và suy diễn sai về tính nguyên tử của nhiều biến.
- Lựa chọn `AtomicInteger/AtomicLong/AtomicReference` so với `LongAdder/LongAccumulator/DoubleAccumulator` tùy nhu cầu **đúng tuyệt đối khi ra quyết định** hay **thống kê throughput cao**.
- Tự chạy ví dụ **Java 17+** minh họa unary update, binary accumulation, xử lý tồn kho cạnh tranh, snapshot immutable và accumulator thống kê.

**Phạm vi:** Java SE, Java Memory Model và concurrency nói chung, không đề cập các API hoặc cấu hình riêng của Spring vì chúng có chương độc lập.

## 1. Vì sao read–modify–write thường gặp race condition?

Giả sử hai thread cùng tăng một biến:

~~~java
int value = sharedCount;
sharedCount = value + 1;
~~~

Kể cả khi `sharedCount` là `volatile`, chuỗi **đọc → tính → ghi** vẫn gồm nhiều bước. Lịch chạy có thể là:

~~~text
Ban đầu sharedCount = 0

Thread A                Thread B
--------                --------
đọc 0
                        đọc 0
tính 1
                        tính 1
ghi 1
                        ghi 1

Đã có hai lần tăng, nhưng kết quả cuối có thể chỉ là 1.
~~~

**Volatile** mang bảo đảm visibility và ordering cho từng thao tác đọc/ghi tương ứng; nó **không biến** hai dòng trên thành một transaction. Nếu chỉ cần tăng một đơn vị, `AtomicInteger.incrementAndGet()` hoặc `getAndIncrement()` đã có semantics phù hợp. Nhưng nếu chuyển đổi phức tạp như “chỉ giảm nếu còn dương”, “đặt giá trị tối đa bằng giới hạn” hay “gộp snapshot theo một công thức”, các phương thức cập nhật bằng hàm rất hữu ích.

Một thay đổi atomic cần có **đơn vị trạng thái rõ ràng**:
- `AtomicInteger` cập nhật **một `int`**.
- `AtomicLong` cập nhật **một `long`**.
- `AtomicReference<V>` cập nhật **một tham chiếu `V`**; nếu `V` là record immutable chứa nhiều trường, một lần thay tham chiếu có thể công bố **một snapshot nhất quán**.
- `LongAccumulator`/`DoubleAccumulator` là những bộ tích lũy có thể **phân tán cập nhật nội bộ để giảm contention**, nên semantics đọc/reset khác với một atomic value đơn.

## 2. Bốn phương thức cốt lõi: unary và accumulator

| Phương thức | Hàm nhận gì? | Biến đổi logic | Giá trị trả về |
| --- | --- | --- | --- |
| `getAndUpdate(fn)` | Giá trị hiện tại | `new = fn(current)` | **Giá trị cũ**, trước lần cập nhật thành công |
| `updateAndGet(fn)` | Giá trị hiện tại | `new = fn(current)` | **Giá trị mới**, sau lần cập nhật thành công |
| `getAndAccumulate(x, fn)` | Giá trị hiện tại và `x` | `new = fn(current, x)` | **Giá trị cũ** |
| `accumulateAndGet(x, fn)` | Giá trị hiện tại và `x` | `new = fn(current, x)` | **Giá trị mới** |

Ở bảng này, “cũ” và “mới” là giá trị gắn với **thao tác atomic riêng đang thực hiện**. Nếu một thread khác cập nhật ngay sau đó, lần gọi `get()` kế tiếp có thể trả một giá trị khác; đừng nghĩ giá trị mà `updateAndGet` trả về nhất thiết vẫn là giá trị hiện hành vào thời điểm caller dùng nó.

### 2.1. Unary update

Với `AtomicInteger`, phương thức nhận một `IntUnaryOperator`:

~~~java
int previous = counter.getAndUpdate(current -> current * 2);
int updated = counter.updateAndGet(current -> current + 3);
~~~

`current` được thư viện đưa vào hàm ở mỗi lần thử cập nhật, **không** nhất thiết giống một lần `counter.get()` mà caller đã thực hiện trước đó. Tương tự, `AtomicLong` nhận `LongUnaryOperator`; `AtomicReference<V>` nhận `UnaryOperator<V>`.

Dấu **getAnd...** ở đầu tên nhắc rằng method trả giá trị **trước** phép thay đổi. Dấu **...AndGet** ở cuối tên nhắc rằng method trả giá trị **sau** phép thay đổi.

### 2.2. Binary accumulation

Với `AtomicInteger`:

~~~java
int previous = counter.getAndAccumulate(5, (current, x) -> current + x);
int updated = counter.accumulateAndGet(7, Math::max);
~~~

Khác unary update, hàm nhận **hai** đối số: **giá trị hiện tại trước**, **giá trị truyền vào method sau**. Với `AtomicLong` là `LongBinaryOperator`; với `AtomicReference<V>` là `BinaryOperator<V>`.

Đừng nhầm:

~~~java
// Đúng khi nghiệp vụ là current - delta:
counter.accumulateAndGet(4, (current, delta) -> current - delta);

// Ngược lại, phép này mang nghĩa delta - current:
counter.accumulateAndGet(4, (current, delta) -> delta - current);
~~~

Với phép giao hoán như cộng, lỗi đảo đối số thường khó phát hiện; với trừ, chia, ghép chuỗi hoặc combine record có thứ tự, nó đổi hoàn toàn ý nghĩa.

### 2.3. Atomic không đồng nghĩa tất cả callback chỉ chạy một lần

Các update method có thể phải thử lại khi CAS thất bại do thread khác vừa thay đổi giá trị. Vì vậy các tài liệu API yêu cầu update function **không có side effect**. Một lời gọi method chỉ có một kết quả cập nhật atomic, nhưng hàm do bạn truyền vào **có thể được tính lại**.

~~~text
Thread A                         Thread B
--------                         --------
đọc state = 10
tính fn(10) -> 11
                                 thay state: 10 -> 20 (CAS thành công)
CAS(10,11) thất bại
đọc lại state = 20
tính fn(20) -> 21
CAS(20,21) thành công

Trạng thái cuối: 21.
fn của A đã chạy hai lần dù chỉ một cập nhật của A thành công.
~~~

Đây là một lịch chạy **có thể xảy ra**, không phải cam kết mọi JVM phải gọi function hai lần. Thông thường thư viện lặp tới khi một phép cập nhật thành công; không bảo đảm một số lần thử tối đa khi contention.

## 3. Ví dụ Java 17: getAndUpdate khác updateAndGet

Tạo file **`UnaryUpdateDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class UnaryUpdateDemo {
    public static void main(String[] args) {
        AtomicInteger value = new AtomicInteger(10);

        int before = value.getAndUpdate(current -> current * 2);
        System.out.printf(
                "getAndUpdate returned=%d current=%d%n",
                before, value.get());

        int after = value.updateAndGet(current -> current + 3);
        System.out.printf(
                "updateAndGet returned=%d current=%d%n",
                after, value.get());
    }
}
~~~

Chạy:

~~~bash
javac UnaryUpdateDemo.java
java UnaryUpdateDemo
~~~

Stdout chính xác khi không có thread nào khác thay đổi `value`:

~~~text
getAndUpdate returned=10 current=20
updateAndGet returned=23 current=23
~~~

Diễn giải:
1. Bắt đầu là `10`. `getAndUpdate(current -> current * 2)` thay giá trị thành 20 nhưng **trả 10**.
2. `updateAndGet(current -> current + 3)` thay giá trị từ 20 thành 23 và **trả 23**.
3. Hai phép cập nhật đều atomic; ví dụ không có tranh chấp nên những lần `get()` sau đó thấy giá trị tương ứng.
4. Nếu có thread thứ ba cập nhật cùng `value` giữa method và `get()`, phần `current` được in ở lần `get()` sau có thể khác giá trị mà method trả về. **Atomicity chỉ áp dụng tại từng method**, không bao trọn cả câu lệnh in tiếp theo.

### Trường hợp dùng thực tế

- `getAndUpdate` phù hợp khi caller cần **giá trị trước** để xác định tác động của hành động, ví dụ claim một đơn vị tài nguyên nếu `previous > 0`.
- `updateAndGet` phù hợp khi caller muốn **snapshot sau khi thay đổi**, ví dụ tính giá trị hạn mức sau điều chỉnh.
- Nếu chỉ cần tăng/cộng một lượng cố định, `getAndIncrement`, `incrementAndGet`, `getAndAdd` và `addAndGet` thường ngắn, rõ và có thể hiệu quả hơn một lambda tổng quát.
- Đừng dùng `set(get() + delta)` để thay thế: thao tác gồm hai method riêng vẫn có lost update.

## 4. Ví dụ Java 17: getAndAccumulate khác accumulateAndGet

Tạo file **`BinaryAccumulateDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class BinaryAccumulateDemo {
    public static void main(String[] args) {
        AtomicInteger number = new AtomicInteger(6);

        int before = number.getAndAccumulate(
                4, (current, multiplier) -> current * multiplier);

        System.out.printf(
                "getAndAccumulate returned=%d current=%d%n",
                before, number.get());

        int after = number.accumulateAndGet(5, Integer::sum);
        System.out.printf(
                "accumulateAndGet returned=%d current=%d%n",
                after, number.get());

        AtomicLong maximum = new AtomicLong(Long.MIN_VALUE);
        long oldMax = maximum.getAndAccumulate(-7L, Long::max);
        long newMax = maximum.accumulateAndGet(-2L, Long::max);

        System.out.printf(
                "maxBeforeIsIdentity=%b maxNow=%d returnedNew=%d%n",
                oldMax == Long.MIN_VALUE, maximum.get(), newMax);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BinaryAccumulateDemo.java
java BinaryAccumulateDemo
~~~

Stdout:

~~~text
getAndAccumulate returned=6 current=24
accumulateAndGet returned=29 current=29
maxBeforeIsIdentity=true maxNow=-2 returnedNew=-2
~~~

Giải thích:
- `getAndAccumulate(4, multiply)` gọi hàm với `current=6` và `multiplier=4` để tạo 24; giá trị trả về là **6**.
- `accumulateAndGet(5, Integer::sum)` cập nhật `24 + 5 = 29`, trả **29**.
- Với một phép lấy **max** khi có thể gặp giá trị âm, `Long.MIN_VALUE` là giá trị khởi tạo hợp lý. Nếu khởi tạo max bằng 0, tập toàn số âm sẽ cho kết quả sai.
- `Long::max` là một hàm tích lũy không cần biết lịch thực thi đối với mỗi cập nhật riêng, nhưng thứ tự các update thành công đồng thời vẫn không được caller dự đoán.

### Các ví dụ lambda thường dùng

~~~java
AtomicInteger bounded = new AtomicInteger(8);
bounded.updateAndGet(current -> Math.min(10, current + 5)); // thành 10

AtomicLong highWater = new AtomicLong(Long.MIN_VALUE);
highWater.accumulateAndGet(42L, Long::max); // thành 42

AtomicInteger remaining = new AtomicInteger(3);
int previous = remaining.getAndUpdate(
        current -> current > 0 ? current - 1 : current);
boolean claimed = previous > 0; // true khi lấy được 1 đơn vị.
~~~

Các đoạn trên là **snippet**, giả định đã import các class tương ứng hoặc dùng tên đầy đủ. Chúng không được trình bày như một chương trình độc lập. Trong ví dụ giới hạn `Math.min(10,current+5)`, nếu có thể nhận giá trị gần `Integer.MAX_VALUE` thì phép cộng `current+5` có nguy cơ overflow; khi đó cần chọn biểu thức chống overflow hoặc validate range theo nghiệp vụ.

## 5. Cơ chế CAS dưới lớp API

Với `AtomicInteger`, một cách **mô phỏng ý nghĩa** của `updateAndGet` là:

~~~java
static int updateExample(
        java.util.concurrent.atomic.AtomicInteger atomic) {
    while (true) {
        int observed = atomic.get();
        int desired = observed + 1;

        if (atomic.compareAndSet(observed, desired)) {
            return desired;
        }
    }
}
~~~

Đây là **phương thức minh họa**, có thể đặt trong class chứa logic tương ứng. Nó cho thấy:
1. **Đọc** giá trị đang quan sát.
2. **Tính** giá trị mới từ snapshot đó.
3. **CAS** chỉ ghi nếu state vẫn bằng giá trị kỳ vọng.
4. Nếu thất bại, **lặp lại** với state mới.

`getAndUpdate` tương tự về ý nghĩa nhưng trả giá trị `observed` của lần CAS thành công. Implementation thực tế có thể có tối ưu nội bộ, không buộc phải triển khai chính xác từng dòng như snippet này.

### Điểm tuyến tính hóa (linearization point)

Một lần update thành công có thể được suy luận như đã diễn ra nguyên tử tại thời điểm CAS thành công. Hai thread đều gọi `updateAndGet(x -> x + 1)` trên cùng một `AtomicInteger` sẽ không làm mất cập nhật, dù các callback có thể được tính nhiều lần.

**Nhưng:** phương thức chỉ bảo vệ atomicity của **một vị trí trạng thái**, không tự gộp thao tác với database, log hay một biến atomic khác. Nếu hai trường `available` và `sold` được cập nhật bằng **hai** atomic riêng, observer vẫn có thể thấy trạng thái trung gian giữa hai lần CAS.

### Visibility và ordering

Các phương thức cập nhật mạnh trên lớp atomic có hiệu ứng bộ nhớ được tài liệu hóa, liên quan đến `VarHandle.compareAndSet`. Không cần tự thêm `volatile` vào giá trị được lớp atomic quản lý. Tuy nhiên, khi trạng thái logic gồm những field bên ngoài object atomic, bạn vẫn phải xác định quan hệ happens-before và invariant cho những field đó. Không suy rằng một CAS trên counter tự “khóa” tất cả dữ liệu ứng dụng.

## 6. Quy tắc vàng: callback phải side-effect-free

### 6.1. Những điều không nên làm trong update function

Một cách dùng nguy hiểm:

~~~java
AtomicInteger remaining = new AtomicInteger(10);

// SAI: side effect có thể chạy nhiều lần khi CAS phải thử lại.
remaining.updateAndGet(current -> {
    chargeCustomer();        // Gọi thanh toán bên ngoài.
    sendNotification();      // Gửi thông báo bên ngoài.
    return current - 1;
});
~~~

Đây là **ví dụ sai có chủ đích**, không phải class chạy độc lập; `chargeCustomer` và `sendNotification` giả định tồn tại. Khi contention, callback có thể chạy lại, khiến thanh toán hoặc thông báo diễn ra nhiều lần dù chỉ một phép cập nhật atomic hoàn tất.

Các loại side effect cần tránh trong hàm update:
- Ghi file, ghi database, gọi mạng, gửi email/thanh toán.
- Sửa một object khác hoặc tăng counter ghi nhận “số lần thành công”.
- Ghi log “đã hoàn tất thành công” trong callback; có thể log cả lần CAS bị hủy.
- Sinh ID nghiệp vụ không được phép tạo lại hoặc consume một giá trị của queue.
- Dựa vào dữ liệu mutable không được đồng bộ, khiến callback thiếu tính xác định giữa các lần thử.

Một hàm tốt có thể viết như **hàm thuần**:

~~~java
current -> current > 0 ? current - 1 : current
(current, delta) -> current + delta
(previous, sample) -> Math.max(previous, sample)
~~~

Dù cùng hàm được gọi nhiều lần, nó chỉ tạo kết quả từ input và không thay đổi thế giới bên ngoài. **Không có bảo đảm callback được gọi đúng một lần**.

### 6.2. Side effect sau khi method trả về có an toàn tuyệt đối không?

Không tự động. Nếu một thread claim tài nguyên bằng cách giảm counter nguyên tử, một lời gọi method trả về có thể xác định **claim được hay không**; sau đó caller mới gửi yêu cầu nghiệp vụ. Nhưng nếu gửi yêu cầu thất bại, bị timeout hoặc retry, vẫn cần thiết kế idempotency, hoàn trả/bù trừ hoặc giao thức transaction riêng.

Atomic update là một thao tác **trong bộ nhớ JVM**. Nó không tự tạo transaction kết hợp với payment gateway, database hoặc hệ thống khác. Đối với sự kiện “chỉ được thanh toán đúng một lần”, thường phải có một trạng thái nghiệp vụ/ID idempotency an toàn ở hệ thống xử lý thanh toán, chứ không dựa duy nhất vào atomic local.

### 6.3. Exception trong callback

Nếu hàm cập nhật ném exception, **lần gọi này không hoàn tất cập nhật được tính từ callback lỗi**. Tuy nhiên, một thread khác vẫn có thể cập nhật atomic value trong khoảng thời gian đó; không được suy từ exception rằng toàn bộ trạng thái chung vẫn như ban đầu. Tránh hàm update làm một nửa side effect rồi ném lỗi, vì CAS không rollback những side effect đã xảy ra.

Với kiểm soát overflow:

~~~java
AtomicInteger amount = new AtomicInteger(Integer.MAX_VALUE);
amount.updateAndGet(current -> Math.addExact(current, 1));
~~~

Đây là snippet minh họa: `Math.addExact` ném `ArithmeticException` khi cộng tràn `int` thay vì âm thầm wrap. Các phép cộng trên `AtomicInteger` thông thường là cộng kiểu `int` Java, vốn có thể overflow theo biểu diễn hai bù. Nếu nghiệp vụ cần số không âm hoặc giới hạn chặt, phải đặt predicate và xử lý overflow trong hàm cập nhật.

## 7. Ví dụ Java 17: nhiều worker claim số lượng hữu hạn

Yêu cầu: có đúng 100 đơn vị tồn kho. Tám worker, mỗi worker thử bán 50 lần. **400 lần thử** cạnh tranh nhau nhưng không được bán quá 100; số tồn kho không âm.

Tạo file **`AtomicStockDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicStockDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger remaining = new AtomicInteger(100);
        ExecutorService pool = Executors.newFixedThreadPool(8);

        try {
            List<Future<Integer>> futures = new ArrayList<>();

            for (int worker = 0; worker < 8; worker++) {
                futures.add(pool.submit(() -> {
                    int successes = 0;
                    for (int i = 0; i < 50; i++) {
                        int old = remaining.getAndUpdate(
                                current ->
                                        current > 0 ? current - 1 : current);
                        if (old > 0) {
                            successes++;
                        }
                    }
                    return successes;
                }));
            }

            int sold = 0;
            for (Future<Integer> future : futures) {
                sold += future.get();
            }

            int rest = remaining.get();
            System.out.printf(
                    "sold=%d remaining=%d invariant=%b%n",
                    sold, rest, sold + rest == 100 && rest >= 0);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac AtomicStockDemo.java
java AtomicStockDemo
~~~

Stdout khi cả tám task hoàn thành bình thường:

~~~text
sold=100 remaining=0 invariant=true
~~~

Tại sao deterministic?
1. `getAndUpdate` thực hiện cập nhật atomic với hàm `current > 0 ? current - 1 : current`.
2. Nếu giá trị **trước** cập nhật lớn hơn 0, đúng một claim thành công; nếu đã 0, số tồn giữ nguyên và claim thất bại.
3. Tổng 400 lần thử, vượt số lượng 100, nên sau mọi task kết thúc có 100 thành công và 300 thất bại; không quan trọng thread nào thắng.
4. `successes++` nằm **ngoài callback**, chỉ sau khi method atomic đã trả về, nên không đếm trùng khi CAS retry.
5. `Future.get()` chờ và phát hiện exception; số `sold` được cộng ở main sau khi task hoàn thành, không phải một atomic field thứ hai cần cập nhật đồng thời.

**Giới hạn:** snapshot `sold + remaining` chỉ được tính sau khi hoàn tất. Nếu hệ thống yêu cầu một thread khác đọc đồng thời **cả hai trường** và luôn thấy invariant `sold + remaining == 100`, phải gói cả hai trong **một state atomic** (ví dụ `AtomicReference` tới record immutable) hoặc dùng lock; hai biến atomic độc lập không tạo snapshot đa trường.

## 8. AtomicReference + record: accumulator cho một snapshot nhiều trường

`AtomicReference<T>` hỗ trợ cùng họ phương thức nhưng thao tác trên **một tham chiếu**. Khi `T` là value object immutable, ta có thể cập nhật nhiều trường một cách nhất quán bằng cách **thay toàn bộ snapshot**, không sửa object cũ.

Tạo file **`ReferenceAccumulatorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ReferenceAccumulatorDemo {
    private record Stats(long count, long sum) {}

    public static void main(String[] args) throws Exception {
        AtomicReference<Stats> stats =
                new AtomicReference<>(new Stats(0, 0));

        Stats before = stats.getAndAccumulate(
                new Stats(1, 7),
                (current, delta) ->
                        new Stats(
                                current.count() + delta.count(),
                                current.sum() + delta.sum()));

        Stats after = stats.get();
        System.out.printf(
                "beforeCount=%d beforeSum=%d nowCount=%d nowSum=%d%n",
                before.count(), before.sum(),
                after.count(), after.sum());

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> tasks = new ArrayList<>();

            for (int i = 0; i < 5; i++) {
                tasks.add(pool.submit(() -> stats.updateAndGet(
                        current -> new Stats(
                                current.count() + 1,
                                current.sum() + 2))));
            }

            for (Future<?> task : tasks) {
                task.get();
            }

            Stats finalSnapshot = stats.get();
            System.out.printf(
                    "finalCount=%d finalSum=%d%n",
                    finalSnapshot.count(), finalSnapshot.sum());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac ReferenceAccumulatorDemo.java
java ReferenceAccumulatorDemo
~~~

Stdout:

~~~text
beforeCount=0 beforeSum=0 nowCount=1 nowSum=7
finalCount=6 finalSum=17
~~~

Giải thích:
- `getAndAccumulate(new Stats(1,7), combine)` cập nhật từ `Stats(0,0)` sang `Stats(1,7)` và **trả object cũ**.
- Năm task tiếp tục dùng `updateAndGet` để tạo năm snapshot mới, mỗi snapshot cộng một vào count và hai vào sum. Kết quả cuối là `count=6`, `sum=7 + 5*2 = 17`.
- Hai field là kiểu `long` trong record và không thay đổi sau construction, nên **một lần `AtomicReference.get()`** trả về một phiên bản nhất quán để đọc cả hai.
- Hàm combine/update chỉ tạo object mới và không có side effect bên ngoài, nên có thể được tính lại an toàn khi CAS contention.

Một lỗi tinh vi cần tránh:

~~~java
long count = stats.get().count();
long sum = stats.get().sum();  // Có thể là phiên bản khác.
~~~

Nếu thread khác cập nhật giữa hai lần `get()`, hai biến được ghép từ **hai snapshot khác nhau**. Muốn có một snapshot nhất quán, phải lấy **một lần**:

~~~java
Stats snapshot = stats.get();
long count = snapshot.count();
long sum = snapshot.sum();
~~~

Hai đoạn này là snippet bên trong class có `Stats` và `stats` được khai báo; không phải chương trình chạy độc lập.

### Giới hạn khi dùng AtomicReference

- Atomicity là của **tham chiếu**. Nếu tham chiếu trỏ đến object mutable mà bên khác sửa trực tiếp, `AtomicReference` không tự làm những mutation đó atomic.
- Record có `List<Person>` hoặc array mutable **không tự deep-immutable**; cần defensive copy hoặc cấu trúc immutable phù hợp.
- Các callback `getAndUpdate/updateAndGet/getAndAccumulate/accumulateAndGet` có thể được gọi lại. Việc tạo value object mới không gây vấn đề logic, nhưng có allocation/GC cost dưới contention.
- Nếu hai object có cùng nội dung nhưng là hai tham chiếu khác nhau, các phép CAS trên `AtomicReference` làm việc dựa trên **tham chiếu kỳ vọng**. Tránh suy luận CAS dựa trên `equals()` thay vì equality của reference.
- Có những thuật toán CAS phức tạp gặp **ABA problem** (state chuyển A→B→A khiến giá trị quan sát có vẻ không đổi); nếu cần phiên bản/generation, có thể gói version vào immutable snapshot hoặc nghiên cứu `AtomicStampedReference`. Không mặc định mọi reference update đều gặp ABA.

## 9. Accumulator có hai ý nghĩa: method trên Atomic* và lớp LongAccumulator

Đây là chỗ dễ lẫn nhất khi đọc API.

**Nhóm 1 — method `getAndAccumulate/accumulateAndGet`:**
- Thuộc `AtomicInteger`, `AtomicLong`, `AtomicReference` và họ atomic array/updater tương ứng.
- Cập nhật **một giá trị/vị trí trạng thái** bằng một hàm binary.
- Trả giá trị **trước/sau** lần cập nhật atomic thành công.
- Phù hợp cả các quyết định check-update mạnh, ví dụ giới hạn tài nguyên hoặc một snapshot cần tính đúng theo phép cập nhật.

**Nhóm 2 — lớp `LongAccumulator`/`DoubleAccumulator`:**
- Dành cho **thống kê/tổng hợp giá trị khi nhiều thread cùng cập nhật**, có thể phân tán trạng thái nội bộ thành nhiều ô để giảm contention.
- Gọi `accumulate(x)` để đưa một giá trị mẫu vào; không trả về “giá trị cũ/mới” của mỗi lần gọi.
- Gọi `get()` để tổng hợp giá trị hiện hành từ các ô; **khi có cập nhật đồng thời, đây không phải snapshot atomic**.
- `reset()` và `getThenReset()` phù hợp với thời điểm không còn writer cập nhật; nếu gọi cạnh tranh với update, kết quả có thể không đại diện chính xác một ranh giới thời gian.
- Hàm tích lũy nên **side-effect-free**, và để có kết quả không phụ thuộc thứ tự thực thi, nên **kết hợp (associative) và giao hoán (commutative)**.

### 9.1. Lớp LongAccumulator dùng identity

Khởi tạo:

~~~java
LongAccumulator maximum =
        new LongAccumulator(Long::max, Long.MIN_VALUE);
~~~

Tham số thứ nhất là `LongBinaryOperator` kết hợp giá trị tích lũy hiện có và mẫu mới; tham số thứ hai là **identity element**.

Một identity tốt phải thỏa:

~~~text
combine(identity, x) == x
combine(x, identity) == x
~~~

Đối với `max` trên toàn bộ miền `long`, `Long.MIN_VALUE` là identity phù hợp. Đối với `sum`, identity là 0; đối với tích thì identity là 1, nhưng phải xét overflow.

Nếu dùng `new LongAccumulator(Long::max, 0)` và mọi mẫu đều âm, kết quả sẽ sai vì 0 lớn hơn mọi mẫu. **Identity không phải “giá trị mặc định tùy ý”.**

### 9.2. Thứ tự tích lũy không được bảo đảm

Với `LongAccumulator`, JVM có thể phân tán update giữa nhiều ô nội bộ, rồi kết hợp lại. Bởi vậy phép toán như max, min, sum số nguyên (theo quy tắc overflow của Java nếu có) hợp với thứ tự bất kỳ. Phép trừ, ghép text có thứ tự, hoặc một hàm tính theo sequence thường **không phù hợp**. Nếu cần áp dụng một trình tự nghiệp vụ cụ thể, sử dụng owner tuần tự hoặc một giao thức có thứ tự rõ ràng.

**Floating-point:** phép cộng `double` không kết hợp chính xác theo số thực vì rounding và đặc thù IEEE 754. Với `DoubleAccumulator` hoặc `DoubleAdder`, thay đổi thứ tự gộp có thể tạo sai lệch làm tròn; không hứa kết quả bit-for-bit giống một phép cộng tuần tự theo thứ tự cố định. Đối với tiền, cân nhắc biểu diễn đơn vị nguyên nhỏ nhất hoặc `BigDecimal` với giao thức đồng bộ thích hợp, thay vì dùng `double` như một số tiền chính xác tuyệt đối.

## 10. Ví dụ Java 17: LongAccumulator cho số liệu nhiều thread

Tạo file **`LongAccumulatorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAccumulator;

public class LongAccumulatorDemo {
    public static void main(String[] args) throws Exception {
        LongAccumulator maximum = new LongAccumulator(
                Long::max, Long.MIN_VALUE);
        LongAccumulator sum = new LongAccumulator(Long::sum, 0L);

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> jobs = new ArrayList<>();

            for (int worker = 0; worker < 4; worker++) {
                final int start = worker * 25 + 1;
                jobs.add(pool.submit(() -> {
                    for (int number = start; number < start + 25; number++) {
                        maximum.accumulate(number);
                        sum.accumulate(number);
                    }
                }));
            }

            for (Future<?> job : jobs) {
                job.get();
            }

            System.out.printf(
                    "max=%d sum=%d%n", maximum.get(), sum.get());

            long previousMax = maximum.getThenReset();
            System.out.printf(
                    "beforeReset=%d identityRestored=%b%n",
                    previousMax, maximum.get() == Long.MIN_VALUE);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LongAccumulatorDemo.java
java LongAccumulatorDemo
~~~

Stdout chính xác sau khi mọi task hoàn thành bình thường:

~~~text
max=100 sum=5050
beforeReset=100 identityRestored=true
~~~

Lý do kết quả xác định:
- Bốn worker xử lý các đoạn số nguyên `1..25`, `26..50`, `51..75` và `76..100`. Tất cả mẫu từ 1 tới 100 được đưa vào đúng một lần.
- `Long::max` và `Long::sum` là các phép phù hợp để tổng hợp không phụ thuộc thứ tự cho tập dữ liệu này; `1+2+...+100 = 5050`.
- `Future.get()` xác nhận mọi job đã xong trước khi main gọi `get()`.
- `getThenReset()` được gọi **sau khi không còn concurrent update**, nên nhận max 100 rồi đặt lại về identity `Long.MIN_VALUE`. Nếu gọi trong lúc writer vẫn chạy, API không bảo đảm một ranh giới cập nhật chính xác.

**Không dùng `LongAccumulator` để quyết định “chỉ bán nếu còn tồn kho” theo dạng `if (accumulator.get() > 0) accumulator.accumulate(-1)`.** `get()` không phải snapshot nguyên tử khi có update đồng thời và chuỗi check-then-accumulate cũng không atomic. Với resource quota, dùng `AtomicInteger.getAndUpdate`, CAS hoặc lock để bảo vệ **cả predicate và thay đổi**.

## 11. So sánh AtomicLong, LongAdder và LongAccumulator

| Tiêu chí | `AtomicLong` | `LongAdder` | `LongAccumulator` |
| --- | --- | --- | --- |
| Giá trị logic | Một `long` nguyên tử | Tổng tích lũy qua nhiều ô nội bộ | Tích lũy qua nhiều ô với hàm tùy chọn |
| Update nổi bật | `incrementAndGet`, `getAndUpdate`, `accumulateAndGet` | `add`, `increment`, `decrement` | `accumulate(x)` |
| Có trả old/new tại mỗi update không? | **Có** với các method tương ứng | **Không** | **Không** |
| Đọc khi writer cạnh tranh | `get()` là đọc atomic của một giá trị | `sum()` không phải snapshot atomic | `get()` không phải snapshot atomic |
| Tránh lost update cho một phép read-modify-write? | **Có** qua update/CAS | Tích lũy số liệu an toàn, không cung cấp check-then-act atomic | Tích lũy số liệu an toàn, không cung cấp check-then-act atomic |
| Hàm tích lũy | Unary/binary operator trên một state | Phép cộng chuyên dụng | Custom `LongBinaryOperator` |
| Tình huống phù hợp | Counter chính xác, quota, high-water mark có trả giá trị | Counter thống kê nhiều writer | Max/min/sum hoặc metric associative/commutative nhiều writer |
| Trade-off | CAS contention trên một giá trị | Nhiều ô, chi phí bộ nhớ, đọc aggregate | Nhiều ô, chi phí bộ nhớ, cần identity/function đúng |

`LongAdder` tương ứng với trường hợp cộng của `LongAccumulator` với identity 0 về mặt chức năng. Dưới contention cao, các adder/accumulator dạng phân tán thường đạt throughput cập nhật tốt hơn một atomic counter tập trung, nhưng phải chấp nhận giới hạn đọc/reset và chi phí bộ nhớ. **Không có một lớp nào luôn nhanh nhất** cho mọi workload; đo bằng benchmark phù hợp và xem đúng workload có cần một giá trị linearizable hay không.

### Khi cần nhiều metric cùng snapshot

Giả sử một hệ thống dùng hai `LongAdder` cho `requests` và `errors`. Sau này muốn đọc “tỉ lệ lỗi” bằng cách gọi `sum()` trên từng adder, hai lần đọc có thể thuộc **hai thời điểm khác nhau**; không phải một transaction thống nhất. Với dashboard chấp nhận approximation, điều đó có thể ổn. Với quyết định nghiệp vụ đòi exact consistency của nhiều trường, nên dùng một immutable record trong `AtomicReference`, lock hoặc snapshot protocol khác.

## 12. Một số nhầm lẫn quan trọng

### 12.1. Dùng getAndUpdate khi cần giá trị sau cập nhật

~~~java
int updated = counter.getAndUpdate(x -> x + 1);
~~~

Tên biến `updated` gây hiểu sai: phương thức trả giá trị **cũ**. Hãy dùng `updateAndGet` nếu cần số mới, hoặc đặt tên `previous` và xử lý theo ý nghĩa cũ.

### 12.2. Tưởng callback “đã được gọi” nghĩa là phép cập nhật “đã thành công”

~~~java
counter.updateAndGet(current -> {
    successCount++;
    return current + 1;
});
~~~

Sai nếu `successCount` là biến được cập nhật từ callback: CAS có thể thất bại và function bị gọi lại. Cũng có data race đối với `successCount++` nếu nhiều thread cùng sửa. Chuyển logic đếm thành công ra **sau khi method trả về**, hoặc thiết kế trạng thái tổng hợp trong một atomic snapshot nếu cần invariant chặt.

### 12.3. Dùng hai atomic riêng cho một invariant

~~~java
available.updateAndGet(x -> x - 1);
sold.updateAndGet(x -> x + 1);
~~~

Mỗi method atomic riêng, nhưng có khoảng thời gian giữa hai method. Một observer có thể thấy `available + sold` tạm sai. Muốn bảo vệ invariant đa trường, dùng lock chung hoặc `AtomicReference` tới immutable record và một lần update toàn snapshot.

### 12.4. Đổi chiều đối số accumulator

~~~java
balance.accumulateAndGet(amount, (current, delta) -> current - delta);
~~~

Hàm nhận **current trước, amount sau**; viết ngược thứ tự khi dùng phép trừ sẽ đổi phép tính. Với `LongAccumulator`, phép trừ cũng không phù hợp làm hàm tổng hợp không phụ thuộc thứ tự.

### 12.5. Gắn side effect vào hàm CAS

Không gọi thanh toán, I/O, sinh business ID dùng một lần, hoặc ghi log “thành công” trong callback. Một phép update thành công **không** ngụ ý callback chỉ chạy một lần.

### 12.6. Hiểu sai identity của LongAccumulator

`new LongAccumulator(Long::max, 0)` không đúng cho mọi input có thể âm. `Long.MIN_VALUE` mới là identity tự nhiên của `max` trên miền `long`.

### 12.7. Dùng LongAccumulator.get() để kiểm soát quota

`get()` khi có update đồng thời không là snapshot nguyên tử; compound action “đọc số còn lại rồi trừ” có race. Dùng `AtomicInteger/AtomicLong` với hàm cập nhật có predicate hoặc locking.

### 12.8. Cộng số nguyên mà bỏ qua overflow

`AtomicInteger.addAndGet` và `updateAndGet(x -> x + amount)` không tự ném exception khi overflow `int`; phép cộng theo Java có thể wrap. Dùng `Math.addExact` hoặc predicate kiểm tra giới hạn nếu overflow là lỗi nghiệp vụ.

### 12.9. Dùng immutable reference nhưng sửa object phía trong

`AtomicReference<List<String>>` chỉ cập nhật **tham chiếu** nguyên tử; không biến `ArrayList.add` thành thao tác thread-safe. Nếu muốn snapshot immutable, dùng value type/defensive copy và publish bản mới.

### 12.10. Gọi getThenReset khi vẫn có writers

`LongAccumulator.getThenReset()` không tạo ranh giới nguyên tử cho các writer đang chạy. Có thể bỏ hoặc gộp sai update tương ứng thời điểm chuyển kỳ thống kê; nếu cần ranh giới kỳ chính xác, điều phối writer dừng/quiescent hoặc thiết kế giao thức chuyển kỳ riêng.

## 13. Chọn API theo tình huống

**Tình huống A — cần trả giá trị cũ** khi cấp phát thứ tự hoặc claim slot: cân nhắc `getAndUpdate` / `getAndAccumulate`; với tăng 1 đơn giản có `getAndIncrement`.

**Tình huống B — cần trả giá trị sau cập nhật**: `updateAndGet` / `accumulateAndGet`; với cộng cố định có `addAndGet`.

**Tình huống C — chuyển đổi dựa trên một trạng thái**, ví dụ clamp vào biên, monotonic max, giảm có điều kiện: `getAndUpdate` hoặc `updateAndGet` với callback pure.

**Tình huống D — có thêm một giá trị đầu vào `x`**, ví dụ số lượng cộng thêm, mẫu đo mới, max với observation mới: `getAndAccumulate` hoặc `accumulateAndGet`; bảo đảm hàm nhận (`current`, `x`) đúng thứ tự.

**Tình huống E — state có nhiều trường nhưng cần snapshot nhất quán**: immutable record + `AtomicReference.updateAndGet` hay `accumulateAndGet`. Reader phải lấy **một snapshot một lần**, và không để reference tới nested mutable state lọt ra.

**Tình huống F — metric thống kê nhiều writers, không cần old/new mỗi update**: `LongAdder` (sum) hoặc `LongAccumulator` (max/min/custom). Chấp nhận `sum/get` khi cập nhật đồng thời không phải snapshot atomic.

**Tình huống G — giao dịch cập nhật nhiều tài nguyên ngoài JVM**: không thể “dùng một CAS” là xong; cần giao thức transaction/idempotency hoặc coordination của chính các hệ thống đó.

## 14. Checklist khi review code Atomic/CAS

1. **Invariant là gì?** Một biến atomic hay một tập trường cần cập nhật thống nhất?
2. **Caller cần old hay new?** Xác định rõ method trả về, đặt tên biến `previous/updated` nhất quán.
3. **Unary hay binary?** Unary nhận current; binary nhận current rồi x.
4. **Callback có pure không?** Không I/O, không gọi thanh toán, không ghi state ngoài atomic, không giả định gọi một lần.
5. **Callback có thể được retry an toàn không?** Chịu được contention và tính toán lại với current mới.
6. **Có overflow không?** Xử lý `int/long` theo yêu cầu nghiệp vụ; chọn `Math.addExact` nếu cần báo lỗi.
7. **Reference có trỏ tới immutable graph không?** Record có field chứa list/array mutable cần defensive copy.
8. **Đọc nhiều field có dùng cùng snapshot không?** Không gọi hai lần `state.get()` rồi trộn hai phiên bản.
9. **Side effect sau claim có thể thất bại không?** Thiết kế bù trừ/idempotency theo hệ thống ngoài JVM.
10. **Có dùng LongAdder/LongAccumulator để check-then-act không?** Nếu có, xem lại vì `get/sum` không phải ranh giới atomic khi concurrent writers.
11. **Hàm accumulator có identity đúng không?** Kiểm tra đối với số âm, giá trị biên và tập rỗng.
12. **Cần kết quả bất biến theo thứ tự không?** Với LongAccumulator, chọn toán tử associative/commutative; chú ý `double` rounding.
13. **Sau concurrent tasks có chờ và kiểm tra exception không?** Với executor, gọi `Future.get()` để không che lỗi.
14. **Đã đo hiệu năng trên workload thật chưa?** Xem throughput thành công, p95/p99 latency, contention, retry/GC và số lượng writer; không khẳng định “lock-free luôn nhanh”.
15. **Kết quả đưa ra có mô tả rõ boundary không?** Giá trị trả về từ một cập nhật atomic không đồng nghĩa snapshot nhất quán của toàn ứng dụng.

## 15. Câu hỏi tự kiểm tra

1. `AtomicInteger(10).getAndUpdate(x -> x * 2)` trả gì, giữ gì? **Trả 10, giữ 20**.
2. `AtomicInteger(10).updateAndGet(x -> x * 2)` trả gì? **Trả 20**, giá trị mới.
3. Với `getAndAccumulate(4, (a,b) -> a-b)`, đối số nào là state hiện tại? **`a`**, còn `b=4`.
4. Tại sao `counter.set(counter.get()+1)` vẫn có lost update? **Vì đọc và ghi tách thành hai operation**.
5. Tại sao callback của `updateAndGet` không được gửi email? **CAS có thể retry và callback được tính lại**.
6. Một thread khác đổi atomic value sau `updateAndGet` nhưng trước `get()`. Hai kết quả có thể khác nhau không? **Có**, vì mỗi method có linearization riêng.
7. `LongAccumulator.accumulate(x)` có trả giá trị old/new giống `AtomicLong.accumulateAndGet` không? **Không**, nó trả `void`.
8. `LongAccumulator.get()` có là snapshot atomic khi các writer vẫn đang cập nhật không? **Không**.
9. Tại sao `LongAccumulator(Long::max, 0)` có thể sai? **Nếu toàn bộ sample âm, 0 sẽ luôn thắng**.
10. Khi nào có thể gọi `LongAccumulator.getThenReset()` để đọc một kỳ đáng tin? **Khi đã điều phối không còn concurrent updates trong ranh giới đó**.
11. Hai `AtomicInteger` cho `available/sold` có đảm bảo observer thấy `available+sold==initial` ở mọi thời điểm không? **Không, phải cập nhật cả cặp theo một giao thức atomic chung**.
12. Dùng `AtomicReference<Stats>` với record immutable mang lại lợi ích gì? **Một lần thay tham chiếu công bố toàn snapshot, reader lấy một tham chiếu rồi đọc các field cùng phiên bản**.
13. `AtomicReference.compareAndSet` so sánh reference hay gọi `equals()` của object? **Tham chiếu kỳ vọng theo identity**.
14. Vì sao `LongAccumulator` cần hàm associative và commutative để có kết quả không phụ thuộc lịch cập nhật? **Thứ tự tích lũy giữa các ô/threads không được bảo đảm**.
15. `DoubleAccumulator` có đảm bảo tổng số thực bit-for-bit không phụ thuộc thứ tự không? **Không, floating-point rounding có thể làm kết quả khác**.
16. Với counter rất đơn giản cần tăng một lần, có nhất thiết dùng lambda không? **Không; `incrementAndGet` hoặc `getAndIncrement` rõ hơn**.

## Kết luận

`getAndUpdate()` và `updateAndGet()` đều **cập nhật nguyên tử bằng một hàm unary**, nhưng một method trả **giá trị cũ**, method kia trả **giá trị mới**. `getAndAccumulate(x,fn)` và `accumulateAndGet(x,fn)` làm tương tự với một hàm binary theo thứ tự đối số **(current, x)**. Các callback phải **không có side effect**, vì có thể bị gọi lại khi CAS cạnh tranh.

Đừng nhầm các method atomic đó với lớp `LongAccumulator`/`DoubleAccumulator` chuyên cho **tích lũy thống kê nhiều writers**: chúng không trả old/new tại mỗi update và phép đọc/reset khi đang cập nhật không phải snapshot atomic. Chọn API dựa trên invariant, nhu cầu trả về, khả năng đọc nhất quán và kết quả cần chính xác; chỉ tối ưu hiệu năng sau khi đã chứng minh đúng dưới concurrency.

## Tài liệu tham khảo Java SE 17

- [AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): `getAndUpdate`, `updateAndGet`, `getAndAccumulate`, `accumulateAndGet`.
- [AtomicLong](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): cập nhật kiểu `long` và memory semantics.
- [AtomicReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): unary/binary update của reference.
- [LongAccumulator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAccumulator.html): identity, accumulation order, get/reset.
- [LongAdder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): thống kê tổng khi nhiều writer.
- [DoubleAccumulator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/DoubleAccumulator.html): tích lũy double và giới hạn do thứ tự làm tròn.
- [Java Language Specification 17, Chapter 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Threads and Locks; happens-before.
