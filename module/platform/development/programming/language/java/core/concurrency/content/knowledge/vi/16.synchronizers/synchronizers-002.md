# CyclicBarrier phối hợp các vòng làm việc trong Java

> **Trọng tâm:** `CyclicBarrier` là một **điểm hẹn đồng bộ có thể tái sử dụng** cho **một số lượng thread cố định**. Mỗi thread thực hiện phần việc của vòng hiện tại rồi gọi `await()`; khi **đủ số parties** đến, barrier có thể chạy một `barrierAction` duy nhất, mở cổng cho các thread tiếp tục và **tự sẵn sàng cho vòng tiếp theo**. Các mốc đồng bộ này giúp các thuật toán nhiều vòng (*iterative/phase-based computation*) không đọc dữ liệu vòng sau trước khi mọi thread hoàn thành phần việc vòng trước. Nhưng một thread vắng mặt, bị ngắt hoặc quá hạn có thể làm cả nhóm kẹt hoặc khiến barrier trở thành *broken*.

Bài thuộc nhóm **Synchronizers**, phạm vi **Java concurrency nói chung**. Ví dụ sử dụng Java SE 17+, không phụ thuộc Spring hay một framework nào khác.

## 1. Vì sao cần một điểm hẹn giữa nhiều thread?

Giả sử chia một mảng thành 4 vùng. 4 worker độc lập tính kết quả của **vòng k** trên vùng mình phụ trách. Vòng `k+1` cần nhìn thấy **toàn bộ** kết quả của vòng `k`; nếu worker nhanh được phép bước sang vòng mới ngay, nó có thể trộn dữ liệu cũ với dữ liệu mới.

~~~text
              VÒNG k                  VÒNG k+1
Worker 1    [tính A] ----┐          [tính A mới] -----┐
Worker 2    [tính B] --┐ |          [tính B mới] ---┐ |
Worker 3    [tính C] ----+--> BARRIER --> [tính C] --+--> BARRIER
Worker 4    [tính D] --┘ |          [tính D mới] ---┘ |
                        |                            |
              Tất cả đã hoàn thành       Tất cả đã hoàn thành
              trước khi sang vòng mới    trước khi sang vòng tiếp
~~~

Barrier là **đồng bộ theo giai đoạn**: những worker cùng một nhóm phải hoàn tất một mốc chung trước khi nhóm đi tiếp. Nó **không** phân phối các task, không tự chia mảng, không tự tạo thread và không sửa thuật toán nghiệp vụ. Lập trình viên vẫn phải viết công việc của từng thread, chọn số worker và quản lý vòng đời.

Ví dụ tình huống phù hợp:

- Tính toán lặp nhiều bước: mô phỏng vật lý, xử lý lưới, thuật toán relaxation, iterative numerical processing.
- Xử lý dữ liệu theo các vòng: mọi worker hoàn thành round hiện tại rồi chuyển state.
- Thử nghiệm concurrency: cần nhiều thread cùng đến một điểm đã định trước để điều phối các bước test.
- Pipeline có các **giai đoạn chung** mà tất cả thành viên nhóm phải hoàn thành trước khi mở giai đoạn mới.

Không dùng barrier khi công việc hoàn toàn độc lập và chỉ cần thu kết quả cuối; lúc ấy `Future.get()`, `invokeAll` hoặc `CountDownLatch` có thể đơn giản hơn.

## 2. API cốt lõi của CyclicBarrier

`java.util.concurrent.CyclicBarrier` có hai constructor chính:

~~~java
// Snippet API; cần import java.util.concurrent.CyclicBarrier.
CyclicBarrier simple = new CyclicBarrier(3);
CyclicBarrier withAction =
        new CyclicBarrier(3, () -> System.out.println("round done"));
~~~

Số `parties` là số **lượt đến** yêu cầu để mở barrier mỗi vòng; trong mô hình thông dụng, mỗi worker đến **một lần cho mỗi vòng**. `parties <= 0` không hợp lệ và constructor ném `IllegalArgumentException`.

Các phương thức:

| API | Ý nghĩa |
| --- | --- |
| `await()` | Worker đến điểm hẹn, **chờ** cho đến khi đủ parties hoặc barrier bị phá; trả arrival index |
| `await(timeout, unit)` | Cũng chờ đủ parties, nhưng có timeout; khi timeout có thể phá cả barrier |
| `getParties()` | Trả số parties cấu hình khi tạo; đây không phải current active-thread count |
| `getNumberWaiting()` | Số parties đang chờ ở barrier hiện tại; dùng chủ yếu cho monitoring/debug |
| `isBroken()` | Cho biết barrier đang ở trạng thái *broken* |
| `reset()` | Đưa barrier vào generation mới, đồng thời làm các waiter hiện hữu nhận `BrokenBarrierException` |

CyclicBarrier **không có** `arrive()` không chờ, `arriveAndDeregister()` hoặc `getPhase()` như `Phaser`. Nó cũng **không tự thay đổi parties** khi một worker chết. Nếu số workers có thể co giãn, hãy cân nhắc một synchronizer khác.

### Parties khác threads trên toàn JVM

`new CyclicBarrier(4)` không có nghĩa JVM chỉ có 4 threads, hay executor sẽ tự tạo 4 worker. Nó chỉ định một *rendezvous* phải có **bốn lần đến của nhóm** ở mỗi vòng. Các thread không tham gia vẫn chạy bình thường. Một barrier dùng chung với những thread không thuộc nhóm có thể làm protocol sai; mỗi thread phải hiểu rõ mình đang tham gia vòng nào.

## 3. Vòng đời một barrier: reusable và generation

Một barrier thành công theo quy trình:

1. Worker A đến và gọi `await` → chờ.
2. Worker B đến → tiếp tục chờ.
3. Worker C đến, đủ `parties=3`.
4. Nếu có `barrierAction`, **thread cuối cùng đến** chạy action.
5. Khi action hoàn tất bình thường, mọi waiter được phép ra khỏi `await`.
6. Barrier **tự reset cho vòng kế tiếp**; nhóm có thể lặp lại cùng quy trình.

~~~text
CyclicBarrier(parties=3)

Generation 0:
 A: await ──────────────┐
 B: await ────────────┐ │
 C: await ── last ────┤ │
                      ▼ ▼
                 [barrierAction]
                        |
                  release A,B,C
                        |
Generation 1:  A/B/C lại await
                        |
                  [barrierAction] ...
~~~

**Phân biệt tự mở lại và reset thủ công:** Sau **một vòng thành công**, CyclicBarrier tự dùng generation tiếp theo; không cần `reset()`. `reset()` chủ yếu phục vụ khi cần xử lý trạng thái broken theo protocol, và nếu đang có waiter, nó **phá vòng mà waiter ấy đang đợi**.

### Không là broadcast event độc lập

Barrier chỉ mở khi **đủ parties** đến. Một thread gọi `await()` trong khi thiếu thành viên không nhận được “event done” từ việc thread khác ở nơi xa gọi `countDown`; nó sẽ chờ. Đây là khác biệt lớn so với `CountDownLatch`.

## 4. Ví dụ 1 — ba worker phối hợp qua ba vòng

Ví dụ dùng 3 thread và 3 vòng. Trong mỗi vòng, worker `i` ghi một giá trị vào **ô riêng `values[i]`**, rồi chờ barrier. `barrierAction` đọc ba ô để tổng hợp và ghi vào tổng chung. Không dựa vào thứ tự OS schedule.

Tạo tệp `ThreeRoundsBarrier.java` (Java 17+):

~~~java
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicInteger;

public class ThreeRoundsBarrier {
    public static void main(String[] args) throws InterruptedException {
        int workers = 3;
        int rounds = 3;
        int[] values = new int[workers];
        AtomicInteger completedRounds = new AtomicInteger();
        AtomicInteger grandTotal = new AtomicInteger();

        CyclicBarrier barrier = new CyclicBarrier(workers, () -> {
            int roundSum = 0;
            for (int value : values) {
                roundSum += value;
            }
            grandTotal.addAndGet(roundSum);
            completedRounds.incrementAndGet();
        });

        Thread[] threads = new Thread[workers];
        for (int i = 0; i < workers; i++) {
            final int slot = i;
            threads[i] = new Thread(() -> {
                try {
                    for (int round = 1; round <= rounds; round++) {
                        values[slot] = round;
                        barrier.await();
                    }
                } catch (Exception failure) {
                    throw new IllegalStateException(failure);
                }
            }, "worker-" + i);
            threads[i].start();
        }

        for (Thread thread : threads) {
            thread.join();
        }

        System.out.println("rounds completed = "
                + completedRounds.get());
        System.out.println("grand total = " + grandTotal.get());
        System.out.println("broken = " + barrier.isBroken());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ThreeRoundsBarrier.java
java ThreeRoundsBarrier
~~~

Stdout trên đường chạy bình thường:

~~~text
rounds completed = 3
grand total = 18
broken = false
~~~

Diễn giải:

- Vòng 1: ba worker đều ghi `1`, action cộng `1+1+1=3`.
- Vòng 2: mỗi worker ghi `2`, action cộng `2+2+2=6`.
- Vòng 3: mỗi worker ghi `3`, action cộng `3+3+3=9`.
- `grandTotal = 3+6+9 = 18`; action được gọi **chính xác một lần cho mỗi vòng thành công**, tổng 3 lần.
- `barrier.await()` ở mỗi worker chặn sự chuyển sang vòng `round+1` cho tới khi mọi worker hoàn thành vòng hiện tại.
- Sau `join` cả ba threads, main đọc kết quả và in đúng một trình tự xác định.

Không đặt `System.out.println` cho từng worker ngay trước barrier rồi đòi thứ tự dòng log giống nhau mọi lần chạy: **thứ tự đến barrier không được scheduler cố định**.

**Vì sao dùng `int[]` không khóa ở đây?** Mỗi thread ghi **một slot khác nhau**; không có hai threads ghi cùng một slot. `barrierAction` đọc sau khi tất cả đã gọi `await`, phù hợp bảo đảm *happens-before* của barrier. Nếu worker khác ngoài nhóm sửa `values` đồng thời, hoặc các worker cùng ghi một slot, vẫn cần đồng bộ bổ sung.

## 5. Giá trị trả về của await(): arrival index

`await()` trả một `int` biểu diễn **vị trí đến trong generation hiện tại**, từ `getParties()-1` cho người đến đầu tới **0 cho người đến cuối**.

Với `parties=4`, bốn calls thành công trong một generation nhận bốn giá trị phân biệt `3,2,1,0`, không nhất thiết theo thứ tự thread IDs. `0` là **last arrival**; đây cũng là thread thực hiện barrier action nếu có.

### Ví dụ 2 — kiểm chứng arrival indices không phụ thuộc scheduling

Tạo `BarrierArrivalIndices.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierArrivalIndices {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger actions = new AtomicInteger();
        CyclicBarrier barrier = new CyclicBarrier(
                4, actions::incrementAndGet);

        List<Integer> indices =
                Collections.synchronizedList(new ArrayList<>());

        Thread[] workers = new Thread[4];
        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                try {
                    indices.add(barrier.await());
                } catch (Exception failure) {
                    throw new IllegalStateException(failure);
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }
        Collections.sort(indices);

        System.out.println("arrival indices = " + indices);
        System.out.println("action count = " + actions.get());
    }
}
~~~

Chạy:

~~~bash
javac BarrierArrivalIndices.java
java BarrierArrivalIndices
~~~

Stdout:

~~~text
arrival indices = [0, 1, 2, 3]
action count = 1
~~~

`indices` là synchronized list vì **nhiều threads cùng add** sau khi barrier mở. Main chỉ sort sau khi tất cả worker đã kết thúc. Không sử dụng `ArrayList` thường để nhiều worker `add` cùng lúc rồi nghĩ barrier làm mọi mutation sau `await` tuần tự: sau khi được mở, **các worker lại tiếp tục đồng thời**.

### Có nên chọn “leader” bằng index 0?

Có thể dùng `index==0` làm dấu hiệu last-arriving thread để thực hiện một thao tác **sau khi barrier đã mở**, nhưng nếu thao tác đó phải hoàn tất **trước khi các worker khác tiếp tục vòng mới**, dùng **`barrierAction`** mới đúng. Sau khi `await` trả về, tất cả có thể chạy đồng thời; những worker khác không phải chờ riêng thao tác của thread index 0.

Thí dụ logic:

~~~java
// Snippet minh họa bên trong một vòng có thể throw Exception.
int index = barrier.await();
if (index == 0) {
    logRoundCompleted();
}
// Không đảm bảo logRoundCompleted() xong trước code của workers khác.
~~~

Nếu cần phát một immutable snapshot vào đầu vòng kế tiếp, hãy xuất bản nó trong barrier action (hoặc thêm một điểm đồng bộ thứ hai sau thao tác leader).

## 6. Barrier action: chạy khi đủ parties, trước khi mở cổng

Constructor `new CyclicBarrier(parties, barrierAction)` cho phép đăng ký một `Runnable` được thực hiện **một lần trên mỗi generation thành công**, khi thread cuối đến và **trước khi các threads còn lại được giải phóng**.

Vai trò điển hình:

- Gộp kết quả tạm của các worker.
- Đổi buffer `next/current` cho vòng kế tiếp.
- Kiểm tra bất biến cuối vòng.
- Tính/ghi nhận thống kê của từng round.
- Reset những dữ liệu thuộc vòng vừa kết thúc, nếu việc reset thực sự diễn ra sau khi mọi worker ngừng dùng chúng.

**Không phải một task chạy trên “barrier thread” riêng.** Barrier action được chạy bởi **last-arriving worker**. Nếu action block lâu, chính worker đó và các waiter đều bị giữ, nên tổng latency vòng tăng. Không thực hiện network I/O vô hạn, lấy lock phức tạp hay chờ một worker khác đang ở cùng barrier trong action.

### Ví dụ 3 — đổi double buffer ở ranh giới vòng

Tạo `DoubleBufferBarrier.java` (Java 17+):

~~~java
import java.util.Arrays;
import java.util.concurrent.CyclicBarrier;

public class DoubleBufferBarrier {
    static final class State {
        int[] current = new int[4];
        int[] next = new int[4];
        int completedRounds;
    }

    public static void main(String[] args) throws InterruptedException {
        State state = new State();

        CyclicBarrier barrier = new CyclicBarrier(4, () -> {
            state.current = state.next;
            state.next = new int[4];
            state.completedRounds++;
        });

        Thread[] workers = new Thread[4];
        for (int i = 0; i < workers.length; i++) {
            final int slot = i;
            workers[i] = new Thread(() -> {
                try {
                    for (int round = 0; round < 3; round++) {
                        state.next[slot] = state.current[slot] + 1;
                        barrier.await();
                    }
                } catch (Exception failure) {
                    throw new IllegalStateException(failure);
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("completed rounds = "
                + state.completedRounds);
        System.out.println("values = "
                + Arrays.toString(state.current));
    }
}
~~~

Chạy:

~~~bash
javac DoubleBufferBarrier.java
java DoubleBufferBarrier
~~~

Đầu ra xác định:

~~~text
completed rounds = 3
values = [3, 3, 3, 3]
~~~

Mỗi worker chỉ sửa `state.next[slot]` của mình trước `await`. Khi cả bốn đến, action đổi tham chiếu buffer và tạo buffer trống cho vòng mới. Các worker chỉ bắt đầu round tiếp sau khi action hoàn tất nên đọc được buffer mới. Sau ba rounds, tất cả giá trị bằng 3.

Đây là phép cập nhật một giá trị trên mỗi slot, không phải bài toán numerical stencil phức tạp. Với thuật toán mà mỗi ô mới phụ thuộc **hàng xóm**, các worker cũng phải đọc **chỉ từ current** và ghi **chỉ vào next** trong một vòng, tránh sửa current khi worker khác còn đọc.

### Không phải mọi mutation đều tự có tính nhất quán

Việc `state.current`/`state.next` là field thường vẫn phù hợp **trong phạm vi đồng bộ của barrier**: các hành động trước `await` được đồng bộ với barrier action và những hành động sau successful `await`. Nếu một thread ngoài barrier muốn đọc snapshot trong lúc workers còn đang tính, thread ấy không được bảo đảm đồng bộ chỉ nhờ barrier; cần safe publication/lock/volatile/immutable snapshot riêng.

## 7. Java Memory Model: happens-before qua barrier

Một điểm nhiều người bỏ qua: `CyclicBarrier` cung cấp quan hệ *memory consistency* trong Javadoc:

> Những hành động trong một thread **trước khi gọi `await()`** *happen-before* những hành động thuộc **barrier action**; những hành động của barrier action *happen-before* những hành động **sau khi `await()` trả về thành công** ở các thread khác.

Sơ đồ:

~~~text
Worker 1: write result[0] -----+
Worker 2: write result[1] -----+--> all await()
Worker 3: write result[2] -----+
                                     |
                                     v
                               barrierAction
                              đọc toàn bộ result
                              cập nhật next state
                                     |
                               happens-before
                                     v
                       workers tiếp tục sau await
                       đọc state đã công bố
~~~

Đây là lý do `ThreeRoundsBarrier` có thể dùng từng slot của một `int[]` mà không cần làm từng slot thành `AtomicInteger`, **nếu ownership của slot và giai đoạn được quản lý đúng**.

Không suy diễn:

- Barrier tự bảo vệ một shared counter khi nhiều worker `counter++` trước `await`. Các lần `++` vẫn cạnh tranh và có lost update.
- Những ghi **sau await** của hai thread tự được serialize. Barrier đã mở, threads lại chạy song song.
- Thread thứ ba không hề tham gia barrier được bảo vệ cho mọi lần đọc state.
- I/O ngoài JVM hoặc transaction database tự có commit/visibility chỉ vì Java thread đã đi qua barrier.
- Khi barrier **broken** và `await` ném exception, code có thể xử lý như một successful phase. Phải coi generation lỗi là không hoàn chỉnh.

Nếu một worker ghi nhiều ô, một thread khác đọc những ô đó **trước khi đủ parties** thông qua đường không được đồng bộ, data race vẫn có thể xảy ra. Barrier chỉ đúng khi mỗi giai đoạn thực sự tuân thủ giới hạn ownership của nó.

## 8. Barrier bị broken nghĩa là gì?

Trạng thái *broken* xuất hiện khi một generation không thể hoàn thành theo protocol. Các nguyên nhân thường gặp:

- Một thread đang chờ tại barrier bị `interrupt()`.
- Một thread gọi timed `await` và **hết thời gian** trước khi đủ parties.
- `barrierAction` ném unchecked exception hoặc error.
- Coordinator gọi `reset()` khi đang có các waiter.
- Một số tình huống lỗi đồng bộ khác theo hợp đồng API.

`CyclicBarrier` dùng mô hình **all-or-none breakage**: khi một waiter thất bại kiểu interrupt/timeout, các waiter còn lại trong generation ấy không nên tiếp tục như thể toàn bộ nhóm thành công; chúng thường nhận `BrokenBarrierException`.

Khi barrier broken:

- `isBroken() == true`.
- Các lời gọi `await` tiếp theo **ném `BrokenBarrierException`** thay vì chờ một generation bình thường (cho tới khi có reset).
- Những threads đang chờ được đánh thức bằng kết quả lỗi.
- Barrier **không tự hồi phục** chỉ vì một worker mới đến.
- Cần quyết định toàn round đã thất bại, thu hồi phần việc hoặc reset theo một coordinator rõ ràng.

### Phân biệt ba exception thường gặp

| Exception | Ai nhận, trong hoàn cảnh nào? |
| --- | --- |
| `InterruptedException` | Worker đang `await` bị interrupt (hoặc vào lúc còn interrupt flag) và call phản ứng với interrupt |
| `TimeoutException` | Worker gọi `await(timeout,unit)` hết thời hạn |
| `BrokenBarrierException` | Worker khác trong nhóm đã làm barrier broken, hoặc caller đến khi barrier đang broken |

CyclicBarrier còn có thể chuyển unchecked exception từ `barrierAction` qua thread thực hiện action. Không “chữa” exception của một worker bằng cách cho worker ấy tiếp tục vòng mới trong khi cả nhóm vẫn broken.

## 9. Ví dụ 4 — timeout phá barrier, reset rồi dùng lại

Tạo `BarrierTimeoutReset.java` (Java 17+):

~~~java
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierTimeoutReset {
    public static void main(String[] args) throws Exception {
        AtomicInteger actions = new AtomicInteger();
        CyclicBarrier barrier = new CyclicBarrier(
                2, actions::incrementAndGet);

        boolean timedOut = false;
        try {
            // Chỉ main tới: không có party thứ hai.
            barrier.await(50, TimeUnit.MILLISECONDS);
        } catch (TimeoutException expected) {
            timedOut = true;
        }

        System.out.println("timed out = " + timedOut);
        System.out.println("broken before reset = "
                + barrier.isBroken());

        barrier.reset();
        System.out.println("broken after reset = "
                + barrier.isBroken());

        AtomicInteger successes = new AtomicInteger();
        Runnable workerTask = () -> {
            try {
                barrier.await();
                successes.incrementAndGet();
            } catch (Exception failure) {
                throw new IllegalStateException(failure);
            }
        };

        Thread a = new Thread(workerTask);
        Thread b = new Thread(workerTask);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("successful await calls = "
                + successes.get());
        System.out.println("actions = " + actions.get());
    }
}
~~~

Chạy:

~~~bash
javac BarrierTimeoutReset.java
java BarrierTimeoutReset
~~~

Stdout:

~~~text
timed out = true
broken before reset = true
broken after reset = false
successful await calls = 2
actions = 1
~~~

Lần `await(50 ms)` đầu không có party thứ hai nên **chắc chắn** timeout; barrier broken. `reset()` tạo generation mới; hai threads của lượt sau cùng chờ và cùng thành công, action chạy một lần.

Đây là demo **reset có điều phối**, không chứng minh có thể reset bất kỳ lúc nào trong hệ thống thật. Nếu workers của generation cũ vẫn đang chạy/phục hồi, gọi reset quá sớm có thể khiến các threads ấy rơi vào generation khác, mất đồng bộ với công việc của nhóm.

### Timeout của một waiter ảnh hưởng cả nhóm

Nếu một worker gặp timeout và phá barrier, những worker khác đã đang đợi ở đó có thể nhận `BrokenBarrierException`. Vì vậy timed await là **timeout ở cấp protocol của nhóm**, không phải chỉ caller tự từ bỏ chờ mà tất cả những người khác sẽ tiếp tục thành công theo lịch cũ.

Đây là khác biệt quan trọng với `Future.get(timeout)`: timeout của một lần đợi Future **không tự hủy computation**; timeout của `CyclicBarrier.await` có thể **làm cả generation broken**.

## 10. Ví dụ 5 — interrupt một waiter làm waiter khác nhận BrokenBarrierException

Để minh họa tính *all-or-none*, dùng `parties=3` nhưng **chỉ tạo hai waiters**. Khi cả hai đang chờ, main ngắt thread A. A nhận `InterruptedException`; B thức dậy với `BrokenBarrierException`.

Tạo `BarrierInterruptDemo.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;

public class BarrierInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        CyclicBarrier barrier = new CyclicBarrier(3);
        List<String> outcomes =
                Collections.synchronizedList(new ArrayList<>());

        Thread a = new Thread(() -> {
            try {
                barrier.await();
                outcomes.add("A-success");
            } catch (InterruptedException expected) {
                outcomes.add("A-interrupted");
                Thread.currentThread().interrupt();
            } catch (BrokenBarrierException ex) {
                outcomes.add("A-broken");
            }
        });

        Thread b = new Thread(() -> {
            try {
                barrier.await();
                outcomes.add("B-success");
            } catch (InterruptedException ex) {
                outcomes.add("B-interrupted");
                Thread.currentThread().interrupt();
            } catch (BrokenBarrierException expected) {
                outcomes.add("B-broken");
            }
        });

        a.start();
        b.start();

        // Chỉ có hai threads, nên barrier(3) chưa thể mở.
        while (barrier.getNumberWaiting() != 2) {
            Thread.yield();
        }
        a.interrupt();

        a.join();
        b.join();
        Collections.sort(outcomes);

        System.out.println("outcomes = " + outcomes);
        System.out.println("broken = " + barrier.isBroken());
        System.out.println("number waiting = "
                + barrier.getNumberWaiting());
    }
}
~~~

Chạy:

~~~bash
javac BarrierInterruptDemo.java
java BarrierInterruptDemo
~~~

Stdout khi không có interruption ngoài chương trình:

~~~text
outcomes = [A-interrupted, B-broken]
broken = true
number waiting = 0
~~~

Vòng `while(getNumberWaiting()!=2)` chỉ dùng để **điều phối demo**, không phải mẫu chờ tốt cho production: nó có thể spin CPU nếu worker không được scheduled. Test suite thực tế nên có **deadline** và nhánh cleanup/fail-fast, không đợi vô hạn dựa vào metric. `getNumberWaiting()` là thông tin hiện trạng, không tạo cơ chế đợi/notification tự thân.

A bị interrupt khi đang chờ → chính A nhận `InterruptedException` và restore flag; B nhận `BrokenBarrierException`. **Cả hai** đều không được coi là đã hoàn thành successful round. Main có thể quyết định bỏ vòng, báo lỗi hoặc tạo protocol reset phù hợp.

## 11. Barrier action có thể ném exception: generation bị phá

Barrier action là một phần của giao thức. Nếu action thất bại, các worker không được phép tiếp tục như đã hoàn thành barrier thành công.

Theo Javadoc:

- Barrier action chạy bởi **thread đến cuối**.
- Nếu action thất bại vì exception, barrier trở thành **broken**.
- Exception từ action được truyền trong thread chạy action.
- Những waiter khác được giải phóng bằng `BrokenBarrierException`.

### Ví dụ 6 — action lỗi và trạng thái broken

Tạo `BarrierActionFailure.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;

public class BarrierActionFailure {
    public static void main(String[] args) throws InterruptedException {
        CyclicBarrier barrier = new CyclicBarrier(2, () -> {
            throw new IllegalStateException("action failed");
        });

        List<String> outcomes =
                Collections.synchronizedList(new ArrayList<>());

        Runnable waiter = () -> {
            try {
                barrier.await();
                outcomes.add("success");
            } catch (InterruptedException e) {
                outcomes.add("InterruptedException");
                Thread.currentThread().interrupt();
            } catch (BrokenBarrierException e) {
                outcomes.add("BrokenBarrierException");
            } catch (IllegalStateException e) {
                outcomes.add("IllegalStateException");
            }
        };

        Thread a = new Thread(waiter);
        Thread b = new Thread(waiter);
        a.start();
        b.start();
        a.join();
        b.join();

        Collections.sort(outcomes);
        System.out.println("outcomes = " + outcomes);
        System.out.println("broken = " + barrier.isBroken());
    }
}
~~~

Chạy:

~~~bash
javac BarrierActionFailure.java
java BarrierActionFailure
~~~

Stdout:

~~~text
outcomes = [BrokenBarrierException, IllegalStateException]
broken = true
~~~

Hai threads đến barrier. Last arriver chạy action và nhận `IllegalStateException`; thread còn lại thức dậy với `BrokenBarrierException`. Action ném exception trước khi hoàn tất thành công nên **generation bị phá**. Dữ liệu vòng đang tính cần được đánh dấu **failed**, không phát ra như một snapshot hợp lệ.

### Barrier action nên làm gì?

Nên là thao tác **ngắn, xác định, biết xử lý lỗi** như đổi buffer, gộp một mảng hoặc kiểm tra invariant. Với công việc tốn thời gian hoặc có I/O, cần cân nhắc thiết kế khác: action chạy dưới thread worker, toàn bộ nhóm đợi action xong. Nếu action đang giữ lock hoặc chờ một task do chính worker còn đang đợi barrier đảm nhiệm, có thể kẹt.

Đừng dùng `try { ... } catch (Exception ignored) { }` để giữ barrier chạy vô hạn khi dữ liệu đã lỗi. Có thể catch một lỗi **được định nghĩa là recoverable** và ghi trạng thái vòng, nhưng failure policy phải rõ ràng.

## 12. reset() không phải nút “chữa deadlock” tự động

`reset()` đưa barrier sang generation mới. Nhưng những worker **đang đợi** sẽ nhận `BrokenBarrierException`, vì generation mà họ tham gia đã bị phá.

Sai lầm:

~~~java
// Snippet về hành vi nguy hiểm.
if (barrier.getNumberWaiting() > 0) {
    barrier.reset(); // Mọi waiter hiện hữu có thể nhận lỗi.
}
~~~

Không được gọi reset định kỳ chỉ vì thấy còn waiters; bản chất barrier là **chờ các parties**. Nếu một worker chậm, reset gây hủy luôn phase; nếu caller không xử lý exception, cả nhóm có thể rơi vào trạng thái không đồng bộ.

Protocol hồi phục gợi ý:

1. Coordinator nhận biết **đã broken** hoặc round bị hủy.
2. Dừng admission vào round mới, yêu cầu tất cả worker xử lý lỗi và **rời wait**.
3. Chờ/ack các worker thuộc generation lỗi, phân loại dữ liệu dở dang.
4. Chỉ khi nhóm đã thống nhất trạng thái, cân nhắc `reset()` hoặc **tạo barrier mới** cho team mới.
5. Tiếp tục từ một state nhất quán, không “chắp” dữ liệu của hai rounds.
6. Nếu số participants thay đổi, `Phaser` hoặc tái cấu trúc worker team thường thích hợp hơn.

Việc đợi mọi worker rời một generation lỗi trước reset là một **quy tắc thiết kế an toàn của ứng dụng**, không phải điều kiện bắt buộc Java API để gọi reset. Ý chính: tránh trộn các nhóm/rounds khi có race giữa recovery và arrivals.

## 13. Một thread không đến đủ barrier: deadlock hoặc chờ vô hạn

`await()` bản thường **không có timeout**. Nếu cấu hình parties=4 nhưng chỉ có 3 workers thật sự gọi await ở một vòng, ba worker có thể chờ mãi.

Nguyên nhân:

- Một worker bị lỗi trước `await`.
- Một worker tự `return` sớm vì điều kiện nghiệp vụ, không báo cho nhóm.
- Số parties cấu hình không khớp số threads đang active.
- Một worker đợi lock mà worker khác giữ khi đang chờ barrier.
- Executor có **ít worker threads hơn parties**, khiến tasks chưa được chạy vì các worker đang chạy đều bị chặn ở barrier.
- Tác vụ bị cancel/interrupted, nhưng code bắt lỗi sai và không báo cho coordinator.
- Một worker gọi `await` hai lần trong một vòng hoặc bỏ qua một round, gây sai phase matching.

### Ví dụ anti-pattern: pool có hai worker nhưng barrier cần ba parties

~~~java
// SAI: demo cấu trúc, đừng chạy rồi chờ Future.get() vô hạn.
ExecutorService pool = Executors.newFixedThreadPool(2);
CyclicBarrier barrier = new CyclicBarrier(3);

for (int i = 0; i < 3; i++) {
    pool.submit(() -> {
        barrier.await();
        return null;
    });
}
~~~

Hai tasks đầu đang chạy và chờ barrier; task thứ ba nằm ở queue của executor vì pool chỉ có 2 workers. Không có worker rảnh để chạy task thứ ba, nên barrier không đủ parties. Đây là **thread-pool starvation deadlock** do thiết kế scheduling, không phải lỗi implementation `CyclicBarrier`.

**Cách sửa:** đảm bảo có **ít nhất số worker có thể đến barrier đồng thời** (hoặc thiết kế lại task scheduling để không block hết pool), và theo dõi exceptions/timeouts. Nếu tasks còn phụ thuộc locks/I/O, chỉ tăng pool size có thể chưa giải quyết nguyên nhân.

## 14. Ví dụ 7 — ExecutorService đủ worker để mở barrier

Tạo `BarrierExecutorPool.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierExecutorPool {
    public static void main(String[] args) throws Exception {
        AtomicInteger actions = new AtomicInteger();
        CyclicBarrier barrier = new CyclicBarrier(
                3, actions::incrementAndGet);

        ExecutorService pool = Executors.newFixedThreadPool(3);
        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                futures.add(pool.submit(() -> barrier.await()));
            }

            List<Integer> indices = new ArrayList<>();
            for (Future<Integer> future : futures) {
                indices.add(future.get());
            }
            Collections.sort(indices);

            System.out.println("indices = " + indices);
            System.out.println("actions = " + actions.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac BarrierExecutorPool.java
java BarrierExecutorPool
~~~

Stdout:

~~~text
indices = [0, 1, 2]
actions = 1
~~~

Có đúng ba worker slots cho ba tasks, nên mỗi task có cơ hội đến barrier. Khi party thứ ba đến, action tăng counter, ba `await` trả về các arrival indices `0,1,2` (sau sort). `Future.get()` chờ cả ba tasks trước khi in kết quả.

**Phạm vi demo:** Không có task nào cố tình lỗi; đây không phải mẫu production có deadline toàn diện. Trong chương trình thật, dùng `get(timeout)`/timed `await` và định nghĩa nhánh cancellation, error propagation, shutdown. Nếu executor có pool size đúng 3 nhưng tasks đợi lẫn nhau ở lock hoặc external resource, barrier vẫn có thể kẹt.

## 15. CyclicBarrier khác CountDownLatch và Phaser

| Tiêu chí | `CyclicBarrier` | `CountDownLatch` | `Phaser` |
| --- | --- | --- | --- |
| Mục tiêu chính | Các parties **cùng đến một điểm hẹn** | Chờ một số events/countdown | Đồng bộ nhiều phases, participants linh hoạt |
| Có reusable tự động? | **Có**, sau một vòng thành công | **Không**, count về 0 rồi latch không reset | **Có**, phase tăng theo mỗi advance |
| Số participants | Cố định khi tạo | Count cố định (nhưng thread countdown có thể khác thread chờ) | Có thể register/deregister động |
| Thread đến có phải chờ? | `await()` chờ | `countDown()` **không chờ**; `await()` của observer mới chờ | `arrive()` không chờ; `arriveAndAwaitAdvance()` chờ |
| Hành động ở ranh giới | `barrierAction` | Không có callback nội tại | Có thể override `onAdvance(...)` |
| Failure khi chờ | Interrupted/timeout có thể làm **broken** toàn barrier | Thread đợi bị interrupt không tự “phá latch” | Có protocol termination/interruptible wait riêng |
| Hỗ trợ giảm parties khi worker rời | Không | Không áp dụng theo mô hình party | `arriveAndDeregister()` |
| Có phase number truy cập trực tiếp? | Không | Không | `getPhase()` |
| Dùng khi | Team ổn định, rounds đồng bộ | One-shot start gate hoặc completion latch | Team/phases linh hoạt, công việc phân đợt phức tạp |

### CountDownLatch: một lần, phân biệt thread báo và thread chờ

~~~java
// Snippet minh họa, không phải chương trình độc lập.
CountDownLatch done = new CountDownLatch(3);
worker1: done.countDown();
worker2: done.countDown();
worker3: done.countDown();
coordinator: done.await();
~~~

Các calls `countDown()` **không block**. Một coordinator có thể đợi ba events hoàn tất mà không yêu cầu workers đồng thời chờ cùng mốc. Latch khi đếm về 0 sẽ giữ trạng thái open; không trở lại 3. Muốn một vòng mới phải tạo latch mới.

### Phaser: parties linh hoạt và các phases

Với `Phaser`, threads có thể `register`, `arriveAndAwaitAdvance` và `arriveAndDeregister`. Nó phù hợp hơn nếu một worker cần rời team giữa các phases hoặc số participants thay đổi. `Phaser` không phải drop-in replacement: cần thiết kế registration/deregistration và failure policy riêng.

Ví dụ cấu trúc:

~~~java
// Snippet API, không phải chương trình độc lập.
Phaser phaser = new Phaser(2);
phaser.arriveAndAwaitAdvance();
phaser.arriveAndDeregister();
~~~

Không tự động gọi `reset` trên CyclicBarrier để giả lập `arriveAndDeregister`. `reset` thay generation nhưng **không đổi** `getParties()` và gây `BrokenBarrierException` cho waiters hiện hữu.

## 16. Khi nào barrier không cần thiết?

Không cần CyclicBarrier nếu:

- Tasks độc lập và có thể kết thúc bất kỳ thứ tự nào; caller chỉ cần `invokeAll` hoặc nhiều `Future.get`.
- Một thread đợi N operations trả kết quả một lần; `CountDownLatch` thường rõ hơn.
- Cần producer gửi work liên tục không theo nhịp chung; dùng `BlockingQueue`/completion protocol.
- Cần “nhiều threads cùng bắt đầu một lúc” ở test duy nhất; một start latch cũng có thể phù hợp hơn.
- Team co giãn liên tục; cố định parties khiến việc thêm/bớt worker khó quản lý.
- Chỉ có một thread thực hiện toàn bộ các bước; barrier không mang lại song song.
- Nhiệm vụ sử dụng async callbacks, không có một nhóm blocking workers ổn định; barrier có thể gây starvation nếu mỗi thread vừa chờ vừa giữ scarce executor worker.

Không phải cứ thấy “làm việc theo vòng” là CyclicBarrier luôn tối ưu. Synchronizer nên phản ánh **quan hệ dependency thật** giữa các bước.

## 17. Cần bảo đảm điều gì trước và sau await?

Một checklist cho mỗi worker:

**Trước await:**

- Hoàn thành việc tính cho **phần dữ liệu thuộc quyền sở hữu** trong round.
- Không giữ lock mà barrier action hoặc worker khác cần để đến barrier.
- Không bỏ cuộc âm thầm; nếu lỗi, báo coordinator để cả nhóm biết cần cancel/reset.
- Không cập nhật state mà worker khác vẫn đang đọc trong round nếu chưa có protocol.
- Kiểm tra cancellation/timeout nếu round có deadline.

**Tại await:**

- Gọi **đúng một lần** cho mỗi round đã thiết kế.
- Dùng timed `await` nếu cần deadline; hiểu timeout của một party sẽ ảnh hưởng cả generation.
- Xử lý riêng `InterruptedException`, `TimeoutException`, `BrokenBarrierException`.
- Không nuốt exception rồi tiếp tục round tiếp như thể barrier thành công.

**Sau successful await:**

- Chỉ khi barrier action đã hoàn tất bình thường, đọc state được publication cho vòng mới.
- Không mặc định tất cả workers sẽ tiếp tục đồng thời hoặc theo thứ tự cố định.
- Không dùng `await` return index để suy ra permanent worker ID.
- Chuẩn bị dữ liệu vòng tiếp và tham gia generation sau theo cùng protocol.

Một pattern có xử lý lỗi:

~~~java
// Snippet minh họa trong một worker loop.
try {
    computeRound();
    barrier.await(2, TimeUnit.SECONDS);
    usePublishedStateForNextRound();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    notifyCoordinatorOfFailure(e);
    return;
} catch (TimeoutException | BrokenBarrierException e) {
    notifyCoordinatorOfFailure(e);
    return;
}
~~~

Các method `computeRound`, `usePublishedStateForNextRound`, `notifyCoordinatorOfFailure` là nghiệp vụ giả định; snippet không biên dịch độc lập. Trong production, coordinator phải biết tất cả workers sẽ thoát và xử lý failed round, không chỉ nhận log rồi tiếp tục dùng shared state dở dang.

## 18. Lỗi thường gặp khi dùng CyclicBarrier

| Sai lầm | Hậu quả | Cách tiếp cận |
| --- | --- | --- |
| Đặt parties=4 nhưng chỉ chạy 3 workers | `await` có thể chờ vô hạn | Khớp số parties và active workers |
| Dùng fixed thread pool 2 cho barrier 3 | Worker pool bị starvation deadlock | Đảm bảo capacity đủ hoặc đổi thiết kế |
| Một worker `return` sớm trước await | Nhóm còn lại kẹt | Báo lỗi và cancel/break protocol |
| Gọi `await` khác số lần giữa workers | Lệch generation, ghép sai các rounds | Quy định vòng lặp, membership thống nhất |
| Gọi `reset` sau **mỗi successful round** | Không cần và có thể phá next generation | Để barrier tự tái sử dụng |
| Gọi reset khi còn waiter rồi coi là success | Waiters nhận `BrokenBarrierException` | Recovery coordinator + consistent state |
| Catch `BrokenBarrierException` rồi tiếp tục tính | Có thể dùng partial data của failed round | Thoát/báo lỗi/restart theo protocol |
| Đặt I/O/blocking dài vào barrier action | Cả nhóm chờ action, tăng latency | Action ngắn, rõ và được kiểm soát |
| Nghĩ `arrival index 0` là leader vĩnh viễn | Last arriver thay đổi theo round | Không gắn với worker identity |
| Leader làm việc **sau await** rồi nghĩ nhóm đã đợi | Workers khác có thể chạy trước khi leader xong | Dùng barrier action hoặc barrier thứ hai |
| Nhiều workers `counter++` trước await | Data race/lost update | Slot riêng/atomic/lock, rồi reduce |
| Shared mutable state đọc ở ngoài barrier | Không có JMM visibility tự động cho thread ngoài | Safe publication riêng |
| Coi timeout chỉ ảnh hưởng caller | Barrier generation có thể broken cho mọi waiter | Có group failure policy |
| Không kiểm tra task errors từ Future | Silent failure làm thiếu party | Thu `ExecutionException`, cancel nhóm |
| Barrier action ném exception không xử lý | Generation broken | Theo dõi/cancel/recovery |
| Dùng `getNumberWaiting()` làm gate chính xác | Snapshot thay đổi theo timing | Dùng protocol/latch/timeout khi test |
| Không join workers khi chương trình kết thúc | Main có thể đóng tài nguyên quá sớm | `join`/`Future.get` và shutdown phối hợp |
| Dùng reset để giảm parties | Parties cố định, reset không deregister | `Phaser` khi membership linh hoạt |

## 19. Test và quan sát barrier trong thực tế

### A. Thực hiện test có kiểm soát

Các ví dụ trên cố tình tránh test dựa vào `Thread.sleep(100)` rồi kết luận “đã chờ đủ”. Với dữ liệu thời gian thực tế, scheduling không có deadline hard real-time.

Đối với automated test production:

1. Dùng `CountDownLatch` để xác nhận task đã vào đoạn cần kiểm tra.
2. Dùng `await(timeout, unit)` để test không treo vô hạn.
3. Nếu phải thử trường hợp thiếu party, chuẩn bị timeout và cleanup rõ.
4. Đảm bảo gọi `join`/`Future.get` với timeout thích hợp.
5. Trong `finally`, hủy các tasks còn sống và đóng executor do test sở hữu.
6. Không giả định thứ tự threads; assert **counts, sets và state cuối**.
7. Với exception, assert **đường lỗi chính xác** của các waiter và trạng thái `isBroken`.
8. Không dùng một global/static CyclicBarrier chia sẻ giữa các test cases độc lập.

### B. Metrics đáng theo dõi

- Số rounds **hoàn tất thành công**, không chỉ số vòng được bắt đầu.
- Thời gian workers chờ ở barrier theo từng round.
- Slowest worker trong nhóm, và sự chênh lệch thời gian hoàn thành round.
- Số lần timeout/interruption/broken barrier.
- Barrier action latency và failures.
- Số members đang active, số parties cấu hình.
- Số tasks bị hủy hoặc còn đang đợi sau lỗi.
- Thread pool active/queued counts để phát hiện starvation.
- Tổng thời gian toàn workflow, data validity của mỗi round.
- Lần thành công cuối cùng, không chỉ “worker thread còn sống”.

### C. `getNumberWaiting` và `isBroken` không phải một transaction

`getNumberWaiting()` cho biết số parties đang đợi ở thời điểm gọi, nhưng các threads có thể đến/rời ngay sau đó. `isBroken()` cũng có thể thay đổi khi reset/recovery. Không tạo algorithm dựa vào:

~~~java
// Sai nếu dùng như protocol đồng bộ duy nhất.
if (barrier.getNumberWaiting() == barrier.getParties() - 1) {
    // Cho rằng chắc mình sẽ là người đến cuối.
    barrier.await();
}
~~~

Giữa check và await có thể xuất hiện arrivals, breakage hoặc reset. Nếu thật sự cần xử lý công việc ở điểm cuối, **`barrierAction`** có hợp đồng đúng hơn so với nhìn số waiter rồi tự chọn leader.

## 20. Thiết kế vòng làm việc có lỗi: policy nên quyết định trước

Trong một ứng dụng thật, một round thất bại có thể do data validation, timeout hay interruption. Trước khi dùng barrier, hãy định nghĩa:

- **Bỏ toàn bộ round hay retry?** Nếu chỉ một phần worker đã ghi side effects, retry có idempotent không?
- **State tạm thuộc round nằm ở đâu?** Có thể bỏ buffer `next` và giữ `current` hợp lệ trước đó không?
- **Ai làm coordinator?** Ai quyết định reset/tạo lại barrier và khởi động đội workers?
- **Workers có thể rời nhóm không?** Nếu có, fixed parties dễ thành vấn đề; cân nhắc `Phaser`.
- **Có giới hạn thời gian không?** Timed await giúp phát hiện nhóm không đủ, nhưng chỉ có nghĩa nếu code có xử lý group failure.
- **Ngoại lệ trong worker truyền đi đâu?** Nếu task được submit bằng `ExecutorService.submit`, caller cần `Future.get` để thu `ExecutionException`; log mặc định có thể không biểu thị đầy đủ lỗi nghiệp vụ.
- **Tài nguyên và cleanup?** Dừng/cancel workers trước khi phá shared buffers hoặc đóng connections đang dùng.
- **Giai đoạn tiếp theo cần điều gì?** Có thể publish immutable snapshot, đổi buffer, hoặc báo lỗi đủ rõ để downstream không đọc dữ liệu dở dang.

Một pattern tốt cho iterative numerical state là double buffering: mọi worker đọc `current`, ghi những ô riêng trong `next`; barrier action đổi buffer **chỉ khi round hoàn tất**. Khi lỗi, coordinator giữ `current` của round đã xác nhận và bỏ `next` chưa hoàn thiện thay vì công bố snapshot nửa chừng.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** `CyclicBarrier(3)` có ba threads, mỗi thread gọi `await()` mỗi vòng. Barrier có cần `reset()` sau vòng thành công không?  
**Đáp án:** Không. Nó tự sẵn sàng cho generation sau khi ba parties đã đến và action (nếu có) hoàn tất.

**Câu 2.** `await()` có trả về giá trị không?  
**Đáp án:** Có, arrival index từ `parties-1` tới `0`. `0` là người đến cuối.

**Câu 3.** Một thread là index 0 ở round 1. Có chắc cũng là index 0 ở round 2 không?  
**Đáp án:** Không. Last arrival thay đổi theo scheduling và workload.

**Câu 4.** Barrier action chạy trên một thread riêng do JDK tạo ra?  
**Đáp án:** Không. Nó chạy trong thread đến cuối, trước khi các waiters được giải phóng.

**Câu 5.** Barrier action cập nhật một shared buffer; các worker sau successful await có được nhìn thấy thay đổi đó theo JMM không?  
**Đáp án:** Có, theo bảo đảm happens-before của barrier. Workers ngoài protocol vẫn cần đồng bộ phù hợp.

**Câu 6.** Ba workers cùng `counter++` trước await có an toàn vì barrier sau đó không?  
**Đáp án:** Không. Race trên `counter++` xảy ra trước barrier; cần atomic/lock hoặc mỗi worker ghi slot riêng.

**Câu 7.** `await(100, MILLISECONDS)` của một thread timeout trong lúc những threads khác đang đợi. Chỉ thread ấy gặp lỗi?  
**Đáp án:** Không. Barrier có thể broken; các waiters khác nhận `BrokenBarrierException`.

**Câu 8.** `barrier.reset()` có đổi số parties từ 4 thành 3 không?  
**Đáp án:** Không. Parties cố định; reset tạo generation mới và làm các waiters hiện tại nhận broken.

**Câu 9.** `ExecutorService.newFixedThreadPool(2)` chạy ba tasks, tất cả `await` trên barrier(3). Điều gì nguy hiểm?  
**Đáp án:** Hai tasks chạy và chờ; task thứ ba xếp hàng không có worker, gây thread-pool starvation deadlock.

**Câu 10.** Một worker ném exception trước await và tự return; hai workers khác chờ barrier(3). Có tự mở không?  
**Đáp án:** Không. Cần failure/cancellation protocol hoặc timeout; thiếu party có thể chờ vô hạn.

**Câu 11.** `barrierAction` ném `IllegalStateException`. Những waiter khác có tiếp tục như round thành công không?  
**Đáp án:** Không. Generation bị broken; last-arriving thread nhận exception, các waiters khác nhận `BrokenBarrierException`.

**Câu 12.** `CountDownLatch` và `CyclicBarrier` khác nhau điểm quan trọng nhất?  
**Đáp án:** Latch là countdown một lần, người `countDown` không chờ; CyclicBarrier là rendezvous của một nhóm cố định và tái sử dụng qua rounds.

**Câu 13.** Muốn worker có thể `arriveAndDeregister` khi hết việc, nên dùng gì?  
**Đáp án:** Cân nhắc `Phaser`; CyclicBarrier không có API deregister.

**Câu 14.** Một thread sau `await` có thể bắt đầu vòng kế trước khi thread khác hoàn tất logic sau `await` không?  
**Đáp án:** Có. Sau khi barrier mở, các workers tiếp tục đồng thời; chỉ logic **trước barrier** và barrier action được mốc ấy đồng bộ.

**Câu 15.** Có nên dùng `getNumberWaiting()` như một condition gate chính xác để quyết định leader của round không?  
**Đáp án:** Không. Đó là snapshot chịu concurrency; barrier action và arrival index theo hợp đồng phù hợp hơn.

## Tài liệu tham khảo Java SE 17

- [`CyclicBarrier` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): reusable barrier, barrier action, arrival index, all-or-none breakage, memory consistency.
- [`BrokenBarrierException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BrokenBarrierException.html): lỗi khi barrier bị phá hoặc reset.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ một lần, không reusable.
- [`Phaser` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): đăng ký/rời parties, phases và advance.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): pool workers, submit, Future và shutdown.
- [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): kết quả task, cancellation và exception.
- [`TimeUnit` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): đơn vị thời gian khi dùng timed await.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before và visibility.

**Ghi nhớ:** `CyclicBarrier` giúp **một nhóm worker cố định cùng hoàn thành từng vòng**, có thể lặp lại mà không reset sau mỗi vòng. Đặt barrier action tại ranh giới khi cần hợp nhất/đổi state, kiểm tra parties và executor capacity, rồi **xử lý timeout/interruption/broken barrier như thất bại của cả round** chứ không lặng lẽ cho các worker tiếp tục với dữ liệu chưa hoàn thiện.