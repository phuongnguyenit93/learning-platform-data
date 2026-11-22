# Java 7 — Phaser: Chờ giai đoạn đổi bằng awaitAdvance

## 1. Mục tiêu, bối cảnh và điều quan trọng nhất

`java.util.concurrent.Phaser` được đưa vào **Java 7** và vẫn là bộ đồng bộ hóa nhiều giai đoạn hiện hành trên **Java 17+**. Nó điều phối các bên tham gia (*registered parties*) theo các vòng/phases. Khi tất cả parties phải đến trong một phase đã đến, phaser có thể **advance** sang phase tiếp theo và giải phóng những thread đang đợi.

**Đề bài trực tiếp của bài này:** “Chờ giai đoạn đổi bằng `awaitAdvance`”, thuộc chủ đề cha “Phaser”.

Method trọng tâm:

```java
int nextPhase = phaser.awaitAdvance(phase);
```

Đây là một **mảnh minh họa**: `phaser` phải là đối tượng `Phaser` hợp lệ và `phase` là số phase bạn muốn quan sát.

**Điểm cốt lõi:** `awaitAdvance(phase)` **không gọi `arrive()` thay bạn, không tự đăng ký party, không tự tiến phase và không đợi “đến phase có số lớn hơn” một cách độc lập**. Nó chờ **phase hiện tại khác với giá trị `phase` được truyền**. Nếu đã khác hoặc phaser đã terminated, nó trả ngay.

Sau bài học, bạn có thể:

1. Hiểu `getPhase()`, số parties đã đăng ký và số parties chưa đến.
2. Phân biệt `arrive()`, `arriveAndAwaitAdvance()`, `arriveAndDeregister()` và `awaitAdvance(int)`.
3. Dùng `awaitAdvance` để một **observer không đăng ký party** chờ sự kiện chuyển phase.
4. Tách việc **thông báo đã đến** (`arrive`) và **chờ vòng hoàn tất** (`awaitAdvance`).
5. Tránh lỗi chụp nhầm phase, đợi thừa một vòng, hoặc chờ mãi vì không có đủ arrivals.
6. Xử lý interrupt, timeout, forced termination và phase âm đúng semantics.
7. Dùng `awaitAdvanceInterruptibly` khi cần cancellation/deadline.
8. Biết timeout/interrupt khi chờ **không tự thay đổi trạng thái phaser**.
9. Tôn trọng việc đăng ký/hủy đăng ký parties và không đếm một party “đến” hai lần trong cùng phase.
10. Hiểu memory-consistency guarantee khi thread ghi dữ liệu trước arrival và thread khác quan sát sau phase advance.
11. Viết tests không phụ thuộc vào ngẫu nhiên thread scheduling.
12. Vận dụng Java 17+ với 15 chương trình độc lập, có code, lệnh biên dịch và stdout đã kiểm chứng.

## 2. Phaser là gì, và “phase” có nghĩa gì?

`Phaser` theo dõi một **thế hệ/vòng đồng bộ hóa** được gọi là `phase`. Ban đầu phase thường là **0**. Mỗi khi tất cả **registered parties chưa đến** của phase hiện tại hoàn thành arrival, phaser advance sang phase kế tiếp, thực hiện `onAdvance` (nếu có), sau đó các observers/waiters thích hợp có thể tiếp tục.

Ví dụ ba parties:

```text
                        PHASE 0
         Party A             Party B             Party C
       arrive()            arrive()            arrive()
            \                  |                  /
             \                 |                 /
              +-------- all arrivals -----------+
                               |
                       onAdvance(0,...)
                               |
                         PHASE 1
                               |
                 awaiting phase 0 is released
```

**Chỉ khi đủ arrivals hợp lệ** phaser mới tự advance. Một thread gọi `awaitAdvance(0)` chỉ quan sát và chờ, **không được tính là một arrival**.

### 2.1. Những giá trị nên quan sát

| API | Ý nghĩa |
| --- | --- |
| `getPhase()` | Phase hiện tại, hoặc số âm khi terminated |
| `getRegisteredParties()` | Số parties đã đăng ký |
| `getArrivedParties()` | Số parties đã đến trong phase hiện tại |
| `getUnarrivedParties()` | Số parties còn phải đến trong phase hiện tại |
| `isTerminated()` | Phaser đã kết thúc hay chưa |
| `register()` | Thêm một party cho phaser |
| `bulkRegister(n)` | Thêm nhiều parties |
| `arrive()` | Ghi nhận một arrival, **không chờ** |
| `arriveAndDeregister()` | Ghi nhận arrival và bỏ đăng ký party |
| `arriveAndAwaitAdvance()` | Ghi nhận arrival và chờ phase đổi |
| `awaitAdvance(phase)` | Chờ/quan sát phase đổi, **không arrival** |

Các số đo là **snapshot**, có thể thay đổi ngay khi threads khác register/arrive/deregister; không dùng chúng như cơ chế synchronization thay cho chính Phaser.

### 2.2. Registered party không đồng nghĩa thread ID

`Phaser` quản lý **số lượng đăng ký**. Nó không ràng buộc mỗi party với một thread identity hay tự kiểm tra mọi lời gọi `arrive()` thuộc thread đã register. Vì vậy programmer phải bảo đảm mỗi logical party:

- Được đăng ký đúng thời điểm.
- Arrival **đúng một lần trong một phase** mà party tham gia.
- Deregister theo thiết kế khi ngừng tham gia.
- Không tự đăng ký “ảo” hoặc double-arrive khiến phase tiến sớm.

Một observer chỉ gọi `awaitAdvance` có thể **không cần đăng ký**; còn một party đã đăng ký nhưng chỉ await mà không arrive có thể làm cả hệ thống kẹt.

## 3. Chữ ký và semantics của awaitAdvance(int)

Java 17 cung cấp:

```java
public int awaitAdvance(int phase)
```

Đây là **chữ ký API**, không phải chương trình độc lập.

Phương thức **chờ cho đến khi phase hiện tại khác argument** hoặc phaser đã terminated. Cụ thể:

| Tình huống tại thời điểm gọi | Hành vi |
| --- | --- |
| `getPhase() == phase` và phaser chưa terminated | Có thể block tới khi phase advance/terminate |
| `getPhase() != phase` | Trả ngay phase hiện tại |
| `phase < 0` | Trả ngay **chính argument âm** |
| Phaser đã terminated và `phase >= 0` | Trả ngay phase hiện tại **âm** |
| Thread bị interrupt trong lúc chờ | **Tiếp tục chờ**; không ném `InterruptedException` |
| Thread chờ không phải registered party | **Hợp lệ**; waiter không thay party counts |

**Kết quả trả về:** phase mới/phase hiện tại sau thay đổi, hoặc số âm nếu terminated (hay argument âm nếu caller đã truyền số âm). Không nên coi kết quả luôn bằng `phase + 1`: phaser có thể tiến nhiều phase trước khi waiter chạy lại, hoặc đã terminated, hoặc argument đã khác ngay từ đầu.

### 3.1. awaitAdvance không phải “await target phase”

`awaitAdvance(99)` khi phaser đang ở phase 1 **trả ngay 1**, không đợi đến phase 99, vì `1 != 99`.

Nếu muốn đạt một số phase mục tiêu, cần **lặp với điều kiện riêng**, xử lý termination, rollover và progress guarantee. Không biến method này thành `waitUntilPhase(target)` bằng cách truyền số target trực tiếp.

### 3.2. Phase âm là tín hiệu termination

Trên Java 17, `getPhase()` sẽ âm sau termination. Với `awaitAdvance(-7)`, contract trả ngay **-7**. Vì vậy code tổng quát nên kiểm:

```java
int next = phaser.awaitAdvance(previous);
if (next < 0) {
    // Phaser terminated, or caller passed negative argument.
    // Stop using this phase as a successful advance.
}
```

Đây là **mảnh minh họa**, `phaser` phải tồn tại. Trạng thái trả âm **không** phải “phase mới vừa hoàn tất thành công”.

## 4. Chờ thay đổi không phải tự tiến phase

Một lỗi cơ bản:

```java
Phaser phaser = new Phaser(1);
int phase = phaser.getPhase();
phaser.awaitAdvance(phase); // Không có ai arrive -> có thể chờ mãi.
```

Đây là **mảnh minh họa có thể chờ vô hạn**; không chạy như một chương trình test. Một registered party đang chờ **chính nó** arrive, nhưng method `awaitAdvance` không arrival. Nếu không có party khác gọi arrive cho đúng registration, phaser không tự tiến.

Cách sửa tùy ownership:

**Bạn là registered party và cần chờ sau khi đã đến:**

```java
int arrivalPhase = phaser.arrive();
int next = phaser.awaitAdvance(arrivalPhase);
```

**Bạn là observer, không phải party:**

```java
int observedPhase = phaser.getPhase();
int next = phaser.awaitAdvance(observedPhase);
// Một registered party khác chịu trách nhiệm arrive.
```

Trong cả hai trường hợp, phải có một đường thực thi thật sự làm đủ arrivals. Không đảm bảo progress chỉ bằng một lời gọi await.

## 5. So sánh ba dạng arrival và waiting

| Lệnh | Có ghi arrival? | Có chờ phase đổi? | Có giảm registered parties? |
| --- | --- | --- | --- |
| `arrive()` | Có | Không | Không |
| `awaitAdvance(phase)` | Không | Có nếu phase hiện tại khớp | Không |
| `arriveAndAwaitAdvance()` | Có | Có | Không |
| `arriveAndDeregister()` | Có | Không | Có |
| `awaitAdvance(arrive())` | Có, trong `arrive()` | Có, trong `awaitAdvance` | Không |
| `awaitAdvance(arriveAndDeregister())` | Có, trong deregistration | Có, trong `awaitAdvance` | Có |

Javadoc mô tả `arriveAndAwaitAdvance()` tương đương về hiệu quả với `awaitAdvance(arrive())`. Khi muốn **timeout hoặc interruptible wait**, bạn có thể tách `arrive()` và `awaitAdvanceInterruptibly(...)`.

### 5.1. Vì sao tách arrive và await hữu ích?

Bạn có thể hoàn tất phần việc của mình rồi ghi nhận arrival trước, sau đó làm một công việc không phụ thuộc vào phase, cuối cùng mới chờ:

```java
int old = phaser.arrive();
doIndependentWork();
int next = phaser.awaitAdvance(old);
```

Đây là **pseudocode**: `doIndependentWork` phải do ứng dụng định nghĩa. Điều kiện tiên quyết là công việc độc lập không cần dữ liệu của phase tiếp theo và không thay đổi registration/arrival sai cách.

### 5.2. Lưu phase do arrive trả về

**Nên:**

```java
int phase = phaser.arrive();
int next = phaser.awaitAdvance(phase);
```

**Dễ sai:**

```java
phaser.arrive();
int phase = phaser.getPhase();
int next = phaser.awaitAdvance(phase);
```

Nếu lời gọi `arrive()` vừa là arrival cuối cùng, nó có thể **đã chuyển sang phase tiếp theo** trước `getPhase()`. Lúc đó đoạn code sai sẽ đợi **một phase nữa**, có thể treo nếu không có arrivals vòng kế tiếp.

`arrive()` trả **phase của arrival**; lưu nó, đừng đọc lại phase để đoán.

## 6. Chương trình A — ObserverAwaitDemo.java

Đây là ví dụ tối thiểu cho một **observer không đăng ký party** chờ phase đổi. Chỉ main thread sở hữu registration của phaser; worker executor chờ dưới vai trò observer.

Lưu file **`ObserverAwaitDemo.java`**:

```java
import java.util.concurrent.*;

public final class ObserverAwaitDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(1);
        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        CountDownLatch ready = new CountDownLatch(1);

        try {
            Future<Integer> observer = executor.submit(() -> {
                int phase = phaser.getPhase();
                ready.countDown();
                return phaser.awaitAdvance(phase);
            });

            if (!ready.await(5, TimeUnit.SECONDS))
                throw new AssertionError("not ready");

            int parties = phaser.getRegisteredParties();
            int arrival = phaser.arrive();
            int advanced = observer.get(5, TimeUnit.SECONDS);

            System.out.println("arrivalPhase=" + arrival);
            System.out.println("observerPhase=" + advanced);
            System.out.println("registeredParties=" + parties);
            System.out.println("phaseNow=" + phaser.getPhase());
        } finally {
            phaser.forceTermination();
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException("executor");
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ObserverAwaitDemo.java
java ObserverAwaitDemo
```

**Stdout đã kiểm chứng:**

```text
arrivalPhase=0
observerPhase=1
registeredParties=1
phaseNow=1
```

### 6.1. Giải thích

- `new Phaser(1)` đăng ký **một party** — main.
- Observer gọi `getPhase()` lấy 0, phát tín hiệu đã chụp phase rồi chờ `awaitAdvance(0)`.
- `ready` giúp main không arrive **trước khi observer đọc phase**, tránh test race.
- Main gọi `arrive()`, là arrival cuối cùng nên phase chuyển từ 0 lên 1.
- Observer trả 1. `registeredParties` vẫn 1, vì **awaitAdvance không register**.
- `forceTermination()` trong finally là cleanup để nếu có lỗi, waiter không bị bỏ kẹt.

### 6.2. Tại sao không dùng Thread.sleep để canh thời điểm?

Sleep vài chục milliseconds không đảm bảo observer đã bắt đầu quan sát; trên máy chậm hoặc quá tải, nó có thể chưa chạy. `CountDownLatch ready` diễn đạt **sự kiện** observer đã chụp phase, đáng tin hơn canh thời gian.

## 7. Tách arrive và awaitAdvance của một registered party

Với `new Phaser(2)`, mỗi phase cần **hai arrivals**.

```text
Registered party A                   Registered party B
        |                                    |
  old = arrive()                             |
        |                                    |
 awaitAdvance(old) ------------- waiting     |
                                             |
                                         arrive()
                                             |
                                      phase 0 -> phase 1
                                             |
           <---------- waiter returns phase 1
```

`awaitAdvance(old)` không tự tính arrival thứ hai; đó là việc party B phải làm.

## 8. Chương trình B — SplitArrivalDemo.java

```java
import java.util.concurrent.*;

public final class SplitArrivalDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(2);
        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        CountDownLatch arrived = new CountDownLatch(1);

        try {
            Future<Integer> waiting = executor.submit(() -> {
                int phase = phaser.arrive();
                arrived.countDown();
                return phaser.awaitAdvance(phase);
            });

            if (!arrived.await(5, TimeUnit.SECONDS))
                throw new AssertionError("missing arrival");

            int unarrived = phaser.getUnarrivedParties();
            int mainArrival = phaser.arrive();
            int after = waiting.get(5, TimeUnit.SECONDS);

            System.out.println("remainingBeforeMain=" +
                    unarrived);
            System.out.println("mainArrivalPhase=" +
                    mainArrival);
            System.out.println("waiterContinuedAt=" + after);
            System.out.println("registeredParties=" +
                    phaser.getRegisteredParties());
        } finally {
            phaser.forceTermination();
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SplitArrivalDemo.java
java SplitArrivalDemo
```

**Stdout đã kiểm chứng:**

```text
remainingBeforeMain=1
mainArrivalPhase=0
waiterContinuedAt=1
registeredParties=2
```

Điểm đáng nhớ: worker đã `arrive()` nhưng chưa đủ vì registered parties vẫn là 2. Main phải arrive để hoàn tất phase. Sau đó waiter trả phase 1. Không có party nào deregister nên số registered vẫn là 2 cho phase kế tiếp.

## 9. Fast path: phase đã khác thì không đợi

`awaitAdvance` là một **phép so sánh phase tại thời điểm gọi**, không phải tín hiệu bắt buộc phải block. Nếu phase đã advance, nó trả ngay.

### 9.1. Chương trình C — PhaseFastPathDemo.java

```java
import java.util.concurrent.*;

public final class PhaseFastPathDemo {
    public static void main(String[] args) {
        Phaser phaser = new Phaser(1);

        int captured = phaser.getPhase();
        int arrival = phaser.arrive();
        int alreadyAdvanced = phaser.awaitAdvance(captured);
        int mismatched = phaser.awaitAdvance(99);
        int negativeArgument = phaser.awaitAdvance(-7);

        System.out.println("captured=" + captured);
        System.out.println("arrival=" + arrival);
        System.out.println("alreadyAdvanced=" + alreadyAdvanced);
        System.out.println("differentArgumentReturned=" +
                mismatched);
        System.out.println("negativeArgumentReturned=" +
                negativeArgument);
        phaser.forceTermination();
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 PhaseFastPathDemo.java
java PhaseFastPathDemo
```

**Stdout đã kiểm chứng:**

```text
captured=0
arrival=0
alreadyAdvanced=1
differentArgumentReturned=1
negativeArgumentReturned=-7
```

### 9.2. Phân tích

- `arrive()` ở phaser chỉ có 1 party tiến phase 0 → 1 ngay.
- `awaitAdvance(captured=0)` thấy phase hiện tại 1, trả ngay 1.
- `awaitAdvance(99)` thấy current phase 1 khác 99, cũng trả ngay **1**, không đợi phase 99.
- `awaitAdvance(-7)` trả ngay **chính argument -7**, ngay cả khi phaser chưa terminated.

Vì thế **không được tự suy một kết quả âm chắc chắn do `forceTermination` vừa xảy ra** nếu code đã truyền một argument âm trước đó.

## 10. Sai lầm phổ biến: chụp phase quá muộn

Giả sử bạn gọi `arrive()` trên phaser chỉ còn một party chưa đến. Arrival của bạn có thể là arrival cuối; phase đã đổi. Nếu bạn tiếp tục:

```java
phaser.arrive();
int now = phaser.getPhase();
phaser.awaitAdvance(now);
```

thì `awaitAdvance(now)` chờ **phase mới** (không phải phase đã đến mà bạn muốn đồng bộ). Nếu không có ai arrive vòng tiếp theo, thread có thể chờ mãi.

### 10.1. Chương trình D — CapturedPhaseDemo.java

Chúng ta dùng timed overload để **chứng minh lỗi mà không tạo test treo vô hạn**.

```java
import java.util.concurrent.*;

public final class CapturedPhaseDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(1);

        int before = phaser.getPhase();
        phaser.arrive();

        int correct = phaser.awaitAdvance(before);

        boolean lateWaitTimedOut = false;
        try {
            phaser.awaitAdvanceInterruptibly(
                    phaser.getPhase(), 40,
                    TimeUnit.MILLISECONDS);
        } catch (TimeoutException expected) {
            lateWaitTimedOut = true;
        } finally {
            phaser.forceTermination();
        }

        System.out.println("correctCaptureReturned=" + correct);
        System.out.println("lateCaptureTimedOut=" +
                lateWaitTimedOut);
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CapturedPhaseDemo.java
java CapturedPhaseDemo
```

**Stdout đã kiểm chứng:**

```text
correctCaptureReturned=1
lateCaptureTimedOut=true
```

**Vì sao?** `before=0` được chụp trước arrival; sau arrival phase là 1, nên `awaitAdvance(before)` trả 1. Còn lệnh dùng `getPhase()` sau arrival nhận 1 và sẽ chờ phase 2; vì không có arrivals tiếp theo nên timed wait hết hạn.

**Quy tắc:** Khi party có nhiệm vụ arrival, dùng **giá trị trả về của `arrive()`**. Khi chỉ quan sát, chụp `getPhase()` **trước sự kiện mình quan tâm**.

## 11. awaitAdvance là uninterruptible wait

Một khác biệt quan trọng giữa:

- `awaitAdvance(int)` — **không ném `InterruptedException`**, tiếp tục chờ dù thread bị interrupt.
- `awaitAdvanceInterruptibly(int)` — **ném `InterruptedException`** khi thread đang chờ và bị interrupt.

Với `awaitAdvance` thường, Java giữ trạng thái interrupted của thread để code sau khi hoàn tất vẫn nhận biết tín hiệu. Đây **không** phải lý do bỏ qua cancellation mãi mãi: muốn dừng waiter trong workflow thì có thể phải dùng timed/interruptible variant hoặc `forceTermination` theo policy.

### 11.1. Không dùng Thread.interrupt để “giải phóng” awaitAdvance

Đoạn sau có thể vẫn chờ:

```java
waiter.interrupt();
// waiter đang phaser.awaitAdvance(oldPhase);
// Chỉ interrupt không làm awaitAdvance kết thúc.
```

Đây là mảnh minh họa. Nếu không có arrivals hoặc termination, waiter không rời await chỉ nhờ interrupt.

## 12. Chương trình E — InterruptPreservingDemo.java

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class InterruptPreservingDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(1);
        CountDownLatch ready = new CountDownLatch(1);
        AtomicInteger advanced = new AtomicInteger(-99);
        AtomicBoolean preserved = new AtomicBoolean();

        Thread waiter = new Thread(() -> {
            int phase = phaser.getPhase();
            ready.countDown();
            int next = phaser.awaitAdvance(phase);
            advanced.set(next);
            preserved.set(Thread.currentThread().isInterrupted());
        }, "await-waiter");

        try {
            waiter.start();
            if (!ready.await(5, TimeUnit.SECONDS))
                throw new AssertionError("not ready");

            waiter.interrupt();
            waiter.join(80);
            boolean stillWaiting = waiter.isAlive();

            phaser.arrive();
            waiter.join(5000);

            if (waiter.isAlive())
                throw new IllegalStateException("still waiting");

            System.out.println("stillWaitingAfterInterrupt=" +
                    stillWaiting);
            System.out.println("advancedPhase=" +
                    advanced.get());
            System.out.println("interruptFlagPreserved=" +
                    preserved.get());
        } finally {
            phaser.forceTermination();
            waiter.join(5000);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 InterruptPreservingDemo.java
java InterruptPreservingDemo
```

**Stdout đã kiểm chứng:**

```text
stillWaitingAfterInterrupt=true
advancedPhase=1
interruptFlagPreserved=true
```

### 12.1. Tại sao waiter vẫn còn sống khi bị interrupt?

Phaser chưa chuyển phase; `awaitAdvance` không thoát chỉ vì interrupt. Main kiểm thread vẫn còn chờ khi chưa có arrival, sau đó gọi `arrive()` và waiter được giải phóng ở phase 1.

### 12.2. Tại sao kiểm bằng isInterrupted thay vì Thread.interrupted?

`Thread.currentThread().isInterrupted()` **không xóa interrupt flag**, phù hợp để kiểm trạng thái preserved. `Thread.interrupted()` là static method **đọc và xóa cờ**, có thể làm bài kiểm sai nếu dùng nó rồi lại kiểm lần nữa.

### 12.3. Tránh thiết kế production dựa vào mốc join(80ms)

`80ms` ở đây chỉ giúp quan sát trạng thái trước arrival; correctness của thuật toán đến từ **ready latch** và arrival theo thứ tự. Không dùng thời gian này làm SLA scheduling, và không dùng sleep để quyết định dữ liệu đã sẵn sàng.

## 13. awaitAdvanceInterruptibly: khi cần phản ứng với interrupt

Phương thức:

```java
int next = phaser.awaitAdvanceInterruptibly(phase);
```

có thể ném `InterruptedException`. Đây là mảnh minh họa, caller phải catch/throws hợp lý.

**Điều quan trọng:** Java 17 Javadoc quy định exceptions gặp khi wait interruptibly hoặc timeout **không làm thay đổi trạng thái phaser**. Method chờ không tự arrival/deregister; nếu task nghiệp vụ ngừng tham gia, ứng dụng phải có **recovery protocol**.

### 13.1. InterruptedException không tự “xóa một party”

Nếu phaser có một registered party chưa arrive, thread chờ bị interrupt không làm `getRegisteredParties()` giảm hoặc `getUnarrivedParties()` tự về 0. Các waiters khác có thể vẫn chờ. Nếu cả workflow không thể tiếp tục, owner thường có thể gọi `forceTermination()` để tránh kẹt.

### 13.2. Một party đã arrive mà timeout/interrupt thì sao?

Nếu party đã gọi `arrive()` ở phase 0, rồi `awaitAdvanceInterruptibly(0)` bị interrupt, **arrival của nó vẫn đã được ghi**. Không được gọi `arriveAndDeregister()` bừa lần nữa trong cùng phase để “cleanup”, vì có thể đếm một arrival thứ hai làm phase tiến sai. Hãy dùng cơ chế hủy/recovery được thiết kế rõ và cân nhắc `forceTermination` nếu cả cuộc đồng bộ cần dừng.

`Phaser` quản lý *counts*, không tự gắn identity cho party, nên lỗi double-arrival đôi khi không ném exception ngay nhưng vẫn phá logic.

## 14. Chương trình F — InterruptibleDemo.java

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class InterruptibleDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(1);
        CountDownLatch ready = new CountDownLatch(1);
        AtomicBoolean threw = new AtomicBoolean();

        Thread waiter = new Thread(() -> {
            int phase = phaser.getPhase();
            ready.countDown();
            try {
                phaser.awaitAdvanceInterruptibly(phase);
            } catch (InterruptedException e) {
                threw.set(true);
            }
        });

        try {
            waiter.start();
            if (!ready.await(5, TimeUnit.SECONDS))
                throw new AssertionError();

            waiter.interrupt();
            waiter.join(5000);
            if (waiter.isAlive())
                throw new IllegalStateException("not interrupted");

            System.out.println("interruptCaught=" +
                    threw.get());
            System.out.println("phaseUnchanged=" +
                    (phaser.getPhase() == 0));
            System.out.println("unarrivedParties=" +
                    phaser.getUnarrivedParties());
        } finally {
            phaser.forceTermination();
            waiter.join(5000);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 InterruptibleDemo.java
java InterruptibleDemo
```

**Stdout đã kiểm chứng:**

```text
interruptCaught=true
phaseUnchanged=true
unarrivedParties=1
```

Waiter chưa registered, chỉ chờ phase0. Khi bị interrupt, nó bắt `InterruptedException` và rời chờ. Phaser vẫn ở phase0 và vẫn có một party chưa arrive. Sự khác biệt này là cơ sở thiết kế cancellation an toàn.

## 15. Timeout: awaitAdvanceInterruptibly(phase, timeout, unit)

Trên Java 17, method timed:

```java
int next = phaser.awaitAdvanceInterruptibly(
        oldPhase, 5, TimeUnit.SECONDS);
```

có thể ném:

- `InterruptedException` nếu thread bị interrupt trong lúc chờ.
- `TimeoutException` nếu chưa quan sát phase đổi trước thời hạn.
- Trả phase hiện tại nếu khác argument hoặc phaser terminated.

**Không tồn tại `awaitAdvance(phase,timeout,unit)` uninterruptible** với đúng tên đó. Phiên bản timed thuộc `awaitAdvanceInterruptibly`.

### 15.1. Timeout không tự advance phase

`TimeoutException` chỉ nói waiter **không quan sát được phase advance trong thời hạn**. Nó không tự deregister, không hủy arrivals, không reset phaser, không rollback tác vụ.

### 15.2. Tránh chờ không có deadline ở biên ứng dụng

Với service/API cần deadline, dùng timed wait và recovery policy thay vì `awaitAdvance` vô hạn. Nếu timeout cho thấy một registered party đã chết hoặc không thể arrive, cần quyết định:

1. Có thể recovery/đăng ký một party mới hợp lệ không?
2. Có cần cho các party khác dừng không?
3. Có cần `forceTermination` không?
4. Đã có arrival nào được ghi chưa?
5. Dữ liệu của phase hiện tại có thể bị dở dang không?

**Không tự động gọi `arrive()` giả làm party bị mất** nếu chưa có một giao thức rõ. Đánh thức các waiters bằng cách làm tiến phase sai còn nguy hiểm hơn báo lỗi.

## 16. Chương trình G — TimedObserverDemo.java

```java
import java.util.concurrent.*;

public final class TimedObserverDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(1);
        boolean timedOut = false;
        int before = phaser.getPhase();

        try {
            phaser.awaitAdvanceInterruptibly(
                    before, 40, TimeUnit.MILLISECONDS);
        } catch (TimeoutException expected) {
            timedOut = true;
        }

        System.out.println("timedOut=" + timedOut);
        System.out.println("phaseUnchanged=" +
                (phaser.getPhase() == before));
        System.out.println("registeredParties=" +
                phaser.getRegisteredParties());
        System.out.println("unarrivedParties=" +
                phaser.getUnarrivedParties());

        phaser.forceTermination();
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 TimedObserverDemo.java
java TimedObserverDemo
```

**Stdout đã kiểm chứng:**

```text
timedOut=true
phaseUnchanged=true
registeredParties=1
unarrivedParties=1
```

Không có task nào arrive, nên timer hết hạn. Phaser vẫn phase0, 1 registered party và 1 unarrived party. **Timeout không tự sửa cân bằng arrivals.**

Trong production, thời hạn 40ms ở đây chỉ là test. Chọn deadline dựa yêu cầu nghiệp vụ, executor load và môi trường chạy.

## 17. Termination: khác hẳn phase advance thành công

Phaser có thể terminated:

1. `onAdvance(...)` trả `true` ở một phase transition.
2. `forceTermination()` được gọi để chấm dứt khẩn cấp/giải phóng waiters.
3. Default `onAdvance` trả true khi `registeredParties==0` do **deregistration cuối cùng**.

Khi terminated:

- `isTerminated()==true`.
- `getPhase()` âm.
- Các methods chờ (bao gồm `awaitAdvance`) **không tiếp tục block**.
- Caller phải kiểm giá trị âm và ngừng xử lý như “phase tiếp theo thành công”.
- `register()`/`bulkRegister()` không tái khởi động phaser đã terminated.
- Muốn có một synchronization run mới, thông thường tạo **Phaser mới**.

### 17.1. forceTermination không tương đương arrive đủ parties

`forceTermination()` phát tín hiệu dừng, **không phải** chứng minh mọi party đã hoàn thành phần việc và đã arrival. Nó giữ nguyên registered-party counts, chỉ chuyển trạng thái sang terminated và giải phóng waiters.

Nếu một observer chờ phase0, bị force terminated, trả về một số âm. Khi đó application không được đọc intermediate outputs như thể phase0 đã được tất cả workers xử lý trọn vẹn.

## 18. Chương trình H — TerminationReleaseDemo.java

```java
import java.util.concurrent.*;

public final class TerminationReleaseDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(1);
        CountDownLatch ready = new CountDownLatch(1);
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            Future<Integer> waiter = executor.submit(() -> {
                int phase = phaser.getPhase();
                ready.countDown();
                return phaser.awaitAdvance(phase);
            });

            if (!ready.await(5, TimeUnit.SECONDS))
                throw new AssertionError();

            phaser.forceTermination();
            int answer = waiter.get(5, TimeUnit.SECONDS);

            System.out.println("terminated=" +
                    phaser.isTerminated());
            System.out.println("awaitReturnedNegative=" +
                    (answer < 0));
            System.out.println("phaseNegative=" +
                    (phaser.getPhase() < 0));
            System.out.println("registeredUnchanged=" +
                    (phaser.getRegisteredParties() == 1));
            System.out.println("negativeArgUnchanged=" +
                    (phaser.awaitAdvance(-17) == -17));
        } finally {
            phaser.forceTermination();
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 TerminationReleaseDemo.java
java TerminationReleaseDemo
```

**Stdout đã kiểm chứng:**

```text
terminated=true
awaitReturnedNegative=true
phaseNegative=true
registeredUnchanged=true
negativeArgUnchanged=true
```

### 18.1. Vì sao số parties không đổi?

`forceTermination` không gọi deregistration. Do đó `getRegisteredParties()==1` dù phaser terminated. Không dùng registered-count=0 làm dấu hiệu duy nhất của termination.

### 18.2. Tại sao không in exact negative phase trong expected stdout?

Java mô tả phase âm sau termination và có quy tắc biểu diễn nội bộ; test nên kiểm **âm** và `isTerminated`. Không cần gắn nghiệp vụ vào một số âm cụ thể ngoài contract. Khi truyền argument âm, `awaitAdvance` trả lại argument ấy.

## 19. Deregistration cuối cùng có thể tự kết thúc phaser

`arriveAndDeregister()` vừa ghi một arrival vừa **giảm số registered parties**. Theo default `onAdvance`, khi một deregistration làm số parties về 0, phaser **terminated**.

Đây là một lý do quan trọng: nếu một observer vẫn muốn chờ phase mới, nhưng mọi parties đồng thời deregister, kết quả của `awaitAdvance` có thể là **phase âm**, không phải 1 hay 2.

### 19.1. Không lạm dụng deregister để “bỏ qua” một phase

Một registered party chỉ deregister một lần theo lifecycle đăng ký của nó. Nếu party đã arrived trong cùng phase, đừng tự gọi lại `arriveAndDeregister` ngay sau timeout/interrupt mà không phân tích số unarrived và stage. Vì `Phaser` không theo thread identity, lời gọi sai có thể làm người khác được release quá sớm.

## 20. Chương trình I — LastDeregisterDemo.java

```java
import java.util.concurrent.*;

public final class LastDeregisterDemo {
    public static void main(String[] args) {
        Phaser phaser = new Phaser(2);

        int first = phaser.arriveAndDeregister();
        int left = phaser.getRegisteredParties();
        boolean before = phaser.isTerminated();

        phaser.arriveAndDeregister();

        System.out.println("firstArrivalPhase=" + first);
        System.out.println("remainingAfterFirst=" + left);
        System.out.println("terminatedBeforeLast=" + before);
        System.out.println("terminatedAfterLast=" +
                phaser.isTerminated());
        System.out.println("registeredAfterLast=" +
                phaser.getRegisteredParties());
        System.out.println("awaitAfterTerminationNegative=" +
                (phaser.awaitAdvance(0) < 0));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 LastDeregisterDemo.java
java LastDeregisterDemo
```

**Stdout đã kiểm chứng:**

```text
firstArrivalPhase=0
remainingAfterFirst=1
terminatedBeforeLast=false
terminatedAfterLast=true
registeredAfterLast=0
awaitAfterTerminationNegative=true
```

Đầu tiên còn một registered party. Lần deregistration thứ hai giảm số parties về 0, default `onAdvance` terminate. `awaitAdvance(0)` sau termination trả âm ngay.

### 20.1. Khi không muốn auto-terminate sau 0 parties

Phaser cho phép override `onAdvance`, ví dụ trả `false` để không dừng chỉ vì tạm thời không có parties. Nhưng điều đó phải phù hợp lifecycle. Trên phaser không có ai có thể arrive và không có đăng ký mới, observer chờ phase vẫn không tiến; tránh tạo phaser sống mãi nhưng không có đường progress.

## 21. Observer không phải party: nhiều người xem một phase

Một thiết kế phổ biến: một nhóm workers là **registered parties**, còn các metrics collectors, coordinator hay clients chỉ **quan sát** phase đổi.

`awaitAdvance` cho phép các observers đọc phase và chờ mà **không tăng registered parties**. Điều này hữu ích vì một observer tạm ngừng hoặc rời đi không nên vô tình làm cản trở workers hoàn tất phase.

Ví dụ:

```text
Party P1 -------- arrive phase 0 -------+
                                       +---- advance phase 0 -> 1
Party P2 -------------------- arrive ---+

Observer O1  awaitAdvance(0) ------------------> released at 1
Observer O2  awaitAdvance(0) ------------------> released at 1
Observer O3  awaitAdvance(0) ------------------> released at 1

Registered parties remain 2, not 5.
```

**Lưu ý:** Observer không đăng ký có thể bỏ lỡ một phase nếu chụp `getPhase()` sau sự kiện cần quan sát. Để đảm bảo không bỏ lỡ **business events**, dùng event queue/log với sequence IDs; Phaser là công cụ đồng bộ hóa trạng thái phase, **không phải event log**.

## 22. Chương trình J — ObserverNotRegisteredDemo.java

```java
import java.util.*;
import java.util.concurrent.*;

public final class ObserverNotRegisteredDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(2);
        ExecutorService executor =
                Executors.newFixedThreadPool(3);
        CountDownLatch ready = new CountDownLatch(3);
        List<Future<Integer>> results = new ArrayList<>();

        try {
            for (int i = 0; i < 3; i++) {
                results.add(executor.submit(() -> {
                    int phase = phaser.getPhase();
                    ready.countDown();
                    return phaser.awaitAdvance(phase);
                }));
            }

            if (!ready.await(5, TimeUnit.SECONDS))
                throw new AssertionError();

            int registered = phaser.getRegisteredParties();

            phaser.arrive();
            int remaining = phaser.getUnarrivedParties();
            phaser.arrive();

            boolean allAtOne = true;
            for (Future<Integer> f : results) {
                allAtOne &=
                        (f.get(5, TimeUnit.SECONDS) == 1);
            }

            System.out.println("observerCount=" + results.size());
            System.out.println("registeredParties=" + registered);
            System.out.println("unarrivedAfterOneArrival=" +
                    remaining);
            System.out.println("allResumedAtOne=" +
                    allAtOne);
        } finally {
            phaser.forceTermination();
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ObserverNotRegisteredDemo.java
java ObserverNotRegisteredDemo
```

**Stdout đã kiểm chứng:**

```text
observerCount=3
registeredParties=2
unarrivedAfterOneArrival=1
allResumedAtOne=true
```

Có 3 observer threads nhưng `registeredParties` vẫn bằng 2. Khi một party arrive, còn một party chưa đến. Khi party thứ hai arrive, cả ba observers được giải phóng ở phase1.

**Lưu ý quan trọng:** ví dụ này dùng main thread để gửi hai arrivals đại diện cho **hai logical registrations** trong test. Phaser không gắn registration với thread identity; trong ứng dụng thật, mỗi logical party nên quản lý arrival của mình đúng một lần.

## 23. Nhiều phase nối tiếp: phải arrival lại ở mỗi vòng

Sau khi phase 0 advance sang 1, nếu registered parties vẫn là N, vòng 1 lại cần **N arrivals mới**. `arrive` chỉ đánh dấu **vòng hiện tại**, không miễn arrival cho các vòng tiếp theo.

Ví dụ phaser có 3 parties và hai rounds:

```text
               ROUND 0                         ROUND 1
  Worker A      arrive(0)                         arrive(1)
  Worker B      arrive(0)                         arrive(1)
  Coordinator   arrive(0)                         arrive(1)

           phase 0 -> 1                       phase 1 -> 2
           all continue                       all continue
```

Nếu có một party rời hệ thống sau round 0, nó cần `arriveAndDeregister` đúng thời điểm; nếu không parties còn lại sẽ chờ một arrival không bao giờ đến ở round tiếp theo.

### 23.1. Đừng tái sử dụng phase cũ cho vòng mới

Trong loop, lấy `phase` mới từ `arrive()` của **vòng hiện tại** rồi gọi `awaitAdvance(phase)`. Nếu cứ giữ 0 sau khi đã phase1, `awaitAdvance(0)` trả ngay và không còn làm barrier vòng 1 nữa.

## 24. Chương trình K — TwoPhasesDemo.java

```java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class TwoPhasesDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(3);
        ExecutorService executor =
                Executors.newFixedThreadPool(2);
        AtomicInteger work = new AtomicInteger();
        List<Future<?>> workers = new ArrayList<>();

        try {
            for (int w = 0; w < 2; w++) {
                workers.add(executor.submit(() -> {
                    for (int round = 0; round < 2; round++) {
                        work.incrementAndGet();
                        int old = phaser.arrive();
                        int next = phaser.awaitAdvance(old);
                        if (next < 0)
                            throw new IllegalStateException(
                                    "terminated");
                    }
                }));
            }

            for (int round = 0; round < 2; round++) {
                int old = phaser.arrive();
                int next = phaser.awaitAdvance(old);
                if (next != round + 1)
                    throw new AssertionError(
                            "next phase " + next);
            }

            for (Future<?> f : workers)
                f.get(5, TimeUnit.SECONDS);

            System.out.println("completedWork=" + work.get());
            System.out.println("phaseNow=" + phaser.getPhase());
            System.out.println("registeredParties=" +
                    phaser.getRegisteredParties());
            System.out.println("unarrivedParties=" +
                    phaser.getUnarrivedParties());
        } finally {
            phaser.forceTermination();
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 TwoPhasesDemo.java
java TwoPhasesDemo
```

**Stdout đã kiểm chứng:**

```text
completedWork=4
phaseNow=2
registeredParties=3
unarrivedParties=3
```

Hai worker xử lý 2 rounds → có 4 công việc leaf được đếm. Main là party thứ ba và arrive trong mỗi round. Sau hai lần advance, phase=2; không có party nào deregister nên vẫn có 3 registrations. Ở đầu phase2, cả ba đều chưa arrive.

### 24.1. Tại sao AtomicInteger ở đây?

Hai workers cùng cập nhật `work`. Dùng `AtomicInteger` để đếm công việc an toàn; `work++` trên một biến int chia sẻ mà không có synchronization sẽ là data race.

### 24.2. Vì sao phải đợi Futures?

`awaitAdvance` đảm bảo ranh giới từng phase, nhưng main vẫn nên lấy kết quả của các Futures để biết **task có ném exception hay không** và xác minh toàn bộ workflow đã hoàn tất. Nếu worker fail, đợi không có deadline có thể treo; các `Future.get(timeout)` trong demo giới hạn việc chờ.

## 25. Memory consistency: dữ liệu trước arrive được công bố sau advance

Java `Phaser` có memory-consistency guarantee. Về ý nghĩa:

- Những hành động trước một hình thức `arrive`
- **happen-before** bước phase advance và `onAdvance` tương ứng
- rồi **happen-before** các hành động sau phase advance được quan sát.

Nhờ đó Phaser có thể đóng vai trò **synchronization barrier** cho dữ liệu chung, không chỉ là đồng hồ đếm phase.

Ví dụ:

```text
Writer: shared[0] = 42;
Writer: phaser.arrive();     -- synchronization boundary --

                               -- phase advances --

Observer: phaser.awaitAdvance(oldPhase);
Observer: int result = shared[0]; // sees 42 under proper protocol
```

**Điều kiện:** các parties phải dùng đúng barrier, dữ liệu phải được truy cập trong protocol hợp lệ và không có writes/reads cạnh tranh ngoài barrier. Phaser không biến toàn bộ shared state thành thread-safe khi bạn đọc/ghi lung tung ngoài những ranh giới đã điều phối.

## 26. Chương trình L — MemoryVisibilityDemo.java

```java
import java.util.concurrent.*;

public final class MemoryVisibilityDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(1);
        int[] shared = {0};
        CountDownLatch ready = new CountDownLatch(1);
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            Future<Integer> observed = executor.submit(() -> {
                int phase = phaser.getPhase();
                ready.countDown();

                int advanced = phaser.awaitAdvance(phase);
                if (advanced < 0)
                    throw new IllegalStateException(
                            "unexpected termination");
                return shared[0];
            });

            if (!ready.await(5, TimeUnit.SECONDS))
                throw new AssertionError();

            shared[0] = 42;
            phaser.arrive();

            int value = observed.get(5, TimeUnit.SECONDS);
            System.out.println("observed=" + value);
            System.out.println("visibleAfterPhaseAdvance=" +
                    (value == 42));
        } finally {
            phaser.forceTermination();
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 MemoryVisibilityDemo.java
java MemoryVisibilityDemo
```

**Stdout đã kiểm chứng:**

```text
observed=42
visibleAfterPhaseAdvance=true
```

### 26.1. Tại sao shared[0] không cần volatile ở đúng demo này?

Main ghi `shared[0]=42` **trước arrival**, observer đọc **sau khi `awaitAdvance` trả về thành công**. Phaser cung cấp memory ordering cho các hành động đó. Ngoài protocol này (ví dụ main liên tục thay đổi shared trong lúc observer đọc), vẫn có thể cần synchronization/volatile/immutable snapshots khác.

### 26.2. Đừng đọc sau forced termination như thể thành công

Nếu worker fail rồi coordinator `forceTermination`, observer có thể được release nhưng worker **chưa ghi xong dữ liệu**. Do đó demo kiểm `advanced<0` và báo lỗi. Memory consistency không đồng nghĩa dữ liệu của một phase đã hoàn tất thành công nếu phaser bị force terminated.

## 27. onAdvance: callback của chuyển phase và chính sách termination

Method có thể override:

```java
@Override
protected boolean onAdvance(int phase, int registeredParties) {
    // Called at an impending phase transition.
    return phase >= maxPhase || registeredParties == 0;
}
```

Đây là **mảnh minh họa**; `maxPhase` phải được định nghĩa.

- `onAdvance` được gọi bởi party gây phase transition, trước khi phát công bố phase mới.
- `phase` là phase đang kết thúc, không phải phase sau khi advance.
- `registeredParties` là số parties tại thời điểm transition theo contract.
- Trả `true` → phaser **terminate** thay vì tiếp tục bình thường.
- Trả `false` → cho phép tiếp tục phase sau.
- Default thường terminate khi số registered parties trở về 0 sau deregistration.
- Không dùng `onAdvance` để gọi `arrive/register/awaitAdvance` trên chính phaser đang advance; API nói behavior không được xác định/không nên dựa vào.
- Tránh callback lâu/chặn/đọc database ở đây: mọi parties đang chờ bước advance có thể bị ảnh hưởng.

### 27.1. onAdvance không phải business transaction hook có rollback

Nếu callback ném unchecked exception/Error, Javadoc nói lỗi có thể propagate tới party gây advance và **không có phase advance**. Những parties đang chờ có thể bị kẹt. Hãy giữ callback đơn giản, deterministic và có phương án recovery (ví dụ force terminate từ coordinator nếu lỗi nghiêm trọng).

## 28. Chương trình M — OnAdvanceDemo.java

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class OnAdvanceDemo {
    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        Phaser phaser = new Phaser(1) {
            protected boolean onAdvance(
                    int phase, int parties) {
                calls.incrementAndGet();
                return phase >= 1 || parties == 0;
            }
        };

        int first = phaser.arrive();
        int current = phaser.getPhase();
        int second = phaser.arrive();

        System.out.println("firstArrivalPhase=" + first);
        System.out.println("phaseAfterFirst=" + current);
        System.out.println("secondArrivalPhase=" + second);
        System.out.println("onAdvanceCalls=" + calls.get());
        System.out.println("terminatedAfterSecond=" +
                phaser.isTerminated());
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 OnAdvanceDemo.java
java OnAdvanceDemo
```

**Stdout đã kiểm chứng:**

```text
firstArrivalPhase=0
phaseAfterFirst=1
secondArrivalPhase=1
onAdvanceCalls=2
terminatedAfterSecond=true
```

Ở transition đầu, `onAdvance(0,1)` trả false nên phase chuyển sang 1. Ở transition sau, `onAdvance(1,1)` trả true nên phaser terminate. Ví dụ đếm callback, không dùng sleeps hoặc nhiều threads để che khuất cơ chế.

## 29. arriveAndAwaitAdvance() so với hai lời gọi tách rời

Javadoc mô tả:

```java
int next = phaser.arriveAndAwaitAdvance();
```

có tác dụng tương đương:

```java
int old = phaser.arrive();
int next = phaser.awaitAdvance(old);
```

Đây là hai **mảnh minh họa**. Khi dùng trong code thật, không gọi **cả hai** cho cùng một party trong một phase, vì đó là ghi arrival hai lần.

### 29.1. Chọn cái nào?

- **`arriveAndAwaitAdvance`:** ngắn gọn nếu mỗi registered party cần luôn arrival rồi chờ barrier, không cần timeout/interruptibility riêng.
- **`arrive + awaitAdvance`:** linh hoạt nếu sau arrival muốn làm việc độc lập hoặc cần quan sát phase riêng.
- **`arrive + awaitAdvanceInterruptibly`:** nếu caller cần policy interrupt/timeouts. Không mặc định deregister khi wait thất bại.

## 30. Chương trình N — ArriveAndAwaitComparisonDemo.java

```java
import java.util.concurrent.*;

public final class ArriveAndAwaitComparisonDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(2);
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            Future<Integer> worker =
                    executor.submit(phaser::arriveAndAwaitAdvance);

            int mainReturn = phaser.arriveAndAwaitAdvance();
            int workerReturn = worker.get(5, TimeUnit.SECONDS);

            System.out.println("mainReturnedPhase=" +
                    mainReturn);
            System.out.println("workerReturnedPhase=" +
                    workerReturn);
            System.out.println("phaseNow=" +
                    phaser.getPhase());
            System.out.println("registeredParties=" +
                    phaser.getRegisteredParties());
        } finally {
            phaser.forceTermination();
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ArriveAndAwaitComparisonDemo.java
java ArriveAndAwaitComparisonDemo
```

**Stdout đã kiểm chứng:**

```text
mainReturnedPhase=1
workerReturnedPhase=1
phaseNow=1
registeredParties=2
```

Cả main và worker gọi arrival rồi chờ. Khi đủ hai arrivals, phase0 → 1; cả hai nhận return value1. Số registrations không đổi vì không deregister.

## 31. Chờ sau khi deregister: awaitAdvance(arriveAndDeregister())

Javadoc còn khuyến nghị pattern:

```java
int old = phaser.arriveAndDeregister();
int next = phaser.awaitAdvance(old);
```

Điều này phù hợp khi caller **rời tập registered parties** ngay sau khi đến nhưng vẫn muốn quan sát phase trước đó được hoàn tất bởi những parties còn lại.

### 31.1. Khác await sau arrive thông thường

- `arrive()` giữ registration cho phase kế tiếp.
- `arriveAndDeregister()` bỏ registration; caller **không phải arrive ở những phase sau**.
- `awaitAdvance(old)` có thể được gọi bởi thread không còn registered, vì nó chỉ quan sát.
- Nếu đó là deregistration cuối cùng, default phaser có thể **terminate**, và result chờ sẽ **âm**.
- Không gọi `arriveAndDeregister` hai lần cho cùng logical registration.

## 32. Chương trình O — DeregisterThenAwaitDemo.java

```java
import java.util.concurrent.*;

public final class DeregisterThenAwaitDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(3);
        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> last = executor.submit(() -> {
                if (!release.await(5, TimeUnit.SECONDS))
                    throw new IllegalStateException();
                return phaser.arrive();
            });

            int old = phaser.arriveAndDeregister();
            int registered = phaser.getRegisteredParties();
            int unarrived = phaser.getUnarrivedParties();

            phaser.arrive();
            release.countDown();

            int lastPhase = last.get(5, TimeUnit.SECONDS);
            int advanced = phaser.awaitAdvance(old);

            System.out.println("deregisteredAt=" + old);
            System.out.println("registeredAfterDeregister=" +
                    registered);
            System.out.println("unarrivedAfterDeregister=" +
                    unarrived);
            System.out.println("lastArrivalPhase=" + lastPhase);
            System.out.println("observerAdvancedAt=" + advanced);
            System.out.println("terminated=" +
                    phaser.isTerminated());
        } finally {
            release.countDown();
            phaser.forceTermination();
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 DeregisterThenAwaitDemo.java
java DeregisterThenAwaitDemo
```

**Stdout đã kiểm chứng:**

```text
deregisteredAt=0
registeredAfterDeregister=2
unarrivedAfterDeregister=2
lastArrivalPhase=0
observerAdvancedAt=1
terminated=false
```

### 32.1. Phân tích

- Ban đầu có 3 registrations ở phase0.
- Caller đầu tiên `arriveAndDeregister()`: ghi arrival của nó, giảm registered từ 3 còn 2; hai parties còn lại chưa arrive.
- Một party khác arrive ở main; party cuối arrive từ executor.
- Khi đủ, phaser phase0 →1 và vẫn có hai registered parties cho phase1.
- Caller đã deregister vẫn có thể gọi `awaitAdvance(old=0)` để quan sát phase1.
- `terminated=false` vì số registered parties vẫn 2.

### 32.2. Vì sao example dùng một thread gọi hai logical arrivals?

Code minh họa một coordinator có thể đại diện các logical registrations khác nhau. `Phaser` không gắn mỗi registration với thread ID. Trong sản phẩm thật, owner phải đảm bảo các arrivals đến từ đúng logical parties, tránh double-arrival.

## 33. awaitAdvance không tự “đăng ký” observer

Một số người nhầm `awaitAdvance(phase)` giống `CountDownLatch.await()` với fixed countdown. Khác biệt:

- `CountDownLatch` chỉ chuyển về 0 một lần, không có phase number lặp.
- `CyclicBarrier.await()` thường **ghi arrival và chờ** trong một lần gọi của registered participants.
- `Phaser.arriveAndAwaitAdvance()` tương tự barrier-arrive-and-wait.
- `Phaser.awaitAdvance(phase)` chỉ quan sát **thay đổi phase**, không count một party.
- `Phaser` hỗ trợ dynamic register/deregister và nhiều rounds.

Vì vậy, khi chọn API đồng bộ hóa, hỏi rõ **caller là party hay observer**. Nếu party, thường cần `arrive` trước await; nếu observer, chỉ await là đúng và không tạo thêm registration.

## 34. Waiters, phase number và thứ tự sự kiện

### 34.1. Observer không đảm bảo nhận đủ từng “event”

Phaser lưu **phase hiện tại**, không ghi log từng transition. Nếu phaser tăng phase 0 →1 →2 trước khi observer được CPU chạy lại, `awaitAdvance(0)` có thể trả current phase2. Nó không tự gọi callback hai lần để replay phase1.

Nếu hệ thống cần xử lý đúng mỗi event, dùng queue/log/sequence-number có cơ chế replay hoặc acknowledgment. Không dùng Phaser như event broker có history.

### 34.2. Phase rollover

Java 17 Javadoc quy định phase bắt đầu tại 0 và sau `Integer.MAX_VALUE` sẽ wrap về 0. Các ví dụ nhỏ không gặp trường hợp này, nhưng **đừng thiết kế so sánh phase bằng “lớn hơn” mãi mãi** cho hệ thống chạy cực lâu. `awaitAdvance` dựa vào khác phase, không dựa vào target lớn hơn argument.

### 34.3. Multiple observers và fairness

`awaitAdvance` giải phóng waiters khi phase chuyển, nhưng **không đảm bảo thứ tự** các threads được chạy sau đó. Scheduler quyết định. Đừng viết logic đòi observer A xử lý trước B trừ khi có synchronization riêng.

### 34.4. No registered parties và liveness

Nếu không có parties hoặc không ai arrive, một observer đang chờ phase có thể chờ mãi trừ khi có registration/arrival mới, hoặc phaser bị terminated. Không có “tự đếm thời gian” ở `awaitAdvance` thường. Với service có deadline, chọn interruptible/timed variant.

## 35. Những lỗi lập trình có thể khiến ứng dụng treo

### 35.1. Registered party chỉ await, quên arrive

`new Phaser(1)`; party duy nhất gọi `awaitAdvance(0)` sẽ tự chờ arrival của chính nó. Đúng ra nó phải `arrive` hoặc `arriveAndAwaitAdvance` theo protocol.

### 35.2. Party fail trước khi arrive

Nếu một trong N parties ném exception trước arrival và không có recovery, các parties còn lại có thể chờ vô hạn. Cần coordinator phát hiện failure và `forceTermination` khi cả cuộc đồng bộ không còn hợp lệ.

### 35.3. Chụp getPhase sau arrival cuối

Vừa `arrive` khiến phase advance, sau đó `awaitAdvance(getPhase())` vô tình chờ phase **tiếp theo**. Sử dụng phase returned by `arrive()`.

### 35.4. Đếm đôi arrival

Một logical party gọi `arrive()` hai lần trong cùng phase có thể làm phaser advance quá sớm hoặc làm trạng thái sai. `Phaser` không xác thực identity của party ở mọi operation.

### 35.5. Thêm registration nhưng không có worker

Gọi `register()` hoặc `bulkRegister(n)` tăng số arrivals cần có. Nếu đã thêm một party mà không có task nào sẽ arrive, phase sẽ kẹt. Registration phải gắn với lifecycle thực tế của nhiệm vụ.

### 35.6. Deregister vào sai phase

Nếu task đã arrived rồi timed out khi chờ, tiếp tục `arriveAndDeregister()` trong cùng phase có thể là **một arrival thứ hai**. Chọn recovery policy đúng; dùng force termination khi không thể khôi phục đồng bộ.

### 35.7. Chờ inside onAdvance

`onAdvance` chạy ở điểm transition; gọi registration/arrival/await bên trong callback không có semantics bảo đảm. Callback chặn lâu cũng giữ chậm toàn bộ chuyển phase. Giữ callback ngắn.

### 35.8. Không kiểm negative return

`forceTermination` giải phóng waiter với phase âm. Nếu code vẫn xử lý kết quả như một phase thành công, có thể sử dụng dữ liệu dở dang.

### 35.9. Dùng Future.get timeout như hủy workflow

`Future.get(5,SECONDS)` timeout chỉ làm thread gọi thôi chờ Future; task có thể vẫn chờ `awaitAdvance`. Chủ động `forceTermination` hoặc cancellation policy theo ownership, không bỏ mặc thread.

### 35.10. Block tất cả ForkJoinPool workers

Phaser được thiết kế dùng được trong ForkJoinPool, nhưng Javadoc lưu ý progress phải phù hợp mức parallelism và số blocked parties. Nếu mọi worker bị block trên một barrier mà party còn thiếu chỉ có thể chạy như task đang queued trong cùng pool, hệ thống có thể không tiến.

Không dựa mù quáng vào work-stealing để sửa mọi kiểu blocking; số workers, pool ownership và phân chia công việc phải được thiết kế.

## 36. Kiến trúc thực hành an toàn

### 36.1. Tách ba vai trò

- **Coordinator/owner:** tạo phaser, quyết định số parties, xử lý failures/termination, sở hữu executor và cleanup.
- **Registered workers:** thực hiện công việc mỗi round, gọi `arrive` đúng một lần, chờ phase đúng như protocol, deregister khi kết thúc.
- **Observers:** chụp phase trước sự kiện, chờ `awaitAdvance(phase)`, không đến/không đăng ký, và xử lý kết quả âm.

### 36.2. Protocol ví dụ

```text
Coordinator:
  create Phaser(n + coordinator?)
  create workers, register correctly
  start tasks
  for each round:
    prepare own work
    arrivalPhase = arrive()
    next = awaitAdvance(arrivalPhase)
    if next < 0: fail/stop

Worker:
  for each round:
    do work for this phase
    arrivalPhase = arrive()
    next = awaitAdvance(arrivalPhase)
    if next < 0: stop

Observer:
  phase = getPhase() BEFORE event
  next = awaitAdvance(phase)
  if next < 0: report terminated
  else: consume committed phase results

Coordinator cleanup on errors:
  forceTermination()
  collect task outcomes
  shutdown owned executor
  await termination
```

Đây là pseudocode hoạt động theo vai trò, **không phải class runnable**. Số registered parties của coordinator phải được quyết định trước; nếu không có coordinator arrival thì **đừng** tính coordinator vào count.

### 36.3. Những lựa chọn thay thế

Nếu một hệ thống chỉ cần đợi một lần, `CountDownLatch` có thể đơn giản hơn. Nếu mọi participant đều arrive-and-wait cùng nhau với số lượng cố định, `CyclicBarrier` có thể dễ hiểu. Khi cần nhiều rounds, dynamic parties hoặc observers tách biệt, `Phaser` có giá trị.

## 37. Mẫu timeout và recovery an toàn hơn

Một observer thuần, không registered, có thể:

```java
int old = phaser.getPhase();

try {
    int next = phaser.awaitAdvanceInterruptibly(
            old, 5, TimeUnit.SECONDS);

    if (next < 0) {
        // The workflow was terminated.
    } else {
        // A different phase was observed.
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Report cancellation; only owner decides whether to terminate.
} catch (TimeoutException e) {
    // Report deadline expiry; observer does not modify party counts.
}
```

Đây là mảnh minh họa, không phải chương trình độc lập. Tách việc observer báo lỗi và coordinator có quyền `forceTermination`. Nếu một worker registered đã arrived trước khi wait, timeout cần xử lý khác — đừng tưởng còn quyền arrival lần nữa.

### 37.1. Không dùng timeout để đánh giá lỗi chỉ qua thời gian

Timeout 5 giây có thể là do CPU quá tải, task chậm hợp lệ, blocked I/O hoặc party thất bại. Nó là **tín hiệu deadline**, không tự xác định root cause. Ghi metrics và outcome của parties, không phá dữ liệu khi chưa hiểu trạng thái.

### 37.2. Chọn forceTermination khi workflow không thể khôi phục

Khi một worker ném exception không thể hoàn tất round, coordinator có thể gọi `forceTermination()` để giải phóng tất cả waiters và thu thập exceptions. Không gọi force termination từ mọi observer nhỏ nếu phaser là tài nguyên dùng chung và observer không phải owner.

## 38. So sánh các phương thức chờ và chọn đúng

| Nhu cầu | API phù hợp | Điều cần nhớ |
| --- | --- | --- |
| Party chỉ ghi arrival | `arrive()` | Không chờ |
| Party arrival rồi chờ | `arriveAndAwaitAdvance()` | Không interruptible/timed |
| Party arrival rồi muốn chờ tách rời | `arrive()` + `awaitAdvance(returnedPhase)` | Lưu phase trước |
| Party arrival rồi chờ có timeout | `arrive()` + `awaitAdvanceInterruptibly(old,t,u)` | Timeout không undo arrival |
| Party rời registration nhưng chờ phase hoàn tất | `arriveAndDeregister()` + `awaitAdvance(old)` | Có thể terminate nếu cuối cùng |
| Observer không registered | `awaitAdvance(getPhase trước event)` | Không increment parties |
| Observer phải phản ứng interrupt | `awaitAdvanceInterruptibly(phase)` | Có thể ném InterruptedException |
| Observer phải có deadline | `awaitAdvanceInterruptibly(phase,t,u)` | Có thể ném TimeoutException |
| Workflow gặp lỗi không thể tiếp tục | `forceTermination()` | Release âm, không cam kết results hoàn chỉnh |
| Muốn biết party counts/phase | `getPhase/getUnarrivedParties` | Snapshot, không dùng thay arrival/wait |

**Không có method nào ở bảng tự tạo bảo đảm all business work thành công**. Barrier phase là synchronization mechanism; failure/outcome của tasks cần được thu thập riêng.

## 39. Ma trận kiểm thử 15 chương trình Java 17

| Chương trình | Mục đích QA | Kết quả ổn định |
| --- | --- | --- |
| `ObserverAwaitDemo` | Observer không đăng ký vẫn chờ được | Phase0 →1; parties1 |
| `SplitArrivalDemo` | Một party arrive rồi chờ party còn lại | Unarrived trước main=1, next1 |
| `PhaseFastPathDemo` | Current phase khác argument thì return ngay | 1; negative arg giữ -7 |
| `CapturedPhaseDemo` | Lưu phase trước event vs đọc trễ | Correct1, late timedOut |
| `InterruptPreservingDemo` | awaitAdvance không ngừng bởi interrupt | Vẫn đợi; flag preserved |
| `InterruptibleDemo` | Bản interruptible ném exception | Phase0 và unarrived1 không đổi |
| `TimedObserverDemo` | Timeout không đổi trạng thái phaser | TimedOut, phase0, parties1 |
| `TerminationReleaseDemo` | Force termination giải phóng waiters | Phase âm, count không đổi |
| `LastDeregisterDemo` | Default terminate khi parties về 0 | terminated=true, await âm |
| `ObserverNotRegisteredDemo` | Nhiều observer không tăng registration | 3 observers, 2 registered |
| `TwoPhasesDemo` | Hai rounds cần arrivals mới | Phase2, work4 |
| `MemoryVisibilityDemo` | Happens-before qua phase advance | Quan sát 42 |
| `OnAdvanceDemo` | Callback và termination có điều kiện | Hai callbacks, terminate sau phase1 |
| `ArriveAndAwaitComparisonDemo` | arriveAndAwaitAdvance kết hợp arrive + wait | Hai callers return1 |
| `DeregisterThenAwaitDemo` | Deregister rồi vẫn quan sát phase | Registered còn2, next1 |

Các chương trình đã biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy trên JDK hiện đại; stdout được lấy từ test thật. Chúng tránh phụ thuộc vào tên thread, số CPU, số lần bị scheduler preempt, hay đo thời gian thực thi chính xác. Tất cả ví dụ có wait hữu hạn/cleanup phù hợp để không cố ý để test process treo khi gặp lỗi.

### 39.1. Không dùng timing làm một hợp đồng Java

Mốc 40ms/80ms/5s trong bài là cơ chế kiểm soát QA, **không phải latency guarantee**. CI quá tải có thể cần deadline lớn hơn hoặc scheduling primitives theo loại test. Assertions cần dựa vào phase/state/outcome chứ không khẳng định một thread phải được chạy trong 1ms.

### 39.2. Những điều cần kiểm riêng ở production

- Task exception trước arrival.
- Registration thay đổi trong lúc phase đang tiến.
- Một party deregister trong khi observers chờ.
- Observer bắt đầu chờ sau khi phase đã advance.
- Nhiều phases có thể tiến trước khi observer lấy CPU.
- Timeout/interrupt và recovery protocol.
- Forced termination và cleanup tài nguyên.
- Thread pool thiếu workers làm xảy ra starvation.
- Phase numbers chạy dài và wrap.
- Correct visibility của outputs theo từng phase.

## 40. Lỗi phổ biến và cách tránh

1. **Chỉ gọi `awaitAdvance` mà không có ai arrival** → chờ mãi.
2. **Registered party nghĩ `awaitAdvance` tự ghi arrival** → thiếu một arrival.
3. **Chụp `getPhase()` sau `arrive()` cuối cùng** → chờ thừa một phase.
4. **Truyền target phase99 vào `awaitAdvance(99)`** → trả ngay nếu current khác99, không đợi tới99.
5. **Không kiểm return âm** → coi termination là thành công.
6. **Gọi Thread.interrupt rồi nghĩ `awaitAdvance` thoát** → nó uninterruptible.
7. **Muốn timeout nhưng gọi `awaitAdvance` thường** → không có overload timed tên đó.
8. **`awaitAdvanceInterruptibly` timeout rồi tự trừ registered count** → timeout không tự deregister.
9. **Worker đã arrived nhưng sau timeout lại `arriveAndDeregister` trong cùng phase** → nguy cơ double-arrival.
10. **Observer không registered lại tự gọi `arrive`** → sai logical party count.
11. **Party fail trước arrival mà coordinator không recovery** → waiters kẹt.
12. **`forceTermination` xong đọc data như round thành công** → dữ liệu có thể chưa hoàn tất.
13. **Đọc `getUnarrivedParties` một lần rồi suy nó bất biến** → snapshot có thể đổi.
14. **Gọi `register` vô điều kiện cho mỗi observer** → tăng arrivals cần có, có thể deadlock.
15. **Mỗi round dùng phase 0 cố định** → sau vòng 0 các waits trả ngay.
16. **Một party arrive hai lần** → Phaser không theo identity, có thể advance sai.
17. **Quên deregister party rời workflow** → phase tiếp theo chờ vô hạn.
18. **Deregister cuối cùng nhưng nghĩ phaser vẫn phase dương** → default termination.
19. **Dùng phase tăng đơn điệu mãi để so sánh lớn hơn** → có rollover.
20. **Dùng Phaser làm durable event history** → observers có thể bỏ lỡ phases.
21. **Chặn trong `onAdvance` hoặc gọi phaser methods từ callback** → tiến trình có thể bị cản trở/hành vi không bảo đảm.
22. **Không chờ Futures khi một worker có exception** → caller không biết failure.
23. **Tất cả pool workers cùng chờ mà thiếu arrival task** → starvation.
24. **Nuốt InterruptedException** → làm mất cancellation policy.
25. **Không đóng executor/forceTermination trong test failure** → leak hoặc test process treo.
26. **Cho rằng onAdvance count là số party** → callback đếm phase transitions, không đếm threads.
27. **Đọc shared data sau return âm** → thiếu guarantee hoàn tất business stage.
28. **Tự tạo registration mà không gắn lifecycle worker thực** → orphaned party.
29. **Đợi bằng sleep thay cho signal đã capture phase** → flaky tests.
30. **Coi Phaser giống CountDownLatch một lần** → sai với multi-phase/dynamic parties.

## 41. Bài tập thực hành có đáp án

**Bài 1.** `awaitAdvance(0)` trên Phaser(1), không ai arrive: kết quả? **Có thể đợi vô hạn**.

**Bài 2.** Một observer không đăng ký party có được gọi awaitAdvance không? **Có**.

**Bài 3.** Observer await có làm `registeredParties` tăng từ 1 lên 2? **Không**.

**Bài 4.** `arrive()` trả về phase nào? **Phase của arrival vừa ghi**, không nhất thiết phase hiện tại lúc code chạy dòng tiếp theo.

**Bài 5.** Tại sao không dùng `getPhase()` ngay sau `arrive()` để chờ? **Có thể đã advance; sẽ chờ vòng khác**.

**Bài 6.** Với Phaser(2), worker arrive, main chưa arrive: `getUnarrivedParties` bao nhiêu? **1**.

**Bài 7.** `awaitAdvance(99)` khi current phase1 có đợi đến99? **Không**, trả ngay1.

**Bài 8.** `awaitAdvance(-7)` trả gì? **-7**.

**Bài 9.** Thread bị interrupt trong `awaitAdvance` thường có thoát không? **Không chỉ vì interrupt**.

**Bài 10.** Thread bị interrupt trong `awaitAdvanceInterruptibly`? **Ném InterruptedException**.

**Bài 11.** Timed wait hết hạn làm phaser tự tiến một phase? **Không**.

**Bài 12.** Timed wait hết hạn làm party tự deregister? **Không**.

**Bài 13.** Đang chờ `awaitAdvance(0)`, owner force terminate thì nhận gì? **Phase âm**.

**Bài 14.** `forceTermination` có làm `registeredParties` về0 không? **Không**, counts được giữ.

**Bài 15.** Hai parties cuối cùng `arriveAndDeregister` hết, default phaser có terminated không? **Có**.

**Bài 16.** Party đã arrive rồi waiter bị interrupt; có nên `arrive` lần nữa không? **Không**, arrival của phase đó đã ghi.

**Bài 17.** `arriveAndAwaitAdvance()` tương đương hiệu quả với tổ hợp nào? **`awaitAdvance(arrive())`**.

**Bài 18.** Party deregister rồi có được await phase cũ hoàn tất không? **Có**, với `awaitAdvance(arriveAndDeregister())`.

**Bài 19.** Một listener chỉ cần quan sát phase mới, có cần register không? **Không**.

**Bài 20.** Observer chụp phase sau event đã diễn ra và gọi awaitAdvance, có thể xảy ra gì? **Chờ sự kiện kế tiếp**.

**Bài 21.** Khi observer ngủ qua 3 phase transitions, awaitAdvance có trả từng transition không? **Không**, chỉ trả phase hiện tại khi nó tiếp tục**.

**Bài 22.** Phaser có bảo đảm thứ tự các observers được scheduler chạy sau advance? **Không**.

**Bài 23.** Mỗi round với 3 parties cần bao nhiêu arrivals? **Ba arrivals hợp lệ**, trừ khi registration thay đổi đúng protocol.

**Bài 24.** `getPhase()` có thể âm khi nào? **Khi phaser terminated**.

**Bài 25.** `getPhase()` có tăng vô hạn vượt Integer.MAX_VALUE không? **Không**, wrap về 0.

**Bài 26.** Đọc shared[0] sau phase advance có thể thấy write trước arrival nhờ gì? **Happens-before / memory consistency guarantee của Phaser**.

**Bài 27.** Điều đó có khiến mọi writes ngoài barrier thread-safe không? **Không**.

**Bài 28.** Nếu worker fail trước arrival, làm sao tránh các waiters kẹt? **Coordinator có thể forceTermination và thu thập failures**, theo ownership.

**Bài 29.** Có nên dùng `onAdvance` để chờ network I/O? **Không**, dễ giữ toàn bộ advance chậm.

**Bài 30.** Muốn observer có deadline, method nào? **`awaitAdvanceInterruptibly(phase,timeout,TimeUnit)`**.

**Bài 31.** `Future.get(timeout)` trên một worker đang await làm phaser tự terminate không? **Không**.

**Bài 32.** `awaitAdvance` so sánh phase bằng lớn hơn hay khác? **Khác phase**.

**Bài 33.** Có thể dùng Phaser làm message queue có khả năng replay mọi phase không? **Không**.

**Bài 34.** Vì sao test dùng CountDownLatch ready? **Đảm bảo observer chụp phase trước arrival, không sleep đoán thời điểm**.

**Bài 35.** Thread bất ngờ bị interrupt nhưng `awaitAdvance` thường vẫn trả phase1; interrupt flag thế nào? **Được bảo toàn**, nên caller có thể xử lý sau đó.

**Bài 36.** Khi read phase âm, có nên coi outputs của vòng đã hoàn tất thành công? **Không**, phải phân biệt termination do lỗi.

**Bài 37.** Nếu parties về0 và bạn muốn phaser vẫn sống, làm thế nào? **Override onAdvance có chủ đích**, nhưng phải bảo đảm có lối progress/registration mới.

**Bài 38.** CountDownLatch và Phaser khác gì ở nhiều rounds? **Latch one-shot, Phaser có nhiều phases và dynamic parties**.

**Bài 39.** Nếu một ForkJoinPool có ít workers hơn số parties đồng thời chờ, có nguy cơ gì? **Starvation/progress issue nếu không thể chạy arrivals còn thiếu**.

**Bài 40.** Nếu chỉ cần đợi một thao tác ở service boundary, có nhất thiết dùng Phaser? **Không**, chọn công cụ đơn giản hơn khi phù hợp.

## 42. Checklist trước khi đưa vào dự án

- [ ] Đúng chủ đề **awaitAdvance**, không nhầm với một barrier luôn tự arrival.
- [ ] Phân loại caller là registered party hay unregistered observer.
- [ ] Số registrations được tạo đúng theo logical parties.
- [ ] Mỗi party arrival đúng một lần trong mỗi phase cần thiết.
- [ ] Nếu tách arrive và wait, dùng **phase returned by arrive()**.
- [ ] Nếu là observer, chụp `getPhase()` trước event cần quan sát.
- [ ] Không truyền “target phase” vào awaitAdvance rồi mong được đợi tới target.
- [ ] Xử lý trả ngay khi phase đã khác argument.
- [ ] Xử lý kết quả âm là termination/negative argument.
- [ ] Đừng quên registration/deregistration lifecycle.
- [ ] Không gọi arriveAndDeregister bừa sau timeout nếu đã arrived.
- [ ] Khi cần cancellation/timeout, dùng awaitAdvanceInterruptibly.
- [ ] Hiểu awaitAdvance thường **không** dừng vì interrupt và bảo toàn interrupt status.
- [ ] Timeout/interrupt không làm thay đổi phaser state.
- [ ] Có recovery/forceTermination policy do coordinator sở hữu.
- [ ] Không coi forceTermination như thành công business phase.
- [ ] Tránh synchronous blocking lâu trong onAdvance.
- [ ] Không dựa vào phase số học lớn hơn xuyên rollover.
- [ ] Không dùng phaser làm event log/replay queue.
- [ ] Đợi các Futures để nhận task exceptions.
- [ ] Nếu dùng ForkJoinPool, đủ resources/progress cho các blocked parties.
- [ ] Bảo vệ dữ liệu chia sẻ, dùng đúng memory ordering của phase boundary.
- [ ] Unit tests không dựa vào số thread chạy hoặc timing OS.
- [ ] Cleanup executor, waiter threads và phaser sau test failures.
- [ ] Code chạy Java 17+ với standard Java concurrency APIs.
- [ ] Special Note được giữ: không trình bày workaround/legacy API lỗi thời như khuyến nghị.

## 43. Tài liệu Java SE 17 chính thức

- [`Phaser` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): `awaitAdvance(int)`, `arrive`, `arriveAndAwaitAdvance`, `arriveAndDeregister`, termination, onAdvance, memory consistency, tiering.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): so sánh với cơ chế chờ một lần.
- [`CyclicBarrier` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): so sánh arrival-and-wait.
- [`ForkJoinPool` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): khả năng chặn/wait và thread-pool liveness khi phối hợp với concurrency tasks.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý executor và task futures trong ví dụ.
- [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout)` và khác biệt với wait của Phaser.
- [`CountDownLatch.await` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html#await()): phối hợp deterministic trong tests.
- [`TimeUnit` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): biểu diễn timeout của overload interruptible.
- [`InterruptedException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html): hợp đồng interruptible waits.
- [`TimeoutException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeoutException.html): timeout không tự thay đổi phaser.

**Tóm tắt cuối:** `Phaser.awaitAdvance(phase)` chờ **phase hiện tại khác phase đã cho** — nó **không** đăng ký party và **không** thay caller gọi `arrive()`. Dùng giá trị `arrive()` trả về để tránh chờ sai vòng; observer không đăng ký chụp phase **trước** sự kiện cần theo dõi. Bản thường là **uninterruptible**, còn `awaitAdvanceInterruptibly` hỗ trợ interrupt/timeout nhưng **không** tự thay trạng thái phaser. Phân biệt phase advance thành công với termination trả âm, có recovery policy, quản lý parties đúng và thu thập task outcomes độc lập. Những nguyên tắc này vẫn áp dụng trên Java 17+ và giúp tránh deadlock do thiếu arrival, double-arrival hoặc phase-capture race.