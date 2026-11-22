# compareAndSet() và nguyên tắc CAS trong Java

## 1. Vấn đề mà CAS giải quyết

Trong lập trình đa luồng, hai thread có thể cùng cập nhật một giá trị. Biểu thức `counter++` thực chất cần đọc giá trị cũ, tính `+1` và ghi kết quả. Các bước có thể xen kẽ:

```text
Ban đầu counter = 10
Thread A: đọc 10              Thread B: đọc 10
Thread A: tính 11             Thread B: tính 11
Thread A: ghi 11              Thread B: ghi 11
Cuối cùng counter = 11, dù đã yêu cầu tăng hai lần.
```

Đây là **lost update**. `volatile` cho một trường có bảo đảm về visibility và thứ tự bộ nhớ, nhưng **không biến phép đọc–sửa–ghi thành một thao tác atomic**. Để sửa đúng, cần một giao thức cho phép phát hiện “giá trị đã bị ai đó đổi trước khi mình ghi”.

**Compare-And-Set (CAS)** là thao tác nguyên tử có điều kiện: **chỉ thay giá trị hiện tại bằng giá trị mới nếu giá trị hiện tại vẫn khớp giá trị kỳ vọng**. Trong thư viện Java, các lớp `AtomicInteger`, `AtomicLong`, `AtomicBoolean`, `AtomicReference` hỗ trợ phương thức `compareAndSet(expected, update)`.

Pseudocode:

```text
CAS(expected, update):
    nếu current khớp expected:
        current = update
        trả về true
    ngược lại:
        giữ nguyên current
        trả về false
```

Điều quan trọng là **so sánh và thay thế hợp thành một thao tác không bị xen ngang**. Viết bằng `if` thông thường trên một trường không được đồng bộ sẽ không tạo ra CAS.

Bài này chỉ nói về **concurrency của Java nói chung**, không phụ thuộc một framework cụ thể.

## 2. Ý nghĩa của kết quả boolean

- `true`: expected khớp giá trị hiện tại tại điểm CAS; cập nhật **đã commit**.
- `false`: đối với **strong CAS `compareAndSet`**, expected không khớp trong lần thử này; `update` **không được ghi**.
- Không có ngoại lệ “CAS tự retry” trong một lời gọi `compareAndSet` đơn lẻ. Người dùng API phải quyết định retry, từ chối hoặc xử lý conflict.
- Nếu dùng `AtomicReference<T>`, việc khớp expected được xét theo **danh tính tham chiếu (`==`)**, không phải `equals()`.
- Với các kiểu atomic số nguyên, so sánh expected theo giá trị nguyên thủy.

### Ví dụ 1: lời gọi thành công và thất bại

Tạo `CasBasicsDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class CasBasicsDemo {
    public static void main(String[] args) {
        AtomicInteger number = new AtomicInteger(10);

        boolean a = number.compareAndSet(10, 11);
        boolean b = number.compareAndSet(10, 12);
        boolean c = number.compareAndSet(11, 20);

        System.out.println("a=" + a);
        System.out.println("b=" + b);
        System.out.println("c=" + c);
        System.out.println("value=" + number.get());
    }
}
```

```bash
javac CasBasicsDemo.java
java CasBasicsDemo
```

Kết quả:

```text
a=true
b=false
c=true
value=20
```

Lần đầu `10 -> 11` thành công. Lần thứ hai vẫn kỳ vọng `10` nên thất bại, giữ nguyên `11`. Lần cuối kỳ vọng `11` nên thành công, ghi `20`.

Trong chương trình đa luồng, lý do expected trở thành “cũ” thường là một thread khác đã cập nhật giá trị giữa lúc mình gọi `get()` và lúc CAS.

## 3. Nhiều thread tranh CAS: chỉ một người thắng cùng expected

Giả sử hai thread cùng đọc `0`, đều gọi `compareAndSet(0, 1)`. Khi một CAS thành công, giá trị đã thành `1`; CAS còn lại với expected `0` phải thất bại nếu không có cập nhật đưa giá trị về `0`. Để kiểm chứng mà không phụ thuộc việc CPU ưu tiên thread nào, dùng latch.

Tạo `CasOneWinnerDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class CasOneWinnerDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger value = new AtomicInteger(0);
        AtomicInteger wins = new AtomicInteger(0);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch go = new CountDownLatch(1);

        Runnable task = () -> {
            int expected = value.get();
            bothRead.countDown();
            try {
                go.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            if (value.compareAndSet(expected, expected + 1)) {
                wins.incrementAndGet();
            }
        };

        Thread a = new Thread(task, "A");
        Thread b = new Thread(task, "B");
        a.start();
        b.start();
        bothRead.await();
        go.countDown();
        a.join();
        b.join();

        System.out.println("wins=" + wins.get());
        System.out.println("value=" + value.get());
    }
}
```

```bash
javac CasOneWinnerDemo.java
java CasOneWinnerDemo
```

Kết quả khi không có interrupt từ bên ngoài:

```text
wins=1
value=1
```

Hai thread chắc chắn đều đọc `0` trước khi được mở latch `go`. Một CAS thay giá trị thành `1`; CAS còn lại thấy expected không phù hợp. **Không thể dự đoán A hay B thắng**, nên ví dụ chỉ in số lần thành công. Nếu mỗi thread đại diện cho một lần **tăng bắt buộc phải được giữ**, thread thất bại phải đọc lại và retry.

## 4. Vòng retry CAS: đọc lại, tính lại, thử lại

Mẫu cập nhật một biến atomic:

```java
while (true) {
    int before = counter.get();
    int after = before + 1;
    if (counter.compareAndSet(before, after)) {
        break;
    }
    // CAS thất bại: thread khác có thể đã cập nhật counter.
    // Lượt sau đọc giá trị mới và tính lại.
}
```

Đây là đoạn minh họa, giả định `counter` là `AtomicInteger`. **Không** đưa `before` ra khỏi vòng rồi dùng mãi expected cũ: khi giá trị đã khác expected, vòng lặp có thể không bao giờ thành công.

### Ví dụ 2: mỗi yêu cầu tăng đều được giữ

Tạo `CasRetryDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class CasRetryDemo {
    static void increment(AtomicInteger value) {
        for (;;) {
            int before = value.get();
            int after = before + 1;
            if (value.compareAndSet(before, after)) {
                return;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger value = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);
        Runnable task = () -> {
            try {
                start.await();
                for (int i = 0; i < 10_000; i++) {
                    increment(value);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(task);
        Thread b = new Thread(task);
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();
        System.out.println("value=" + value.get());
    }
}
```

```bash
javac CasRetryDemo.java
java CasRetryDemo
```

Kết quả khi không có interrupt từ bên ngoài:

```text
value=20000
```

Mỗi thread tăng 10.000 lần. Khi CAS thất bại, nó thử lại với giá trị hiện tại; không bỏ một lần tăng. `join()` giúp main chỉ in sau khi cả hai hoàn tất.

Mẫu này chưa xử lý giới hạn số nguyên, hủy tác vụ, hoặc nhiều side effect khác. Nếu `int` có thể vượt giới hạn, phải thiết kế kiểm tra overflow. Nếu một vòng retry cần hủy được, cần chủ động đọc trạng thái interrupt hoặc token hủy tại điểm phù hợp.

## 5. Điểm tuyến tính hóa và JMM

CAS thành công có thể được hiểu là có một **linearization point** — điểm logic mà thay đổi từ expected sang update có hiệu lực nguyên tử. Điều này giải thích vì sao hai CAS cùng mong chờ một giá trị không thể cùng ghi đè mù quáng như hai phép `counter++`.

Các atomic API thông thường còn có **bảo đảm bộ nhớ** theo Java Memory Model (JMM). `get()`, `set()`, `compareAndSet()` cung cấp ngữ nghĩa phù hợp cho công bố và quan sát dữ liệu như các thao tác volatile tương ứng. Một thread tạo trạng thái hoàn chỉnh rồi công bố qua atomic reference, thread khác nhận tham chiếu đó bằng `get()` có quan hệ visibility/happens-before phù hợp để quan sát dữ liệu đã khởi tạo trước lúc công bố.

Nhưng không được suy rộng:

- Một CAS trên `atomic` không tự bảo vệ các trường mutable của object khác.
- Một CAS không thay thế transaction cho thao tác gồm nhiều biến/đối tượng riêng.
- Hai CAS thành công liên tiếp vẫn có **hai** điểm tuyến tính hóa, không hợp thành một giao dịch nguyên tử.
- Nếu object được công bố còn bị sửa không đồng bộ về sau, nguyên tử ở cấp tham chiếu không cứu các data race bên trong.

Hãy suy luận theo **đơn vị trạng thái cần nhất quán**, không chỉ theo sự xuất hiện của tên API atomic.

## 6. `AtomicReference` so theo identity, không phải `equals()`

Với `AtomicReference<T>`, expected phải là **đúng tham chiếu** đang được lưu. Hai object có nội dung bằng nhau theo `equals()` vẫn là hai identity khác nhau.

Tạo `CasReferenceIdentityDemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class CasReferenceIdentityDemo {
    record State(int value) {}

    public static void main(String[] args) {
        State original = new State(5);
        State equalCopy = new State(5);
        AtomicReference<State> ref = new AtomicReference<>(original);

        System.out.println("equals=" + original.equals(equalCopy));
        System.out.println("same=" + (original == equalCopy));

        boolean wrong = ref.compareAndSet(equalCopy, new State(6));
        boolean right = ref.compareAndSet(original, new State(6));

        System.out.println("wrong=" + wrong);
        System.out.println("right=" + right);
        System.out.println("value=" + ref.get().value());
    }
}
```

```bash
javac CasReferenceIdentityDemo.java
java CasReferenceIdentityDemo
```

Kết quả:

```text
equals=true
same=false
wrong=false
right=true
value=6
```

`State` là record nên hai record với cùng giá trị có `equals() == true`, nhưng chúng là hai object. CAS dùng tham chiếu `equalCopy` làm expected thất bại, còn dùng `original` là tham chiếu thực sự đang giữ thì thành công.

Đúng mẫu là:

```java
State before = ref.get();
State after = new State(before.value() + 1);
boolean changed = ref.compareAndSet(before, after);
```

Đây là đoạn minh họa; nếu `changed` là `false`, cần quyết định retry hoặc báo conflict. Tránh tự tạo một object mới “bằng” với state hiện tại rồi truyền làm expected.

## 7. CAS một immutable snapshot để cập nhật nhiều biến liên quan

Giả sử `left` và `right` là hai số dư có tổng luôn bằng `100`. Hai `AtomicInteger` cập nhật lần lượt:

```java
left.addAndGet(-1);
right.addAndGet(1);
```

vẫn có thể khiến reader thấy tổng bằng `99` ở giữa hai bước. Mỗi atomic tự nhất quán không biến một nhóm field thành transaction.

Giải pháp phù hợp với trạng thái nhỏ là gói cả hai trong **một record bất biến** và CAS **một tham chiếu gốc**.

Tạo `CasSnapshotDemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class CasSnapshotDemo {
    record Balances(int left, int right) {
        Balances {
            if (left < 0 || right < 0 || left + right != 100) {
                throw new IllegalArgumentException("invalid state");
            }
        }
    }

    static void transferOne(AtomicReference<Balances> ref) {
        for (;;) {
            Balances before = ref.get();
            Balances after =
                    new Balances(before.left() - 1, before.right() + 1);

            if (ref.compareAndSet(before, after)) {
                return;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Balances> state =
                new AtomicReference<>(new Balances(100, 0));

        Runnable task = () -> {
            for (int i = 0; i < 50; i++) {
                transferOne(state);
            }
        };

        Thread a = new Thread(task);
        Thread b = new Thread(task);
        a.start();
        b.start();
        a.join();
        b.join();

        Balances snapshot = state.get();
        System.out.println("left=" + snapshot.left());
        System.out.println("right=" + snapshot.right());
        System.out.println("total="
                + (snapshot.left() + snapshot.right()));
    }
}
```

```bash
javac CasSnapshotDemo.java
java CasSnapshotDemo
```

Kết quả:

```text
left=0
right=100
total=100
```

Hai thread mỗi người thực hiện 50 lần chuyển một đơn vị, tất cả đều phải commit. Mỗi vòng CAS tạo một record hoàn chỉnh, hợp lệ; nếu bị cạnh tranh, vòng lặp lấy record mới và tính lại. Không có record nào bị sửa tại chỗ.

**Reader phải lấy một tham chiếu duy nhất** khi cần nhiều trường cùng phiên bản:

```java
Balances snapshot = state.get();
int left = snapshot.left();
int right = snapshot.right();
```

Đây là đoạn minh họa dùng `state` ở ví dụ trên. Nếu gọi `state.get().left()` và `state.get().right()` **hai lần riêng**, writer có thể thay snapshot giữa hai lượt, khiến reader ghép hai phiên bản khác nhau.

Ví dụ cố ý có đúng 100 đơn vị và đúng 100 lần chuyển nên không âm. Trong ứng dụng thật, validation như đủ tiền, overflow, điều kiện hủy phải được kiểm tra trên **mỗi snapshot đọc lại**, và cập nhật RAM không thay thế transaction database.

## 8. Hàm CAS nội bộ có thể bị gọi lại

`AtomicInteger.updateAndGet`, `getAndUpdate` và các biến thể của `AtomicReference` thường thực hiện cơ chế retry nội bộ để áp dụng một hàm của giá trị cũ.

```java
AtomicInteger n = new AtomicInteger(10);
int after = n.updateAndGet(old -> old + 5);
```

Đoạn minh họa này cần import `AtomicInteger`; `after` bằng `15` khi không có writer khác. Nhưng nếu bị contention, hàm `old -> old + 5` **có thể được gọi nhiều lần** cho một lần commit.

Vì vậy không nên viết:

```java
n.updateAndGet(old -> {
    chargeCustomer(); // Có thể gọi nhiều lần do retry!
    return old + 5;
});
```

Đây là phản ví dụ, `chargeCustomer()` là hàm nghiệp vụ. Hàm cập nhật nên thuần (không có tác dụng phụ không thể lặp), tính state mới từ state cũ. Side effect bên ngoài CAS phải được điều phối bằng idempotency hoặc transaction nếu hệ thống yêu cầu “một lần duy nhất”; chuyển side effect ra ngoài lambda **không tự làm hai hệ thống trở thành một transaction**.

Một quy tắc quan trọng: **mỗi lần CAS thất bại phải tính lại state và điều kiện hợp lệ trên snapshot mới**. Không tái sử dụng kết quả kiểm tra từ phiên bản cũ nếu điều kiện nghiệp vụ có thể thay đổi.

## 9. ABA problem: giá trị A → B → A

CAS xem **giá trị hiện tại**, không tự lưu lịch sử. Nếu thread A đọc giá trị `A` rồi chờ, thread B có thể đổi `A -> B -> A`. Khi A gọi CAS với expected `A`, thao tác có thể thành công. Đây gọi là **ABA**.

```text
Thread A: read A ------------------ CAS(A, C) SUCCESS
Thread B:        A -> B -> A
Shared:    A ------- B ---- A ------ C
```

CAS không sai: tại thời điểm của nó, current quả thực là A. **Lỗi chỉ xuất hiện nếu thuật toán giả định “vẫn A” đồng nghĩa “chưa có thay đổi lịch sử”.** Ví dụ, với node của một lock-free stack, tham chiếu trở lại node cũ không nhất thiết có nghĩa các liên kết còn như trước.

### Phiên bản hóa bằng `AtomicStampedReference`

Java cung cấp `AtomicStampedReference<V>` để cập nhật nguyên tử một cặp **(reference, stamp)**. Mọi writer có thể tăng stamp theo giao thức, nhờ đó trạng thái quay lại cùng reference vẫn được nhận ra là một phiên bản mới.

Tạo `CasAbaDemo.java`:

```java
import java.util.concurrent.atomic.AtomicStampedReference;

public class CasAbaDemo {
    public static void main(String[] args) {
        Object a = new Object();
        Object b = new Object();
        Object c = new Object();

        AtomicStampedReference<Object> state =
                new AtomicStampedReference<>(a, 0);
        int oldStamp = state.getStamp();

        boolean ab = state.compareAndSet(a, b, 0, 1);
        boolean ba = state.compareAndSet(b, a, 1, 2);
        boolean stale =
                state.compareAndSet(a, c, oldStamp, oldStamp + 1);

        System.out.println("A-B=" + ab);
        System.out.println("B-A=" + ba);
        System.out.println("same=" + (state.getReference() == a));
        System.out.println("stale=" + stale);
        System.out.println("stamp=" + state.getStamp());
    }
}
```

```bash
javac CasAbaDemo.java
java CasAbaDemo
```

Kết quả:

```text
A-B=true
B-A=true
same=true
stale=false
stamp=2
```

Tham chiếu đã quay về đúng object `a`, nhưng stamp tăng từ `0` lên `2`. CAS với expected stamp `0` thất bại. Cơ chế cần **mọi writer cập nhật stamp nhất quán**. Stamp `int` vẫn có giới hạn và có thể quay vòng nếu hệ thống chạy đủ lâu. `AtomicMarkableReference` giữ một cờ boolean kèm tham chiếu cho bài toán đánh dấu trạng thái cụ thể, không phải version counter tổng quát.

**Không phải mọi ABA là bug:** nếu thuật toán chỉ quan tâm giá trị hiện tại, việc quay lại giá trị cũ có thể hoàn toàn chấp nhận.

## 10. Strong CAS và weak CAS

`compareAndSet` thông thường của `AtomicInteger` và `AtomicReference` là **strong CAS**: khi trả `false`, expected không khớp tại lần thử tương ứng.

Một số phương thức **weak CAS** như `weakCompareAndSetPlain` có thể trả `false` dù expected khớp (**spurious failure**). Vì vậy không thể suy ra chắc chắn đã có writer khác chỉ từ một lần weak CAS trả false. Các biến thể weak CAS như `weakCompareAndSetAcquire`, `weakCompareAndSetRelease` còn có ngữ nghĩa bộ nhớ khác nhau; không thay tên phương thức mà bỏ qua hợp đồng ordering.

`compareAndSet` là lựa chọn dễ hiểu hơn cho đa số trường hợp. Weak CAS chỉ nên dùng khi biết rõ memory ordering và thuật toán retry cần thiết.

**Đừng nhầm** spurious failure của weak CAS với spurious wakeup của `Object.wait()` hoặc `Condition.await()`. Chúng là hai hiện tượng thuộc các API khác nhau.

## 11. CAS so với các primitive khác

| Primitive | Điểm mạnh | Điểm phải lưu ý |
| --- | --- | --- |
| `volatile` | Công bố/quan sát giá trị đơn lẻ theo ordering JMM | `counter++` không nguyên tử |
| `synchronized` | Bảo vệ critical section, có mutual exclusion và happens-before qua cùng monitor | Cần lock scope đúng, quản lý contention |
| `AtomicInteger.incrementAndGet` | Tăng nguyên tử, không cần tự viết loop | Phù hợp một biến số |
| `compareAndSet` | Chuyển trạng thái có điều kiện, cập nhật nguyên tử một vị trí | Phải xử lý thất bại |
| `AtomicReference<State>` | Công bố immutable snapshot nguyên tử | State bên trong phải thực sự bất biến hoặc có đồng bộ riêng |
| `LongAdder` | Có thể tăng throughput khi nhiều writer cộng dồn | `sum()` không phải snapshot nguyên tử dưới writer đồng thời |

Nếu chỉ tăng số, ưu tiên `incrementAndGet` cho rõ ràng. Nếu nhiều field phải đổi như một đơn vị, dùng một snapshot gốc hoặc lock. Với contention cao, CAS loop có thể tiêu tốn CPU do retry; **không mặc định CAS luôn nhanh hơn khóa**.

Khái niệm **lock-free** chỉ đúng khi **toàn thuật toán** bảo đảm có một operation nào đó tiến triển; không có nghĩa mọi thread chắc chắn thành công trong thời gian ngắn. **Wait-free** mạnh hơn: từng operation có bảo đảm giới hạn bước. CAS là nền tảng nhiều thuật toán không chặn, nhưng việc thấy một CAS trong method không chứng minh method đó lock-free.

## 12. CAS có cần xử lý interrupt hay hủy không?

Lời gọi `compareAndSet` không phải thao tác chờ khóa kiểu `lockInterruptibly()`, nên không tự ném `InterruptedException` để báo hủy. Một vòng retry CPU-bound có thể cần đọc `Thread.currentThread().isInterrupted()` hoặc một token hủy ở điểm an toàn:

```java
for (;;) {
    if (Thread.currentThread().isInterrupted()) {
        return; // Chưa commit lượt cập nhật này.
    }

    State before = ref.get();
    State after = calculateNext(before);

    if (ref.compareAndSet(before, after)) {
        return; // Lượt cập nhật đã commit.
    }
}
```

Đây là đoạn minh họa với `State`, `ref` và `calculateNext` do ứng dụng định nghĩa. Tín hiệu hủy có thể đến **ngay sau kiểm tra nhưng trước CAS**; nếu cần “cancel hoặc commit, không thể cả hai” ở một điểm logic, phải mô hình hóa trạng thái hủy trong cùng state machine hoặc dùng giao thức điều phối chặt hơn.

Dừng task sau một nửa thao tác nhiều bước có thể làm hỏng invariant. Chỉ phản hồi hủy ở điểm an toàn hoặc có rollback phù hợp. `Thread.interrupt()` không tự hoàn tác một CAS đã thành công.

## 13. CAS dùng cho state machine

Một use case dễ hiểu là chỉ cho phép task chuyển `NEW -> RUNNING -> DONE`. Nếu hai thread cùng đòi khởi động, chỉ một phép chuyển `NEW -> RUNNING` được phép thành công.

Tạo `CasStateDemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class CasStateDemo {
    enum Status { NEW, RUNNING, DONE }

    public static void main(String[] args) {
        AtomicReference<Status> state =
                new AtomicReference<>(Status.NEW);

        boolean start = state.compareAndSet(Status.NEW, Status.RUNNING);
        boolean startAgain = state.compareAndSet(Status.NEW, Status.RUNNING);
        boolean finish = state.compareAndSet(Status.RUNNING, Status.DONE);

        System.out.println("start=" + start);
        System.out.println("startAgain=" + startAgain);
        System.out.println("finish=" + finish);
        System.out.println("state=" + state.get());
    }
}
```

```bash
javac CasStateDemo.java
java CasStateDemo
```

Kết quả:

```text
start=true
startAgain=false
finish=true
state=DONE
```

`enum` có constant là object duy nhất, phù hợp với identity CAS. Ví dụ giải thích các chuyển trạng thái theo một chuỗi đơn luồng; với nhiều thread phải thiết kế đầy đủ quy tắc `FAILED`, `CANCELED`, kết quả task và side effect ngoài JVM. Một CAS state thành công không tự có nghĩa toàn bộ nghiệp vụ đã xong.

## 14. Những API gần CAS

- `compareAndSet(e, u)` trả boolean: có commit khi expected khớp không?
- `compareAndExchange(e, u)` trả **giá trị được quan sát** tại điểm so sánh (witness), thay vì chỉ boolean. Có trong Java 9+.
- `getAndSet(u)` thay atomically bằng `u` và trả giá trị cũ, không kiểm tra expected.
- `getAndUpdate(fn)` và `updateAndGet(fn)` áp dụng hàm cập nhật với khả năng retry; khác nhau ở giá trị trả về.
- `VarHandle` cung cấp các thao tác atomic/memory ordering cấp thấp trên field/array element, hữu ích khi cần thiết kế đặc thù; với đa số bài toán, atomic wrapper dễ dùng hơn.

Không thay một API bằng API khác chỉ vì cả hai có chữ “set”: expected, giá trị trả về và memory ordering có thể khác nhau.

## 15. Những lỗi điển hình cần tránh

1. **Bỏ qua boolean:** gọi CAS rồi báo thành công dù nhận `false`.
2. **Retry với expected cũ:** không đọc lại state khiến loop có thể chạy mãi.
3. **Gọi side effect trong lambda retry:** tác vụ có thể lặp nhiều lần cho một lần commit.
4. **Lấy hai snapshot khác thời điểm:** đọc hai field qua hai lần `AtomicReference.get()` có thể ghép hai version.
5. **Dùng hai biến atomic cho một invariant:** mỗi biến nguyên tử riêng không bảo vệ toàn bộ nhóm.
6. **Nhầm equals và identity:** `AtomicReference.compareAndSet` so tham chiếu object.
7. **Bỏ qua ABA:** giá trị quay về cũ không chứng minh lịch sử không thay đổi.
8. **Tưởng CAS không bao giờ tốn CPU:** contention cao tạo nhiều lần thất bại, có thể cần backoff hoặc primitive khác.
9. **Bỏ qua overflow và chính sách hủy:** CAS không tự kiểm tra domain bound hay nhận interrupt.
10. **Đánh đồng CAS với giao dịch:** một update RAM không làm I/O, database hoặc message broker được commit nguyên tử cùng nó.

## 16. Tự kiểm tra

**Câu 1.** `AtomicInteger` có giá trị `4`. Gọi `compareAndSet(4, 5)` rồi `compareAndSet(4, 6)`. Kết quả?

**Trả lời:** `true` rồi `false`; giá trị cuối `5`.

**Câu 2.** Hai thread đọc cùng `0` rồi CAS `(0, 1)`. Nếu không có writer khác, cả hai có thành công không?

**Trả lời:** Không. Một thread thắng và đổi giá trị thành `1`. Thread kia phải retry với expected mới nếu muốn thực hiện lượt tăng riêng của nó.

**Câu 3.** `volatile int x` có làm `x++` an toàn với nhiều writer không?

**Trả lời:** Không. Visibility khác atomicity của toàn bộ read-modify-write.

**Câu 4.** Hai record có `equals()==true` nhưng `==false`; dùng record mới làm expected của CAS reference có đúng không?

**Trả lời:** Không nếu reference hiện tại giữ record còn lại. CAS reference so identity.

**Câu 5.** Hai số dư dùng hai `AtomicInteger` riêng có đủ bảo đảm tổng không đổi khi chuyển tiền không?

**Trả lời:** Không. Phải bảo vệ nhóm cập nhật/đọc hoặc gói thành một immutable snapshot thay bằng CAS trên root reference.

**Câu 6.** Vì sao hàm `updateAndGet` nên không có side effect?

**Trả lời:** Hàm có thể được gọi lại do contention, khiến side effect lặp nhiều lần.

**Câu 7.** ABA `A -> B -> A` có làm CAS sai về nguyên tử không?

**Trả lời:** Không. CAS xét giá trị tại thời điểm thực hiện; lỗi chỉ có nếu thuật toán cần lịch sử mà không lưu version.

**Câu 8.** `weakCompareAndSetPlain` trả false có luôn biểu thị thread khác đã sửa không?

**Trả lời:** Không. Weak CAS có thể thất bại giả.

**Câu 9.** CAS có tự bảo đảm thread bị hủy sẽ không commit tiếp không?

**Trả lời:** Không. Cần thiết kế điểm hủy và commit rõ ràng, có thể gộp trạng thái cancel trong một state machine atomic.

## 17. Tổng kết

**CAS = compare rồi set atomically nếu và chỉ nếu giá trị hiện tại còn khớp expected.** Để giữ mọi lần cập nhật dưới contention, dùng vòng **đọc lại → tính lại → CAS → retry nếu thất bại**. Một CAS thành công có điểm tuyến tính hóa rõ cho **một vị trí atomic**.

Trong Java, áp dụng đúng còn đòi hỏi hiểu **visibility/happens-before của JMM**, so sánh identity của `AtomicReference`, ABA, weak CAS và side effect khi retry. Khi invariant trải trên nhiều field, đóng gói chúng thành **immutable snapshot** rồi CAS một tham chiếu gốc, hoặc dùng khóa cùng giao thức; đừng dùng CAS như giải pháp thay thế cho mọi transaction hay mọi điều phối giữa thread.
