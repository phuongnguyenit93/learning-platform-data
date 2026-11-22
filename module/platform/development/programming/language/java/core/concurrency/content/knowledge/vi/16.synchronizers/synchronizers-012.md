# Tránh deadlock do thiếu arrive(), countDown() hoặc release()

## 1. Mục tiêu học tập và phạm vi

Sau bài này, bạn có thể:

- Phân biệt **deadlock**, **chờ vô hạn vì thiếu tín hiệu**, **resource leak**, **starvation** và **broken barrier**. Không phải mọi thread đang WAITING đều chứng minh một vòng chờ deadlock theo nghĩa chặt.
- Hiểu vai trò của **CountDownLatch.countDown()**, **CyclicBarrier.await()**, **Phaser.arrive()/arriveAndDeregister()** và **Semaphore.release()** trong việc giúp thread khác tiến lên.
- Nhận diện các nhánh **return sớm**, **exception**, **interruption**, **timeout**, **task bị từ chối**, **task chưa start** khiến sự kiện hoàn tất không được báo.
- Dùng **try/finally**, đăng ký/bỏ đăng ký participant có kiểm soát, và **chỉ release permit khi acquire thành công**.
- Chọn **timeout, failure propagation, cancellation và abort policy** để hệ thống thoát khỏi chờ vô hạn, nhưng không nhầm timeout với việc sửa xong trạng thái hoặc rollback side effect.
- Phân biệt **phát tín hiệu task kết thúc** với **phát tín hiệu task thành công**; không gọi countDown hoặc arrive để giả mạo điều kiện nghiệp vụ chưa đạt.
- Chạy các chương trình Java 17+ minh họa liveness failure và cách tổ chức giao thức đúng, với stdout có thể kiểm chứng bằng latch, join và exception handling thay vì dựa vào Thread.sleep.

Đây là bài của **Synchronizers** trong **Java concurrency nói chung**. Các cơ chế liên quan riêng tới Spring đã có chương riêng và không được sử dụng ở đây.

## 2. Synchronizer không tự cứu một giao thức bị bỏ dở

Nhiều primitive chỉ hoạt động đúng khi **tất cả bên tham gia tuân thủ giao thức**. Chúng không có khả năng suy đoán rằng một thread đã thất bại, bị hủy, quên gọi completion hay làm mất permit.

~~~text
Thread A                              Thread B
--------                              --------
thực hiện công việc                   await tín hiệu
       |
       +-- thành công -> signal ----------> tiếp tục
       |
       +-- exception -> quên signal ------> vẫn chờ
       |
       +-- return sớm -> quên signal -----> vẫn chờ
~~~

Một trường hợp khác:

~~~text
Worker A: semaphore.acquire() -> giữ permit
          gặp lỗi rồi return, quên release()
Worker B: semaphore.acquire() -> không còn permit -> chờ
~~~

Cách xử lý phụ thuộc **ngữ nghĩa tín hiệu**:

- Nếu latch đại diện cho **“worker đã kết thúc, kể cả lỗi”**, hãy countDown trong finally và lưu lỗi ở một kênh riêng.
- Nếu latch đại diện cho **“tất cả bước đã đạt điều kiện thành công”**, không được countDown vô điều kiện trong finally rồi cho consumer tưởng đã thành công. Cần mô hình trạng thái FAILED, kênh báo lỗi hoặc thay đổi primitive/giao thức.
- Nếu Phaser có participant đã đăng ký nhưng worker không thể tiếp tục, việc deregister đúng lúc có thể ngăn kẹt pha; song phải chứng minh pha sau vẫn có ý nghĩa.
- Với semaphore, release chỉ khi permit thật sự đã được acquire theo hợp đồng; release dư tạo ra lỗi khác, có thể nghiêm trọng hơn việc chờ lâu.

**Mấu chốt:** xác định rõ ai phải phát tín hiệu, tín hiệu biểu diễn điều gì, và từng đường thoát thực thi làm gì.

## 3. “Deadlock” có đúng là tên của mọi ca treo?

Một chương trình chờ mãi có thể do nhiều dạng lỗi khác nhau:

| Hiện tượng | Ví dụ | Phân tích |
| --- | --- | --- |
| **Deadlock vòng chờ** | A giữ lock L, chờ B; B cần L mới có thể kết thúc | Có chu trình phụ thuộc tài nguyên |
| **Missing signal / liveness failure** | Latch count=1 nhưng không ai có khả năng countDown | Waiter mắc kẹt dù không thấy vòng khóa hai thread |
| **Broken barrier** | Một party timeout/interrupted trong CyclicBarrier.await() | Barrier bị broken; các waiter khác nhận BrokenBarrierException |
| **Permit leak** | Semaphore.acquire thành công nhưng không release | Permit khả dụng giảm, người chờ có thể bị kẹt |
| **Starvation** | Task giữ mọi worker rồi chờ task con trong cùng pool | Task con không được lịch chạy, dù không có hai monitor |
| **Live lock** | Nhiều thread liên tục nhường/đổi trạng thái nhưng không tiến triển | Có hoạt động, không có progress nghiệp vụ |

Các kiểu **WAITING**, **TIMED_WAITING** trong thread dump là dấu hiệu chẩn đoán, không phải chứng minh một loại lỗi. Một thread hoàn toàn có thể WAITING hợp lệ vì đang đợi sự kiện chưa đến.

### Wait-for graph

~~~text
A đợi B hoàn tất
B đợi khóa L do A đang giữ
     A --> B --> L --> A  : chu trình deadlock

C đợi latch count về 0
Không còn producer sở hữu trách nhiệm countDown
     C --> latch?        : chờ vĩnh viễn vì mất completion
~~~

Hai trường hợp đều ảnh hưởng liveness, nhưng khắc phục khác nhau: trường hợp một cần phá dependency/lock order; trường hợp hai cần sửa giao thức hoàn tất và báo lỗi.

## 4. CountDownLatch: thiếu countDown khiến await không kết thúc

**CountDownLatch(initialCount)** là synchronizer một lần. Mỗi countDown() làm counter giảm một (đến 0 thì dừng). **await()** chờ đến khi counter về 0; khi count đã về 0, các await tiếp theo đi qua.

~~~java
// Minh họa, không phải file độc lập:
CountDownLatch completed = new CountDownLatch(2);
workerA.start();
workerB.start();
completed.await();
~~~

Nếu workerA và workerB đều phải countDown một lần nhưng một bên return trước khi báo, completed.getCount() có thể mãi lớn hơn 0.

**Counter không tự giảm khi Thread kết thúc**, khi Runnable ném exception hoặc khi executor shutdown. Primitive không biết câu chuyện nghiệp vụ đằng sau biến completed.

### Nguyên nhân thường gặp

- countDown đặt cuối thân try, exception ném trước dòng đó.
- Một nhánh return ngay khi phát hiện lỗi đầu vào.
- Task chưa được submit do RejectedExecutionException nhưng coordinator vẫn cộng count của task ấy.
- Worker chết trước khi bắt đầu và coordinator không có chính sách bù/failure.
- Thread bị interrupt khi đang làm việc và handler thoát mà không báo completion.
- Đếm sai số lượng worker/giai đoạn: tạo latch count=5 nhưng thực tế chỉ có 4 người có trách nhiệm báo.
- Một bên tưởng bên kia sẽ countDown, nên không ai thực hiện.

**Bất biến cần xác định:** nếu latch đại diện cho N completion, phải có **N nghĩa vụ hoàn tất** và mỗi nghĩa vụ cần đi đến trạng thái kết thúc đúng một lần, kể cả đường lỗi đã được xử lý.

### finally không tự bảo đảm thành công

~~~java
// Mảnh code trong Runnable, không phải chương trình độc lập:
try {
    doWork();
} catch (RuntimeException failure) {
    recordFailure(failure);
} finally {
    completed.countDown();
}
~~~

Trong ví dụ này, countDown nghĩa **“đã kết thúc do thành công hoặc lỗi”**. Consumer sau await phải kiểm tra **recordFailure** hoặc trạng thái result. Nếu đặt tên latch là allSucceeded rồi countDown mọi đường lỗi, đó là giao thức sai.

## 5. Ví dụ 1: CountDownLatch báo hoàn tất, lỗi theo kênh riêng

Tệp **LatchFinallyDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class LatchFinallyDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch completed = new CountDownLatch(2);
        AtomicInteger succeeded = new AtomicInteger();
        AtomicInteger failed = new AtomicInteger();

        Runnable good = () -> {
            try {
                succeeded.incrementAndGet();
            } finally {
                completed.countDown();
            }
        };

        Runnable bad = () -> {
            try {
                throw new IllegalStateException("demo failure");
            } catch (IllegalStateException ex) {
                failed.incrementAndGet();
            } finally {
                completed.countDown();
            }
        };

        Thread first = new Thread(good, "good");
        Thread second = new Thread(bad, "bad");
        first.start();
        second.start();

        completed.await();
        first.join();
        second.join();

        System.out.println("remaining = " + completed.getCount());
        System.out.println("succeeded = " + succeeded.get());
        System.out.println("failed = " + failed.get());
        System.out.println("all succeeded = " + (failed.get() == 0));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LatchFinallyDemo.java
java LatchFinallyDemo
~~~

Stdout:

~~~text
remaining = 0
succeeded = 1
failed = 1
all succeeded = false
~~~

**Giải thích:**

1. Coordinator tạo latch count=2 theo hai nghĩa vụ completion.
2. Cả good và bad đều đưa countDown vào finally.
3. Task bad ném exception có chủ đích; catch ghi thất bại, finally vẫn báo **kết thúc**.
4. await hoàn tất khi count=0, không có busy waiting.
5. Thống kê riêng cho biết **không phải tất cả đã thành công**.
6. join đợi cả hai thread kết thúc trước khi in stdout, tạo điểm đọc kết quả rõ ràng.

### Khi không nên countDown trong finally?

Nếu tín hiệu là **“giai đoạn đã đạt điều kiện an toàn để tiếp tục”**, thất bại không được phát như thành công. Thiết kế đúng thường dùng **result/failure state** độc lập và coordinator kiểm tra nó sau latch, hoặc dùng Future để lấy kết quả/exception. Không sửa bug treo bằng cách cho downstream đi vào trạng thái thiếu dữ liệu.

## 6. Ví dụ 2: mô phỏng thiếu countDown với timeout có kiểm soát

Ví dụ sau không spawn một worker bí ẩn để làm chương trình treo. Ta tạo latch mà **không thread nào countDown**, rồi dùng overload có timeout để quan sát ngữ nghĩa mà không bị mắc vĩnh viễn.

Tệp **MissingLatchSignalDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class MissingLatchSignalDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch neverCompleted = new CountDownLatch(1);

        boolean completed =
                neverCompleted.await(15, TimeUnit.MILLISECONDS);

        System.out.println("completed = " + completed);
        System.out.println("remaining = " + neverCompleted.getCount());
    }
}
~~~

~~~bash
javac -encoding UTF-8 MissingLatchSignalDemo.java
java MissingLatchSignalDemo
~~~

Stdout:

~~~text
completed = false
remaining = 1
~~~

**Vì sao chính xác?** Không có đường code gọi countDown(), nên sau khoảng chờ có giới hạn, await(timeout) trả false và counter vẫn 1. **Timeout không làm count giảm**, không cấp phép tiếp tục logic thành công và không sửa lỗi mất completion.

Trong sản phẩm thật, timeout cần dẫn tới một chính sách rõ:

- Báo lỗi hoặc trả trạng thái **INCOMPLETE**.
- Cố cancel task còn tồn tại nếu task hỗ trợ hợp tác hủy.
- Thu thập diagnostics và tìm participant nào không báo.
- Retry khi nghiệp vụ cho phép, có backoff/idempotency.
- Không lặp timeout rồi tiếp tục chờ vô hạn nếu deadline của request đã hết.

**CountDownLatch không reset.** Nếu cần nhiều pha lặp hoặc số party động, xem CyclicBarrier/Phaser và các quy tắc khác bên dưới.

## 7. CountDownLatch và Future: cách xử lý exception tốt hơn

Nếu một nhóm task chạy trong ExecutorService và caller cần biết **kết quả riêng**, giữ danh sách **Future** thường tự nhiên hơn dùng một latch chỉ để biết completion.

~~~java
// Minh họa trong một method có ExecutorService pool:
Future<Integer> f = pool.submit(() -> calculate());
try {
    int result = f.get();
} catch (ExecutionException ex) {
    handleFailure(ex.getCause());
}
~~~

Đây không phải chương trình độc lập: calculate(), handleFailure(), pool và import được giả định. Future.get() có thể ném InterruptedException; nếu dùng timeout, còn có TimeoutException.

**Phân biệt:** Future có trạng thái **done** kể cả failure/cancellation. Caller phải kiểm tra get()/exception, không dựa vào isDone() để kết luận thành công.

### Bẫy: đếm nghĩa vụ trước khi task được nhận

~~~text
Coordinator tạo latch count=10
Executor chỉ nhận 8 task; 2 lần submit bị reject.
8 worker hoàn tất và countDown 8 lần.
Latch còn 2; không ai có trách nhiệm countDown.
~~~

Nếu vẫn muốn dùng latch, phải có contract rõ rằng **coordinator bù completion của task không được nhận** hoặc abort toàn bộ workflow. Không được phát tín hiệu thành công giả. Với các task bị reject, caller cần xử lý **RejectedExecutionException** ngay khi submit thay vì bỏ qua nó.

Một giải pháp khác là **chỉ tính các nghĩa vụ đã được chấp nhận** qua một cơ chế đăng ký động (Phaser) hoặc collection of Futures, nhưng phải giải quyết được race giữa register/start và đóng admission.

## 8. CyclicBarrier: thiếu một party có thể kẹt cả nhóm

**CyclicBarrier(parties)** tạo điểm gặp cho đúng số party cố định tại mỗi **generation**. Mỗi bên gọi **await()**; khi đủ parties, barrier trip, các thread được phép tiếp tục và barrier sẵn sàng dùng cho generation tiếp theo.

~~~text
CyclicBarrier(3)

Thread A: ... await() ---+
Thread B: ... await() ---+-- đủ 3 --> cùng tiếp tục
Thread C: ... await() ---+
~~~

Nếu C **không gọi await()** mà A/B đều gọi await() không timeout, các thread ấy có thể chờ mãi. Đó là lỗi giao thức participant. **CyclicBarrier không tự biết C đã chết** khi C chưa từng vào barrier.

### Khác CountDownLatch

| Thuộc tính | CountDownLatch | CyclicBarrier |
| --- | --- | --- |
| Số lượng | CountDown theo số completion | Số party cố định phải await trong một pha |
| Reuse | Không reset sau khi về 0 | Có thể dùng qua nhiều generation |
| Tín hiệu đến từ | Worker countDown | Mỗi party đến await |
| Lỗi/chờ thiếu party | Có thể chờ vô hạn | Có thể chờ vô hạn nếu không timeout/interruption |
| Timeout | await(timeout) trả boolean | await(timeout) có thể ném TimeoutException và làm barrier broken |
| Failure state | Không có built-in broken flag | có **isBroken()** |

**Không dùng countdown thay vì barrier chỉ vì đều có chữ “chờ”.** Một barrier đồng bộ các bên ở **cùng mốc pha**, còn latch cho phép một hoặc nhiều waiter quan sát một counter về 0.

### Vai trò của barrier action

Constructor CyclicBarrier có thể nhận một **Runnable barrierAction** chạy khi đủ parties, trước khi các party được giải phóng. Nếu action ném exception, có thể gây broken barrier. Không đặt side effect blocking dài trong barrier action rồi ngạc nhiên vì tất cả party đều bị kéo chậm.

## 9. Ví dụ 3: thiếu một party trong CyclicBarrier

Tệp **BarrierMissingPartyDemo.java**:

~~~java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class BarrierMissingPartyDemo {
    public static void main(String[] args) throws InterruptedException {
        CyclicBarrier barrier = new CyclicBarrier(2);
        AtomicBoolean timedOut = new AtomicBoolean();

        Thread onlyParticipant = new Thread(() -> {
            try {
                barrier.await(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                timedOut.set(true);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } catch (BrokenBarrierException ex) {
                throw new AssertionError("unexpected broken", ex);
            }
        });

        onlyParticipant.start();
        // Không có party thứ hai nào gọi await().
        onlyParticipant.join();

        System.out.println("timed out = " + timedOut.get());
        System.out.println("broken = " + barrier.isBroken());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BarrierMissingPartyDemo.java
java BarrierMissingPartyDemo
~~~

Stdout:

~~~text
timed out = true
broken = true
~~~

**Tại sao?**

- Barrier cần 2 party nhưng chỉ một thread tới await.
- Sau timeout, await ném TimeoutException và generation chuyển sang trạng thái broken.
- Main join thread rồi đọc flags.
- Không dùng Thread.sleep để “hy vọng” bắt kịp.
- Đầu ra minh họa đường lỗi, **không phải cách vận hành thành công** của barrier.

Nếu một thread đang await bị interrupt, barrier cũng có thể bị broken và các waiter khác nhận BrokenBarrierException. **Không được catch InterruptedException rồi im lặng bỏ qua** khi đồng đội đang trông chờ party đó.

### Timeout không tự làm các bên hoàn thành giai đoạn

Khi barrier broken, phải coi generation ấy thất bại. Có thể **reset()** trong một protocol tái khởi động có điều phối, nhưng reset tùy tiện trong lúc party khác còn dùng barrier gây lỗi logic. Thiết kế cần biết ai được quyền reset, ai hủy công việc cũ và lúc nào tất cả bên sẵn sàng bước vào generation mới.

## 10. Ví dụ 4: CyclicBarrier có đủ party, lặp hai pha

Tệp **BarrierTwoPhasesDemo.java**:

~~~java
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierTwoPhasesDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger trips = new AtomicInteger();
        CyclicBarrier barrier = new CyclicBarrier(
                2, trips::incrementAndGet
        );
        AtomicInteger completed = new AtomicInteger();

        Runnable worker = () -> {
            try {
                for (int phase = 0; phase < 2; phase++) {
                    // Thực hiện bước cục bộ rồi tới cùng barrier.
                    barrier.await(5, TimeUnit.SECONDS);
                    completed.incrementAndGet();
                }
            } catch (Exception ex) {
                throw new IllegalStateException("barrier failed", ex);
            }
        };

        Thread a = new Thread(worker, "a");
        Thread b = new Thread(worker, "b");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("barrier trips = " + trips.get());
        System.out.println("completed steps = " + completed.get());
        System.out.println("broken = " + barrier.isBroken());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BarrierTwoPhasesDemo.java
java BarrierTwoPhasesDemo
~~~

Stdout với môi trường xử lý bình thường và không bị interrupt từ bên ngoài:

~~~text
barrier trips = 2
completed steps = 4
broken = false
~~~

Cả a và b đều tới barrier đúng hai lần, nên action chạy hai lần; mỗi thread đi qua mỗi pha rồi tăng completed. **Thời lượng chờ không phải benchmark**; giới hạn 5 giây chỉ là đường thoát khi môi trường có vấn đề, không phải SLA thời gian cố định.

**Nếu một worker có thể rời workflow trước pha 2**, CyclicBarrier fixed parties có thể không phù hợp, trừ khi coordinator có protocol rõ để kết thúc hoặc khởi tạo nhóm mới. Dùng Phaser khi cần participant động.

## 11. Phaser: arrived, unarrived và registered parties

**Phaser** hỗ trợ đồng bộ hóa nhiều pha với **số party có thể thay đổi**. Một party có thể register, **arrive**, **arriveAndAwaitAdvance**, hoặc **arriveAndDeregister**.

| API | Ngữ nghĩa |
| --- | --- |
| register() | Đăng ký thêm một party |
| bulkRegister(n) | Đăng ký n party |
| arrive() | Báo party đã đến pha hiện tại, không chờ |
| arriveAndAwaitAdvance() | Báo đã đến và chờ pha chuyển |
| arriveAndDeregister() | Báo đến và rời khỏi nhóm party cho các pha sau |
| awaitAdvance(phase) | Chờ pha đổi, bản thân không thay arrive |
| awaitAdvanceInterruptibly(phase, timeout, unit) | Chờ có interrupt/timeout theo overload |
| forceTermination() | Buộc Phaser kết thúc, đánh thức bên chờ theo ngữ nghĩa termination |
| getRegisteredParties()/getUnarrivedParties() | Số party đăng ký/chưa arrive ở pha hiện tại |

**Khác biệt sống còn:** **awaitAdvance(phase) không tự gọi arrive()**. Nếu một party chỉ gọi awaitAdvance khi nó còn nghĩa vụ arrive mà không ai khác bù, phase có thể không tiến.

### Ví dụ các lỗi

~~~text
Phaser đăng ký 3 parties.
A gọi arrive().
B gọi arrive().
C exception trước arrive().
C không deregister.
=> unarrived vẫn còn 1, phase không advance.
~~~

Nếu một participant biến mất sau khi register và coordinator không có protocol phát hiện/bù, các waiter có thể mắc kẹt. **Phaser không tự đoán party đã chết**.

**Không register quá sớm:** nếu register trước khi có khả năng start worker và start thất bại, nghĩa vụ arrive vẫn tồn tại. Cần đặt nghĩa vụ register/start/deregister trong một scope có thể quản lý lỗi.

## 12. Phaser và finally: đúng nhưng không phải luôn cần thiết

Với worker chỉ tham gia một giai đoạn rồi rời, có thể:

~~~java
// Mảnh code minh họa; phaser đã được chia sẻ và đăng ký party.
try {
    doWork();
} finally {
    phaser.arriveAndDeregister();
}
~~~

Đây là mảnh code, cần doWork() và cơ chế start/exception phù hợp. finally đảm bảo worker không giữ party lâu hơn vòng đời dự kiến khi code đi qua đường thoát bình thường hoặc exception.

**Nhưng** nếu worker thất bại làm phase tiếp theo không còn an toàn, chỉ deregister rồi cho tất cả tiếp tục là sai về nghiệp vụ. Hãy lưu trạng thái FAILED, báo coordinator và hủy pha hoặc **forceTermination()** theo một protocol đã xác định.

### Lỗi gọi arrive hai lần

Một party đã gọi **arrive()** trong phase hiện tại **không được arrive thêm một lần cùng phase**. Đếm thừa có thể vi phạm giao thức của Phaser hoặc ném IllegalStateException khi số party/unarrived không hợp lệ. Nếu finally gọi arriveAndDeregister sau khi phần thân đã arrive(), phải kiểm soát trạng thái để **tránh double arrive**.

Dùng một **chỗ sở hữu trách nhiệm arrival** ở mỗi phase, thay vì nhiều nhánh cùng tự báo.

## 13. Ví dụ 5: Phaser với worker đăng ký trước khi start

Tệp **PhaserDeregisterDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Phaser;
import java.util.concurrent.atomic.AtomicInteger;

public class PhaserDeregisterDemo {
    public static void main(String[] args) throws InterruptedException {
        Phaser phaser = new Phaser(1); // Main là coordinator.
        AtomicInteger completed = new AtomicInteger();
        List<Thread> workers = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            phaser.register(); // Trách nhiệm của worker mới.
            Thread worker = new Thread(() -> {
                try {
                    completed.incrementAndGet();
                } finally {
                    phaser.arriveAndDeregister();
                }
            }, "worker-" + i);
            workers.add(worker);
            worker.start();
        }

        phaser.arriveAndAwaitAdvance();
        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("completed = " + completed.get());
        System.out.println(
                "registered parties = " + phaser.getRegisteredParties()
        );

        phaser.arriveAndDeregister(); // Coordinator rời Phaser.
    }
}
~~~

~~~bash
javac -encoding UTF-8 PhaserDeregisterDemo.java
java PhaserDeregisterDemo
~~~

Stdout:

~~~text
completed = 3
registered parties = 1
~~~

**Giải thích:**

- Main được đăng ký ngay từ new Phaser(1).
- Trước khi start từng worker, coordinator register nghĩa vụ của worker đó.
- Mỗi worker, kể cả khi logic phát sinh unchecked exception sau khi vào try, vẫn arriveAndDeregister ở finally.
- Main tới arriveAndAwaitAdvance, đợi các worker đã đăng ký cho phase hiện tại hoàn tất/deregister.
- Sau khi phase tiến, chỉ còn main đã đăng ký: registered parties = 1.
- Main deregister ở cuối; không còn participant nào.
- completed phản ánh ba worker đã xử lý phần minh họa.

**Giới hạn:** Ví dụ giả định start() thành công và không có lỗi fatal trước khi vào try. Ứng dụng thật cần xử lý trường hợp **Thread.start() thất bại**, không để party đã register tồn tại mà không có worker, và có coordinator failure policy.

### Nếu thread thất bại giữa nhiều phase

Khi có nhiều vòng, cần quy định worker được phép rời ở phase nào, liệu số party có thể giảm hay không, và một lỗi có làm kết quả của phase đó vô nghĩa không. **arriveAndDeregister** chỉ quản lý số người tham gia; nó không tự bù dữ liệu nghiệp vụ mà người rời chưa sản xuất.

## 14. Timeout của Phaser khác CyclicBarrier

**CyclicBarrier.await(timeout)** khi một party timeout thường **break barrier** và các waiter khác có đường nhận BrokenBarrierException.

Với **Phaser.awaitAdvanceInterruptibly(phase, timeout, unit)**, một thread timeout/interrupted **không tự làm Phaser terminated**, và phương thức chờ này **không tự thay nghĩa vụ arrive** của một party. Nếu lỗi điều phối vẫn tồn tại, các bên khác có thể tiếp tục bị kẹt.

Một chiến lược khi không thể tiếp tục:

1. Coordinator nhận TimeoutException hoặc InterruptedException.
2. Ghi nhận phase thất bại và ngừng cấp tác vụ mới cho phase đó.
3. Ra quyết định **forceTermination()** nếu toàn nhóm phải dừng.
4. Yêu cầu mọi worker hợp tác với dừng/hủy và giải phóng tài nguyên.
5. Tách phần **dừng chờ** khỏi phần **rollback/compensation** cho side effect bên ngoài.

**forceTermination không giết thread và không rollback transaction.** Nó thay trạng thái của phaser và đánh thức waiter theo hợp đồng; worker vẫn có thể đang làm việc nếu không tự kiểm tra.

## 15. Semaphore: thiếu release khiến permit bị rò

**Semaphore(permits)** đại diện cho số quyền truy cập còn có thể cấp. **acquire()** có thể chờ cho đến khi lấy được permit; **release()** trả permit.

~~~java
// Anti-pattern minh họa:
sem.acquire();
doWork(); // Exception ở đây khiến sem.release không được gọi.
sem.release();
~~~

Mảnh code không độc lập; sem và doWork phải có sẵn, phương thức cần xử lý InterruptedException. Nếu worker throw hoặc return trước release, permit giảm vĩnh viễn theo góc nhìn semaphore cho đến khi có hành động bù đúng.

**Một semaphore bị leak hết permits có thể khiến mọi caller mới chờ vô hạn.** Đó là liveness failure; khi kết hợp nhiều resource/lock, nó còn có thể tạo deadlock vòng chờ.

### Pattern đúng với acquire interruptible

~~~java
// Mảnh code trong phương thức throws InterruptedException.
boolean acquired = false;
try {
    sem.acquire();
    acquired = true;
    doWork();
} finally {
    if (acquired) {
        sem.release();
    }
}
~~~

**Vì sao cần cờ acquired?** acquire() có thể ném InterruptedException **trước khi lấy được permit**. Nếu finally gọi release vô điều kiện, số permit tăng sai, tạo over-release.

### Cách khác: đặt try ngay sau acquire

~~~java
sem.acquire();
try {
    doWork();
} finally {
    sem.release();
}
~~~

Khi sem.acquire() ném exception, code chưa vào try/finally này, nên không release. Khi acquire thành công và đi vào try, finally trả permit. Đây là mẫu gọn đúng trong luồng bình thường, nhưng phải xét lỗi bất thường trong khoảng giữa acquire và try nếu có thao tác bổ sung; nên giữ khoảng này tối thiểu.

## 16. Ví dụ 6: bị interrupt trước khi acquire thì không release thừa

Ta dùng một holder giữ permit duy nhất. Waiter bị interrupt trong khi đang cố acquire nên **không có permit** để trả. Trong finally, waiter chỉ release khi acquired thành true.

Tệp **SemaphoreInterruptDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

public class SemaphoreInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore permits = new Semaphore(1);
        CountDownLatch holderReady = new CountDownLatch(1);
        CountDownLatch allowRelease = new CountDownLatch(1);
        AtomicBoolean waiterInterrupted = new AtomicBoolean();

        Thread holder = new Thread(() -> {
            boolean acquired = false;
            try {
                permits.acquire();
                acquired = true;
                holderReady.countDown();
                allowRelease.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                if (acquired) {
                    permits.release();
                }
            }
        });

        holder.start();
        holderReady.await(); // Holder đang giữ permit duy nhất.

        Thread waiter = new Thread(() -> {
            boolean acquired = false;
            try {
                permits.acquire();
                acquired = true;
            } catch (InterruptedException ex) {
                waiterInterrupted.set(true);
                Thread.currentThread().interrupt();
            } finally {
                if (acquired) {
                    permits.release();
                }
            }
        });

        waiter.start();
        waiter.interrupt();
        waiter.join();

        allowRelease.countDown();
        holder.join();

        System.out.println(
                "waiter interrupted = " + waiterInterrupted.get()
        );
        System.out.println("permits = " + permits.availablePermits());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SemaphoreInterruptDemo.java
java SemaphoreInterruptDemo
~~~

Stdout:

~~~text
waiter interrupted = true
permits = 1
~~~

**Lập luận:**

1. Holder acquire permit rồi báo holderReady; main mới cho waiter start.
2. Waiter không thể lấy permit đang được holder giữ.
3. Main interrupt waiter; nếu interrupt đến trước khi waiter thực sự block, acquire interruptible vẫn xử lý trạng thái interrupt khi bắt đầu.
4. Vì acquire không thành công, cờ acquired vẫn false; waiter không gọi release.
5. Holder sau đó được mở latch, trả đúng một permit.
6. Kết quả permits=1, không bị over-release.

**Lưu ý:** Semaphore không gắn ownership permit cứng với thread như ReentrantLock; API cho phép một thread khác release. Nhưng vì vậy **ứng dụng phải giữ kỷ luật ownership** của permit ở mức nghiệp vụ, không được coi release tùy tiện là an toàn.

## 17. Ví dụ 7: Semaphore giới hạn đồng thời và hoàn trả sau mọi đường

Tệp **SemaphoreCapacityDemo.java**:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreCapacityDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore slots = new Semaphore(2);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        AtomicInteger completed = new AtomicInteger();

        Runnable task = () -> {
            boolean acquired = false;
            try {
                slots.acquire();
                acquired = true;

                int now = active.incrementAndGet();
                peak.accumulateAndGet(now, Math::max);
                try {
                    if (6 * 7 == 42) {
                        completed.incrementAndGet();
                    }
                } finally {
                    active.decrementAndGet();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                if (acquired) {
                    slots.release();
                }
            }
        };

        Thread[] threads = new Thread[4];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(task);
            threads[i].start();
        }
        for (Thread t : threads) {
            t.join();
        }

        System.out.println("completed = " + completed.get());
        System.out.println("peak <= 2 = " + (peak.get() <= 2));
        System.out.println("permits = " + slots.availablePermits());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SemaphoreCapacityDemo.java
java SemaphoreCapacityDemo
~~~

Stdout:

~~~text
completed = 4
peak <= 2 = true
permits = 2
~~~

Giới hạn **2 permit** khiến không hơn 2 task có thể đi vào critical section cùng lúc. Vì tác vụ rất ngắn, peak thực tế có thể bằng 1 hoặc 2; chỉ assert bất biến **peak <= 2**, không in “peak = 2” khi scheduler không bảo đảm.

**Sửa thiếu release không chỉ để tránh treo**: nếu release thiếu, permits còn 0/1; nếu release thừa, permits có thể vượt 2 và làm mất giới hạn concurrency.

## 18. Semaphore: acquire nhiều permit phải release đúng số

Với **acquire(n)** và **release(n)**, việc trả số permit phải khớp với số đã lấy thực sự.

~~~java
// Mảnh code trong phương thức throws InterruptedException:
sem.acquire(2);
try {
    useTwoResources();
} finally {
    sem.release(2);
}
~~~

Nếu lấy 2 mà chỉ release 1, semaphore bị leak một permit. Nếu lấy 1 mà release 2, giới hạn bị phá.

**Không nên** làm:

~~~java
// Anti-pattern: lỗi vì chưa chắc acquire thành công.
try {
    sem.acquire(2);
    work();
} finally {
    sem.release(2);
}
~~~

Nếu acquire(2) bị interrupt trước khi trả, finally vẫn release 2 dù caller chưa được cấp chúng. Với tryAcquire(timeout) trả false cũng tương tự: chỉ release nếu kết quả thực sự là true.

### Tính fairness

Semaphore có constructor fairness. Fair mode ảnh hưởng thứ tự cấp permit cho các thread chờ theo hợp đồng, nhưng không bảo đảm mọi thread được CPU đúng lượt hoặc mọi tryAcquire không tham gia policy. **Fairness không sửa permit leak**.

## 19. Return, exception, interrupt và cancel: ma trận trách nhiệm

| Điểm thoát | CountDownLatch | Phaser/CyclicBarrier | Semaphore |
| --- | --- | --- | --- |
| Thành công | Báo completion theo hợp đồng | Arrive đúng phase / await đúng generation | Release permit đã acquire |
| Validation thất bại trước khi làm việc | Báo failure; completion tùy ngữ nghĩa | Abort/deregister nếu đã register | Không release nếu chưa acquire |
| Runtime exception giữa đường | finally cho completion; lưu lỗi | Deregister hoặc terminate theo policy, tránh double arrive | finally release permit sở hữu |
| InterruptedException | Propagate/restore và báo trạng thái | Hủy pha/điều phối bên còn lại theo contract | Nếu acquire chưa thành công: không release |
| Timeout chờ bên khác | Không coi false là thành công | Barrier broken hoặc Phaser timeout cần coordinator xử lý | tryAcquire false: không giữ permit |
| Executor từ chối task | Coordinator xử lý nghĩa vụ task chưa nhận | Không để registration mồ côi | Không giả định permit thuộc task đã reject |
| Task bị cancel trước khi chạy | Coordinator cần completion/failure protocol | Hủy hoặc deregister party đã đăng ký | Chỉ trả permit nếu thực sự đã lấy |
| Shutdown trong lúc pending | Không tự countDown các nghĩa vụ | Không tự unregister party còn thiếu | Không tự thu hồi permit mà task cũ đang giữ |

**Nguyên tắc:** mỗi primitive có **đơn vị trách nhiệm** khác nhau (count, party-phase, permit). Đừng sửa một đơn vị bằng cách phát thừa đơn vị khác.

## 20. Dùng timeout để phát hiện, không để che lỗi

Một lệnh await() vô hạn là phù hợp khi protocol đã chứng minh sẽ có tín hiệu và yêu cầu cho phép chờ. Trong hệ thống nhiều nguồn lỗi, overload có timeout thường hữu ích:

~~~java
// Minh họa với CountDownLatch:
if (!completed.await(5, TimeUnit.SECONDS)) {
    throw new IllegalStateException("completion deadline exceeded");
}
~~~

Không phải chương trình độc lập: completed cần có và method cần khai báo InterruptedException.

**Timeout chỉ cung cấp đường thoát cho waiter.** Nó không:

- Giảm CountDownLatch count.
- Khôi phục permit đã bị leak.
- Bắt thread khác tự gọi arrive.
- Dừng task đang chạy hoặc hoàn tác external I/O.
- Chứng minh worker nào gây lỗi nếu thiếu telemetry.
- Biến kết quả thiếu dữ liệu thành kết quả thành công.

Một chính sách timeout tốt gồm **thông báo lỗi**, **cancel hợp tác**, **thu thập diagnostic**, **cleanup**, **backoff/retry có giới hạn**, và cách trả kết quả chính xác cho caller.

### Deadline tổng thay vì cấp lại timeout

Nếu workflow gồm ba bước chờ, mỗi bước timeout 5 giây, tổng thời gian có thể gần 15 giây, trái với deadline toàn request 5 giây. Nên tính **remaining budget** từ một clock đơn điệu (**System.nanoTime()**) trước từng bước chờ. Không dùng wall-clock time dễ thay đổi để đo elapsed.

## 21. Không giữ lock rồi chờ tín hiệu do người cần lock tạo

Đây là deadlock thực sự:

~~~text
Thread A:
  synchronized(lock L) {
      latch.await();
  }

Thread B:
  synchronized(lock L) {
      prepareData();
      latch.countDown();
  }
~~~

A đang giữ L nhưng chờ latch; B phải lấy L mới countDown. Ta có vòng phụ thuộc:

~~~text
A giữ L -> chờ latch
B cần L -> mới countDown
      ^             |
      +-------------+
~~~

**Đổi await() sang await(timeout)** giúp A có đường thoát sau hạn, nhưng không làm thiết kế đúng. Khi có thể, hãy **đưa await ra ngoài critical section**; khi lấy lại lock, phải kiểm tra lại state vì có thể thay đổi. Với Condition.await(), chính await sẽ nhả **lock liên kết với Condition** trong thời gian chờ, nhưng không nhả tất cả các lock khác mà thread đang giữ.

### “Chờ khi giữ lock” cũng gặp với Future

Một task giữ lock rồi Future.get() đợi task con cần lock ấy cũng tạo chu trình tương tự. Phải kiểm tra **dependency graph**, không chỉ lệnh arrive/countDown/release.

## 22. Thread pool starvation: không đủ worker để phát tín hiệu

Một nguồn kẹt liveness khác:

~~~text
Single-thread executor:
  Task A đang chạy trên worker duy nhất.
    A submit Task B vào cùng executor.
    A gọi futureB.get() hoặc latch.await() chờ B.
  Task B đang nằm trong queue nhưng không có worker rảnh.

=> A chờ B, B chờ worker mà A đang chiếm.
~~~

Đây là **thread-starvation deadlock**. Tăng pool lên 2 có thể làm ví dụ chạy ở mức tải thấp, nhưng một pool có 2 worker vẫn có thể bị 2 task cha chiếm hết rồi cùng chờ 2 task con. **Thay số worker không sửa nguyên tắc phụ thuộc vòng**.

Giải pháp:

- Không block đợi một tác vụ **chỉ có thể chạy trên tài nguyên do chính mình giữ**.
- Dùng composition bất đồng bộ, workflow state machine, hoặc cơ chế hỗ trợ fork/join đúng contract khi phù hợp.
- Phân tách nguồn tài nguyên nếu dependency hợp lệ và được kiểm soát.
- Giới hạn backlog, theo dõi worker active và queue age.
- Không nhầm **executor đã nhận task** với **task đã được thực thi**.

## 23. Participant động và task không được start

Ví dụ Phaser với N worker phải xử lý các ca:

1. Coordinator register participant.
2. Tạo hoặc submit task.
3. Submit có thể **bị reject**, Thread.start có thể thất bại, hoặc cancel xảy ra trước start.
4. Nếu participant đã register nhưng không có worker nào sẽ arrive, **pha bị mắc kẹt**.

Một thiết kế an toàn cần **register/start/rollback** trong cùng protocol. Ví dụ đơn giản:

~~~text
register party
try:
    submit work (work có finally -> arriveAndDeregister)
catch rejection:
    arriveAndDeregister chính party vừa register
    báo workflow failure, không giả vờ bước thành công
~~~

Đây là pseudocode cho một giao thức trong đó party mới **chưa arrive phase hiện hành**. Nếu worker đã bắt đầu hoặc có thể vừa chạy đồng thời với đường hủy, không được coordinator và worker **cùng deregister một party hai lần**. Cần cơ chế ownership/once-token cho nghĩa vụ hoàn tất.

### Race giữa cancel và start

Task có thể nhận cancel ngay khi worker bắt đầu; coordinator chưa biết nó đã tới finally hay chưa. Không nên dựa vào một boolean thường để quyết định ai release/deregister, vì check–then–act cũng có race. Có thể dùng **AtomicBoolean.compareAndSet(false,true)** cho *once completion* của một nghĩa vụ, hoặc cấu trúc task lifecycle có trạng thái và quyền sở hữu rõ.

**Once-completion khác “signal success”**: kể cả khi báo completion exactly once trong JVM, nghiệp vụ vẫn có thể FAILED hoặc CANCELLED, và process crash không được xử lý bởi AtomicBoolean.

## 24. Idempotency và trách nhiệm của tín hiệu

**CountDownLatch.countDown()** sau khi count=0 không làm âm. Điều này không có nghĩa gọi thừa countDown là an toàn về mặt giao thức: nếu count ban đầu N mà một worker countDown hai lần, latch có thể về 0 **trước khi worker khác kết thúc**.

**Semaphore.release()** có thể làm permit tăng quá giới hạn thiết kế khi gọi thừa. Nó không tự gắn ownership với thread.

**Phaser.arrive()** có trách nhiệm phase/party; gọi thừa hoặc deregister sai có thể phá phối hợp.

**CyclicBarrier.await()** là nghĩa vụ đến điểm gặp đúng **một lần trong mỗi generation**; không thể một thread gọi await hai lần liên tiếp để thay cho party còn thiếu, vì nó sẽ tự block ở lần đầu.

### Sổ nghĩa vụ

Hữu ích khi code review:

| Primitive | Nghĩa vụ | Điều kiện giải phóng hợp lệ |
| --- | --- | --- |
| CountDownLatch | Một count theo worker/giai đoạn | Worker đã đạt định nghĩa completion |
| CyclicBarrier | Một await mỗi party trong một generation | Party thực sự tới rào cản của generation ấy |
| Phaser | Một arrival mỗi party mỗi phase | Party arrive hợp lệ; deregister khi rời |
| Semaphore | Một permit đã acquire | Chủ thể trả đúng số permit theo giao thức |

Trong code, nên ghi rõ **ai sở hữu nghĩa vụ**, ai được phép phát tín hiệu thay thế và khi nào trạng thái lỗi phải được công bố.

## 25. Metrics, diagnostics và thread dump

Khi ứng dụng treo:

1. Xác định loại primitive và **đơn vị chờ** còn thiếu.
2. Với CountDownLatch, log **getCount()** và danh sách nhiệm vụ dự kiến; đừng chỉ thấy getCount()>0 rồi suy ra worker nào lỗi.
3. Với CyclicBarrier, xem **getNumberWaiting()**, **isBroken()**, số parties và generation ở cấp giao thức.
4. Với Phaser, xem **getPhase()**, **getRegisteredParties()**, **getUnarrivedParties()**; đây là snapshot có thể thay đổi.
5. Với Semaphore, xem **availablePermits()**, queue length ước lượng, số permit từng task đã acquire; không dùng queue length làm logic correctness.
6. Thu **thread dump** để thấy thread chờ trên synchronizer, lock, Future hay executor queue.
7. Kiểm tra **exception logs**, task rejection, cancellation, timeout và interrupted flags.
8. Xác định **thread nào còn có khả năng phát tín hiệu** hay vòng dependency đã kín.
9. Có correlation id cho mỗi nghĩa vụ: registered, started, arrived/released/failed/cancelled.
10. Tránh instrument bằng shared atomic counter nóng trên mọi bước hiệu năng cao nếu nó tạo contention đáng kể; có thể batch metric khi cần.

**Thread dump chỉ là một ảnh chụp**, còn nguyên nhân thường nằm ở sự kiện trước đó: task throw, missed release, submit bị reject, hoặc phase participant không được deregister.

### Kiểm tra liveness khác correctness

Một test xác minh **không treo** chưa chứng minh output đúng. Ví dụ thêm countDown vô điều kiện có thể làm test hoàn tất nhanh nhưng đọc dữ liệu chưa được tạo. Mọi phép sửa liveness phải giữ invariant nghiệp vụ.

## 26. Kiểm thử đúng bằng bất biến

Thay vì chạy 1000 lần và hy vọng race xuất hiện, hãy **điều khiển lịch**:

- Dùng CountDownLatch để bắt buộc worker tới một điểm trước khi main thực hiện bước tiếp theo.
- Dùng **await(timeout)** cho đường lỗi, tránh test treo vô hạn khi protocol có bug.
- Dùng **join()** để chắc worker đã kết thúc trước khi kiểm tra final state.
- Dùng AtomicBoolean/AtomicInteger cho biến quan sát được nhiều thread cập nhật.
- Nếu muốn thử interrupted waiter, giữ permit/latch bằng một worker rồi interrupt waiter theo giao thức.
- Với CyclicBarrier thiếu party, chỉ start một party trong barrier 2 parties rồi dùng timed await để có kết quả xác định.
- Với Phaser, register số party rõ, mọi worker deregister trong finally, coordinator đợi phase transition.
- Với Semaphore, xác minh **availablePermits() trở lại mức ban đầu** và **peak concurrent tasks <= permits** sau khi join.

**Không assert** rằng hai thread nhất định chạy xen kẽ một cách ngẫu nhiên; không in tên thread hoặc timestamp giả định thứ tự scheduler. Test nên chứng minh invariant, không dựa vào thời gian sleep “đủ dài”.

## 27. Anti-pattern và cách khắc phục

| Anti-pattern | Vì sao sai | Sửa bằng |
| --- | --- | --- |
| countDown chỉ ở cuối try | Exception/return bỏ qua | finally nếu latch đại diện completion |
| countDown cuối finally nhưng không ghi lỗi | Waiter có thể tưởng task thành công | Result/error state riêng |
| Khởi tạo latch với count lớn hơn nghĩa vụ thực | Waiter có thể không bao giờ qua | Kiểm kê obligations và xử lý rejected task |
| Gọi countDown hai lần từ một worker | Latch có thể mở quá sớm | Exactly-once completion protocol |
| CyclicBarrier.await không timeout dù party có thể chết | Các waiter còn lại mắc kẹt | Timed await + abort/recovery policy |
| Thấy BrokenBarrierException rồi cứ tiếp tục nghiệp vụ | Dữ liệu pha có thể thiếu | Xem generation thất bại, restart có điều phối |
| Phaser register rồi task bị reject | Party không bao giờ arrive | Deregister có ownership rõ |
| Phaser awaitAdvance khi party chưa arrive | Phase không tiến | Phân biệt arrive và awaitAdvance |
| Phaser arrive hai lần cùng phase | Vi phạm protocol | Một owner/phase, tránh double arrival |
| forceTermination rồi coi đã cancel worker | Worker vẫn có thể chạy | Hủy hợp tác và cleanup |
| Semaphore.acquire rồi release không ở finally | Exception gây permit leak | finally release đúng số permit |
| release trong finally dù acquire thất bại | Over-release, phá giới hạn | Cờ acquired hoặc try sau acquire |
| release sai số permit | Leak hoặc over-release | Acquire/release cùng số |
| Giữ lock trong lúc await tín hiệu do người cần lock tạo | Vòng deadlock | Phá dependency; chờ ngoài critical section |
| Task trong single worker chờ task con cùng pool | Thread-starvation deadlock | Composition / tránh blocking cùng worker |
| Timeout rồi trả success | Che lỗi completion | Failure/cancel/partial-state theo contract |
| Dùng sleep để chữa missing signal | Không tạo sự kiện cần thiết | Sửa protocol và happens-before |
| Nuốt InterruptedException rồi tiếp tục | Không phản hồi yêu cầu hủy | Propagate hoặc restore interrupt rồi thoát phù hợp |

## 28. Checklist review giao thức

**CountDownLatch**

- [ ] Count đúng với số nghĩa vụ completion thực sự?
- [ ] Mỗi nghĩa vụ chỉ countDown một lần?
- [ ] Đường exception, return, interrupt và task rejection được xử lý?
- [ ] Latch có nghĩa “done” hay “success”? Có result/error riêng?
- [ ] Waiter có deadline và nhánh timeout phù hợp?

**CyclicBarrier / Phaser**

- [ ] Số parties của mỗi phase/generation đúng?
- [ ] Mọi party có điểm arrive/await hợp lệ?
- [ ] Party rời workflow có deregister hoặc abort theo policy?
- [ ] Không register party không có worker rồi bỏ quên?
- [ ] Không double arrive/deregister?
- [ ] Có xử lý broken barrier, timeout, interruption?
- [ ] Nếu phase thất bại, downstream có biết và dừng hợp lý?

**Semaphore**

- [ ] Acquire thật sự thành công trước khi release?
- [ ] Release đúng số permit đã acquire?
- [ ] Toàn bộ critical section được bảo vệ bằng try/finally?
- [ ] Không có đường early-return bỏ release?
- [ ] Không có over-release phá giới hạn concurrency?
- [ ] Có timeout hoặc đường hủy phù hợp khi resource không có sẵn?

**Hệ thống**

- [ ] Không block giữ lock hoặc worker mà producer tín hiệu đang cần?
- [ ] Có telemetry về nghĩa vụ đã đăng ký, hoàn tất, thất bại?
- [ ] Không cho rằng timeout/cancel tự rollback I/O/DB?
- [ ] Đã test cả lỗi và thành công, không chỉ happy path?
- [ ] Có bất biến nghiệp vụ để biết “đã tiếp tục” là an toàn?

## 29. Tự kiểm tra

**1. Vì sao CountDownLatch có thể treo khi một worker ném exception?**  
Vì countDown không được gọi nếu đặt ở cuối try; latch không biết Thread đã chết. Cần completion protocol với finally hoặc failure channel phù hợp.

**2. Đặt countDown trong finally có luôn đúng không?**  
Chỉ khi countDown đại diện “đã kết thúc”. Nếu nó đại diện “đã thành công”, phải tách status và bảo đảm downstream không hiểu sai.

**3. CountDownLatch.await(20ms) trả false có làm counter giảm không?**  
Không. Count vẫn giữ nguyên; timeout là đường thoát của waiter.

**4. CyclicBarrier cần 3 party nhưng chỉ có 2 đến await; điều gì xảy ra nếu không có timeout/interrupt?**  
Hai party có thể chờ vô hạn nếu party thứ ba không bao giờ đến.

**5. Timed await trong CyclicBarrier timeout thì barrier ra sao?**  
Barrier bị broken; các waiter khác có thể nhận BrokenBarrierException. Phải xử lý failure/recovery có điều phối.

**6. Phaser.awaitAdvance(phase) có tự tính caller đã arrive không?**  
Không. Caller phải hoàn thành nghĩa vụ arrive bằng API phù hợp; awaitAdvance chỉ chờ phase đổi.

**7. Một party đã register rồi không start; Phaser có tự bỏ nó không?**  
Không. Coordinator cần xử lý registration không có worker, hoặc abort toàn workflow.

**8. Khi worker chỉ tham gia một phase rồi rời, API nào phù hợp?**  
arriveAndDeregister() theo protocol, thường trong finally nếu báo kết thúc cả đường lỗi, kết hợp báo lỗi riêng.

**9. Phaser.forceTermination() có dừng tất cả worker đang thực thi không?**  
Không. Nó chuyển phaser sang trạng thái terminated; worker phải tự hợp tác với cancellation và cleanup.

**10. Semaphore.acquire bị InterruptedException trước khi lấy permit; có được release không?**  
Không. Release khi chưa acquire làm permit tăng sai. Chỉ release nếu acquire thành công.

**11. Nếu Semaphore(2) bị gọi release ba lần nhưng chỉ acquire hai lần, điều gì sai?**  
Có thể tăng permit vượt 2, phá giới hạn concurrency theo thiết kế.

**12. Vì sao lock + latch.await có thể tạo deadlock vòng?**  
Nếu người phát countDown cần khóa đang được waiter giữ, hai bên phụ thuộc lẫn nhau.

**13. Một single-thread executor task submit child vào chính executor và gọi get thì sao?**  
Worker đang đợi child, child chờ worker rảnh; có thể tạo thread-starvation deadlock.

**14. Tại sao timeout không đủ để chứng minh sửa liveness?**  
Nó chỉ dừng chờ của caller; nghĩa vụ arrival/countDown/permit vẫn sai và trạng thái nghiệp vụ có thể thiếu.

**15. Các chỉ số getCount/getUnarrivedParties/availablePermits chứng minh đúng đắn không?**  
Chúng hỗ trợ chẩn đoán; phải phân tích nghĩa vụ/ownership, các đường exception và invariant, không chỉ nhìn snapshot.

## 30. Tổng kết

Thiếu một lời gọi **countDown(), arrive()/arriveAndDeregister() hoặc release()** có thể khiến các thread khác **không bao giờ tiến triển**. Nhưng gọi thừa hoặc báo tín hiệu sai ngữ nghĩa cũng nguy hiểm: latch có thể mở sớm, phaser vi phạm phase protocol, semaphore mất giới hạn tài nguyên.

Cách thiết kế đáng tin:

1. Ghi rõ **nghĩa vụ** của mỗi participant/task/permit và ai sở hữu.
2. Cấu trúc code với **try/finally** để cleanup và báo kết thúc theo đúng contract.
3. **Không phát tín hiệu thành công giả**; truyền failure/result ở kênh riêng.
4. **Không release nếu acquire chưa thành công**; tránh double-arrive, double-countDown.
5. Dùng **timeout + failure propagation + cancellation** để có đường thoát kiểm soát khi bên kia không thể tiếp tục.
6. Kiểm tra dependency graph để không giữ lock/worker mà người phát tín hiệu cần.
7. Test các đường **exception, interrupt, rejection và shutdown** bằng synchronization xác định, sau đó kiểm tra invariant nghiệp vụ.

Điểm cốt lõi không chỉ là “cho thread hết chờ”, mà là bảo đảm **mỗi sự kiện hoàn tất được phát đúng một lần, đúng ý nghĩa, đúng chủ sở hữu, và mọi thread tiếp tục trên một trạng thái hợp lệ**.
