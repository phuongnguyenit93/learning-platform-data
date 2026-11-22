# Phaser: Rút khỏi nhóm bằng arriveAndDeregister()

> **Chủ đề:** Sử dụng `Phaser.arriveAndDeregister()` để một *party* báo đã đến phase hiện tại **và đồng thời rút khỏi các phase tiếp theo**, không đứng chờ các party khác. Đây là khả năng đồng bộ nhiều giai đoạn với số người tham gia biến đổi linh hoạt, có từ **Java 7** và vẫn được hỗ trợ trong **Java 17+**. Bài chỉ dùng API hiện hành của `java.util.concurrent`, không dựa vào phương thức đồng bộ hóa đã lỗi thời. Các ví dụ Java 17 được biên dịch, chạy độc lập và đối chiếu stdout; phần minh họa concurrency chủ động tránh giả định thứ tự scheduling không được đảm bảo.

## 1. Bối cảnh: Vì sao Phaser cần rút party?

Một hệ thống xử lý dữ liệu qua nhiều vòng có thể có ba workers cùng làm việc trong phase 0, nhưng một worker hoàn thành nhiệm vụ sớm và không tham gia phase 1, phase 2. Nếu cơ chế barrier vẫn **đếm worker đó ở mọi vòng**, các workers còn lại có thể chờ vô hạn vì không còn ai phát tín hiệu arrival cho suất đã đăng ký.

`Phaser` giải quyết tình huống này bằng khả năng **đăng ký động và rút khỏi nhóm động**. Mỗi phase có một số *registered parties* và một số *unarrived parties*. Khi tất cả những parties còn được tính cho phase hiện tại đã đến, Phaser chuyển sang phase kế tiếp. Nếu party đã xong công việc, `arriveAndDeregister()` giúp giảm số suất phải chờ ở hiện tại và các phase sau.

```text
Phaser phase 0: A, B, C đã đăng ký
      |
      +-- A: arrive()                 -- A vẫn đăng ký cho phase sau
      +-- B: arriveAndDeregister()    -- B báo đã đến và rút hẳn
      +-- C: arrive()                 -- C báo đã đến
      |
      v
Phaser phase 1: chỉ A, C còn đăng ký
      |
      +-- A và C phải đến; không chờ B nữa
```

**Điểm mấu chốt:** `arriveAndDeregister()` **không** có nghĩa “đợi mọi người xong rồi mới rút”. Nó ghi nhận arrival và deregistration rồi **trả về ngay**, trừ các chi phí điều phối nội bộ/phase advance có thể xảy ra. Nếu rút khiến unarrived về 0, chính thread gọi có thể chạy `onAdvance()` và thúc đẩy chuyển phase.

### 1.1. Phân biệt thread với party

Trong `Phaser`, một **party là một suất đăng ký**, không phải đối tượng Thread được API nhận diện bằng ID. Một thread có thể quản lý nhiều logical parties, và một task có thể được chuyển qua thread khác. `Phaser` chỉ giữ **các bộ đếm**, không lưu danh sách danh tính để kiểm tra “thread này đã register chưa”.

Vì vậy:
- Đừng tự cho rằng “mỗi Thread đương nhiên là một party”.
- Chỉ method thực sự sở hữu suất đăng ký mới được báo arrival/deregister thay suất đó.
- Hai lần `arriveAndDeregister()` từ cùng code path có thể **tiêu thụ hai suất khác nhau**, chứ API không nhất thiết phát hiện được call thứ hai thuộc cùng một logical party.
- Một thread không cần có “tên” gắn trong Phaser; ứng dụng phải quản lý token/ownership ở tầng của mình.

Đây là lý do thiết kế `try/finally` và cancellation cần rất cẩn thận.

## 2. Ba method dễ nhầm: arrive, arriveAndAwaitAdvance, arriveAndDeregister

| Method | Ghi nhận arrival ở phase hiện tại | Rút khỏi các phase kế tiếp | Chờ phase chuyển |
| --- | --- | --- | --- |
| `arrive()` | Có | Không | Không |
| `arriveAndAwaitAdvance()` | Có | Không | Có, trừ khi đã terminated |
| `arriveAndDeregister()` | Có | **Có** | **Không** |
| `awaitAdvance(phase)` | **Không** | **Không** | Có nếu phase còn đang là phase được chỉ định |

`arrive()` báo đã làm xong vòng hiện tại nhưng **vẫn là thành viên** ở vòng sau. `arriveAndAwaitAdvance()` vừa báo đã đến, vừa đợi các parties còn lại trước khi sang vòng sau. `arriveAndDeregister()` vừa báo đã đến, vừa rút khỏi nhóm, **không tự chờ**.

### 2.1. Giá trị trả về của `arriveAndDeregister()`

Chữ ký Java:

```java
int arrivalPhase = phaser.arriveAndDeregister();
```

Đây là snippet với `Phaser phaser` hợp lệ do caller quản lý. Giá trị `arrivalPhase` là **số phase mà arrival/deregistration được áp dụng**, không bắt buộc bằng `phaser.getPhase()` sau lời gọi. Nếu đây là arrival cuối cùng, `getPhase()` có thể đã tăng sang phase mới (hoặc âm khi termination), còn giá trị trả về vẫn là phase vừa hoàn tất. Nếu Phaser đã terminated, phương thức trả giá trị âm.

**Không** xem `arrivalPhase==phase+1` là hợp đồng. Để biết trạng thái hiện tại dùng `getPhase()` và `isTerminated()`, chấp nhận chúng có thể thay đổi theo concurrency.

### 2.2. Bộ đếm thay đổi như thế nào?

Trong một phase đang hoạt động, một deregistration hợp lệ thông thường:
- `registeredParties` giảm 1;
- `unarrivedParties` giảm 1 vì party đồng thời báo arrival;
- số arrivals đã ghi nhận của các parties còn lại không bị “mất”;
- nếu `unarrivedParties` về 0, phase advance;
- ở phase mới, các parties **còn đăng ký** bắt đầu ở trạng thái unarrived.

Bộ ba quan sát:
- `getRegisteredParties()` — tổng số parties đang đăng ký.
- `getUnarrivedParties()` — bao nhiêu parties chưa đến trong phase hiện tại.
- `getArrivedParties()` — bao nhiêu parties đã đến trong phase hiện tại.

Các số liệu này là **snapshot giám sát**, không phải primitive để quyết định synchronization bằng cách tự polling: giá trị có thể đổi tức thì. Sau termination, Javadoc nêu `getArrivedParties()` và `getUnarrivedParties()` có thể vô nghĩa/không xác định; không dùng chúng để suy lịch sử sự kiện khi terminated.

### 2.3. Cơ chế phase advance

Mỗi phase bắt đầu ở số 0, tăng khi tất cả parties của phase đó đã đến. Khi thread cuối cùng đến, `Phaser` gọi `onAdvance(currentPhase, registeredParties)` trên thread hoàn tất transition; method này quyết định có **terminate** hay không. Implementation mặc định của `onAdvance` trả true khi số parties đã trở thành 0 do deregistration.

Do đó nếu một party cuối cùng gọi `arriveAndDeregister()`, Phaser mặc định **terminated**, không chỉ trở về một barrier trống chờ đăng ký mới.

## 3. Chương trình 1 — xem từng bước thay đổi registered/unarrived

Chạy một thứ tự tuần tự có chủ ý để quan sát rõ. Khởi tạo ba **logical parties** A, B, C; code trong main đại diện lần lượt các parties này để minh họa bộ đếm. Đây không phải ví dụ ba threads.

Lưu thành `PhaserCountsDemo.java`:

```java
import java.util.concurrent.Phaser;

public class PhaserCountsDemo {
    static void show(String label, Phaser p) {
        System.out.printf("%s phase=%d parties=%d unarrived=%d arrived=%d%n",
                label, p.getPhase(), p.getRegisteredParties(),
                p.getUnarrivedParties(), p.getArrivedParties());
    }
    public static void main(String[] args) {
        Phaser p = new Phaser(3);
        show("start", p);
        p.arrive();
        show("afterArrive", p);
        int leftAt = p.arriveAndDeregister();
        System.out.println("deregisterReturned=" + leftAt);
        show("afterDrop", p);
        p.arrive();
        show("afterLastArrival", p);
        p.arriveAndDeregister();
        System.out.println("afterSecondDropParties=" + p.getRegisteredParties());
        p.arriveAndDeregister();
        System.out.println("finalParties=" + p.getRegisteredParties());
        System.out.println("terminated=" + p.isTerminated());
        System.out.println("finalPhaseNegative=" + (p.getPhase() < 0));
    }
}
```

Lệnh Java 17:

```bash
javac -encoding UTF-8 --release 17 PhaserCountsDemo.java
java PhaserCountsDemo
```

Stdout **đã biên dịch và kiểm chứng**:

```text
start phase=0 parties=3 unarrived=3 arrived=0
afterArrive phase=0 parties=3 unarrived=2 arrived=1
deregisterReturned=0
afterDrop phase=0 parties=2 unarrived=1 arrived=1
afterLastArrival phase=1 parties=2 unarrived=2 arrived=0
afterSecondDropParties=1
finalParties=0
terminated=true
finalPhaseNegative=true
```

**Giải thích từng bước:**
1. `new Phaser(3)` đăng ký 3 parties, phase 0, chưa ai đến.
2. Party A `arrive()`: tổng đăng ký vẫn 3, unarrived giảm còn 2.
3. Party B `arriveAndDeregister()`: trả phase 0; tổng đăng ký giảm 2, unarrived giảm 1. Party A vẫn được tính đã đến.
4. Party C `arrive()`: unarrived về 0, phase advance sang 1. **Chỉ A, C tiếp tục cần báo arrival ở phase 1.**
5. Ở phase 1, A rút rồi C rút (trong demo dùng main đại diện). Khi party cuối rút, số đăng ký về 0 và mặc định Phaser terminated.

Chương trình không in `getUnarrivedParties()` sau termination vì giá trị đó không có ý nghĩa hữu ích theo Javadoc.

### 3.1. Không coi `arriveAndDeregister` là “release tất cả”

Nếu có ba parties và một party dereg, nhưng hai party còn lại chưa đến, phase vẫn chưa chuyển. Nó chỉ giảm một suất chờ. Những parties còn lại phải báo đến hoặc cũng rút, trừ khi ứng dụng thực hiện `forceTermination()` theo chính sách hủy toàn bộ.

## 4. Phương thức không chờ: worker rút, worker khác vẫn có thể đang đợi

`arriveAndDeregister()` là một **arrival không chờ**. Điều này đặc biệt hữu ích khi worker hoàn thành mọi vòng của mình nhưng những worker khác vẫn có việc. Worker đó không cần ở lại chỉ để đợi barrier.

### 4.1. Chương trình 2 — rút nhóm không giải phóng waiter khi vẫn còn party khác

Lưu thành `PhaserNonBlockingDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Phaser;
import java.util.concurrent.TimeUnit;

public class PhaserNonBlockingDemo {
    public static void main(String[] args) throws Exception {
        Phaser p = new Phaser(3); // Three logical parties: waiter, leaver, finisher
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch passed = new CountDownLatch(1);
        Thread waiter = new Thread(() -> {
            ready.countDown();
            int next = p.arriveAndAwaitAdvance();
            if (next < 0) throw new AssertionError("unexpected termination");
            passed.countDown();
        }, "waiter");
        waiter.start();
        if (!ready.await(2, TimeUnit.SECONDS)) throw new AssertionError("not ready");
        int returned = p.arriveAndDeregister(); // Simulated leaver on main thread
        System.out.println("dropReturned=" + returned);
        System.out.println("registeredAfterDrop=" + p.getRegisteredParties());
        System.out.println("waiterStillWaiting=" + (passed.getCount() == 1));
        p.arrive(); // Third logical party completes this phase
        if (!passed.await(2, TimeUnit.SECONDS)) throw new AssertionError("not released");
        waiter.join(2_000);
        System.out.println("phaseAfterRelease=" + p.getPhase());
        System.out.println("waiterReleased=" + (passed.getCount() == 0));
        p.forceTermination();
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PhaserNonBlockingDemo.java
java PhaserNonBlockingDemo
```

Stdout đã kiểm chứng:

```text
dropReturned=0
registeredAfterDrop=2
waiterStillWaiting=true
phaseAfterRelease=1
waiterReleased=true
```

Chương trình sử dụng `CountDownLatch` để có thứ tự test rõ, không dựa vào `Thread.sleep`. Main đóng vai party rút và party cuối cùng đến; waiter là một thread độc lập. Sau rút, vẫn còn hai logical parties: waiter chưa đủ điều kiện vượt barrier cho tới khi party cuối báo `arrive()`. `forceTermination()` ở cuối chỉ là dọn trạng thái thử nghiệm, không phải bước cần có sau mọi deregistration.

**Lưu ý:** `ready.countDown()` xảy ra ngay trước lời gọi `arriveAndAwaitAdvance()`. Kể cả scheduler chưa cho waiter thực sự vào lời gọi, condition “chưa đủ tất cả arrivals” vẫn bảo đảm waiter không thể vượt phase trước khi party cuối đến.

## 5. Pattern thực tế: worker làm nhiều vòng rồi rút sớm

Một ứng dụng tính toán lặp có thể có workers với số vòng khác nhau. Worker ngắn hoàn thành vòng 0 rồi **arriveAndDeregister()**; worker dài tiếp tục chờ ở mỗi vòng còn lại. Điều phối viên có thể đăng ký một suất để tham gia và quan sát phase advances.

### 5.1. Vì sao cần đăng ký trước khi submit tasks?

Nếu main bắt đầu chờ phase trước khi workers được đăng ký, Phaser có thể advance quá sớm: không có đủ parties được tính. Thực hành tốt:
1. Xác định những workers sẽ chạy ở phase đầu.
2. `register()` hoặc `bulkRegister(n)` **trước khi** để root/coordinator bắt đầu chờ phase.
3. Submit tasks; nếu một submit bị `RejectedExecutionException`, gỡ suất đã đăng ký mà task không bao giờ sử dụng.
4. Workers hoàn thành từng phase bằng `arriveAndAwaitAdvance()`; khi kết thúc sớm hoặc hoàn tất toàn bộ, dùng `arriveAndDeregister()` đúng một lần.
5. Coordinator cũng phải xử lý party của mình; không để coordinator còn registered vô thời hạn khi không còn tham gia.

### 5.2. Chương trình 3 — một worker rời ở vòng đầu, worker kia làm ba vòng

Lưu thành `PhaserMultiRoundDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class PhaserMultiRoundDemo {
    public static void main(String[] args) throws Exception {
        Phaser p = new Phaser(1); // Coordinator remains registered
        p.bulkRegister(2);
        AtomicInteger shortRounds = new AtomicInteger();
        AtomicInteger longRounds = new AtomicInteger();
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<?> shortTask = executor.submit(() -> {
                boolean registered = true;
                try {
                    shortRounds.incrementAndGet();
                    p.arriveAndDeregister(); // Finished after the first phase
                    registered = false;
                } finally {
                    if (registered) p.arriveAndDeregister();
                }
            });
            Future<?> longTask = executor.submit(() -> {
                boolean registered = true;
                try {
                    for (int round = 0; round < 3; round++) {
                        longRounds.incrementAndGet();
                        p.arriveAndAwaitAdvance();
                    }
                } finally {
                    if (registered) p.arriveAndDeregister();
                }
            });
            for (int round = 0; round < 3; round++) {
                int result = p.arriveAndAwaitAdvance();
                if (result < 0) throw new AssertionError("unexpected termination");
            }
            shortTask.get(3, TimeUnit.SECONDS);
            longTask.get(3, TimeUnit.SECONDS);
            System.out.println("shortWorkerRounds=" + shortRounds.get());
            System.out.println("longWorkerRounds=" + longRounds.get());
            System.out.println("phaseAfterThreeRounds=" + p.getPhase());
            System.out.println("coordinatorOnly=" + (p.getRegisteredParties() == 1));
            p.arriveAndDeregister(); // Coordinator leaves last
            System.out.println("terminated=" + p.isTerminated());
        } finally {
            p.forceTermination();
            executor.shutdownNow();
            if (!executor.awaitTermination(3, TimeUnit.SECONDS))
                throw new AssertionError("pool still running");
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PhaserMultiRoundDemo.java
java PhaserMultiRoundDemo
```

Stdout đã chạy:

```text
shortWorkerRounds=1
longWorkerRounds=3
phaseAfterThreeRounds=3
coordinatorOnly=true
terminated=true
```

Diễn tiến:
- Trước vòng đầu: có 3 parties (coordinator + worker ngắn + worker dài).
- Worker ngắn xử lý một vòng rồi dereg; không phải đến ở phase 1/2.
- Worker dài và coordinator tiếp tục `arriveAndAwaitAdvance()` để phối hợp hai vòng còn lại.
- Sau ba phase advances, worker dài dereg. Chỉ còn coordinator đăng ký.
- Coordinator rút cuối cùng, khiến Phaser terminated theo hành vi mặc định.

### 5.3. Phạm vi an toàn của finally trong ví dụ

Ví dụ mô phỏng các thao tác thành công và một đường rút bình thường có kiểm soát. `registered` là cờ **ownership của logical party**, không phải trạng thái do Phaser tự gắn với Thread. Với code production:
- Nếu một worker có thể gọi `arrive()` trước khi xảy ra lỗi ở cùng phase, không được gọi `arriveAndDeregister()` ngay trong finally **của cùng phase** rồi vô tình báo arrival lần hai.
- Nếu đã hoàn tất `arriveAndAwaitAdvance()` và bắt đầu phase mới, dereg ở phase mới là hợp lệ.
- Nếu `onAdvance()` do ứng dụng override có thể ném unchecked exception hoặc workflow có cancel giữa các thao tác, cần state machine của từng party để tránh double arrival.
- Khi một worker thất bại không thể sửa trạng thái barrier một cách an toàn, chiến lược rõ ràng thường là **forceTermination và báo lỗi cho tất cả workers**, thay vì giả vờ công việc đã hoàn tất.

Đừng biến snippet finally của một ví dụ đơn giản thành quy tắc “bất kỳ lúc nào lỗi cũng cứ dereg”.

## 6. Party cuối rút có thể làm Phaser terminated

`Phaser` mặc định gọi `onAdvance()` khi phase có đủ arrivals, và implementation mặc định của `onAdvance` trả true khi **registered parties bằng 0** do deregistration. Khi đó:
- `isTerminated()` thành true.
- `getPhase()` âm (thể hiện trạng thái termination).
- Các lời gọi synchronization về sau không chờ barrier nữa mà trả giá trị âm phù hợp.
- `register()` sau termination **không** đăng ký mới được; trả giá trị âm.
- Không thể “mở lại” cùng Phaser mặc định đã terminated chỉ bằng cách gọi register.

### 6.1. Chương trình 4 — party cuối rút và register muộn bị từ chối

Lưu thành `PhaserLastPartyDemo.java`:

```java
import java.util.concurrent.Phaser;

public class PhaserLastPartyDemo {
    public static void main(String[] args) {
        Phaser p = new Phaser(1);
        System.out.println("beforeParties=" + p.getRegisteredParties());
        int returned = p.arriveAndDeregister();
        System.out.println("dropReturned=" + returned);
        System.out.println("afterParties=" + p.getRegisteredParties());
        System.out.println("terminated=" + p.isTerminated());
        System.out.println("negativePhase=" + (p.getPhase() < 0));
        int lateRegistration = p.register();
        System.out.println("lateRegisterRejected=" + (lateRegistration < 0));
        System.out.println("partiesStillZero=" + (p.getRegisteredParties() == 0));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PhaserLastPartyDemo.java
java PhaserLastPartyDemo
```

Stdout đã kiểm chứng:

```text
beforeParties=1
dropReturned=0
afterParties=0
terminated=true
negativePhase=true
lateRegisterRejected=true
partiesStillZero=true
```

**Lưu ý cần phân biệt:** `new Phaser(0)` ban đầu tạo Phaser không có party nhưng **chưa terminated**. Nó có thể nhận party đầu bằng `register()`. Ngược lại, `new Phaser(1)` rồi `arriveAndDeregister()` party cuối sẽ làm Phaser **terminated** theo mặc định. Hai trạng thái đều có 0 parties nhưng không có cùng semantics.

### 6.2. Khi nào nên cho Phaser tiếp tục hoạt động dù tạm thời còn 0 parties?

Nếu ứng dụng có nhiều đợt workers lần lượt đến và đi, cần hỗ trợ “zero parties” rồi register lại, có thể override `onAdvance` trả false:

```java
Phaser reusable = new Phaser(1) {
    @Override
    protected boolean onAdvance(int phase, int registeredParties) {
        return false;
    }
};
```

Đây là snippet. Nó tắt **hành vi termination mặc định khi parties về 0**; application phải tự định ra lúc nào dừng bằng `forceTermination()` hoặc override điều kiện kết thúc khác. Nếu giữ Phaser không bao giờ terminated nhưng không có ai quản lý lifecycle, có thể tạo rủi ro resource/logic leak ở tầng nghiệp vụ.

### 6.3. Chương trình 5 — override onAdvance để tái đăng ký

Lưu thành `PhaserNonTerminatingDemo.java`:

```java
import java.util.concurrent.Phaser;

public class PhaserNonTerminatingDemo {
    public static void main(String[] args) {
        Phaser p = new Phaser(1) {
            @Override protected boolean onAdvance(int phase, int registeredParties) {
                return false; // Keep the phaser reusable with zero parties
            }
        };
        int leftAt = p.arriveAndDeregister();
        System.out.println("firstDropPhase=" + leftAt);
        System.out.println("partiesAfterDrop=" + p.getRegisteredParties());
        System.out.println("stillActive=" + !p.isTerminated());
        System.out.println("advancedPhase=" + p.getPhase());
        int newRegistration = p.register();
        System.out.println("newRegistrationPhase=" + newRegistration);
        System.out.println("newParties=" + p.getRegisteredParties());
        p.arriveAndDeregister();
        System.out.println("phaseAfterSecondDrop=" + p.getPhase());
        p.forceTermination();
        System.out.println("terminatedAfterForce=" + p.isTerminated());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PhaserNonTerminatingDemo.java
java PhaserNonTerminatingDemo
```

Stdout đã kiểm chứng:

```text
firstDropPhase=0
partiesAfterDrop=0
stillActive=true
advancedPhase=1
newRegistrationPhase=1
newParties=1
phaseAfterSecondDrop=2
terminatedAfterForce=true
```

**Giải thích:** Đợt đầu rút hết nhưng Phaser không terminated vì `onAdvance` luôn trả false. Một party mới đăng ký ở phase 1 rồi rút ở phase đó, chuyển sang phase 2; cuối cùng ứng dụng chủ động `forceTermination()`.

**Cảnh báo khi override:** Javadoc không bảo đảm hành vi khi gọi `register()`, arrival hoặc waiting methods của **cùng Phaser** từ bên trong `onAdvance()`. Giữ callback ngắn, tránh block lâu và không tái nhập lại Phaser từ callback. Override termination policy phải dựa trên business contract, không tự xem “onAdvance luôn false” là mặc định phù hợp mọi ứng dụng.

## 7. Đã deregister vẫn có thể chờ phase bằng awaitAdvance

Một trường hợp dễ nhầm: tác vụ muốn **rút khỏi nhóm** để không tham gia các vòng sau, nhưng vẫn cần biết những người ở lại đã **hoàn tất phase hiện tại** trước khi xử lý việc độc lập tiếp theo.

API cho phép kết hợp:

```java
int arrivalPhase = phaser.arriveAndDeregister();
int next = phaser.awaitAdvance(arrivalPhase);
```

Đây là snippet. `arriveAndDeregister()` ghi nhận arrival và rút party. `awaitAdvance(arrivalPhase)` sau đó **chỉ chờ/quan sát** phase chuyển, không thêm party mới và không làm một arrival khác. Điều này tương ứng với pattern được nêu trong Javadoc `Phaser`.

Lời gọi `awaitAdvance(phase)` không yêu cầu caller phải đang registered. Nó trả ngay nếu phase hiện tại đã khác giá trị truyền vào hoặc Phaser đã terminated. Nếu truyền giá trị phase không đúng hoặc đã cũ, nó có thể trả ngay thay vì đợi điều bạn tưởng.

### 7.1. Chương trình 6 — rút rồi đợi những parties còn lại

Lưu thành `PhaserDeregisterThenAwaitDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class PhaserDeregisterThenAwaitDemo {
    public static void main(String[] args) throws Exception {
        Phaser p = new Phaser(3); // Two parties stay; one leaves
        int previous = p.arriveAndDeregister();
        AtomicInteger advanced = new AtomicInteger(Integer.MIN_VALUE);
        CountDownLatch started = new CountDownLatch(1);
        Thread observer = new Thread(() -> {
            started.countDown();
            advanced.set(p.awaitAdvance(previous)); // Observing only; not registered
        }, "observer");
        observer.start();
        if (!started.await(2, TimeUnit.SECONDS)) throw new AssertionError("not started");
        p.arrive();
        p.arrive();
        observer.join(2_000);
        if (observer.isAlive()) throw new AssertionError("observer stuck");
        System.out.println("deregisterAtPhase=" + previous);
        System.out.println("observedNextPhase=" + advanced.get());
        System.out.println("stillRegisteredParties=" + p.getRegisteredParties());
        p.arriveAndDeregister();
        p.arriveAndDeregister();
        System.out.println("terminatedAfterRemainingLeave=" + p.isTerminated());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PhaserDeregisterThenAwaitDemo.java
java PhaserDeregisterThenAwaitDemo
```

Stdout đã chạy:

```text
deregisterAtPhase=0
observedNextPhase=1
stillRegisteredParties=2
terminatedAfterRemainingLeave=true
```

Có ba logical parties ban đầu. Một party rời ở phase 0, observer không trở thành registered party. Hai parties còn lại đến, phase chuyển sang 1; observer nhận thông báo chuyển phase. Tại phase 1 vẫn có **2 parties** đã đăng ký. Chúng rút sau đó và phaser mới terminated.

### 7.2. Khi nào `awaitAdvance` không nên dùng vô thời hạn?

Nếu party còn lại bị crash, chờ `awaitAdvance` bình thường có thể kéo dài vô hạn. Với deadline ứng dụng, dùng `awaitAdvanceInterruptibly(phase,timeout,unit)` để timeout hoặc xử lý interruption. Cần có chính sách rõ nếu timeout:
- Không giả định timeout tự dereg/forceTerminate.
- Nếu đã ghi nhận `arrive()` ở phase đó, không được cứ gọi `arriveAndDeregister()` thêm lần trong cùng phase rồi “rút hộ” một party khác.
- Nếu không thể tiếp tục barrier an toàn sau lỗi, coordinator có thể `forceTermination()` và phát tín hiệu hủy toàn nhóm.
- Nếu chỉ observer không registered, timeout của observer không thay đổi party counts.

## 8. Timeout/chờ bị ngắt không tự rút party

`Phaser` có:
- `awaitAdvance(phase)`: đợi chuyển phase, kể cả khi thread chờ bị interrupt; không tự hủy barrier vì interrupt.
- `awaitAdvanceInterruptibly(phase)`: có thể ném `InterruptedException`.
- `awaitAdvanceInterruptibly(phase, timeout, TimeUnit)`: có thể ném `InterruptedException` hoặc `TimeoutException`.
- `arriveAndAwaitAdvance()`: arrival và chờ, tương tự `awaitAdvance(arrive())` về tác dụng.

Điểm chung quan trọng trong Javadoc: exception khi chờ theo các dạng interruptible/timeout **không tự thay đổi trạng thái Phaser**. Vì thế `Future.cancel(true)` hoặc `Thread.interrupt` không phải một chiến lược deregistration tự động khi task đã đăng ký.

### 8.1. Chương trình 7 — timeout sau arrive không thay đổi party counts

Lưu thành `PhaserTimedAwaitDemo.java`:

```java
import java.util.concurrent.Phaser;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class PhaserTimedAwaitDemo {
    public static void main(String[] args) throws Exception {
        Phaser p = new Phaser(2); // Logical A and B
        int aArrivedAt = p.arrive(); // A arrived, does not withdraw
        boolean didTimeOut = false;
        try {
            p.awaitAdvanceInterruptibly(aArrivedAt, 50, TimeUnit.MILLISECONDS);
        } catch (TimeoutException expected) {
            didTimeOut = true;
        }
        System.out.println("timedOut=" + didTimeOut);
        System.out.println("partiesAfterTimeout=" + p.getRegisteredParties());
        System.out.println("unarrivedAfterTimeout=" + p.getUnarrivedParties());
        p.arriveAndDeregister(); // Logical B withdraws from phase 0
        System.out.println("phaseAfterBLeaves=" + p.getPhase());
        System.out.println("partiesAfterBLeaves=" + p.getRegisteredParties());
        p.arriveAndDeregister(); // A leaves in phase 1, NOT again in phase 0
        System.out.println("terminatedAfterALeaves=" + p.isTerminated());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PhaserTimedAwaitDemo.java
java PhaserTimedAwaitDemo
```

Stdout đã kiểm chứng:

```text
timedOut=true
partiesAfterTimeout=2
unarrivedAfterTimeout=1
phaseAfterBLeaves=1
partiesAfterBLeaves=1
terminatedAfterALeaves=true
```

Với phase 0, party A đã `arrive()` nhưng vẫn registered. `awaitAdvanceInterruptibly` hết 50 ms vì party B chưa đến. **Phaser không tự giảm parties**: vẫn registered=2, unarrived=1. Party B thật sự `arriveAndDeregister()`, làm phase chuyển sang 1. Chỉ sau đó party A mới được `arriveAndDeregister()` ở **phase 1**, không phải gọi thêm một arrival trong phase 0.

**Sai lầm cần tránh:**

```java
int phase = phaser.arrive();
try {
    phaser.awaitAdvanceInterruptibly(phase, 100, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    phaser.arriveAndDeregister(); // SAI: có thể báo arrival lần hai cùng phase!
}
```

Đây là **anti-pattern snippet**, không phải chương trình nên chạy. Khi party đã arrive ở phase hiện tại, deregister ngay trong catch có thể gây double arrival và vô tình làm phase advance mà một party khác chưa xong. Tùy trạng thái bộ đếm, Java có thể phát hiện lỗi ở operation hiện tại hoặc **một thao tác sau**; không dựa vào exception để bảo vệ ownership.

Một hệ thống muốn hủy tất cả vòng khi timeout có thể gọi `forceTermination()` một lần từ owner/coordinator, để những waiter khác thoát thay vì tự tính lại party counts từ các callback muộn.

## 9. Worker lỗi: rút bình thường hay forceTerminate?

Có hai loại kết thúc rất khác nhau:

**Kết thúc bình thường:** Worker hoàn tất phần việc của mình, không cần tham gia các phase sau. Nó `arriveAndDeregister()`. Các parties còn lại tiếp tục và chờ nhau theo cách bình thường.

**Lỗi làm workflow không thể tin cậy:** Worker chưa hoàn tất trách nhiệm, một phase yêu cầu đủ kết quả/side effects để proceed. Nếu worker bị lỗi, việc deregister “như đã xong” có thể làm những workers khác vượt barrier với dữ liệu thiếu. Khi failure là **fatal** ở tầng nghiệp vụ, nên lưu lỗi và `forceTermination()` để thả tất cả waiters, sau đó thông báo kết quả thất bại cho caller.

### 9.1. `forceTermination()` giữ nguyên số parties

Theo Javadoc, `forceTermination()`:
- chuyển Phaser sang terminated, giải phóng các waiters;
- không sửa số `registeredParties`;
- gọi nhiều lần không gây thêm tác dụng;
- với các Phaser phân cấp liên quan, termination lan sang toàn bộ cấu trúc;
- những lời gọi synchronization về sau có thể trả phase âm.

Nếu sau forceTermination, `getRegisteredParties()==2`, điều đó **không** có nghĩa “còn hai workers đang sống”, cũng không phải một leak token bắt buộc. Đây chỉ là count không bị thay đổi khi ép termination. Để quan sát workers đã kết thúc, theo dõi `Future`, thread lifecycle và resource cleanup riêng.

### 9.2. Chương trình 8 — lỗi worker giải phóng coordinator

Lưu thành `PhaserFailureTerminationDemo.java`:

```java
import java.util.concurrent.Phaser;
import java.util.concurrent.atomic.AtomicReference;

public class PhaserFailureTerminationDemo {
    public static void main(String[] args) throws Exception {
        Phaser p = new Phaser(2); // Coordinator and worker
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread worker = new Thread(() -> {
            try {
                throw new IllegalStateException("synthetic worker failure");
            } catch (RuntimeException e) {
                failure.set(e);
                p.forceTermination();
            }
        }, "failing-worker");
        worker.start();
        int result = p.arriveAndAwaitAdvance();
        worker.join(2_000);
        if (worker.isAlive()) throw new AssertionError("worker did not stop");
        System.out.println("failureObserved=" + (failure.get() != null));
        System.out.println("waiterReleasedByTermination=" + (result < 0));
        System.out.println("terminated=" + p.isTerminated());
        System.out.println("registeredCountsUnchanged=" + (p.getRegisteredParties() == 2));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PhaserFailureTerminationDemo.java
java PhaserFailureTerminationDemo
```

Stdout đã chạy:

```text
failureObserved=true
waiterReleasedByTermination=true
terminated=true
registeredCountsUnchanged=true
```

Worker mô phỏng lỗi, lưu cause rồi forceTermination; coordinator không cần đợi arrival từ worker lỗi. Ví dụ không tự coi `arriveAndDeregister()` là xử lý lỗi hợp lý: một party bị lỗi không được giả vờ đã tạo ra kết quả thành công nếu phase yêu cầu kết quả đó.

### 9.3. Phải báo lỗi qua channel riêng

Phaser chỉ đồng bộ phase; nó **không lưu lý do thất bại**. Nếu forceTermination làm `arriveAndAwaitAdvance()` trả giá trị âm, caller vẫn phải đọc failure từ `Future.get()`, `AtomicReference<Throwable>` hoặc một result channel có contract rõ. Đừng chỉ coi “Phaser terminated” là success hoặc timeout; nó có thể do last-party normal shutdown hoặc fatal failure.

## 10. Không có party identity: chống deregister hai lần

`Phaser` không biết “party A thuộc Thread T1”. Giả sử `new Phaser(2)` và code của A gọi `arriveAndDeregister()` hai lần trong cùng phase; lời gọi thứ hai có thể làm hết suất chờ của **party B** chứ không chắc API phát hiện “A đang tự rút hai lần”. Trường hợp tệ hơn là barrier advance quá sớm với dữ liệu B chưa chuẩn bị.

Cách phòng:
- Mỗi registration có một **owner duy nhất** ở tầng ứng dụng.
- Duy trì trạng thái `ACTIVE`/`ARRIVED`/`DEREGISTERED` theo phase.
- Không gọi `arriveAndDeregister()` sau khi một logical party đã deregister.
- Không gọi `arrive()` hai lần trong cùng phase.
- Nếu task thực hiện nhiều phases, cập nhật phase state theo kết quả barrier và xử lý lỗi một cách có coordination.
- Nếu nhiều callbacks cùng có thể xử lý cancellation, dùng guard kiểu `AtomicBoolean.compareAndSet` cho **một lần deregistration cuối cùng**.
- Không xem `getRegisteredParties()` là bằng chứng ownership để quyết định tự dereg bao nhiêu lần.

### 10.1. Chương trình 9 — một one-shot party handle có close idempotent

Đây là wrapper **minh họa dành riêng cho membership một lượt**: mỗi handle `register()` một suất, và `close()` thay mặt suất đó `arriveAndDeregister()` **tối đa một lần**. Nó không phải một abstraction đầy đủ cho tasks tham gia nhiều phases; nếu task đã arrive ở phase hiện tại, phải thiết kế state-aware cleanup như phần trên.

Lưu thành `PhaserPartyLeaseDemo.java`:

```java
import java.util.concurrent.Phaser;
import java.util.concurrent.atomic.AtomicBoolean;

public class PhaserPartyLeaseDemo {
    static final class OneShotParty implements AutoCloseable {
        final Phaser phaser;
        final AtomicBoolean active = new AtomicBoolean(true);
        OneShotParty(Phaser phaser) {
            this.phaser = phaser;
            int phase = phaser.register();
            if (phase < 0) throw new IllegalStateException("phaser terminated");
        }
        @Override public void close() {
            if (active.compareAndSet(true, false)) {
                phaser.arriveAndDeregister();
            }
        }
    }
    public static void main(String[] args) {
        Phaser p = new Phaser();
        OneShotParty a = new OneShotParty(p);
        OneShotParty b = new OneShotParty(p);
        System.out.println("initialParties=" + p.getRegisteredParties());
        a.close();
        System.out.println("afterFirstClose=" + p.getRegisteredParties());
        a.close(); // One-shot guard; do NOT deregister a different party
        System.out.println("afterDuplicateClose=" + p.getRegisteredParties());
        b.close();
        System.out.println("afterLastClose=" + p.getRegisteredParties());
        System.out.println("terminated=" + p.isTerminated());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PhaserPartyLeaseDemo.java
java PhaserPartyLeaseDemo
```

Stdout đã kiểm chứng:

```text
initialParties=2
afterFirstClose=1
afterDuplicateClose=1
afterLastClose=0
terminated=true
```

Hai handles đăng ký hai suất. `a.close()` giảm từ 2 xuống 1. `a.close()` thêm lần nữa **không** giảm từ 1 xuống 0, nhờ `AtomicBoolean` trong wrapper. Chỉ khi `b.close()` thì party cuối rút. Đây là **quản lý danh tính logical parties ở tầng ứng dụng**; bản thân Phaser không cấp một RegistrationToken object.

### 10.2. Rủi ro khi dùng AutoCloseable cho multi-phase workers

`OneShotParty.close()` giả định handle **chưa báo arrival nào trong phase hiện tại**. Với một worker thật đã gọi `arrive()` rồi chờ, close trong catch/finally của cùng phase sẽ là **arrival thứ hai**. Muốn wrapper cho multi-phase, phải lưu current phase và trạng thái đã-arrived, đồng bộ hóa với các callbacks/failures và quy định giải pháp nếu phase không thể hoàn tất. Đơn giản hơn, dùng forceTermination khi cả nhóm phải abort.

## 11. Phân cấp Phaser: child rút hết sẽ rút khỏi parent

`Phaser` hỗ trợ cấu trúc cây (*tiered phasers*) để giảm contention khi có rất nhiều parties. Một child tạo bằng `new Phaser(parent, n)` với n>0 được **đăng ký thành một party ở parent**. Khi child có zero parties do `arriveAndDeregister()`, child sẽ **tự deregister khỏi parent**.

Điều này quan trọng vì nếu child không dereg parent, parent có thể tiếp tục đợi một nhánh đã hết workers.

### 11.1. Chương trình 10 — child không còn party, parent đếm giảm

Lưu thành `PhaserTieredDropDemo.java`:

```java
import java.util.concurrent.Phaser;

public class PhaserTieredDropDemo {
    public static void main(String[] args) {
        Phaser parent = new Phaser(1); // Coordinator at parent
        Phaser child = new Phaser(parent, 2);
        System.out.println("parentInitiallyRegistered=" + parent.getRegisteredParties());
        child.arriveAndDeregister();
        System.out.println("childPartiesAfterOneDrop=" + child.getRegisteredParties());
        System.out.println("parentAfterOneDrop=" + parent.getRegisteredParties());
        child.arriveAndDeregister();
        System.out.println("childPartiesAfterLastDrop=" + child.getRegisteredParties());
        System.out.println("parentAfterChildZero=" + parent.getRegisteredParties());
        parent.arriveAndDeregister();
        System.out.println("parentTerminated=" + parent.isTerminated());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PhaserTieredDropDemo.java
java PhaserTieredDropDemo
```

Stdout đã kiểm chứng:

```text
parentInitiallyRegistered=2
childPartiesAfterOneDrop=1
parentAfterOneDrop=2
childPartiesAfterLastDrop=0
parentAfterChildZero=1
parentTerminated=true
```

Parent bắt đầu với coordinator (1) cộng child (1) = 2 parties. Child có hai parties nội bộ; rút một vẫn còn một nên parent vẫn 2. Child rút party cuối => child không còn party và tự deregister khỏi parent, khiến parent còn 1. Coordinator cuối cùng rút, parent terminated.

### 11.2. Không tự “deregister parent hộ child” lần thứ hai

Khi child đã được liên kết với parent, phần đăng ký/deregistration với parent được Phaser quản lý tự động. Không tự gọi `parent.arriveAndDeregister()` thay cho child **ngoài** suất parent của chính caller, nếu không sẽ có double deregistration và nguy cơ phase advance quá sớm.

### 11.3. Giới hạn số parties trong implementation hiện hành

Javadoc Java SE 17 ghi implementation `Phaser` hiện tại giới hạn tối đa **65.535 parties** trên một Phaser. `register()`/`bulkRegister()` vượt giới hạn có thể ném `IllegalStateException`. Với workloads rất lớn, dùng tiered phasers hoặc tổ chức nhóm theo cấp, không cố đăng ký quá giới hạn. Giới hạn này là thuộc tính implementation JDK được tài liệu hóa; không phải lời khuyên đăng ký hàng chục nghìn parties nếu workload nhỏ.

## 12. Registration trước submit và xử lý ExecutorService từ chối task

Một lỗi phổ biến:
1. Main gọi `phaser.register()`.
2. `executor.submit(...)` bị từ chối do pool shutdown/queue capacity.
3. Task không bao giờ chạy, nên không ai deregister suất vừa đăng ký.
4. Các parties còn lại chờ barrier vô hạn.

Phải **gỡ registration** nếu chưa bàn giao thành công quyền sở hữu cho task. Một mẫu logic một-lượt:

```java
phaser.register(); // Caller owns a newly created party slot.
try {
    executor.execute(() -> {
        try {
            doOneShotWork();
        } finally {
            phaser.arriveAndDeregister(); // Worker owns exactly this slot now.
        }
    });
} catch (RejectedExecutionException rejected) {
    phaser.arriveAndDeregister(); // Task was never accepted, caller still owns slot.
    throw rejected;
}
```

Đây là **snippet**, cần khai báo `Phaser phaser`, `Executor executor`, `doOneShotWork` và imports; **chỉ an toàn khi task không tự arrive trước finally**. Nếu `execute` được chấp nhận và task lại lỗi trong `doOneShotWork`, việc deregister có thể là policy “worker này rời và không cần kết quả”; nếu output của task bắt buộc cho vòng khác, hãy thêm error signal và dùng `forceTermination()` để abort thay vì giả như hoàn tất.

Đối với `ExecutorService.submit`, cũng có thể trả `Future` của task; nhưng việc cancel Future không làm party tự deregister trong mọi trường hợp, nhất là task bị cancel trước khi chạy. Hãy quản lý ownership ở wrapper/submission protocol, xử lý rejection, cancellation pre-start và cleanup sau completion bằng state guard.

## 13. Phases, memory visibility và waiting semantics

Javadoc `Phaser` công bố *memory consistency effects*: actions trước một hình thức `arrive` **happen-before** corresponding phase advance và actions trong `onAdvance`, từ đó **happen-before** actions sau phase advance. Vì thế barrier có thể đóng vai trò đồng bộ bộ nhớ giữa các tasks ở ranh giới phase.

**Nhưng rút party không đồng nghĩa chờ:**
- Worker gọi `arriveAndDeregister()` rồi lập tức dùng dữ liệu do các workers còn lại tạo **sau** đó không được bảo đảm chỉ vì đã dereg.
- Nếu cần thấy kết quả ở cuối phase, worker có thể gọi `awaitAdvance(arrivalPhase)` sau dereg, hoặc đồng bộ bằng Future/latch/volatile/lock theo contract.
- Biến shared mutable vẫn cần thiết kế thread-safe; Phaser không tự biến mọi truy cập shared collections thành an toàn.
- `getRegisteredParties()` và `getUnarrivedParties()` là snapshots giám sát, không thay happens-before/waiting.

### 13.1. onAdvance không phải chỗ để block dài

`onAdvance` được gọi bởi party làm phase hoàn tất. Nếu callback chặn lâu, phase advances và các waiters sẽ bị kéo dài. Không gọi lại register/arrival/await của chính Phaser trong `onAdvance` vì tài liệu nói behavior không được chỉ định. Chỉ làm công việc ngắn, deterministic và theo chính sách termination.

## 14. Một state machine tối thiểu cho party

```text
UNREGISTERED
     |
     | register hoặc bulkRegister trước khi submit
     v
REGISTERED_UNARRIVED (phase p)
     |                  \
     | arrive()          \ arriveAndDeregister()
     v                    \
ARRIVED_WAITING (p)        \--> DEREGISTERED
     |                         | (không tự wait)
     | awaitAdvance(p)         v
     v                       Có thể awaitAdvance(p) với tư cách observer
REGISTERED_UNARRIVED (phase p+1)
     |
     +-- tiếp tục vòng sau
     +-- rút đúng một lần (nếu chưa arrive phase này)
     |
     +-- lỗi fatal --> forceTermination() do coordinator quyết định
```

Đây là **state machine logic của ứng dụng**. `Phaser` không tự giữ enum per-party. Trạng thái `ARRIVED_WAITING` của một party không được xử lý bằng một `arriveAndDeregister()` nữa ngay ở phase p, vì như vậy sẽ báo arrival lần hai; hãy đợi phase advance hợp lệ hoặc terminate toàn nhóm theo failure policy.

### 14.1. Ba policy cần ghi rõ trong code review

1. **Normal completion:** Party làm xong và không tham gia phase sau; rút đúng một lần.
2. **Recoverable cancellation:** Party chưa đến, có thể rút mà không làm hỏng invariant; coordinator biết party này không cần cho output.
3. **Fatal failure:** Kết quả thiếu làm cả phase không còn đúng; forceTermination + propagate failure là policy hợp lý hơn deregister như success.

Tùy nghiệp vụ, một cancellation có thể thuộc nhóm 2 hoặc 3. Không có policy chung áp dụng máy móc cho mọi bài toán.

## 15. Ví dụ thường sai và cách sửa

### 15.1. Sai: gọi arrive rồi deregister cùng phase

```java
int p = phaser.arrive();
if (cancelled) {
    phaser.arriveAndDeregister(); // SAI: một party arrive hai lần ở phase p
}
```

Đây là **anti-pattern snippet**. Cần ghi nhớ đã đến ở phase nào. Nếu không thể hoàn tất phase do cancellation, forceTerminate theo policy hoặc để party chờ chuyển phase trước khi rút ở phase mới.

### 15.2. Sai: deregister lại trong hai catch/finally

```java
try {
    work();
    phaser.arriveAndDeregister();
} catch (RuntimeException ex) {
    phaser.arriveAndDeregister(); // Có thể thêm dereg khi work đã rút rồi
    throw ex;
} finally {
    phaser.arriveAndDeregister(); // Tiếp tục đếm sai, nghiêm trọng hơn
}
```

Đây là anti-pattern; nếu cần cleanup một-lượt, đặt dereg trong **một** finally và bảo đảm body không có arrival trước đó. Nếu có nhiều paths cạnh tranh, dùng ownership guard, không để exception handler/finally cùng tự decrement.

### 15.3. Sai: rút coordinator rồi nghĩ Phaser luôn sẽ còn sống

```java
Phaser p = new Phaser(1);
p.arriveAndDeregister();
p.register(); // Không đăng ký mới được: Phaser mặc định đã terminated
```

Đây là anti-pattern cho kỳ vọng tái sử dụng. Nếu muốn zero parties rồi re-register, override `onAdvance` trả false hoặc tạo Phaser mới theo vòng đời ứng dụng.

### 15.4. Sai: chờ vô thời hạn sau khi một party biến mất

```java
Phaser p = new Phaser(2);
p.arriveAndAwaitAdvance(); // Một party khác không tới -> chờ vô hạn
```

Đây là anti-pattern khi code còn lại không bao giờ báo arrival/deregister/terminate. Cần đảm bảo task lifecycle, cancellation path và một phương thức giải phóng nhóm khi failure. Đừng dùng `Thread.sleep` để hy vọng barrier tự hết hạn.

### 15.5. Sai: dùng số registered như số thread còn chạy

`getRegisteredParties()==3` chỉ là số suất đăng ký. Có thể ba parties thuộc một thread, hoặc một party xử lý qua nhiều threads. Muốn biết tasks kết thúc hay chưa, kiểm tra `Future`/executor lifecycle, không suy từ Phaser party count.

## 16. Bảng ngoại lệ và hiện tượng cần phân biệt

| Hiện tượng/ngoại lệ | Vì sao xảy ra | Hành động đúng |
| --- | --- | --- |
| `IllegalStateException` | Quá số parties tối đa, unarrived/registered đếm âm do arrival sai | Sửa ownership và base case; không retry mù |
| `arriveAndDeregister()` trả âm | Phaser đã terminated | Không coi như đã dereg thành công ở phase đang mở |
| `register()` trả âm | Phaser đã terminated; đăng ký không có tác dụng | Tạo Phaser mới hoặc đổi lifecycle policy |
| `isTerminated()==true` sau party cuối | Termination mặc định khi parties về 0 | Đúng nếu đã kết thúc hoàn toàn |
| `isTerminated()==true` do forceTermination | Coordinator ép dừng toàn nhóm | Đọc failure cause và cleanup |
| `TimeoutException` từ `awaitAdvanceInterruptibly` | Waiter hết hạn; Phaser state không tự thay đổi | Phối hợp cancel/forceTermination theo policy |
| `InterruptedException` từ interruptible await | Waiter bị interrupt; không tự deregister | Propagate/restore interrupt và tránh double arrival |
| `awaitAdvance()` không phản hồi | Còn party chưa đến hoặc không ai forceTerminate | Diagnostics, bounded wait/termination policy |
| Counts không như mong đợi | Register trước submit thất bại; double dereg; party còn đăng ký | Quản lý membership ownership rõ |
| Phase chuyển bất ngờ | Một party báo arrival hai lần hoặc registration race | Guard logical party/phase states |
| `forceTermination()` vẫn reports registered>0 | Theo API, termination không thay registered count | Không xem nó như bằng chứng task leak |
| Child về zero làm parent party giảm | Tự động tier deregistration | Không dereg parent hộ child lần nữa |

### 16.1. Tại sao không chỉ bắt IllegalStateException?

Javadoc nói việc một party chưa đăng ký gọi `arrive()/arriveAndDeregister()` là **usage error**, nhưng một số sai lầm có thể chỉ biểu hiện bằng `IllegalStateException` ở **operation sau**, hoặc không bao giờ hiện thành exception. Vì vậy exception không phải công cụ xác minh identity. Testing và state guard ở tầng ứng dụng là bắt buộc.

## 17. Kiểm thử concurrency mà không dựa vào timing may rủi

Một test đáng tin cho `arriveAndDeregister()` nên:
- Khởi tạo party count rõ, xác định ai sở hữu từng suất.
- Dùng `CountDownLatch` để bảo đảm test thread đã khởi động trước khi main thực hiện bước tiếp.
- Dùng `Future.get(timeout)` hoặc `Thread.join(timeout)` để test không treo vô hạn.
- Không suy thread scheduling theo thứ tự `println` giữa threads.
- Kiểm tra phase và party counts tại các thời điểm **được điều phối**.
- Tránh đọc snapshot counts giữa các arrivals đồng thời rồi assert giá trị tuyệt đối ngẫu nhiên.
- Với lỗi/cancel, quan sát riêng Phaser termination, task Future outcome và executor shutdown.
- Sau test, `forceTermination()` nếu cần để giải phóng waiters, rồi shutdown executor có timeout.
- Không lạm dụng `Thread.sleep` thay `CountDownLatch` cho coordination.
- Chạy nhiều lượt và đưa vào CI với kiểm thử điều kiện race/registration.

### 17.1. Điều gì không thể kiểm tra chỉ với isTerminated?

`isTerminated()` không nói worker đã chạy thành công, liệu output đúng, liệu exception đã được propagate, hay executor threads đã dừng. Test cần kiểm chứng riêng kết quả nghiệp vụ, `Future` và cleanup. Thậm chí khi terminated, registered count có thể vẫn dương nếu forceTermination.

## 18. So sánh Phaser với những công cụ khác

| Công cụ | Khi nào phù hợp | Vì sao Phaser deregister khác |
| --- | --- | --- |
| `CountDownLatch` | Đợi một nhóm tác vụ một lần | Latch không reset cho nhiều phases và không có dynamic party registration |
| `CyclicBarrier` | N threads cố định gặp nhau lặp lại | Không thiết kế để party count thay đổi linh hoạt sau mỗi vòng |
| `Phaser` | Nhiều vòng, thay đổi số parties, các subgroups | `arriveAndDeregister` vừa đến vừa rút khỏi các phase kế tiếp |
| `CompletableFuture` | Phối hợp kết quả/tác vụ bất đồng bộ | Không phải barrier N party tái sử dụng theo phase |
| `Structured concurrency` (nếu runtime hỗ trợ) | Quản lý vòng đời tasks cha/con theo scope | Không tự thay thế Phaser khi cần barrier nhiều vòng có party động |

Trong Java 17, `Phaser` là API ổn định trong `java.base`; không cần các tính năng preview để dùng. Tránh mô tả Java 17 đã có một API structured concurrency ổn định tương đương Phaser: tại thời điểm Java 17, đây không phải lựa chọn thay thế trực tiếp để deregister các phases.

## 19. Hiệu năng và khả năng mở rộng

`Phaser` hỗ trợ đăng ký/rút linh hoạt nhưng mỗi arrival có chi phí đồng bộ. Đừng tạo phase cho từng phép tính cực nhỏ nếu số worker cực lớn rồi kỳ vọng overhead miễn phí.

Một vài tiêu chí:
- Số phases mỗi giây và số parties mỗi phase.
- Tần suất register/deregister (biến động nhiều có thể gây contention).
- Chi phí `onAdvance`, không nên block.
- Có cần tiered phasers để giảm contention khi rất đông parties?
- Số threads đang chờ, giới hạn parallelism của `ForkJoinPool` hoặc ExecutorService.
- Sự tồn tại của một coordinator party giúp giữ phaser sống nhưng có thể gây deadlock nếu coordinator quên arrival.
- Chiến lược abort toàn bộ khi một worker thất bại.
- Rủi ro worker bị cancel trước khi chạy nhưng slot đã đăng ký.
- Nhu cầu tách nhóm workers cho từng pipeline/task batch thay vì reuse một Phaser không rõ owner.

Javadoc nêu `Phaser` có thể dùng với `ForkJoinPool`, và tiến độ được đảm bảo khi mức song song đủ cho số parties có thể bị blocked cùng lúc. Đừng dùng một pool quá nhỏ cho nhiều tasks đều đứng chờ barrier trước khi các tasks còn lại được lên lịch; đó là nguy cơ starvation không thể sửa chỉ bằng `arriveAndDeregister`.

## 20. Checklist code review

1. Có phân biệt logical party với Thread?
2. Có xác định mỗi `register()` thuộc owner nào?
3. Có đăng ký trước khi tasks bắt đầu cần đồng bộ?
4. Có gỡ slot nếu submission bị rejected?
5. Có phân biệt `arrive()`, `arriveAndAwaitAdvance()`, `arriveAndDeregister()`?
6. Worker rút có đúng là đã hoàn tất trách nhiệm ở phase hiện tại?
7. Worker còn dùng Phaser ở phase sau có bị rút nhầm không?
8. Có gọi `arriveAndDeregister` đúng một lần cho mỗi logical party?
9. Có tránh double arrival khi vừa `arrive()` vừa dereg trong cùng phase?
10. Có guard các callback/cancellation paths cạnh tranh?
11. Có hiểu `arriveAndDeregister` không chờ?
12. Nếu muốn rút rồi đợi, có dùng `awaitAdvance(returnedPhase)`?
13. Có xử lý phase return âm/termination?
14. Có hiểu party cuối rút làm default Phaser terminated?
15. Nếu cần re-register từ zero, có chủ động override `onAdvance` hoặc tạo phaser mới?
16. Có tránh gọi lại Phaser methods trong `onAdvance`?
17. Có giữ callback `onAdvance` nhanh và không block?
18. Nếu party timeout sau `arrive`, có tránh dereg ngay cùng phase?
19. `awaitAdvanceInterruptibly` timeout/interrupt có được hiểu là không tự thay đổi registered count?
20. Có policy rõ cho recoverable withdrawal và fatal failure?
21. Khi fatal failure, có propagate cause và `forceTermination` theo owner?
22. Có hiểu `forceTermination` không giảm registered count?
23. Có dùng Future/ExecutorService để xác nhận tasks thật đã dừng?
24. Có dùng `getRegisteredParties/getUnarrivedParties` chỉ để monitor, không làm synchronization control?
25. Có xử lý parent-child phaser tự dereg khi child về zero?
26. Có tránh dereg parent hai lần?
27. Có kiểm tra giới hạn parties (implementation 65.535)?
28. Có tránh chờ barrier vô hạn khi worker biến mất?
29. Test có dùng latch/future/deadline thay sleep-based race assumptions?
30. Có làm sạch executor/threads sau khi Phaser hoàn tất?

## 21. Tự kiểm tra kiến thức

**Câu 1.** `arriveAndDeregister()` có chờ các parties khác không?  
**Đáp án:** Không, method ghi arrival và rút suất đăng ký, không chờ barrier.

**Câu 2.** So với `arrive()` khác gì?  
**Đáp án:** `arrive()` không rút party khỏi các phase sau.

**Câu 3.** So với `arriveAndAwaitAdvance()` khác gì?  
**Đáp án:** Method kia vừa arrive vừa chờ và vẫn registered.

**Câu 4.** Giá trị int trả về là phase mới hay phase arrival?  
**Đáp án:** Phase mà arrival được ghi nhận; có thể khác `getPhase()` ngay sau đó.

**Câu 5.** Sau `new Phaser(3)`, một arrive và một dereg thì registered/unarrived còn bao nhiêu?  
**Đáp án:** registered 2, unarrived 1, nếu phase chưa advance.

**Câu 6.** Worker đã dereg có cần arrive ở phase sau không?  
**Đáp án:** Không; nếu muốn tham gia lại phải register phù hợp khi Phaser còn active.

**Câu 7.** Party cuối rút thì Phaser mặc định thế nào?  
**Đáp án:** Terminated do `onAdvance` mặc định.

**Câu 8.** `register()` sau khi terminated có khôi phục Phaser không?  
**Đáp án:** Không; trả giá trị âm, không đăng ký.

**Câu 9.** Muốn zero parties mà vẫn active để nhận đăng ký mới?  
**Đáp án:** Tạo policy `onAdvance` trả false, hoặc tạo Phaser mới khi thích hợp.

**Câu 10.** Có thể gọi `awaitAdvance(arriveAndDeregister())` không?  
**Đáp án:** Có; đợi chuyển phase sau khi đã rút, không tái đăng ký.

**Câu 11.** `awaitAdvanceInterruptibly` timeout có tự rút party không?  
**Đáp án:** Không.

**Câu 12.** `arrive()` rồi catch timeout gọi `arriveAndDeregister()` ngay cùng phase có an toàn?  
**Đáp án:** Không; có thể double arrival.

**Câu 13.** Phaser lưu danh sách Thread IDs đã đăng ký?  
**Đáp án:** Không, chỉ quản lý counters, không identity.

**Câu 14.** Làm sao tránh hai code paths cùng dereg một slot?  
**Đáp án:** Ownership rõ và guard như AtomicBoolean/party state.

**Câu 15.** Worker lỗi bắt buộc cho output thì nên bình thường dereg?  
**Đáp án:** Thường không; cần fail-fast/forceTermination và propagate failure.

**Câu 16.** `forceTermination` có tự giảm registered counts?  
**Đáp án:** Không.

**Câu 17.** Child phaser hết parties thì parent tự xảy ra gì?  
**Đáp án:** Child tự deregister khỏi parent theo tiered behavior.

**Câu 18.** `getUnarrivedParties()` sau termination có đáng tin?  
**Đáp án:** Không; Javadoc nói giá trị có thể vô nghĩa/arbitrary.

**Câu 19.** Vì sao phải register trước submit?  
**Đáp án:** Tránh phase advance trước khi task tham gia; nếu submit bị từ chối phải dereg slot.

**Câu 20.** Có thể dùng Phaser ổn định trên Java 17 không?  
**Đáp án:** Có, API `java.util.concurrent.Phaser` thuộc Java SE từ Java 7 và còn được hỗ trợ.

## 22. Bài tập thực hành

### Bài A — timeline bộ đếm

Chạy `PhaserCountsDemo`, ghi bảng phase/registered/unarrived trước và sau mỗi lệnh; giải thích vì sao deregReturned=0 nhưng getPhase có thể thành 1 sau lần arrive cuối.

### Bài B — không chờ

Chạy `PhaserNonBlockingDemo`, thay một `arrive()` bằng một `arriveAndDeregister()` của party cuối; quan sát phase advance và số registered còn lại. Không thay đổi ownership bừa bãi.

### Bài C — worker rút sớm

Chạy `PhaserMultiRoundDemo`, cho worker ngắn làm hai vòng thay vì một. Bảo đảm coordinator/worker dài vẫn tiến qua ba phases và cuối cùng Phaser terminated.

### Bài D — last party và lifecycle

Chạy `PhaserLastPartyDemo`; thử `new Phaser(0)` và `register()` trước bất kỳ deregistration nào, so sánh với register sau default termination.

### Bài E — onAdvance policy

Chạy `PhaserNonTerminatingDemo`; thay return false bằng `return registeredParties == 0` và mô tả vì sao không re-register được sau zero-party transition.

### Bài F — rút rồi chờ

Chạy `PhaserDeregisterThenAwaitDemo`; thay `awaitAdvance` bằng interruptible timed await và mô tả xử lý TimeoutException mà không tái đăng ký party.

### Bài G — timeout không tự đổi state

Chạy `PhaserTimedAwaitDemo`; sau timeout giải thích vì sao registered vẫn 2 và unarrived vẫn 1, sau đó thay B dereg bằng B arrive.

### Bài H — fail-fast

Chạy `PhaserFailureTerminationDemo`; theo dõi failure cause riêng với `isTerminated`, và kiểm tra registeredCount không thay đổi sau forceTermination.

### Bài I — chống double dereg

Chạy `PhaserPartyLeaseDemo`; bỏ AtomicBoolean guard trong bản thử nghiệm được cô lập và giải thích nguy cơ đóng nhầm slot của party B. Khôi phục guard trước khi triển khai.

### Bài J — tiered Phaser

Chạy `PhaserTieredDropDemo`; đổi child từ hai thành ba parties, kiểm tra parent không giảm cho tới khi child về zero.

### Bài K — cancellation pre-start

Tạo `ExecutorService` đã shutdown, thử submit một task sau `register()`. Bắt `RejectedExecutionException` và dereg slot trong caller; xác minh không còn phantom party.

### Bài L — nhiều phases và lỗi sau arrive

Thiết kế state machine per logical party với trạng thái chưa arrive/đã arrive/đã dereg. Khi timed await bị lỗi sau arrive, không được double arrival; mô tả khi nào gọi forceTermination.

## 23. Tài liệu Java chính thức

- [Oracle Java SE 17 — Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): `arriveAndDeregister`, counts, onAdvance, termination, tiering, waiting, memory effects và số parties tối đa.
- [Oracle Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordination trong các ví dụ kiểm thử concurrency.
- [Oracle Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý task submission, futures và shutdown.
- [Oracle Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get` và cancellation.
- [Oracle Java SE 17 — TimeUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): timed waits.
- [Oracle Java SE 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): quan hệ giữa pool parallelism và các tasks có thể block tại Phaser.

**Kết luận:** `arriveAndDeregister()` là cách một logical party **vừa báo đã đến vừa rút khỏi những phase sau, không chờ**. Nó giúp những workers còn lại không bị ràng buộc bởi một participant đã hoàn tất. Nhưng việc rút an toàn đòi hỏi quản lý ownership và phase state: không báo arrival/deregister hai lần, không coi timeout/interruption tự rút group, phân biệt normal withdrawal với fatal failure, hiểu last-party termination và xử lý parent-child tự động khi dùng tiered Phaser. Khi thiết kế đúng, `Phaser` vẫn là công cụ đồng bộ nhiều giai đoạn có party động phù hợp với Java hiện đại.
