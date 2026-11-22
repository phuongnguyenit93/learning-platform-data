# 22.3 Tái hiện deadlock rồi dựng vòng chờ từ nhiều nguồn bằng chứng

## Mục tiêu

**Deadlock** là tình trạng một nhóm luồng không thể tiến triển vì mỗi luồng đang chờ tài nguyên do luồng khác trong chính nhóm giữ, tạo thành một **chu trình quan hệ chờ**. Trong Java, một ví dụ dễ kiểm chứng là hai platform threads giữ hai monitor theo thứ tự ngược nhau.

Bài thực hành này hướng dẫn:

1. **Tái hiện deadlock có chủ đích, có thể lặp lại** với synchronized, hai object locks và CountDownLatch; không chỉ tăng xác suất bằng Thread.sleep.
2. Đọc **ThreadMXBean.findMonitorDeadlockedThreads()**, **findDeadlockedThreads()**, **ThreadInfo.getLockOwnerName()**, trạng thái và các monitors đang giữ.
3. Thu **jcmd PID Thread.print -l** hoặc **jstack -l**, ghép các dòng waiting-to-lock/locked theo cùng monitor identity và đối chiếu owner từ MXBean.
4. Ghi **JFR custom events** mô tả mốc trước khi BLOCKED, đọc summary/metadata/print và hiểu vì sao một sự kiện jdk.JavaMonitorEnter của lần chờ vô hạn có thể không nằm trong recording.
5. Xây **wait-for graph** có hướng, xác minh cạnh A → B và B → A rồi tìm cycle.
6. Sửa lỗi bằng **global lock order**, kiểm chứng bằng regression test phù hợp và phân biệt monitor deadlock với contention, starvation, sleep/park, I/O stall, distributed deadlock.

**An toàn:** mã đầu tiên cố tình làm hai threads kẹt vĩnh viễn. Chỉ chạy ở môi trường lab được phép, không chạy trong dịch vụ production; không sử dụng Thread.stop hay kill -9 để “kiểm thử” ứng dụng thật.

## 1. Vòng chờ xuất hiện như thế nào?

Giả sử hai shared objects có monitors đặt tên dễ đọc là LEFT và RIGHT.

~~~text
worker-A                      worker-B
--------                      --------
synchronized(LEFT)            synchronized(RIGHT)
  đang giữ LEFT                 đang giữ RIGHT
        |                             |
  yêu cầu RIGHT                 yêu cầu LEFT
        |                             |
  B đang giữ RIGHT              A đang giữ LEFT
        |                             |
        +----------- chu trình ------+
~~~

Hai mức biểu diễn:

~~~text
Đồ thị tài nguyên:
  worker-A --> RIGHT --> worker-B --> LEFT --> worker-A

Đồ thị wait-for chỉ gồm threads:
  worker-A --> worker-B
  worker-B --> worker-A
~~~

Quy ước **T → U** nghĩa là T đang chờ một lock do U giữ. Hai cạnh đối nghịch tạo chu trình; Java monitor chỉ thuộc một thread ở một thời điểm nên cả hai không thể lấy được lock tiếp theo và tự hoàn tất.

### Bốn điều kiện cần hiểu

- **Mutual exclusion:** monitor không được sở hữu đồng thời bởi hai threads.
- **Hold and wait:** mỗi thread giữ một lock trong lúc chờ lock khác.
- **No preemption:** không có cơ chế an toàn tự cướp monitor từ thread chủ sở hữu.
- **Circular wait:** A chờ B và B chờ A.

Một thread đang **BLOCKED** chưa đủ kết luận deadlock: có thể nó chỉ đang chờ một thread khác làm việc xong. Phải chứng minh **vòng chờ khép kín** hoặc có bằng chứng deadlock tương đương.

**Synchronized không có timed try-acquire** như ReentrantLock.tryLock(timeout,...). Khi worker bị BLOCKED ở entry của intrinsic monitor, interrupt thông thường không khiến nó nhả monitor hay hủy lệnh lấy lock.

## 2. Những bằng chứng cần lấy

| Nguồn | Câu hỏi có thể trả lời | Giới hạn |
| --- | --- | --- |
| **Source code** | Thứ tự lấy locks nào có thể tạo vòng? | Code cho khả năng, chưa chứng minh trạng thái runtime |
| **ThreadMXBean** | Thread nào BLOCKED, chờ lock nào, owner là ai? Có monitor cycle không? | Chủ yếu platform threads và các resource kinds JVM hỗ trợ |
| **jcmd Thread.print -l** | Stack, trạng thái, waiting-to-lock identity và locked identity ở thời điểm chụp? | Snapshot có thể tốn thời gian, format theo JVM/JDK |
| **JFR custom event** | A/B đã giữ lock đầu và thử lock thứ hai khi nào? | Mốc ứng dụng, chưa phải lời chứng độc lập về owner hiện tại |
| **JFR built-in events** | Có contention/park/wait trước sự cố? | Event settings, threshold và event đang chờ chưa kết thúc |
| **OS/JVM metrics** | Đúng PID? process còn sống? CPU/threads thay đổi? | OS không tự giải mã Java monitor ownership |

Không phải càng nhiều file thì càng đúng. **Thread dump và ThreadMXBean** chứng minh owner graph; **JFR** chứng minh timeline dẫn đến trạng thái đó; **source code** giải thích tại sao trình tự tạo vòng chờ.

## 3. Vì sao dùng CountDownLatch thay Thread.sleep?

Một ví dụ ngây thơ dùng Thread.sleep để hy vọng hai threads giữ lock đầu trong cùng thời điểm có thể **không bao giờ tái hiện** deadlock dưới scheduler khác.

Chúng ta dùng hai CountDownLatch:

1. Worker A vào synchronized(LEFT), đánh dấu A đã sở hữu LEFT và mở latch A.
2. Worker B vào synchronized(RIGHT), đánh dấu B đã sở hữu RIGHT và mở latch B.
3. A chỉ được thử synchronized(RIGHT) sau khi biết B đã giữ RIGHT.
4. B chỉ được thử synchronized(LEFT) sau khi biết A đã giữ LEFT.
5. Cả hai vẫn **giữ lock thứ nhất** trong lúc chờ/thử lock thứ hai, nên vòng chờ sẽ hình thành.

Trong giai đoạn chờ latch, threads có thể hiện trạng thái **WAITING**. Sau khi cả hai latches đã mở và chúng tranh lock thứ hai, chúng chuyển sang **BLOCKED (on object monitor)**. Cần chọn đúng thời điểm thu thread dump.

## 4. Chương trình Java 17+ độc lập: DeadlockEvidenceLab.java

Chương trình tạo monitor deadlock, ghi custom JFR events **lab.LockMilestone**, phát hiện cycle bằng ThreadMXBean, xuất file **deadlock-evidence.jfr** và giữ JVM còn sống khoảng 120 giây để thu thread dump từ terminal khác.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Comparator;
import java.util.concurrent.CountDownLatch;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class DeadlockEvidenceLab {
    private static final Object LEFT = new Object();
    private static final Object RIGHT = new Object();

    private static final CountDownLatch LEFT_HELD =
            new CountDownLatch(1);
    private static final CountDownLatch RIGHT_HELD =
            new CountDownLatch(1);

    @Name("lab.LockMilestone")
    @Label("Lock Milestone")
    @Category({"Lab", "Concurrency"})
    public static class LockMilestone extends Event {
        @Label("Worker")
        public String worker;
        @Label("Action")
        public String action;
        @Label("Lock Name")
        public String lockName;
    }

    private static void emit(String worker, String action,
                             String lockName) {
        LockMilestone event = new LockMilestone();
        if (event.isEnabled()) {
            event.worker = worker;
            event.action = action;
            event.lockName = lockName;
            event.commit();
        }
    }

    private static void launch(String name,
                               Object first, String firstName,
                               Object second, String secondName,
                               CountDownLatch own,
                               CountDownLatch other) {
        Thread worker = new Thread(() -> {
            synchronized (first) {
                emit(name, "ACQUIRED_FIRST", firstName);
                own.countDown();

                try {
                    other.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }

                emit(name, "TRY_SECOND", secondName);
                synchronized (second) {
                    // Deadlock có chủ đích: không tới đoạn này.
                    emit(name, "ACQUIRED_SECOND", secondName);
                }
            }
        }, name);

        // Chỉ để main có thể kết thúc sau khoảng lab:
        worker.setDaemon(true);
        worker.start();
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.enable(LockMilestone.class)
                    .withoutThreshold();
            recording.start();

            launch("worker-A", LEFT, "LEFT", RIGHT, "RIGHT",
                    LEFT_HELD, RIGHT_HELD);
            launch("worker-B", RIGHT, "RIGHT", LEFT, "LEFT",
                    RIGHT_HELD, LEFT_HELD);

            ThreadMXBean bean =
                    ManagementFactory.getThreadMXBean();
            long[] ids = null;

            // Lab: tối đa khoảng 5 giây để kiểm tra cycle.
            // Không polling dày kiểu này ở production.
            for (int attempt = 0; attempt < 100; attempt++) {
                ids = bean.findMonitorDeadlockedThreads();
                if (ids != null && ids.length == 2) {
                    break;
                }
                Thread.sleep(50L);
            }
            if (ids == null || ids.length != 2) {
                throw new IllegalStateException(
                        "Expected a two-thread monitor deadlock");
            }

            ThreadInfo[] infos =
                    bean.getThreadInfo(ids, true, true);
            Arrays.sort(infos, Comparator.comparing(
                    ThreadInfo::getThreadName));

            System.out.println("Deadlocked threads: "
                    + infos.length);
            for (ThreadInfo info : infos) {
                System.out.println(info.getThreadName()
                        + " -> " + info.getLockOwnerName()
                        + " (" + info.getThreadState() + ")");
            }

            recording.stop();
            recording.dump(Path.of("deadlock-evidence.jfr"));

            System.out.println("JFR saved: deadlock-evidence.jfr");
            System.out.println("PID: "
                    + ProcessHandle.current().pid());
            System.out.println("Snapshot window: 120 seconds");

            Thread.sleep(120_000L);
        }
    }
}
~~~

**Biên dịch và chạy** bằng JDK 17+ HotSpot/OpenJDK có module jdk.jfr:

~~~bash
javac --add-modules java.management,jdk.jfr DeadlockEvidenceLab.java
java --add-modules java.management,jdk.jfr DeadlockEvidenceLab
~~~

**Các dòng do chương trình in khi chạy thành công** (PID thay đổi theo lần chạy):

~~~text
Deadlocked threads: 2
worker-A -> worker-B (BLOCKED)
worker-B -> worker-A (BLOCKED)
JFR saved: deadlock-evidence.jfr
PID: <PID thực tế>
Snapshot window: 120 seconds
~~~

**<PID thực tế> là placeholder minh họa**, không phải literal output của Java. Ngoài PID, cấu trúc hai cạnh và thứ tự hai dòng được ổn định nhờ sort theo thread name. Kết quả JFR thật có timestamps và event order tùy scheduler.

Nếu JFR không được hỗ trợ trong runtime, không ghi được file, hoặc thread detector báo lỗi quyền/VM capabilities thì ví dụ có thể ném exception; phải sửa môi trường thay vì coi đây là “không có deadlock”.

### Chú thích các điểm quan trọng

- **CountDownLatch** bảo đảm cả hai thread đã vào lock thứ nhất trước khi thử lấy lock thứ hai; không có sleep giả để “hy vọng đúng timing”.
- **ThreadMXBean.findMonitorDeadlockedThreads()** trả IDs của threads trong chu trình object monitors, hoặc **null** nếu không tìm thấy chu trình thuộc phạm vi hỗ trợ.
- **getThreadInfo(ids, true, true)** yêu cầu lock ownership details; HotSpot thông thường hỗ trợ monitors và ownable synchronizers.
- **Recording.stop() rồi dump(Path)** lưu custom milestone events trước khi người học thu jcmd, nên file vẫn đọc được trong khi JVM còn sống.
- **setDaemon(true)** không “giải cứu” deadlock; nó chỉ cho phép JVM thoát khi main và các non-daemon threads khác đã kết thúc. Không áp dụng cách này để sửa dịch vụ thật.
- **Snapshot window 120 seconds** chỉ là khoảng giúp người học mở terminal khác. Không phải bảo đảm về deadline công cụ hay hệ thống.

### Vì sao chương trình sẽ tạo vòng chờ?

Ở thời điểm mỗi latch được count down, luồng đó đang **nằm trong synchronized(first)**. LEFT_HELD và RIGHT_HELD chỉ cùng mở sau khi A nắm LEFT và B nắm RIGHT. Hai monitor này vẫn được giữ khi await kết thúc. A cần RIGHT do B giữ; B cần LEFT do A giữ. Kết quả là mỗi luồng không thể tiếp tục nếu luồng kia chưa nhả khóa, còn luồng kia cũng không thể nhả khóa khi đang bị chặn.

Hai custom events **ACQUIRED_FIRST** xảy ra trước các events **TRY_SECOND** của cùng worker. Tuy nhiên thứ tự giữa A và B không cố định. **ACQUIRED_SECOND** không xuất hiện trong bản ghi bình thường vì không luồng nào lấy được second lock.

## 5. Phát hiện từ ThreadMXBean

**java.lang.management.ThreadMXBean** cung cấp dữ liệu thread state và lock ownership trong JVM. Những API cần phân biệt:

| API | Phạm vi |
| --- | --- |
| **findMonitorDeadlockedThreads()** | Chu trình platform threads chờ **object monitors** (synchronized) |
| **findDeadlockedThreads()** | Chu trình platform threads chờ **object monitors hoặc ownable synchronizers** như ReentrantLock khi VM hỗ trợ |
| **getThreadInfo(ids, true, true)** | Stack và thông tin locked monitors/ownable synchronizers cho IDs |
| **dumpAllThreads(true, true)** | Snapshot live **platform threads**, có thể tốn chi phí khi rất nhiều threads |

Trong **Java 21**, ThreadMXBean không hỗ trợ giám sát **virtual threads**; null từ detector không chứng minh toàn hệ thống không có deadlock, đặc biệt các cycles có virtual threads, database locks hoặc phân tán nhiều JVM.

### ThreadInfo: các trường cần ghi

- **getThreadName() / getThreadId()**: tên và Java thread ID tại thời điểm snapshot; Java ID không phải OS TID/nid.
- **getThreadState()**: BLOCKED, WAITING, TIMED_WAITING, RUNNABLE...
- **getLockName() / getLockInfo()**: đối tượng thread đang chờ.
- **getLockOwnerName() / getLockOwnerId()**: luồng chủ sở hữu monitor/ownable synchronizer đang chờ.
- **getLockedMonitors()**: monitors thread đang giữ.
- **getLockedSynchronizers()**: ownable synchronizers mà thread đang giữ.
- **getStackTrace()**: frame/đường code đang bị chặn.
- **getBlockedTime()**: có thể trả -1 khi contention monitoring không bật/không hỗ trợ.

Một **edge** được tạo khi có quan hệ rõ ràng: “thread T chờ lock do thread U giữ” → **T → U**.

~~~text
worker-A state=BLOCKED
  waiting=RIGHT; owner=worker-B; holds=LEFT
  => worker-A --> worker-B

worker-B state=BLOCKED
  waiting=LEFT; owner=worker-A; holds=RIGHT
  => worker-B --> worker-A
~~~

Trong output thật, ThreadMXBean biết lock identity/owner nhưng không tự biết nhãn nghiệp vụ **LEFT/RIGHT** nếu code không mô tả; đây là cách diễn giải kết hợp với source. Luôn dùng owner IDs/monitor identities thuộc **cùng snapshot** khi dựng đồ thị, thay vì chỉ so tên thread.

### BLOCKED, WAITING và TIMED_WAITING

- **BLOCKED** là chờ để vào/reenter intrinsic monitor bị giữ.
- **WAITING** có thể do Object.wait(), CountDownLatch.await(), Thread.join() hoặc LockSupport.park(); không đồng nghĩa deadlock.
- **TIMED_WAITING** có thể do Thread.sleep(), timed await/park; thường mang timeout bình thường.
- **RUNNABLE** không bảo đảm thread thật sự tiêu thụ CPU tại thời điểm OS đo; có thể đang ở các native operations.

Ở lúc chạy demo ban đầu, threads chờ latch có thể hiện **WAITING**. Khi cả hai thử synchronized(second), chúng trở thành **BLOCKED**. Đây là lý do lấy snapshot đúng thời điểm và, khi có thời gian, lặp lại sau vài giây.

## 6. Nguồn độc lập: jcmd Thread.print -l và jstack -l

Trong khoảng JVM còn sống, mở terminal khác trên **cùng máy/namespace có thể attach JVM**.

### 6.1. Tìm đúng PID

~~~bash
jcmd -l
jcmd <PID> help Thread.print
~~~

Thay **<PID>** bằng số process do chương trình in. Dấu ngoặc nhọn chỉ là placeholder; đừng gõ nguyên văn trong shell. Với Docker/Kubernetes, PID trong container và trên host có thể khác; jcmd cần quyền attach và effective user/group thích hợp.

### 6.2. Lấy một thread dump

~~~bash
jcmd <PID> Thread.print -l > deadlock-thread-dump.txt
~~~

Trong JDK 21, **Thread.print -l** in stack và thông tin locks/concurrent synchronizers; thường có phần báo deadlock Java-level khi VM phát hiện. Tùy phiên bản, cú pháp và các trường cụ thể cần xác minh bằng **jcmd PID help Thread.print**.

Cũng có thể dùng:

~~~bash
jstack -l <PID> > deadlock-jstack.txt
~~~

Tài liệu Oracle khuyến nghị ưu tiên jcmd trong nhiều công việc chẩn đoán. Khi chỉ còn ít thời gian trước restart, ưu tiên **một snapshot đầy đủ**, không chờ đủ nhiều công cụ. Thread dump có thể gây overhead khi số threads lớn hoặc VM không phản hồi attach.

### 6.3. Mẫu thread dump đã rút gọn

Đây là **ví dụ cấu trúc**, không phải stdout cố định; địa chỉ, line numbers, nid và cách trình bày thay đổi theo JVM:

~~~text
"worker-A" ... java.lang.Thread.State: BLOCKED (on object monitor)
  - waiting to lock <0x0000BBBB> (a java.lang.Object)
  - locked <0x0000AAAA> (a java.lang.Object)

"worker-B" ... java.lang.Thread.State: BLOCKED (on object monitor)
  - waiting to lock <0x0000AAAA> (a java.lang.Object)
  - locked <0x0000BBBB> (a java.lang.Object)

Found one Java-level deadlock:
  worker-A waits for monitor held by worker-B
  worker-B waits for monitor held by worker-A
~~~

Cách suy luận:

1. A chờ monitor **BBBB**.
2. B đang **giữ BBBB**.
3. B chờ monitor **AAAA**.
4. A đang **giữ AAAA**.
5. Suy ra **A → B → A**, một chu trình không có thread nào có thể tiến triển.

**Không giả định các giá trị 0xAAAA/0xBBBB là cố định.** Trong output thực, hãy match chính các token monitor IDs trong **cùng một thread dump**. Không lấy **System.identityHashCode(obj)** rồi so trực tiếp với VM object address: đó là các khái niệm/biểu diễn khác nhau.

### 6.4. Nếu trạng thái chưa chắc chắn

Lấy snapshot thứ hai sau khoảng ngắn nếu process còn sống:

~~~bash
sleep 5
jcmd <PID> Thread.print -l > deadlock-thread-dump-2.txt
~~~

Với deadlock thật, owner cycle lặp lại và các threads không tiến triển. Nhưng một monitor contention dài cũng có thể không thay đổi qua hai snapshots; **chính chu trình ownership/waiting** mới là điểm quyết định.

Nếu jcmd không attach được, ghi lỗi cùng timestamp, không suy “không deadlock”. Một số HotSpot trên Linux có thể in dump khi nhận **SIGQUIT** theo runbook, nhưng cần quyền, đúng process và quản lý output. Không gửi kill -9 và không chủ động phá dữ liệu.

## 7. Nguồn timeline: JFR custom milestone events

Trong chương trình lab, recording được cấu hình:

~~~java
recording.enable(LockMilestone.class)
        .withoutThreshold();
recording.start();
~~~

Sau khi detector tìm thấy vòng, chương trình **stop() rồi dump()** thành file JFR. Custom type **lab.LockMilestone** có các trường:

| Field | Ví dụ | Nghĩa |
| --- | --- | --- |
| worker | worker-A | Thread phát dấu mốc |
| action | ACQUIRED_FIRST, TRY_SECOND | Vị trí đã đi qua trong code |
| lockName | LEFT, RIGHT | Nhãn nghiệp vụ do lập trình viên định nghĩa |
| startTime/eventThread | Do JVM ghi nếu có | Mốc thời gian/luồng tạo event |

Các lệnh:

~~~bash
jfr summary deadlock-evidence.jfr
jfr metadata --events lab.LockMilestone deadlock-evidence.jfr
jfr print --events lab.LockMilestone deadlock-evidence.jfr
~~~

- **summary**: recording start/duration, số instances theo type và serialized size.
- **metadata**: event name, category, field schema.
- **print**: từng instance và giá trị field, timestamps.

Trong một run đúng, có **bốn milestone records**: A và B mỗi luồng phát **ACQUIRED_FIRST** và **TRY_SECOND**. Ví dụ một thứ tự hợp lệ:

~~~text
worker-A  ACQUIRED_FIRST  LEFT
worker-B  ACQUIRED_FIRST  RIGHT
worker-B  TRY_SECOND      LEFT
worker-A  TRY_SECOND      RIGHT
~~~

Thứ tự A/B có thể khác. **Không có ACQUIRED_SECOND** vì synchronized(second) không được vào. Không suy từ JFR custom events đơn lẻ rằng locks thật sự thuộc owner nào: các mốc do code phát giúp mô tả timeline, còn thread dump/ThreadInfo là bằng chứng độc lập về ownership hiện tại.

### Vì sao jdk.JavaMonitorEnter có thể không có sự kiện của deadlock?

Trong JFR, **jdk.JavaMonitorEnter** mô tả contended monitor entry, thường là duration event. Với lần chờ **không bao giờ hoàn tất**, event chưa có điểm kết thúc để ghi theo cơ chế thông thường; file có thể không chứa instance tương ứng. Ngoài ra event còn phụ thuộc **enabled/threshold/recording period**.

Phân biệt:

- **jdk.JavaMonitorEnter**: contention khi vào monitor.
- **jdk.JavaMonitorWait**: liên quan Object.wait(), không giống mọi monitor entry BLOCKED.
- **jdk.ThreadPark**: việc park thread (chẳng hạn trong một số dạng java.util.concurrent wait), không phải chỉ báo độc lập của mọi deadlock.
- **JFR JavaMonitorEnter Count=0**: không chứng minh không có deadlock, vì event có thể đang chờ hoàn thành hoặc chưa bật.

Với một recording production khác (file phải thực sự tồn tại):

~~~bash
jfr summary incident.jfr
jfr metadata --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark incident.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark incident.jfr
~~~

Các event này chủ yếu cho **bối cảnh contention/park trước khi kẹt**, còn bằng chứng cycle hiện thời nên lấy từ thread snapshots/ThreadMXBean khi JVM còn sống. Recording bắt đầu **sau khi deadlock đã hình thành** không thể tự hồi phục các mốc ACQUIRED_FIRST trước đó.

### Vì sao không bật custom lock events ồ ạt ở production?

Ghi một event cho mỗi lần lock ở tần suất hàng triệu/giây có thể tạo overhead. Chỉ instrument những critical sections hoặc workflow có giá trị, dùng fields nhỏ, thiết lập threshold/retention phù hợp và không ghi secrets. Telemetry cũng có thể thay đổi timing; nên kiểm chứng bằng dữ liệu độc lập.

## 8. Ghép bằng chứng thành bảng và đồ thị

| Câu hỏi | MXBean | jcmd dump | JFR | Code |
| --- | --- | --- | --- | --- |
| A đang BLOCKED không? | getThreadState | BLOCKED entry | Không nhất thiết | Có khả năng |
| A chờ lock do B giữ? | getLockOwnerName/Id | waiting/locked cùng identity | TRY_SECOND(RIGHT) | LEFT → RIGHT |
| B chờ lock do A giữ? | getLockOwnerName/Id | waiting/locked cùng identity | TRY_SECOND(LEFT) | RIGHT → LEFT |
| Có chu trình? | findMonitorDeadlockedThreads | Deadlock section và owner graph | Bối cảnh, chưa đủ | Thiết kế có thể tạo cycle |
| Mốc khởi đầu? | Snapshot time | Dump timestamp | ACQUIRED_FIRST/TRY_SECOND timestamps | Chưa đủ timestamp thực |
| Liệu có progress? | Cùng trạng thái khi đo lại | Chụp nhiều dump | Không có ACQUIRED_SECOND trong demo | Operation không vào critical section tiếp |

**Kết luận mạnh:** MXBean xác nhận A chờ B và B chờ A, jcmd cho cùng quan hệ qua monitor IDs, JFR cho các mốc dẫn tới đối tượng chờ. **Kết luận yếu:** chỉ có hai threads BLOCKED hoặc chỉ thấy một JFR ThreadPark dài.

### Dựng wait-for graph theo từng bước

1. Đặt mỗi **platform thread ID** là một vertex, giữ thread name làm nhãn.
2. Với mỗi thread T có lock owner U được xác minh, tạo cạnh **T → U**.
3. Ghi thêm edge metadata: waiting monitor identity, owner identity, thread state, timestamp.
4. Chạy DFS với trạng thái **WHITE/GRAY/BLACK** để phát hiện back-edge tới vertex GRAY; hoặc dùng thuật toán strongly connected components.
5. Nếu có cycle khép kín, dựng lại chuỗi thread IDs và các monitors trong cycle.
6. Xác nhận bằng nguồn thứ hai cùng khoảng thời gian; không ghép các snapshots từ nhiều lần restart hay nhiều PID vào một graph.

Độ phức tạp DFS là **O(V+E)** cho V threads, E edges sau khi đã đọc đúng lock ownership. Nếu getLockOwnerId()=-1 hoặc owner null, graph **không đầy đủ**; không tự thêm cạnh dựa vào suy đoán.

Một chuỗi A → B → C nhưng C đang chạy và có thể nhả lock **không tạo chu trình**; đó là contention/backpressure hoặc sự cố khác, chưa đủ chứng minh Java deadlock.

## 9. Phân biệt với các tình huống gần giống

| Hiện tượng | Triệu chứng | Cách chứng minh |
| --- | --- | --- |
| Intrinsic monitor deadlock | BLOCKED và owner cycle | jcmd/MXBean monitor identities |
| ReentrantLock deadlock | WAITING/park, ownable synchronizers bị giữ vòng | findDeadlockedThreads + lock ownership |
| Lock contention | A chờ B nhưng B còn chạy và có thể nhả lock | Nhiều snapshots, owner tiến triển |
| Thread pool starvation | Tasks chờ nhau/queue không có worker rảnh | Queue/task dependency graph; có thể MXBean null |
| Livelock | Threads RUNNABLE/retry nhưng không hoàn thành | CPU, retry counters, JFR/progress |
| Socket/file I/O stall | Stack ở network/file call | I/O latency/timeout, downstream metrics |
| Object.wait bình thường | WAITING on monitor | Notifier/condition và hợp đồng chờ |
| Distributed deadlock | Transactions/services khóa tài nguyên liên process | DB locks, transaction IDs, traces |
| Virtual-thread cycle | Java 21 MXBean không thấy đầy đủ | Công cụ hỗ trợ virtual threads và graph dependencies |

**Không suy mọi hang là monitor deadlock.** Đặc biệt database row locks không nằm trong các object monitor Java; phải dùng chẩn đoán phía database nếu vòng chờ nằm ở đó.

## 10. Sửa lỗi bằng một thứ tự lock nhất quán

Với hai monitors, cách đơn giản là yêu cầu **mọi đoạn code** lấy LEFT rồi mới RIGHT, tuyệt đối không có nhánh RIGHT rồi LEFT khi đã giữ một lock.

Đoạn minh họa (chỉ chạy khi LEFT/RIGHT đã được khai báo trong class):

~~~java
private static void updateSafely() {
    synchronized (LEFT) {
        synchronized (RIGHT) {
            // Cập nhật trạng thái chia sẻ.
        }
    }
}
~~~

Điều này loại bỏ **vòng chờ do thứ tự lấy hai locks đảo nhau**. Tuy nhiên contention vẫn có thể tồn tại, và bug khác vẫn có thể gây deadlock nếu bên trong gọi code lấy thêm các locks theo thứ tự không nhất quán.

Đừng xem tăng thread count, timeout HTTP hoặc bật daemon là cách giải quyết deadlock. Chúng không phá được monitor cycle.

### Tại sao test harness cũ phải được thay?

Demo ban đầu yêu cầu **hai worker đều đã nắm lock first của mình** rồi mới cho thử lock thứ hai. Khi đổi cả A và B thành **LEFT → RIGHT**, worker A có thể nắm LEFT rồi chờ worker B báo đã nắm LEFT; B không thể có LEFT để báo, nên chính **CountDownLatch barrier** trở thành điểm chờ vô hạn. Nếu giữ nguyên barrier cũ, bạn sẽ tưởng bản fix không chạy.

Vì vậy, kiểm thử bản sửa dùng một **start latch trước khi vào bất kỳ monitor nào**, cho hai worker bắt đầu gần nhau rồi join với timeout. Không dùng synchronization của test để đòi hai luồng cùng giữ một monitor độc quyền.

## 11. Chương trình Java 17+ thứ hai: SafeLockOrderDemo.java

Đây là chương trình độc lập để xác minh hai workers dùng chung global order đều hoàn thành.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class SafeLockOrderDemo {
    private static final Object LEFT = new Object();
    private static final Object RIGHT = new Object();
    private static final CountDownLatch START =
            new CountDownLatch(1);

    private static void work() {
        synchronized (LEFT) {
            synchronized (RIGHT) {
                // Cả hai workers dùng cùng lock order.
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Thread a = new Thread(() -> {
            try {
                START.await();
                work();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "worker-A");

        Thread b = new Thread(() -> {
            try {
                START.await();
                work();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "worker-B");

        a.start();
        b.start();
        START.countDown();

        a.join(TimeUnit.SECONDS.toMillis(5));
        b.join(TimeUnit.SECONDS.toMillis(5));

        if (a.isAlive() || b.isAlive()) {
            throw new IllegalStateException(
                    "Workers did not finish in time");
        }
        System.out.println("Both workers completed");
    }
}
~~~

~~~bash
javac SafeLockOrderDemo.java
java SafeLockOrderDemo
~~~

Khi hoàn tất bình thường, **stdout chính xác**:

~~~text
Both workers completed
~~~

**Kết luận đúng phạm vi:** chương trình nhỏ này hoàn tất, không có monitor cycle trong hai critical sections đang thử. Nó **không chứng minh** mọi call path của một ứng dụng production đều hết deadlock. Cần code review lock ordering, regression tests trên các đường nested calls và load/chaos tests có điều kiện tái hiện.

### Nếu cần timeout để tránh chờ vô hạn

**ReentrantLock.tryLock(timeout, unit)** có thể giúp từ bỏ lần lấy lock thứ hai và release lock thứ nhất trong finally; nhưng ReentrantLock vẫn deadlock nếu dùng **lock()** theo thứ tự đảo. Nếu retry vô hạn sau timeout, nguy cơ **livelock**. Timeout/retry cần theo hợp đồng nghiệp vụ, có idempotency/backoff và bảo vệ shared-state invariants.

Fragment dưới đây chỉ minh họa khi first/second là hai ReentrantLock, còn updateState/reportRetry là các hàm đã được ứng dụng định nghĩa:

~~~java
if (first.tryLock()) {
    try {
        if (second.tryLock(100, TimeUnit.MILLISECONDS)) {
            try {
                updateState();
            } finally {
                second.unlock();
            }
        } else {
            reportRetry();
        }
    } finally {
        first.unlock();
    }
}
~~~

Phải xử lý trường hợp **first.tryLock() trả false** (ví dụ retry hoặc trả lỗi). Không copy fragment này như chương trình độc lập; nó cần class/variables/import thích hợp.

### Cách giảm khả năng deadlock trong codebase

- Áp dụng **global lock order** theo resource IDs cho mọi call path.
- Không thực hiện network, DB I/O hoặc gọi callback/plugin không kiểm soát trong vùng đang giữ locks.
- Giảm nested locking; dùng immutable snapshots, actor/message passing hoặc concurrent collections khi phù hợp.
- Tránh lock nhiều đối tượng bằng identity hash mà không xử lý collisions/tie-breaker.
- Đặt tên/ghi chú thứ tự khóa trong API contracts và review tự động hóa khi khả thi.
- Monitor tình trạng queue/blocked threads trong production, nhưng tránh polling deadlock detection quá dày vì có overhead.

## 12. Quy trình phản ứng khi deadlock xảy ra trên hệ thống thật

1. **Xác minh đúng JVM**: timestamp, PID, container ID/Pod UID, host, JVM start time, version/build và tình trạng request.
2. **Thu ngay một thread dump** nếu hang/blocked threads là triệu chứng chính. Đừng bắt đầu bằng heap dump lớn khi không có bằng chứng heap retention.
3. **Lấy JFR đang chạy** nếu có để giữ timeline trước khi restart. Một recording mới không tái tạo quá khứ.
4. **Dựng edges** T → owner từ lock identities/ThreadInfo; xác minh cycle và stack frames dẫn đến thứ tự lấy lock.
5. Nếu còn thời gian, lấy snapshot thứ hai, đối chiếu ThreadMXBean/JFR và request queue/GC/I/O.
6. Chỉ can thiệp restart/mitigation khi được phê duyệt; trước đó lưu artifacts an toàn.
7. Sau fix, thiết kế test tái hiện deterministic và kiểm tra tính đúng/throughput, không chỉ “không thấy deadlock trong một run”.

Dữ liệu JFR, thread dump và logs có thể chứa tên method, thông tin nghiệp vụ, paths và thậm chí secrets tùy instrumentation. Bảo vệ bằng access control, encryption/retention thích hợp; không chia sẻ công khai HPROF/JFR/thread dumps của production.

## 13. Những lỗi dễ mắc

1. Thấy hai BLOCKED threads rồi kết luận deadlock mà chưa xem owner cycle.
2. Nhầm WAITING trên CountDownLatch với monitor entry BLOCKED.
3. Dựa vào Thread.sleep để đảm bảo tái hiện race.
4. Tin vào source code mà không chụp trạng thái runtime.
5. Tin custom JFR TRY_SECOND như bằng chứng độc lập của monitor owner.
6. Không thấy jdk.JavaMonitorEnter rồi phủ nhận deadlock.
7. Thấy findDeadlockedThreads() null rồi phủ nhận deadlock ngoài phạm vi MXBean.
8. Dùng thread name làm khóa graph khi nhiều threads trùng tên; cần thread IDs.
9. Nhầm Java thread ID với Linux TID/nid.
10. So Java identityHashCode với địa chỉ internal monitor trong dump.
11. Ghép edges từ hai PID hoặc hai snapshots khác thời điểm.
12. Coi Java monitor deadlock và distributed database deadlock là cùng phạm vi phát hiện.
13. Cho rằng ReentrantLock tự tránh mọi deadlock.
14. Dùng Thread.stop hoặc ngắt BLOCKED synchronized để sửa lỗi.
15. Đổi lock order nhưng giữ barrier test vốn phụ thuộc thứ tự ngược.
16. Bật profiler hoặc event recording quá nặng trên production đang yếu.
17. Chạy jcmd liên tục khi JVM không thể attach, làm mất cửa sổ bằng chứng.
18. Kết luận fix hoàn toàn vì một test nhỏ qua, bỏ qua các call paths khác.

## 14. Bài tập tự kiểm tra

**Câu 1.** Thread dump cho A BLOCKED chờ lock X do B giữ; B BLOCKED chờ lock Y do A giữ. Có cycle không?  
**Đáp án:** Có, nếu các quan hệ waiting/owner thuộc cùng snapshot: **A → B → A**.

**Câu 2.** A BLOCKED chờ B, nhưng B đang RUNNABLE làm I/O rồi sẽ release lock. Có chắc deadlock Java không?  
**Đáp án:** Chưa. Mới có A → B, chưa có B → A tạo cycle. Có thể là contention hoặc I/O stall.

**Câu 3.** JFR lab.LockMilestone ghi 4 events nhưng không ghi ACQUIRED_SECOND. Chỉ thế đã chứng minh deadlock chưa?  
**Đáp án:** Chưa. Nó chứng minh mã đã tới mốc TRY_SECOND nhưng không độc lập xác nhận lock owner; cần ThreadInfo/thread dump.

**Câu 4.** Vì sao một thread chờ synchronized vô hạn có thể không sinh jdk.JavaMonitorEnter instance trong JFR?  
**Đáp án:** Contention event là duration event thường được commit khi thao tác vào monitor hoàn thành; vô hạn chờ có thể không có end, cùng với enabled/threshold restrictions.

**Câu 5.** findMonitorDeadlockedThreads và findDeadlockedThreads khác nhau thế nào?  
**Đáp án:** Bản đầu chỉ xét object monitors; bản sau còn xét ownable synchronizers trên platform threads khi JVM hỗ trợ.

**Câu 6.** Tại sao sửa cả hai threads thành LEFT → RIGHT nhưng vẫn dùng hai latches chờ “mỗi worker đã giữ first lock” có thể làm test đứng?  
**Đáp án:** Vì first lock lúc này trùng nhau và độc quyền: một worker giữ LEFT đợi người kia báo đã giữ LEFT, điều không thể xảy ra. Phải thiết kế lại harness.

**Câu 7.** Trong Java 21, ThreadMXBean trả null có đủ chứng minh không tồn tại virtual-thread deadlock không?  
**Đáp án:** Không. API không hỗ trợ virtual-thread monitoring; cần công cụ và graph tương ứng.

**Câu 8.** Một dump có waiting-to-lock 0xABC ở A và locked 0xABC ở B. Làm gì tiếp?  
**Đáp án:** Tạo edge A → B, kiểm tra B đang chờ monitor do ai giữ, tìm vòng và so với MXBean ở cùng JVM/snapshot window.

## 15. Tài liệu tham khảo

- [Oracle JDK 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): phạm vi platform threads, findMonitorDeadlockedThreads, findDeadlockedThreads và lock information.
- [Oracle JDK 21 — ThreadInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html): Thread.State, getLockOwnerId/Name, getLockedMonitors và getLockedSynchronizers.
- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): Thread.print -l, help, quyền attach và impact.
- [Oracle JDK 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): lấy thread dumps bằng jcmd/jstack và phân tích deadlock/hang.
- [Oracle JDK 21 — JFR Recording](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): enable, start, stop, dump và custom event lifecycle.
- [Oracle JDK 21 — JFR Event](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html): custom event, isEnabled và commit.
- [Oracle JDK 21 — jfr command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): summary, metadata và print.
- [Oracle JDK 21 — Troubleshooting JFR](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html): JavaMonitorEnter/Wait, ThreadPark, event threshold và latency.
