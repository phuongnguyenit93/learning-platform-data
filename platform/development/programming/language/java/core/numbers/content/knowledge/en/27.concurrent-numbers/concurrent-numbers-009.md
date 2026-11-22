# Atomic không có nghĩa tự phát hiện tràn số trong Java

## 1. Vấn đề: thao tác nguyên tử vẫn có thể trả về giá trị sai về mặt nghiệp vụ

Trong môi trường nhiều luồng, chúng ta dùng `AtomicInteger` hoặc `AtomicLong` để cập nhật bộ đếm mà không bị mất lượt tăng do các phép đọc–sửa–ghi xen kẽ. Nhưng **atomic (nguyên tử) chỉ mô tả cách các luồng quan sát một thao tác cập nhật; nó không đảm bảo phép toán số học có kiểm tra tràn**.

Ví dụ, bộ đếm `AtomicInteger` ở giá trị lớn nhất:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger(Integer.MAX_VALUE);
System.out.println(counter.incrementAndGet()); // -2147483648
~~~

Không có `ArithmeticException` nào được tự động ném. Giá trị `int` vượt giới hạn đã **quấn vòng** (*wrap around*) về `Integer.MIN_VALUE`, và thao tác tăng vẫn được thực hiện theo cơ chế nguyên tử. Một bộ đếm số yêu cầu không âm có thể bất ngờ thành số âm mặc dù hoàn toàn không gặp *lost update*.

Sau bài này, bạn cần phân biệt ba yêu cầu:

1. **Atomicity**: không để hai luồng giẫm lên cùng một cập nhật.
2. **Overflow detection**: phát hiện kết quả không biểu diễn được trong kiểu `int`/`long`.
3. **Business policy**: sau khi phát hiện tràn, hệ thống phải báo lỗi, từ chối cập nhật, bão hòa tại giới hạn hay chuyển sang miền số lớn hơn.

Một cấu trúc `Atomic*` mặc định chỉ giải quyết yêu cầu thứ nhất. Hai yêu cầu còn lại là trách nhiệm thiết kế của ứng dụng.

## 2. Cơ chế tràn số nguyên của Java

Kiểu nguyên có dấu trong Java có giới hạn cố định:

| Kiểu | Độ rộng | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: | ---: |
| `int` | 32 bit | `-2_147_483_648` | `2_147_483_647` |
| `long` | 64 bit | `-9_223_372_036_854_775_808` | `9_223_372_036_854_775_807` |

Với phép cộng/trừ số nguyên thông thường, khi kết quả toán học nằm ngoài miền biểu diễn, phần bit kết quả được giữ theo phép toán số nguyên Java và diễn giải lại theo kiểu có dấu. Ví dụ:

~~~java
int x = Integer.MAX_VALUE;
System.out.println(x + 1); // -2147483648

long y = Long.MIN_VALUE;
System.out.println(y - 1L); // 9223372036854775807
~~~

Đây là **kết quả quy định của ngôn ngữ**, không phải hành vi bất định và không phải ngoại lệ tự động.

Các method atomic dùng cùng miền giá trị và không làm cho số nguyên trở thành vô hạn:

~~~java
AtomicInteger a = new AtomicInteger(Integer.MAX_VALUE);
int old = a.getAndIncrement();  // old = 2147483647
int now = a.get();              // now = -2147483648
~~~

Điểm dễ gây nhầm: `getAndIncrement()` trả **giá trị trước khi tăng**, nên lần gọi làm tràn có thể trả về một số trông vẫn hợp lệ trong khi **trạng thái đã bị thay đổi thành số âm**. Ngược lại, `incrementAndGet()` trả ngay giá trị mới đã tràn.

Tương tự, `AtomicLong.addAndGet(1L)`, `getAndAdd(...)`, `decrementAndGet()` và các biến thể khác vẫn có thể làm tràn tại biên của `long` nếu sử dụng phép toán số nguyên thông thường.

## 3. Atomicity bảo đảm điều gì, và không bảo đảm điều gì?

Đối với `AtomicInteger` hoặc `AtomicLong`, các phương thức cập nhật nguyên tử bảo đảm mỗi cập nhật quan sát được theo cơ chế nhất quán của biến atomic: một phép `incrementAndGet` không bị tách thành thao tác đọc và ghi độc lập mà luồng khác có thể xen vào làm mất một increment.

Nếu 4 luồng, mỗi luồng gọi `incrementAndGet()` 10.000 lần trên cùng một bộ đếm khởi đầu ở 0, tổng cuối cùng là 40.000 **nếu không có ngoại lệ hoặc tràn** và tất cả cập nhật hoàn thành.

Tuy nhiên, atomicity **không cung cấp**:

- Tự phát hiện tràn `int`/`long`.
- Tự chứng minh giá trị luôn không âm hoặc luôn nằm trong một miền nghiệp vụ.
- Tự chặn việc ai đó sử dụng `set(...)` để gán giá trị ngoài chính sách.
- Một giao dịch nguyên tử xuyên nhiều biến atomic độc lập, nhiều bảng database hoặc nhiều service.
- Bất kỳ bảo đảm nào rằng giá trị đọc được giữa các lần cập nhật vẫn là snapshot bất biến.

Nói cách khác, `AtomicInteger` có thể thực hiện một cách hoàn hảo phép cộng 1 theo kiểu `int`, nhưng **kết quả kiểu `int`** có thể khác kết quả số nguyên toán học bạn mong muốn.

## 4. Cách phát hiện tràn: `Math.addExact` và các hàm *Exact*

Java cung cấp các hàm kiểm tra tràn trong `java.lang.Math`:

| Hàm | Mục đích | Khi ngoài miền |
| --- | --- | --- |
| `Math.addExact(a, b)` | Cộng `int` hoặc `long` có kiểm tra | `ArithmeticException` |
| `Math.subtractExact(a, b)` | Trừ có kiểm tra | `ArithmeticException` |
| `Math.multiplyExact(a, b)` | Nhân có kiểm tra | `ArithmeticException` |
| `Math.incrementExact(x)` | Tăng 1 có kiểm tra | `ArithmeticException` |
| `Math.decrementExact(x)` | Giảm 1 có kiểm tra | `ArithmeticException` |
| `Math.negateExact(x)` | Đổi dấu có kiểm tra | `ArithmeticException` |
| `Math.toIntExact(longValue)` | Chuyển `long` sang `int` có kiểm tra miền | `ArithmeticException` |

Ví dụ:

~~~java
System.out.println(Math.addExact(10, 20)); // 30
System.out.println(Math.incrementExact(7)); // 8

try {
    Math.addExact(Integer.MAX_VALUE, 1);
} catch (ArithmeticException e) {
    System.out.println("overflow detected");
}
~~~

Stdout:

~~~text
30
8
overflow detected
~~~

`Math.addExact` giúp phát hiện tràn **bên trong một phép toán**, nhưng chỉ gọi `Math.addExact` ở ngoài biến atomic chưa tạo ra cập nhật đồng thời an toàn.

Sai lầm phổ biến:

~~~java
AtomicInteger counter = new AtomicInteger(0);

// SAI trong môi trường nhiều luồng:
int proposed = Math.addExact(counter.get(), 1);
counter.set(proposed);
~~~

Hai luồng có thể cùng đọc 0, cùng tính 1, rồi cùng set 1. Không có overflow, nhưng vẫn bị **lost update**. Cần kết hợp phép tính Exact và một **cập nhật nguyên tử**.

## 5. Kết hợp kiểm tra tràn và cập nhật nguyên tử bằng `updateAndGet`

Cách ngắn gọn cho `AtomicInteger` là:

~~~java
AtomicInteger counter = new AtomicInteger(0);
int next = counter.updateAndGet(current -> Math.addExact(current, 1));
~~~

Phương thức `updateAndGet(IntUnaryOperator)` đọc trạng thái, áp dụng hàm và cập nhật bằng một cơ chế nguyên tử; khi có tranh chấp, hàm có thể bị gọi lại với giá trị mới. Kết quả trả về là giá trị đã cập nhật thành công.

Ví dụ cộng thêm một bước `delta`:

~~~java
static int checkedAdd(AtomicInteger counter, int delta) {
    return counter.updateAndGet(current -> Math.addExact(current, delta));
}
~~~

Với `AtomicLong`:

~~~java
static long checkedAdd(AtomicLong counter, long delta) {
    return counter.updateAndGet(current -> Math.addExact(current, delta));
}
~~~

Hai đoạn trên là các **phương thức minh họa**, cần đặt vào lớp Java với imports tương ứng. Một ví dụ chương trình chạy độc lập có đầy đủ imports và main nằm ở mục 8.

### Điều gì xảy ra khi tính toán ném ngoại lệ?

Nếu `Math.addExact(current, delta)` phát hiện tràn, nó ném `ArithmeticException` trước khi lần thử đó thực hiện bước cập nhật atomic thành công. Vì vậy, **lần gọi bị lỗi không áp dụng giá trị bị tràn**.

Tuy nhiên, trong chương trình nhiều luồng, các luồng **khác** vẫn có thể cập nhật bộ đếm trước hoặc sau khi phương thức ném lỗi. Không được diễn giải ngoại lệ thành khẳng định rằng “giá trị hiện tại của biến vẫn đúng bằng giá trị tôi vừa đọc” trong mọi hoàn cảnh.

Khi code khác vẫn được phép gọi `incrementAndGet()`, `set(...)` hoặc `getAndAdd(...)` trực tiếp lên cùng bộ đếm, bảo đảm “luôn phát hiện tràn” cũng bị phá vỡ. Hãy bọc counter trong một API duy nhất áp dụng chính sách kiểm tra, không công khai mutable reference cho caller tùy ý ghi.

### Vì sao callback phải thuần?

`updateAndGet` và `getAndUpdate` **có thể gọi lại hàm cập nhật** khi có luồng khác sửa giá trị giữa bước đọc và so sánh/ghi (CAS). Do đó:

~~~java
// KHÔNG nên: side effect có thể xảy ra nhiều lần khi CAS phải retry.
counter.updateAndGet(current -> {
    sendNotification(); // Không được đặt tác vụ gửi bên trong callback.
    return Math.addExact(current, 1);
});
~~~

Thông báo, ghi log nghiệp vụ có chi phí, chuyển tiền, phát sự kiện hoặc ghi database không được thực hiện như side effect không idempotent bên trong hàm update. Hàm nên chỉ biến đổi giá trị đầu vào thành giá trị mới theo cách xác định; thực hiện tác vụ phụ ở tầng khác theo hợp đồng xử lý thành công và lỗi. Chú ý ngay cả tác vụ sau khi update thành công cũng không tự trở thành một transaction nguyên tử xuyên atomic counter và hệ thống ngoài.

## 6. Vì sao kiểm tra trước bằng `get()` không đủ?

Đoạn sau trông hợp lý nhưng bị race:

~~~java
// SAI: kiểm tra và increment là hai thao tác riêng biệt.
if (counter.get() < Integer.MAX_VALUE) {
    counter.incrementAndGet();
}
~~~

Giả sử giá trị lúc đầu bằng `Integer.MAX_VALUE - 1`:

1. Luồng A đọc và xác nhận nhỏ hơn `Integer.MAX_VALUE`.
2. Luồng B cũng đọc và xác nhận nhỏ hơn `Integer.MAX_VALUE`.
3. A tăng bộ đếm đến `Integer.MAX_VALUE`.
4. B tăng tiếp: tràn về `Integer.MIN_VALUE`.

Cả hai phép `get` và `incrementAndGet` riêng lẻ đều atomic. Nhưng **cặp kiểm tra–cập nhật không phải một thao tác nguyên tử**.

Thay bằng:

~~~java
counter.updateAndGet(current -> Math.incrementExact(current));
~~~

Nếu hai luồng cùng cập nhật gần biên, một trong các lần thử có thể thành công đưa giá trị tới `Integer.MAX_VALUE`, còn lần thử cập nhật vượt biên bị từ chối bằng ngoại lệ. Điều kiện kiểm tra và kết quả số học được gắn vào cùng giá trị dùng cho cập nhật nguyên tử thành công.

Một cách khác khi cần kiểm soát hành vi đặc biệt là vòng lặp `compareAndSet`:

~~~java
static int incrementChecked(AtomicInteger counter) {
    while (true) {
        int current = counter.get();
        int next = Math.incrementExact(current);
        if (counter.compareAndSet(current, next)) {
            return next;
        }
    }
}
~~~

Khi CAS thất bại, vòng lặp đọc lại và tính lại dựa trên trạng thái mới. `compareAndSet` chỉ ghi nếu giá trị hiện hành vẫn bằng giá trị được mong đợi. Đây là khuôn mẫu cơ bản để gắn kiểm tra điều kiện vào cập nhật một biến atomic; cần chú ý tiến trình có thể lặp nhiều lần nếu tranh chấp cao.

**Quan trọng:** đoạn CAS trên kiểm tra tràn theo **giá trị quan sát được ở mỗi lần thử**. Nó không kết hợp nguyên tử với một bất biến nằm ở biến khác hoặc database.

## 7. Chọn chính sách khi tiến sát giới hạn

Chỉ phát hiện tràn chưa quyết định ứng dụng sẽ làm gì. Hợp đồng phải chỉ rõ một trong các hành vi thích hợp:

### A. Từ chối cập nhật và báo lỗi

Dùng `Math.addExact` trong `updateAndGet`, để ngoại lệ được chuyển thành lỗi nghiệp vụ hoặc kết quả rõ ràng ở ranh giới API.

- Phù hợp với bộ đếm không được mất thông tin.
- Giúp giám sát phát hiện sự cố cấu hình hoặc ước lượng kích thước sai.
- Cần xử lý retry: nếu client tự gửi lại cùng yêu cầu, đừng để tạo hiệu ứng trùng lặp ở nơi khác.

### B. Bão hòa tại ngưỡng (*saturating counter*)

Nếu hợp đồng cho phép “tối đa là MAX”, có thể dùng:

~~~java
static int saturatingIncrement(AtomicInteger counter) {
    return counter.updateAndGet(current ->
            current == Integer.MAX_VALUE ? Integer.MAX_VALUE : current + 1);
}
~~~

Đây là chính sách **bão hòa**, không phải “tăng chính xác số lần gọi”. Khi đã đạt MAX, các lần tăng tiếp theo bị mất về mặt đếm. Với trường hợp chỉ cộng số không âm và counter luôn trong miền đã xác thực, quy tắc trên dễ hiểu; với `delta` dương/âm tổng quát, phải định nghĩa cả biên dưới lẫn biên trên và tránh overflow ngay trong phép so sánh ngưỡng.

### C. Chuyển sang miền biểu diễn lớn hơn

- `AtomicLong` có miền lớn hơn `AtomicInteger`, nhưng **vẫn tràn**.
- `BigInteger` có precision tùy ý, có thể kết hợp `AtomicReference<BigInteger>` và cập nhật bằng `updateAndGet`.
- `BigDecimal` cần dùng khi có phần thập phân chính xác; chọn kiểu số và cơ chế đồng thời dựa trên miền thực tế.

Ví dụ dùng số nguyên lớn:

~~~java
import java.math.BigInteger;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<BigInteger> counter =
        new AtomicReference<>(BigInteger.valueOf(Long.MAX_VALUE));

BigInteger next = counter.updateAndGet(
        current -> current.add(BigInteger.ONE)
);

System.out.println(next); // 9223372036854775808
~~~

`BigInteger` không bị giới hạn 64 bit như `long`, nhưng kích thước số và chi phí cấp phát/tính toán tăng theo độ lớn. `AtomicReference<BigInteger>` tạo/cập nhật object mới, có thể chịu chi phí CAS retry khi nhiều luồng tranh chấp; điều này khác bản chất với một atomic primitive đơn giản.

### D. Phân đoạn số đo hoặc thay đổi mô hình

Với tổng số sự kiện trong hàng thập kỷ, một bộ đếm duy nhất có thể không phải mô hình tốt. Có thể lưu các bộ đếm theo khoảng thời gian hoặc partition rồi tổng hợp bằng kiểu số đủ lớn. Tuy nhiên, phân đoạn không tự giải quyết tràn nếu sau đó cộng dồn bằng kiểu `long` quá nhỏ.

Không nên âm thầm chọn chính sách wrap-around nếu người sử dụng hiểu counter là một tổng luôn tăng, không âm và chính xác.

## 8. Chương trình Java 17+ chạy độc lập

Tạo tệp `AtomicOverflowDemo.java`:

~~~java
import java.math.BigInteger;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicOverflowDemo {

    static int checkedAdd(AtomicInteger counter, int delta) {
        return counter.updateAndGet(value -> Math.addExact(value, delta));
    }

    static long checkedAdd(AtomicLong counter, long delta) {
        return counter.updateAndGet(value -> Math.addExact(value, delta));
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger ordinaryInt = new AtomicInteger(Integer.MAX_VALUE);
        System.out.println("wrapped int: " + ordinaryInt.incrementAndGet());

        AtomicLong ordinaryLong = new AtomicLong(Long.MAX_VALUE);
        System.out.println("wrapped long: " + ordinaryLong.addAndGet(1L));

        AtomicInteger checked = new AtomicInteger(Integer.MAX_VALUE);
        try {
            checkedAdd(checked, 1);
        } catch (ArithmeticException ex) {
            System.out.println("checked overflow caught");
        }
        System.out.println("checked after failure: " + checked.get());
        System.out.println("checked decrement: " + checkedAdd(checked, -1));

        AtomicInteger concurrent = new AtomicInteger(0);
        Thread[] threads = new Thread[4];

        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(() -> {
                for (int j = 0; j < 10_000; j++) {
                    checkedAdd(concurrent, 1);
                }
            });
            threads[i].start();
        }

        for (Thread thread : threads) {
            thread.join();
        }
        System.out.println("concurrent count: " + concurrent.get());

        AtomicReference<BigInteger> unbounded = new AtomicReference<>(
                BigInteger.valueOf(Long.MAX_VALUE)
        );
        BigInteger next = unbounded.updateAndGet(
                value -> value.add(BigInteger.ONE)
        );
        System.out.println("beyond long: " + next);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AtomicOverflowDemo.java
java AtomicOverflowDemo
~~~

Stdout mong đợi:

~~~text
wrapped int: -2147483648
wrapped long: -9223372036854775808
checked overflow caught
checked after failure: 2147483647
checked decrement: 2147483646
concurrent count: 40000
beyond long: 9223372036854775808
~~~

Giải thích kết quả:

1. Hai lệnh đầu chứng minh phép cộng atomic vẫn tràn theo giới hạn kiểu nguyên.
2. `checkedAdd(checked, 1)` ở ngưỡng MAX bị `Math.addExact` từ chối trước khi ghi giá trị mới, nên khi **không có luồng khác can thiệp**, `checked.get()` vẫn ở MAX.
3. Cộng `-1` hợp lệ và được thực hiện nguyên tử, đưa counter về `2147483646`.
4. Bốn luồng, mỗi luồng cập nhật 10.000 lần, cho đúng 40.000. Tất cả cập nhật đều hoàn tất trước khi đọc kết quả nhờ `Thread.join()`; số này nằm rất xa giới hạn `int`.
5. Bộ đếm `AtomicReference<BigInteger>` vượt giới hạn `long` mà không wrap.

Đây là ví dụ nhỏ minh họa ngữ nghĩa; phép kiểm tra nhiều luồng ở giá trị 40.000 **không phải bằng chứng rằng ứng dụng không bao giờ tràn**. Phải kiểm tra riêng tại các giá trị biên và giới hạn miền dữ liệu thực tế.

## 9. Khi nào nên dùng `LongAdder` hoặc `LongAccumulator`?

Java còn cung cấp `LongAdder` và `LongAccumulator` trong `java.util.concurrent.atomic`, thường hữu ích cho thống kê cập nhật với tranh chấp cao.

~~~java
import java.util.concurrent.atomic.LongAdder;

LongAdder events = new LongAdder();
events.increment();
events.add(5L);

System.out.println(events.sum()); // 6
~~~

Nhưng **`LongAdder` không tự kiểm tra tràn**: nó sử dụng các giá trị kiểu `long`, tổng có thể vượt miền và wrap. Hơn nữa, khi có cập nhật đồng thời, `sum()` không phải snapshot nguyên tử của tất cả phần đang được cập nhật; nó không phù hợp để làm một lần kiểm tra giới hạn chính xác rồi quyết định cho phép tăng tiếp.

Không giải quyết vấn đề bằng cách:

~~~java
// SAI nếu cần giới hạn cứng trong môi trường có cập nhật đồng thời.
if (events.sum() < LIMIT) {
    events.increment();
}
~~~

`LongAccumulator` cho phép khai báo hàm tích lũy, nhưng việc cung cấp toán tử cộng không tự tạo cơ chế tràn có kiểm soát hoặc transaction xuyên dữ liệu. Một hàm tích lũy tùy biến cũng phải được thiết kế về tính kết hợp, retry, tranh chấp và chính sách khi vượt miền. Nếu cần một giới hạn cứng trên một counter riêng lẻ, `AtomicInteger`/`AtomicLong` với cập nhật có kiểm tra là điểm khởi đầu dễ kiểm chứng hơn.

## 10. Các bẫy liên quan khi thiết kế counter

### A. Không kiểm tra bằng biểu thức đã tràn

~~~java
int next = counter.incrementAndGet();
if (next < 0) {
    // Trễ: bộ đếm đã được cập nhật thành giá trị âm.
}
~~~

Cách này có thể giúp phát hiện bất thường **sau khi xảy ra**, nhưng không đảm bảo bất biến “counter không bao giờ âm”. Nếu số âm vốn là giá trị hợp lệ, kiểm tra như vậy còn gây báo động giả.

### B. Đừng kỳ vọng `volatile` tự cộng nguyên tử

~~~java
volatile int total = 0;
~~~

Trong một trường của lớp, `volatile` giúp bảo đảm khả năng nhìn thấy giá trị và các quan hệ về thứ tự bộ nhớ theo Java Memory Model, nhưng biểu thức `total++` vẫn là tổ hợp đọc–cộng–ghi và có thể bị mất lượt cập nhật. `volatile` cũng không kiểm tra overflow. Nếu yêu cầu cập nhật nguyên tử, dùng phương án đồng bộ/atomic thích hợp.

### C. Nhiều biến atomic không tạo một giao dịch

Nếu cần trừ số dư ở một tài khoản và cộng số dư ở tài khoản khác, hai `AtomicLong` riêng lẻ không tự tạo giao dịch nguyên tử. Một phép trừ có kiểm tra và một phép cộng có kiểm tra vẫn có thể để trạng thái nửa chừng nếu bước sau thất bại. Hãy chọn transactional database, khóa đồng bộ thích hợp, hoặc cập nhật một object trạng thái bất biến được bọc trong một `AtomicReference` với CAS, tùy kiến trúc.

### D. Chính sách lỗi phải có ở mọi lối ghi

Một API `checkedIncrement()` không hữu ích nếu nơi khác vẫn có thể gọi trực tiếp `atomicCounter.getAndIncrement()`. Đóng gói reference trong lớp, chỉ mở các phương thức cập nhật đúng quy tắc và có kiểm thử biên.

### E. Overflow có thể đến từ chuyển kiểu

Một tổng `long` vẫn có thể bị cắt còn `int`:

~~~java
long count = 3_000_000_000L;
int unsafe = (int) count; // giá trị sai nếu mong giữ nguyên count

try {
    int safe = Math.toIntExact(count);
} catch (ArithmeticException e) {
    System.out.println("too large for int");
}
~~~

`Math.toIntExact` hữu ích ở ranh giới API khi dữ liệu được thu thập bằng `long` nhưng caller đòi `int`. Cast thường không tự phát hiện mất dữ liệu.

## 11. Kiểm thử đúng trọng tâm

Bộ kiểm thử nên có cả **biên số học** lẫn **tranh chấp đồng thời**. Một bộ chỉ kiểm tra 10.000 lần tăng sẽ không phát hiện lỗi wrap tại MAX.

| Trạng thái ban đầu | Cập nhật | Hành vi atomic thông thường | Hành vi checked `Math.addExact` |
| --- | --- | --- | --- |
| `0` | `+1` | `1` | `1` |
| `Integer.MAX_VALUE - 1` | `+1` | `Integer.MAX_VALUE` | `Integer.MAX_VALUE` |
| `Integer.MAX_VALUE` | `+1` | `Integer.MIN_VALUE` | Ném `ArithmeticException` |
| `Integer.MIN_VALUE` | `-1` | `Integer.MAX_VALUE` | Ném `ArithmeticException` |
| `Integer.MIN_VALUE` | `+1` | `Integer.MIN_VALUE + 1` | `Integer.MIN_VALUE + 1` |
| `Long.MAX_VALUE` (kiểu `long`) | `+1L` | `Long.MIN_VALUE` | Ném `ArithmeticException` |

Cần đặc biệt xét:

- **Giá trị trả về:** `getAndIncrement` trả giá trị cũ; `incrementAndGet` trả giá trị mới.
- **Trạng thái khi lỗi:** với test một luồng, kiểm tra giá trị không bị thay đổi sau ngoại lệ `addExact`.
- **Tranh chấp gần MAX:** hai luồng cùng tăng từ `MAX - 1`; với checked update, đúng một cập nhật có thể đưa lên MAX, cập nhật vượt MAX phải bị từ chối. Test cần đồng bộ điểm bắt đầu và bắt kết quả/ngoại lệ của từng thread để tránh bỏ sót lỗi.
- **Callback có side effect:** kiểm tra logic không phụ thuộc số lần gọi của hàm update khi CAS retry.
- **Điều kiện nghiệp vụ:** nếu counter phải không âm, trường hợp `delta < 0` còn cần kiểm tra miền không âm riêng; `Math.addExact` chỉ ngăn overflow, không ngăn kết quả âm hợp lệ về mặt `int`.
- **Các đường ghi khác:** kiểm tra không có caller dùng phương thức bypass chính sách checked.

Trong một test chạy nhiều luồng, phải chờ tất cả futures/threads hoàn tất và thu thập exception, nếu không lỗi ở worker thread có thể bị bỏ qua và test chính vẫn pass.

## 12. Bài tập vận dụng

**Bài 1.** Với:

~~~java
AtomicInteger a = new AtomicInteger(Integer.MAX_VALUE);
System.out.println(a.getAndIncrement());
System.out.println(a.get());
~~~

Đầu ra là gì? `getAndIncrement()` có ném exception không?

**Bài 2.** Một API dùng:

~~~java
if (counter.get() != Integer.MAX_VALUE) {
    counter.incrementAndGet();
}
~~~

Tại sao đoạn này vẫn có thể tràn khi có hai luồng? Hãy thay bằng một câu lệnh dùng `updateAndGet` và `Math.incrementExact`.

**Bài 3.** Với `AtomicLong` đang ở `Long.MIN_VALUE`, `decrementAndGet()` trả gì? Còn `updateAndGet(Math::decrementExact)` sẽ thế nào?

**Bài 4.** Counter phải nằm trong khoảng 0–100. Sử dụng `Math.addExact` có đủ để bảo đảm điều kiện này không? Nếu không, cần kiểm tra gì **bên trong cùng callback**?

**Bài 5.** Vì sao không nên gọi `sendEmail()` trong callback của `updateAndGet`? Nếu gọi bên ngoài callback sau khi update thành công thì những bảo đảm nào vẫn chưa có?

### Đáp án

1. Lần in đầu trả `2147483647` (giá trị cũ); lần in sau trả `-2147483648` (đã wrap). Không có exception tự động.
2. Hai luồng cùng có thể đọc `MAX - 1`, cả hai vượt qua kiểm tra; sau hai cập nhật trạng thái wrap. Dùng `counter.updateAndGet(Math::incrementExact)` hoặc `counter.updateAndGet(v -> Math.addExact(v, 1))`.
3. `decrementAndGet()` wrap thành `Long.MAX_VALUE`. `Math.decrementExact` ném `ArithmeticException` trước khi lần thử cập nhật quá biên được commit.
4. Không đủ: ví dụ tăng từ 100 lên 101 không overflow kiểu `int`. Trong callback, kiểm tra `next` nằm trong `[0, 100]` và báo lỗi hoặc bão hòa theo hợp đồng nghiệp vụ; kết hợp kiểm tra và cập nhật thành một thao tác atomic.
5. Callback có thể chạy nhiều lần do CAS retry, khiến email gửi trùng. Đưa email ra ngoài callback tránh side effect khi tính lại, nhưng việc cập nhật bộ đếm và gửi email vẫn không phải transaction nguyên tử, nên cần thiết kế giao tiếp/đảm bảo gửi phù hợp.

**Điểm cần nhớ:** `AtomicInteger` và `AtomicLong` giúp các luồng cập nhật đúng theo phép toán kiểu số nguyên Java; chúng **không** biến phép toán thành arithmetic có kiểm tra. Khi muốn từ chối tràn, kết hợp `Math.*Exact` với `updateAndGet` hoặc một vòng CAS đúng, đồng thời đóng gói mọi lối ghi và kiểm thử tại giới hạn.
