# Atomic updateAndGet, getAndUpdate và các biến thể accumulate trong Java

## 1. Bối cảnh và mục tiêu

Trong chương trình đa luồng, **đọc một biến, tính giá trị mới rồi ghi lại** tưởng như đơn giản nhưng có thể làm mất cập nhật:

```java
int old = counter;
counter = old + 1;
```

*Đây là đoạn mã minh họa cho biến `int` thường, không phải chương trình độc lập.*

Khi nhiều thread chạy đồng thời, hai thread có thể đọc **cùng giá trị cũ** rồi ghi đè nhau. Kể cả khi khai báo biến là `volatile`, biểu thức `counter++` vẫn là thao tác đọc–tính–ghi gồm nhiều bước, **không phải** một cập nhật nguyên tử.

Các lớp trong `java.util.concurrent.atomic` giải quyết trường hợp một giá trị cần được cập nhật theo hàm phụ thuộc vào giá trị hiện tại. Từ **Java 8**, chúng có bốn nhóm phương thức rất hữu ích:

- `getAndUpdate(updateFunction)`: tính và ghi giá trị mới một cách atomic, nhưng **trả giá trị cũ**.
- `updateAndGet(updateFunction)`: tính và ghi giá trị mới một cách atomic, nhưng **trả giá trị mới**.
- `getAndAccumulate(x, accumulatorFunction)`: gộp giá trị hiện tại với đối số `x`, **trả giá trị cũ**.
- `accumulateAndGet(x, accumulatorFunction)`: gộp giá trị hiện tại với `x`, **trả giá trị mới**.

Đây là các phương thức **vẫn hiện hành** trong `AtomicInteger`, `AtomicLong`, `AtomicReference` và những dạng atomic array/field updater. Chúng tiện hơn việc tự viết vòng lặp compare-and-set cho nhiều phép cập nhật đơn giản, nhưng **có một lưu ý an toàn cực kỳ quan trọng**: hàm cập nhật có thể **bị gọi lại** khi có tranh chấp giữa các thread.

Sau bài, bạn có thể:

1. Chọn đúng giữa `getAndUpdate` và `updateAndGet` dựa trên dữ liệu trả về.
2. Phân biệt cập nhật **một tham số** và tích lũy **hai tham số**.
3. Đọc chính xác thứ tự đối số của accumulator function: **(current, x)**.
4. Viết hàm pure/side-effect-free để dùng an toàn trong vòng CAS retry.
5. Sử dụng các biến thể trên `AtomicInteger`, `AtomicLong`, `AtomicReference`, `AtomicIntegerArray`, `AtomicReferenceArray` và `AtomicIntegerFieldUpdater`.
6. Bảo vệ nhiều field **liên quan trong cùng một immutable state** bằng `AtomicReference`.
7. Chứng minh cập nhật đúng khi nhiều thread cùng làm việc, không dựa vào `Thread.sleep`.
8. Hiểu vì sao atomic **không đồng nghĩa** transaction nhiều object, cập nhật trong database, hoặc exactly-once side effect.
9. Xử lý overflow, exception trong lambda, null reference và lựa chọn `LongAdder` khi cần counters có mức tranh chấp cao.
10. Thiết kế code review, test và đo hiệu năng dựa trên bảo đảm thật của Java.

Các chương trình chạy được trong bài sử dụng **Java 17+** để tận dụng `record` và `List.of`/`List.copyOf`; những thao tác atomic được học đều có từ Java 8 và vẫn được hỗ trợ trong Java hiện hành.

## 2. Khái niệm atomic read–modify–write

Một cập nhật dạng `newValue = f(currentValue)` cần bảo đảm không bị chen vào một cách khiến update của thread khác bị mất. Các phương thức `updateAndGet`/`getAndUpdate` cung cấp một **thao tác cập nhật atomic đối với một biến atomic đó**.

Ví dụ, có `AtomicInteger count` chứa 10:

```text
updateAndGet(current -> current * 2)
   current = 10
   new     = 20
   atomic state becomes 20
   returns 20

getAndUpdate(current -> current + 5)
   current = 20
   new     = 25
   atomic state becomes 25
   returns 20
```

Lưu ý rằng cả hai cập nhật **state giống nhau nếu dùng cùng một hàm**. Khác biệt là **giá trị mà caller nhận lại**. Nếu caller cần biết số đã được ghi sau update, chọn `updateAndGet`; nếu cần tính chênh lệch hoặc biết snapshot trước thay đổi, chọn `getAndUpdate`.

Mô hình tương tự áp dụng cho `accumulate`: hàm nhận **hai** đối số, trong đó đối số đầu là giá trị hiện có, đối số thứ hai là dữ liệu mới cần gộp vào.

### 2.1. Bảng bốn phương thức

| API | Functional interface | Công thức nguyên tử | Trả về |
| --- | --- | --- | --- |
| `getAndUpdate(f)` | `IntUnaryOperator` / `LongUnaryOperator` / `UnaryOperator<V>` | `new = f(current)` | **current cũ** |
| `updateAndGet(f)` | Như trên | `new = f(current)` | **new đã cập nhật** |
| `getAndAccumulate(x,f)` | `IntBinaryOperator` / `LongBinaryOperator` / `BinaryOperator<V>` | `new = f(current,x)` | **current cũ** |
| `accumulateAndGet(x,f)` | Như trên | `new = f(current,x)` | **new đã cập nhật** |

Đối với array/field updater, còn phải đưa **index** hoặc **object chủ** vào trước các tham số trên. Không có tham số `parallelismThreshold` ở các phương thức này: đó là tham số của **bulk operations khác**, không thuộc atomic update.

## 3. Ví dụ `AtomicInteger`: giá trị trả về trước và sau

Lưu `AtomicReturnValuesDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicReturnValuesDemo {
    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger(10);

        int beforeDouble = counter.getAndUpdate(v -> v * 2);
        int afterDouble = counter.get();

        int afterAdd = counter.updateAndGet(v -> v + 5);

        int beforeMinus = counter.getAndAccumulate(
                3, (current, x) -> current - x);
        int afterMinus = counter.get();

        int afterMultiply = counter.accumulateAndGet(
                4, (current, x) -> current * x);

        System.out.println("beforeDouble = " + beforeDouble);
        System.out.println("afterDouble = " + afterDouble);
        System.out.println("afterAdd = " + afterAdd);
        System.out.println("beforeMinus = " + beforeMinus);
        System.out.println("afterMinus = " + afterMinus);
        System.out.println("afterMultiply = " + afterMultiply);
        System.out.println("final = " + counter.get());
    }
}
```

Chạy:

```bash
javac AtomicReturnValuesDemo.java
java AtomicReturnValuesDemo
```

Stdout:

```text
beforeDouble = 10
afterDouble = 20
afterAdd = 25
beforeMinus = 25
afterMinus = 22
afterMultiply = 88
final = 88
```

Giải thích từng bước:

- `getAndUpdate(v -> v * 2)` chuyển 10 → 20, nhưng trả **10**.
- `updateAndGet(v -> v + 5)` chuyển 20 → 25, trả **25**.
- `getAndAccumulate(3,(current,x)->current-x)` chuyển 25 → 22, trả **25**.
- `accumulateAndGet(4,(current,x)->current*x)` chuyển 22 → 88, trả **88**.

**Điểm cần ghi nhớ:** `getAndUpdate` và `updateAndGet` không nên bị đánh giá chỉ qua giá trị trả về. Muốn biết trạng thái sau update, dùng `get()` hoặc giá trị mới của `updateAndGet`; muốn biết state trước đó, dùng return từ `getAndUpdate`.

### 3.1. So với `getAndIncrement` và `incrementAndGet`

Các phép đơn giản có sẵn:

- `counter.getAndIncrement()`: cộng 1, trả giá trị cũ.
- `counter.incrementAndGet()`: cộng 1, trả giá trị mới.
- `counter.getAndAdd(delta)` và `counter.addAndGet(delta)`: cộng số cho trước, trả giá trị cũ/mới.
- `counter.getAndSet(value)`: thay bằng giá trị cho trước, trả giá trị cũ.

Nếu chỉ cộng 1, dùng `incrementAndGet` có thể rõ nghĩa và phù hợp hơn `updateAndGet(v -> v + 1)`. Các phương thức nhận lambda phát huy tác dụng khi có **logic chuyển trạng thái tùy biến**: giới hạn tối đa, chuyển trạng thái có điều kiện, bitmask, rolling sequence, dựng immutable DTO mới.

## 4. Thứ tự tham số `(current, x)` của accumulator

Javadoc quy định hàm nhị phân nhận **giá trị hiện tại làm tham số thứ nhất**, còn `x` được truyền vào `accumulate` làm tham số thứ hai. Đây là điểm rất dễ đảo nhầm.

Ví dụ từ state 10:

```text
getAndAccumulate(3, (current, x) -> current * 10 + x)

current = 10
x       = 3
new     = 10 * 10 + 3 = 103
returns old = 10
```

Không được suy ngược phép tính thành `3*10+10=40`.

Lưu `AtomicAccumulateOrderDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicAccumulateOrderDemo {
    public static void main(String[] args) {
        AtomicInteger value = new AtomicInteger(10);

        int old = value.getAndAccumulate(
                3, (current, x) -> current * 10 + x);
        int afterAppend = value.get();

        int afterMinus = value.accumulateAndGet(
                2, (current, x) -> current - x);

        int previousBeforeLastMinus = value.getAndAccumulate(
                4, (current, x) -> current - x);

        System.out.println("old = " + old);
        System.out.println("afterAppend = " + afterAppend);
        System.out.println("afterMinus = " + afterMinus);
        System.out.println("previousBeforeLastMinus = " +
                previousBeforeLastMinus);
        System.out.println("final = " + value.get());
    }
}
```

```bash
javac AtomicAccumulateOrderDemo.java
java AtomicAccumulateOrderDemo
```

```text
old = 10
afterAppend = 103
afterMinus = 101
previousBeforeLastMinus = 101
final = 97
```

**Phân biệt với parallel reduction:** `AtomicInteger.accumulateAndGet` cập nhật **một ô trạng thái** theo thứ tự atomic nào đó; hàm nhị phân **không bắt buộc** phải giao hoán/kết hợp được như reducer dùng cho các bulk parallel reductions. Phép trừ hay nối chuỗi **hợp lệ ở đây** nếu được định nghĩa rõ ràng. Nhưng nếu nhiều thread cùng gọi với giá trị khác nhau, **thứ tự cập nhật thực tế có thể khác nhau**, nên kết quả cuối của hàm không giao hoán có thể phụ thuộc lịch thực thi.

**Đối với accumulator function:** yêu cầu chính từ Javadoc là **side-effect-free**, vì nó có thể được đánh giá lại khi CAS retry. Điều này khác với yêu cầu đại số đối với các bộ `LongAccumulator`/`ConcurrentHashMap.reduce` dùng reduction song song.

## 5. `AtomicLong`: phép cập nhật với số nguyên 64 bit

`AtomicLong` có cùng bốn nhóm phương thức, nhưng dùng `LongUnaryOperator` và `LongBinaryOperator`.

Lưu `AtomicLongUpdateDemo.java`:

```java
import java.util.concurrent.atomic.AtomicLong;

public class AtomicLongUpdateDemo {
    public static void main(String[] args) {
        AtomicLong balance = new AtomicLong(1_000L);

        long previous = balance.getAndAccumulate(
                250L, Long::sum);
        long afterDeposit = balance.get();

        long afterDouble = balance.accumulateAndGet(
                2L, (current, x) -> current * x);

        long afterMinimum = balance.updateAndGet(
                current -> Math.max(current, 3_000L));

        long oldBeforeDivide = balance.getAndUpdate(
                current -> current / 3L);

        System.out.println("previous = " + previous);
        System.out.println("afterDeposit = " + afterDeposit);
        System.out.println("afterDouble = " + afterDouble);
        System.out.println("afterMinimum = " + afterMinimum);
        System.out.println("oldBeforeDivide = " +
                oldBeforeDivide);
        System.out.println("final = " + balance.get());
    }
}
```

```bash
javac AtomicLongUpdateDemo.java
java AtomicLongUpdateDemo
```

```text
previous = 1000
afterDeposit = 1250
afterDouble = 2500
afterMinimum = 3000
oldBeforeDivide = 3000
final = 1000
```

`Long::sum` làm thao tác cộng như một biểu thức trong CAS loop. Nếu chỉ cần cộng `delta` vào long atomic, `getAndAdd(delta)` hoặc `addAndGet(delta)` thường trực tiếp và diễn đạt ý định rõ hơn.

**Không nhầm AtomicLong với xử lý giao dịch tiền tệ đầy đủ.** Một scalar `long` có thể mô hình hóa số đơn vị tiền nhỏ nhất, nhưng atomic cập nhật một giá trị không tự kiểm soát nhiều tài khoản, ledger entries, persistence, authorization hoặc rollback trên database. Các quy tắc đó cần thiết kế giao dịch ở tầng ứng dụng/storage.

## 6. Cập nhật có điều kiện: chặn giá trị vượt ngưỡng

Một ứng dụng có thể cần clamp counter vào `[0, max]` hoặc chỉ chuyển trạng thái nếu thỏa điều kiện.

`updateAndGet` hỗ trợ hàm tính giá trị mới từ state hiện tại:

```java
int capped = count.updateAndGet(
        current -> Math.min(10, current + 5));
```

*Snippet giả định `count` là `AtomicInteger` đã khai báo.*

Lưu `AtomicBoundedCounterDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicBoundedCounterDemo {
    public static void main(String[] args) {
        AtomicInteger count = new AtomicInteger(8);

        int afterCapped = count.updateAndGet(
                current -> Math.min(10, current + 5));

        int beforeDecrease = count.getAndUpdate(
                current -> Math.max(0, current - 4));

        int afterDecrease = count.get();

        int afterMax = count.accumulateAndGet(
                9, Math::max);

        System.out.println("afterCapped = " + afterCapped);
        System.out.println("beforeDecrease = " + beforeDecrease);
        System.out.println("afterDecrease = " + afterDecrease);
        System.out.println("afterMax = " + afterMax);
    }
}
```

```bash
javac AtomicBoundedCounterDemo.java
java AtomicBoundedCounterDemo
```

```text
afterCapped = 10
beforeDecrease = 10
afterDecrease = 6
afterMax = 9
```

Tính đúng đắn **phụ thuộc vào invariant**. Với phép `current + delta`, nếu có nguy cơ tràn `int` trước khi `Math.min` chạy, clamp bằng `Math.min(max, current + delta)` **chưa đủ**. Cần kiểm tra overflow hoặc dùng kiểu rộng hơn và các hàm `Math.addExact`, trừ khi đã chứng minh input trong khoảng an toàn.

### 6.1. Muốn biết thao tác có thành công không?

`updateAndGet` trả **state mới**, nhưng đôi khi state mới không cho biết “yêu cầu này được chấp nhận hay từ chối”.

Ví dụ inventory có 0 hàng: lambda `current > 0 ? current - 1 : current` giữ 0. Hai lần gọi có thể cùng trả 0, nhưng một lần có thể vừa bán đơn vị cuối cùng và lần khác không bán được. Nếu cần kết quả nghiệp vụ per-request, hãy dùng:

- Một vòng `compareAndSet` thiết kế để trả **trạng thái thành công/thất bại rõ ràng** sau CAS thành công.
- `AtomicReference` giữ immutable state/metadata đầy đủ rồi quyết định kết quả theo contract.
- Khóa hoặc transaction trong các trường hợp update nhiều biến/trạng thái ngoài JVM.

**Không phát sinh sự kiện “đã bán hàng” ngay trong lambda**; lambda có thể bị gọi lại khi tranh chấp và tạo duplicate side effect.

## 7. Cơ chế CAS: vì sao callback có thể chạy nhiều lần?

Triển khai có thể dùng vòng **compare-and-set (CAS)**:

```text
read current
     |
calculate new = f(current)
     |
CAS(current, new) --------------+
     |                          |
     | success                  | failure (other thread changed state)
     v                          v
  return old/new             read latest value
                                |
                                +-- evaluate f(latest) again
```

Đây là **mô hình khái niệm** để hiểu behavior. JDK có thể tối ưu vòng lặp, dùng `weakCompareAndSetVolatile` trong nội bộ và tránh tính lại nếu giá trị đọc chưa đổi; không dựa vào số lần gọi hàm cụ thể như một contract.

Javadoc Oracle nêu rõ: **update function nên không có side effect vì nó có thể được áp dụng lại khi nỗ lực cập nhật thất bại do tranh chấp giữa thread**.

Vì vậy **đừng** viết:

```java
counter.updateAndGet(current -> {
    sendPaymentRequest();    // SAI: có thể chạy nhiều lần
    return current + 1;
});
```

*Snippet là anti-pattern minh họa; `counter` và `sendPaymentRequest` không được định nghĩa. Không chạy trên môi trường thật.*

Hoặc:

```java
counter.accumulateAndGet(delta, (current, amount) -> {
    auditLog.append("charged"); // SAI: không bảo đảm exactly once
    return current + amount;
});
```

*Snippet anti-pattern, không phải chương trình độc lập.*

Hàm đúng nên tính **một kết quả chỉ từ các đối số và dữ liệu bất biến**:

```java
counter.accumulateAndGet(delta,
        (current, amount) -> current + amount);
```

*Snippet giả định `counter` và `delta` đã khai báo.*

Nếu cập nhật thành công và bạn cần gửi notification, có thể thực hiện side effect **sau khi operation trả về**, nhưng vẫn phải xem xét mô hình lỗi (process crash giữa update và notification, retry phía caller, yêu cầu idempotency). Một atomic variable trong RAM không cung cấp transaction với hệ thống ngoài.

## 8. Demo kiểm thử CAS retry bằng hai thread có đồng bộ

Có thể chứng minh **hàm đã được tính lại** bằng cách tạo một cuộc tranh chấp có chủ đích:

1. Thread A vào lần tính lambda đầu tiên, đọc `current = 0` rồi tạm đợi.
2. Thread B ghi atomically giá trị `10`.
3. Thread A tiếp tục: CAS dựa trên `0` thất bại vì state đã đổi thành `10`.
4. Vòng update tính lại hàm trên giá trị mới và kết thúc ở `11`.

Trong test này, một counter ghi nhận **số lần callback được gọi** là instrumentation cố ý; trong code production chính side effect như vậy **không nên** đặt trong hàm cập nhật.

Lưu `AtomicRetryUnderContentionDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicRetryUnderContentionDemo {
    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        AtomicInteger state = new AtomicInteger(0);
        AtomicInteger evaluations = new AtomicInteger();

        CountDownLatch firstCall = new CountDownLatch(1);
        CountDownLatch changed = new CountDownLatch(1);

        Thread updater = new Thread(() ->
                state.updateAndGet(current -> {
                    int n = evaluations.incrementAndGet();

                    if (n == 1) {
                        firstCall.countDown();
                        await(changed);
                    }

                    return current + 1;
                }));

        Thread interferer = new Thread(() -> {
            await(firstCall);
            state.set(10);
            changed.countDown();
        });

        updater.start();
        interferer.start();

        updater.join();
        interferer.join();

        System.out.println("final = " + state.get());
        System.out.println("lambdaInvokedAgain = " +
                (evaluations.get() > 1));
    }
}
```

```bash
javac AtomicRetryUnderContentionDemo.java
java AtomicRetryUnderContentionDemo
```

```text
final = 11
lambdaInvokedAgain = true
```

**Ý nghĩa:** một lần gọi `updateAndGet` không đồng nghĩa **một lần gọi lambda**. Bất kỳ I/O, gửi message, sinh ID không idempotent hoặc mutation state bên ngoài trong lambda đều có nguy cơ chạy hơn một lần.

Hàm tính thuần:

```java
current -> current + 1
```

được phép đánh giá lại bao nhiêu lần cũng cho ý nghĩa giống nhau trên **mỗi giá trị current mà nó nhận được**.

### 8.1. Side-effect-free khác với “không được tạo object”

Một lambda `AtomicReference.updateAndGet(old -> new State(...))` có thể **tạo object immutable mới** và vẫn side-effect-free theo nghĩa ứng dụng: nó không sửa object đã publish hay gửi I/O. Nếu CAS thất bại, object trung gian có thể bị bỏ và lambda chạy lại; đây là chi phí allocation chấp nhận được khi cần state immutable.

**Không nên** mutate một `List`/`Map` đã được nhiều thread chia sẻ trong lambda rồi trả lại chính object đó; CAS chỉ bảo vệ **reference**, không đảo ngược các mutation đã xảy ra.

## 9. `AtomicReference<V>` với immutable state nhiều trường

`AtomicInteger`/`AtomicLong` bảo vệ **một giá trị primitive**. Khi hai hoặc nhiều trường phải cùng thay đổi theo invariant, có thể đặt chúng vào **một object immutable** và dùng `AtomicReference<State>` để thay **toàn bộ state** bằng một CAS.

Lưu `AtomicReferenceStateDemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicReferenceStateDemo {
    record AccountState(long balance, int revision) {
    }

    public static void main(String[] args) {
        AtomicReference<AccountState> account =
                new AtomicReference<>(
                        new AccountState(100L, 0));

        AccountState previous = account.getAndUpdate(
                state -> new AccountState(
                        state.balance() - 25L,
                        state.revision() + 1));

        AccountState updated = account.accumulateAndGet(
                new AccountState(10L, 0),
                (current, deposit) -> new AccountState(
                        current.balance() + deposit.balance(),
                        current.revision() + 1));

        System.out.println("previous = " + previous);
        System.out.println("updated = " + updated);
        System.out.println("final = " + account.get());
    }
}
```

```bash
javac AtomicReferenceStateDemo.java
java AtomicReferenceStateDemo
```

```text
previous = AccountState[balance=100, revision=0]
updated = AccountState[balance=85, revision=2]
final = AccountState[balance=85, revision=2]
```

Cách viết này bảo đảm reader gọi `account.get()` nhận một **pair balance + revision cùng từ một state đã publish**, không phải balance mới và revision cũ bị trộn do hai atomic độc lập.

**Quan trọng:** object phải thực sự immutable ở các field có liên quan. Java `record` có các field final, nhưng nếu record chứa một `ArrayList` mutable hoặc một object khác có mutable state, record đó chỉ **shallow immutable**; mutation bên trong vẫn có thể xảy ra ngoài CAS. Dùng các cấu trúc bất biến hoặc defensive copy khi cần.

**Không coi đây là hệ thống chuyển tiền nhiều tài khoản**: CAS trên một AtomicReference đảm bảo cập nhật **một reference trong một process**, không tạo transaction giữa hai tài khoản, hai tiến trình hoặc database. Kiểm soát quy tắc số dư và persistence ở tầng nghiệp vụ phù hợp.

## 10. Cập nhật danh sách bằng cách tạo bản copy bất biến

Một lỗi phổ biến với `AtomicReference<List<T>>`:

```java
ref.updateAndGet(list -> {
    list.add("A");     // SAI nếu list đang chia sẻ
    return list;
});
```

*Snippet phản ví dụ: nếu callback chạy nhiều lần, danh sách có thể bị sửa nhiều lần; CAS không bảo vệ mutation của `list`.*

Thay vào đó, lấy state cũ làm nguồn chỉ đọc, tạo một list **mới**, thay reference bằng list bất biến:

Lưu `AtomicReferenceListDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicReferenceListDemo {
    public static void main(String[] args) {
        AtomicReference<List<String>> state =
                new AtomicReference<>(List.of());

        List<String> afterOne = state.updateAndGet(old -> {
            List<String> next = new ArrayList<>(old);
            next.add("A");
            return List.copyOf(next);
        });

        List<String> afterMore = state.accumulateAndGet(
                List.of("B", "C"),
                (old, incoming) -> {
                    List<String> next = new ArrayList<>(old);
                    next.addAll(incoming);
                    return List.copyOf(next);
                });

        System.out.println("afterOne = " + afterOne);
        System.out.println("afterMore = " + afterMore);
        System.out.println("sameFinal = " +
                state.get().equals(afterMore));
    }
}
```

```bash
javac AtomicReferenceListDemo.java
java AtomicReferenceListDemo
```

```text
afterOne = [A]
afterMore = [A, B, C]
sameFinal = true
```

Ở đây mỗi lần CAS thử lại chỉ tạo **bản copy cục bộ mới**, không chạm một list dùng chung. Sau khi CAS thành công, state là một list **unmodifiable** theo contract của `List.copyOf`. `List.copyOf` không cho phép phần tử null và cũng không làm immutable các object mutable bên trong list.

**Giới hạn hiệu năng:** copy cả danh sách mỗi lần cập nhật có chi phí O(n). Nếu danh sách rất lớn, ghi liên tục hoặc nhiều thread cùng append, đây có thể không phải cấu trúc phù hợp. Cân nhắc concurrent queue, cấu trúc persistent immutable hoặc batching tùy bài toán; đừng dùng CAS-loop copy list như một giải pháp chung cho mọi collection.

## 11. `AtomicReference` cho phép null — nhưng lambda phải xử lý

Khác với `ConcurrentHashMap` không chấp nhận value null, `AtomicReference<V>` có thể giữ `null` như một trạng thái hợp lệ. Nếu lambda gọi method trên current mà không kiểm tra null, có thể ném `NullPointerException`.

Lưu `AtomicReferenceNullDemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicReferenceNullDemo {
    public static void main(String[] args) {
        AtomicReference<String> status =
                new AtomicReference<>(null);

        String initialized = status.updateAndGet(
                previous ->
                        previous == null ? "READY" : previous);

        String old = status.getAndUpdate(
                String::toLowerCase);

        String extended = status.accumulateAndGet(
                "!", String::concat);

        System.out.println("initialized = " + initialized);
        System.out.println("old = " + old);
        System.out.println("extended = " + extended);
        System.out.println("final = " + status.get());
    }
}
```

```bash
javac AtomicReferenceNullDemo.java
java AtomicReferenceNullDemo
```

```text
initialized = READY
old = READY
extended = ready!
final = ready!
```

Nếu callback trả null, `AtomicReference` có thể cập nhật thành null. Điều này có thể là contract hợp lệ như “không có giá trị”, nhưng phải xem xét cách các thread khác đọc và cách code bảo vệ null.

Một `null` từ atomic reference không đồng nghĩa “future bị lỗi” hay “key thiếu trong map”; đây là giá trị hiện tại của chính reference, cần được giải thích theo domain.

## 12. Mảng atomic: `AtomicIntegerArray` và `AtomicReferenceArray`

Khi cần nhiều slot độc lập, các class atomic array cung cấp overload nhận **index**:

- `getAndUpdate(index, operator)` / `updateAndGet(index, operator)`.
- `getAndAccumulate(index, x, operator)` / `accumulateAndGet(index, x, operator)`.
- `get(index)`, `set(index,value)`, `compareAndSet(index,expected,update)`.

Mỗi phép cập nhật bảo vệ **một slot**. Nó **không** làm thao tác cập nhật hai index khác nhau trở thành một transaction.

Lưu `AtomicArrayVariantsDemo.java`:

```java
import java.util.concurrent.atomic.AtomicIntegerArray;
import java.util.concurrent.atomic.AtomicReferenceArray;

public class AtomicArrayVariantsDemo {
    public static void main(String[] args) {
        AtomicIntegerArray numbers =
                new AtomicIntegerArray(3);

        int oldAtOne = numbers.getAndUpdate(
                1, current -> current + 5);

        int afterAccumulate = numbers.accumulateAndGet(
                1, 7, Integer::sum);

        numbers.updateAndGet(
                2, current -> current + 3);

        int previousAtTwo = numbers.getAndAccumulate(
                2, 2, (current, x) -> current * x);

        AtomicReferenceArray<String> labels =
                new AtomicReferenceArray<>(
                        new String[]{"a", "b"});

        String first = labels.updateAndGet(
                0, String::toUpperCase);
        String second = labels.accumulateAndGet(
                1, "!", String::concat);

        System.out.println("oldAtOne = " + oldAtOne);
        System.out.println("afterAccumulate = " +
                afterAccumulate);
        System.out.println("previousAtTwo = " +
                previousAtTwo);
        System.out.println("values = [" +
                numbers.get(0) + ", " +
                numbers.get(1) + ", " +
                numbers.get(2) + "]");
        System.out.println("referenceValues = [" +
                first + ", " + second + "]");
    }
}
```

```bash
javac AtomicArrayVariantsDemo.java
java AtomicArrayVariantsDemo
```

```text
oldAtOne = 0
afterAccumulate = 12
previousAtTwo = 3
values = [0, 12, 6]
referenceValues = [A, b!]
```

Các index từ 0 đến `length()-1`. Truy cập ngoài phạm vi ném `IndexOutOfBoundsException`. Cũng giống `AtomicReference` thường, `AtomicReferenceArray` bảo vệ **việc thay reference ở một slot**, không tự bảo vệ mutable object được trỏ tới.

**Chọn kiểu:** nếu cần một mảng dài với từng phần tử có update atomically, atomic array hợp lý; nếu cần một invariant liên quan tất cả index, cân nhắc immutable aggregate state, lock hoặc cấu trúc phù hợp hơn.

## 13. `AtomicIntegerFieldUpdater`: cập nhật một field volatile trong object

Không phải lúc nào cũng cần bọc mỗi counter trong một object `AtomicInteger`. `AtomicIntegerFieldUpdater<T>` cung cấp atomic update đối với một field `volatile int` có quyền truy cập hợp lệ trong một object thuộc class đích.

Yêu cầu quan trọng:

- Field mục tiêu phải có kiểu đúng (ví dụ `volatile int` cho `AtomicIntegerFieldUpdater`).
- Không được là field tùy ý không volatile hoặc dùng sai kiểu dữ liệu.
- Java access control vẫn áp dụng; việc gọi `newUpdater(...)` có thể thất bại do field không tồn tại, sai modifier hoặc không đủ quyền.
- Các cập nhật của updater áp dụng cho **field trên object được truyền vào**, không phải một object updater tự lưu counter.
- Hàm callback vẫn phải side-effect-free và có thể bị tính lại khi contention.

Lưu `AtomicFieldUpdaterDemo.java`:

```java
import java.util.concurrent.atomic.AtomicIntegerFieldUpdater;

public class AtomicFieldUpdaterDemo {
    static class Holder {
        volatile int count;
    }

    private static final AtomicIntegerFieldUpdater<Holder>
            COUNT = AtomicIntegerFieldUpdater.newUpdater(
                    Holder.class, "count");

    public static void main(String[] args) {
        Holder holder = new Holder();

        int previous = COUNT.getAndUpdate(
                holder, current -> current + 2);

        int updated = COUNT.accumulateAndGet(
                holder, 5, Integer::sum);

        System.out.println("previous = " + previous);
        System.out.println("updated = " + updated);
        System.out.println("fieldValue = " + holder.count);
    }
}
```

```bash
javac AtomicFieldUpdaterDemo.java
java AtomicFieldUpdaterDemo
```

```text
previous = 0
updated = 7
fieldValue = 7
```

Có các họ tương tự như `AtomicLongFieldUpdater` và `AtomicReferenceFieldUpdater`, với yêu cầu modifier/kiểu field tương ứng.

### 13.1. Khi nào không nên dùng field updater?

`AtomicFieldUpdater` có nhiều ràng buộc field, quyền truy cập và chi tiết layout object. Nếu không có lý do rõ về memory footprint hoặc tương thích object model, dùng `AtomicInteger`/`AtomicReference` thường trực quan hơn. Trong các codebase mới có nhu cầu access mode chi tiết hoặc cập nhật field với VarHandle, `VarHandle` là API hiện hành từ Java 9; nhưng không nên tự chuyển mọi code sang VarHandle nếu chỉ cần bốn phép cập nhật thông dụng.

## 14. Nhiều thread cập nhật chung một AtomicInteger

Muốn chứng minh **không mất update**, chạy nhiều thread, mỗi thread cập nhật 1.000 lần, rồi chờ mọi task hoàn tất trước khi đọc kết quả. Đây là bài test tính đúng đắn, không đo tốc độ.

Lưu `AtomicConcurrentCounterDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

public class AtomicConcurrentCounterDemo {
    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger();
        ExecutorService executor =
                Executors.newFixedThreadPool(4);

        try {
            CompletableFuture<?>[] tasks =
                    IntStream.range(0, 4)
                    .mapToObj(worker -> CompletableFuture.runAsync(
                            () -> {
                                for (int i = 0; i < 1_000; i++) {
                                    counter.updateAndGet(
                                            old -> old + 1);
                                }
                            }, executor))
                    .toArray(CompletableFuture<?>[]::new);

            CompletableFuture.allOf(tasks).join();

            System.out.println("expected = 4000");
            System.out.println("actual = " + counter.get());
            System.out.println("correct = " +
                    (counter.get() == 4_000));
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac AtomicConcurrentCounterDemo.java
java AtomicConcurrentCounterDemo
```

```text
expected = 4000
actual = 4000
correct = true
```

Ở đây kết quả cuối là 4000 vì phép cộng 1 là cập nhật atomic cho một biến và **toàn bộ writers đã kết thúc trước khi assert**. Không cần phụ thuộc cách thread interleave.

**Đừng suy từ bài test này rằng updateAndGet luôn tối ưu nhất cho counter.** Nếu nghiệp vụ chỉ tăng 1, `incrementAndGet` diễn đạt ngắn hơn; nếu chỉ cần thống kê tổng cộng rất nhiều thread, `LongAdder` có thể cho throughput tốt hơn dưới contention, nhưng `sum()` có semantics khác khi đang cập nhật. Xem mục 19.

## 15. Bảo toàn invariant nhiều field với AtomicReference

Một ví dụ nhiều field là hàng tồn kho gồm:

- `available`: số lượng còn lại.
- `sold`: số lượng đã bán.

Giả sử hệ thống ban đầu có 3 đơn vị và chỉ cho giảm available khi available > 0. Muốn giữ invariant `available + sold == 3`, đặt cả hai vào **cùng một record** rồi cập nhật cả state bằng `AtomicReference.updateAndGet`.

Lưu `AtomicInventoryInvariantDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.IntStream;

public class AtomicInventoryInvariantDemo {
    record Stock(int available, int sold) {
    }

    public static void main(String[] args) {
        AtomicReference<Stock> inventory =
                new AtomicReference<>(new Stock(3, 0));

        ExecutorService executor =
                Executors.newFixedThreadPool(3);

        try {
            CompletableFuture<?>[] requests =
                    IntStream.range(0, 5)
                    .mapToObj(i -> CompletableFuture.runAsync(
                            () -> inventory.updateAndGet(
                                    current ->
                                            current.available() > 0
                                            ? new Stock(
                                                    current.available() - 1,
                                                    current.sold() + 1)
                                            : current),
                            executor))
                    .toArray(CompletableFuture<?>[]::new);

            CompletableFuture.allOf(requests).join();

            Stock result = inventory.get();

            System.out.println("state = " + result);
            System.out.println("invariant = " +
                    (result.available() + result.sold() == 3));
            System.out.println("nonNegative = " +
                    (result.available() >= 0));
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac AtomicInventoryInvariantDemo.java
java AtomicInventoryInvariantDemo
```

```text
state = Stock[available=0, sold=3]
invariant = true
nonNegative = true
```

Có 5 request tranh chấp 3 đơn vị; **chỉ ba đơn vị được trừ vào state**, hai request còn lại giữ state ở 0. Tuy nhiên, ví dụ này **không trả trạng thái thành công cho mỗi request**, không ghi order, không có persistence hay transaction phân tán. Trong hệ thống bán hàng thật, cần thiết kế cách báo kết quả cho từng request và phối hợp database/đơn hàng.

**Không đặt `chargeCreditCard()` bên trong lambda cập nhật**: do CAS retry, một request có thể bị charge nhiều lần dù chỉ một lần cập nhật state. Tách bước ghi nhận quyết định bán hàng và bước tương tác hệ thống ngoài thành workflow giao dịch/idempotent rõ ràng.

## 16. Overflow và exception của update function

`AtomicInteger` và `AtomicLong` có phạm vi số hữu hạn. Nếu hàm cập nhật dùng phép `current + 1` với `int` ở `Integer.MAX_VALUE`, kết quả Java tràn về `Integer.MIN_VALUE` theo quy tắc số nguyên.

`AtomicInteger` làm phép cập nhật atomically, **không tự kiểm tra overflow**.

Nếu nghiệp vụ không cho phép overflow, dùng `Math.addExact`/`Math.multiplyExact` trong updater (hoặc quy tắc kiểm tra bằng phạm vi rộng hơn) để ném exception thay vì ghi giá trị tràn.

Lưu `AtomicOverflowDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicOverflowDemo {
    public static void main(String[] args) {
        AtomicInteger wrapping =
                new AtomicInteger(Integer.MAX_VALUE);

        int wrapped = wrapping.updateAndGet(
                current -> current + 1);

        AtomicInteger checked =
                new AtomicInteger(Integer.MAX_VALUE);

        try {
            checked.accumulateAndGet(
                    1, Math::addExact);
            System.out.println("unexpected");
        } catch (ArithmeticException e) {
            System.out.println("checkedRejected = true");
        }

        System.out.println("wrapped = " + wrapped);
        System.out.println("checkedValue = " + checked.get());
    }
}
```

```bash
javac AtomicOverflowDemo.java
java AtomicOverflowDemo
```

```text
checkedRejected = true
wrapped = -2147483648
checkedValue = 2147483647
```

Trong ví dụ không có concurrent writer, exception xảy ra **trước khi cập nhật**, nên `checked` vẫn giữ `Integer.MAX_VALUE`. Nhưng khi có thread khác, không nên khẳng định sau exception toàn bộ state “chưa ai thay đổi”: một thread khác vẫn có thể cập nhật AtomicInteger đồng thời.

### 16.1. Nếu lambda ném exception

Nếu update function throw, **lần thử cập nhật đó** không tạo giá trị mới từ hàm. Exception được truyền cho caller (được bọc thêm hay không tùy call path của ứng dụng). Đừng nuốt exception rồi giả vờ cập nhật thành công.

Lưu `AtomicUpdateExceptionDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicUpdateExceptionDemo {
    public static void main(String[] args) {
        AtomicInteger value = new AtomicInteger(3);

        try {
            value.updateAndGet(current -> {
                if (current >= 3) {
                    throw new IllegalArgumentException(
                            "limit reached");
                }
                return current + 1;
            });
            System.out.println("unexpected");
        } catch (IllegalArgumentException e) {
            System.out.println("rejected = true");
        }

        System.out.println("afterRejected = " + value.get());

        int afterValid = value.updateAndGet(
                current -> current - 1);

        System.out.println("afterValid = " + afterValid);
    }
}
```

```bash
javac AtomicUpdateExceptionDemo.java
java AtomicUpdateExceptionDemo
```

```text
rejected = true
afterRejected = 3
afterValid = 2
```

Với code gọi API thực, nên log nguyên nhân tại tầng được phép và trả thông báo domain phù hợp. Không biến exception từ callback thành một side effect khác chạy bên trong vòng CAS rồi bỏ qua.

## 17. Phép cập nhật đơn nhất không biến cả workflow thành atomic

Một AtomicInteger đảm bảo atomicity của việc cập nhật **một giá trị**; nó không tự tạo atomicity cho:

- Hai `AtomicInteger` riêng lẻ.
- Hai slot khác nhau trong `AtomicIntegerArray`.
- Một update AtomicReference và một database transaction.
- Một atomic counter với một network request đã gửi.
- Việc cập nhật object mutable nằm sau một AtomicReference.
- Một quy trình nhiều bước có quy tắc kiểm tra và side effect tách rời mà không có bảo vệ.

Ví dụ sai:

```java
if (balance.get() >= amount) {
    balance.addAndGet(-amount);
}
```

*Đây là snippet anti-pattern: `balance` và `amount` cần được khai báo. Check và update là hai thao tác riêng, nên nhiều thread có thể cùng đọc đủ số dư rồi cùng trừ.*

**Cách sửa** với một numeric state: dùng `updateAndGet` có condition ngay trong callback để giữ invariant về state, rồi thiết kế cách báo thành công; hoặc viết CAS loop trả kết quả đúng khi operation chỉ được chấp nhận nếu đủ số dư. Nếu nghiệp vụ cần nhiều trường/kết quả, dùng immutable state trong một AtomicReference; nếu cần nhiều tài khoản/database, dùng transaction hoặc cơ chế đồng bộ thích hợp.

### 17.1. CAS retry và visibility

Theo Java API hiện hành, các phương thức này có **memory effects như `VarHandle.compareAndSet`**. Điều đó bao gồm các bảo đảm cập nhật/quan sát state phù hợp với CAS trên chính biến atomic.

Không nên mô tả mỗi lần đọc state là một transaction snapshot của toàn ứng dụng. Thread-safe ở cấp atomic variable **không đồng nghĩa** an toàn khi truy cập hàng chục object mutable mà lambda đóng trên đó.

### 17.2. Reference equality và ABA

`AtomicReference.compareAndSet(expected,newValue)` so sánh **reference identity** cho expected state; các phương thức functional update có thể dùng CAS nội bộ. Trong một số thuật toán lock-free, hiện tượng **ABA** xảy ra khi state đổi A→B→A làm một CAS chỉ xét reference tưởng rằng không có thay đổi.

`AtomicStampedReference` và `AtomicMarkableReference` là API hiện hành để xử lý các trường hợp cần version/mark, nhưng **không có nghĩa mọi AtomicReference.updateAndGet đều phải dùng stamped reference**. Chỉ dùng những primitive đó khi thiết kế thuật toán có nguy cơ ABA cụ thể, và cần kiểm tra invariant bằng test.

Trong ví dụ immutable record `AccountState(balance, revision)`, revision được ghi trong state để minh họa dữ liệu; nó không tự thay thế mọi cơ chế chống ABA trong một thuật toán CAS đặc thù.

## 18. Lựa chọn giữa AtomicInteger, AtomicLong, AtomicReference và LongAdder

| Nhu cầu | Kiểu/API nên xem xét | Vì sao |
| --- | --- | --- |
| Một counter int với logic custom | `AtomicInteger.updateAndGet` / `accumulateAndGet` | Cập nhật scalar atomically |
| Một counter long với logic custom | `AtomicLong` | Dải số rộng hơn |
| Chỉ tăng/giảm số 1 hoặc delta | `incrementAndGet` / `getAndAdd` | Ý định đơn giản, không cần lambda |
| Một bất biến liên quan vài field | `AtomicReference<ImmutableState>` | Thay cả state bằng một CAS |
| Nhiều slot độc lập | `AtomicIntegerArray`/`AtomicReferenceArray` | Atomicity từng index |
| Một field volatile trong object hiện hữu | `Atomic*FieldUpdater` | Không cần wrapper Atomic riêng nhưng phải thỏa ràng buộc |
| Bộ đếm thống kê contention cao, không cần từng giá trị updated sau mỗi thao tác | `LongAdder` | Có thể giảm contention |
| Phép tích lũy giao hoán/kết hợp với identity | `LongAccumulator` | API tích lũy chuyên biệt |
| Nhiều giá trị có transaction nghiệp vụ chung | Lock/DB transaction/aggregate state | Một atomic scalar không đủ |

**Bảo đảm khác nhau:**

- `AtomicLong.addAndGet` trả **giá trị mới chính xác** của operation được thực hiện tại thời điểm atomic update.
- `LongAdder.add` trả `void`; `LongAdder.sum()` **không phải snapshot nguyên tử** khi các thread đang cập nhật. Nó phù hợp với thống kê cần throughput, chứ không thay hoàn toàn AtomicLong cho các thuật toán cần `compareAndSet`, giá trị trước/sau của chính update hoặc điều kiện gắn với update.
- `LongAccumulator.accumulate(x)` tích lũy với function và identity, kết quả có thể được đọc qua `get()`; các điều kiện đại số và snapshot là khác với AtomicLong functional update. Đừng dùng nó khi kết quả phụ thuộc một thứ tự operation cụ thể.
- `AtomicReference` tiện để bảo vệ consistency của state nhỏ/immutable, nhưng mỗi retry có thể tạo nhiều object hơn và tăng contention khi state lớn.

### 18.1. Ví dụ so kết quả khi không có writer đang chạy

Lưu `AtomicVsLongAdderDemo.java`:

```java
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;
import java.util.concurrent.atomic.LongAccumulator;

public class AtomicVsLongAdderDemo {
    public static void main(String[] args) {
        AtomicLong exact = new AtomicLong();
        LongAdder statistics = new LongAdder();
        LongAccumulator maximum = new LongAccumulator(
                Long::max, Long.MIN_VALUE);

        for (int i = 1; i <= 1_000; i++) {
            exact.accumulateAndGet(1L, Long::sum);
            statistics.add(1L);
        }

        maximum.accumulate(5L);
        maximum.accumulate(30L);
        maximum.accumulate(12L);

        System.out.println("atomic = " + exact.get());
        System.out.println("adder = " + statistics.sum());
        System.out.println("max = " + maximum.get());
        System.out.println("sameSum = " +
                (exact.get() == statistics.sum()));
    }
}
```

```bash
javac AtomicVsLongAdderDemo.java
java AtomicVsLongAdderDemo
```

```text
atomic = 1000
adder = 1000
max = 30
sameSum = true
```

Từ bài test không concurrent writer này, hai tổng bằng nhau. Không suy ra latency giống nhau hoặc `LongAdder.sum()` có atomic snapshot trong lúc thread khác vẫn đang tăng. Muốn so hiệu năng, phải benchmark trên workload thực với số thread, contention và môi trường CPU đại diện.

## 19. Cách chọn phương thức theo giá trị caller cần

Câu hỏi nhanh:

- “Tôi cần **giá trị trước khi thay đổi**?” → `getAndUpdate` hoặc `getAndAccumulate`.
- “Tôi cần **giá trị vừa được ghi**?” → `updateAndGet` hoặc `accumulateAndGet`.
- “Tôi có **chỉ một giá trị hiện tại** cần tính lại?” → unary update.
- “Tôi có một **đối số x mới** muốn đưa vào phép gộp?” → binary accumulate.
- “Tôi chỉ cộng một hằng số?” → `getAndAdd` / `addAndGet` thường rõ ràng hơn.
- “Tôi cần nhiều field luôn nhất quán?” → `AtomicReference<ImmutableState>` hoặc cơ chế đồng bộ phù hợp.
- “Tôi phải gọi network/API trong quá trình cập nhật?” → **không đặt vào callback CAS**; thiết kế workflow/idempotency ngoài lambda.
- “Tôi cần biết một request có được chấp nhận không?” → đừng tự suy từ giá trị sau update khi nhiều tình huống có thể tạo cùng giá trị; cần kết quả nghiệp vụ rõ ràng.

### 19.1. Bẫy với hàm không giao hoán

Một hàm như `(current,x) -> current - x` dùng được cho `accumulateAndGet`, bởi vì mỗi CAS thành công tạo ra một bước cập nhật tuần tự hóa trên một atomic variable. Tuy nhiên, nếu hai thread đồng thời gọi `accumulateAndGet(2, subtract)` và `accumulateAndGet(5, subtract)`, thứ tự CAS thành công không được chọn theo thứ tự lời gọi trong source code.

Với phép cộng/trừ đơn giản, có thể tình cờ kết quả cuối giống nhau, nhưng với phép nối chuỗi, ghép trạng thái, phép nhân–cộng phụ thuộc thứ tự hoặc các quy tắc phi giao hoán khác, kết quả có thể khác.

**Không lấy behavior này để suy ngược rằng reducer của `ConcurrentHashMap.reduce` có thể không associative/commutative.** Các bulk parallel reductions là một nhóm API khác, có yêu cầu đại số riêng do có thể chia và kết hợp các nhánh theo cây.

## 20. Test chiến lược: kiểm chứng đúng mà không dựa vào timing

Bộ kiểm thử tốt cho atomic functional updates nên có:

1. **Old/new return**: với cùng hàm, kiểm tra return từ `getAndUpdate` là state cũ và `updateAndGet` là state mới.
2. **Thứ tự đối số**: accumulator phải tính từ `(current,x)`, không phải `(x,current)`.
3. **Cạnh biên**: zero, số âm, giới hạn max/min, overflow.
4. **Hàm từ chối**: lambda ném exception thì không ghi một giá trị mới từ lần thử đó.
5. **Contention**: nhiều thread cùng cập nhật; đợi tất cả hoàn tất trước khi assert kết quả.
6. **CAS retry**: orchestration với latch; test chứng minh callback có thể chạy lại, không gọi I/O.
7. **Reference immutable state**: mọi field trong một state luôn giữ invariant.
8. **Atomic array**: đúng index, lỗi out-of-bounds, cập nhật từng slot.
9. **Field updater**: field volatile, access level hợp lệ và fail khi field không đúng contract.
10. **Value null**: `AtomicReference` có thể giữ null, lambda phải xử lý nếu domain cho phép.
11. **LongAdder**: sau khi writers dừng, tổng đúng; không assert snapshot nguyên tử khi writers đang tăng.
12. **No external side effects**: callback không gửi email, tạo order hay cập nhật hệ thống ngoài.
13. **No exact lambda count**: trừ một test điều khiển retry có chủ đích, không giả định callback đúng một lần.
14. **Memory and performance**: đo contention, allocation và throughput riêng; correctness test không phải benchmark.

**Đừng dùng `Thread.sleep` để cố ép contention** rồi phụ thuộc vào thứ tự thread. Ví dụ `AtomicRetryUnderContentionDemo` dùng `CountDownLatch` tạo đúng ranh giới CAS; ví dụ `AtomicConcurrentCounterDemo` đợi tất cả task qua `CompletableFuture.allOf` trước khi kiểm tra.

### 20.1. Bài tập thực hành

**Bài 1 — Return values.** Khởi tạo `AtomicInteger(7)`, gọi `getAndUpdate(v->v*2)` rồi `accumulateAndGet(5,Integer::sum)`. In giá trị cũ và giá trị mới.

**Bài 2 — Hạn mức.** Có một quota tối đa 10. Viết `updateAndGet` để tăng 5 nhưng không vượt 10; giải thích cách tránh overflow khi current gần `Integer.MAX_VALUE`.

**Bài 3 — Functional accumulator.** Giải thích vì sao `accumulateAndGet(3,(current,x)->current*10+x)` trên giá trị 10 cho ra 103. Nếu đảo đối số thì kết quả nào sai?

**Bài 4 — Retry hazard.** Nếu cập nhật được gọi 1 lần nhưng lambda bị tính 2 lần do CAS thất bại, điều gì xảy ra với `sendEmail()` nằm trong lambda? Nêu cách tách side effect.

**Bài 5 — Immutable state.** Có record `State(int available, int sold)`. Dùng `AtomicReference` để chuyển 1 đơn vị từ available sang sold nếu có hàng, giữ invariant tổng không đổi.

**Bài 6 — Atomic arrays.** Dùng `AtomicIntegerArray` có 3 slot; tăng slot 1 bằng 5 rồi cộng thêm 7 với `accumulateAndGet`. Chứng minh slot 0 và slot 2 không thay đổi.

**Bài 7 — LongAdder.** Với 10 thread cập nhật counter nhiều lần, khi nào nên dùng `LongAdder` hơn `AtomicLong`? Nếu thuật toán cần trả số mới sau mỗi update thì thay thế có đầy đủ nghĩa không?

### 20.2. Lời giải Java cho bài 1

Lưu `AtomicPractice.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicPractice {
    public static void main(String[] args) {
        AtomicInteger value = new AtomicInteger(7);

        int before = value.getAndUpdate(
                current -> current * 2);

        int after = value.accumulateAndGet(
                5, Integer::sum);

        AtomicReference<String> status =
                new AtomicReference<>("PENDING");

        String updatedStatus = status.updateAndGet(
                current -> "READY");

        System.out.println("before = " + before);
        System.out.println("after = " + after);
        System.out.println("final = " + value.get());
        System.out.println("status = " + updatedStatus);
    }
}
```

```bash
javac AtomicPractice.java
java AtomicPractice
```

```text
before = 7
after = 19
final = 19
status = READY
```

Lời giải bài 2 xem `AtomicBoundedCounterDemo` kèm phần overflow. Bài 3 xem `AtomicAccumulateOrderDemo`. Bài 4 xem `AtomicRetryUnderContentionDemo`. Bài 5 xem `AtomicInventoryInvariantDemo`. Bài 6 xem `AtomicArrayVariantsDemo`. Bài 7 xem `AtomicVsLongAdderDemo`.

## 21. Lỗi phổ biến và cách phòng tránh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nhầm `getAndUpdate` trả giá trị mới | Caller nhận số cũ rồi tính sai | Đọc rõ tên: `getAnd...` trả old |
| Nhầm `updateAndGet` trả giá trị cũ | Sai logic tính chênh lệch | Kiểm tra return semantics |
| Đảo `(current,x)` thành `(x,current)` | Sai phép trừ, ghép chuỗi, cập nhật có thứ tự | Current luôn là đối số thứ nhất |
| Đưa gửi email/I/O vào lambda | Có thể chạy nhiều lần do CAS retry | Hàm side-effect-free; I/O ngoài CAS |
| Mutate object cũ trong AtomicReference | State có thể đã bị thay đổi trước CAS thành công | Dựng immutable state mới |
| Nghĩ CAS trên reference bảo vệ mọi mutable field phía sau | Race trên object mutable | Dùng deep immutable hoặc synchronization |
| Dùng `volatile int++` thay AtomicInteger | Mất increment | `incrementAndGet`/`updateAndGet` |
| Nghĩ `updateAndGet` bảo vệ hai AtomicInteger độc lập | Invariant nhiều biến vẫn bị chen | Một immutable aggregate hoặc lock/transaction |
| Dùng `Math.min(max, current+delta)` khi có nguy cơ overflow | Có thể âm hóa trước clamp | Kiểm tra overflow / `Math.addExact` |
| Nuốt exception trong operator và trả state bất kỳ | Che lỗi nghiệp vụ | Báo lỗi hoặc có contract fallback minh bạch |
| Giả định lambda đúng một lần | Duplicate side effect hoặc metrics sai | Không làm side effect trong updater |
| Dùng `AtomicReference<List>` rồi gọi `list.add` | Mutation ngoài CAS, race | Copy local rồi publish immutable list |
| Coi `getAndUpdate` là transaction database | Chỉ atomic trong JVM | Transaction ở storage/DB |
| Dùng CAS nhưng cần biết request bán hàng có được chấp nhận | Giá trị state mới không luôn đủ để suy ra | Thiết kế result riêng và CAS loop hợp lệ |
| Coi AtomicInteger increment và LongAdder.add có mọi semantics giống nhau | LongAdder không trả updated value, sum không atomic snapshot | Chọn theo contract |
| Đưa custom function không giao hoán vào bulk parallel reduction | Kết quả tùy cách nhóm | Phân biệt reduction và atomic accumulator |
| Benchmark một lần bằng `System.nanoTime` và kết luận speedup | Dễ bị JIT, scheduling, tải máy chi phối | Warmup, JMH, đo workloads đại diện |
| Quên xử lý null của AtomicReference | NPE khi callback truy cập null | Chính sách init rõ ràng |
| Dùng FieldUpdater cho field không volatile | Khởi tạo updater lỗi | Tuân thủ kiểu/volatile/access contract |

## 22. Checklist code review trước khi đưa vào production

- Giá trị tôi cần trả là **trước** hay **sau** cập nhật?
- Đây là phép unary update hay accumulate với đối số `x`?
- Tôi có đang dùng đúng thứ tự `(current,x)` không?
- Có biến/mutable object được capture vào lambda trong khi thread khác có thể sửa không?
- Lambda có hoàn toàn side-effect-free không? Có I/O, random không kiểm soát, sinh số thứ tự, log đếm sự kiện hoặc mutation shared state không?
- Nếu CAS retry 10 lần, việc tính lambda 10 lần có vẫn an toàn không?
- Tôi có cần trả **trạng thái chấp nhận/từ chối** của chính request thay vì chỉ state mới không?
- Đã tránh read-check-write rời rạc cho invariant đang bị tranh chấp chưa?
- Có overflow hoặc giá trị ngoài range có thể lọt qua operator không?
- Với AtomicReference, state mới có immutable thực sự hay chỉ shallow immutable?
- Nếu nhiều field liên quan, chúng có nằm trong một state được publish atomically không?
- Với array, tôi có hiểu atomicity là **mỗi index** chứ không phải cả mảng không?
- Với field updater, target field có đúng kiểu `volatile` và access level không?
- Khi có exception trong updater, code có báo lỗi thay vì giả thành công không?
- Đã test contention bằng latch/barrier và assert sau khi writers hoàn tất chưa?
- Nếu dùng `LongAdder` hoặc `LongAccumulator`, có hiểu rằng snapshot/ordering và return semantics khác AtomicLong không?
- Nếu có database/network, đã xác định rõ ranh giới transaction/idempotency chưa?
- Đã chọn API Java hiện hành và không dùng kiến thức legacy không?

## 23. Tài liệu Oracle Java hiện hành

- `AtomicInteger` — `getAndUpdate`, `updateAndGet`, `getAndAccumulate`, `accumulateAndGet`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- `AtomicLong` — các biến thể long: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html
- `AtomicReference` — các biến thể reference: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html
- `AtomicIntegerArray` — cập nhật theo index: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicIntegerArray.html
- `AtomicReferenceArray` — reference array: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicReferenceArray.html
- `AtomicIntegerFieldUpdater` — cập nhật field volatile: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicIntegerFieldUpdater.html
- `AtomicReferenceFieldUpdater` — updater reference field: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicReferenceFieldUpdater.html
- `LongAdder` — counter khi có contention: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- `LongAccumulator` — accumulator có identity: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAccumulator.html
- `VarHandle` — memory effects và compareAndSet: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/VarHandle.html

**Tổng kết:** `getAndUpdate` và `getAndAccumulate` trả **state cũ**, còn `updateAndGet` và `accumulateAndGet` trả **state mới**. `accumulatorFunction(current,x)` nhận **current trước, x sau**. Các cập nhật được thực hiện atomically đối với một biến/slot/field được quản lý, nhưng **lambda có thể được tính lại khi tranh chấp**, vì vậy phải side-effect-free và không mutate object chia sẻ. Khi bài toán có nhiều field, cần cùng một immutable state hoặc cơ chế transaction phù hợp. Chọn AtomicInteger/AtomicLong/AtomicReference hay LongAdder theo **bảo đảm nghiệp vụ thật sự cần**, không chỉ theo cái tên “atomic”.