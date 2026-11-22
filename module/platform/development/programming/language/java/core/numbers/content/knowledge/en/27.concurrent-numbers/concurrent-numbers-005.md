# Compare-and-set và việc hàm cập nhật có thể bị gọi lại

## 1. Vấn đề khi nhiều luồng cùng cập nhật một con số

Giả sử một chương trình Java lưu bộ đếm lượt truy cập, số ghế còn lại, tổng số đơn hàng hoặc trạng thái số của một thiết bị. Nếu nhiều luồng cùng đọc, tính toán và ghi biến, đoạn mã sau **không bảo đảm tăng chính xác**:

```java
// Counter là lớp chứa một trường mutable:
class Counter {
    int value = 0;

    void increment() {
        value = value + 1;
    }
}
```

Phép `value = value + 1` là chuỗi thao tác: đọc giá trị, tính `+1`, ghi kết quả. Hai luồng có thể cùng đọc 10 rồi cùng ghi 11, khiến một lần tăng bị mất (*lost update*). Thêm `volatile` giúp bảo đảm tính hiển thị nhất định của truy cập biến, nhưng **không biến cả phép đọc–sửa–ghi thành một thao tác nguyên tử**.

Các lớp trong `java.util.concurrent.atomic`, đặc biệt `AtomicInteger` và `AtomicLong`, hỗ trợ các thao tác nguyên tử trên một giá trị số. Cơ chế quan trọng để hiểu chúng là **compare-and-set (CAS)** và **vòng lặp thử lại** khi giá trị đang được luồng khác thay đổi.

Mục tiêu chính của bài: hiểu chính xác điều kiện CAS thành công, vì sao hàm đưa vào `updateAndGet()` hoặc `getAndUpdate()` có thể được gọi **nhiều lần cho một lời gọi API**, cách thiết kế hàm cập nhật an toàn, và lúc nào nên chọn API số nguyên tử khác.

## 2. Compare-and-set (CAS) là gì?

Trong `AtomicInteger`:

```java
boolean compareAndSet(int expectedValue, int newValue);
```

Ý nghĩa: tại thời điểm thao tác nguyên tử được thực hiện, nếu giá trị hiện tại **bằng** `expectedValue`, đặt nó thành `newValue` và trả `true`; nếu không, giữ nguyên giá trị và trả `false`.

```java
AtomicInteger seats = new AtomicInteger(2);

boolean first = seats.compareAndSet(2, 1); // true: 2 -> 1
boolean stale = seats.compareAndSet(2, 0); // false: current là 1
int remaining = seats.get();               // 1
```

Trong một lần CAS thành công, kiểm tra điều kiện và ghi giá trị được thực hiện cùng một bước nguyên tử đối với biến atomic đó. Nó bảo vệ thao tác **trên chính biến ấy** trước sự tranh chấp giữa các luồng cùng thao tác đúng thông qua atomic.

Có thể hình dung:

```text
Giá trị hiện tại = 10

Luồng A đọc 10, dự tính ghi 15.
Luồng B đọc 10, CAS(10, 20) thành công -> giá trị = 20.
Luồng A CAS(10, 15) thất bại vì giá trị hiện tại đã là 20.
Luồng A phải đọc lại 20 và tính phương án mới, ví dụ 25.
```

CAS không tự chọn cách tính lại. Vòng lặp của ứng dụng hoặc các API như `updateAndGet()` thực hiện công việc đó.

## 3. Vòng lặp CAS: vì sao hàm cập nhật được tính lại?

Hãy xem một mô hình minh họa của `updateAndGet()`, **không phải bản chép mã nguồn nội bộ JDK**:

```java
static int updateWithCas(
        AtomicInteger value,
        java.util.function.IntUnaryOperator updater) {
    for (;;) {
        int observed = value.get();
        int candidate = updater.applyAsInt(observed);
        if (value.compareAndSet(observed, candidate)) {
            return candidate;
        }
        // Có tranh chấp: đọc lại giá trị, gọi updater lần nữa.
    }
}
```

Phương thức trên là mã minh họa cần đặt trong một lớp Java, với `import java.util.concurrent.atomic.AtomicInteger;`. Khi CAS thất bại vì có một cập nhật cạnh tranh, vòng lặp tính lại `candidate` từ giá trị mới. Do đó:

- **Một lần gọi `updateAndGet(f)` có thể gọi `f` nhiều lần**; số lần tùy diễn biến tranh chấp.
- **Chỉ phép CAS thành công mới chốt cập nhật** của lời gọi đó. Các kết quả tính thử trước đó có thể bị loại bỏ.
- Giá trị mà `f` nhận ở mỗi lần chạy có thể khác nhau, vì trạng thái dùng để tính mới đã thay đổi.
- Không được suy rằng “hàm trả kết quả một lần” đồng nghĩa “callback đã chạy một lần”.

Đây là hợp đồng quan trọng của các phương thức cập nhật bằng hàm trên atomic: tài liệu Java khuyến nghị hàm cập nhật **không có tác dụng phụ** (*side-effect-free*) vì nó có thể bị áp dụng lại khi thao tác cập nhật thất bại do tranh chấp.

## 4. Ví dụ Java 17 có thể tái hiện retry một cách xác định

Trong chương trình sau, hai `CountDownLatch` dùng **chỉ để kiểm chứng**: buộc luồng cạnh tranh cập nhật số từ 10 thành 20 **sau khi** callback lượt đầu tiên đã đọc 10 nhưng **trước khi** CAS của lượt đó diễn ra.

Tạo tệp **`CasRetryDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class CasRetryDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger seats = new AtomicInteger(2);
        System.out.println("firstCAS=" + seats.compareAndSet(2, 1)
                + ", seats=" + seats.get());
        System.out.println("staleCAS=" + seats.compareAndSet(2, 0)
                + ", seats=" + seats.get());

        AtomicInteger value = new AtomicInteger(10);
        AtomicInteger calls = new AtomicInteger();
        AtomicInteger firstSeen = new AtomicInteger(-1);
        AtomicInteger secondSeen = new AtomicInteger(-1);
        CountDownLatch firstCall = new CountDownLatch(1);
        CountDownLatch competitorDone = new CountDownLatch(1);

        Thread competitor = new Thread(() -> {
            try {
                firstCall.await();
                if (!value.compareAndSet(10, 20)) {
                    throw new AssertionError("Expected competing CAS to succeed");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            } finally {
                competitorDone.countDown();
            }
        });
        competitor.start();

        int result = value.updateAndGet(old -> {
            int pass = calls.incrementAndGet();
            if (pass == 1) {
                firstSeen.set(old);
                firstCall.countDown();
                try {
                    competitorDone.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(e);
                }
            } else {
                secondSeen.set(old);
            }
            return old + 5;
        });
        competitor.join();

        System.out.println("updateAndGet=" + result
                + ", calls=" + calls.get()
                + ", seen=" + firstSeen.get() + "," + secondSeen.get());
        int previous = value.getAndUpdate(x -> x + 5);
        System.out.println("getAndUpdate old=" + previous + ", now=" + value.get());
        int sum = value.accumulateAndGet(12, Integer::sum);
        System.out.println("accumulateAndGet=" + sum);

        AtomicLong longValue = new AtomicLong(4_000_000_000L);
        System.out.println("longAfter=" + longValue.updateAndGet(x -> x + 1));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac CasRetryDemo.java
java CasRetryDemo
```

Kết quả **đã kiểm chứng** khi biên dịch với `javac --release 17`:

```text
firstCAS=true, seats=1
staleCAS=false, seats=1
updateAndGet=25, calls=2, seen=10,20
getAndUpdate old=25, now=30
accumulateAndGet=42
longAfter=4000000001
```

**Giải thích vì sao callback chạy hai lần:**

1. `value` bắt đầu là 10. Lượt áp dụng hàm đầu tiên nhận `old = 10`, lưu dấu vết vào `firstSeen` và ra hiệu cho luồng cạnh tranh.
2. Callback chờ `competitorDone`. Luồng cạnh tranh gọi `value.compareAndSet(10, 20)` thành công, vì lần cập nhật chính chưa chốt.
3. Callback đầu tiên tiếp tục, đề xuất 15. CAS áp dụng đề xuất đó thất bại: số hiện tại đã là 20, không còn là 10.
4. API cập nhật thử lại; callback nhận `old = 20`, tính 25. Lần CAS tiếp theo thành công vì luồng cạnh tranh đã hoàn thành.
5. `updateAndGet()` trả 25. Bộ đếm chẩn đoán `calls = 2` chứng minh **một lời gọi API có hai lần đánh giá callback**.

Trong ví dụ, `calls.incrementAndGet()`, `firstSeen.set()` và hai latch là **tác dụng phụ chủ đích của mã thử nghiệm** để quan sát retry. **Không sao chép mô hình callback có tác dụng phụ này vào xử lý nghiệp vụ thực tế.** Các callback sản xuất bên dưới chỉ tính toán từ tham số nhận vào.

Lưu ý: đây là ví dụ có điều phối để làm lỗi CAS xuất hiện chắc chắn. Khi tranh chấp ngẫu nhiên trong hệ thống thật, callback có thể chạy một lần, hai lần hoặc nhiều lần; không giả định một số lần cụ thể.

## 5. Hàm cập nhật phải an toàn khi được gọi lại

Một hàm cập nhật **thuần** (*pure function*) chỉ tính kết quả từ dữ liệu đầu vào và các hằng số/đầu vào bất biến liên quan, không tạo tác dụng phụ có thể quan sát từ bên ngoài.

### Cách đúng: tính lại giá trị số

```java
AtomicInteger balance = new AtomicInteger(100);
int latest = balance.updateAndGet(current -> current + 20);
// balance = 120 nếu không có cập nhật cạnh tranh khác
```

Hàm `current -> current + 20` có thể được gọi lại với giá trị mới sau khi CAS thất bại; giá trị cuối được chốt sau một CAS thành công.

**Không yêu cầu hàm phải bất biến dưới phép áp dụng hai lần** theo nghĩa toán học `f(f(x)) = f(x)`. Hàm `f(x) = x + 20` không có tính chất đó nhưng vẫn phù hợp. Điều cần thiết là việc **tính thử nhiều lần không gây thêm tác dụng phụ**, và hàm tính đúng kết quả từ giá trị *hiện tại được truyền vào*.

### Cách sai: gửi email, ghi log nghiệp vụ, gọi API bên ngoài

```java
// PHẢN VÍ DỤ — không thực hiện hành động ngoài trong callback.
balance.updateAndGet(current -> {
    sendNotification("Đã cộng 20"); // Có thể chạy nhiều lần.
    return current + 20;
});
```

`sendNotification(...)` là ký hiệu minh họa hành vi bên ngoài, không phải phương thức có sẵn trong Java. Nếu CAS thất bại, thông báo có thể được gửi dù đề xuất `current + 20` **chưa từng được ghi**, hoặc gửi nhiều lần.

Tương tự, tránh gọi dịch vụ mạng, ghi file/database, phát thông điệp, tạo giao dịch thanh toán, tăng một bộ đếm nghiệp vụ khác, hoặc tạo ID mới bên trong callback mà bạn chỉ muốn thực hiện một lần.

Nếu cần hành động phụ sau khi cập nhật:

```java
int newValue = balance.updateAndGet(current -> current + 20);
// Sau khi lời gọi thành công, phần code này chỉ chạy một lần theo luồng này.
recordSuccessfulUpdate(newValue);
```

`recordSuccessfulUpdate(...)` cũng là ký hiệu minh họa, không phải phương thức Java có sẵn. Đây là bước **sau** khi cập nhật chốt thành công; tuy nhiên cập nhật atomic và hành động bên ngoài **không phải một giao dịch duy nhất**. Nếu ứng dụng có thể bị dừng giữa hai bước, hoặc cần bảo đảm gửi sự kiện đúng một lần khi có retry toàn bộ tác vụ, phải thiết kế thêm giao dịch, outbox hoặc khóa idempotency phù hợp.

### Các lỗi tinh vi khác

- **Đọc biến thay đổi từ bên ngoài:** `updateAndGet(x -> x + currentBonus.get())` có thể tính phần cộng khác nhau giữa các lần thử nếu `currentBonus` đổi. Nếu nghiệp vụ yêu cầu giữ nguyên khoản cộng cho *một* hành động, chụp giá trị thưởng trước rồi dùng hằng số đó trong callback.
- **Thời gian và random:** `Instant.now()`, số ngẫu nhiên hoặc truy vấn trạng thái ngoài trong callback có thể cho kết quả khác nhau khi retry. Quyết định đầu vào bất biến trước khi cập nhật.
- **Ngoại lệ:** nếu callback ném ngoại lệ, lời gọi cập nhật đó không chốt giá trị đề xuất; các tác dụng phụ đã xảy ra ở những lượt callback trước **không được hoàn tác**.
- **Đọc hai atomic riêng lẻ:** callback chỉ bảo đảm CAS nguyên tử cho **một biến atomic đích**. Nó không chốt đồng thời một bản ghi nghiệp vụ trải qua nhiều biến khác.

## 6. Các API liên quan và giá trị trả về

| API | Cập nhật giá trị | Kết quả trả về | Lưu ý |
| --- | --- | --- | --- |
| `compareAndSet(expected, next)` | Nếu hiện tại bằng expected thì ghi next | `boolean` | `false` khi điều kiện không còn đúng |
| `getAndSet(next)` | Ghi next nguyên tử | **Giá trị cũ** | Không cần callback |
| `getAndIncrement()` | Cộng 1 | **Giá trị cũ** | Phù hợp bộ đếm đơn giản |
| `incrementAndGet()` | Cộng 1 | **Giá trị mới** | Không cần viết lambda |
| `getAndAdd(delta)` | Cộng delta | **Giá trị cũ** | Không cần viết callback |
| `addAndGet(delta)` | Cộng delta | **Giá trị mới** | Không cần viết callback |
| `getAndUpdate(f)` | Tính số mới bằng f | **Giá trị cũ của lần cập nhật thành công** | f có thể gọi lại |
| `updateAndGet(f)` | Tính số mới bằng f | **Giá trị mới đã chốt** | f có thể gọi lại |
| `getAndAccumulate(x, f)` | Tính bằng f(current, x) | **Giá trị cũ** | f có thể gọi lại |
| `accumulateAndGet(x, f)` | Tính bằng f(current, x) | **Giá trị mới** | f có thể gọi lại |

`AtomicInteger` sử dụng `IntUnaryOperator` cho `getAndUpdate`/`updateAndGet` và `IntBinaryOperator` cho `getAndAccumulate`/`accumulateAndGet`. `AtomicLong` có API tương tự với `LongUnaryOperator` và `LongBinaryOperator`.

Trong chương trình kiểm chứng, sau khi `value = 25`:

```java
int old = value.getAndUpdate(x -> x + 5);      // old = 25; value = 30
int now = value.accumulateAndGet(12, Integer::sum); // now = 42; value = 42
```

Với phép cộng đơn giản, thường ưu tiên `addAndGet(5)` hay `getAndAdd(5)`. Những phương thức chuyên biệt này truyền ý định rõ ràng và tránh việc tạo callback nghiệp vụ không cần thiết. Khi công thức phụ thuộc trạng thái hiện tại, như giới hạn trên/dưới, các phương thức cập nhật bằng hàm là thích hợp.

### Ví dụ giới hạn giá trị

```java
AtomicInteger capacity = new AtomicInteger(7);
int capped = capacity.updateAndGet(
        current -> Math.min(10, current + 4));
// capped = 10
```

Callback `Math.min(10, current + 4)` không có tác dụng phụ; nếu luồng khác thay đổi `capacity`, lời gọi có thể tính lại dựa trên giá trị mới.

**Chú ý overflow:** `current + 4` với `int` vẫn có thể tràn nếu gần `Integer.MAX_VALUE`. Nếu muốn báo lỗi thay vì tràn, dùng `Math.addExact(current, 4)` và quy định rõ cách xử lý ngoại lệ. `AtomicInteger` không tự ngăn tràn số học.

## 7. Tự viết vòng CAS khi cần điều kiện cụ thể

Một tình huống là chỉ cho phép giữ chỗ khi số ghế còn lại lớn hơn 0:

```java
static boolean tryReserve(AtomicInteger remaining) {
    for (;;) {
        int old = remaining.get();
        if (old <= 0) {
            return false;
        }
        if (remaining.compareAndSet(old, old - 1)) {
            return true;
        }
        // Trạng thái đổi: đọc lại và kiểm tra điều kiện lần nữa.
    }
}
```

Đây là **đoạn mã phương thức**, đặt bên trong lớp Java và import `AtomicInteger`. Khi số ghế bằng 0, trả false; khi còn ghế, thử trừ đi 1 bằng CAS. Nếu thất bại do tranh chấp, vòng lặp **kiểm tra lại cả điều kiện** trước khi thử tiếp.

Nếu viết `if (remaining.get() > 0) remaining.decrementAndGet();` thì việc kiểm tra và giảm số ghế không nguyên tử như một thao tác kết hợp; hai luồng có thể cùng thấy “còn 1 ghế” và đều giảm xuống, gây âm số ghế. Vòng CAS ở trên gắn điều kiện `old > 0` với phiên bản số mà CAS đang kiểm tra.

Một lời gọi `tryReserve` hoàn thành thành công tương ứng một lần giảm nguyên tử. Nhưng toàn bộ tác vụ nghiệp vụ (ví dụ ghi database, thanh toán, tạo vé) cần cơ chế giao dịch riêng nếu phải đảm bảo nhất quán qua nhiều tài nguyên.

## 8. AtomicLong và giá trị lớn

Khi đếm số lớn vượt phạm vi `int`, dùng `AtomicLong`:

```java
AtomicLong processedBytes = new AtomicLong(4_000_000_000L);
long newTotal = processedBytes.updateAndGet(current -> current + 1);
// newTotal = 4_000_000_001L
```

Tính nguyên tử và yêu cầu callback không có tác dụng phụ vẫn như `AtomicInteger`. Chọn kiểu `long` không loại bỏ nguy cơ overflow `long`; Java không tự làm phép cộng bão hòa. Nếu có thể vượt `Long.MAX_VALUE`, cần lựa chọn kiểu/thuật toán và kiểm tra giới hạn thích hợp.

Nếu bạn cần số thập phân chính xác như `BigDecimal` thay vì `int`/`long`, có thể dùng `AtomicReference<BigDecimal>` vì `BigDecimal` bất biến:

```java
// Cần import java.math.BigDecimal và
// java.util.concurrent.atomic.AtomicReference.
AtomicReference<BigDecimal> total =
        new AtomicReference<>(new BigDecimal("10.00"));

total.updateAndGet(old -> old.add(new BigDecimal("2.50")));
// total.get() = 12.50
```

Callback `old -> old.add(...)` tạo giá trị `BigDecimal` mới mà không sửa số cũ; cách làm này phù hợp với việc tính lại khi CAS thất bại. Trong `AtomicReference`, `compareAndSet` so khớp tham chiếu mong đợi, **không gọi `BigDecimal.equals()` hay `compareTo()`**. Trường hợp nhiều trường dữ liệu cần chốt cùng lúc, cân nhắc giữ một đối tượng trạng thái bất biến trong một `AtomicReference` hoặc dùng đồng bộ/giao dịch thích hợp.

## 9. Ranh giới của CAS: những điều không được suy diễn

### 9.1. CAS không đảm bảo callback chỉ chạy một lần

Lỗi hay gặp nhất là đặt hành động có tác dụng phụ vào callback và cho rằng API “chỉ cập nhật một lần” nghĩa là callback “chỉ chạy một lần”. **Kết quả tính thử bị CAS từ chối nhưng tác dụng phụ bên ngoài vẫn có thể xảy ra.**

Một callback phù hợp có dạng `old -> old + increment`, trong đó `increment` đã được xác định ổn định trước khi gọi; không thao tác cơ sở dữ liệu, gửi thông báo hay sinh ID trong đó.

### 9.2. Một atomic không biến nhiều bước nghiệp vụ thành giao dịch

`AtomicInteger` chỉ chốt một giá trị của một đối tượng atomic. Khi thay đổi hai biến độc lập, hoặc cần đồng bộ con số với dữ liệu ở file/database, các cập nhật riêng lẻ không trở thành một thao tác nguyên tử chung. Có thể dùng khóa, giao dịch hoặc một đối tượng trạng thái bất biến duy nhất tùy cấu trúc bài toán.

### 9.3. Liveness và contention

CAS là kỹ thuật thường dùng để triển khai cấu trúc dữ liệu và phép toán không dùng khóa tường minh. Dưới tranh chấp cao, một luồng có thể thử lại nhiều lần và tốn CPU; một lần gọi riêng không có bảo đảm chạy thành công sau đúng một số lần cố định. Khi công thức đắt đỏ, tính đi tính lại cũng có chi phí đáng kể.

Đối với một bộ đếm cộng dồn được cập nhật rất nhiều luồng và không đòi hỏi điều kiện CAS riêng cho mỗi lần cập nhật, `LongAdder` có thể là lựa chọn hữu ích để cải thiện thông lượng. Tuy nhiên, `LongAdder.sum()` không phải snapshot nguyên tử của tất cả cập nhật đang đồng thời diễn ra; nó không thay thế `AtomicLong` khi cần đọc một trạng thái chính xác tại một thời điểm để ra quyết định.

### 9.4. Quan hệ với volatile và memory visibility

`AtomicInteger.get()` và `set()` có ngữ nghĩa truy cập bộ nhớ kiểu volatile; `compareAndSet()` cung cấp thao tác nguyên tử và các hiệu ứng bộ nhớ tương ứng theo Java API. Các thao tác này giúp các luồng nhìn thấy việc cập nhật giá trị atomic theo mô hình bộ nhớ Java.

Điều đó **không làm cho mọi biến thông thường** hoặc mọi quan hệ giữa các đối tượng trở nên thread-safe. Một tham chiếu atomic tới đối tượng mutable cũng không tự bảo vệ các trường mutable bên trong đối tượng ấy.

### 9.5. ABA: trạng thái có thể đổi rồi quay lại

Nếu giá trị ban đầu là A, luồng khác thay thành B rồi lại A trước lúc CAS, thì `compareAndSet(A, next)` có thể thành công vì CAS kiểm tra **giá trị hiện tại**, chứ không biết lịch sử thay đổi. Đây là *ABA problem*, cần quan tâm khi nghiệp vụ phụ thuộc việc “chưa có thay đổi nào xảy ra” chứ không chỉ so sánh số hiện tại. Với bài toán phù hợp, có thể quản lý cả phiên bản/trạng thái hoặc dùng `AtomicStampedReference`; đừng mặc định CAS cho biết đã không có hoạt động giữa hai lần đọc.

## 10. Lỗi thường gặp và cách tránh

1. **Lầm tưởng `volatile int` đủ cho `x++`.** Nó không làm phép đọc–sửa–ghi thành một thao tác nguyên tử. Dùng `AtomicInteger.incrementAndGet()` hoặc đồng bộ phù hợp.
2. **Viết callback có tác dụng phụ.** Nếu `updateAndGet()` retry, lệnh gửi email hoặc ghi database có thể chạy nhiều lần. Đưa tác dụng phụ ra ngoài và thiết kế ranh giới giao dịch riêng.
3. **Dùng dữ liệu đang thay đổi ngoài callback.** Cùng một lời gọi API có thể tính kết quả khác nhau không chỉ vì atomic đổi mà còn vì biến ngoài đổi. Chụp dữ liệu đầu vào cần nhất quán trước khi cập nhật.
4. **Hiểu nhầm giá trị trả về.** `getAndUpdate` trả số cũ, `updateAndGet` trả số mới; tương tự với cặp accumulate.
5. **Tự viết CAS loop nhưng không đọc và kiểm tra lại điều kiện.** Khi CAS thất bại, phải xem trạng thái mới có còn cho phép thao tác không.
6. **Dùng callback cho phép cộng đơn giản không cần thiết.** `getAndAdd` hoặc `addAndGet` diễn đạt rõ hơn và tránh callback.
7. **Cho rằng AtomicInteger/AtomicLong không bao giờ tràn.** Tính nguyên tử khác hoàn toàn với kiểm tra phạm vi số học; dùng `Math.addExact` hoặc giới hạn nghiệp vụ khi cần.
8. **Thử nghiệm đa luồng bằng `sleep()` rồi tin kết quả luôn tái hiện.** Lịch luồng không xác định; ví dụ kiểm chứng ở trên dùng `CountDownLatch` để tạo thứ tự rõ ràng.
9. **Nhầm callback chạy lại với cập nhật được chốt nhiều lần.** Trong một lời gọi hoàn tất thành công, kết quả của một lần cập nhật được CAS chấp nhận; việc tính thử trước đó có thể bị bỏ.
10. **Dùng một atomic để suy ra nhất quán toàn hệ thống.** Khi có nhiều biến hoặc tài nguyên khác, cần thêm giao thức đồng bộ hay giao dịch.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Vì sao `updateAndGet(x -> x + 1)` có thể đánh giá lambda nhiều lần nhưng một lời gọi thành công chỉ chốt một lần cộng?  
**Đáp án:** mỗi lần thử tính một ứng viên từ trạng thái quan sát; nếu CAS thất bại, ứng viên bị bỏ và lambda được gọi lại với trạng thái mới. Chỉ lần CAS thành công mới ghi ứng viên.

**Câu 2.** Có nên viết `atomic.updateAndGet(x -> { sendEmail(); return x + 1; })` không?  
**Đáp án:** không. `sendEmail()` minh họa tác dụng phụ có thể lặp lại khi retry; cần tách khỏi callback, và thiết kế xử lý nghiệp vụ nếu yêu cầu chính xác một lần.

**Câu 3.** Khi `AtomicInteger` đang là 8, `compareAndSet(7, 9)` trả gì?  
**Đáp án:** `false`, giá trị vẫn 8 vì giá trị mong đợi là 7.

**Câu 4.** Sau `int old = value.getAndUpdate(x -> x * 2)` với `value = 4` (không có cạnh tranh), `old` và `value.get()` là gì?  
**Đáp án:** `old = 4`, `value.get() = 8`.

**Câu 5.** Một lambda `x -> x + 3` có bắt buộc thỏa `f(f(x)) == f(x)` để an toàn retry không?  
**Đáp án:** không. Hàm cộng 3 không idempotent theo nghĩa toán học; điều cần là tính thử lại không có tác dụng phụ và kết quả mới đúng từ trạng thái được truyền vào.

**Câu 6.** Nếu có ba biến `AtomicInteger` riêng cho `available`, `reserved` và `sold`, một lời gọi CAS trên `available` có bảo đảm ba biến đổi đồng thời không?  
**Đáp án:** không. CAS trên một atomic không tạo giao dịch xuyên nhiều atomic hoặc các tài nguyên khác.

## 12. Kết luận

- **CAS** kiểm tra giá trị đang có và chỉ ghi giá trị mới nếu trạng thái vẫn khớp với giá trị mong đợi.
- **`updateAndGet`, `getAndUpdate` và các biến thể accumulate có thể tính callback nhiều lần** do tranh chấp và retry.
- **Hàm cập nhật cần không có tác dụng phụ**; tính lại không đồng nghĩa chốt nhiều lần. Không đặt ghi database, gửi thông báo hay cập nhật một tài nguyên khác trong callback.
- Với phép cộng/tăng đơn giản, cân nhắc `incrementAndGet` hoặc `addAndGet`; với điều kiện gắn với trạng thái hiện tại, sử dụng hàm cập nhật thuần hoặc vòng CAS tự kiểm tra lại điều kiện.
- Chọn `AtomicInteger` hay `AtomicLong` theo phạm vi số và quy tắc nghiệp vụ; tính nguyên tử không loại bỏ overflow, lỗi giao dịch đa tài nguyên hay vấn đề tranh chấp.

Tài liệu chính thức Java SE 17:

- [`AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
- [`AtomicLong`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html)
- [`AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)
- [`CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [`LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
