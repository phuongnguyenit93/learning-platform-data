# AtomicInteger: getAndIncrement, incrementAndGet và các phép cập nhật nguyên tử trong Java

## 1. Vì sao phép tăng số thông thường có thể sai khi có nhiều luồng?

Giả sử nhiều luồng Java cùng tăng một bộ đếm:

~~~java
int counter = 0;
counter++;
~~~

Trông như một thao tác duy nhất, nhưng về ý nghĩa cập nhật, `counter++` gồm những bước đọc giá trị cũ, tính giá trị mới, rồi ghi lại. Hai luồng có thể cùng đọc `counter = 5`, cùng tính `6` và cùng ghi `6`: **hai lần tăng nhưng kết quả chỉ tăng một lần**. Đây là một dạng *lost update* (mất cập nhật).

Đặt một biến `int` thành `volatile` giúp các luồng có bảo đảm nhất định về khả năng quan sát và thứ tự đọc/ghi, nhưng **không biến biểu thức `counter++` thành thao tác nguyên tử**.

Khi chỉ cần một số nguyên dùng chung có các thao tác cập nhật độc lập, Java cung cấp `java.util.concurrent.atomic.AtomicInteger`. Các phương thức như `getAndIncrement()`, `incrementAndGet()`, `getAndAdd()`, `addAndGet()`, `getAndUpdate()`, `updateAndGet()` và `compareAndSet()` thực hiện thao tác với ngữ nghĩa nguyên tử phù hợp cho nhiều luồng.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger(0);
counter.incrementAndGet();
~~~

Đây là đoạn minh họa đặt trong một lớp/phương thức. Đối tượng `AtomicInteger` giữ một giá trị `int` có thể thay đổi; nó **không** phải `Integer` bất biến.

Mục tiêu bài học: hiểu chính xác phương thức nào trả **giá trị trước cập nhật**, phương thức nào trả **giá trị sau cập nhật**, các phép cập nhật theo hàm, cơ chế so sánh rồi đổi (CAS), và giới hạn của bảo đảm nguyên tử.

## 2. getAndIncrement và incrementAndGet: cùng tăng 1, khác giá trị trả về

Hai phương thức đều tăng giá trị được giữ lên 1 theo một thao tác nguyên tử, nhưng thời điểm của giá trị trả về khác nhau:

| Phương thức | Phép cập nhật | Giá trị trả về |
| --- | --- | --- |
| `getAndIncrement()` | Tăng 1 | **Giá trị cũ**, ngay trước lần tăng thành công |
| `incrementAndGet()` | Tăng 1 | **Giá trị mới**, ngay sau lần tăng thành công |
| `getAndDecrement()` | Giảm 1 | **Giá trị cũ** |
| `decrementAndGet()` | Giảm 1 | **Giá trị mới** |

Ví dụ bắt đầu từ 10:

~~~java
AtomicInteger counter = new AtomicInteger(10);

int oldValue = counter.getAndIncrement(); // oldValue = 10, counter = 11
int newValue = counter.incrementAndGet(); // newValue = 12, counter = 12
~~~

Điểm quan trọng: tiền tố **`getAnd...`** nghĩa là phương thức trả **giá trị cũ** rồi áp dụng cập nhật; hậu tố **`...AndGet`** nghĩa là trả **giá trị sau khi đã cập nhật**. Trong cả hai trường hợp, cập nhật là nguyên tử; khác biệt thuộc về **giá trị mà lời gọi trả về**.

So sánh với cú pháp số nguyên thông thường giúp ghi nhớ:

~~~java
int x = 10;
int a = x++; // a = 10, x = 11
int b = ++x; // b = 12, x = 12
~~~

Về giá trị trả về trong một luồng, `getAndIncrement()` tương tự `x++`, còn `incrementAndGet()` tương tự `++x`. **Sự tương tự dừng ở ý nghĩa trả về**: các phép cập nhật trên `AtomicInteger` được thiết kế để dùng đồng thời, trong khi `x++` trên biến dùng chung không có bảo đảm cập nhật nguyên tử.

### Chọn giá trị cũ hay mới theo nghiệp vụ

Nếu muốn phát số thứ tự **bắt đầu từ 0**, có thể dùng:

~~~java
AtomicInteger sequence = new AtomicInteger(0);
int firstId = sequence.getAndIncrement();  // 0
int secondId = sequence.getAndIncrement(); // 1
~~~

Nếu muốn đếm **số công việc đã hoàn thành**, rồi dùng ngay tổng mới:

~~~java
AtomicInteger completed = new AtomicInteger(0);
int countAfterCompletion = completed.incrementAndGet(); // 1
~~~

Hai ví dụ trên chỉ minh họa ở mức tiến trình hiện tại. `AtomicInteger` không tạo ID bền vững sau khi ứng dụng khởi động lại, cũng không bảo đảm duy nhất trên nhiều JVM/máy chủ.

## 3. Các phương thức cộng, trừ và ghi trực tiếp

Không chỉ tăng giảm 1, `AtomicInteger` còn cung cấp nhiều phương thức:

| Phương thức | Hành động | Trả về |
| --- | --- | --- |
| `get()` | Đọc giá trị hiện tại | Giá trị đọc được |
| `set(v)` | Gán `v` | `void` |
| `getAndSet(v)` | Thay bằng `v` nguyên tử | Giá trị **trước** khi thay |
| `getAndAdd(delta)` | Cộng `delta` nguyên tử | Giá trị **trước** khi cộng |
| `addAndGet(delta)` | Cộng `delta` nguyên tử | Giá trị **sau** khi cộng |
| `getAndIncrement()` | Cộng 1 nguyên tử | Giá trị cũ |
| `incrementAndGet()` | Cộng 1 nguyên tử | Giá trị mới |
| `getAndDecrement()` | Trừ 1 nguyên tử | Giá trị cũ |
| `decrementAndGet()` | Trừ 1 nguyên tử | Giá trị mới |

Giả sử giá trị ban đầu là 20:

~~~java
AtomicInteger value = new AtomicInteger(20);

int before = value.getAndAdd(5); // before = 20; value = 25
int after = value.addAndGet(-3);  // after = 22; value = 22
int previous = value.getAndSet(0); // previous = 22; value = 0
~~~

Dùng `getAndAdd(-3)` hoặc `addAndGet(-3)` khi muốn trừ 3. Các cập nhật này là nguyên tử ngay cả khi nhiều luồng cùng tác động vào **cùng một đối tượng** `AtomicInteger`.

Tuy nhiên, `counter.get()` rồi `counter.set(counter.get() + 1)` **không tương đương** với `incrementAndGet()` trong môi trường đồng thời: phép đọc và ghi nằm trong các lời gọi riêng lẻ, một luồng khác có thể chen vào.

## 4. Chương trình Java 17 đầy đủ: giá trị cũ, mới và cập nhật theo hàm

Tạo tệp `AtomicUpdatesDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicUpdatesDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger(10);

        System.out.println("getAndIncrement: "
                + counter.getAndIncrement() + ", now=" + counter.get());
        System.out.println("incrementAndGet: "
                + counter.incrementAndGet() + ", now=" + counter.get());

        System.out.println("getAndAdd(5): "
                + counter.getAndAdd(5) + ", now=" + counter.get());
        System.out.println("addAndGet(-2): "
                + counter.addAndGet(-2) + ", now=" + counter.get());

        System.out.println("getAndUpdate(x -> x * 2): "
                + counter.getAndUpdate(x -> x * 2)
                + ", now=" + counter.get());
        System.out.println("updateAndGet(x -> x + 3): "
                + counter.updateAndGet(x -> x + 3)
                + ", now=" + counter.get());

        System.out.println("getAndAccumulate(4): "
                + counter.getAndAccumulate(4, (current, x) -> current + x * 2)
                + ", now=" + counter.get());
        System.out.println("accumulateAndGet(50, max): "
                + counter.accumulateAndGet(50, Math::max)
                + ", now=" + counter.get());

        System.out.println("compareAndSet(50, 60): "
                + counter.compareAndSet(50, 60)
                + ", now=" + counter.get());
        System.out.println("compareAndSet(50, 70): "
                + counter.compareAndSet(50, 70)
                + ", now=" + counter.get());

        System.out.println("getAndSet(0): "
                + counter.getAndSet(0) + ", now=" + counter.get());

        AtomicInteger parallelCount = new AtomicInteger();
        Thread[] workers = new Thread[4];
        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 25_000; j++) {
                    parallelCount.incrementAndGet();
                }
            });
            workers[i].start();
        }
        for (Thread worker : workers) {
            worker.join();
        }
        System.out.println("Parallel count: " + parallelCount.get());
    }
}
~~~

Chạy:

~~~bash
javac AtomicUpdatesDemo.java
java AtomicUpdatesDemo
~~~

Kết quả chuẩn:

~~~text
getAndIncrement: 10, now=11
incrementAndGet: 12, now=12
getAndAdd(5): 12, now=17
addAndGet(-2): 15, now=15
getAndUpdate(x -> x * 2): 15, now=30
updateAndGet(x -> x + 3): 33, now=33
getAndAccumulate(4): 33, now=41
accumulateAndGet(50, max): 50, now=50
compareAndSet(50, 60): true, now=60
compareAndSet(50, 70): false, now=60
getAndSet(0): 60, now=0
Parallel count: 100000
~~~

Các giá trị ở phần đầu xác định vì chỉ có luồng `main` cập nhật `counter`. Ở cuối, bốn luồng cùng tăng `parallelCount` 25.000 lần; lời gọi `join()` bảo đảm luồng chính đợi các luồng hoàn thành trước khi đọc tổng, nên kết quả luôn là **100.000** nếu tất cả luồng chạy thành công. Thứ tự **từng lần tăng** giữa các luồng không được xác định, nhưng tổng của các lần tăng nguyên tử thì không bị mất.

Hai phương thức `getAndAccumulate` và `accumulateAndGet` nhận một toán hạng bổ sung và hàm ghép, sẽ được giải thích kỹ bên dưới.

## 5. getAndUpdate và updateAndGet: cập nhật qua hàm

Đôi khi thao tác không đơn giản là cộng hoặc trừ. Chẳng hạn muốn tăng một giá trị theo quy tắc riêng, giới hạn kết quả hoặc chuyển trạng thái của một bộ đếm. Java hỗ trợ:

~~~java
int old = value.getAndUpdate(x -> x * 2);
int updated = value.updateAndGet(x -> x + 3);
~~~

Trong hai phương thức, một hàm `IntUnaryOperator` biến **giá trị hiện tại** thành **giá trị mới**. Khác biệt là:

- `getAndUpdate(function)`: trả **giá trị trước cập nhật thành công**.
- `updateAndGet(function)`: trả **giá trị mới sau cập nhật thành công**.

Ví dụ, nếu `value` ban đầu là 8:

~~~java
AtomicInteger value = new AtomicInteger(8);

int a = value.getAndUpdate(x -> x * 2); // a=8; value=16
int b = value.updateAndGet(x -> x + 3); // b=19; value=19
~~~

Các hàm cập nhật có thể được chạy **nhiều lần** trong một lời gọi khi có cạnh tranh giữa các luồng. Thực thi thường dùng cơ chế thử cập nhật rồi lặp lại khi trạng thái đã thay đổi. Vì thế, hàm cập nhật nên **không có tác dụng phụ** (*side-effect-free*) và tính kết quả từ các đối số:

~~~java
value.updateAndGet(x -> Math.min(x + 1, 100));
~~~

Không nên đặt thao tác ghi cơ sở dữ liệu, gửi tin nhắn, ghi log đếm số lần nghiệp vụ, gọi dịch vụ bên ngoài hoặc tự tăng một bộ đếm khác bên trong lambda với giả định lambda chỉ được gọi đúng một lần:

~~~java
// Ví dụ SAI về kỳ vọng: lambda có thể chạy lại khi tranh chấp.
value.updateAndGet(x -> {
    externalCounter.incrementAndGet();
    return x + 1;
});
~~~

Nếu lời gọi bị thử lại, `externalCounter` có thể bị tăng nhiều hơn một lần trong khi `value` chỉ cập nhật thành công một lần. Đưa tác dụng phụ ra sau thao tác thành công, đồng thời xem xét tính nhất quán của nghiệp vụ nếu cần cập nhật nhiều hệ thống.

### Ví dụ giới hạn tối đa 100

~~~java
AtomicInteger progress = new AtomicInteger(98);

int after = progress.updateAndGet(x -> Math.min(100, x + 1));
// after = 99

after = progress.updateAndGet(x -> Math.min(100, x + 1));
// after = 100

after = progress.updateAndGet(x -> Math.min(100, x + 1));
// after = 100
~~~

Trong các ví dụ này, một phép cập nhật nguyên tử được áp dụng trên một số nguyên tại một thời điểm. Nếu nghiệp vụ có nhiều trường cần giữ bất biến cùng nhau, cần một thiết kế đồng bộ tổng thể.

## 6. getAndAccumulate và accumulateAndGet: ghép thêm toán hạng

Khi phép cập nhật cần cả **giá trị hiện tại** và **một toán hạng** riêng, dùng:

~~~java
value.getAndAccumulate(x, (current, operand) -> ...);
value.accumulateAndGet(x, (current, operand) -> ...);
~~~

Hàm thuộc loại `IntBinaryOperator`. Thứ tự tham số là **giá trị hiện tại trước**, **toán hạng `x` sau**. Lấy ví dụ:

~~~java
AtomicInteger score = new AtomicInteger(10);

int previous = score.getAndAccumulate(
        4, (current, increment) -> current + increment * 2);
// previous=10, score=18

int latest = score.accumulateAndGet(25, Math::max);
// latest=25, score=25
~~~

Ở đây `Math::max` giữ giá trị lớn hơn giữa giá trị đang lưu và ngưỡng truyền vào. Thao tác có thể phù hợp với việc giữ “giá trị lớn nhất đã quan sát”.

Một số mục đích khác của hàm tích lũy:

- `Math::min`: giữ giá trị nhỏ nhất quan sát.
- `(current, increment) -> current + increment`: cộng toán hạng, tương tự `addAndGet` khi cần giá trị sau.
- `(current, factor) -> current * factor`: nhân với hệ số, có thể bị tràn `int`.
- `(current, newValue) -> Math.max(current, newValue)`: chỉ tăng đến mức cao nhất đã thấy.

Cũng giống `getAndUpdate`, hàm tích lũy có thể được thực thi lại trong khi tranh chấp. Hãy dùng **hàm thuần không có tác dụng phụ**, không giả định số lần callback được gọi bằng số cập nhật thành công.

## 7. compareAndSet: cập nhật có điều kiện bằng CAS

`compareAndSet(expectedValue, newValue)` thường được viết tắt là **CAS** (*compare-and-set*). Nó thực hiện logic nguyên tử:

> Nếu giá trị hiện tại bằng `expectedValue`, thay bằng `newValue` và trả `true`; nếu khác, không thay đổi và trả `false`.

~~~java
AtomicInteger stock = new AtomicInteger(5);

boolean first = stock.compareAndSet(5, 4);  // true; stock=4
boolean second = stock.compareAndSet(5, 3); // false; stock=4
~~~

CAS cần thiết khi cập nhật chỉ được phép xảy ra nếu trạng thái vẫn giống thời điểm ta quan sát. Nó giúp tránh kiểu cập nhật “đọc rồi ghi” làm mất thay đổi từ luồng khác.

Một vòng lặp CAS có thể biểu diễn logic “không cho giá trị giảm dưới 0”:

~~~java
static boolean tryTakeOne(AtomicInteger stock) {
    while (true) {
        int current = stock.get();
        if (current == 0) {
            return false;
        }
        if (stock.compareAndSet(current, current - 1)) {
            return true;
        }
    }
}
~~~

Đây là **mảnh phương thức** nằm trong lớp có `import java.util.concurrent.atomic.AtomicInteger;`, giả định `stock` không null và bất biến của ứng dụng bảo đảm giá trị không âm ngay từ đầu. Nếu các luồng khác đặt giá trị âm hoặc có thao tác điều chỉnh phức tạp, phải kiểm tra lại điều kiện nghiệp vụ.

Giải thích:

1. Đọc giá trị hiện tại.
2. Nếu đã bằng 0, không thể lấy thêm.
3. Thử CAS chuyển từ `current` sang `current - 1`.
4. Nếu luồng khác vừa sửa giá trị, CAS thất bại; vòng lặp đọc lại rồi quyết định trên giá trị mới.

Một cách khác với chỉ một số nguyên là:

~~~java
static boolean tryTakeOne(AtomicInteger stock) {
    int old = stock.getAndUpdate(x -> x > 0 ? x - 1 : x);
    return old > 0;
}
~~~

Chỉ chọn **một** trong hai định nghĩa phương thức `tryTakeOne` khi đưa vào cùng lớp, vì chúng có cùng chữ ký. Cách `getAndUpdate` có điều kiện ngay trong hàm nguyên tử; dù giá trị không đổi khi hết hàng, lời gọi cập nhật vẫn trả giá trị cũ để quyết định.

### Giới hạn của CAS với nhiều bước và hiện tượng ABA

CAS trên `AtomicInteger` so sánh một giá trị `int` hiện tại; nó không ghi nhớ lịch sử. Nếu một luồng nhìn thấy `A`, một luồng khác đổi `A → B → A`, thì lần CAS đầu có thể vẫn thành công vì **giá trị cuối đã quay lại A**, dù trạng thái từng thay đổi. Đây là **vấn đề ABA**.

Nếu lịch sử chuyển trạng thái hoặc version là quan trọng, có thể phải mô hình hóa thêm phiên bản, dùng loại atomic khác như `AtomicStampedReference` cho đối tượng tham chiếu, hoặc sử dụng khóa/dữ liệu phù hợp. Không nên tự suy diễn rằng CAS trên một `int` sẽ giải quyết mọi giao dịch hoặc bất biến nhiều trường.

## 8. AtomicInteger bảo đảm điều gì về đồng thời và bộ nhớ?

`AtomicInteger` cung cấp các thao tác nguyên tử cho **một giá trị nguyên** và các ngữ nghĩa bộ nhớ được quy định. Những thao tác thông dụng như `get()`, `set()`, `compareAndSet()`, `getAndIncrement()` tương ứng với việc quan sát/cập nhật trạng thái có thứ tự bộ nhớ phù hợp; không cần tự đặt `volatile` lên một biến `int` khác để biến thao tác atomic thành an toàn.

Cần tách ba khái niệm:

- **Atomicity — tính nguyên tử:** Một lần cập nhật atomic thành công không bị “nửa chừng”; nhiều luồng tăng cùng bộ đếm không làm mất cập nhật.
- **Visibility — khả năng quan sát:** Giá trị được công bố/đọc theo ngữ nghĩa bộ nhớ của phương thức, giúp các luồng có thể nhìn thấy cập nhật phù hợp.
- **Ordering — thứ tự:** Các tác vụ có thể phải tuân theo quy tắc thứ tự bộ nhớ nhất định. Những phương thức mới như `getAcquire`, `setRelease` hay `getOpaque` có ngữ nghĩa yếu hơn/tập trung hơn và chỉ nên chọn khi hiểu đúng yêu cầu đồng thời.

**Bảo đảm trên một biến không tự biến nhiều bước thành một giao dịch.** Ví dụ:

~~~java
if (balance.get() >= 10) {
    balance.addAndGet(-10);
}
~~~

Đây không phải một phép “kiểm tra rồi trừ” nguyên tử. Hai luồng có thể cùng thấy `balance = 10` và cùng trừ, để lại `-10`. Muốn giữ bất biến “không trừ quá số dư”, dùng CAS hoặc một `updateAndGet` có điều kiện cùng logic trong lambda, đồng thời xác định rõ cách báo thành công/thất bại.

Trong trường hợp có **hai** biến cần cập nhật đồng thời (ví dụ `balanceA` và `balanceB` để chuyển tiền), hai `AtomicInteger` riêng không tạo ra giao dịch nguyên tử trên cả cặp. Cần đồng bộ bằng khóa, mô hình trạng thái chung dưới một phép cập nhật, hoặc cơ chế giao dịch phù hợp.

## 9. Phân biệt atomic update với synchronized và volatile

| Công cụ | Có thể giải quyết gì? | Không đủ trong trường hợp nào? |
| --- | --- | --- |
| `volatile int count` | Bảo đảm đặc tính visibility và ordering của đọc/ghi biến `volatile` | `count++` vẫn có thể mất cập nhật |
| `AtomicInteger.incrementAndGet()` | Tăng một giá trị nguyên tử | Nhiều trường/bất biến phức tạp không tự được bảo vệ |
| `synchronized` | Cho phép bảo vệ một đoạn mã phức tạp bằng cùng một monitor | Có thể làm tăng tranh chấp hoặc khóa nếu thiết kế không phù hợp |
| `ReentrantLock` | Khóa tường minh cho miền dữ liệu lớn hơn, có một số khả năng bổ sung | Cần quản lý khóa đúng, thường dùng `try/finally` |

`AtomicInteger` thường rất thuận tiện khi bộ đếm đơn giản; vòng lặp CAS có thể thử lại khi tranh chấp, không có nghĩa mọi thao tác sẽ xong sau đúng một lần thử. Một thiết kế đúng cần chọn **đơn vị trạng thái phải được bảo vệ**, rồi chọn công cụ phù hợp.

## 10. Tràn số nguyên, giới hạn miền và loại số khác

`AtomicInteger` lưu giá trị **`int` 32-bit có dấu**. Các phép tăng/cộng không tự ném lỗi khi vượt phạm vi `int`: kết quả tuân theo quy tắc tràn số nguyên Java theo biểu diễn 32-bit.

~~~java
AtomicInteger count = new AtomicInteger(Integer.MAX_VALUE);
int next = count.incrementAndGet();
System.out.println(next); // -2147483648
~~~

Vì vậy, một bộ đếm tăng liên tục có thể **quay sang số âm**. Tính nguyên tử không đồng nghĩa có kiểm soát overflow. Nếu cần phạm vi lớn hơn, dùng `AtomicLong` (64-bit); nếu cần số rất lớn không giới hạn bởi các loại số nguyên cơ bản, cần thiết kế bộ nhớ và đồng bộ khác, vì `AtomicInteger` không thể tự biến thành `BigInteger`.

Với bộ đếm cộng dồn có tranh chấp cao giữa nhiều luồng, `LongAdder` đôi khi cho hiệu năng tốt hơn `AtomicLong` nhờ phân tán cập nhật, nhưng `sum()` không nhất thiết là **ảnh chụp nguyên tử** của toàn bộ cập nhật đang diễn ra. Không thay `AtomicInteger` bằng `LongAdder` khi cần CAS/giá trị thứ tự chính xác mỗi lần cập nhật.

Nếu yêu cầu “tăng tới mức tối đa rồi dừng”, có thể dùng:

~~~java
AtomicInteger limit = new AtomicInteger(Integer.MAX_VALUE - 1);
int updated = limit.updateAndGet(x ->
        x == Integer.MAX_VALUE ? x : x + 1);
~~~

Biểu thức này không tràn nếu giá trị bắt đầu không vượt `Integer.MAX_VALUE`, và không có tác nhân khác đặt dữ liệu về trạng thái không hợp lệ. Với nghiệp vụ cần chính sách overflow khác, hãy xác định rõ: chặn giá trị, báo lỗi, hay chuyển sang loại dữ liệu rộng hơn.

## 11. Những lỗi phổ biến

**Lỗi 1 — Nhầm giá trị trả về.** `getAndIncrement()` trả giá trị **trước** khi tăng; `incrementAndGet()` trả giá trị **sau** khi tăng. Khi phát ID hoặc đếm sự kiện, nhầm điểm bắt đầu có thể gây lệch một đơn vị.

**Lỗi 2 — Tưởng `get()` rồi `set()` là một cập nhật nguyên tử.** Hai lời gọi riêng vẫn cho phép luồng khác chen vào. Dùng `getAndAdd`, `updateAndGet`, CAS hoặc khóa theo yêu cầu.

**Lỗi 3 — Dùng `volatile int` và `++` để tránh mất cập nhật.** `volatile` không gom phép đọc, cộng và ghi thành một hành động nguyên tử.

**Lỗi 4 — Viết hàm cập nhật có tác dụng phụ.** Lambda trong `getAndUpdate`/`updateAndGet`/`accumulateAndGet` có thể được chạy nhiều lần dưới tranh chấp. Không thực hiện side effect trong callback với kỳ vọng chạy đúng một lần.

**Lỗi 5 — Đọc giá trị ngay sau khi cập nhật rồi coi đó luôn là kết quả riêng của lời gọi.** Trong nhiều luồng, ngay sau `getAndIncrement()`, một luồng khác có thể tăng thêm trước `get()`. Nếu cần biết **giá trị đã cấp cho chính lời gọi của mình**, hãy dùng trực tiếp kết quả mà phương thức trả về.

**Lỗi 6 — Cho rằng AtomicInteger giải quyết giao dịch nhiều biến.** Cập nhật `a` rồi `b` không nguyên tử trên cặp biến; luồng khác có thể quan sát trạng thái trung gian. Dùng đồng bộ phù hợp hoặc gộp trạng thái nếu phải giữ bất biến chung.

**Lỗi 7 — Quên tràn int.** `incrementAndGet()` tại `Integer.MAX_VALUE` có thể quay về `Integer.MIN_VALUE` mà không ném ngoại lệ.

**Lỗi 8 — Tưởng một vòng CAS luôn thành công ngay.** Nếu giá trị bị luồng khác sửa, CAS trả false; vòng lặp phải đọc và quyết định lại. Trong tải tranh chấp nặng, nhiều lần thử có thể xảy ra.

**Lỗi 9 — Dùng bộ đếm AtomicInteger làm ID toàn cục.** Nó chỉ quản lý trạng thái trong phạm vi đối tượng/JVM. Restart, nhiều instance, nhiều máy hoặc phạm vi `int` đều có thể phá kỳ vọng ID duy nhất dài hạn.

**Lỗi 10 — Dùng lại số thứ tự đã cấp nhưng bỏ qua giá trị trả về.** Với `getAndIncrement` đa luồng, mỗi lời gọi có một giá trị cũ riêng trước khi wrap-around; cần lưu kết quả ấy tại đúng chỗ thay vì lấy `get()` sau đó.

## 12. Bài tập áp dụng và lời giải

### Bài 1. Dự đoán giá trị trả về

~~~java
AtomicInteger x = new AtomicInteger(5);
int a = x.getAndIncrement();
int b = x.incrementAndGet();
int c = x.getAndAdd(3);
int d = x.addAndGet(-2);
~~~

**Đáp án:** `a = 5`, `b = 7`, `c = 7`, `d = 8`; giá trị cuối của `x` là `8`.

Diễn giải: bắt đầu 5 → `getAndIncrement` trả 5, lưu 6 → `incrementAndGet` lưu/trả 7 → `getAndAdd(3)` trả 7, lưu 10 → `addAndGet(-2)` lưu/trả 8.

### Bài 2. Giữ giá trị lớn nhất từng quan sát

Muốn giữ `maximum` không bao giờ giảm, khi có quan sát mới `observed`, hãy viết:

~~~java
AtomicInteger maximum = new AtomicInteger(0);
int latest = maximum.accumulateAndGet(25, Math::max);
~~~

`latest` là 25. Nếu một luồng khác đồng thời báo giá trị 30, phép tích lũy kiểu `Math.max` bảo toàn quy tắc lớn nhất của những lần cập nhật thành công. Nếu giá trị có thể âm và cần max trong toàn miền `int`, phải chọn giá trị khởi tạo phù hợp thay vì mặc định 0.

### Bài 3. Sửa kiểm tra rồi cập nhật không an toàn

Mã sau bị race:

~~~java
if (stock.get() > 0) {
    stock.decrementAndGet();
}
~~~

Cách sửa khi chỉ cần bảo vệ một `AtomicInteger` và biết `stock` ban đầu không âm:

~~~java
int previous = stock.getAndUpdate(x -> x > 0 ? x - 1 : x);
boolean taken = previous > 0;
~~~

Đây là mảnh code giả định `stock` đã được khai báo. Hàm cập nhật vừa kiểm tra vừa tính trạng thái mới trong một thao tác nguyên tử; `previous > 0` cho biết lời gọi này có lấy được một đơn vị hay không.

### Bài 4. Vì sao đoạn code có thể in giá trị khác?

~~~java
int myNumber = shared.getAndIncrement();
int observedNow = shared.get();
~~~

`observedNow` có thể lớn hơn `myNumber + 1` bởi các luồng khác có thể thực hiện thêm cập nhật giữa hai lời gọi. Kết quả `myNumber` vẫn là giá trị cũ đã được cấp **nguyên tử cho chính lời gọi**. Không giả định `get()` tiếp theo là snapshot riêng của cập nhật của luồng mình.

### Bài 5. Kiểm tra tràn số

~~~java
AtomicInteger x = new AtomicInteger(Integer.MAX_VALUE);
System.out.println(x.getAndIncrement());
System.out.println(x.get());
~~~

**Đáp án:**

~~~text
2147483647
-2147483648
~~~

Lời gọi đầu trả giá trị cũ là `Integer.MAX_VALUE`, trong khi giá trị đã lưu tăng qua biên rồi tràn thành `Integer.MIN_VALUE`.

## 13. Tóm lược cách chọn phương thức

- Cần **giá trị trước khi tăng/giảm/cộng** → dùng `getAndIncrement`, `getAndDecrement`, `getAndAdd`.
- Cần **giá trị sau khi tăng/giảm/cộng** → dùng `incrementAndGet`, `decrementAndGet`, `addAndGet`.
- Cần **hàm tính từ giá trị đang lưu** → dùng `getAndUpdate` hoặc `updateAndGet` với callback thuần, chọn giá trị cũ/mới tương ứng.
- Cần **ghép một toán hạng mới với trạng thái hiện tại** → dùng `getAndAccumulate` hoặc `accumulateAndGet`.
- Cần **chỉ cập nhật nếu còn đúng giá trị kỳ vọng** → dùng `compareAndSet` và xử lý trường hợp thất bại.
- Cần **một giá trị đếm nguyên tử** → `AtomicInteger` có thể phù hợp; cần nhiều giá trị phải thay đổi cùng lúc → chọn cơ chế đồng bộ/giao dịch bao quát trạng thái đó.

**Ghi nhớ:** Các thao tác của `AtomicInteger` cung cấp cập nhật nguyên tử trên **một số nguyên**. Khác biệt giữa `getAnd...` và `...AndGet` nằm ở **giá trị trả về trước hay sau cập nhật**; tính an toàn đồng thời không có nghĩa mọi phép toán nhiều bước, nhiều biến hoặc mọi side effect trong callback đều nguyên tử.
