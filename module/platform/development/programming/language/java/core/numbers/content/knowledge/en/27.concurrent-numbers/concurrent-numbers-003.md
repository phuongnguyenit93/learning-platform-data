# AtomicInteger và AtomicLong trong Java: cập nhật số an toàn giữa nhiều luồng

Trong chương trình có nhiều luồng, biểu thức `counter++` **không phải một thao tác nguyên tử** chỉ vì `counter` có kiểu nguyên thủy `int` hoặc được khai báo `volatile`. Khi hai luồng cùng đọc giá trị cũ rồi cùng ghi giá trị mới, một lần tăng có thể bị mất (*lost update*).

`AtomicInteger` và `AtomicLong` trong package `java.util.concurrent.atomic` cung cấp các thao tác nguyên tử như tăng, cộng, đổi và cập nhật có điều kiện trên **một giá trị số nguyên**. Chúng phù hợp với bộ đếm, số thứ tự, cờ trạng thái số học hoặc một trạng thái được mã hóa bằng số cần cập nhật giữa nhiều luồng, khi không cần khóa bao quanh toàn bộ khối nghiệp vụ.

Bài này giải thích ý nghĩa nguyên tử, cách sử dụng API, cơ chế CAS, bảo đảm bộ nhớ, giới hạn với nhiều biến, tràn số và trường hợp chọn cấu trúc khác.

## 1. Vì sao `counter++` có thể làm mất số lần tăng?

Xét một trường được chia sẻ:

```java
private int counter = 0;

void increase() {
    counter++; // Không bảo đảm nguyên tử khi có nhiều luồng cùng gọi
}
```

Ở mức logic, biểu thức tăng gồm ba việc: đọc `counter`, cộng 1, ghi lại kết quả. Một lịch xen kẽ có thể như sau:

| Thời điểm | Luồng A | Luồng B | Giá trị chung |
|---|---|---|---:|
| Ban đầu | | | 10 |
| 1 | Đọc 10 | | 10 |
| 2 | | Đọc 10 | 10 |
| 3 | Tính 11 và ghi 11 | | 11 |
| 4 | | Tính 11 và ghi 11 | 11 |

Hai luồng đều đã thực hiện một lần tăng nhưng giá trị cuối là **11 thay vì 12**. Ví dụ này là một lịch có thể xảy ra; kết quả cụ thể của một chương trình chạy nhiều luồng còn phụ thuộc lịch thực thi.

Nếu thay trường bằng `volatile int counter`, thao tác đọc/ghi có bảo đảm visibility tương ứng với volatile, **nhưng tổ hợp đọc → cộng → ghi vẫn không thành một thao tác nguyên tử**. `volatile` không sửa được lost update này.

Có thể bảo vệ phép tăng bằng khóa `synchronized`, hoặc dùng:

```java
import java.util.concurrent.atomic.AtomicInteger;

private final AtomicInteger counter = new AtomicInteger();

void increase() {
    counter.incrementAndGet();
}
```

`incrementAndGet()` là một phép cập nhật nguyên tử. Nếu các luồng chỉ thay đổi bộ đếm thông qua các phương thức nguyên tử trên cùng đối tượng, các lần tăng sẽ không bị mất vì thao tác đọc–sửa–ghi bị xen giữa.

## 2. AtomicInteger và AtomicLong khác nhau thế nào?

| Đặc điểm | `AtomicInteger` | `AtomicLong` |
|---|---|---|
| Giá trị lưu trữ | `int` có dấu, 32 bit | `long` có dấu, 64 bit |
| Phạm vi | -2.147.483.648 đến 2.147.483.647 | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |
| Tạo với giá trị ban đầu | `new AtomicInteger(10)` | `new AtomicLong(10L)` |
| Đọc và gán | `get()`, `set(...)` | `get()`, `set(...)` |
| Tăng, giảm, cộng | `incrementAndGet()`, `addAndGet(...)`, ... | Các phương thức cùng tên với tham số/kết quả `long` |
| Cập nhật có điều kiện | `compareAndSet(...)`, `compareAndExchange(...)` | Các phương thức tương ứng trên `long` |
| Biểu thức ví dụ | `counter.incrementAndGet()` | `sequence.incrementAndGet()` |

Cả hai là **lớp đối tượng**, khác `int`/`long` nguyên thủy. Ví dụ `AtomicInteger counter = new AtomicInteger(5)` lưu trạng thái hiện tại bên trong đối tượng, còn biến `counter` là tham chiếu đến đối tượng đó. Cách dùng thường là giữ tham chiếu cố định bằng `final`, rồi thao tác trên giá trị nguyên tử:

```java
private final AtomicLong sequence = new AtomicLong(100L);

long nextSequence() {
    return sequence.incrementAndGet();
}
```

`final` ở đây ngăn gán lại tham chiếu `sequence`. Nó không làm giá trị bên trong đối tượng bất biến; `incrementAndGet()` vẫn cập nhật giá trị đó.

### Khởi tạo

```java
AtomicInteger zeroCounter = new AtomicInteger();     // ban đầu 0
AtomicInteger withInitial = new AtomicInteger(42);  // ban đầu 42
AtomicLong longCounter = new AtomicLong(1_000_000L);
```

Các đoạn mã rời trong bài chỉ minh họa cú pháp trong một lớp/phương thức phù hợp; chương trình Java độc lập có `main` xuất hiện ở phần ví dụ thực hành.

## 3. Các thao tác cơ bản và giá trị trả về

Một ưu điểm của API này là tên phương thức cho biết rõ nó trả về **giá trị trước** hay **giá trị sau** cập nhật.

| Phương thức | Ý nghĩa | Kết quả trả về |
|---|---|---|
| `get()` | Đọc trạng thái hiện tại | Giá trị đọc được |
| `set(v)` | Gán trạng thái mới | `void` |
| `getAndSet(v)` | Thay bằng `v` một cách nguyên tử | Giá trị cũ |
| `getAndIncrement()` | Tăng 1 | Giá trị trước khi tăng |
| `incrementAndGet()` | Tăng 1 | Giá trị sau khi tăng |
| `getAndDecrement()` | Giảm 1 | Giá trị trước khi giảm |
| `decrementAndGet()` | Giảm 1 | Giá trị sau khi giảm |
| `getAndAdd(delta)` | Cộng `delta` | Giá trị cũ |
| `addAndGet(delta)` | Cộng `delta` | Giá trị mới |
| `compareAndSet(expected, update)` | Chỉ đổi khi giá trị hiện tại bằng `expected` | `boolean` báo thành công |
| `compareAndExchange(expected, update)` | So sánh rồi có thể đổi | Giá trị quan sát được trước phép so sánh/đổi |
| `getAndUpdate(fn)` | Cập nhật bằng hàm trên trạng thái hiện tại | Giá trị cũ |
| `updateAndGet(fn)` | Cập nhật bằng hàm trên trạng thái hiện tại | Giá trị mới |
| `getAndAccumulate(x, fn)` | Kết hợp giá trị hiện tại với `x` bằng hàm hai đối số | Giá trị cũ |
| `accumulateAndGet(x, fn)` | Kết hợp hai giá trị rồi cập nhật | Giá trị mới |

Các phương thức tương ứng đều có trên `AtomicInteger` và `AtomicLong`, với chữ ký sử dụng `int`/`IntUnaryOperator`/`IntBinaryOperator` hoặc `long`/`LongUnaryOperator`/`LongBinaryOperator` theo lớp.

Ví dụ khác biệt “trước và sau”:

```java
AtomicInteger x = new AtomicInteger(5);

int oldValue = x.getAndIncrement(); // oldValue = 5, x = 6
int newValue = x.incrementAndGet(); // newValue = 7, x = 7
int beforeAdd = x.getAndAdd(3);     // beforeAdd = 7, x = 10
int afterAdd = x.addAndGet(2);      // afterAdd = 12, x = 12
```

Không nên viết `get()` rồi `set(get() + 1)` để thay thế `incrementAndGet()`: hai lệnh riêng không hợp thành một thao tác nguyên tử.

## 4. Cơ chế CAS và điểm tuyến tính hóa

**CAS** (*compare-and-set*, so sánh và gán có điều kiện) nhận ba yếu tố logic: giá trị đang lưu, giá trị mong đợi và giá trị mới. Chỉ khi giá trị hiện tại bằng giá trị mong đợi, phép thay đổi mới xảy ra.

```java
AtomicInteger state = new AtomicInteger(10);

boolean first = state.compareAndSet(10, 20); // true
boolean second = state.compareAndSet(10, 30); // false
int current = state.get();                  // 20
```

Sau phép CAS đầu, trạng thái là 20, vì vậy phép thứ hai với `expected = 10` thất bại. Nó **không** ghi 30; trạng thái cuối vẫn là 20.

`compareAndExchange(expected, newValue)` cũng so sánh rồi có thể cập nhật nguyên tử, nhưng trả về **giá trị thực tế quan sát được** tại lúc thao tác thay vì `boolean`:

```java
AtomicLong slot = new AtomicLong(5L);

long observed1 = slot.compareAndExchange(5L, 8L);  // 5; slot = 8
long observed2 = slot.compareAndExchange(5L, 9L);  // 8; slot vẫn = 8
```

Với những phép đọc–sửa–ghi nguyên tử, ta có thể lý luận như thể mỗi phép có một **điểm tuyến tính hóa** (linearization point): tại một thời điểm trừu tượng, cả thao tác trở nên có hiệu lực đối với các luồng cùng quan sát biến nguyên tử đó. Các thao tác có thể diễn ra đồng thời, nhưng tác động lên **một đối tượng atomic** có thứ tự tương thích với bảo đảm nguyên tử của API.

### Vòng lặp CAS để tăng có điều kiện

Giả sử chỉ muốn tăng bộ đếm khi giá trị còn dưới 100:

```java
static boolean incrementBelow100(AtomicInteger counter) {
    while (true) {
        int current = counter.get();
        if (current >= 100) {
            return false;
        }
        if (counter.compareAndSet(current, current + 1)) {
            return true;
        }
        // Luồng khác đã cập nhật trước: đọc lại và thử lại.
    }
}
```

Đây là **phương thức minh họa**, cần đặt trong một lớp và import `AtomicInteger`. Việc kiểm tra `current < 100` và việc ghi `current + 1` đi qua điều kiện CAS dựa trên cùng giá trị mong đợi; nếu một luồng khác đổi giá trị thì phép CAS thất bại và vòng lặp kiểm tra lại.

Trong ví dụ này điều kiện `current >= 100` còn bảo vệ trước nguy cơ tràn do cộng 1, vì mọi lần tăng thành công đều diễn ra khi `current < 100`. Nếu cho phép các thao tác khác làm bộ đếm giảm hoặc thay đổi tùy ý, cần định nghĩa rõ hợp đồng nghiệp vụ để bảo đảm giới hạn.

**Không khẳng định mọi phép CAS luôn thành công ở lần đầu:** dưới tranh chấp, nhiều luồng có thể phải thử lại. CAS tránh dùng một khóa ứng dụng cho thao tác đơn lẻ, nhưng vẫn tiêu tốn CPU nếu có tranh chấp cao.

### Hàm cập nhật có thể chạy nhiều lần

`updateAndGet(fn)` và `getAndUpdate(fn)` thuận tiện để gói vòng lặp cập nhật trong API:

```java
AtomicInteger count = new AtomicInteger(7);
int capped = count.updateAndGet(v -> Math.min(v + 1, 10)); // 8
```

Khi có tranh chấp, hàm `fn` **có thể được gọi nhiều lần** trước khi cập nhật thành công. Hàm nên **không có tác dụng phụ** và cho kết quả ổn định theo tham số truyền vào. Tránh gọi API mạng, ghi cơ sở dữ liệu, tăng một bộ đếm khác, log nghiệp vụ một lần duy nhất hoặc sinh ngẫu nhiên không kiểm soát ngay bên trong lambda: hàm có thể chạy lại và gây tác dụng phụ trùng lặp.

Đối với cập nhật cần nhiều bước hoặc nhiều tài nguyên, nên xem xét khóa hoặc một cơ chế phối hợp khác.

## 5. Bảo đảm visibility và quan hệ với volatile

Các phương thức chuẩn `get()` và `set(v)` của `AtomicInteger`/`AtomicLong` có hiệu ứng bộ nhớ tương đương **volatile read** và **volatile write** đối với giá trị atomic. Các thao tác như `compareAndSet` cung cấp ngữ nghĩa nguyên tử cùng ràng buộc bộ nhớ tương ứng theo tài liệu JDK.

Điều này giải quyết hai nhu cầu khác nhau:

1. **Visibility (khả năng quan sát):** cập nhật có thể được luồng khác quan sát thông qua những thao tác đọc phù hợp theo Java Memory Model.
2. **Atomic read–modify–write:** hai luồng cùng tăng không thể làm mất một lần tăng nếu đều dùng `incrementAndGet()` trên cùng đối tượng.

`volatile` đơn thuần hỗ trợ nhu cầu thứ nhất cho thao tác trên một trường, nhưng không tự làm phép `x++` nguyên tử. `AtomicInteger` bổ sung các phép cập nhật kết hợp nguyên tử.

Ví dụ về thứ tự công bố dữ liệu:

```java
class Holder {
    private int data;
    private final AtomicInteger ready = new AtomicInteger(0);

    void publish() {
        data = 42;
        ready.set(1);
    }

    int consumeAfterReady() {
        while (ready.get() == 0) {
            Thread.onSpinWait();
        }
        return data;
    }
}
```

Nếu một luồng thực hiện `publish()` và luồng khác nhìn thấy `ready.get() == 1` từ lần `set(1)` đó, quan hệ **happens-before** thông qua thao tác kiểu volatile khiến phép ghi `data = 42` trước khi phát cờ có thể được luồng đọc nhìn thấy, theo các giả định không có cập nhật cạnh tranh khác lên `data` và `ready`. Đây là **ví dụ giải thích memory ordering**, không phải khuyến nghị dùng vòng lặp bận trong ứng dụng thực tế; thường nên dùng `CountDownLatch`, `Future`, `BlockingQueue` hoặc công cụ đồng bộ phù hợp.

Một số API mở rộng có ngữ nghĩa bộ nhớ khác, như `lazySet` (release), `getAcquire`, `setRelease`, `getOpaque`, `setOpaque`, `getPlain` và `setPlain` ở các phiên bản Java hỗ trợ. **Không tùy tiện thay `get()/set()` bằng những biến thể yếu hơn** nếu chưa chứng minh được yêu cầu đồng bộ; các ví dụ và lý luận cơ bản ở đây dùng `get()`/`set()` và phép CAS chuẩn.

## 6. Chương trình Java 17+ hoàn chỉnh

Lưu vào tệp `AtomicNumbersDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class AtomicNumbersDemo {
    public static void main(String[] args) throws InterruptedException {
        final int workers = 4;
        final int iterations = 10_000;
        AtomicInteger counter = new AtomicInteger();
        AtomicLong total = new AtomicLong();
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(workers);

        for (int w = 0; w < workers; w++) {
            Thread thread = new Thread(() -> {
                try {
                    start.await();
                    for (int i = 0; i < iterations; i++) {
                        counter.incrementAndGet();
                        total.addAndGet(2L);
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    done.countDown();
                }
            });
            thread.start();
        }

        start.countDown();
        done.await();
        System.out.println("counter = " + counter.get());
        System.out.println("total = " + total.get());

        AtomicInteger state = new AtomicInteger(5);
        System.out.println("getAndIncrement = "
                + state.getAndIncrement() + ", now = " + state.get());
        System.out.println("incrementAndGet = " + state.incrementAndGet());
        System.out.println("getAndAdd = "
                + state.getAndAdd(3) + ", now = " + state.get());
        System.out.println("addAndGet = " + state.addAndGet(2));
        System.out.println("CAS = " + state.compareAndSet(12, 20)
                + ", now = " + state.get());
        System.out.println("compareAndExchange = "
                + state.compareAndExchange(20, 30)
                + ", now = " + state.get());
        System.out.println("updateAndGet = "
                + state.updateAndGet(v -> v * 2));
        System.out.println("accumulateAndGet = "
                + state.accumulateAndGet(5, Integer::sum));

        System.out.println("int wrap = "
                + new AtomicInteger(Integer.MAX_VALUE)
                        .incrementAndGet());
        System.out.println("long wrap = "
                + new AtomicLong(Long.MAX_VALUE)
                        .incrementAndGet());
    }
}
```

Biên dịch và chạy (JDK 17+):

```bash
javac AtomicNumbersDemo.java
java AtomicNumbersDemo
```

**Stdout khi các luồng hoàn tất bình thường, không bị ngắt:**

```text
counter = 40000
total = 80000
getAndIncrement = 5, now = 6
incrementAndGet = 7
getAndAdd = 7, now = 10
addAndGet = 12
CAS = true, now = 20
compareAndExchange = 20, now = 30
updateAndGet = 60
accumulateAndGet = 65
int wrap = -2147483648
long wrap = -9223372036854775808
```

Bốn luồng cùng đếm, mỗi luồng tăng `counter` 10.000 lần và cộng `total` thêm 2L cho mỗi vòng. Vì mỗi thao tác trên từng atomic là nguyên tử, kết quả cuối sau khi toàn bộ vòng lặp chạy đủ lần là `4 × 10.000 = 40.000` và `4 × 10.000 × 2 = 80.000`. `CountDownLatch` bảo đảm `main` chờ các luồng hoàn thành trước khi in ra; nó không thay thế vai trò của `AtomicInteger`/`AtomicLong` đối với các cập nhật đồng thời.

Trong ví dụ, nếu một luồng bị interrupt trong khi chờ `start.await()`, nó sẽ thoát và có thể không thực hiện đủ số vòng. Dòng stdout trên phản ánh điều kiện chạy thông thường không bị ngắt; khi thiết kế hệ thống thật phải quyết định chính sách xử lý hủy tác vụ và kết quả một phần.

Các dòng thao tác trên `state` minh họa rõ giá trị trước/sau, CAS thành công và `compareAndExchange` trả giá trị đã quan sát. Hai dòng cuối nhắc rằng **atomic không có nghĩa kiểm tra tràn số**.

## 7. Atomic không có nghĩa mọi thứ đều an toàn

### 7.1. Mỗi phép cập nhật riêng lẻ được bảo vệ, không phải một giao dịch nhiều biến

Ví dụ dùng hai atomic:

```java
AtomicInteger stock = new AtomicInteger(10);
AtomicInteger sold = new AtomicInteger(0);

stock.decrementAndGet();
sold.incrementAndGet();
```

Mỗi dòng nguyên tử trên **một đối tượng riêng**, nhưng giữa hai dòng một luồng khác có thể đọc thấy `stock` đã giảm mà `sold` chưa tăng. Hai biến không tạo thành một **transaction** thống nhất.

Nếu yêu cầu bất biến `stock + sold == 10` tại mọi quan sát hợp lệ, cần một cơ chế đồng bộ điều phối cả hai trường, như `synchronized`/`Lock`, hoặc đóng gói toàn bộ trạng thái bất biến vào **một** đối tượng immutable và thay tham chiếu bằng `AtomicReference` với một thuật toán đúng. `AtomicInteger` và `AtomicLong` tự chúng không thể làm nguyên tử một cập nhật gồm nhiều biến.

### 7.2. Đọc rồi hành động riêng lẻ vẫn có race

Sai lầm dễ gặp:

```java
if (counter.get() < 100) {
    counter.incrementAndGet();
}
```

Hai luồng có thể đều quan sát 99 và cùng tăng: kết quả lên 101. Cả hai lần tăng đều nguyên tử, nhưng toàn bộ **kiểm tra → quyết định → tăng** chưa nguyên tử. Phải dùng vòng lặp CAS như ở phần 4 hoặc một cơ chế khóa thích hợp để kiểm tra và cập nhật theo cùng một trạng thái.

### 7.3. `AtomicLong` không ngăn tràn

`AtomicInteger` dùng số nguyên `int`; `AtomicLong` dùng `long`. Các phép cộng/tăng theo ngữ nghĩa số nguyên Java vẫn **wrap around** khi vượt miền có dấu:

```java
AtomicInteger a = new AtomicInteger(Integer.MAX_VALUE);
System.out.println(a.incrementAndGet()); // -2147483648

AtomicLong b = new AtomicLong(Long.MAX_VALUE);
System.out.println(b.incrementAndGet()); // -9223372036854775808
```

Nếu nghiệp vụ đòi **không bao giờ vượt giới hạn**, hãy xử lý điều kiện bằng CAS loop hoặc logic giới hạn phù hợp. Nếu cần đếm chính xác lớn hơn phạm vi `long`, phải dùng biểu diễn khác (ví dụ `BigInteger` với cơ chế đồng bộ/`AtomicReference`), không chỉ thay `AtomicInteger` bằng `AtomicLong` rồi giả định vô hạn.

### 7.4. CAS so sánh giá trị hiện tại, nhưng có thể gặp ABA

Giả sử trạng thái biến đổi theo chuỗi `A → B → A`. Một luồng giữ giá trị cũ `A` rồi dùng CAS mong đợi `A` có thể thành công vì hiện tại lại là `A`, dù đã xảy ra các thay đổi trung gian. Đây là **ABA problem**. Đối với bộ đếm đơn giản, ABA có thể không ảnh hưởng đến tính đúng; với thuật toán lock-free dựa trên lịch sử trạng thái, cần xem xét phiên bản đi kèm (ví dụ đếm phiên bản hoặc `AtomicStampedReference` với tham chiếu), hoặc một thiết kế đồng bộ khác. `AtomicInteger` không tự phát hiện lịch sử `A → B → A`.

### 7.5. Atomic không bảo đảm công bằng thứ tự luồng

Các phép CAS có thể thất bại và thử lại nhiều lần khi contention cao. Không nên suy ra tất cả luồng sẽ tiến triển công bằng, hay mọi thao tác đều thực thi với thời gian cố định trong mọi lịch chạy. Thiết kế cần phù hợp yêu cầu throughput, latency và khả năng tiến triển dưới tải.

## 8. Khi nào chọn LongAdder, synchronized hoặc AtomicReference?

**AtomicInteger/AtomicLong** phù hợp khi cần các thao tác **chính xác, riêng lẻ** như `getAndIncrement()`, `compareAndSet()` hoặc lấy một số thứ tự duy nhất.

Khi nhiều luồng cùng cập nhật một bộ đếm tích lũy và không cần CAS/số thứ tự duy nhất từ mỗi lần tăng, `LongAdder` có thể giảm tranh chấp bằng cách phân tán các cập nhật:

```java
import java.util.concurrent.atomic.LongAdder;

LongAdder requests = new LongAdder();
requests.increment();
requests.add(5L);

long approxAtMoment = requests.sum(); // sau hai cập nhật tuần tự: 6
```

**Cần phân biệt:** `LongAdder.sum()` không phải một snapshot nguyên tử đối với những cập nhật đồng thời đang diễn ra; không dùng `LongAdder` để gán ID duy nhất hoặc thực thi điều kiện CAS dựa trên một giá trị quan sát chính xác. So sánh hiệu năng bằng benchmark thực tế: `LongAdder` không mặc nhiên tốt hơn trong mọi tải hoặc khi tranh chấp thấp.

| Nhu cầu | Cấu trúc phù hợp |
|---|---|
| Sinh ID/số thứ tự tăng dần trong phạm vi kiểu | `AtomicLong.incrementAndGet()`; xử lý tràn theo yêu cầu |
| Tăng bộ đếm chính xác và đọc giá trị hiện tại | `AtomicInteger` hoặc `AtomicLong` |
| Thống kê lượng request có nhiều luồng cập nhật, chấp nhận `sum()` không là snapshot nguyên tử lúc đang ghi | `LongAdder` |
| Nhiều trường phải đồng thời thỏa bất biến | `synchronized`, `Lock`, hoặc thiết kế trạng thái gộp |
| Thay nguyên tử một đối tượng trạng thái bất biến | `AtomicReference<State>` |
| Nhiều giá trị lớn hơn 64 bit | Mô hình `BigInteger` cộng đồng bộ hoặc tham chiếu atomic thích hợp |

Lựa chọn công cụ phụ thuộc **bất biến cần bảo vệ**, chứ không chỉ việc dữ liệu có nhiều luồng truy cập.

## 9. Lỗi thường gặp và cách tránh

1. **Nghĩ `volatile int++` là nguyên tử.** `volatile` không gộp phép đọc, cộng và ghi. Dùng `incrementAndGet()` hoặc đồng bộ hóa.
2. **Tách một phép cập nhật thành `get()` rồi `set()`.** Hai lệnh riêng có thể xen kẽ. Dùng `addAndGet`, `getAndUpdate` hoặc CAS.
3. **Nhầm giá trị cũ và mới.** `getAndIncrement()` trả giá trị trước; `incrementAndGet()` trả giá trị sau. Chọn theo yêu cầu cấp số hay bộ đếm.
4. **Cho rằng hai Atomic là một giao dịch.** Cập nhật `balanceA` rồi `balanceB` để lại một khoảng thời gian có trạng thái trung gian quan sát được.
5. **Đặt tác dụng phụ trong hàm `updateAndGet`.** Lambda có thể chạy lại khi CAS thất bại; cần dùng hàm thuần, không gọi API có tác dụng ngoài.
6. **Dùng `AtomicLong` và cho rằng không bao giờ tràn.** `long` vẫn có giới hạn, tăng qua `Long.MAX_VALUE` sẽ wrap.
7. **Dựa vào `LongAdder.sum()` như snapshot nguyên tử đang đồng thời cập nhật.** `sum()` phục vụ thống kê, không cam kết snapshot tức thời dưới tranh chấp.
8. **Dùng vòng `while (flag.get() == 0)` để chờ dài.** Bận chờ tiêu thụ CPU; chọn cơ chế chờ, thông báo hoặc blocking phù hợp.
9. **Hiểu CAS là khóa toàn bộ đoạn code.** CAS bảo vệ việc so sánh/cập nhật một biến, không tự đồng bộ các hiệu ứng bên ngoài phép CAS.
10. **Nghĩ có atomic là toàn bộ ứng dụng thread-safe.** Cần xét tham chiếu chia sẻ, thứ tự thao tác, dữ liệu khác và bất biến nghiệp vụ.

## 10. Tự kiểm tra

**Câu 1.** Vì sao `volatile int count; count++;` vẫn mất lần tăng?  
**Đáp án:** Phép `++` gồm nhiều bước và có thể xen kẽ. `volatile` cho hiệu ứng visibility của các lần đọc/ghi, không làm toàn bộ phép đọc–sửa–ghi nguyên tử.

**Câu 2.** `new AtomicInteger(3).getAndIncrement()` trả về gì? Giá trị cuối?  
**Đáp án:** Trả 3 (giá trị cũ); đối tượng chứa 4.

**Câu 3.** `new AtomicLong(7).incrementAndGet()` trả về gì?  
**Đáp án:** 8, là giá trị mới sau cập nhật.

**Câu 4.** Tại sao `if (a.get() < 100) a.incrementAndGet();` có thể vượt 100?  
**Đáp án:** Điều kiện và lần tăng là hai thao tác riêng; nhiều luồng có thể cùng đọc 99 rồi cùng tăng. Dùng CAS loop để kiểm tra và cập nhật trên cùng giá trị quan sát.

**Câu 5.** `compareAndSet(10, 20)` trả `false` nói lên điều gì?  
**Đáp án:** Giá trị đang quan sát trong phép CAS không khớp 10 nên phép gán 20 không xảy ra. Nên đọc lại và quyết định thử tiếp nếu thuật toán yêu cầu.

**Câu 6.** Vì sao không nên gọi hệ thống ngoài trong lambda của `updateAndGet`?  
**Đáp án:** Hàm có thể được gọi nhiều lần do tranh chấp và CAS retry; hiệu ứng ngoài có thể bị lặp.

**Câu 7.** Khi nào dùng `LongAdder` thay `AtomicLong`?  
**Đáp án:** Khi cần nhiều luồng tích lũy bộ đếm thống kê dưới tranh chấp và không đòi đọc snapshot nguyên tử hoặc cấp số/compare-and-set từ từng lần cập nhật.

**Câu 8.** `AtomicLong.incrementAndGet()` trên `Long.MAX_VALUE` trả gì?  
**Đáp án:** `Long.MIN_VALUE` do phép toán số nguyên wrap; atomicity không ngăn tràn.

**Quy tắc ghi nhớ:** `AtomicInteger` và `AtomicLong` cung cấp các phép thao tác **nguyên tử trên một giá trị số nguyên**, cùng hiệu ứng bộ nhớ phù hợp của API. Chúng ngăn lost update khi dùng đúng phương thức, nhưng **không tự thay thế giao dịch nhiều biến, kiểm tra bất biến tổng hợp, xử lý tràn số hoặc chính sách tiến triển giữa các luồng**.
