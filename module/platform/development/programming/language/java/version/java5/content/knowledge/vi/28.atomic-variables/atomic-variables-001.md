# Biến nguyên tử và thao tác đọc–sửa–ghi

## 1. Vì sao một câu lệnh tăng vẫn có thể mất cập nhật?

Giả sử hai luồng cùng tăng số yêu cầu đã xử lý. Câu lệnh `count++` nhìn ngắn nhưng về mặt logic gồm ba bước:

1. **Đọc** giá trị hiện tại.
2. **Sửa** giá trị vừa đọc, chẳng hạn cộng 1.
3. **Ghi** kết quả trở lại biến dùng chung.

Đó là thao tác **đọc–sửa–ghi (read–modify–write, RMW)**. Nếu cả chuỗi không được bảo vệ như một thao tác nguyên tử, các luồng có thể xen kẽ:

| Thứ tự | Luồng T1 | Luồng T2 | Giá trị dùng chung |
| --- | --- | --- | --- |
| 1 | Đọc 0 | | 0 |
| 2 | | Đọc 0 | 0 |
| 3 | Tính 1, ghi 1 | | 1 |
| 4 | | Tính 1, ghi 1 | 1 |

Đã có hai yêu cầu tăng nhưng kết quả chỉ là 1. Đây là **mất cập nhật (lost update)**. Không cần hai CPU ghi đúng cùng một thời điểm để lỗi xảy ra; việc xen kẽ các bước đã đủ.

Một lần đọc hay ghi `int` riêng lẻ không bị xé thành hai nửa, nhưng điều đó không làm cả phép tăng thành nguyên tử. `volatile` bổ sung quy tắc quan sát và thứ tự bộ nhớ, **không gộp phép đọc và phép ghi của `count++` thành một thao tác**. Xem [Java Memory Model](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5).

## 2. Biến nguyên tử cung cấp điều gì?

Các lớp trong `java.util.concurrent.atomic` cung cấp phương thức truy cập và cập nhật nguyên tử một giá trị. Trong bài này, “nguyên tử” có nghĩa người sử dụng không quan sát được một thao tác cập nhật hợp lệ bị chen ngang bởi cập nhật khác ngay giữa bước đọc và ghi của chính thao tác đó.

| Lớp | Giá trị chính được quản lý | Ví dụ sử dụng |
| --- | --- | --- |
| `AtomicInteger` | Một `int` | Bộ đếm, số chỗ còn lại |
| `AtomicLong` | Một `long` | Dãy số, bộ đếm có miền lớn hơn |
| `AtomicBoolean` | Một `boolean` | Giành quyền thực hiện một việc một lần |
| `AtomicReference<T>` | Một tham chiếu | Thay một bản trạng thái bất biến |

Các lớp này tập trung vào **một giá trị được quản lý**, không tự biến toàn bộ mã xung quanh thành giao dịch. `AtomicReference` quản lý tham chiếu; đối tượng được tham chiếu vẫn cần quy tắc riêng nếu nó có thể bị sửa. Xem [tổng quan gói atomic](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/package-summary.html).

Ví dụ khai báo dùng chung:

```java
private final AtomicInteger requests = new AtomicInteger(0);
```

`final` giữ ổn định tham chiếu tới đối tượng bộ đếm, không cấm giá trị bên trong thay đổi. Các luồng phải truy cập **cùng đối tượng** `requests`; mỗi luồng tạo bộ đếm riêng thì không có tổng chung.

## 3. Dùng đúng phương thức cho đúng thao tác

| Phương thức AtomicInteger | Tác dụng | Giá trị trả về |
| --- | --- | --- |
| `get()` | Đọc hiện tại | Giá trị hiện tại |
| `set(v)` | Ghi một giá trị | Không có |
| `getAndIncrement()` | Tăng 1 nguyên tử | Giá trị trước khi tăng |
| `incrementAndGet()` | Tăng 1 nguyên tử | Giá trị sau khi tăng |
| `getAndAdd(delta)` | Cộng delta nguyên tử | Giá trị trước khi cộng |
| `addAndGet(delta)` | Cộng delta nguyên tử | Giá trị sau khi cộng |
| `getAndSet(v)` | Đổi sang v nguyên tử | Giá trị trước khi đổi |
| `compareAndSet(expected, next)` | Ghi nếu hiện tại bằng expected | Thành công hay thất bại |

`get()` rồi `set()` là **hai thao tác riêng**, dù mỗi phương thức có bảo đảm riêng. Vì vậy cách sau vẫn sai khi có cập nhật đồng thời:

```java
counter.set(counter.get() + 1); // Không phải một lần tăng nguyên tử.
```

Hãy dùng `counter.incrementAndGet()` hoặc `counter.getAndIncrement()` tùy cần kết quả trước hay sau. Với các phương thức thông thường như `get()`, `set()` và `compareAndSet()`, API cũng quy định hiệu ứng bộ nhớ phù hợp cho chia sẻ giữa các luồng; không nên coi chúng chỉ là phép toán số học. Tham khảo [AtomicInteger](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html).

## 4. Ví dụ chạy được: ép xuất hiện mất cập nhật

Nếu chỉ chạy nhiều luồng rồi chờ may mắn thấy kết quả sai, một lần chạy có thể tình cờ cho kết quả đúng. Ví dụ sau dùng `CyclicBarrier` để buộc cả hai tác vụ đọc xong giá trị 0 **trước khi một trong hai ghi**. Nhờ vậy kết quả mất cập nhật được tái lập rõ ràng.

Phần thứ nhất dùng biến `volatile int`; phần thứ hai cố tình ghép `get()` và `set()` sai; phần thứ ba dùng phép tăng nguyên tử đúng.

Lưu thành `AtomicRmwDemo.java`, chạy bằng JDK 17 trở lên:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicRmwDemo {
    private static volatile int volatileCount;

    private static void runPair(ExecutorService pool, Callable<Void> action)
            throws Exception {
        Future<Void> first = pool.submit(action);
        Future<Void> second = pool.submit(action);
        first.get();
        second.get();
    }

    private static boolean tryTakeOne(AtomicInteger remaining) {
        while (true) {
            int current = remaining.get();
            if (current <= 0) {
                return false;
            }
            if (remaining.compareAndSet(current, current - 1)) {
                return true;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            CyclicBarrier volatileReadDone = new CyclicBarrier(2);
            runPair(pool, () -> {
                int observed = volatileCount;
                volatileReadDone.await();
                volatileCount = observed + 1;
                return null;
            });
            System.out.println("volatile read-modify-write=" + volatileCount);

            AtomicInteger split = new AtomicInteger(0);
            CyclicBarrier atomicReadDone = new CyclicBarrier(2);
            runPair(pool, () -> {
                int observed = split.get();
                atomicReadDone.await();
                split.set(observed + 1);
                return null;
            });
            System.out.println("atomic get then set=" + split.get());

            AtomicInteger atomic = new AtomicInteger(0);
            runPair(pool, () -> {
                atomic.incrementAndGet();
                return null;
            });
            System.out.println("atomic increment=" + atomic.get());

            int oldValue = atomic.getAndIncrement();
            System.out.println("old=" + oldValue + ", current=" + atomic.get());
            int newValue = atomic.incrementAndGet();
            System.out.println("new=" + newValue + ", current=" + atomic.get());

            AtomicInteger remaining = new AtomicInteger(1);
            System.out.println("take first=" + tryTakeOne(remaining));
            System.out.println("take second=" + tryTakeOne(remaining));
            System.out.println("remaining=" + remaining.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac AtomicRmwDemo.java
java AtomicRmwDemo
```

Stdout:

```text
volatile read-modify-write=1
atomic get then set=1
atomic increment=2
old=2, current=3
new=4, current=4
take first=true
take second=false
remaining=0
```

Hai tác vụ đầu cùng đọc 0 nên cùng ghi 1. Kết quả này không nói `volatile` hay `AtomicInteger.get()` trả dữ liệu “sai”; lỗi là chương trình cho phép cả hai dùng cùng một kết quả đọc để quyết định ghi sau đó.

Ở phép thử thứ ba, hai lần `incrementAndGet()` không mất nhau nên kết quả là 2. Các dòng `old` và `new` được in sau khi hai tác vụ đã hoàn tất, vì vậy minh họa trực tiếp sự khác nhau giữa trả giá trị cũ và trả giá trị mới. Chương trình không in giá trị trung gian từ hai tác vụ để tránh nhầm thứ tự stdout với thứ tự cập nhật.

`CyclicBarrier` trong hai phần sai chỉ phục vụ minh chứng cách xen kẽ. Nó không phải cách sửa bộ đếm. Chương trình này cũng không phải phép đo hiệu năng.

## 5. Cập nhật có điều kiện bằng CAS

**CAS (compare-and-set)** thử ghi giá trị mới chỉ khi giá trị hiện tại còn bằng giá trị kỳ vọng. Trong `tryTakeOne()`:

1. Đọc `current`.
2. Nếu không còn chỗ, trả `false`.
3. Thử chuyển từ `current` sang `current - 1` bằng một CAS.
4. Nếu thành công, việc lấy một chỗ hoàn tất.
5. Nếu thất bại, luồng khác đã làm giá trị không còn khớp; đọc lại và tính lại.

Giả sử còn một chỗ và hai luồng cùng đọc 1. Chỉ một luồng có thể chuyển 1 → 0 thành công. Luồng còn lại thử CAS với kỳ vọng 1 nhưng hiện tại là 0, nên thất bại; vòng sau nó thấy hết chỗ và trả `false`.

Điểm khác với mã sau là quyết định “còn chỗ” và việc trừ được gắn bằng một lần cập nhật có điều kiện:

```java
// Minh họa lỗi: hai luồng có thể cùng vượt qua phép kiểm tra.
if (remaining.get() > 0) {
    remaining.decrementAndGet();
}
```

Ngay cả `decrementAndGet()` nguyên tử cũng không cứu được **cả cặp kiểm tra rồi hành động** khi chúng tách rời. Với đoạn lỗi, hai luồng cùng thấy 1 có thể lần lượt trừ xuống 0 rồi -1.

CAS chỉ so sánh giá trị ở thời điểm thực hiện; nó không chứng minh rằng biến chưa từng thay đổi rồi quay về giá trị cũ. Nếu bài toán cần theo dõi lịch sử hay phiên bản, phải đưa thông tin đó vào thiết kế trạng thái.

## 6. Phép biến đổi bằng hàm cập nhật

Khi cần biến đổi từ giá trị cũ, có thể dùng `updateAndGet()` hoặc `getAndUpdate()`. Ví dụ minh họa bên trong phương thức đã có biến `score`:

```java
int updated = score.updateAndGet(current -> current + 5);
```

Hàm cập nhật có thể bị đánh giá lại khi có tranh chấp. Vì vậy nó nên chỉ tính giá trị mới, không gửi email, ghi giao dịch ngoài, tăng một bộ đếm khác hay in thông báo mang ý nghĩa “đã cập nhật thành công”. Những tác dụng phụ đó có thể xảy ra nhiều lần dù một lần cập nhật cuối cùng chỉ được chấp nhận một lần.

Vòng CAS tự viết cũng có cùng yêu cầu: phần trước CAS có thể chạy lại. Đưa một tác dụng phụ sau CAS thành công chỉ giúp nó chạy một lần cho lần gọi thành công đó; vẫn không tạo giao dịch nguyên tử với hệ thống ngoài. Xem [hợp đồng hàm cập nhật AtomicInteger](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html#updateAndGet(java.util.function.IntUnaryOperator)).

## 7. Giới hạn cần hiểu trước khi thay khóa bằng biến nguyên tử

### Một thao tác nguyên tử không bao phủ nhiều biến

Hai biến `AtomicInteger` không tạo một trạng thái đôi nguyên tử. Nếu cần bảo toàn `used + free == capacity`, cập nhật `used` rồi `free` riêng lẻ cho phép người quan sát thấy trạng thái trung gian. Có thể bảo vệ cả trạng thái bằng cùng một khóa hoặc đóng gói trạng thái thành một đối tượng bất biến rồi thay một tham chiếu nguyên tử; cần thiết kế theo bất biến thật sự của bài toán.

### Không trộn nhiều hợp đồng cập nhật tùy tiện

Nếu một số luồng dùng CAS còn luồng khác tùy ý `set()` để khôi phục giá trị cũ, thuật toán cấp chỗ hoặc sinh số có thể không còn đúng dù từng lời gọi API vẫn nguyên tử. Quy tắc được phép chuyển trạng thái phải được áp dụng cho tất cả người ghi.

### Nguyên tử không giải quyết miền số

`AtomicInteger` vẫn có miền `int`. Khi vượt giới hạn, phép tăng có hành vi tràn số như phép toán `int`, không tự ném lỗi vì là biến nguyên tử. Chọn miền số và chính sách tràn phù hợp; `AtomicLong` chỉ mở rộng miền, không làm nó vô hạn.

### Không đồng nhất nguyên tử với nhanh hơn hay chờ hữu hạn

CAS có thể phải thử lại nhiều lần khi tranh chấp. Không có bảo đảm rằng một luồng cụ thể luôn thành công ngay hoặc chỉ sau một số vòng cố định. Một thuật toán không dùng khóa cũng không tự bảo đảm công bằng. Đo hiệu năng theo tải thực tế thay vì suy từ tên lớp.

## 8. Tự kiểm tra

1. `volatile int n; n++;` có tăng nguyên tử không? **Không**, phép đọc–sửa–ghi chưa được gộp.
2. `AtomicInteger` với `set(get() + 1)` có tránh mất cập nhật không? **Không**, đó vẫn là hai thao tác tách rời.
3. Cần trả giá trị trước khi tăng thì dùng gì? **`getAndIncrement()`**.
4. Cần giảm chỉ khi hiện tại còn dương thì làm thế nào? **Dùng cập nhật có điều kiện được thiết kế đúng, chẳng hạn vòng CAS như `tryTakeOne()`**.
5. Nhiều trường có quan hệ ràng buộc thì chỉ đổi từng trường sang atomic đã đủ chưa? **Chưa**, phải bảo vệ toàn bộ bất biến của trạng thái.
