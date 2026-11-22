# AtomicInteger, AtomicLong và AtomicBoolean trong Java

Khi nhiều thread cùng đọc và thay đổi một biến, ba thao tác tưởng như đơn giản — đọc giá trị, tính giá trị mới, rồi ghi lại — có thể xen kẽ khiến dữ liệu sai. `AtomicInteger`, `AtomicLong` và `AtomicBoolean` trong `java.util.concurrent.atomic` cung cấp các **phép đọc, ghi và cập nhật nguyên tử trên một giá trị** với các bảo đảm bộ nhớ xác định theo Java Memory Model (JMM). Chúng đặc biệt phù hợp với bộ đếm, sequence number, cờ trạng thái và một số giao thức chuyển trạng thái đơn giản.

Điểm quan trọng nhất: **một thao tác atomic không có nghĩa mọi logic bao quanh nó tự động atomic**. Dùng `AtomicInteger.incrementAndGet()` có thể tránh lost update khi tăng một bộ đếm, nhưng một chuỗi `get()` rồi `set()` vẫn có khoảng xen kẽ; `AtomicBoolean` có thể bảo đảm chỉ một thread đổi cờ từ `false` sang `true`, nhưng không tự bảo đảm công việc phía sau đã hoàn tất.

Bài này thuộc chủ đề **Atomic & CAS** của **Java concurrency nói chung**. Các API và ví dụ dùng Java SE 17+, không dùng cơ chế concurrency riêng của Spring Framework.

## 1. Vì sao `int`, `long` và `boolean` thông thường không đủ?

Ví dụ:

```java
final class UnsafeCounter {
    private int value;

    void increment() {
        value++; // Không atomic.
    }

    int get() {
        return value;
    }
}
```

Đoạn trên là class minh họa, không có `main`. Hai thread có thể cùng đọc `value == 10`, cùng tính `11` rồi cùng ghi `11`. Kết quả bị **lost update**: hai lời gọi tăng chỉ tạo hiệu ứng một lần tăng.

`value++` là phép **read-modify-write**, không phải thao tác không thể xen giữa. Đánh dấu field thành `volatile int value` giúp cung cấp semantics visibility/ordering cho từng lần đọc/ghi volatile, **nhưng không làm toàn bộ `value++` thành atomic**.

Tách ba nhu cầu:

- **Atomicity:** một operation diễn ra như một bước không thể bị thread khác xen giữa ở ranh giới API đã định nghĩa.
- **Visibility và ordering:** reader được bảo đảm quan sát các ghi trước đó khi có quan hệ happens-before phù hợp.
- **Coordination/progress:** thread nào chờ ai, ai có quyền thực hiện tác vụ, khi nào dừng hoặc báo hoàn tất.

Atomic variables hỗ trợ hai nhóm đầu trong **phạm vi mỗi phép toán và giao thức dùng đúng**. Chúng không thay `CountDownLatch`, `BlockingQueue`, `Future` hoặc monitor khi cần phối hợp tiến độ hay giao dịch nhiều field.

## 2. Ba lớp atomic cơ bản

| Lớp | Giá trị được quản lý | Mẫu sử dụng phù hợp |
| --- | --- | --- |
| `AtomicInteger` | Một `int` 32-bit có dấu | Đếm task, version nhỏ, trạng thái số, quota đơn biến |
| `AtomicLong` | Một `long` 64-bit có dấu | Sequence number, số liệu lớn, counter dài hạn |
| `AtomicBoolean` | Một `boolean` | Cờ một lần, trạng thái enabled/stopped, quyền bắt đầu thao tác |
 
Cả ba đều nằm trong `java.util.concurrent.atomic` và cho phép **nhiều thread dùng chung một instance**. Ví dụ:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicBoolean;

AtomicInteger total = new AtomicInteger(0);
AtomicLong sequence = new AtomicLong(1000L);
AtomicBoolean started = new AtomicBoolean(false);
```

Đây là đoạn minh họa khai báo biến, không phải chương trình độc lập.

Không có nghĩa object nào chứa atomic field cũng thread-safe. Nếu một class có `AtomicInteger count` và một `ArrayList` được nhiều thread sửa, chỉ **các thao tác được atomic class bảo đảm** là atomic; list và những invariant liên quan vẫn cần thiết kế riêng.

Đối với counter tăng với contention cực cao, `LongAdder` đôi khi hữu ích hơn `AtomicLong` cho thống kê. Nhưng `LongAdder.sum()` trong lúc các thread cập nhật **không phải snapshot atomic**, nên không thay thế tùy tiện khi cần một con số tuyến tính hóa tại một thời điểm.

## 3. API quan trọng: không chỉ `get()` và `set()`

Các method thường gặp:

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `get()` | Đọc giá trị bằng semantics volatile | Giá trị có thể thay đổi ngay sau khi trả về |
| `set(newValue)` | Ghi giá trị bằng semantics volatile | Một lần ghi atomic, không phải phép kiểm tra-ghi có điều kiện |
| `getAndSet(newValue)` | Thay giá trị atomic, trả **giá trị cũ** | Hữu ích để lấy rồi reset counter hoặc claim một cờ |
| `compareAndSet(expected, update)` | Nếu giá trị hiện tại bằng expected, atomically đổi sang update | Trả `true` khi update thành công; `false` khi expected không còn khớp |
| `compareAndExchange(expected, update)` | Trao đổi có điều kiện, trả giá trị đã quan sát tại thời điểm thao tác | Có từ Java 9; giá trị trả về giúp biết trạng thái thực |
| `lazySet(newValue)` | Ghi với release semantics (weak hơn volatile `set` ở một số chiều) | Chỉ dùng nếu hiểu giao thức publication và ordering cần thiết |

Riêng `AtomicInteger` và `AtomicLong` có:

| API | Kết quả |
| --- | --- |
| `getAndIncrement()` | Tăng 1, trả giá trị **trước** khi tăng |
| `incrementAndGet()` | Tăng 1, trả giá trị **sau** khi tăng |
| `getAndDecrement()` và `decrementAndGet()` | Giảm 1; khác giá trị cũ/mới |
| `getAndAdd(delta)` | Cộng delta, trả giá trị cũ |
| `addAndGet(delta)` | Cộng delta, trả giá trị mới |
| `getAndUpdate(fn)` và `updateAndGet(fn)` | Tính giá trị mới bằng hàm một ngôi; có thể chạy lại hàm do tranh chấp |
| `getAndAccumulate(x, fn)` và `accumulateAndGet(x, fn)` | Tính giá trị mới bằng hàm hai ngôi; có thể chạy lại hàm khi CAS thất bại |

`AtomicBoolean` không có phép tăng/giảm; bộ ba quan trọng của nó là `get`, `set` và `compareAndSet`, cùng `getAndSet`.

**Quy ước return value là một phần quan trọng của contract.** Một lỗi thường gặp là dùng `getAndIncrement()` rồi nghĩ nó trả số mới, hoặc dùng `incrementAndGet()` khi muốn phát ID bằng giá trị trước increment.

## 4. CAS: Compare-And-Set hoạt động thế nào?

CAS biểu diễn một phép cập nhật có điều kiện:

```text
current = giá trị của atomic variable tại điểm thực hiện

nếu current == expected:
    đặt current = update
    trả về true
ngược lại:
    giữ nguyên current
    trả về false
```

Đây là **mô hình ý nghĩa**, không phải pseudo-code được triển khai bằng một lượt đọc ordinary rồi ghi ordinary. Sức mạnh của CAS là bước kiểm tra và thay đổi được bảo đảm **atomic** theo hợp đồng của operation.

Ví dụ:

```java
AtomicInteger state = new AtomicInteger(10);

boolean first = state.compareAndSet(10, 20);   // true
boolean second = state.compareAndSet(10, 30);  // false
int now = state.get();                         // 20
```

Đây là ví dụ minh họa với biến đã import `AtomicInteger`, không phải class có `main`.

Khi hai thread cùng CAS từ `0` sang hai giá trị khác nhau, **chỉ một** có thể thành công trên cùng trạng thái `0` nếu không có thao tác khác đưa trạng thái trở lại `0`. Thread thua phải xử lý kết quả `false` — không được giả định thao tác đã thực hiện.

### CAS và linearizability

Mỗi `compareAndSet` có thể được coi như xảy ra tại một điểm quan sát giữa lúc gọi và lúc trả về; các lần cập nhật thành công cho **một atomic variable** có thứ tự phù hợp. Nhưng **toàn bộ nhiều lời gọi CAS/get/set**, hoặc cập nhật atomic variable cộng với thao tác I/O ngoài đó, không tự biến thành một transaction tuyến tính hóa.

CAS cũng không tự cam kết fairness: một thread có thể thua nhiều lần trong cạnh tranh cao. Một thuật toán lặp CAS thường tránh monitor lock cho cập nhật nhỏ nhưng vẫn tiêu tốn CPU khi retry nhiều lần.

## 5. Ví dụ Java 17+: ba lớp trong chương trình đa luồng

Lưu thành `AtomicBasicsDemo.java`:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class AtomicBasicsDemo {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicInteger processed = new AtomicInteger();
        AtomicLong total = new AtomicLong();
        AtomicBoolean claimed = new AtomicBoolean(false);

        Runnable work = () -> {
            for (int i = 0; i < 10_000; i++) {
                processed.incrementAndGet();
                total.addAndGet(2L);
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);

        first.start();
        second.start();
        first.join();
        second.join();

        boolean firstClaim = claimed.compareAndSet(false, true);
        boolean secondClaim = claimed.compareAndSet(false, true);

        System.out.println("Processed: " + processed.get());
        System.out.println("Total: " + total.get());
        System.out.println("First claim: " + firstClaim);
        System.out.println("Second claim: " + secondClaim);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac AtomicBasicsDemo.java
java AtomicBasicsDemo
```

Stdout chính xác:

```text
Processed: 20000
Total: 40000
First claim: true
Second claim: false
```

Giải thích:

1. Hai worker cùng giữ reference tới **cùng** `processed` và `total`.
2. `incrementAndGet` và `addAndGet` là những operation atomic độc lập, nên mỗi worker hoàn tất 10.000 lần cập nhật trên mỗi biến, không có lost update.
3. `Thread.join()` đợi **cả hai** worker xong trước khi main in. Do đó output không phụ thuộc vào việc worker nào chạy nhanh hơn.
4. `compareAndSet(false, true)` lần đầu thành công; lần thứ hai thất bại do cờ đã là `true`. Hai lần CAS này được main gọi tuần tự chỉ để minh họa giá trị trả về.
5. **Không** suy ra từ chương trình rằng `processed` và `total` được thay đổi như một cặp atomic. Một reader chạy ngay giữa hai lần update trong worker có thể nhìn thấy chúng ở hai mốc khác nhau.

Nếu nghiệp vụ đòi hỏi "mọi lúc `total == 2 * processed`" đối với reader concurrent, cần một giao thức khác để bảo vệ **invariant giữa hai biến**, ví dụ khóa hoặc một immutable state object được thay nguyên tử qua `AtomicReference`.

## 6. `AtomicInteger`: bộ đếm, trạng thái số và hạn mức

### Đếm số operation hoàn thành

`AtomicInteger` rất phù hợp với:

- Số lượng tác vụ đã hoàn tất.
- Số phần tử được xử lý, khi một event được tính đúng một lần.
- Đếm số waiter hoặc số yêu cầu đang hoạt động với giao thức tăng/giảm rõ.
- Trạng thái số dạng `NEW=0`, `RUNNING=1`, `DONE=2` khi cần transition atomic theo điều kiện.

Lưu ý nghĩa của counter phải được xác định: **số tác vụ bắt đầu, số tác vụ thành công và số tác vụ đang chạy là ba metric khác nhau**. Một atomic counter có thể đếm chính xác từng lần gọi tăng nhưng không tự biết lần tăng có đại diện đúng nghiệp vụ hay không.

### Không viết check-then-act bằng hai operation

Anti-pattern:

```java
if (inFlight.get() < limit) {
    inFlight.incrementAndGet();
}
```

Nếu hai thread cùng thấy giá trị ngay dưới `limit`, cả hai có thể tăng, khiến hạn mức bị vượt. `get` và `incrementAndGet` **riêng lẻ** an toàn; **chuỗi hai lời gọi** không atomic.

Giải pháp là gói phép kiểm tra và thay đổi thành **một operation logic CAS loop** hoặc sử dụng `Semaphore` nếu mục đích thực sự là hạn chế permit và cần phối hợp chờ.

## 7. Ví dụ Java 17+: tăng với giới hạn bằng CAS loop

Lưu thành `BoundedAtomicCounterDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedAtomicCounterDemo {

    static final class BoundedCounter {
        private final int maximum;
        private final AtomicInteger value = new AtomicInteger();

        BoundedCounter(int maximum) {
            if (maximum < 0) {
                throw new IllegalArgumentException("negative maximum");
            }
            this.maximum = maximum;
        }

        boolean tryIncrement() {
            while (true) {
                int current = value.get();
                if (current >= maximum) {
                    return false;
                }
                if (value.compareAndSet(current, current + 1)) {
                    return true;
                }
                // Thua tranh chấp: đọc lại và kiểm tra giới hạn.
            }
        }

        int get() {
            return value.get();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        BoundedCounter counter = new BoundedCounter(1_750);
        AtomicInteger successes = new AtomicInteger();
        Thread[] workers = new Thread[8];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int attempt = 0; attempt < 1_000; attempt++) {
                    if (counter.tryIncrement()) {
                        successes.incrementAndGet();
                    }
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Accepted: " + successes.get());
        System.out.println("Counter: " + counter.get());
    }
}
```

```bash
javac BoundedAtomicCounterDemo.java
java BoundedAtomicCounterDemo
```

Stdout chính xác:

```text
Accepted: 1750
Counter: 1750
```

Phân tích từng bước:

- Mỗi worker cố tăng 1.000 lần; tổng là 8.000 lần thử nhưng counter tối đa 1.750.
- `current = value.get()` chỉ là ảnh chụp tạm. Thread khác có thể thay đổi value ngay sau đó.
- `compareAndSet(current, current + 1)` bảo đảm rằng chỉ thread còn thấy **đúng current** mới thay đổi được sang `current + 1`.
- Nếu CAS thất bại, vòng lặp phải **đọc lại** và kiểm tra giới hạn. Không dùng một giá trị `current` cũ để retry vô hạn.
- Khi giá trị đạt 1.750, mọi lần thử mới trả `false`. Vì đây là counter chỉ tăng và không có phép giảm, không có đường quay lại trạng thái cũ.
- `successes` đếm số lời gọi `tryIncrement` trả true; output được in sau `join()` nên tổng chính xác.

Giới hạn của giải pháp: nó chỉ quản lý **một biến**; không có cơ chế chờ khi hết chỗ. Nếu cần cấp/release slot cho tài nguyên, quản lý fairness, timeout, interruption và chờ permit, `Semaphore` thường diễn đạt đúng hơn. Vòng CAS có thể retry nhiều lần dưới contention mạnh.

### Vì sao `current + 1` không overflow trong ví dụ?

Constructor chỉ chấp nhận `maximum >= 0`. CAS chỉ tính `current + 1` khi `current < maximum`; vì `maximum` là `int`, `current` không thể lớn hơn `Integer.MAX_VALUE - 1` tại nhánh cập nhật. Do đó ví dụ không bị overflow ở bước này.

Đối với counter không có giới hạn, `AtomicInteger.incrementAndGet()` **không tự kiểm tra overflow**; nếu tăng quá `Integer.MAX_VALUE`, giá trị sẽ wrap sang `Integer.MIN_VALUE` theo số nguyên Java. Nếu hệ thống cần tính đơn điệu tuyệt đối hoặc ID không được tái sử dụng, phải quản lý ngưỡng và vòng đời.

## 8. `AtomicLong`: sequence number và số liệu lớn

`AtomicLong` có cùng nhóm phép toán số học như `AtomicInteger` nhưng lưu một `long` 64-bit, hữu ích khi số lượng thao tác có thể vượt khoảng `int`.

Ví dụ phát sequence number:

```java
AtomicLong nextId = new AtomicLong(1_000L);
long first = nextId.getAndIncrement();   // 1000
long second = nextId.getAndIncrement();  // 1001
```

Đây là đoạn minh họa. `getAndIncrement` trả giá trị cũ; nếu cần trả giá trị sau khi tăng, dùng `incrementAndGet`.

### Phạm vi duy nhất của ID

Một `AtomicLong` đảm bảo mỗi update thành công trên **chính instance đó** có thứ tự atomic. Nhưng không tự bảo đảm:

- ID là duy nhất giữa **hai tiến trình JVM khác nhau**;
- ID tồn tại bền vững sau restart;
- ID không bị trùng nếu counter overflow hoặc bị reset;
- các bản ghi được commit theo thứ tự số ID;
- request lấy ID thấp hơn hoàn tất công việc sớm hơn.

Đây là sự khác nhau giữa **atomic sequence in-process** và **distributed/durable identity**. Trên một JVM, nếu không reset và chưa overflow, `getAndIncrement` có thể dùng phát số tăng dần cho nhiều caller đồng thời. Nhưng không phải công cụ giải quyết mọi yêu cầu ID trong hệ thống phân tán.

### Ví dụ Java 17+ xác nhận ID không trùng

Lưu thành `AtomicSequenceDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicLong;

public class AtomicSequenceDemo {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicLong nextId = new AtomicLong(1_000);
        long[] issued = new long[400];
        Thread[] workers = new Thread[4];

        for (int worker = 0; worker < workers.length; worker++) {
            final int index = worker;
            workers[worker] = new Thread(() -> {
                int offset = index * 100;
                for (int j = 0; j < 100; j++) {
                    issued[offset + j] = nextId.getAndIncrement();
                }
            });
            workers[worker].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        Arrays.sort(issued);
        boolean contiguous = true;
        for (int i = 0; i < issued.length; i++) {
            if (issued[i] != 1_000L + i) {
                contiguous = false;
                break;
            }
        }

        System.out.println("Issued: " + issued.length);
        System.out.println("Range: " + issued[0] + ".."
                + issued[issued.length - 1]);
        System.out.println("Contiguous: " + contiguous);
    }
}
```

```bash
javac AtomicSequenceDemo.java
java AtomicSequenceDemo
```

Stdout chính xác:

```text
Issued: 400
Range: 1000..1399
Contiguous: true
```

Mỗi worker ghi vào **một vùng chỉ số riêng** của array nên không có hai writer tranh cùng phần tử. `join` công bố các ghi của worker cho main trước khi sort và đọc. Các giá trị phát ra có thể thuộc worker khác nhau theo thứ tự không cố định, nhưng tập giá trị là từ 1000 đến 1399 và không trùng. Sắp xếp trước khi in khiến kết quả xác định.

## 9. `AtomicBoolean`: cờ đơn và quyền chuyển trạng thái

`AtomicBoolean` phù hợp để quản lý một trạng thái nhị phân mà nhiều thread có thể đọc/đổi:

- Cờ yêu cầu dừng công việc.
- Cờ đã bắt đầu hoặc đã gửi tín hiệu một lần.
- Cờ "chỉ cho một caller nhận quyền".
- Cờ bật/tắt một chức năng khi ngữ nghĩa không cần thêm trạng thái.

Khác biệt giữa `set(true)` và `compareAndSet(false, true)` rất quan trọng:

```java
AtomicBoolean started = new AtomicBoolean(false);

started.set(true); // Ghi true; mọi caller đều có thể gọi thành công.

boolean winner = started.compareAndSet(false, true);
// Chỉ trả true nếu caller thắng chuyển false -> true.
```

Một cờ `true` có thể có nghĩa "đã có ai đó claim quyền" chứ chưa có nghĩa "công việc đã thành công". Nếu cần phân biệt `NEW`, `RUNNING`, `SUCCEEDED` và `FAILED`, cờ boolean thường **không đủ biểu diễn trạng thái**; hãy dùng state machine, future hoặc enum/state atomic phù hợp.

### Ví dụ Java 17+: chỉ một thread claim quyền bắt đầu

Lưu thành `AtomicBooleanOnceDemo.java`:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicBooleanOnceDemo {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicBoolean claimed = new AtomicBoolean(false);
        AtomicInteger winners = new AtomicInteger();
        Thread[] candidates = new Thread[6];

        for (int i = 0; i < candidates.length; i++) {
            candidates[i] = new Thread(() -> {
                if (claimed.compareAndSet(false, true)) {
                    winners.incrementAndGet();
                }
            });
            candidates[i].start();
        }

        for (Thread candidate : candidates) {
            candidate.join();
        }

        System.out.println("Winners: " + winners.get());
        System.out.println("Claimed: " + claimed.get());
    }
}
```

```bash
javac AtomicBooleanOnceDemo.java
java AtomicBooleanOnceDemo
```

Stdout chính xác:

```text
Winners: 1
Claimed: true
```

Dù sáu thread chạy theo lịch nào, chỉ một CAS từ `false` sang `true` có thể thành công khi không có thread nào reset cờ. Vì mỗi winner tăng counter đúng một lần và main đợi hết các thread, kết quả là xác định.

**Đừng tự động áp dụng lại cách này để đảm bảo exactly-once side effect.** Ví dụ winner cập nhật `claimed = true` rồi gọi một external service. Nếu service lỗi, cờ vẫn true; những caller khác sẽ không thử nữa. Muốn "đã hoàn thành thành công đúng một lần" phải có **giao thức xử lý lỗi**, idempotency/retry và trạng thái biểu diễn completion, không chỉ cờ claim.

## 10. Cờ dừng và sự khác nhau giữa visibility với wake-up

Một dạng phổ biến:

```java
final class StopSignal {
    private final java.util.concurrent.atomic.AtomicBoolean
            stopped = new java.util.concurrent.atomic.AtomicBoolean();

    void requestStop() {
        stopped.set(true);
    }

    boolean shouldStop() {
        return stopped.get();
    }
}
```

Class minh họa này dùng `AtomicBoolean` để publish cờ. Khi worker chủ động kiểm tra `shouldStop()`, nó có thể quan sát cập nhật nhờ semantics volatile của `get()/set()`.

**Nhưng cờ không đánh thức thread đang block.** Nếu worker đang `BlockingQueue.take()`, `Thread.sleep(...)`, `CountDownLatch.await()` hoặc I/O, riêng `stopped.set(true)` không khiến thread rời lời gọi đó. Tùy API, cần thêm interruption, timeout, sentinel/poison-pill, close signal hoặc cơ chế đóng resource.

Không nên dùng vòng `while (!stopped.get()) { }` chạy mãi trên CPU chỉ để chờ event. Một vòng spin có thể phù hợp với đoạn cực ngắn trong một số thuật toán đặc biệt, nhưng với tác vụ ứng dụng thông thường nên dùng blocking coordination có chính sách hủy.

### Stop flag không thay `Thread.interrupt()`

`AtomicBoolean` và interruption phục vụ hai vai trò khác nhau:

- Flag mang **yêu cầu ở mức trạng thái ứng dụng** do người lập trình định nghĩa.
- `Thread.interrupt()` mang **yêu cầu ngắt** theo hợp đồng của thread/API blocking. Nó không cưỡng bức giết thread; có thao tác ném `InterruptedException`, có thao tác phản hồi khác hoặc không hỗ trợ interruption như kỳ vọng.

Nếu catch `InterruptedException` mà không thể xử lý tại chỗ, cách thông dụng là kết thúc tác vụ và/hoặc khôi phục flag bằng `Thread.currentThread().interrupt()`. Đừng nuốt exception rồi tiếp tục chờ vô hạn.

## 11. `getAndSet`: lấy giá trị cũ, reset hoặc claim

`getAndSet` thực hiện exchange atomic:

```java
AtomicInteger intervalCount = new AtomicInteger(17);

int previous = intervalCount.getAndSet(0); // 17
int current = intervalCount.get();         // 0
```

Đây là đoạn minh họa. Với nhiều writer tiếp tục cập nhật trong lúc reset, `getAndSet(0)` có một điểm exchange atomic. Nhưng nếu phải tính tổng qua **nhiều counter** cùng lúc, nhiều lần `getAndSet` trên các biến khác nhau **không tạo một snapshot toàn cục**.

Với `AtomicBoolean`:

```java
AtomicBoolean pending = new AtomicBoolean(true);
boolean wasPending = pending.getAndSet(false);
```

Caller nhận `true` nếu tại thời điểm exchange cờ là `true`. Các thread khác có thể đổi cờ sau đó. Nếu nghiệp vụ yêu cầu chỉ thread nào nhìn thấy `false` mới có quyền set true, `compareAndSet(false, true)` diễn đạt điều kiện rõ ràng hơn `getAndSet(true)`.

## 12. Các method nhận hàm: `updateAndGet` và `accumulateAndGet`

Một số cập nhật không đơn thuần cộng 1. API hỗ trợ cập nhật qua hàm:

```java
AtomicInteger level = new AtomicInteger(8);

int updated = level.updateAndGet(current ->
        Math.min(10, current + 1)); // 9

int previous = level.getAndAccumulate(4,
        (current, delta) -> Math.min(10, current + delta)); // 9

int now = level.get(); // 10
```

Đây là đoạn minh họa sau khi import `AtomicInteger`.

**Quy tắc cực quan trọng:** hàm được truyền vào `updateAndGet`, `getAndUpdate`, `accumulateAndGet` hoặc `getAndAccumulate` **có thể bị gọi lại nhiều lần** nếu CAS thất bại do tranh chấp. Do đó hàm nên **không có side effect**, xác định theo input, chạy nhanh và không block.

Sai:

```java
counter.updateAndGet(old -> {
    sendEmail();  // Side effect có thể xảy ra nhiều lần khi retry!
    return old + 1;
});
```

Đây là anti-pattern minh họa; `sendEmail()` giả định. Một callback gửi email, ghi file, increment counter bên ngoài hoặc gọi network không được đặt trong hàm update nếu có nguy cơ bị thực thi lại. Hãy tách side effect sang một giao thức riêng sau khi update thành công, đồng thời cân nhắc idempotency, thứ tự và lỗi.

Hàm cũng không nên tự đọc rồi sửa chính atomic variable theo cách làm việc retry khó hiểu; chỉ trả giá trị mới dựa trên tham số hiện tại và điều kiện được kiểm soát.

## 13. Ví dụ Java 17+: update function thuần và bounded value

Lưu thành `AtomicUpdateDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class AtomicUpdateDemo {
    public static void main(String[] args) {
        AtomicInteger level = new AtomicInteger(8);

        int updated = level.updateAndGet(
                current -> Math.min(10, current + 1));

        int previous = level.getAndAccumulate(4,
                (current, delta) -> Math.min(10, current + delta));

        AtomicLong bytes = new AtomicLong(100);
        long after = bytes.addAndGet(25L);

        System.out.println("Updated level: " + updated);
        System.out.println("Previous level: " + previous);
        System.out.println("Current level: " + level.get());
        System.out.println("Bytes: " + after);
    }
}
```

```bash
javac AtomicUpdateDemo.java
java AtomicUpdateDemo
```

Stdout chính xác:

```text
Updated level: 9
Previous level: 9
Current level: 10
Bytes: 125
```

Mỗi lambda chỉ tính giá trị từ đối số, không tạo side effect. Do đó việc JDK có thể thử lại hàm vì CAS thất bại không nhân đôi một external action.

Hạn chế: phép `Math.min(10, current + 1)` **không phải giải pháp xử lý overflow tổng quát** khi current có thể gần `Integer.MAX_VALUE`. Trong ví dụ, giá trị được quản lý thuộc vùng nhỏ (8 đến 10) nên an toàn. Nếu dùng cho input tùy ý, phải kiểm tra giới hạn trước khi cộng hoặc dùng phép kiểm tra/overflow-safe phù hợp.

## 14. Memory semantics: atomics cung cấp những gì theo JMM?

`AtomicInteger`, `AtomicLong` và `AtomicBoolean` không chỉ cung cấp arithmetic/CAS. Các operation như `get()` và `set()` có semantics bộ nhớ tương đương đọc/ghi **volatile** của biến giá trị; các cập nhật như `compareAndSet`, `getAndSet` và arithmetic atomic có những bảo đảm phù hợp với read-modify-write volatile.

Hiểu mẫu publication đơn giản:

```java
int payload; // Ordinary data, ví dụ trong một holder.
AtomicBoolean ready = new AtomicBoolean(false);

// Writer:
payload = 42;
ready.set(true);

// Reader:
if (ready.get()) {
    use(payload); // Đọc payload đã được công bố đúng giao thức.
}
```

Đây là đoạn minh họa logic, `payload` và `ready` là state dùng chung và `use` là phương thức giả định. Nếu **writer chỉ ghi payload trước `ready.set(true)`**, còn reader chỉ đọc payload **sau khi `ready.get()` đã quan sát true** từ publication đó, và không có writer khác sửa payload xung đột, thì quan hệ happens-before từ volatile write/read đảm bảo reader thấy payload phù hợp.

Điều này đến từ tính bắc cầu:

```text
writer: write payload = 42
                  |
                  v
           ready.set(true)       volatile write
                  |
             synchronizes-with
                  |
                  v
reader:     ready.get() == true  volatile read
                  |
                  v
             read payload
```

Không phải dữ liệu ordinary nào cũng tự trở nên safe nếu có một atomic variable ở gần đó. Nếu có **nhiều lượt publication**, reader giữ tham chiếu mutable lâu, hoặc các writer khác sửa payload, cần xác định giao thức chi tiết hơn. Với nhiều field cần quan sát đồng thời, cân nhắc immutable snapshot và công bố cả tham chiếu qua `AtomicReference` hoặc khóa.

### `lazySet` và các access mode nâng cao

`lazySet` có release semantics; nó có thể hữu ích trong giao thức one-way publication, nhưng **không hứa reader bất kỳ sẽ thấy trạng thái trong một thời hạn cụ thể**. Java 9+ còn có các thao tác plain, opaque, acquire, release và compare-and-exchange variants. Chúng phục vụ lập trình concurrency chuyên sâu.

Đừng dùng một access mode yếu hơn chỉ vì nghĩ "nhanh hơn" mà chưa phân tích đầy đủ JMM. Với ứng dụng thông thường, `get()`, `set()` và `compareAndSet()` rõ ràng, ít rủi ro hơn. `AtomicBoolean` không phải primitive chờ hay đánh thức; `get()` quan sát giá trị chứ không đợi một sự kiện xảy ra.

## 15. Overflow, khoảng giá trị và kiểu dữ liệu

### `AtomicInteger` và `AtomicLong` không tự báo overflow

`AtomicInteger.incrementAndGet()` thực hiện phép tăng trên kiểu `int`; khi vượt `Integer.MAX_VALUE`, kết quả wrap theo số nguyên 32-bit Java. `AtomicLong` có vấn đề tương tự sau `Long.MAX_VALUE`.

Nếu ID hoặc version **không được phép quay lại**, phải quản lý overflow:

- Kiểm tra hạn mức trước khi tăng trong một phép cập nhật atomic có điều kiện.
- Dùng `long` khi khoảng `int` không đủ, nhưng vẫn phải xác định vòng đời và ngưỡng.
- Không sử dụng counter JVM-local làm global unique ID nếu còn nhiều instance JVM hoặc restart.
- Nếu cần phép cộng overflow-safe, dùng kiểm tra phù hợp (như `Math.addExact` trong giao thức update rõ ràng) và xác định cách xử lý exception.

### Một `long` ordinary và một `AtomicLong` không giống nhau

Một field ordinary `long` không tự làm `value++` atomic; ngoài ra JMM còn phân biệt các bảo đảm cho non-volatile `long`/`double` ở mức đọc/ghi 64-bit. Trong thực tế trên nhiều JVM hiện đại, một số thao tác 64-bit thường không bị xé, nhưng **không được dựa vào chi tiết triển khai thay cho hợp đồng Java**. `AtomicLong` cung cấp atomic operations và memory semantics rõ ràng, dùng được giữa các nền tảng tuân thủ JMM.

**Kiểu lớn hơn không có nghĩa contention thấp hơn.** `AtomicLong` phù hợp vì khoảng giá trị cần thiết, không mặc nhiên nhanh hơn `AtomicInteger`.

## 16. ABA problem: CAS thành công không có nghĩa state chưa từng thay đổi

CAS chỉ so giá trị hiện tại với giá trị mong đợi. Giả sử:

```text
Thread A đọc state = A
Thread B đổi A -> B -> A
Thread A compareAndSet(A, C) thành công
```

Tại lúc CAS của A, giá trị đúng là A, nên CAS hợp lệ. Nhưng A có thể **nhầm rằng không có thay đổi nào** trong lúc nó xử lý. Đây là **ABA problem**.

Với counter chỉ tăng không reset trong khoảng không overflow, ABA thường ít đáng lo. Nhưng với state có thể quay lại giá trị cũ, ví dụ cờ false/true/false, ID tái sử dụng hoặc thuật toán lock-free trên cấu trúc dữ liệu, ABA có thể phá giả định nghiệp vụ.

Cách giảm rủi ro tùy bài toán:

- Dùng một **version/generation** tăng theo mỗi thay đổi quan trọng.
- Với tham chiếu object, xem `AtomicStampedReference` nếu cần so cả reference và stamp.
- Gói state và version vào một immutable object rồi cập nhật thông qua `AtomicReference` với CAS trên reference.
- Dùng monitor/lock nếu atomicity của nhiều field hoặc thuật toán lifecycle phức tạp hơn lợi ích của CAS.

**Một `AtomicBoolean` không biết lịch sử.** Nếu cờ từ `false` thành `true` rồi trở lại `false`, CAS kỳ vọng false vẫn có thể thành công — không có bất cứ cam kết "cờ chưa từng đổi" nào trong `compareAndSet`.

## 17. Thread safety của một biến khác với invariant nhiều biến

Giả sử cần bảo đảm `available + reserved == capacity`. Dù `available` và `reserved` đều là `AtomicInteger`, chuỗi:

```java
available.decrementAndGet();
reserved.incrementAndGet();
```

vẫn gồm **hai operation atomic riêng biệt**. Một reader nằm giữa hai bước có thể thấy tổng tạm thời khác `capacity`. Nếu invariant phải luôn đúng với các reader concurrent, cần giải pháp ở ranh giới transaction:

- Giữ **một monitor hoặc lock chung** quanh cả cập nhật và mọi điểm quan sát liên quan.
- Gói các field thành **một immutable state** rồi đổi toàn bộ reference bằng một CAS được thiết kế đúng.
- Chuyển mutable state cho **một owner** duy nhất và giao tiếp qua queue/message.
- Nếu yêu cầu chỉ là quan sát sau khi mọi worker kết thúc, dùng proper completion primitive rồi đọc kết quả tại điểm đó.

Tương tự, một `AtomicBoolean initialized` cộng với một mutable `List` cần giao thức safe publication. Cờ true không khiến các lần sửa list concurrent về sau trở thành an toàn.

Không nên kết luận **"class thread-safe" chỉ vì field đều có tiền tố Atomic**. Thread safety phụ thuộc invariant, alias, callbacks, collection values, tài nguyên bên ngoài và các operation được người dùng ghép lại.

## 18. `AtomicBoolean` và state machine: "đã claim" khác "đã hoàn thành"

Một service có thể muốn chỉ cho một thread làm một công việc, các thread khác chờ kết quả. Một cờ `AtomicBoolean busy` hỗ trợ claim:

```java
if (busy.compareAndSet(false, true)) {
    try {
        doWork();
    } finally {
        busy.set(false);
    }
}
```

Đây là **mẫu minh họa**, `busy` và `doWork` giả định. Một số rủi ro:

- Cờ reset về false cho phép thread khác chạy lại, nên đây là **exclusive-in-progress**, không phải once-ever.
- `doWork` ném exception rồi reset về false, có thể đã tạo **partial side effect**; retry phải có policy.
- Các thread không claim được chỉ bỏ qua công việc; nếu cần chờ, dùng `Semaphore`, `Lock`, queue hoặc future phù hợp.
- Nếu muốn caller khác nhận **cùng kết quả** của một lần tính toán, `CompletableFuture<T>` hoặc future được công bố an toàn thường diễn đạt completion tốt hơn cờ.
- Nếu doWork bị kẹt trong I/O, flag không tự tạo timeout/cancellation.

Nếu có trạng thái `NEW`, `RUNNING`, `SUCCEEDED`, `FAILED`, nên dùng state machine rõ và xác định transition hợp lệ. `AtomicInteger` có thể giữ enum ordinal hoặc mã trạng thái, nhưng phải quản lý mapping và kết quả; dùng enum qua `AtomicReference<State>` thường dễ đọc hơn khi phạm vi bài toán cần nhiều trạng thái.

## 19. `AtomicLong` so với `LongAdder`: khi nào ưu tiên throughput?

Một `AtomicLong` quản lý **một giá trị**; nhiều thread cập nhật một biến có thể tạo contention tại cùng một điểm. `LongAdder` phân tán hoạt động cập nhật nội bộ để cải thiện throughput trong một số workload có contention cao.

| Tiêu chí | `AtomicLong` | `LongAdder` |
| --- | --- | --- |
| Đọc một giá trị tại một operation | `get()` đọc giá trị atomic | `sum()` tổng hợp nhiều thành phần |
| Tăng 1 | `incrementAndGet()` hoặc `getAndIncrement()` | `increment()` |
| Cần lấy giá trị mới ngay sau lần tăng | Có, qua `incrementAndGet()` | Không cung cấp semantics tương ứng trên tổng toàn bộ adder |
| Snapshot khi writer vẫn cập nhật | `get()` là một atomic read | `sum()` không phải atomic snapshot toàn cục |
| Contention cao, chỉ đo thống kê | Có thể thành điểm tranh chấp | Thường là lựa chọn nên benchmark |

Nếu đang đếm "tổng request đã từng xử lý" chỉ để hiển thị thống kê xấp xỉ trong lúc cập nhật liên tục, `LongAdder` có thể phù hợp. Nếu cần CAS để thực thi hạn mức, ID hoặc chuyển trạng thái có điều kiện, **`AtomicLong`** diễn đạt contract chính xác hơn.

Đừng đổi `AtomicLong` sang `LongAdder` chỉ dựa trên benchmark mà bỏ qua khác biệt về **ngữ nghĩa đọc**.

## 20. CAS loop: retry, starvation và side effect

Mẫu thông dụng:

```java
while (true) {
    int oldValue = atomic.get();
    int newValue = transform(oldValue); // Hàm nên thuần.
    if (atomic.compareAndSet(oldValue, newValue)) {
        break;
    }
}
```

Đây là mẫu minh họa; `atomic` và `transform` chưa khai báo. CAS thất bại khi trạng thái đã đổi từ giá trị mong đợi, nên ta thử lại dựa trên giá trị mới.

Các hệ quả:

- Hàm `transform` có thể chạy nhiều lần, nên **không đặt I/O, callback hoặc external side effect** trong quá trình tính giá trị mới.
- Một thread có thể thua liên tục, đặc biệt nếu contention rất cao; **không có fairness tự động**.
- Retry là việc tiêu thụ CPU; nên benchmark trước khi kết luận CAS loop nhanh hơn `synchronized` trong workload thực tế.
- Với dữ liệu nhiều field, việc ghép state thành một atomic reference hoặc dùng lock có thể đơn giản, dễ review hơn.
- CAS failure không phải exception: caller phải kiểm tra giá trị `false` và thực hiện policy tương ứng (retry, bỏ cuộc hoặc báo lỗi).
- Nếu algorithm có ABA, phải thêm version hoặc thiết kế loại bỏ đường quay lại state cũ không hợp lệ.

`compareAndSet` bản strong không có semantics "được phép thất bại giả" như một số biến thể `weakCompareAndSet...`. Các biến thể weak CAS và các memory access mode yếu hơn phù hợp cho thuật toán nâng cao, không nên tự thay vào code thông thường nếu chưa chứng minh được tính đúng.

## 21. Có cần `synchronized` khi đã dùng Atomic?

**Có thể có.** Atomic variables loại bỏ nhu cầu khóa cho **một số operation đơn biến**, không cấm dùng khóa khi nghiệp vụ cần.

Chọn công cụ theo invariant:

| Bài toán | Công cụ thường phù hợp |
| --- | --- |
| Một bộ đếm nhiều writer tăng/giảm độc lập | `AtomicInteger` hoặc `AtomicLong` |
| Một flag duy nhất dùng để claim quyền | `AtomicBoolean.compareAndSet` |
| Giới hạn một counter chỉ tăng đến max | CAS loop trên `AtomicInteger` |
| Hạn chế nhiều task giữ permit và phải chờ/cancel | `Semaphore` hoặc queue bounded |
| Snapshot nhất quán của hai field thay đổi cùng nhau | `synchronized`/`Lock` hoặc một immutable state atomic reference |
| Điều phối completion giữa worker và caller | `Future`, `CountDownLatch`, `Thread.join()` |
| Map gồm nhiều entry concurrent | `ConcurrentHashMap` với operation atomic theo key, không phải một atomic field cho cả map |
| Counter thống kê contention cao | Cân nhắc `LongAdder` và semantics của `sum()` |

`synchronized` còn cung cấp **critical section**: thread giữ một monitor trong lúc kiểm tra và cập nhật invariant nhiều bước. Một `AtomicInteger` chỉ bảo vệ trường atomic đó, không khóa hoạt động trên collection hay field khác.

Thường nên **đơn giản hóa ownership và trạng thái** trước khi tìm cách thay mọi lock bằng CAS phức tạp.

## 22. Các lỗi phổ biến với ba loại Atomic

1. **"`volatile count++` đã atomic."** Sai; phải dùng operation atomic hoặc lock.
2. **"Dùng `AtomicInteger` thì mọi lời gọi `get` rồi `set` là atomic."** Sai; hai lời gọi có khoảng xen kẽ.
3. **"`compareAndSet` trả false nghĩa là JVM lỗi."** Sai; có thread khác cập nhật hoặc expected không khớp.
4. **"Atomic biến class thành thread-safe."** Sai nếu class còn invariant nhiều field, mutable collection hoặc callback không được bảo vệ.
5. **"`AtomicBoolean` true nghĩa công việc đã thành công."** Chỉ đúng nếu chính giao thức định nghĩa và công bố completion như vậy; CAS claim là bước khác completion.
6. **"Cờ dừng đánh thức thread đang block."** Sai; cần signaling/interruption/timeout/close phù hợp.
7. **"`AtomicLong` tạo ID duy nhất toàn hệ thống phân tán."** Sai; atomicity theo instance/JVM không cung cấp distributed uniqueness hoặc durability.
8. **"Atomic counters không overflow."** Sai; phép số học kiểu `int`/`long` wrap nếu vượt phạm vi.
9. **"Lambda của `updateAndGet` chỉ chạy đúng một lần."** Sai; có thể bị gọi lại do CAS retry.
10. **"CAS thành công chứng tỏ giá trị chưa từng thay đổi."** Sai với ABA khi state quay lại giá trị mong đợi.
11. **"`lazySet` là `set` giống hệt mọi mặt."** Không; access mode và ordering có điểm khác, cần đọc contract.
12. **"Đọc hai Atomic liên tiếp tạo snapshot nhất quán."** Sai; giữa hai lần đọc, các writer vẫn có thể tiến hành.
13. **"Atomic operation bảo đảm mọi thread có tiến độ công bằng."** Không; scheduling và retry có thể gây starvation.
14. **"Không cần kiểm tra kết quả `compareAndSet`."** Sai; nếu bỏ qua `false`, cập nhật dự định có thể chưa được thực hiện.
15. **"Dùng `getAndIncrement` là lấy giá trị sau tăng."** Sai; nó trả giá trị cũ. Dùng `incrementAndGet` để lấy giá trị mới.

## 23. Checklist thiết kế và code review

Trước khi chọn một trong ba atomic class, hãy trả lời:

1. **State có thật sự là một giá trị độc lập không?** Nếu invariant gồm nhiều field, đừng mặc định một atomic đủ.
2. **Ai đọc và ai ghi?** Có bao nhiêu writer, reader, và instance atomic có thực sự được chia sẻ đúng không?
3. **Operation cần atomic là gì?** Tăng một lần, check-and-update, exchange hay giao dịch nhiều bước?
4. **API nào trả giá trị cũ, API nào trả giá trị mới?** Đừng nhầm `getAnd...` với `...AndGet`.
5. **Memory publication được tạo bằng cách nào?** Có đường happens-before rõ ràng từ writer đến reader không?
6. **Có thể overflow/reset không?** Nếu giá trị dùng làm ID/version, xác định chính sách giới hạn.
7. **Có ABA không?** State có thể quay lại expected trước CAS không, và logic có cần nhớ lịch sử không?
8. **Hàm update có side effect không?** Mọi lambda gọi từ `updateAndGet`/`accumulateAndGet` nên chịu được retry.
9. **Cờ dừng có đủ đánh thức worker không?** Nếu worker block, cần interrupt/timeout/protocol riêng.
10. **Có cần giới hạn concurrency bằng permit hoặc queue không?** Nếu có, cân nhắc `Semaphore`/`BlockingQueue` thay vì counter tự chế.
11. **Có yếu tố performance đáng đo không?** Benchmark contention thực tế; đừng đổi code đúng, rõ ràng lấy tối ưu đoán mò.
12. **Completion và failure được truyền về thế nào?** Một flag claim không thay future hoặc state machine rõ ràng.

## 24. Câu hỏi tự kiểm tra

**1. Vì sao `AtomicInteger` xử lý lost update tốt hơn `volatile int` với `count++`?**

`AtomicInteger.incrementAndGet` là operation read-modify-write atomic. `volatile count++` chỉ bảo đảm semantics của lần đọc/ghi riêng, không ghép thành một operation.

**2. Hai thread gọi `AtomicBoolean.compareAndSet(false, true)`. Có thể cả hai trả `true` không nếu cờ ban đầu false và không ai reset?**

Không. Khi CAS đầu tiên thành công, trạng thái thành true; CAS kỳ vọng false còn lại sẽ thất bại. Nếu có thread reset true về false, một CAS tiếp theo có thể thành công lại.

**3. Gọi `AtomicLong.getAndIncrement()` từ 100 thread có đảm bảo ID unique trên nhiều JVM không?**

Không. Nó bảo đảm những operation atomic trên **cùng một instance**, không tự điều phối nhiều tiến trình, restart hay overflow.

**4. `getAndSet(0)` có tạo một snapshot atomic của nhiều `AtomicInteger` không?**

Không. Mỗi exchange chỉ atomic trên một biến riêng; không có transaction toàn cục giữa các biến.

**5. Với logic "chỉ tăng khi dưới max", vì sao `get() < max` rồi `incrementAndGet()` không đủ?**

Vì thread khác có thể tăng giữa hai lời gọi. Dùng CAS loop hoặc operation khác bao cả kiểm tra và thay đổi.

**6. Có nên gửi email trong lambda của `updateAndGet` không?**

Không. Lambda có thể bị chạy lại khi CAS tranh chấp, khiến email được gửi nhiều lần dù chỉ một update cuối cùng thành công.

**7. `AtomicBoolean stopped` có thay cho interrupt được không?**

Không. Cờ không tự đánh thức worker đang block; interruption có hợp đồng khác và một số operation đáp ứng bằng `InterruptedException`.

**8. CAS có thể bỏ sót việc state đã đổi A → B → A không?**

Có. Đây là ABA problem: CAS chỉ so giá trị hiện tại với expected, không ghi nhận lịch sử. Nếu lịch sử quan trọng, dùng version/stamp hoặc giao thức phù hợp.

**9. Khi nào `LongAdder` có thể tốt hơn `AtomicLong`?**

Khi workload chủ yếu là thống kê nhiều writer có contention cao, và chấp nhận `sum()` khi cập nhật concurrent không phải snapshot atomic. Nếu cần CAS/hạn mức chính xác tại một operation, dùng `AtomicLong`.

**10. Một class có hai `AtomicInteger` thì có tự bảo đảm tổng hai biến luôn bằng N không?**

Không. Hai operation trên hai atomic variable là độc lập. Muốn reader thấy invariant tổng thể, cần transaction dưới lock hoặc state được thay như một đơn vị.

## 25. Tổng kết

- **`AtomicInteger`**: counter hoặc trạng thái kiểu `int` với phép đọc, ghi, arithmetic và CAS atomic.
- **`AtomicLong`**: cùng mô hình với `long`, phù hợp counter và sequence trong một phạm vi sở hữu xác định; không bảo đảm global uniqueness/durability hay tránh overflow.
- **`AtomicBoolean`**: flag và chuyển trạng thái nhị phân bằng CAS; claim quyền không đồng nghĩa hoàn thành công việc.
- **`compareAndSet`**: atomic check-and-update; phải xử lý failure, retry có kiểm soát và hiểu ABA khi giá trị có thể quay lại.
- **Memory semantics** của atomic operations giúp xây publication đúng theo JMM; tuy nhiên không bảo vệ tự động mutable object, nhiều field hoặc workflow bao quanh.
- **Không đặt side effect vào update function** có thể retry; không dùng flag đơn làm giải pháp cho blocking coordination hoặc lifecycle phức tạp.
- **Atomic không thay thế mọi khóa**: khi invariant nhiều biến, yêu cầu chờ, transaction hoặc callback phức tạp, `synchronized`, `Lock`, `Semaphore` hay mô hình single-owner có thể dễ chứng minh đúng hơn.

Cách áp dụng hiệu quả nhất là bắt đầu từ câu hỏi **"phép toán logic nhỏ nhất nào phải atomic?"**. Nếu chỉ cần cập nhật một `int`, `long` hoặc `boolean`, ba atomic class là công cụ gọn và mạnh. Nếu tính đúng đắn trải qua nhiều biến hoặc nhiều giai đoạn, hãy thiết kế giao thức đồng bộ ở **cấp nghiệp vụ**, thay vì kỳ vọng một biến atomic giải quyết toàn bộ concurrency.