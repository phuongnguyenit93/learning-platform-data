# Mutual exclusion và memory visibility của monitor trong Java

> **Phạm vi:** hai bảo đảm nền tảng của cơ chế `synchronized` trong Java SE: **mutual exclusion** (loại trừ lẫn nhau khi thao tác trên state dùng chung) và **memory visibility/ordering** theo Java Memory Model. Nội dung tập trung vào Java nói chung, độc lập với các cơ chế concurrency dành riêng cho Spring.

## 1. Mục tiêu và ý tưởng cốt lõi

Một chương trình nhiều thread có thể sai theo **hai cách khác nhau** ngay cả khi mỗi thread đều chạy đúng những dòng mã được viết:

- **Race về thao tác:** nhiều thread xen kẽ bước đọc–tính–ghi hoặc cùng lúc thay đổi những trường phải nhất quán. Ví dụ hai phép `counter++` mất một lần tăng.
- **Thiếu quan hệ visibility/ordering:** một thread đã ghi giá trị nhưng thread khác không có cơ chế đồng bộ thích hợp để bảo đảm việc đọc thấy những ghi đó theo yêu cầu của chương trình.

Java cung cấp **intrinsic monitor** thông qua `synchronized` để giải quyết đồng thời hai vấn đề khi **tất cả truy cập liên quan tuân thủ cùng một giao thức khóa**:

1. **Mutual exclusion:** chỉ một thread được sở hữu một monitor tại một thời điểm; do đó các critical section dùng cùng monitor không chạy chồng lên nhau.
2. **Memory visibility/ordering:** một lần **unlock** monitor `m` *synchronizes-with* các lần **lock sau đó trên chính monitor `m`** theo quy tắc Java Memory Model (JMM). Quan hệ này tham gia xây dựng *happens-before*.

Sau bài học, bạn cần hiểu được lúc nào một phần mã thực sự được bảo vệ, tại sao một reader phải dùng đúng monitor, cách đọc quan hệ *happens-before*, khi nào `synchronized` còn chưa đủ để bảo toàn invariant, và cách kiểm chứng bằng ví dụ Java 17+.

**Kết luận thiết kế quan trọng:** không đủ nếu chỉ nói “writer có synchronized”. Cần biết **đối tượng monitor nào** được dùng, **những thao tác nào** nằm bên trong critical section, và **reader lấy cùng monitor lúc nào**.

## 2. Một monitor gắn với một object cụ thể

Trong Java, mỗi object có một **intrinsic lock / monitor**. Biểu thức `synchronized (guard) { ... }` cần giành quyền sở hữu monitor của đúng object mà `guard` tham chiếu.

Nếu một thread đã giữ monitor đó, thread khác muốn vào vùng `synchronized` dùng cùng monitor phải chờ. Nếu hai đoạn code dùng **hai object khác nhau**, chúng không loại trừ nhau chỉ vì cùng đặt tên biến là `guard`.

Ví dụ minh họa:

```java
final class SharedCounter {
    private final Object monitor = new Object();
    private int value;

    void increment() {
        synchronized (monitor) {
            value++;
        }
    }

    int value() {
        synchronized (monitor) {
            return value;
        }
    }
}
```

Đây là một **class có thể biên dịch** trong file `SharedCounter.java`. `monitor` là cùng một object được cả hai method sử dụng; nó là `private final` để ngăn caller trực tiếp nắm monitor và ngăn code bình thường đổi tham chiếu.

Với mỗi instance `SharedCounter`, mọi lần `increment()` sẽ đi lần lượt qua critical section. Khi `value()` lấy monitor sau khi một `increment()` đã nhả, nó nhận được các bảo đảm memory visibility tương ứng.

**Hai instance khác nhau có monitor riêng.** Nếu tạo hai `new SharedCounter()`, mỗi instance có một `new Object()` và hai counter không loại trừ nhau; điều này thường là điều mong muốn khi state của chúng độc lập.

### Các dạng synchronized và monitor tương ứng

| Cú pháp | Monitor được lấy | Hệ quả |
|---|---|---|
| `synchronized (guard) { ... }` | Object do `guard` trỏ tới khi đánh giá biểu thức | Những vùng dùng **cùng object** phối hợp với nhau. |
| `synchronized void update() { ... }` trên instance | `this` | Các synchronized instance method của cùng instance dùng cùng monitor. |
| `static synchronized void update() { ... }` | Object `Class` của class chứa method | Các static synchronized method cùng class dùng monitor của `Class`. |
| `synchronized (SomeType.class) { ... }` | Object `SomeType.class` | Có thể phối hợp với static synchronized của cùng class tương ứng. |

Không được nhầm `static synchronized` với việc khóa **mọi instance**: nó khóa Class object, còn các instance method synchronized khóa từng instance. Vì vậy một static synchronized method và một instance synchronized method **không nhất thiết chặn nhau**.

**Reentrancy:** một thread đã sở hữu monitor được phép vào lại chính monitor đó, chẳng hạn một instance synchronized method gọi instance synchronized method khác trên cùng `this`. Quy tắc “mỗi monitor một owner” vẫn đúng: đây là **một owner** vào nhiều mức, không phải hai thread cùng vào.

## 3. Mutual exclusion: vì sao nó ngăn lost update?

Giả sử có:

```java
counter++;
```

Đây là một **biểu thức minh họa**, với `counter` là trường `int` trong class chứa nó. Ở mức hành vi, phép tăng gồm đọc giá trị cũ, tính giá trị mới, rồi ghi về. Hai thread có thể xen kẽ:

| Bước | Thread A | Thread B | `counter` |
|---|---|---|---|
| 0 | — | — | 0 |
| 1 | Đọc 0 | — | 0 |
| 2 | — | Đọc 0 | 0 |
| 3 | Ghi 1 | — | 1 |
| 4 | — | Ghi 1 | 1 |

Kết quả cuối là **1**, dù cả hai đã thực hiện một phép tăng; đây là **lost update**. Bảng là một lịch minh họa đơn giản, không mô tả toàn bộ hành vi bộ nhớ mà JMM cho phép đối với chương trình có data race.

Đặt toàn bộ thao tác trong một critical section chung:

```java
synchronized (guard) {
    counter++;
}
```

Đây cũng là **mã minh họa**, giả sử `guard` và `counter` là các trường đã khai báo. Nếu cả A và B dùng **cùng instance `guard`**, A phải hoàn thành critical section rồi nhả monitor trước khi B giành được (hoặc ngược lại). Vì thế, lần tăng thứ hai sẽ đọc giá trị sau lần tăng thứ nhất, không có lịch hai thread cùng đọc 0 rồi cùng ghi 1 **trong vùng được cùng khóa bảo vệ**.

Hai phần của bài toán “tăng số đếm” phải được chứng minh riêng:

- **Atomicity ở cấp thao tác:** đọc–tính–ghi nằm chung một critical section, không có writer khác cùng dùng monitor chen vào giữa.
- **Visibility khi quan sát:** reader dùng cùng monitor, hoặc có một quan hệ *happens-before* khác phù hợp; nếu reader truy cập trực tiếp bên ngoài synchronization thì không được suy ra bảo đảm ấy từ monitor của writer.

Một khóa chỉ loại trừ code **có dùng khóa đó**. `synchronized` không chặn một thread cố tình ghi trường trực tiếp từ code hoàn toàn không lấy monitor.

## 4. Memory visibility theo Java Memory Model

### Quy tắc release/acquire của monitor

Theo **JLS `17.4.4**, một hành động **unlock** trên monitor `m` *synchronizes-with* mọi hành động **lock tiếp theo trên cùng monitor `m`** trong synchronization order.

Cần đọc chính xác:

- **Cùng monitor:** phải đúng một object monitor, không phải hai object “tương đương” theo `equals()`.
- **Unlock và lock:** là hai synchronization actions, có ý nghĩa vượt ngoài việc scheduler cho phép thread chạy.
- **Tiếp theo trong synchronization order:** không có bảo đảm thread nào được lock trước theo thứ tự đến. Khi một lần lock thực sự nằm sau unlock tương ứng, ta có cạnh memory ordering được JMM quy định.

### Từ synchronizes-with đến happens-before

JMM định nghĩa quan hệ **happens-before (HB)** từ thứ tự chương trình (*program order*) và các cạnh *synchronizes-with*, có tính bắc cầu. Giả sử:

```text
Thread A                                Thread B
------------------------------          ----------------------------
synchronized (m) {                      synchronized (m) {
    data = 42;                              int observed = data;
} // unlock(m)                          } // unlock(m)

A: ghi data=42
    --program order--> A: unlock(m)
    --synchronizes-with--> B: lock(m) sau unlock của A
    --program order--> B: đọc data

Vậy ghi của A happens-before đọc của B.
```

Sơ đồ này **chỉ xét tình huống B lấy monitor sau A đã unlock**. Nếu B vào vùng synchronized trước A, B có thể thấy giá trị cũ. Một thread tạo ra sớm, gọi `start()` sớm hoặc bắt đầu chờ khóa sớm **không chứng minh** nó giành monitor trước.

HB cung cấp quy tắc về những ghi mà hành động đọc được phép quan sát. Nếu A ghi 42, B lock sau unlock của A và **không có một cập nhật hợp lệ khác đối với `data` xen giữa**, B không thể viện cớ “cache chưa kịp đồng bộ” để thấy giá trị cũ theo cách vi phạm HB.

**Không cần mô hình “unlock flush toàn bộ cache vật lý, lock reload toàn bộ RAM”.** Đó không phải hợp đồng của ngôn ngữ. JVM/JIT/CPU có nhiều cách triển khai barriers và tối ưu, miễn giữ các ràng buộc quan sát do JMM quy định.

### Hai tình huống cần phân biệt

**1. Dùng đúng monitor:**

```java
// Các field của một class:
private final Object guard = new Object();
private int result;

void writeResult(int value) {
    synchronized (guard) {
        result = value;
    }
}

int readResult() {
    synchronized (guard) {
        return result;
    }
}
```

Đây là các **thành viên của cùng một class**, không phải chương trình độc lập. Nếu `readResult` giành monitor sau khi `writeResult` đã nhả, giá trị ghi trước unlock đã được công bố cho reader theo HB (trừ khi có writer khác cập nhật hợp lệ trước lần đọc đó).

**2. Dùng khác monitor:**

```java
// Mã minh họa thiếu cùng giao thức đồng bộ:
private final Object writerGuard = new Object();
private final Object readerGuard = new Object();
private int result;

void writeResult(int value) {
    synchronized (writerGuard) {
        result = value;
    }
}

int readResult() {
    synchronized (readerGuard) {
        return result;
    }
}
```

Writer unlock `writerGuard`, còn reader lock `readerGuard`. Hai hành động đó **không** tạo cạnh *synchronizes-with* theo **quy tắc monitor cùng object**. Không có mutual exclusion giữa hai khối; chương trình còn có thể có data race nếu không tồn tại HB từ nguồn khác. Sửa bằng cách dùng **cùng monitor** cho mọi truy cập cần bảo vệ, hoặc đổi sang primitive có hợp đồng synchronization phù hợp.

## 5. Visibility không đồng nghĩa với một kết quả hay thứ tự cố định

Một ví dụ hay bị hiểu sai:

- A định ghi `data = 42` dưới monitor `m`.
- B định đọc `data` dưới cùng monitor `m`.
- Hai thread được khởi chạy gần nhau.

Cả hai đều dùng đúng monitor. Nhưng B có thể giành monitor **trước** khi A ghi; khi ấy B đọc giá trị ban đầu là hợp lệ. `synchronized` chỉ đảm bảo rằng các critical section **không chồng lên nhau**, và bảo đảm visibility cho lần lock xảy ra **sau** unlock của writer.

Nếu yêu cầu nghiệp vụ là **B phải đợi A công bố dữ liệu**, cần thêm protocol để phối hợp giai đoạn:

- Predicate `ready` được ghi/đọc dưới cùng monitor, kết hợp `wait()/notifyAll()`.
- Hoặc dùng `BlockingQueue`, `CountDownLatch`, `Future.get()` nếu API tương ứng khớp mục tiêu.

Không dùng `Thread.sleep(50)` như bằng chứng A đã xong: ngủ một khoảng thời gian **không tạo mối quan hệ HB cần thiết** và không bảo đảm thứ tự giữa các thread.

### Monitor bảo vệ tính nhất quán của nhiều trường

Giả sử ledger giữ invariant:

\[
\text{total} = 10 \times \text{updates}
\]

Nếu writer làm `total += 10` rồi `updates++` bên trong cùng monitor, một reader cũng lấy đúng monitor để đọc **cả hai trường** sẽ quan sát snapshot trước hoặc sau **một lần cập nhật nguyên vẹn**, không quan sát trạng thái giữa hai bước.

Nếu reader gọi hai getter synchronized **riêng biệt**, nó có thể thấy `total` từ một lần cập nhật và `updates` từ lần sau, vì khóa được nhả ở giữa hai lời gọi. Để bảo đảm nhất quán đa trường, reader cần **một critical section bao quanh toàn bộ snapshot**, hoặc lấy một immutable snapshot được xây dựng bên trong khóa.

Một chi tiết quan trọng: hai trường không nhất thiết phải là `volatile` khi **mọi đường đọc/ghi cần thiết đều tuân theo cùng monitor**. Các unlock/lock thiết lập visibility và critical section thiết lập atomicity. Thêm volatile từng trường không biến hai lần đọc riêng lẻ thành một snapshot nhất quán.

## 6. Thực hành Java 17+: cập nhật atomic và snapshot nhìn thấy đúng

Chương trình sau có hai writer cùng cập nhật `total` và `updates`. Một reader chạy song song, lấy snapshot nhiều lần và kiểm tra invariant. Cả ba cùng sử dụng một instance `Ledger`.

Tạo file **`MonitorSafetyLab.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class MonitorSafetyLab {
    record Snapshot(long total, long updates) {
        boolean valid() { return total == updates * 10L; }
    }

    static final class Ledger {
        private final Object guard = new Object();
        private long total;
        private long updates;

        void addTen() {
            synchronized (guard) {
                total += 10;
                updates++;
            }
        }

        Snapshot snapshot() {
            synchronized (guard) {
                return new Snapshot(total, updates);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Ledger ledger = new Ledger();
        ExecutorService executor = Executors.newFixedThreadPool(3);
        try {
            Future<?> first = executor.submit(() -> {
                for (int i = 0; i < 10_000; i++) ledger.addTen();
            });
            Future<?> second = executor.submit(() -> {
                for (int i = 0; i < 10_000; i++) ledger.addTen();
            });
            Future<Boolean> reader = executor.submit(() -> {
                for (int i = 0; i < 20_000; i++) {
                    if (!ledger.snapshot().valid()) return false;
                }
                return true;
            });

            first.get();
            second.get();
            boolean readConsistent = reader.get();
            Snapshot end = ledger.snapshot();

            System.out.println("readSnapshotsConsistent=" + readConsistent);
            System.out.println("finalTotal=" + end.total());
            System.out.println("finalUpdates=" + end.updates());
            System.out.println("finalInvariant=" + end.valid());
        } finally {
            executor.shutdown();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 MonitorSafetyLab.java
java MonitorSafetyLab
```

**Stdout đã xác minh:**

```text
readSnapshotsConsistent=true
finalTotal=200000
finalUpdates=20000
finalInvariant=true
```

### Phân tích cơ chế, không dựa vào “chạy may mắn”

1. Mỗi lời gọi `addTen()` lấy monitor `guard` của **cùng Ledger** và cập nhật cả `total` lẫn `updates` trước khi nhả.
2. Một writer khác không thể vào `addTen()` dùng cùng `guard` khi writer đầu còn trong critical section. Do đó có đúng 20.000 phép tăng hợp lệ, mỗi lần đóng góp 10.
3. `snapshot()` cũng phải giành đúng `guard`. Khi nó trả về, record `Snapshot` chứa hai giá trị được đọc **trong một critical section**; không có writer nào xen giữa hai lần đọc.
4. `record Snapshot` là dữ liệu chỉ chứa hai `long`; các component final và value object này không có đường thay đổi nội dung. Trả record ra khỏi lock không làm snapshot trở thành mutable.
5. `Future.get()` là điểm main đợi các task hoàn tất, có memory-consistency guarantees của executor/Future. Khi main đọc snapshot cuối, cả hai writer đã xong; vì thế tổng bằng `20_000 × 10 = 200_000`. **`Future.get()` giúp hoàn tất/visibility ở phía main nhưng không làm các update giữa hai writer tự atomic**; trách nhiệm đó thuộc về monitor.
6. Reader có thể lấy 20.000 snapshot **trước, trong hoặc sau** phần lớn hoạt động writer. Vì mọi snapshot được tạo dưới khóa chung, biểu thức invariant luôn đúng, dù lịch thread thay đổi.

Đối với một chương trình benchmark, ví dụ này không đo overhead; nó kiểm tra **correctness**. Từ kết quả đúng trên một lần chạy không thể kết luận “mã không có race” nói chung, nhưng ở đây quy tắc khóa có thể chứng minh invariant cho mọi interleaving hợp lệ.

**Giới hạn của ví dụ:** phép tính `updates * 10L` có thể overflow trong bài toán tổng quát; số vòng của chương trình hiện tại nhỏ và không có nguy cơ overflow. Nếu dùng ledger thực tế, cần mô hình số tiền, kiểm tra overflow và trạng thái transaction phù hợp. `shutdown()` dừng nhận task mới; ở đây `Future.get()` đã đợi toàn bộ task đã submit. Trong ứng dụng dài hạn, cần quy trình graceful termination và xử lý `InterruptedException`/`ExecutionException` theo contract.

## 7. Phân biệt “đọc từng field an toàn” và “snapshot nhất quán”

Ví dụ cấu trúc sau *không* bảo đảm snapshot đa trường:

```java
// Các method của một class giả định chứa guard, total và updates:
long getTotal() {
    synchronized (guard) {
        return total;
    }
}

long getUpdates() {
    synchronized (guard) {
        return updates;
    }
}

// Thread reader:
long a = getTotal();
long b = getUpdates();
```

Đây là **đoạn code minh họa**, chưa phải class độc lập. Giữa hai lần gọi getter, reader đã nhả monitor. Writer có thể cập nhật cả hai trường và nhả monitor trước khi reader gọi getter thứ hai; kết quả `a` và `b` không phải từ cùng thời điểm logic.

Khắc phục:

```java
// Method của class có guard, total và updates:
Snapshot snapshot() {
    synchronized (guard) {
        return new Snapshot(total, updates);
    }
}
```

Đây là đoạn minh họa cùng kiểu `record Snapshot(long total, long updates)` trong ví dụ trên. Snapshot là một *đơn vị logic* của thao tác đọc, nên cần tạo dưới một lần giành monitor.

Tương tự, nếu yêu cầu nghiệp vụ là “kiểm tra đủ tài nguyên rồi trừ”, hãy gộp **check + update** vào một critical section:

```java
// Method của class có trường int available và monitor guard:
boolean reserveOne() {
    synchronized (guard) {
        if (available == 0) return false;
        available--;
        return true;
    }
}
```

Hai method `hasStock()` và `decrement()`, dù mỗi method riêng có synchronized, cũng có thể để một thread khác chen vào khoảng giữa. Mutual exclusion phải bảo vệ **toàn bộ transaction logic** mà bạn muốn là atomic.

## 8. Khi nào synchronized được nhả?

### Khi rời synchronized block/method

Java tự giải phóng mức sở hữu monitor tương ứng khi control flow rời `synchronized`, kể cả khi có `return` hoặc exception. Một instance synchronized method dùng monitor của `this`; static synchronized method dùng object `Class`.

```java
int compute() {
    synchronized (guard) {
        if (inputInvalid()) return -1;
        return calculate();
    } // monitor được nhả kể cả khi return hoặc exception
}
```

Đây là **method minh họa**; `guard`, `inputInvalid()` và `calculate()` được định nghĩa bên ngoài đoạn code. Việc nhả monitor **không** tự hoàn tác những cập nhật dữ liệu đã xảy ra trước khi exception được ném. Nếu invariant có thể bị dở dang khi exception, cần exception-safe update hoặc chiến lược rollback.

### Reentrancy

Một thread đã giữ monitor vẫn có thể vào lại monitor đó, ví dụ một method `synchronized` gọi method `synchronized` khác trên cùng instance. JVM duy trì số lần sở hữu tương ứng; monitor chỉ khả dụng cho thread khác khi đã nhả hết các mức.

### Thread khác đang tranh monitor

Thread chưa lấy được monitor ở lối vào `synchronized` có thể ở trạng thái `Thread.State.BLOCKED`. Khi owner nhả monitor, contender có cơ hội lấy; JVM không bảo đảm contender nào thắng theo FIFO hay một thời hạn cụ thể. `Thread.interrupt()` không làm một lời gọi đang chờ *monitor entry* tự ném `InterruptedException`.

**Không nhầm với `ReentrantLock`:** explicit lock thuộc `java.util.concurrent.locks` có những cơ chế chờ và API khác (`lockInterruptibly`, `tryLock`). `Thread.State.BLOCKED` dành cho monitor, không bao quát mọi hoạt động chờ khóa.

## 9. Object.wait/notify: visibility gắn với việc chờ điều kiện

Khi thread muốn **đợi một điều kiện thay đổi**, chỉ lấy monitor rồi quay vòng kiểm tra điều kiện sẽ lãng phí CPU và có thể giữ monitor quá lâu. Java cung cấp `Object.wait()`/`notify()`/`notifyAll()` cho giao thức condition wait trên intrinsic monitor.

Mẫu minh họa đúng:

```java
private final Object guard = new Object();
private boolean ready;
private String value;

void publish(String text) {
    synchronized (guard) {
        value = text;
        ready = true;
        guard.notifyAll();
    }
}

String await() throws InterruptedException {
    synchronized (guard) {
        while (!ready) {
            guard.wait();
        }
        return value;
    }
}
```

Đây là **các thành viên của một class**, không phải tệp Java độc lập. Đặt cả predicate `ready`, dữ liệu `value`, thao tác `wait` và thông báo dưới **cùng monitor**.

Cơ chế:

1. Consumer phải sở hữu monitor `guard` trước khi gọi `guard.wait()`; nếu gọi ngoài vùng sở hữu monitor, JVM ném `IllegalMonitorStateException`.
2. `wait()` đưa thread vào wait set và **nhả monitor `guard`**, để producer có thể vào vùng `synchronized(guard)`.
3. Producer ghi dữ liệu, đổi predicate rồi gọi `notifyAll()` khi còn giữ monitor. **`notifyAll()` không tự giải phóng monitor**: producer chỉ nhả khi rời synchronized.
4. Consumer được thức dậy phải **lấy lại monitor** trước khi `wait()` trả về. Lúc đó các cập nhật của producer đã được công bố qua quy tắc unlock→subsequent lock.
5. Consumer kiểm tra lại `ready` bằng vòng `while` vì có thể có **spurious wakeup**, hoặc một waiter khác đã tiêu thụ/đổi điều kiện trong lúc nó chờ giành lại monitor.
6. Nếu producer đã publish trước khi consumer vào `wait`, consumer thấy `ready == true` dưới khóa và **không cần wait**; predicate ngăn lost notification.

`Object.wait()` **chỉ nhả monitor của object được gọi**. Nếu thread đang giữ thêm monitor khác thì `wait` không tự nhả monitor đó. `Thread.sleep()` hoàn toàn **không nhả monitor đang giữ**; dùng sleep để đợi điều kiện là một thiết kế khác và không cung cấp quy tắc notify/reacquire.

### Tại sao notify không phải ranh giới “reader chạy ngay”?

Bởi vì producer vẫn giữ monitor từ lúc `notifyAll()` cho đến khi thoát critical section. Thread vừa được thông báo có thể phải đợi ở `BLOCKED` trong khi cố lấy lại monitor; nó không thể đi tiếp vào critical section trước thời điểm đó. Trường hợp nhiều consumer được notifyAll, từng consumer sẽ tranh monitor theo lịch không xác định.

Trong ứng dụng thông thường, `BlockingQueue`/`CountDownLatch`/`Condition` có thể đơn giản hơn việc tự viết `wait/notify`, nhưng nguyên lý monitor ownership và visibility vẫn là nền tảng giúp hiểu cơ chế.

## 10. Khi nào memory visibility không được bảo đảm bởi monitor?

### Reader không cùng monitor

```java
// Mô tả một class chứa trường int value và Object guard:
void update(int number) {
    synchronized (guard) {
        value = number;
    }
}

int unguardedRead() {
    return value; // không acquire cùng monitor
}
```

Đây là mã minh họa. Lần đọc không khóa không có cạnh HB từ unlock của writer **chỉ nhờ monitor rule**. Có thể tồn tại HB từ cơ chế khác trong một tình huống gọi cụ thể, nhưng bản thân API này không thể tuyên bố thread-safe chỉ vì writer có synchronized.

### Dùng hai object monitor khác nhau

`synchronized (new Object())` bên trong từng lần gọi tạo monitor mới, nên các lần gọi không loại trừ nhau. Hai object khác nhau dù `equals` trả true vẫn có monitor độc lập. Đừng dùng cùng tên biến hoặc cùng chuỗi ký tự như bằng chứng identity.

### Khóa một bước, bỏ khóa bước khác

Nếu phép cập nhật gồm “đọc bản ghi, kiểm tra điều kiện, ghi bản ghi”, chỉ khóa bước ghi có thể vẫn sai vì giá trị kiểm tra đã cũ. Cần critical section bao phủ toàn bộ **invariant transaction** hoặc primitive atomic ở mức logic.

### Khóa cấp instance nhưng state cấp static

Một instance synchronized method trên object A không loại trừ instance synchronized method trên object B. Nếu cả hai cùng ghi một trường `static`, việc `synchronized` trên từng instance **không** tạo mutual exclusion chung. Cần khóa được chia sẻ bởi tất cả writer/reader của state static, hoặc thiết kế lại ownership.

### Có published reference nhưng mutable state tiếp tục đổi

Safe publication của object không đồng nghĩa mọi lần mutation về sau đều thread-safe. Nếu một thread đăng reference vào shared map qua queue rồi tiếp tục thay đổi fields không có synchronization, thread khác có thể gặp data race khi đọc.

## 11. Volatile, atomic và synchronized giải quyết các yêu cầu khác nhau

| Yêu cầu | `synchronized` với cùng monitor | `volatile` | `AtomicInteger` |
|---|---|---|---|
| Visibility/ordering các truy cập phối hợp đúng | Có: unlock→lock, HB | Có: volatile write→read và quy tắc JMM liên quan | Có memory semantics được API quy định |
| Atomic read-modify-write `x++` | **Có** nếu toàn bộ thao tác trong cùng critical section | **Không**, dù `x` là volatile | **Có** với `incrementAndGet()` |
| Bảo vệ invariant gồm nhiều trường | **Có** nếu đọc/ghi cả nhóm dưới một monitor | Không tự bảo vệ group transaction | Không tự bảo vệ nhóm nhiều atomic variables |
| Reader phải dùng protocol nhất quán | Có | Có: đọc đúng volatile và giao thức publish | Có: dùng atomic operation/snapshot phù hợp |
| Thread có thể phải đợi lock | Có | Không để chỉ đọc/ghi volatile | Có thể có contention/retry ở atomic |

Đừng coi `volatile` là “synchronized nhẹ”. Hai cơ chế có API, atomicity và memory semantics khác nhau. Một bộ đếm độc lập có thể phù hợp với `AtomicInteger`; các trường có invariant như `total` và `updates` trong ví dụ phù hợp với monitor bảo vệ toàn bộ snapshot.

**Đặc biệt:** `volatile long` có bảo đảm atomicity cho access đơn lẻ, nhưng hai phép volatile access không trở thành một transaction. Tương tự, `final` trên một object reference không làm object mutable được tham chiếu tự an toàn.

Một công cụ `ReentrantLock` theo API `Lock` cung cấp memory effects của acquire/release tương tự monitor lock/unlock, đồng thời thêm khả năng như timed/interruptible acquisition. Khi chuyển đổi từ `synchronized` sang `Lock`, phải bảo đảm mọi đường truy cập dùng **đúng cùng lock và try/finally**; nó không phải một tối ưu hiệu năng mặc nhiên.

## 12. Những điểm tinh tế của monitor visibility

### Không phải mọi quan hệ HB đều yêu cầu monitor

JMM cũng quy định các cạnh khác:

- Actions trước `Thread.start()` HB actions trong thread mới.
- Hành động của thread kết thúc HB việc thread khác xác nhận nó kết thúc bằng `join()` thành công.
- Volatile write *synchronizes-with* volatile read phù hợp theo synchronization order.
- `Future.get()`, `BlockingQueue`, các đồng bộ trong `java.util.concurrent` có memory-consistency guarantees riêng.

Do đó không nên kết luận “reader không lock thì chắc chắn đọc sai” nếu có một HB path khác bảo đảm điều đó. Cần đánh giá **giao thức hoàn chỉnh**. Nhưng một class dùng monitor để quản lý state thường nên duy trì chính sách mọi truy cập thông thường qua monitor đó, tránh ngầm dựa vào một caller cụ thể đã `join()`.

### Happens-before không có nghĩa có một lịch CPU cố định

HB là quan hệ trên **memory actions** và các quy tắc quan sát, không phải cam kết thread A được xếp lịch ngay trước thread B. Một reader có thể chờ monitor lâu, hoặc vào sớm trước writer. Sự đúng đắn thường phải chứng minh cho **mọi lịch được phép**, không dựa vào kết quả thường thấy trên một máy.

### Visibility và atomicity là hai điều độc lập

Lấy đúng monitor cho phép reader thấy dữ liệu đã công bố và không đọc giữa critical section của writer. Nhưng nếu writer **không gộp** toàn bộ cập nhật invariant trong cùng một critical section, reader vẫn có thể đọc một trạng thái giữa hai vùng synchronized khác nhau; tất cả các đọc vẫn hợp lệ theo HB, nhưng invariant nghiệp vụ đã không được bảo vệ.

Ví dụ sai:

```java
// Giả sử total, updates, guard là các trường của class:
void addTenWrong() {
    synchronized (guard) {
        total += 10;
    }
    synchronized (guard) {
        updates++;
    }
}
```

Đây là method minh họa, không phải chương trình độc lập. Reader gọi `snapshot()` giữa hai khối có thể nhận `total` mới nhưng `updates` cũ. Sửa bằng **một vùng synchronized bao quanh cả hai cập nhật**.

### Lock granularity và hiệu năng

Khóa hẹp giúp nhiều thread xử lý những state độc lập song song; khóa quá rộng làm tăng contention. Nhưng tách một monitor bảo vệ invariant thành hai monitor mà không thiết kế lại protocol có thể phá tính đúng đắn. **Ưu tiên chứng minh invariant trước khi giảm contention**; profiling thực tế mới cho thấy chi phí monitor có đáng tối ưu không.

## 13. Thread state và công cụ chẩn đoán

Khi chương trình có latency cao hoặc nghi data race:

1. **Xác định monitor identity:** code có sử dụng cùng object khóa cho writer và reader không?
2. **Lập bản đồ tất cả đường đọc/ghi:** có getter không synchronized, callback hoặc truy cập trực tiếp từ thread khác không?
3. **Xác định invariant cần nguyên tử:** check-then-act hay snapshot hai trường có bị chia thành nhiều critical section không?
4. **Tìm HB path:** unlock trên monitor nào, reader lock monitor nào và vào sau unlock không? Có HB edges từ `join`, `Future.get`, volatile hoặc queue không?
5. **Quan sát contention:** nếu nhiều thread ở `BLOCKED` trên monitor, tìm owner và code giữ lock quá lâu.
6. **Thử nghiệm correctness:** tạo tải nhiều writer/reader, kiểm tra invariant; dùng `CountDownLatch`/barrier để phối hợp checkpoint thay vì `sleep` làm “bảo đảm”.

Công cụ hữu ích cho Java 17+:

```bash
jcmd <PID> Thread.print -l
```

Thread dump có thể cho thấy `BLOCKED (on object monitor)` và monitor đang bị tranh, nhưng chỉ là ảnh chụp thời điểm. Một thread `WAITING (on object monitor)` tại `Object.wait()` đang đợi điều kiện; không đồng nghĩa nó vẫn giữ monitor mà nó wait. Thread `WAITING (parking)` có thể đang đợi primitive khác, như explicit lock.

JFR có thể giúp thu thập các sự kiện contention/wait trong khoảng thời gian:

```bash
jcmd <PID> JFR.start name=monitors settings=profile duration=60s filename=monitors.jfr
jfr summary monitors.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait monitors.jfr
```

Các lệnh trên áp dụng khi JDK/JVM hỗ trợ JFR và process tồn tại đủ lâu. Event có thể không được bật hoặc bị lọc theo threshold, vì thế **không thấy event không chứng minh không có contention**. Dùng workload thực tế, stack trace, số liệu blocked time và p95/p99 để hiểu tác động.

**ThreadMXBean:** `java.lang.management.ThreadMXBean` có API đọc blocked count/time với monitor contention khi JVM hỗ trợ và monitoring được bật. Nó không phải thước đo cho mọi kiểu chờ khóa, context switch của OS hoặc đúng/sai của Java Memory Model. Dữ liệu quan sát chỉ giúp tìm vị trí; correctness vẫn cần dựa vào contract của mã nguồn.

## 14. Lỗi phổ biến và cách sửa

1. **“Synchronized chỉ ngăn hai thread vào cùng lúc.”** Thiếu một nửa: monitor unlock→lock còn tạo memory ordering/visibility qua HB.
2. **“Writer khóa rồi thì reader có thể đọc biến thường trực tiếp.”** Không có bảo đảm đó từ monitor rule. Reader phải theo protocol hoặc có HB path khác phù hợp.
3. **“Hai object khác nhau nhưng `equals()` bằng nhau là cùng lock.”** Sai: monitor dựa trên object identity.
4. **“`synchronized(new Object())` ở mỗi lần gọi bảo vệ shared field.”** Sai: mỗi lần dùng monitor mới, không có mutual exclusion xuyên lời gọi.
5. **“Hai synchronized getters liên tiếp là một snapshot nguyên tử.”** Sai: monitor được nhả giữa các lời gọi, writer có thể chen vào.
6. **“`static synchronized` khóa cùng monitor với instance synchronized.”** Sai: Class object khác monitor `this`.
7. **“`count++` dưới volatile là atomic.”** Sai: volatile không gộp read-modify-write thành một action nguyên tử.
8. **“Đã synchronized thì thread đầu tiên gọi method sẽ luôn vào trước.”** Sai: `synchronized` không bảo đảm FIFO/fairness.
9. **“`notifyAll()` nhả monitor ngay.”** Sai: chỉ thông báo; caller vẫn giữ monitor đến khi rời critical section.
10. **“`wait()` nhả tất cả các monitor đang giữ.”** Sai: nó chỉ nhả monitor của chính object nhận `wait()`.
11. **“`sleep()` hoặc `yield()` giúp các ghi được thread khác thấy an toàn.”** Không phải synchronization protocol cho shared state.
12. **“Có HB nên không bao giờ deadlock.”** HB không tự ngăn lock-order deadlock. A giữ khóa X chờ Y, B giữ Y chờ X vẫn có thể không tiến triển.
13. **“Exception làm JVM quên nhả intrinsic monitor.”** Java nhả khi scope synchronized kết thúc đột ngột; tuy nhiên state đã mutate không tự rollback.
14. **“Muốn nhanh chỉ cần xóa synchronized.”** Thay đổi phải giữ tính đúng đắn; giảm thời gian critical section hoặc partition invariant an toàn trước khi quyết định bỏ monitor.
15. **“Thấy kết quả đúng một triệu lần tức không còn race.”** Test là bằng chứng trên các lịch đã chạy; phân tích ownership, HB và invariant mới giải thích tính đúng đắn cho mọi lịch hợp lệ.

## 15. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** A ghi `x=7` rồi unlock monitor `m`; B sau đó lock cùng `m` và đọc `x`, không có writer khác. B có thể đọc giá trị cũ vì `x` không volatile không?  
**Đáp án:** Không, với điều kiện unlock của A đứng trước lock của B trong synchronization order, ghi của A HB lần đọc của B; đây là bảo đảm memory visibility.

**Câu 2.** A dùng `synchronized(left)`, B dùng `synchronized(right)` trên hai object khác nhau, cả hai đọc/ghi cùng `x`. Có mutual exclusion và HB qua monitor rule không?  
**Đáp án:** Không. Hai monitor độc lập; cần cùng monitor hoặc cơ chế đồng bộ khác tạo HB hợp lệ.

**Câu 3.** Hai writer mỗi thread thực hiện 10.000 lần `count++` trong cùng monitor; main gọi `join` cả hai rồi đọc `count` dưới monitor. Kết quả là bao nhiêu nếu ban đầu 0?  
**Đáp án:** 20.000. Monitor bảo vệ từng lần tăng; join bảo đảm hai writer hoàn tất trước khi đọc.

**Câu 4.** Một thread gọi synchronized instance method trên `a`, thread khác gọi cùng method trên `b`. Chúng có tranh một monitor không?  
**Đáp án:** Không nếu `a` và `b` là hai instance khác nhau. Mỗi method khóa `this` của instance tương ứng.

**Câu 5.** Vì sao writer cập nhật `total` và `updates` dưới một monitor nhưng reader cần đọc hai trường trong **cùng một critical section**?  
**Đáp án:** Nếu reader nhả khóa giữa hai lần đọc, writer có thể hoàn tất một update ở giữa; hai giá trị có thể thuộc hai trạng thái logic khác nhau.

**Câu 6.** Consumer gọi `wait()` trên object `m` khi đang sở hữu `m`. Nó có giữ `m` trong lúc chờ không?  
**Đáp án:** Không. `wait()` nhả monitor `m`, rồi consumer phải lấy lại `m` trước khi `wait()` trả về. Monitor khác đang giữ không được tự nhả.

**Câu 7.** Producer gọi `notifyAll()` rồi làm việc lâu trước khi rời synchronized. Consumer có thể chạy tiếp bên trong cùng monitor ngay sau notify không?  
**Đáp án:** Không. Producer vẫn sở hữu monitor; consumer phải đợi producer unlock rồi mới có thể reacquire.

**Câu 8.** `volatile int counter; counter++;` có tương đương `synchronized(guard) { counter++; }` không?  
**Đáp án:** Không. Volatile access có ordering/visibility, nhưng `counter++` vẫn là read-modify-write và có thể mất cập nhật.

**Câu 9.** Một lần writer unlock `m` trước reader lock `m` có buộc reader luôn nhìn thấy giá trị của **writer đó**, dù thread thứ ba đã thay đổi giá trị hợp lệ giữa hai lần không?  
**Đáp án:** Không nhất thiết. HB bảo đảm các quy tắc quan sát và ordering, nhưng một writer khác có thể cập nhật giá trị trước lần đọc; cần xét toàn bộ lịch và các ghi liên quan.

**Câu 10.** Nếu `synchronized` giải quyết correctness, vẫn có thể có vấn đề performance hoặc liveness không?  
**Đáp án:** Có. Giữ monitor lâu tạo contention; lồng nhiều monitor không nhất quán có thể deadlock; scheduler không cam kết fairness. Đúng dữ liệu và tiến triển/hiệu năng là các thuộc tính cần đánh giá riêng.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 17 `17.1 — Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1): monitor, lock/unlock, mutual exclusion.
- [JLS `17.4.4 — Synchronization Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.4): quy tắc *synchronizes-with* của unlock/lock.
- [JLS `17.4.5 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5): program order, synchronizes-with, HB, correctly synchronized.
- [JLS `14.19 — synchronized Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.19): scope của synchronized và abrupt completion.
- [Java SE 17 Object API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): `wait`, `notify`, `notifyAll` và điều kiện sở hữu monitor.
- [Java SE 17 Thread.State](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): `BLOCKED`, `WAITING` và trạng thái thread.
- [Java SE 17 ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý task và memory consistency.
- [Java SE 17 Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): completion và memory consistency qua `get()`.

**Ghi nhớ:** mutual exclusion làm những thread dùng **cùng monitor** không chạy xen giữa critical section của nhau; memory visibility xuất phát từ cạnh **unlock(m) → subsequent lock(m)** trong Java Memory Model. Muốn chương trình đúng, cả writer và reader phải dùng giao thức nhất quán, và **toàn bộ invariant logic** phải nằm trong phạm vi được bảo vệ.